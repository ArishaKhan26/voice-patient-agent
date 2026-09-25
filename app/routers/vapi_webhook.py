"""Handles Vapi's server-URL webhook: tool calls made during a live call,
and the end-of-call report sent once the call ends.

Payload shapes verified against Vapi's docs (docs.vapi.ai) as of this
build. Two fields below are documented assumptions rather than confirmed
facts, since Vapi's docs were incomplete/ambiguous on them - both are
coded defensively (checked in multiple possible locations) and should be
double-checked against a real test call in the Vapi dashboard:
  1. The webhook-secret header name (assumed: "x-vapi-secret").
  2. Where "summary" lives on the end-of-call-report (checked in three
     possible locations: message.summary, message.analysis.summary,
     and artifact.summary).
"""
import os

from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app import crud
from app.database import SessionLocal
from app.normalize import normalize_phone
from app.vapi_tools import find_patient_tool, submit_patient_tool

router = APIRouter(prefix="/vapi", tags=["vapi"])

WEBHOOK_SECRET = os.getenv("VAPI_WEBHOOK_SECRET")


@router.post("/webhook")
async def vapi_webhook(
    request: Request,
    x_vapi_secret: str | None = Header(default=None, alias="x-vapi-secret"),
):
    if WEBHOOK_SECRET and x_vapi_secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="invalid webhook secret")

    body = await request.json()
    message = body.get("message", {})
    msg_type = message.get("type")

    db = SessionLocal()
    try:
        if msg_type == "tool-calls":
            return _handle_tool_calls(db, message)
        if msg_type == "end-of-call-report":
            _handle_end_of_call_report(db, message)
            return {}
        # Other message types (status-update, transcript, speech-update,
        # assistant-request, etc.) aren't used by this build - ack quietly.
        return {}
    finally:
        db.close()


def _handle_tool_calls(db: Session, message: dict) -> dict:
    call = message.get("call") or {}
    call_id = call.get("id")
    tool_calls = message.get("toolCallList") or []

    results = []
    for tc in tool_calls:
        tool_call_id = tc.get("id")
        name = tc.get("name")
        arguments = tc.get("arguments") or {}

        if name == "find_patient":
            result = find_patient_tool(db, arguments)
        elif name == "submit_patient":
            result = submit_patient_tool(db, arguments, call_id)
        else:
            result = {"ok": False, "error": f"unknown tool: {name}"}

        results.append({"toolCallId": tool_call_id, "result": result})

    return {"results": results}


def _handle_end_of_call_report(db: Session, message: dict) -> None:
    call = message.get("call") or {}
    call_id = call.get("id")
    ended_reason = message.get("endedReason")

    artifact = message.get("artifact") or {}
    transcript = artifact.get("transcript") or message.get("transcript")
    summary = (
        message.get("summary")
        or (message.get("analysis") or {}).get("summary")
        or artifact.get("summary")
    )

    phone_number = None
    raw_phone = (call.get("customer") or {}).get("number")
    if raw_phone:
        phone_number = normalize_phone(str(raw_phone))

    patient = crud.find_patient_by_call_id(db, call_id) if call_id else None
    if patient is None and phone_number:
        patient = crud.find_by_phone(db, phone_number)

    crud.create_call_log(
        db,
        vapi_call_id=call_id,
        patient_id=patient.patient_id if patient else None,
        phone_number=phone_number,
        transcript=transcript,
        summary=summary,
        ended_reason=ended_reason,
    )

    print(
        f"CALL ENDED {call_id} reason={ended_reason} "
        f"patient={patient.patient_id if patient else 'unmatched'}"
    )
    if transcript:
        print(f"TRANSCRIPT ({call_id}):\n{transcript}")
