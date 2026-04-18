# Hardware Architecture

Sinai is designed as a local-first edge deployment. The Raspberry Pi is the main controller, local AI host, and dashboard server. The Arduino acts as a simple analog bridge for the Grove Light Sensor.

## Components

| Component | Role | Interface |
| --- | --- | --- |
| Raspberry Pi | Main controller, local dashboard, recommendation engine | Python, Streamlit, I2C, USB serial |
| Arduino | Grove Light Sensor bridge | USB serial to Raspberry Pi |
| Grove Light Sensor | Light level input | Analog pin A0 on Arduino |
| SPA06-003 / SPL06-style sensor | Pressure and temperature | I2C |
| VEML6070 | UV sensing | I2C |
| CCS811 | Air quality, eCO2, TVOC | I2C |

## Data Flow

```text
Grove Light Sensor -> Arduino -> USB Serial -> Raspberry Pi
SPA06-003 ---------> I2C ------------------> Raspberry Pi
VEML6070 ----------> I2C ------------------> Raspberry Pi
CCS811 ------------> I2C ------------------> Raspberry Pi

Raspberry Pi -> Sensor ingestion -> Normalization -> Crop scoring -> AI-ready recommendation layer -> Streamlit dashboard
```

## Reliability Model

The app defaults to demo/mock mode so the hackathon presentation is reliable. In live sensor mode, each hardware reader fails independently. If one sensor is missing, the app keeps the live readings that worked and fills the missing fields with mock data. If no live sensor values are available, the app clearly warns that it is using mock fallback data.

## Raspberry Pi Notes

1. Enable I2C with `sudo raspi-config`.
2. Install demo dependencies with `pip install -r requirements.txt`.
3. Install hardware dependencies with `pip install -r requirements-hardware.txt`.
4. Connect the Arduino over USB and set `ARDUINO_PORT`, for example `/dev/ttyACM0`.
5. Run Streamlit on the Pi and open the dashboard from the local network.

## Environment Variables

| Variable | Purpose | Example |
| --- | --- | --- |
| `SINAI_FORCE_MOCK` | Keep mock mode forced even if live mode is selected | `false` |
| `ARDUINO_PORT` | Arduino serial device | `/dev/ttyACM0` or `COM3` |
| `ARDUINO_BAUD` | Arduino serial baud rate | `9600` |
| `SPA06_I2C_BUS` | Raspberry Pi I2C bus | `1` |
| `SPA06_I2C_ADDRESS` | Pressure sensor address | `0x77` |
| `OLLAMA_HOST` | Optional local model endpoint | `http://localhost:11434` |
| `OLLAMA_MODEL` | Optional Ollama model name | `llama3.2:1b` |
| `AGRISENSE_FORCE_MOCK` | Legacy compatibility alias for `SINAI_FORCE_MOCK` | `false` |
