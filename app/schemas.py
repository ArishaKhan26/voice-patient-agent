"""Pydantic v2 models shared by the REST API and the voice agent's tools.
One set of validators means a value is checked and normalized the same
way whether it came from a typed POST body or a spoken phone call.
"""
import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from app.normalize import (
    validate_city,
    validate_dob,
    validate_email_field,
    validate_member_id,
    validate_name,
    validate_phone,
    validate_state,
    validate_zip,
)

Sex = Literal["Male", "Female", "Other", "Decline to Answer"]


class PatientCreate(BaseModel):
    first_name: str
    last_name: str
    date_of_birth: date
    sex: Sex
    phone_number: str
    email: str | None = None
    address_line_1: str
    address_line_2: str | None = None
    city: str
    state: str
    zip_code: str
    insurance_provider: str | None = None
    insurance_member_id: str | None = None
    preferred_language: str = "English"
    emergency_contact_name: str | None = None
    emergency_contact_phone: str | None = None

    @field_validator("first_name")
    @classmethod
    def _first_name(cls, v: str) -> str:
        return validate_name(v, "first name")

    @field_validator("last_name")
    @classmethod
    def _last_name(cls, v: str) -> str:
        return validate_name(v, "last name")

    @field_validator("date_of_birth", mode="before")
    @classmethod
    def _dob(cls, v) -> date:
        return validate_dob(v)

    @field_validator("phone_number")
    @classmethod
    def _phone(cls, v: str) -> str:
        return validate_phone(v)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str | None) -> str | None:
        return validate_email_field(v) if v else None

    @field_validator("address_line_1")
    @classmethod
    def _address_line_1(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("address line 1 is required")
        return v

    @field_validator("city")
    @classmethod
    def _city(cls, v: str) -> str:
        return validate_city(v)

    @field_validator("state")
    @classmethod
    def _state(cls, v: str) -> str:
        return validate_state(v)

    @field_validator("zip_code")
    @classmethod
    def _zip(cls, v: str) -> str:
        return validate_zip(v)

    @field_validator("insurance_member_id")
    @classmethod
    def _member_id(cls, v: str | None) -> str | None:
        return validate_member_id(v) if v else None

    @field_validator("emergency_contact_phone")
    @classmethod
    def _emergency_phone(cls, v: str | None) -> str | None:
        return validate_phone(v, "emergency contact phone") if v else None


class PatientUpdate(BaseModel):
    """Same field rules as PatientCreate, but every field is optional -
    used for partial PUT updates."""

    first_name: str | None = None
    last_name: str | None = None
    date_of_birth: date | None = None
    sex: Sex | None = None
    phone_number: str | None = None
    email: str | None = None
    address_line_1: str | None = None
    address_line_2: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    insurance_provider: str | None = None
    insurance_member_id: str | None = None
    preferred_language: str | None = None
    emergency_contact_name: str | None = None
    emergency_contact_phone: str | None = None

    @field_validator("first_name")
    @classmethod
    def _first_name(cls, v):
        return validate_name(v, "first name") if v else v

    @field_validator("last_name")
    @classmethod
    def _last_name(cls, v):
        return validate_name(v, "last name") if v else v

    @field_validator("date_of_birth", mode="before")
    @classmethod
    def _dob(cls, v):
        return validate_dob(v) if v else v

    @field_validator("phone_number")
    @classmethod
    def _phone(cls, v):
        return validate_phone(v) if v else v

    @field_validator("email")
    @classmethod
    def _email(cls, v):
        return validate_email_field(v) if v else v

    @field_validator("city")
    @classmethod
    def _city(cls, v):
        return validate_city(v) if v else v

    @field_validator("state")
    @classmethod
    def _state(cls, v):
        return validate_state(v) if v else v

    @field_validator("zip_code")
    @classmethod
    def _zip(cls, v):
        return validate_zip(v) if v else v

    @field_validator("insurance_member_id")
    @classmethod
    def _member_id(cls, v):
        return validate_member_id(v) if v else v

    @field_validator("emergency_contact_phone")
    @classmethod
    def _emergency_phone(cls, v):
        return validate_phone(v, "emergency contact phone") if v else v


class PatientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    patient_id: uuid.UUID
    first_name: str
    last_name: str
    date_of_birth: date
    sex: str
    phone_number: str
    email: str | None
    address_line_1: str
    address_line_2: str | None
    city: str
    state: str
    zip_code: str
    insurance_provider: str | None
    insurance_member_id: str | None
    preferred_language: str
    emergency_contact_name: str | None
    emergency_contact_phone: str | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class CallLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    vapi_call_id: str | None
    phone_number: str | None
    transcript: str | None
    summary: str | None
    ended_reason: str | None
    created_at: datetime
