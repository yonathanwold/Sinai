"""Explainable environmental classification heuristics."""

from __future__ import annotations

from app.models.environmental import ClassifiedEnvironment, SensorSnapshot


def classify_temperature(temperature_c: float | None) -> str:
    if temperature_c is None:
        return "unknown"
    if temperature_c < 10:
        return "cold"
    if temperature_c < 18:
        return "cool"
    if temperature_c < 30:
        return "warm"
    return "hot"


def classify_light(light_lux: float | None) -> str:
    if light_lux is None:
        return "unknown"
    if light_lux < 1_000:
        return "low"
    if light_lux < 10_000:
        return "medium"
    return "high"


def classify_uv(uv_index: float | None) -> str:
    if uv_index is None:
        return "unknown"
    if uv_index < 3:
        return "low"
    if uv_index < 6:
        return "medium"
    return "high"


def classify_air_quality(eco2_ppm: int | None, tvoc_ppb: int | None) -> str:
    if eco2_ppm is None and tvoc_ppb is None:
        return "unknown"

    eco2 = eco2_ppm if eco2_ppm is not None else 400
    tvoc = tvoc_ppb if tvoc_ppb is not None else 0

    if eco2 <= 800 and tvoc <= 220:
        return "good"
    if eco2 <= 1_200 and tvoc <= 660:
        return "fair"
    return "poor"


def classify_pressure_trend(history_hpa: list[float]) -> str:
    if len(history_hpa) < 2:
        return "stable"

    delta = history_hpa[-1] - history_hpa[0]
    if delta > 1.0:
        return "rising"
    if delta < -1.0:
        return "falling"
    return "stable"


def normalize_environment(snapshot: SensorSnapshot) -> ClassifiedEnvironment:
    return ClassifiedEnvironment(
        raw=snapshot,
        temperature_label=classify_temperature(snapshot.temperature_c),
        light_label=classify_light(snapshot.light_lux),
        uv_label=classify_uv(snapshot.uv_index),
        air_quality_label=classify_air_quality(
            snapshot.air_quality_eco2_ppm,
            snapshot.air_quality_tvoc_ppb,
        ),
        pressure_trend=classify_pressure_trend(snapshot.pressure_history_hpa),
    )
