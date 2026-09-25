import uuid

import pytest
from sqlalchemy import delete

from app.database import SessionLocal
from app.models import Patient
from app.vapi_tools import find_patient_tool, submit_patient_tool

VALID_FIELDS = {
    "first_name": "Vapi",
    "last_name": "Caller",
    "date_of_birth": "01/01/1980",
    "sex": "Other",
    "phone_number": "555-777-0000",
    "address_line_1": "1 Call St",
    "city": "Columbus",
    "state": "OH",
    "zip_code": "43215",
}


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.execute(delete(Patient).where(Patient.phone_number == "5557770000"))
    session.commit()
    session.close()


def test_find_patient_tool_not_found(db):
    result = find_patient_tool(db, {"phone": "555-777-0000"})
    assert result == {"found": False}


def test_submit_patient_tool_create_then_find(db):
    preview = submit_patient_tool(db, {"fields": VALID_FIELDS, "confirmed": False}, "call-1")
    assert preview["ok"] is True
    assert preview["confirmed"] is False
    assert preview["normalized"]["state"] == "OH"

    saved = submit_patient_tool(db, {"fields": VALID_FIELDS, "confirmed": True}, "call-1")
    assert saved["ok"] is True
    assert saved["confirmed"] is True
    patient_id = saved["patient_id"]

    found = find_patient_tool(db, {"phone": "5557770000"})
    assert found["found"] is True
    assert found["patient_id"] == patient_id


def test_submit_patient_tool_invalid_fields(db):
    bad_fields = {**VALID_FIELDS, "phone_number": "123"}
    result = submit_patient_tool(db, {"fields": bad_fields, "confirmed": False}, "call-2")
    assert result["ok"] is False
    assert "phone_number" in result["errors"]


def test_submit_patient_tool_update_existing(db):
    created = submit_patient_tool(db, {"fields": VALID_FIELDS, "confirmed": True}, "call-3")
    patient_id = created["patient_id"]

    updated = submit_patient_tool(
        db,
        {"fields": {"city": "Cleveland"}, "confirmed": True, "patient_id": patient_id},
        "call-4",
    )
    assert updated["ok"] is True
    assert updated["patient_id"] == patient_id

    patient = db.get(Patient, uuid.UUID(patient_id))
    assert patient.city == "Cleveland"
    assert patient.last_name == "Caller"  # untouched fields stay as-is
