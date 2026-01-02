"""
Run this Python script locally to create gamification database tables
No need for Railway UI or endpoints
"""

import psycopg2
import sys

# Get your DATABASE_URL from Railway
# Railway → PostgreSQL → Variables tab → Copy DATABASE_URL value
DATABASE_URL = ""

# REPLACE THE DATABASE_URL ABOVE WITH YOUR ACTUAL VALUE FROM RAILWAY

def run_gamification_migration():
    print("=" * 60)
    print("RUNNING GAMIFICATION DATABASE MIGRATION")
    print("=" * 60)
    
    try:
        print("\nConnecting to database...")
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        print("✓ Connected successfully")
        
        # Create user_points table
        print("\nCreating user_points table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_points (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                points INTEGER DEFAULT 0,
                total_earned INTEGER DEFAULT 0,
                level INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                UNIQUE(user_id)
            )
        """)
        conn.commit()
        print("✓ user_points table created")
        
        # Create points_history table
        print("\nCreating points_history table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS points_history (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                points INTEGER NOT NULL,
                reason VARCHAR(255),
                activity_type VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        conn.commit()
        print("✓ points_history table created")
        
        # Create indexes for points_history
        print("Creating indexes for points_history...")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_points_history_user ON points_history(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_points_history_date ON points_history(created_at)")
        conn.commit()
        print("✓ points_history indexes created")
        
        # Create user_badges table
        print("\nCreating user_badges table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_badges (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                badge_type VARCHAR(50) NOT NULL,
                badge_name VARCHAR(100) NOT NULL,
                description TEXT,
                icon VARCHAR(50),
                earned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        conn.commit()
        print("✓ user_badges table created")
        
        # Create index for user_badges
        print("Creating index for user_badges...")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_badges_user ON user_badges(user_id)")
        conn.commit()
        print("✓ user_badges index created")
        
        # Create weekly_goals table
        print("\nCreating weekly_goals table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS weekly_goals (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                week_start DATE NOT NULL,
                goal_type VARCHAR(50) NOT NULL,
                target_value INTEGER NOT NULL,
                current_value INTEGER DEFAULT 0,
                completed BOOLEAN DEFAULT FALSE,
                points_reward INTEGER DEFAULT 0,
                completed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        conn.commit()
        print("✓ weekly_goals table created")
        
        # Create indexes for weekly_goals
        print("Creating indexes for weekly_goals...")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_weekly_goals_user ON weekly_goals(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_weekly_goals_week ON weekly_goals(week_start)")
        conn.commit()
        print("✓ weekly_goals indexes created")
        
        # Create user_streaks table
        print("\nCreating user_streaks table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_streaks (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                current_streak INTEGER DEFAULT 0,
                longest_streak INTEGER DEFAULT 0,
                last_activity_date DATE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                UNIQUE(user_id)
            )
        """)
        conn.commit()
        print("✓ user_streaks table created")
        
        # Initialize weekly goals for existing users
        print("\nInitializing weekly goals for existing users...")
        cursor.execute("""
            INSERT INTO weekly_goals (user_id, week_start, goal_type, target_value, points_reward)
            SELECT 
                id,
                DATE_TRUNC('week', CURRENT_DATE),
                'lessons_completed',
                5,
                100
            FROM users
            WHERE id NOT IN (
                SELECT DISTINCT user_id 
                FROM weekly_goals 
                WHERE week_start = DATE_TRUNC('week', CURRENT_DATE)
            )
        """)
        rows_inserted = cursor.rowcount
        conn.commit()
        print(f"✓ Created weekly goals for {rows_inserted} users")
        
        # Verify all tables
        print("\nVerifying tables...")
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('user_points', 'points_history', 'user_badges', 
                               'weekly_goals', 'user_streaks')
            ORDER BY table_name
        """)
        
        tables = [row[0] for row in cursor.fetchall()]
        
        print("\n" + "=" * 60)
        print("✓✓✓ GAMIFICATION MIGRATION COMPLETE ✓✓✓")
        print("=" * 60)
        print(f"\nTables created ({len(tables)}):")
        for table in tables:
            print(f"  ✓ {table}")
        
        if len(tables) == 5:
            print("\n✓ All gamification tables successfully created!")
        else:
            print(f"\n⚠ Warning: Expected 5 tables, but only created {len(tables)}")
        
        # Show sample data
        print("\n" + "=" * 60)
        print("GAMIFICATION SYSTEM READY")
        print("=" * 60)
        print("\nFeatures enabled:")
        print("  ✓ Points system (10-50 pts per lesson)")
        print("  ✓ Levels (every 500 points)")
        print("  ✓ 8 badges to earn")
        print("  ✓ Weekly goals (5 lessons/week)")
        print("  ✓ Streak tracking")
        print("\nNext steps:")
        print("  1. Update app.py with gamification backend code")
        print("  2. Update dashboard.html with gamification frontend code")
        print("  3. Deploy to Railway")
        print("  4. Start earning points and badges!")
        
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
        print("   (Should look like: postgresql://postgres:ABC123@xyz.railway.app:5432/railway)")
        print("5. Replace the DATABASE_URL at the top of this script")
        print("6. Run: python run_gamification_migration.py")
        sys.exit(1)
    
    success = run_gamification_migration()
    sys.exit(0 if success else 1)