# Achieve 365 Reading Rewards
# AI-Powered Adaptive Learning System

from fastapi import FastAPI, HTTPException, Depends, Request, BackgroundTasks, Header
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Dict, Any
import sqlite3
import psycopg2
import psycopg2.extras
import bcrypt
import jwt
from datetime import datetime, timedelta, timezone
import openai
import os
import json
from pathlib import Path
import random
import traceback
from openai import OpenAI
import resend
import secrets, hashlib
import requests

# Import our new utilities
from readability import analyze_readability, get_difficulty_for_user
from content_generator import ContentGenerator

# Initialize FastAPI
app = FastAPI(title="Achieve 365 - Phase 2")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
SECRET_KEY = os.getenv("SECRET_KEY", "achieve-365-reading-secret-key-change-in-production")
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

# Configure Resend
resend.api_key = os.getenv("RESEND_API_KEY")  # Add this to your .env file
FROM_EMAIL = os.getenv("FROM_EMAIL", "no-reply@4dgaming.games")
APP_BASE_URL = os.getenv("APP_BASE_URL", "https://ai-assessment-production-e027.up.railway.app")

# Store password reset tokens (in production, use database)
password_reset_tokens = {}

print(f"Using {'PostgreSQL' if USE_POSTGRES else 'SQLite'} database")
print(f"OpenAI API {'configured' if OPENAI_API_KEY else 'NOT configured'}")

# Add this near the top with your other configurations
SECRET_KEY = "your-secret-key-here"  # Use the same key you use for login tokens

def validate_token(token):
    """Validate JWT token and return user data"""
    if not token:
        return None
    
    try:
        # Decode the token
        payload = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
        user_id = payload.get('user_id')
        
        if not user_id:
            return None
        
        # Get user from database
        conn = get_db()
        cursor = conn.cursor()
        
        if USE_POSTGRES:
            cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        else:
            cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        
        user_row = cursor.fetchone()
        conn.close()
        
        if not user_row:
            return None
        
        # Return user dict
        if hasattr(user_row, 'keys'):
            return dict(user_row)
        else:
            # SQLite tuple format
            return {
                'id': user_row[0],
                'email': user_row[1],
                'full_name': user_row[3],
                'role': user_row[4]
            }
            
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
    except Exception as e:
        print(f"Error validating token: {e}")
        return None

# Pydantic models (existing + new)
class UserCreate(BaseModel):
    email: str
    password: str
    full_name: str
    age: Optional[int] = None
    age_band: Optional[str] = None
    grade_band: Optional[str] = None      # NEW: Student's grade level
    reading_level: Optional[str] = None   # NEW: Initial reading difficulty
        
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
    
class InviteAdminReq(BaseModel):
    email: EmailStr
    
class AcceptInviteReq(BaseModel):
    token: str = Field(..., min_length=10)
    password: str = Field(..., min_length=6)
    
class AdminInviteActionRequest(BaseModel):
    # optional note for auditing/logging if you want
    note: Optional[str] = None

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
        cursor = get_cursor(conn)
        
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
        
        # ADD YOUR NEW TABLE HERE:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reading_level_history (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                previous_level VARCHAR(50),
                new_level VARCHAR(50),
                score INTEGER,
                test_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create admin
        admin_hash = bcrypt.hashpw("admin123".encode('utf-8'), bcrypt.gensalt())
        try:
            cursor.execute(
                "INSERT INTO users (email, password_hash, full_name, role) VALUES (?, ?, ?, ?)",
                ("admin@mfs.org", admin_hash.decode('utf-8'), "Achieve 365 Administrator", "admin")
            )
        except sqlite3.IntegrityError:
            pass
    
    conn.commit()
    conn.close()

init_db()

# Helper functions
def get_db():
    if USE_POSTGRES:
        return psycopg2.connect(DATABASE)
    else:
        conn = sqlite3.connect(DATABASE, timeout=30.0, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        return conn

import psycopg2.extras

def get_cursor(conn):
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if USE_POSTGRES else conn.cursor()


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
    cursor = get_cursor(conn)
    if USE_POSTGRES:
        cursor.execute("UPDATE users SET last_active = NOW() WHERE id = %s", (user_id,))
    else:
        cursor.execute("UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()

ADMIN_EMAILS = {
    e.strip().lower()
    for e in os.getenv("ADMIN_EMAILS", "").split(",")
    if e.strip()
}

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

@app.get("/register", response_class=HTMLResponse)
async def serve_register():
    response = FileResponse("static/register.html")
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.get("/reset-password")
async def reset_password_page():
    """Serve the password reset page"""
    return FileResponse('static/reset-password.html')

@app.get("/admin-invite", include_in_schema=False)
def admin_invite_page():
    return FileResponse("static/admin-invite.html")

# ============================================
# AUTHENTICATION (Original)
# ============================================

ADMIN_INVITE_CODE = os.getenv("ADMIN_INVITE_CODE")  # set in Railway
# Optional: allowlist instead/in addition
ADMIN_EMAILS = set(
    e.strip().lower()
    for e in os.getenv("ADMIN_EMAILS", "").split(",")
    if e.strip()
)


@app.post("/api/register")
async def register(user: UserCreate):
    conn = get_db()
    cursor = get_cursor(conn)
 
    password_hash = bcrypt.hashpw(user.password.encode('utf-8'), bcrypt.gensalt())
 
    # ✅ Server decides role (email allowlist)
    email_lc = user.email.lower().strip()
    final_role = "admin" if (ADMIN_EMAILS and email_lc in ADMIN_EMAILS) else "student"
 
    try:
        if USE_POSTGRES:
            cursor.execute(
                """INSERT INTO users (email, password_hash, full_name, role, age, age_band, grade_band, reading_level)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                (user.email, password_hash.decode('utf-8'), user.full_name, final_role,
                 user.age, user.age_band, user.grade_band, user.reading_level)
            )
            result = cursor.fetchone()
            user_id = result["id"] if isinstance(result, dict) else result[0]
        else:
            cursor.execute(
                """INSERT INTO users (email, password_hash, full_name, role, age, age_band, grade_band, reading_level) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (user.email, password_hash.decode('utf-8'), user.full_name, final_role,
                 user.age, user.age_band, user.grade_band, user.reading_level)
            )
            user_id = cursor.lastrowid
 
        conn.commit()
        
        initialize_new_user(user_id)
 
        # ✅ token uses final_role
        token = create_token(user_id, final_role)
 
        return {
            "success": True,
            "token": token,
            "user": {
                "id": user_id,
                "email": user.email,
                "full_name": user.full_name,
                "role": final_role,
                "age": user.age,                    # ADD THIS
                "age_band": user.age_band,
                "grade_band": user.grade_band,      # ADD THIS
                "reading_level": user.reading_level # ADD THIS
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

def get_current_user(authorization: str = Header(None)) -> dict:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization")
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid Authorization format")
    return verify_token(parts[1])

def require_admin(user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

@app.post("/api/login")
async def login(credentials: UserLogin):
    conn = get_db()
    cursor = get_cursor(conn)
    
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
    
    initialize_new_user(user['id'])
    
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
# PASSWORD RESET
# ============================================
    
@app.post("/api/auth/forgot-password")
async def forgot_password(request: dict):
    """Send password reset email"""
    email = request.get('email')
    
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")
    
    conn = get_db()
    cursor = get_cursor(conn)
    
    try:
        # Check if user exists
        if USE_POSTGRES:
            cursor.execute("SELECT id, full_name FROM users WHERE email = %s", (email,))
        else:
            cursor.execute("SELECT id, full_name FROM users WHERE email = ?", (email,))
        
        result = cursor.fetchone()
        
        # Always return success (security best practice - don't reveal if email exists)
        if not result:
            return {
                "success": True,
                "message": "If that email exists, a reset link has been sent."
            }
        
        user_id = result['id']
        user_name = result['full_name']
        
        # Generate reset token
        reset_token = secrets.token_urlsafe(32)
        
        # Store token with expiration (1 hour)
        password_reset_tokens[reset_token] = {
            'user_id': user_id,
            'email': email,
            'expires': datetime.now() + timedelta(hours=1)
        }
        
        # Create reset link need to change to clients url
        reset_link = f"https://ai-assessment-production-e027.up.railway.app/reset-password?token={reset_token}"
        
        # Send email via Resend
        try:
            resend.Emails.send({
                "from": "Achieve 365 <noreply@4dgaming.games>",  # Update with your domain
                "to": email,
                "subject": "Reset Your Achieve 365 Password",
                "html": f"""
                    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                        <h2 style="color: #2A398A;">Reset Your Password</h2>
                        <p>Hi {user_name},</p>
                        <p>We received a request to reset your password for your Achieve 365 account.</p>
                        <p>Click the button below to reset your password:</p>
                        <div style="text-align: center; margin: 30px 0;">
                            <a href="{reset_link}" 
                               style="background: #2A398A; 
                                      color: white; 
                                      padding: 12px 30px; 
                                      text-decoration: none; 
                                      border-radius: 5px;
                                      display: inline-block;">
                                Reset Password
                            </a>
                        </div>
                        <p>Or copy and paste this link into your browser:</p>
                        <p style="word-break: break-all; color: #666;">{reset_link}</p>
                        <p style="color: #999; font-size: 14px;">
                            This link will expire in 1 hour. If you didn't request this, you can safely ignore this email.
                        </p>
                        <hr style="border: none; border-top: 1px solid #ddd; margin: 30px 0;">
                        <p style="color: #999; font-size: 12px;">
                            Achieve 365 - Empowering Adult Literacy
                        </p>
                    </div>
                """
            })
            
            print(f"✅ Password reset email sent to {email}")
            
        except Exception as email_error:
            print(f"❌ Email error: {email_error}")
            raise HTTPException(status_code=500, detail="Failed to send reset email")
        
        return {
            "success": True,
            "message": "If that email exists, a reset link has been sent."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Forgot password error: {e}")
        raise HTTPException(status_code=500, detail="Failed to process request")
    finally:
        conn.close()

@app.post("/api/auth/reset-password")
async def reset_password(request: dict):
    """Reset password using token"""
    token = request.get('token')
    new_password = request.get('password')
    
    if not token or not new_password:
        raise HTTPException(status_code=400, detail="Token and password are required")
    
    # Validate token
    if token not in password_reset_tokens:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    
    token_data = password_reset_tokens[token]
    
    # Check expiration
    if datetime.now() > token_data['expires']:
        del password_reset_tokens[token]
        raise HTTPException(status_code=400, detail="Reset token has expired")
    
    # Update password
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        password_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
        
        if USE_POSTGRES:
            cursor.execute(
                "UPDATE users SET password_hash = %s WHERE id = %s",
                (password_hash.decode('utf-8'), token_data['user_id'])
            )
        else:
            cursor.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (password_hash.decode('utf-8'), token_data['user_id'])
            )
        
        conn.commit()
        
        # Delete used token
        del password_reset_tokens[token]
        
        return {
            "success": True,
            "message": "Password reset successfully"
        }
        
    except Exception as e:
        conn.rollback()
        print(f"Password reset error: {e}")
        raise HTTPException(status_code=500, detail="Failed to reset password")
    finally:
        conn.close()
        
# ============================================
# 1. ADD THIS HELPER FUNCTION
# ============================================

def initialize_new_user(user_id):
    """
    Initialize all required database records for a new user
    Prevents HTTP 500 errors when new users access the dashboard
    """
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        print(f"Initializing user data for user_id: {user_id}")
        
        # Initialize user_streaks
        if USE_POSTGRES:
            cursor.execute("""
                INSERT INTO user_streaks (user_id, current_streak, longest_streak, last_activity_date)
                VALUES (%s, 0, 0, CURRENT_DATE)
                ON CONFLICT (user_id) DO NOTHING
            """, (user_id,))
        else:
            cursor.execute("""
                INSERT OR IGNORE INTO user_streaks (user_id, current_streak, longest_streak, last_activity_date)
                VALUES (?, 0, 0, date('now'))
            """, (user_id,))
        
        # Check if you have user_stats table - if so, initialize it
        try:
            if USE_POSTGRES:
                cursor.execute("""
                    INSERT INTO user_stats (user_id, total_lessons, total_points, average_score)
                    VALUES (%s, 0, 0, 0)
                    ON CONFLICT (user_id) DO NOTHING
                """, (user_id,))
            else:
                cursor.execute("""
                    INSERT OR IGNORE INTO user_stats (user_id, total_lessons, total_points, average_score)
                    VALUES (?, 0, 0, 0)
                """, (user_id,))
        except:
            pass  # Table might not exist, that's OK
        
        conn.commit()
        print(f"✓ User data initialized successfully for user_id: {user_id}")
        
    except Exception as e:
        print(f"Error initializing user {user_id}: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
    finally:
        conn.close()

# ============================================
# ASSESSMENT ENDPOINTS (Phase 1 + Phase 2)
# ============================================

def get_age_appropriate_interest_questions(age, grade_band):
    """
    Generate age-appropriate interest questions based on student's age and grade
    """
    
    # Ages 3-7 (Pre-K to 2nd Grade)
    if age <= 7 or grade_band in ['pre-k', 'kindergarten', '1st', '2nd']:
        return [
            {
                "id": 1,
                "question": "What do you like to play with?",
                "category": "play",
                "options": ["Toys", "Games", "Drawing", "Outside", "Other"]
            },
            {
                "id": 2,
                "question": "What animals do you like?",
                "category": "animals",
                "options": ["Dogs", "Cats", "Birds", "Fish", "Other"]
            },
            {
                "id": 3,
                "question": "What colors do you like best?",
                "category": "colors",
                "options": ["Blue", "Red", "Green", "Purple", "Other"]
            },
            {
                "id": 4,
                "question": "What do you like to eat?",
                "category": "food",
                "options": ["Pizza", "Fruit", "Chicken", "Vegetables", "Other"]
            },
            {
                "id": 5,
                "question": "Where do you like to go?",
                "category": "places",
                "options": ["Park", "Library", "Store", "Friend's house", "Other"]
            },
            {
                "id": 6,
                "question": "What do you like to watch?",
                "category": "shows",
                "options": ["Cartoons", "Animals", "Music", "Sports", "Other"]
            },
            {
                "id": 7,
                "question": "Who do you like to play with?",
                "category": "social",
                "options": ["Friends", "Family", "By myself", "Pets", "Other"]
            },
            {
                "id": 8,
                "question": "What makes you happy?",
                "category": "emotions",
                "options": ["Playing", "Learning", "Helping", "Making things", "Other"]
            }
        ]
    
    # Ages 8-11 (3rd to 5th Grade)
    elif age <= 11 or grade_band in ['3rd', '4th', '5th', 'elementary']:
        return [
            {
                "id": 1,
                "question": "What do you like to do after school?",
                "category": "activities",
                "options": ["Play sports", "Play video games", "Read", "Draw or make art", "Other"]
            },
            {
                "id": 2,
                "question": "What type of stories do you like?",
                "category": "stories",
                "options": ["Adventure", "Funny stories", "Animal stories", "Real-life stories", "Other"]
            },
            {
                "id": 3,
                "question": "What's your favorite subject in school?",
                "category": "school",
                "options": ["Math", "Reading", "Science", "Art/Music", "Other"]
            },
            {
                "id": 4,
                "question": "What do you want to learn about?",
                "category": "topics",
                "options": ["Animals", "Space", "Sports", "Technology", "Other"]
            },
            {
                "id": 5,
                "question": "What do you like to do with friends?",
                "category": "social",
                "options": ["Play games", "Talk", "Make things", "Play sports", "Other"]
            },
            {
                "id": 6,
                "question": "What music do you like?",
                "category": "music",
                "options": ["Hip-hop/Rap", "R&B", "Pop", "Gospel", "Other"]
            },
            {
                "id": 7,
                "question": "What would you like to be when you grow up?",
                "category": "career",
                "options": ["Doctor/Nurse", "Teacher", "Athlete", "Artist/Musician", "Other"]
            },
            {
                "id": 8,
                "question": "What do you like to watch or follow?",
                "category": "media",
                "options": ["Sports", "Music videos", "Gaming", "Funny videos", "Other"]
            },
            {
                "id": 9,
                "question": "What makes a story interesting to you?",
                "category": "engagement",
                "options": ["Action", "Humor", "Learning something", "Relatable characters", "Other"]
            },
            {
                "id": 10,
                "question": "What do you like to create or build?",
                "category": "creativity",
                "options": ["Art", "Music", "Stories", "Games", "Other"]
            }
        ]
    
    # Ages 12-14 (6th to 8th Grade / Middle School)
    elif age <= 14 or grade_band in ['6th', '7th', '8th', 'middle']:
        return [
            {
                "id": 1,
                "question": "What content do you most enjoy?",
                "category": "content",
                "options": ["Sports", "Music", "Technology", "Social issues", "Other"]
            },
            {
                "id": 2,
                "question": "What type of stories interest you?",
                "category": "stories",
                "options": ["Action/Adventure", "Mystery", "Real-life experiences", "Fantasy/Sci-fi", "Other"]
            },
            {
                "id": 3,
                "question": "What do you spend most of your free time doing?",
                "category": "activities",
                "options": ["Gaming", "Sports", "Social media", "Creating content", "Other"]
            },
            {
                "id": 4,
                "question": "What career fields interest you?",
                "category": "career",
                "options": ["Medicine/Healthcare", "Technology/Engineering", "Arts/Entertainment", "Business/Entrepreneurship", "Other"]
            },
            {
                "id": 5,
                "question": "What music genre do you listen to most?",
                "category": "music",
                "options": ["Hip-hop/Rap", "R&B/Soul", "Pop", "Gospel/Christian", "Other"]
            },
            {
                "id": 6,
                "question": "What topics do you want to learn more about?",
                "category": "topics",
                "options": ["Science/Tech", "History/Culture", "Social justice", "Business/Money", "Other"]
            },
            {
                "id": 7,
                "question": "What type of reading do you prefer?",
                "category": "reading",
                "options": ["Short articles", "Long stories", "Social media posts", "News/Current events", "Other"]
            },
            {
                "id": 8,
                "question": "What do you follow on social media?",
                "category": "social_media",
                "options": ["Sports/Athletes", "Musicians/Artists", "Influencers", "News/Politics", "Other"]
            },
            {
                "id": 9,
                "question": "What makes you want to read something?",
                "category": "motivation",
                "options": ["Relatable to my life", "Teaches me something", "Entertaining", "Helps with school", "Other"]
            },
            {
                "id": 10,
                "question": "What challenges interest you?",
                "category": "challenges",
                "options": ["Community issues", "Personal growth", "Academic success", "Creative projects", "Other"]
            }
        ]
    
    # Ages 15-18 (High School)
    elif age <= 18 or grade_band in ['9th', '10th', '11th', '12th', 'high']:
        return [
            {
                "id": 1,
                "question": "What career path are you most interested in?",
                "category": "career",
                "options": ["Healthcare", "Technology/Engineering", "Business/Entrepreneurship", "Creative Arts", "Other"]
            },
            {
                "id": 2,
                "question": "What topics are you passionate about?",
                "category": "passion",
                "options": ["Social justice", "Technology/Innovation", "Arts/Culture", "Business/Economics", "Other"]
            },
            {
                "id": 3,
                "question": "What type of content do you engage with most?",
                "category": "content",
                "options": ["News/Current events", "Entertainment", "Educational content", "Career development", "Other"]
            },
            {
                "id": 4,
                "question": "What reading format do you prefer?",
                "category": "format",
                "options": ["Articles (500-1000 words)", "Long-form essays", "Social media threads", "Research/Academic", "Other"]
            },
            {
                "id": 5,
                "question": "What motivates you to read?",
                "category": "motivation",
                "options": ["Career preparation", "Personal development", "Entertainment", "Social awareness", "Other"]
            },
            {
                "id": 6,
                "question": "What skills do you want to develop?",
                "category": "skills",
                "options": ["Critical thinking", "Communication", "Technical skills", "Leadership", "Other"]
            },
            {
                "id": 7,
                "question": "What music genre resonates with you?",
                "category": "music",
                "options": ["Hip-hop/Rap", "R&B/Soul", "Gospel", "Pop/Alternative", "Other"]
            },
            {
                "id": 8,
                "question": "What issues matter most to you?",
                "category": "issues",
                "options": ["Education access", "Economic opportunity", "Criminal justice reform", "Environmental justice", "Other"]
            },
            {
                "id": 9,
                "question": "After high school, what are you planning?",
                "category": "future",
                "options": ["4-year college", "Community college", "Trade school", "Work/Entrepreneurship", "Other"]
            },
            {
                "id": 10,
                "question": "What type of stories resonate with you?",
                "category": "stories",
                "options": ["Coming-of-age narratives", "Social commentary", "Success stories", "Historical perspectives", "Other"]
            }
        ]
    
    # Ages 19+ (Adult / College / Professional)
    else:
        return [
            {
                "id": 1,
                "question": "What are your primary professional interests?",
                "category": "career",
                "options": ["Career advancement", "Entrepreneurship", "Industry knowledge", "Continuing education", "Other"]
            },
            {
                "id": 2,
                "question": "What type of reading supports your goals?",
                "category": "reading",
                "options": ["Professional development", "Industry news", "Academic research", "Personal growth", "Other"]
            },
            {
                "id": 3,
                "question": "What topics are most relevant to your work?",
                "category": "work",
                "options": ["Technology/Innovation", "Business strategy", "Leadership", "Social impact", "Other"]
            },
            {
                "id": 4,
                "question": "What content format works best for you?",
                "category": "format",
                "options": ["Articles (1000+ words)", "Case studies", "Research papers", "Industry reports", "Other"]
            },
            {
                "id": 5,
                "question": "What drives your learning?",
                "category": "motivation",
                "options": ["Career growth", "Skill development", "Community impact", "Personal fulfillment", "Other"]
            },
            {
                "id": 6,
                "question": "What professional skills are you developing?",
                "category": "skills",
                "options": ["Leadership", "Technical expertise", "Communication", "Strategic thinking", "Other"]
            },
            {
                "id": 7,
                "question": "What issues are you focused on?",
                "category": "issues",
                "options": ["Economic empowerment", "Educational equity", "Community development", "Social justice", "Other"]
            },
            {
                "id": 8,
                "question": "What content helps you most?",
                "category": "content",
                "options": ["How-to guides", "Best practices", "Case studies", "Research findings", "Other"]
            },
            {
                "id": 9,
                "question": "What are your long-term goals?",
                "category": "goals",
                "options": ["Career success", "Business ownership", "Community leadership", "Lifelong learning", "Other"]
            },
            {
                "id": 10,
                "question": "What perspectives interest you?",
                "category": "perspective",
                "options": ["Innovation/Future trends", "Historical context", "Community voices", "Expert analysis", "Other"]
            }
        ]

def generate_interest_assessment(age=None, grade_band=None):
    """Generate age-appropriate interest assessment questions"""
    
    # If age/grade not provided, use generic questions
    if not age or not grade_band:
        age = 12  # Default to middle school
        grade_band = 'middle'
    
    print(f"Generating interest assessment for age={age}, grade={grade_band}")
    
    # Get age-appropriate questions
    questions = get_age_appropriate_interest_questions(age, grade_band)
    
    print(f"✓ Generated {len(questions)} age-appropriate questions")
    return questions

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
    reading_level = None  # Default
    
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
async def get_interest_assessment(request: Request, token: str = None):
    """Get age-appropriate interest assessment questions for the user"""
    try:
        # Try to get token from header first, then query param
        if not token:
            auth_header = request.headers.get('Authorization')
            if auth_header and auth_header.startswith('Bearer '):
                token = auth_header.replace('Bearer ', '')
        
        if not token:
            raise HTTPException(status_code=401, detail="Missing authorization token")
        
        user_data = verify_token(token)
        user_id = user_data["user_id"]
        
        conn = get_db()
        
        # Use dict cursor
        if USE_POSTGRES:
            import psycopg2.extras
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        else:
            import sqlite3
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
        
        # Fetch user's age and grade
        if USE_POSTGRES:
            cursor.execute("""
                SELECT age, grade_band 
                FROM users 
                WHERE id = %s
            """, (user_id,))
        else:
            cursor.execute("""
                SELECT age, grade_band 
                FROM users 
                WHERE id = ?
            """, (user_id,))
        
        user = cursor.fetchone()
        conn.close()
        
        if user:
            age = user['age'] or 7
            grade_band = user['grade_band'] or 'elementary'
            print(f"📚 Interest assessment for user {user_id}: age={age}, grade={grade_band}")
        else:
            # Default if not found
            age = 7
            grade_band = 'elementary'
            print(f"⚠️ User {user_id} not found, using defaults: age={age}, grade={grade_band}")
        
        # Generate age-appropriate questions
        questions = generate_interest_assessment(age, grade_band)
        print(f"✓ Generated {len(questions)} questions for {age}yo in {grade_band}")
        
        return {"questions": questions}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting interest assessment: {e}")
        import traceback
        traceback.print_exc()
        # Return age-appropriate default questions
        questions = generate_interest_assessment(7, 'elementary')
        return {"questions": questions}
    
@app.get("/api/user/assessment-status")
async def get_assessment_status(request: Request):
    """Check if user has completed their initial assessment"""
    try:
        # Get token from Authorization header
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            raise HTTPException(status_code=401, detail="Missing authorization token")
        
        token = auth_header.replace('Bearer ', '')
        user_data = verify_token(token)
        user_id = user_data["user_id"]
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Check if user has interest_tags (completed interest assessment)
        if USE_POSTGRES:
            cursor.execute("""
                SELECT interest_tags, total_passages_read
                FROM users 
                WHERE id = %s
            """, (user_id,))
        else:
            cursor.execute("""
                SELECT interest_tags, total_passages_read
                FROM users 
                WHERE id = ?
            """, (user_id,))
        
        user = cursor.fetchone()
        conn.close()
        
        if not user:
            return {"assessment_complete": False}
        
        interest_tags = user['interest_tags'] if hasattr(user, 'keys') else user[0]
        total_read = user['total_passages_read'] if hasattr(user, 'keys') else user[1]
        
        # Assessment is complete if they have interests (took interest assessment)
        assessment_complete = bool(interest_tags and interest_tags != '[]')
        
        return {
            "assessment_complete": assessment_complete,
            "has_interests": bool(interest_tags),
            "passages_read": total_read or 0
        }
        
    except Exception as e:
        print(f"Error checking assessment status: {e}")
        return {"assessment_complete": False}
    
@app.get("/api/me")
async def me(user=Depends(get_current_user)):
    return {"user_id": user["user_id"], "role": user["role"]}

# ============================================
# ADMIN ENDPOINTS
# ============================================
    
@app.get("/api/admin/reading-level-distribution")
async def get_reading_level_distribution(admin=Depends(require_admin)):
    """Get distribution of students across reading levels"""
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        if USE_POSTGRES:
            cursor.execute("""
                SELECT 
                    COALESCE(reading_level, 'Not Assessed') as level,
                    COUNT(*) as count
                FROM users 
                WHERE role = 'student'
                GROUP BY reading_level
                ORDER BY 
                    CASE reading_level
                        WHEN 'beginner' THEN 1
                        WHEN 'intermediate' THEN 2
                        WHEN 'advanced' THEN 3
                        ELSE 4
                    END
            """)
        else:
            cursor.execute("""
                SELECT 
                    COALESCE(reading_level, 'Not Assessed') as level,
                    COUNT(*) as count
                FROM users 
                WHERE role = 'student'
                GROUP BY reading_level
                ORDER BY 
                    CASE reading_level
                        WHEN 'beginner' THEN 1
                        WHEN 'intermediate' THEN 2
                        WHEN 'advanced' THEN 3
                        ELSE 4
                    END
            """)
        
        rows = cursor.fetchall()
        distribution = []
        
        for row in rows:
            distribution.append({
                'level': (row['level'] if hasattr(row, 'keys') else row[0]).title(),
                'count': row['count'] if hasattr(row, 'keys') else row[1]
            })
        
        conn.close()
        
        return {
            "success": True,
            "distribution": distribution
        }
        
    except Exception as e:
        conn.close()
        print(f"Error getting reading level distribution: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/interest-topics")
async def get_interest_topics(admin=Depends(require_admin)):
    """Get breakdown of popular interest topics"""
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        if USE_POSTGRES:
            cursor.execute("""
                SELECT interest_tags 
                FROM users 
                WHERE role = 'student' 
                AND interest_tags IS NOT NULL 
                AND interest_tags != '[]'
            """)
        else:
            cursor.execute("""
                SELECT interest_tags 
                FROM users 
                WHERE role = 'student' 
                AND interest_tags IS NOT NULL 
                AND interest_tags != '[]'
            """)
        
        rows = cursor.fetchall()
        
        # Count all interests
        interest_counts = {}
        
        for row in rows:
            tags_str = row['interest_tags'] if hasattr(row, 'keys') else row[0]
            try:
                tags = json.loads(tags_str) if isinstance(tags_str, str) else tags_str
                if isinstance(tags, list):
                    for tag in tags:
                        tag = tag.strip().lower()
                        if tag:
                            interest_counts[tag] = interest_counts.get(tag, 0) + 1
            except:
                pass
        
        conn.close()
        
        # Sort by count and get top 10
        sorted_interests = sorted(interest_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        
        topics = [
            {
                'topic': topic.title(),
                'count': count
            }
            for topic, count in sorted_interests
        ]
        
        # If no data, provide sample data
        if not topics:
            topics = [
                {'topic': 'Science', 'count': 0},
                {'topic': 'Technology', 'count': 0},
                {'topic': 'History', 'count': 0},
                {'topic': 'Arts', 'count': 0},
                {'topic': 'Sports', 'count': 0}
            ]
        
        return {
            "success": True,
            "topics": topics
        }
        
    except Exception as e:
        conn.close()
        print(f"Error getting interest topics: {e}")
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
    
# Add these endpoints to app.py after /api/assessment/submit

@app.post("/api/reading-level/update")
async def update_reading_level(request: Request):
    """Update user's reading level and save history"""
    try:
        data = await request.json()
        token = data.get('token')
        new_level = data.get('level')
        score = data.get('score', 0)
        
        user_data = verify_token(token)
        user_id = user_data["user_id"]
        
        conn = get_db()
        
        if USE_POSTGRES:
            import psycopg2.extras
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        else:
            import sqlite3
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
        
        # Get current level
        if USE_POSTGRES:
            cursor.execute("SELECT reading_level FROM users WHERE id = %s", (user_id,))
        else:
            cursor.execute("SELECT reading_level FROM users WHERE id = ?", (user_id,))
        
        user = cursor.fetchone()
        previous_level = user['reading_level'] if user else None
        
        # Save to history
        if USE_POSTGRES:
            cursor.execute("""
                INSERT INTO reading_level_history 
                (user_id, previous_level, new_level, score)
                VALUES (%s, %s, %s, %s)
            """, (user_id, previous_level, new_level, score))
            
            # Update user's current level
            cursor.execute("""
                UPDATE users 
                SET reading_level = %s, level_estimate = %s
                WHERE id = %s
            """, (new_level, new_level, user_id))
        else:
            cursor.execute("""
                INSERT INTO reading_level_history 
                (user_id, previous_level, new_level, score)
                VALUES (?, ?, ?, ?)
            """, (user_id, previous_level, new_level, score))
            
            cursor.execute("""
                UPDATE users 
                SET reading_level = ?, level_estimate = ?
                WHERE id = ?
            """, (new_level, new_level, user_id))
        
        conn.commit()
        conn.close()
        
        return {
            "success": True,
            "previous_level": previous_level,
            "new_level": new_level,
            "message": f"Reading level updated from {previous_level} to {new_level}"
        }
        
    except Exception as e:
        print(f"Error updating reading level: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/reading-level/history")
async def get_reading_level_history(token: str):
    """Get user's reading level history"""
    try:
        user_data = verify_token(token)
        user_id = user_data["user_id"]
        
        conn = get_db()
        
        if USE_POSTGRES:
            import psycopg2.extras
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute("""
                SELECT previous_level, new_level, score, test_date
                FROM reading_level_history
                WHERE user_id = %s
                ORDER BY test_date DESC
                LIMIT 10
            """, (user_id,))
        else:
            import sqlite3
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT previous_level, new_level, score, test_date
                FROM reading_level_history
                WHERE user_id = ?
                ORDER BY test_date DESC
                LIMIT 10
            """, (user_id,))
        
        history = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return {"success": True, "history": history}
        
    except Exception as e:
        print(f"Error getting reading level history: {e}")
        return {"success": False, "history": []}
    
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
    cursor = get_cursor(conn)
    
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
    """Get a reading passage matched to user's level, interests, age, and grade"""
    user_data = verify_token(token)
    user_id = user_data["user_id"]
    
    conn = get_db()
    
    # FIX: Get dict cursor for both databases
    if USE_POSTGRES:
        import psycopg2.extras
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    else:
        import sqlite3
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
    
    # Get user profile
    if USE_POSTGRES:
        cursor.execute("""
            SELECT id, level_estimate, interest_tags, total_passages_read,
                   age, grade_band, reading_level, age_band
            FROM users WHERE id = %s
        """, (user_id,))
    else:
        cursor.execute("""
            SELECT id, level_estimate, interest_tags, total_passages_read,
                   age, grade_band, reading_level, age_band
            FROM users WHERE id = ?
        """, (user_id,))
    
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")
    
    # Now user is a dict for both PostgreSQL and SQLite
    level_estimate = user['level_estimate'] or user['reading_level'] or 'intermediate'
    interest_tags = json.loads(user['interest_tags'] or '[]')
    total_read = user['total_passages_read'] or 0
    age = user['age'] or 10
    grade_band = user['grade_band'] or 'elementary'
    age_band = user['age_band'] or 'child'
    
    # For first passage, make it easier (quick win strategy)
    if total_read == 0:
        challenge = "easier"
        target_words = get_target_words(grade_band, "easier")
    else:
        target_words = get_target_words(grade_band, challenge)
    
    if not content_generator:
        raise HTTPException(status_code=503, detail="Content generation not available. Please configure OpenAI API key.")
    
    # NEW: Smart topic selection based on age and interests
    topic = select_age_appropriate_topic(interest_tags, age, grade_band)
    
    # NEW: Better difficulty mapping based on grade and challenge
    difficulty = calculate_difficulty(grade_band, level_estimate, challenge)
    
    print(f"Generating passage: user_id={user_id}, age={age}, grade={grade_band}, topic={topic}, difficulty={difficulty}, words={target_words}")
    
    try:
        # Generate passage with enhanced context
        passage_data = content_generator.generate_passage(
           topic=topic,
           difficulty_level=difficulty,
           word_count_min=target_words - 25,  # ✅ Correct parameter name
           word_count_max=target_words + 25,  # ✅ Correct parameter name
           user_interests=interest_tags,
           age=age,
           grade_band=grade_band
        )
        print(f"✓ Passage generated: {passage_data['title']}")
        
        # Save to database
        if USE_POSTGRES:
            print(f"Saving passage to database...")
            cursor.execute(
                """INSERT INTO passages 
                (title, content, source, topic_tags, word_count, readability_score, flesch_ease, 
                    difficulty_level, estimated_minutes, approved, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                (passage_data['title'], 
                passage_data['content'], 
                passage_data.get('source', 'AI Generated'),
                json.dumps(passage_data.get('topic_tags', [])),
                passage_data.get('word_count', 100),
                passage_data.get('readability_score'),
                passage_data.get('flesch_ease'),
                passage_data.get('difficulty_level', difficulty),
                passage_data.get('estimated_minutes', 2),
                True, 1)
            )
            result = cursor.fetchone()
            passage_id = result['id']
            print(f"✓ Passage saved with ID: {passage_id}")
        else:
            cursor.execute(
                """INSERT INTO passages 
                (title, content, source, topic_tags, word_count, readability_score, flesch_ease,
                    difficulty_level, estimated_minutes, approved, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (passage_data['title'], 
                passage_data['content'], 
                passage_data.get('source', 'AI Generated'),
                json.dumps(passage_data.get('topic_tags', [])),
                passage_data.get('word_count', 100),
                passage_data.get('readability_score'),
                passage_data.get('flesch_ease'),
                passage_data.get('difficulty_level', difficulty),
                passage_data.get('estimated_minutes', 2),
                True, 1)
            )
            passage_id = cursor.lastrowid
        
        # Generate comprehension questions
        questions = content_generator.generate_comprehension_questions(
            passage_text=passage_data['content'],
            passage_title=passage_data['title'],
            num_questions=3
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
            print(f"✓ Passage saved with ID: {passage_id}")
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
            "title": passage_data.get('title', 'Reading Passage'),
            "content": passage_data.get('content', ''),
            "word_count": passage_data.get('word_count', len(passage_data.get('content', '').split())),
            "estimated_minutes": passage_data.get('estimated_minutes', 2),
            "difficulty_level": passage_data.get('difficulty_level', difficulty),
            "vocabulary": passage_data.get('vocabulary_words', []),
            "questions": questions,
            "is_first_passage": total_read == 0,
            "personalized_for": {
                "age": age,
                "grade": grade_band,
                "interests": interest_tags,
                "topic": topic
            }
        }
        
    except Exception as e:
        conn.close()
        import traceback
        print(f"❌ Error generating passage: {e}")
        print(f"Traceback: {traceback.format_exc()}")  # ✅ Full error details
        raise HTTPException(status_code=500, detail=f"Failed to generate passage: {str(e)}")


# NEW HELPER FUNCTIONS - Add these above the endpoint

def get_target_words(grade_band, challenge="appropriate"):
    """
    Get appropriate word count based on grade level and challenge
    """
    word_count_map = {
        'pre-k': {'easier': 50, 'appropriate': 75, 'challenging': 100},
        'kindergarten': {'easier': 75, 'appropriate': 100, 'challenging': 125},
        '1st': {'easier': 100, 'appropriate': 125, 'challenging': 150},
        '2nd': {'easier': 125, 'appropriate': 150, 'challenging': 175},
        '3rd': {'easier': 150, 'appropriate': 175, 'challenging': 200},
        '4th': {'easier': 175, 'appropriate': 200, 'challenging': 250},
        '5th': {'easier': 200, 'appropriate': 250, 'challenging': 300},
        'elementary': {'easier': 150, 'appropriate': 200, 'challenging': 250},
        '6th': {'easier': 250, 'appropriate': 300, 'challenging': 350},
        '7th': {'easier': 275, 'appropriate': 325, 'challenging': 375},
        '8th': {'easier': 300, 'appropriate': 350, 'challenging': 400},
        'middle': {'easier': 275, 'appropriate': 325, 'challenging': 375},
        '9th': {'easier': 350, 'appropriate': 400, 'challenging': 450},
        '10th': {'easier': 375, 'appropriate': 425, 'challenging': 475},
        '11th': {'easier': 400, 'appropriate': 450, 'challenging': 500},
        '12th': {'easier': 425, 'appropriate': 475, 'challenging': 550},
        'high': {'easier': 375, 'appropriate': 425, 'challenging': 500},
        'adult': {'easier': 350, 'appropriate': 450, 'challenging': 600},
        'college': {'easier': 400, 'appropriate': 500, 'challenging': 650},
        'professional': {'easier': 450, 'appropriate': 550, 'challenging': 700}
    }
    
    counts = word_count_map.get(grade_band, word_count_map['elementary'])
    return counts.get(challenge, counts['appropriate'])


def select_age_appropriate_topic(interests, age, grade_band):
    """
    Select topic from interests that's appropriate for age/grade
    """
    # Age-appropriate topic filters
    age_appropriate_topics = {
        'pre-k': ['animals', 'colors', 'shapes', 'family', 'toys', 'food', 'nature'],
        'kindergarten': ['animals', 'family', 'seasons', 'friends', 'pets', 'garden'],
        'elementary': ['animals', 'sports', 'space', 'dinosaurs', 'ocean', 'video games', 
                      'art', 'music', 'nature', 'adventure', 'friendship'],
        'middle': ['sports', 'science', 'technology', 'music', 'history', 'adventure', 
                  'mystery', 'fantasy', 'environment', 'social media'],
        'high': ['science', 'technology', 'history', 'literature', 'psychology', 
                'current events', 'philosophy', 'career', 'relationships'],
        'adult': ['technology', 'business', 'health', 'finance', 'politics', 
                 'philosophy', 'career development', 'relationships', 'wellness'],
        'college': ['technology', 'business', 'psychology', 'sociology', 'economics',
                   'research', 'career', 'innovation'],
        'professional': ['business', 'leadership', 'technology', 'innovation', 
                        'industry trends', 'professional development']
    }
    
    # Simplify grade_band to main categories
    if grade_band in ['pre-k', 'kindergarten', '1st', '2nd', '3rd', '4th', '5th']:
        category = 'elementary'
    elif grade_band in ['6th', '7th', '8th']:
        category = 'middle'
    elif grade_band in ['9th', '10th', '11th', '12th']:
        category = 'high'
    else:
        category = grade_band if grade_band in age_appropriate_topics else 'elementary'
    
    appropriate = age_appropriate_topics.get(category, age_appropriate_topics['elementary'])
    
    # Find matching interests
    if interests:
        # Check if any interest matches age-appropriate topics
        matching = [i for i in interests if any(i.lower() in topic.lower() for topic in appropriate)]
        if matching:
            return random.choice(matching)
        # Otherwise use first interest (student chose it!)
        return interests[0]
    
    # No interests? Pick age-appropriate default
    return random.choice(appropriate)


def calculate_difficulty(grade_band, reading_level, challenge):
    """
    Calculate appropriate difficulty based on grade, reading level, and challenge
    """
    # Base difficulty from grade
    grade_difficulty_map = {
        'pre-k': 'beginner',
        'kindergarten': 'beginner',
        '1st': 'beginner',
        '2nd': 'beginner',
        '3rd': 'beginner',
        '4th': 'intermediate',
        '5th': 'intermediate',
        'elementary': 'intermediate',
        '6th': 'intermediate',
        '7th': 'intermediate',
        '8th': 'advanced',
        'middle': 'intermediate',
        '9th': 'advanced',
        '10th': 'advanced',
        '11th': 'advanced',
        '12th': 'advanced',
        'high': 'advanced',
        'adult': 'advanced',
        'college': 'advanced',
        'professional': 'advanced'
    }
    
    base_difficulty = grade_difficulty_map.get(grade_band, 'intermediate')
    
    # Adjust based on challenge parameter
    difficulty_levels = ['beginner', 'intermediate', 'advanced']
    
    try:
        base_index = difficulty_levels.index(base_difficulty)
    except ValueError:
        base_index = 1  # Default to intermediate
    
    if challenge == "easier":
        final_index = max(0, base_index - 1)
    elif challenge == "challenging":
        final_index = min(2, base_index + 1)
    else:  # appropriate
        final_index = base_index
    
    # Override with user's actual reading_level if available
    if reading_level and reading_level in difficulty_levels:
        user_index = difficulty_levels.index(reading_level)
        # Average the grade-based and user-based difficulty
        final_index = (final_index + user_index) // 2
    
    return difficulty_levels[final_index]
    
import os
import base64
from datetime import datetime
from fastapi import File, UploadFile

# ============================================
# PROFILE PHOTO ENDPOINTS
# ============================================

@app.post("/api/profile/upload-photo")
async def upload_profile_photo(request: Request):
    """Upload custom profile photo"""
    try:
        # Get multipart form data
        form = await request.form()
        token = form.get('token')
        photo = form.get('photo')
        
        if not token:
            raise HTTPException(status_code=400, detail="Token required")
        
        if not photo:
            raise HTTPException(status_code=400, detail="Photo required")
        
        # Verify token
        user_data = verify_token(token)
        user_id = user_data["user_id"]
        
        # Read photo data
        photo_data = await photo.read()
        
        # Validate file size (max 5MB)
        if len(photo_data) > 5 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File too large (max 5MB)")
        
        # Validate file type
        content_type = photo.content_type
        if not content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="Only image files allowed")
        
        # Convert to base64 for storage
        base64_image = base64.b64encode(photo_data).decode('utf-8')
        photo_url = f"data:{content_type};base64,{base64_image}"
        
        # Save to database
        conn = get_db()
        cursor = conn.cursor()
        
        if USE_POSTGRES:
            cursor.execute(
                """UPDATE users SET profile_photo = %s WHERE id = %s""",
                (photo_url, user_id)
            )
        else:
            cursor.execute(
                """UPDATE users SET profile_photo = ? WHERE id = ?""",
                (photo_url, user_id)
            )
        
        conn.commit()
        conn.close()
        
        return {
            "success": True,
            "message": "Profile photo uploaded successfully",
            "photo_url": photo_url
        }
        
    except Exception as e:
        print(f"Error uploading profile photo: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/profile/set-avatar")
async def set_avatar(request: Request):
    """Set avatar from preset options"""
    try:
        data = await request.json()
        token = data.get('token')
        avatar = data.get('avatar')
        
        if not token or not avatar:
            raise HTTPException(status_code=400, detail="Token and avatar required")
        
        # Verify token
        user_data = verify_token(token)
        user_id = user_data["user_id"]
        
        # Save to database
        conn = get_db()
        cursor = conn.cursor()
        
        if USE_POSTGRES:
            cursor.execute(
                """UPDATE users SET profile_photo = %s WHERE id = %s""",
                (avatar, user_id)
            )
        else:
            cursor.execute(
                """UPDATE users SET profile_photo = ? WHERE id = ?""",
                (avatar, user_id)
            )
        
        conn.commit()
        conn.close()
        
        return {
            "success": True,
            "message": "Avatar set successfully",
            "avatar": avatar
        }
        
    except Exception as e:
        print(f"Error setting avatar: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/profile/photo")
async def get_profile_photo(token: str):
    """Get user's current profile photo"""
    try:
        # Verify token
        user_data = verify_token(token)
        user_id = user_data["user_id"]
        
        # Get from database
        conn = get_db()
        cursor = conn.cursor()
        
        if USE_POSTGRES:
            cursor.execute(
                """SELECT profile_photo FROM users WHERE id = %s""",
                (user_id,)
            )
        else:
            cursor.execute(
                """SELECT profile_photo FROM users WHERE id = ?""",
                (user_id,)
            )
        
        result = cursor.fetchone()
        conn.close()
        
        if not result:
            raise HTTPException(status_code=404, detail="User not found")
        
        photo = result['profile_photo'] if hasattr(result, 'keys') else result[0]
        
        return {
            "success": True,
            "photo_url": photo
        }
        
    except Exception as e:
        print(f"Error getting profile photo: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

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
# GAMIFICATION BACKEND & ENDPOINTS
# ============================================================

@app.get('/api/gamification/data')
async def get_gamification_data(token: str):
    """Get all gamification data for user"""
    
    if not token:
        raise HTTPException(status_code=401, detail='No token provided')
    
    user = validate_token(token)
    if not user:
        raise HTTPException(status_code=401, detail='Invalid token')
    
    user_id = user['id']
    conn = get_db()
    cursor = get_cursor(conn)
    
    try:
        # Get points and level
        if USE_POSTGRES:
            cursor.execute(
                "SELECT points, total_earned, level FROM user_points WHERE user_id = %s",
                (user_id,)
            )
        else:
            cursor.execute(
                "SELECT points, total_earned, level FROM user_points WHERE user_id = ?",
                (user_id,)
            )
        
        points_row = cursor.fetchone()
        if points_row:
            current_points = points_row['points'] if hasattr(points_row, 'keys') else points_row[0]
            total_earned = points_row['total_earned'] if hasattr(points_row, 'keys') else points_row[1]
            level = points_row['level'] if hasattr(points_row, 'keys') else points_row[2]
        else:
            current_points = 0
            total_earned = 0
            level = 1
        
        # Get earned badges
        if USE_POSTGRES:
            cursor.execute(
                """SELECT badge_type, badge_name, description, icon, earned_at 
                   FROM user_badges 
                   WHERE user_id = %s 
                   ORDER BY earned_at DESC""",
                (user_id,)
            )
        else:
            cursor.execute(
                """SELECT badge_type, badge_name, description, icon, earned_at 
                   FROM user_badges 
                   WHERE user_id = ? 
                   ORDER BY earned_at DESC""",
                (user_id,)
            )
        
        badge_rows = cursor.fetchall()
        badges = []
        for row in badge_rows:
            badges.append({
                'badge_type': row['badge_type'] if hasattr(row, 'keys') else row[0],
                'name': row['badge_name'] if hasattr(row, 'keys') else row[1],
                'description': row['description'] if hasattr(row, 'keys') else row[2],
                'icon': row['icon'] if hasattr(row, 'keys') else row[3],
                'earned_at': row['earned_at'] if hasattr(row, 'keys') else row[4]
            })
        
        # Get weekly goals (current week only) - removed goal_name and icon
        week_start = datetime.now() - timedelta(days=datetime.now().weekday())
        week_start = week_start.date()
        
        if USE_POSTGRES:
            cursor.execute(
                """SELECT id, goal_type, target_value, current_value, 
                          completed, points_reward
                   FROM weekly_goals 
                   WHERE user_id = %s AND week_start = %s
                   ORDER BY created_at DESC""",
                (user_id, week_start)
            )
        else:
            cursor.execute(
                """SELECT id, goal_type, target_value, current_value, 
                          completed, points_reward
                   FROM weekly_goals 
                   WHERE user_id = ? AND week_start = ?
                   ORDER BY created_at DESC""",
                (user_id, week_start)
            )
        
        goal_rows = cursor.fetchall()
        weekly_goals = []
        for row in goal_rows:
            goal_type = row['goal_type'] if hasattr(row, 'keys') else row[1]
            goal_config = WEEKLY_GOAL_TYPES.get(goal_type, {})
            
            weekly_goals.append({
                'id': row['id'] if hasattr(row, 'keys') else row[0],
                'goal_type': goal_type,
                'goal_name': goal_config.get('name', goal_type),  # Get from config
                'target_value': row['target_value'] if hasattr(row, 'keys') else row[2],
                'current_value': row['current_value'] if hasattr(row, 'keys') else row[3],
                'completed': row['completed'] if hasattr(row, 'keys') else row[4],
                'points_reward': row['points_reward'] if hasattr(row, 'keys') else row[5],
                'icon': goal_config.get('icon', '🎯')  # Get from config
            })
        
        # Get available goal types (ones not yet created this week)
        existing_types = [g['goal_type'] for g in weekly_goals]
        available_types = []
        
        for goal_type, config in WEEKLY_GOAL_TYPES.items():
            if goal_type not in existing_types:
                available_types.append({
                    'type': goal_type,
                    'name': config['name'],
                    'description': config['description'],
                    'default_target': config['default_target'],
                    'points_reward': config['points_reward'],
                    'icon': config['icon']
                })
        
        conn.close()
        
        return {
            'success': True,
            'points': current_points,
            'total_earned': total_earned,
            'level': level,
            'badges': badges,
            'badges_count': len(badges),
            'weekly_goals': weekly_goals,
            'available_goal_types': available_types
        }
        
    except Exception as e:
        conn.close()
        print(f"Error getting gamification data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post('/api/gamification/goals/create')
async def create_weekly_goal(request: Request):
    """Create a new weekly goal"""
    data = await request.json()
    token = data.get('token')
    goal_type = data.get('goal_type')
    custom_target = data.get('custom_target')
    
    print(f"Creating goal - Type: {goal_type}, Custom Target: {custom_target}, Type: {type(custom_target)}")
    
    if not token:
        raise HTTPException(status_code=401, detail='No token provided')
    
    if not goal_type:
        raise HTTPException(status_code=400, detail='No goal type provided')
    
    user = validate_token(token)
    if not user:
        raise HTTPException(status_code=401, detail='Invalid token')
    
    user_id = user['id']
    
    # Validate goal type
    if goal_type not in WEEKLY_GOAL_TYPES:
        raise HTTPException(status_code=400, detail='Invalid goal type')
    
    goal_config = WEEKLY_GOAL_TYPES[goal_type]
    
    # Convert custom_target to int if provided
    if custom_target:
        try:
            target = int(custom_target)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail='Invalid target value')
    else:
        target = goal_config['default_target']
    
    # Validate target
    if target < 1:
        raise HTTPException(status_code=400, detail='Target must be at least 1')
    
    print(f"Final target value: {target}, user_id: {user_id}")
    
    conn = get_db()
    cursor = get_cursor(conn)
    
    try:
        week_start = datetime.now() - timedelta(days=datetime.now().weekday())
        week_start = week_start.date()
        week_end = week_start + timedelta(days=6)
        
        # Check if goal already exists
        if USE_POSTGRES:
            cursor.execute(
                "SELECT id FROM weekly_goals WHERE user_id = %s AND week_start = %s AND goal_type = %s",
                (user_id, week_start, goal_type)
            )
        else:
            cursor.execute(
                "SELECT id FROM weekly_goals WHERE user_id = ? AND week_start = ? AND goal_type = ?",
                (user_id, week_start, goal_type)
            )
        
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail='Goal already exists for this week')
        
        print(f"Inserting goal - user_id: {user_id}, week_start: {week_start}, week_end: {week_end}, goal_type: {goal_type}, target: {target}, points: {goal_config['points_reward']}")
        
        # Create new goal with week_end
        if USE_POSTGRES:
            sql = """INSERT INTO weekly_goals 
                   (user_id, week_start, week_end, goal_type, target_value, current_value, 
                    completed, points_reward)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                   RETURNING id"""
            params = (user_id, week_start, week_end, goal_type, target, 0, False, goal_config['points_reward'])
            print(f"PostgreSQL Query: {sql}")
            print(f"Parameters: {params}")
            cursor.execute(sql, params)
            result = cursor.fetchone()
            goal_id = result['id'] if hasattr(result, 'keys') else result[0]
        else:
            sql = """INSERT INTO weekly_goals 
                   (user_id, week_start, week_end, goal_type, target_value, current_value, 
                    completed, points_reward)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)"""
            params = (user_id, week_start, week_end, goal_type, target, 0, 0, goal_config['points_reward'])
            print(f"SQLite Query: {sql}")
            print(f"Parameters: {params}")
            cursor.execute(sql, params)
            goal_id = cursor.lastrowid
        
        conn.commit()
        
        return {
            'success': True,
            'goal_id': goal_id,
            'goal_type': goal_type,
            'message': f'Weekly goal "{goal_config["name"]}" created successfully!'
        }
        
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        print(f"Error creating weekly goal: {e}")
        print(f"Error type: {type(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        conn.close()

# Points configuration
POINTS_CONFIG = {
    'lesson_complete': 10,
    'perfect_score': 50,
    'high_score': 25,  # 80%+
    'good_score': 15,  # 60-79%
    'daily_streak': 5,
    'weekly_goal': 100,
    'badge_earned': 20,
    'reading_time_goal': 75,
    'accuracy_goal': 125
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
    'consistency_king': {'name': 'Consistency King', 'description': '7-day streak', 'icon': '👑', 'points': 100},
    'accuracy_master': {'name': 'Accuracy Master', 'description': 'Achieve 90%+ average score', 'icon': '🎖️', 'points': 150},
    'reading_warrior': {'name': 'Reading Warrior', 'description': 'Read for 60 minutes in one week', 'icon': '⚔️', 'points': 80}
}

# Weekly goal types
WEEKLY_GOAL_TYPES = {
    'lessons_completed': {
        'name': 'Complete Lessons',
        'description': 'Complete a target number of lessons this week',
        'default_target': 5,
        'points_reward': 100,
        'icon': '📖'
    },
    'reading_time': {
        'name': 'Reading Time',
        'description': 'Read for a total number of minutes this week',
        'default_target': 30,
        'points_reward': 75,
        'icon': '⏱️'
    },
    'average_score': {
        'name': 'Average Score',
        'description': 'Maintain an average score above target',
        'default_target': 80,
        'points_reward': 125,
        'icon': '🎯'
    },
    'perfect_scores': {
        'name': 'Perfect Scores',
        'description': 'Achieve a number of perfect scores this week',
        'default_target': 3,
        'points_reward': 150,
        'icon': '💯'
    },
    'daily_streak': {
        'name': 'Daily Streak',
        'description': 'Complete lessons on X different days',
        'default_target': 5,
        'points_reward': 100,
        'icon': '🔥'
    }
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
    """Award badge to user - Fixed version"""
    print(f"🎖️ Attempting to award badge '{badge_type}' to user {user_id}")
    
    # Check if already has badge first
    if has_badge(user_id, badge_type):
        print(f"⚠️ User {user_id} already has badge '{badge_type}'")
        return False
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        print(f"💾 Inserting badge into database: {badge_type}, {badge_name}")
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
        print(f"✅ Badge '{badge_type}' inserted successfully")
        
        # Award points for badge (avoiding circular call)
        points = BADGES[badge_type]['points']
        result = award_points(user_id, points, f'Earned badge: {badge_name}', 'badge')
        print(f"💰 Awarded {points} points for badge")
        
        return {'badge_awarded': True, 'points_awarded': points, 'level_up': result.get('level_up', False)}
    except Exception as e:
        conn.rollback()
        conn.close()
        print(f"❌ Error awarding badge: {e}")
        traceback.print_exc()
        return False

def check_and_award_badges(user_id):
    """Check and award new badges - Enhanced version"""
    print(f"🎯 Checking badges for user {user_id}")
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
        
        result = cursor.fetchone()
        lesson_count = result['count'] if hasattr(result, 'keys') else result[0]
        print(f"📊 User has completed {lesson_count} lessons")
        
        # First lesson badge
        if lesson_count >= 1:
            has_first = has_badge(user_id, 'first_lesson')
            print(f"🏅 First lesson badge check: lesson_count={lesson_count}, has_badge={has_first}")
            if not has_first:
                badge = BADGES['first_lesson']
                print(f"🎁 Awarding first lesson badge: {badge}")
                result = award_badge(user_id, 'first_lesson', badge['name'], badge['description'], badge['icon'])
                print(f"✅ Award result: {result}")
                if result:
                    new_badges.append({'badge': badge, 'result': result})
            else:
                print(f"⚠️ User already has first_lesson badge")
        else:
            print(f"⚠️ User doesn't have enough lessons yet: {lesson_count} < 1")
        
        # Bookworm badge (50 lessons)
        if lesson_count >= 50 and not has_badge(user_id, 'bookworm'):
            badge = BADGES['bookworm']
            result = award_badge(user_id, 'bookworm', badge['name'], badge['description'], badge['icon'])
            if result:
                new_badges.append({'badge': badge, 'result': result})
        
        # Perfect streak check (last 3 lessons)
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
                result = award_badge(user_id, 'perfect_streak_3', badge['name'], badge['description'], badge['icon'])
                if result:
                    new_badges.append({'badge': badge, 'result': result})
        
        # Check lessons this week for Speed Reader badge
        from datetime import datetime, timedelta
        week_start = datetime.now() - timedelta(days=datetime.now().weekday())
        
        if USE_POSTGRES:
            cursor.execute(
                """SELECT COUNT(*) FROM session_logs 
                   WHERE user_id = %s AND completion_status = 'completed' 
                   AND completed_at >= %s""",
                (user_id, week_start)
            )
        else:
            cursor.execute(
                """SELECT COUNT(*) FROM session_logs 
                   WHERE user_id = ? AND completion_status = 'completed' 
                   AND completed_at >= ?""",
                (user_id, week_start)
            )
        
        result = cursor.fetchone()
        lessons_this_week = result['count'] if hasattr(result, 'keys') else result[0]
        
        if lessons_this_week >= 10 and not has_badge(user_id, 'speed_reader'):
            badge = BADGES['speed_reader']
            result = award_badge(user_id, 'speed_reader', badge['name'], badge['description'], badge['icon'])
            if result:
                new_badges.append({'badge': badge, 'result': result})
        
        # Time-based badges
        current_hour = datetime.now().hour
        
        if current_hour < 9 and not has_badge(user_id, 'early_bird'):
            badge = BADGES['early_bird']
            result = award_badge(user_id, 'early_bird', badge['name'], badge['description'], badge['icon'])
            if result:
                new_badges.append({'badge': badge, 'result': result})
        
        if current_hour >= 21 and not has_badge(user_id, 'night_owl'):
            badge = BADGES['night_owl']
            result = award_badge(user_id, 'night_owl', badge['name'], badge['description'], badge['icon'])
            if result:
                new_badges.append({'badge': badge, 'result': result})
        
        # Accuracy Master badge (90%+ average)
        if USE_POSTGRES:
            cursor.execute(
                """SELECT AVG(comprehension_score) FROM session_logs 
                   WHERE user_id = %s AND completion_status = 'completed'""",
                (user_id,)
            )
        else:
            cursor.execute(
                """SELECT AVG(comprehension_score) FROM session_logs 
                   WHERE user_id = ? AND completion_status = 'completed'""",
                (user_id,)
            )
        
        result = cursor.fetchone()
        avg_score = result['avg'] if hasattr(result, 'keys') else result[0]
        
        if avg_score and avg_score >= 90 and lesson_count >= 10 and not has_badge(user_id, 'accuracy_master'):
            badge = BADGES['accuracy_master']
            result = award_badge(user_id, 'accuracy_master', badge['name'], badge['description'], badge['icon'])
            if result:
                new_badges.append({'badge': badge, 'result': result})
        
        # Check 7-day streak for Consistency King
        if USE_POSTGRES:
            cursor.execute(
                """SELECT DISTINCT DATE(completed_at) FROM session_logs 
                   WHERE user_id = %s AND completion_status = 'completed'
                   ORDER BY DATE(completed_at) DESC LIMIT 7""",
                (user_id,)
            )
        else:
            cursor.execute(
                """SELECT DISTINCT DATE(completed_at) FROM session_logs 
                   WHERE user_id = ? AND completion_status = 'completed'
                   ORDER BY DATE(completed_at) DESC LIMIT 7""",
                (user_id,)
            )
        
        dates = [row[0] for row in cursor.fetchall()]
        
        # Check if dates are consecutive
        if len(dates) >= 7:
            is_streak = True
            for i in range(len(dates) - 1):
                date1 = datetime.strptime(str(dates[i]), '%Y-%m-%d').date() if isinstance(dates[i], str) else dates[i]
                date2 = datetime.strptime(str(dates[i+1]), '%Y-%m-%d').date() if isinstance(dates[i+1], str) else dates[i+1]
                if (date1 - date2).days != 1:
                    is_streak = False
                    break
            
            if is_streak and not has_badge(user_id, 'consistency_king'):
                badge = BADGES['consistency_king']
                result = award_badge(user_id, 'consistency_king', badge['name'], badge['description'], badge['icon'])
                if result:
                    new_badges.append({'badge': badge, 'result': result})
        
        conn.close()
        return new_badges
        
    except Exception as e:
        conn.close()
        print(f"❌ Error checking badges: {e}")
        import traceback
        traceback.print_exc()
        return []


def update_weekly_goals(user_id, session_data=None):
    """Update progress on all active weekly goals"""
    print(f"📈 Updating weekly goals for user {user_id}")
    conn = get_db()
    cursor = conn.cursor()
    goals_completed = []
    
    try:
        from datetime import datetime, timedelta
        week_start = datetime.now() - timedelta(days=datetime.now().weekday())
        week_start = week_start.date()
        print(f"📅 Week start: {week_start}")
        
        # Get all active goals for current week
        if USE_POSTGRES:
            cursor.execute(
                "SELECT * FROM weekly_goals WHERE user_id = %s AND week_start = %s AND completed = FALSE",
                (user_id, week_start)
            )
        else:
            cursor.execute(
                "SELECT * FROM weekly_goals WHERE user_id = ? AND week_start = ? AND completed = 0",
                (user_id, week_start)
            )
        
        goals = cursor.fetchall()
        print(f"🎯 Found {len(goals)} active goals")
        
        for goal in goals:
            goal_id = goal['id'] if hasattr(goal, 'keys') else goal[0]
            goal_type = goal['goal_type'] if hasattr(goal, 'keys') else goal[3]
            target = goal['target_value'] if hasattr(goal, 'keys') else goal[4]
            points_reward = goal['points_reward'] if hasattr(goal, 'keys') else goal[7]
            
            print(f"   📊 Processing goal: {goal_type} (target: {target})")
            
            # Calculate current progress based on goal type
            current_value = calculate_goal_progress(user_id, goal_type, week_start, cursor)
            print(f"   ✅ Current progress: {current_value}/{target}")
            
            # Update goal progress
            if current_value >= target:
                # Goal completed!
                if USE_POSTGRES:
                    cursor.execute(
                        "UPDATE weekly_goals SET current_value = %s, completed = TRUE, completed_at = NOW() WHERE id = %s",
                        (current_value, goal_id)
                    )
                else:
                    cursor.execute(
                        "UPDATE weekly_goals SET current_value = ?, completed = 1, completed_at = datetime('now') WHERE id = ?",
                        (current_value, goal_id)
                    )
                conn.commit()
                
                # Award points
                award_points(user_id, points_reward, f'{WEEKLY_GOAL_TYPES[goal_type]["name"]} goal completed', 'goal')
                goals_completed.append(goal_type)
            else:
                # Just update progress
                if USE_POSTGRES:
                    cursor.execute("UPDATE weekly_goals SET current_value = %s WHERE id = %s", (current_value, goal_id))
                else:
                    cursor.execute("UPDATE weekly_goals SET current_value = ? WHERE id = ?", (current_value, goal_id))
                conn.commit()
        
        conn.close()
        return {'goals_completed': goals_completed}
        
    except Exception as e:
        conn.rollback()
        conn.close()
        print(f"Error updating weekly goals: {e}")
        return {'error': str(e)}

def calculate_goal_progress(user_id, goal_type, week_start, cursor):
    """Calculate current progress for a specific goal type"""
    print(f"      🔍 Calculating progress for {goal_type}")
    from datetime import datetime, timedelta
    
    week_end = week_start + timedelta(days=7)
    
    if goal_type == 'lessons_completed':
        if USE_POSTGRES:
            cursor.execute(
                """SELECT COUNT(*) FROM session_logs 
                   WHERE user_id = %s AND completion_status = 'completed' 
                   AND completed_at >= %s AND completed_at < %s""",
                (user_id, week_start, week_end)
            )
        else:
            cursor.execute(
                """SELECT COUNT(*) FROM session_logs 
                   WHERE user_id = ? AND completion_status = 'completed' 
                   AND completed_at >= ? AND completed_at < ?""",
                (user_id, week_start, week_end)
            )
        result = cursor.fetchone()
        count = result['count'] if hasattr(result, 'keys') else result[0]
        print(f"         → lessons_completed: {count}")
        return count
    
    elif goal_type == 'reading_time':
        if USE_POSTGRES:
            cursor.execute(
                """SELECT SUM(EXTRACT(EPOCH FROM (completed_at - started_at))/60) 
                   FROM session_logs 
                   WHERE user_id = %s AND completion_status = 'completed' 
                   AND completed_at >= %s AND completed_at < %s""",
                (user_id, week_start, week_end)
            )
        else:
            cursor.execute(
                """SELECT SUM((julianday(completed_at) - julianday(started_at)) * 24 * 60) 
                   FROM session_logs 
                   WHERE user_id = ? AND completion_status = 'completed' 
                   AND completed_at >= ? AND completed_at < ?""",
                (user_id, week_start, week_end)
            )
        row = cursor.fetchone()
        result = row['sum'] if hasattr(row, 'keys') else row[0]
        minutes = int(result) if result else 0
        print(f"         → reading_time: {minutes} minutes")
        return minutes
    
    elif goal_type == 'average_score':
        if USE_POSTGRES:
            cursor.execute(
                """SELECT AVG(comprehension_score) FROM session_logs 
                   WHERE user_id = %s AND completion_status = 'completed' 
                   AND completed_at >= %s AND completed_at < %s""",
                (user_id, week_start, week_end)
            )
        else:
            cursor.execute(
                """SELECT AVG(comprehension_score) FROM session_logs 
                   WHERE user_id = ? AND completion_status = 'completed' 
                   AND completed_at >= ? AND completed_at < ?""",
                (user_id, week_start, week_end)
            )
        row = cursor.fetchone()
        result = row['avg'] if hasattr(row, 'keys') else row[0]
        avg = int(result) if result else 0
        print(f"         → average_score: {avg}")
        return avg
    
    elif goal_type == 'perfect_scores':
        if USE_POSTGRES:
            cursor.execute(
                """SELECT COUNT(*) FROM session_logs 
                   WHERE user_id = %s AND completion_status = 'completed' 
                   AND comprehension_score = 100
                   AND completed_at >= %s AND completed_at < %s""",
                (user_id, week_start, week_end)
            )
        else:
            cursor.execute(
                """SELECT COUNT(*) FROM session_logs 
                   WHERE user_id = ? AND completion_status = 'completed' 
                   AND comprehension_score = 100
                   AND completed_at >= ? AND completed_at < ?""",
                (user_id, week_start, week_end)
            )
        result = cursor.fetchone()
        count = result['count'] if hasattr(result, 'keys') else result[0]
        print(f"         → perfect_scores: {count}")
        return count
    
    elif goal_type == 'daily_streak':
        # Count distinct days with completed lessons this week
        if USE_POSTGRES:
            cursor.execute(
                """SELECT COUNT(DISTINCT DATE(completed_at)) FROM session_logs 
                   WHERE user_id = %s AND completion_status = 'completed'
                   AND completed_at >= %s AND completed_at < %s""",
                (user_id, week_start, week_end)
            )
        else:
            cursor.execute(
                """SELECT COUNT(DISTINCT DATE(completed_at)) FROM session_logs 
                   WHERE user_id = ? AND completion_status = 'completed'
                   AND completed_at >= ? AND completed_at < ?""",
                (user_id, week_start, week_end)
            )
        
        result = cursor.fetchone()
        days = result['count'] if hasattr(result, 'keys') else result[0]
        print(f"         → daily_streak: {days} days")
        return days
    
    print(f"         → Unknown goal type: {goal_type}, returning 0")
    return 0

def get_available_goal_types():
    """Get list of available weekly goal types"""
    return WEEKLY_GOAL_TYPES

def get_user_weekly_goals(user_id):
    """Get all weekly goals for user"""
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        from datetime import datetime, timedelta
        week_start = datetime.now() - timedelta(days=datetime.now().weekday())
        week_start = week_start.date()
        
        if USE_POSTGRES:
            cursor.execute(
                "SELECT * FROM weekly_goals WHERE user_id = %s AND week_start = %s ORDER BY created_at",
                (user_id, week_start)
            )
        else:
            cursor.execute(
                "SELECT * FROM weekly_goals WHERE user_id = ? AND week_start = ? ORDER BY created_at",
                (user_id, week_start)
            )
        
        goals = cursor.fetchall()
        conn.close()
        
        return [dict(goal) if hasattr(goal, 'keys') else 
                {'id': goal[0], 'goal_type': goal[3], 'target_value': goal[4], 
                 'current_value': goal[5], 'completed': goal[6]} 
                for goal in goals]
        
    except Exception as e:
        conn.close()
        print(f"Error getting weekly goals: {e}")
        return []
    
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
        cursor = get_cursor(conn)
        
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
    

# DUPLICATE ENDPOINT REMOVED - Using the one at line 5605 instead

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
async def get_enhanced_analytics(admin=Depends(require_admin)):
    """Enhanced analytics for admin dashboard"""
    
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
        
        # ========== GET USER INFO WITH STREAK ==========
        if USE_POSTGRES:
            cursor.execute(
                """SELECT u.id, u.full_name, u.email, u.reading_level, 
                          COALESCE(us.current_streak, 0) as current_streak
                   FROM users u
                   LEFT JOIN user_streaks us ON u.id = us.user_id
                   WHERE u.id = %s""",
                (user_id,)
            )
        else:
            cursor.execute(
                """SELECT u.id, u.full_name, u.email, u.reading_level, 
                          COALESCE(us.current_streak, 0) as current_streak
                   FROM users u
                   LEFT JOIN user_streaks us ON u.id = us.user_id
                   WHERE u.id = ?""",
                (user_id,)
            )
        
        user_row = cursor.fetchone()
        
        if not user_row:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Parse user data
        if hasattr(user_row, 'keys'):
            user_info = {
                'id': user_row['id'],
                'full_name': user_row['full_name'],
                'email': user_row['email'],
                'reading_level': user_row['reading_level'],
                'current_streak': user_row['current_streak']
            }
        else:
            user_info = {
                'id': user_row[0],
                'full_name': user_row[1],
                'email': user_row[2],
                'reading_level': user_row[3],
                'current_streak': user_row[4]
            }
        # ============================================
        
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
            
        # Calculate streak
        streak = calculate_streak(user_id, conn)
        
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
        
        # Handle both dict-like and tuple
        if hasattr(stats, 'keys'):
            total_lessons = stats['total_lessons'] or 0
            avg_score = stats['avg_score']
            total_time = stats['total_time'] or 0
            last_activity = stats['last_activity']
        else:
            total_lessons = stats[0] or 0
            avg_score = stats[1]
            total_time = stats[2] or 0
            last_activity = stats[3]
        
        # Round average score
        avg_score_rounded = round(avg_score, 1) if avg_score else 0
        total_time_minutes = round(total_time / 60, 1)
        
        conn.close()
        
        # ========== UPDATE RETURN TO INCLUDE USER ==========
        return {
            "success": True,
            "user": user_info,  # ← ADD THIS LINE!
            "sessions": sessions,
            "stats": {
                "total_lessons": total_lessons,
                "average_score": avg_score_rounded,
                "total_time_minutes": total_time_minutes,
                "last_activity": last_activity,
                "reading_level": user_info['reading_level'],  # ← ADD THIS
                "streak": streak  # ← ADD THIS
            }
        }
        # ===================================================
        
    except Exception as e:
        print(f"Error getting progress: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    
@app.get("/api/student/weekly-goals")
async def get_weekly_goals(token: str):
    """Get student's weekly goals"""
    try:
        user_data = verify_token(token)
        user_id = user_data["user_id"]
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Check if weekly_goals table exists
        try:
            if USE_POSTGRES:
                cursor.execute(
                    """SELECT goal_type, target_value, current_value, week_start, week_end
                       FROM weekly_goals 
                       WHERE user_id = %s 
                       AND week_start <= CURRENT_DATE 
                       AND week_end >= CURRENT_DATE""",
                    (user_id,)
                )
            else:
                cursor.execute(
                    """SELECT goal_type, target_value, current_value, week_start, week_end
                       FROM weekly_goals 
                       WHERE user_id = ? 
                       AND week_start <= date('now') 
                       AND week_end >= date('now')""",
                    (user_id,)
                )
            
            goals = []
            for row in cursor.fetchall():
                goal_type = row['goal_type'] if hasattr(row, 'keys') else row[0]
                target = row['target_value'] if hasattr(row, 'keys') else row[1]
                current = row['current_value'] if hasattr(row, 'keys') else row[2]
                
                # Map goal types to display info
                goal_info = {
                    'lessons': {'name': 'Complete Lessons', 'icon': '📚'},
                    'reading_time': {'name': 'Reading Time (min)', 'icon': '⏱️'},
                    'score': {'name': 'Average Score', 'icon': '⭐'},
                }
                
                info = goal_info.get(goal_type, {'name': goal_type.title(), 'icon': '🎯'})
                
                goals.append({
                    'name': info['name'],
                    'icon': info['icon'],
                    'current': current or 0,
                    'target': target or 0,
                    'progress': round((current / target * 100) if target > 0 else 0, 1)
                })
            
            conn.close()
            
            # If no goals exist, return default goals
            if not goals:
                # Get current week's stats
                if USE_POSTGRES:
                    cursor = conn.cursor()
                    cursor.execute(
                        """SELECT COUNT(*) as lessons_this_week
                           FROM session_logs 
                           WHERE user_id = %s 
                           AND completion_status = 'completed'
                           AND completed_at >= date_trunc('week', CURRENT_DATE)""",
                        (user_id,)
                    )
                    result = cursor.fetchone()
                    lessons_this_week = result['lessons_this_week'] if hasattr(result, 'keys') else result[0]
                    conn.close()
                else:
                    lessons_this_week = 0
                
                goals = [
                    {
                        'name': 'Complete 55 Lessons',
                        'icon': '📚',
                        'current': lessons_this_week,
                        'target': 15,
                        'progress': round((lessons_this_week / 5 * 100), 1)
                    },
                    {
                        'name': 'Maintain 80% Average',
                        'icon': '⭐',
                        'current': 90,  # Use their actual average
                        'target': 80,
                        'progress': 100
                    }
                ]
            
            return {
                "success": True,
                "goals": goals
            }
            
        except Exception as table_error:
            # Table doesn't exist, return default goals
            print(f"Weekly goals table doesn't exist: {table_error}")
            return {
                "success": True,
                "goals": [
                    {
                        'name': 'Complete 5 Lessons This Week',
                        'icon': '📚',
                        'current': 0,
                        'target': 5,
                        'progress': 0
                    }
                ]
            }
        
    except Exception as e:
        print(f"Error getting weekly goals: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    
def calculate_streak(user_id, conn):
    """Calculate user's current day streak"""
    cursor = conn.cursor()
    
    try:
        # Get distinct dates when user completed lessons
        if USE_POSTGRES:
            cursor.execute(
                """SELECT DISTINCT DATE(completed_at) as lesson_date
                   FROM session_logs
                   WHERE user_id = %s 
                   AND completion_status = 'completed'
                   ORDER BY lesson_date DESC
                   LIMIT 30""",
                (user_id,)
            )
        else:
            cursor.execute(
                """SELECT DISTINCT DATE(completed_at) as lesson_date
                   FROM session_logs
                   WHERE user_id = ? 
                   AND completion_status = 'completed'
                   ORDER BY lesson_date DESC
                   LIMIT 30""",
                (user_id,)
            )
        
        dates = [row[0] if isinstance(row, tuple) else row['lesson_date'] for row in cursor.fetchall()]
        
        if not dates:
            return 0
        
        # Calculate streak
        from datetime import datetime, timedelta
        
        streak = 0
        current_date = datetime.now().date()
        
        # Check if they completed a lesson today or yesterday
        if dates[0] == current_date or dates[0] == current_date - timedelta(days=1):
            streak = 1
            expected_date = dates[0] - timedelta(days=1)
            
            # Count consecutive days
            for i in range(1, len(dates)):
                if dates[i] == expected_date:
                    streak += 1
                    expected_date -= timedelta(days=1)
                else:
                    break
        
        return streak
        
    except Exception as e:
        print(f"Error calculating streak: {e}")
        return 0
    
# Health Check Endpoint - Add to app.py

# Copy this entire section and paste it into your app.py
# (Put it near the other @app.get endpoints, around line 3850)

@app.get("/api/health/full")
async def full_health_check():
    """
    Comprehensive health check - shows what's working and what's broken
    Visit: https://your-railway-url.railway.app/api/health/full
    """
    conn = get_db()
    cursor = get_cursor(conn)
    
    results = {
        "database": "connected",
        "tables": {},
        "issues": [],
        "ready_for_placement": False
    }
    
    # Check each table
    tables_to_check = [
        "users",
        "passages", 
        "passage_questions",
        "placement_attempts",
        "session_logs",
        "writing_exercises",
        "vocabulary_tracker",
        "discussions"
    ]
    
    for table in tables_to_check:
        try:
            cursor.execute(f"SELECT COUNT(*) as c FROM {table}")
            count = cursor.fetchone()
            results["tables"][table] = {
                "exists": True,
                "count": count['c'] if USE_POSTGRES else count[0]
            }
        except Exception as e:
            results["tables"][table] = {
                "exists": False,
                "error": str(e)
            }
            results["issues"].append(f"Table '{table}' missing or broken: {str(e)}")
    
    # Check passages specifically
    if results["tables"].get("passages", {}).get("exists"):
        try:
            cursor.execute("SELECT COUNT(*) as c FROM passages WHERE approved=true" if USE_POSTGRES else "SELECT COUNT(*) as c FROM passages WHERE approved=1")
            approved_count = cursor.fetchone()
            results["passages_approved"] = approved_count['c'] if USE_POSTGRES else approved_count[0]
            
            if results["passages_approved"] == 0:
                results["issues"].append("⚠️ No approved passages! Users can't take placement test.")
        except Exception as e:
            results["issues"].append(f"Error checking approved passages: {str(e)}")
    
    # Check if passages have questions
    if results["tables"].get("passage_questions", {}).get("exists"):
        try:
            cursor.execute("""
                SELECT p.id, p.title, COUNT(pq.id) as q_count
                FROM passages p
                LEFT JOIN passage_questions pq ON p.id = pq.passage_id
                WHERE p.approved=true
                GROUP BY p.id, p.title
                HAVING COUNT(pq.id) = 0
                LIMIT 5
            """ if USE_POSTGRES else """
                SELECT p.id, p.title, COUNT(pq.id) as q_count
                FROM passages p
                LEFT JOIN passage_questions pq ON p.id = pq.passage_id
                WHERE p.approved=1
                GROUP BY p.id, p.title
                HAVING COUNT(pq.id) = 0
                LIMIT 5
            """)
            passages_without_questions = cursor.fetchall()
            if passages_without_questions and len(passages_without_questions) > 0:
                results["issues"].append(f"⚠️ {len(passages_without_questions)} approved passages have no questions!")
        except Exception as e:
            results["issues"].append(f"Error checking passage questions: {str(e)}")
    
    # Check user table columns
    try:
        if USE_POSTGRES:
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'users'
            """)
        else:
            cursor.execute("PRAGMA table_info(users)")
        
        columns = cursor.fetchall()
        required_columns = ['age_band', 'grade_band', 'interest_tags', 'level_estimate']
        existing_columns = [c['column_name'] if USE_POSTGRES else c[1] for c in columns]
        
        missing_columns = [col for col in required_columns if col not in existing_columns]
        if missing_columns:
            results["issues"].append(f"⚠️ Users table missing columns: {', '.join(missing_columns)}")
    except Exception as e:
        results["issues"].append(f"Error checking user columns: {str(e)}")
    
    # Check OPENAI_API_KEY
    results["openai_configured"] = bool(os.getenv("OPENAI_API_KEY"))
    if not results["openai_configured"]:
        results["issues"].append("⚠️ OPENAI_API_KEY not set - AI features won't work")
    
    # Check content generator
    results["content_generator"] = content_generator is not None
    if not content_generator:
        results["issues"].append("⚠️ Content generator not initialized")
    
    # Determine if ready for placement test
    passages_ready = results["tables"].get("passages", {}).get("count", 0) > 0
    questions_ready = results["tables"].get("passage_questions", {}).get("count", 0) > 0
    placement_table_ready = results["tables"].get("placement_attempts", {}).get("exists", False)
    
    results["ready_for_placement"] = passages_ready and questions_ready and placement_table_ready
    
    if not results["ready_for_placement"]:
        if not passages_ready:
            results["issues"].append("❌ CRITICAL: No passages in database - placement test will fail!")
        if not questions_ready:
            results["issues"].append("❌ CRITICAL: No questions in database - placement test will fail!")
        if not placement_table_ready:
            results["issues"].append("❌ CRITICAL: placement_attempts table missing!")
    
    conn.close()
    
    results["status"] = "healthy" if len(results["issues"]) == 0 else "unhealthy"
    results["timestamp"] = datetime.now(timezone.utc).isoformat()
    
    return results
    
# ============================================
# PLACEMENT TEST
# ============================================

import json, random
from fastapi import HTTPException, Request

PLACEMENT_MAX_ATTEMPTS = 3
PLACEMENT_WC_MIN, PLACEMENT_WC_MAX = 120, 180

@app.get("/api/placement/next")
async def get_next_placement(token: str):
    user_data = verify_token(token)
    user_id = user_data["user_id"]
    
    conn = get_db()
    cursor = get_cursor(conn)
    
    # Check attempts
    cursor.execute(
        "SELECT COUNT(*) AS c FROM placement_attempts WHERE user_id=%s" if USE_POSTGRES
        else "SELECT COUNT(*) AS c FROM placement_attempts WHERE user_id=?",
        (user_id,)
    )
    row = cursor.fetchone()
    attempts = (row["c"] if hasattr(row, "keys") else row[0]) or 0
    
    if attempts >= PLACEMENT_MAX_ATTEMPTS:
        conn.close()
        return {"done": True, "attempt": attempts, "total_attempts": PLACEMENT_MAX_ATTEMPTS}
    
    # ⭐ FIX: Get passages from ALL levels for placement
    # Pick one from each level progressively
    levels = ["beginner", "intermediate", "advanced"]
    target_level = levels[attempts % 3]  # Rotate through levels
    
    if USE_POSTGRES:
        cursor.execute(
            """
            SELECT id, title, content, word_count, difficulty_level
            FROM passages
            WHERE approved=true
              AND difficulty_level=%s
              AND word_count BETWEEN %s AND %s
            ORDER BY RANDOM()
            LIMIT 1
            """,
            (target_level, PLACEMENT_WC_MIN, PLACEMENT_WC_MAX)
        )
    else:
        cursor.execute(
            """
            SELECT id, title, content, word_count, difficulty_level
            FROM passages
            WHERE approved=1
              AND difficulty_level=?
              AND word_count BETWEEN ? AND ?
            ORDER BY RANDOM()
            LIMIT 1
            """,
            (target_level, PLACEMENT_WC_MIN, PLACEMENT_WC_MAX)
        )
    
    p = cursor.fetchone()

    # ⭐ FALLBACK: If no passage at target level, try ANY level
    if not p:
        print(f"⚠️ No {target_level} passages, trying any level...")
        
        if USE_POSTGRES:
            cursor.execute(
                """
                SELECT id, title, content, word_count, difficulty_level
                FROM passages
                WHERE approved=true AND word_count BETWEEN %s AND %s
                ORDER BY RANDOM() LIMIT 1
                """,
                (PLACEMENT_WC_MIN, PLACEMENT_WC_MAX)
            )
        else:
            cursor.execute(
                """
                SELECT id, title, content, word_count, difficulty_level
                FROM passages
                WHERE approved=1 AND word_count BETWEEN ? AND ?
                ORDER BY RANDOM() LIMIT 1
                """,
                (PLACEMENT_WC_MIN, PLACEMENT_WC_MAX)
            )
        
        p = cursor.fetchone()
        
        if p:
            actual_level = p["difficulty_level"] if hasattr(p, "keys") else p[4]
            print(f"✅ Using {actual_level} level as fallback")

    # Only error if STILL no passages
    if not p:
        conn.close()
        raise HTTPException(500, "No passages in database!")

    passage_id = p["id"] if hasattr(p, "keys") else p[0]
    title = p["title"] if hasattr(p, "keys") else p[1]
    content = p["content"] if hasattr(p, "keys") else p[2]
    word_count = p["word_count"] if hasattr(p, "keys") else p[3]
    difficulty_level = p["difficulty_level"] if hasattr(p, "keys") else p[4]

    # questions (use your existing table)
    cursor.execute(
        "SELECT question_text, correct_answer, options, explanation FROM passage_questions WHERE passage_id=%s" if USE_POSTGRES
        else "SELECT question_text, correct_answer, options, explanation FROM passage_questions WHERE passage_id=?",
        (passage_id,)
    )
    qs = cursor.fetchall() or []
    conn.close()

    questions = []
    for q in qs[:3]:
        options_raw = q["options"] if hasattr(q, "keys") else q[2]
        try:
            opts = json.loads(options_raw) if isinstance(options_raw, str) else (options_raw or [])
        except:
            opts = []
        questions.append({
            "question": q["question_text"] if hasattr(q, "keys") else q[0],
            "options": opts,
            # don't send correct answer to client if you want to prevent cheating:
            # "correct_answer": q["correct_answer"] ...
        })

    return {
        "done": False,
        "attempt": attempts + 1,
        "total_attempts": PLACEMENT_MAX_ATTEMPTS,
        "passage": {
            "id": passage_id,
            "title": title,
            "content": content,
            "word_count": word_count,
            "difficulty_level": difficulty_level
        },
        "questions": questions
    }

import re

def _count_words(text: str) -> int:
    return len(re.findall(r"\b[\w']+\b", text or ""))

def _compute_level_update(current_level: str, score: float, wpm: float) -> str:
    levels = ["beginner", "intermediate", "advanced"]
    idx = levels.index(current_level) if current_level in levels else 1

    # tune thresholds as you like
    if score >= 80 and wpm >= 130 and idx < 2:
        idx += 1
    elif score <= 55 and idx > 0:
        idx -= 1
    return levels[idx]

@app.post("/api/placement/submit")
async def submit_placement(request: Request):
    data = await request.json()
    token = data.get("token")
    passage_id = int(data.get("passage_id"))
    answers = data.get("answers") or []
    time_spent_seconds = int(data.get("time_spent_seconds") or 0)

    user_data = verify_token(token)
    user_id = user_data["user_id"]

    conn = get_db()
    cursor = get_cursor(conn)

    # get passage word_count + difficulty
    cursor.execute(
        "SELECT word_count, difficulty_level FROM passages WHERE id=%s" if USE_POSTGRES
        else "SELECT word_count, difficulty_level FROM passages WHERE id=?",
        (passage_id,)
    )
    p = cursor.fetchone()
    if not p:
        conn.close()
        raise HTTPException(status_code=404, detail="Passage not found")

    wc = (p["word_count"] if hasattr(p, "keys") else p[0]) or 0
    difficulty_shown = (p["difficulty_level"] if hasattr(p, "keys") else p[1]) or "intermediate"

    # fetch correct answers for grading
    cursor.execute(
        "SELECT correct_answer FROM passage_questions WHERE passage_id=%s ORDER BY id ASC" if USE_POSTGRES
        else "SELECT correct_answer FROM passage_questions WHERE passage_id=? ORDER BY id ASC",
        (passage_id,)
    )
    correct_rows = cursor.fetchall() or []
    correct = [(r["correct_answer"] if hasattr(r, "keys") else r[0]) for r in correct_rows][:len(answers)]

    total = max(1, len(correct))
    correct_n = 0
    for i in range(min(len(answers), len(correct))):
        if str(answers[i]).strip() == str(correct[i]).strip():
            correct_n += 1
    score = round((correct_n / total) * 100.0, 2)

    minutes = max(1/60, time_spent_seconds / 60.0)
    wpm = round((wc / minutes), 1) if wc else 0.0

    # current provisional level from users table
    cursor.execute(
        "SELECT level_estimate FROM users WHERE id=%s" if USE_POSTGRES else "SELECT level_estimate FROM users WHERE id=?",
        (user_id,)
    )
    r = cursor.fetchone()
    current_level = (r["level_estimate"] if hasattr(r, "keys") else r[0]) or "intermediate"

    new_level = _compute_level_update(current_level, score, wpm)

    defaults = {
        "beginner": (150, 200),
        "intermediate": (200, 250),
        "advanced": (250, 300),
    }
    mn, mx = defaults[new_level]

    # store attempt
    cursor.execute(
        """
        INSERT INTO placement_attempts
          (user_id, passage_id, difficulty_level, word_count, time_spent_seconds, wpm, comprehension_score)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
        """ if USE_POSTGRES else
        """
        INSERT INTO placement_attempts
          (user_id, passage_id, difficulty_level, word_count, time_spent_seconds, wpm, comprehension_score)
        VALUES (?,?,?,?,?,?,?)
        """,
        (user_id, passage_id, difficulty_shown, int(wc), int(time_spent_seconds), float(wpm), float(score))
    )

    # update user's current estimate + ranges
    cursor.execute(
        "UPDATE users SET level_estimate=%s, word_count_min=%s, word_count_max=%s WHERE id=%s" if USE_POSTGRES else
        "UPDATE users SET level_estimate=?, word_count_min=?, word_count_max=? WHERE id=?",
        (new_level, mn, mx, user_id)
    )

    conn.commit()
    conn.close()

    return {
        "success": True,
        "score": score,
        "wpm": wpm,
        "new_level": new_level,
        "word_count_range": [mn, mx],
    }

@app.post("/api/placement/retake")
async def retake_placement(request: Request):
    """
    Allows a student to retake placement by clearing prior placement attempts
    and resetting reading level fields that your lesson generator relies on.
    """
    try:
        data = await request.json()
        token = data.get("token")
        if not token:
            raise HTTPException(status_code=401, detail="Missing token")

        user_data = verify_token(token)
        user_id = user_data["user_id"]
        role = user_data.get("role")

        # You can decide if admins can force-retake for a student later.
        if role != "student":
            raise HTTPException(status_code=403, detail="Student only")

        conn = get_db()
        cursor = get_cursor(conn)

        # 1) Clear placement attempts
        if USE_POSTGRES:
            cursor.execute("DELETE FROM placement_attempts WHERE user_id = %s", (user_id,))
        else:
            cursor.execute("DELETE FROM placement_attempts WHERE user_id = ?", (user_id,))

        # 2) Reset reading level + word count bounds (so placement is truly required again)
        #    Adjust these field names if your users table uses different column names.
        if USE_POSTGRES:
            cursor.execute(
                """
                UPDATE users
                SET level_estimate = NULL,
                    word_count_min = NULL,
                    word_count_max = NULL
                WHERE id = %s
                """,
                (user_id,)
            )
        else:
            cursor.execute(
                """
                UPDATE users
                SET level_estimate = NULL,
                    word_count_min = NULL,
                    word_count_max = NULL
                WHERE id = ?
                """,
                (user_id,)
            )

        conn.commit()
        conn.close()

        return {"success": True, "message": "Placement reset. Student may retake placement now."}

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error retaking placement: {e}")
        raise HTTPException(status_code=500, detail=str(e))



# ============================================
# LESSONS ENDPOINTS (Phase 2 - AI Generated)
# ============================================

@app.get("/api/lessons/next")
async def get_next_lesson(token: str, exclude_topics: str = None):
    """Get next AI-generated lesson with topic variety (fast + reliable)"""

    import json
    import random
    import re
    import hashlib
    from difflib import SequenceMatcher

    print("=" * 50)
    print("LESSON REQUEST RECEIVED")
    print("=" * 50)

    def count_words(text: str) -> int:
        return len(re.findall(r"\b[\w']+\b", text or ""))

    # Less aggressive fingerprint (prevents false “duplicate”)
    def fp(text: str, max_chars: int = 800) -> str:
        norm = re.sub(r"\s+", " ", (text or "").strip().lower())
        norm = norm[:max_chars]
        return hashlib.sha256(norm.encode("utf-8")).hexdigest()

    # Near-duplicate check (only rejects if VERY similar)
    def is_near_duplicate(a: str, b: str, threshold: float = 0.94) -> bool:
        a = (a or "").strip().lower()
        b = (b or "").strip().lower()
        if not a or not b:
            return False
        # Compare only first part (fast + good enough)
        a = re.sub(r"\s+", " ", a)[:1500]
        b = re.sub(r"\s+", " ", b)[:1500]
        return SequenceMatcher(None, a, b).ratio() >= threshold

    def normalize_passage(p: dict, topic: str, difficulty: str) -> dict:
        if not isinstance(p, dict):
            p = {}

        p.setdefault("title", topic)
        p.setdefault("content", "")
        p["source"] = p.get("source") or "AI"
        p["difficulty_level"] = p.get("difficulty_level") or difficulty

        if not p.get("topic_tags"):
            p["topic_tags"] = [topic]

        # Always compute word_count from content
        p["word_count"] = count_words(p.get("content", ""))

        # Optional DB fields
        p.setdefault("readability_score", None)
        p.setdefault("flesch_ease", None)
        p.setdefault("estimated_minutes", None)

        # Lists used by response
        p.setdefault("key_concepts", [])
        p.setdefault("vocabulary_words", [])

        return p

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

        # Step 3: Fetch user + recent data
        print("Step 3: Fetching user from database...")
        conn = get_db()
        cursor = get_cursor(conn)

        if USE_POSTGRES:
            cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        else:
            cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))

        user = cursor.fetchone()
        if not user:
            conn.close()
            raise HTTPException(status_code=404, detail=f"User {user_id} not found")

        print(f"✓ User found: {user.get('full_name') or user.get('email')}")

        # Step 4: Parse interests
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

        # Check if user has completed reading level assessment
        reading_level = user.get('reading_level') or user.get('level_estimate')

        if not reading_level:
            conn.close()
            raise HTTPException(status_code=409, detail="Reading level assessment required")

        print(f"✓ Reading level: {reading_level}")

        # Recent titles/content for duplicate detection
        cursor.execute(
            """
            SELECT title, content
            FROM passages
            WHERE created_by = %s
            ORDER BY created_at DESC
            LIMIT 30
            """ if USE_POSTGRES else
            """
            SELECT title, content
            FROM passages
            WHERE created_by = ?
            ORDER BY created_at DESC
            LIMIT 30
            """,
            (user_id,)
        )
        recent = cursor.fetchall() or []

        recent_titles = set()
        recent_fps = set()
        recent_previews = []

        for r in recent:
            t = r["title"] if isinstance(r, dict) else r[0]
            c = r["content"] if isinstance(r, dict) else r[1]
            if t:
                recent_titles.add(t.strip().lower())
            if c:
                recent_fps.add(fp(c))
                recent_previews.append((c or "")[:1500])

        # Step 4b: Recently used topics
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
                topic_tags = row[0] if isinstance(row, tuple) else row.get('topic_tags')
                if topic_tags:
                    try:
                        tags = json.loads(topic_tags) if isinstance(topic_tags, str) else topic_tags
                        if isinstance(tags, list):
                            recent_topics.extend(tags)
                    except:
                        pass

            if exclude_topics:
                recent_topics.extend(exclude_topics.split(','))

            print(f"✓ Recent topics: {recent_topics}")
        except Exception as e:
            print(f"Warning: Could not fetch recent topics: {e}")
            recent_topics = []

        available_interests = [i for i in interests if i not in recent_topics]
        if not available_interests:
            print("All topics used recently - resetting to full list")
            available_interests = interests

        print(f"✓ Available interests (excluding recent): {available_interests}")

        # Step 5: Word count + difficulty
        print("Step 5: Getting word count settings...")
        word_count_min = user.get('word_count_min')
        word_count_max = user.get('word_count_max')
        level_estimate = (user.get('level_estimate') or user.get('reading_level') or 'intermediate').lower()
        difficulty = level_estimate

        if not word_count_min or not word_count_max:
            defaults = {
                'beginner': (150, 200),
                'intermediate': (200, 250),
                'advanced': (250, 300),
            }
            word_count_min, word_count_max = defaults.get(level_estimate, (200, 250))

        cursor.execute(
            "SELECT COUNT(*) AS c FROM session_logs WHERE user_id = %s" if USE_POSTGRES
            else "SELECT COUNT(*) AS c FROM session_logs WHERE user_id = ?",
            (user_id,)
        )
        row = cursor.fetchone()
        sessions_count = (row["c"] if isinstance(row, dict) else row[0]) or 0

        if sessions_count == 0:
            if level_estimate == "intermediate":
                difficulty = "beginner"
            word_count_min, word_count_max = 150, 200

        print(f"✓ Difficulty: {difficulty}")
        print(f"✓ Word count range: {word_count_min}-{word_count_max} words")

        # Step 6: Select topic
        print("Step 6: Selecting topic...")
        topic = random.choice(available_interests)
        print(f"✓ Selected topic: {topic}")

        # Done with DB reads
        conn.close()

        # Step 7: Generate passage (duplicates-only retries)
        print("Step 7: Generating passage...")

        # Try up to 3 topics max (duplicates only). No word-count retry storms here.
        topics_to_try = available_interests[:]
        random.shuffle(topics_to_try)

        if topic in topics_to_try:
            topics_to_try.remove(topic)
        topics_to_try = [topic] + topics_to_try
        topics_to_try = topics_to_try[:3]

        passage_data = None
        picked_topic = None
        last_candidate = None

        for attempt, picked_topic in enumerate(topics_to_try, start=1):
            print(f"   Try {attempt}/{len(topics_to_try)}")
            print(f"   Topic: {picked_topic}")
            print(f"   Difficulty: {difficulty}")
            print(f"   Word count range: {word_count_min}-{word_count_max}")

            candidate = content_generator.generate_passage(
                topic=picked_topic,
                difficulty_level=difficulty,
                word_count_min=word_count_min,
                word_count_max=word_count_max,
                user_interests=interests
            )

            candidate = normalize_passage(candidate, picked_topic, difficulty)
            last_candidate = candidate

            title_l = (candidate.get("title") or "").strip().lower()
            content = candidate.get("content") or ""
            content_fp = fp(content)

            # Duplicate checks (avoid false positives)
            dup = False
            if title_l and title_l in recent_titles:
                dup = True

            if content_fp in recent_fps:
                dup = True

            if not dup:
                for prev in recent_previews:
                    if is_near_duplicate(content, prev, threshold=0.94):
                        dup = True
                        break

            if dup:
                print("⚠️ Reject: duplicate title/content")
                continue

            passage_data = candidate
            break

        # If everything looked duplicate, ACCEPT last candidate instead of failing for an hour.
        if not passage_data:
            passage_data = last_candidate
            if not passage_data:
                raise HTTPException(status_code=500, detail="Failed to generate lesson content.")
            print("⚠️ Could not find a non-duplicate quickly; accepting last candidate.")

        topic = picked_topic or topic
        passage_data = normalize_passage(passage_data, topic, difficulty)

        # Step 8: Save passage
        print("Step 8: Saving passage to database...")
        conn = get_db()
        cursor = get_cursor(conn)

        try:
            if USE_POSTGRES:
                cursor.execute(
                    """INSERT INTO passages
                       (title, content, source, topic_tags, word_count, readability_score, flesch_ease,
                        difficulty_level, estimated_minutes, approved, created_by)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       RETURNING id""",
                    (
                        passage_data.get('title'),
                        passage_data.get('content'),
                        passage_data.get('source', 'AI'),
                        json.dumps(passage_data.get('topic_tags', [topic])),
                        passage_data.get('word_count', 0),
                        passage_data.get('readability_score'),
                        passage_data.get('flesch_ease'),
                        passage_data.get('difficulty_level', difficulty),
                        passage_data.get('estimated_minutes'),
                        True,
                        user_id
                    )
                )
                result = cursor.fetchone()
                lesson_id = result['id'] if isinstance(result, dict) else result[0]
            else:
                cursor.execute(
                    """INSERT INTO passages
                       (title, content, source, topic_tags, word_count, readability_score, flesch_ease,
                        difficulty_level, estimated_minutes, approved, created_by)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        passage_data.get('title'),
                        passage_data.get('content'),
                        passage_data.get('source', 'AI'),
                        json.dumps(passage_data.get('topic_tags', [topic])),
                        passage_data.get('word_count', 0),
                        passage_data.get('readability_score'),
                        passage_data.get('flesch_ease'),
                        passage_data.get('difficulty_level', difficulty),
                        passage_data.get('estimated_minutes'),
                        True,
                        user_id
                    )
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
                passage_text=passage_data.get('content', ''),
                passage_title=passage_data.get('title', topic),
                num_questions=3
            )
            print(f"✓ Generated {len(questions)} questions")
        except Exception as q_error:
            print(f"✗ ERROR generating questions: {q_error}")
            import traceback
            traceback.print_exc()
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
                        (
                            lesson_id,
                            q['question'],
                            q.get('type'),
                            q['correct_answer'],
                            json.dumps(q.get('options', [])),
                            q.get('explanation'),
                            q.get('difficulty', 1)
                        )
                    )
                else:
                    cursor.execute(
                        """INSERT INTO passage_questions
                           (passage_id, question_text, question_type, correct_answer, options, explanation, difficulty)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (
                            lesson_id,
                            q['question'],
                            q.get('type'),
                            q['correct_answer'],
                            json.dumps(q.get('options', [])),
                            q.get('explanation'),
                            q.get('difficulty', 1)
                        )
                    )

            conn.commit()
            print(f"✓ Saved {len(questions)} questions")

        except Exception as save_q_error:
            print(f"✗ ERROR saving questions: {save_q_error}")
            import traceback
            traceback.print_exc()
            conn.rollback()
            # continue anyway

        conn.close()

        # Step 11: Update user activity
        print("Step 11: Updating user activity...")
        update_user_activity(user_id)

        # Step 12: Return response
        print("Step 12: Formatting response...")
        response = {
            'id': lesson_id,
            'title': passage_data.get('title', topic),
            'content': passage_data.get('content', ''),
            'difficulty_level': passage_data.get('difficulty_level', difficulty),
            'word_count': passage_data.get('word_count', 0),
            'key_points': passage_data.get('key_concepts', []),
            'vocabulary': passage_data.get('vocabulary_words', []),
            'questions': questions
        }

        print("=" * 50)
        print("✓ LESSON GENERATED SUCCESSFULLY")
        print("=" * 50)

        return response

    except HTTPException:
        raise
    except Exception as e:
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
        
        passage_data = content_generator.generate_passage(
            topic=topic,
            difficulty_level="intermediate",
            word_count_min=75,   # ✅ target_words - 25
            word_count_max=125,  # ✅ target_words + 25
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
async def get_all_students(admin=Depends(require_admin)):
    
    conn = get_db()
    cursor = get_cursor(conn)
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
async def get_student_details(student_id: int, admin=Depends(require_admin)):
    """Get detailed progress for a specific student"""
    
    conn = get_db()
    cursor = get_cursor(conn)
    
    # Get student info
    if USE_POSTGRES:
        cursor.execute("SELECT * FROM users WHERE id = %s", (student_id,))
    else:
        cursor.execute("SELECT * FROM users WHERE id = ?", (student_id,))
    
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Student not found")
    student = dict(row)
    
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
    
@app.get("/api/admin/student/{student_id}/progress")
async def get_student_progress(student_id: int, admin=Depends(require_admin)):
    
    conn = get_db()
    cursor = get_cursor(conn)

    # Student basic info
    cursor.execute(
        """
        SELECT
            sl.id,
            sl.passage_id,
            sl.completion_status,
            sl.comprehension_score,
            sl.time_spent_seconds,
            sl.completed_at,
            sl.started_at,
            p.title,
            p.difficulty_level
        FROM session_logs sl
        LEFT JOIN passages p ON p.id = sl.passage_id
        WHERE sl.user_id = %s
        ORDER BY sl.started_at DESC
        LIMIT 50
        """ if USE_POSTGRES else
        """
        SELECT
            sl.id,
            sl.passage_id,
            sl.completion_status,
            sl.comprehension_score,
            sl.time_spent_seconds,
            sl.completed_at,
            sl.started_at,
            p.title,
            p.difficulty_level
        FROM session_logs sl
        LEFT JOIN passages p ON p.id = sl.passage_id
        WHERE sl.user_id = ?
        ORDER BY sl.started_at DESC
        LIMIT 50
        """,
        (student_id,)
    )
    student_row = cursor.fetchone()
    if not student_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Student not found")

    student = dict(student_row)

    rows = [dict(r) for r in (cursor.fetchall() or [])]

    progress_rows = [{
        "id": r["id"],
        "lesson_id": r.get("passage_id"),
        "title": r.get("title") or (f"Passage #{r.get('passage_id')}" if r.get("passage_id") else "Untitled"),
        "topic": r.get("topic") or "General",
        "completed": (r.get("completion_status") == "completed"),
        "score": r.get("comprehension_score"),
        "time_spent": r.get("time_spent_seconds"),
        "completed_at": str(r.get("completed_at") or r.get("started_at") or ""),
    } for r in rows]

    # 1) Try progress table (empty in your screenshot)
    try:
        cursor.execute(
            """
            SELECT id, lesson_id, completed, score, time_spent, completed_at
            FROM progress
            WHERE user_id = %s
            ORDER BY completed_at DESC NULLS LAST
            LIMIT 50
            """ if USE_POSTGRES else
            """
            SELECT id, lesson_id, completed, score, time_spent, completed_at
            FROM progress
            WHERE user_id = ?
            ORDER BY completed_at DESC
            LIMIT 50
            """,
            (student_id,)
        )
        progress_rows = [dict(r) for r in (cursor.fetchall() or [])]
    except Exception:
        progress_rows = []

    # 2) If progress table is empty, build progress-like rows from session_logs
    if not progress_rows:
        cursor.execute(
            """
            SELECT id, passage_id, completion_status, comprehension_score, time_spent_seconds, completed_at, started_at
            FROM session_logs
            WHERE user_id = %s
            ORDER BY started_at DESC
            LIMIT 50
            """ if USE_POSTGRES else
            """
            SELECT id, passage_id, completion_status, comprehension_score, time_spent_seconds, completed_at, started_at
            FROM session_logs
            WHERE user_id = ?
            ORDER BY started_at DESC
            LIMIT 50
            """,
            (student_id,)
        )
        sessions = [dict(r) for r in (cursor.fetchall() or [])]

        # Normalize into the "progress" shape the frontend expects
        progress_rows = [{
            "id": s["id"],
            "lesson_id": s.get("passage_id"),
            "completed": (s.get("completion_status") == "completed"),
            "score": s.get("comprehension_score"),
            "time_spent": s.get("time_spent_seconds"),
            "completed_at": str(s.get("completed_at") or s.get("started_at") or ""),
        } for s in sessions]

    conn.close()

    return {
        "success": True,
        "student": student,
        "progress": progress_rows,   # ✅ THIS is what your UI expects
    }
    
@app.delete("/api/admin/student/{student_id}")
async def delete_student(student_id: int, admin=Depends(require_admin)):
    """Delete a student and all their data"""
    print(f"\n{'='*60}")
    print(f"DELETE CALLED FOR STUDENT ID: {student_id}")
    print(f"{'='*60}\n")
    
    conn = get_db()
    cursor = get_cursor(conn)
    
    try:
        # Check student exists
        cursor.execute(
            "SELECT full_name FROM users WHERE id=%s AND role='student'" if USE_POSTGRES
            else "SELECT full_name FROM users WHERE id=? AND role='student'",
            (student_id,)
        )
        
        student = cursor.fetchone()
        if not student:
            conn.close()
            raise HTTPException(404, "Student not found")
        
        name = student["full_name"] if hasattr(student, "keys") else student[0]
        
        # Delete related data (order matters!)
        tables_to_clean = [
            # Tables referencing user_sessions
            "timeout_events",       # session_id → user_sessions
            "activity_log",         # session_id → user_sessions
            
            # Tables directly referencing users
            "session_logs",         # user_id → users
            "user_sessions",        # user_id → users
            "placement_attempts",   # user_id → users
            "weekly_goals",         # user_id → users
            "user_badges",          # user_id → users (probably)
            "user_essays",          # user_id → users
            "user_points",          # user_id → users
            "user_streaks",         # user_id → users
            "points_history",       # user_id → users
            "progress",             # user_id → users
            "vocabulary_tracker",   # user_id → users
            "writing_exercises",    # user_id → users (maybe)
            "difficulty_adjustments", # user_id → users (maybe)
            "assessments",          # user_id → users (maybe)
            "discussions",          # user_id → users (maybe)
            "admin_alerts"          # student_id → users (maybe)
        ]
        
        for table in tables_to_clean:
            try:
                cursor.execute(
                    
                    f"DELETE FROM {table} WHERE user_id=%s" if USE_POSTGRES
                    else f"DELETE FROM {table} WHERE user_id=?",
                    (student_id,)
                )
                conn.commit()
                print(f"✓ Deleted from {table}")
            except Exception as e:
                conn.rollback()
                print(f"⚠️ Skipping {table}: {e}")
        
        # Delete user
        cursor.execute(
            "DELETE FROM users WHERE id=%s" if USE_POSTGRES
            else "DELETE FROM users WHERE id=?",
            (student_id,)
        )
        
        conn.commit()
        conn.close()
        
        print(f"✅ Deleted student: {name}")
        
        return {"success": True, "message": f"Deleted {name}"}
        
    except HTTPException:
        conn.rollback()
        conn.close()
        raise
    except Exception as e:
        conn.rollback()
        conn.close()
        print(f"❌ Error: {e}")
        raise HTTPException(500, str(e))

@app.get("/api/admin/analytics")
async def get_analytics(admin=Depends(require_admin)):
    """Get basic analytics (Phase 1 compatibility)"""
    
    conn = get_db()
    cursor = get_cursor(conn)

    
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

@app.get("/api/admin/platform-activity")
async def get_platform_activity(days: int = 7, admin=Depends(require_admin)):

    days = max(1, min(int(days or 7), 30))

    conn = get_db()
    cursor = get_cursor(conn)   # <-- THIS is the missing piece

    if USE_POSTGRES:
        cursor.execute(
            """
            WITH day_series AS (
              SELECT generate_series(
                CURRENT_DATE - (%s::int - 1),
                CURRENT_DATE,
                interval '1 day'
              )::date AS day
            ),
            agg AS (
              SELECT
                CAST(started_at AS date) AS day,
                COUNT(*) AS starts,
                SUM(CASE WHEN completion_status = 'completed' THEN 1 ELSE 0 END) AS completes,
                COUNT(DISTINCT user_id) AS engaged
              FROM session_logs
              WHERE started_at >= (CURRENT_DATE - (%s::int - 1))
                AND started_at <  (CURRENT_DATE + 1)
              GROUP BY 1
            )
            SELECT
              s.day,
              COALESCE(a.engaged, 0) AS engaged,
              COALESCE(a.starts, 0) AS starts,
              COALESCE(a.completes, 0) AS completes,
              CASE
                WHEN COALESCE(a.starts, 0) = 0 THEN 0
                ELSE ROUND((a.completes::numeric / a.starts::numeric) * 100, 2)
              END AS completion_rate
            FROM day_series s
            LEFT JOIN agg a USING (day)
            ORDER BY s.day;
            """,
            (days, days),
        )

        rows = cursor.fetchall()
        conn.close()

        return {
            "success": True,
            "labels": [r["day"].strftime("%b %d") for r in rows],
            "engagement": [int(r["engaged"]) for r in rows],
            "completion_rate": [float(r["completion_rate"]) for r in rows],
        }

    # SQLite fallback (if needed later)
    cursor = conn.cursor()
    # (optional: implement if you ever flip USE_POSTGRES off)
    conn.close()
    return {"success": True, "labels": [], "engagement": [], "completion_rate": []}

# ========== ADMIN ENDPOINTS ==========

@app.get("/api/admin/sessions/active")
async def get_active_sessions(admin=Depends(require_admin)):
    """Get all active sessions (admin only)"""
    try:
        
        conn = get_db()
        cursor = get_cursor(conn)
        
        if USE_POSTGRES:
            cursor.execute("""
                SELECT
                    us.id,
                    us.user_id,
                    u.full_name,
                    u.email,
                    us.status,
                    us.session_start,
                    us.last_activity,
                    us.break_start
                FROM user_sessions us
                JOIN users u ON u.id = us.user_id
                WHERE us.session_end IS NULL
                ORDER BY us.last_activity DESC NULLS LAST, us.session_start DESC
            """)
        else:
            cursor.execute("""
                SELECT
                    us.id,
                    us.user_id,
                    u.full_name,
                    u.email,
                    us.status,
                    us.session_start,
                    us.last_activity,
                    us.break_start
                FROM user_sessions us
                JOIN users u ON u.id = us.user_id
                WHERE us.session_end IS NULL
                ORDER BY us.last_activity DESC, us.session_start DESC
            """)
        
        rows = cursor.fetchall()
        sessions = []
        
        for row in rows:
            if hasattr(row, 'keys'):
                # PostgreSQL with RealDictCursor
                sessions.append({
                    'session_id': row['id'],
                    'user_id': row['user_id'],
                    'user_name': row['full_name'],
                    'user_email': row['email'],
                    'status': row['status'],
                    'session_start': str(row['session_start']),
                    'last_activity': str(row['last_activity']) if row['last_activity'] else None,
                    'break_start': str(row['break_start']) if row['break_start'] else None
                })
            else:
                # SQLite with Row
                sessions.append({
                    'session_id': row[0],
                    'user_id': row[1],
                    'user_name': row[2],
                    'user_email': row[3],
                    'status': row[4],
                    'session_start': str(row[5]),
                    'last_activity': str(row[6]) if row[6] else None,
                    'break_start': str(row[7]) if row[7] else None
                })
        
        conn.close()
        
        return {
            "success": True,
            "sessions": sessions,
            "count": len(sessions)
        }
        
    except Exception as e:
        print(f"Error getting active sessions: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/admin/activity/recent")
async def get_recent_activity(hours: int = 24, admin=Depends(require_admin)):
    """Get recent activity logs (admin only)"""
    try:
        
        conn = get_db()
        cursor = get_cursor(conn)
        
        if USE_POSTGRES:
            cursor.execute("""
                SELECT 
                    a.id,
                    a.user_id,
                    a.session_id,
                    a.activity_type,
                    a.activity_details,
                    a.timestamp,
                    u.full_name,
                    u.email
                FROM activity_log a
                JOIN users u ON a.user_id = u.id
                WHERE a.timestamp > NOW() - (%s * INTERVAL '1 hour')
                ORDER BY a.timestamp DESC
                LIMIT 100
            """, (hours,))
        else:
            cursor.execute("""
                SELECT 
                    a.id,
                    a.user_id,
                    a.session_id,
                    a.activity_type,
                    a.activity_details,
                    a.timestamp,
                    u.full_name,
                    u.email
                FROM activity_log a
                JOIN users u ON a.user_id = u.id
                WHERE a.timestamp > datetime('now', '-' || ? || ' hours')
                ORDER BY a.timestamp DESC
                LIMIT 100
            """, (hours,))
        
        rows = cursor.fetchall()
        activities = []
        
        for row in rows:
            if hasattr(row, 'keys'):
                # PostgreSQL with RealDictCursor
                activities.append({
                    'id': row['id'],
                    'user_id': row['user_id'],
                    'session_id': row['session_id'],
                    'user_name': row['full_name'],
                    'user_email': row['email'],
                    'activity_type': row['activity_type'],
                    'activity_details': row['activity_details'],
                    'timestamp': str(row['timestamp'])
                })
            else:
                # SQLite with Row
                activities.append({
                    'id': row[0],
                    'user_id': row[1],
                    'session_id': row[2],
                    'activity_type': row[3],
                    'activity_details': row[4],
                    'timestamp': str(row[5]),
                    'user_name': row[6],
                    'user_email': row[7]
                })
        
        conn.close()
        
        return {
            "success": True,
            "activities": activities,
            "count": len(activities)
        }
        
    except Exception as e:
        print(f"Error getting activity: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    
def require_admin_db(user=Depends(get_current_user)):
    user_id = user["user_id"]
    conn = get_db()
    cursor = get_cursor(conn)
    try:
        if USE_POSTGRES:
            cursor.execute("SELECT role FROM users WHERE id=%s", (user_id,))
        else:
            cursor.execute("SELECT role FROM users WHERE id=?", (user_id,))
        row = cursor.fetchone()
        role = (row["role"] if isinstance(row, dict) else row[0]) if row else None
        if role != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")
        return {"user_id": user_id, "role": role}
    finally:
        conn.close()
    
@app.get("/api/admin/stats")
async def admin_stats(admin=Depends(require_admin)):
    return {"ok": True}

@app.get("/admin-dashboard", response_class=HTMLResponse)
async def admin_dashboard(admin=Depends(require_admin)):
    with open("admin-dashboard.html", "r", encoding="utf-8") as f:
        return f.read()

# ============================================
# ESSAY ALERTS & REVIEW ENDPOINTS
# ============================================

@app.get("/api/admin/alerts/unread")
async def get_unread_alerts(limit: int = 50, admin=Depends(require_admin)):
    """Get unread admin alerts"""
    
    conn = get_db()
    cursor = conn.cursor()

    try:
        if USE_POSTGRES:
            cursor.execute("""
                SELECT
                    a.id AS alert_id,
                    a.alert_type,
                    a.user_id,
                    u.full_name AS user_name,
                    u.email AS user_email,
                    a.essay_id,
                    a.priority,
                    a.message,
                    a.details,
                    a.created_at
                FROM admin_alerts a
                JOIN users u ON u.id = a.user_id
                WHERE a.is_read = FALSE
                ORDER BY 
                    CASE a.priority
                        WHEN 'urgent' THEN 1
                        WHEN 'high' THEN 2
                        WHEN 'normal' THEN 3
                        ELSE 4
                    END,
                    a.created_at DESC
                LIMIT %s
            """, (limit,))
        else:
            cursor.execute("""
                SELECT
                    a.id AS alert_id,
                    a.alert_type,
                    a.user_id,
                    u.full_name AS user_name,
                    u.email AS user_email,
                    a.essay_id,
                    a.priority,
                    a.message,
                    a.details,
                    a.created_at
                FROM admin_alerts a
                JOIN users u ON u.id = a.user_id
                WHERE a.is_read = 0
                ORDER BY 
                    CASE a.priority
                        WHEN 'urgent' THEN 1
                        WHEN 'high' THEN 2
                        WHEN 'normal' THEN 3
                        ELSE 4
                    END,
                    a.created_at DESC
                LIMIT ?
            """, (limit,))

        rows = cursor.fetchall()
        alerts = []
        
        for row in rows:
            alerts.append({
                'alert_id': row['alert_id'] if hasattr(row, 'keys') else row[0],
                'alert_type': row['alert_type'] if hasattr(row, 'keys') else row[1],
                'user_id': row['user_id'] if hasattr(row, 'keys') else row[2],
                'user_name': row['user_name'] if hasattr(row, 'keys') else row[3],
                'user_email': row['user_email'] if hasattr(row, 'keys') else row[4],
                'essay_id': row['essay_id'] if hasattr(row, 'keys') else row[5],
                'priority': row['priority'] if hasattr(row, 'keys') else row[6],
                'message': row['message'] if hasattr(row, 'keys') else row[7],
                'details': row['details'] if hasattr(row, 'keys') else row[8],
                'created_at': str(row['created_at'] if hasattr(row, 'keys') else row[9])
            })
        
        conn.close()
        
        return {
            "success": True,
            "count": len(alerts),
            "alerts": alerts
        }

    except Exception as e:
        conn.close()
        print(f"Error getting unread alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/essays/needs-review")
async def get_essays_needing_review(limit: int = 50, admin=Depends(require_admin)):
    conn = get_db()
    cursor = get_cursor(conn)

    try:
        if USE_POSTGRES:
            cursor.execute("""
                SELECT
                    e.id AS essay_id,
                    e.user_id,
                    u.full_name AS user_name,
                    u.email AS user_email,
                    e.essay_number,
                    e.comprehension_score,
                    e.comprehension_level,
                    e.word_count,
                    e.created_at
                FROM user_essays e
                JOIN users u ON u.id = e.user_id
                WHERE e.needs_admin_review = TRUE
                  AND e.reviewed_at IS NULL
                ORDER BY e.created_at DESC
                LIMIT %s
            """, (limit,))
        else:
            cursor.execute("""
                SELECT
                    e.id AS essay_id,
                    e.user_id,
                    u.full_name AS user_name,
                    u.email AS user_email,
                    e.essay_number,
                    e.comprehension_score,
                    e.comprehension_level,
                    e.word_count,
                    e.created_at
                FROM user_essays e
                JOIN users u ON u.id = e.user_id
                WHERE e.needs_admin_review = 1
                  AND e.reviewed_at IS NULL
                ORDER BY e.created_at DESC
                LIMIT ?
            """, (limit,))

        rows = cursor.fetchall()
        essays = []
        
        for row in rows:
            essays.append({
                'essay_id': row['essay_id'] if hasattr(row, 'keys') else row[0],
                'user_id': row['user_id'] if hasattr(row, 'keys') else row[1],
                'user_name': row['user_name'] if hasattr(row, 'keys') else row[2],
                'user_email': row['user_email'] if hasattr(row, 'keys') else row[3],
                'essay_number': row['essay_number'] if hasattr(row, 'keys') else row[4],
                'comprehension_score': row['comprehension_score'] if hasattr(row, 'keys') else row[5],
                'comprehension_level': row['comprehension_level'] if hasattr(row, 'keys') else row[6],
                'word_count': row['word_count'] if hasattr(row, 'keys') else row[7],
                'created_at': str(row['created_at'] if hasattr(row, 'keys') else row[8])
            })
        
        conn.close()
        
        return {
            "success": True,
            "count": len(essays),
            "essays": essays
        }

    except Exception as e:
        conn.close()
        print(f"Error getting essays needing review: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/essay/{essay_id}/details")
async def get_essay_details(essay_id: int, admin=Depends(require_admin)):
    """Get full essay details including text, feedback, and student info"""
    
    conn = get_db()
    cursor = get_cursor(conn)

    try:
        if USE_POSTGRES:
            cursor.execute("""
                SELECT
                    e.*,
                    u.full_name AS user_name,
                    u.email AS user_email,
                    u.reading_level
                FROM user_essays e
                JOIN users u ON u.id = e.user_id
                WHERE e.id = %s
            """, (essay_id,))
        else:
            cursor.execute("""
                SELECT
                    e.*,
                    u.full_name AS user_name,
                    u.email AS user_email,
                    u.reading_level
                FROM user_essays e
                JOIN users u ON u.id = e.user_id
                WHERE e.id = ?
            """, (essay_id,))

        row = cursor.fetchone()
        
        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail="Essay not found")
        
        # Convert row to dict properly
        if hasattr(row, 'keys'):
            # PostgreSQL RealDictCursor - already a dict-like object
            essay = dict(row)
        else:
            # SQLite Row - convert using column names
            essay = {}
            for key in row.keys():
                essay[key] = row[key]
        
        # Parse JSON fields
        if essay.get('ai_feedback'):
            try:
                if isinstance(essay['ai_feedback'], str):
                    essay['ai_feedback'] = json.loads(essay['ai_feedback'])
            except:
                pass
        
        if essay.get('lesson_topics'):
            try:
                if isinstance(essay['lesson_topics'], str):
                    essay['lesson_topics'] = json.loads(essay['lesson_topics'])
                elif not isinstance(essay['lesson_topics'], list):
                    essay['lesson_topics'] = []
            except:
                essay['lesson_topics'] = []
        
        conn.close()
        
        return {
            "success": True,
            "essay": essay
        }

    except HTTPException:
        raise
    except Exception as e:
        conn.close()
        print(f"Error getting essay details: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/admin/alert/{alert_id}/mark-resolved")
async def mark_alert_resolved(
    alert_id: int,
    request: Request,
    admin=Depends(require_admin),
):
    body = await request.json()
    admin_notes = body.get("notes", "")
        
    conn = get_db()
    cursor = get_cursor(conn)
        
    try:
        if USE_POSTGRES:
            cursor.execute("""
                UPDATE admin_alerts
                SET is_read = TRUE,
                    is_resolved = TRUE,
                    resolved_at = NOW(),
                    resolved_by = %s,
                    resolution_notes = %s
                WHERE id = %s
            """, (admin['user_id'], admin_notes, alert_id))
        else:
            cursor.execute("""
                UPDATE admin_alerts
                SET is_read = 1,
                    is_resolved = 1,
                    resolved_at = datetime('now'),
                    resolved_by = ?,
                    resolution_notes = ?
                WHERE id = ?
            """, (admin['user_id'], admin_notes, alert_id))
            
        conn.commit()
        conn.close()
            
        print(f"✅ Alert {alert_id} marked as resolved by admin {admin['user_id']}")
            
        return {"success": True, "message": "Alert marked as resolved"}
            
    except Exception as e:
        conn.rollback()
        conn.close()
        raise
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(500, str(e))
    finally:
        conn.close()

def row_to_dict(cursor, row):
    if row is None:
        return None
    if hasattr(row, "keys"):
        return dict(row)
    cols = [d[0] for d in cursor.description]
    return dict(zip(cols, row))

@app.post("/api/admin/essay/{essay_id}/mark-reviewed")
async def mark_essay_reviewed(essay_id: int, body: dict, admin=Depends(require_admin)):
    notes = body.get("notes", "").strip()
    conn = get_db()
    cursor = get_cursor(conn)
    try:
        # Optional: ensure essay exists (prevents silent no-op updates)
        if USE_POSTGRES:
            cursor.execute("SELECT id FROM user_essays WHERE id=%s", (essay_id,))
        else:
            cursor.execute("SELECT id FROM user_essays WHERE id=?", (essay_id,))
        exists = cursor.fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="Essay not found")
        
        # Update reviewed fields
        if USE_POSTGRES:
            cursor.execute("""
                UPDATE user_essays
                SET reviewed_at = NOW(),
                    needs_admin_review = FALSE,
                    admin_reviewed = TRUE,
                    admin_notes = %s
                WHERE id = %s
            """, (notes, essay_id))
        else:
            cursor.execute("""
                UPDATE user_essays
                SET reviewed_at = datetime('now'),
                    needs_admin_review = 0,
                    admin_reviewed = 1,
                    admin_notes = ?
                WHERE id = ?
            """, (notes, essay_id))
        
        conn.commit()
        print(f"✅ Essay {essay_id} marked as reviewed by admin {admin['user_id']}")
        return {"success": True}
        
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        print("Error marking essay reviewed:", e)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
    
# ============================================================

@app.get("/api/admin/admins")
async def list_admins(admin=Depends(require_admin)):
    conn = get_db()
    cursor = get_cursor(conn)
    try:
        if USE_POSTGRES:
            cursor.execute("""
                SELECT id, email, full_name, role
                FROM users
                WHERE role = 'admin'
                ORDER BY id DESC
            """)
            rows = cursor.fetchall() or []
            admins = [{
                "id": r["id"] if isinstance(r, dict) else r[0],
                "email": r["email"] if isinstance(r, dict) else r[1],
                "full_name": r["full_name"] if isinstance(r, dict) else r[2],
                "role": r["role"] if isinstance(r, dict) else r[3],
            } for r in rows]
        else:
            cursor.execute("""
                SELECT id, email, full_name, role
                FROM users
                WHERE role = 'admin'
                ORDER BY id DESC
            """)
            rows = cursor.fetchall() or []
            admins = [{"id": r[0], "email": r[1], "full_name": r[2], "role": r[3]} for r in rows]

        return {"success": True, "count": len(admins), "admins": admins}
    finally:
        conn.close
        
@app.post("/api/admin/invites")
async def create_admin_invite(body: InviteAdminReq, admin=Depends(require_admin)):
    email = (body.email or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")

    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    expires_at = datetime.utcnow() + timedelta(hours=24)

    conn = get_db()
    cur = get_cursor(conn)

    try:
        # 1) Store invite (NOT committed yet)
        if USE_POSTGRES:
            cur.execute("""
                INSERT INTO admin_invites (email, token_hash, expires_at, invited_by)
                VALUES (%s, %s, %s, %s)
                RETURNING id
            """, (email, token_hash, expires_at, admin["user_id"]))

            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=500, detail="Failed to create invite (no id returned)")
            invite_id = row["id"] if isinstance(row, Mapping) else row[0]

        else:
            cur.execute("""
                INSERT INTO admin_invites (email, token_hash, created_at, expires_at, invited_by)
                VALUES (?, ?, ?, ?, ?)
            """, (
                email,
                token_hash,
                datetime.utcnow().isoformat(),
                expires_at.isoformat(),
                admin["user_id"],
            ))
            invite_id = cur.lastrowid

        # 2) Build invite link
        invite_link = f"{APP_BASE_URL}/admin-invite?token={raw_token}"

        # 3) Send email via Resend (same verified sender style as forgot-password)
        try:
            resend.Emails.send({
                "from": "Achieve 365 <noreply@4dgaming.games>",  # must be verified in Resend
                "to": email,
                "subject": "You’ve been invited as an administrator",
                "html": f"""
                    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                        <h2 style="color: #2A398A;">Admin Invitation</h2>
                        <p>You’ve been invited to become an administrator.</p>
                        <p>This link expires in 24 hours.</p>

                        <div style="text-align: center; margin: 30px 0;">
                            <a href="{invite_link}"
                               style="background: #2A398A;
                                      color: white;
                                      padding: 12px 30px;
                                      text-decoration: none;
                                      border-radius: 5px;
                                      display: inline-block;">
                                Accept Admin Invite
                            </a>
                        </div>

                        <p>Or copy and paste this link into your browser:</p>
                        <p style="word-break: break-all; color: #666;">{invite_link}</p>

                        <p style="color: #999; font-size: 14px;">
                            If you weren’t expecting this invite, you can ignore this email.
                        </p>

                        <hr style="border: none; border-top: 1px solid #ddd; margin: 30px 0;">
                        <p style="color: #999; font-size: 12px;">
                            Achieve 365 - Empowering Adult Literacy
                        </p>
                    </div>
                """
            })
            print(f"✅ Admin invite email sent to {email}")

        except Exception as email_error:
            print(f"❌ Invite email error: {email_error}")
            conn.rollback()  # prevents “invite created but email failed”
            raise HTTPException(status_code=500, detail="Failed to send invite email")

        # 4) Only commit if email succeeded
        conn.commit()
        return {"success": True, "invite_id": invite_id}

    except HTTPException:
        raise
    except Exception as e:
        print(f"Create admin invite error: {e}")
        conn.rollback()
        raise HTTPException(status_code=500, detail="Failed to create admin invite")
    finally:
        conn.close()

def get_bearer_token(authorization: Optional[str] = Header(None)) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid Authorization header")
    return parts[1].strip()

def require_admin(token: str = Depends(get_bearer_token)) -> dict:
    payload = verify_token(token)
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return payload

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")    

def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def send_resend_email(to_email: str, subject: str, html: str):
    if not RESEND_API_KEY or not FROM_EMAIL or not APP_BASE_URL:
        raise HTTPException(status_code=500, detail="Resend not configured (RESEND_API_KEY/FROM_EMAIL/APP_BASE_URL)")

    r = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
        json={"from": FROM_EMAIL, "to": [to_email], "subject": subject, "html": html},
        timeout=15
    )
    if r.status_code >= 300:
        raise HTTPException(status_code=500, detail=f"Resend error: {r.text}")

def send_admin_invite_email(to_email: str, invite_url: str):
    if not RESEND_API_KEY:
        raise HTTPException(status_code=500, detail="RESEND_API_KEY not configured")

    payload = {
        "from": FROM_EMAIL,
        "to": [to_email],
        "subject": "You’ve been invited as an Achieve 365 Administrator",
        "html": f"""
          <p>You’ve been invited to be an <b>Administrator</b> on Achieve 365.</p>
          <p>Click to set your password (link expires in 24 hours):</p>
          <p><a href="{invite_url}">Set Admin Password</a></p>
          <p>If you didn’t expect this email, you can ignore it.</p>
        """
    }

    r = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=15,
    )

    if r.status_code >= 300:
        raise HTTPException(status_code=500, detail=f"Resend error: {r.text}")
    
from collections.abc import Mapping


@app.post("/api/admin/invites/accept")
async def accept_admin_invite(body: AcceptInviteReq):
    raw_token = (body.token or "").strip()
    password = body.password or ""
    if not raw_token or not password:
        raise HTTPException(status_code=400, detail="Token and password are required")
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    conn = get_db()
    cur = get_cursor(conn)
    try:
        # 1) find pending invite (your schema uses used_at)
        if USE_POSTGRES:
            cur.execute("""
              SELECT id, email
              FROM admin_invites
              WHERE token_hash=%s
                AND used_at IS NULL
                AND revoked_at IS NULL
                AND expires_at > NOW()
              LIMIT 1
            """, (token_hash,))
        else:
            cur.execute("""
              SELECT id, email
              FROM admin_invites
              WHERE token_hash=?
                AND used_at IS NULL
                AND revoked_at IS NULL
                AND expires_at > ?
              LIMIT 1
            """, (token_hash, datetime.utcnow().isoformat()))
        invite = cur.fetchone()
        if not invite:
            raise HTTPException(status_code=400, detail="Invalid or expired invite")
        invite_id = invite["id"] if isinstance(invite, Mapping) else invite[0]
        email = (invite["email"] if isinstance(invite, Mapping) else invite[1]).lower().strip()
        
        # 2) hash password
        password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        
        # 3) upsert user as admin
        if USE_POSTGRES:
            cur.execute("SELECT id FROM users WHERE email=%s LIMIT 1", (email,))
        else:
            cur.execute("SELECT id FROM users WHERE email=? LIMIT 1", (email,))
        existing = cur.fetchone()
        
        if existing:
            user_id = existing["id"] if isinstance(existing, Mapping) else existing[0]
            if USE_POSTGRES:
                cur.execute(
                    "UPDATE users SET role='admin', password_hash=%s WHERE id=%s",
                    (password_hash, user_id)
                )
            else:
                cur.execute(
                    "UPDATE users SET role='admin', password_hash=? WHERE id=?",
                    (password_hash, user_id)
                )
        else:
            # Create new admin user
            if USE_POSTGRES:
                cur.execute("""
                  INSERT INTO users (email, full_name, password_hash, role, created_at)
                  VALUES (%s, %s, %s, 'admin', NOW())
                  RETURNING id
                """, (email, "Administrator", password_hash))
                row = cur.fetchone()
                # ✅ FIX: Handle both dict and tuple
                user_id = row["id"] if isinstance(row, Mapping) else row[0]
            else:
                cur.execute("""
                  INSERT INTO users (email, full_name, password_hash, role, created_at)
                  VALUES (?, ?, ?, 'admin', ?)
                """, (email, "Administrator", password_hash, datetime.utcnow().isoformat()))
                user_id = cur.lastrowid
        
        # 4) mark invite used
        if USE_POSTGRES:
            cur.execute("UPDATE admin_invites SET used_at = NOW() WHERE id = %s", (invite_id,))
        else:
            cur.execute("UPDATE admin_invites SET used_at = ? WHERE id = ?", (datetime.utcnow().isoformat(), invite_id))
        
        conn.commit()
        return {"success": True, "user_id": user_id}
        
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        print("accept_admin_invite error:", e)
        import traceback
        traceback.print_exc()  # ✅ Add full traceback for debugging
        raise HTTPException(status_code=500, detail="Failed to accept invite")
    finally:
        conn.close()

def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

from collections.abc import Mapping

@app.get("/api/admin/invites")
async def list_admin_invites(admin=Depends(require_admin)):
    conn = get_db()
    cur = get_cursor(conn)
    try:
        if USE_POSTGRES:
            cur.execute("""
              SELECT id, email, invited_by, created_at, expires_at, used_at, revoked_at
              FROM admin_invites
              ORDER BY id DESC
              LIMIT 200
            """)
        else:
            cur.execute("""
              SELECT id, email, invited_by, created_at, expires_at, used_at, revoked_at
              FROM admin_invites
              ORDER BY id DESC
              LIMIT 200
            """)

        rows = cur.fetchall() or []

        # normalize sqlite tuples -> dicts if needed
        if rows and not isinstance(rows[0], Mapping):
            cols = ["id","email","invited_by","created_at","expires_at","used_at","revoked_at"]
            rows = [dict(zip(cols, r)) for r in rows]

        return {"success": True, "invites": rows}
    finally:
        conn.close()

@app.post("/api/admin/invites/{invite_id}/resend")
async def resend_admin_invite(invite_id: int, admin=Depends(require_admin)):
    conn = get_db()
    cursor = get_cursor(conn)

    try:
        # 1) load invite
        if USE_POSTGRES:
            cursor.execute("""
                SELECT id, email, used_at, revoked_at
                FROM admin_invites
                WHERE id = %s
            """, (invite_id,))
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Invite not found")
            email = row["email"]
            used_at = row["used_at"]
            revoked_at = row["revoked_at"]
        else:
            cursor.execute("""
                SELECT id, email, used_at, revoked_at
                FROM admin_invites
                WHERE id = ?
            """, (invite_id,))
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Invite not found")
            _, email, used_at, revoked_at = row

        if used_at or revoked_at:
            raise HTTPException(status_code=400, detail="Invite is not pending")

        # 2) revoke old invite
        if USE_POSTGRES:
            cursor.execute("UPDATE admin_invites SET revoked_at = NOW() WHERE id = %s", (invite_id,))
        else:
            cursor.execute("UPDATE admin_invites SET revoked_at = datetime('now') WHERE id = ?", (invite_id,))

        # 3) create new invite + email it
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        expires_at = datetime.now(timezone.utc) + timedelta(hours=24)

        if USE_POSTGRES:
            cursor.execute("""
                INSERT INTO admin_invites (email, token_hash, expires_at, invited_by)
                VALUES (%s, %s, %s, %s)
                RETURNING id
            """, (email.lower().strip(), token_hash, expires_at, admin["user_id"]))
            row2 = cursor.fetchone()
            new_id = row2["id"] if isinstance(row2, dict) else row2[0]

        else:
            cursor.execute("""
                INSERT INTO admin_invites (email, token_hash, expires_at, invited_by)
                VALUES (?, ?, ?, ?)
            """, (email.lower().strip(), token_hash, expires_at.isoformat(), admin["user_id"]))
            new_id = cursor.lastrowid

        conn.commit()

        invite_link = f"{APP_BASE_URL}/admin-invite?token={raw_token}"
        send_resend_email(
            to_email=email,
            subject="Administrator invite link (new)",
            html=f"""
              <p>You have a new administrator invite link (expires in 24 hours).</p>
              <p><a href="{invite_link}">Accept Admin Invite</a></p>
              <p style="word-break:break-all;">{invite_link}</p>
            """
        )

        return {"success": True, "new_invite_id": new_id}

    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
        
from fastapi.responses import RedirectResponse

@app.get("/admin-invite.html", include_in_schema=False)
def admin_invite_html_redirect(token: str | None = None):
    url = "/admin-invite"
    if token:
        url += f"?token={token}"
    return RedirectResponse(url=url, status_code=307)

        
@app.post("/api/admin/invites/{invite_id}/revoke")
async def revoke_admin_invite(invite_id: int, admin=Depends(require_admin)):
    conn = get_db()
    cursor = get_cursor(conn)

    try:
        if USE_POSTGRES:
            cursor.execute("""
                UPDATE admin_invites
                SET revoked_at = NOW()
                WHERE id = %s AND used_at IS NULL AND revoked_at IS NULL
            """, (invite_id,))
            if cursor.rowcount == 0:
                raise HTTPException(status_code=400, detail="Invite not pending or not found")
        else:
            cursor.execute("""
                UPDATE admin_invites
                SET revoked_at = datetime('now')
                WHERE id = ? AND used_at IS NULL AND revoked_at IS NULL
            """, (invite_id,))
            if cursor.rowcount == 0:
                raise HTTPException(status_code=400, detail="Invite not pending or not found")

        conn.commit()
        return {"success": True}

    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
        
@app.delete("/api/admin/invites/{invite_id}")
async def revoke_admin_invite(invite_id: int, admin=Depends(require_admin)):
    conn = get_db()
    cur = get_cursor(conn)
    try:
        if USE_POSTGRES:
            cur.execute("""
              UPDATE admin_invites
              SET revoked_at = NOW()
              WHERE id = %s AND used_at IS NULL
            """, (invite_id,))
        else:
            cur.execute("""
              UPDATE admin_invites
              SET revoked_at = ?
              WHERE id = ? AND used_at IS NULL
            """, (datetime.utcnow().isoformat(), invite_id))

        conn.commit()
        return {"success": True}
    finally:
        conn.close()


# ============================================================
@app.get("/api/student/gamification")
async def get_gamification_data(token: str):
    """Get gamification data"""
    try:
        user_data = verify_token(token)
        user_id = user_data["user_id"]
        
        conn = get_db()
        cursor = get_cursor(conn)
        
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
            cursor.execute("SELECT * FROM weekly_goals WHERE user_id = %s AND week_start = %s ORDER BY created_at DESC", (user_id, week_start))
        else:
            cursor.execute("SELECT * FROM weekly_goals WHERE user_id = ? AND week_start = ? ORDER BY created_at DESC", (user_id, week_start))
        
        goals = []
        for row in cursor.fetchall():
            goal_type = row['goal_type'] if hasattr(row, 'keys') else row[3]
            goal_config = WEEKLY_GOAL_TYPES.get(goal_type, {})
            
            goals.append({
                'goal_type': goal_type,
                'goal_name': goal_config.get('name', goal_type),
                'icon': goal_config.get('icon', '🎯'),
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
    recent_lessons = data.get("recent_lessons", [])
    
    try:
        user_data = verify_token(token)
        user_id = user_data["user_id"]
        
        conn = get_db()
        cursor = get_cursor(conn)
        
        # Get user info - USING full_name
        if USE_POSTGRES:
            cursor.execute("SELECT full_name, reading_level FROM users WHERE id = %s", (user_id,))
        else:
            cursor.execute("SELECT full_name, reading_level FROM users WHERE id = ?", (user_id,))
        
        user_row = cursor.fetchone()
        user_name = user_row['full_name'] if hasattr(user_row, 'keys') else user_row[0]
        current_level = user_row['reading_level'] if hasattr(user_row, 'keys') else user_row[1]
        
        # Count existing essays
        if USE_POSTGRES:
            cursor.execute("SELECT COUNT(*) FROM user_essays WHERE user_id = %s", (user_id,))
        else:
            cursor.execute("SELECT COUNT(*) FROM user_essays WHERE user_id = ?", (user_id,))
        
        result = cursor.fetchone()
        essay_number = (result['count'] if hasattr(result, 'keys') else result[0]) + 1
        
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
            model="gpt-4o",
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
    """Update user's reading level and increase LESSON word count by 100"""
    conn = get_db()
    cursor = get_cursor(conn)
    
    try:
        # Get current level and word counts
        if USE_POSTGRES:
            cursor.execute(
                """SELECT reading_level, essay_word_count_requirement, 
                   word_count_min, word_count_max 
                   FROM users WHERE id = %s""", 
                (user_id,)
            )
        else:
            cursor.execute(
                """SELECT reading_level, essay_word_count_requirement, 
                   word_count_min, word_count_max 
                   FROM users WHERE id = ?""", 
                (user_id,)
            )
        
        result = cursor.fetchone()
        old_level = result['reading_level'] if hasattr(result, 'keys') else result[0]
        current_essay_words = result['essay_word_count_requirement'] if hasattr(result, 'keys') else result[1]
        current_min = result['word_count_min'] if hasattr(result, 'keys') else result[2]
        current_max = result['word_count_max'] if hasattr(result, 'keys') else result[3]
        
        # Set defaults if not set
        if not current_essay_words:
            level_defaults = {'beginner': 25, 'intermediate': 50, 'advanced': 75}
            current_essay_words = level_defaults.get(old_level, 25)
        
        if not current_min or not current_max:
            current_min = 50
            current_max = 75
        
        # Increase LESSON word count by 100
        new_min = current_min + 100
        new_max = current_max + 100
        
        # Increase ESSAY word count by 25
        new_essay_words = current_essay_words + 25
        
        # Update user level and word counts
        if USE_POSTGRES:
            cursor.execute(
                """UPDATE users 
                   SET reading_level = %s, 
                       essay_word_count_requirement = %s,
                       word_count_min = %s,
                       word_count_max = %s
                   WHERE id = %s""",
                (new_level, new_essay_words, new_min, new_max, user_id)
            )
        else:
            cursor.execute(
                """UPDATE users 
                   SET reading_level = ?, 
                       essay_word_count_requirement = ?,
                       word_count_min = ?,
                       word_count_max = ?
                   WHERE id = ?""",
                (new_level, new_essay_words, new_min, new_max, user_id)
            )
        
        # Log adjustment
        adjustment_log = (
            f"{reason} | "
            f"Lesson words: {current_min}-{current_max} → {new_min}-{new_max} | "
            f"Essay words: {current_essay_words} → {new_essay_words}"
        )
        
        if USE_POSTGRES:
            cursor.execute(
                """INSERT INTO difficulty_adjustments 
                   (user_id, essay_id, previous_level, new_level, reason)
                   VALUES (%s, %s, %s, %s, %s)""",
                (user_id, essay_id, old_level, new_level, adjustment_log)
            )
        else:
            cursor.execute(
                """INSERT INTO difficulty_adjustments 
                   (user_id, essay_id, previous_level, new_level, reason)
                   VALUES (?, ?, ?, ?, ?)""",
                (user_id, essay_id, old_level, new_level, adjustment_log)
            )
        
        conn.commit()
        conn.close()
        
        print(f"✓ User {user_id} level updated: {old_level} → {new_level}")
        print(f"✓ Lesson word count: {current_min}-{current_max} → {new_min}-{new_max}")
        print(f"✓ Essay word count: {current_essay_words} → {new_essay_words}")
        
    except Exception as e:
        print(f"Error updating difficulty: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
        conn.close()

def create_admin_alert(user_id, essay_id, alert_type, priority, message, details):
    """Create admin alert"""
    conn = get_db()
    cursor = get_cursor(conn)
    
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
                """SELECT COUNT(*) as count FROM session_logs 
                   WHERE user_id = %s AND completion_status = 'completed'""",
                (user_id,)
            )
        else:
            cursor.execute(
                """SELECT COUNT(*) as count FROM session_logs 
                   WHERE user_id = ? AND completion_status = 'completed'""",
                (user_id,)
            )
        
        result = cursor.fetchone()
        total_lessons = result['count'] if hasattr(result, 'keys') else result[0] if result else 0
        
        print(f"✓ User {user_id} has completed {total_lessons} lessons")
        
        # Count completed essays
        if USE_POSTGRES:
            cursor.execute("SELECT COUNT(*) as count FROM user_essays WHERE user_id = %s", (user_id,))
        else:
            cursor.execute("SELECT COUNT(*) as count FROM user_essays WHERE user_id = ?", (user_id,))
        
        result = cursor.fetchone()
        total_essays = result['count'] if hasattr(result, 'keys') else result[0] if result else 0
        
        print(f"✓ User {user_id} has completed {total_essays} essays")
        
        # Essay is due every 3 lessons
        expected_essays = total_lessons // 3
        essay_due = (total_lessons > 0 and 
                     total_lessons % 3 == 0 and 
                     total_essays < expected_essays)
        
        print(f"✓ Essay due: {essay_due}")
        
        # If essay is due, get last 3 lessons from passages table
        recent_lessons = []
        if essay_due:
            try:
                if USE_POSTGRES:
                    cursor.execute(
                        """SELECT p.id, p.title, p.content
                           FROM session_logs sl
                           JOIN passages p ON sl.passage_id = p.id
                           WHERE sl.user_id = %s 
                           AND sl.completion_status = 'completed'
                           ORDER BY sl.completed_at DESC
                           LIMIT 3""",
                        (user_id,)
                    )
                else:
                    cursor.execute(
                        """SELECT p.id, p.title, p.content
                           FROM session_logs sl
                           JOIN passages p ON sl.passage_id = p.id
                           WHERE sl.user_id = ? 
                           AND sl.completion_status = 'completed'
                           ORDER BY sl.completed_at DESC
                           LIMIT 3""",
                        (user_id,)
                    )
                
                rows = cursor.fetchall()
                
                for row in rows:
                    recent_lessons.append({
                        'id': row['id'] if hasattr(row, 'keys') else row[0],
                        'title': row['title'] if hasattr(row, 'keys') else row[1],
                        'content': (row['content'] if hasattr(row, 'keys') else row[2])[:500] if (row['content'] if hasattr(row, 'keys') else row[2]) else ''
                    })
                
                print(f"✓ Found {len(recent_lessons)} lessons from passages table")
                
            except Exception as e:
                print(f"⚠ Error getting lesson titles: {e}")
                import traceback
                traceback.print_exc()
        
        # If we still don't have 3 lessons, use generic placeholders
        if essay_due and len(recent_lessons) < 3:
            print(f"⚠ Only found {len(recent_lessons)} lessons, using placeholders")
            while len(recent_lessons) < 3:
                recent_lessons.append({
                    'id': len(recent_lessons),
                    'title': f'Recent Lesson {len(recent_lessons) + 1}',
                    'content': 'A lesson you recently completed.'
                })
        
        conn.close()
        
        print(f"✓ Returning {len(recent_lessons)} lessons")
        if recent_lessons:
            for i, lesson in enumerate(recent_lessons):
                print(f"  Lesson {i+1}: {lesson['title']}")
        
        return {
            "success": True,
            "essay_due": essay_due,
            "total_lessons": total_lessons,
            "total_essays": total_essays,
            "lesson_count_for_next_essay": total_lessons,
            "recent_lessons": recent_lessons
        }
        
    except Exception as e:
        print(f"✗ ERROR in check_essay_due: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    
@app.get("/api/essay/word-count-requirement")
async def get_word_count_requirement(token: str):
    """Get current essay word count requirement for user"""
    try:
        user_data = verify_token(token)
        user_id = user_data["user_id"]
        
        conn = get_db()
        cursor = conn.cursor()
        
        if USE_POSTGRES:
            cursor.execute(
                "SELECT essay_word_count_requirement, reading_level FROM users WHERE id = %s",
                (user_id,)
            )
        else:
            cursor.execute(
                "SELECT essay_word_count_requirement, reading_level FROM users WHERE id = ?",
                (user_id,)
            )
        
        result = cursor.fetchone()
        word_count = result['essay_word_count_requirement'] if hasattr(result, 'keys') else result[0]
        reading_level = result['reading_level'] if hasattr(result, 'keys') else result[1]
        
        # Use correct defaults: 25, 50, 75
        if not word_count:
            level_defaults = {'beginner': 25, 'intermediate': 50, 'advanced': 75}
            word_count = level_defaults.get(reading_level, 25)
        
        conn.close()
        
        return {
            "success": True,
            "word_count_requirement": word_count,
            "reading_level": reading_level
        }
        
    except Exception as e:
        print(f"Error getting word count: {e}")
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
        cursor = get_cursor(conn)
        
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
        cursor = get_cursor(conn)
        
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
        cursor = get_cursor(conn)
        
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
        cursor = get_cursor(conn)
        
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
        cursor = get_cursor(conn)
        
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
        cursor = get_cursor(conn)
        
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
        cursor = get_cursor(conn)
        
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
    
# ============================================
# AI TUTOR ENDPOINTS
# ============================================

@app.post("/api/tutor/message")
async def get_tutor_message(request: Request):
    """Generate personalized AI tutor message with voice-friendly text"""
    try:
        data = await request.json()
        token = data.get('token')
        context = data.get('context')  # 'greeting', 'instruction', 'success', 'struggle', 'encouragement', 'milestone'
        student_name = data.get('student_name', 'there')
        score = data.get('score')
        lesson_number = data.get('lesson_number')
        
        # Verify token
        user_data = verify_token(token)
        
        # Generate personalized message based on context
        messages = generate_tutor_message(context, student_name, score, lesson_number)
        
        return {
            "success": True,
            "message": messages['text'] or "",
            "emotion": messages['emotion']  # happy, encouraging, celebrating, thoughtful
        }
        
    except Exception as e:
        print(f"Error generating tutor message: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


def generate_tutor_message(context, student_name, score=None, lesson_number=None):
    """Generate personalized tutor messages optimized for text-to-speech"""
    
    # Get first name only for more natural speech
    first_name = student_name.split()[0] if student_name and student_name != 'there' else student_name
    
    if context == "greeting":
        return {"text": "", "emotion": "neutral"}

    
    if context == 'greeting':
        messages = [
            f"Hello {first_name}! I'm so excited to learn with you today!",
            f"Welcome back, {first_name}! Ready to explore something amazing?",
            f"Hi {first_name}! Great to see you! Let's make today's lesson awesome!",
            f"Hey {first_name}! I'm here to help you succeed. Let's get started!"
        ]
        emotion = 'happy'
        
    elif context == 'instruction':
        messages = [
            f"{first_name}, read this passage carefully. Take your time and enjoy the story! Then we'll check your understanding.",
            f"Here's your next reading for today, {first_name}. Focus on the main ideas and interesting details. You've got this!",
            f"{first_name}! Let's dive into this passage together, Read at your own pace, and I'll be here when you're ready for questions.",
            f"{first_name}, It's time to read! Remember, it's not a race. Understanding is what matters most!"
        ]
        emotion = 'encouraging'
        
    elif context == 'success':
        if score and score >= 80:
            messages = [
                f"Outstanding work, {first_name}! You scored {score} percent! You're really mastering this!",
                f"Wow {first_name}! {score} percent is fantastic! You understood that passage perfectly!",
                f"Incredible, {first_name}! {score} percent! Your hard work is really paying off! Keep it up!",
                f"Amazing job, {first_name}! {score} percent! I'm so proud of your progress!"
            ]
            emotion = 'celebrating'
        else:
            messages = [
                f"Good effort, {first_name}! You scored {score} percent. Every lesson makes you stronger!",
                f"Nice work, {first_name}! {score} percent shows you're learning. Keep practicing!",
                f"You're doing great, {first_name}! {score} percent is progress. Each lesson builds your skills!",
                f"Well done, {first_name}! {score} percent means you're on the right track. Keep going!"
            ]
            emotion = 'encouraging'
            
    elif context == 'struggle':
        messages = [
            f"Hey {first_name}, I know this one was challenging. That's okay! Challenges help us grow. Want to try another passage?",
            f"{first_name}, even the best readers find some passages tricky. The important thing is you're trying! Let's keep practicing.",
            f"Don't worry, {first_name}! Learning has ups and downs. You're doing better than you think. Keep going!",
            f"{first_name}, remember: every expert was once a beginner. You're building important skills. I believe in you!"
        ]
        emotion = 'encouraging'
        
    elif context == 'encouragement':
        messages = [
            f"You're making real progress, {first_name}! Every word you read makes you a better reader!",
            f"Keep up the fantastic work, {first_name}! You're building skills that will help you forever!",
            f"{first_name}, I can see how much you're improving! You should be proud of yourself!",
            f"You're doing amazing, {first_name}! Each lesson brings you closer to your goals!"
        ]
        emotion = 'happy'
        
    elif context == 'milestone':
        if lesson_number and lesson_number % 10 == 0:
            messages = [
                f"Wow {first_name}! You've completed {lesson_number} lessons! That's incredible dedication!",
                f"Amazing milestone, {first_name}! {lesson_number} lessons shows real commitment to learning!",
                f"{first_name}, {lesson_number} lessons completed! You're unstoppable! Keep this momentum going!"
            ]
        else:
            messages = [
                f"Great progress, {first_name}! Lesson {lesson_number} done! You're on a roll!",
                f"Another lesson complete, {first_name}! That's lesson {lesson_number}! Keep it up!",
                f"Excellent, {first_name}! Lesson {lesson_number} is behind you! Onward and upward!"
            ]
        emotion = 'celebrating'
    
    else:
        messages = [f"Great to have you here, {first_name}! Let's learn together!"]
        emotion = 'happy'
    
    return {
        'text': random.choice(messages),
        'emotion': emotion
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