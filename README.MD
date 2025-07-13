# Peltrack

## A Pelco-D Rotor Controller with Web Interface for Ham Radio Operators

This project provides a Python-based controller for antenna rotators using the Pelco-D protocol. It includes:
- A calibration tool
- A web-based debug/control interface
- A TCP server compatible with EasyComm & Hamlib)
- Live UI updates when controlled externally (e.g., by Gpredict)

---

## 🎞️ Features

- Serial communication with Pelco-D compatible pan/tilt rotors
- Web UI with real-time position feedback and visualizer
- TCP server for satellite tracking via **Gpredict**
- Calibration tool to measure rotor speed (°/sec)
- Supports full elevation + azimuth movement
- Accurate state persistence across manual + automated control

---

## 🔧 Requirements

- Python 3.10+
- Pelco-D compatible rotator (via RS-485)
- USB–RS485 adapter (e.g., CH340, FTDI)
- `requirements.txt` dependencies

### Install Dependencies

```bash
python -m venv venv
venv\Scripts\activate             # Windows
# OR
source venv/bin/activate         # macOS/Linux

pip install -r requirements.txt
```

---

## 🚀 Usage

### 1. Calibrate the Rotor

Accurate rotor control requires knowing your rotor’s **degrees per second** speed.

#### Initial Setup

- Connect your rotator via RS-485 and power it on.
- Rotate azimuth to its **leftmost mechanical stop**, then **center it facing true North**.
- Tilt the antenna so it is **pointing straight up**.
- This becomes your reference: **Az = 0°, El = 90°**.

#### Run Calibration

```bash
python calibrate.py
```

- Follow the prompts.
- The tool measures speed by rotating for 10 seconds.
- You enter how far it turned.
- Results are saved in `config.json`.

---

### 2. Start the Web + Gpredict Server

```bash
python peltrack.py --port COM4 --baud 2400
```

This starts:

- ✅ Web UI on [http://localhost:5000](http://localhost:5000)
- ✅ Gpredict-compatible TCP server on port **4533**

Gpredict can now command rotor movement — the Web UI updates live.

---

## 🌐 Web Interface

Features:
- View current azimuth and elevation
- Absolute move commands
- Elevation nudges (↑/↓)
- Set to "horizon" (el=0)
- Visual dial + bar graph
- "Run Demo" simulates satellite pass
- Live updates if rotor is moved externally (e.g. by Gpredict)

---

## 🛁 Gpredict Setup

1. Open Gpredict Preferences → Interfaces → Rotator
2. Add a new interface:
   - **Hostname**: `localhost`
   - **Port**: `4533`
   - **Protocol**: `Hamlib rotctld` or `EasyComm II`
3. Enable rotator interface during satellite passes.

---

## 📜 Resetting / Re-Zeroing

If the rotor is bumped, moved manually, or drifts:

- Use the Web UI’s **"Reset Position"** to mark current position as 0/0
- Or from Python:

```python
from state import reset_position
reset_position()
```

You can also **re-run the calibration script** at any time.

---

## 🔁 Live Sync with Gpredict

When Gpredict sends new commands, the Web UI **automatically updates** in real-time to reflect the current position.

No page refresh needed — uses `Flask-SocketIO` + `eventlet`.

---

## 🧪 Tested With

- Windows 11 + Python 3.11
- CH340 USB–RS485 adapter
- [Gpredict 2.3](https://gpredict.oz9aec.net/)
- [SkyRoof 1.15 Beta](https://skyroof.org/)

---

## 📁 Project Structure

```
peltrack/
├── calibrate.py           # CLI calibration tool
├── config.json            # Saved calibration data (az/el speed)
├── easycomm_server.py     # TCP server for Gpredict
├── page_template.py       # Web UI HTML template
├── pelco_commands.py      # Rotor control logic
├── peltrack.py            # Flask + SocketIO + TCP bridge
├── requirements.txt       # Dependencies
├── state.py               # Shared config/state/limits
└── limits.json            # Optional Az/El range limits 
```

---

## 📌 License

MIT License. Use at your own risk.

---

## 🚀 Credits

2025 — Avi Solomon (AE7ET)
