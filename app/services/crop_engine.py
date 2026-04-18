"""Crop ranking logic for disaster-resilient planting decisions."""

from __future__ import annotations

import json
from pathlib import Path

from app.models.crop import Crop, CropScore
from app.models.environmental import ClassifiedEnvironment
from app.utils.config import CROP_DATA_PATH


DISASTER_PRIORITY_CATEGORIES = {"emergency", "resilient", "staple"}


class CropScoringEngine:
    def __init__(self, crops: list[Crop]):
        self.crops = crops

    @classmethod
    def from_json(cls, path: Path = CROP_DATA_PATH) -> "CropScoringEngine":
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return cls([Crop.from_dict(item) for item in payload["crops"]])

    def rank_crops(self, environment: ClassifiedEnvironment, limit: int | None = None) -> list[CropScore]:
        scores = [self._score_crop(crop, environment) for crop in self.crops]
        ranked = sorted(scores, key=lambda item: item.score, reverse=True)
        return ranked[:limit] if limit else ranked

    def emergency_candidates(self, limit: int = 5) -> list[Crop]:
        candidates = [
            crop
            for crop in self.crops
            if "emergency" in crop.category or crop.time_to_harvest_days <= 35
        ]
        return sorted(
            candidates,
            key=lambda crop: (crop.time_to_harvest_days, -crop.resilience_rating),
        )[:limit]

    def _score_crop(self, crop: Crop, environment: ClassifiedEnvironment) -> CropScore:
        score = 0.0
        reasons: list[str] = []
        cautions: list[str] = []

        score += self._match_component(
            environment.temperature_label,
            crop.preferred_temperature_bands,
            20,
            "temperature",
            reasons,
            cautions,
        )
        score += self._match_component(
            environment.light_label,
            crop.preferred_light_levels,
            15,
            "light",
            reasons,
            cautions,
        )
        score += self._match_component(
            environment.uv_label,
            crop.preferred_uv_levels,
            10,
            "UV",
            reasons,
            cautions,
        )
        score += self._match_component(
            environment.air_quality_label,
            crop.air_tolerance,
            10,
            "air quality",
            reasons,
            cautions,
        )

        resilience_points = crop.resilience_rating * 6
        score += resilience_points
        reasons.append(f"resilience rating {crop.resilience_rating}/5 supports disruption planning")

        if crop.time_to_harvest_days <= 30:
            score += 20
            reasons.append("fast harvest window supports emergency food access")
        elif crop.time_to_harvest_days <= 60:
            score += 12
            reasons.append("moderate harvest window supports recovery planting")
        elif crop.time_to_harvest_days <= 90:
            score += 6
            reasons.append("fits medium-term resilience planning")
        else:
            cautions.append("longer harvest timeline may not address immediate food gaps")

        if DISASTER_PRIORITY_CATEGORIES.intersection(crop.category):
            score += 8
            reasons.append("category aligns with disaster response priorities")

        if environment.pressure_trend == "falling":
            if crop.resilience_rating >= 4:
                score += 4
                reasons.append("high resilience is useful when falling pressure signals unstable weather")
            else:
                cautions.append("falling pressure may indicate weather volatility")

        return CropScore(
            crop=crop,
            score=min(score, 100),
            reasons=reasons[:4],
            cautions=cautions[:3],
            suggested_use_case=self._use_case_for(crop),
        )

    @staticmethod
    def _match_component(
        label: str,
        preferred_labels: list[str],
        points: int,
        name: str,
        reasons: list[str],
        cautions: list[str],
    ) -> float:
        if label == "unknown":
            cautions.append(f"{name} data unavailable; using resilience and harvest timing")
            return points * 0.35
        if label in preferred_labels:
            reasons.append(f"{name} is {label}, matching the crop preference")
            return float(points)
        cautions.append(f"{name} is {label}; preferred: {', '.join(preferred_labels)}")
        return points * 0.25

    @staticmethod
    def _use_case_for(crop: Crop) -> str:
        if "emergency" in crop.category or crop.time_to_harvest_days <= 30:
            return "emergency food support"
        if "staple" in crop.category or crop.time_to_harvest_days <= 75:
            return "recovery planting"
        return "resilience planning"
