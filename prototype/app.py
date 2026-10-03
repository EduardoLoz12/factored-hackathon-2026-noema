"""API local, sin credenciales bancarias ni acciones financieras reales."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from prototype.core import Core

ROOT = Path(__file__).resolve().parent
core = Core(os.environ.get("NOEMA_DEMO_DB", "data/prototype/demo.sqlite"))
app = FastAPI(title="Noema Local · Demo", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])
ALLOWED_ORIGINS = {"http://127.0.0.1:8765", "http://localhost:8765"}


@app.middleware("http")
async def local_only(request: Request, call_next):
    if request.method == "POST":
        origin = request.headers.get("origin")
        if origin is not None and origin not in ALLOWED_ORIGINS:
            return JSONResponse({"detail": "Origen no permitido"}, status_code=403)
        if request.headers.get("x-noema-local") != "1":
            return JSONResponse({"detail": "Falta control local"}, status_code=403)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "connect-src 'self'; media-src 'self' blob:; img-src 'self' data:; frame-ancestors 'none'"
    )
    response.headers["Permissions-Policy"] = "microphone=(self), camera=()"
    return response


def authenticated(request):
    token = request.cookies.get("noema_session", "")
    try:
        core.authenticate(token, request.headers.get("x-csrf-token", ""))
    except PermissionError as exc:
        raise HTTPException(401, "Inicia una sesión demo nueva") from exc
    return token


class Message(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class Confirmation(BaseModel):
    action_id: str = Field(min_length=1, max_length=100)


@app.get("/api/health")
def health():
    return {
        "status": "local_demo",
        "paid_services": False,
        "voice_model_ready": Path("data/models/whisper-tiny/model.bin").exists(),
        "real_bank_connected": False,
    }


@app.post("/api/session")
def session():
    token, csrf = core.session()
    result = JSONResponse({"csrf": csrf, "mode": "demo", "name": "Cliente demo"})
    result.set_cookie("noema_session", token, httponly=True, samesite="strict", max_age=7200)
    return result


@app.post("/api/chat")
def chat(body: Message, request: Request):
    token = authenticated(request)
    return core.chat(token, body.message)


@app.post("/api/confirm")
def confirm(body: Confirmation, request: Request):
    token = authenticated(request)
    try:
        return core.confirm(token, body.action_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.get("/api/cases")
def cases(request: Request):
    token = authenticated(request)
    with core.connect() as db:
        rows = db.execute(
            "SELECT id,reason,status FROM cases WHERE session=? ORDER BY created DESC", (token,)
        ).fetchall()
    return {"cases": [dict(row) for row in rows], "real_handoff_connected": False}


@app.post("/api/transcribe")
def transcribe(request: Request, audio: UploadFile):
    authenticated(request)
    content = audio.file.read(8 * 1024 * 1024 + 1)
    if len(content) > 8 * 1024 * 1024:
        raise HTTPException(413, "Audio demasiado grande; usa menos de 30 segundos")
    model_path = Path("data/models/whisper-tiny")
    if not (model_path / "model.bin").exists():
        raise HTTPException(503, "Reconocimiento local pendiente; escribe tu mensaje")
    from faster_whisper import WhisperModel

    try:
        with tempfile.NamedTemporaryFile(suffix=".audio") as file:
            file.write(content)
            file.flush()
            model = WhisperModel(
                str(model_path),
                device="cpu",
                compute_type="int8",
                local_files_only=True,
                cpu_threads=2,
            )
            segments, info = model.transcribe(file.name, beam_size=1)
            if info.duration > 35:
                raise HTTPException(413, "La grabación supera 30 segundos")
            transcript = " ".join(segment.text.strip() for segment in segments)
        return {
            "text": transcript,
            "language": info.language,
            "requires_user_review": True,
            "processing": "local",
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(422, "No pude transcribir el audio; puedes escribirlo") from exc


app.mount("/", StaticFiles(directory=ROOT / "web", html=True), name="web")
