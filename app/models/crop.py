"""Crop domain models and scoring result structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Crop:
    name: str
    category: list[str]
    preferred_temperature_bands: list[str]
    preferred_light_levels: list[str]
    preferred_uv_levels: list[str]
    air_tolerance: list[str]
    resilience_rating: int
    time_to_harvest_days: int
    notes: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Crop":
        return cls(
            name=payload["name"],
            category=list(payload.get("category", [])),
            preferred_temperature_bands=list(payload.get("preferred_temperature_bands", [])),
            preferred_light_levels=list(payload.get("preferred_light_levels", [])),
            preferred_uv_levels=list(payload.get("preferred_uv_levels", [])),
            air_tolerance=list(payload.get("air_tolerance", [])),
            resilience_rating=int(payload.get("resilience_rating", 1)),
            time_to_harvest_days=int(payload.get("time_to_harvest_days", 90)),
            notes=payload.get("notes", ""),
        )


@dataclass(frozen=True)
class CropScore:
    crop: Crop
    score: float
    reasons: list[str] = field(default_factory=list)
    cautions: list[str] = field(default_factory=list)
    suggested_use_case: str = "resilience planning"

    @property
    def score_percent(self) -> int:
        return max(0, min(100, round(self.score)))
