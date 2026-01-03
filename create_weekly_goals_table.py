#!/usr/bin/env python3
"""
Fix existing weekly_goals table by adding missing columns
Run this to update the table schema
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor

# Get database URL from environment variable
DATABASE_URL = ""

if not DATABASE_URL:
    print("❌ ERROR: DATABASE_URL environment variable not set!")
    print("Set it with: export DATABASE_URL='your-railway-postgres-url'")
    exit(1)

try:
    print("🔗 Connecting to database...")
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    print("✓ Connected successfully")
    print()
    
    # Check current table structure
    print("🔍 Checking current weekly_goals table structure...")
    
    cursor.execute("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'weekly_goals'
        ORDER BY ordinal_position;
    """)
    
    current_columns = {row['column_name']: row['data_type'] for row in cursor.fetchall()}
    
    if not current_columns:
        print("❌ Table doesn't exist yet!")
        exit(1)
    
    print("Current columns:")
    for col, dtype in current_columns.items():
        print(f"  - {col} ({dtype})")
    print()
    
    # Required columns
    required_columns = {
        'week_start': 'date',
        'week_end': 'date',
        'created_at': 'timestamp without time zone',
        'updated_at': 'timestamp without time zone'
    }
    
    # Add missing columns
    print("📝 Adding missing columns...")
    
    for col_name, col_type in required_columns.items():
        if col_name not in current_columns:
            print(f"  Adding {col_name}...")
            
            if col_name == 'week_start':
                cursor.execute("""
                    ALTER TABLE weekly_goals 
                    ADD COLUMN week_start DATE NOT NULL DEFAULT CURRENT_DATE;
                """)
            elif col_name == 'week_end':
                cursor.execute("""
                    ALTER TABLE weekly_goals 
                    ADD COLUMN week_end DATE NOT NULL DEFAULT (CURRENT_DATE + INTERVAL '7 days');
                """)
            elif col_name == 'created_at':
                cursor.execute("""
                    ALTER TABLE weekly_goals 
                    ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
                """)
            elif col_name == 'updated_at':
                cursor.execute("""
                    ALTER TABLE weekly_goals 
                    ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
                """)
            
            print(f"    ✓ Added {col_name}")
        else:
            print(f"  ✓ {col_name} already exists")
    
    print()
    
    # Create index (drop first if exists)
    print("📇 Creating index...")
    
    cursor.execute("""
        DROP INDEX IF EXISTS idx_weekly_goals_user_dates;
    """)
    
    cursor.execute("""
        CREATE INDEX idx_weekly_goals_user_dates 
        ON weekly_goals(user_id, week_start, week_end);
    """)
    
    print("✓ Index created")
    
    # Commit changes
    conn.commit()
    
    # Verify final structure
    print()
    print("🔍 Verifying final table structure...")
    
    cursor.execute("""
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns 
        WHERE table_name = 'weekly_goals'
        ORDER BY ordinal_position;
    """)
    
    columns = cursor.fetchall()
    
    print()
    print("✅ FINAL WEEKLY_GOALS TABLE STRUCTURE:")
    print("-" * 80)
    print(f"{'COLUMN':<20} {'TYPE':<30} {'NULLABLE':<10} {'DEFAULT':<20}")
    print("-" * 80)
    for col in columns:
        nullable = "YES" if col['is_nullable'] == 'YES' else "NO"
        default = str(col['column_default'])[:20] if col['column_default'] else '-'
        print(f"{col['column_name']:<20} {col['data_type']:<30} {nullable:<10} {default:<20}")
    
    print()
    print("✅ SUCCESS! weekly_goals table has been updated")
    print()
    
    cursor.close()
    conn.close()
    
except psycopg2.Error as e:
    print(f"❌ Database error: {e}")
    exit(1)
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    exit(1)