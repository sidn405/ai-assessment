import os
import sys
import psycopg2


DDL = """
CREATE TABLE IF NOT EXISTS admin_invites (
  id SERIAL PRIMARY KEY,
  email TEXT NOT NULL,
  token_hash TEXT NOT NULL UNIQUE,
  expires_at TIMESTAMPTZ NOT NULL,
  used_at TIMESTAMPTZ,
  revoked_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  invited_by INTEGER
);

CREATE INDEX IF NOT EXISTS idx_admin_invites_email ON admin_invites(email);
CREATE INDEX IF NOT EXISTS idx_admin_invites_expires_at ON admin_invites(expires_at);
CREATE INDEX IF NOT EXISTS idx_admin_invites_used_at ON admin_invites(used_at);
CREATE INDEX IF NOT EXISTS idx_admin_invites_revoked_at ON admin_invites(revoked_at);
"""

DATABASE_URL="postgresql://postgres:SKSlhHaXStrzUeYLftOkMFwcoKHSMRSo@ballast.proxy.rlwy.net:49390/railway"

def get_conn():
    # Prefer Railway-style DATABASE_URL
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        return psycopg2.connect(db_url)

    # Fallback to discrete env vars
    host = os.getenv("PGHOST", "localhost")
    port = int(os.getenv("PGPORT", "5432"))
    user = os.getenv("PGUSER", "postgres")
    password = os.getenv("PGPASSWORD", "")
    dbname = os.getenv("PGDATABASE", "postgres")

    return psycopg2.connect(
        host=host, port=port, user=user, password=password, dbname=dbname
    )


def main():
    try:
        conn = get_conn()
    except Exception as e:
        print("❌ Failed to connect to Postgres:", e)
        sys.exit(1)

    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(DDL)
        print("✅ admin_invites table + indexes created (or already existed).")
    except Exception as e:
        print("❌ Failed to run DDL:", e)
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
