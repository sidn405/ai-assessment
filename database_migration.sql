-- MFS Literacy Platform - Phase 2 Database Migration
-- Run this in Railway PostgreSQL Data tab

-- ============================================
-- STEP 1: Extend Users Table
-- ============================================

ALTER TABLE users ADD COLUMN IF NOT EXISTS age_band VARCHAR(20);
ALTER TABLE users ADD COLUMN IF NOT EXISTS grade_band VARCHAR(20);
ALTER TABLE users ADD COLUMN IF NOT EXISTS interest_tags TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS level_estimate VARCHAR(20);
ALTER TABLE users ADD COLUMN IF NOT EXISTS words_per_session INTEGER DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS total_passages_read INTEGER DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS comprehension_score REAL DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_active TIMESTAMP;

-- ============================================
-- STEP 2: Create Passages Table
-- ============================================

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
    metadata TEXT,
    FOREIGN KEY (created_by) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_passages_difficulty ON passages(difficulty_level);
CREATE INDEX IF NOT EXISTS idx_passages_word_count ON passages(word_count);
CREATE INDEX IF NOT EXISTS idx_passages_approved ON passages(approved);
CREATE INDEX IF NOT EXISTS idx_passages_source ON passages(source);

-- ============================================
-- STEP 3: Create Session Logs Table
-- ============================================

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
);

CREATE INDEX IF NOT EXISTS idx_session_user ON session_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_session_passage ON session_logs(passage_id);
CREATE INDEX IF NOT EXISTS idx_session_completed ON session_logs(completed_at);
CREATE INDEX IF NOT EXISTS idx_session_status ON session_logs(completion_status);

-- ============================================
-- STEP 4: Create Comprehension Questions Table
-- ============================================

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
);

CREATE INDEX IF NOT EXISTS idx_questions_passage ON passage_questions(passage_id);
CREATE INDEX IF NOT EXISTS idx_questions_type ON passage_questions(question_type);

-- ============================================
-- STEP 5: Create Writing Exercises Table
-- ============================================

CREATE TABLE IF NOT EXISTS writing_exercises (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    passage_id INTEGER,
    prompt TEXT NOT NULL,
    user_response TEXT,
    ai_feedback TEXT,
    score REAL,
    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    revised_response TEXT,
    revision_submitted_at TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (passage_id) REFERENCES passages(id)
);

CREATE INDEX IF NOT EXISTS idx_writing_user ON writing_exercises(user_id);
CREATE INDEX IF NOT EXISTS idx_writing_submitted ON writing_exercises(submitted_at);

-- ============================================
-- STEP 6: Create Vocabulary Tracker Table
-- ============================================

CREATE TABLE IF NOT EXISTS vocabulary_tracker (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    word VARCHAR(100) NOT NULL,
    definition TEXT,
    context_passage_id INTEGER,
    encountered_count INTEGER DEFAULT 1,
    mastered BOOLEAN DEFAULT FALSE,
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_reviewed TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (context_passage_id) REFERENCES passages(id),
    UNIQUE(user_id, word)
);

CREATE INDEX IF NOT EXISTS idx_vocab_user ON vocabulary_tracker(user_id);
CREATE INDEX IF NOT EXISTS idx_vocab_word ON vocabulary_tracker(word);
CREATE INDEX IF NOT EXISTS idx_vocab_mastered ON vocabulary_tracker(mastered);

-- ============================================
-- STEP 7: Create Discussions Table
-- ============================================

CREATE TABLE IF NOT EXISTS discussions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    passage_id INTEGER,
    message_role VARCHAR(20) NOT NULL,
    message_content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (passage_id) REFERENCES passages(id)
);

CREATE INDEX IF NOT EXISTS idx_discussion_user ON discussions(user_id);
CREATE INDEX IF NOT EXISTS idx_discussion_passage ON discussions(passage_id);
CREATE INDEX IF NOT EXISTS idx_discussion_created ON discussions(created_at);

-- ============================================
-- STEP 8: Insert Sample Passages (Optional)
-- ============================================

-- Sample beginner passage
INSERT INTO passages (title, content, source, topic_tags, word_count, readability_score, flesch_ease, difficulty_level, estimated_minutes, approved, created_by)
VALUES (
    'The Amazing Sun',
    'The sun is a star. It is very big and very hot. The sun gives us light during the day. It also gives us warmth. Plants need the sun to grow. Animals need the sun too. We should be thankful for the sun. Without the sun, there would be no life on Earth. The sun is about 93 million miles away from Earth. That is very far! Even though it is far away, we can still feel its heat and see its light.',
    'PD',
    '["science", "nature", "space"]',
    85,
    3.5,
    85.0,
    'beginner',
    1,
    true,
    1
) ON CONFLICT DO NOTHING;

-- Sample intermediate passage  
INSERT INTO passages (title, content, source, topic_tags, word_count, readability_score, flesch_ease, difficulty_level, estimated_minutes, approved, created_by)
VALUES (
    'How Computers Work',
    'Computers are amazing machines that have changed our world. Inside every computer is something called a processor, which is like the brain of the computer. The processor follows instructions very quickly - millions of times per second! Computers also have memory, which stores information temporarily while you work. The hard drive is where files are saved permanently. When you type on the keyboard or move the mouse, the computer receives your input and processes it. Then it shows the results on the screen. Modern computers can do many things at once, from playing music to editing videos. Understanding how computers work helps us use them more effectively and appreciate the technology that powers our digital world.',
    'AI',
    '["technology", "computers", "education"]',
    125,
    7.2,
    65.0,
    'intermediate',
    2,
    true,
    1
) ON CONFLICT DO NOTHING;

-- ============================================
-- STEP 9: Verify Migration
-- ============================================

-- Check that all tables exist
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
ORDER BY table_name;

-- Check row counts
SELECT 'users' as table_name, COUNT(*) as row_count FROM users
UNION ALL
SELECT 'passages', COUNT(*) FROM passages
UNION ALL
SELECT 'session_logs', COUNT(*) FROM session_logs
UNION ALL
SELECT 'passage_questions', COUNT(*) FROM passage_questions
UNION ALL
SELECT 'writing_exercises', COUNT(*) FROM writing_exercises
UNION ALL
SELECT 'vocabulary_tracker', COUNT(*) FROM vocabulary_tracker
UNION ALL
SELECT 'discussions', COUNT(*) FROM discussions;

-- ============================================
-- MIGRATION COMPLETE!
-- ============================================

-- GAMIFICATION SYSTEM DATABASE MIGRATION
-- Run this to add points, badges, goals, and streaks

-- Points and rewards tables
