#!/usr/bin/env python3
"""Forward Arduino serial JSON lines into Sinai local data ingest API.

Example:
  python arduino/serial_to_sinai.py --port /dev/ttyACM0 --server http://127.0.0.1:8501
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import sys
import time
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

import serial


ALIASES: dict[str, tuple[str, ...]] = {
    "temperature_c": ("temperature_c", "temperature", "temp", "temp_c", "t"),
    "humidity_percent": ("humidity_percent", "humidity", "humidity_pct", "h"),
    "soil_moisture_pct": ("soil_moisture_pct", "soil_moisture", "soil", "soil_pct"),
    "pressure_hpa": ("pressure_hpa", "pressure", "pressure_mb"),
    "uv_index": ("uv_index", "uv", "uvi"),
    "light_lux": ("light_lux", "light", "lux"),
    "air_quality_eco2_ppm": ("air_quality_eco2_ppm", "eco2", "co2", "co2_ppm"),
    "air_quality_tvoc_ppb": ("air_quality_tvoc_ppb", "tvoc", "tvoc_ppb"),
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
        cleaned = value.strip().replace("%", "")
        if not cleaned:
            return None
        try:
            numeric = float(cleaned)
            return None if numeric != numeric else numeric
        except ValueError:
            return None
    return None


def parse_kv_line(line: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    chunks = [part.strip() for part in line.split(",") if part.strip()]
    for chunk in chunks:
        if "=" in chunk:
            key, value = chunk.split("=", 1)
        elif ":" in chunk:
            key, value = chunk.split(":", 1)
        else:
            continue
        result[key.strip()] = value.strip()
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
    args = parse_args()
    print(
        f"[Sinai Bridge] Opening {args.port} @ {args.baud} -> {args.server.rstrip('/')}/api/data/ingest",
        flush=True,
    )

    try:
        serial_conn = serial.Serial(args.port, args.baud, timeout=1)
    except serial.SerialException as exc:
        print(f"[Sinai Bridge] Failed to open serial port: {exc}", file=sys.stderr)
        return 1

    consecutive_failures = 0
    with serial_conn:
        while True:
            try:
                raw_line = serial_conn.readline().decode("utf-8", errors="ignore").strip()
                if not raw_line:
                    continue

                try:
                    payload = json.loads(raw_line)
                    if not isinstance(payload, dict):
                        continue
                except json.JSONDecodeError:
                    payload = parse_kv_line(raw_line)
                    if not payload:
                        continue

                readings = canonical_readings(payload)
                if not readings:
                    continue

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
                consecutive_failures = 0
                print(f"[Sinai Bridge] Sent {readings}", flush=True)
            except KeyboardInterrupt:
                print("\n[Sinai Bridge] Stopped by user.")
                return 0
            except (serial.SerialException, TimeoutError, URLError, OSError) as exc:
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
