"""
Shared state management for rotor control.
Handles position tracking, serial connection, and config persistence.
"""

import json
import os
from threading import Lock

DEVICE_ADDRESS = 1

_position = [0.0, 0.0]  # [azimuth, elevation]
_serial_port_instance = None
lock = Lock()

CONFIG_FILE = "config.json"
DEFAULT_CONFIG = {
    "AZIMUTH_SPEED_DPS": 6.0,
    "ELEVATION_SPEED_DPS": 4.0
}
_config = DEFAULT_CONFIG.copy()


# --- Serial Port Management ---
def set_serial_port(port):
    global _serial_port_instance
    _serial_port_instance = port


def get_serial_port():
    return _serial_port_instance


# --- Position Management ---
def set_position(az, el):
    global _position
    _position = [float(az), float(el)]


def get_position():
    return _position.copy()


def reset_position():
    set_position(0.0, 0.0)


# --- Config Management ---
def load_config():
    global _config
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                _config.update(json.load(f))
        except Exception as e:
            print(f"[WARN] Failed to load config: {e}")


def save_config():
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(_config, f, indent=2)
        print("[INFO] Config saved.")
    except Exception as e:
        print(f"[ERROR] Failed to save config: {e}")


def get_config(key):
    return _config.get(key, DEFAULT_CONFIG.get(key))


def set_config(key, value):
    _config[key] = value
    save_config()


# Load config on import
load_config()
