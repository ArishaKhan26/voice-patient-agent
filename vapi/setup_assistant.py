"""Creates or updates the Vapi assistant from vapi/assistant.json +
prompts/system_prompt.md, filling in secrets/dynamic values from .env at
runtime - the committed assistant.json never contains real secrets.

Run this in Stage 5, AFTER deploying to Render and setting PUBLIC_BASE_URL,
since the webhook needs a real public URL for Vapi to call.

Usage: source venv/bin/activate && python vapi/setup_assistant.py

NOTE on assumptions: a few Vapi field names below (model.url for
custom-llm, model.apiKey, messagePlan.idleMessages, endCallFunctionEnabled)
were not fully confirmed against Vapi's docs during development - they're
based on the most common documented pattern, but Vapi's schema does
change. After running this script, open the assistant in the Vapi
dashboard and check the Model tab: if the Groq connection or system
prompt don't look right there, paste the Groq API key in manually and
adjust the field that didn't take (the tools/serverUrl/transcriber
sections are more confidently correct and shouldn't need touching).
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


def build_payload() -> dict:
    with open(ASSISTANT_JSON_PATH) as f:
        payload = json.load(f)

    system_prompt = load_system_prompt()
    payload["model"]["model"] = GROQ_MODEL
    payload["model"]["messages"][0]["content"] = system_prompt
    payload["model"]["apiKey"] = GROQ_API_KEY  # best-effort field name, see module docstring

    payload["serverUrl"] = f"{PUBLIC_BASE_URL.rstrip('/')}/vapi/webhook"
    payload["serverUrlSecret"] = VAPI_WEBHOOK_SECRET

    return payload


def main():
    _require(VAPI_API_KEY, "VAPI_API_KEY")
    _require(GROQ_API_KEY, "GROQ_API_KEY")
    _require(PUBLIC_BASE_URL, "PUBLIC_BASE_URL")
    _require(VAPI_WEBHOOK_SECRET, "VAPI_WEBHOOK_SECRET")

    payload = build_payload()
    headers = {"Authorization": f"Bearer {VAPI_API_KEY}", "Content-Type": "application/json"}

    existing_id = None
    if os.path.exists(ASSISTANT_ID_FILE):
        with open(ASSISTANT_ID_FILE) as f:
            existing_id = f.read().strip() or None

    with httpx.Client(timeout=30) as client:
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
    print(f"    serverUrl -> {payload['serverUrl']}")
    print("    Next: open this assistant in the Vapi dashboard, do a test web call,")
    print("    then claim a free phone number and attach it to this assistant.")


if __name__ == "__main__":
    main()
