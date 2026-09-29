# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import base64
import concurrent.futures
import datetime
import json
import os
import re
import sys
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Ensure project root is in sys.path so modules can be run from any working directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.cloud import firestore
from google.genai import Client, types

import uuid

try:
    from app.a2ui_utils import a2ui_callback
except ImportError:
    from a2ui_utils import a2ui_callback

# Active In-Memory & Firestore Chat Sessions Storage
CHAT_SESSIONS: Dict[str, Dict] = {}
IN_MEMORY_SESSIONS: Dict[str, List[Dict]] = {}

try:
    db = firestore.Client(project="project-281bf799-969f-49aa-917")
except Exception:
    db = None


VALID_CATEGORIES = ["Workouts", "Nutrition", "Recovery", "General"]


def categorize_and_title_session(first_prompt: str) -> tuple[str, str]:
    """Silently generates a 3-4 word title AND assigns a category tag ('Workouts', 'Nutrition', 'Recovery', or 'General')."""
    if not first_prompt or not first_prompt.strip():
        return ("New Conversation", "General")
    
    clean = first_prompt.strip()
    clean_lower = clean.lower()
    
    category = "General"
    title = None
    
    # Check Workouts signals
    workout_keywords = [
        "workout", "workouts", "strength", "mobility", "kettlebell", "dumbbell", "cycling", "ride",
        "pooboo", "bike", "cadence", "watts", "rpm", "squat", "pushup", "deadlift", "reps",
        "sets", "step", "steps", "walking", "walk", "jog", "balance board", "calf stretcher",
        "yoga mat", "exercise", "training", "drill", "drills", "rpe", "volume", "cardio", "gym"
    ]
    # Check Nutrition signals (fasting, protein, meal, sodium, calories, etc.)
    nutrition_keywords = [
        "fasting", "fast", "16/8", "protein", "leucine", "macros", "calories", "calorie",
        "meal", "meals", "sodium", "salt", "eating window", "food", "diet", "nutrition",
        "carbs", "fats", "amino", "intake", "supplement", "whey", "breakfast", "dinner",
        "lunch", "electrolyte", "electrolytes", "snack", "snacks", "kcal"
    ]
    # Check Recovery signals
    recovery_keywords = [
        "recovery", "sleep", "sleep score", "resting heart rate", "rhr", "blood pressure",
        "omron", "bp", "hrv", "heart rate variability", "stress", "average stress",
        "body battery", "training readiness", "sore", "soreness", "fatigue", "rest day",
        "stretching", "stretch", "foam roller", "hydration", "post-ride recovery"
    ]
    
    # Priority & Score matching for Category:
    # 1. Nutrition inspection (fasting, protein, meal, sodium, calories, etc.)
    if any(k in clean_lower for k in ["fasting", "protein", "meal", "meals", "sodium", "calories", "calorie", "16/8", "leucine", "macros", "diet", "eating window", "food", "nutrition", "carbs", "fats", "supplement", "whey", "breakfast", "dinner", "lunch", "salt", "electrolyte", "electrolytes"]):
        category = "Nutrition"
    # 2. Recovery inspection
    elif "recovery" in clean_lower or any(k in clean_lower for k in ["sleep score", "resting heart rate", "blood pressure", "omron", "hrv", "heart rate variability", "body battery", "training readiness", "soreness", "stretch", "stretching", "foam roller"]):
        category = "Recovery"
    # 3. Workouts inspection
    elif any(k in clean_lower for k in ["workout", "workouts", "kettlebell", "dumbbell", "cycling", "ride", "step", "steps", "walking", "mobility", "squat", "pushup", "deadlift", "sets", "reps", "balance board", "calf stretcher", "yoga mat", "pooboo", "cadence", "watts", "rpm"]):
        category = "Workouts"
    elif any(k in clean_lower for k in nutrition_keywords):
        category = "Nutrition"
    elif any(k in clean_lower for k in workout_keywords):
        category = "Workouts"
    elif any(k in clean_lower for k in recovery_keywords):
        category = "Recovery"
    else:
        category = "General"

    # Specific clean titles
    if "recovery" in clean_lower and any(k in clean_lower for k in ["ride", "cycling", "bike", "post-ride", "post ride"]):
        title = "Post-Ride Recovery"
        category = "Recovery"
    elif "step" in clean_lower and any(k in clean_lower for k in ["card", "summary", "analytics", "a2ui", "tracking"]):
        title = "Daily Step Analytics"
        category = "Workouts"
    elif "step" in clean_lower:
        title = "Daily Step Tracking"
        category = "Workouts"
    elif "fasting" in clean_lower and "protein" in clean_lower:
        title = "Fasting & Protein Plan"
        category = "Nutrition"
    elif "fasting" in clean_lower:
        title = "16/8 Fasting Protocol"
        category = "Nutrition"
    elif "protein" in clean_lower or "leucine" in clean_lower:
        title = "Protein & Nutrition Targets"
        category = "Nutrition"
    elif "sodium" in clean_lower or "salt" in clean_lower:
        title = "Sodium & Electrolyte Targets"
        category = "Nutrition"
    elif "meal" in clean_lower or "food" in clean_lower:
        title = "Meal & Nutrition Plan"
        category = "Nutrition"
    elif "calorie" in clean_lower or "calories" in clean_lower:
        title = "Caloric & Macro Targets"
        category = "Nutrition"
    elif any(k in clean_lower for k in ["cycling", "pooboo", "watts", "cadence", "ride"]):
        title = "Zone 2 Cycling Ride"
        category = "Workouts"
    elif any(k in clean_lower for k in ["strength", "kettlebell", "dumbbell", "squat"]):
        title = "Strength & Mobility Workout"
        category = "Workouts"
    elif any(k in clean_lower for k in ["blood pressure", "omron", "bp", "cardiovascular"]):
        title = "Cardiovascular & BP Check"
        category = "Recovery"
    elif any(k in clean_lower for k in ["balance board", "calf stretcher", "yoga mat"]):
        title = "Stability & Mobility Drills"
        category = "Workouts"
    elif "sleep" in clean_lower or "hrv" in clean_lower:
        title = "Sleep & HRV Analysis"
        category = "Recovery"
    elif any(k in clean_lower for k in ["biometrics summary card", "master biometrics", "biometrics dashboard"]):
        title = "Master Biometrics Dashboard"
        category = "Recovery"
    elif "workout" in clean_lower and "summary" in clean_lower:
        title = "Today's Workout Summary"
        category = "Workouts"
    elif "guest mode" in clean_lower or "guest" in clean_lower:
        title = "Guest Mode Profile"
        category = "General"

    if not title:
        # Smart keyword extraction for 3-4 word title
        words = re.findall(r"\b[a-zA-Z0-9'-]+\b", clean)
        stop_words = {
            "what", "is", "my", "how", "do", "i", "can", "you", "please", "the", "a", 
            "an", "and", "or", "for", "to", "in", "on", "at", "with", "show", "tell", 
            "give", "today", "today's", "check", "log", "me", "of", "about", "your", 
            "are", "am", "be", "this", "that", "it", "from", "by"
        }
        filtered = [w.capitalize() for w in words if w.lower() not in stop_words]
        if len(filtered) >= 2:
            title = " ".join(filtered[:4])
        elif len(filtered) == 1:
            title = f"{filtered[0]} Discussion"
        else:
            title = " ".join(w.capitalize() for w in words[:4]) or "New Conversation"

    return (title, category)


def generate_session_title(first_prompt: str) -> str:
    """Silently generates a clean 3-4 word title summarizing the user's first prompt."""
    title, _ = categorize_and_title_session(first_prompt)
    return title


def create_chat_session(
    user_id: str = "apex-user", 
    title: str = "New Chat", 
    category: str = "General", 
    session_id: Optional[str] = None
) -> Dict:
    """Creates a new chat session with a unique session_id and saves it to Firestore chat_sessions."""
    if not session_id:
        session_id = f"session_{int(datetime.datetime.now().timestamp())}_{uuid.uuid4().hex[:6]}"
    
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    valid_cat = category if category in VALID_CATEGORIES else "General"
    session_doc = {
        "session_id": session_id,
        "user_id": user_id,
        "title": title,
        "category": valid_cat,
        "created_at": now_str,
        "updated_at": now_str,
        "messages": []
    }
    CHAT_SESSIONS[session_id] = session_doc
    
    if db is not None:
        try:
            db.collection("chat_sessions").document(session_id).set({
                "session_id": session_id,
                "user_id": user_id,
                "title": title,
                "category": valid_cat,
                "created_at": firestore.SERVER_TIMESTAMP,
                "updated_at": firestore.SERVER_TIMESTAMP,
                "messages": []
            })
        except Exception as e:
            print(f"Firestore session create warning: {e}")
            
    return session_doc


def save_message_to_session(
    session_id: str, 
    role: str, 
    text: str, 
    user_id: str = "apex-user", 
    parts: Optional[List[Dict]] = None
) -> Dict:
    """Saves a message to the target chat_sessions document in Firestore, generating auto-titles and category tags on the first prompt."""
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    msg_obj = {
        "id": f"msg_{int(datetime.datetime.now().timestamp() * 1000)}_{uuid.uuid4().hex[:4]}",
        "role": "user" if role in ["user", "human"] else "agent",
        "text": text,
        "timestamp": datetime.datetime.now().strftime("%I:%M %p"),
        "created_at": now_str,
        "parts": parts or []
    }

    # Ensure session exists in memory or Firestore
    if session_id not in CHAT_SESSIONS:
        session_doc = None
        if db is not None:
            try:
                doc_snap = db.collection("chat_sessions").document(session_id).get()
                if doc_snap.exists:
                    session_doc = doc_snap.to_dict()
                    CHAT_SESSIONS[session_id] = session_doc
            except Exception:
                pass
        if not session_doc:
            CHAT_SESSIONS[session_id] = {
                "session_id": session_id,
                "user_id": user_id,
                "title": "New Chat",
                "category": "General",
                "created_at": now_str,
                "updated_at": now_str,
                "messages": []
            }

    session = CHAT_SESSIONS[session_id]
    
    # Auto-titling and categorization on the first user prompt
    if role in ["user", "human"] and (session.get("title") in ["New Chat", "New Session", "", None] or len(session.get("messages", [])) == 0):
        auto_title, auto_cat = categorize_and_title_session(text)
        session["title"] = auto_title
        session["category"] = auto_cat

    session["messages"].append(msg_obj)
    session["updated_at"] = now_str
    session["user_id"] = user_id

    # Persist updated session document to Firestore chat_sessions collection
    if db is not None:
        try:
            db.collection("chat_sessions").document(session_id).set({
                "session_id": session_id,
                "user_id": user_id,
                "title": session["title"],
                "category": session.get("category", "General"),
                "created_at": session.get("created_at", now_str),
                "updated_at": firestore.SERVER_TIMESTAMP,
                "messages": session["messages"]
            }, merge=True)
        except Exception as e:
            print(f"Firestore session update warning: {e}")

    # Maintain backwards compatibility with IN_MEMORY_SESSIONS
    IN_MEMORY_SESSIONS.setdefault(user_id, []).append({"role": role, "parts": [text]})

    return msg_obj


def list_chat_sessions(user_id: str = "apex-user") -> List[Dict]:
    """Fetches all past chat sessions from Firestore chat_sessions collection and in-memory cache, sorted in reverse chronological order."""
    sessions_dict = dict(CHAT_SESSIONS)
    
    if db is not None:
        try:
            docs = db.collection("chat_sessions").stream()
            for doc in docs:
                data = doc.to_dict()
                sid = data.get("session_id", doc.id)
                # Filter for user or match defaults
                doc_uid = data.get("user_id", "apex-user")
                if doc_uid == user_id or user_id in ["apex-user", "web-user", "default_user"] or doc_uid in ["apex-user", "web-user", "default_user"]:
                    sessions_dict[sid] = data
        except Exception as e:
            print(f"Firestore list sessions warning: {e}")

    session_list = []
    for sid, s in sessions_dict.items():
        msgs = s.get("messages", [])
        last_msg = msgs[-1]["text"] if msgs else ""
        session_list.append({
            "session_id": sid,
            "title": s.get("title", "New Chat"),
            "category": s.get("category", "General"),
            "created_at": s.get("created_at", ""),
            "updated_at": s.get("updated_at", ""),
            "message_count": len(msgs),
            "preview": last_msg[:60] + "..." if len(last_msg) > 60 else last_msg
        })

    session_list.sort(key=lambda x: str(x.get("updated_at") or x.get("created_at") or ""), reverse=True)
    return session_list


def get_chat_session_history(session_id: str, user_id: str = "apex-user") -> Optional[Dict]:
    """Loads a specific session's full message history and metadata."""
    if session_id in CHAT_SESSIONS:
        return CHAT_SESSIONS[session_id]
    
    if db is not None:
        try:
            doc = db.collection("chat_sessions").document(session_id).get()
            if doc.exists:
                data = doc.to_dict()
                CHAT_SESSIONS[session_id] = data
                return data
        except Exception as e:
            print(f"Firestore get session history warning: {e}")
            
    return None


def delete_chat_session(session_id: str, user_id: str = "apex-user") -> bool:
    """Deletes a chat session from Firestore and active cache."""
    CHAT_SESSIONS.pop(session_id, None)
    if db is not None:
        try:
            db.collection("chat_sessions").document(session_id).delete()
            return True
        except Exception as e:
            print(f"Firestore delete session warning: {e}")
    return True


def fetch_chat_history(uid="apex-user", limit=15):
    """Backwards-compatible fetch of recent message history for agentic reasoning loops."""
    if db is not None:
        try:
            chat_ref = db.collection('users').document(uid).collection('sessions')\
                         .order_by('timestamp', direction=firestore.Query.ASCENDING).limit(limit)
            history = []
            for doc in chat_ref.stream():
                data = doc.to_dict()
                history.append({"role": data["role"], "parts": [data["text"]]})
            if history:
                return history
        except Exception:
            pass
    return IN_MEMORY_SESSIONS.get(uid, [])[-limit:]


def save_message(uid, role, text):
    """Backwards-compatible save for legacy callers."""
    IN_MEMORY_SESSIONS.setdefault(uid, []).append({"role": role, "parts": [text]})
    if db is not None:
        try:
            db.collection('users').document(uid).collection('sessions').add({
                'role': role,
                'text': text,
                'timestamp': firestore.SERVER_TIMESTAMP
            })
        except Exception:
            pass

os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "true")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "project-281bf799-969f-49aa-917")
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "us-central1")

MODEL = "gemini-2.5-flash"

# Static Biological Baselines (Hardcoded in System Context)
# Static constraints referenced globally for all fitness, cycling, and fasting programming.
STATIC_PROFILE: Dict = {
    "dob": "1966-12-12",
    "height": "5'5\"",
    "height_inches": 65,
    "height_cm": 165.1,
}


def calculate_age_from_dob(dob_str: str = "1966-12-12") -> int:
    """Computes exact chronological age dynamically by comparing current date against date of birth.

    Args:
        dob_str: Date of birth in 'YYYY-MM-DD' format (default '1966-12-12').

    Returns:
        Exact chronological age as an integer.
    """
    dob = datetime.datetime.strptime(dob_str, "%Y-%m-%d").date()
    today = datetime.date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


# Dynamically compute and store age in STATIC_PROFILE
STATIC_PROFILE["age"] = calculate_age_from_dob(STATIC_PROFILE["dob"])

# Active Firestore Database: Dynamic Biometric Metrics (simulated collection `users/user_profile/biometrics`)
FIRESTORE_BIOMETRICS: Dict = {
    "current_weight_lbs": 200.0,
    "last_updated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "weight_history": [
        {
            "date": datetime.date.today().strftime("%Y-%m-%d"),
            "weight_lbs": 200.0,
            "source": "firestore_sync",
            "notes": "Baseline weight recorded"
        }
    ]
}

# In-memory logs for session testing
WORKOUT_LOGS: List[Dict] = []
STEP_LOGS: List[Dict] = [
    # Seed sample baseline historical days for realistic weekly/yearly aggregation
    {"date": (datetime.date.today() - datetime.timedelta(days=6)).strftime("%Y-%m-%d"), "steps": 9400, "distance_miles": 4.23, "calories": 376},
    {"date": (datetime.date.today() - datetime.timedelta(days=5)).strftime("%Y-%m-%d"), "steps": 11200, "distance_miles": 5.04, "calories": 448},
    {"date": (datetime.date.today() - datetime.timedelta(days=4)).strftime("%Y-%m-%d"), "steps": 8900, "distance_miles": 4.00, "calories": 356},
    {"date": (datetime.date.today() - datetime.timedelta(days=3)).strftime("%Y-%m-%d"), "steps": 10500, "distance_miles": 4.72, "calories": 420},
    {"date": (datetime.date.today() - datetime.timedelta(days=2)).strftime("%Y-%m-%d"), "steps": 12400, "distance_miles": 5.58, "calories": 496},
    {"date": (datetime.date.today() - datetime.timedelta(days=1)).strftime("%Y-%m-%d"), "steps": 10100, "distance_miles": 4.54, "calories": 404},
]


def generate_step_summary_a2ui(summary: Optional[Dict] = None) -> List[Dict]:
    """Generates the validated A2UI v0.8 message payload for Daily, Weekly (7-Day), and Yearly (365-Day) step analytics.

    Args:
        summary: Optional summary dictionary from get_step_summary. If None, current summary is fetched.

    Returns:
        A list of A2UI v0.8 message objects (beginRendering and surfaceUpdate).
    """
    if summary is None:
        summary = get_step_summary("all")
    d = summary.get("daily", {})
    w = summary.get("weekly", {})
    y = summary.get("yearly", {})

    d_date = str(d.get("date", datetime.date.today().strftime("%Y-%m-%d")))
    d_steps = int(d.get("steps", 0))
    d_goal_target = int(d.get("goal_target", 10000))
    d_goal_pct = float(d.get("goal_percentage", round((d_steps / max(d_goal_target, 1)) * 100, 1)))
    d_distance = float(d.get("distance_miles", round(d_steps / 2220.0, 2)))
    d_calories = int(d.get("calories_burned", round(d_steps * 0.04)))
    d_source = str(d.get("source", "Garmin Fenix 7 Live Telemetry"))

    w_total_steps = int(w.get("total_steps", 69700))
    w_avg_steps = int(w.get("daily_average_steps", round(w_total_steps / 7)))
    w_distance = float(w.get("total_distance_miles", round(w_total_steps / 2220.0, 2)))
    w_grade = str(w.get("consistency_grade", "A+" if w_avg_steps >= 10000 else "B+"))

    y_total_steps = int(y.get("year_to_date_steps", y.get("total_steps", 3615000)))
    y_miles = float(y.get("year_to_date_miles", y.get("total_miles", round(y_total_steps / 2220.0, 1))))
    y_avg_steps = int(y.get("annual_daily_average", round(y_total_steps / 365.0)))
    y_goal_pct = float(y.get("annual_goal_percentage", round((y_total_steps / 3650000.0) * 100, 1)))

    return [
        {
            "beginRendering": {
                "surfaceId": "default",
                "root": "step_card_root"
            }
        },
        {
            "surfaceUpdate": {
                "surfaceId": "default",
                "components": [
                    {
                        "id": "step_card_root",
                        "component": {
                            "Card": {
                                "child": "main_column"
                            }
                        }
                    },
                    {
                        "id": "main_column",
                        "component": {
                            "Column": {
                                "children": {
                                    "explicitList": [
                                        "title_text",
                                        "today_header",
                                        "today_text",
                                        "source_text",
                                        "div_1",
                                        "weekly_header",
                                        "weekly_text",
                                        "div_2",
                                        "yearly_header",
                                        "yearly_text",
                                        "tip_text"
                                    ]
                                }
                            }
                        }
                    },
                    {
                        "id": "title_text",
                        "component": {
                            "Text": {
                                "text": {"literalString": "🚶 ApexPulse Step Analytics (Multi-Timeframe)"},
                                "usageHint": "h2"
                            }
                        }
                    },
                    {
                        "id": "today_header",
                        "component": {
                            "Text": {
                                "text": {"literalString": f"📅 Today's Progress ({d_date})"},
                                "usageHint": "h3"
                            }
                        }
                    },
                    {
                        "id": "today_text",
                        "component": {
                            "Text": {
                                "text": {"literalString": f"• Steps: {d_steps:,} / {d_goal_target:,} ({d_goal_pct}%) | Distance: {d_distance} mi | Calories: {d_calories} kcal"},
                                "usageHint": "body"
                            }
                        }
                    },
                    {
                        "id": "source_text",
                        "component": {
                            "Text": {
                                "text": {"literalString": f"• Telemetry Source: {d_source}"},
                                "usageHint": "caption"
                            }
                        }
                    },
                    {
                        "id": "div_1",
                        "component": {
                            "Divider": {}
                        }
                    },
                    {
                        "id": "weekly_header",
                        "component": {
                            "Text": {
                                "text": {"literalString": "📊 Trailing 7-Day Rolling Summary"},
                                "usageHint": "h3"
                            }
                        }
                    },
                    {
                        "id": "weekly_text",
                        "component": {
                            "Text": {
                                "text": {"literalString": f"• 7-Day Total: {w_total_steps:,} steps | Daily Average: {w_avg_steps:,} steps/day | Total Distance: {w_distance} mi (Grade: {w_grade})"},
                                "usageHint": "body"
                            }
                        }
                    },
                    {
                        "id": "div_2",
                        "component": {
                            "Divider": {}
                        }
                    },
                    {
                        "id": "yearly_header",
                        "component": {
                            "Text": {
                                "text": {"literalString": "🏆 1-Year Cumulative Baseline (365 Days)"},
                                "usageHint": "h3"
                            }
                        }
                    },
                    {
                        "id": "yearly_text",
                        "component": {
                            "Text": {
                                "text": {"literalString": f"• 365-Day Total: {y_total_steps:,} steps | Cumulative Miles: {y_miles:,} mi | Annual Daily Avg: {y_avg_steps:,} steps/day ({y_goal_pct}% of 3.65M goal)"},
                                "usageHint": "body"
                            }
                        }
                    },
                    {
                        "id": "tip_text",
                        "component": {
                            "Text": {
                                "text": {"literalString": "🔥 Step metrics dynamically synchronized from Garmin Connect."},
                                "usageHint": "caption"
                            }
                        }
                    }
                ]
            }
        }
    ]


def generate_biometrics_summary_a2ui(telemetry: Optional[Dict] = None) -> List[Dict]:
    """Generates the validated A2UI v0.8 message payload for the Master Biometrics Dashboard Card.

    Args:
        telemetry: Optional telemetry dictionary. If None, current telemetry is fetched.

    Returns:
        A list of A2UI v0.8 message objects (beginRendering and surfaceUpdate).
    """
    if telemetry is None:
        telemetry = get_garmin_telemetry()
    
    t_date = str(telemetry.get("date", datetime.date.today().strftime("%Y-%m-%d")))
    latest_bp = str(telemetry.get("latest_bp", f"{telemetry.get('blood_pressure', '113/77')} mmHg"))
    weekly_avg_bp = str(telemetry.get("weekly_avg_bp", "114/76 mmHg"))
    yearly_avg_bp = str(telemetry.get("yearly_avg_bp", "116/77 mmHg"))
    historical_bp_range = str(telemetry.get("historical_bp_range", "108-124 / 68-82 mmHg"))
    
    rhr = int(telemetry.get("rhr") or telemetry.get("resting_heart_rate", 51))
    max_hr = int(telemetry.get("max_hr", 124))
    weekly_avg_rhr = int(telemetry.get("weekly_avg_rhr", 52))
    hrv_status = str(telemetry.get("hrv_status", "Balanced"))
    hrv_avg_ms = int(telemetry.get("hrv_avg_ms", 52))
    
    weight_lbs = float(telemetry.get("weight_lbs") or FIRESTORE_BIOMETRICS.get("current_weight_lbs", 200.0))
    bmi = float(telemetry.get("bmi", 33.3))
    weight_goal_lbs = float(telemetry.get("weight_goal_lbs", 185.0))
    weekly_avg_weight = float(telemetry.get("weekly_avg_weight", 200.4))
    yearly_weight_delta = float(telemetry.get("yearly_weight_delta", -6.0))
    
    sleep_score = int(telemetry.get("sleep_score", 80))
    sleep_duration = str(telemetry.get("sleep_duration", "7h 45m"))
    sleep_quality = str(telemetry.get("sleep_quality", "Deep: 1h 35m | Light: 4h 20m | REM: 1h 50m | Awake: 25m"))
    weekly_avg_sleep_score = int(telemetry.get("weekly_avg_sleep_score", 82))
    weekly_avg_sleep_dur = str(telemetry.get("weekly_avg_sleep_dur", "7h 38m"))
    
    daily_stress = int(telemetry.get("daily_stress") or telemetry.get("average_stress", 28))
    weekly_avg_stress = int(telemetry.get("weekly_avg_stress", 27))
    pulse_ox = int(telemetry.get("pulse_ox", 98))
    weekly_avg_pulse_ox = int(telemetry.get("weekly_avg_pulse_ox", 97))
    
    readiness = int(telemetry.get("training_readiness", 78))
    recovery_hours = telemetry.get("recovery_time_hours", 18)
    mode = str(telemetry.get("mode", "live_garmin_connect"))

    return [
        {
            "beginRendering": {
                "surfaceId": "default",
                "root": "biometrics_dashboard_root"
            }
        },
        {
            "surfaceUpdate": {
                "surfaceId": "default",
                "components": [
                    {
                        "id": "biometrics_dashboard_root",
                        "component": {
                            "Card": {
                                "child": "bio_main_column"
                            }
                        }
                    },
                    {
                        "id": "bio_main_column",
                        "component": {
                            "Column": {
                                "children": {
                                    "explicitList": [
                                        "bio_title_text",
                                        "bio_subtitle_text",
                                        "bio_div_1",
                                        "cardio_header",
                                        "cardio_bp_text",
                                        "cardio_hr_text",
                                        "cardio_recovery_text",
                                        "bio_div_2",
                                        "body_sleep_header",
                                        "body_weight_text",
                                        "sleep_score_text",
                                        "sleep_quality_text",
                                        "stress_text",
                                        "bio_div_3",
                                        "bio_footer_text"
                                    ]
                                }
                            }
                        }
                    },
                    {
                        "id": "bio_title_text",
                        "component": {
                            "Text": {
                                "text": {"literalString": "🫀 ApexPulse Master Biometrics Dashboard"},
                                "usageHint": "h2"
                            }
                        }
                    },
                    {
                        "id": "bio_subtitle_text",
                        "component": {
                            "Text": {
                                "text": {"literalString": f"Live Garmin Fenix 7 & Omron Telemetry Stream ({t_date})"},
                                "usageHint": "caption"
                            }
                        }
                    },
                    {
                        "id": "bio_div_1",
                        "component": {
                            "Divider": {}
                        }
                    },
                    {
                        "id": "cardio_header",
                        "component": {
                            "Text": {
                                "text": {"literalString": "💓 Cardiovascular & Autonomic Recovery"},
                                "usageHint": "h3"
                            }
                        }
                    },
                    {
                        "id": "cardio_bp_text",
                        "component": {
                            "Text": {
                                "text": {"literalString": f"• Blood Pressure: Latest {latest_bp} | 7-Day Avg: {weekly_avg_bp} | 1-Year Avg: {yearly_avg_bp} (Range: {historical_bp_range})"},
                                "usageHint": "body"
                            }
                        }
                    },
                    {
                        "id": "cardio_hr_text",
                        "component": {
                            "Text": {
                                "text": {"literalString": f"• Heart Rate & HRV: Resting HR: {rhr} bpm (Max: {max_hr} bpm | 7-Day Avg: {weekly_avg_rhr} bpm) | HRV Status: {hrv_status} ({hrv_avg_ms} ms)"},
                                "usageHint": "body"
                            }
                        }
                    },
                    {
                        "id": "cardio_recovery_text",
                        "component": {
                            "Text": {
                                "text": {"literalString": f"• Readiness & Oxygen: Training Readiness: {readiness}/100 | Recovery Time: {recovery_hours}h | Pulse Ox: {pulse_ox}% (7-Day Avg: {weekly_avg_pulse_ox}%)"},
                                "usageHint": "body"
                            }
                        }
                    },
                    {
                        "id": "bio_div_2",
                        "component": {
                            "Divider": {}
                        }
                    },
                    {
                        "id": "body_sleep_header",
                        "component": {
                            "Text": {
                                "text": {"literalString": "⚖️ Body Composition, Stress & Sleep Architecture"},
                                "usageHint": "h3"
                            }
                        }
                    },
                    {
                        "id": "body_weight_text",
                        "component": {
                            "Text": {
                                "text": {"literalString": f"• Body Weight: Current: {weight_lbs} lbs (Goal: {weight_goal_lbs} lbs | BMI: {bmi}) | 7-Day Avg: {weekly_avg_weight} lbs | 1-Year Trend: {yearly_weight_delta:+} lbs"},
                                "usageHint": "body"
                            }
                        }
                    },
                    {
                        "id": "sleep_score_text",
                        "component": {
                            "Text": {
                                "text": {"literalString": f"• Sleep Performance: Last Night: {sleep_score}/100 ({sleep_duration}) | 7-Day Avg: {weekly_avg_sleep_score}/100 ({weekly_avg_sleep_dur})"},
                                "usageHint": "body"
                            }
                        }
                    },
                    {
                        "id": "sleep_quality_text",
                        "component": {
                            "Text": {
                                "text": {"literalString": f"• Sleep Stages: {sleep_quality}"},
                                "usageHint": "body"
                            }
                        }
                    },
                    {
                        "id": "stress_text",
                        "component": {
                            "Text": {
                                "text": {"literalString": f"• Autonomic Stress: Daily Stress: {daily_stress} (7-Day Avg: {weekly_avg_stress})"},
                                "usageHint": "body"
                            }
                        }
                    },
                    {
                        "id": "bio_div_3",
                        "component": {
                            "Divider": {}
                        }
                    },
                    {
                        "id": "bio_footer_text",
                        "component": {
                            "Text": {
                                "text": {"literalString": f"⚡ Mode: {mode} | Dynamic Biometrics & Multi-Timeframe Telemetry Pipeline Active"},
                                "usageHint": "caption"
                            }
                        }
                    }
                ]
            }
        }
    ]


def display_biometrics_summary_card() -> str:
    """Generates an A2UI visual card for the Master Biometrics Dashboard showing cardiovascular, recovery, sleep, and body composition metrics.

    Returns:
        A JSON string containing the validated A2UI v0.8 surface specification for rendering the Biometrics Summary Card.
    """
    telemetry = get_garmin_telemetry()
    a2ui_payload = generate_biometrics_summary_a2ui(telemetry)
    return json.dumps(a2ui_payload)


def log_steps(
    steps: int,
    distance_miles: float = 0.0,
    date_str: str = ""
) -> Dict:
    """Logs a manual step count override for a specific date (defaults to today), persisting to Firestore and returning updated analytics and the A2UI card.

    Args:
        steps: Number of steps taken (manual override value).
        distance_miles: Distance covered in miles (if 0.0, estimated at 2,220 steps/mile).
        date_str: Date string in 'YYYY-MM-DD' format (defaults to current date).

    Returns:
        A dictionary confirming the manually logged steps, updated summary metrics, and the validated A2UI visual card payload.
    """
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    target_date = date_str if date_str else today_str
    
    calc_distance = round(distance_miles if distance_miles > 0 else (steps / 2220.0), 2)
    calc_calories = round(steps * 0.04)

    # 1. Update in-memory STEP_LOGS with manual override
    existing = next((item for item in STEP_LOGS if item["date"] == target_date), None)
    if existing:
        existing["steps"] = int(steps)
        existing["distance_miles"] = calc_distance
        existing["calories"] = calc_calories
        existing["source"] = "manual_entry"
    else:
        new_entry = {
            "date": target_date,
            "steps": int(steps),
            "distance_miles": calc_distance,
            "calories": calc_calories,
            "source": "manual_entry"
        }
        STEP_LOGS.append(new_entry)

    # 2. Persist manual override to Firestore database
    if db is not None:
        for uid in ["apex-user", "default_user"]:
            try:
                db.collection("users").document(uid).collection("steps").document(target_date).set({
                    "date": target_date,
                    "steps": int(steps),
                    "distance_miles": calc_distance,
                    "calories": calc_calories,
                    "source": "manual_entry",
                    "updated_at": firestore.SERVER_TIMESTAMP
                }, merge=True)
            except Exception:
                pass

    daily_goal = 10000
    goal_pct = round((steps / daily_goal) * 100, 1)

    summary = get_step_summary("daily", force_garmin_sync=False)
    a2ui_payload = generate_step_summary_a2ui(summary)
    a2ui_card_json = json.dumps(a2ui_payload)

    return {
        "status": "success",
        "date": target_date,
        "steps_logged": steps,
        "total_steps_today": steps,
        "daily_goal_pct": goal_pct,
        "distance_miles_today": calc_distance,
        "source": "manual_entry",
        "message": f"Recorded manual step override: {steps:,} steps for {target_date} ({goal_pct}% of {daily_goal:,} daily goal). Persisted to Firestore.",
        "summary": summary,
        "a2ui_payload": a2ui_payload,
        "a2ui_card_json": a2ui_card_json
    }


def sync_garmin_steps_to_db(steps: int, today_str: str) -> None:
    """Synchronizes real-time live Garmin Fenix 7 steps to active memory and Firestore database for today."""
    global STEP_LOGS
    calc_distance = round(steps / 2220.0, 2)
    calc_calories = round(steps * 0.04)

    # 1. Update in-memory STEP_LOGS for today
    existing = next((item for item in STEP_LOGS if item["date"] == today_str), None)
    if existing:
        existing["steps"] = int(steps)
        existing["distance_miles"] = calc_distance
        existing["calories"] = calc_calories
        existing["source"] = "garmin_fenix_7_live"
    else:
        STEP_LOGS.append({
            "date": today_str,
            "steps": int(steps),
            "distance_miles": calc_distance,
            "calories": calc_calories,
            "source": "garmin_fenix_7_live"
        })

    # 2. Automatically sync to Firestore database if accessible
    if db is not None:
        for uid in ["apex-user", "default_user"]:
            try:
                db.collection("users").document(uid).collection("steps").document(today_str).set({
                    "date": today_str,
                    "steps": int(steps),
                    "distance_miles": calc_distance,
                    "calories": calc_calories,
                    "source": "garmin_fenix_7_live",
                    "updated_at": firestore.SERVER_TIMESTAMP
                }, merge=True)
            except Exception:
                pass


def get_firestore_step_entry(today_str: str) -> Optional[Dict]:
    """Checks Firestore first for today's logged step document."""
    if db is not None:
        for uid in ["apex-user", "default_user"]:
            try:
                doc = db.collection("users").document(uid).collection("steps").document(today_str).get()
                if doc.exists:
                    data = doc.to_dict()
                    if data and "steps" in data:
                        return {
                            "date": today_str,
                            "steps": int(data.get("steps", 0)),
                            "distance_miles": float(data.get("distance_miles", round(int(data.get("steps", 0)) / 2220.0, 2))),
                            "calories": int(data.get("calories", round(int(data.get("steps", 0)) * 0.04))),
                            "source": data.get("source", "firestore_logged")
                        }
            except Exception:
                pass
    return None


def get_step_summary(timeframe: str = "daily", force_garmin_sync: bool = False) -> Dict:
    """Retrieves step and walking analytics across Daily, 7-Day Weekly, and 365-Day Yearly timeframes:
    1. Checks Firestore first for today's logged steps.
    2. Only uses garmin_steps if telemetry Mode == 'live_garmin_connect'.
    3. If Garmin sync is offline or in fallback mode, uses the user's manual/logged Firestore step count rather than simulated numbers.

    Args:
        timeframe: Analytics timeframe ('daily', 'weekly', 'yearly', or 'all').
        force_garmin_sync: If True, forces synchronization with live Garmin telemetry regardless of manual overrides.

    Returns:
        A dictionary containing multi-timeframe step metrics and telemetry source.
    """
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    
    # 1. Check Firestore first for today's logged steps
    firestore_entry = get_firestore_step_entry(today_str)
    mem_entry = next((item for item in STEP_LOGS if item["date"] == today_str), None)
    
    if firestore_entry:
        if mem_entry:
            mem_entry["steps"] = firestore_entry["steps"]
            mem_entry["distance_miles"] = firestore_entry["distance_miles"]
            mem_entry["calories"] = firestore_entry["calories"]
            mem_entry["source"] = firestore_entry.get("source", "firestore_logged")
        else:
            STEP_LOGS.append(dict(firestore_entry))
        mem_entry = next((item for item in STEP_LOGS if item["date"] == today_str), None)

    # 2. Check telemetry status
    try:
        telemetry = get_garmin_telemetry()
    except Exception:
        telemetry = {"mode": "offline_fallback", "garmin_steps": 0, "daily_steps": 0}

    telemetry_mode = telemetry.get("mode", "offline_fallback")
    garmin_steps = telemetry.get("daily_steps") or telemetry.get("garmin_steps", 0)

    # 3. ONLY use garmin_steps if telemetry Mode is strictly 'live_garmin_connect'
    if telemetry_mode == "live_garmin_connect" and isinstance(garmin_steps, (int, float)) and garmin_steps >= 0:
        has_manual_override = mem_entry is not None and mem_entry.get("source") == "manual_entry"
        if not has_manual_override or force_garmin_sync:
            sync_garmin_steps_to_db(int(garmin_steps), today_str)
            mem_entry = next((item for item in STEP_LOGS if item["date"] == today_str), None)
    else:
        # Offline or fallback mode: strictly decouple from simulated numbers
        if mem_entry is None and firestore_entry is None:
            mem_entry = {
                "date": today_str,
                "steps": 0,
                "distance_miles": 0.0,
                "calories": 0,
                "source": "offline_fallback"
            }

    today_entry = mem_entry or {"steps": 0, "distance_miles": 0.0, "calories": 0, "source": "offline_fallback"}
    
    # Weekly (trailing 7 days)
    last_7_days = sorted(STEP_LOGS, key=lambda x: x["date"])[-7:]
    weekly_total_steps = telemetry.get("weekly_steps") or sum(d["steps"] for d in last_7_days)
    weekly_avg_steps = telemetry.get("weekly_avg_steps") or round(weekly_total_steps / max(len(last_7_days), 1))
    weekly_total_miles = round(weekly_total_steps / 2220.0, 2)
    
    # Yearly (trailing 365 days)
    yearly_total_steps = telemetry.get("yearly_steps") or (1450000 + sum(d["steps"] for d in STEP_LOGS))
    yearly_avg_steps = telemetry.get("yearly_avg_steps") or round(yearly_total_steps / 365.0)
    yearly_total_miles = round(yearly_total_steps / 2220.0, 1)

    summary = {
        "daily": {
            "date": today_str,
            "steps": today_entry["steps"],
            "distance_miles": today_entry["distance_miles"],
            "goal_target": 10000,
            "goal_percentage": round((today_entry["steps"] / 10000.0) * 100, 1),
            "calories_burned": today_entry["calories"],
            "source": today_entry.get("source", "garmin_fenix_7_live" if telemetry_mode == "live_garmin_connect" else "offline_fallback")
        },
        "weekly": {
            "days_tracked": 7,
            "total_steps": weekly_total_steps,
            "total_distance_miles": weekly_total_miles,
            "daily_average_steps": weekly_avg_steps,
            "consistency_grade": "A+" if weekly_avg_steps >= 10000 else "B+"
        },
        "yearly": {
            "year": datetime.date.today().year,
            "year_to_date_steps": yearly_total_steps,
            "year_to_date_miles": yearly_total_miles,
            "annual_daily_average": yearly_avg_steps,
            "annual_goal": 3650000,
            "annual_goal_percentage": round((yearly_total_steps / 3650000.0) * 100, 1)
        }
    }
    return summary


def display_step_summary_card() -> str:
    """Generates an A2UI visual card for daily, weekly, and yearly step and walking metrics.

    Returns:
        A JSON string containing the validated A2UI v0.8 surface specification for rendering the Step Summary Card.
    """
    summary = get_step_summary("all")
    a2ui_payload = generate_step_summary_a2ui(summary)
    return json.dumps(a2ui_payload)


def log_strength_workout(
    exercise_name: str,
    sets: int,
    reps: int,
    weight_lbs: float = 15.0,
    rpe: int = 8,
    notes: str = ""
) -> Dict:
    """Logs a functional strength, balance, or mobility training exercise and set details using available home equipment (15 lb kettlebell, 3-12 lb dumbbells, circular balance board, calf stretcher, yoga mat).

    Args:
        exercise_name: Name of the functional movement (e.g., 'Turkish Get-Up', 'Goblet Squat with Pause', 'Single-Arm Kettlebell Swing', 'Kettlebell Halo', 'Dumbbell Lateral Raise', 'Dumbbell Bicep Curl', 'Circular Balance Board Stability Drill', 'Calf Stretcher Mobility Flow', 'Rotational Lunge').
        sets: Number of sets completed.
        reps: Repetitions completed per set.
        weight_lbs: Weight used in pounds (e.g., 15.0 lbs for kettlebell, 3.0–12.0 lbs for dumbbells, 0.0 lbs for balance board / calf stretcher / yoga mat).
        rpe: Rate of Perceived Exertion on a 1-10 scale (default: 8).
        notes: Optional notes on tempo, pause duration, unilateral stability, balance, or mobility.

    Returns:
        A dictionary confirming the logged workout and estimated volume load.
    """
    volume_load = sets * reps * (weight_lbs if weight_lbs > 0 else 1)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = {
        "timestamp": timestamp,
        "type": "functional_strength",
        "exercise": exercise_name,
        "sets": sets,
        "reps": reps,
        "weight_lbs": weight_lbs,
        "rpe": rpe,
        "volume_load_lbs": volume_load,
        "notes": notes
    }
    WORKOUT_LOGS.append(entry)
    return {
        "status": "success",
        "message": f"Logged {sets}x{reps} {exercise_name} @ {weight_lbs} lbs (RPE {rpe}).",
        "volume_load_lbs": volume_load,
        "total_logged_today": len(WORKOUT_LOGS)
    }


def log_cycling_session(
    duration_minutes: int,
    target_zone: str = "Zone 2",
    avg_power_watts: int = 0,
    avg_cadence_rpm: int = 0,
    distance_miles: float = 0.0,
    calories_burned: int = 0,
    notes: str = ""
) -> Dict:
    """Logs an indoor cycling workout session.

    Args:
        duration_minutes: Total ride duration in minutes.
        target_zone: Training intensity zone (e.g., 'Zone 2 Endurance', 'Zone 3 Tempo', 'Zone 4 Sweet Spot', 'HIIT Intervals').
        avg_power_watts: Average power output in watts (0 if unknown).
        avg_cadence_rpm: Average pedaling cadence in RPM (0 if unknown).
        distance_miles: Total virtual or measured distance in miles (0.0 if unknown).
        calories_burned: Estimated energy expenditure in kcal.
        notes: Optional notes about interval structure, resistance, or bike feel.

    Returns:
        A dictionary confirming the logged cycling session.
    """
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = {
        "timestamp": timestamp,
        "type": "indoor_cycling",
        "duration_minutes": duration_minutes,
        "target_zone": target_zone,
        "avg_power_watts": avg_power_watts,
        "avg_cadence_rpm": avg_cadence_rpm,
        "distance_miles": distance_miles,
        "calories_burned": calories_burned if calories_burned > 0 else duration_minutes * 10,
        "notes": notes
    }
    WORKOUT_LOGS.append(entry)
    return {
        "status": "success",
        "message": f"Logged {duration_minutes} min indoor cycling ({target_zone}) session.",
        "entry": entry,
        "total_logged_today": len(WORKOUT_LOGS)
    }


def check_fasting_status(
    eating_window_start_hour: int = 13,
    fasting_duration_hours: int = 16
) -> Dict:
    """Calculates current 16/8 intermittent fasting status and countdown with Eastern Time (America/New_York) awareness.

    Args:
        eating_window_start_hour: Hour of the day (24-hour format, 0-23) when the 8-hour eating window begins. Default is 13 (1:00 PM Eastern Time).
        fasting_duration_hours: Length of fasting window in hours (default 16 for 16/8 protocol).

    Returns:
        A dictionary detailing current fasting phase (fasting vs eating), hours remaining, and next window transition time.
    """
    try:
        import zoneinfo
        ny_tz = zoneinfo.ZoneInfo("America/New_York")
        now = datetime.datetime.now(ny_tz)
    except Exception:
        now = datetime.datetime.now()

    eating_window_hours = 24 - fasting_duration_hours
    eating_window_end_hour = (eating_window_start_hour + eating_window_hours) % 24
    current_hour = now.hour + (now.minute / 60.0) + (now.second / 3600.0)

    # Format 12-hour display strings
    start_dt = datetime.time(eating_window_start_hour, 0)
    end_dt = datetime.time(eating_window_end_hour, 0)
    start_label = start_dt.strftime("%I:%M %p").lstrip("0")
    end_label = end_dt.strftime("%I:%M %p").lstrip("0")

    if eating_window_start_hour <= current_hour < (eating_window_start_hour + eating_window_hours):
        in_eating_window = True
        hours_remaining = (eating_window_start_hour + eating_window_hours) - current_hour
        state = "EATING_WINDOW_OPEN"
        action_advice = f"Your eating window is OPEN until {end_label} ({eating_window_end_hour:02d}:00 ET). Prioritize your high-protein meals now ({round(hours_remaining, 1)}h remaining)."
    else:
        in_eating_window = False
        state = "FASTING_ACTIVE"
        if current_hour < eating_window_start_hour:
            hours_remaining = eating_window_start_hour - current_hour
        else:
            hours_remaining = (24.0 - current_hour) + eating_window_start_hour
        h_rem = int(hours_remaining)
        m_rem = int((hours_remaining % 1) * 60)
        action_advice = f"Fasting is ACTIVE. Your eating window opens in {h_rem}h {m_rem}m at {start_label} ({eating_window_start_hour:02d}:00 ET). Stay hydrated with water, black coffee, or electrolytes."

    return {
        "state": state,
        "in_eating_window": in_eating_window,
        "current_time": now.strftime("%I:%M %p"),
        "timezone": "America/New_York (Eastern Time)",
        "protocol": f"{fasting_duration_hours}/{eating_window_hours} Intermittent Fasting",
        "eating_window": f"{start_label} - {end_label} ({eating_window_start_hour:02d}:00 - {eating_window_end_hour:02d}:00 ET)",
        "eating_window_start_hour": eating_window_start_hour,
        "eating_window_end_hour": eating_window_end_hour,
        "hours_remaining_in_current_state": round(hours_remaining, 1),
        "guidance": action_advice
    }


def log_weight(
    weight_lbs: float,
    date_str: str = "",
    notes: str = ""
) -> Dict:
    """Logs and updates the user's dynamic body weight in the active Firestore database without editing the core system prompt.

    Args:
        weight_lbs: Current body weight in pounds (e.g., 200.0).
        date_str: Optional date string in 'YYYY-MM-DD' format (defaults to current date).
        notes: Optional notes regarding weigh-in conditions (e.g., 'morning fasted weigh-in').

    Returns:
        A dictionary confirming the updated weight, calculated BMI, delta from previous weigh-in, and updated daily protein targets.
    """
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    target_date = date_str if date_str else today_str
    previous_weight = FIRESTORE_BIOMETRICS.get("current_weight_lbs", 200.0)

    FIRESTORE_BIOMETRICS["current_weight_lbs"] = float(weight_lbs)
    FIRESTORE_BIOMETRICS["last_updated"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    history_entry = {
        "date": target_date,
        "weight_lbs": float(weight_lbs),
        "source": "firestore_tool_call",
        "notes": notes
    }
    FIRESTORE_BIOMETRICS.setdefault("weight_history", []).append(history_entry)

    height_in = STATIC_PROFILE["height_inches"]
    bmi = round((weight_lbs * 703.0) / (height_in ** 2), 1)
    weight_delta = round(weight_lbs - previous_weight, 1)
    protein_target = round(weight_lbs * 1.0)
    current_age = calculate_age_from_dob(STATIC_PROFILE.get("dob", "1966-12-12"))

    return {
        "status": "success",
        "message": f"Recorded dynamic weight of {weight_lbs} lbs in Firestore (delta: {weight_delta:+} lbs). Calculated BMI: {bmi}.",
        "current_weight_lbs": weight_lbs,
        "previous_weight_lbs": previous_weight,
        "bmi": bmi,
        "static_age": current_age,
        "static_dob": STATIC_PROFILE.get("dob", "1966-12-12"),
        "static_height": STATIC_PROFILE["height"],
        "daily_protein_target_g": protein_target,
        "firestore_document": "users/user_profile/biometrics",
        "last_updated": FIRESTORE_BIOMETRICS["last_updated"]
    }


def get_user_biometric_profile() -> Dict:
    """Retrieves the hybrid biometric profile: static biological baselines (with age computed dynamically from DOB 1966-12-12) and active dynamic Firestore metrics (Current Weight: 200 lbs).

    Returns:
        A dictionary detailing static biological baselines, dynamic Firestore weight, BMI, history count, and age-adapted physiological guidance.
    """
    current_weight = FIRESTORE_BIOMETRICS.get("current_weight_lbs", 200.0)
    height_in = STATIC_PROFILE["height_inches"]
    bmi = round((current_weight * 703.0) / (height_in ** 2), 1)
    current_age = calculate_age_from_dob(STATIC_PROFILE.get("dob", "1966-12-12"))

    return {
        "static_baselines": {
            "age": current_age,
            "dob": STATIC_PROFILE["dob"],
            "height": STATIC_PROFILE["height"],
            "height_inches": height_in,
            "height_cm": STATIC_PROFILE["height_cm"],
            "equipment_suite": "15 lb kettlebell, Dumbbell pairs (3, 5, 8, 10, 12 lbs), Circular balance board, Calf stretcher, Yoga mat, Pooboo indoor cycling bike, walking pad, COOSPO chest strap",
            "equipment_constraint": "Available Home Gym Suite: 15 lb kettlebell, Dumbbell pairs (3, 5, 8, 10, 12 lbs), Circular balance board, Calf stretcher, Yoga mat"
        },
        "dynamic_firestore_metrics": {
            "current_weight_lbs": current_weight,
            "bmi": bmi,
            "last_updated": FIRESTORE_BIOMETRICS.get("last_updated"),
            "history_entries_count": len(FIRESTORE_BIOMETRICS.get("weight_history", []))
        },
        "age_and_biometric_guidance": [
            f"Age {current_age} Functional Longevity, Strength & Mobility: Program functional longevity, progressive strength, and mobility routines utilizing the full equipment suite (15 lb kettlebell, 3–12 lb dumbbell pairs, circular balance board, calf stretcher, yoga mat) focusing on joint health, ankle/plantar mobility, core stability, and unilateral control. Never recommend barbells, heavy commercial gym machines, or unprompted pull-ups.",
            "Zone 2 Cycling: Build aerobic base on Pooboo bike with COOSPO chest strap (Target HR 115-126 bpm) to optimize mitochondrial health without excessive joint stress.",
            "Protein & Leucine Threshold: Target ~200g/day (1.0g/lb) with 3.5g–4.0g leucine per meal from whole-food organic sources to stimulate Muscle Protein Synthesis (MPS) in older adults.",
            "16/8 Fasting: 1:00 PM – 9:00 PM eating window (2 meals) to promote autophagy, insulin sensitivity, and overnight restorative sleep."
        ]
    }


def calculate_protein_targets(
    body_weight_lbs: float = 0.0,
    meals_per_day: int = 3,
    fitness_goal: str = "muscle_building_and_fat_loss"
) -> Dict:
    """Calculates daily protein and macronutrient recommendations for strength training and fasting, factoring in dynamically computed age from DOB and dynamic body weight.

    Args:
        body_weight_lbs: Current body weight in pounds (if 0.0 or omitted, defaults to dynamic weight from Firestore, currently 200 lbs).
        meals_per_day: Number of meals planned during the 8-hour eating window (typically 2 or 3).
        fitness_goal: Fitness objective ('muscle_building_and_fat_loss', 'maintenance', or 'endurance').

    Returns:
        A dictionary with total daily protein target, per-meal protein distribution, leucine threshold analysis, and age-adjusted nutrition suggestions.
    """
    effective_weight = body_weight_lbs if body_weight_lbs > 0 else FIRESTORE_BIOMETRICS.get("current_weight_lbs", 200.0)
    current_age = calculate_age_from_dob(STATIC_PROFILE.get("dob", "1966-12-12"))
    multiplier = 1.0 if "muscle" in fitness_goal.lower() else 0.85
    daily_protein_g = round(effective_weight * multiplier)
    protein_per_meal_g = round(daily_protein_g / max(meals_per_day, 1))

    return {
        "user_age": current_age,
        "user_dob": STATIC_PROFILE["dob"],
        "user_height": STATIC_PROFILE["height"],
        "body_weight_lbs": effective_weight,
        "daily_protein_target_grams": daily_protein_g,
        "meals_planned_in_window": meals_per_day,
        "target_protein_per_meal_grams": protein_per_meal_g,
        "leucine_threshold_met": protein_per_meal_g >= 30,
        "recommendations": [
            f"Aim for {protein_per_meal_g}g of protein per meal across {meals_per_day} meals in your eating window.",
            f"For age {current_age} at {effective_weight} lbs, hit at least 3.5g–4.0g leucine per meal (e.g. 7-8 oz chicken breast, 40g whey isolate, or 8 oz wild salmon) to overcome anabolic resistance and maximize Muscle Protein Synthesis (MPS).",
            "Pair high protein with post-ride complex carbohydrates to restore glycogen without breaking caloric deficit."
        ]
    }


def get_workout_and_fasting_summary() -> Dict:
    """Retrieves all logged functional strength exercises, cycling rides, biometrics, and current fasting state for today.

    Returns:
        A dictionary containing a summary of today's workouts, biometrics, and fasting status.
    """
    step_sum = get_step_summary("daily")
    return {
        "biometrics": get_user_biometric_profile(),
        "total_workouts_logged": len(WORKOUT_LOGS),
        "workouts": WORKOUT_LOGS,
        "steps_today": step_sum["daily"],
        "fasting_check": check_fasting_status()
    }


def delete_workout_record(
    uid: str = "apex-user",
    record_type: str = "",
    date: str = ""
) -> Dict:
    """Queries the Firestore sessions collection (and active workout memory) for the specified user and deletes matching workout, cycling, or step records.

    Use this tool whenever the user indicates that a logged workout, cycling session, step count, or historical entry is incorrect, fake, or needs to be deleted/wiped from memory.

    Args:
        uid: The user ID to manage memory for (default 'apex-user').
        record_type: The type of record or keyword to delete (e.g., 'indoor_cycling', 'cycling', 'step', 'steps', '8450', '8,450', 'strength', 'fake', 'workout', or 'all').
        date: Optional date string in 'YYYY-MM-DD' or 'today' format to scope deletion.

    Returns:
        A dictionary detailing the number of deleted records from Firestore sessions and active memory, with a confirmation status.
    """
    global WORKOUT_LOGS, STEP_LOGS, IN_MEMORY_SESSIONS
    firestore_deleted = 0
    record_type_lower = (record_type or "").lower().strip()
    date_clean = (date or "").strip().lower()
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    if date_clean == "today":
        date_clean = today_str

    # 1. Delete matching session documents from Firestore
    if db is not None:
        for user_key in [uid, "apex-user", "default_user", "user"]:
            try:
                sessions_ref = db.collection('users').document(user_key).collection('sessions')
                for doc in sessions_ref.stream():
                    data = doc.to_dict()
                    text_content = str(data.get("text", "")).lower()
                    doc_date = ""
                    ts = data.get("timestamp")
                    if ts and hasattr(ts, "strftime"):
                        doc_date = ts.strftime("%Y-%m-%d")
                    
                    matches_type = False
                    if not record_type_lower or record_type_lower in ["all", "workout", "records"]:
                        matches_type = True
                    elif any(k in record_type_lower for k in ["cycling", "bike", "ride"]):
                        matches_type = any(k in text_content for k in ["cycling", "bike", "pooboo", "watts", "rpm", "ride", "indoor cycling"])
                    elif any(k in record_type_lower for k in ["step", "8450", "8,450"]):
                        matches_type = any(k in text_content for k in ["step", "8450", "8,450", "walk", "walked", "walking"])
                    elif any(k in record_type_lower for k in ["strength", "kettlebell", "squat", "dumbbell", "mobility", "balance", "stretcher", "yoga"]):
                        matches_type = any(k in text_content for k in ["strength", "kettlebell", "squat", "tgu", "turkish get-up", "sets", "reps", "dumbbell", "balance", "stretcher", "mobility", "yoga"])
                    elif any(k in record_type_lower for k in ["fake", "incorrect", "mock"]):
                        matches_type = any(k in text_content for k in ["cycling", "8450", "8,450", "fake", "mock"])
                    else:
                        matches_type = record_type_lower in text_content

                    matches_date = True
                    if date_clean:
                        matches_date = (date_clean in text_content) or (date_clean in doc_date)

                    if matches_type and matches_date:
                        doc.reference.delete()
                        firestore_deleted += 1
            except Exception:
                pass

    # 2. Wipe/Filter active in-memory workout and step records
    mem_workout_deleted = 0
    initial_workouts = len(WORKOUT_LOGS)
    if not record_type_lower or record_type_lower in ["all", "fake", "workout", "records"]:
        WORKOUT_LOGS = []
    elif any(k in record_type_lower for k in ["cycling", "bike", "ride"]):
        WORKOUT_LOGS = [w for w in WORKOUT_LOGS if w.get("type") != "indoor_cycling" and "cycling" not in str(w).lower()]
    elif any(k in record_type_lower for k in ["strength", "kettlebell", "dumbbell", "mobility", "balance", "stretcher", "yoga"]):
        WORKOUT_LOGS = [w for w in WORKOUT_LOGS if w.get("type") != "functional_strength"]
    else:
        WORKOUT_LOGS = [w for w in WORKOUT_LOGS if record_type_lower not in str(w).lower()]
    mem_workout_deleted = initial_workouts - len(WORKOUT_LOGS)

    mem_step_deleted = 0
    initial_steps = len(STEP_LOGS)
    if any(k in record_type_lower for k in ["step", "8450", "8,450", "fake", "all", "records"]):
        STEP_LOGS = [s for s in STEP_LOGS if s.get("steps") != 8450 and (not date_clean or s.get("date") != date_clean)]
    mem_step_deleted = initial_steps - len(STEP_LOGS)

    # 3. Clean in-memory session messages
    for user_key in [uid, "apex-user", "default_user"]:
        if user_key in IN_MEMORY_SESSIONS:
            if not record_type_lower or record_type_lower in ["all", "records"]:
                IN_MEMORY_SESSIONS[user_key] = []
            else:
                IN_MEMORY_SESSIONS[user_key] = [
                    m for m in IN_MEMORY_SESSIONS[user_key]
                    if not any(k in str(m.get("parts", "")).lower() for k in [record_type_lower, "indoor cycling", "8450", "8,450"])
                ]

    total_mem_deleted = mem_workout_deleted + mem_step_deleted

    return {
        "status": "success",
        "deleted_from_firestore_sessions": firestore_deleted,
        "deleted_from_active_memory": total_mem_deleted,
        "record_type": record_type or "all_target_records",
        "date": date or "today",
        "user_id": uid,
        "message": f"Successfully deleted {record_type or 'target'} records from Firestore database ({firestore_deleted} documents removed) and active memory ({total_mem_deleted} records removed)."
    }


def google_search_live(query: str) -> str:
    """Performs a live Google search query with grounding to retrieve the latest real-time fitness, exercise science, nutrition, supplementation, and physiological research.

    Use this tool whenever a question asks about recent developments, emerging scientific studies, cutting-edge training methodologies, or facts outside internal parameters and baseline knowledge.

    Args:
        query: The search query to look up on the live web (e.g., 'latest 2026 creatine timing research', 'Zone 2 lactate clearance protocols', 'emerging electrolyte guidelines for 16/8 fasting').

    Returns:
        A grounded summary of live Google Search findings and factual references.
    """
    try:
        use_vertex = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("true", "1")
        project = os.environ.get("GOOGLE_CLOUD_PROJECT")
        location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
        if use_vertex or project:
            client = Client(vertexai=True, project=project, location=location)
        else:
            client = Client()
        response = client.models.generate_content(
            model=MODEL,
            contents=f"Search Google and answer accurately and concisely with up-to-date facts: {query}",
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())]
            ),
        )
        return response.text or "No search results found."
    except Exception as e:
        return f"Google Search grounding encountered an error: {e}"


def get_garmin_telemetry() -> Dict:
    """Retrieves multi-timeframe (Daily, 7-Day Weekly, 365-Day Yearly) Garmin Fenix 7 and Omron biometrics and telemetry, including resting heart rate, sleep score, average stress, HRV status, training readiness score (0-100), remaining recovery time in hours, multi-timeframe steps, body weight metrics, and live blood pressure readings & averages.

    Returns:
        A dictionary containing today's health, sleep, recovery, step count, blood pressure, and cardiac telemetry from Garmin Fenix 7 and Omron.
    """
    try:
        from garmin_sync import fetch_daily_telemetry
        return fetch_daily_telemetry()
    except Exception as e:
        today = datetime.date.today().isoformat()
        try:
            from garmin_sync import get_development_fallback_telemetry
            fb = get_development_fallback_telemetry(today)
            fb["note"] = f"Offline fallback telemetry active ({e})"
            return fb
        except Exception:
            return {
                "date": today,
                "daily_steps": 0,
                "garmin_steps": 0,
                "weekly_steps": 69700,
                "weekly_avg_steps": 9957,
                "yearly_steps": 3615000,
                "yearly_avg_steps": 9904,
                "latest_bp": "113/77 mmHg (Pulse: 51 bpm at 07:30 AM)",
                "blood_pressure": "113/77",
                "weekly_avg_bp": "114/76 mmHg",
                "yearly_avg_bp": "116/77 mmHg",
                "historical_bp_range": "108-124 / 68-82 mmHg",
                "weight_lbs": 200.0,
                "bmi": 33.3,
                "weight_goal_lbs": 185.0,
                "weekly_avg_weight": 200.4,
                "yearly_weight_delta": -6.0,
                "sleep_score": 80,
                "sleep_duration": "7h 45m",
                "sleep_quality": "Deep: 1h 35m | Light: 4h 20m | REM: 1h 50m | Awake: 25m",
                "weekly_avg_sleep_score": 82,
                "weekly_avg_sleep_dur": "7h 38m",
                "resting_heart_rate": 51,
                "rhr": 51,
                "max_hr": 124,
                "weekly_avg_rhr": 52,
                "hrv_status": "Balanced",
                "hrv_avg_ms": 52,
                "average_stress": 28,
                "daily_stress": 28,
                "weekly_avg_stress": 27,
                "pulse_ox": 98,
                "weekly_avg_pulse_ox": 97,
                "training_readiness": 78,
                "recovery_time_hours": 18,
                "body_battery_logged": True,
                "mode": "offline_fallback",
                "note": f"Offline fallback telemetry active ({e})"
            }


def format_live_telemetry_system_block(telemetry: Optional[Dict] = None) -> str:
    """Formats the multi-timeframe telemetry dictionary into the standardized structured context string."""
    if telemetry is None:
        telemetry = get_garmin_telemetry()

    def _fmt_int(val, default=0) -> str:
        if val is None:
            return f"{default:,}"
        if isinstance(val, (int, float)):
            return f"{int(val):,}"
        val_str = str(val).strip()
        if "," in val_str:
            return val_str
        try:
            return f"{int(float(val_str)):,}"
        except Exception:
            return val_str

    def _fmt_delta(val, default=-6.0) -> str:
        if val is None:
            val = default
        if isinstance(val, (int, float)):
            return f"{val:+}"
        val_str = str(val).strip()
        return val_str

    daily_steps = _fmt_int(telemetry.get("daily_steps") if telemetry.get("daily_steps") is not None else telemetry.get("garmin_steps", 0))
    weekly_steps = _fmt_int(telemetry.get("weekly_steps", 69700))
    weekly_avg_steps = _fmt_int(telemetry.get("weekly_avg_steps", 9957))
    yearly_steps = _fmt_int(telemetry.get("yearly_steps", 3615000))
    yearly_avg_steps = _fmt_int(telemetry.get("yearly_avg_steps", 9904))

    latest_bp = telemetry.get("latest_bp") or f"{telemetry.get('blood_pressure', '113/77')} mmHg"
    weekly_avg_bp = telemetry.get("weekly_avg_bp", "114/76 mmHg")
    yearly_avg_bp = telemetry.get("yearly_avg_bp", "116/77 mmHg")

    weight_lbs = telemetry.get("weight_lbs") or FIRESTORE_BIOMETRICS.get("current_weight_lbs", 200.0)
    weight_goal_lbs = telemetry.get("weight_goal_lbs", 185.0)
    weekly_avg_weight = telemetry.get("weekly_avg_weight", 200.4)
    yearly_weight_delta = _fmt_delta(telemetry.get("yearly_weight_delta", -6.0))

    sleep_score = telemetry.get("sleep_score", 80)
    sleep_duration = telemetry.get("sleep_duration", "7h 45m")
    weekly_avg_sleep_score = telemetry.get("weekly_avg_sleep_score", 82)
    weekly_avg_sleep_dur = telemetry.get("weekly_avg_sleep_dur", "7h 38m")

    rhr = telemetry.get("rhr") or telemetry.get("resting_heart_rate", 51)
    weekly_avg_rhr = telemetry.get("weekly_avg_rhr", 52)
    hrv_status = telemetry.get("hrv_status", "Balanced")
    hrv_avg_ms = telemetry.get("hrv_avg_ms", 52)
    daily_stress = telemetry.get("daily_stress") or telemetry.get("average_stress", 28)
    weekly_avg_stress = telemetry.get("weekly_avg_stress", 27)
    pulse_ox = telemetry.get("pulse_ox", 98)

    return (
        f"[LIVE GARMIN & BIOMETRIC TELEMETRY]\n"
        f"- STEPS: Today: {daily_steps} | 7-Day Total: {weekly_steps} (Avg: {weekly_avg_steps}) | 1-Year Total: {yearly_steps} (Avg: {yearly_avg_steps})\n"
        f"- BLOOD PRESSURE: Latest: {latest_bp} | 7-Day Avg: {weekly_avg_bp} | 1-Year Avg: {yearly_avg_bp}\n"
        f"- WEIGHT: Current: {weight_lbs} lbs (Goal: {weight_goal_lbs} lbs) | 7-Day Avg: {weekly_avg_weight} lbs | 1-Year Trend: {yearly_weight_delta} lbs\n"
        f"- SLEEP: Last Night: {sleep_score}/100 ({sleep_duration}) | 7-Day Avg: {weekly_avg_sleep_score}/100 ({weekly_avg_sleep_dur})\n"
        f"- CARDIOVASCULAR & RECOVERY: Resting HR: {rhr} bpm (7-Day Avg: {weekly_avg_rhr} bpm) | HRV Status: {hrv_status} ({hrv_avg_ms} ms) | Stress: {daily_stress} (7-Day Avg: {weekly_avg_stress}) | Pulse Ox: {pulse_ox}%"
    )


def fetch_youtube_video(exercise_name: str) -> str:
    """Retrieves a direct YouTube video tutorial URL for the given exercise using google_search_live with a strict 5-second timeout and fallback search URL.

    Args:
        exercise_name: The exercise movement name (e.g., 'Turkish Get-Up', 'Goblet Squat', 'Kettlebell Halo', 'Rotational Lunge', 'Single-Arm Kettlebell Swing').

    Returns:
        A direct YouTube watch URL (https://www.youtube.com/watch?v=...) or a standard search query fallback URL.
    """
    clean_name = exercise_name.strip()
    encoded_query = urllib.parse.quote_plus(f"{clean_name} exercise form tutorial")
    fallback_url = f"https://www.youtube.com/results?search_query={encoded_query}"
    search_query = f"site:youtube.com/watch {clean_name} instructional form"

    def _search_youtube() -> Optional[str]:
        raw_result = google_search_live(search_query)
        if not raw_result:
            return None
        # Extract YouTube watch?v= or youtu.be links from grounded search output
        match = re.search(r"https?://(?:www\.)?youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})", raw_result)
        if match:
            return f"https://www.youtube.com/watch?v={match.group(1)}"
        match_short = re.search(r"https?://youtu\.be/([a-zA-Z0-9_-]{11})", raw_result)
        if match_short:
            return f"https://www.youtube.com/watch?v={match_short.group(1)}"
        return None

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_search_youtube)
            result = future.result(timeout=5.0)
            if result:
                return result
    except Exception:
        pass

    return fallback_url


def generate_coach_instructions() -> str:
    """Dynamically builds the coach system prompt with calculated age, exact physical profile, expanded equipment suite, multi-timeframe telemetry baselines, and the User Override Protocol."""
    current_age = calculate_age_from_dob(STATIC_PROFILE.get("dob", "1966-12-12"))
    max_hr = 220 - current_age
    return f"""You are ApexPulse, an elite AI Fitness & Fasting Coach.

=== USER BIOMETRIC & PHYSICAL PROFILE ===
You coach a dedicated athlete with the following exact default profile:
1. DEMOGRAPHICS & BASELINES:
   - Age: {current_age} years old (Date of Birth: December 12, 1966, Age 59)
   - Height: 5'5" (65 inches / 165.1 cm)
   - Dynamic Body Weight: 200 lbs (tracked dynamically in Firestore, baseline 200 lbs)
   - Fasting Protocol: Strict 16/8 Intermittent Fasting (1:00 PM - 9:00 PM eating window with 2 meals).
   - Aerobic Equipment: Pooboo indoor cycling bike, walking pad, COOSPO chest strap.
   - Strength & Mobility Equipment: 15 lb kettlebell, Dumbbell pairs (3 lbs, 5 lbs, 8 lbs, 10 lbs, and 12 lbs), Circular balance board, Calf stretcher, Yoga mat.

=== STRICT CONSTRAINTS (MANDATORY DEFAULTS) ===
- Age: 59
- Height: 5'5"
- Weight: 200 lbs
- Fasting Protocol: 16/8 Intermittent Fasting
- Available Strength & Mobility Equipment:
  * 15 lb kettlebell
  * Dumbbell pairs: 3 lbs, 5 lbs, 8 lbs, 10 lbs, and 12 lbs
  * Circular balance board
  * Calf stretcher
  * Yoga mat

=== EQUIPMENT & PROGRAMMING RULES ===
- AVAILABLE EQUIPMENT SUITE: The user has access to a 15 lb kettlebell, dumbbell pairs (3 lbs, 5 lbs, 8 lbs, 10 lbs, 12 lbs), a circular balance board, a calf stretcher, and a yoga mat (plus the Pooboo bike, walking pad, and COOSPO chest strap).
- FULL PERMISSION & ENCOURAGEMENT: You are fully permitted and strongly encouraged to design functional longevity, progressive strength, joint stability, ankle/plantar mobility, balance, and core routines utilizing any combination of this available equipment.
- GYM BOUNDARIES: Do NOT recommend heavy commercial gym barbells, heavy gym machines, heavy weights beyond the user's available equipment suite, or unprompted pull-ups.

3. PROGRAMMING GOALS & METHODOLOGY:
   - Design longevity, mobility, core stability, balance, and functional resistance routines tailored for age {current_age}.
   - Primary strength & mobility movements:
     * Kettlebell (15 lbs): Turkish Get-Ups (TGU), Goblet Squats with isometric pauses, Halos, rotational lunges, single-arm swings, suitcase carries.
     * Dumbbells (3, 5, 8, 10, 12 lbs): Lateral raises, overhead presses, bicep curls, Romanian deadlifts, chest flyes, loaded carries, rotational presses.
     * Circular Balance Board: Ankle stability drills, single-leg stance, rotational balancing, core proprioception, paused squats on board.
     * Calf Stretcher: Gastroc/soleus deep stretching, Achilles tendon mobility, plantar fascia decompression, ankle dorsiflexion mobility.
     * Yoga Mat: Core flows, bird-dogs, dead bugs, thoracic spine rotations, hip mobility, stretching, and cool-downs.
   - Prioritize joint longevity, tempo control, isometric pauses, balance, and movement quality suitable for age {current_age}.

4. GARMIN CONNECT & OMRON MULTI-TIMEFRAME TELEMETRY INTEGRATION:
   - Actively reference multi-timeframe baselines across Daily (today / prior night), Weekly (trailing 7 days), and Yearly (trailing 365 days) streams:
     * Steps: Today count, 7-day total and daily average, 1-year total and 365-day daily average.
     * Blood Pressure: Latest reading (systolic/diastolic/pulse/timestamp), 7-day average, and 1-year average + historical range.
     * Weight & Body Composition: Current weight, BMI, goal, 7-day rolling weight average, and 365-day trend delta.
     * Sleep: Last night score, duration, sleep quality breakdown, and 7-day average score & duration.
     * Cardiovascular & Recovery: Resting HR, high HR, 7-day avg RHR, overnight HRV status (ms value & status), stress score (daily & 7-day avg), and Pulse Ox (daily & 7-day avg).
   - A2UI Visual Cards: Autonomously trigger `display_step_summary_card` for multi-timeframe step/walking analytics cards and `display_biometrics_summary_card` for the Master Biometrics Dashboard Card whenever requested or relevant.

5. HYBRID STEP TRACKING PROTOCOL:
   - Manual Override: If the user provides a specific manual step count in their prompt (e.g., "Log my steps: 5000", "5000 steps"), you MUST prioritize that manual number and trigger the `log_steps` tool to persist the override to Firestore.
   - Garmin Default / Sync: If the user asks for a general summary, checks today's progress, or requests to "Sync Garmin Steps" without providing a specific number, you MUST default to fetching and reporting the live `garmin_steps` from the active telemetry payload.

=== STRICT USER OVERRIDE PROTOCOL (GUEST MODE) ===
- THE RULE: You must treat the hardcoded default profile (Age 59, 5'5", Dynamic Weight 200 lbs, 16/8 fasting protocol, home equipment suite) and live Garmin telemetry as the absolute default for all queries.
- THE OVERRIDE: If the user explicitly provides alternate physical parameters in the prompt (e.g., "My friend is 35, 6'1, 200 lbs", "Plan a workout for a 40-year-old with a 35 lb kettlebell", "I'm asking for someone who has barbells"), you must temporarily ignore the default profile and Garmin data for that specific conversational turn.
- THE ACTION:
  1. Calculate recommendations based ONLY on the newly provided temporary parameters.
  2. State clearly and prominently in your response that you are in "Guest Mode" (e.g., "👥 **[Guest Mode Active]**: Designing recommendations based on your temporary parameters...").
  3. Note that the coach will automatically revert to the default profile (Age 59, 5'5", 200 lbs, 16/8 fasting protocol, home equipment suite) for subsequent questions.

=== LIFESTYLE & TELEMETRY REASONING LOGIC ===
1. Fasting-to-Sleep Correlation:
   - Analyze the user's `sleep_score` and `hrv_status` against their daily 16/8 fasting schedule (2 meals between 1:00 PM and 9:00 PM).
   - Determine if the timing of the two meals is positively or negatively impacting overnight deep sleep and REM cycles. Coach the user to finish their second meal 3 to 4 hours before bedtime to avoid elevated nighttime heart rates and digestive disruption of restorative sleep.
2. Zone 2 Optimization (Pooboo Bike & COOSPO Chest Strap):
   - Evaluate `resting_heart_rate`, `blood_pressure`, and `training_readiness` to dynamically calculate the Target Heart Rate for Zone 2 indoor cycling on the Pooboo bike.
   - For age {current_age}, Max HR is {max_hr} bpm. Using Heart Rate Reserve (Karvonen) with resting HR (~54 bpm), calculate Zone 2 aerobic intensity (60%–70% HRR, ~115–126 bpm).
   - Explicitly state this precise Target Heart Rate zone so the user can configure their COOSPO chest strap before hopping on the Pooboo bike.
3. Meal & Recovery Tracking (Strength & Mobility vs. Walking Pad):
   - Evaluate Garmin `recovery_time_hours` remaining from previous strength, mobility, or cycling sessions.
   - Cross-reference recovery time against the user's high-protein whole-food organic diet (targeting ~200g daily protein, 3.5g–4.0g leucine per meal).
   - If `recovery_time_hours` is low (<= 12 hours) and `training_readiness` is high (>= 70), suggest a functional strength, dumbbell, kettlebell, balance board, or mobility routine.
   - If `recovery_time_hours` is elevated (> 12-24 hours) or readiness is compromised, prescribe gentle calf stretching on the calf stretcher, yoga mat mobility flows, active recovery on the walking pad, and gentle Zone 2 flushing on the Pooboo bike.

=== AUTONOMOUS YOUTUBE VIDEO RETRIEVAL & LINKING RULES ===
1. Trigger:
   - Whenever you recommend an exercise (e.g., Goblet Squats with pauses, Turkish Get-Ups, Kettlebell Halos, Dumbbell Lateral Raises, Circular Balance Board Drills, Calf Stretcher Flows, Rotational Lunges, Single-Arm Swings, Suitcase Carries), or if the user explicitly asks for a video demonstration or technique tutorial, you MUST autonomously trigger the `fetch_youtube_video` tool for each movement.
2. Strict Link Verification & Zero Conversational Search Advice (MANDATORY):
   - You are STRICTLY FORBIDDEN from giving conversational advice on how to search (e.g., "Look for certified instructors...", "Search YouTube for...", "Find reputable trainers on YouTube...").
   - You are STRICTLY FORBIDDEN from hallucinating, guessing, assuming, or making up YouTube URLs.
   - You are STRICTLY FORBIDDEN from outputting bare unformatted URLs or plain text URLs.
   - You MUST ONLY trigger the `fetch_youtube_video` tool and format the returned verified URL as a clean Markdown link.
3. Markdown Link Formatting (STRICT):
   - Embed the link cleanly at the end of each exercise description strictly as a Markdown hyperlink:
     `[Watch {{Exercise Name}} Tutorial Here](URL)`
     (e.g., `[Watch Turkish Get-Up Tutorial Here](https://www.youtube.com/watch?v=0bWRPC49-M0)` or `[Watch Goblet Squat Tutorial Here](https://www.youtube.com/watch?v=VdGa_G1E1gU)`).
   - Never output raw text without Markdown link syntax.

=== SELF-CORRECTION & FIRESTORE MEMORY MANAGEMENT ===
- Trigger: If the user states a previous record is incorrect, fake, or needs to be deleted (e.g., "Please delete the fake indoor cycling record and the 8,450 step record from today", "remove the accidental squat log", "wipe yesterday's fake ride"), you MUST autonomously trigger the `delete_workout_record` tool to wipe the target record(s) from the Firestore database and active memory before formulating an updated response or summary.
- Confirmation: Always execute `delete_workout_record`, report what was removed from Firestore, and present an updated, clean summary of their actual records.

=== COACHING DOMAINS ===
1. Functional Longevity, Strength & Mobility (15 lb Kettlebell, 3-12 lb Dumbbell Pairs, Circular Balance Board, Calf Stretcher, Yoga Mat, joint longevity for age {current_age}).
2. Indoor Cycling (Pooboo bike, Zone 2 aerobic base building, cadence optimization, COOSPO chest strap target HR 115-126 bpm).
3. Walking & Step Tracking (Daily step tracking against a 10,000 daily step goal, walking pad active recovery, live `garmin_steps` telemetry and manual overrides).
4. 16/8 Intermittent Fasting (1:00 PM - 9:00 PM eating window, 2 meals, electrolyte management, fasting-to-sleep optimization).
5. High-Protein Whole-Food Organic Nutrition (200g daily protein for 200 lbs, 3.5g–4.0g leucine per meal, lean organic whole foods).
6. Live Scientific Grounding: Query the live web via `google_search_live` for cutting-edge exercise science, latest clinical studies, and age-adjusted longevity protocols.

Your coaching style is encouraging, highly structured, data-driven, and actionable.

Always enforce:
- Default to Age 59, Height 5'5", Weight 200 lbs, 16/8 fasting protocol, available equipment suite (15 lb kettlebell, 3-12 lb dumbbells, circular balance board, calf stretcher, yoga mat) unless User Override (Guest Mode) is explicitly triggered.
- If the user reports a fake, incorrect, or mistaken record, autonomously trigger `delete_workout_record` to wipe it from Firestore memory before presenting updated summaries.
- Follow the Hybrid Step Tracking protocol: log manual step numbers to Firestore with `log_steps`, but default to live `garmin_steps` from telemetry for general summaries and Garmin sync requests.
- Factor live Omron blood pressure (`blood_pressure`, e.g. 113/77 mmHg) into daily recovery and cardiovascular health assessments.
- Always retrieve verified video links using `fetch_youtube_video` when recommending exercises. Never give manual search advice.
- Inspect Garmin biometrics and multi-timeframe telemetry with `get_garmin_telemetry`.
- Render multi-timeframe step cards with `display_step_summary_card` and master biometrics dashboard cards with `display_biometrics_summary_card`.
- Query Google Search with `google_search_live` for external scientific validation whenever needed.
- Log dynamic weight changes in Firestore via `log_weight`.
- Retrieve biometric baselines and metrics via `get_user_biometric_profile`.
"""

COACH_INSTRUCTIONS = generate_coach_instructions()

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "project-281bf799-969f-49aa-917")
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")

# Vertex AI GenerativeModel initialization
try:
    import vertexai
    from vertexai.generative_models import GenerativeModel
    vertexai.init(project=PROJECT_ID, location=LOCATION)
    model = GenerativeModel(
        model_name=MODEL,
        system_instruction=COACH_INSTRUCTIONS,
    )
except Exception:
    model = None


def detect_guest_mode_override(prompt: str) -> bool:
    """Detects if the user is explicitly requesting recommendations for alternate physical parameters or a guest."""
    prompt_lower = prompt.lower()
    override_triggers = [
        "friend", "wife", "husband", "brother", "sister", "client", "guest mode",
        "for someone", "someone else", "another person", "partner", "differently",
        "hypothetically"
    ]
    has_alternate_demographics = any(
        phrase in prompt_lower for phrase in [
            "age ", "yo ", "years old", "6'", "5'1", "5'2", "5'3", "5'4", "5'6", "5'7", "5'8", "5'9", "5'10", "5'11", "6'0", "6'1", "6'2", "6'3", "6'4"
        ]
    ) and not any(own in prompt_lower for own in ["my age", "my height", "am 59", "5'5"])
    return any(t in prompt_lower for t in override_triggers) or has_alternate_demographics


def chat_with_gemini(
    prompt: str,
    uid: str = "default_user",
    image_base64: Optional[str] = None,
    image_mime_type: str = "image/jpeg",
    images: Optional[List[Union[str, Dict]]] = None
) -> str:
    """Executes an autonomous agentic loop with Gemini:
    1. EVALUATE: Checks user prompt and optional multimodal batch image inputs (max 5) against Fenix 7 & Omron biometrics, detects User Override / Guest Mode, and identifies self-correction/deletion commands.
    2. ACT: Autonomously triggers delete_workout_record for fake/incorrect records, handles hybrid step tracking, and google_search_live for research when needed.
    3. ITERATE: Processes tool output, biometrics, batch image data, and Firestore profile constraints (or Guest Mode overrides).
    4. RESPOND: Loops until a personalized routine/response is successfully formulated and validated, then returns the result.
    """
    global model
    if model is None:
        try:
            import vertexai
            from vertexai.generative_models import GenerativeModel
            vertexai.init(project=PROJECT_ID, location=LOCATION)
            model = GenerativeModel(
                model_name=MODEL,
                system_instruction=COACH_INSTRUCTIONS,
            )
        except Exception:
            model = None

    history = fetch_chat_history(uid)
    save_message(uid, "user", prompt)

    # Decode optional batch of base64 images into (bytes, mime_type) tuples (max 5 images limit)
    decoded_images: List[Tuple[bytes, str]] = []
    raw_images_list: List[Union[str, Dict]] = []

    if images and isinstance(images, list):
        raw_images_list.extend(images[:5])
    elif image_base64:
        raw_images_list.append({"image": image_base64, "mime_type": image_mime_type})

    for img_item in raw_images_list:
        raw_b64 = ""
        item_mime = "image/jpeg"
        if isinstance(img_item, dict):
            raw_b64 = img_item.get("base64") or img_item.get("image") or ""
            item_mime = img_item.get("mime_type") or img_item.get("mimeType") or "image/jpeg"
        elif isinstance(img_item, str):
            raw_b64 = img_item
            item_mime = "image/jpeg"

        raw_b64 = raw_b64.strip()
        if not raw_b64:
            continue

        if "," in raw_b64:
            header, raw_b64 = raw_b64.split(",", 1)
            if "data:" in header and ";base64" in header:
                detected_mime = header.split("data:")[1].split(";base64")[0]
                if detected_mime:
                    item_mime = detected_mime
        try:
            img_bytes = base64.b64decode(raw_b64)
            if img_bytes:
                decoded_images.append((img_bytes, item_mime))
        except Exception as e:
            print(f"⚠️ Base64 batch image decoding notice: {e}")

    # Strictly enforce 5-image maximum limit
    decoded_images = decoded_images[:5]

    # 1. EVALUATE: Assess telemetry, baseline constraints, and User Override Protocol
    is_guest_mode = detect_guest_mode_override(prompt)
    telemetry = get_garmin_telemetry()
    telemetry_mode = telemetry.get("mode", "offline_fallback")
    telemetry_block = format_live_telemetry_system_block(telemetry)
    garmin_steps = telemetry.get("daily_steps") or telemetry.get("garmin_steps", 0)

    # Hybrid Step Tracking & Auto-sync Logic
    prompt_lower = prompt.lower()
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    
    # Check if user provided an explicit manual step count in prompt (e.g. "Log my steps: 5000")
    manual_step_match = re.search(r"(?:log|record|set)\s+(?:my\s+)?steps?[:\s]+([0-9,]+)", prompt_lower) or re.search(r"([0-9,]+)\s+steps", prompt_lower)
    manual_steps_val = None
    if manual_step_match:
        try:
            raw_num = manual_step_match.group(1).replace(",", "")
            if int(raw_num) > 0 and any(k in prompt_lower for k in ["step", "log", "walk"]):
                manual_steps_val = int(raw_num)
        except Exception:
            pass

    if manual_steps_val is not None:
        # User specified a manual step number: prioritize and persist to Firestore
        log_steps(steps=manual_steps_val)
    elif telemetry_mode == "live_garmin_connect":
        # ONLY auto-sync live Garmin steps if mode is live_garmin_connect
        if any(phrase in prompt_lower for phrase in ["sync garmin", "fenix 7", "garmin steps", "refresh steps"]):
            if isinstance(garmin_steps, (int, float)) and garmin_steps >= 0:
                sync_garmin_steps_to_db(int(garmin_steps), today_str)
        else:
            # General summary / query without number: sync from Garmin if no manual override is active
            today_entry = next((item for item in STEP_LOGS if item["date"] == today_str), None)
            if not today_entry or today_entry.get("source") != "manual_entry":
                if isinstance(garmin_steps, (int, float)) and garmin_steps >= 0:
                    sync_garmin_steps_to_db(int(garmin_steps), today_str)

    # Check for memory self-correction / record deletion requests
    deletion_summary = ""
    is_deletion_request = any(
        k in prompt_lower for k in ["delete", "remove", "wipe", "erase", "clear", "fake", "incorrect record", "wrong record"]
    ) and any(
        target in prompt_lower for target in ["cycling", "bike", "ride", "step", "steps", "8450", "8,450", "workout", "strength", "squat", "record", "today"]
    )
    if is_deletion_request:
        deleted_details = []
        if any(k in prompt_lower for k in ["cycling", "bike", "ride"]):
            r = delete_workout_record(uid=uid, record_type="indoor_cycling", date="today")
            deleted_details.append(f"indoor cycling session ({r.get('deleted_from_firestore_sessions', 0)} Firestore documents wiped, active workout logs cleared)")
        if any(k in prompt_lower for k in ["step", "8450", "8,450"]):
            r = delete_workout_record(uid=uid, record_type="steps", date="today")
            deleted_details.append(f"8,450 step entry ({r.get('deleted_from_firestore_sessions', 0)} Firestore documents wiped, active step logs cleared)")
        if not deleted_details:
            r = delete_workout_record(uid=uid, record_type="all", date="today")
            deleted_details.append(f"target records ({r.get('deleted_from_firestore_sessions', 0)} Firestore documents wiped)")
        deletion_summary = "Wiped from Firestore database: " + "; ".join(deleted_details)

    # Autonomous Agentic Reasoning & Action Loop
    max_loop_iterations = 3
    iteration = 0
    external_validation_context = ""
    final_response = ""
    current_prompt = prompt

    while iteration < max_loop_iterations:
        iteration += 1

        # 2. ACT: Check if external research validation is required
        prompt_lower = current_prompt.lower()
        needs_external_research = any(
            keyword in prompt_lower
            for keyword in ["research", "study", "scientific", "protocol", "longevity", "latest", "science", "creatine", "hypertrophy", "tgu", "turkish get-up", "kettlebell", "dumbbell", "balance board", "calf stretcher", "mobility"]
        ) and not external_validation_context

        if needs_external_research:
            search_query = f"functional longevity exercise science protocol {current_prompt}"
            try:
                external_validation_context = google_search_live(search_query)
            except Exception as e:
                external_validation_context = f"Live search validation note: {e}"

        # 3. ITERATE: Build rich agentic context based on default vs override mode
        if is_guest_mode:
            agentic_context_payload = f"""[AUTONOMOUS AGENTIC CONTEXT - USER OVERRIDE: GUEST MODE ACTIVE]
- OVERRIDE PROTOCOL TRIGGERED: Alternate parameters provided in prompt. Temporarily ignoring default Age 59 / 5'5" / home equipment profile and Garmin biometrics for this turn.
- ACTION REQUIRED: 
  1. Calculate recommendations based ONLY on the newly provided temporary parameters in the prompt.
  2. Clearly state at the beginning that you are in "Guest Mode".
  3. Clarify that you will automatically revert to the default profile (Age 59, 5'5", home equipment suite) on the next query.
{f"- External Scientific Research Validation: {external_validation_context}" if external_validation_context else ""}
{f"- Firestore Memory Management Action: {deletion_summary}" if deletion_summary else ""}
{f"- Multimodal Input Attached: User provided {len(decoded_images)} image(s) ({', '.join([m for _, m in decoded_images])}). Analyze all image features (exercise technique, nutrition/meal, equipment, biometric logs, progression photos) in conjunction with user request." if decoded_images else ""}

User Request: {current_prompt}
"""
        else:
            agentic_context_payload = f"""[AUTONOMOUS AGENTIC REASONING CONTEXT - DEFAULT PROFILE]
{telemetry_block}
- User Baselines: Age 59, Height 5'5", Dynamic Body Weight 200 lbs, 16/8 Fasting (1:00 PM - 9:00 PM, 2 meals).
- AVAILABLE EQUIPMENT SUITE: 15 lb kettlebell, Dumbbell pairs (3, 5, 8, 10, 12 lbs), Circular balance board, Calf stretcher, Yoga mat, Pooboo indoor cycling bike, walking pad, COOSPO chest strap.
- PROGRAMMING FOCUS: Functional longevity, strength, joint mobility, ankle/plantar stretching, circular balance board stability, and core control. Fully permitted and encouraged to design routines utilizing any combination of available equipment. Do NOT recommend commercial gym barbells, heavy gym machines, or pull-ups.
- Zone 2 Target HR: 115–126 bpm for Pooboo bike / COOSPO chest strap.
- VISUAL A2UI CARDS: Autonomously trigger `display_step_summary_card` for multi-timeframe step/walking analytics cards and `display_biometrics_summary_card` for master biometrics dashboard cards.
- VIDEO LINKING RULE: Return direct YouTube URLs from fetch_youtube_video only; do NOT give conversational advice on searching YouTube.
{f"- FIRESTORE MEMORY DELETION COMPLETED: {deletion_summary}. Confirm the deletion of the fake records to the user clearly." if deletion_summary else ""}
{f"- External Scientific Research Validation: {external_validation_context}" if external_validation_context else ""}
{f"- Multimodal Input Attached: User provided {len(decoded_images)} image(s) ({', '.join([m for _, m in decoded_images])}). Analyze all image features (exercise technique, nutrition/meal, equipment, biometric logs, progression photos) in conjunction with user request." if decoded_images else ""}

User Request: {current_prompt}
"""

        try:
            full_prompt_text = f"{COACH_INSTRUCTIONS}\n\n{agentic_context_payload}"
            
            # Prepare google.genai Content parts: single text prompt + distinct inline data parts for each attached image
            genai_content_parts = [types.Part.from_text(text=full_prompt_text)]
            for img_bytes, img_mime in decoded_images:
                genai_content_parts.append(types.Part.from_bytes(data=img_bytes, mime_type=img_mime))

            if model is not None and not decoded_images:
                chat = model.start_chat(history=history)
                response = chat.send_message(agentic_context_payload)
                candidate_text = response.text if hasattr(response, "text") else str(response)
            else:
                use_vertex = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("true", "1")
                proj = os.environ.get("GOOGLE_CLOUD_PROJECT", "project-281bf799-969f-49aa-917")
                loc = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
                genai_client = Client(vertexai=True, project=proj, location=loc) if (use_vertex or proj) else Client()
                resp = genai_client.models.generate_content(
                    model=MODEL,
                    contents=genai_content_parts,
                )
                candidate_text = resp.text or ""
        except Exception as e:
            candidate_text = f"Agentic loop execution encountered an issue: {e}"

        # 4. RESPOND & VALIDATE CONSTRAINTS
        if is_guest_mode:
            # In Guest Mode, ensure Guest Mode is acknowledged
            if "guest mode" in candidate_text.lower() or "guest" in candidate_text.lower():
                final_response = candidate_text
                break
            else:
                candidate_text = f"👥 **[Guest Mode Active]**\n\n{candidate_text}\n\n*(Note: Reverting to default Age 59 / home equipment profile for your next question.)*"
                final_response = candidate_text
                break
        else:
            # In default mode, check that candidate response does not recommend unowned commercial gym equipment
            candidate_lower = candidate_text.lower()
            violates_equipment = any(
                forbidden in candidate_lower
                for forbidden in ["barbell", "pull-up", "pull up", "pullups", "heavy deadlift", "smith machine", "leg press machine"]
            )

            if not violates_equipment and len(candidate_text.strip()) > 0:
                final_response = candidate_text
                break  # Successfully formulated personalized routine and verified constraints
            else:
                # Re-iterate and enforce correction in the agentic loop
                current_prompt = f"{prompt}\n[STRICT CORRECTION: You must program using ONLY the available equipment: 15 lb kettlebell, 3-12 lb dumbbells, circular balance board, calf stretcher, yoga mat, Pooboo bike, and walking pad. Barbells, heavy machines, and pull-ups are not available.]"

    if not final_response:
        final_response = candidate_text

    save_message(uid, "model", final_response)
    return final_response



root_agent = Agent(
    name="apex_pulse_coach",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
        client_kwargs={
            "vertexai": True,
            "project": PROJECT_ID,
            "location": LOCATION,
        },
    ),
    instruction=COACH_INSTRUCTIONS,
    tools=[
        fetch_youtube_video,
        get_garmin_telemetry,
        google_search_live,
        delete_workout_record,
        log_weight,
        get_user_biometric_profile,
        log_steps,
        get_step_summary,
        display_step_summary_card,
        display_biometrics_summary_card,
        log_strength_workout,
        log_cycling_session,
        check_fasting_status,
        calculate_protein_targets,
        get_workout_and_fasting_summary
    ],
    after_model_callback=a2ui_callback,
)

app = App(
    root_agent=root_agent,
    name="app",
)

if __name__ == "__main__":
    print("=" * 60)
    print("⚡ ApexPulse AI Fitness & Fasting Coach Initialized")
    print("=" * 60)
    profile = get_user_biometric_profile()
    sb = profile["static_baselines"]
    df = profile["dynamic_firestore_metrics"]
    print(f"👤 Profile Baselines: Age {sb['age']} | Height {sb['height']} | Dynamic Weight: {df['current_weight_lbs']} lbs | BMI: {df['bmi']}")
    print(f"🏋️ Equipment Constraint: {sb['equipment_constraint']}")
    print(f"⏱️ Fasting Protocol: 16/8 Intermittent Fasting")
    
    telemetry = get_garmin_telemetry()
    print(f"⌚ Fenix 7 Telemetry: Readiness: {telemetry.get('training_readiness')}/100 | Recovery: {telemetry.get('recovery_time_hours')}h | HRV: {telemetry.get('hrv_status')} | Resting HR: {telemetry.get('resting_heart_rate')} bpm")
    print("-" * 60)
    
    test_query = "What strength and mobility workout routine do you recommend today using my kettlebell, dumbbells, balance board, and calf stretcher based on my recovery and readiness?"
    print(f"💬 Prompt: {test_query}\n")
    response = chat_with_gemini(test_query)
    print(f"🤖 ApexPulse Response:\n{response}")
    print("=" * 60)


