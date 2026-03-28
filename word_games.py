# word_games.py - Add this to your FastAPI backend

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timedelta
import sqlite3

router = APIRouter(prefix="/api/word-games", tags=["word-games"])

# ========================================
# REQUEST/RESPONSE MODELS
# ========================================

class VocabularyWord(BaseModel):
    word: str
    definition: str
    sentence: str

class MarkWordsUsedRequest(BaseModel):
    game_type: str
    words: List[str]

class CompleteGameRequest(BaseModel):
    game_type: str
    score: int
    rounds_completed: int
    time_seconds: int

# ========================================
# DATABASE HELPERS
# ========================================

def get_db():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

# ========================================
# ENDPOINTS
# ========================================

@router.get("/vocabulary")
async def get_game_vocabulary(user_id: int = Depends(get_current_user)):
    """
    Get ALL vocabulary from user's completed lessons.
    Returns 100+ words to ensure variety across many game rounds.
    """
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Get vocabulary from user's completed lessons
        cursor.execute("""
            SELECT DISTINCT 
                v.word,
                v.definition,
                v.example_sentence as sentence
            FROM vocabulary v
            JOIN lesson_vocabulary lv ON v.id = lv.vocabulary_id
            JOIN user_lessons ul ON lv.lesson_id = ul.lesson_id
            WHERE ul.user_id = ? 
            AND ul.completed = 1
            ORDER BY RANDOM()
            LIMIT 200
        """, (user_id,))
        
        rows = cursor.fetchall()
        
        vocabulary = [
            {
                "word": row["word"],
                "definition": row["definition"],
                "sentence": row["sentence"]
            }
            for row in rows
        ]
        
        # If user has less than 20 words, add some starter vocabulary
        if len(vocabulary) < 20:
            cursor.execute("""
                SELECT word, definition, example_sentence as sentence
                FROM vocabulary
                WHERE difficulty = 'beginner'
                ORDER BY RANDOM()
                LIMIT ?
            """, (20 - len(vocabulary),))
            
            starter_words = cursor.fetchall()
            vocabulary.extend([
                {
                    "word": row["word"],
                    "definition": row["definition"],
                    "sentence": row["sentence"]
                }
                for row in starter_words
            ])
        
        return {
            "vocabulary": vocabulary,
            "count": len(vocabulary)
        }
        
    finally:
        conn.close()


@router.get("/used-words")
async def get_used_words(
    game_type: str,
    user_id: int = Depends(get_current_user)
):
    """
    Get words user has already seen in this game type.
    Only returns words from last 7 days to allow eventual reuse.
    """
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT word 
            FROM game_used_words
            WHERE user_id = ? 
            AND game_type = ?
            AND created_at > datetime('now', '-7 days')
        """, (user_id, game_type))
        
        rows = cursor.fetchall()
        used_words = [row["word"] for row in rows]
        
        return {
            "used_words": used_words,
            "count": len(used_words)
        }
        
    finally:
        conn.close()


@router.post("/mark-used")
async def mark_words_used(
    request: MarkWordsUsedRequest,
    user_id: int = Depends(get_current_user)
):
    """
    Mark words as used so they don't repeat immediately.
    Uses INSERT OR IGNORE to handle duplicates gracefully.
    """
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        for word in request.words:
            cursor.execute("""
                INSERT OR IGNORE INTO game_used_words 
                (user_id, game_type, word, created_at)
                VALUES (?, ?, ?, datetime('now'))
            """, (user_id, request.game_type, word.lower()))
        
        conn.commit()
        
        return {
            "success": True,
            "marked": len(request.words)
        }
        
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.post("/reset-used-words")
async def reset_used_words(
    game_type: str,
    user_id: int = Depends(get_current_user)
):
    """
    Reset used words when all vocabulary has been seen.
    Called automatically by frontend when needed.
    """
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            DELETE FROM game_used_words
            WHERE user_id = ? AND game_type = ?
        """, (user_id, game_type))
        
        conn.commit()
        
        return {
            "success": True,
            "message": "Used words reset"
        }
        
    finally:
        conn.close()


@router.post("/complete")
async def complete_game(
    request: CompleteGameRequest,
    user_id: int = Depends(get_current_user)
):
    """
    Record game completion and update user statistics.
    Also checks for and awards new badges.
    """
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Insert game completion
        cursor.execute("""
            INSERT INTO game_completions 
            (user_id, game_type, score, rounds_completed, time_seconds, completed_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
        """, (
            user_id,
            request.game_type,
            request.score,
            request.rounds_completed,
            request.time_seconds
        ))
        
        # Update user stats
        cursor.execute("""
            UPDATE users
            SET 
                games_played = COALESCE(games_played, 0) + 1,
                total_game_score = COALESCE(total_game_score, 0) + ?
            WHERE id = ?
        """, (request.score, user_id))
        
        conn.commit()
        
        # Check for new badges
        new_badges = check_and_award_game_badges(user_id, cursor)
        
        conn.commit()
        
        return {
            "success": True,
            "new_badges": new_badges
        }
        
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/stats")
async def get_game_stats(user_id: int = Depends(get_current_user)):
    """
    Get user's game statistics for display on Progress page.
    """
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT 
                COUNT(*) as games_played,
                COALESCE(SUM(score), 0) as total_score,
                COALESCE(AVG(score), 0) as avg_score,
                COALESCE(MAX(score), 0) as high_score,
                COALESCE(SUM(time_seconds), 0) as total_time
            FROM game_completions
            WHERE user_id = ?
        """, (user_id,))
        
        stats = cursor.fetchone()
        
        # Get recent games
        cursor.execute("""
            SELECT game_type, score, rounds_completed, completed_at
            FROM game_completions
            WHERE user_id = ?
            ORDER BY completed_at DESC
            LIMIT 10
        """, (user_id,))
        
        recent = cursor.fetchall()
        
        return {
            "games_played": stats["games_played"],
            "total_score": stats["total_score"],
            "avg_score": round(stats["avg_score"], 1),
            "high_score": stats["high_score"],
            "total_time_minutes": round(stats["total_time"] / 60, 1),
            "recent_games": [
                {
                    "game_type": row["game_type"],
                    "score": row["score"],
                    "rounds": row["rounds_completed"],
                    "date": row["completed_at"]
                }
                for row in recent
            ]
        }
        
    finally:
        conn.close()


# ========================================
# HELPER FUNCTIONS
# ========================================

def check_and_award_game_badges(user_id: int, cursor) -> List[str]:
    """
    Check if user has earned any new game-related badges.
    Returns list of newly awarded badge types.
    """
    new_badges = []
    
    # Get user's game stats
    cursor.execute("""
        SELECT COUNT(*) as games_played
        FROM game_completions
        WHERE user_id = ?
    """, (user_id,))
    
    games_played = cursor.fetchone()["games_played"]
    
    # Badge: First Game (1 game)
    if games_played == 1:
        cursor.execute("""
            INSERT OR IGNORE INTO user_badges (user_id, badge_type, earned_at)
            VALUES (?, 'first_game', datetime('now'))
        """, (user_id,))
        if cursor.rowcount > 0:
            new_badges.append('first_game')
    
    # Badge: Game Enthusiast (10 games)
    if games_played == 10:
        cursor.execute("""
            INSERT OR IGNORE INTO user_badges (user_id, badge_type, earned_at)
            VALUES (?, 'game_enthusiast', datetime('now'))
        """, (user_id,))
        if cursor.rowcount > 0:
            new_badges.append('game_enthusiast')
    
    # Badge: Game Master (50 games)
    if games_played == 50:
        cursor.execute("""
            INSERT OR IGNORE INTO user_badges (user_id, badge_type, earned_at)
            VALUES (?, 'game_master', datetime('now'))
        """, (user_id,))
        if cursor.rowcount > 0:
            new_badges.append('game_master')
    
    # Badge: Perfect Score (score >= 500 in one game)
    cursor.execute("""
        SELECT MAX(score) as max_score
        FROM game_completions
        WHERE user_id = ?
    """, (user_id,))
    
    max_score = cursor.fetchone()["max_score"]
    if max_score and max_score >= 500:
        cursor.execute("""
            INSERT OR IGNORE INTO user_badges (user_id, badge_type, earned_at)
            VALUES (?, 'perfect_score', datetime('now'))
        """, (user_id,))
        if cursor.rowcount > 0:
            new_badges.append('perfect_score')
    
    return new_badges


def get_current_user():
    """
    Extract user ID from JWT token.
    Replace with your actual auth logic.
    """
    # This is a placeholder - implement based on your auth system
    from fastapi import Header
    def inner(authorization: str = Header(None)):
        if not authorization:
            raise HTTPException(status_code=401, detail="Not authenticated")
        # Decode JWT and extract user_id
        # return user_id
        pass
    return inner