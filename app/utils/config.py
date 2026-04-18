"""Runtime configuration with local-first defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CROP_DATA_PATH = PROJECT_ROOT / "app" / "data" / "crops.json"


@dataclass(frozen=True)
class AppConfig:
    force_mock: bool = False
    arduino_port: str | None = None
    arduino_baud: int = 9600
    spa06_i2c_bus: int = 1
    spa06_i2c_address: int = 0x77
    ollama_host: str | None = None
    ollama_model: str = "llama3.2:1b"


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _first_env(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


def get_config() -> AppConfig:
    return AppConfig(
        force_mock=_env_bool("SINAI_FORCE_MOCK", _env_bool("AGRISENSE_FORCE_MOCK", False)),
        arduino_port=os.getenv("ARDUINO_PORT"),
        arduino_baud=int(os.getenv("ARDUINO_BAUD", "9600")),
        spa06_i2c_bus=int(os.getenv("SPA06_I2C_BUS", "1")),
        spa06_i2c_address=int(os.getenv("SPA06_I2C_ADDRESS", "0x77"), 16),
        ollama_host=_first_env("SINAI_OLLAMA_HOST", "OLLAMA_HOST"),
        ollama_model=_first_env("SINAI_OLLAMA_MODEL", "OLLAMA_MODEL") or "llama3.2:1b",
    )
