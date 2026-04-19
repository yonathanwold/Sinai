"""Context assembly for Sinai chat prompts and side panel rendering."""

from __future__ import annotations

from app.services.crop_engine import CropScoringEngine
from app.services.normalization import normalize_environment
from app.services.sensor_ingestion import REGION_PROFILES, SensorIngestionService
from app.utils.config import get_config
from app.utils.formatting import fmt_number, humanize_label


class ContextProvider:
    """Build structured, explainable context for the assistant."""

    def __init__(self) -> None:
        self.config = get_config()
        self.sensor_service = SensorIngestionService(self.config)
        self.crop_engine = CropScoringEngine.from_json()
        self.default_region = next(iter(REGION_PROFILES.keys()))

    def get_context(
        self,
        mode: str = "mock",
        site_name: str = "Sinai Local Node",
        region: str | None = None,
    ) -> dict[str, object]:
        mode = mode if mode in {"mock", "live"} else "mock"
        resolved_region = region if region in REGION_PROFILES else self.default_region

        snapshot = self.sensor_service.read_environment(
            mode=mode,
            site_name=site_name,
            region=resolved_region,
        )
        environment = normalize_environment(snapshot)
        ranked = self.crop_engine.rank_crops(environment)

        top_crops = [
            {
                "name": item.crop.name,
                "score": item.score_percent,
                "time_to_harvest_days": item.crop.time_to_harvest_days,
                "resilience_rating": item.crop.resilience_rating,
                "category": [humanize_label(cat) for cat in item.crop.category],
                "use_case": item.suggested_use_case,
                "reasons": item.reasons[:2],
                "cautions": item.cautions[:2],
            }
            for item in ranked[:5]
        ]

        labels = environment.labels()
        risks = self._build_risks(labels)
        return {
            "site_name": snapshot.site_name,
            "region": snapshot.region,
            "source": snapshot.source,
            "timestamp_utc": snapshot.timestamp.isoformat(),
            "readings": {
                "temperature_c": snapshot.temperature_c,
                "pressure_hpa": snapshot.pressure_hpa,
                "light_lux": snapshot.light_lux,
                "air_quality_eco2_ppm": snapshot.air_quality_eco2_ppm,
                "air_quality_tvoc_ppb": snapshot.air_quality_tvoc_ppb,
            },
            "labels": labels,
            "summary": self._summary(snapshot, labels),
            "top_crops": top_crops,
            "risk_flags": risks,
            "warnings": snapshot.warnings,
            "available_regions": list(REGION_PROFILES.keys()),
        }

    @staticmethod
    def _summary(snapshot, labels: dict[str, str]) -> str:
        return (
            f"Conditions are {labels['temperature']} with {labels['light']} light. "
            f"Air quality is {labels['air_quality']} and pressure trend is "
            f"{labels['pressure_trend']}. "
            f"Current readings: {fmt_number(snapshot.temperature_c, ' C')}, "
            f"{fmt_number(snapshot.pressure_hpa, ' hPa', 1)}, "
            f"{fmt_number(snapshot.light_lux, ' lux', 0)} light, "
            f"eCO2 {fmt_number(snapshot.air_quality_eco2_ppm, ' ppm', 0)}."
        )

    @staticmethod
    def _build_risks(labels: dict[str, str]) -> list[str]:
        risk_flags: list[str] = []
        if labels["temperature"] == "hot":
            risk_flags.append("Heat stress risk for fragile seedlings and water demand.")
        if labels["pressure_trend"] == "falling":
            risk_flags.append("Falling pressure may indicate unstable weather conditions.")
        if labels["air_quality"] == "poor":
            risk_flags.append("Poor air quality may reduce growth quality for sensitive crops.")
        if not risk_flags:
            risk_flags.append("No high-severity alert. Continue daily monitoring for rapid changes.")
        return risk_flags
