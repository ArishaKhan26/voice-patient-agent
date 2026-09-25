"""Creates or updates the Vapi assistant from vapi/assistant.json +
prompts/system_prompt.md, filling in secrets/dynamic values from .env at
runtime - the committed assistant.json never contains real secrets.

Run this in Stage 5, AFTER deploying to Render and setting PUBLIC_BASE_URL,
since the webhook needs a real public URL for Vapi to call.

Usage: source venv/bin/activate && python vapi/setup_assistant.py

Field shapes below were verified directly against Vapi's live OpenAPI
spec (docs.vapi.ai/openapi/api-reference.json) on 2026-09-25, after an
initial guess-based version got rejected by the API on both `model.apiKey`
and `model.credentialId` (Vapi's actual pattern: create a Credential
resource, then reference it via the assistant's top-level `credentialIds`
array - not any field on `model` itself). Webhook auth is NOT a
Vapi-native field (there's no shared-secret field in the schema at all) -
this build instead sets a static `x-webhook-secret` header via
`assistant.server.headers`, checked in app/routers/vapi_webhook.py.

IMPORTANT: model.metadataSendMode is explicitly set to "off" in
assistant.json. Vapi's default ("variable") injects the entire `call` and
`assistant` config objects as extra top-level fields into the raw request
it sends to the custom-llm endpoint. Groq's strict OpenAI-compatible
validator rejects this outright ("property 'assistant' is unsupported",
HTTP 400) - every single test call failed on this until it was found by
pulling the raw request/response out of Vapi's call-logs endpoint
(GET /call/{id}/call-logs). This was NOT model-specific - it broke every
Groq model tried (llama-3.3-70b-versatile before it was deprecated,
openai/gpt-oss-120b, openai/gpt-oss-20b, qwen/qwen3.8-27b), which is why
several earlier debugging detours (assuming it was a reasoning-model
streaming-format issue, or a Groq per-minute rate limit) were dead ends.
"""
import json
import os
import re
import sys

import httpx
from dotenv import load_dotenv

load_dotenv()

VAPI_API_KEY = os.getenv("VAPI_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL")
VAPI_WEBHOOK_SECRET = os.getenv("VAPI_WEBHOOK_SECRET")

HERE = os.path.dirname(os.path.abspath(__file__))
ASSISTANT_ID_FILE = os.path.join(HERE, ".assistant_id")
CREDENTIAL_ID_FILE = os.path.join(HERE, ".credential_id")
ASSISTANT_JSON_PATH = os.path.join(HERE, "assistant.json")
SYSTEM_PROMPT_PATH = os.path.join(os.path.dirname(HERE), "prompts", "system_prompt.md")

VAPI_BASE = "https://api.vapi.ai"


def _require(value, name):
    if not value:
        print(f"FAIL: {name} is not set in .env")
        sys.exit(1)
    return value


def load_system_prompt() -> str:
    with open(SYSTEM_PROMPT_PATH) as f:
        content = f.read()
    match = re.search(r"```text\n(.*?)\n```", content, re.DOTALL)
    if not match:
        print("FAIL: couldn't find the ```text fenced prompt block in prompts/system_prompt.md")
        sys.exit(1)
    return match.group(1).strip()


def get_or_create_groq_credential(client: httpx.Client, headers: dict) -> str:
    """Vapi's custom-llm provider takes the API key via a separate
    Credential resource, referenced from the assistant's top-level
    credentialIds array (confirmed via Vapi's OpenAPI spec - CreateAssistantDTO
    has no apiKey or credentialId field anywhere on `model` itself)."""
    if os.path.exists(CREDENTIAL_ID_FILE):
        with open(CREDENTIAL_ID_FILE) as f:
            cached = f.read().strip()
        if cached:
            return cached

    resp = client.post(
        f"{VAPI_BASE}/credential",
        headers=headers,
        json={"provider": "custom-llm", "apiKey": GROQ_API_KEY, "name": "groq"},
    )
    if resp.status_code not in (200, 201):
        print(f"FAIL: creating Groq credential returned {resp.status_code}")
        print(resp.text)
        sys.exit(1)

    credential_id = resp.json()["id"]
    with open(CREDENTIAL_ID_FILE, "w") as f:
        f.write(credential_id)
    return credential_id


def build_payload(credential_id: str) -> dict:
    with open(ASSISTANT_JSON_PATH) as f:
        payload = json.load(f)

    system_prompt = load_system_prompt()
    payload["model"]["model"] = GROQ_MODEL
    payload["model"]["messages"][0]["content"] = system_prompt

    payload["credentialIds"] = [credential_id]
    payload["server"] = {
        "url": f"{PUBLIC_BASE_URL.rstrip('/')}/vapi/webhook",
        "headers": {"x-webhook-secret": VAPI_WEBHOOK_SECRET},
    }

    return payload


def main():
    _require(VAPI_API_KEY, "VAPI_API_KEY")
    _require(GROQ_API_KEY, "GROQ_API_KEY")
    _require(PUBLIC_BASE_URL, "PUBLIC_BASE_URL")
    _require(VAPI_WEBHOOK_SECRET, "VAPI_WEBHOOK_SECRET")

    headers = {"Authorization": f"Bearer {VAPI_API_KEY}", "Content-Type": "application/json"}

    existing_id = None
    if os.path.exists(ASSISTANT_ID_FILE):
        with open(ASSISTANT_ID_FILE) as f:
            existing_id = f.read().strip() or None

    with httpx.Client(timeout=30) as client:
        credential_id = get_or_create_groq_credential(client, headers)
        payload = build_payload(credential_id)

        if existing_id:
            resp = client.patch(f"{VAPI_BASE}/assistant/{existing_id}", headers=headers, json=payload)
        else:
            resp = client.post(f"{VAPI_BASE}/assistant", headers=headers, json=payload)

    if resp.status_code not in (200, 201):
        print(f"FAIL: Vapi API returned {resp.status_code}")
        print(resp.text)
        sys.exit(1)

    data = resp.json()
    assistant_id = data.get("id")
    with open(ASSISTANT_ID_FILE, "w") as f:
        f.write(assistant_id or "")

    action = "Updated" if existing_id else "Created"
    print(f"OK: {action} assistant {assistant_id}")
    print(f"    server.url -> {payload['server']['url']}")
    print("    Next: open this assistant in the Vapi dashboard, do a test web call,")
    print("    then claim a free phone number and attach it to this assistant.")


if __name__ == "__main__":
    main()
