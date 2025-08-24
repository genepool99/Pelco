"""Shared state and configuration management for Pelco-D rotor control.

Provides:
- Thread-safe rotor position tracking
- Thread-safe serial handle storage
- Persistent config file management (atomic writes)
- Last-request (req_az/req_el) tracking + clamped flag for the UI
- Backward-compatible aliases for common accessors

ENV:
- PELTRACK_CONFIG: optional absolute/relative path to the config.json to use.
  If unset, defaults to a file next to this module.
"""

from __future__ import annotations

import json
import os
import logging
from threading import RLock
from typing import Any, Dict, Optional, Tuple


class RotorState:
    """Process-wide state container for Pelco-D rotor control.

    Thread-safety:
        All public getters/setters are serialized with a single process-wide
        lock (``RotorState.lock``). We use an RLock to avoid deadlocks when a
        method (e.g., set_config) calls another method (e.g., save_config)
        that also needs the same lock.

    Persistence:
        Config writes are atomic (write to ``.tmp`` then ``os.replace``).
        The config file location can be overridden via ``PELTRACK_CONFIG``.

    Stored values:
        - Position (azimuth, elevation) in *physical degrees* as floats.
        - Serial port handle (pyserial ``Serial`` or compatible).
        - Last UI request (requested az/el before clamping) + clamped flag.
        - Config dictionary with sane defaults.
    """

    # Pelco-D device address (0x01 typical).
    DEVICE_ADDRESS: int = 1

    # Internal state
    _POSITION: Tuple[float, float] = (0.0, 0.0)     # (azimuth, elevation) phys degrees
    _SERIAL_PORT: Optional[object] = None           # pyserial.Serial or compatible

    # Last user request (unclamped) + whether backend clamped to limits
    _LAST_REQUEST: Optional[Tuple[float, float]] = None
    _LAST_WAS_CLAMPED: bool = False

    # Config file path
    _BASE_DIR: str = os.path.dirname(__file__)
    _CONFIG_FILE: str = os.getenv("PELTRACK_CONFIG", os.path.join(_BASE_DIR, "config.json"))

    # Defaults (extend safely as features land)
    _DEFAULT_CONFIG: Dict[str, Any] = {
        "AZIMUTH_SPEED_DPS": 9.4,
        "ELEVATION_SPEED_DPS": 10.8,
        "CALIBRATE_DOWN_DURATION_SEC": 20,
        "CALIBRATE_UP_TRAVEL_DEGREES": 90,
        "CALIBRATE_AZ_LEFT_DURATION_SEC": 28,
        "TIME_SAFETY_FACTOR": 0.985,
        "REZERO_EXTRA_SECS": 1.5,
        "EL_NEAR_STOP_DEG": 8.0,
        "EL_BREAKAWAY_SEC_UP": 0.6,
        "EL_BREAKAWAY_SEC_DOWN": 0.4,
        "EL_BREAKAWAY_SPEED_BYTE": 63,
        "EL_UP_NEAR_STOP_FACTOR": 0.90,
        "EL_DOWN_NEAR_STOP_FACTOR": 0.95,
        "EL_APPROACH_OVERSHOOT_DEG": 0.0,
        "ZERO_OVERDRIVE_SEC": 0.0,
    }
    _CONFIG: Dict[str, Any] = _DEFAULT_CONFIG.copy()

    # Process-wide lock for all state/config/serial operations (re-entrant!)
    lock: RLock = RLock()

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
        """Set the current rotor position (physical degrees) (thread-safe)."""
        with cls.lock:
            cls._POSITION = (float(az), float(el))

    @classmethod
    def get_position(cls) -> Tuple[float, float]:
        """Get the current azimuth/elevation (physical degrees) (thread-safe)."""
        with cls.lock:
            return cls._POSITION

    @classmethod
    def reset_position(cls) -> None:
        """Reset rotor position to default (0° azimuth, 0° elevation)."""
        cls.set_position(0.0, 0.0)

    # ----------------- Last Request (for UI) -----------------
    @classmethod
    def set_last_request(cls, req_az: float, req_el: float, clamped: bool = False) -> None:
        """Remember the last requested (unclamped) az/el and whether it was clamped."""
        with cls.lock:
            cls._LAST_REQUEST = (float(req_az), float(req_el))
            cls._LAST_WAS_CLAMPED = bool(clamped)


    @classmethod
    def get_last_request(cls) -> Tuple[Optional[float], Optional[float], bool]:
        """Return a 3-tuple (req_az|None, req_el|None, clamped)."""
        # Snapshot under lock, then work outside the lock
        with cls.lock:
            last = cls._LAST_REQUEST
            clamped = cls._LAST_WAS_CLAMPED

        # Pylint-friendly guard: Optional[...] → check None, then unpack
        if last is None:
            return (None, None, False)

        req_az_raw, req_el_raw = last  # safe after None-check

        try:
            req_az = float(req_az_raw)
            req_el = float(req_el_raw)
        except (TypeError, ValueError):
            # Defensive reset if anything looks corrupted
            with cls.lock:
                cls._LAST_REQUEST = None
                cls._LAST_WAS_CLAMPED = False
            return (None, None, False)

        return (req_az, req_el, clamped)




    # ----------------- Config -----------------
    @classmethod
    def set_config_path(cls, path: str) -> None:
        """Override the config file path and reload configuration (thread-safe)."""
        with cls.lock:
            cls._CONFIG_FILE = path
            cls.load_config()

    @classmethod
    def load_config(cls) -> None:
        """Load configuration from JSON, merging into defaults (thread-safe)."""
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
        """Persist configuration to JSON atomically (thread-safe)."""
        with cls.lock:
            path = cls._CONFIG_FILE
            tmp_path = f"{path}.tmp"
            try:
                os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(cls._CONFIG, f, indent=2, sort_keys=True)
                os.replace(tmp_path, path)
                logging.info("Config saved to %s.", path)
            except OSError as err:
                # Best-effort cleanup of temp file
                try:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                except OSError:
                    pass
                logging.error("Failed to save config to %s: %s", path, err)

    @classmethod
    def get_config(cls, key: str) -> Any:
        """Retrieve a configuration value (with fallback to defaults) (thread-safe)."""
        with cls.lock:
            return cls._CONFIG.get(key, cls._DEFAULT_CONFIG.get(key))

    @classmethod
    def set_config(cls, key: str, value: Any) -> None:
        """Set and persist a single configuration value (thread-safe)."""
        with cls.lock:
            cls._CONFIG[key] = value
            cls.save_config()

    @classmethod
    def update_config(cls, mapping: Dict[str, Any]) -> None:
        """Update multiple configuration values and persist once (thread-safe)."""
        with cls.lock:
            cls._CONFIG.update(mapping)
            cls.save_config()


# ----------------- Aliases (backward compatible) -----------------
DEVICE_ADDRESS = RotorState.DEVICE_ADDRESS
lock = RotorState.lock
set_position = RotorState.set_position
get_position = RotorState.get_position
reset_position = RotorState.reset_position
set_serial_port = RotorState.set_serial_port
get_serial_port = RotorState.get_serial_port
get_config = RotorState.get_config
set_config = RotorState.set_config
get_last_request = RotorState.get_last_request
set_last_request = RotorState.set_last_request

# Load config on import
RotorState.load_config()
