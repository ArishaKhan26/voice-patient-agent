import os
import sys

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.routers import patients, vapi_webhook

app = FastAPI(title="Patient Registration API")

app.include_router(patients.router)
app.include_router(vapi_webhook.router)

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


@app.get("/")
def dashboard():
    return FileResponse(os.path.join(STATIC_DIR, "dashboard.html"))


@app.get("/health")
def health():
    return {"data": {"status": "ok"}, "error": None}


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()

    if any(e.get("type") == "json_invalid" for e in errors):
        return JSONResponse(status_code=400, content={"data": None, "error": "Malformed JSON in request body"})

    field_errors = {}
    for e in errors:
        loc = [str(p) for p in e["loc"] if p != "body"]
        field = loc[-1] if loc else "body"
        field_errors[field] = e["msg"]

    return JSONResponse(status_code=422, content={"data": None, "error": field_errors})


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(status_code=exc.status_code, content={"data": None, "error": exc.detail})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    print(f"UNHANDLED ERROR on {request.method} {request.url.path}: {exc}", file=sys.stderr)
    return JSONResponse(status_code=500, content={"data": None, "error": "Internal server error"})
