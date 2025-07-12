"""Shared state and configuration management for Pelco-D rotor control."""

import json
import os
import logging
from threading import Lock

DEVICE_ADDRESS = 1

_POSITION = [0.0, 0.0]  # [azimuth, elevation]
_SERIAL_PORT = None
_CONFIG_FILE = "config.json"
_DEFAULT_CONFIG = {
    "AZIMUTH_SPEED_DPS": 6.0,
    "ELEVATION_SPEED_DPS": 4.0
}
_CONFIG = _DEFAULT_CONFIG.copy()

lock = Lock()

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)


# --- Serial Port Management ---
def set_serial_port(port):
    """Store the serial port instance globally."""
    global _SERIAL_PORT
    _SERIAL_PORT = port


def get_serial_port():
    """Return the currently set serial port instance."""
    return _SERIAL_PORT


# --- Position Management ---
def set_position(az, el):
    """Update the current azimuth and elevation position."""
    _POSITION[0] = float(az)
    _POSITION[1] = float(el)


def get_position():
    """Get a copy of the current azimuth and elevation position."""
    return _POSITION.copy()


def reset_position():
    """Reset the internal position to azimuth=0, elevation=0."""
    set_position(0.0, 0.0)


# --- Config Management ---
def load_config():
    """Load configuration from disk if available."""
    if os.path.exists(_CONFIG_FILE):
        try:
            with open(_CONFIG_FILE, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
                _CONFIG.update(loaded)
        except (OSError, ValueError) as e:
            logging.warning("Failed to load config: %s", e)


def save_config():
    """Persist current configuration values to disk."""
    try:
        with open(_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(_CONFIG, f, indent=2)
        logging.info("Config saved.")
    except OSError as e:
        logging.error("Failed to save config: %s", e)


def get_config(key):
    """Retrieve a config value or default if not set."""
    return _CONFIG.get(key, _DEFAULT_CONFIG.get(key))


def set_config(key, value):
    """Update a configuration key and persist it."""
    _CONFIG[key] = value
    save_config()


# Load config when module is imported
load_config()
