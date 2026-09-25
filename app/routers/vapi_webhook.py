"""Handles Vapi's server-URL webhook: tool calls made during a live call,
and the end-of-call report sent once the call ends.

Payload shapes verified directly against Vapi's live OpenAPI spec
(docs.vapi.ai/openapi/api-reference.json and .../webhooks.json) on
2026-09-25, not just prose docs - in particular:
  - ToolCall nests name/arguments under `function`, and `arguments`
    arrives as a JSON-encoded STRING, not an object (ToolCallFunction
    schema).
  - ToolCallResult.result must be a STRING, so tool results are
    json.dumps()'d before being returned.
  - end-of-call-report has no top-level `summary` field - it's under
    `analysis.summary` (ServerMessageEndOfCallReport / Analysis schemas).
  - `customer` lives at the top level of the message, not nested under
    `call` (ServerMessageEndOfCallReport schema).

The one thing NOT verifiable from the spec: the webhook auth mechanism
isn't a Vapi-native shared-secret field (there's no such field in the
current schema at all) - so instead this build defines its own contract:
setup_assistant.py sets a static `x-webhook-secret` header via
`assistant.server.headers`, and this file checks for that same header.
"""
import json
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
    x_webhook_secret: str | None = Header(default=None, alias="x-webhook-secret"),
):
    if WEBHOOK_SECRET and x_webhook_secret != WEBHOOK_SECRET:
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
        func = tc.get("function") or {}
        name = func.get("name")

        raw_arguments = func.get("arguments")
        if isinstance(raw_arguments, str):
            try:
                arguments = json.loads(raw_arguments) if raw_arguments else {}
            except json.JSONDecodeError:
                arguments = {}
        else:
            arguments = raw_arguments or {}

        if name == "find_patient":
            result = find_patient_tool(db, arguments)
        elif name == "submit_patient":
            result = submit_patient_tool(db, arguments, call_id)
        else:
            result = {"ok": False, "error": f"unknown tool: {name}"}

        results.append({"toolCallId": tool_call_id, "name": name, "result": json.dumps(result)})

    return {"results": results}


def _handle_end_of_call_report(db: Session, message: dict) -> None:
    call = message.get("call") or {}
    call_id = call.get("id")
    ended_reason = message.get("endedReason")

    artifact = message.get("artifact") or {}
    transcript = artifact.get("transcript")
    summary = (message.get("analysis") or {}).get("summary")

    phone_number = None
    raw_phone = (message.get("customer") or {}).get("number")
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
