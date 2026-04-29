"""
School Support Migration Script
Run this to add school column to users table
"""

import psycopg2
import sys

# Your database URL
DATABASE_URL = ""

migration_sql = """
-- Add school column to users table
ALTER TABLE users 
ADD COLUMN IF NOT EXISTS school TEXT;

-- Create index for faster school filtering
CREATE INDEX IF NOT EXISTS idx_users_school ON users(school);
"""

def run_migration():
    try:
        print("🔗 Connecting to database...")
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        print("🔧 Running migration...")
        cursor.execute(migration_sql)
        conn.commit()
        
        print("✅ Migration completed successfully!")
        
        # Verify column was added
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'users' 
            AND column_name = 'school'
        """)
        
        result = cursor.fetchone()
        if result:
            print(f"✅ Verified: 'school' column added to users table")
        else:
            print("⚠️  Warning: Could not verify column was added")
        
        # Show current users
        cursor.execute("""
            SELECT COUNT(*) FROM users WHERE role = 'student'
        """)
        student_count = cursor.fetchone()[0]
        print(f"\n📊 Current students: {student_count}")
        
        cursor.execute("""
            SELECT COUNT(*) FROM users WHERE role = 'admin'
        """)
        admin_count = cursor.fetchone()[0]
        print(f"📊 Current admins: {admin_count}")
        
        cursor.close()
        conn.close()
        
        print("\n✅ Migration complete! Next steps:")
        print("1. Assign admins to schools (see assign_admins.py)")
        print("2. Update backend code (see BACKEND_SCHOOL_CHANGES.txt)")
        print("3. Deploy updated frontend files")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_migration()