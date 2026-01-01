# MFS Literacy Platform - Phase 2: Complete Backend
# AI-Powered Adaptive Learning System

from fastapi import FastAPI, HTTPException, Depends, Request, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import sqlite3
import psycopg2
import psycopg2.extras
import bcrypt
import jwt
from datetime import datetime, timedelta
import openai
import os
import json
from pathlib import Path
import random

# Import our new utilities
from readability import analyze_readability, get_difficulty_for_user
from content_generator import ContentGenerator

# Initialize FastAPI
app = FastAPI(title="MFS Literacy Assessment Platform - Phase 2")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
SECRET_KEY = os.getenv("SECRET_KEY", "mfs-literacy-platform-secret-key-change-in-production")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
openai.api_key = OPENAI_API_KEY

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

USE_POSTGRES = DATABASE_URL is not None
DATABASE = DATABASE_URL if USE_POSTGRES else "mfs_literacy.db"

# Initialize content generator
content_generator = ContentGenerator(OPENAI_API_KEY) if OPENAI_API_KEY else None

print(f"Using {'PostgreSQL' if USE_POSTGRES else 'SQLite'} database")
print(f"OpenAI API {'configured' if OPENAI_API_KEY else 'NOT configured'}")

# Pydantic models (existing + new)
class UserCreate(BaseModel):
    email: str
    password: str
    full_name: str
    role: str = "student"
    age_band: Optional[str] = None
    
class UserLogin(BaseModel):
    email: str
    password: str

class InterestOnboarding(BaseModel):
    interests: List[str]
    topics: List[str]
    age_band: Optional[str] = None
    grade_preference: Optional[str] = None

class ReadingFeedback(BaseModel):
    passage_id: int
    feedback: str  # 'too_easy', 'just_right', 'too_hard'
    time_spent: int
    completed: bool

class ComprehensionAnswers(BaseModel):
    passage_id: int
    answers: List[Dict]
    time_spent: int

class DiscussionMessage(BaseModel):
    passage_id: Optional[int] = None
    message: str

class WritingSubmission(BaseModel):
    prompt: str
    response: str
    passage_id: Optional[int] = None

class WritingRevision(BaseModel):
    exercise_id: int
    revised_response: str

# Database initialization
def init_db():
    if USE_POSTGRES:
        conn = psycopg2.connect(DATABASE)
        cursor = conn.cursor()
        
        # Original tables (simplified - assume migration ran)
        # Users, assessments, lessons, progress tables exist
        
        # Ensure new columns exist in users table
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS age_band VARCHAR(20)")
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS grade_band VARCHAR(20)")
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS interest_tags TEXT")
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS level_estimate VARCHAR(20)")
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS words_per_session INTEGER DEFAULT 0")
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS total_passages_read INTEGER DEFAULT 0")
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS comprehension_score REAL DEFAULT 0")
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_active TIMESTAMP")
            conn.commit()
        except:
            conn.rollback()
        
    else:
        conn = sqlite3.connect(DATABASE, timeout=30.0)
        conn.execute('PRAGMA journal_mode=WAL')
        cursor = conn.cursor()
        
        # Create all tables for SQLite (for local development)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                full_name TEXT NOT NULL,
                role TEXT NOT NULL,
                reading_level TEXT,
                interests TEXT,
                age_band TEXT,
                grade_band TEXT,
                interest_tags TEXT,
                level_estimate TEXT,
                words_per_session INTEGER DEFAULT 0,
                total_passages_read INTEGER DEFAULT 0,
                comprehension_score REAL DEFAULT 0,
                last_active TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create admin
        admin_hash = bcrypt.hashpw("admin123".encode('utf-8'), bcrypt.gensalt())
        try:
            cursor.execute(
                "INSERT INTO users (email, password_hash, full_name, role) VALUES (?, ?, ?, ?)",
                ("admin@mfs.org", admin_hash.decode('utf-8'), "MFS Administrator", "admin")
            )
        except sqlite3.IntegrityError:
            pass
    
    conn.commit()
    conn.close()

init_db()

# Helper functions
def get_db():
    if USE_POSTGRES:
        conn = psycopg2.connect(DATABASE)
        conn.cursor_factory = psycopg2.extras.RealDictCursor
        return conn
    else:
        conn = sqlite3.connect(DATABASE, timeout=30.0, check_same_thread=False)
        conn.execute('PRAGMA journal_mode=WAL')
        conn.row_factory = sqlite3.Row
        return conn

def create_token(user_id: int, role: str) -> str:
    payload = {
        "user_id": user_id,
        "role": role,
        "exp": datetime.utcnow() + timedelta(days=7)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

def verify_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

def update_user_activity(user_id: int):
    """Update last_active timestamp"""
    conn = get_db()
    cursor = conn.cursor()
    if USE_POSTGRES:
        cursor.execute("UPDATE users SET last_active = NOW() WHERE id = %s", (user_id,))
    else:
        cursor.execute("UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()

# ============================================
# STATIC FILE ROUTES
# ============================================

@app.get("/", response_class=HTMLResponse)
async def serve_landing():
    return FileResponse("static/index.html")

@app.get("/dashboard", response_class=HTMLResponse)
async def serve_dashboard():
    return FileResponse("static/dashboard.html")

@app.get("/admin-dashboard", response_class=HTMLResponse)
async def serve_admin():
    return FileResponse("static/admin-dashboard.html")

@app.get("/reading", response_class=HTMLResponse)
async def serve_reading():
    return FileResponse("static/reading.html")

@app.get("/writing", response_class=HTMLResponse)
async def serve_writing():
    return FileResponse("static/writing.html")

# ============================================
# AUTHENTICATION (Original)
# ============================================

@app.post("/api/register")
async def register(user: UserCreate):
    conn = get_db()
    cursor = conn.cursor()
    
    password_hash = bcrypt.hashpw(user.password.encode('utf-8'), bcrypt.gensalt())
    
    try:
        if USE_POSTGRES:
            cursor.execute(
                """INSERT INTO users (email, password_hash, full_name, role, age_band) 
                   VALUES (%s, %s, %s, %s, %s) RETURNING id""",
                (user.email, password_hash.decode('utf-8'), user.full_name, user.role, user.age_band)
            )
            result = cursor.fetchone()
            user_id = result['id']
        else:
            cursor.execute(
                "INSERT INTO users (email, password_hash, full_name, role, age_band) VALUES (?, ?, ?, ?, ?)",
                (user.email, password_hash.decode('utf-8'), user.full_name, user.role, user.age_band)
            )
            user_id = cursor.lastrowid
        
        conn.commit()
        token = create_token(user_id, user.role)
        
        return {
            "success": True,
            "token": token,
            "user": {
                "id": user_id,
                "email": user.email,
                "full_name": user.full_name,
                "role": user.role
            }
        }
    except (sqlite3.IntegrityError, psycopg2.errors.UniqueViolation):
        conn.rollback()
        raise HTTPException(status_code=400, detail="Email already registered")
    except Exception as e:
        conn.rollback()
        print(f"Registration error: {e}")
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")
    finally:
        conn.close()

@app.post("/api/login")
async def login(credentials: UserLogin):
    conn = get_db()
    cursor = conn.cursor()
    
    if USE_POSTGRES:
        cursor.execute("SELECT * FROM users WHERE email = %s", (credentials.email,))
    else:
        cursor.execute("SELECT * FROM users WHERE email = ?", (credentials.email,))
    
    user = cursor.fetchone()
    conn.close()
    
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    password_hash = user['password_hash']
    
    if not bcrypt.checkpw(credentials.password.encode('utf-8'), password_hash.encode('utf-8')):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Update last active
    update_user_activity(user['id'])
    
    token = create_token(user['id'], user['role'])
    
    return {
        "success": True,
        "token": token,
        "user": {
            "id": user['id'],
            "email": user['email'],
            "full_name": user['full_name'],
            "role": user['role'],
            "reading_level": user.get('reading_level'),
            "interests": user.get('interests'),
            "level_estimate": user.get('level_estimate')
        }
    }

# ============================================
# ASSESSMENT ENDPOINTS (Phase 1 + Phase 2)
# ============================================

async def generate_interest_assessment() -> List[Dict]:
    """Generate questions to assess student's reading interests"""
    
    # Comprehensive fallback questions (always work!)
    fallback_questions = [
        {
            "id": 1,
            "question": "What type of stories interest you most?",
            "options": ["Adventure and action", "Real-life stories and biographies", "Science and technology", "Sports and fitness"],
            "category": "genre"
        },
        {
            "id": 2,
            "question": "Which topic sounds most interesting to you?",
            "options": ["Technology and computers", "History and culture", "Nature and animals", "Music and arts"],
            "category": "topic"
        },
        {
            "id": 3,
            "question": "What do you enjoy reading about?",
            "options": ["How things work", "Famous people's lives", "Fantasy and imagination", "Current events and news"],
            "category": "interest"
        },
        {
            "id": 4,
            "question": "Which activity interests you most?",
            "options": ["Playing sports", "Using technology", "Creating art", "Helping others"],
            "category": "activity"
        },
        {
            "id": 5,
            "question": "What would you like to learn more about?",
            "options": ["Space and planets", "Business and money", "Health and fitness", "Entertainment and movies"],
            "category": "learning"
        },
        {
            "id": 6,
            "question": "What kind of book would you pick up?",
            "options": ["A mystery to solve", "A guide or how-to book", "A story about real events", "A book with pictures and graphics"],
            "category": "format"
        },
        {
            "id": 7,
            "question": "Which career field sounds interesting?",
            "options": ["Medicine and healthcare", "Engineering and building", "Law and justice", "Creative arts and design"],
            "category": "career"
        },
        {
            "id": 8,
            "question": "What do you do in your free time?",
            "options": ["Watch videos online", "Play games", "Read or research", "Spend time outdoors"],
            "category": "hobby"
        },
        {
            "id": 9,
            "question": "Which subject was your favorite in school?",
            "options": ["Math and numbers", "English and writing", "Science experiments", "Social studies and history"],
            "category": "subject"
        },
        {
            "id": 10,
            "question": "What type of content do you enjoy most?",
            "options": ["Short articles and posts", "Long detailed explanations", "Visual content with images", "Step-by-step instructions"],
            "category": "content_type"
        }
    ]
    
    # Try OpenAI first if available
    if not OPENAI_API_KEY or OPENAI_API_KEY == "":
        print("No OpenAI API key - using fallback questions")
        return fallback_questions
    
    try:
        print("Calling OpenAI to generate assessment questions...")
        
        prompt = """Generate 10 multiple-choice questions to assess a student's reading interests.
        Each question should help identify topics they enjoy (sports, technology, history, fiction, science, etc.).
        
        Return a JSON array with this structure:
        [
            {
                "id": 1,
                "question": "What type of stories interest you most?",
                "options": ["Adventure stories", "Real-life stories", "Science topics", "Sports news"],
                "category": "genre"
            }
        ]
        
        Make questions engaging and appropriate for diverse reading levels."""
        
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are an expert educator creating reading assessments."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            timeout=10
        )
        
        print("OpenAI response received, parsing...")
        
        content = response.choices[0].message.content
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        
        questions = json.loads(content)
        print(f"Successfully parsed {len(questions)} AI-generated questions")
        return questions
        
    except Exception as e:
        print(f"OpenAI error: {e} - using fallback questions")
        return fallback_questions

async def analyze_assessment_results(answers: List[Dict]) -> Dict:
    """Analyze assessment answers to determine interests and reading level"""
    
    # Extract interests from answers
    interests = []
    topics = []
    
    for answer in answers:
        category = answer.get('category', '')
        selected = answer.get('answer', '')
        
        if category in ['genre', 'topic', 'interest', 'learning']:
            topics.append(selected.lower())
        
    # Determine reading level based on answer patterns
    # For now, default to intermediate
    reading_level = "intermediate"
    
    # Extract unique interests
    unique_interests = list(set(topics))[:5]  # Top 5
    
    return {
        "reading_level": reading_level,
        "interests": unique_interests if unique_interests else ["general reading"],
        "topics": topics
    }

@app.get("/api/assessment/interest")
async def get_interest_assessment():
    """Get interest assessment questions (Phase 1 compatibility)"""
    print("Assessment endpoint called - generating questions...")
    try:
        questions = await generate_interest_assessment()
        print(f"Generated {len(questions)} questions")
        return {"questions": questions}
    except Exception as e:
        print(f"Error generating assessment: {e}")
        raise HTTPException(status_code=500, detail=f"Assessment generation failed: {str(e)}")

@app.post("/api/assessment/submit")
async def submit_assessment(request: Request):
    """Submit assessment results (Phase 1 compatibility)"""
    data = await request.json()
    token = data.get("token")
    answers = data.get("answers", [])
    
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    user_data = verify_token(token)
    user_id = user_data["user_id"]
    
    # Analyze results
    analysis = await analyze_assessment_results(answers)
    
    # Update user profile
    conn = get_db()
    cursor = conn.cursor()
    
    if USE_POSTGRES:
        cursor.execute(
            """UPDATE users 
               SET reading_level = %s, interests = %s, interest_tags = %s, level_estimate = %s
               WHERE id = %s""",
            (analysis['reading_level'], json.dumps(analysis['interests']), 
             json.dumps(analysis['interests']), analysis['reading_level'], user_id)
        )
    else:
        cursor.execute(
            """UPDATE users 
               SET reading_level = ?, interests = ?, interest_tags = ?, level_estimate = ?
               WHERE id = ?""",
            (analysis['reading_level'], json.dumps(analysis['interests']),
             json.dumps(analysis['interests']), analysis['reading_level'], user_id)
        )
    
    conn.commit()
    conn.close()
    
    update_user_activity(user_id)
    
    return {
        "success": True,
        "analysis": analysis
    }

# ============================================
# PHASE 2: ONBOARDING ENDPOINTS
# ============================================

@app.post("/api/onboard/interests")
async def onboard_interests(request: Request):
    """Process interest onboarding and update user profile"""
    data = await request.json()
    token = data.get("token")
    interests = data.get("interests", [])
    topics = data.get("topics", [])
    age_band = data.get("age_band")
    
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    user_data = verify_token(token)
    user_id = user_data["user_id"]
    
    # Combine interests and topics
    all_interests = list(set(interests + topics))
    
    # Determine initial level estimate based on age
    level_map = {
        "18-24": "intermediate",
        "25-34": "intermediate",
        "35-44": "intermediate",
        "45+": "intermediate",
        "under-18": "beginner"
    }
    level_estimate = level_map.get(age_band, "intermediate")
    
    # Determine grade band
    grade_map = {
        "under-18": "high",
        "18-24": "adult",
        "25-34": "adult",
        "35-44": "adult",
        "45+": "adult"
    }
    grade_band = grade_map.get(age_band, "adult")
    
    # Update user profile
    conn = get_db()
    cursor = conn.cursor()
    
    if USE_POSTGRES:
        cursor.execute(
            """UPDATE users 
               SET interest_tags = %s, age_band = %s, level_estimate = %s, grade_band = %s, last_active = NOW()
               WHERE id = %s""",
            (json.dumps(all_interests), age_band, level_estimate, grade_band, user_id)
        )
    else:
        cursor.execute(
            """UPDATE users 
               SET interest_tags = ?, age_band = ?, level_estimate = ?, grade_band = ?, last_active = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (json.dumps(all_interests), age_band, level_estimate, grade_band, user_id)
        )
    
    conn.commit()
    conn.close()
    
    update_user_activity(user_id)
    
    return {
        "success": True,
        "profile": {
            "interests": all_interests,
            "level_estimate": level_estimate,
            "grade_band": grade_band
        }
    }

# ============================================
# PHASE 2: READING ENDPOINTS
# ============================================

@app.get("/api/read/sample")
async def get_reading_sample(token: str, challenge: str = "appropriate"):
    """Get a reading passage matched to user's level and interests"""
    user_data = verify_token(token)
    user_id = user_data["user_id"]
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Get user profile
    if USE_POSTGRES:
        cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    else:
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    
    user = cursor.fetchone()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    level_estimate = user.get('level_estimate') or 'intermediate'
    interest_tags = json.loads(user.get('interest_tags') or '[]')
    total_read = user.get('total_passages_read') or 0
    
    # For first passage, make it easier (quick win strategy)
    if total_read == 0:
        challenge = "easier"
        target_words = 150
    else:
        target_words = 200
    
    # Try to get a passage from database first
    # TODO: Implement database passage retrieval with matching
    # For now, generate a new one
    
    if not content_generator:
        raise HTTPException(status_code=503, detail="Content generation not available. Please configure OpenAI API key.")
    
    # Pick a topic from interests or random
    topic = random.choice(interest_tags) if interest_tags else random.choice(["science", "technology", "history", "nature"])
    
    # Adjust difficulty based on challenge parameter
    difficulty_map = {
        "easier": "beginner" if level_estimate == "intermediate" else level_estimate,
        "appropriate": level_estimate,
        "challenging": "advanced" if level_estimate == "intermediate" else level_estimate
    }
    difficulty = difficulty_map.get(challenge, level_estimate)
    
    print(f"Generating passage: topic={topic}, difficulty={difficulty}, words={target_words}")
    
    try:
        # Generate passage
        passage_data = content_generator.generate_passage(
            topic=topic,
            difficulty_level=difficulty,
            target_words=target_words,
            user_interests=interest_tags
        )
        
        # Save to database
        if USE_POSTGRES:
            cursor.execute(
                """INSERT INTO passages 
                   (title, content, source, topic_tags, word_count, readability_score, flesch_ease, 
                    difficulty_level, estimated_minutes, approved, created_by)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                (passage_data['title'], passage_data['content'], passage_data['source'],
                 json.dumps(passage_data['topic_tags']), passage_data['word_count'],
                 passage_data.get('readability_score'), passage_data.get('flesch_ease'),
                 passage_data['difficulty_level'], passage_data.get('estimated_minutes'),
                 True, 1)  # Auto-approve AI content for now
            )
            result = cursor.fetchone()
            passage_id = result['id']
        else:
            cursor.execute(
                """INSERT INTO passages 
                   (title, content, source, topic_tags, word_count, readability_score, flesch_ease,
                    difficulty_level, estimated_minutes, approved, created_by)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (passage_data['title'], passage_data['content'], passage_data['source'],
                 json.dumps(passage_data['topic_tags']), passage_data['word_count'],
                 passage_data.get('readability_score'), passage_data.get('flesch_ease'),
                 passage_data['difficulty_level'], passage_data.get('estimated_minutes'),
                 True, 1)
            )
            passage_id = cursor.lastrowid
        
        # Generate comprehension questions
        questions = content_generator.generate_comprehension_questions(
            passage_text=passage_data['content'],
            passage_title=passage_data['title'],
            num_questions=3  # Start with 3 questions
        )
        
        # Save questions
        for q in questions:
            if USE_POSTGRES:
                cursor.execute(
                    """INSERT INTO passage_questions 
                       (passage_id, question_text, question_type, correct_answer, options, explanation, difficulty)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                    (passage_id, q['question'], q.get('type'), q['correct_answer'],
                     json.dumps(q.get('options', [])), q.get('explanation'), q.get('difficulty', 1))
                )
            else:
                cursor.execute(
                    """INSERT INTO passage_questions 
                       (passage_id, question_text, question_type, correct_answer, options, explanation, difficulty)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (passage_id, q['question'], q.get('type'), q['correct_answer'],
                     json.dumps(q.get('options', [])), q.get('explanation'), q.get('difficulty', 1))
                )
        
        # Create session log
        if USE_POSTGRES:
            cursor.execute(
                """INSERT INTO session_logs (user_id, passage_id, started_at)
                   VALUES (%s, %s, NOW()) RETURNING id""",
                (user_id, passage_id)
            )
            result = cursor.fetchone()
            session_id = result['id']
        else:
            cursor.execute(
                """INSERT INTO session_logs (user_id, passage_id, started_at)
                   VALUES (?, ?, CURRENT_TIMESTAMP)""",
                (user_id, passage_id)
            )
            session_id = cursor.lastrowid
        
        conn.commit()
        conn.close()
        
        update_user_activity(user_id)
        
        return {
            "passage_id": passage_id,
            "session_id": session_id,
            "title": passage_data['title'],
            "content": passage_data['content'],
            "word_count": passage_data['word_count'],
            "estimated_minutes": passage_data.get('estimated_minutes', 2),
            "difficulty_level": passage_data['difficulty_level'],
            "vocabulary": passage_data.get('vocabulary_words', []),
            "questions": questions,
            "is_first_passage": total_read == 0
        }
        
    except Exception as e:
        conn.close()
        print(f"Error generating passage: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate passage: {str(e)}")

@app.post("/api/read/feedback")
async def submit_reading_feedback(request: Request):
    """Submit feedback on passage difficulty"""
    data = await request.json()
    token = data.get("token")
    
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    user_data = verify_token(token)
    user_id = user_data["user_id"]
    
    session_id = data.get("session_id")
    feedback = data.get("feedback")  # 'too_easy', 'just_right', 'too_hard'
    time_spent = data.get("time_spent", 0)
    completed = data.get("completed", True)
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Update session log
    completion_status = 'completed' if completed else 'partial'
    
    if USE_POSTGRES:
        cursor.execute(
            """UPDATE session_logs 
               SET completed_at = NOW(), completion_status = %s, time_spent_seconds = %s, feedback = %s
               WHERE id = %s""",
            (completion_status, time_spent, feedback, session_id)
        )
        
        # Get passage to update user stats
        cursor.execute(
            """SELECT p.word_count FROM session_logs sl
               JOIN passages p ON sl.passage_id = p.id
               WHERE sl.id = %s""",
            (session_id,)
        )
    else:
        cursor.execute(
            """UPDATE session_logs 
               SET completed_at = CURRENT_TIMESTAMP, completion_status = ?, time_spent_seconds = ?, feedback = ?
               WHERE id = ?""",
            (completion_status, time_spent, feedback, session_id)
        )
        
        cursor.execute(
            """SELECT p.word_count FROM session_logs sl
               JOIN passages p ON sl.passage_id = p.id
               WHERE sl.id = ?""",
            (session_id,)
        )
    
    result = cursor.fetchone()
    word_count = result['word_count'] if USE_POSTGRES else result[0]
    
    # Update user stats
    if USE_POSTGRES:
        cursor.execute(
            """UPDATE users 
               SET total_passages_read = total_passages_read + 1,
                   words_per_session = (words_per_session + %s) / 2,
                   last_active = NOW()
               WHERE id = %s""",
            (word_count, user_id)
        )
        
        # Adjust level estimate based on feedback
        if feedback == 'too_easy':
            cursor.execute(
                """UPDATE users 
                   SET level_estimate = CASE 
                       WHEN level_estimate = 'beginner' THEN 'intermediate'
                       WHEN level_estimate = 'intermediate' THEN 'advanced'
                       ELSE level_estimate
                   END
                   WHERE id = %s""",
                (user_id,)
            )
        elif feedback == 'too_hard':
            cursor.execute(
                """UPDATE users 
                   SET level_estimate = CASE 
                       WHEN level_estimate = 'advanced' THEN 'intermediate'
                       WHEN level_estimate = 'intermediate' THEN 'beginner'
                       ELSE level_estimate
                   END
                   WHERE id = %s""",
                (user_id,)
            )
    else:
        cursor.execute(
            """UPDATE users 
               SET total_passages_read = total_passages_read + 1,
                   words_per_session = (words_per_session + ?) / 2,
                   last_active = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (word_count, user_id)
        )
        
        # Adjust level based on feedback (SQLite version)
        if feedback == 'too_easy':
            cursor.execute("SELECT level_estimate FROM users WHERE id = ?", (user_id,))
            current_level = cursor.fetchone()[0]
            new_level = 'intermediate' if current_level == 'beginner' else 'advanced' if current_level == 'intermediate' else current_level
            cursor.execute("UPDATE users SET level_estimate = ? WHERE id = ?", (new_level, user_id))
        elif feedback == 'too_hard':
            cursor.execute("SELECT level_estimate FROM users WHERE id = ?", (user_id,))
            current_level = cursor.fetchone()[0]
            new_level = 'beginner' if current_level == 'intermediate' else 'intermediate' if current_level == 'advanced' else current_level
            cursor.execute("UPDATE users SET level_estimate = ? WHERE id = ?", (new_level, user_id))
    
    conn.commit()
    conn.close()
    
    return {"success": True, "message": "Feedback recorded"}

@app.post("/api/read/comprehension")
async def submit_comprehension_answers(request: Request):
    """Submit answers to comprehension questions"""
    data = await request.json()
    token = data.get("token")
    
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    user_data = verify_token(token)
    user_id = user_data["user_id"]
    
    session_id = data.get("session_id")
    answers = data.get("answers", [])
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Calculate score
    correct_count = sum(1 for ans in answers if ans.get('is_correct', False))
    total_questions = len(answers)
    score = (correct_count / total_questions * 100) if total_questions > 0 else 0
    
    # Update session log
    if USE_POSTGRES:
        cursor.execute(
            """UPDATE session_logs 
               SET answers = %s, comprehension_score = %s
               WHERE id = %s""",
            (json.dumps(answers), score, session_id)
        )
        
        # Update user comprehension score (rolling average)
        cursor.execute(
            """UPDATE users 
               SET comprehension_score = (comprehension_score + %s) / 2
               WHERE id = %s""",
            (score, user_id)
        )
    else:
        cursor.execute(
            """UPDATE session_logs 
               SET answers = ?, comprehension_score = ?
               WHERE id = ?""",
            (json.dumps(answers), score, session_id)
        )
        
        cursor.execute(
            """UPDATE users 
               SET comprehension_score = (comprehension_score + ?) / 2
               WHERE id = ?""",
            (score, user_id)
        )
    
    conn.commit()
    conn.close()
    
    # Generate encouraging feedback
    if score >= 80:
        message = "Excellent work! You really understood the passage!"
    elif score >= 60:
        message = "Good job! You're getting it!"
    else:
        message = "Keep practicing! Let's try another passage to build your skills."
    
    return {
        "success": True,
        "score": round(score, 1),
        "correct": correct_count,
        "total": total_questions,
        "message": message
    }

# ============================================
# PHASE 2: DISCUSSION ENDPOINTS
# ============================================

@app.post("/api/discuss")
async def discuss_passage(request: Request):
    """Have a discussion about a passage with AI"""
    data = await request.json()
    token = data.get("token")
    
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    user_data = verify_token(token)
    user_id = user_data["user_id"]
    
    passage_id = data.get("passage_id")
    user_message = data.get("message")
    
    if not content_generator:
        raise HTTPException(status_code=503, detail="Discussion feature requires OpenAI API key")
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Get passage content
    if USE_POSTGRES:
        cursor.execute("SELECT content FROM passages WHERE id = %s", (passage_id,))
    else:
        cursor.execute("SELECT content FROM passages WHERE id = ?", (passage_id,))
    
    passage = cursor.fetchone()
    
    if not passage:
        raise HTTPException(status_code=404, detail="Passage not found")
    
    passage_text = passage['content'] if USE_POSTGRES else passage[0]
    
    # Generate AI response
    try:
        ai_response = content_generator.generate_discussion_prompt(passage_text, user_message)
        
        # Save conversation
        if USE_POSTGRES:
            cursor.execute(
                """INSERT INTO discussions (user_id, passage_id, message_role, message_content)
                   VALUES (%s, %s, %s, %s)""",
                (user_id, passage_id, 'user', user_message)
            )
            cursor.execute(
                """INSERT INTO discussions (user_id, passage_id, message_role, message_content)
                   VALUES (%s, %s, %s, %s)""",
                (user_id, passage_id, 'assistant', ai_response)
            )
        else:
            cursor.execute(
                """INSERT INTO discussions (user_id, passage_id, message_role, message_content)
                   VALUES (?, ?, ?, ?)""",
                (user_id, passage_id, 'user', user_message)
            )
            cursor.execute(
                """INSERT INTO discussions (user_id, passage_id, message_role, message_content)
                   VALUES (?, ?, ?, ?)""",
                (user_id, passage_id, 'assistant', ai_response)
            )
        
        conn.commit()
        conn.close()
        
        update_user_activity(user_id)
        
        return {
            "success": True,
            "response": ai_response
        }
        
    except Exception as e:
        conn.close()
        print(f"Discussion error: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate response")

@app.get("/api/discuss/history")
async def get_discussion_history(token: str, passage_id: int):
    """Get discussion history for a passage"""
    user_data = verify_token(token)
    user_id = user_data["user_id"]
    
    conn = get_db()
    cursor = conn.cursor()
    
    if USE_POSTGRES:
        cursor.execute(
            """SELECT message_role, message_content, created_at 
               FROM discussions 
               WHERE user_id = %s AND passage_id = %s 
               ORDER BY created_at ASC""",
            (user_id, passage_id)
        )
    else:
        cursor.execute(
            """SELECT message_role, message_content, created_at 
               FROM discussions 
               WHERE user_id = ? AND passage_id = ? 
               ORDER BY created_at ASC""",
            (user_id, passage_id)
        )
    
    messages = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return {"messages": messages}

# ============================================
# PHASE 2: WRITING ENDPOINTS
# ============================================

@app.post("/api/write/submit")
async def submit_writing(request: Request):
    """Submit a writing response for AI feedback"""
    data = await request.json()
    token = data.get("token")
    
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    user_data = verify_token(token)
    user_id = user_data["user_id"]
    
    prompt = data.get("prompt")
    user_response = data.get("response")
    passage_id = data.get("passage_id")
    
    if not content_generator:
        return {
            "success": True,
            "feedback": {
                "positive_feedback": "Great job getting your ideas down!",
                "suggestions": ["Try adding more details to support your main point."],
                "revised_example": user_response,
                "encouragement": "Keep writing - you're doing well!",
                "score": 75
            },
            "exercise_id": None
        }
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Get passage context if provided
    passage_context = None
    if passage_id:
        if USE_POSTGRES:
            cursor.execute("SELECT content FROM passages WHERE id = %s", (passage_id,))
        else:
            cursor.execute("SELECT content FROM passages WHERE id = ?", (passage_id,))
        
        passage = cursor.fetchone()
        passage_context = passage['content'] if passage else None
    
    # Generate feedback
    try:
        feedback = content_generator.provide_writing_feedback(
            prompt=prompt,
            user_response=user_response,
            passage_context=passage_context
        )
        
        # Save exercise
        if USE_POSTGRES:
            cursor.execute(
                """INSERT INTO writing_exercises 
                   (user_id, passage_id, prompt, user_response, ai_feedback, score)
                   VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
                (user_id, passage_id, prompt, user_response, json.dumps(feedback), feedback.get('score'))
            )
            result = cursor.fetchone()
            exercise_id = result['id']
        else:
            cursor.execute(
                """INSERT INTO writing_exercises 
                   (user_id, passage_id, prompt, user_response, ai_feedback, score)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (user_id, passage_id, prompt, user_response, json.dumps(feedback), feedback.get('score'))
            )
            exercise_id = cursor.lastrowid
        
        conn.commit()
        conn.close()
        
        update_user_activity(user_id)
        
        return {
            "success": True,
            "feedback": feedback,
            "exercise_id": exercise_id
        }
        
    except Exception as e:
        conn.close()
        print(f"Writing feedback error: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate feedback")

@app.post("/api/write/revise")
async def submit_revision(request: Request):
    """Submit a revised writing response"""
    data = await request.json()
    token = data.get("token")
    
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    user_data = verify_token(token)
    user_id = user_data["user_id"]
    
    exercise_id = data.get("exercise_id")
    revised_response = data.get("revised_response")
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Update exercise
    if USE_POSTGRES:
        cursor.execute(
            """UPDATE writing_exercises 
               SET revised_response = %s, revision_submitted_at = NOW()
               WHERE id = %s AND user_id = %s""",
            (revised_response, exercise_id, user_id)
        )
    else:
        cursor.execute(
            """UPDATE writing_exercises 
               SET revised_response = ?, revision_submitted_at = CURRENT_TIMESTAMP
               WHERE id = ? AND user_id = ?""",
            (revised_response, exercise_id, user_id)
        )
    
    conn.commit()
    conn.close()
    
    return {
        "success": True,
        "message": "Excellent! Your revision shows real improvement!"
    }

@app.get("/api/write/history")
async def get_writing_history(token: str, limit: int = 10):
    """Get user's writing exercise history"""
    user_data = verify_token(token)
    user_id = user_data["user_id"]
    
    conn = get_db()
    cursor = conn.cursor()
    
    if USE_POSTGRES:
        cursor.execute(
            """SELECT id, prompt, user_response, score, submitted_at, revised_response
               FROM writing_exercises 
               WHERE user_id = %s 
               ORDER BY submitted_at DESC 
               LIMIT %s""",
            (user_id, limit)
        )
    else:
        cursor.execute(
            """SELECT id, prompt, user_response, score, submitted_at, revised_response
               FROM writing_exercises 
               WHERE user_id = ? 
               ORDER BY submitted_at DESC 
               LIMIT ?""",
            (user_id, limit)
        )
    
    exercises = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return {"exercises": exercises}

# ============================================
# PHASE 2: ENHANCED ANALYTICS
# ============================================

@app.get("/api/student/progress")
async def get_student_progress(token: str):
    """Get detailed progress for current student"""
    user_data = verify_token(token)
    user_id = user_data["user_id"]
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Get user stats
    if USE_POSTGRES:
        cursor.execute(
            """SELECT total_passages_read, words_per_session, comprehension_score, level_estimate
               FROM users WHERE id = %s""",
            (user_id,)
        )
    else:
        cursor.execute(
            """SELECT total_passages_read, words_per_session, comprehension_score, level_estimate
               FROM users WHERE id = ?""",
            (user_id,)
        )
    
    user_stats = dict(cursor.fetchone())
    
    # Get recent sessions
    if USE_POSTGRES:
        cursor.execute(
            """SELECT sl.*, p.title, p.word_count
               FROM session_logs sl
               JOIN passages p ON sl.passage_id = p.id
               WHERE sl.user_id = %s AND sl.completed_at IS NOT NULL
               ORDER BY sl.completed_at DESC
               LIMIT 10""",
            (user_id,)
        )
    else:
        cursor.execute(
            """SELECT sl.*, p.title, p.word_count
               FROM session_logs sl
               JOIN passages p ON sl.passage_id = p.id
               WHERE sl.user_id = ? AND sl.completed_at IS NOT NULL
               ORDER BY sl.completed_at DESC
               LIMIT 10""",
            (user_id,)
        )
    
    recent_sessions = [dict(row) for row in cursor.fetchall()]
    
    # Calculate Day-1 metric (passages completed today)
    if USE_POSTGRES:
        cursor.execute(
            """SELECT COUNT(*) as count
               FROM session_logs
               WHERE user_id = %s 
               AND completion_status = 'completed'
               AND started_at >= CURRENT_DATE""",
            (user_id,)
        )
        result = cursor.fetchone()
        today_count = result['count']
    else:
        cursor.execute(
            """SELECT COUNT(*) as count
               FROM session_logs
               WHERE user_id = ? 
               AND completion_status = 'completed'
               AND DATE(started_at) = DATE('now')""",
            (user_id,)
        )
        result = cursor.fetchone()
        today_count = result[0]
    
    conn.close()
    
    return {
        "user_stats": user_stats,
        "recent_sessions": recent_sessions,
        "today_completed": today_count,
        "day1_goal_met": today_count >= 3
    }

@app.get("/api/admin/analytics-v2")
async def get_enhanced_analytics(token: str):
    """Enhanced analytics for admin dashboard"""
    user_data = verify_token(token)
    if user_data["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Basic stats
    cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'student'")
    result = cursor.fetchone()
    total_students = result['count'] if USE_POSTGRES else result[0]
    
    # Day-1 Success Rate
    if USE_POSTGRES:
        cursor.execute(
            """SELECT 
                COUNT(DISTINCT user_id) as total,
                COUNT(DISTINCT CASE WHEN passages >= 3 THEN user_id END) as met_goal
               FROM (
                   SELECT user_id, COUNT(*) as passages
                   FROM session_logs
                   WHERE completion_status = 'completed'
                   AND started_at >= CURRENT_DATE
                   GROUP BY user_id
               ) daily_stats"""
        )
        result = cursor.fetchone()
        day1_total = result['total']
        day1_met = result['met_goal']
    else:
        cursor.execute(
            """SELECT 
                COUNT(DISTINCT user_id) as total,
                SUM(CASE WHEN passages >= 3 THEN 1 ELSE 0 END) as met_goal
               FROM (
                   SELECT user_id, COUNT(*) as passages
                   FROM session_logs
                   WHERE completion_status = 'completed'
                   AND DATE(started_at) = DATE('now')
                   GROUP BY user_id
               )"""
        )
        result = cursor.fetchone()
        day1_total = result[0]
        day1_met = result[1]
    
    day1_success_rate = (day1_met / day1_total * 100) if day1_total > 0 else 0
    
    # Average comprehension by question type
    if USE_POSTGRES:
        cursor.execute(
            """SELECT 
                pq.question_type,
                COUNT(*) as total_questions,
                AVG(sl.comprehension_score) as avg_score
               FROM session_logs sl
               JOIN passage_questions pq ON sl.passage_id = pq.passage_id
               WHERE sl.comprehension_score IS NOT NULL
               GROUP BY pq.question_type"""
        )
    else:
        cursor.execute(
            """SELECT 
                pq.question_type,
                COUNT(*) as total_questions,
                AVG(sl.comprehension_score) as avg_score
               FROM session_logs sl
               JOIN passage_questions pq ON sl.passage_id = pq.passage_id
               WHERE sl.comprehension_score IS NOT NULL
               GROUP BY pq.question_type"""
        )
    
    comprehension_by_type = [dict(row) for row in cursor.fetchall()]
    
    # Stamina trend (last 7 days)
    if USE_POSTGRES:
        cursor.execute(
            """SELECT 
                DATE(started_at) as date,
                AVG(p.word_count) as avg_words,
                COUNT(*) as sessions
               FROM session_logs sl
               JOIN passages p ON sl.passage_id = p.id
               WHERE started_at >= CURRENT_DATE - INTERVAL '7 days'
               AND completion_status = 'completed'
               GROUP BY DATE(started_at)
               ORDER BY date"""
        )
    else:
        cursor.execute(
            """SELECT 
                DATE(started_at) as date,
                AVG(p.word_count) as avg_words,
                COUNT(*) as sessions
               FROM session_logs sl
               JOIN passages p ON sl.passage_id = p.id
               WHERE DATE(started_at) >= DATE('now', '-7 days')
               AND completion_status = 'completed'
               GROUP BY DATE(started_at)
               ORDER BY date"""
        )
    
    stamina_trend = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return {
        "total_students": total_students,
        "day1_success_rate": round(day1_success_rate, 1),
        "day1_active_today": day1_total,
        "comprehension_by_type": comprehension_by_type,
        "stamina_trend": stamina_trend
    }

# ============================================
# LESSONS ENDPOINTS (Phase 1 compatibility)
# ============================================

@app.get("/api/lessons/next")
async def get_next_lesson(token: str):
    """Get next lesson (Phase 1 compatibility - redirects to Phase 2 reading)"""
    # For Phase 1 compatibility, redirect to reading sample
    return await get_reading_sample(token, "appropriate")

@app.post("/api/lessons/progress")
async def save_lesson_progress(request: Request):
    """Save lesson progress (Phase 1 compatibility)"""
    data = await request.json()
    token = data.get("token")
    
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # For Phase 1 compatibility, just acknowledge
    return {"success": True, "message": "Progress saved"}

# ============================================
# ADMIN ENDPOINTS (Original + Enhanced)
# ============================================

@app.get("/api/admin/students")
async def get_all_students(token: str):
    user_data = verify_token(token)
    if user_data["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """SELECT id, email, full_name, level_estimate, total_passages_read, 
           comprehension_score, last_active, created_at 
           FROM users WHERE role = 'student'
           ORDER BY created_at DESC"""
    )
    students = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return {"students": students}

@app.get("/api/admin/student/{student_id}/details")
async def get_student_details(student_id: int, token: str):
    """Get detailed progress for a specific student"""
    user_data = verify_token(token)
    if user_data["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Get student info
    if USE_POSTGRES:
        cursor.execute("SELECT * FROM users WHERE id = %s", (student_id,))
    else:
        cursor.execute("SELECT * FROM users WHERE id = ?", (student_id,))
    
    student = dict(cursor.fetchone())
    
    # Get session history
    if USE_POSTGRES:
        cursor.execute(
            """SELECT sl.*, p.title, p.word_count, p.difficulty_level
               FROM session_logs sl
               JOIN passages p ON sl.passage_id = p.id
               WHERE sl.user_id = %s
               ORDER BY sl.started_at DESC
               LIMIT 20""",
            (student_id,)
        )
    else:
        cursor.execute(
            """SELECT sl.*, p.title, p.word_count, p.difficulty_level
               FROM session_logs sl
               JOIN passages p ON sl.passage_id = p.id
               WHERE sl.user_id = ?
               ORDER BY sl.started_at DESC
               LIMIT 20""",
            (student_id,)
        )
    
    sessions = [dict(row) for row in cursor.fetchall()]
    
    # Get writing exercises
    if USE_POSTGRES:
        cursor.execute(
            """SELECT prompt, score, submitted_at, revised_response IS NOT NULL as has_revision
               FROM writing_exercises
               WHERE user_id = %s
               ORDER BY submitted_at DESC
               LIMIT 10""",
            (student_id,)
        )
    else:
        cursor.execute(
            """SELECT prompt, score, submitted_at, 
                      CASE WHEN revised_response IS NOT NULL THEN 1 ELSE 0 END as has_revision
               FROM writing_exercises
               WHERE user_id = ?
               ORDER BY submitted_at DESC
               LIMIT 10""",
            (student_id,)
        )
    
    writing = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return {
        "student": student,
        "sessions": sessions,
        "writing": writing
    }

@app.get("/api/admin/analytics")
async def get_analytics(token: str):
    """Get basic analytics (Phase 1 compatibility)"""
    user_data = verify_token(token)
    if user_data["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Total students
    cursor.execute("SELECT COUNT(*) as count FROM users WHERE role = 'student'")
    result = cursor.fetchone()
    total_students = result['count'] if USE_POSTGRES else result[0]
    
    # Total lessons completed
    if USE_POSTGRES:
        cursor.execute("SELECT COUNT(*) as count FROM session_logs WHERE completion_status = 'completed'")
        result = cursor.fetchone()
        total_completed = result['count']
    else:
        cursor.execute("SELECT COUNT(*) as count FROM session_logs WHERE completion_status = 'completed'")
        result = cursor.fetchone()
        total_completed = result[0] if result else 0
    
    # Average score
    cursor.execute("SELECT AVG(comprehension_score) as avg_score FROM session_logs WHERE comprehension_score IS NOT NULL")
    result = cursor.fetchone()
    if USE_POSTGRES:
        avg_score = result['avg_score'] if result['avg_score'] is not None else 0
    else:
        avg_score = result[0] if result and result[0] is not None else 0
    
    # Active students (completed in last 7 days)
    if USE_POSTGRES:
        cursor.execute(
            "SELECT COUNT(DISTINCT user_id) as count FROM session_logs WHERE started_at >= NOW() - INTERVAL '7 days'"
        )
        result = cursor.fetchone()
        active_students = result['count']
    else:
        cursor.execute(
            "SELECT COUNT(DISTINCT user_id) as count FROM session_logs WHERE DATE(started_at) >= DATE('now', '-7 days')"
        )
        result = cursor.fetchone()
        active_students = result[0] if result else 0
    
    conn.close()
    
    return {
        "total_students": total_students,
        "total_lessons_completed": total_completed,
        "average_score": round(float(avg_score), 2) if avg_score else 0,
        "active_students": active_students
    }

# Mount static files
try:
    app.mount("/static", StaticFiles(directory="static"), name="static")
except:
    print("Warning: static directory not found")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)