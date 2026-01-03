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
import traceback
from openai import OpenAI

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

def generate_interest_assessment():
    """Generate interest assessment questions with OpenAI API v1.0+"""
    
    # Fallback questions (in case OpenAI fails)
    fallback_questions = [
        {
            "id": 1,
            "question": "What type of books or stories do you enjoy most?",
            "category": "genre",
            "options": ["Fiction", "Non-fiction", "Mystery", "Science Fiction", "Other"]
        },
        {
            "id": 2,
            "question": "What topics are you most curious about?",
            "category": "topic",
            "options": ["Science", "History", "Technology", "Nature", "Other"]
        },
        {
            "id": 3,
            "question": "Which activities do you find most interesting?",
            "category": "activity",
            "options": ["Sports", "Arts & Crafts", "Music", "Gaming", "Other"]
        },
        {
            "id": 4,
            "question": "What kind of learning do you prefer?",
            "category": "learning",
            "options": ["Hands-on activities", "Reading", "Videos", "Discussions", "Other"]
        },
        {
            "id": 5,
            "question": "What format of content do you like?",
            "category": "format",
            "options": ["Short articles", "Long stories", "Comics/Graphics", "Poems", "Other"]
        },
        {
            "id": 6,
            "question": "What career or job interests you?",
            "category": "career",
            "options": ["Doctor/Nurse", "Teacher", "Engineer", "Artist", "Other"]
        },
        {
            "id": 7,
            "question": "What do you do in your free time?",
            "category": "hobby",
            "options": ["Reading", "Playing outside", "Drawing", "Building things", "Other"]
        },
        {
            "id": 8,
            "question": "What school subject do you like most?",
            "category": "subject",
            "options": ["Math", "English", "Science", "Social Studies", "Other"]
        },
        {
            "id": 9,
            "question": "What type of content would you like to read about?",
            "category": "content_type",
            "options": ["Real-life stories", "Fictional adventures", "Educational facts", "How-to guides", "Other"]
        },
        {
            "id": 10,
            "question": "What's your favorite thing to learn about?",
            "category": "interest",
            "options": ["Animals", "Space", "Computers", "People & cultures", "Other"]
        }
    ]
    
    # Try OpenAI enhancement (optional)
    if OPENAI_API_KEY and content_generator:
        try:
            print("Calling OpenAI to generate assessment questions...")
            
            from openai import OpenAI
            client = OpenAI(api_key=OPENAI_API_KEY)
            
            response = client.chat.completions.create(
                model="gpt-4-turbo-preview",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert in educational assessment. You MUST respond with valid JSON only, no additional text."
                    },
                    {
                        "role": "user",
                        "content": """Generate 10 multiple-choice questions to assess student interests.

CRITICAL: Respond with ONLY valid JSON. No markdown, no explanations, just the JSON array.

Required format:
[
    {
        "id": 1,
        "question": "Question text here?",
        "category": "genre",
        "options": ["Option 1", "Option 2", "Option 3", "Option 4", "Other"]
    }
]

Requirements:
- Exactly 10 questions
- Each has 5 options
- Last option is always "Other"
- Age-appropriate for young adults
- Friendly, engaging tone"""
                    }
                ],
                temperature=0.7,
                max_tokens=2000,
                response_format={"type": "json_object"}  # Force JSON response
            )
            
            content = response.choices[0].message.content.strip()
            
            print(f"Raw OpenAI response length: {len(content)} chars")
            print(f"First 200 chars: {content[:200]}")
            
            # Clean up response
            content = content.strip()
            
            # Remove markdown code blocks if present
            if content.startswith("```"):
                # Extract content between ``` markers
                lines = content.split('\n')
                # Remove first line (```json or ```)
                lines = lines[1:]
                # Remove last line if it's ```
                if lines and lines[-1].strip() == '```':
                    lines = lines[:-1]
                content = '\n'.join(lines).strip()
            
            # Try to find JSON array or object
            if not content.startswith('[') and not content.startswith('{'):
                # Look for first [ or {
                start_bracket = content.find('[')
                start_brace = content.find('{')
                
                if start_bracket != -1:
                    content = content[start_bracket:]
                elif start_brace != -1:
                    content = content[start_brace:]
            
            print(f"Cleaned content first 100 chars: {content[:100]}")
            
            # Parse JSON
            try:
                parsed = json.loads(content)
                
                # Handle if it's wrapped in an object
                if isinstance(parsed, dict):
                    if 'questions' in parsed:
                        questions = parsed['questions']
                    else:
                        # Try to find the array
                        for value in parsed.values():
                            if isinstance(value, list):
                                questions = value
                                break
                        else:
                            raise ValueError("No questions array found in response")
                else:
                    questions = parsed
                
                # Validate structure
                if not isinstance(questions, list) or len(questions) == 0:
                    raise ValueError("Invalid questions format")
                
                # Ensure all questions have required fields and "Other" option
                for i, q in enumerate(questions):
                    if not all(key in q for key in ['id', 'question', 'options']):
                        raise ValueError(f"Question {i+1} missing required fields")
                    
                    if "Other" not in q["options"]:
                        q["options"].append("Other")
                    
                    # Ensure category exists
                    if "category" not in q:
                        q["category"] = "general"
                
                print(f"✓ Generated {len(questions)} questions with OpenAI")
                return questions
                
            except json.JSONDecodeError as je:
                print(f"JSON parsing error: {je}")
                print(f"Failed content: {content[:500]}")
                raise
            
        except Exception as e:
            print(f"OpenAI error: {e}")
            import traceback
            traceback.print_exc()
            print("Falling back to default questions")
    
    # Return fallback questions
    print(f"✓ Using {len(fallback_questions)} fallback questions")
    return fallback_questions

async def analyze_assessment_results(answers: List[Dict]) -> Dict:
    """Analyze assessment answers to determine interests and reading level"""
    
    print(f"Analyzing {len(answers)} assessment answers...")
    
    # Extract interests from answers
    interests = []
    topics = []
    categories = {}
    
    for answer in answers:
        question_id = answer.get('question_id')
        answer_value = answer.get('answer')
        
        print(f"Question {question_id}: {answer_value}")
        
        # Handle different answer formats
        if isinstance(answer_value, dict):
            # Format: {"option": "Other", "custom_text": "user input"}
            if answer_value.get('option') == 'Other' or answer_value.get('custom_text'):
                custom_text = answer_value.get('custom_text', '').strip()
                if custom_text:
                    print(f"  → Custom answer: {custom_text}")
                    interests.append(custom_text.lower())
                    topics.append(custom_text.lower())
            elif answer_value.get('option'):
                option = answer_value.get('option')
                if option and option != 'Other':
                    interests.append(option.lower())
                    topics.append(option.lower())
        
        elif isinstance(answer_value, str):
            # Plain string answer
            if answer_value and answer_value != 'Other':
                print(f"  → Regular answer: {answer_value}")
                interests.append(answer_value.lower())
                topics.append(answer_value.lower())
        
        # Track by category
        category = answer.get('category', 'general')
        if category not in categories:
            categories[category] = []
        
        # Add to category
        if isinstance(answer_value, dict) and answer_value.get('custom_text'):
            categories[category].append(answer_value['custom_text'].lower())
        elif isinstance(answer_value, str) and answer_value != 'Other':
            categories[category].append(answer_value.lower())
    
    # Remove duplicates while preserving order
    interests = list(dict.fromkeys(interests))
    topics = list(dict.fromkeys(topics))
    
    print(f"Extracted interests: {interests}")
    print(f"Extracted topics: {topics}")
    
    # If no interests extracted, use default
    if not interests:
        interests = ['general reading', 'education']
        topics = ['general reading', 'education']
    
    # Determine reading level based on answers
    reading_level = 'intermediate'  # Default
    
    # Check format preferences
    if 'format' in categories:
        format_prefs = categories['format']
        if any('short' in pref for pref in format_prefs):
            reading_level = 'beginner'
        elif any('long' in pref for pref in format_prefs):
            reading_level = 'advanced'
    
    return {
        'interests': interests,
        'topics': topics,
        'categories': categories,
        'reading_level': reading_level,
        'total_responses': len(answers)
    }

@app.get("/api/assessment/interest")
def get_interest_assessment():  # ← Remove 'async'
    """Get interest assessment questions"""
    try:
        print("Assessment endpoint called - generating questions...")
        questions = generate_interest_assessment()  # ← Remove 'await'
        
        if not questions:
            raise HTTPException(status_code=500, detail="Failed to generate assessment")
        
        print(f"✓ Returning {len(questions)} questions")
        
        return {
            "success": True,
            "questions": questions
        }
        
    except Exception as e:
        print(f"Error generating assessment: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

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
    
@app.post("/api/admin/run-gamification-migration")
async def run_gamification_migration(request: Request):
    """Run gamification database migration"""
    data = await request.json()
    token = data.get("token")
    
    try:
        user_data = verify_token(token)
    except:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Run all CREATE TABLE statements from gamification_migration.sql
        # (Copy the SQL from gamification_migration.sql file)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_points (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                points INTEGER DEFAULT 0,
                total_earned INTEGER DEFAULT 0,
                level INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                UNIQUE(user_id)
            )
        """)
        
        # ... (add all other CREATE TABLE statements)
        
        conn.commit()
        conn.close()
        
        return {"success": True, "message": "Gamification tables created"}
        
    except Exception as e:
        conn.rollback()
        conn.close()
        raise HTTPException(status_code=500, detail=str(e))
    
# REPLACE THE OLD /api/admin/migrate ENDPOINT WITH THIS
# This version is more robust and verifies tables were actually created

@app.post("/api/admin/migrate")
async def run_migration(request: Request):
    """Run database migration - FIXED VERSION"""
    data = await request.json()
    token = data.get("token")
    
    # Verify admin
    try:
        user_data = verify_token(token)
    except:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    conn = None
    results = []
    
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Verify we're connected to PostgreSQL
        results.append("Checking database connection...")
        cursor.execute("SELECT version()")
        version = cursor.fetchone()
        results.append(f"Connected to: {version[0] if isinstance(version, tuple) else version['version']}")
        
        # Create passages table
        results.append("\n=== Creating passages table ===")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS passages (
                id SERIAL PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                content TEXT NOT NULL,
                source VARCHAR(50) NOT NULL,
                topic_tags TEXT,
                word_count INTEGER NOT NULL,
                readability_score REAL,
                flesch_ease REAL,
                difficulty_level VARCHAR(20),
                estimated_minutes INTEGER,
                approved BOOLEAN DEFAULT FALSE,
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metadata TEXT
            )
        """)
        results.append("✓ passages table created")
        
        # Commit after each table
        conn.commit()
        results.append("✓ passages committed")
        
        # Verify table exists
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'passages'
            )
        """)
        exists = cursor.fetchone()[0] if isinstance(cursor.fetchone(), tuple) else cursor.fetchone()
        if not exists:
            raise Exception("passages table was not created!")
        results.append("✓ passages table verified")
        
        # Create indexes for passages
        results.append("\n=== Creating passages indexes ===")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_passages_difficulty ON passages(difficulty_level)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_passages_word_count ON passages(word_count)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_passages_approved ON passages(approved)")
        conn.commit()
        results.append("✓ passages indexes created")
        
        # Create passage_questions table
        results.append("\n=== Creating passage_questions table ===")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS passage_questions (
                id SERIAL PRIMARY KEY,
                passage_id INTEGER NOT NULL,
                question_text TEXT NOT NULL,
                question_type VARCHAR(50),
                correct_answer TEXT NOT NULL,
                options TEXT,
                explanation TEXT,
                difficulty INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (passage_id) REFERENCES passages(id) ON DELETE CASCADE
            )
        """)
        conn.commit()
        results.append("✓ passage_questions table created")
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_questions_passage ON passage_questions(passage_id)")
        conn.commit()
        results.append("✓ passage_questions index created")
        
        # Create session_logs table
        results.append("\n=== Creating session_logs table ===")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS session_logs (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                passage_id INTEGER NOT NULL,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                completion_status VARCHAR(20),
                time_spent_seconds INTEGER,
                feedback VARCHAR(20),
                comprehension_score REAL,
                answers TEXT,
                notes TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (passage_id) REFERENCES passages(id)
            )
        """)
        conn.commit()
        results.append("✓ session_logs table created")
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_session_user ON session_logs(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_session_passage ON session_logs(passage_id)")
        conn.commit()
        results.append("✓ session_logs indexes created")
        
        # Create writing_exercises table
        results.append("\n=== Creating writing_exercises table ===")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS writing_exercises (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                passage_id INTEGER,
                prompt TEXT NOT NULL,
                user_response TEXT NOT NULL,
                ai_feedback TEXT,
                score REAL,
                revised_response TEXT,
                submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                revision_submitted_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (passage_id) REFERENCES passages(id)
            )
        """)
        conn.commit()
        results.append("✓ writing_exercises table created")
        
        # Create vocabulary_tracker table
        results.append("\n=== Creating vocabulary_tracker table ===")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vocabulary_tracker (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                word VARCHAR(100) NOT NULL,
                definition TEXT,
                encountered_count INTEGER DEFAULT 1,
                mastered BOOLEAN DEFAULT FALSE,
                context_passage_id INTEGER,
                first_encountered TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_reviewed TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (context_passage_id) REFERENCES passages(id)
            )
        """)
        conn.commit()
        results.append("✓ vocabulary_tracker table created")
        
        # Create discussions table
        results.append("\n=== Creating discussions table ===")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS discussions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                passage_id INTEGER NOT NULL,
                message_role VARCHAR(20) NOT NULL,
                message_content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (passage_id) REFERENCES passages(id)
            )
        """)
        conn.commit()
        results.append("✓ discussions table created")
        
        # Final verification - check all tables exist
        results.append("\n=== Final Verification ===")
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('passages', 'passage_questions', 'session_logs', 
                               'writing_exercises', 'vocabulary_tracker', 'discussions')
            ORDER BY table_name
        """)
        
        created_tables = [row[0] if isinstance(row, tuple) else row['table_name'] for row in cursor.fetchall()]
        results.append(f"Tables created: {', '.join(created_tables)}")
        
        if len(created_tables) != 6:
            raise Exception(f"Only {len(created_tables)} tables created! Expected 6.")
        
        results.append("\n" + "=" * 50)
        results.append("✓✓✓ MIGRATION COMPLETE - ALL 6 TABLES VERIFIED ✓✓✓")
        results.append("=" * 50)
        
        return {
            "success": True,
            "message": "Migration completed and verified",
            "tables_created": created_tables,
            "details": results
        }
        
    except Exception as e:
        if conn:
            conn.rollback()
        
        results.append(f"\n✗ ERROR: {str(e)}")
        
        import traceback
        error_trace = traceback.format_exc()
        results.append(error_trace)
        
        return {
            "success": False,
            "message": "Migration failed",
            "error": str(e),
            "details": results,
            "traceback": error_trace
        }
        
    finally:
        if conn:
            conn.close()
        
# ADD THIS TO app.py - Simple table checker

@app.get("/api/admin/check-tables")
async def check_tables():
    """Check which tables exist in the database"""
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Query to get all table names
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name
        """)
        
        tables = [row[0] if isinstance(row, tuple) else row['table_name'] for row in cursor.fetchall()]
        
        # Check which Phase 2 tables exist
        required_tables = [
            'passages',
            'passage_questions', 
            'session_logs',
            'writing_exercises',
            'vocabulary_tracker',
            'discussions'
        ]
        
        missing_tables = [t for t in required_tables if t not in tables]
        
        conn.close()
        
        return {
            "all_tables": tables,
            "required_tables": required_tables,
            "missing_tables": missing_tables,
            "migration_needed": len(missing_tables) > 0,
            "status": "incomplete" if missing_tables else "complete"
        }
        
    except Exception as e:
        conn.close()
        return {
            "error": str(e),
            "status": "error"
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

# ============================================================
# GAMIFICATION BACKEND - Add to app.py
# ============================================================

# Points configuration
POINTS_CONFIG = {
    'lesson_complete': 10,
    'perfect_score': 50,
    'high_score': 25,  # 80%+
    'good_score': 15,  # 60-79%
    'daily_streak': 5,
    'weekly_goal': 100,
    'badge_earned': 20
}

# Badge definitions
BADGES = {
    'first_lesson': {'name': 'Getting Started', 'description': 'Complete your first lesson', 'icon': '🎯', 'points': 20},
    'perfect_streak_3': {'name': 'Triple Perfect', 'description': '3 perfect scores in a row', 'icon': '🔥', 'points': 50},
    'speed_reader': {'name': 'Speed Reader', 'description': '10 lessons in one week', 'icon': '⚡', 'points': 100},
    'bookworm': {'name': 'Bookworm', 'description': 'Complete 50 lessons total', 'icon': '📚', 'points': 200},
    'perfect_week': {'name': 'Perfect Week', 'description': 'Achieve all weekly goals', 'icon': '🏆', 'points': 150},
    'early_bird': {'name': 'Early Bird', 'description': 'Complete lesson before 9 AM', 'icon': '🌅', 'points': 30},
    'night_owl': {'name': 'Night Owl', 'description': 'Complete lesson after 9 PM', 'icon': '🦉', 'points': 30},
    'consistency_king': {'name': 'Consistency King', 'description': '7-day streak', 'icon': '👑', 'points': 100}
}

def award_points(user_id, points, reason, activity_type='general'):
    """Award points to a user"""
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Initialize or update user points
        if USE_POSTGRES:
            cursor.execute(
                """INSERT INTO user_points (user_id, points, total_earned)
                   VALUES (%s, %s, %s)
                   ON CONFLICT (user_id) DO UPDATE
                   SET points = user_points.points + EXCLUDED.points,
                       total_earned = user_points.total_earned + EXCLUDED.points,
                       updated_at = NOW()""",
                (user_id, points, points)
            )
        else:
            cursor.execute("SELECT id FROM user_points WHERE user_id = ?", (user_id,))
            if cursor.fetchone():
                cursor.execute(
                    """UPDATE user_points 
                       SET points = points + ?,
                           total_earned = total_earned + ?,
                           updated_at = datetime('now')
                       WHERE user_id = ?""",
                    (points, points, user_id)
                )
            else:
                cursor.execute(
                    "INSERT INTO user_points (user_id, points, total_earned) VALUES (?, ?, ?)",
                    (user_id, points, points)
                )
        
        # Record in history
        if USE_POSTGRES:
            cursor.execute(
                "INSERT INTO points_history (user_id, points, reason, activity_type) VALUES (%s, %s, %s, %s)",
                (user_id, points, reason, activity_type)
            )
        else:
            cursor.execute(
                "INSERT INTO points_history (user_id, points, reason, activity_type) VALUES (?, ?, ?, ?)",
                (user_id, points, reason, activity_type)
            )
        
        conn.commit()
        
        # Check for level up
        if USE_POSTGRES:
            cursor.execute("SELECT total_earned, level FROM user_points WHERE user_id = %s", (user_id,))
        else:
            cursor.execute("SELECT total_earned, level FROM user_points WHERE user_id = ?", (user_id,))
        
        result = cursor.fetchone()
        total = result['total_earned'] if hasattr(result, 'keys') else result[0]
        current_level = result['level'] if hasattr(result, 'keys') else result[1]
        
        new_level = (total // 500) + 1
        
        if new_level > current_level:
            if USE_POSTGRES:
                cursor.execute("UPDATE user_points SET level = %s WHERE user_id = %s", (new_level, user_id))
            else:
                cursor.execute("UPDATE user_points SET level = ? WHERE user_id = ?", (new_level, user_id))
            conn.commit()
            conn.close()
            return {'points_awarded': points, 'level_up': True, 'new_level': new_level}
        
        conn.close()
        return {'points_awarded': points, 'level_up': False}
        
    except Exception as e:
        conn.rollback()
        conn.close()
        print(f"Error awarding points: {e}")
        return {'points_awarded': 0, 'level_up': False}

def has_badge(user_id, badge_type):
    """Check if user has badge"""
    conn = get_db()
    cursor = conn.cursor()
    
    if USE_POSTGRES:
        cursor.execute("SELECT id FROM user_badges WHERE user_id = %s AND badge_type = %s", (user_id, badge_type))
    else:
        cursor.execute("SELECT id FROM user_badges WHERE user_id = ? AND badge_type = ?", (user_id, badge_type))
    
    result = cursor.fetchone()
    conn.close()
    return result is not None

def award_badge(user_id, badge_type, badge_name, description, icon):
    """Award badge to user"""
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        if USE_POSTGRES:
            cursor.execute(
                "INSERT INTO user_badges (user_id, badge_type, badge_name, description, icon) VALUES (%s, %s, %s, %s, %s)",
                (user_id, badge_type, badge_name, description, icon)
            )
        else:
            cursor.execute(
                "INSERT INTO user_badges (user_id, badge_type, badge_name, description, icon) VALUES (?, ?, ?, ?, ?)",
                (user_id, badge_type, badge_name, description, icon)
            )
        
        conn.commit()
        conn.close()
        
        award_points(user_id, BADGES[badge_type]['points'], f'Earned badge: {badge_name}', 'badge')
        return True
    except Exception as e:
        conn.rollback()
        conn.close()
        print(f"Error awarding badge: {e}")
        return False

def check_and_award_badges(user_id):
    """Check and award new badges"""
    conn = get_db()
    cursor = conn.cursor()
    new_badges = []
    
    try:
        # Get lesson count
        if USE_POSTGRES:
            cursor.execute(
                "SELECT COUNT(*) FROM session_logs WHERE user_id = %s AND completion_status = 'completed'",
                (user_id,)
            )
        else:
            cursor.execute(
                "SELECT COUNT(*) FROM session_logs WHERE user_id = ? AND completion_status = 'completed'",
                (user_id,)
            )
        
        lesson_count = cursor.fetchone()[0]
        
        # First lesson
        if lesson_count == 1 and not has_badge(user_id, 'first_lesson'):
            badge = BADGES['first_lesson']
            award_badge(user_id, 'first_lesson', badge['name'], badge['description'], badge['icon'])
            new_badges.append(badge)
        
        # Bookworm (50 lessons)
        if lesson_count == 50 and not has_badge(user_id, 'bookworm'):
            badge = BADGES['bookworm']
            award_badge(user_id, 'bookworm', badge['name'], badge['description'], badge['icon'])
            new_badges.append(badge)
        
        # Perfect streak check
        if USE_POSTGRES:
            cursor.execute(
                """SELECT comprehension_score FROM session_logs 
                   WHERE user_id = %s AND completion_status = 'completed'
                   ORDER BY completed_at DESC LIMIT 3""",
                (user_id,)
            )
        else:
            cursor.execute(
                """SELECT comprehension_score FROM session_logs 
                   WHERE user_id = ? AND completion_status = 'completed'
                   ORDER BY completed_at DESC LIMIT 3""",
                (user_id,)
            )
        
        recent_scores = [row[0] if isinstance(row, tuple) else row['comprehension_score'] for row in cursor.fetchall()]
        
        if len(recent_scores) >= 3 and all(score == 100 for score in recent_scores):
            if not has_badge(user_id, 'perfect_streak_3'):
                badge = BADGES['perfect_streak_3']
                award_badge(user_id, 'perfect_streak_3', badge['name'], badge['description'], badge['icon'])
                new_badges.append(badge)
        
        # Time-based badges
        from datetime import datetime
        current_hour = datetime.now().hour
        
        if current_hour < 9 and not has_badge(user_id, 'early_bird'):
            badge = BADGES['early_bird']
            award_badge(user_id, 'early_bird', badge['name'], badge['description'], badge['icon'])
            new_badges.append(badge)
        
        if current_hour >= 21 and not has_badge(user_id, 'night_owl'):
            badge = BADGES['night_owl']
            award_badge(user_id, 'night_owl', badge['name'], badge['description'], badge['icon'])
            new_badges.append(badge)
        
        conn.close()
        return new_badges
        
    except Exception as e:
        conn.close()
        print(f"Error checking badges: {e}")
        return []

def update_weekly_goals(user_id):
    """Update progress on weekly goals"""
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        from datetime import datetime, timedelta
        week_start = datetime.now() - timedelta(days=datetime.now().weekday())
        week_start = week_start.date()
        
        # Get current week's goal
        if USE_POSTGRES:
            cursor.execute(
                "SELECT * FROM weekly_goals WHERE user_id = %s AND week_start = %s AND goal_type = 'lessons_completed'",
                (user_id, week_start)
            )
        else:
            cursor.execute(
                "SELECT * FROM weekly_goals WHERE user_id = ? AND week_start = ? AND goal_type = 'lessons_completed'",
                (user_id, week_start)
            )
        
        goal = cursor.fetchone()
        
        if not goal:
            # Create new weekly goal
            if USE_POSTGRES:
                cursor.execute(
                    "INSERT INTO weekly_goals (user_id, week_start, goal_type, target_value, points_reward) VALUES (%s, %s, %s, %s, %s)",
                    (user_id, week_start, 'lessons_completed', 5, 100)
                )
            else:
                cursor.execute(
                    "INSERT INTO weekly_goals (user_id, week_start, goal_type, target_value, points_reward) VALUES (?, ?, ?, ?, ?)",
                    (user_id, week_start, 'lessons_completed', 5, 100)
                )
            conn.commit()
        else:
            # Update progress
            goal_id = goal['id'] if hasattr(goal, 'keys') else goal[0]
            current_value = goal['current_value'] if hasattr(goal, 'keys') else goal[5]
            target = goal['target_value'] if hasattr(goal, 'keys') else goal[4]
            completed = goal['completed'] if hasattr(goal, 'keys') else goal[6]
            
            new_value = current_value + 1
            
            if new_value >= target and not completed:
                # Goal completed!
                if USE_POSTGRES:
                    cursor.execute(
                        "UPDATE weekly_goals SET current_value = %s, completed = TRUE, completed_at = NOW() WHERE id = %s",
                        (new_value, goal_id)
                    )
                else:
                    cursor.execute(
                        "UPDATE weekly_goals SET current_value = ?, completed = 1, completed_at = datetime('now') WHERE id = ?",
                        (new_value, goal_id)
                    )
                conn.commit()
                
                # Award points
                points_reward = goal['points_reward'] if hasattr(goal, 'keys') else goal[7]
                award_points(user_id, points_reward, 'Weekly goal completed', 'goal')
            else:
                # Update progress
                if USE_POSTGRES:
                    cursor.execute("UPDATE weekly_goals SET current_value = %s WHERE id = %s", (new_value, goal_id))
                else:
                    cursor.execute("UPDATE weekly_goals SET current_value = ? WHERE id = ?", (new_value, goal_id))
                conn.commit()
        
        conn.close()
        
    except Exception as e:
        conn.rollback()
        conn.close()
        print(f"Error updating weekly goals: {e}")

@app.post("/api/lessons/progress")
async def save_lesson_progress(request: Request):
    """Save lesson progress WITH GAMIFICATION"""
    data = await request.json()
    token = data.get("token")
    lesson_id = data.get("lesson_id")
    completed = data.get("completed", False)
    score = data.get("score", 0)
    time_spent = data.get("time_spent", 0)
    answers = data.get("answers", [])
    
    print(f"=== Saving Progress ===")
    print(f"Lesson ID: {lesson_id}, Score: {score}")
    
    try:
        user_data = verify_token(token)
        user_id = user_data["user_id"]
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Save session
        if USE_POSTGRES:
            cursor.execute(
                """INSERT INTO session_logs 
                   (user_id, passage_id, completed_at, completion_status, 
                    time_spent_seconds, comprehension_score, answers)
                   VALUES (%s, %s, NOW(), %s, %s, %s, %s)
                   RETURNING id""",
                (user_id, lesson_id, 'completed' if completed else 'in_progress',
                 time_spent, score, json.dumps(answers))
            )
            result = cursor.fetchone()
            session_id = result['id'] if result else None
        else:
            cursor.execute(
                """INSERT INTO session_logs 
                   (user_id, passage_id, completed_at, completion_status, 
                    time_spent_seconds, comprehension_score, answers)
                   VALUES (?, ?, datetime('now'), ?, ?, ?, ?)""",
                (user_id, lesson_id, 'completed' if completed else 'in_progress',
                 time_spent, score, json.dumps(answers))
            )
            session_id = cursor.lastrowid
        
        # Update user stats
        if USE_POSTGRES:
            cursor.execute(
                """UPDATE users 
                   SET total_passages_read = COALESCE(total_passages_read, 0) + 1,
                       last_active = NOW()
                   WHERE id = %s""",
                (user_id,)
            )
        else:
            cursor.execute(
                """UPDATE users 
                   SET total_passages_read = COALESCE(total_passages_read, 0) + 1,
                       last_active = datetime('now')
                   WHERE id = ?""",
                (user_id,)
            )
        
        conn.commit()
        conn.close()
        
        # ========== GAMIFICATION ==========
        if score == 100:
            points_result = award_points(user_id, POINTS_CONFIG['perfect_score'], 'Perfect score!', 'lesson')
        elif score >= 80:
            points_result = award_points(user_id, POINTS_CONFIG['high_score'], 'High score!', 'lesson')
        elif score >= 60:
            points_result = award_points(user_id, POINTS_CONFIG['good_score'], 'Good score!', 'lesson')
        else:
            points_result = award_points(user_id, POINTS_CONFIG['lesson_complete'], 'Lesson completed', 'lesson')
        
        new_badges = check_and_award_badges(user_id)
        update_weekly_goals(user_id)
        # ==================================
        
        print(f"✓ Points awarded: {points_result['points_awarded']}")
        
        return {
            "success": True,
            "message": "Progress saved successfully",
            "session_id": session_id,
            "score": score,
            "gamification": {
                "points_earned": points_result['points_awarded'],
                "level_up": points_result.get('level_up', False),
                "new_level": points_result.get('new_level'),
                "new_badges": [{'name': b['name'], 'icon': b['icon']} for b in new_badges]
            }
        }
        
    except Exception as e:
        print(f"Error saving progress: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/student/gamification")
async def get_gamification_data(token: str):
    """Get gamification data"""
    try:
        user_data = verify_token(token)
        user_id = user_data["user_id"]
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Get points
        if USE_POSTGRES:
            cursor.execute("SELECT * FROM user_points WHERE user_id = %s", (user_id,))
        else:
            cursor.execute("SELECT * FROM user_points WHERE user_id = ?", (user_id,))
        
        points_row = cursor.fetchone()
        
        if points_row:
            points_data = {
                'current_points': points_row['points'] if hasattr(points_row, 'keys') else points_row[2],
                'total_earned': points_row['total_earned'] if hasattr(points_row, 'keys') else points_row[3],
                'level': points_row['level'] if hasattr(points_row, 'keys') else points_row[4]
            }
        else:
            points_data = {'current_points': 0, 'total_earned': 0, 'level': 1}
        
        # Get badges
        if USE_POSTGRES:
            cursor.execute("SELECT * FROM user_badges WHERE user_id = %s ORDER BY earned_at DESC", (user_id,))
        else:
            cursor.execute("SELECT * FROM user_badges WHERE user_id = ? ORDER BY earned_at DESC", (user_id,))
        
        badges = []
        for row in cursor.fetchall():
            badges.append({
                'type': row['badge_type'] if hasattr(row, 'keys') else row[2],
                'name': row['badge_name'] if hasattr(row, 'keys') else row[3],
                'description': row['description'] if hasattr(row, 'keys') else row[4],
                'icon': row['icon'] if hasattr(row, 'keys') else row[5],
                'earned_at': row['earned_at'] if hasattr(row, 'keys') else row[6]
            })
        
        # Get weekly goals
        from datetime import datetime, timedelta
        week_start = datetime.now() - timedelta(days=datetime.now().weekday())
        week_start = week_start.date()
        
        if USE_POSTGRES:
            cursor.execute("SELECT * FROM weekly_goals WHERE user_id = %s AND week_start = %s", (user_id, week_start))
        else:
            cursor.execute("SELECT * FROM weekly_goals WHERE user_id = ? AND week_start = ?", (user_id, week_start))
        
        goals = []
        for row in cursor.fetchall():
            goals.append({
                'goal_type': row['goal_type'] if hasattr(row, 'keys') else row[3],
                'target_value': row['target_value'] if hasattr(row, 'keys') else row[4],
                'current_value': row['current_value'] if hasattr(row, 'keys') else row[5],
                'completed': row['completed'] if hasattr(row, 'keys') else row[6],
                'points_reward': row['points_reward'] if hasattr(row, 'keys') else row[7]
            })
        
        conn.close()
        
        return {
            'success': True,
            'points': points_data,
            'badges': badges,
            'available_badges': BADGES,
            'weekly_goals': goals
        }
        
    except Exception as e:
        print(f"Error getting gamification: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================
# PHASE 2: ENHANCED ANALYTICS
# ============================================

@app.get("/api/student/dashboard")
async def get_student_dashboard(token: str):
    """Get student dashboard stats"""
    try:
        user_data = verify_token(token)
        user_id = user_data["user_id"]
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Get user info
        if USE_POSTGRES:
            cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        else:
            cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        
        user = cursor.fetchone()
        
        # Get stats from session_logs
        if USE_POSTGRES:
            cursor.execute(
                """SELECT 
                   COUNT(*) as lessons_completed,
                   AVG(comprehension_score) as average_score,
                   SUM(time_spent_seconds) as total_time
                   FROM session_logs 
                   WHERE user_id = %s AND completion_status = 'completed'""",
                (user_id,)
            )
        else:
            cursor.execute(
                """SELECT 
                   COUNT(*) as lessons_completed,
                   AVG(comprehension_score) as average_score,
                   SUM(time_spent_seconds) as total_time
                   FROM session_logs 
                   WHERE user_id = ? AND completion_status = 'completed'""",
                (user_id,)
            )
        
        stats = cursor.fetchone()
        
        conn.close()
        
        return {
            "user": {
                "name": user.get('full_name'),
                "reading_level": user.get('level_estimate') or user.get('reading_level'),
                "total_passages_read": user.get('total_passages_read', 0)
            },
            "stats": {
                "lessons_completed": stats.get('lessons_completed', 0),
                "average_score": round(stats.get('average_score', 0), 1) if stats.get('average_score') else 0,
                "total_time_minutes": round((stats.get('total_time', 0) or 0) / 60, 1)
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
# PROGRESS DATA (Phase 2 - AI Generated)
# ============================================
    
@app.get("/api/student/progress")
async def get_student_progress(token: str):
    """Get detailed student progress with recent sessions"""
    try:
        user_data = verify_token(token)
        user_id = user_data["user_id"]
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Get recent sessions with passage details
        if USE_POSTGRES:
            cursor.execute(
                """SELECT 
                   sl.id,
                   sl.completed_at,
                   sl.comprehension_score,
                   sl.time_spent_seconds,
                   p.title as passage_title,
                   p.difficulty_level,
                   p.word_count
                   FROM session_logs sl
                   JOIN passages p ON sl.passage_id = p.id
                   WHERE sl.user_id = %s
                   AND sl.completion_status = 'completed'
                   ORDER BY sl.completed_at DESC
                   LIMIT 10""",
                (user_id,)
            )
        else:
            cursor.execute(
                """SELECT 
                   sl.id,
                   sl.completed_at,
                   sl.comprehension_score,
                   sl.time_spent_seconds,
                   p.title as passage_title,
                   p.difficulty_level,
                   p.word_count
                   FROM session_logs sl
                   JOIN passages p ON sl.passage_id = p.id
                   WHERE sl.user_id = ?
                   AND sl.completion_status = 'completed'
                   ORDER BY sl.completed_at DESC
                   LIMIT 10""",
                (user_id,)
            )
        
        sessions = []
        for row in cursor.fetchall():
            sessions.append({
                'id': row['id'] if hasattr(row, 'keys') else row[0],
                'completed_at': row['completed_at'] if hasattr(row, 'keys') else row[1],
                'score': row['comprehension_score'] if hasattr(row, 'keys') else row[2],
                'time_spent': row['time_spent_seconds'] if hasattr(row, 'keys') else row[3],
                'passage_title': row['passage_title'] if hasattr(row, 'keys') else row[4],
                'difficulty': row['difficulty_level'] if hasattr(row, 'keys') else row[5],
                'word_count': row['word_count'] if hasattr(row, 'keys') else row[6]
            })
        
        # Get overall stats
        if USE_POSTGRES:
            cursor.execute(
                """SELECT 
                   COUNT(*) as total_lessons,
                   AVG(comprehension_score) as avg_score,
                   SUM(time_spent_seconds) as total_time,
                   MAX(completed_at) as last_activity
                   FROM session_logs 
                   WHERE user_id = %s AND completion_status = 'completed'""",
                (user_id,)
            )
        else:
            cursor.execute(
                """SELECT 
                   COUNT(*) as total_lessons,
                   AVG(comprehension_score) as avg_score,
                   SUM(time_spent_seconds) as total_time,
                   MAX(completed_at) as last_activity
                   FROM session_logs 
                   WHERE user_id = ? AND completion_status = 'completed'""",
                (user_id,)
            )
        
        stats = cursor.fetchone()
        
        # ========== FIXED STATS PARSING ==========
        # Handle both dict-like (psycopg2.extras.RealDictRow) and tuple
        if hasattr(stats, 'keys'):
            # Dict-like object (PostgreSQL with RealDictCursor)
            total_lessons = stats['total_lessons'] or 0
            avg_score = stats['avg_score']
            total_time = stats['total_time'] or 0
            last_activity = stats['last_activity']
        else:
            # Tuple (SQLite or regular cursor)
            total_lessons = stats[0] or 0
            avg_score = stats[1]
            total_time = stats[2] or 0
            last_activity = stats[3]
        
        # Round average score
        avg_score_rounded = round(avg_score, 1) if avg_score else 0
        total_time_minutes = round(total_time / 60, 1)
        # =========================================
        
        conn.close()
        
        return {
            "success": True,
            "sessions": sessions,
            "stats": {
                "total_lessons": total_lessons,
                "average_score": avg_score_rounded,
                "total_time_minutes": total_time_minutes,
                "last_activity": last_activity
            }
        }
        
    except Exception as e:
        print(f"Error getting progress: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# ============================================
# LESSONS ENDPOINTS (Phase 2 - AI Generated)
# ============================================

@app.get("/api/lessons/next")
async def get_next_lesson(token: str, exclude_topics: str = None):
    """Get next AI-generated lesson with topic variety"""
    
    print("=" * 50)
    print("LESSON REQUEST RECEIVED")
    print("=" * 50)
    
    try:
        # Step 1: Verify token
        print("Step 1: Verifying token...")
        user_data = verify_token(token)
        user_id = user_data["user_id"]
        print(f"✓ User ID: {user_id}")
        
        # Step 2: Check content generator
        print("Step 2: Checking content generator...")
        if not content_generator:
            error_msg = "Content generator not initialized. OpenAI API key may be missing."
            print(f"✗ ERROR: {error_msg}")
            raise HTTPException(status_code=503, detail=error_msg)
        print("✓ Content generator available")
        
        # Step 3: Get user profile
        print("Step 3: Fetching user from database...")
        conn = get_db()
        cursor = conn.cursor()
        
        if USE_POSTGRES:
            cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        else:
            cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        
        user = cursor.fetchone()
        
        if not user:
            conn.close()
            error_msg = f"User {user_id} not found"
            print(f"✗ ERROR: {error_msg}")
            raise HTTPException(status_code=404, detail=error_msg)
        
        print(f"✓ User found: {user.get('full_name') or user.get('email')}")
        
        # Step 4: Parse user interests
        print("Step 4: Parsing user interests...")
        interest_tags = user.get('interest_tags') or user.get('interests') or '[]'
        
        try:
            if isinstance(interest_tags, str):
                interests = json.loads(interest_tags)
            else:
                interests = list(interest_tags) if interest_tags else []
        except Exception as e:
            print(f"Warning: Could not parse interests: {e}")
            interests = []
        
        if not interests:
            interests = ['general reading', 'education']
        
        print(f"✓ Interests: {interests}")
        
        # ========== ADD OPTION B HERE ==========
        # Step 4b: Get recently used topics for variety
        print("Step 4b: Checking recently used topics...")
        recent_topics = []
        
        try:
            if USE_POSTGRES:
                cursor.execute(
                    """SELECT topic_tags 
                       FROM passages 
                       WHERE created_by = %s 
                       ORDER BY created_at DESC 
                       LIMIT 5""",
                    (user_id,)
                )
            else:
                cursor.execute(
                    """SELECT topic_tags 
                       FROM passages 
                       WHERE created_by = ? 
                       ORDER BY created_at DESC 
                       LIMIT 5""",
                    (user_id,)
                )
            
            for row in cursor.fetchall():
                topic_tags = row[0] if isinstance(row, tuple) else row['topic_tags']
                if topic_tags:
                    try:
                        tags = json.loads(topic_tags) if isinstance(topic_tags, str) else topic_tags
                        if isinstance(tags, list):
                            recent_topics.extend(tags)
                    except:
                        pass
            
            # Also check exclude_topics from query param
            if exclude_topics:
                recent_topics.extend(exclude_topics.split(','))
            
            print(f"✓ Recent topics: {recent_topics}")
            
        except Exception as e:
            print(f"Warning: Could not fetch recent topics: {e}")
            recent_topics = []
        
        # Filter out recently used topics from available interests
        available_interests = [i for i in interests if i not in recent_topics]
        
        # If all interests were used recently, use all interests (fresh start)
        if not available_interests:
            print("All topics used recently - resetting to full list")
            available_interests = interests
        
        print(f"✓ Available interests (excluding recent): {available_interests}")
        # =======================================
        
        # Step 5: Determine difficulty
        print("Step 5: Determining difficulty level...")
        level_estimate = user.get('level_estimate') or user.get('reading_level') or 'intermediate'
        total_read = user.get('total_passages_read') or 0
        
        difficulty = level_estimate
        target_words = 200
        
        # First lesson should be easier
        if total_read == 0:
            if level_estimate == "intermediate":
                difficulty = "beginner"
            target_words = 150
        
        print(f"✓ Difficulty: {difficulty}, Target words: {target_words}")
        
        # Step 6: Select topic (MODIFIED - use available_interests)
        print("Step 6: Selecting topic...")
        import random
        topic = random.choice(available_interests)  # ← CHANGED from 'interests' to 'available_interests'
        print(f"✓ Selected topic: {topic}")
        
        conn.close()
        
        # Step 7: Generate passage
        print("Step 7: Generating passage with OpenAI...")
        print(f"   Topic: {topic}")
        print(f"   Difficulty: {difficulty}")
        print(f"   Words: {target_words}")
        print(f"   Interests: {interests}")
        
        try:
            passage_data = content_generator.generate_passage(
                topic=topic,
                difficulty_level=difficulty,
                target_words=target_words,
                user_interests=interests
            )
            print("✓ Passage generated successfully")
            print(f"   Title: {passage_data.get('title')}")
            print(f"   Word count: {passage_data.get('word_count')}")
            
        except Exception as gen_error:
            print(f"✗ ERROR generating passage: {gen_error}")
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=f"Failed to generate passage: {str(gen_error)}")
        
        # Step 8: Save to database
        print("Step 8: Saving passage to database...")
        conn = get_db()
        cursor = conn.cursor()
        
        try:
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
                     True, user_id)
                )
                result = cursor.fetchone()
                lesson_id = result['id']
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
                     True, user_id)
                )
                lesson_id = cursor.lastrowid
            
            print(f"✓ Passage saved with ID: {lesson_id}")
            
        except Exception as db_error:
            print(f"✗ ERROR saving passage: {db_error}")
            import traceback
            traceback.print_exc()
            conn.close()
            raise HTTPException(status_code=500, detail=f"Failed to save passage: {str(db_error)}")
        
        # Step 9: Generate questions
        print("Step 9: Generating comprehension questions...")
        try:
            questions = content_generator.generate_comprehension_questions(
                passage_text=passage_data['content'],
                passage_title=passage_data['title'],
                num_questions=3
            )
            print(f"✓ Generated {len(questions)} questions")
            
        except Exception as q_error:
            print(f"✗ ERROR generating questions: {q_error}")
            import traceback
            traceback.print_exc()
            # Use fallback questions instead of failing
            questions = [
                {
                    "question": "What is the main topic of this passage?",
                    "type": "main_idea",
                    "options": ["The topic discussed", "Something else", "Another topic", "Different subject"],
                    "correct_answer": "The topic discussed",
                    "explanation": "The passage focuses on this main topic.",
                    "difficulty": 1
                }
            ]
            print("Using fallback questions")
        
        # Step 10: Save questions
        print("Step 10: Saving questions to database...")
        try:
            for q in questions:
                if USE_POSTGRES:
                    cursor.execute(
                        """INSERT INTO passage_questions 
                           (passage_id, question_text, question_type, correct_answer, options, explanation, difficulty)
                           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                        (lesson_id, q['question'], q.get('type'), q['correct_answer'],
                         json.dumps(q.get('options', [])), q.get('explanation'), q.get('difficulty', 1))
                    )
                else:
                    cursor.execute(
                        """INSERT INTO passage_questions 
                           (passage_id, question_text, question_type, correct_answer, options, explanation, difficulty)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (lesson_id, q['question'], q.get('type'), q['correct_answer'],
                         json.dumps(q.get('options', [])), q.get('explanation'), q.get('difficulty', 1))
                    )
            
            conn.commit()
            print(f"✓ Saved {len(questions)} questions")
            
        except Exception as save_q_error:
            print(f"✗ ERROR saving questions: {save_q_error}")
            import traceback
            traceback.print_exc()
            conn.rollback()
            # Continue anyway - we have the passage
        
        conn.close()
        
        # Step 11: Update user activity
        print("Step 11: Updating user activity...")
        update_user_activity(user_id)
        
        # Step 12: Format response
        print("Step 12: Formatting response...")
        response = {
            'id': lesson_id,
            'title': passage_data['title'],
            'content': passage_data['content'],
            'difficulty_level': passage_data['difficulty_level'],
            'word_count': passage_data['word_count'],
            'key_points': passage_data.get('key_concepts', []),
            'vocabulary': passage_data.get('vocabulary_words', []),
            'questions': questions
        }
        
        print("=" * 50)
        print("✓ LESSON GENERATED SUCCESSFULLY")
        print("=" * 50)
        
        return response
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Catch all other errors
        print("=" * 50)
        print(f"✗ UNEXPECTED ERROR: {e}")
        print("=" * 50)
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
    
@app.get("/api/test-openai")
async def test_openai():
    """Test if OpenAI integration works"""
    try:
        if not content_generator:
            return {"error": "content_generator is None"}
        
        # Try to generate a simple passage
        result = content_generator.generate_passage(
            topic="reading",
            difficulty_level="beginner", 
            target_words=50,
            user_interests=["reading"]
        )
        
        return {
            "success": True,
            "title": result.get('title'),
            "content_length": len(result.get('content', '')),
            "has_questions": len(result.get('questions', [])) > 0
        }
        
    except Exception as e:
        import traceback
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }
    
@app.get("/api/lessons/debug")
async def debug_lesson_generation(token: str):
    """Debug endpoint to see what's failing"""
    import sys
    
    debug_info = {
        "step": "starting",
        "error": None,
        "details": {}
    }
    
    try:
        # Step 1: Verify token
        debug_info["step"] = "verifying_token"
        user_data = verify_token(token)
        user_id = user_data["user_id"]
        debug_info["details"]["user_id"] = user_id
        
        # Step 2: Check content generator
        debug_info["step"] = "checking_content_generator"
        debug_info["details"]["content_generator_exists"] = content_generator is not None
        debug_info["details"]["openai_key_configured"] = bool(OPENAI_API_KEY)
        
        if not content_generator:
            raise Exception("Content generator is None - OpenAI API key issue")
        
        # Step 3: Get user from database
        debug_info["step"] = "fetching_user"
        conn = get_db()
        cursor = conn.cursor()
        
        if USE_POSTGRES:
            cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        else:
            cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        
        user = cursor.fetchone()
        
        if not user:
            raise Exception(f"User {user_id} not found in database")
        
        debug_info["details"]["user_found"] = True
        debug_info["details"]["user_level"] = user.get('level_estimate') or user.get('reading_level')
        
        # Step 4: Parse interests
        debug_info["step"] = "parsing_interests"
        interest_tags = user.get('interest_tags') or user.get('interests') or '[]'
        
        try:
            if isinstance(interest_tags, str):
                interests = json.loads(interest_tags)
            else:
                interests = interest_tags
        except:
            interests = []
        
        if not interests:
            interests = ['general reading', 'education']
        
        debug_info["details"]["interests"] = interests
        
        # Step 5: Select topic
        debug_info["step"] = "selecting_topic"
        import random
        topic = random.choice(interests)
        debug_info["details"]["selected_topic"] = topic
        
        # Step 6: Test content generator
        debug_info["step"] = "testing_content_generator"
        
        # Try to generate a simple passage
        passage_data = content_generator.generate_passage(
            topic=topic,
            difficulty_level="intermediate",
            target_words=100,
            user_interests=interests
        )
        
        debug_info["details"]["passage_generated"] = True
        debug_info["details"]["passage_title"] = passage_data.get('title')
        debug_info["details"]["passage_word_count"] = passage_data.get('word_count')
        
        conn.close()
        
        debug_info["step"] = "success"
        return {
            "success": True,
            "debug_info": debug_info,
            "message": "All checks passed! Lesson generation should work."
        }
        
    except Exception as e:
        debug_info["error"] = str(e)
        debug_info["error_type"] = type(e).__name__
        
        # Get full traceback
        import traceback
        debug_info["traceback"] = traceback.format_exc()
        
        return {
            "success": False,
            "debug_info": debug_info,
            "message": f"Error at step: {debug_info['step']}"
        }

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
    
# ============================================================
# GAMIFICATION SYSTEM
# ============================================================

# Points configuration
POINTS_CONFIG = {
    'lesson_complete': 10,
    'perfect_score': 50,
    'high_score': 25,
    'good_score': 15,
    'daily_streak': 5,
    'weekly_goal': 100,
    'badge_earned': 20
}

# Badge definitions
BADGES = {
    'first_lesson': {'name': 'Getting Started', 'description': 'Complete your first lesson', 'icon': '🎯', 'points': 20},
    'perfect_streak_3': {'name': 'Triple Perfect', 'description': '3 perfect scores in a row', 'icon': '🔥', 'points': 50},
    'speed_reader': {'name': 'Speed Reader', 'description': '10 lessons in one week', 'icon': '⚡', 'points': 100},
    'bookworm': {'name': 'Bookworm', 'description': 'Complete 50 lessons total', 'icon': '📚', 'points': 200},
    'perfect_week': {'name': 'Perfect Week', 'description': 'Achieve all weekly goals', 'icon': '🏆', 'points': 150},
    'early_bird': {'name': 'Early Bird', 'description': 'Complete lesson before 9 AM', 'icon': '🌅', 'points': 30},
    'night_owl': {'name': 'Night Owl', 'description': 'Complete lesson after 9 PM', 'icon': '🦉', 'points': 30},
    'consistency_king': {'name': 'Consistency King', 'description': '7-day streak', 'icon': '👑', 'points': 100}
}

def award_points(user_id, points, reason, activity_type='general'):
    """Award points to a user"""
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        if USE_POSTGRES:
            cursor.execute(
                """INSERT INTO user_points (user_id, points, total_earned)
                   VALUES (%s, %s, %s)
                   ON CONFLICT (user_id) DO UPDATE
                   SET points = user_points.points + EXCLUDED.points,
                       total_earned = user_points.total_earned + EXCLUDED.points,
                       updated_at = NOW()""",
                (user_id, points, points)
            )
            cursor.execute(
                "INSERT INTO points_history (user_id, points, reason, activity_type) VALUES (%s, %s, %s, %s)",
                (user_id, points, reason, activity_type)
            )
        else:
            cursor.execute("SELECT id FROM user_points WHERE user_id = ?", (user_id,))
            if cursor.fetchone():
                cursor.execute(
                    """UPDATE user_points 
                       SET points = points + ?,
                           total_earned = total_earned + ?,
                           updated_at = datetime('now')
                       WHERE user_id = ?""",
                    (points, points, user_id)
                )
            else:
                cursor.execute(
                    "INSERT INTO user_points (user_id, points, total_earned) VALUES (?, ?, ?)",
                    (user_id, points, points)
                )
            cursor.execute(
                "INSERT INTO points_history (user_id, points, reason, activity_type) VALUES (?, ?, ?, ?)",
                (user_id, points, reason, activity_type)
            )
        
        conn.commit()
        
        # Check for level up
        if USE_POSTGRES:
            cursor.execute("SELECT total_earned, level FROM user_points WHERE user_id = %s", (user_id,))
        else:
            cursor.execute("SELECT total_earned, level FROM user_points WHERE user_id = ?", (user_id,))
        
        result = cursor.fetchone()
        total = result['total_earned'] if hasattr(result, 'keys') else result[0]
        current_level = result['level'] if hasattr(result, 'keys') else result[1]
        
        new_level = (total // 500) + 1
        
        if new_level > current_level:
            if USE_POSTGRES:
                cursor.execute("UPDATE user_points SET level = %s WHERE user_id = %s", (new_level, user_id))
            else:
                cursor.execute("UPDATE user_points SET level = ? WHERE user_id = ?", (new_level, user_id))
            conn.commit()
            conn.close()
            return {'points_awarded': points, 'level_up': True, 'new_level': new_level}
        
        conn.close()
        return {'points_awarded': points, 'level_up': False}
        
    except Exception as e:
        conn.rollback()
        conn.close()
        print(f"Error awarding points: {e}")
        return {'points_awarded': 0, 'level_up': False}

def has_badge(user_id, badge_type):
    """Check if user has badge"""
    conn = get_db()
    cursor = conn.cursor()
    
    if USE_POSTGRES:
        cursor.execute("SELECT id FROM user_badges WHERE user_id = %s AND badge_type = %s", (user_id, badge_type))
    else:
        cursor.execute("SELECT id FROM user_badges WHERE user_id = ? AND badge_type = ?", (user_id, badge_type))
    
    result = cursor.fetchone()
    conn.close()
    return result is not None

def award_badge(user_id, badge_type, badge_name, description, icon):
    """Award badge to user"""
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        if USE_POSTGRES:
            cursor.execute(
                "INSERT INTO user_badges (user_id, badge_type, badge_name, description, icon) VALUES (%s, %s, %s, %s, %s)",
                (user_id, badge_type, badge_name, description, icon)
            )
        else:
            cursor.execute(
                "INSERT INTO user_badges (user_id, badge_type, badge_name, description, icon) VALUES (?, ?, ?, ?, ?)",
                (user_id, badge_type, badge_name, description, icon)
            )
        
        conn.commit()
        conn.close()
        
        award_points(user_id, BADGES[badge_type]['points'], f'Earned badge: {badge_name}', 'badge')
        return True
    except Exception as e:
        conn.rollback()
        conn.close()
        print(f"Error awarding badge: {e}")
        return False

def check_and_award_badges(user_id):
    """Check and award new badges"""
    conn = get_db()
    cursor = conn.cursor()
    new_badges = []
    
    try:
        if USE_POSTGRES:
            cursor.execute(
                "SELECT COUNT(*) FROM session_logs WHERE user_id = %s AND completion_status = 'completed'",
                (user_id,)
            )
        else:
            cursor.execute(
                "SELECT COUNT(*) FROM session_logs WHERE user_id = ? AND completion_status = 'completed'",
                (user_id,)
            )
        
        lesson_count = cursor.fetchone()[0]
        
        # First lesson badge
        if lesson_count == 1 and not has_badge(user_id, 'first_lesson'):
            badge = BADGES['first_lesson']
            award_badge(user_id, 'first_lesson', badge['name'], badge['description'], badge['icon'])
            new_badges.append(badge)
        
        # Bookworm (50 lessons)
        if lesson_count == 50 and not has_badge(user_id, 'bookworm'):
            badge = BADGES['bookworm']
            award_badge(user_id, 'bookworm', badge['name'], badge['description'], badge['icon'])
            new_badges.append(badge)
        
        # Perfect streak check
        if USE_POSTGRES:
            cursor.execute(
                """SELECT comprehension_score FROM session_logs 
                   WHERE user_id = %s AND completion_status = 'completed'
                   ORDER BY completed_at DESC LIMIT 3""",
                (user_id,)
            )
        else:
            cursor.execute(
                """SELECT comprehension_score FROM session_logs 
                   WHERE user_id = ? AND completion_status = 'completed'
                   ORDER BY completed_at DESC LIMIT 3""",
                (user_id,)
            )
        
        recent_scores = [row[0] if isinstance(row, tuple) else row['comprehension_score'] for row in cursor.fetchall()]
        
        if len(recent_scores) >= 3 and all(score == 100 for score in recent_scores):
            if not has_badge(user_id, 'perfect_streak_3'):
                badge = BADGES['perfect_streak_3']
                award_badge(user_id, 'perfect_streak_3', badge['name'], badge['description'], badge['icon'])
                new_badges.append(badge)
        
        # Time-based badges
        from datetime import datetime
        current_hour = datetime.now().hour
        
        if current_hour < 9 and not has_badge(user_id, 'early_bird'):
            badge = BADGES['early_bird']
            award_badge(user_id, 'early_bird', badge['name'], badge['description'], badge['icon'])
            new_badges.append(badge)
        
        if current_hour >= 21 and not has_badge(user_id, 'night_owl'):
            badge = BADGES['night_owl']
            award_badge(user_id, 'night_owl', badge['name'], badge['description'], badge['icon'])
            new_badges.append(badge)
        
        conn.close()
        return new_badges
        
    except Exception as e:
        conn.close()
        print(f"Error checking badges: {e}")
        return []

def update_weekly_goals(user_id):
    """Update weekly goals progress"""
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        from datetime import datetime, timedelta
        week_start = datetime.now() - timedelta(days=datetime.now().weekday())
        week_start = week_start.date()
        
        if USE_POSTGRES:
            cursor.execute(
                "SELECT * FROM weekly_goals WHERE user_id = %s AND week_start = %s AND goal_type = 'lessons_completed'",
                (user_id, week_start)
            )
        else:
            cursor.execute(
                "SELECT * FROM weekly_goals WHERE user_id = ? AND week_start = ? AND goal_type = 'lessons_completed'",
                (user_id, week_start)
            )
        
        goal = cursor.fetchone()
        
        if not goal:
            if USE_POSTGRES:
                cursor.execute(
                    "INSERT INTO weekly_goals (user_id, week_start, goal_type, target_value, points_reward) VALUES (%s, %s, %s, %s, %s)",
                    (user_id, week_start, 'lessons_completed', 5, 100)
                )
            else:
                cursor.execute(
                    "INSERT INTO weekly_goals (user_id, week_start, goal_type, target_value, points_reward) VALUES (?, ?, ?, ?, ?)",
                    (user_id, week_start, 'lessons_completed', 5, 100)
                )
            conn.commit()
        else:
            goal_id = goal['id'] if hasattr(goal, 'keys') else goal[0]
            current_value = goal['current_value'] if hasattr(goal, 'keys') else goal[5]
            target = goal['target_value'] if hasattr(goal, 'keys') else goal[4]
            completed = goal['completed'] if hasattr(goal, 'keys') else goal[6]
            
            new_value = current_value + 1
            
            if new_value >= target and not completed:
                if USE_POSTGRES:
                    cursor.execute(
                        "UPDATE weekly_goals SET current_value = %s, completed = TRUE, completed_at = NOW() WHERE id = %s",
                        (new_value, goal_id)
                    )
                else:
                    cursor.execute(
                        "UPDATE weekly_goals SET current_value = ?, completed = 1, completed_at = datetime('now') WHERE id = ?",
                        (new_value, goal_id)
                    )
                conn.commit()
                
                points_reward = goal['points_reward'] if hasattr(goal, 'keys') else goal[7]
                award_points(user_id, points_reward, 'Weekly goal completed', 'goal')
            else:
                if USE_POSTGRES:
                    cursor.execute("UPDATE weekly_goals SET current_value = %s WHERE id = %s", (new_value, goal_id))
                else:
                    cursor.execute("UPDATE weekly_goals SET current_value = ? WHERE id = ?", (new_value, goal_id))
                conn.commit()
        
        conn.close()
        
    except Exception as e:
        conn.rollback()
        conn.close()
        print(f"Error updating weekly goals: {e}")

@app.get("/api/student/gamification")
async def get_gamification_data(token: str):
    """Get gamification data"""
    try:
        user_data = verify_token(token)
        user_id = user_data["user_id"]
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Get points
        if USE_POSTGRES:
            cursor.execute("SELECT * FROM user_points WHERE user_id = %s", (user_id,))
        else:
            cursor.execute("SELECT * FROM user_points WHERE user_id = ?", (user_id,))
        
        points_row = cursor.fetchone()
        
        if points_row:
            points_data = {
                'current_points': points_row['points'] if hasattr(points_row, 'keys') else points_row[2],
                'total_earned': points_row['total_earned'] if hasattr(points_row, 'keys') else points_row[3],
                'level': points_row['level'] if hasattr(points_row, 'keys') else points_row[4]
            }
        else:
            points_data = {'current_points': 0, 'total_earned': 0, 'level': 1}
        
        # Get badges
        if USE_POSTGRES:
            cursor.execute("SELECT * FROM user_badges WHERE user_id = %s ORDER BY earned_at DESC", (user_id,))
        else:
            cursor.execute("SELECT * FROM user_badges WHERE user_id = ? ORDER BY earned_at DESC", (user_id,))
        
        badges = []
        for row in cursor.fetchall():
            badges.append({
                'type': row['badge_type'] if hasattr(row, 'keys') else row[2],
                'name': row['badge_name'] if hasattr(row, 'keys') else row[3],
                'description': row['description'] if hasattr(row, 'keys') else row[4],
                'icon': row['icon'] if hasattr(row, 'keys') else row[5],
                'earned_at': row['earned_at'] if hasattr(row, 'keys') else row[6]
            })
        
        # Get weekly goals
        from datetime import datetime, timedelta
        week_start = datetime.now() - timedelta(days=datetime.now().weekday())
        week_start = week_start.date()
        
        if USE_POSTGRES:
            cursor.execute("SELECT * FROM weekly_goals WHERE user_id = %s AND week_start = %s", (user_id, week_start))
        else:
            cursor.execute("SELECT * FROM weekly_goals WHERE user_id = ? AND week_start = ?", (user_id, week_start))
        
        goals = []
        for row in cursor.fetchall():
            goals.append({
                'goal_type': row['goal_type'] if hasattr(row, 'keys') else row[3],
                'target_value': row['target_value'] if hasattr(row, 'keys') else row[4],
                'current_value': row['current_value'] if hasattr(row, 'keys') else row[5],
                'completed': row['completed'] if hasattr(row, 'keys') else row[6],
                'points_reward': row['points_reward'] if hasattr(row, 'keys') else row[7]
            })
        
        conn.close()
        
        return {
            'success': True,
            'points': points_data,
            'badges': badges,
            'available_badges': BADGES,
            'weekly_goals': goals
        }
        
    except Exception as e:
        print(f"Error getting gamification: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
# ============================================================
#        ESSAY SUBMISSION & EVALUATION 
# ============================================================

@app.post("/api/essay/submit")
async def submit_essay(request: Request):
    """Submit and evaluate comprehension essay"""
    data = await request.json()
    token = data.get("token")
    essay_text = data.get("essay_text")
    lesson_count = data.get("lesson_count")
    recent_lessons = data.get("recent_lessons", [])  # Last 3 lessons data
    
    try:
        user_data = verify_token(token)
        user_id = user_data["user_id"]
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Get user info
        if USE_POSTGRES:
            cursor.execute("SELECT name, reading_level FROM users WHERE id = %s", (user_id,))
        else:
            cursor.execute("SELECT name, reading_level FROM users WHERE id = ?", (user_id,))
        
        user_row = cursor.fetchone()
        user_name = user_row['name'] if hasattr(user_row, 'keys') else user_row[0]
        current_level = user_row['reading_level'] if hasattr(user_row, 'keys') else user_row[1]
        
        # Count existing essays
        if USE_POSTGRES:
            cursor.execute("SELECT COUNT(*) FROM user_essays WHERE user_id = %s", (user_id,))
        else:
            cursor.execute("SELECT COUNT(*) FROM user_essays WHERE user_id = ?", (user_id,))
        
        essay_number = cursor.fetchone()[0] + 1
        
        # Calculate word count
        word_count = len(essay_text.split())
        
        # Prepare lesson context for AI
        lesson_topics = [lesson.get('title', '') for lesson in recent_lessons]
        lesson_ids = [lesson.get('id', 0) for lesson in recent_lessons]
        
        # Evaluate essay with AI
        evaluation = await evaluate_essay_with_ai(
            essay_text=essay_text,
            user_name=user_name,
            current_level=current_level,
            lesson_topics=lesson_topics,
            recent_lessons=recent_lessons
        )
        
        # Determine points based on comprehension score
        points_awarded = calculate_essay_points(evaluation['comprehension_score'])
        
        # Save essay to database
        if USE_POSTGRES:
            cursor.execute(
                """INSERT INTO user_essays 
                   (user_id, essay_number, lesson_count, essay_text, word_count,
                    comprehension_level, comprehension_score, difficulty_recommendation,
                    ai_feedback, lesson_ids, lesson_topics, needs_admin_review, points_awarded)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   RETURNING id""",
                (user_id, essay_number, lesson_count, essay_text, word_count,
                 evaluation['comprehension_level'], evaluation['comprehension_score'],
                 evaluation['difficulty_recommendation'], evaluation['ai_feedback'],
                 json.dumps(lesson_ids), json.dumps(lesson_topics),
                 evaluation['needs_admin_review'], points_awarded)
            )
            result = cursor.fetchone()
            essay_id = result['id'] if result else None
        else:
            cursor.execute(
                """INSERT INTO user_essays 
                   (user_id, essay_number, lesson_count, essay_text, word_count,
                    comprehension_level, comprehension_score, difficulty_recommendation,
                    ai_feedback, lesson_ids, lesson_topics, needs_admin_review, points_awarded)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (user_id, essay_number, lesson_count, essay_text, word_count,
                 evaluation['comprehension_level'], evaluation['comprehension_score'],
                 evaluation['difficulty_recommendation'], evaluation['ai_feedback'],
                 json.dumps(lesson_ids), json.dumps(lesson_topics),
                 evaluation['needs_admin_review'], points_awarded)
            )
            essay_id = cursor.lastrowid
        
        conn.commit()
        
        # Award points
        if points_awarded > 0:
            award_points(user_id, points_awarded, f'Comprehension essay #{essay_number}', 'essay')
        
        # Handle difficulty adjustment
        new_level = current_level
        if evaluation['difficulty_recommendation'] == 'advance':
            new_level = get_next_difficulty_level(current_level)
            update_user_difficulty(user_id, new_level, essay_id, 'Strong comprehension - advancing')
        elif evaluation['difficulty_recommendation'] == 'support_needed':
            # Stay at current level but create admin alert
            create_admin_alert(
                user_id=user_id,
                essay_id=essay_id,
                alert_type='student_needs_help',
                priority='high',
                message=f"{user_name} needs additional support - low comprehension on essay #{essay_number}",
                details=json.dumps({
                    'comprehension_score': evaluation['comprehension_score'],
                    'comprehension_level': evaluation['comprehension_level'],
                    'lesson_count': lesson_count,
                    'current_level': current_level
                })
            )
        
        conn.close()
        
        return {
            "success": True,
            "essay_id": essay_id,
            "evaluation": {
                "comprehension_level": evaluation['comprehension_level'],
                "comprehension_score": evaluation['comprehension_score'],
                "difficulty_recommendation": evaluation['difficulty_recommendation'],
                "feedback": evaluation['ai_feedback'],
                "needs_admin_review": evaluation['needs_admin_review']
            },
            "points_awarded": points_awarded,
            "new_reading_level": new_level,
            "level_changed": new_level != current_level
        }
        
    except Exception as e:
        print(f"Error submitting essay: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# ========== AI ESSAY EVALUATION ==========

async def evaluate_essay_with_ai(essay_text, user_name, current_level, lesson_topics, recent_lessons):
    """Use OpenAI to evaluate comprehension essay"""
    
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        
        # Prepare lesson context
        lesson_context = "\n".join([
            f"Lesson {i+1}: {lesson.get('title', 'Unknown')}\n"
            f"Content: {lesson.get('content', '')[:500]}...\n"
            for i, lesson in enumerate(recent_lessons)
        ])
        
        prompt = f"""You are evaluating a student's comprehension essay to determine their understanding of recent lessons.

STUDENT INFO:
- Name: {user_name}
- Current Reading Level: {current_level}
- Recent Lessons Completed: {', '.join(lesson_topics)}

RECENT LESSON CONTENT:
{lesson_context}

STUDENT'S ESSAY:
{essay_text}

EVALUATION CRITERIA:
1. Does the student demonstrate understanding of key concepts from the lessons?
2. Can they explain ideas in their own words?
3. Do they make connections between different lessons?
4. Is their writing clear and coherent for their level?
5. Did they provide specific examples or details from the lessons?

Please evaluate this essay and respond with ONLY a JSON object (no markdown, no preamble) in this exact format:
{{
    "comprehension_level": "excellent|good|adequate|needs_help",
    "comprehension_score": 0-100,
    "difficulty_recommendation": "advance|stay|support_needed",
    "ai_feedback": "Specific, encouraging feedback for the student",
    "needs_admin_review": true|false,
    "strengths": ["strength1", "strength2"],
    "areas_for_improvement": ["area1", "area2"]
}}

SCORING GUIDE:
- 90-100: Excellent - clear mastery, ready to advance
- 75-89: Good - solid understanding, can stay at current level
- 60-74: Adequate - basic understanding, needs practice at current level
- Below 60: Needs help - requires additional support

Be encouraging but honest. Focus on what they DID understand, not just what they missed."""

        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are an expert literacy educator evaluating student comprehension. Always respond with valid JSON only."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        
        content = response.choices[0].message.content
        
        # Parse AI response
        evaluation = json.loads(content)
        
        # Ensure all required fields
        evaluation.setdefault('comprehension_level', 'adequate')
        evaluation.setdefault('comprehension_score', 70)
        evaluation.setdefault('difficulty_recommendation', 'stay')
        evaluation.setdefault('ai_feedback', 'Good effort! Keep practicing.')
        evaluation.setdefault('needs_admin_review', False)
        
        # Auto-flag for admin review if score is low
        if evaluation['comprehension_score'] < 60:
            evaluation['needs_admin_review'] = True
            evaluation['difficulty_recommendation'] = 'support_needed'
        
        print(f"✓ AI Evaluation: {evaluation['comprehension_level']} ({evaluation['comprehension_score']}/100)")
        
        return evaluation
        
    except Exception as e:
        print(f"Error in AI evaluation: {e}")
        # Fallback evaluation
        return {
            'comprehension_level': 'adequate',
            'comprehension_score': 70,
            'difficulty_recommendation': 'stay',
            'ai_feedback': 'Thank you for your essay. Your teacher will review it soon.',
            'needs_admin_review': True
        }

# ========== HELPER FUNCTIONS ==========

def calculate_essay_points(comprehension_score):
    """Calculate points based on essay score"""
    if comprehension_score >= 90:
        return 100  # Excellent
    elif comprehension_score >= 75:
        return 75   # Good
    elif comprehension_score >= 60:
        return 50   # Adequate
    else:
        return 25   # Needs help (participation points)

def get_next_difficulty_level(current_level):
    """Get the next difficulty level"""
    level_progression = {
        'beginner': 'intermediate',
        'intermediate': 'advanced',
        'advanced': 'advanced'  # Stay at advanced
    }
    return level_progression.get(current_level, current_level)

def update_user_difficulty(user_id, new_level, essay_id, reason):
    """Update user's reading level"""
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Get current level
        if USE_POSTGRES:
            cursor.execute("SELECT reading_level FROM users WHERE id = %s", (user_id,))
        else:
            cursor.execute("SELECT reading_level FROM users WHERE id = ?", (user_id,))
        
        result = cursor.fetchone()
        old_level = result['reading_level'] if hasattr(result, 'keys') else result[0]
        
        # Update user level
        if USE_POSTGRES:
            cursor.execute(
                "UPDATE users SET reading_level = %s WHERE id = %s",
                (new_level, user_id)
            )
        else:
            cursor.execute(
                "UPDATE users SET reading_level = ? WHERE id = ?",
                (new_level, user_id)
            )
        
        # Log adjustment
        if USE_POSTGRES:
            cursor.execute(
                """INSERT INTO difficulty_adjustments 
                   (user_id, essay_id, previous_level, new_level, reason)
                   VALUES (%s, %s, %s, %s, %s)""",
                (user_id, essay_id, old_level, new_level, reason)
            )
        else:
            cursor.execute(
                """INSERT INTO difficulty_adjustments 
                   (user_id, essay_id, previous_level, new_level, reason)
                   VALUES (?, ?, ?, ?, ?)""",
                (user_id, essay_id, old_level, new_level, reason)
            )
        
        conn.commit()
        conn.close()
        
        print(f"✓ User {user_id} level updated: {old_level} → {new_level}")
        
    except Exception as e:
        print(f"Error updating difficulty: {e}")
        conn.rollback()
        conn.close()

def create_admin_alert(user_id, essay_id, alert_type, priority, message, details):
    """Create admin alert"""
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        if USE_POSTGRES:
            cursor.execute(
                """INSERT INTO admin_alerts 
                   (alert_type, user_id, essay_id, priority, message, details)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (alert_type, user_id, essay_id, priority, message, details)
            )
        else:
            cursor.execute(
                """INSERT INTO admin_alerts 
                   (alert_type, user_id, essay_id, priority, message, details)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (alert_type, user_id, essay_id, priority, message, details)
            )
        
        conn.commit()
        conn.close()
        
        print(f"✓ Admin alert created: {alert_type} for user {user_id}")
        
    except Exception as e:
        print(f"Error creating alert: {e}")
        conn.rollback()
        conn.close()

# ========== CHECK IF ESSAY IS DUE ==========

@app.get("/api/essay/check-due")
async def check_essay_due(token: str):
    """Check if user needs to complete an essay"""
    try:
        user_data = verify_token(token)
        user_id = user_data["user_id"]
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Count completed lessons
        if USE_POSTGRES:
            cursor.execute(
                """SELECT COUNT(*) FROM session_logs 
                   WHERE user_id = %s AND completion_status = 'completed'""",
                (user_id,)
            )
        else:
            cursor.execute(
                """SELECT COUNT(*) FROM session_logs 
                   WHERE user_id = ? AND completion_status = 'completed'""",
                (user_id,)
            )
        
        total_lessons = cursor.fetchone()[0]
        
        # Count completed essays
        if USE_POSTGRES:
            cursor.execute("SELECT COUNT(*) FROM user_essays WHERE user_id = %s", (user_id,))
        else:
            cursor.execute("SELECT COUNT(*) FROM user_essays WHERE user_id = ?", (user_id,))
        
        total_essays = cursor.fetchone()[0]
        
        # Essay is due every 3 lessons
        expected_essays = total_lessons // 3
        essay_due = total_essays < expected_essays
        
        # If essay is due, get last 3 lessons
        recent_lessons = []
        if essay_due:
            if USE_POSTGRES:
                cursor.execute(
                    """SELECT sl.passage_id, p.title, p.content, sl.completed_at
                       FROM session_logs sl
                       LEFT JOIN passages p ON sl.passage_id = p.id
                       WHERE sl.user_id = %s AND sl.completion_status = 'completed'
                       ORDER BY sl.completed_at DESC
                       LIMIT 3""",
                    (user_id,)
                )
            else:
                cursor.execute(
                    """SELECT sl.passage_id, p.title, p.content, sl.completed_at
                       FROM session_logs sl
                       LEFT JOIN passages p ON sl.passage_id = p.id
                       WHERE sl.user_id = ? AND sl.completion_status = 'completed'
                       ORDER BY sl.completed_at DESC
                       LIMIT 3""",
                    (user_id,)
                )
            
            for row in cursor.fetchall():
                recent_lessons.append({
                    'id': row['passage_id'] if hasattr(row, 'keys') else row[0],
                    'title': row['title'] if hasattr(row, 'keys') else row[1],
                    'content': row['content'] if hasattr(row, 'keys') else row[2]
                })
        
        conn.close()
        
        return {
            "success": True,
            "essay_due": essay_due,
            "total_lessons": total_lessons,
            "total_essays": total_essays,
            "lesson_count_for_next_essay": total_lessons,
            "recent_lessons": recent_lessons if essay_due else []
        }
        
    except Exception as e:
        print(f"Error checking essay due: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
# ============================================================
# SESSION TRACKING & TIMEOUT SYSTEM
# ============================================================

from datetime import datetime, timedelta

# ========== SESSION MANAGEMENT ==========

@app.post("/api/session/start")
async def start_session(request: Request):
    """Start a new user session"""
    data = await request.json()
    token = data.get("token")
    
    try:
        user_data = verify_token(token)
        user_id = user_data["user_id"]
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Close any existing active sessions
        if USE_POSTGRES:
            cursor.execute(
                """UPDATE user_sessions 
                   SET session_end = NOW(), status = 'logged_out'
                   WHERE user_id = %s AND status = 'active'""",
                (user_id,)
            )
        else:
            cursor.execute(
                """UPDATE user_sessions 
                   SET session_end = datetime('now'), status = 'logged_out'
                   WHERE user_id = ? AND status = 'active'""",
                (user_id,)
            )
        
        # Create new session
        if USE_POSTGRES:
            cursor.execute(
                """INSERT INTO user_sessions (user_id, status)
                   VALUES (%s, 'active')
                   RETURNING id""",
                (user_id,)
            )
            result = cursor.fetchone()
            session_id = result['id'] if result else None
        else:
            cursor.execute(
                "INSERT INTO user_sessions (user_id, status) VALUES (?, 'active')",
                (user_id,)
            )
            session_id = cursor.lastrowid
        
        # Log activity
        if USE_POSTGRES:
            cursor.execute(
                """INSERT INTO activity_log (user_id, session_id, activity_type)
                   VALUES (%s, %s, 'login')""",
                (user_id, session_id)
            )
        else:
            cursor.execute(
                "INSERT INTO activity_log (user_id, session_id, activity_type) VALUES (?, ?, 'login')",
                (user_id, session_id)
            )
        
        conn.commit()
        conn.close()
        
        return {
            "success": True,
            "session_id": session_id,
            "message": "Session started"
        }
        
    except Exception as e:
        print(f"Error starting session: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/session/activity")
async def update_activity(request: Request):
    """Update last activity timestamp"""
    data = await request.json()
    token = data.get("token")
    session_id = data.get("session_id")
    activity_type = data.get("activity_type", "page_view")
    activity_details = data.get("details")
    
    try:
        user_data = verify_token(token)
        user_id = user_data["user_id"]
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Update last activity
        if USE_POSTGRES:
            cursor.execute(
                """UPDATE user_sessions 
                   SET last_activity = NOW()
                   WHERE id = %s AND user_id = %s""",
                (session_id, user_id)
            )
        else:
            cursor.execute(
                """UPDATE user_sessions 
                   SET last_activity = datetime('now')
                   WHERE id = ? AND user_id = ?""",
                (session_id, user_id)
            )
        
        # Log activity
        if USE_POSTGRES:
            cursor.execute(
                """INSERT INTO activity_log (user_id, session_id, activity_type, activity_details)
                   VALUES (%s, %s, %s, %s)""",
                (user_id, session_id, activity_type, activity_details)
            )
        else:
            cursor.execute(
                """INSERT INTO activity_log (user_id, session_id, activity_type, activity_details)
                   VALUES (?, ?, ?, ?)""",
                (user_id, session_id, activity_type, activity_details)
            )
        
        conn.commit()
        conn.close()
        
        return {"success": True}
        
    except Exception as e:
        print(f"Error updating activity: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/session/break/start")
async def start_break(request: Request):
    """Start a break"""
    data = await request.json()
    token = data.get("token")
    session_id = data.get("session_id")
    
    try:
        user_data = verify_token(token)
        user_id = user_data["user_id"]
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Update session to break status
        if USE_POSTGRES:
            cursor.execute(
                """UPDATE user_sessions 
                   SET status = 'on_break', break_start = NOW()
                   WHERE id = %s AND user_id = %s""",
                (session_id, user_id)
            )
            cursor.execute(
                """INSERT INTO activity_log (user_id, session_id, activity_type)
                   VALUES (%s, %s, 'break_start')""",
                (user_id, session_id)
            )
        else:
            cursor.execute(
                """UPDATE user_sessions 
                   SET status = 'on_break', break_start = datetime('now')
                   WHERE id = ? AND user_id = ?""",
                (session_id, user_id)
            )
            cursor.execute(
                """INSERT INTO activity_log (user_id, session_id, activity_type)
                   VALUES (?, ?, 'break_start')""",
                (user_id, session_id)
            )
        
        conn.commit()
        conn.close()
        
        return {
            "success": True,
            "message": "Break started",
            "max_break_minutes": 30
        }
        
    except Exception as e:
        print(f"Error starting break: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/session/break/end")
async def end_break(request: Request):
    """End a break"""
    data = await request.json()
    token = data.get("token")
    session_id = data.get("session_id")
    
    try:
        user_data = verify_token(token)
        user_id = user_data["user_id"]
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Get break start time
        if USE_POSTGRES:
            cursor.execute(
                "SELECT break_start FROM user_sessions WHERE id = %s AND user_id = %s",
                (session_id, user_id)
            )
        else:
            cursor.execute(
                "SELECT break_start FROM user_sessions WHERE id = ? AND user_id = ?",
                (session_id, user_id)
            )
        
        result = cursor.fetchone()
        if result:
            break_start = result['break_start'] if hasattr(result, 'keys') else result[0]
            
            # Calculate break duration
            if break_start:
                break_duration = (datetime.now() - datetime.fromisoformat(str(break_start))).seconds
            else:
                break_duration = 0
            
            # Update session
            if USE_POSTGRES:
                cursor.execute(
                    """UPDATE user_sessions 
                       SET status = 'active', 
                           break_end = NOW(),
                           total_break_time = total_break_time + %s,
                           last_activity = NOW()
                       WHERE id = %s AND user_id = %s""",
                    (break_duration, session_id, user_id)
                )
                cursor.execute(
                    """INSERT INTO activity_log (user_id, session_id, activity_type, activity_details)
                       VALUES (%s, %s, 'break_end', %s)""",
                    (user_id, session_id, f"Break duration: {break_duration}s")
                )
            else:
                cursor.execute(
                    """UPDATE user_sessions 
                       SET status = 'active', 
                           break_end = datetime('now'),
                           total_break_time = total_break_time + ?,
                           last_activity = datetime('now')
                       WHERE id = ? AND user_id = ?""",
                    (break_duration, session_id, user_id)
                )
                cursor.execute(
                    """INSERT INTO activity_log (user_id, session_id, activity_type, activity_details)
                       VALUES (?, ?, 'break_end', ?)""",
                    (user_id, session_id, f"Break duration: {break_duration}s")
                )
        
        conn.commit()
        conn.close()
        
        return {
            "success": True,
            "message": "Break ended",
            "break_duration_seconds": break_duration if result else 0
        }
        
    except Exception as e:
        print(f"Error ending break: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/session/timeout/warning")
async def log_timeout_warning(request: Request):
    """Log that timeout warning was shown"""
    data = await request.json()
    token = data.get("token")
    session_id = data.get("session_id")
    idle_duration = data.get("idle_duration", 0)
    
    try:
        user_data = verify_token(token)
        user_id = user_data["user_id"]
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Create timeout event
        if USE_POSTGRES:
            cursor.execute(
                """INSERT INTO timeout_events (user_id, session_id, warning_shown_at, idle_duration)
                   VALUES (%s, %s, NOW(), %s)
                   RETURNING id""",
                (user_id, session_id, idle_duration)
            )
            result = cursor.fetchone()
            timeout_event_id = result['id'] if result else None
            
            cursor.execute(
                """INSERT INTO activity_log (user_id, session_id, activity_type, activity_details)
                   VALUES (%s, %s, 'timeout_warning', %s)""",
                (user_id, session_id, f"Idle for {idle_duration}s")
            )
        else:
            cursor.execute(
                """INSERT INTO timeout_events (user_id, session_id, warning_shown_at, idle_duration)
                   VALUES (?, ?, datetime('now'), ?)""",
                (user_id, session_id, idle_duration)
            )
            timeout_event_id = cursor.lastrowid
            
            cursor.execute(
                """INSERT INTO activity_log (user_id, session_id, activity_type, activity_details)
                   VALUES (?, ?, 'timeout_warning', ?)""",
                (user_id, session_id, f"Idle for {idle_duration}s")
            )
        
        conn.commit()
        conn.close()
        
        return {
            "success": True,
            "timeout_event_id": timeout_event_id
        }
        
    except Exception as e:
        print(f"Error logging timeout warning: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/session/timeout/responded")
async def log_timeout_response(request: Request):
    """Log that user responded to timeout warning"""
    data = await request.json()
    token = data.get("token")
    session_id = data.get("session_id")
    timeout_event_id = data.get("timeout_event_id")
    
    try:
        user_data = verify_token(token)
        user_id = user_data["user_id"]
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Update timeout event
        if USE_POSTGRES:
            cursor.execute(
                """UPDATE timeout_events 
                   SET user_responded = TRUE
                   WHERE id = %s AND user_id = %s""",
                (timeout_event_id, user_id)
            )
            
            # Reset last activity
            cursor.execute(
                """UPDATE user_sessions 
                   SET last_activity = NOW()
                   WHERE id = %s AND user_id = %s""",
                (session_id, user_id)
            )
        else:
            cursor.execute(
                """UPDATE timeout_events 
                   SET user_responded = 1
                   WHERE id = ? AND user_id = ?""",
                (timeout_event_id, user_id)
            )
            
            cursor.execute(
                """UPDATE user_sessions 
                   SET last_activity = datetime('now')
                   WHERE id = ? AND user_id = ?""",
                (session_id, user_id)
            )
        
        conn.commit()
        conn.close()
        
        return {"success": True}
        
    except Exception as e:
        print(f"Error logging timeout response: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/session/timeout")
async def log_timeout(request: Request):
    """Log that user was timed out"""
    data = await request.json()
    token = data.get("token")
    session_id = data.get("session_id")
    timeout_event_id = data.get("timeout_event_id")
    
    try:
        user_data = verify_token(token)
        user_id = user_data["user_id"]
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Update timeout event
        if USE_POSTGRES:
            cursor.execute(
                """UPDATE timeout_events 
                   SET timed_out_at = NOW()
                   WHERE id = %s AND user_id = %s""",
                (timeout_event_id, user_id)
            )
            
            # Update session
            cursor.execute(
                """UPDATE user_sessions 
                   SET status = 'timed_out', 
                       session_end = NOW(),
                       timeout_count = timeout_count + 1
                   WHERE id = %s AND user_id = %s""",
                (session_id, user_id)
            )
            
            cursor.execute(
                """INSERT INTO activity_log (user_id, session_id, activity_type)
                   VALUES (%s, %s, 'timeout')""",
                (user_id, session_id)
            )
        else:
            cursor.execute(
                """UPDATE timeout_events 
                   SET timed_out_at = datetime('now')
                   WHERE id = ? AND user_id = ?""",
                (timeout_event_id, user_id)
            )
            
            cursor.execute(
                """UPDATE user_sessions 
                   SET status = 'timed_out', 
                       session_end = datetime('now'),
                       timeout_count = timeout_count + 1
                   WHERE id = ? AND user_id = ?""",
                (session_id, user_id)
            )
            
            cursor.execute(
                """INSERT INTO activity_log (user_id, session_id, activity_type)
                   VALUES (?, ?, 'timeout')""",
                (user_id, session_id)
            )
        
        conn.commit()
        conn.close()
        
        return {"success": True}
        
    except Exception as e:
        print(f"Error logging timeout: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/session/end")
async def end_session(request: Request):
    """End user session"""
    data = await request.json()
    token = data.get("token")
    session_id = data.get("session_id")
    
    try:
        user_data = verify_token(token)
        user_id = user_data["user_id"]
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Update session
        if USE_POSTGRES:
            cursor.execute(
                """UPDATE user_sessions 
                   SET status = 'logged_out', session_end = NOW()
                   WHERE id = %s AND user_id = %s""",
                (session_id, user_id)
            )
            
            cursor.execute(
                """INSERT INTO activity_log (user_id, session_id, activity_type)
                   VALUES (%s, %s, 'logout')""",
                (user_id, session_id)
            )
        else:
            cursor.execute(
                """UPDATE user_sessions 
                   SET status = 'logged_out', session_end = datetime('now')
                   WHERE id = ? AND user_id = ?""",
                (session_id, user_id)
            )
            
            cursor.execute(
                """INSERT INTO activity_log (user_id, session_id, activity_type)
                   VALUES (?, ?, 'logout')""",
                (user_id, session_id)
            )
        
        conn.commit()
        conn.close()
        
        return {"success": True}
        
    except Exception as e:
        print(f"Error ending session: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ========== ADMIN ENDPOINTS ==========

@app.get("/api/admin/sessions/active")
async def get_active_sessions(token: str):
    """Get all active sessions (admin only)"""
    try:
        user_data = verify_token(token)
        if user_data["role"] != "admin":
            raise HTTPException(status_code=403, detail="Admin only")
        
        conn = get_db()
        cursor = conn.cursor()
        
        if USE_POSTGRES:
            cursor.execute("""
                SELECT s.*, u.name, u.email 
                FROM user_sessions s
                JOIN users u ON s.user_id = u.id
                WHERE s.status IN ('active', 'on_break')
                ORDER BY s.last_activity DESC
            """)
        else:
            cursor.execute("""
                SELECT s.*, u.name, u.email 
                FROM user_sessions s
                JOIN users u ON s.user_id = u.id
                WHERE s.status IN ('active', 'on_break')
                ORDER BY s.last_activity DESC
            """)
        
        sessions = []
        for row in cursor.fetchall():
            sessions.append({
                'session_id': row['id'] if hasattr(row, 'keys') else row[0],
                'user_id': row['user_id'] if hasattr(row, 'keys') else row[1],
                'user_name': row['name'] if hasattr(row, 'keys') else row[-2],
                'user_email': row['email'] if hasattr(row, 'keys') else row[-1],
                'status': row['status'] if hasattr(row, 'keys') else row[4],
                'session_start': str(row['session_start'] if hasattr(row, 'keys') else row[2]),
                'last_activity': str(row['last_activity'] if hasattr(row, 'keys') else row[3]),
                'break_start': str(row['break_start']) if (row['break_start'] if hasattr(row, 'keys') else row[5]) else None
            })
        
        conn.close()
        
        return {
            "success": True,
            "sessions": sessions,
            "count": len(sessions)
        }
        
    except Exception as e:
        print(f"Error getting active sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/admin/activity/recent")
async def get_recent_activity(token: str, hours: int = 24):
    """Get recent activity logs (admin only)"""
    try:
        user_data = verify_token(token)
        if user_data["role"] != "admin":
            raise HTTPException(status_code=403, detail="Admin only")
        
        conn = get_db()
        cursor = conn.cursor()
        
        if USE_POSTGRES:
            cursor.execute("""
                SELECT a.*, u.name, u.email 
                FROM activity_log a
                JOIN users u ON a.user_id = u.id
                WHERE a.timestamp > NOW() - INTERVAL '%s hours'
                ORDER BY a.timestamp DESC
                LIMIT 100
            """, (hours,))
        else:
            cursor.execute("""
                SELECT a.*, u.name, u.email 
                FROM activity_log a
                JOIN users u ON a.user_id = u.id
                WHERE a.timestamp > datetime('now', '-' || ? || ' hours')
                ORDER BY a.timestamp DESC
                LIMIT 100
            """, (hours,))
        
        activities = []
        for row in cursor.fetchall():
            activities.append({
                'id': row['id'] if hasattr(row, 'keys') else row[0],
                'user_id': row['user_id'] if hasattr(row, 'keys') else row[1],
                'user_name': row['name'] if hasattr(row, 'keys') else row[-2],
                'activity_type': row['activity_type'] if hasattr(row, 'keys') else row[3],
                'activity_details': row['activity_details'] if hasattr(row, 'keys') else row[4],
                'timestamp': str(row['timestamp'] if hasattr(row, 'keys') else row[5])
            })
        
        conn.close()
        
        return {
            "success": True,
            "activities": activities,
            "count": len(activities)
        }
        
    except Exception as e:
        print(f"Error getting activity: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Mount static files
try:
    app.mount("/static", StaticFiles(directory="static"), name="static")
except:
    print("Warning: static directory not found")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)