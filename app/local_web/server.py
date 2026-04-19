"""FastAPI server for Sinai local network chat demo.

Run for local-network demos:
    python -m app.local_web.server

Or with uvicorn:
    uvicorn app.local_web.server:app --host 0.0.0.0 --port 8501 --reload
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware
import uvicorn

from app.local_web.services.context_provider import ContextProvider
from app.local_web.services.fallback_assistant import fallback_response
from app.local_web.services.ollama_client import OllamaClient
from app.local_web.services.prompting import build_messages
from app.local_web.services.session_store import SessionStore


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(
    title="Sinai Local Web Assistant",
    version="1.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SINAI_SESSION_SECRET", "sinai-demo-session-secret"),
    same_site="lax",
    https_only=False,
)

session_store = SessionStore(max_turns=16)
context_provider = ContextProvider()
ollama_client = OllamaClient()


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    mode: Literal["mock", "live"] = "mock"
    site_name: str = Field(default="Sinai Local Node", min_length=2, max_length=120)
    region: str | None = Field(default=None, max_length=120)


class ContextRequest(BaseModel):
    mode: Literal["mock", "live"] = "mock"
    site_name: str = Field(default="Sinai Local Node", min_length=2, max_length=120)
    region: str | None = Field(default=None, max_length=120)


def _get_session_id(request: Request) -> str:
    session_id = request.session.get("sinai_session_id")
    if not session_id:
        session_id = str(uuid.uuid4())
        request.session["sinai_session_id"] = session_id
    return session_id


@app.get("/")
def serve_index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/static/{file_path:path}")
def serve_static(file_path: str) -> FileResponse:
    target = (STATIC_DIR / file_path).resolve()
    if STATIC_DIR.resolve() not in target.parents and target != STATIC_DIR.resolve():
        raise HTTPException(status_code=404, detail="Not found")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(target)


@app.get("/api/health")
def health() -> dict[str, object]:
    state = ollama_client.health()
    return {
        "ok": state.ok,
        "status_text": state.status_text,
        "active_model": state.active_model,
        "host": ollama_client.host,
    }


@app.get("/api/context")
def get_context(
    mode: Literal["mock", "live"] = "mock",
    site_name: str = "Sinai Local Node",
    region: str | None = None,
) -> dict[str, object]:
    return context_provider.get_context(mode=mode, site_name=site_name, region=region)


@app.post("/api/context")
def post_context(payload: ContextRequest) -> dict[str, object]:
    return context_provider.get_context(
        mode=payload.mode,
        site_name=payload.site_name,
        region=payload.region,
    )


@app.get("/api/history")
def get_history(request: Request) -> dict[str, object]:
    session_id = _get_session_id(request)
    return {
        "session_id": session_id,
        "messages": session_store.history(session_id),
    }


@app.get("/api/live-feed")
def get_live_feed(limit: int = 30) -> dict[str, object]:
    return {
        "items": session_store.live_feed(limit=limit),
    }


@app.post("/api/reset")
def reset_history(request: Request) -> dict[str, object]:
    session_id = _get_session_id(request)
    session_store.clear(session_id)
    return {"ok": True}


@app.post("/api/chat")
def chat(request: Request, payload: ChatRequest) -> dict[str, object]:
    session_id = _get_session_id(request)
    question = payload.message.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    context = context_provider.get_context(
        mode=payload.mode,
        site_name=payload.site_name,
        region=payload.region,
    )
    history = session_store.history(session_id)
    messages = build_messages(
        user_message=question,
        context=context,
        history=history,
    )

    source = "ollama"
    model_name = None
    try:
        answer, model_name = ollama_client.chat(messages)
    except Exception:
        source = "fallback"
        answer = fallback_response(question, context)

    session_store.add_turn(session_id, role="user", content=question)
    session_store.add_turn(session_id, role="assistant", content=answer)

    return {
        "reply": answer,
        "source": source,
        "model": model_name,
        "context": context,
        "history": session_store.history(session_id),
    }


if __name__ == "__main__":
    uvicorn.run("app.local_web.server:app", host="0.0.0.0", port=8501, reload=False)
