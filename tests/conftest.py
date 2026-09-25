import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.database import SessionLocal
from app.main import app
from app.models import Patient


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def cleanup_patients():
    """Hard-deletes any patients created during a test, by phone number,
    so the test suite doesn't leave demo data behind in Neon."""
    created_phones = []
    yield created_phones
    if created_phones:
        db = SessionLocal()
        try:
            db.execute(delete(Patient).where(Patient.phone_number.in_(created_phones)))
            db.commit()
        finally:
            db.close()
