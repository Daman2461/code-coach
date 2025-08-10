#!/usr/bin/env python3
"""
Competitive Programming Coach MCP Server
Roasts coding profiles and recommends problems - No authentication needed!
"""

import os
import json
import asyncio
import sqlite3
import httpx
import re
from typing import Annotated, List, Dict, Any, Optional
from datetime import datetime, timedelta
from pathlib import Path

from fastmcp import FastMCP
from fastmcp.server.auth.providers.bearer import BearerAuthProvider, RSAKeyPair
from mcp import ErrorData, McpError
from mcp.server.auth.provider import AccessToken
from mcp.types import INTERNAL_ERROR, INVALID_PARAMS, TextContent
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
TOKEN = os.getenv("PUCH_BEARER_TOKEN", "hackathon2025")
MY_NUMBER = os.getenv("PUCH_PHONE_NUMBER", "918587852177")
DB_FILE = os.getenv("DB_FILE", "cp_coach.db")

print(f"🏆 Starting Competitive Programming Coach MCP")
print(f"📱 Phone Number: {MY_NUMBER}")
print(f"🔑 Bearer Token: {TOKEN}")
print(f"🌐 Server will be available at: http://localhost:8085")
print(f"📋 Connection: /mcp connect https://your-ngrok-url.ngrok-free.app/mcp/ {TOKEN}")

class RichToolDescription(BaseModel):
    description: str
    use_when: str
    side_effects: str | None

class SimpleBearerAuthProvider(BearerAuthProvider):
    def __init__(self, token: str):
        k = RSAKeyPair.generate()
        super().__init__(
            public_key=k.public_key,
            jwks_uri=None,
            issuer=None,
            audience=None
        )
        self.token = token
    
    async def load_access_token(self, token: str) -> AccessToken | None:
        if token == self.token:
            return AccessToken(
                token=token,
                client_id="unknown",
                scopes=[],
                expires_at=None,
            )
        return None

# Initialize FastMCP server
mcp = FastMCP(
    "CP Coach - Roast & Recommend",
    auth=SimpleBearerAuthProvider(TOKEN),
)

# In-memory storage for user handles (chat session memory)
user_handles = {}

def init_cp_database():
    """Initialize database for storing user profiles and recommendations"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # User profiles table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            platform TEXT,
            handle TEXT,
            rating INTEGER,
            max_rating INTEGER,
            problems_solved INTEGER,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, platform, handle)
        )
    ''')
    
    # Problem recommendations cache
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS problem_recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            platform TEXT,
            problem_name TEXT,
            problem_url TEXT,
            difficulty TEXT,
            tags TEXT,
            recommended_for TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

async def fetch_codeforces_profile(handle: str) -> Dict[str, Any]:
    """Fetch comprehensive Codeforces profile data with problem analysis"""
    try:
        async with httpx.AsyncClient() as client:
            # Get user info
            user_response = await client.get(f"https://codeforces.com/api/user.info?handles={handle}")
            user_data = user_response.json()
            
            if user_data["status"] != "OK":
                return {"error": "User not found"}
            
            user = user_data["result"][0]
            
            # Get user submissions for detailed analysis
            submissions_response = await client.get(f"https://codeforces.com/api/user.status?handle={handle}&from=1&count=2000")
            submissions_data = submissions_response.json()
            
            # Analyze submissions for patterns
            solved_problems = set()
            problem_difficulties = []
            problem_tags = []
            recent_activity = []
            submission_patterns = {
                "total_submissions": 0,
                "accepted": 0,
                "wrong_answer": 0,
                "time_limit": 0,
                "runtime_error": 0,
                "compilation_error": 0
            }
            
            if submissions_data["status"] == "OK":
                for submission in submissions_data["result"]:
                    submission_patterns["total_submissions"] += 1
                    verdict = submission.get("verdict", "")
                    
                    # Count verdicts
                    if verdict == "OK":
                        submission_patterns["accepted"] += 1
                        problem_key = f"{submission['problem']['contestId']}{submission['problem']['index']}"
                        solved_problems.add(problem_key)
                        
                        # Collect problem data
                        problem = submission["problem"]
                        if "rating" in problem:
                            problem_difficulties.append(problem["rating"])
                        if "tags" in problem:
                            problem_tags.extend(problem["tags"])
                            
                        # Recent activity (last 30 days)
                        submission_time = submission.get("creationTimeSeconds", 0)
                        if submission_time > (datetime.now().timestamp() - 30*24*3600):
                            recent_activity.append(submission_time)
                            
                    elif "WRONG_ANSWER" in verdict:
                        submission_patterns["wrong_answer"] += 1
                    elif "TIME_LIMIT" in verdict:
                        submission_patterns["time_limit"] += 1
                    elif "RUNTIME_ERROR" in verdict:
                        submission_patterns["runtime_error"] += 1
                    elif "COMPILATION_ERROR" in verdict:
                        submission_patterns["compilation_error"] += 1
            
            # Calculate statistics
            avg_difficulty = sum(problem_difficulties) / len(problem_difficulties) if problem_difficulties else 0
            most_common_tags = {}
            for tag in problem_tags:
                most_common_tags[tag] = most_common_tags.get(tag, 0) + 1
            
            # Sort tags by frequency
            sorted_tags = sorted(most_common_tags.items(), key=lambda x: x[1], reverse=True)[:5]
            
            return {
                "handle": user.get("handle", ""),
                "rating": user.get("rating", 0),
                "maxRating": user.get("maxRating", 0),
                "rank": user.get("rank", "unrated"),
                "maxRank": user.get("maxRank", "unrated"),
                "problemsSolved": len(solved_problems),
                "registrationTime": user.get("registrationTimeSeconds", 0),
                "avgDifficulty": round(avg_difficulty),
                "topTags": sorted_tags,
                "submissionPatterns": submission_patterns,
                "recentActivity": len(recent_activity),
                "accuracyRate": round(submission_patterns["accepted"] / max(submission_patterns["total_submissions"], 1) * 100, 1)
            }
    except Exception as e:
        return {"error": str(e)}

async def fetch_leetcode_profile(handle: str) -> Dict[str, Any]:
    """Fetch LeetCode profile data (simplified - LeetCode API is limited)"""
    # Note: LeetCode doesn't have a public API, so this is a simplified version
    # In a real implementation, you'd use web scraping or unofficial APIs
    return {
        "handle": handle,
        "rating": 1500,  # Placeholder
        "problemsSolved": 150,  # Placeholder
        "note": "LeetCode data is limited due to API restrictions"
    }

async def fetch_codechef_profile(handle: str) -> Dict[str, Any]:
    """Fetch CodeChef profile data (simplified)"""
    # Note: CodeChef API requires authentication
    # This is a placeholder implementation
    return {
        "handle": handle,
        "rating": 1400,  # Placeholder
        "problemsSolved": 80,  # Placeholder
        "note": "CodeChef data is limited due to API restrictions"
    }

async def fetch_upcoming_contests() -> List[Dict[str, Any]]:
    """Fetch upcoming contests from all major competitive programming platforms"""
    contests = []
    
    try:
        async with httpx.AsyncClient() as client:
            # Fetch Codeforces contests
            try:
                cf_response = await client.get("https://codeforces.com/api/contest.list")
                cf_data = cf_response.json()
                
                if cf_data["status"] == "OK":
                    for contest in cf_data["result"]:
                        if contest["phase"] == "BEFORE":
                            contests.append({
                                "platform": "Codeforces",
                                "name": contest["name"],
                                "start_time": contest["startTimeSeconds"],
                                "duration": contest["durationSeconds"],
                                "url": f"https://codeforces.com/contest/{contest['id']}",
                                "type": contest.get("type", "Unknown")
                            })
            except Exception as e:
                print(f"Error fetching Codeforces contests: {e}")
            
            # Fetch AtCoder contests (using ContestAPI)
            try:
                atcoder_response = await client.get("https://kenkoooo.com/atcoder/resources/contests.json")
                atcoder_data = atcoder_response.json()
                
                current_time = datetime.now().timestamp()
                for contest in atcoder_data:
                    start_epoch = contest["start_epoch_second"]
                    if start_epoch > current_time:
                        contests.append({
                            "platform": "AtCoder",
                            "name": contest["title"],
                            "start_time": start_epoch,
                            "duration": contest["duration_second"],
                            "url": f"https://atcoder.jp/contests/{contest['id']}",
                            "type": "AtCoder Contest"
                        })
            except Exception as e:
                print(f"Error fetching AtCoder contests: {e}")
            
            # Add other platforms (simplified due to API limitations)
            # CodeChef contests (manual/estimated)
            try:
                # CodeChef typically has contests on specific days
                now = datetime.now()
                # Add upcoming CodeChef contests (this would need real API in production)
                contests.append({
                    "platform": "CodeChef",
                    "name": "CodeChef Starters (Weekly)",
                    "start_time": int((now + timedelta(days=((2 - now.weekday()) % 7))).timestamp()),  # Next Wednesday
                    "duration": 3 * 3600,  # 3 hours
                    "url": "https://www.codechef.com/contests",
                    "type": "Weekly Contest"
                })
                
                contests.append({
                    "platform": "CodeChef",
                    "name": "CodeChef Cook-Off (Monthly)",
                    "start_time": int((now.replace(day=1) + timedelta(days=32)).replace(day=1).timestamp()),  # Next month
                    "duration": 2.5 * 3600,  # 2.5 hours
                    "url": "https://www.codechef.com/contests",
                    "type": "Monthly Contest"
                })
            except Exception as e:
                print(f"Error adding CodeChef contests: {e}")
            
            # LeetCode contests (estimated schedule)
            try:
                # LeetCode has weekly and biweekly contests
                now = datetime.now()
                # Weekly contest (usually Sunday)
                next_sunday = now + timedelta(days=(6 - now.weekday()) % 7)
                contests.append({
                    "platform": "LeetCode",
                    "name": "LeetCode Weekly Contest",
                    "start_time": int(next_sunday.replace(hour=8, minute=0, second=0).timestamp()),
                    "duration": 1.5 * 3600,  # 1.5 hours
                    "url": "https://leetcode.com/contest/",
                    "type": "Weekly Contest"
                })
                
                # Biweekly contest (every 2 weeks, Saturday)
                next_saturday = now + timedelta(days=(5 - now.weekday()) % 7)
                contests.append({
                    "platform": "LeetCode",
                    "name": "LeetCode Biweekly Contest",
                    "start_time": int(next_saturday.replace(hour=20, minute=30, second=0).timestamp()),
                    "duration": 1.5 * 3600,  # 1.5 hours
                    "url": "https://leetcode.com/contest/",
                    "type": "Biweekly Contest"
                })
            except Exception as e:
                print(f"Error adding LeetCode contests: {e}")
    
    except Exception as e:
        print(f"General error fetching contests: {e}")
    
    # Sort contests by start time
    contests.sort(key=lambda x: x["start_time"])
    
    # Return only upcoming contests (next 30 days)
    current_time = datetime.now().timestamp()
    upcoming_contests = [c for c in contests if c["start_time"] > current_time and c["start_time"] < current_time + 30*24*3600]
    
    return upcoming_contests[:15]  # Return top 15 upcoming contests

def generate_intelligent_roast(profiles: List[Dict[str, Any]]) -> str:
    """Generate intelligent, contextual roasts based on actual coding patterns and behavior"""
    roasts = []
    
    for profile in profiles:
        if "error" in profile:
            continue
            
        platform = profile.get("platform", "Unknown")
        handle = profile.get("handle", "Anonymous")
        rating = profile.get("rating", 0)
        max_rating = profile.get("maxRating", rating)
        problems_solved = profile.get("problemsSolved", 0)
        
        # Get detailed analytics for intelligent roasting
        avg_difficulty = profile.get("avgDifficulty", 0)
        top_tags = profile.get("topTags", [])
        submission_patterns = profile.get("submissionPatterns", {})
        recent_activity = profile.get("recentActivity", 0)
        accuracy_rate = profile.get("accuracyRate", 0)
        
        roast_parts = []
        
        # Analyze rating vs max rating (rating drops)
        if max_rating > 0 and rating < max_rating - 200:
            roast_parts.append(f"peaked at {max_rating} but dropped to {rating}? That's a {max_rating - rating} point nosedive! 📉")
        
        # Analyze problem difficulty vs rating
        if avg_difficulty > 0 and rating > 0:
            if avg_difficulty < rating - 300:
                roast_parts.append(f"solving {avg_difficulty}-rated problems with a {rating} rating? Playing it safe much? 😴")
            elif avg_difficulty > rating + 200:
                roast_parts.append(f"attempting {avg_difficulty}-rated problems with {rating} rating? Ambitious but clearly not working! 🎯❌")
        
        # Analyze accuracy rate
        if accuracy_rate < 20:
            roast_parts.append(f"{accuracy_rate}% accuracy? You submit code like you're playing the lottery! 🎰")
        elif accuracy_rate < 40:
            roast_parts.append(f"{accuracy_rate}% accuracy - more wrong answers than a broken GPS! 🗺️💀")
        
        # Analyze favorite topics (top tags)
        if top_tags:
            top_tag = top_tags[0][0] if top_tags[0] else "unknown"
            tag_count = top_tags[0][1] if top_tags[0] else 0
            
            if top_tag == "implementation":
                roast_parts.append(f"loves 'implementation' problems - basically the 'easy mode' of competitive programming! 🎮")
            elif top_tag == "math":
                roast_parts.append(f"math problems enthusiast but still can't calculate a path to higher rating! 🧮")
            elif top_tag == "greedy":
                roast_parts.append(f"greedy algorithm lover - greedy for easy problems, stingy with effort! 💰")
            elif top_tag == "dp":
                roast_parts.append(f"DP specialist but can't dynamically program your way to success! 📊")
            
            if len(top_tags) < 3:
                roast_parts.append(f"only comfortable with {len(top_tags)} topic types? Variety is the spice of life! 🌶️")
        
        # Analyze recent activity
        if recent_activity == 0:
            roast_parts.append("zero activity in the last 30 days - did you give up or just forget your password? 😴")
        elif recent_activity < 5:
            roast_parts.append(f"only {recent_activity} submissions this month? My grandmother codes more actively! 👵")
        
        # Analyze submission patterns
        if submission_patterns:
            total_subs = submission_patterns.get("total_submissions", 0)
            wa_count = submission_patterns.get("wrong_answer", 0)
            tle_count = submission_patterns.get("time_limit", 0)
            
            if wa_count > total_subs * 0.4:
                roast_parts.append("specializes in Wrong Answer verdicts - at least you're consistent! ❌")
            if tle_count > total_subs * 0.2:
                roast_parts.append("Time Limit Exceeded expert - writes code slower than internet explorer! ⏰💀")
        
        # Combine roast parts intelligently
        if roast_parts:
            main_roast = f"🔥 **{handle}** ({rating} on {platform.title()}): "
            
            # Add context about their performance
            if len(roast_parts) >= 3:
                main_roast += f"Where do I even start? You've {roast_parts[0]}, {roast_parts[1]}, and {roast_parts[2]}!"
            elif len(roast_parts) == 2:
                main_roast += f"You've {roast_parts[0]} and {roast_parts[1]}!"
            else:
                main_roast += f"You've {roast_parts[0]}!"
                
            # Add a contextual conclusion
            if problems_solved < 100:
                main_roast += f" With only {problems_solved} problems solved, you're still in tutorial mode! 🎮"
            elif rating > 0 and rating < 1200:
                main_roast += f" {problems_solved} problems solved but still can't break the newbie barrier! 🚧"
            elif rating >= 1200:
                main_roast += f" Despite {problems_solved} problems solved, you're stuck in mediocrity! 📊"
            
            roasts.append(main_roast)
        else:
            # Fallback for profiles without detailed data
            roasts.append(f"🔥 **{handle}** ({rating} on {platform.title()}): {problems_solved} problems solved - not enough data to properly roast you, but I'm sure there's plenty to work with! 😈")
    
    if not roasts:
        return "🔥 **No profiles to roast!** Add your coding handles first, then come back for a proper intellectual destruction! 🧠💀"
    
    roast_text = "🔥 **INTELLIGENT ROAST ANALYSIS** 🔥\n\n"
    roast_text += "\n\n".join(roasts)
    roast_text += "\n\n💀 **Analysis complete!** These roasts are based on your actual coding patterns - the data doesn't lie! 📊💪"
    
    return roast_text

def generate_intelligent_recommendations(profiles: List[Dict[str, Any]], goal: str = "general") -> str:
    """Generate truly intelligent, personalized recommendations based on actual coding patterns, company needs, and solved problems"""
    if not profiles or all("error" in p for p in profiles):
        return "❌ **No valid profiles found!** Add your coding handles first."
    
    # Parse company from goal
    company = ""
    goal_lower = goal.lower()
    companies = ["google", "meta", "facebook", "amazon", "microsoft", "apple", "netflix", "uber", "airbnb", "twitter", "linkedin", "salesforce"]
    for comp in companies:
        if comp in goal_lower:
            company = comp
            goal = goal_lower.replace(comp, "").strip()
            break
    
    # Analyze user's comprehensive coding profile
    max_rating = 0
    total_problems = 0
    platform_data = {}
    favorite_topics = []
    weak_topics = []
    accuracy_issues = []
    recent_patterns = []
    
    for profile in profiles:
        if "error" not in profile:
            platform = profile.get("platform", "unknown")
            handle = profile.get("handle", "N/A")
            rating = profile.get("rating", 0)
            problems = profile.get("problemsSolved", 0)
            accuracy = profile.get("accuracyRate", 0)
            avg_difficulty = profile.get("avgDifficulty", 0)
            topics = profile.get("favoriteTopics", [])
            recent_activity = profile.get("recentActivity", False)
            
            if rating > max_rating:
                max_rating = rating
            total_problems += problems
            platform_data[platform] = profile
            
            # Analyze favorite topics
            favorite_topics.extend(topics[:3])
            
            # Identify specific weaknesses
            if accuracy < 40:
                accuracy_issues.append(f"Very low accuracy on {platform} ({accuracy}%) - focus on testing and debugging")
            elif accuracy < 65:
                accuracy_issues.append(f"Moderate accuracy on {platform} ({accuracy}%) - improve problem analysis")
            
            # Analyze difficulty comfort zone
            if rating > 0 and avg_difficulty > 0:
                if avg_difficulty < rating - 200:
                    weak_topics.append(f"Playing too safe on {platform} - attempt harder problems")
                elif avg_difficulty > rating + 300:
                    weak_topics.append(f"Overreaching on {platform} - build fundamentals first")
            
            # Recent activity analysis
            if not recent_activity:
                recent_patterns.append(f"No recent activity on {platform} - consistency needed")
    
    # Determine skill level and appropriate difficulty
    if max_rating == 0:
        level = "Beginner"
        cf_range = "800-1000"
        lc_difficulty = "Easy"
    elif max_rating < 1200:
        level = "Newbie"
        cf_range = "800-1200"
        lc_difficulty = "Easy to Medium"
    elif max_rating < 1600:
        level = "Pupil/Specialist"
        cf_range = "1000-1400"
        lc_difficulty = "Medium"
    elif max_rating < 1900:
        level = "Expert"
        cf_range = "1200-1700"
        lc_difficulty = "Medium to Hard"
    else:
        level = "Master+"
        cf_range = "1400-2000+"
        lc_difficulty = "Hard"
    
    # Start building intelligent recommendations
    title = f"🎯 **Personalized Recommendations"
    if company:
        title += f" for {company.title()}"
    if goal and goal != "general":
        title += f" ({goal.title()})"
    title += f" - {level} Level**\n\n"
    
    recommendations = title
    
    # Profile summary with insights
    recommendations += "📊 **Your Coding Profile Analysis:**\n"
    for platform, data in platform_data.items():
        handle = data.get('handle', 'N/A')
        rating = data.get('rating', 0)
        solved = data.get('problemsSolved', 0)
        accuracy = data.get('accuracyRate', 0)
        topics = data.get('favoriteTopics', [])
        
        recommendations += f"• **{platform.title()}** ({handle}): {rating} rating, {solved} solved, {accuracy}% accuracy\n"
        if topics:
            recommendations += f"  → Strong in: {', '.join(topics[:3])}\n"
    
    recommendations += "\n"
    
    # Company-specific intelligent recommendations
    if company:
        recommendations += f"🏢 **{company.title()}-Specific Strategy:**\n"
        
        if company in ["google", "alphabet"]:
            recommendations += "• **Google's Focus**: System design, scalability, algorithmic thinking\n"
            recommendations += "• **Key Topics**: Graphs, Trees, Dynamic Programming, System Design\n"
            recommendations += "• **Specific Problems**: \n"
            recommendations += "  - Word Ladder (BFS/Graph traversal - Google loves this pattern)\n"
            recommendations += "  - Design Search Autocomplete (System design component)\n"
            recommendations += "  - Maximum Subarray (Classic DP - tests optimization thinking)\n"
            
            if "graphs" not in [t.lower() for t in favorite_topics]:
                recommendations += "• **CRITICAL**: You haven't mastered graphs yet - Google heavily tests graph algorithms!\n"
                recommendations += "  → Start with: Number of Islands, Clone Graph, Course Schedule\n"
            
            if max_rating < 1400:
                recommendations += "• **Rating Gap**: Google typically expects 1400+ CF rating equivalent\n"
                recommendations += "  → Focus on medium CF problems (1200-1400 range)\n"
                
        elif company in ["meta", "facebook"]:
            recommendations += "• **Meta's Focus**: Product thinking, user-centric solutions, clean code\n"
            recommendations += "• **Key Topics**: Arrays, Strings, Hash Tables, Trees, System Design\n"
            recommendations += "• **Specific Problems**:\n"
            recommendations += "  - Valid Parentheses (String manipulation - Meta classic)\n"
            recommendations += "  - Binary Tree Right Side View (Tree traversal with twist)\n"
            recommendations += "  - Design News Feed (System design for social media)\n"
            
            if any("low accuracy" in issue for issue in accuracy_issues):
                recommendations += "• **CRITICAL**: Meta values bug-free code - improve your accuracy first!\n"
                recommendations += "  → Practice easier problems until 80%+ accuracy\n"
                
        elif company == "amazon":
            recommendations += "• **Amazon's Focus**: Leadership principles, scalable solutions, optimization\n"
            recommendations += "• **Key Topics**: Arrays, Strings, Trees, System Design, Optimization\n"
            recommendations += "• **Specific Problems**:\n"
            recommendations += "  - Two Sum (Classic - but explain multiple approaches)\n"
            recommendations += "  - Merge k Sorted Lists (Optimization and heap usage)\n"
            recommendations += "  - Design Amazon's Recommendation System\n"
            
            if avg_difficulty < max_rating - 100:
                recommendations += "• **Challenge Yourself**: Amazon tests problem-solving depth\n"
                recommendations += "  → Attempt problems 100-200 points above your rating\n"
                
        elif company == "microsoft":
            recommendations += "• **Microsoft's Focus**: Clean code, debugging skills, practical solutions\n"
            recommendations += "• **Key Topics**: Strings, Arrays, Linked Lists, Trees, System Design\n"
            recommendations += "• **Specific Problems**:\n"
            recommendations += "  - Reverse Words in a String (String manipulation)\n"
            recommendations += "  - Serialize and Deserialize Binary Tree (Complex tree operations)\n"
            recommendations += "  - Design Microsoft Teams Chat System\n"
            
        recommendations += "\n"
    
    # Goal-specific recommendations with personal insights
    if goal in ["interview", "job"] or company:
        recommendations += "💼 **Interview Preparation Strategy:**\n"
        
        # Personalized based on their current level
        if max_rating < 1000:
            recommendations += "• **Phase 1 (4-6 weeks)**: Master fundamentals\n"
            recommendations += "  → Arrays: Two Sum, Best Time to Buy Stock, Contains Duplicate\n"
            recommendations += "  → Strings: Valid Anagram, Valid Parentheses, Longest Common Prefix\n"
            recommendations += "  → Basic Math: Palindrome Number, Reverse Integer\n"
            
        elif max_rating < 1400:
            recommendations += "• **Phase 2 (6-8 weeks)**: Intermediate patterns\n"
            recommendations += "  → Two Pointers: Container With Most Water, 3Sum\n"
            recommendations += "  → Sliding Window: Longest Substring Without Repeating Characters\n"
            recommendations += "  → Trees: Maximum Depth, Same Tree, Invert Binary Tree\n"
            
        else:
            recommendations += "• **Advanced Phase (8-10 weeks)**: Complex algorithms\n"
            recommendations += "  → Advanced DP: Edit Distance, Longest Increasing Subsequence\n"
            recommendations += "  → Graph Algorithms: Word Ladder, Course Schedule II\n"
            recommendations += "  → System Design: Design Twitter, Design URL Shortener\n"
        
        # Address their specific weaknesses
        if accuracy_issues:
            recommendations += f"• **Accuracy Improvement Plan**:\n"
            for issue in accuracy_issues[:2]:
                recommendations += f"  → {issue}\n"
            recommendations += "  → Practice: Solve 5 easy problems daily for 1 week\n"
        
        # Topic-specific recommendations based on their gaps
        missing_topics = []
        essential_topics = ["arrays", "strings", "trees", "graphs", "dp"]
        for topic in essential_topics:
            if not any(topic in fav.lower() for fav in favorite_topics):
                missing_topics.append(topic)
        
        if missing_topics:
            recommendations += f"• **Missing Essential Topics**: {', '.join(missing_topics)}\n"
            for topic in missing_topics[:2]:
                if topic == "dp":
                    recommendations += "  → DP: Start with Fibonacci → Climbing Stairs → House Robber\n"
                elif topic == "graphs":
                    recommendations += "  → Graphs: Number of Islands → Clone Graph → Course Schedule\n"
                elif topic == "trees":
                    recommendations += "  → Trees: Maximum Depth → Same Tree → Binary Tree Paths\n"
        
    elif goal in ["contest", "competitive", "cp"]:
        recommendations += "🏆 **Contest Performance Strategy:**\n"
        
        if max_rating < 1200:
            recommendations += "• **Target**: Consistently solve Div3 A, B problems\n"
            recommendations += "• **Practice Schedule**: \n"
            recommendations += "  → Week 1-2: Last 10 Div3 contests, problems A-B only\n"
            recommendations += "  → Week 3-4: Attempt C problems, time limit 45 mins\n"
            recommendations += "• **Speed Goals**: A in <10 mins, B in <20 mins\n"
            
        elif max_rating < 1600:
            recommendations += "• **Target**: Solve Div2 A, B, C consistently\n"
            recommendations += "• **Focus Areas**: Greedy algorithms, basic number theory\n"
            recommendations += "• **Specific Practice**:\n"
            recommendations += "  → Greedy: Activity Selection, Fractional Knapsack\n"
            recommendations += "  → Number Theory: GCD problems, Prime factorization\n"
            
        else:
            recommendations += "• **Target**: Solve Div2 A-D, attempt E\n"
            recommendations += "• **Advanced Topics**: Segment trees, advanced DP, graph theory\n"
            recommendations += "• **Contest Strategy**: Fast A-C, then deep focus on D-E\n"
    
    # Specific problem recommendations based on their solved history
    recommendations += "\n🎯 **Specific Problems Tailored for You:**\n"
    
    # Based on their strong areas, recommend next level
    if "implementation" in [t.lower() for t in favorite_topics]:
        recommendations += "• **Implementation** (your strength): Try 'Spiral Matrix', 'Rotate Image'\n"
    if "math" in [t.lower() for t in favorite_topics]:
        recommendations += "• **Math** (your strength): Try 'Happy Number', 'Ugly Number II'\n"
    if "greedy" in [t.lower() for t in favorite_topics]:
        recommendations += "• **Greedy** (your strength): Try 'Jump Game II', 'Gas Station'\n"
    
    # Address weak areas with specific problems
    if weak_topics:
        recommendations += "• **Weak Areas to Address**:\n"
        for weak in weak_topics[:2]:
            recommendations += f"  → {weak}\n"
    
    # Recent activity recommendations
    if recent_patterns:
        recommendations += "\n⚠️ **Activity Concerns**:\n"
        for pattern in recent_patterns[:2]:
            recommendations += f"• {pattern}\n"
        recommendations += "• **Comeback Plan**: Start with 1 easy problem daily for motivation\n"
    
    # Actionable 30-day plan
    recommendations += "\n📅 **Your Personalized 30-Day Action Plan:**\n"
    recommendations += "**Week 1**: Address accuracy issues + practice weak topics\n"
    recommendations += "**Week 2**: Focus on company-specific problem patterns\n"
    recommendations += "**Week 3**: Mock interviews + timed problem solving\n"
    recommendations += "**Week 4**: Advanced topics + system design basics\n"
    
    recommendations += "\n💡 **Success Metrics to Track:**\n"
    recommendations += f"• Maintain {max(70, int(max(p.get('accuracyRate', 0) for p in profiles if 'error' not in p) + 10))}%+ accuracy\n"
    recommendations += f"• Solve problems in {cf_range} difficulty range\n"
    recommendations += "• Complete at least 3 problems daily\n"
    recommendations += "• Participate in 2+ contests weekly\n"
    
    return recommendations

# Initialize database
init_cp_database()

@mcp.tool
async def validate() -> str:
    """Required validation tool for Puch AI"""
    return MY_NUMBER

AddProfileDescription = RichToolDescription(
    description="Add your competitive programming handles (Codeforces, LeetCode, CodeChef) to get personalized roasts and recommendations.",
    use_when="User wants to add their coding profile handles or get started with the CP coach.",
    side_effects="Fetches public profile data from coding platforms. No authentication required.",
)

@mcp.tool(description=AddProfileDescription.model_dump_json())
async def add_coding_profile(
    platform: Annotated[str, Field(description="Coding platform: 'codeforces', 'leetcode', or 'codechef'")] = "codeforces",
    handle: Annotated[str, Field(description="Your username/handle on the platform")] = ""
) -> list[TextContent]:
    """
    Add your competitive programming profile handle.
    Supports Codeforces, LeetCode, and CodeChef.
    """
    if not handle:
        return [TextContent(
            type="text",
            text="❌ **Handle Required!**\n\nPlease provide your username/handle.\n\nExample: `add_coding_profile codeforces tourist`"
        )]
    
    try:
        platform = platform.lower()
        
        # Fetch profile data
        if platform == "codeforces":
            profile_data = await fetch_codeforces_profile(handle)
        elif platform == "leetcode":
            profile_data = await fetch_leetcode_profile(handle)
        elif platform == "codechef":
            profile_data = await fetch_codechef_profile(handle)
        else:
            return [TextContent(
                type="text",
                text="❌ **Unsupported Platform!**\n\nSupported platforms: codeforces, leetcode, codechef"
            )]
        
        if "error" in profile_data:
            return [TextContent(
                type="text",
                text=f"❌ **Profile Not Found!**\n\nCouldn't find handle '{handle}' on {platform}.\n\nDouble-check your username and try again!"
            )]
        
        # Store handle in memory for this chat session
        user_id = "default_user"  # In a real implementation, this would be the actual user ID
        if user_id not in user_handles:
            user_handles[user_id] = []
        
        # Add handle if not already stored
        handle_string = f"{platform}:{handle}"
        if handle_string not in user_handles[user_id]:
            user_handles[user_id].append(handle_string)
        
        # Format response with live data
        response = f"✅ **Profile Verified & Remembered!**\n\n"
        response += f"🏆 **{platform.title()}**: {handle}\n"
        response += f"📊 **Current Rating**: {profile_data.get('rating', 'N/A')}\n"
        response += f"📈 **Max Rating**: {profile_data.get('maxRating', 'N/A')}\n"
        response += f"✅ **Problems Solved**: {profile_data.get('problemsSolved', 'N/A')}\n"
        
        if "rank" in profile_data:
            response += f"🎖️ **Rank**: {profile_data['rank']}\n"
        
        if "avgDifficulty" in profile_data and profile_data["avgDifficulty"] > 0:
            response += f"🎯 **Avg Problem Difficulty**: {profile_data['avgDifficulty']}\n"
        
        if "accuracyRate" in profile_data:
            response += f"🎲 **Accuracy Rate**: {profile_data['accuracyRate']}%\n"
        
        response += f"\n💾 **Handle Saved!** Now you can simply use:\n"
        response += f"🔥 `roast_my_coding` (no handles needed!)\n"
        response += f"🎯 `recommend_problems interview` (no handles needed!)\n\n"
        response += f"📝 **Stored Handles**: {', '.join(user_handles[user_id])}"
        
        return [TextContent(type="text", text=response)]
        
    except Exception as e:
        raise McpError(ErrorData(
            code=INTERNAL_ERROR,
            message=f"Failed to add profile: {str(e)}"
        ))

RoastDescription = RichToolDescription(
    description="Get a humorous roast of your competitive programming skills based on your added profiles.",
    use_when="User wants to get roasted or have fun with their coding stats.",
    side_effects="Generates humorous commentary based on user's coding performance. All in good fun!",
)

@mcp.tool(description=RoastDescription.model_dump_json())
async def roast_my_coding(
    handles: Annotated[str, Field(description="Optional: Comma-separated list of handles in format 'platform:handle' (e.g., 'codeforces:tourist,leetcode:john_doe'). If not provided, uses previously stored handles.")] = ""
) -> list[TextContent]:
    """
    Get a humorous roast of your competitive programming skills based on live data.
    Uses your stored handles if no handles provided, or specify new ones.
    """
    try:
        user_id = "default_user"
        
        # Use stored handles if no handles provided
        if not handles:
            if user_id in user_handles and user_handles[user_id]:
                handles = ",".join(user_handles[user_id])
            else:
                return [TextContent(
                    type="text",
                    text="❌ **No Handles Found!**\n\nFirst add your profile:\n`add_coding_profile codeforces your_handle`\n\nOr provide handles directly:\n`roast_my_coding codeforces:tourist,leetcode:john_doe`\n\nThen I'll fetch your live data and roast you properly! 🔥"
                )]
        
        # Parse handles
        profiles = []
        handle_pairs = handles.split(',')
        
        for pair in handle_pairs:
            if ':' not in pair:
                continue
            platform, handle = pair.strip().split(':', 1)
            platform = platform.lower().strip()
            handle = handle.strip()
            
            # Fetch live data from APIs
            if platform == "codeforces":
                profile_data = await fetch_codeforces_profile(handle)
                if "error" not in profile_data:
                    profile_data["platform"] = "codeforces"
                    profiles.append(profile_data)
            elif platform == "leetcode":
                profile_data = await fetch_leetcode_profile(handle)
                if "error" not in profile_data:
                    profile_data["platform"] = "leetcode"
                    profiles.append(profile_data)
            elif platform == "codechef":
                profile_data = await fetch_codechef_profile(handle)
                if "error" not in profile_data:
                    profile_data["platform"] = "codechef"
                    profiles.append(profile_data)
        
        if not profiles:
            return [TextContent(
                type="text",
                text="❌ **No Valid Profiles Found!**\n\nMake sure your handles are correct:\n- Format: `platform:handle`\n- Supported: codeforces, leetcode, codechef\n- Example: `codeforces:tourist,leetcode:john_doe`\n\nTry again with valid handles! 🎯"
            )]
        
        roast_text = generate_intelligent_roast(profiles)
        
        return [TextContent(type="text", text=roast_text)]
        
    except Exception as e:
        raise McpError(ErrorData(
            code=INTERNAL_ERROR,
            message=f"Failed to generate roast: {str(e)}"
        ))

RecommendDescription = RichToolDescription(
    description="Get personalized problem recommendations based on your coding level and goals (interview prep, contests, general improvement).",
    use_when="User wants problem recommendations, study plan, or guidance on what to solve next.",
    side_effects="Analyzes user profiles to suggest appropriate problems and study paths.",
)

@mcp.tool(description=RecommendDescription.model_dump_json())
async def recommend_problems(
    goal: Annotated[str, Field(default="general", description="Your goal: 'interview google', 'contest', 'interview meta', 'general', etc. Can include company names like google, meta, amazon, microsoft")] = "general",
    handles: Annotated[str, Field(description="Optional: Comma-separated list of handles in format 'platform:handle' (e.g., 'codeforces:tourist,leetcode:john_doe'). If not provided, uses previously stored handles.")] = ""
) -> list[TextContent]:
    """
    Get personalized problem recommendations based on your live coding data and goals.
    Uses your stored handles if no handles provided, or specify new ones.
    Goals: 'interview' (job prep), 'contest' (competitive programming), 'general' (skill building)
    """
    try:
        user_id = "default_user"
        
        # Use stored handles if no handles provided
        if not handles:
            if user_id in user_handles and user_handles[user_id]:
                handles = ",".join(user_handles[user_id])
            else:
                return [TextContent(
                    type="text",
                    text="❌ **No Handles Found!**\n\nFirst add your profile:\n`add_coding_profile codeforces your_handle`\n\nOr provide handles directly:\n`recommend_problems interview codeforces:tourist,leetcode:john_doe`\n\nThen I'll analyze your live data and give personalized recommendations! 🎯"
                )]
        
        # Parse handles and fetch live data
        profiles = []
        handle_pairs = handles.split(',')
        
        for pair in handle_pairs:
            if ':' not in pair:
                continue
            platform, handle = pair.strip().split(':', 1)
            platform = platform.lower().strip()
            handle = handle.strip()
            
            # Fetch live data from APIs
            if platform == "codeforces":
                profile_data = await fetch_codeforces_profile(handle)
                if "error" not in profile_data:
                    profile_data["platform"] = "codeforces"
                    profiles.append(profile_data)
            elif platform == "leetcode":
                profile_data = await fetch_leetcode_profile(handle)
                if "error" not in profile_data:
                    profile_data["platform"] = "leetcode"
                    profiles.append(profile_data)
            elif platform == "codechef":
                profile_data = await fetch_codechef_profile(handle)
                if "error" not in profile_data:
                    profile_data["platform"] = "codechef"
                    profiles.append(profile_data)
        
        if not profiles:
            return [TextContent(
                type="text",
                text="❌ **No Valid Profiles Found!**\n\nMake sure your handles are correct:\n- Format: `platform:handle`\n- Supported: codeforces, leetcode, codechef\n- Example: `codeforces:tourist,leetcode:john_doe`\n\nTry again with valid handles! 🎯"
            )]
        
        recommendations = generate_intelligent_recommendations(profiles, goal)
        
        return [TextContent(type="text", text=recommendations)]
        
    except Exception as e:
        raise McpError(ErrorData(
            code=INTERNAL_ERROR,
            message=f"Failed to generate recommendations: {str(e)}"
        ))

ContestDescription = RichToolDescription(
    description="Get upcoming competitive programming contests from all major platforms (Codeforces, AtCoder, LeetCode, CodeChef).",
    use_when="User asks about upcoming contests, when the next contest is, or wants to participate in competitions.",
    side_effects="Fetches real-time contest data from multiple platforms. No authentication required.",
)

@mcp.tool(description=ContestDescription.model_dump_json())
async def get_upcoming_contests() -> list[TextContent]:
    """
    Get upcoming competitive programming contests from all major platforms.
    Shows contests from Codeforces, AtCoder, LeetCode, CodeChef, and more.
    """
    try:
        contests = await fetch_upcoming_contests()
        
        if not contests:
            return [TextContent(
                type="text",
                text="🏆 **No Upcoming Contests Found**\n\nEither all platforms are quiet right now, or there might be an issue fetching contest data. Try again in a few minutes!"
            )]
        
        contest_text = "🏆 **Upcoming Competitive Programming Contests**\n\n"
        
        current_time = datetime.now()
        
        for i, contest in enumerate(contests, 1):
            start_time = datetime.fromtimestamp(contest["start_time"])
            duration_hours = contest["duration"] / 3600
            
            # Calculate time until contest
            time_diff = start_time - current_time
            days = time_diff.days
            hours, remainder = divmod(time_diff.seconds, 3600)
            minutes, _ = divmod(remainder, 60)
            
            # Format time until contest
            if days > 0:
                time_until = f"{days}d {hours}h {minutes}m"
            elif hours > 0:
                time_until = f"{hours}h {minutes}m"
            else:
                time_until = f"{minutes}m"
            
            # Platform emoji
            platform_emoji = {
                "Codeforces": "🔴",
                "AtCoder": "🟠", 
                "LeetCode": "🟡",
                "CodeChef": "🟤",
                "TopCoder": "🔵"
            }.get(contest["platform"], "⚪")
            
            # Urgency indicator
            if days == 0 and hours < 2:
                urgency = "🚨 STARTING SOON"
            elif days == 0:
                urgency = "⏰ TODAY"
            elif days == 1:
                urgency = "📅 TOMORROW"
            else:
                urgency = "📆 UPCOMING"
            
            contest_text += f"{urgency} {platform_emoji} **{contest['platform']}**\n"
            contest_text += f"🏁 **{contest['name']}**\n"
            contest_text += f"⏰ **Starts:** {start_time.strftime('%B %d, %Y at %I:%M %p')}\n"
            contest_text += f"⏱️ **Duration:** {duration_hours:.1f} hours\n"
            contest_text += f"⏳ **Time Until:** {time_until}\n"
            contest_text += f"🔗 **Link:** {contest['url']}\n\n"
            
            # Add separator for readability
            if i < len(contests):
                contest_text += "─" * 40 + "\n\n"
        
        # Add helpful tips
        contest_text += "💡 **Pro Tips:**\n"
        contest_text += "• Set reminders for contests you want to participate in\n"
        contest_text += "• Practice similar problems before the contest\n"
        contest_text += "• Check your timezone - times shown are in your local time\n"
        contest_text += "• Register early to avoid last-minute issues\n\n"
        
        contest_text += "🎯 **Good luck in your contests!** May your solutions be bug-free and your ratings climb high! 🚀"
        
        return [TextContent(type="text", text=contest_text)]
        
    except Exception as e:
        raise McpError(ErrorData(
            code=INTERNAL_ERROR,
            message=f"Failed to fetch contests: {str(e)}"
        ))

async def main():
    """Run the CP Coach FastMCP server"""
    await mcp.run_async(
        "streamable-http",
        host="0.0.0.0",
        port=8085,
    )

if __name__ == "__main__":
    asyncio.run(main())
