"""Deterministic fallback response logic for Sinai."""

from __future__ import annotations


def fallback_response(user_message: str, context: dict[str, object]) -> str:
    """Return resilient guidance if local LLM is unavailable."""

    labels = context.get("labels", {})
    top_crops = context.get("top_crops", [])
    risks = context.get("risk_flags", [])
    summary = context.get("summary", "Local context is available with partial details.")

    question = user_message.lower()
    crop_name = top_crops[0]["name"] if top_crops else "the top-ranked resilient crop"

    lines: list[str] = [f"Current context: {summary}"]

    if "crop" in question or "plant" in question:
        lines.append(
            f"Start with {crop_name} for immediate deployment because it fits the current profile and resilience constraints."
        )
        if len(top_crops) > 1:
            lines.append(
                f"Use {top_crops[1]['name']} as the secondary option to diversify risk and harvest timing."
            )

    if "risk" in question or "storm" in question or "disaster" in question:
        if risks:
            lines.append("Top risks to monitor:")
            for risk in risks[:3]:
                lines.append(f"- {risk}")
        else:
            lines.append("No immediate high-risk signal is present, but continue daily condition checks.")

    if "what should we do" in question or "next" in question or "action" in question:
        lines.extend(
            [
                "Suggested actions:",
                "- Next 24h: secure seeds, water plan, and planting labor schedule.",
                "- Next 3 days: plant fast-yield and resilient crops in staggered batches.",
                "- Next week: re-check temperature, pressure trend, and air quality before scaling.",
            ]
        )

    if labels:
        lines.append(
            "Observed condition labels: "
            f"temperature={labels.get('temperature')}, "
            f"light={labels.get('light')}, "
            f"air_quality={labels.get('air_quality')}, "
            f"pressure_trend={labels.get('pressure_trend')}."
        )

    lines.append("Local quick-response mode is active while the full on-device AI model starts.")
    return "\n".join(lines)
