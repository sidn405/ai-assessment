-- migration_word_games.sql
-- Run this to add word games tables to your database

-- ========================================
-- GAME USED WORDS TABLE
-- ========================================
CREATE TABLE IF NOT EXISTS game_used_words (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    game_type TEXT NOT NULL,  -- 'word-search', 'word-scramble', 'word-match', etc.
    word TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(user_id, game_type, word)
);

CREATE INDEX IF NOT EXISTS idx_game_used_words_user 
ON game_used_words(user_id, game_type);

CREATE INDEX IF NOT EXISTS idx_game_used_words_date 
ON game_used_words(created_at);

-- ========================================
-- GAME COMPLETIONS TABLE
-- ========================================
CREATE TABLE IF NOT EXISTS game_completions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    game_type TEXT NOT NULL,
    score INTEGER NOT NULL,
    rounds_completed INTEGER NOT NULL,
    time_seconds INTEGER NOT NULL,
    completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_game_completions_user 
ON game_completions(user_id, game_type);

CREATE INDEX IF NOT EXISTS idx_game_completions_date 
ON game_completions(user_id, completed_at DESC);

-- ========================================
-- UPDATE USERS TABLE
-- ========================================
-- Add game statistics columns to users table
ALTER TABLE users ADD COLUMN games_played INTEGER DEFAULT 0;
ALTER TABLE users ADD COLUMN total_game_score INTEGER DEFAULT 0;

-- ========================================
-- ADD NEW BADGE TYPES
-- ========================================
-- If you have a badges table, add these badge definitions
-- If not, these will be defined in your BADGES constant in frontend

-- Badge: First Game
-- INSERT INTO badges (type, name, icon, description, points) 
-- VALUES ('first_game', 'First Game', '🎮', 'Complete your first word game', 10);

-- Badge: Game Enthusiast  
-- INSERT INTO badges (type, name, icon, description, points)
-- VALUES ('game_enthusiast', 'Game Enthusiast', '🎯', 'Complete 10 word games', 25);

-- Badge: Game Master
-- INSERT INTO badges (type, name, icon, description, points)
-- VALUES ('game_master', 'Game Master', '👑', 'Complete 50 word games', 50);

-- Badge: Perfect Score
-- INSERT INTO badges (type, name, icon, description, points)
-- VALUES ('perfect_score', 'Perfect Score', '⭐', 'Score 500+ points in one game', 30);

-- ========================================
-- CLEANUP OLD DATA (OPTIONAL)
-- ========================================
-- Remove used words older than 30 days to keep table small
-- Run this periodically as a maintenance job:
-- DELETE FROM game_used_words WHERE created_at < datetime('now', '-30 days');