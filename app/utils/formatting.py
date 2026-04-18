"""Small formatting helpers for dashboard display."""

from __future__ import annotations


def fmt_number(value: float | int | None, suffix: str = "", digits: int = 1) -> str:
    if value is None:
        return "Unavailable"
    if isinstance(value, int):
        return f"{value}{suffix}"
    return f"{value:.{digits}f}{suffix}"


def humanize_label(label: str) -> str:
    return label.replace("_", " ").title()
