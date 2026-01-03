-- COMPREHENSIVE ESSAY ASSESSMENT SYSTEM - DATABASE MIGRATION

-- User essays table
CREATE TABLE IF NOT EXISTS user_essays (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    essay_number INTEGER NOT NULL, -- 1st essay, 2nd essay, etc.
    lesson_count INTEGER NOT NULL, -- Completed after how many lessons (3, 6, 9, etc.)
    essay_text TEXT NOT NULL,
    word_count INTEGER,
    
    -- AI Evaluation
    comprehension_level VARCHAR(50), -- excellent, good, adequate, needs_help
    comprehension_score INTEGER, -- 0-100
    difficulty_recommendation VARCHAR(50), -- advance, stay, support_needed
    ai_feedback TEXT,
    
    -- Related lessons
    lesson_ids TEXT, -- JSON array of last 3 lesson IDs
    lesson_topics TEXT, -- JSON array of topics covered
    
    -- Admin tracking
    needs_admin_review BOOLEAN DEFAULT FALSE,
    admin_notified BOOLEAN DEFAULT FALSE,
    admin_reviewed BOOLEAN DEFAULT FALSE,
    admin_notes TEXT,
    
    -- Gamification
    points_awarded INTEGER DEFAULT 0,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TIMESTAMP,
    
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_user_essays_user ON user_essays(user_id);
CREATE INDEX IF NOT EXISTS idx_user_essays_needs_review ON user_essays(needs_admin_review);
CREATE INDEX IF NOT EXISTS idx_user_essays_created ON user_essays(created_at);

-- Difficulty adjustments log
CREATE TABLE IF NOT EXISTS difficulty_adjustments (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    essay_id INTEGER,
    previous_level VARCHAR(50),
    new_level VARCHAR(50),
    reason TEXT,
    adjusted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (essay_id) REFERENCES user_essays(id)
);

CREATE INDEX IF NOT EXISTS idx_difficulty_adjustments_user ON difficulty_adjustments(user_id);

-- Admin alerts table
CREATE TABLE IF NOT EXISTS admin_alerts (
    id SERIAL PRIMARY KEY,
    alert_type VARCHAR(50) NOT NULL, -- student_needs_help, low_comprehension, essay_review
    user_id INTEGER NOT NULL,
    essay_id INTEGER,
    priority VARCHAR(20) DEFAULT 'normal', -- low, normal, high, urgent
    message TEXT NOT NULL,
    details TEXT, -- JSON with additional context
    
    is_read BOOLEAN DEFAULT FALSE,
    is_resolved BOOLEAN DEFAULT FALSE,
    resolved_by INTEGER,
    resolved_at TIMESTAMP,
    resolution_notes TEXT,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (essay_id) REFERENCES user_essays(id),
    FOREIGN KEY (resolved_by) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_admin_alerts_type ON admin_alerts(alert_type);
CREATE INDEX IF NOT EXISTS idx_admin_alerts_read ON admin_alerts(is_read);
CREATE INDEX IF NOT EXISTS idx_admin_alerts_resolved ON admin_alerts(is_resolved);
CREATE INDEX IF NOT EXISTS idx_admin_alerts_created ON admin_alerts(created_at);