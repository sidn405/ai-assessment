"""
COMPREHENSIVE ESSAY ASSESSMENT SYSTEM - Database Migration Script

Run this locally to create the required database tables.
"""

import psycopg2
import sys

# UPDATE THIS WITH YOUR RAILWAY DATABASE_URL
DATABASE_URL = "postgresql://postgres:YOUR_PASSWORD@YOUR_HOST:YOUR_PORT/railway"

def run_migration():
    print("=" * 70)
    print("COMPREHENSIVE ESSAY SYSTEM - DATABASE MIGRATION")
    print("=" * 70)
    
    try:
        print("\nConnecting to database...")
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        print("✓ Connected")
        
        # Create user_essays table
        print("\nCreating user_essays table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_essays (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                essay_number INTEGER NOT NULL,
                lesson_count INTEGER NOT NULL,
                essay_text TEXT NOT NULL,
                word_count INTEGER,
                comprehension_level VARCHAR(50),
                comprehension_score INTEGER,
                difficulty_recommendation VARCHAR(50),
                ai_feedback TEXT,
                lesson_ids TEXT,
                lesson_topics TEXT,
                needs_admin_review BOOLEAN DEFAULT FALSE,
                admin_notified BOOLEAN DEFAULT FALSE,
                admin_reviewed BOOLEAN DEFAULT FALSE,
                admin_notes TEXT,
                points_awarded INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                reviewed_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_essays_user ON user_essays(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_essays_needs_review ON user_essays(needs_admin_review)")
        conn.commit()
        print("✓ user_essays created")
        
        # Create difficulty_adjustments table
        print("Creating difficulty_adjustments table...")
        cursor.execute("""
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
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_difficulty_adjustments_user ON difficulty_adjustments(user_id)")
        conn.commit()
        print("✓ difficulty_adjustments created")
        
        # Create admin_alerts table
        print("Creating admin_alerts table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS admin_alerts (
                id SERIAL PRIMARY KEY,
                alert_type VARCHAR(50) NOT NULL,
                user_id INTEGER NOT NULL,
                essay_id INTEGER,
                priority VARCHAR(20) DEFAULT 'normal',
                message TEXT NOT NULL,
                details TEXT,
                is_read BOOLEAN DEFAULT FALSE,
                is_resolved BOOLEAN DEFAULT FALSE,
                resolved_by INTEGER,
                resolved_at TIMESTAMP,
                resolution_notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (essay_id) REFERENCES user_essays(id)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_admin_alerts_read ON admin_alerts(is_read)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_admin_alerts_resolved ON admin_alerts(is_resolved)")
        conn.commit()
        print("✓ admin_alerts created")
        
        print("\n" + "=" * 70)
        print("✓✓✓ MIGRATION COMPLETE! ✓✓✓")
        print("=" * 70)
        print("\nNext steps:")
        print("  1. Add essay_system_backend.py code to app.py")
        print("  2. Add essay_frontend_complete.js code to dashboard.html")
        print("  3. Add essay_admin_complete.html code to admin-dashboard.html")
        print("  4. Deploy to Railway")
        print("=" * 70)
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        return False

if __name__ == "__main__":
    if "YOUR_PASSWORD" in DATABASE_URL:
        print("\n" + "=" * 70)
        print("ERROR: Update DATABASE_URL at top of this script!")
        print("=" * 70)
        print("\nGet it from: Railway → PostgreSQL → Variables → DATABASE_URL")
        sys.exit(1)
    
    success = run_migration()
    sys.exit(0 if success else 1)