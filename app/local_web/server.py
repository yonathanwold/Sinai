"""FastAPI server for Sinai local multi-device hackathon demo.

Run:
    python -m app.local_web.server

Or with uvicorn:
    uvicorn app.local_web.server:app --host 0.0.0.0 --port 8501 --reload
"""

from __future__ import annotations

import asyncio
from collections import defaultdict, deque
import contextlib
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
from typing import Any, Literal
import uuid

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware
import uvicorn

from app.local_web.services.context_provider import ContextProvider
from app.local_web.services.fallback_assistant import fallback_response
from app.local_web.services.ollama_client import OllamaClient
from app.local_web.services.prompting import build_messages
from app.local_web.services.session_store import SessionStore
from app.services.normalization import (
    classify_air_quality,
    classify_light,
    classify_pressure_trend,
    classify_temperature,
)


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
SITE_NAME = os.getenv("SINAI_SITE_NAME", "Sinai Local Node A-17")
DATA_POLL_INTERVAL = float(os.getenv("SINAI_DATA_POLL_INTERVAL", "1.2"))
DEFAULT_DATA_MODE = os.getenv("SINAI_MONITOR_DATA_MODE", "live")
ARDUINO_STALE_SECONDS = float(os.getenv("SINAI_ARDUINO_STALE_SECONDS", "25"))
OLLAMA_PROGRESS_PATH = Path(
    os.getenv("SINAI_OLLAMA_PROGRESS_PATH", "/boot/firmware/sinai-ollama-progress.json")
)


app = FastAPI(
    title="Sinai Local Web Assistant",
    version="3.0.0",
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


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
        if numeric != numeric:  # NaN check
            return None
        return numeric
    if isinstance(value, str):
        cleaned = value.strip().replace("%", "")
        if not cleaned:
            return None
        try:
            numeric = float(cleaned)
            if numeric != numeric:
                return None
            return numeric
        except ValueError:
            return None
    return None


def _humidity_label(value: float | None) -> str:
    if value is None:
        return "unknown"
    if value < 35:
        return "dry"
    if value <= 65:
        return "balanced"
    return "humid"


def _soil_label(value: float | None) -> str:
    if value is None:
        return "unknown"
    if value < 28:
        return "dry"
    if value <= 62:
        return "balanced"
    return "wet"


def _pressure_history_with_latest(
    history: list[float] | None,
    pressure_hpa: float | None,
) -> list[float]:
    safe_history = [float(item) for item in (history or []) if _coerce_float(item) is not None]
    if pressure_hpa is not None:
        safe_history.append(float(pressure_hpa))
    return safe_history[-6:] if safe_history else []


def _labels_for_readings(
    readings: dict[str, float | None],
    pressure_history_hpa: list[float] | None = None,
) -> dict[str, str]:
    return {
        "temperature": classify_temperature(readings.get("temperature_c")),
        "light": classify_light(readings.get("light_lux")),
        "air_quality": classify_air_quality(
            int(readings["air_quality_eco2_ppm"])
            if readings.get("air_quality_eco2_ppm") is not None
            else None,
            int(readings["air_quality_tvoc_ppb"])
            if readings.get("air_quality_tvoc_ppb") is not None
            else None,
        ),
        "pressure_trend": classify_pressure_trend(pressure_history_hpa or []),
        "humidity": _humidity_label(readings.get("humidity_percent")),
        "soil": _soil_label(readings.get("soil_moisture_pct")),
    }


class RealtimeHub:
    """Tracks monitor/client websockets and dispatches realtime updates."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._monitors: set[WebSocket] = set()
        self._clients: dict[str, set[WebSocket]] = defaultdict(set)

    async def connect(self, websocket: WebSocket, role: str, session_id: str | None = None) -> None:
        await websocket.accept()
        async with self._lock:
            if role == "monitor":
                self._monitors.add(websocket)
                return
            if session_id:
                self._clients[session_id].add(websocket)

    async def disconnect(self, websocket: WebSocket, role: str, session_id: str | None = None) -> None:
        async with self._lock:
            if role == "monitor":
                self._monitors.discard(websocket)
                return
            if not session_id:
                return
            bucket = self._clients.get(session_id)
            if not bucket:
                return
            bucket.discard(websocket)
            if not bucket:
                self._clients.pop(session_id, None)

    async def broadcast_monitors(self, payload: dict[str, object]) -> None:
        async with self._lock:
            sockets = list(self._monitors)
        await self._send_many(sockets, payload, role="monitor")

    async def broadcast_clients(self, payload: dict[str, object], session_id: str | None = None) -> None:
        async with self._lock:
            if session_id:
                sockets = list(self._clients.get(session_id, set()))
            else:
                sockets = [ws for bucket in self._clients.values() for ws in bucket]
        await self._send_many(sockets, payload, role="client", session_id=session_id)

    async def _send_many(
        self,
        sockets: list[WebSocket],
        payload: dict[str, object],
        role: str,
        session_id: str | None = None,
    ) -> None:
        stale: list[WebSocket] = []
        for websocket in sockets:
            try:
                await websocket.send_json(payload)
            except Exception:
                stale.append(websocket)

        if not stale:
            return

        async with self._lock:
            if role == "monitor":
                for websocket in stale:
                    self._monitors.discard(websocket)
                return

            if session_id:
                bucket = self._clients.get(session_id, set())
                for websocket in stale:
                    bucket.discard(websocket)
                if not bucket:
                    self._clients.pop(session_id, None)
                return

            for websocket in stale:
                for sid, bucket in list(self._clients.items()):
                    bucket.discard(websocket)
                    if not bucket:
                        self._clients.pop(sid, None)


class SensorFeedState:
    """Polling cache used by Data Mode, monitor broadcasts, and Arduino bridge ingest."""

    def __init__(self, provider: ContextProvider) -> None:
        self.provider = provider
        self.mode = DEFAULT_DATA_MODE if DEFAULT_DATA_MODE in {"mock", "live"} else "live"
        self.site_name = SITE_NAME
        self.region = self.provider.default_region
        self._lock = asyncio.Lock()
        self._latest: dict[str, object] = {}
        self._history: deque[dict[str, object]] = deque(maxlen=140)
        self._bridge_latest: dict[str, object] | None = None
        self._bridge_seen_monotonic: float | None = None

    def _build_base_frame(self) -> dict[str, object]:
        snapshot = self.provider.sensor_service.read_environment(
            mode=self.mode,
            site_name=self.site_name,
            region=self.region,
        )
        readings: dict[str, float | None] = {
            "temperature_c": _coerce_float(snapshot.temperature_c),
            "humidity_percent": None,
            "soil_moisture_pct": None,
            "pressure_hpa": _coerce_float(snapshot.pressure_hpa),
            "light_lux": _coerce_float(snapshot.light_lux),
            "air_quality_eco2_ppm": _coerce_float(snapshot.air_quality_eco2_ppm),
            "air_quality_tvoc_ppb": _coerce_float(snapshot.air_quality_tvoc_ppb),
        }
        pressure_history = _pressure_history_with_latest(
            history=snapshot.pressure_history_hpa,
            pressure_hpa=readings.get("pressure_hpa"),
        )
        labels = _labels_for_readings(readings, pressure_history_hpa=pressure_history)
        return {
            "timestamp_utc": snapshot.timestamp.isoformat(),
            "source": snapshot.source,
            "site_name": snapshot.site_name,
            "region": snapshot.region,
            "bridge": {"active": False, "source": None, "device_name": None, "last_seen_utc": None},
            "readings": readings,
            "labels": labels,
            "warnings": list(snapshot.warnings)[:6],
            "pressure_history_hpa": pressure_history,
        }

    def _active_bridge_locked(self) -> dict[str, object] | None:
        if not self._bridge_latest or self._bridge_seen_monotonic is None:
            return None
        elapsed = time.monotonic() - self._bridge_seen_monotonic
        if elapsed > ARDUINO_STALE_SECONDS:
            return None
        return self._bridge_latest

    @staticmethod
    def _merged_source(base_source: str, bridge_source: str) -> str:
        if not base_source:
            return bridge_source
        if base_source == bridge_source:
            return base_source
        if bridge_source in base_source:
            return base_source
        return f"{base_source}+{bridge_source}"

    @staticmethod
    def _compose_summary_line(readings: dict[str, float | None]) -> str:
        parts: list[str] = []
        if readings.get("temperature_c") is not None:
            parts.append(f"T {readings['temperature_c']:.1f} C")
        if readings.get("humidity_percent") is not None:
            parts.append(f"H {readings['humidity_percent']:.0f}%")
        if readings.get("soil_moisture_pct") is not None:
            parts.append(f"Soil {readings['soil_moisture_pct']:.0f}%")
        if readings.get("light_lux") is not None:
            parts.append(f"Light {readings['light_lux']:.0f} lx")
        return " | ".join(parts) if parts else "No sensor values available"

    def _merge_frame(
        self,
        base_frame: dict[str, object],
        bridge_frame: dict[str, object] | None,
    ) -> dict[str, object]:
        merged = dict(base_frame)
        merged_readings = dict(base_frame.get("readings", {}))
        warnings = list(base_frame.get("warnings", []))

        if bridge_frame:
            bridge_readings = bridge_frame.get("readings", {})
            if isinstance(bridge_readings, dict):
                for key, value in bridge_readings.items():
                    numeric = _coerce_float(value)
                    if numeric is not None:
                        merged_readings[key] = numeric

            source = str(bridge_frame.get("source", "arduino-serial"))
            merged["source"] = self._merged_source(str(base_frame.get("source", "live")), source)
            merged["site_name"] = bridge_frame.get("site_name") or merged.get("site_name")
            merged["region"] = bridge_frame.get("region") or merged.get("region")
            merged["bridge"] = {
                "active": True,
                "source": source,
                "device_name": bridge_frame.get("device_name") or "Arduino",
                "last_seen_utc": bridge_frame.get("timestamp_utc"),
            }
            warnings = list(dict.fromkeys([*warnings, "Arduino serial feed is active."]))[:6]
            merged["timestamp_utc"] = datetime.now(timezone.utc).isoformat()
        else:
            merged["bridge"] = {
                "active": False,
                "source": None,
                "device_name": None,
                "last_seen_utc": None,
            }

        pressure_history = _pressure_history_with_latest(
            history=base_frame.get("pressure_history_hpa"),  # type: ignore[arg-type]
            pressure_hpa=_coerce_float(merged_readings.get("pressure_hpa")),
        )
        labels = _labels_for_readings(merged_readings, pressure_history_hpa=pressure_history)

        merged["readings"] = merged_readings
        merged["labels"] = labels
        merged["warnings"] = warnings
        merged["pressure_history_hpa"] = pressure_history
        merged["summary_line"] = self._compose_summary_line(merged_readings)
        return merged

    async def refresh(self) -> dict[str, object]:
        base_frame = await asyncio.to_thread(self._build_base_frame)
        async with self._lock:
            bridge = self._active_bridge_locked()
            merged = self._merge_frame(base_frame, bridge)
            self._latest = merged
            self._history.append(merged)
        return merged

    async def ingest(
        self,
        readings: dict[str, float | None],
        source: str,
        site_name: str | None,
        region: str | None,
        device_name: str | None,
        timestamp_utc: str | None,
    ) -> None:
        clean_readings = {
            key: value
            for key, value in readings.items()
            if value is not None and key in SENSOR_READING_KEYS
        }
        if not clean_readings:
            raise ValueError("No valid sensor values in ingest payload.")

        bridge_frame = {
            "timestamp_utc": timestamp_utc or datetime.now(timezone.utc).isoformat(),
            "source": source or "arduino-serial",
            "site_name": site_name,
            "region": region,
            "device_name": device_name or "Arduino",
            "readings": clean_readings,
        }
        async with self._lock:
            self._bridge_latest = bridge_frame
            self._bridge_seen_monotonic = time.monotonic()

    async def payload(self) -> dict[str, object]:
        async with self._lock:
            latest = dict(self._latest)
            history = list(self._history)[-60:]

        if not latest:
            latest = await self.refresh()
            history = [latest]

        series = {
            "temperature_c": [item.get("readings", {}).get("temperature_c") for item in history],
            "humidity_percent": [item.get("readings", {}).get("humidity_percent") for item in history],
            "soil_moisture_pct": [item.get("readings", {}).get("soil_moisture_pct") for item in history],
            "pressure_hpa": [item.get("readings", {}).get("pressure_hpa") for item in history],
            "light_lux": [item.get("readings", {}).get("light_lux") for item in history],
            "air_quality_eco2_ppm": [
                item.get("readings", {}).get("air_quality_eco2_ppm") for item in history
            ],
            "air_quality_tvoc_ppb": [
                item.get("readings", {}).get("air_quality_tvoc_ppb") for item in history
            ],
            "timestamps": [item.get("timestamp_utc") for item in history],
        }
        return {
            "current": latest,
            "history": history[-16:],
            "series": series,
        }


realtime_hub = RealtimeHub()
sensor_feed = SensorFeedState(context_provider)

SENSOR_READING_KEYS = {
    "temperature_c",
    "humidity_percent",
    "soil_moisture_pct",
    "pressure_hpa",
    "light_lux",
    "air_quality_eco2_ppm",
    "air_quality_tvoc_ppb",
}

SENSOR_KEY_ALIASES: dict[str, tuple[str, ...]] = {
    "temperature_c": ("temperature_c", "temperature", "temp_c", "temp", "t"),
    "humidity_percent": ("humidity_percent", "humidity", "humidity_pct", "h"),
    "soil_moisture_pct": ("soil_moisture_pct", "soil_moisture", "soil", "soil_pct"),
    "pressure_hpa": ("pressure_hpa", "pressure", "pressure_mb"),
    "light_lux": ("light_lux", "light", "lux"),
    "air_quality_eco2_ppm": ("air_quality_eco2_ppm", "eco2", "co2", "co2_ppm"),
    "air_quality_tvoc_ppb": ("air_quality_tvoc_ppb", "tvoc", "tvoc_ppb"),
}


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    mode: Literal["mock", "live"] = "live"
    site_name: str = Field(default="Sinai Local Node", min_length=2, max_length=120)
    region: str | None = Field(default=None, max_length=120)


class ContextRequest(BaseModel):
    mode: Literal["mock", "live"] = "live"
    site_name: str = Field(default="Sinai Local Node", min_length=2, max_length=120)
    region: str | None = Field(default=None, max_length=120)


class DeviceRegisterRequest(BaseModel):
    device_name: str = Field(..., min_length=1, max_length=28)


class DataIngestRequest(BaseModel):
    source: str = Field(default="arduino-serial", min_length=1, max_length=80)
    site_name: str | None = Field(default=None, max_length=120)
    region: str | None = Field(default=None, max_length=120)
    device_name: str | None = Field(default=None, max_length=64)
    timestamp_utc: str | None = Field(default=None, max_length=64)
    readings: dict[str, Any] = Field(default_factory=dict)
    temperature_c: float | None = None
    humidity_percent: float | None = None
    soil_moisture_pct: float | None = None
    pressure_hpa: float | None = None
    uv_index: float | None = None
    light_lux: float | None = None
    air_quality_eco2_ppm: float | None = None
    air_quality_tvoc_ppb: float | None = None


@dataclass
class PromptQueueJob:
    session_id: str
    device_name: str
    question: str
    payload: "ChatRequest"
    enqueued_at_utc: str
    future: asyncio.Future[dict[str, object]]


class PromptQueueProcessor:
    """Single-worker FIFO queue for prompt processing across all devices."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[PromptQueueJob] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None
        self._processing = False
        self._active_job: dict[str, object] | None = None

    def snapshot(self) -> dict[str, object]:
        queued = self._queue.qsize()
        processing = self._processing
        active = self._active_job if processing else None
        preview: list[dict[str, object]] = []
        start_position = 2 if active else 1
        for idx, queued_job in enumerate(list(self._queue._queue)[:8], start=start_position):  # noqa: SLF001
            preview.append(
                {
                    "position": idx,
                    "session_id": queued_job.session_id,
                    "device_name": queued_job.device_name,
                    "question": queued_job.question[:180],
                    "enqueued_at_utc": queued_job.enqueued_at_utc,
                }
            )
        return {
            "queued": queued,
            "waiting": queued,
            "processing": processing,
            "pending_total": queued + (1 if processing else 0),
            "active": active,
            "items": preview,
            "next_question": (
                str(active.get("question", ""))
                if active
                else (preview[0]["question"] if preview else None)
            ),
            "next_device_name": (
                str(active.get("device_name", ""))
                if active
                else (preview[0]["device_name"] if preview else None)
            ),
        }

    async def start(self) -> None:
        if self._worker_task and not self._worker_task.done():
            return
        self._worker_task = asyncio.create_task(self._run(), name="sinai-prompt-queue")

    async def stop(self) -> None:
        if not self._worker_task:
            return
        self._worker_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._worker_task
        self._worker_task = None
        self._processing = False

    async def enqueue(self, job: PromptQueueJob) -> None:
        await self._queue.put(job)

    async def _run(self) -> None:
        while True:
            job = await self._queue.get()
            self._processing = True
            self._active_job = {
                "position": 1,
                "session_id": job.session_id,
                "device_name": job.device_name,
                "question": job.question[:180],
                "enqueued_at_utc": job.enqueued_at_utc,
            }
            try:
                await _broadcast_queue_status()
                result = await _process_chat_job(job)
                if not job.future.done():
                    job.future.set_result(result)
            except Exception as exc:
                if not job.future.done():
                    job.future.set_exception(exc)
            finally:
                self._processing = False
                self._active_job = None
                self._queue.task_done()
                await _broadcast_queue_status()


prompt_queue = PromptQueueProcessor()


def _extract_ingest_readings(payload: DataIngestRequest) -> dict[str, float | None]:
    merged: dict[str, Any] = dict(payload.readings)

    for key in SENSOR_READING_KEYS:
        value = getattr(payload, key)
        if value is not None:
            merged[key] = value

    normalized: dict[str, float | None] = {}
    for canonical, aliases in SENSOR_KEY_ALIASES.items():
        value = None
        for alias in aliases:
            if alias in merged:
                value = _coerce_float(merged.get(alias))
                if value is not None:
                    break
        normalized[canonical] = value
    return normalized


def _get_session_id(request: Request) -> str:
    session_id = request.session.get("sinai_session_id")
    if not session_id:
        session_id = str(uuid.uuid4())
        request.session["sinai_session_id"] = session_id
    return session_id


async def _broadcast_device_snapshot() -> None:
    await realtime_hub.broadcast_monitors(
        {
            "type": "device_snapshot",
            "devices": session_store.devices_snapshot(),
        }
    )


async def _broadcast_queue_status() -> None:
    snapshot = {
        "type": "queue_status",
        **prompt_queue.snapshot(),
    }
    await realtime_hub.broadcast_monitors(snapshot)
    await realtime_hub.broadcast_clients(snapshot)


async def _broadcast_sensor_snapshot() -> None:
    await realtime_hub.broadcast_monitors(
        {
            "type": "sensor_update",
            "payload": await sensor_feed.payload(),
        }
    )


async def _sensor_poll_loop() -> None:
    while True:
        try:
            frame = await sensor_feed.refresh()
            await realtime_hub.broadcast_monitors(
                {
                    "type": "sensor_update",
                    "payload": frame,
                }
            )
        except Exception:
            # Keep background loop alive during demos even on transient sensor failures.
            pass
        await asyncio.sleep(DATA_POLL_INTERVAL)


async def _process_chat_job(job: PromptQueueJob) -> dict[str, object]:
    history_before = session_store.history(job.session_id)
    context = await asyncio.to_thread(
        context_provider.get_context,
        job.payload.mode,
        job.payload.site_name,
        job.payload.region,
    )
    messages = build_messages(
        user_message=job.question,
        context=context,
        history=history_before,
    )

    user_event = session_store.add_turn(job.session_id, role="user", content=job.question)
    await realtime_hub.broadcast_monitors({"type": "chat_event", "item": user_event})

    source = "ollama"
    model_name = None
    try:
        answer, model_name = await asyncio.to_thread(ollama_client.chat, messages)
    except Exception:
        source = "fallback"
        answer = fallback_response(job.question, context)

    assistant_event = session_store.add_turn(job.session_id, role="assistant", content=answer)

    await realtime_hub.broadcast_monitors({"type": "chat_event", "item": assistant_event})
    await realtime_hub.broadcast_clients(
        {"type": "chat_event", "item": assistant_event},
        session_id=job.session_id,
    )
    await _broadcast_device_snapshot()

    return {
        "reply": answer,
        "source": source,
        "model": model_name,
        "context": {
            "site_name": context.get("site_name"),
            "region": context.get("region"),
            "source": context.get("source"),
            "timestamp_utc": context.get("timestamp_utc"),
            "summary": context.get("summary"),
            "labels": context.get("labels", {}),
            "readings": context.get("readings", {}),
        },
        "history": session_store.history(job.session_id),
    }


@app.on_event("startup")
async def on_startup() -> None:
    await sensor_feed.refresh()
    await prompt_queue.start()
    app.state.sensor_poll_task = asyncio.create_task(_sensor_poll_loop())


@app.on_event("shutdown")
async def on_shutdown() -> None:
    await prompt_queue.stop()
    poll_task = getattr(app.state, "sensor_poll_task", None)
    if poll_task:
        poll_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await poll_task


@app.get("/")
def serve_index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/monitor")
def serve_monitor() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/client")
def serve_client() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/generate_204", include_in_schema=False)
@app.get("/gen_204", include_in_schema=False)
@app.get("/hotspot-detect.html", include_in_schema=False)
@app.get("/library/test/success.html", include_in_schema=False)
@app.get("/success.txt", include_in_schema=False)
@app.get("/ncsi.txt", include_in_schema=False)
@app.get("/connecttest.txt", include_in_schema=False)
@app.get("/redirect", include_in_schema=False)
def captive_portal_redirect() -> RedirectResponse:
    return RedirectResponse(url="/client", status_code=302)


@app.get("/static/{file_path:path}")
def serve_static(file_path: str) -> FileResponse:
    target = (STATIC_DIR / file_path).resolve()
    static_root = STATIC_DIR.resolve()
    if static_root not in target.parents and target != static_root:
        raise HTTPException(status_code=404, detail="Not found")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(target)


@app.get("/api/health")
def health() -> dict[str, object]:
    state = ollama_client.health()
    connected_count = len([d for d in session_store.devices_snapshot() if d.get("connected")])
    return {
        "ok": state.ok,
        "status_text": state.status_text,
        "active_model": state.active_model,
        "host": ollama_client.host,
        "connected_devices": connected_count,
    }


@app.get("/api/session")
def get_session(request: Request) -> dict[str, object]:
    session_id = _get_session_id(request)
    profile = session_store.touch_device(session_id)
    return {
        "session_id": session_id,
        "device": profile,
    }


@app.post("/api/device/register")
async def register_device(request: Request, payload: DeviceRegisterRequest) -> dict[str, object]:
    session_id = _get_session_id(request)
    profile = session_store.register_device(session_id, payload.device_name)
    await _broadcast_device_snapshot()
    return {
        "session_id": session_id,
        "device": profile,
    }


@app.get("/api/devices")
def get_devices() -> dict[str, object]:
    return {"devices": session_store.devices_snapshot()}


@app.get("/api/context")
def get_context(
    mode: Literal["mock", "live"] = "live",
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
    session_store.touch_device(session_id)
    return {
        "session_id": session_id,
        "messages": session_store.history(session_id),
    }


@app.get("/api/live-feed")
def get_live_feed(limit: int = 36) -> dict[str, object]:
    return {"items": session_store.live_feed(limit=limit)}


@app.get("/api/data/live")
async def get_data_live() -> dict[str, object]:
    return await sensor_feed.payload()


@app.get("/api/queue/status")
def get_queue_status() -> dict[str, object]:
    return prompt_queue.snapshot()


@app.get("/api/ollama/progress")
def get_ollama_progress() -> dict[str, object]:
    if not OLLAMA_PROGRESS_PATH.exists():
        return {
            "phase": "unknown",
            "percent": None,
            "message": "Waiting for local model setup status.",
            "updated_at": None,
        }

    try:
        payload = json.loads(OLLAMA_PROGRESS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "phase": "unknown",
            "percent": None,
            "message": "Local model status is temporarily unavailable.",
            "updated_at": None,
        }

    return {
        "phase": payload.get("phase", "unknown"),
        "percent": payload.get("percent"),
        "message": payload.get("message", "Local model setup is running."),
        "updated_at": payload.get("updated_at"),
    }


@app.post("/api/data/ingest")
async def ingest_data(payload: DataIngestRequest) -> dict[str, object]:
    readings = _extract_ingest_readings(payload)
    try:
        await sensor_feed.ingest(
            readings=readings,
            source=payload.source,
            site_name=payload.site_name,
            region=payload.region,
            device_name=payload.device_name,
            timestamp_utc=payload.timestamp_utc,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    frame = await sensor_feed.refresh()
    await realtime_hub.broadcast_monitors({"type": "sensor_update", "payload": frame})
    return {"ok": True, "frame": frame}


@app.post("/api/reset")
async def reset_history(request: Request) -> dict[str, object]:
    session_id = _get_session_id(request)
    session_store.clear(session_id)
    await _broadcast_device_snapshot()
    return {"ok": True}


@app.post("/api/chat")
async def chat(request: Request, payload: ChatRequest) -> dict[str, object]:
    session_id = _get_session_id(request)
    profile = session_store.touch_device(session_id)
    question = payload.message.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    loop = asyncio.get_running_loop()
    future: asyncio.Future[dict[str, object]] = loop.create_future()
    queued_snapshot = prompt_queue.snapshot()
    job = PromptQueueJob(
        session_id=session_id,
        device_name=str(profile.get("device_name", "Unknown device")),
        question=question,
        payload=payload,
        enqueued_at_utc=datetime.now(timezone.utc).isoformat(),
        future=future,
    )
    await prompt_queue.enqueue(job)
    await _broadcast_queue_status()

    try:
        result = await future
    except asyncio.CancelledError:
        if not future.done():
            future.cancel()
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Queue processing failed: {exc}") from exc

    result["queue"] = {
        "queued_ahead_on_submit": queued_snapshot["pending_total"],
        **prompt_queue.snapshot(),
    }
    return result


@app.websocket("/ws/realtime")
async def websocket_realtime(websocket: WebSocket) -> None:
    role = websocket.query_params.get("role", "client")
    role = role if role in {"client", "monitor"} else "client"
    session_id = websocket.query_params.get("session_id")

    if role == "client" and not session_id:
        await websocket.close(code=4400, reason="session_id is required for client sockets")
        return

    await realtime_hub.connect(websocket, role=role, session_id=session_id)

    if role == "client" and session_id:
        session_store.set_connected(session_id, True)
        await _broadcast_device_snapshot()
        await websocket.send_json(
            {
                "type": "welcome",
                "role": "client",
                "session_id": session_id,
                "device": session_store.device_profile(session_id),
                "queue": prompt_queue.snapshot(),
            }
        )
    else:
        await websocket.send_json(
            {
                "type": "welcome",
                "role": "monitor",
                "devices": session_store.devices_snapshot(),
                "feed": session_store.live_feed(limit=40),
                "data": await sensor_feed.payload(),
                "queue": prompt_queue.snapshot(),
            }
        )

    try:
        while True:
            raw = await websocket.receive_text()
            if raw.lower() == "ping":
                await websocket.send_text("pong")
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue

            action = str(payload.get("action", "")).strip().lower()
            if action == "ping":
                await websocket.send_json({"type": "pong"})
            elif action == "refresh":
                await websocket.send_json(
                    {
                        "type": "snapshot",
                        "devices": session_store.devices_snapshot(),
                        "feed": session_store.live_feed(limit=40),
                        "data": await sensor_feed.payload(),
                        "queue": prompt_queue.snapshot(),
                    }
                )
    except WebSocketDisconnect:
        pass
    finally:
        await realtime_hub.disconnect(websocket, role=role, session_id=session_id)
        if role == "client" and session_id:
            session_store.set_connected(session_id, False)
            await _broadcast_device_snapshot()


if __name__ == "__main__":
    uvicorn.run("app.local_web.server:app", host="0.0.0.0", port=8501, reload=False)
