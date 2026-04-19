"""In-memory session history for local Sinai chat usage."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from threading import Lock
from typing import Literal


ChatRole = Literal["user", "assistant"]


@dataclass(frozen=True)
class ChatEvent:
    session_id: str
    device_name: str
    device_color: str
    role: ChatRole
    content: str
    timestamp_utc: str

    @classmethod
    def create(
        cls,
        session_id: str,
        device_name: str,
        device_color: str,
        role: ChatRole,
        content: str,
    ) -> "ChatEvent":
        return cls(
            session_id=session_id,
            device_name=device_name,
            device_color=device_color,
            role=role,
            content=content,
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
        )


@dataclass
class DeviceProfile:
    session_id: str
    device_name: str
    device_color: str
    connected: bool
    last_seen_utc: str
    message_count: int


class SessionStore:
    """Simple in-memory chat store keyed by session id."""

    def __init__(self, max_turns: int = 14, max_feed_events: int = 200):
        self.max_messages = max_turns * 2
        self._store: dict[str, deque[ChatEvent]] = defaultdict(
            lambda: deque(maxlen=self.max_messages)
        )
        self._live_feed: deque[ChatEvent] = deque(maxlen=max_feed_events)
        self._devices: dict[str, DeviceProfile] = {}
        self._lock = Lock()

    @staticmethod
    def _now_utc() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _sanitize_name(name: str | None) -> str:
        candidate = (name or "").strip()
        if not candidate:
            return ""
        collapsed = " ".join(candidate.split())
        return collapsed[:28]

    @staticmethod
    def _default_name(session_id: str) -> str:
        return f"Device-{session_id[:4]}"

    @staticmethod
    def _device_color(session_id: str) -> str:
        palette = [
            "#4f9d7a",
            "#c78f4b",
            "#5b8ec6",
            "#bf5e57",
            "#4aa3a0",
            "#8f9a4b",
            "#6a8c6b",
            "#c06d4f",
            "#4e7ea5",
            "#aa7b52",
            "#5f9a92",
            "#6f8f4f",
        ]
        digest = hashlib.sha1(session_id.encode("utf-8")).hexdigest()
        return palette[int(digest[:8], 16) % len(palette)]

    def register_device(self, session_id: str, requested_name: str | None = None) -> dict[str, object]:
        safe_name = self._sanitize_name(requested_name)
        with self._lock:
            profile = self._devices.get(session_id)
            if profile is None:
                profile = DeviceProfile(
                    session_id=session_id,
                    device_name=safe_name or self._default_name(session_id),
                    device_color=self._device_color(session_id),
                    connected=False,
                    last_seen_utc=self._now_utc(),
                    message_count=0,
                )
                self._devices[session_id] = profile
            else:
                if safe_name:
                    profile.device_name = safe_name
                profile.last_seen_utc = self._now_utc()

            return self._device_dict(profile)

    def touch_device(self, session_id: str) -> dict[str, object]:
        return self.register_device(session_id=session_id, requested_name=None)

    def set_connected(self, session_id: str, connected: bool) -> None:
        with self._lock:
            profile = self._devices.get(session_id)
            if profile is None:
                profile = DeviceProfile(
                    session_id=session_id,
                    device_name=self._default_name(session_id),
                    device_color=self._device_color(session_id),
                    connected=connected,
                    last_seen_utc=self._now_utc(),
                    message_count=0,
                )
                self._devices[session_id] = profile
                return

            profile.connected = connected
            profile.last_seen_utc = self._now_utc()

    def add_turn(self, session_id: str, role: ChatRole, content: str) -> dict[str, object]:
        with self._lock:
            profile = self._devices.get(session_id)
            if profile is None:
                profile = DeviceProfile(
                    session_id=session_id,
                    device_name=self._default_name(session_id),
                    device_color=self._device_color(session_id),
                    connected=False,
                    last_seen_utc=self._now_utc(),
                    message_count=0,
                )
                self._devices[session_id] = profile

            event = ChatEvent.create(
                session_id=session_id,
                device_name=profile.device_name,
                device_color=profile.device_color,
                role=role,
                content=content,
            )
            self._store[session_id].append(event)
            self._live_feed.append(event)
            profile.last_seen_utc = self._now_utc()
            profile.message_count += 1
            event_dict = self._event_dict(event)
        return event_dict

    def history(self, session_id: str) -> list[dict[str, object]]:
        with self._lock:
            turns = list(self._store.get(session_id, []))
        return [self._event_dict(turn) for turn in turns]

    def live_feed(self, limit: int = 30) -> list[dict[str, object]]:
        bounded_limit = max(1, min(limit, 120))
        with self._lock:
            turns = list(self._live_feed)[-bounded_limit:]

        turns.reverse()
        return [self._event_dict(turn) for turn in turns]

    def devices_snapshot(self) -> list[dict[str, object]]:
        with self._lock:
            profiles = list(self._devices.values())

        profiles.sort(
            key=lambda item: (
                item.connected,
                item.last_seen_utc,
            ),
            reverse=True,
        )
        return [self._device_dict(profile) for profile in profiles]

    def device_profile(self, session_id: str) -> dict[str, object]:
        with self._lock:
            profile = self._devices.get(session_id)
            if profile is None:
                profile = DeviceProfile(
                    session_id=session_id,
                    device_name=self._default_name(session_id),
                    device_color=self._device_color(session_id),
                    connected=False,
                    last_seen_utc=self._now_utc(),
                    message_count=0,
                )
                self._devices[session_id] = profile
            return self._device_dict(profile)

    def clear(self, session_id: str) -> None:
        with self._lock:
            self._store.pop(session_id, None)

    @staticmethod
    def _event_dict(event: ChatEvent) -> dict[str, object]:
        return {
            "session_id": event.session_id,
            "device_name": event.device_name,
            "device_color": event.device_color,
            "role": event.role,
            "content": event.content,
            "timestamp_utc": event.timestamp_utc,
        }

    @staticmethod
    def _device_dict(profile: DeviceProfile) -> dict[str, object]:
        return {
            "session_id": profile.session_id,
            "device_name": profile.device_name,
            "device_color": profile.device_color,
            "connected": profile.connected,
            "last_seen_utc": profile.last_seen_utc,
            "message_count": profile.message_count,
        }
