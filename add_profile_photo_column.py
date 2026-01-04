#!/usr/bin/env python3
"""
Add profile_photo column to users table
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor

# Get database URL from environment variable
DATABASE_URL = ""

if not DATABASE_URL:
    print("❌ ERROR: DATABASE_URL environment variable not set!")
    exit(1)

try:
    print("🔗 Connecting to database...")
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    print("✓ Connected successfully")
    print()
    
    # Check if column exists
    print("🔍 Checking if profile_photo column exists...")
    
    cursor.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'users' AND column_name = 'profile_photo';
    """)
    
    exists = cursor.fetchone()
    
    if exists:
        print("✓ profile_photo column already exists")
    else:
        print("📝 Adding profile_photo column...")
        
        cursor.execute("""
            ALTER TABLE users 
            ADD COLUMN profile_photo VARCHAR(500) DEFAULT NULL;
        """)
        
        print("✓ profile_photo column added")
    
    # Commit changes
    conn.commit()
    
    # Verify
    cursor.execute("""
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns 
        WHERE table_name = 'users'
        ORDER BY ordinal_position;
    """)
    
    columns = cursor.fetchall()
    
    print()
    print("✅ USERS TABLE STRUCTURE:")
    print("-" * 80)
    print(f"{'COLUMN':<20} {'TYPE':<30} {'NULLABLE':<10}")
    print("-" * 80)
    for col in columns:
        nullable = "YES" if col['is_nullable'] == 'YES' else "NO"
        print(f"{col['column_name']:<20} {col['data_type']:<30} {nullable:<10}")
    
    print()
    print("✅ SUCCESS! profile_photo column is ready")
    print()
    
    cursor.close()
    conn.close()
    
except psycopg2.Error as e:
    print(f"❌ Database error: {e}")
    exit(1)
except Exception as e:
    print(f"❌ Error: {e}")
    exit(1)