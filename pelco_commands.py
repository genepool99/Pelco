"""
Control functions for a Pelco-D based rotor system.
Includes time-aware motion estimation and calibration support.
"""

import time
import serial

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


def init_serial(port, baudrate):
    ser = serial.Serial(port=port, baudrate=baudrate, timeout=1)
    set_serial_port(ser)


def send_pelco_d(cmd1, cmd2, data1, data2=0x00):
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
        print(f"[DEBUG] Sent PELCO-D: {[hex(b) for b in msg]}")
        time.sleep(0.05)


def stop():
    send_pelco_d(0x00, 0x00, 0x00, 0x00)


def send_command(az_target, el_target):
    az_current, el_current = get_position()
    az_delta = az_target - az_current
    el_delta = el_target - el_current

    az_speed = get_config("AZIMUTH_SPEED_DPS")
    el_speed = get_config("ELEVATION_SPEED_DPS")

    az_direction = 0x02 if az_delta > 0 else (0x04 if az_delta < 0 else 0)
    el_direction = 0x08 if el_delta > 0 else (0x10 if el_delta < 0 else 0)

    az_time = abs(az_delta) / az_speed if az_delta != 0 else 0
    el_time = abs(el_delta) / el_speed if el_delta != 0 else 0
    move_duration = max(az_time, el_time)

    if move_duration == 0:
        return "No movement needed"

    cmd2 = 0x00
    if az_direction:
        cmd2 |= az_direction
    if el_direction:
        cmd2 |= el_direction

    print(f"[DEBUG] Moving: Δaz={az_delta:.1f}°, Δel={el_delta:.1f}°, est. duration={move_duration:.2f}s")
    send_pelco_d(0x00, cmd2, 0x20, 0x20)
    time.sleep(move_duration)
    stop()
    set_position(az_target, el_target)
    return f"Moved to az={az_target:.1f}, el={el_target:.1f} over ~{move_duration:.1f}s"

def nudge_elevation(direction, duration):
    """Adjust elevation briefly in a direction (+1 for up, -1 for down) for a fixed duration."""
    if direction not in (-1, 1):
        return "Invalid direction"

    cmd2 = 0x08 if direction > 0 else 0x10  # Up or Down
    send_pelco_d(0x00, cmd2, 0x00, 0x20)
    time.sleep(duration)
    stop()

    az, el = get_position()
    el += direction * get_config("ELEVATION_SPEED_DPS") * duration
    set_position(az, max(-45, min(45, el)))
    return f"Nudged elevation {'up' if direction > 0 else 'down'} for {duration:.1f} seconds"

def set_horizon():
    """Move the elevation to 0 while maintaining azimuth."""
    az, _ = get_position()
    return send_command(az, 0.0)

def calibrate():
    print("[INFO] Calibration starting: rotating fully left to find mechanical stop.")
    send_pelco_d(0x00, 0x04, 0x20, 0x00)
    time.sleep(40)
    stop()
    print("[INFO] Now manually rotate to TRUE NORTH and level elevation.")
    set_position(0.0, 0.0)
    return "Calibration complete. Azimuth set to 0, elevation set to 0."


def test_azimuth_speed(duration=10):
    print(f"[INFO] Rotating right for {duration} seconds. Measure how many degrees it moved.")
    send_pelco_d(0x00, 0x02, 0x20, 0x00)
    time.sleep(duration)
    stop()
    try:
        degrees = float(input("Enter degrees moved: "))
        speed = degrees / duration
        set_config("AZIMUTH_SPEED_DPS", speed)
        print(f"[RESULT] Saved AZIMUTH_SPEED_DPS = {speed:.2f}")
    except ValueError:
        print("[ERROR] Invalid input.")


def test_elevation_speed(duration=10):
    print(f"[INFO] Tilting up for {duration} seconds. Measure how many degrees it moved.")
    send_pelco_d(0x00, 0x08, 0x00, 0x20)
    time.sleep(duration)
    stop()
    try:
        degrees = float(input("Enter degrees moved: "))
        speed = degrees / duration
        set_config("ELEVATION_SPEED_DPS", speed)
        print(f"[RESULT] Saved ELEVATION_SPEED_DPS = {speed:.2f}")
    except ValueError:
        print("[ERROR] Invalid input.")


def timed_move(cmd2, duration=4):
    send_pelco_d(0x00, cmd2, 0x20, 0x20)
    time.sleep(duration)
    stop()


def run_demo_sequence():
    timed_move(0x02, 0.5)  # Right
    timed_move(0x04, 0.5)  # Left
    timed_move(0x02, 0.3)
    timed_move(0x04, 0.3)
    timed_move(0x08, 0.3)  # Up
    timed_move(0x10, 0.3)  # Down
    return "Fast visible demo complete"