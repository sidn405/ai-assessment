"""
Add word_count_min and word_count_max columns to users table
"""

import psycopg2
import sys

DATABASE_URL = ""

def add_word_count_columns():
    print("=" * 70)
    print("ADD WORD COUNT COLUMNS TO USERS TABLE")
    print("=" * 70)
    
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        print("✓ Connected to database\n")
        
        # Check if columns already exist
        print("[1] Checking if columns exist...")
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'users' 
            AND column_name IN ('word_count_min', 'word_count_max')
        """)
        
        existing_columns = [row[0] for row in cursor.fetchall()]
        print(f"Existing columns: {existing_columns if existing_columns else 'None'}")
        
        # Add word_count_min if not exists
        if 'word_count_min' not in existing_columns:
            print("\n[2] Adding word_count_min column...")
            cursor.execute("""
                ALTER TABLE users 
                ADD COLUMN word_count_min INTEGER
            """)
            print("✓ word_count_min column added")
        else:
            print("\n[2] word_count_min column already exists")
        
        # Add word_count_max if not exists
        if 'word_count_max' not in existing_columns:
            print("\n[3] Adding word_count_max column...")
            cursor.execute("""
                ALTER TABLE users 
                ADD COLUMN word_count_max INTEGER
            """)
            print("✓ word_count_max column added")
        else:
            print("\n[3] word_count_max column already exists")
        
        conn.commit()
        
        # Set initial values based on reading level
        print("\n[4] Setting initial word count values based on reading level...")
        cursor.execute("""
            UPDATE users 
            SET word_count_min = CASE 
                    WHEN reading_level = 'beginner' THEN 150
                    WHEN reading_level = 'intermediate' THEN 200
                    WHEN reading_level = 'advanced' THEN 250
                    ELSE 150
                END,
                word_count_max = CASE 
                    WHEN reading_level = 'beginner' THEN 200
                    WHEN reading_level = 'intermediate' THEN 250
                    WHEN reading_level = 'advanced' THEN 300
                    ELSE 200
                END
            WHERE word_count_min IS NULL OR word_count_max IS NULL
        """)
        
        rows_updated = cursor.rowcount
        conn.commit()
        print(f"✓ Updated {rows_updated} users with initial word counts")
        
        # Verify
        print("\n[5] Verifying results...")
        cursor.execute("""
            SELECT id, full_name, reading_level, word_count_min, word_count_max
            FROM users
            ORDER BY id
        """)
        
        print("\n{:<5} {:<20} {:<15} {:<8} {:<8}".format("ID", "Name", "Level", "Min", "Max"))
        print("-" * 65)
        
        for row in cursor.fetchall():
            print("{:<5} {:<20} {:<15} {:<8} {:<8}".format(
                row[0] or 0,
                (row[1] or 'Unknown')[:20],
                row[2] or 'beginner',
                row[3] or 0,
                row[4] or 0
            ))
        
        conn.close()
        
        print("\n" + "=" * 70)
        print("✓✓✓ MIGRATION COMPLETE!")
        print("=" * 70)
        print("\nWord count ranges set:")
        print("  • Beginner: 150-200 words")
        print("  • Intermediate: 200-250 words")
        print("  • Advanced: 250-300 words")
        print("\nNext lesson will use these values!")
        
        return True
        
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    if "YOUR_PASSWORD" in DATABASE_URL:
        print("\n" + "=" * 70)
        print("ERROR: Update DATABASE_URL at top of this script!")
        print("=" * 70)
        sys.exit(1)
    
    success = add_word_count_columns()
    sys.exit(0 if success else 1)