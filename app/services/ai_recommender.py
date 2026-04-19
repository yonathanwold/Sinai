"""Local-model-ready recommendation service with deterministic fallback."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from app.models.crop import CropScore
from app.models.environmental import ClassifiedEnvironment
from app.utils.config import AppConfig


@dataclass(frozen=True)
class RecommendationNarrative:
    overview: str
    top_crop_explanations: list[str]
    cautions: list[str]
    resilience_insights: list[str]
    emergency_suggestions: list[str]


class AIRecommendationService:
    """Recommendation facade that can later call Ollama or another local model."""

    def __init__(self, config: AppConfig):
        self.config = config

    def recommend(
        self,
        environment: ClassifiedEnvironment,
        ranked_crops: list[CropScore],
        emergency_crop_names: list[str],
        disaster_context: str,
    ) -> RecommendationNarrative:
        local_response = self._try_local_model(environment, ranked_crops[:3], disaster_context)
        if local_response:
            return local_response
        return self._fallback_recommendation(
            environment,
            ranked_crops[:3],
            emergency_crop_names,
            disaster_context,
        )

    def _try_local_model(
        self,
        environment: ClassifiedEnvironment,
        top_scores: list[CropScore],
        disaster_context: str,
    ) -> RecommendationNarrative | None:
        if not self.config.ollama_host:
            return None

        prompt = {
            "task": "Explain crop recommendations for a disaster-resilient food dashboard.",
            "environment": environment.labels(),
            "disaster_context": disaster_context,
            "top_crops": [
                {
                    "name": item.crop.name,
                    "score": item.score_percent,
                    "reasons": item.reasons,
                    "cautions": item.cautions,
                    "use_case": item.suggested_use_case,
                }
                for item in top_scores
            ],
            "format": "Return concise JSON with overview, crop_explanations, cautions, insights.",
        }
        body = json.dumps(
            {
                "model": self.config.ollama_model,
                "prompt": json.dumps(prompt),
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
            with urllib.request.urlopen(request, timeout=2) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
            return None

        text = payload.get("response", "").strip()
        if not text:
            return None

        return RecommendationNarrative(
            overview=text,
            top_crop_explanations=[
                f"{item.crop.name}: {item.suggested_use_case} with score {item.score_percent}."
                for item in top_scores
            ],
            cautions=self._collect_cautions(top_scores),
            resilience_insights=self._insights(environment, disaster_context),
            emergency_suggestions=[],
        )

    def _fallback_recommendation(
        self,
        environment: ClassifiedEnvironment,
        top_scores: list[CropScore],
        emergency_crop_names: list[str],
        disaster_context: str,
    ) -> RecommendationNarrative:
        labels = environment.labels()
        overview = (
            "The current site profile favors crops that can tolerate "
            f"{labels['temperature']} temperatures, {labels['light']} light, "
            f"and {labels['air_quality']} air quality. "
            "The ranking prioritizes fast harvest cycles and resilience for local food continuity."
        )

        top_crop_explanations = [
            (
                f"{item.crop.name}: recommended for {item.suggested_use_case}. "
                f"Key factors: {'; '.join(item.reasons[:3])}."
            )
            for item in top_scores
        ]

        return RecommendationNarrative(
            overview=overview,
            top_crop_explanations=top_crop_explanations,
            cautions=self._collect_cautions(top_scores),
            resilience_insights=self._insights(environment, disaster_context),
            emergency_suggestions=[
                f"{name} is a practical candidate when teams need quick, locally managed planting."
                for name in emergency_crop_names
            ],
        )

    @staticmethod
    def _collect_cautions(top_scores: list[CropScore]) -> list[str]:
        cautions: list[str] = []
        for item in top_scores:
            cautions.extend([f"{item.crop.name}: {caution}" for caution in item.cautions])
        return cautions or ["No major environmental cautions detected for the top-ranked crops."]

    @staticmethod
    def _insights(environment: ClassifiedEnvironment, disaster_context: str) -> list[str]:
        insights = [
            f"Use this deployment as an offline decision point for {disaster_context.lower()}.",
            "Prioritize seed stock for crops with short harvest windows and high resilience ratings.",
            "Recheck conditions after storms, smoke events, or generator use because light and air quality can shift quickly.",
        ]
        if environment.pressure_trend == "falling":
            insights.append("Falling pressure suggests possible weather instability; protect seedlings and delay fragile transplants.")
        return insights
