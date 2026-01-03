"""
Update Essay Word Count Requirements in Database

This script resets essay word counts based on reading level:
- beginner: 25 words
- intermediate: 50 words
- advanced: 75 words
"""

import psycopg2
import sys

# UPDATE THIS WITH YOUR RAILWAY DATABASE_URL
DATABASE_URL = "y"

def update_essay_word_counts():
    print("=" * 70)
    print("UPDATE ESSAY WORD COUNT REQUIREMENTS")
    print("=" * 70)
    
    try:
        print("\n[1/4] Connecting to database...")
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        print("✓ Connected successfully")
        
        # Show current values
        print("\n[2/4] Current essay word count requirements:")
        cursor.execute("""
            SELECT id, full_name, reading_level, essay_word_count_requirement 
            FROM users
            ORDER BY id
        """)
        
        print("\n{:<5} {:<20} {:<15} {:<10}".format("ID", "Name", "Level", "Words"))
        print("-" * 55)
        
        for row in cursor.fetchall():
            user_id = row[0] if row[0] else 0
            name = row[1] if row[1] else 'Unknown'
            level = row[2] if row[2] else 'beginner'
            words = row[3] if row[3] else 'NULL'
            print("{:<5} {:<20} {:<15} {:<10}".format(user_id, name, level, str(words)))
        
        # Update essay word counts
        print("\n[3/4] Updating essay word count requirements...")
        
        # First, set any NULL reading_levels to 'beginner'
        cursor.execute("""
            UPDATE users 
            SET reading_level = 'beginner'
            WHERE reading_level IS NULL
        """)
        
        # Now update word counts based on level
        cursor.execute("""
            UPDATE users 
            SET essay_word_count_requirement = CASE 
                WHEN reading_level = 'beginner' THEN 25
                WHEN reading_level = 'intermediate' THEN 50
                WHEN reading_level = 'advanced' THEN 75
                ELSE 25
            END
        """)
        
        rows_updated = cursor.rowcount
        conn.commit()
        print(f"✓ Updated {rows_updated} users")
        
        # Verify updates
        print("\n[4/4] Verifying updates...")
        cursor.execute("""
            SELECT id, full_name, reading_level, essay_word_count_requirement 
            FROM users
            ORDER BY id
        """)
        
        print("\n{:<5} {:<20} {:<15} {:<10}".format("ID", "Name", "Level", "Words"))
        print("-" * 55)
        
        correct_counts = 0
        for row in cursor.fetchall():
            user_id = row[0] if row[0] else 0
            name = row[1] if row[1] else 'Unknown'
            level = row[2] if row[2] else 'beginner'
            words = row[3] if row[3] else 25
            
            # Check if word count matches level
            expected = {'beginner': 25, 'intermediate': 50, 'advanced': 75}
            is_correct = words == expected.get(level, 25)
            
            status = "✓" if is_correct else "✗"
            if is_correct:
                correct_counts += 1
            
            print("{:<5} {:<20} {:<15} {:<10} {}".format(
                user_id, name[:20], level, words, status
            ))
        
        print("\n" + "=" * 70)
        print(f"✓✓✓ UPDATE COMPLETE! {correct_counts}/{rows_updated} users have correct word counts")
        print("=" * 70)
        
        print("\nWord count settings:")
        print("  • Beginner level: 25 words")
        print("  • Intermediate level: 50 words")
        print("  • Advanced level: 75 words")
        print("  • Each level up: +25 words")
        
        conn.close()
        return True
        
    except psycopg2.Error as e:
        print(f"\n✗ DATABASE ERROR: {e}")
        print("\nTroubleshooting:")
        print("  • Verify DATABASE_URL is correct")
        print("  • Check PostgreSQL is running on Railway")
        print("  • Ensure network connection is stable")
        return False
        
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("ESSAY WORD COUNT UPDATE SCRIPT")
    print("=" * 70)
    
    # Check if DATABASE_URL is configured
    if "YOUR_PASSWORD" in DATABASE_URL or "YOUR_HOST" in DATABASE_URL:
        print("\n" + "=" * 70)
        print("ERROR: DATABASE_URL NOT CONFIGURED")
        print("=" * 70)
        print("\nPlease update the DATABASE_URL in this script first!")
        print("\nSteps:")
        print("  1. Go to Railway Dashboard")
        print("  2. Click on your PostgreSQL service")
        print("  3. Click 'Variables' tab")
        print("  4. Copy the DATABASE_URL value")
        print("  5. Paste it at the top of this script (line 13)")
        print("  6. Run: python update_essay_word_counts.py")
        print("\n" + "=" * 70)
        sys.exit(1)
    
    # Confirm before running
    print("\nThis script will:")
    print("  • Set beginner users to 25 word requirement")
    print("  • Set intermediate users to 50 word requirement")
    print("  • Set advanced users to 75 word requirement")
    
    response = input("\nContinue? (yes/no): ").lower().strip()
    
    if response not in ['yes', 'y']:
        print("\nCancelled by user.")
        sys.exit(0)
    
    # Run update
    success = update_essay_word_counts()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)