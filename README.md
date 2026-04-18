# AgriSense AI

Disaster-Resilient Food Intelligence Platform for the Sinai hackathon project.

AgriSense AI is a local-first food intelligence MVP for NGOs, governments, agricultural co-ops, and disaster response organizations. It combines edge environmental sensing with explainable crop recommendations so field teams can make local food decisions when internet access, cloud dashboards, or centralized supply chains fail.

## What It Does

- Reads pressure, temperature, UV, air quality, and light data from a Raspberry Pi plus Arduino sensor stack.
- Runs in demo/mock mode automatically when hardware is unavailable.
- Normalizes raw readings into simple labels: cold, cool, warm, hot, low, medium, high, good, fair, poor, rising, stable, and falling.
- Scores crops using explainable heuristics for climate fit, resilience, and time to harvest.
- Presents the result as a B2B SaaS dashboard for deployment sites, agencies, and relief operations.
- Includes a local-model-ready AI recommendation service that can later connect to Ollama.

## Folder Structure

```text
Sinai/
  app/
    dashboard/
      streamlit_app.py
    data/
      crops.json
    models/
      crop.py
      environmental.py
    services/
      ai_recommender.py
      crop_engine.py
      normalization.py
      sensor_ingestion.py
    utils/
      config.py
      formatting.py
  arduino/
    grove_light_serial.ino
  docs/
    hardware_architecture.md
  README.md
  requirements.txt
  requirements-hardware.txt
```

## Hardware Architecture

```text
Arduino reads Grove Light Sensor on A0
Arduino sends JSON over serial to Raspberry Pi

Raspberry Pi reads:
- SPA06-003 / SPL06-style pressure and temperature sensor over I2C
- VEML6070 UV sensor over I2C
- CCS811 eCO2 and TVOC air quality sensor over I2C
- Arduino light readings over USB serial

Raspberry Pi runs:
- sensor ingestion
- classification
- crop scoring
- recommendation explanations
- Streamlit dashboard
```

More hardware notes are in `docs/hardware_architecture.md`.

## Software Architecture

- `app/models`: domain dataclasses for sensor snapshots, classified environments, crops, and crop scores.
- `app/services/sensor_ingestion.py`: mock sensor generator plus best-effort live hardware readers.
- `app/services/normalization.py`: explainable environmental classification rules.
- `app/services/crop_engine.py`: crop scoring and emergency crop selection.
- `app/services/ai_recommender.py`: local AI abstraction with deterministic fallback explanations.
- `app/dashboard/streamlit_app.py`: polished operator dashboard and B2B demo framing.
- `app/data/crops.json`: seed crop database with resilience, harvest time, and environmental preferences.

## Quick Start

From the project root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app/dashboard/streamlit_app.py
```

The app defaults to demo/mock mode, so it should run without sensors.

## Run In Mock Mode

Mock mode is the default. You can also force it explicitly:

```powershell
$env:AGRISENSE_FORCE_MOCK="true"
streamlit run app/dashboard/streamlit_app.py
```

Use the sidebar to choose a region such as Coastal Recovery Zone, Urban Relief Hub, Dry Inland Cooperative, or Mountain Valley Site.

## Connect Real Sensors Later

On the Raspberry Pi:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-hardware.txt
export AGRISENSE_FORCE_MOCK=false
export ARDUINO_PORT=/dev/ttyACM0
streamlit run app/dashboard/streamlit_app.py --server.address 0.0.0.0
```

On Windows with an Arduino connected:

```powershell
$env:AGRISENSE_FORCE_MOCK="false"
$env:ARDUINO_PORT="COM3"
streamlit run app/dashboard/streamlit_app.py
```

If any sensor fails, the app logs a warning in Sensor diagnostics and fills the missing values with mock data.

## Optional Local AI

The current recommendation layer is deterministic and offline-safe. To try Ollama later:

```bash
export OLLAMA_HOST=http://localhost:11434
export OLLAMA_MODEL=llama3.2
```

The service is already abstracted in `app/services/ai_recommender.py`.

## Hackathon Demo Script

1. Open with the problem: after disasters, communities may lose internet access and supply chains, but local food decisions still need to happen.
2. Show the Raspberry Pi and Arduino architecture: local sensors feed an edge dashboard.
3. Open the dashboard and select a scenario like Hurricane recovery.
4. Point to the environmental cards: the system converts raw readings into explainable labels.
5. Show the top 3 crops and explain that scoring prioritizes crop fit, fast harvest, and resilience.
6. Open Sensor diagnostics and mention that mock fallback keeps field demos reliable.
7. Close with the business model: recurring analytics and AI recommendations per deployment site for NGOs, governments, co-ops, and disaster agencies.

## Where To Customize

- Edit crops and scoring inputs in `app/data/crops.json`.
- Tune classification thresholds in `app/services/normalization.py`.
- Adjust crop ranking weights in `app/services/crop_engine.py`.
- Swap in a real local model in `app/services/ai_recommender.py`.
- Change dashboard copy and layout in `app/dashboard/streamlit_app.py`.
- Update hardware wiring notes in `docs/hardware_architecture.md`.

## Notes

This MVP is intentionally reliability-first. It is built to demo well even if the hardware kit is incomplete, the serial port changes, or I2C sensors are unavailable during judging.
