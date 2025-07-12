# pelco_commands.py
"""
Control functions for a Pelco-D based rotor system.
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
)


def init_serial(port, baudrate):
    """Initialize and store the shared serial connection."""
    ser = serial.Serial(port=port, baudrate=baudrate, timeout=1)
    set_serial_port(ser)


def send_pelco_d(cmd1, cmd2, data1, data2=0x00):
    """Send a PELCO-D command packet."""
    ser = get_serial_port()
    if not ser:
        raise RuntimeError("Serial port not initialized")
    with lock:
        msg = bytearray([
            0xFF,  # sync byte
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
    """Send a stop command to halt all movement."""
    send_pelco_d(0x00, 0x00, 0x00, 0x00)


def send_command(az, el):
    """Send a movement command toward the target azimuth/elevation."""
    az = max(0, min(359, int(az)))
    el = max(-45, min(45, int(el)))

    pan_speed = 0x20
    tilt_speed = 0x20

    cmd1 = 0x00
    cmd2 = 0x00

    if az > 0:
        cmd2 |= 0x02  # Right
    elif az < 0:
        cmd2 |= 0x04  # Left

    if el > 0:
        cmd2 |= 0x08  # Up
    elif el < 0:
        cmd2 |= 0x10  # Down

    print(f"[DEBUG] Moving from az={get_position()[0]}, el={get_position()[1]} to az={az}, el={el}")
    send_pelco_d(cmd1, cmd2, pan_speed, tilt_speed)
    set_position(az, el)
    return f"Command sent to move to az={az}, el={el}"


def nudge_elevation(direction, duration):
    """Adjust elevation briefly in a direction (+1 for up, -1 for down) for a fixed duration."""
    if direction not in (-1, 1):
        return "Invalid direction"

    cmd1 = 0x00
    cmd2 = 0x08 if direction > 0 else 0x10  # Up or Down
    pan_speed = 0x00
    tilt_speed = 0x20

    print(f"[DEBUG] Nudging elevation {'up' if direction > 0 else 'down'} for {duration}s")
    send_pelco_d(cmd1, cmd2, pan_speed, tilt_speed)
    time.sleep(duration)
    stop()
    return f"Nudged elevation {'up' if direction > 0 else 'down'} for {duration} seconds"



def set_horizon():
    """Move the elevation to 0 while maintaining azimuth."""
    az, _ = get_position()
    set_position(az, 0)
    return send_command(az, 0)


def calibrate():
    """
    Automatically calibrate azimuth by rotating fully left to stop,
    then prompt user to manually align to true north and level the elevation.
    Sets internal position to (0, 0).
    """
    print("[INFO] Calibration starting: rotating all the way left to find stop.")
    send_pelco_d(0x00, 0x04, 0x20, 0x00)  # Command: Turn Left at moderate speed
    time.sleep(40)  # Adjust based on your hardware’s full left rotation time
    stop()
    print("[INFO] Please manually rotate to TRUE NORTH (geographic) and level the elevation.")
    set_position(0, 0)
    return "Azimuth stop reached. Device set to az=0, el=0. Please ensure it's pointed true north and leveled."

def timed_move(cmd2, duration=4):
    send_pelco_d(0x00, cmd2, 0x20, 0x20)
    time.sleep(duration)
    stop()

def run_demo_sequence():
    """Fast demo with visible rotor movement."""
    timed_move(0x02, 0.5)  # Right
    timed_move(0x04, 0.5)  # Left
    timed_move(0x02, 0.3)
    timed_move(0x04, 0.3)
    timed_move(0x08, 0.3)  # Up
    timed_move(0x10, 0.3)  # Down
    return "Fast visible demo complete"
