"""Control functions for a Pelco-D based rotor system.

Supports:
- Manual and programmatic control
- Estimated motion duration using configured speeds
- Real-time updates via callback injection
"""

import time
import os
import json
import logging
from typing import Optional, Callable
import serial
from state import RotorState, DEVICE_ADDRESS

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)

UpdateCallback = Optional[Callable[[str], None]]

# --------------------------------------------------------------------
# Limits: load from limits.json with sensible fallbacks
# EL geometry: 90° = neutral (straight up), typical range 45–135°
# --------------------------------------------------------------------
_THIS_DIR = os.path.dirname(__file__)
_LIMITS_PATH = os.path.join(_THIS_DIR, "limits.json")

def _load_limits():
    az_min, az_max = 0.0, 360.0
    el_min, el_max = 45.0, 135.0
    try:
        with open(_LIMITS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError as e:
        logging.info("limits.json not found (%s); using defaults AZ[0,360], EL[45,135].", e)
        return az_min, az_max, el_min, el_max
    except (json.JSONDecodeError, OSError) as e:
        logging.warning("Failed to read/parse limits.json (%s); using defaults.", e)
        return az_min, az_max, el_min, el_max
    else:
        return (
            float(data.get("az_min", az_min)),
            float(data.get("az_max", az_max)),
            float(data.get("el_min", el_min)),
            float(data.get("el_max", el_max)),
        )

AZ_MIN, AZ_MAX, ELEVATION_MIN, ELEVATION_MAX = _load_limits()

def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))

# --------------------------------------------------------------------
# Serial / Pelco-D primitives
# --------------------------------------------------------------------
def init_serial(port: str, baudrate: int):
    """Open a serial connection to the Pelco-D device."""
    ser = serial.Serial(port=port, baudrate=baudrate, timeout=1)
    RotorState.set_serial_port(ser)

def send_pelco_d(cmd1: int, cmd2: int, data1: int, data2: int = 0x00):
    """Send a Pelco-D command frame over serial."""
    ser = RotorState.get_serial_port()
    if not ser:
        raise RuntimeError("Serial port not initialized")

    with RotorState.lock:
        msg = bytearray([
            0xFF,
            DEVICE_ADDRESS,
            cmd1,
            cmd2,
            data1,
            data2,
            (DEVICE_ADDRESS + cmd1 + cmd2 + data1 + data2) % 256,
        ])
        ser.write(msg)
        logging.debug("Sent PELCO-D: %s", [hex(b) for b in msg])
        time.sleep(0.05)

def stop():
    """Immediately halt all rotor motion."""
    send_pelco_d(0x00, 0x00, 0x00, 0x00)

def _get_config_with_default(key: str, default: float) -> float:
    value = RotorState.get_config(key)
    if value is None:
        logging.warning("Config '%s' not set. Using default: %s", key, default)
        return default
    return value

def _calculate_motion_time(delta: float, speed: float) -> float:
    if speed is None or speed <= 0:
        # Guard against bad config values
        return 0.0 if delta == 0 else 0.0
    return abs(delta) / speed if delta else 0.0

# --------------------------------------------------------------------
# High-level motion
# --------------------------------------------------------------------
def send_command(az_target: float, el_target: float, update_callback: UpdateCallback = None) -> str:
    """Move rotor to the target azimuth and elevation.

    Targets are clamped to AZ[AZ_MIN,AZ_MAX], EL[ELEVATION_MIN,ELEVATION_MAX]
    *before* timing is calculated so motion duration and stored state match
    the actual mechanical move.
    """
    # Clamp EARLY to keep timing/state consistent with mechanical limits
    az_target = _clamp(az_target, AZ_MIN, AZ_MAX)
    el_target = _clamp(el_target, ELEVATION_MIN, ELEVATION_MAX)

    logging.info("Moving to AZ=%.1f°, EL=%.1f°", az_target, el_target)
    az_current, el_current = RotorState.get_position()
    az_delta = az_target - az_current
    el_delta = el_target - el_current

    az_speed = _get_config_with_default("AZIMUTH_SPEED_DPS", 10.0)
    el_speed = _get_config_with_default("ELEVATION_SPEED_DPS", 5.0)

    az_time = _calculate_motion_time(az_delta, az_speed)
    el_time = _calculate_motion_time(el_delta, el_speed)
    move_duration = max(az_time, el_time)

    if move_duration == 0:
        # Still update state to the clamped target, in case caller fed an out-of-range value
        RotorState.set_position(az_target, el_target)
        msg = "No movement needed"
        if update_callback:
            update_callback(msg)
        return msg

    # Build direction byte
    cmd2 = 0
    if az_delta > 0:
        cmd2 |= 0x02  # Right
    elif az_delta < 0:
        cmd2 |= 0x04  # Left
    if el_delta > 0:
        cmd2 |= 0x08  # Up
    elif el_delta < 0:
        cmd2 |= 0x10  # Down

    logging.debug("Moving: Δaz=%.1f°, Δel=%.1f°, est. duration=%.2fs",
                  az_delta, el_delta, move_duration)

    # Start motion at fixed speed (0x20 is a typical mid/fast step for many heads)
    send_pelco_d(0x00, cmd2, 0x20, 0x20)
    time.sleep(move_duration)
    stop()

    # Store final (already clamped) position
    RotorState.set_position(az_target, el_target)

    msg = f"Moved to az={az_target:.1f}, el={el_target:.1f} over ~{move_duration:.1f}s"
    if update_callback:
        update_callback(msg)
    return msg

def nudge_elevation(direction: int, duration: float, update_callback: UpdateCallback = None) -> str:
    """Briefly nudge elevation up (+1) or down (-1) for a duration in seconds."""
    if direction not in (-1, 1):
        return "Invalid direction"

    cmd2 = 0x08 if direction > 0 else 0x10
    send_pelco_d(0x00, cmd2, 0x00, 0x20)
    time.sleep(duration)
    stop()

    az, el = RotorState.get_position()
    el_speed = _get_config_with_default("ELEVATION_SPEED_DPS", 5.0)
    delta = direction * el_speed * duration
    new_el = _clamp(el + delta, ELEVATION_MIN, ELEVATION_MAX)
    RotorState.set_position(az, new_el)

    msg = f"Nudged elevation {'up' if direction > 0 else 'down'} for {duration:.1f} seconds"
    if update_callback:
        update_callback(msg)
    return msg

def set_horizon(update_callback: UpdateCallback = None) -> str:
    """Return elevation to 90 degrees (neutral/zenith), keeping current azimuth."""
    az, _ = RotorState.get_position()
    return send_command(az, 90.0, update_callback=update_callback)

# --------------------------------------------------------------------
# Calibration & tests
# --------------------------------------------------------------------
def calibrate(update_callback: UpdateCallback = None) -> str:
    """
    Calibrate both azimuth and elevation:
    - Tilt fully down
    - Tilt up by configured degrees
    - Rotate azimuth fully left
    """
    # --- Load timing/config values ---
    down_time = _get_config_with_default("CALIBRATE_DOWN_DURATION_SEC", 10)
    up_degrees = _get_config_with_default("CALIBRATE_UP_TRAVEL_DEGREES", 90)
    el_speed = _get_config_with_default("ELEVATION_SPEED_DPS", 5.0)
    az_time = _get_config_with_default("CALIBRATE_AZ_LEFT_DURATION_SEC", 40)

    logging.info("Starting calibration with down_time=%.1f, up_degrees=%s, az_time=%.1f",
                 down_time, up_degrees, az_time)

    # --- Elevation calibration ---
    logging.info("Calibration: tilting fully down to find mechanical stop.")
    send_pelco_d(0x00, 0x10, 0x00, 0x20)  # Down
    time.sleep(down_time)
    stop()

    logging.info("Calibration: tilting up ~%s° at %.1f°/s.", up_degrees, el_speed)
    send_pelco_d(0x00, 0x08, 0x00, 0x20)  # Up
    time.sleep(float(up_degrees) / el_speed if el_speed > 0 else 0)
    stop()

    # --- Azimuth calibration ---
    logging.info("Calibration: rotating azimuth fully left.")
    send_pelco_d(0x00, 0x04, 0x20, 0x00)  # Left
    time.sleep(az_time)
    stop()

    # --- Finalize position: neutral/zenith at EL=90 ---
    RotorState.set_position(0.0, 90.0)

    msg = (
        "✓ Calibration complete. Azimuth set to 0°, Elevation set to 90°.\n"
        "Use the web UI to make fine adjustments if needed."
    )
    if update_callback:
        update_callback(msg)

    return msg

def test_azimuth_speed(duration: int = 10):
    """Test azimuth speed by rotating right and measuring degrees."""
    logging.info("Rotating right for %d seconds. Measure degrees moved.", duration)
    send_pelco_d(0x00, 0x02, 0x20, 0x00)
    time.sleep(duration)
    stop()
    try:
        degrees = float(input("Enter degrees moved: "))
        RotorState.set_config("AZIMUTH_SPEED_DPS", degrees / duration)
        logging.info("Saved AZIMUTH_SPEED_DPS = %.2f", degrees / duration)
    except ValueError:
        logging.error("Invalid input.")

def test_elevation_speed(duration: int = 10):
    """Test elevation speed by tilting up and measuring degrees."""
    logging.info("Tilting up for %d seconds. Measure degrees moved.", duration)
    send_pelco_d(0x00, 0x08, 0x00, 0x20)
    time.sleep(duration)
    stop()
    try:
        degrees = float(input("Enter degrees moved: "))
        RotorState.set_config("ELEVATION_SPEED_DPS", degrees / duration)
        logging.info("Saved ELEVATION_SPEED_DPS = %.2f", degrees / duration)
    except ValueError:
        logging.error("Invalid input.")

def run_demo_sequence(update_callback: UpdateCallback = None):
    """Run a fixed set of positions to demo rotor movement."""
    steps = [
        (0, 90),
        (90, 60),
        (180, 45),
        (270, 70),
        (0, 90),
    ]
    for az, el in steps:
        send_command(az, el, update_callback=update_callback)
    if update_callback:
        update_callback("Demo sequence completed.")
