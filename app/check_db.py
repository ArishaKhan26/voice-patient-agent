"""One-off script: confirms DATABASE_URL in .env actually connects.
Prints only success/failure - never the connection string itself.
Run with: source venv/bin/activate && python app/check_db.py
"""
import os
import sys

from dotenv import load_dotenv

load_dotenv()

database_url = os.getenv("DATABASE_URL")

if not database_url:
    print("FAIL: DATABASE_URL is not set in .env")
    sys.exit(1)

try:
    import psycopg

    with psycopg.connect(database_url, connect_timeout=10) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT version();")
            version = cur.fetchone()[0]
    print("OK: connected to Postgres")
    print(f"    server: {version.split(',')[0]}")
except Exception as e:
    print(f"FAIL: could not connect - {type(e).__name__}: {e}")
    sys.exit(1)
