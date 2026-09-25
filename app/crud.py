import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CallLog, Patient
from app.schemas import PatientCreate, PatientUpdate


def create_patient(db: Session, data: PatientCreate) -> Patient:
    patient = Patient(**data.model_dump())
    db.add(patient)
    db.commit()
    db.refresh(patient)
    return patient


def get_patient(db: Session, patient_id: uuid.UUID) -> Patient | None:
    stmt = select(Patient).where(
        Patient.patient_id == patient_id, Patient.deleted_at.is_(None)
    )
    return db.execute(stmt).scalar_one_or_none()


def list_patients(
    db: Session,
    last_name: str | None = None,
    date_of_birth=None,
    phone_number: str | None = None,
) -> list[Patient]:
    stmt = select(Patient).where(Patient.deleted_at.is_(None))
    if last_name:
        stmt = stmt.where(Patient.last_name.ilike(last_name))
    if date_of_birth:
        stmt = stmt.where(Patient.date_of_birth == date_of_birth)
    if phone_number:
        stmt = stmt.where(Patient.phone_number == phone_number)
    stmt = stmt.order_by(Patient.created_at.desc())
    return list(db.execute(stmt).scalars().all())


def find_by_phone(db: Session, phone_number: str) -> Patient | None:
    """Most recent active patient at this phone number - used for
    returning-caller / duplicate detection."""
    stmt = (
        select(Patient)
        .where(Patient.phone_number == phone_number, Patient.deleted_at.is_(None))
        .order_by(Patient.created_at.desc())
    )
    return db.execute(stmt).scalars().first()


def update_patient(db: Session, patient: Patient, data: PatientUpdate) -> Patient:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(patient, field, value)
    db.commit()
    db.refresh(patient)
    return patient


def soft_delete_patient(db: Session, patient: Patient) -> Patient:
    patient.deleted_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(patient)
    return patient


def link_patient_call(db: Session, patient: Patient, call_id: str) -> None:
    patient.vapi_call_id = call_id
    db.commit()


def find_patient_by_call_id(db: Session, call_id: str) -> Patient | None:
    stmt = select(Patient).where(Patient.vapi_call_id == call_id)
    return db.execute(stmt).scalar_one_or_none()


def create_call_log(
    db: Session,
    vapi_call_id: str | None,
    patient_id: uuid.UUID | None,
    phone_number: str | None,
    transcript: str | None,
    summary: str | None,
    ended_reason: str | None,
) -> CallLog:
    log = CallLog(
        vapi_call_id=vapi_call_id,
        patient_id=patient_id,
        phone_number=phone_number,
        transcript=transcript,
        summary=summary,
        ended_reason=ended_reason,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log
