# Peltrack
## A Pelco-D Rotor Controller with Web Interface for Ham Radio Operators

This project provides a Python-based controller for an antenna rotator using the Pelco-D protocol. It includes:
- A calibration tool
- A web-based control interface
- A TCP server compatible with Gpredict (`rotctld` or EasyComm-like) for satellite tracking

---

## 🎞️ Features

- Serial communication with a Pelco-D compatible pan/tilt unit
- Interactive web UI for testing and sending commands
- Command-line calibration mode
- TCP server for integration with **Gpredict**

---

## 🔧 Requirements

- Python 3.10+
- A Pelco-D compatible rotator (via RS-485)
- USB–RS485 adapter (e.g., CH340, FTDI)
- Flask (for the web UI)

### Install Dependencies

```bash
pip install flask
```

---

## 🚀 Usage

### 1. Calibrate the Rotor

Accurate rotor control requires knowing how fast your Pelco-D unit moves in **degrees per second**. The calibration tool determines this automatically.

#### Initial Setup
- Connect your rotator via RS-485 and power it on.
- Verify your USB–RS485 adapter is connected (e.g., `COM4` on Windows).
- Manually rotate the azimuth to its **leftmost stop**, then turn it right to face **true North**.
- Level the elevation so it's flat (0°).
- This becomes your **zero reference position**: Azimuth = 0°, Elevation = 0°.

#### Run the Tool

```bash
python calibrate.py
```

You will:
1. Enter your serial port (e.g., `COM4`) and optional baud rate.
2. Let the motor move for 10 seconds during each test.
3. Measure how far it turned and input the degrees moved.

The script will:
- Calculate **azimuth and elevation speed** (°/sec)
- Save the result to `config.json`

---

### 2. Start the Web + Gpredict Server

```bash
python pelco_web.py --port COM4 --baud 2400
```

- Web UI: [http://localhost:5000](http://localhost:5000)
- Gpredict TCP server: Port `4533`  
  Supports both **EasyComm** and **Hamlib-style** `P az el` commands.

---

## 🌐 Web Interface

- View current azimuth and elevation
- Send absolute positions
- Nudge elevation up/down
- Run a test demo
- Reset or re-calibrate

---

## 🛁 Gpredict Setup

1. Open Gpredict Preferences → Interfaces → Rotator.
2. Add a new interface:
   - **Hostname**: `localhost`
   - **Port**: `4533`
   - **Protocol**: `Hamlib rotctld` or `EasyComm II`
3. Enable the rotator interface during satellite tracking.

---

## 📜 Resetting / Re-Zeroing

If the rotor is moved manually or drifts out of alignment:

- Use the web UI’s **“Reset Position”** button to set internal tracking to AZ=0, EL=0.
- Or reset from code:

```python
from state import reset_position
reset_position()
```

You may also re-run the calibration script at any time.

---

## 📍 Notes

- Re-calibration is only needed if motor speed changes (due to hardware differences or wear).
- Always manually re-zero if the mount is physically adjusted.
- Accurate calibration ensures precise satellite tracking and rotator control.

---

## 🧪 Tested With

- Windows 11+ Python 3.11
- CH340 USB–RS485 adapter
- [Gpredict 2.3](https://gpredict.oz9aec.net/) & [SkyRoof 1.15 Beta](https://skyroof.org/)


---

## 📁 Project Structure

```
├── pelco_commands.py       # Core rotor logic
├── state.py                # Shared state and config management
├── pelco_web.py            # Flask app + TCP control server
├── easycomm_server.py      # TCP server for Gpredict (EasyComm/Hamlib)
├── calibrate.py            # CLI-based rotor calibration tool
├── page_template.py        # HTML for control interface
├── config.json             # Saved calibration values
```

---

## 📌 License

MIT License. Use at your own risk.

---

## 🚀 Credits

2025 - Avi Solomon (AE7ET) 