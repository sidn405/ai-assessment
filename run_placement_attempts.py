"""
Run this Python script locally to create the placement_attempts table (PostgreSQL / Railway)

Purpose:
- Stores reading-level placement test results separate from session_logs
- Supports selecting/confirming a student's reading level before generating lessons

How to use:
1) Railway Dashboard → PostgreSQL service → Variables → copy DATABASE_URL
2) Paste it into DATABASE_URL below (or set it as an env var DATABASE_URL)
3) Run: python run_placement_attempts.py

Notes:
- Assumes your project already has `users(id)` and `passages(id)` tables.
- Safe to run multiple times (uses IF NOT EXISTS).
"""

import os
import sys
import psycopg2

# Get your DATABASE_URL from Railway
# Railway → PostgreSQL → Variables tab → Copy DATABASE_URL value
DATABASE_URL = ""  # e.g. postgresql://postgres:ABC123@xyz.railway.app:5432/railway

# Prefer env var if present (lets you avoid hardcoding secrets)
DATABASE_URL = "postgresql://postgres:YOUR_PASSWORD@YOUR_HOST:YOUR_PORT/railway"


def run_placement_attempts_migration() -> bool:
    print("=" * 60)
    print("RUNNING PLACEMENT ATTEMPTS DATABASE MIGRATION")
    print("=" * 60)

    try:
        print("\nConnecting to database...")
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        print("✓ Connected successfully")

        # Create placement_attempts table
        print("\nCreating placement_attempts table...")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS placement_attempts (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                passage_id INTEGER NOT NULL,
                difficulty_level VARCHAR(50) NOT NULL,   -- beginner|intermediate|advanced
                word_count INTEGER NOT NULL DEFAULT 0,
                time_spent_seconds INTEGER NOT NULL DEFAULT 0,
                wpm NUMERIC(6,1) NOT NULL DEFAULT 0,
                comprehension_score NUMERIC(5,2) NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (passage_id) REFERENCES passages(id) ON DELETE CASCADE
            )
            """
        )
        conn.commit()
        print("✓ placement_attempts table created")

        # Indexes (fast lookup per user + recent)
        print("Creating indexes for placement_attempts...")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_placement_attempts_user_created ON placement_attempts(user_id, created_at DESC)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_placement_attempts_user_passage ON placement_attempts(user_id, passage_id)"
        )
        conn.commit()
        print("✓ placement_attempts indexes created")

        # Verify table exists
        print("\nVerifying table...")
        cursor.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = 'placement_attempts'
            """
        )
        exists = cursor.fetchone() is not None

        print("\n" + "=" * 60)
        if exists:
            print("✓✓✓ PLACEMENT ATTEMPTS MIGRATION COMPLETE ✓✓✓")
            print("=" * 60)
            print("\nTable created:")
            print("  ✓ placement_attempts")
            print("\nNext steps:")
            print("  1. Add /api/placement/next and /api/placement/submit endpoints")
            print("  2. Update your frontend to run placement after interest assessment")
            print("  3. Gate /api/lessons/next until placement is complete")
        else:
            print("⚠ Migration ran, but placement_attempts was not found in information_schema.")
            print("   Check DB permissions / schema.")
            print("=" * 60)

        conn.close()
        return bool(exists)

    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    if not DATABASE_URL or "YOUR_PASSWORD" in DATABASE_URL or "postgresql://postgres:YOUR_PASSWORD" in DATABASE_URL:
        print("=" * 60)
        print("ERROR: Please set DATABASE_URL in this script or as an environment variable!")
        print("=" * 60)
        print("\nSteps:")
        print("1. Go to Railway Dashboard")
        print("2. Click PostgreSQL service")
        print("3. Click 'Variables' tab")
        print("4. Copy the DATABASE_URL value")
        print("   (Looks like: postgresql://postgres:ABC123@xyz.railway.app:5432/railway)")
        print("5. Either:")
        print("   - Paste it into DATABASE_URL at the top of this script, OR")
        print("   - Run with env var: DATABASE_URL='...' python run_placement_attempts.py")
        sys.exit(1)

    ok = run_placement_attempts_migration()
    sys.exit(0 if ok else 1)
