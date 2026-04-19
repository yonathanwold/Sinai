# Sinai

Sinai is a **local-first multi-device assistant platform** for live demos.

It is designed for hackathon judging:
- one shared monitor view for the room
- many phone clients with clear device identity
- a dedicated Data Mode fed by live Arduino/sensor readings
- realtime sync across monitor, phones, and sensor updates
- global FIFO prompt queue so responses follow ask order across devices
- local execution on laptop or Raspberry Pi (no cloud dependency required)

## Final Demo Surfaces

### 1) Main Monitor (`/monitor`)
- **Assistant Mode**: shared feed of prompts + assistant responses
- **Data Mode**: live sensor dashboard with readable metrics and update feed
- connected devices list and recent activity
- clear per-device names and accents

### 2) Phone Client (`/client`)
- first-join device naming
- persisted identity in local storage
- prompt input and response history
- touch-friendly composer and fast send flow

### 3) Arduino Data Feed
- ingest endpoint: `POST /api/data/ingest`
- serial bridge script: `arduino/serial_to_sinai.py`
- merged into Data Mode in near realtime

---

## Recommended Project Structure

```text
Sinai/
  app/
    local_web/
      server.py                        # FastAPI app + websockets + data ingest
      services/
        context_provider.py            # Context construction (live/mock)
        fallback_assistant.py          # Fallback response path
        ollama_client.py               # Local Ollama client
        prompting.py                   # System prompt + message assembly
        session_store.py               # Device identity + session/feed state
      static/
        index.html                     # Monitor + client surfaces
        app.js                         # Realtime UI logic and rendering
        styles.css                     # Production-ready demo styling
    services/
      sensor_ingestion.py              # Hardware/mock sensor acquisition
      normalization.py                 # Sensor label classification
    models/
      environmental.py                 # Sensor domain models
  arduino/
    grove_light_serial.ino             # Example Arduino sketch (JSON serial lines)
    serial_to_sinai.py                 # Serial -> Sinai ingest bridge
  docs/
    install_sinai_web_pi.sh            # One-command Pi setup
    setup_pi_hotspot_portal.sh         # Pi hotspot + captive redirect
    install_ollama_mini_pi.sh
    pi_ollama_deployment.md
  requirements.txt
  requirements-hardware.txt
```

---

## Architecture Summary

### Runtime Components
- **FastAPI server** (`app/local_web/server.py`)
  - REST API for chat, context, history, devices, and data ingest
  - WebSocket endpoint for low-latency monitor/client updates
  - background sensor polling loop for dashboard freshness
- **SessionStore**
  - per-device identity (name, color, message count, connection state)
  - per-session chat history
  - shared monitor feed
- **SensorFeedState**
  - baseline sensor frames from live/mock provider
  - optional Arduino bridge overlay with stale-time handling
  - rolling history + trend series for Data Mode
- **Ollama path + fallback path**
  - local LLM via Ollama when available
  - deterministic fallback response when unavailable

### Realtime Data Flow
1. Phone opens `/client`, joins with device name.
2. Device identity is registered and persisted.
3. Prompt is sent to `POST /api/chat`.
4. Prompt + reply events are broadcast to monitor through websocket.
5. Phone receives updated history/reply and keeps identity attached.

### Arduino Data Flow
1. Arduino emits JSON lines over serial (USB).
2. `arduino/serial_to_sinai.py` parses and posts readings to `POST /api/data/ingest`.
3. Server merges readings into current sensor frame.
4. Data Mode updates instantly on monitor via websocket broadcasts.

---

## Local Run Instructions

## 1) Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate   # Windows PowerShell: .\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
```

## 2) (Recommended) Ensure Ollama is running

```bash
ollama serve
ollama pull llama3.2:1b
```

## 3) Start Sinai server

```bash
uvicorn app.local_web.server:app --host 0.0.0.0 --port 8501
```

Open:
- monitor: `http://<host-ip>:8501/monitor`
- phone: `http://<host-ip>:8501/client`

If you open `/` directly, default surface is the phone/client flow.

## 4) Optional Arduino bridge

```bash
python arduino/serial_to_sinai.py --port /dev/ttyACM0 --server http://127.0.0.1:8501
```

Windows example:

```bash
python arduino/serial_to_sinai.py --port COM5 --server http://127.0.0.1:8501
```

---

## API Notes

### Chat
- `POST /api/chat`
- body:

```json
{
  "message": "What should we prioritize next 24h?",
  "mode": "live",
  "site_name": "Sinai Local Node",
  "region": "Coastal Recovery Zone"
}
```

### Device Registration
- `POST /api/device/register`
- body:

```json
{
  "device_name": "Judge Phone 1"
}
```

### Arduino Data Ingest
- `POST /api/data/ingest`
- body:

```json
{
  "source": "arduino-serial",
  "device_name": "Arduino Uno",
  "readings": {
    "temperature_c": 27.3,
    "humidity_percent": 56,
    "soil_moisture_pct": 41,
    "light_lux": 9120,
    "uv_index": 4.2,
    "air_quality_eco2_ppm": 742,
    "air_quality_tvoc_ppb": 182,
    "pressure_hpa": 1008.2
  }
}
```

---

## Environment Variables

### AI / Service
- `OLLAMA_HOST` (default `http://127.0.0.1:11434`)
- `OLLAMA_MODEL` (default from app config)
- `SINAI_SESSION_SECRET`

### Demo Behavior
- `SINAI_SITE_NAME` (default `Sinai Local Node A-17`)
- `SINAI_MONITOR_DATA_MODE` (`live` or `mock`, default `live`)
- `SINAI_DATA_POLL_INTERVAL` (seconds, default `1.2`)
- `SINAI_ARDUINO_STALE_SECONDS` (seconds, default `25`)

---

## Raspberry Pi Deployment Notes

## One-command install on Pi

```bash
cd /home/pi/Sinai
bash docs/install_sinai_web_pi.sh llama3.2:1b /home/pi/Sinai
```

This installs dependencies, pulls model, and creates `sinai-web` systemd service.

## Check services

```bash
systemctl status sinai-web --no-pager
systemctl status ollama --no-pager
```

## Pi hotspot for local-only phone demo

```bash
sudo bash docs/setup_pi_hotspot_portal.sh Sinai-AI-Test OPEN 192.168.50.1
```

Then phones join Pi Wi-Fi and open:
- `http://192.168.50.1:8501/client`

Use monitor/HDMI:
- `http://127.0.0.1:8501/monitor`

`OPEN` means no password. If you want a password later, pass one as the second argument.

---

## Performance Decisions (for live judging reliability)

- reduced assistant response target length for faster generation
- reduced Ollama token ceiling for faster turnaround
- websocket-first realtime updates for monitor/client
- fallback polling only when websocket is disconnected
- lightweight DOM updates and bounded feed/history windows
- rolling sensor history for sparkline rendering (small in-memory footprint)
- reconnect handling for phones that refresh or temporarily drop Wi-Fi

---

## Demo Script (2-3 minutes)

1. Open monitor on HDMI (`/monitor`).
2. Connect two phones to `/client`, set different device names.
3. Send prompts from both phones; monitor shows identity per prompt/reply.
4. Switch monitor to Data Mode.
5. Start Arduino bridge and show live metric changes.
6. Emphasize that everything runs locally on one node.
