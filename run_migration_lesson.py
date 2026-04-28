import psycopg2
import os

# Your database URL
DATABASE_URL = ""

# SQL migration
migration_sql = """
-- Add column to track last used interest index
ALTER TABLE users 
ADD COLUMN IF NOT EXISTS last_interest_index INTEGER DEFAULT 0;

-- Add column to track topic history as JSON
ALTER TABLE users 
ADD COLUMN IF NOT EXISTS topic_history TEXT DEFAULT '{}';

-- Update existing users to have default values
UPDATE users 
SET last_interest_index = 0, topic_history = '{}' 
WHERE last_interest_index IS NULL OR topic_history IS NULL;
"""

try:
    print("Connecting to database...")
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    print("Running migration...")
    cursor.execute(migration_sql)
    conn.commit()
    
    print("✅ Migration completed successfully!")
    
    # Verify columns were added
    cursor.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'users' 
        AND column_name IN ('last_interest_index', 'topic_history')
    """)
    
    columns = cursor.fetchall()
    print(f"✅ Verified columns added: {[col[0] for col in columns]}")
    
    cursor.close()
    conn.close()
    
except Exception as e:
    print(f"❌ Error: {e}")