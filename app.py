from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
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

# Initialize FastAPI
app = FastAPI(title="MFS Literacy Assessment Platform")

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

# Database configuration - Use PostgreSQL if available, otherwise SQLite
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

USE_POSTGRES = DATABASE_URL is not None
DATABASE = DATABASE_URL if USE_POSTGRES else "mfs_literacy.db"

print(f"Using {'PostgreSQL' if USE_POSTGRES else 'SQLite'} database")
if USE_POSTGRES:
    print(f"Database URL configured")

# Pydantic models
class UserCreate(BaseModel):
    email: str
    password: str
    full_name: str
    role: str = "student"  # student or admin
    
class UserLogin(BaseModel):
    email: str
    password: str

class AssessmentResponse(BaseModel):
    question_id: int
    answer: str
    
class LessonProgress(BaseModel):
    lesson_id: int
    completed: bool
    score: Optional[float] = None
    time_spent: Optional[int] = None

# Database initialization
def init_db():
    if USE_POSTGRES:
        conn = psycopg2.connect(DATABASE)
        cursor = conn.cursor()
        
        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                full_name TEXT NOT NULL,
                role TEXT NOT NULL,
                reading_level TEXT,
                interests TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Assessment results table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS assessments (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                assessment_type TEXT NOT NULL,
                questions TEXT NOT NULL,
                answers TEXT NOT NULL,
                reading_level TEXT,
                interests TEXT,
                completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Lessons table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS lessons (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                reading_level TEXT NOT NULL,
                topic TEXT NOT NULL,
                difficulty INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Student progress table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS progress (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                lesson_id INTEGER NOT NULL,
                completed BOOLEAN DEFAULT FALSE,
                score REAL,
                time_spent INTEGER,
                completed_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id),
                FOREIGN KEY (lesson_id) REFERENCES lessons (id)
            )
        ''')
        
        # Admin account
        admin_hash = bcrypt.hashpw("admin123".encode('utf-8'), bcrypt.gensalt())
        try:
            cursor.execute(
                "INSERT INTO users (email, password_hash, full_name, role) VALUES (%s, %s, %s, %s)",
                ("admin@mfs.org", admin_hash.decode('utf-8'), "MFS Administrator", "admin")
            )
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
        
    else:
        conn = sqlite3.connect(DATABASE, timeout=30.0)
        conn.execute('PRAGMA journal_mode=WAL')
        cursor = conn.cursor()
        
        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                full_name TEXT NOT NULL,
                role TEXT NOT NULL,
                reading_level TEXT,
                interests TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Assessment results table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS assessments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                assessment_type TEXT NOT NULL,
                questions TEXT NOT NULL,
                answers TEXT NOT NULL,
                reading_level TEXT,
                interests TEXT,
                completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Lessons table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS lessons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                reading_level TEXT NOT NULL,
                topic TEXT NOT NULL,
                difficulty INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Student progress table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS progress (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                lesson_id INTEGER NOT NULL,
                completed BOOLEAN DEFAULT 0,
                score REAL,
                time_spent INTEGER,
                completed_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id),
                FOREIGN KEY (lesson_id) REFERENCES lessons (id)
            )
        ''')
        
        # Admin account
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

# Initialize database on startup
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

def db_execute(cursor, query, params=None, is_postgres=USE_POSTGRES):
    """Execute query with proper parameter substitution for SQLite or PostgreSQL"""
    if is_postgres:
        # PostgreSQL uses %s for all parameters
        query = query.replace('?', '%s')
    if params:
        cursor.execute(query, params)
    else:
        cursor.execute(query)
    return cursor

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

# OpenAI integration functions
async def generate_interest_assessment() -> List[Dict]:
    """Generate questions to assess student's reading interests"""
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
    
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are an expert educator creating reading assessments."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )
        
        content = response.choices[0].message.content
        # Extract JSON from markdown if present
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
            
        return json.loads(content)
    except Exception as e:
        # Fallback questions
        return [
            {
                "id": 1,
                "question": "What type of stories interest you most?",
                "options": ["Adventure stories", "Real-life stories", "Science topics", "Sports news"],
                "category": "genre"
            },
            {
                "id": 2,
                "question": "Which topic sounds most interesting to you?",
                "options": ["Technology and computers", "History and culture", "Nature and animals", "Music and arts"],
                "category": "topic"
            }
        ]

async def generate_reading_level_test(interests: str) -> List[Dict]:
    """Generate adaptive reading level assessment based on interests"""
    prompt = f"""Create 5 reading comprehension passages with questions to assess reading level.
    Student interests: {interests}
    
    Include passages at different difficulty levels (elementary, middle, high school).
    Each passage should relate to the student's interests.
    
    Return JSON:
    [
        {{
            "id": 1,
            "passage": "Short paragraph about topic...",
            "questions": [
                {{
                    "question": "What is the main idea?",
                    "options": ["A", "B", "C", "D"],
                    "correct": 0,
                    "difficulty": "elementary"
                }}
            ]
        }}
    ]"""
    
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are an expert literacy educator."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )
        
        content = response.choices[0].message.content
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
            
        return json.loads(content)
    except:
        return []

async def analyze_assessment_results(answers: List[dict]) -> Dict[str, Any]:
    """Use AI to analyze assessment results and determine reading level and interests"""
    prompt = f"""Analyze these assessment answers and determine:
    1. Reading level (elementary, middle, high_school, adult)
    2. Top 3 interest areas
    3. Recommended starting lessons
    
    Answers: {json.dumps(answers)}
    
    Return JSON:
    {{
        "reading_level": "middle",
        "interests": ["technology", "sports", "science"],
        "strengths": ["comprehension", "vocabulary"],
        "areas_for_improvement": ["inference", "critical_thinking"],
        "recommended_topics": ["tech innovation", "sports history", "space exploration"]
    }}"""
    
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are an expert in literacy assessment and education."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5
        )
        
        content = response.choices[0].message.content
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
            
        return json.loads(content)
    except:
        return {
            "reading_level": "middle",
            "interests": ["general"],
            "strengths": [],
            "areas_for_improvement": [],
            "recommended_topics": []
        }

async def generate_adaptive_lesson(user_profile: dict, previous_performance: dict) -> Dict:
    """Generate personalized lesson content based on student profile and performance"""
    prompt = f"""Create an engaging reading lesson for a student with this profile:
    - Reading Level: {user_profile.get('reading_level', 'middle')}
    - Interests: {user_profile.get('interests', 'general')}
    - Recent Performance: {previous_performance}
    
    The lesson should:
    1. Match their reading level
    2. Relate to their interests
    3. Include comprehension questions
    4. Gradually increase difficulty if they're performing well
    
    Return JSON:
    {{
        "title": "Lesson title",
        "content": "Engaging passage text...",
        "difficulty_level": 5,
        "questions": [
            {{
                "question": "Question text",
                "options": ["A", "B", "C", "D"],
                "correct": 0,
                "explanation": "Why this is correct"
            }}
        ],
        "vocabulary": ["word1": "definition1"],
        "next_steps": "Recommendation for next lesson"
    }}"""
    
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are an expert educator creating personalized reading lessons."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.8
        )
        
        content = response.choices[0].message.content
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
            
        return json.loads(content)
    except Exception as e:
        return {
            "title": "Sample Lesson",
            "content": "This is a sample lesson. Please configure OpenAI API key for personalized content.",
            "difficulty_level": 5,
            "questions": [],
            "vocabulary": {},
            "next_steps": "Continue practicing"
        }

# API Routes

@app.get("/", response_class=HTMLResponse)
async def serve_landing():
    return FileResponse("static/index.html")

@app.get("/dashboard", response_class=HTMLResponse)
async def serve_dashboard():
    return FileResponse("static/dashboard.html")

@app.get("/admin-dashboard", response_class=HTMLResponse)
async def serve_admin():
    return FileResponse("static/admin-dashboard.html")

# Authentication
@app.post("/api/register")
async def register(user: UserCreate):
    conn = get_db()
    cursor = conn.cursor()
    
    # Hash password
    password_hash = bcrypt.hashpw(user.password.encode('utf-8'), bcrypt.gensalt())
    
    try:
        if USE_POSTGRES:
            cursor.execute(
                "INSERT INTO users (email, password_hash, full_name, role) VALUES (%s, %s, %s, %s) RETURNING id",
                (user.email, password_hash.decode('utf-8'), user.full_name, user.role)
            )
            user_id = cursor.fetchone()[0]
        else:
            cursor.execute(
                "INSERT INTO users (email, password_hash, full_name, role) VALUES (?, ?, ?, ?)",
                (user.email, password_hash.decode('utf-8'), user.full_name, user.role)
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
    
    # Get password_hash - works for both dict (Postgres) and Row (SQLite)
    password_hash = user['password_hash'] if USE_POSTGRES else user['password_hash']
    
    # Verify password
    if not bcrypt.checkpw(credentials.password.encode('utf-8'), password_hash.encode('utf-8')):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = create_token(user['id'], user['role'])
    
    return {
        "success": True,
        "token": token,
        "user": {
            "id": user['id'],
            "email": user['email'],
            "full_name": user['full_name'],
            "role": user['role'],
            "reading_level": user['reading_level'],
            "interests": user['interests']
        }
    }

# Assessment endpoints
@app.get("/api/assessment/interest")
async def get_interest_assessment():
    questions = await generate_interest_assessment()
    return {"questions": questions}

@app.post("/api/assessment/submit")
async def submit_assessment(request: Request):
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
            "UPDATE users SET reading_level = %s, interests = %s WHERE id = %s",
            (analysis['reading_level'], json.dumps(analysis['interests']), user_id)
        )
        
        # Save assessment
        cursor.execute(
            "INSERT INTO assessments (user_id, assessment_type, questions, answers, reading_level, interests) VALUES (%s, %s, %s, %s, %s, %s)",
            (user_id, "initial", json.dumps([]), json.dumps(answers), analysis['reading_level'], json.dumps(analysis['interests']))
        )
    else:
        cursor.execute(
            "UPDATE users SET reading_level = ?, interests = ? WHERE id = ?",
            (analysis['reading_level'], json.dumps(analysis['interests']), user_id)
        )
        
        # Save assessment
        cursor.execute(
            "INSERT INTO assessments (user_id, assessment_type, questions, answers, reading_level, interests) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, "initial", json.dumps([]), json.dumps(answers), analysis['reading_level'], json.dumps(analysis['interests']))
        )
    
    conn.commit()
    conn.close()
    
    return {
        "success": True,
        "analysis": analysis
    }

# Lesson endpoints
@app.get("/api/lessons/next")
async def get_next_lesson(token: str):
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
    
    # Get recent performance
    if USE_POSTGRES:
        cursor.execute(
            "SELECT * FROM progress WHERE user_id = %s ORDER BY completed_at DESC LIMIT 5",
            (user_id,)
        )
    else:
        cursor.execute(
            "SELECT * FROM progress WHERE user_id = ? ORDER BY completed_at DESC LIMIT 5",
            (user_id,)
        )
    
    recent = cursor.fetchall()
    conn.close()
    
    user_profile = {
        "reading_level": user['reading_level'] or "middle",
        "interests": json.loads(user['interests']) if user['interests'] else ["general"]
    }
    
    performance = {
        "average_score": sum([r['score'] or 0 for r in recent]) / len(recent) if recent else 0,
        "completed_count": len(recent)
    }
    
    # Generate personalized lesson
    lesson = await generate_adaptive_lesson(user_profile, performance)
    
    # Save lesson to database
    conn = get_db()
    cursor = conn.cursor()
    
    if USE_POSTGRES:
        cursor.execute(
            "INSERT INTO lessons (title, content, reading_level, topic, difficulty) VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (lesson['title'], json.dumps(lesson), user_profile['reading_level'], user_profile['interests'][0], lesson.get('difficulty_level', 5))
        )
        lesson_id = cursor.fetchone()[0]
    else:
        cursor.execute(
            "INSERT INTO lessons (title, content, reading_level, topic, difficulty) VALUES (?, ?, ?, ?, ?)",
            (lesson['title'], json.dumps(lesson), user_profile['reading_level'], user_profile['interests'][0], lesson.get('difficulty_level', 5))
        )
        lesson_id = cursor.lastrowid
    
    conn.commit()
    conn.close()
    
    lesson['id'] = lesson_id
    return lesson

@app.post("/api/lessons/progress")
async def save_progress(data: dict, token: str):
    user_data = verify_token(token)
    user_id = user_data["user_id"]
    
    conn = get_db()
    cursor = conn.cursor()
    
    if USE_POSTGRES:
        cursor.execute(
            "INSERT INTO progress (user_id, lesson_id, completed, score, time_spent, completed_at) VALUES (%s, %s, %s, %s, %s, %s)",
            (user_id, data['lesson_id'], data['completed'], data.get('score'), data.get('time_spent'), datetime.utcnow())
        )
    else:
        cursor.execute(
            "INSERT INTO progress (user_id, lesson_id, completed, score, time_spent, completed_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, data['lesson_id'], data['completed'], data.get('score'), data.get('time_spent'), datetime.utcnow())
        )
    
    conn.commit()
    conn.close()
    
    return {"success": True}

# Admin endpoints
@app.get("/api/admin/students")
async def get_all_students(token: str):
    user_data = verify_token(token)
    if user_data["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, email, full_name, reading_level, interests, created_at FROM users WHERE role = 'student'")
    students = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return {"students": students}

@app.get("/api/admin/student/{student_id}/progress")
async def get_student_progress(student_id: int, token: str):
    user_data = verify_token(token)
    if user_data["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    conn = get_db()
    cursor = conn.cursor()
    
    if USE_POSTGRES:
        cursor.execute(
            """SELECT p.*, l.title, l.topic 
            FROM progress p 
            JOIN lessons l ON p.lesson_id = l.id 
            WHERE p.user_id = %s 
            ORDER BY p.completed_at DESC""",
            (student_id,)
        )
    else:
        cursor.execute(
            """SELECT p.*, l.title, l.topic 
            FROM progress p 
            JOIN lessons l ON p.lesson_id = l.id 
            WHERE p.user_id = ? 
            ORDER BY p.completed_at DESC""",
            (student_id,)
        )
    
    progress = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return {"progress": progress}

@app.get("/api/admin/analytics")
async def get_analytics(token: str):
    user_data = verify_token(token)
    if user_data["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Total students
    cursor.execute("SELECT COUNT(*) as count FROM users WHERE role = 'student'")
    total_students = cursor.fetchone()['count'] if USE_POSTGRES else cursor.fetchone()[0]
    
    # Total lessons completed
    if USE_POSTGRES:
        cursor.execute("SELECT COUNT(*) as count FROM progress WHERE completed = TRUE")
        total_completed = cursor.fetchone()['count']
    else:
        cursor.execute("SELECT COUNT(*) as count FROM progress WHERE completed = 1")
        total_completed = cursor.fetchone()[0]
    
    # Average score
    cursor.execute("SELECT AVG(score) as avg_score FROM progress WHERE score IS NOT NULL")
    result = cursor.fetchone()
    avg_score = result['avg_score'] if USE_POSTGRES else result[0]
    avg_score = avg_score or 0
    
    # Active students (completed lesson in last 7 days)
    if USE_POSTGRES:
        cursor.execute(
            "SELECT COUNT(DISTINCT user_id) as count FROM progress WHERE completed_at >= NOW() - INTERVAL '7 days'"
        )
        active_students = cursor.fetchone()['count']
    else:
        cursor.execute(
            "SELECT COUNT(DISTINCT user_id) as count FROM progress WHERE completed_at >= datetime('now', '-7 days')"
        )
        active_students = cursor.fetchone()[0]
    
    conn.close()
    
    return {
        "total_students": total_students,
        "total_lessons_completed": total_completed,
        "average_score": round(avg_score, 2),
        "active_students": active_students
    }

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)