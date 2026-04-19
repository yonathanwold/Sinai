"""Small Ollama client used by the Sinai local web server."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass(frozen=True)
class OllamaHealth:
    ok: bool
    status_text: str
    active_model: str | None = None


class OllamaClient:
    """Wrapper around Ollama /api/tags and /api/chat endpoints."""

    def __init__(self) -> None:
        self.host = (
            os.getenv("SINAI_OLLAMA_HOST")
            or os.getenv("OLLAMA_HOST")
            or "http://127.0.0.1:11434"
        )
        self.preferred_model = (
            os.getenv("SINAI_OLLAMA_MODEL")
            or os.getenv("OLLAMA_MODEL")
            or "llama3.2:1b"
        )
        self.request_timeout_seconds = int(os.getenv("SINAI_OLLAMA_TIMEOUT", "240"))
        self.max_tokens = int(os.getenv("SINAI_OLLAMA_MAX_TOKENS", "140"))

    def health(self) -> OllamaHealth:
        try:
            tags = self._fetch_tags()
        except (urllib.error.URLError, OSError, TimeoutError, json.JSONDecodeError):
            return OllamaHealth(
                ok=False,
                status_text="Local AI offline. Using deterministic fallback guidance.",
                active_model=None,
            )

        models = [str(item.get("name", "")).strip() for item in tags.get("models", [])]
        model = self._select_model(models)
        if not models:
            return OllamaHealth(
                ok=False,
                status_text="Ollama reachable but no model is loaded.",
                active_model=None,
            )
        return OllamaHealth(
            ok=True,
            status_text=f"Local AI running with model: {model}",
            active_model=model,
        )

    def chat(self, messages: list[dict[str, str]]) -> tuple[str, str]:
        tags = self._fetch_tags()
        models = [str(item.get("name", "")).strip() for item in tags.get("models", [])]
        model = self._select_model(models)
        if not model:
            raise RuntimeError("No Ollama model is available. Run `ollama pull <model>` first.")

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            # Qwen-family models can emit "thinking" instead of direct content.
            # For a user-facing chat UX we disable that mode.
            "think": False,
            "options": {
                "temperature": 0.2,
                "num_predict": self.max_tokens,
            },
        }
        body = json.dumps(payload).encode("utf-8")

        request = urllib.request.Request(
            f"{self.host.rstrip('/')}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(request, timeout=self.request_timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8"))

        message_payload = data.get("message", {}) or {}
        content = str(message_payload.get("content", "")).strip()
        if not content:
            content = str(message_payload.get("thinking", "")).strip()
        if not content:
            content = str(data.get("response", "")).strip()
        if not content:
            raise RuntimeError("Ollama returned an empty response.")

        return content, model

    def _fetch_tags(self) -> dict[str, object]:
        request = urllib.request.Request(
            f"{self.host.rstrip('/')}/api/tags",
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=8) as response:
            return json.loads(response.read().decode("utf-8"))

    def _select_model(self, available_models: list[str]) -> str | None:
        if not available_models:
            return None

        if self.preferred_model in available_models:
            return self.preferred_model

        for candidate in available_models:
            if candidate.startswith(self.preferred_model):
                return candidate

        return available_models[0]
