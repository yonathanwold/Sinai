"""Environmental domain models used across ingestion, scoring, and UI."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class SensorSnapshot:
    """A single merged reading from hardware and/or mock data."""

    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    temperature_c: float | None = None
    pressure_hpa: float | None = None
    pressure_history_hpa: list[float] = field(default_factory=list)
    uv_index: float | None = None
    air_quality_eco2_ppm: int | None = None
    air_quality_tvoc_ppb: int | None = None
    light_lux: float | None = None
    light_raw: int | None = None
    source: str = "unknown"
    site_name: str = "Unassigned site"
    region: str = "Demo region"
    warnings: list[str] = field(default_factory=list)

    def with_mock_fallback(self, fallback: "SensorSnapshot") -> "SensorSnapshot":
        """Fill missing values with a fallback snapshot while preserving warnings."""

        merged_warnings = list(dict.fromkeys([*self.warnings, *fallback.warnings]))
        return SensorSnapshot(
            timestamp=self.timestamp,
            temperature_c=self.temperature_c
            if self.temperature_c is not None
            else fallback.temperature_c,
            pressure_hpa=self.pressure_hpa if self.pressure_hpa is not None else fallback.pressure_hpa,
            pressure_history_hpa=self.pressure_history_hpa or fallback.pressure_history_hpa,
            uv_index=self.uv_index,
            air_quality_eco2_ppm=self.air_quality_eco2_ppm
            if self.air_quality_eco2_ppm is not None
            else fallback.air_quality_eco2_ppm,
            air_quality_tvoc_ppb=self.air_quality_tvoc_ppb
            if self.air_quality_tvoc_ppb is not None
            else fallback.air_quality_tvoc_ppb,
            light_lux=self.light_lux if self.light_lux is not None else fallback.light_lux,
            light_raw=self.light_raw if self.light_raw is not None else fallback.light_raw,
            source="live+mock-fallback" if self.source == "live" else fallback.source,
            site_name=self.site_name or fallback.site_name,
            region=self.region or fallback.region,
            warnings=merged_warnings,
        )

    def to_display_dict(self) -> dict[str, Any]:
        """Return dashboard-friendly raw values."""

        return {
            "timestamp_utc": self.timestamp.isoformat(),
            "temperature_c": self.temperature_c,
            "pressure_hpa": self.pressure_hpa,
            "pressure_history_hpa": self.pressure_history_hpa,
            "uv_index": self.uv_index,
            "air_quality_eco2_ppm": self.air_quality_eco2_ppm,
            "air_quality_tvoc_ppb": self.air_quality_tvoc_ppb,
            "light_lux": self.light_lux,
            "light_raw": self.light_raw,
            "source": self.source,
            "site_name": self.site_name,
            "region": self.region,
            "warnings": self.warnings,
        }


@dataclass(frozen=True)
class ClassifiedEnvironment:
    """Explainable labels derived from raw sensor values."""

    raw: SensorSnapshot
    temperature_label: str
    light_label: str
    uv_label: str
    air_quality_label: str
    pressure_trend: str

    def labels(self) -> dict[str, str]:
        return {
            "temperature": self.temperature_label,
            "light": self.light_label,
            "air_quality": self.air_quality_label,
            "pressure_trend": self.pressure_trend,
        }
