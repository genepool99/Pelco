"""Shared state and configuration management for Pelco-D rotor control.

Provides:
- In-memory rotor position tracking
- Persistent config file management
- Thread-safe access to serial and settings
"""

import json
import os
import logging
from threading import Lock

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)


class RotorState:
    """Manages rotor position, configuration, and serial communication state."""

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

    @classmethod
    def set_serial_port(cls, port):
        """Store the serial port instance globally."""
        cls._SERIAL_PORT = port

    @classmethod
    def get_serial_port(cls):
        """Return the currently configured serial port instance."""
        return cls._SERIAL_PORT

    @classmethod
    def set_position(cls, az, el):
        """
        Set the current rotor position in memory.

        Args:
            az (float): Azimuth angle in degrees.
            el (float): Elevation angle in degrees.
        """
        cls._POSITION[0] = float(az)
        cls._POSITION[1] = float(el)

    @classmethod
    def get_position(cls):
        """
        Get a copy of the current azimuth and elevation.

        Returns:
            list: [azimuth, elevation] as floats.
        """
        return cls._POSITION.copy()

    @classmethod
    def reset_position(cls):
        """Reset rotor position to default (0° azimuth, 0° elevation)."""
        cls.set_position(0.0, 0.0)

    @classmethod
    def load_config(cls):
        """Load configuration settings from a JSON file, if it exists."""
        if os.path.exists(cls._CONFIG_FILE):
            try:
                with open(cls._CONFIG_FILE, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    cls._CONFIG.update(loaded)
            except (OSError, ValueError) as e:
                logging.warning("Failed to load config: %s", e)

    @classmethod
    def save_config(cls):
        """Save current configuration settings to a JSON file."""
        try:
            with open(cls._CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(cls._CONFIG, f, indent=2)
            logging.info("Config saved.")
        except OSError as e:
            logging.error("Failed to save config: %s", e)

    @classmethod
    def get_config(cls, key):
        """
        Retrieve a configuration value.

        Args:
            key (str): Name of the setting.

        Returns:
            Value from config or fallback default.
        """
        return cls._CONFIG.get(key, cls._DEFAULT_CONFIG.get(key))

    @classmethod
    def set_config(cls, key, value):
        """
        Set and persist a configuration value.

        Args:
            key (str): Setting name.
            value: Value to store.
        """
        cls._CONFIG[key] = value
        cls.save_config()


# Aliases for easier import usage
DEVICE_ADDRESS = RotorState.DEVICE_ADDRESS
lock = RotorState.lock
set_position = RotorState.set_position
get_position = RotorState.get_position
reset_position = RotorState.reset_position
set_serial_port = RotorState.set_serial_port
get_serial_port = RotorState.get_serial_port
get_config = RotorState.get_config
set_config = RotorState.set_config

# Load config when module is imported
RotorState.load_config()
