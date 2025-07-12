"""
Control functions for a Pelco-D based rotor system.
Includes time-aware motion estimation and calibration support.
"""

import time
import serial
import logging

from state import (
    lock,
    DEVICE_ADDRESS,
    get_position,
    set_position,
    get_serial_port,
    set_serial_port,
    get_config,
    set_config
)

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)


def init_serial(port, baudrate):
    """Initialize and open a serial connection."""
    ser = serial.Serial(port=port, baudrate=baudrate, timeout=1)
    set_serial_port(ser)


def send_pelco_d(cmd1, cmd2, data1, data2=0x00):
    """Send a single Pelco-D command frame."""
    ser = get_serial_port()
    if not ser:
        raise RuntimeError("Serial port not initialized")

    with lock:
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
    """Send stop command to rotor."""
    send_pelco_d(0x00, 0x00, 0x00, 0x00)


def send_command(az_target, el_target):
    """
    Move the rotor to a given azimuth and elevation.
    Duration is estimated from configured degrees/second.
    """
    az_current, el_current = get_position()
    az_delta = az_target - az_current
    el_delta = el_target - el_current

    az_speed = get_config("AZIMUTH_SPEED_DPS")
    el_speed = get_config("ELEVATION_SPEED_DPS")

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

    send_pelco_d(0x00, cmd2, 0x20, 0x20)
    time.sleep(move_duration)
    stop()
    set_position(az_target, el_target)
    return f"Moved to az={az_target:.1f}, el={el_target:.1f} over ~{move_duration:.1f}s"


def nudge_elevation(direction, duration):
    """Nudge elevation up or down briefly by one unit of motion."""
    if direction not in (-1, 1):
        return "Invalid direction"

    cmd2 = 0x08 if direction > 0 else 0x10
    send_pelco_d(0x00, cmd2, 0x00, 0x20)
    time.sleep(duration)
    stop()

    az, el = get_position()
    el += direction * get_config("ELEVATION_SPEED_DPS") * duration
    set_position(az, max(-45, min(45, el)))
    return f"Nudged elevation {'up' if direction > 0 else 'down'} for {duration:.1f} seconds"


def set_horizon():
    """Move elevation back to 0 while preserving azimuth."""
    az, _ = get_position()
    return send_command(az, 0.0)


def calibrate():
    """
    Perform calibration by rotating left to mechanical stop,
    then resetting az/el position to 0.
    """
    logging.info("Calibration: rotating fully left to find mechanical stop.")
    send_pelco_d(0x00, 0x04, 0x20, 0x00)
    time.sleep(40)
    stop()
    logging.info("Now manually rotate to TRUE NORTH and level elevation.")
    set_position(0.0, 0.0)
    return "Calibration complete. Azimuth set to 0, elevation set to 0."


def test_azimuth_speed(duration=10):
    """Manually test azimuth speed over a timed interval."""
    logging.info("Rotating right for %d seconds. Measure degrees moved.", duration)
    send_pelco_d(0x00, 0x02, 0x20, 0x00)
    time.sleep(duration)
    stop()
    try:
        degrees = float(input("Enter degrees moved: "))
        speed = degrees / duration
        set_config("AZIMUTH_SPEED_DPS", speed)
        logging.info("Saved AZIMUTH_SPEED_DPS = %.2f", speed)
    except ValueError:
        logging.error("Invalid input.")


def test_elevation_speed(duration=10):
    """Manually test elevation speed over a timed interval."""
    logging.info("Tilting up for %d seconds. Measure degrees moved.", duration)
    send_pelco_d(0x00, 0x08, 0x00, 0x20)
    time.sleep(duration)
    stop()
    try:
        degrees = float(input("Enter degrees moved: "))
        speed = degrees / duration
        set_config("ELEVATION_SPEED_DPS", speed)
        logging.info("Saved ELEVATION_SPEED_DPS = %.2f", speed)
    except ValueError:
        logging.error("Invalid input.")


def run_demo_sequence():
    """
    Run a demo by issuing a series of az/el targets like Gpredict would.
    This simulates actual tracking motion using send_command().
    """
    waypoints = [
        (0.0, 0.0),
        (45.0, 10.0),
        (90.0, 20.0),
        (135.0, 10.0),
        (180.0, 0.0),
        (135.0, -10.0),
        (90.0, -20.0),
        (45.0, -10.0),
        (0.0, 0.0)
    ]

    results = []
    for az, el in waypoints:
        result = send_command(az, el)
        results.append(result)
        time.sleep(0.5)

    return "\n".join(results)
