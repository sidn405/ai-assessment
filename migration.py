import psycopg2
import os

# Get your DATABASE_URL from Railway
DATABASE_URL = os.getenv('DATABASE_URL')

if not DATABASE_URL:
    print("❌ DATABASE_URL not found in environment")
    print("Set it with: $env:DATABASE_URL='your_postgres_url'")
    exit(1)

# Migration SQL
migration_sql = """
-- Game used words table
CREATE TABLE IF NOT EXISTS game_used_words (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    game_type VARCHAR(50) NOT NULL,
    word VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(user_id, game_type, word)
);

CREATE INDEX IF NOT EXISTS idx_game_used_words_user ON game_used_words(user_id, game_type);
CREATE INDEX IF NOT EXISTS idx_game_used_words_date ON game_used_words(created_at);

-- Game completions table
CREATE TABLE IF NOT EXISTS game_completions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    game_type VARCHAR(50) NOT NULL,
    score INTEGER NOT NULL,
    rounds_completed INTEGER NOT NULL,
    time_seconds INTEGER NOT NULL,
    completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_game_completions_user ON game_completions(user_id, game_type);
CREATE INDEX IF NOT EXISTS idx_game_completions_date ON game_completions(user_id, completed_at DESC);

-- Update users table
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name='users' AND column_name='games_played'
    ) THEN
        ALTER TABLE users ADD COLUMN games_played INTEGER DEFAULT 0;
    END IF;
    
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name='users' AND column_name='total_game_score'
    ) THEN
        ALTER TABLE users ADD COLUMN total_game_score INTEGER DEFAULT 0;
    END IF;
END $$;
"""

# Connect and run
try:
    print("🔌 Connecting to database...")
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    print("📝 Running migration...")
    cursor.execute(migration_sql)
    conn.commit()
    
    print("✅ Migration successful!")
    
    # Verify tables
    cursor.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_name IN ('game_used_words', 'game_completions')
    """)
    tables = cursor.fetchall()
    print(f"✅ Created tables: {[t[0] for t in tables]}")
    
    # Check users columns
    cursor.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'users' 
        AND column_name IN ('games_played', 'total_game_score')
    """)
    columns = cursor.fetchall()
    print(f"✅ Added columns to users: {[c[0] for c in columns]}")
    
    cursor.close()
    conn.close()
    print("\n🎉 All done!")
    
except Exception as e:
    print(f"❌ Migration failed: {e}")
    if conn:
        conn.rollback()