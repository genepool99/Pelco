"""Shared state and configuration management for Pelco-D rotor control (refactored).

Provides:
- Thread-safe rotor position tracking
- Thread-safe serial handle storage
- Persistent config file management (atomic writes)
- Last-request tracking (requested vs applied/clamped targets)
- Aliases for convenient imports (backward compatible)

ENV:
- PELTRACK_CONFIG: optional absolute/relative path to the config.json to use.
  If unset, defaults to a file next to this module.
"""

from __future__ import annotations

import json
import os
import logging
from threading import Lock
from typing import Any, Dict, Optional, Tuple


class RotorState:
    """Manages rotor position, configuration, and serial communication state.

    Notes:
        * All public mutators/accessors are guarded by a single process-wide lock
          (``RotorState.lock``) to avoid race conditions across threads.
        * Config writes are atomic: write to ``.tmp`` then ``os.replace``.
        * The default config path can be overridden via the ``PELTRACK_CONFIG`` env var.
    """

    # Pelco-D device address (0x01 typical). Kept here for backward compat.
    DEVICE_ADDRESS: int = 1

    # Internal state
    _POSITION: Tuple[float, float] = (0.0, 0.0)  # (azimuth, elevation)
    _SERIAL_PORT: Optional[object] = None  # pyserial.Serial or compatible

    # Track the last user request vs the applied/clamped move for UI/reporting
    # Example structure:
    # {
    #   "req_az": 380.0, "req_el": 140.0,
    #   "target_az": 360.0, "target_el": 135.0,
    #   "clamped": True, "ts": 1712345678.9, "action": "set"
    # }
    _LAST_REQUEST: Optional[Dict[str, Any]] = None

    # Config file
    _BASE_DIR: str = os.path.dirname(__file__)
    _CONFIG_FILE: str = os.getenv("PELTRACK_CONFIG", os.path.join(_BASE_DIR, "config.json"))

    _DEFAULT_CONFIG: Dict[str, Any] = {
        "AZIMUTH_SPEED_DPS": 6.0,
        "ELEVATION_SPEED_DPS": 4.0,
    }
    _CONFIG: Dict[str, Any] = _DEFAULT_CONFIG.copy()

    # Global lock used across serial send, position, last-request, and config ops
    lock: Lock = Lock()

    # ----------------- Serial Port -----------------
    @classmethod
    def set_serial_port(cls, port: object) -> None:
        """Store the serial port instance globally (thread-safe)."""
        with cls.lock:
            cls._SERIAL_PORT = port

    @classmethod
    def get_serial_port(cls) -> Optional[object]:
        """Return the currently configured serial port instance (thread-safe)."""
        with cls.lock:
            return cls._SERIAL_PORT

    # ----------------- Position -----------------
    @classmethod
    def set_position(cls, az: float, el: float) -> None:
        """Set the current rotor position in memory (thread-safe)."""
        with cls.lock:
            cls._POSITION = (float(az), float(el))

    @classmethod
    def get_position(cls) -> Tuple[float, float]:
        """Get the current azimuth and elevation as a tuple (thread-safe)."""
        with cls.lock:
            return cls._POSITION

    @classmethod
    def reset_position(cls) -> None:
        """Reset rotor position to default (0° azimuth, 0° elevation)."""
        cls.set_position(0.0, 0.0)

    # ----------------- Last Request (req vs applied/clamped) -----------------
    @classmethod
    def set_last_request(cls, data: Dict[str, Any]) -> None:
        """Store details of the last requested move (thread-safe, in-memory only)."""
        with cls.lock:
            cls._LAST_REQUEST = dict(data) if data is not None else None

    @classmethod
    def get_last_request(cls) -> Optional[Dict[str, Any]]:
        """Return a shallow copy of the last requested move, if any (thread-safe)."""
        with cls.lock:
            return None if cls._LAST_REQUEST is None else dict(cls._LAST_REQUEST)

    @classmethod
    def clear_last_request(cls) -> None:
        """Clear the last-request record (thread-safe)."""
        with cls.lock:
            cls._LAST_REQUEST = None

    # ----------------- Config -----------------
    @classmethod
    def set_config_path(cls, path: str) -> None:
        """Override the config file path and reload configuration (thread-safe)."""
        with cls.lock:
            cls._CONFIG_FILE = path
            # Do not clear current config; load will merge
            cls.load_config()

    @classmethod
    def load_config(cls) -> None:
        """Load configuration settings from the JSON file, if it exists (thread-safe)."""
        with cls.lock:
            path = cls._CONFIG_FILE
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    cls._CONFIG.update(data)
                else:
                    logging.warning("Config file %s did not contain a JSON object; ignoring.", path)
            except FileNotFoundError:
                # No config yet is fine; we'll create on first save
                pass
            except json.JSONDecodeError as err:
                logging.warning("Failed to parse JSON from %s: %s", path, err)
            except OSError as err:
                logging.warning("Failed to load config %s: %s", path, err)

    @classmethod
    def save_config(cls) -> None:
        """Save current configuration settings to JSON (atomic, thread-safe)."""
        with cls.lock:
            path = cls._CONFIG_FILE
            tmp_path = f"{path}.tmp"
            try:
                # Ensure directory exists if a custom path was specified
                os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(cls._CONFIG, f, indent=2, sort_keys=True)
                os.replace(tmp_path, path)
                logging.info("Config saved to %s.", path)
            except OSError as err:
                # Best effort cleanup of temp file
                try:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                except OSError:
                    pass
                logging.error("Failed to save config to %s: %s", path, err)

    @classmethod
    def get_config(cls, key: str) -> Any:
        """Retrieve a configuration value with default fallback (thread-safe)."""
        with cls.lock:
            return cls._CONFIG.get(key, cls._DEFAULT_CONFIG.get(key))

    @classmethod
    def set_config(cls, key: str, value: Any) -> None:
        """Set and persist a configuration value (thread-safe)."""
        with cls.lock:
            cls._CONFIG[key] = value
            # Save immediately to be consistent with existing behavior
            # (callers rely on persistence after a single set)
            cls.save_config()

    @classmethod
    def update_config(cls, mapping: Dict[str, Any]) -> None:
        """Update multiple configuration values and persist once (thread-safe)."""
        with cls.lock:
            cls._CONFIG.update(mapping)
            cls.save_config()


# -------------- Aliases for easier import usage (backward compatible) --------------
DEVICE_ADDRESS = RotorState.DEVICE_ADDRESS
lock = RotorState.lock
set_position = RotorState.set_position
get_position = RotorState.get_position
reset_position = RotorState.reset_position
set_serial_port = RotorState.set_serial_port
get_serial_port = RotorState.get_serial_port
get_config = RotorState.get_config
set_config = RotorState.set_config

# NEW: last-request aliases
get_last_request = RotorState.get_last_request
set_last_request = RotorState.set_last_request
clear_last_request = RotorState.clear_last_request

# Load config when module is imported
RotorState.load_config()
