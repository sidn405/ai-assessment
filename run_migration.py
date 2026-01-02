"""
Run this Python script locally to create database tables directly
No need for Railway UI or endpoints
"""

import psycopg2
import sys

# Get your DATABASE_URL from Railway
# Railway → PostgreSQL → Variables tab → Copy DATABASE_URL value
DATABASE_URL = ""

# REPLACE THE DATABASE_URL ABOVE WITH YOUR ACTUAL VALUE FROM RAILWAY

def run_migration():
    print("=" * 60)
    print("RUNNING PHASE 2 DATABASE MIGRATION")
    print("=" * 60)
    
    try:
        print("\nConnecting to database...")
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        print("✓ Connected successfully")
        
        # Create passages table
        print("\nCreating passages table...")
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
        conn.commit()
        print("✓ passages table created")
        
        # Create indexes
        print("Creating indexes for passages...")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_passages_difficulty ON passages(difficulty_level)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_passages_word_count ON passages(word_count)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_passages_approved ON passages(approved)")
        conn.commit()
        print("✓ passages indexes created")
        
        # Create passage_questions table
        print("\nCreating passage_questions table...")
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
        print("✓ passage_questions table created")
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_questions_passage ON passage_questions(passage_id)")
        conn.commit()
        print("✓ passage_questions index created")
        
        # Create session_logs table
        print("\nCreating session_logs table...")
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
        print("✓ session_logs table created")
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_session_user ON session_logs(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_session_passage ON session_logs(passage_id)")
        conn.commit()
        print("✓ session_logs indexes created")
        
        # Create writing_exercises table
        print("\nCreating writing_exercises table...")
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
        print("✓ writing_exercises table created")
        
        # Create vocabulary_tracker table
        print("\nCreating vocabulary_tracker table...")
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
        print("✓ vocabulary_tracker table created")
        
        # Create discussions table
        print("\nCreating discussions table...")
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
        print("✓ discussions table created")
        
        # Verify all tables
        print("\nVerifying tables...")
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('passages', 'passage_questions', 'session_logs', 
                               'writing_exercises', 'vocabulary_tracker', 'discussions')
            ORDER BY table_name
        """)
        
        tables = [row[0] for row in cursor.fetchall()]
        
        print("\n" + "=" * 60)
        print("✓✓✓ MIGRATION COMPLETE ✓✓✓")
        print("=" * 60)
        print(f"\nTables created ({len(tables)}):")
        for table in tables:
            print(f"  ✓ {table}")
        
        if len(tables) == 6:
            print("\n✓ All Phase 2 tables successfully created!")
        else:
            print(f"\n⚠ Warning: Expected 6 tables, but only created {len(tables)}")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    if "YOUR_PASSWORD" in DATABASE_URL:
        print("=" * 60)
        print("ERROR: Please update DATABASE_URL in this script!")
        print("=" * 60)
        print("\nSteps:")
        print("1. Go to Railway Dashboard")
        print("2. Click PostgreSQL service")
        print("3. Click 'Variables' tab")
        print("4. Copy the DATABASE_URL value")
        print("5. Replace the DATABASE_URL at the top of this script")
        print("6. Run: python run_migration.py")
        sys.exit(1)
    
    success = run_migration()
    sys.exit(0 if success else 1)