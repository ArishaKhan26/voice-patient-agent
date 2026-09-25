"""The two voice-agent tools, as plain functions decoupled from Vapi's
webhook payload shape - app/routers/vapi_webhook.py handles parsing
Vapi's request/response format; this file just does the work.
"""
import uuid

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app import crud
from app.normalize import normalize_phone
from app.schemas import PatientCreate, PatientUpdate


def _field_errors_from(exc: ValidationError) -> dict[str, str]:
    errors = {}
    for err in exc.errors():
        loc = [str(p) for p in err["loc"] if p != "body"]
        field = loc[-1] if loc else "unknown"
        errors[field] = err["msg"]
    return errors


def find_patient_tool(db: Session, arguments: dict) -> dict:
    """Returning-caller / duplicate detection. arguments: {"phone": "..."}"""
    phone = normalize_phone(str(arguments.get("phone", "")))
    if len(phone) != 10:
        return {"found": False, "error": "phone number must have 10 digits"}

    patient = crud.find_by_phone(db, phone)
    if patient is None:
        return {"found": False}

    return {
        "found": True,
        "patient_id": str(patient.patient_id),
        "first_name": patient.first_name,
        "last_name": patient.last_name,
    }


def submit_patient_tool(db: Session, arguments: dict, call_id: str | None) -> dict:
    """arguments: {"fields": {...patient data...}, "confirmed": bool,
    "patient_id": optional str}.
    confirmed=false: validate + normalize only, for read-back.
    confirmed=true: validate + save to the database.
    patient_id present (from an earlier find_patient hit in this same
    call): updates that existing record instead of creating a new one -
    this is what makes the "update instead of create" duplicate-detection
    flow real rather than just spoken acknowledgment."""
    fields = arguments.get("fields") or {}
    confirmed = bool(arguments.get("confirmed", False))
    patient_id_raw = arguments.get("patient_id")

    if patient_id_raw:
        return _update_existing_patient(db, fields, confirmed, patient_id_raw, call_id)
    return _create_new_patient(db, fields, confirmed, call_id)


def _create_new_patient(db: Session, fields: dict, confirmed: bool, call_id: str | None) -> dict:
    try:
        data = PatientCreate(**fields)
    except ValidationError as exc:
        return {"ok": False, "confirmed": False, "errors": _field_errors_from(exc)}

    if not confirmed:
        return {"ok": True, "confirmed": False, "normalized": data.model_dump(mode="json")}

    try:
        patient = crud.create_patient(db, data)
        if call_id:
            crud.link_patient_call(db, patient, call_id)
        print(
            f"PATIENT SAVED via call {call_id}: {patient.patient_id} "
            f"{patient.first_name} {patient.last_name}"
        )
        return {
            "ok": True,
            "confirmed": True,
            "patient_id": str(patient.patient_id),
            "message": f"You're all set, {patient.first_name}.",
        }
    except Exception as exc:
        print(f"DB WRITE FAILED during call {call_id}: {exc}\nPayload was: {fields}")
        return {
            "ok": False,
            "confirmed": True,
            "error": "database_error",
            "message": "I'm sorry, I couldn't save your information just now. Let's try that one more time.",
        }


def _update_existing_patient(
    db: Session, fields: dict, confirmed: bool, patient_id_raw, call_id: str | None
) -> dict:
    try:
        data = PatientUpdate(**fields)
    except ValidationError as exc:
        return {"ok": False, "confirmed": False, "errors": _field_errors_from(exc)}

    if not confirmed:
        return {
            "ok": True,
            "confirmed": False,
            "normalized": data.model_dump(mode="json", exclude_unset=True),
        }

    try:
        patient_uuid = uuid.UUID(str(patient_id_raw))
    except ValueError:
        return {"ok": False, "error": "that patient record id wasn't valid"}

    patient = crud.get_patient(db, patient_uuid)
    if patient is None:
        return {"ok": False, "error": "couldn't find that patient record to update"}

    try:
        patient = crud.update_patient(db, patient, data)
        if call_id:
            crud.link_patient_call(db, patient, call_id)
        print(f"PATIENT UPDATED via call {call_id}: {patient.patient_id} {patient.first_name} {patient.last_name}")
        return {
            "ok": True,
            "confirmed": True,
            "patient_id": str(patient.patient_id),
            "message": f"You're all updated, {patient.first_name}.",
        }
    except Exception as exc:
        print(f"DB WRITE FAILED during call {call_id}: {exc}\nPayload was: {fields}")
        return {
            "ok": False,
            "confirmed": True,
            "error": "database_error",
            "message": "I'm sorry, I couldn't save your information just now. Let's try that one more time.",
        }
