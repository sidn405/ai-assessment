"""
Local Python script to run session tracking database migration
"""

import psycopg2
import sys

# Get your DATABASE_URL from Railway
# Railway → PostgreSQL → Variables tab → Copy DATABASE_URL value
DATABASE_URL = "postgresql://postgres:YOUR_PASSWORD@YOUR_HOST:YOUR_PORT/railway"

# REPLACE THE DATABASE_URL ABOVE WITH YOUR ACTUAL VALUE FROM RAILWAY

def run_session_tracking_migration():
    print("=" * 60)
    print("SESSION TRACKING DATABASE MIGRATION")
    print("=" * 60)
    
    try:
        print("\nConnecting to database...")
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        print("✓ Connected successfully")
        
        # Create user_sessions table
        print("\nCreating user_sessions table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_sessions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                session_start TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                session_end TIMESTAMP,
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status VARCHAR(50) DEFAULT 'active',
                break_start TIMESTAMP,
                break_end TIMESTAMP,
                total_active_time INTEGER DEFAULT 0,
                total_break_time INTEGER DEFAULT 0,
                timeout_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        conn.commit()
        print("✓ user_sessions table created")
        
        # Create indexes for user_sessions
        print("Creating indexes for user_sessions...")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_sessions_user ON user_sessions(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_sessions_status ON user_sessions(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_sessions_start ON user_sessions(session_start)")
        conn.commit()
        print("✓ user_sessions indexes created")
        
        # Create activity_log table
        print("\nCreating activity_log table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS activity_log (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                session_id INTEGER,
                activity_type VARCHAR(50) NOT NULL,
                activity_details TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (session_id) REFERENCES user_sessions(id)
            )
        """)
        conn.commit()
        print("✓ activity_log table created")
        
        # Create indexes for activity_log
        print("Creating indexes for activity_log...")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_activity_log_user ON activity_log(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_activity_log_session ON activity_log(session_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_activity_log_type ON activity_log(activity_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_activity_log_timestamp ON activity_log(timestamp)")
        conn.commit()
        print("✓ activity_log indexes created")
        
        # Create timeout_events table
        print("\nCreating timeout_events table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS timeout_events (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                session_id INTEGER,
                warning_shown_at TIMESTAMP,
                user_responded BOOLEAN DEFAULT FALSE,
                timed_out_at TIMESTAMP,
                idle_duration INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (session_id) REFERENCES user_sessions(id)
            )
        """)
        conn.commit()
        print("✓ timeout_events table created")
        
        # Create indexes for timeout_events
        print("Creating indexes for timeout_events...")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_timeout_events_user ON timeout_events(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_timeout_events_session ON timeout_events(session_id)")
        conn.commit()
        print("✓ timeout_events indexes created")
        
        # Verify all tables
        print("\nVerifying tables...")
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('user_sessions', 'activity_log', 'timeout_events')
            ORDER BY table_name
        """)
        
        tables = [row[0] for row in cursor.fetchall()]
        
        print("\n" + "=" * 60)
        print("✓✓✓ SESSION TRACKING MIGRATION COMPLETE ✓✓✓")
        print("=" * 60)
        print(f"\nTables created ({len(tables)}):")
        for table in tables:
            print(f"  ✓ {table}")
        
        if len(tables) == 3:
            print("\n✓ All session tracking tables successfully created!")
        else:
            print(f"\n⚠ Warning: Expected 3 tables, but only created {len(tables)}")
        
        print("\n" + "=" * 60)
        print("SESSION TRACKING SYSTEM READY")
        print("=" * 60)
        print("\nFeatures enabled:")
        print("  ✓ Automatic session tracking")
        print("  ✓ 7-minute idle warning")
        print("  ✓ 10-minute auto logout")
        print("  ✓ 30-minute break feature")
        print("  ✓ Complete activity logging")
        print("  ✓ Admin monitoring dashboard")
        print("\nNext steps:")
        print("  1. Update app.py with session tracking backend code")
        print("  2. Update dashboard.html with timeout & break system")
        print("  3. Update admin-dashboard.html with session tracking display")
        print("  4. Deploy to Railway")
        print("  5. Test the system!")
        
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
        print("6. Run: python run_session_tracking_migration.py")
        sys.exit(1)
    
    success = run_session_tracking_migration()
    sys.exit(0 if success else 1)