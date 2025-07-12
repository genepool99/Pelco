"""
Shared state management for rotor control.
Handles position tracking and the serial connection.
"""

from threading import Lock

DEVICE_ADDRESS = 1

_position = [0, 0]  # [azimuth, elevation]
_serial_port_instance = None
lock = Lock()


def set_serial_port(port):
    """Store the initialized serial port object."""
    global _serial_port_instance
    _serial_port_instance = port


def get_serial_port():
    """Return the current serial port instance."""
    return _serial_port_instance


def set_position(az, el):
    """Set the internal azimuth and elevation position."""
    global _position
    _position = [az, el]


def get_position():
    """Return the current [azimuth, elevation] as a list."""
    return _position.copy()


def reset_position():
    """Reset the position to 0, 0."""
    set_position(0, 0)
