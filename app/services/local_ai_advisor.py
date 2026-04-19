"""Local LLM advisor service for interactive field guidance."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from app.models.environmental import ClassifiedEnvironment
from app.utils.config import AppConfig


class LocalAIAdvisorService:
    """Ask a local LLM for guidance, with deterministic fallback."""

    def __init__(self, config: AppConfig):
        self.config = config

    def ask(
        self,
        question: str,
        environment: ClassifiedEnvironment,
        top_scores: list,
        cautions: list[str],
    ) -> tuple[str, str]:
        prompt = question.strip()
        if not prompt:
            return "Please ask a question so Sinai can give field guidance.", "fallback"

        model_answer = self._ask_local_model(prompt, environment, top_scores, cautions)
        if model_answer:
            return model_answer, "local_llm"

        return self._fallback(prompt, environment, top_scores, cautions), "fallback"

    def health(self) -> tuple[bool, str]:
        """Check local model availability for UI status indicators."""
        if not self.config.ollama_host:
            return False, "OLLAMA_HOST is not configured."
        try:
            request = urllib.request.Request(
                f"{self.config.ollama_host.rstrip('/')}/api/tags",
                method="GET",
            )
            with urllib.request.urlopen(request, timeout=3) as response:
                if response.status != 200:
                    return False, f"Ollama endpoint returned status {response.status}."
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
            return False, "Ollama endpoint is unreachable."

        models = payload.get("models", [])
        model_names = [str(item.get("name", "")) for item in models]
        if any(name.startswith(self.config.ollama_model) for name in model_names):
            return True, f"Connected. Model '{self.config.ollama_model}' is available."
        if model_names:
            return True, f"Connected. Available models: {', '.join(model_names[:3])}."
        return True, "Connected to Ollama, but no models are loaded."

    def _ask_local_model(
        self,
        question: str,
        environment: ClassifiedEnvironment,
        top_scores: list,
        cautions: list[str],
    ) -> str | None:
        if not self.config.ollama_host:
            return None

        top_lines = []
        for item in top_scores[:3]:
            top_lines.append(
                f"{item.crop.name} score {item.score_percent}/100, "
                f"harvest {item.crop.time_to_harvest_days} days, "
                f"use case {item.suggested_use_case}"
            )
        top_summary = "; ".join(top_lines)

        labels = environment.labels()
        payload = {
            "task": (
                "You are Sinai Local Advisor. Give practical and human-friendly advice "
                "for field teams using local crop intelligence."
            ),
            "rules": [
                "Keep the answer concise.",
                "Use concrete steps for NGOs, governments, or co-ops.",
                "Connect advice to the current sensor profile.",
                "Highlight immediate action, next-week action, and risk watch.",
            ],
            "environment": labels,
            "top_crops": top_summary,
            "cautions": cautions[:3],
            "question": question,
        }

        body = json.dumps(
            {
                "model": self.config.ollama_model,
                "prompt": json.dumps(payload),
                "stream": False,
            }
        ).encode("utf-8")

        try:
            request = urllib.request.Request(
                f"{self.config.ollama_host.rstrip('/')}/api/generate",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=6) as response:
                content = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
            return None

        text = str(content.get("response", "")).strip()
        return text or None

    @staticmethod
    def _fallback(
        question: str,
        environment: ClassifiedEnvironment,
        top_scores: list,
        cautions: list[str],
    ) -> str:
        labels = environment.labels()
        top = top_scores[:3]
        if not top:
            return (
                "Sinai could not find crop rankings right now. "
                "Re-run the site refresh and check sensor diagnostics."
            )

        first = top[0]
        second = top[1] if len(top) > 1 else None
        third = top[2] if len(top) > 2 else None

        steps = [
            (
                f"Immediate: Start with {first.crop.name} because it has the strongest fit "
                f"({first.score_percent}/100) for current conditions."
            ),
            (
                f"Next 7 days: Prepare seed and labor scheduling around "
                f"{first.crop.time_to_harvest_days}-day harvest planning."
            ),
        ]

        if second:
            steps.append(
                f"Backup path: Keep {second.crop.name} ready as your secondary crop option."
            )
        if third:
            steps.append(
                f"Resilience path: Track inputs for {third.crop.name} as a third option."
            )

        if labels["pressure_trend"] == "falling":
            steps.append("Risk watch: Falling pressure may signal unstable weather. Protect young seedlings.")
        if labels["air_quality"] == "poor":
            steps.append("Risk watch: Poor air quality can stress tender crops. Prioritize resilient varieties.")
        if cautions:
            steps.append(f"Operational caution: {cautions[0]}")

        lower_q = question.lower()
        if "why" in lower_q:
            steps.append(
                "Why these crops: Sinai balances environmental fit, resilience rating, and harvest speed."
            )
        if "harvest" in lower_q or "timeline" in lower_q:
            steps.append(
                "Timeline note: Plan staggered planting windows so harvests are continuous, not all-at-once."
            )
        if "community" in lower_q or "family" in lower_q:
            steps.append(
                "Community note: Pair fast emergency crops with one longer-duration staple for stability."
            )

        answer = [
            "Local AI fallback guidance:",
            (
                f"Current profile: temperature {labels['temperature']}, light {labels['light']}, "
                f"air quality {labels['air_quality']}."
            ),
            "",
        ]
        answer.extend([f"- {item}" for item in steps[:6]])
        return "\n".join(answer)
