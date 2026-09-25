"""One-off, idempotent migration: adds vapi_call_id to patients and
creates the call_logs table. Safe to re-run - uses IF NOT EXISTS.
Run with: source venv/bin/activate && python -m app.add_call_support
"""
from sqlalchemy import text

from app.database import Base, engine
from app.models import CallLog, Patient  # noqa: F401 - registers models with Base

with engine.begin() as conn:
    conn.execute(text("ALTER TABLE patients ADD COLUMN IF NOT EXISTS vapi_call_id VARCHAR(64)"))
    conn.execute(
        text("CREATE INDEX IF NOT EXISTS ix_patients_vapi_call_id ON patients (vapi_call_id)")
    )

Base.metadata.create_all(bind=engine)
print("OK: patients.vapi_call_id ready, call_logs table ready")
