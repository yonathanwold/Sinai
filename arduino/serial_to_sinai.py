#!/usr/bin/env python3
"""Forward Arduino serial JSON lines into Sinai local data ingest API.

Example:
  python arduino/serial_to_sinai.py --port /dev/ttyACM0 --server http://127.0.0.1:8501
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import re
import sys
import time
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

ALIASES: dict[str, tuple[str, ...]] = {
    "temperature_c": (
        "temperature_c",
        "temperature",
        "temp",
        "temp_c",
        "t",
        "temperature_tmp36",
        "temperature_tmp36_c",
    ),
    "humidity_percent": ("humidity_percent", "humidity", "humidity_pct", "h"),
    "soil_moisture_pct": ("soil_moisture_pct", "soil_moisture", "soil", "soil_pct"),
    "pressure_hpa": ("pressure_hpa", "pressure", "pressure_mb"),
    "uv_index": ("uv_index", "uv", "uvi"),
    "light_lux": ("light_lux", "light", "lux"),
    "air_quality_eco2_ppm": ("air_quality_eco2_ppm", "eco2", "co2", "co2_ppm"),
    "air_quality_tvoc_ppb": ("air_quality_tvoc_ppb", "tvoc", "tvoc_ppb", "voc"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Arduino serial bridge for Sinai")
    parser.add_argument("--port", required=True, help="Serial port, e.g. /dev/ttyACM0 or COM5")
    parser.add_argument("--baud", type=int, default=9600, help="Serial baud rate")
    parser.add_argument(
        "--server",
        default="http://127.0.0.1:8501",
        help="Sinai server base URL, e.g. http://127.0.0.1:8501",
    )
    parser.add_argument(
        "--source",
        default="arduino-serial",
        help="Source tag sent to Sinai ingest API",
    )
    parser.add_argument(
        "--device-name",
        default="Arduino",
        help="Device name shown in Data Mode",
    )
    parser.add_argument(
        "--site-name",
        default=None,
        help="Optional site name override for ingested data",
    )
    parser.add_argument(
        "--region",
        default=None,
        help="Optional region override for ingested data",
    )
    return parser.parse_args()


def coerce_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
        return None if numeric != numeric else numeric
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return None
        # Accept values with units like "23.4 C", "1012 hPa", or "411 ppm".
        match = re.search(r"[-+]?\d+(?:\.\d+)?", cleaned.replace(",", ""))
        if not match:
            return None
        numeric = float(match.group(0))
        return None if numeric != numeric else numeric
    return None


def normalize_key(key: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", key.strip().lower())
    return normalized.strip("_")


def parse_kv_line(line: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    chunks = [part.strip() for part in re.split(r"[,\|]", line) if part.strip()]
    for chunk in chunks:
        if "=" in chunk:
            key, value = chunk.split("=", 1)
        elif ":" in chunk:
            key, value = chunk.split(":", 1)
        else:
            continue
        normalized_key = normalize_key(key)
        if normalized_key:
            result[normalized_key] = value.strip()
    return result


def canonical_readings(payload: dict[str, Any]) -> dict[str, float]:
    normalized: dict[str, float] = {}
    for canonical, aliases in ALIASES.items():
        value: float | None = None
        for alias in aliases:
            if alias in payload:
                value = coerce_float(payload.get(alias))
                if value is not None:
                    break
        if value is not None:
            normalized[canonical] = value
    return normalized


def normalize_payload_keys(payload: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in payload.items():
        normalized_key = normalize_key(str(key))
        if normalized_key:
            normalized[normalized_key] = value
    return normalized


def post_ingest(server: str, body: dict[str, Any]) -> None:
    url = f"{server.rstrip('/')}/api/data/ingest"
    data = json.dumps(body).encode("utf-8")
    request = Request(
        url=url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=4) as response:
        response.read()


def main() -> int:
    try:
        import serial as serial_module  # type: ignore
    except ImportError:
        print("[Sinai Bridge] Missing dependency: pyserial (`pip install pyserial`).", file=sys.stderr)
        return 1

    args = parse_args()
    print(
        f"[Sinai Bridge] Opening {args.port} @ {args.baud} -> {args.server.rstrip('/')}/api/data/ingest",
        flush=True,
    )

    try:
        serial_conn = serial_module.Serial(args.port, args.baud, timeout=1)
    except serial_module.SerialException as exc:
        print(f"[Sinai Bridge] Failed to open serial port: {exc}", file=sys.stderr)
        return 1

    consecutive_failures = 0
    cycle_readings: dict[str, float] = {}
    cycle_started_at: float | None = None

    def emit_cycle(readings: dict[str, float]) -> None:
        body = {
            "source": args.source,
            "device_name": args.device_name,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "readings": readings,
        }
        if args.site_name:
            body["site_name"] = args.site_name
        if args.region:
            body["region"] = args.region

        post_ingest(args.server, body)
        print(f"[Sinai Bridge] Sent {readings}", flush=True)

    with serial_conn:
        while True:
            try:
                raw_line = serial_conn.readline().decode("utf-8", errors="ignore").strip()
                now = time.monotonic()

                if raw_line:
                    if raw_line.startswith("----"):
                        if cycle_readings:
                            emit_cycle(dict(cycle_readings))
                            cycle_readings.clear()
                            cycle_started_at = None
                            consecutive_failures = 0
                        continue

                    try:
                        json_payload = json.loads(raw_line)
                        if isinstance(json_payload, dict):
                            payload = normalize_payload_keys(json_payload)
                        else:
                            payload = {}
                    except json.JSONDecodeError:
                        payload = parse_kv_line(raw_line)

                    readings = canonical_readings(payload)
                    if readings:
                        if cycle_started_at is None:
                            cycle_started_at = now
                        cycle_readings.update(readings)
                        # JSON snapshots usually include a complete set; send immediately.
                        if raw_line.startswith("{") and raw_line.endswith("}"):
                            emit_cycle(dict(cycle_readings))
                            cycle_readings.clear()
                            cycle_started_at = None
                            consecutive_failures = 0
                # Fallback flush for sketches without separator lines.
                if cycle_readings and cycle_started_at and (now - cycle_started_at) > 2.2:
                    emit_cycle(dict(cycle_readings))
                    cycle_readings.clear()
                    cycle_started_at = None
                    consecutive_failures = 0
            except KeyboardInterrupt:
                print("\n[Sinai Bridge] Stopped by user.")
                return 0
            except (serial_module.SerialException, TimeoutError, URLError, OSError) as exc:
                consecutive_failures += 1
                wait_seconds = min(5, 1 + consecutive_failures)
                print(
                    f"[Sinai Bridge] Temporary error ({exc}). Retrying in {wait_seconds}s...",
                    file=sys.stderr,
                    flush=True,
                )
                time.sleep(wait_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
