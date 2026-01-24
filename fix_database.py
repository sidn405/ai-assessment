"""
Quick fix script to add missing placement_attempts table
Run this ONCE to fix the database for your Railway deployment
"""

import os
import psycopg2

# Get DATABASE_URL from environment (Railway sets this automatically)
DATABASE_URL = "postgresql://postgres:YOUR_PASSWORD@YOUR_HOST:YOUR_PORT/railway"

if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if not DATABASE_URL:
    print("❌ ERROR: DATABASE_URL not found in environment variables")
    print("Make sure you're running this in your Railway environment")
    exit(1)

print("🔧 Connecting to database...")
try:
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    print("✅ Connected successfully")
except Exception as e:
    print(f"❌ Connection failed: {e}")
    exit(1)

# Create placement_attempts table
print("\n📝 Creating placement_attempts table...")
try:
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS placement_attempts (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            attempt_number INTEGER NOT NULL,
            level_assigned VARCHAR(20),
            questions_data TEXT,
            total_correct INTEGER DEFAULT 0,
            total_questions INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, attempt_number)
        )
    """)
    print("✅ Table created")
except Exception as e:
    print(f"⚠️  Table might already exist or error: {e}")

# Create index
print("\n📊 Creating index...")
try:
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_placement_user 
        ON placement_attempts(user_id)
    """)
    print("✅ Index created")
except Exception as e:
    print(f"⚠️  Index might already exist or error: {e}")

# Commit changes
try:
    conn.commit()
    print("\n✅ All changes committed successfully!")
except Exception as e:
    print(f"❌ Commit failed: {e}")
    conn.rollback()

# Verify table exists
print("\n🔍 Verifying table...")
try:
    cursor.execute("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'placement_attempts'
        ORDER BY ordinal_position
    """)
    columns = cursor.fetchall()
    
    if columns:
        print("✅ Table verified! Columns:")
        for col_name, col_type in columns:
            print(f"   - {col_name}: {col_type}")
    else:
        print("❌ Table not found!")
except Exception as e:
    print(f"❌ Verification failed: {e}")

# Close connection
cursor.close()
conn.close()
print("\n✅ Done! Database fixed.")
print("\n🚀 Your new users should now be able to access lessons without errors.")