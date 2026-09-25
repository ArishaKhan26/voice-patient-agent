import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import crud
from app.database import get_db
from app.schemas import CallLogOut, PatientCreate, PatientOut, PatientUpdate

router = APIRouter(prefix="/patients", tags=["patients"])


def envelope(data):
    return {"data": data, "error": None}


@router.get("")
def list_patients(
    last_name: str | None = None,
    date_of_birth: date | None = None,
    phone_number: str | None = None,
    db: Session = Depends(get_db),
):
    patients = crud.list_patients(db, last_name, date_of_birth, phone_number)
    return envelope([PatientOut.model_validate(p) for p in patients])


@router.get("/{patient_id}")
def get_patient(patient_id: uuid.UUID, db: Session = Depends(get_db)):
    patient = crud.get_patient(db, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return envelope(PatientOut.model_validate(patient))


@router.post("", status_code=201)
def create_patient(data: PatientCreate, db: Session = Depends(get_db)):
    patient = crud.create_patient(db, data)
    print(f"PATIENT CREATED: {patient.patient_id} {patient.first_name} {patient.last_name}")
    return envelope(PatientOut.model_validate(patient))


@router.put("/{patient_id}")
def update_patient(patient_id: uuid.UUID, data: PatientUpdate, db: Session = Depends(get_db)):
    patient = crud.get_patient(db, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    patient = crud.update_patient(db, patient, data)
    return envelope(PatientOut.model_validate(patient))


@router.get("/{patient_id}/calls")
def list_patient_calls(patient_id: uuid.UUID, db: Session = Depends(get_db)):
    patient = crud.get_patient(db, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    calls = crud.list_calls_for_patient(db, patient_id)
    return envelope([CallLogOut.model_validate(c) for c in calls])


@router.delete("/{patient_id}")
def delete_patient(patient_id: uuid.UUID, db: Session = Depends(get_db)):
    patient = crud.get_patient(db, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    patient = crud.soft_delete_patient(db, patient)
    return envelope(PatientOut.model_validate(patient))
