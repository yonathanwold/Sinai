# Sinai

**Sinai — Offline AI for resilient food systems and environmental decisions.**

Sinai is a local-network AI assistant for low-resource and disaster-prone environments.  
It runs on a Raspberry Pi or local machine, uses local sensor/mock context, and answers mission-oriented questions through a chat-first web interface powered by Ollama.

## Why This MVP Matters

Sinai demonstrates a product-level concept, not a sensor script:

- local AI assistant as the primary workflow
- context-aware guidance with environmental signals
- resilient operation when internet access is unreliable
- accessible to multiple nearby users from phones/laptops over local Wi-Fi

Crop recommendation is included, but as one capability among broader resilience decision support.

## Main Features

- Chat-first UI (primary screen)
- Local Ollama integration (`/api/chat`)
- Context injection (temperature, pressure, UV, light, air quality, summary, top crops, risk flags)
- Mock or live sensor mode
- Session-based history (in-memory + browser session storage)
- Quick action prompts for:
  - Analyze conditions
  - Recommend crops
  - Explain risks
  - Suggest resilient next steps
- Local AI status indicator (`Local AI Running` or fallback mode)

## Project Structure

```text
Sinai/
  app/
    local_web/
      server.py
      static/
        index.html
        styles.css
        app.js
      services/
        context_provider.py
        fallback_assistant.py
        ollama_client.py
        prompting.py
        session_store.py
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
    install_ollama_mini_pi.sh
    install_sinai_web_pi.sh
    pi_ollama_deployment.md
  requirements.txt
  requirements-hardware.txt
```

## Backend Architecture (Local Web)

- **FastAPI server**: `app/local_web/server.py`
- **Chat endpoint**: `POST /api/chat`
- **Context endpoint**: `GET /api/context`
- **Health endpoint**: `GET /api/health`
- **Session history**: `GET /api/history`, `POST /api/reset`

Flow:

1. Collect environment context (mock/live).
2. Build system + context-grounded prompt.
3. Send to Ollama.
4. Return action-oriented response for resilience planning.
5. If Ollama is unavailable, use deterministic fallback guidance.

## Local Setup

### 1) Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2) Configure Ollama (optional but recommended)

```bash
export OLLAMA_HOST=http://127.0.0.1:11434
export OLLAMA_MODEL=llama3.2:1b
```

Sinai also accepts:

- `SINAI_OLLAMA_HOST`
- `SINAI_OLLAMA_MODEL`

### 3) Run the local web app (chat-first demo)

```bash
uvicorn app.local_web.server:app --host 0.0.0.0 --port 8501 --reload
```

Open:

- Local machine: `http://localhost:8501`
- Same Wi-Fi device: `http://<your-ip>:8501`

### 4) (Optional) Streamlit dashboard

```bash
streamlit run app/dashboard/streamlit_app.py --server.address 0.0.0.0 --server.port 8501
```

## Raspberry Pi One-Command Setup (FastAPI Web App)

On the Pi, run:

```bash
cd /home/pi/Sinai
bash docs/install_sinai_web_pi.sh llama3.2:1b /home/pi/Sinai
```

This installs system dependencies, Ollama, the model, Python packages, and configures `sinai-web` as a startup service.

## Network Demo (Phone/Laptop)

1. Ensure host machine and demo devices are on the same network.
2. Run Sinai with `--host 0.0.0.0`.
3. Find your machine IP:
   - macOS/Linux: `hostname -I` or `ip a`
   - Windows: `ipconfig`
4. Open `http://<ip>:8501` from phone browser.

## Sensor and Context Notes

- In **mock mode**, Sinai generates realistic region-based environmental context.
- In **live mode**, Sinai attempts hardware reads and auto-backfills missing values with mock data.
- Legacy force-mock env var remains supported:
  - `SINAI_FORCE_MOCK=true`
  - compatibility alias: `AGRISENSE_FORCE_MOCK=true`

## System Prompt Behavior

Sinai is configured to:

- stay grounded in provided context
- avoid hallucinating missing values
- explain uncertainty honestly
- provide practical actions for low-resource decision-making
- prioritize resilience, preparedness, and food access

## Fast Hackathon Demo Script (3 Minutes)

1. Open Sinai chat UI and show `Local AI Running`.
2. Ask: “What should we prioritize this week for safe food production?”
3. Ask: “What risks should we watch if weather becomes unstable?”
4. Ask: “Why is crop X not ideal right now?”
5. Highlight that everything runs locally and is accessible from nearby phones without cloud dependency.

## Where to Customize Quickly

- LLM behavior/system rules: `app/local_web/services/prompting.py`
- Context construction and top crops: `app/local_web/services/context_provider.py`
- Ollama behavior/model selection: `app/local_web/services/ollama_client.py`
- Chat UI and interaction: `app/local_web/static/index.html`, `app/local_web/static/styles.css`, `app/local_web/static/app.js`
