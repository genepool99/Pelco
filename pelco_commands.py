"""Control functions for a Pelco-D based rotor system.
Includes serial setup, calibrated movement logic, and demo sequencing.

Supports:
- Manual and programmatic control
- Estimated motion duration using configured speeds
- Real-time updates via callback injection
"""

import time
import logging
import serial

from state import RotorState, DEVICE_ADDRESS

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)


def init_serial(port, baudrate):
    """Initialize and open a serial connection to the Pelco-D device."""
    ser = serial.Serial(port=port, baudrate=baudrate, timeout=1)
    RotorState.set_serial_port(ser)


def send_pelco_d(cmd1, cmd2, data1, data2=0x00):
    """
    Construct and send a Pelco-D protocol command frame over serial.
    """
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
        time.sleep(0.05)  # allow processing time


def stop():
    """Send stop command to immediately halt all rotor motion."""
    send_pelco_d(0x00, 0x00, 0x00, 0x00)


def send_command(az_target, el_target):
    """
    Move the rotor to a target azimuth and elevation.
    Uses configured speed to calculate estimated duration.
    """
    az_current, el_current = RotorState.get_position()
    az_delta = az_target - az_current
    el_delta = el_target - el_current

    az_speed = RotorState.get_config("AZIMUTH_SPEED_DPS")
    el_speed = RotorState.get_config("ELEVATION_SPEED_DPS")

    az_direction = 0x02 if az_delta > 0 else (0x04 if az_delta < 0 else 0)
    el_direction = 0x08 if el_delta > 0 else (0x10 if el_delta < 0 else 0)

    az_time = abs(az_delta) / az_speed if az_delta else 0
    el_time = abs(el_delta) / el_speed if el_delta else 0
    move_duration = max(az_time, el_time)

    if move_duration == 0:
        return "No movement needed"

    cmd2 = 0x00
    if az_direction:
        cmd2 |= az_direction
    if el_direction:
        cmd2 |= el_direction

    logging.debug(
        "Moving: Δaz=%.1f°, Δel=%.1f°, est. duration=%.2fs",
        az_delta, el_delta, move_duration
    )

    send_pelco_d(0x00, cmd2, 0x20, 0x20)  # fixed speed
    time.sleep(move_duration)
    stop()

    RotorState.set_position(az_target, el_target)
    return f"Moved to az={az_target:.1f}, el={el_target:.1f} over ~{move_duration:.1f}s"


def nudge_elevation(direction, duration):
    """
    Nudge elevation up or down briefly.
    
    Args:
        direction: +1 for up, -1 for down
        duration: time in seconds to hold nudge
    """
    if direction not in (-1, 1):
        return "Invalid direction"

    cmd2 = 0x08 if direction > 0 else 0x10
    send_pelco_d(0x00, cmd2, 0x00, 0x20)
    time.sleep(duration)
    stop()

    az, el = RotorState.get_position()
    el += direction * RotorState.get_config("ELEVATION_SPEED_DPS") * duration
    RotorState.set_position(az, max(-45, min(45, el)))
    return f"Nudged elevation {'up' if direction > 0 else 'down'} for {duration:.1f} seconds"


def set_horizon():
    """Return elevation to 0 degrees, preserving current azimuth."""
    az, _ = RotorState.get_position()
    return send_command(az, 0.0)


def calibrate():
    """
    Calibrate rotor by rotating fully left (mechanical stop),
    then prompt user to manually align to North and level.
    """
    logging.info("Calibration: rotating fully left to find mechanical stop.")
    send_pelco_d(0x00, 0x04, 0x20, 0x00)
    time.sleep(40)
    stop()

    logging.info("Now manually rotate to TRUE NORTH and level elevation.")
    RotorState.set_position(0.0, 0.0)
    return "Calibration complete. Azimuth set to 0, elevation set to 0."


def test_azimuth_speed(duration=10):
    """
    Manual test of azimuth speed. Prompts user to enter result.
    
    Args:
        duration: test duration in seconds
    """
    logging.info("Rotating right for %d seconds. Measure degrees moved.", duration)
    send_pelco_d(0x00, 0x02, 0x20, 0x00)
    time.sleep(duration)
    stop()
    try:
        degrees = float(input("Enter degrees moved: "))
        speed = degrees / duration
        RotorState.set_config("AZIMUTH_SPEED_DPS", speed)
        logging.info("Saved AZIMUTH_SPEED_DPS = %.2f", speed)
    except ValueError:
        logging.error("Invalid input.")


def test_elevation_speed(duration=10):
    """
    Manual test of elevation speed. Prompts user to enter result.

    Args:
        duration: test duration in seconds
    """
    logging.info("Tilting up for %d seconds. Measure degrees moved.", duration)
    send_pelco_d(0x00, 0x08, 0x00, 0x20)
    time.sleep(duration)
    stop()
    try:
        degrees = float(input("Enter degrees moved: "))
        speed = degrees / duration
        RotorState.set_config("ELEVATION_SPEED_DPS", speed)
        logging.info("Saved ELEVATION_SPEED_DPS = %.2f", speed)
    except ValueError:
        logging.error("Invalid input.")


def run_demo_sequence(update_callback=None):
    """
    Execute a predefined movement sequence for demonstration.
    
    If `update_callback` is provided, it's called after each step.
    This allows WebSocket updates to be emitted live.
    """
    steps = [
        (0, 0),
        (90, 30),
        (180, 45),
        (270, 10),
        (0, 0)
    ]
    for az, el in steps:
        msg = send_command(az, el)
        if update_callback:
            update_callback(msg)
    if update_callback:
        update_callback("Demo sequence completed.")
