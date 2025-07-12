# Pelco-D Rotor Controller with Web Interface + Gpredict Support

This project provides a Python-based controller for an antenna rotator using the Pelco-D protocol. It includes:
- A calibration tool
- A web-based control interface
- A TCP server compatible with Gpredict (`rotctld` or EasyComm-like) for satellite tracking

## 📦 Features

- Serial communication with a Pelco-D compatible pan/tilt unit
- Interactive web UI to test and send commands
- Command-line calibration mode
- TCP server for integration with **Gpredict**

---

## 🔧 Requirements

- Python 3.10+
- A Pelco-D compatible rotator (via RS-485)
- USB–RS485 adapter (e.g., CH340, FTDI)
- Flask (for the web UI)

Install dependencies:

```bash
pip install flask
```

## 🚀 Usage

### 1. Calibrate Your Rotor
Run the calibration script to determine degrees/second speed for azimuth and elevation:

```bash
python calibrate.py
```

Follow prompts to connect to your serial port (e.g., COM4).  
Enter degrees moved after each test.  
Values will be saved to `config.json`.

### 2. Start the Web + Gpredict Server

```bash
python pelco_web.py --port COM4 --baud 2400
```

- Web UI: [http://localhost:5000](http://localhost:5000)
- Gpredict TCP: port 4533 (supports both EasyComm and Hamlib-style `P az el` commands)

---

## 🌐 Web Interface

- View current position and speed
- Send az/el positions
- Nudge elevation up/down
- Run test demo
- Reset or calibrate manually

---

## 📡 Gpredict Setup

In Gpredict:

1. Open Preferences → Interfaces → Rotator.
2. Add a new interface:
    - Hostname: `localhost`
    - Port: `4533`
    - Protocol: Hamlib rotctld or EasyComm II
3. Enable the rotator interface while tracking.

---

