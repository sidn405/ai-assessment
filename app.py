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
from openai import OpenAI
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

# Initialize OpenAI client (v1.0+)
openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# Database configuration
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
    role: str = "student"
    
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

# OpenAI integration functions
async def generate_interest_assessment() -> List[Dict]:
    """Generate questions to assess student's reading interests"""
    
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
        
        response = openai_client.chat.completions.create(
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
        print(f"OpenAI error: {type(e).__name__}: {str(e)} - using fallback questions")
        return fallback_questions

async def analyze_assessment_results(answers: List[dict]) -> Dict[str, Any]:
    """Use AI to analyze assessment results and determine reading level and interests"""
    
    # Fallback analysis based on answers
    fallback_analysis = {
        "reading_level": "middle",
        "interests": ["technology", "sports", "science"],
        "strengths": ["comprehension", "vocabulary"],
        "areas_for_improvement": ["inference", "critical_thinking"],
        "recommended_topics": ["tech innovation", "sports history", "space exploration"]
    }
    
    if not OPENAI_API_KEY or OPENAI_API_KEY == "":
        print("No OpenAI API key - using fallback analysis")
        return fallback_analysis
    
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
        response = openai_client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are an expert in literacy assessment and education."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5,
            timeout=10
        )
        
        content = response.choices[0].message.content
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
            
        return json.loads(content)
    except Exception as e:
        print(f"Error analyzing assessment: {type(e).__name__}: {str(e)}")
        return fallback_analysis

async def generate_adaptive_lesson(user_profile: dict, previous_performance: dict) -> Dict:
    """Generate personalized lesson content based on student profile and performance"""
    
    fallback_lesson = {
        "title": "Introduction to Reading Comprehension",
        "content": "Reading comprehension is the ability to understand and interpret what you read. This skill is essential for success in school and in everyday life. When you read, your brain processes the words on the page and connects them to your existing knowledge and experiences.",
        "difficulty_level": 5,
        "questions": [
            {
                "question": "What is reading comprehension?",
                "options": [
                    "The ability to read quickly",
                    "The ability to understand and interpret text",
                    "The ability to memorize words",
                    "The ability to write well"
                ],
                "correct": 1,
                "explanation": "Reading comprehension is about understanding and making sense of what you read."
            }
        ],
        "vocabulary": {
            "comprehension": "Understanding or grasping the meaning of something",
            "interpret": "To explain or understand the meaning of something"
        },
        "next_steps": "Practice with more complex passages"
    }
    
    if not OPENAI_API_KEY or OPENAI_API_KEY == "":
        print("No OpenAI API key - using fallback lesson")
        return fallback_lesson
    
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
        "vocabulary": {{"word1": "definition1"}},
        "next_steps": "Recommendation for next lesson"
    }}"""
    
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are an expert educator creating personalized reading lessons."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.8,
            timeout=15
        )
        
        content = response.choices[0].message.content
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
            
        return json.loads(content)
    except Exception as e:
        print(f"Error generating lesson: {type(e).__name__}: {str(e)}")
        return fallback_lesson

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

@app.post("/api/register")
async def register(user: UserCreate):
    conn = get_db()
    cursor = conn.cursor()
    
    password_hash = bcrypt.hashpw(user.password.encode('utf-8'), bcrypt.gensalt())
    
    try:
        if USE_POSTGRES:
            cursor.execute(
                "INSERT INTO users (email, password_hash, full_name, role) VALUES (%s, %s, %s, %s) RETURNING id",
                (user.email, password_hash.decode('utf-8'), user.full_name, user.role)
            )
            result = cursor.fetchone()
            user_id = result['id']
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

@app.get("/api/assessment/interest")
async def get_interest_assessment():
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
    data = await request.json()
    token = data.get("token")
    answers = data.get("answers", [])
    
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    user_data = verify_token(token)
    user_id = user_data["user_id"]
    
    analysis = await analyze_assessment_results(answers)
    
    conn = get_db()
    cursor = conn.cursor()
    
    if USE_POSTGRES:
        cursor.execute(
            "UPDATE users SET reading_level = %s, interests = %s WHERE id = %s",
            (analysis['reading_level'], json.dumps(analysis['interests']), user_id)
        )
        
        cursor.execute(
            "INSERT INTO assessments (user_id, assessment_type, questions, answers, reading_level, interests) VALUES (%s, %s, %s, %s, %s, %s)",
            (user_id, "initial", json.dumps([]), json.dumps(answers), analysis['reading_level'], json.dumps(analysis['interests']))
        )
    else:
        cursor.execute(
            "UPDATE users SET reading_level = ?, interests = ? WHERE id = ?",
            (analysis['reading_level'], json.dumps(analysis['interests']), user_id)
        )
        
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

@app.get("/api/lessons/next")
async def get_next_lesson(token: str):
    user_data = verify_token(token)
    user_id = user_data["user_id"]
    
    conn = get_db()
    cursor = conn.cursor()
    
    if USE_POSTGRES:
        cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    else:
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    
    user = cursor.fetchone()
    
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
    
    lesson = await generate_adaptive_lesson(user_profile, performance)
    
    conn = get_db()
    cursor = conn.cursor()
    
    if USE_POSTGRES:
        cursor.execute(
            "INSERT INTO lessons (title, content, reading_level, topic, difficulty) VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (lesson['title'], json.dumps(lesson), user_profile['reading_level'], user_profile['interests'][0], lesson.get('difficulty_level', 5))
        )
        result = cursor.fetchone()
        lesson_id = result['id']
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
async def save_progress(request: Request):
    data = await request.json()
    token = data.get("token")
    
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    
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
    
    cursor.execute("SELECT COUNT(*) as count FROM users WHERE role = 'student'")
    total_students = cursor.fetchone()['count'] if USE_POSTGRES else cursor.fetchone()[0]
    
    if USE_POSTGRES:
        cursor.execute("SELECT COUNT(*) as count FROM progress WHERE completed = TRUE")
        total_completed = cursor.fetchone()['count']
    else:
        cursor.execute("SELECT COUNT(*) as count FROM progress WHERE completed = 1")
        total_completed = cursor.fetchone()[0]
    
    cursor.execute("SELECT AVG(score) as avg_score FROM progress WHERE score IS NOT NULL")
    result = cursor.fetchone()
    avg_score = result['avg_score'] if USE_POSTGRES else result[0]
    avg_score = avg_score or 0
    
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

app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)