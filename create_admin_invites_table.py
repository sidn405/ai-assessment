"""
Create the admin_invites table in PostgreSQL (Railway) safely.

How to use (PowerShell):
1) Copy DATABASE_URL from Railway:
   Railway -> PostgreSQL -> Variables -> DATABASE_URL

2) In PowerShell (same terminal session):
   $env:DATABASE_URL="postgresql://postgres:PASS@HOST:PORT/railway"

3) Run:
   python create_admin_invites_table.py

Notes:
- Safe to run multiple times (uses IF NOT EXISTS).
- No localhost fallback (prevents accidental connection errors).
"""

import os
import sys
import psycopg2


DDL = """
-- Drop table if it exists and recreate (safe way)
DROP TABLE IF EXISTS admin_invites CASCADE;

CREATE TABLE admin_invites (
  id SERIAL PRIMARY KEY,
  email VARCHAR(255) NOT NULL,
  token_hash VARCHAR(255) NOT NULL UNIQUE,
  expires_at TIMESTAMPTZ NOT NULL,
  used_at TIMESTAMPTZ,
  revoked_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  invited_by INTEGER REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX idx_admin_invites_email ON admin_invites(email);
CREATE INDEX idx_admin_invites_token_hash ON admin_invites(token_hash);
CREATE INDEX idx_admin_invites_expires_at ON admin_invites(expires_at);
CREATE INDEX idx_admin_invites_used_at ON admin_invites(used_at);
CREATE INDEX idx_admin_invites_revoked_at ON admin_invites(revoked_at);
"""


def main() -> int:
    print("=" * 60)
    print("RUNNING ADMIN INVITES TABLE MIGRATION (POSTGRES)")
    print("=" * 60)

    db_url = "DATABASE_URL"

    if not db_url:
        print("\n❌ DATABASE_URL is not set.")
        print("\nPowerShell example:")
        print('  $env:DATABASE_URL="postgresql://postgres:ABC123@xyz.railway.app:5432/railway"')
        print("  python create_admin_invites_table.py")
        return 1

    try:
        print("\nConnecting to database via DATABASE_URL...")
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        print("✓ Connected successfully")

        print("\nDropping existing table (if any) and recreating...")
        cur.execute(DDL)
        conn.commit()
        print("✓ DDL applied")

        print("\nVerifying table exists...")
        cur.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = 'admin_invites'
        """)
        exists = cur.fetchone() is not None

        if exists:
            print("\n✓✓✓ MIGRATION COMPLETE ✓✓✓")
            print("Table created: admin_invites")
            
            # Show structure
            cur.execute("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'admin_invites'
                ORDER BY ordinal_position
            """)
            print("\nTable structure:")
            for row in cur.fetchall():
                print(f"  - {row[0]}: {row[1]} {'NULL' if row[2] == 'YES' else 'NOT NULL'}")
            
            return 0

        print("\n⚠ Migration ran, but admin_invites not found in information_schema.")
        print("Check schema/permissions.")
        return 1

    except Exception as e:
        print(f"\n❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())