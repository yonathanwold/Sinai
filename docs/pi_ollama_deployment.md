# Sinai Pi + Ollama Mini Deployment

This guide turns Sinai into a portable offline decision node:

- Sensor ingestion on Raspberry Pi + Arduino
- Deterministic crop ranking in Python
- Local LLM explanation with Ollama mini
- Multi-user local website accessible by phone/laptop
- Shared monitor surface + phone client split
- Optional Arduino serial bridge service

## 1. One-command setup

From the Sinai repo on Raspberry Pi:

```bash
bash docs/install_sinai_web_pi.sh llama3.2:1b /home/pi/Sinai
```

This installs Ollama, pulls `llama3.2:1b`, installs Python deps, and creates `sinai-web` (FastAPI local web app) as a systemd service.

To enable automatic Arduino bridge service during install, set env vars first:

```bash
export ARDUINO_PORT=/dev/ttyACM0
export ARDUINO_BAUD=9600
export ARDUINO_DEVICE_NAME="Arduino Uno"
bash docs/install_sinai_web_pi.sh llama3.2:1b /home/pi/Sinai
```

If you still need the Streamlit dashboard service flow, use:

```bash
bash docs/install_ollama_mini_pi.sh llama3.2:1b /home/pi/Sinai
```

## 2. Manual setup (if you prefer)

```bash
sudo apt update && sudo apt upgrade -y
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl enable --now ollama
ollama pull llama3.2:1b

cd /home/pi/Sinai
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-hardware.txt

export OLLAMA_HOST=http://127.0.0.1:11434
export OLLAMA_MODEL=llama3.2:1b
export SINAI_FORCE_MOCK=false
uvicorn app.local_web.server:app --host 0.0.0.0 --port 8501
```

## 3. Local network access

Users connected to the same Wi-Fi (or Pi hotspot) can open:

```text
Monitor: http://<pi-ip>:8501/monitor
Phone:   http://<pi-ip>:8501/client
```

Find the Pi IP:

```bash
hostname -I
```

## 4. Hotspot mode (fully offline demo)

For hackathon demos, Pi hotspot mode gives the cleanest story:

1. Pi creates AP network.
2. Phones/laptops join Pi SSID.
3. Users open `/client` on phones and `/monitor` on HDMI/shared screen.

This demonstrates true offline operation even when external internet is unavailable.

One-command hotspot + captive redirect setup:

```bash
sudo bash docs/setup_pi_hotspot_portal.sh Sinai-AI-Test OPEN 192.168.50.1
```

After phones join the Pi SSID, most devices auto-open a captive portal window that redirects to:

```text
Monitor: http://192.168.50.1/monitor
Phone:   http://192.168.50.1/client
```

If captive portal auto-open does not trigger, users can browse to that URL directly.

`OPEN` sets no Wi-Fi password for quick live demos.

## 5. Safety model (recommended)

- Keep crop scoring deterministic in `app/services/crop_engine.py`.
- Use local LLM only for explanations and Q&A in `app/services/local_ai_advisor.py`.
- Keep fallback guidance enabled so the UI still works if Ollama is unavailable.
