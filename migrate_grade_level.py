"""
Grade Level Migration Script
Adds grade_band and reading_level columns to users table
Run this once to update your Railway PostgreSQL database
"""

import os
import psycopg2

# Get DATABASE_URL from environment or paste it here
DATABASE_URL = os.getenv("DATABASE_URL") or "postgresql://..."

if not DATABASE_URL or DATABASE_URL == "postgresql://...":
    print("❌ ERROR: DATABASE_URL not set!")
    print("\nOptions:")
    print("1. Set environment variable:")
    print('   $env:DATABASE_URL="postgresql://postgres:..."')
    print("\n2. Or paste your Railway PostgreSQL URL in this script (line 11)")
    exit(1)

# Fix postgres:// to postgresql:// if needed
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

print("🔧 Connecting to Railway PostgreSQL...")

try:
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    print("✅ Connected successfully!")
    
    # Add grade_band column
    print("\n📝 Adding grade_band column...")
    cursor.execute("""
        ALTER TABLE users 
        ADD COLUMN IF NOT EXISTS grade_band VARCHAR(20)
    """)
    print("✅ grade_band column added (or already exists)")
    
    # Add reading_level column
    print("\n📝 Adding reading_level column...")
    cursor.execute("""
        ALTER TABLE users 
        ADD COLUMN IF NOT EXISTS reading_level VARCHAR(20)
    """)
    print("✅ reading_level column added (or already exists)")
    
    # Commit changes
    conn.commit()
    print("\n💾 Changes committed to database")
    
    # Verify columns exist
    print("\n🔍 Verifying columns...")
    cursor.execute("""
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_name = 'users'
        AND column_name IN ('grade_band', 'reading_level')
        ORDER BY column_name
    """)
    
    results = cursor.fetchall()
    
    if len(results) == 2:
        print("✅ Verification successful! Columns added:")
        print("\n  Column Name    | Data Type         | Nullable")
        print("  ---------------+-------------------+---------")
        for row in results:
            print(f"  {row[0]:<15}| {row[1]:<18}| {row[2]}")
    else:
        print("⚠️  Warning: Expected 2 columns but found", len(results))
    
    # Optional: Set defaults for existing users
    print("\n❓ Set default values for existing users without grade levels?")
    print("   (Sets grade_band='adult', reading_level='intermediate')")
    response = input("   Type 'yes' to update existing users: ").strip().lower()
    
    if response == 'yes':
        cursor.execute("""
            UPDATE users 
            SET grade_band = 'adult',
                reading_level = 'intermediate'
            WHERE grade_band IS NULL
        """)
        updated_count = cursor.rowcount
        conn.commit()
        print(f"✅ Updated {updated_count} existing users with default values")
    else:
        print("⏭️  Skipped updating existing users")
    
    # Show sample data
    print("\n📊 Sample of users table (last 3 users):")
    cursor.execute("""
        SELECT id, email, grade_band, age_band, reading_level
        FROM users
        ORDER BY created_at DESC
        LIMIT 3
    """)
    
    users = cursor.fetchall()
    if users:
        print("\n  ID | Email                | Grade    | Age Band  | Reading Level")
        print("  ---+----------------------+----------+-----------+--------------")
        for user in users:
            print(f"  {user[0]:<3}| {user[1]:<21}| {str(user[2] or 'NULL'):<9}| {str(user[3] or 'NULL'):<10}| {user[4] or 'NULL'}")
    else:
        print("  No users found in database")
    
    # Close connection
    cursor.close()
    conn.close()
    
    print("\n" + "="*60)
    print("✅ MIGRATION COMPLETE!")
    print("="*60)
    print("\nYou can now:")
    print("1. Register new users with grade level selection")
    print("2. Test the feature at your Railway URL")
    print("3. Verify data with: SELECT * FROM users;")
    
except psycopg2.Error as e:
    print(f"\n❌ Database error: {e}")
    print("\nTroubleshooting:")
    print("- Verify DATABASE_URL is correct")
    print("- Check Railway PostgreSQL is online")
    print("- Ensure you have permissions to ALTER table")
    
except Exception as e:
    print(f"\n❌ Unexpected error: {e}")
    
finally:
    if 'conn' in locals() and conn:
        conn.close()
        print("\n🔌 Database connection closed")