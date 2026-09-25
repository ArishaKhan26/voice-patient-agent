# Voice AI Patient Registration Agent

A phone number you can call to register as a new patient by natural
conversation. The agent collects your demographics, reads them back for
confirmation, saves them to a persistent database, and hangs up. A REST
API and a small web dashboard expose the stored data.

**Call it**: `+1 (916) 659-1123`
**Dashboard / API base URL**: https://voice-patient-agent-xtnn.onrender.com
**Repo**: https://github.com/ArishaKhan26/voice-patient-agent

## Architecture

```
Caller's phone
     |  (regular PSTN call)
     v
Vapi  --  telephony + Deepgram (speech-to-text) + Vapi voice (text-to-speech)
     |  sends each conversation turn to an LLM, and calls tools via webhook
     v
Groq  --  runs the LLM (openai/gpt-oss-120b, via Vapi's "Custom LLM" integration)
     |  when the LLM decides to call find_patient / submit_patient
     v
FastAPI on Render  --  app/routers/vapi_webhook.py handles the tool calls
     |  same validation/DB layer is reused by the public REST API
     v
Neon Postgres  --  patients + call_logs tables, persists across restarts
```

The same FastAPI app also serves:
- `GET /patients`, `GET /patients/:id`, `POST /patients`, `PUT /patients/:id`,
  `DELETE /patients/:id` (soft delete) - the REST API, open/no auth (demo data
  only), consistent `{"data": ..., "error": ...}` envelope.
- `GET /patients/:id/calls` - call transcripts/summaries linked to a patient.
- `GET /` - the dashboard (patient list, filters, detail view with call
  history), plain HTML/CSS/vanilla JS, no build step.
- `POST /vapi/webhook` - the single endpoint Vapi calls for both tool
  invocations during a live call and the end-of-call report.

One shared Pydantic model (`app/schemas.py`) validates data for both the
REST API and the voice agent's tools, so a value is checked and normalized
the same way regardless of which path it came in through.

## Tech stack (and why)

| Layer | Choice | Why |
|---|---|---|
| Backend | FastAPI + Pydantic v2 | Async, automatic request validation, and a schema I could reuse verbatim between the REST API and the voice tools. |
| ORM / DB driver | SQLAlchemy 2 + psycopg 3 | Modern async-capable ORM; psycopg 3 (not psycopg2) is the actively maintained driver. |
| Database | Neon Postgres | Required over SQLite - Render's free-tier disk is wiped on every restart, so anything file-based would lose data. Neon's free tier persists. |
| Voice platform | Vapi | Abstracts telephony + STT + TTS behind one config and one webhook, which is the fastest path to a working phone number in a time-boxed build. |
| Speech-to-text | Deepgram (nova-2) | Vapi's default, solid accuracy for a live phone call. |
| LLM | Groq (see note below) | Fast inference, generous-enough free tier, OpenAI-compatible API so it plugs into Vapi's "Custom LLM" integration with just a base URL. |
| Hosting | Render (free web service) | Simple GitHub auto-deploy, matches the brief's constraint. |

## Setup (local development)

```bash
git clone https://github.com/ArishaKhan26/voice-patient-agent.git
cd voice-patient-agent
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in real values - see Env vars below
python -m app.init_db          # creates the patients table
python -m app.add_call_support # adds call_logs table + patients.vapi_call_id
uvicorn app.main:app --reload --port 8000
```

Visit `http://127.0.0.1:8000/` for the dashboard, `http://127.0.0.1:8000/docs`
for interactive API docs.

Run tests: `pytest tests/` (runs against your real `DATABASE_URL` - there's
no separate test DB; SQLite isn't used anywhere in this project per the
hard constraint above, so tests exercise the same Postgres dialect as
production, and clean up the rows they create afterward).

### Deploying / reconfiguring the Vapi assistant

`vapi/assistant.json` is the static template (tools, transcriber, voice,
end-call phrases); `vapi/setup_assistant.py` fills in secrets and dynamic
values from `.env` and creates or updates the assistant via Vapi's API:

```bash
python vapi/setup_assistant.py
```

Safe to re-run any time the prompt, tools, or model change - it detects
whether an assistant already exists (`vapi/.assistant_id`, gitignored) and
PATCHes it instead of creating a duplicate.

## Env vars

See `.env.example` for the full list with no values. Summary:

| Var | Purpose |
|---|---|
| `GROQ_API_KEY`, `GROQ_MODEL` | LLM credentials/model (see deviation note below) |
| `DATABASE_URL` | Neon Postgres connection string |
| `VAPI_API_KEY` | Used only by `vapi/setup_assistant.py` to create/update the assistant |
| `DEEPGRAM_API_KEY` | Not read directly by this app - Deepgram is configured through Vapi's dashboard/API, this key documents which account is in use |
| `VAPI_WEBHOOK_SECRET` | Shared secret checked on every `/vapi/webhook` request (see below) |
| `PUBLIC_BASE_URL` | This app's own public URL, used to construct the webhook URL sent to Vapi |
| `VAPI_PHONE_NUMBER` | The claimed number, documented here for reference |


## Data model

`patients` table: all fields from the spec, with DB-level `CHECK`
constraints (sex enum, phone/state/zip length, DOB not in the future) in
addition to Pydantic validation - so direct SQL writes are protected too,
not just API requests. `phone_number` is indexed but not unique (families
share numbers). Soft delete via `deleted_at`.

`call_logs` table: one row per call, `patient_id` nullable (a dropped call
before confirmation still gets logged, with nothing written to `patients`)
- transcript and summary from Vapi's end-of-call report, linked to the
patient via a `vapi_call_id` column on `patients` set at save time.

## Voice agent design

Two tools only, per the token-budget constraint:

- **`find_patient(phone)`** - returning-caller lookup.
- **`submit_patient(fields, confirmed, patient_id?)`** - `confirmed: false`
  validates and returns normalized values + field errors for read-back;
  `confirmed: true` saves. The optional `patient_id` (set when
  `find_patient` found an existing record and the caller wants to update
  it) makes the "update instead of create" duplicate-detection bonus
  actually functional - it updates that record instead of inserting a
  new one - without needing a third tool.

Full system prompt and the reasoning behind each instruction:
[`prompts/system_prompt.md`](prompts/system_prompt.md).

## Known limitations and deviations from the original plan

- **No silence/idle-message handling.** The plan called for idle prompts
  during silence; Vapi's current API has no `silenceTimeoutSeconds` or
  idle-message field at all (verified directly against their live OpenAPI
  spec, not just docs) - this appears to have been removed or restructured
  since the original design was written. Not implemented.
- **Webhook auth is a custom convention, not a Vapi-native feature.** Vapi's
  schema has no shared-secret field for webhooks. This build works around
  it by setting a static `x-webhook-secret` header via
  `assistant.server.headers`, checked in `app/routers/vapi_webhook.py`.
- **Deepgram phone-audio transcription isn't perfect** - digit sequences
  spoken quickly are occasionally misheard (e.g. "16" as "6"). Mitigated by
  the confirm/read-back step already required before saving, not fully
  solved (inherent to STT over a phone line).
- **Render free tier sleeps after 15 minutes idle** - the first request
  after a gap can take 30-60s. Worth pinging the `/health` endpoint to
  warm it up before a live demo/review call.
- **Groq's free tier is rate-limited per organization, not per app** -
  during development, competing test traffic against the same Groq account
  briefly triggered rate limits. Not an issue for isolated real usage, but
  worth knowing if load-testing against the same API key.

## Next steps (if continuing past the time box)

- Add a small proxy in front of Groq to implement true 429 fallback
  between two models, since Vapi's custom-llm integration doesn't support
  this natively.
- Spanish language support and appointment scheduling (explicitly
  deprioritized per the brief's own bonus ordering).
- Automated tests at the webhook-route level (current tests cover the tool
  functions directly and the REST API; a full simulated-payload test
  against `/vapi/webhook` itself would close the last gap).
- An uptime pinger (e.g. a free cron service hitting `/health` every few
  minutes) so the Render service never cold-starts during a review.
