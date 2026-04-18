# Sinai

Sinai is a disaster-resilient, offline-capable food intelligence MVP for NGOs, governments, co-ops, and response agencies.

It combines edge sensors, deterministic crop scoring, and a local AI advisor so field teams can make food-production decisions even when internet and supply chains fail.

## What Sinai Does

- Ingests sensor data from Raspberry Pi I2C sensors plus Arduino serial light readings.
- Auto-falls back to realistic mock data if live hardware is missing.
- Classifies environment with explainable labels (temperature, light, UV, air quality, pressure trend).
- Scores and ranks crops with resilience and harvest-speed priorities.
- Serves a polished local dashboard that can be opened from nearby phones/laptops.
- Supports local LLM guidance through Ollama, with deterministic fallback always available.

## Product Framing

Sinai is designed as an edge SaaS deployment model:

- `Edge node`: Raspberry Pi runs sensing, scoring, LLM interface, and web dashboard.
- `Users`: nearby field operators connect via local network/hotspot on any browser.
- `Business model`: recurring analytics and recommendation software per deployment site.

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
      local_ai_advisor.py
      normalization.py
      sensor_ingestion.py
    utils/
      config.py
      formatting.py
  arduino/
    grove_light_serial.ino
  docs/
    hardware_architecture.md
    pi_ollama_deployment.md
    install_ollama_mini_pi.sh
  README.md
  requirements.txt
  requirements-hardware.txt
```

## Hardware Architecture

```text
Arduino (Grove Light Sensor A0)
  -> serial JSON -> Raspberry Pi

Raspberry Pi (I2C sensors)
  - SPA06-003 (pressure/temperature)
  - VEML6070 (UV)
  - CCS811 (air quality)
  - Arduino serial light

Pi runtime
  - sensor ingestion + fallback
  - environment classification
  - crop scoring and ranking
  - local AI explanations (optional)
  - Streamlit web dashboard
```

## Software Architecture

- `app/services/sensor_ingestion.py`: live reads + mock fallback merge.
- `app/services/normalization.py`: explainable threshold classification.
- `app/services/crop_engine.py`: ranking logic + emergency candidates.
- `app/services/ai_recommender.py`: narrative recommendation output.
- `app/services/local_ai_advisor.py`: local LLM Q&A adapter + fallback.
- `app/dashboard/streamlit_app.py`: B2B-ready UI with `Sinai Dashboard`, `Local LLM Advisor`, and `Edge Deployment` tabs.

## Quick Start (Local Demo)

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app/dashboard/streamlit_app.py
```

### Linux / macOS / Raspberry Pi

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app/dashboard/streamlit_app.py
```

Open `http://localhost:8501`.

## Mock Mode and Live Mode

- Dashboard defaults to mock-friendly behavior and never hard-crashes on sensor failures.
- In the sidebar, choose:
  - `Demo/mock mode`
  - `Live sensor mode` (with automatic backfill for missing signals)

You can force mock mode by env var:

```bash
export SINAI_FORCE_MOCK=true
```

Legacy compatibility is kept for `AGRISENSE_FORCE_MOCK`.

## Raspberry Pi + Ollama Mini (Recommended for Demo)

Fast path:

```bash
bash docs/install_ollama_mini_pi.sh llama3.2:1b /home/pi/Sinai
```

Detailed instructions:

- `docs/pi_ollama_deployment.md`

Important environment variables:

- `OLLAMA_HOST` or `SINAI_OLLAMA_HOST` (example: `http://127.0.0.1:11434`)
- `OLLAMA_MODEL` or `SINAI_OLLAMA_MODEL` (default: `llama3.2:1b`)

## Multi-User Offline Access

Run Streamlit on all interfaces:

```bash
streamlit run app/dashboard/streamlit_app.py --server.address 0.0.0.0 --server.port 8501
```

Nearby users on the same network open:

```text
http://<pi-ip>:8501
```

For strongest offline story, use Pi hotspot mode and let all demo devices join that SSID.

## Arduino Sketch

Upload:

- `arduino/grove_light_serial.ino`

This sends light readings over serial for Pi ingestion.

## Hackathon Demo Flow (3-4 minutes)

1. Open with disruption problem: no cloud, no stable supply chains, but food decisions still needed.
2. Show Sinai dashboard live with current field profile and top crop strategy.
3. Open `Local LLM Advisor` tab and ask an operational question.
4. Open `Edge Deployment` tab to show local-network URLs and Pi deployment readiness.
5. Close with B2B model: deploy per site for NGOs/agencies with recurring analytics + AI guidance.

## Where To Customize Quickly

- Crop library and metadata: `app/data/crops.json`
- Scoring weights and ranking: `app/services/crop_engine.py`
- Classification thresholds: `app/services/normalization.py`
- Local LLM behavior/fallback: `app/services/local_ai_advisor.py`
- UI copy, layout, visuals: `app/dashboard/streamlit_app.py`
- Pi deployment setup: `docs/pi_ollama_deployment.md`

## Notes

Sinai is intentionally reliability-first for live judging:

- sensor read failures degrade gracefully
- mock data preserves demo continuity
- recommendation engine remains deterministic
- local AI layer improves explainability without becoming a single point of failure
