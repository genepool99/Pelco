"""Control functions for a Pelco-D based rotor system.

Supports:
- Manual and programmatic control
- Estimated motion duration using configured speeds
- Real-time updates via callback injection
"""

import time
import logging
from typing import Optional, Callable
import serial
from state import RotorState, DEVICE_ADDRESS

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)

UpdateCallback = Optional[Callable[[str], None]]

# Adjust these if your mount allows > 90° tilt
ELEVATION_MIN = 0.0
ELEVATION_MAX = 90.0


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


def _calculate_motion_time(delta: float, speed: float) -> float:
    return abs(delta) / speed if delta else 0.0


def send_command(az_target: float, el_target: float, update_callback: UpdateCallback = None) -> str:
    """Move rotor to the target azimuth and elevation."""
    logging.info("Moving to AZ=%.1f°, EL=%.1f°", az_target, el_target)
    az_current, el_current = RotorState.get_position()
    az_delta = az_target - az_current
    el_delta = el_target - el_current

    az_speed = RotorState.get_config("AZIMUTH_SPEED_DPS")
    el_speed = RotorState.get_config("ELEVATION_SPEED_DPS")

    az_time = _calculate_motion_time(az_delta, az_speed)
    el_time = _calculate_motion_time(el_delta, el_speed)
    move_duration = max(az_time, el_time)

    if move_duration == 0:
        return "No movement needed"

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
    send_pelco_d(0x00, cmd2, 0x20, 0x20)  # Fixed speed
    time.sleep(move_duration)
    stop()

    # Clamp to limits
    el_target = max(ELEVATION_MIN, min(ELEVATION_MAX, el_target))
    RotorState.set_position(az_target, el_target)

    msg = f"Moved to az={az_target:.1f}, el={el_target:.1f} over ~{move_duration:.1f}s"
    if update_callback:
        update_callback(msg)
    return msg


def nudge_elevation(direction: int, duration: float, update_callback: UpdateCallback = None) -> str:
    """Briefly nudge elevation up or down."""
    if direction not in (-1, 1):
        return "Invalid direction"

    cmd2 = 0x08 if direction > 0 else 0x10
    send_pelco_d(0x00, cmd2, 0x00, 0x20)
    time.sleep(duration)
    stop()

    az, el = RotorState.get_position()
    delta = direction * RotorState.get_config("ELEVATION_SPEED_DPS") * duration
    new_el = el + delta
    new_el = max(ELEVATION_MIN, min(ELEVATION_MAX, new_el))
    RotorState.set_position(az, new_el)

    msg = f"Nudged elevation {'up' if direction > 0 else 'down'} for {duration:.1f} seconds"
    if update_callback:
        update_callback(msg)
    return msg


def set_horizon(update_callback: UpdateCallback = None) -> str:
    """Return elevation to 90 degrees (facing straight up), keeping current azimuth."""
    az, _ = RotorState.get_position()
    return send_command(az, 90.0, update_callback=update_callback)

def _get_config_with_default(key: str, default: float) -> float:
    value = RotorState.get_config(key)
    if value is None:
        logging.warning("Config '%s' not set. Using default: %s", key, default)
        return default
    return value

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
     
    logging.info("Starting calibration with down_time=%.1f, up_degrees=%d, az_time=%.1f",
                 down_time, up_degrees, az_time)

    # --- Elevation calibration ---
    logging.info("Calibration: tilting fully down to find mechanical stop.")
    send_pelco_d(0x00, 0x10, 0x00, 0x20)  # Down
    time.sleep(down_time)
    stop()

    logging.info("Calibration: tilting up ~%d° at %.1f°/s.", up_degrees, el_speed)
    send_pelco_d(0x00, 0x08, 0x00, 0x20)  # Up
    time.sleep(up_degrees / el_speed)
    stop()

    # --- Azimuth calibration ---
    logging.info("Calibration: rotating azimuth fully left.")
    send_pelco_d(0x00, 0x04, 0x20, 0x00)  # Left
    time.sleep(az_time)
    stop()

    # --- Finalize position ---
    RotorState.set_position(0.0, 90.0)

    msg = (
        "✓ Calibration complete. Azimuth set to 0°, Elevation set to 90°.\n"
        "Please use the web UI to make fine adjustments if needed."
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
        (0, 90)
    ]
    for az, el in steps:
        send_command(az, el, update_callback=update_callback)
    if update_callback:
        update_callback("Demo sequence completed.")
