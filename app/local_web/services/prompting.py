"""Prompt templates for Sinai chat behavior."""

from __future__ import annotations

import json


SINAI_SYSTEM_PROMPT = """
You are Sinai, an offline environmental and food resilience assistant.

Mission:
- Support users in low-resource, disaster-prone, or food-insecure environments.
- Provide practical, action-oriented decision support for resilience planning.
- Crop recommendation is one capability, not the entire product.

Rules:
- Ground answers in the provided local context block and explicitly reference it.
- Never invent sensor values or claim data you were not given.
- If data is missing or uncertain, say so clearly and provide safe fallback guidance.
- Focus on food access, preparedness, risk reduction, and sustainability.
- Assume unreliable connectivity; do not require internet-dependent steps.

Response style:
- Keep a calm, trustworthy tone.
- Include:
  1) what current conditions imply,
  2) practical actions (now / next few days),
  3) key tradeoffs or risks to monitor.
- Use short paragraphs or bullet points that field teams can execute quickly.
- Default to concise outputs (about 120-180 words) unless the user asks for depth.
""".strip()


def _compact_context(context: dict[str, object]) -> dict[str, object]:
    top_crops = context.get("top_crops", [])
    compact_top = []
    for crop in top_crops[:3]:
        compact_top.append(
            {
                "name": crop.get("name"),
                "score": crop.get("score"),
                "harvest_days": crop.get("time_to_harvest_days"),
                "use_case": crop.get("use_case"),
            }
        )

    return {
        "site_name": context.get("site_name"),
        "region": context.get("region"),
        "source": context.get("source"),
        "summary": context.get("summary"),
        "labels": context.get("labels", {}),
        "readings": context.get("readings", {}),
        "top_crops": compact_top,
        "risk_flags": list(context.get("risk_flags", []))[:3],
        "warnings": list(context.get("warnings", []))[:2],
    }


def build_messages(
    user_message: str,
    context: dict[str, object],
    history: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Build Ollama chat messages with context injection."""

    context_block = json.dumps(_compact_context(context), indent=2)
    messages: list[dict[str, str]] = [
        {"role": "system", "content": SINAI_SYSTEM_PROMPT},
        {
            "role": "system",
            "content": (
                "Current local deployment context (treat as operational ground truth):\n"
                f"{context_block}"
            ),
        },
    ]

    # Keep recent turns to preserve short-session continuity.
    for turn in history[-4:]:
        role = turn.get("role", "")
        content = turn.get("content", "").strip()
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": user_message.strip()})
    return messages
