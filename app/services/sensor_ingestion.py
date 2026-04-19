"""Sensor ingestion for mock mode and Raspberry Pi deployments."""

from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.models.environmental import SensorSnapshot
from app.utils.config import AppConfig


REGION_PROFILES: dict[str, dict[str, Any]] = {
    "Coastal Recovery Zone": {
        "temperature": (24.0, 33.0),
        "pressure": (1004.0, 1012.0),
        "eco2": (450, 900),
        "tvoc": (60, 260),
        "light": (8_000, 42_000),
        "trend": "falling",
    },
    "Urban Relief Hub": {
        "temperature": (20.0, 29.0),
        "pressure": (1008.0, 1018.0),
        "eco2": (650, 1_350),
        "tvoc": (120, 700),
        "light": (800, 12_000),
        "trend": "stable",
    },
    "Dry Inland Cooperative": {
        "temperature": (27.0, 38.0),
        "pressure": (1010.0, 1020.0),
        "eco2": (430, 850),
        "tvoc": (40, 200),
        "light": (18_000, 60_000),
        "trend": "rising",
    },
    "Mountain Valley Site": {
        "temperature": (12.0, 23.0),
        "pressure": (990.0, 1004.0),
        "eco2": (420, 760),
        "tvoc": (30, 180),
        "light": (4_000, 28_000),
        "trend": "stable",
    },
}


@dataclass
class MockSensorProvider:
    site_name: str
    region: str

    def read(self) -> SensorSnapshot:
        profile = REGION_PROFILES.get(self.region, REGION_PROFILES["Coastal Recovery Zone"])
        pressure = random.uniform(*profile["pressure"])
        history = self._pressure_history(pressure, profile["trend"])
        light_lux = random.uniform(*profile["light"])

        return SensorSnapshot(
            timestamp=datetime.now(timezone.utc),
            temperature_c=round(random.uniform(*profile["temperature"]), 1),
            pressure_hpa=round(pressure, 1),
            pressure_history_hpa=history,
            uv_index=None,
            air_quality_eco2_ppm=random.randint(*profile["eco2"]),
            air_quality_tvoc_ppb=random.randint(*profile["tvoc"]),
            light_lux=round(light_lux, 0),
            light_raw=max(0, min(1023, round(light_lux / 60))),
            source="mock",
            site_name=self.site_name,
            region=self.region,
        )

    @staticmethod
    def _pressure_history(current: float, trend: str) -> list[float]:
        if trend == "falling":
            start = current + random.uniform(1.2, 3.0)
        elif trend == "rising":
            start = current - random.uniform(1.2, 3.0)
        else:
            start = current + random.uniform(-0.5, 0.5)

        return [round(start + ((current - start) * idx / 4), 1) for idx in range(5)]


class HardwareSensorProvider:
    """Best-effort Pi hardware reader. Failures are returned as warnings."""

    def __init__(self, config: AppConfig, site_name: str, region: str):
        self.config = config
        self.site_name = site_name
        self.region = region

    def read(self) -> SensorSnapshot:
        warnings: list[str] = []

        temperature_c, pressure_hpa = self._read_spa06(warnings)
        eco2_ppm, tvoc_ppb = self._read_ccs811(warnings)
        light_lux, light_raw = self._read_arduino_light(warnings)

        pressure_history = [pressure_hpa] if pressure_hpa is not None else []
        return SensorSnapshot(
            timestamp=datetime.now(timezone.utc),
            temperature_c=temperature_c,
            pressure_hpa=pressure_hpa,
            pressure_history_hpa=pressure_history,
            uv_index=None,
            air_quality_eco2_ppm=eco2_ppm,
            air_quality_tvoc_ppb=tvoc_ppb,
            light_lux=light_lux,
            light_raw=light_raw,
            source="live",
            site_name=self.site_name,
            region=self.region,
            warnings=warnings,
        )

    def _read_spa06(self, warnings: list[str]) -> tuple[float | None, float | None]:
        try:
            from smbus2 import SMBus  # type: ignore
        except ImportError:
            warnings.append("SPA06/SPL06 reader unavailable: install smbus2 on Raspberry Pi.")
            return None, None

        try:
            with SMBus(self.config.spa06_i2c_bus) as bus:
                sensor = SPA06Reader(bus, self.config.spa06_i2c_address)
                return sensor.read_temperature_pressure()
        except Exception as exc:  # Hardware buses fail loudly when sensors are absent.
            warnings.append(f"SPA06/SPL06 read failed: {exc}")
            return None, None

    @staticmethod
    def _read_ccs811(warnings: list[str]) -> tuple[int | None, int | None]:
        try:
            import board  # type: ignore
            import adafruit_ccs811  # type: ignore
        except ImportError:
            warnings.append("CCS811 reader unavailable: install Adafruit CircuitPython libraries.")
            return None, None

        try:
            i2c = board.I2C()
            sensor = adafruit_ccs811.CCS811(i2c)
            for _ in range(10):
                if sensor.data_ready:
                    return int(sensor.eco2), int(sensor.tvoc)
                time.sleep(0.1)
            warnings.append("CCS811 did not report data_ready before timeout.")
            return None, None
        except Exception as exc:
            warnings.append(f"CCS811 read failed: {exc}")
            return None, None

    def _read_arduino_light(self, warnings: list[str]) -> tuple[float | None, int | None]:
        if not self.config.arduino_port:
            warnings.append("Arduino light sensor port not configured; set ARDUINO_PORT.")
            return None, None

        try:
            import serial  # type: ignore
        except ImportError:
            warnings.append("Arduino serial reader unavailable: install pyserial.")
            return None, None

        try:
            with serial.Serial(
                self.config.arduino_port,
                self.config.arduino_baud,
                timeout=2,
            ) as connection:
                line = connection.readline().decode("utf-8", errors="ignore").strip()
            payload = json.loads(line)
            return float(payload.get("light_lux")), int(payload.get("light_raw"))
        except Exception as exc:
            warnings.append(f"Arduino light read failed: {exc}")
            return None, None


class SPA06Reader:
    """Minimal SPL06/SPA06 pressure and temperature reader."""

    SCALE_FACTORS = {
        1: 524_288,
        2: 1_572_864,
        4: 3_670_016,
        8: 7_864_320,
        16: 253_952,
        32: 516_096,
        64: 1_040_384,
        128: 2_088_960,
    }

    def __init__(self, bus: Any, address: int):
        self.bus = bus
        self.address = address

    def read_temperature_pressure(self) -> tuple[float, float]:
        self._configure()
        coeffs = self._read_coefficients()
        raw_pressure = self._read_signed_24(0x00)
        raw_temperature = self._read_signed_24(0x03)
        scale = self.SCALE_FACTORS[8]

        temp_scaled = raw_temperature / scale
        pressure_scaled = raw_pressure / scale
        temperature_c = (coeffs["c0"] * 0.5) + (coeffs["c1"] * temp_scaled)
        pressure_pa = (
            coeffs["c00"]
            + pressure_scaled
            * (
                coeffs["c10"]
                + pressure_scaled * (coeffs["c20"] + pressure_scaled * coeffs["c30"])
            )
            + temp_scaled * coeffs["c01"]
            + temp_scaled
            * pressure_scaled
            * (coeffs["c11"] + pressure_scaled * coeffs["c21"])
        )
        return round(temperature_c, 1), round(pressure_pa / 100.0, 1)

    def _configure(self) -> None:
        self.bus.write_byte_data(self.address, 0x06, 0x03)
        self.bus.write_byte_data(self.address, 0x07, 0x83)
        self.bus.write_byte_data(self.address, 0x08, 0x07)
        time.sleep(0.08)

    def _read_coefficients(self) -> dict[str, int]:
        data = self.bus.read_i2c_block_data(self.address, 0x10, 18)
        return {
            "c0": self._sign_extend((data[0] << 4) | (data[1] >> 4), 12),
            "c1": self._sign_extend(((data[1] & 0x0F) << 8) | data[2], 12),
            "c00": self._sign_extend((data[3] << 12) | (data[4] << 4) | (data[5] >> 4), 20),
            "c10": self._sign_extend(((data[5] & 0x0F) << 16) | (data[6] << 8) | data[7], 20),
            "c01": self._sign_extend((data[8] << 8) | data[9], 16),
            "c11": self._sign_extend((data[10] << 8) | data[11], 16),
            "c20": self._sign_extend((data[12] << 8) | data[13], 16),
            "c21": self._sign_extend((data[14] << 8) | data[15], 16),
            "c30": self._sign_extend((data[16] << 8) | data[17], 16),
        }

    def _read_signed_24(self, register: int) -> int:
        data = self.bus.read_i2c_block_data(self.address, register, 3)
        return self._sign_extend((data[0] << 16) | (data[1] << 8) | data[2], 24)

    @staticmethod
    def _sign_extend(value: int, bits: int) -> int:
        sign_bit = 1 << (bits - 1)
        return (value & (sign_bit - 1)) - (value & sign_bit)


class SensorIngestionService:
    def __init__(self, config: AppConfig):
        self.config = config

    def read_environment(self, mode: str, site_name: str, region: str) -> SensorSnapshot:
        mock_provider = MockSensorProvider(site_name=site_name, region=region)
        if mode == "mock" or self.config.force_mock:
            return mock_provider.read()

        hardware_snapshot = HardwareSensorProvider(self.config, site_name, region).read()
        mock_snapshot = mock_provider.read()
        merged = hardware_snapshot.with_mock_fallback(mock_snapshot)

        if self._has_no_live_values(hardware_snapshot):
            return SensorSnapshot(
                timestamp=merged.timestamp,
                temperature_c=merged.temperature_c,
                pressure_hpa=merged.pressure_hpa,
                pressure_history_hpa=merged.pressure_history_hpa,
                uv_index=None,
                air_quality_eco2_ppm=merged.air_quality_eco2_ppm,
                air_quality_tvoc_ppb=merged.air_quality_tvoc_ppb,
                light_lux=merged.light_lux,
                light_raw=merged.light_raw,
                source=merged.source,
                site_name=merged.site_name,
                region=merged.region,
                warnings=[
                    *merged.warnings,
                    "No live sensor values were available; dashboard is using mock fallback data.",
                ],
            )
        return merged

    @staticmethod
    def _has_no_live_values(snapshot: SensorSnapshot) -> bool:
        return all(
            value is None
            for value in [
                snapshot.temperature_c,
                snapshot.pressure_hpa,
                snapshot.air_quality_eco2_ppm,
                snapshot.air_quality_tvoc_ppb,
                snapshot.light_lux,
            ]
        )
