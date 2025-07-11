import serial
import time
import threading

from state import (
    lock,
    DEVICE_ADDRESS,
    get_position,
    set_position,
    AZ_MIN,
    AZ_MAX,
    EL_MIN,
    EL_MAX,
)

# Global serial instance
ser = None

def init_serial(port, baudrate):
    global ser
    ser = serial.Serial(port=port, baudrate=baudrate, timeout=1)
    print(f"[DEBUG] Serial initialized on {port} at {baudrate} bps")

def send_pelco_d(cmd1, cmd2, data1, data2=0x00):
    global ser
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
    print("[DEBUG] Sending stop command")
    send_pelco_d(0x00, 0x00, 0x00, 0x00)

def nudge_elevation(direction, duration=0.2):
    if direction not in (-1, 1):
        return "Invalid direction"

    cmd1 = 0x00
    cmd2 = 0x08 if direction > 0 else 0x10

    print(f"[DEBUG] Sending nudge: direction={direction}, duration={duration}s")
    send_pelco_d(cmd1, cmd2, 0x20, 0x20)
    time.sleep(duration)
    stop()

    az, el = get_position()
    step = direction * (duration * 10)  # adjustable scaling factor
    new_el = max(EL_MIN, min(EL_MAX, el + step))
    print(f"[DEBUG] Nudged elevation from {el} to {new_el} (step={step})")
    set_position(az, new_el)
    return f"Nudged elevation to {new_el}" 

def set_horizon():
    az, _ = get_position()
    print("[DEBUG] Setting elevation to horizon (0 degrees)")
    set_position(az, 0)
    return send_command(az, 0)

def send_command(az, el, duration=0):
    az = max(AZ_MIN, min(AZ_MAX, int(az)))
    el = max(EL_MIN, min(EL_MAX, int(el)))

    pan_speed = 0x20
    tilt_speed = 0x20

    cmd1 = 0x00
    cmd2 = 0x00

    current_az, current_el = get_position()

    print(f"[DEBUG] Moving from az={current_az}, el={current_el} to az={az}, el={el}")

    if az > current_az:
        cmd2 |= 0x02  # Right
    elif az < current_az:
        cmd2 |= 0x04  # Left

    if el > current_el:
        cmd2 |= 0x08  # Up
    elif el < current_el:
        cmd2 |= 0x10  # Down

    send_pelco_d(cmd1, cmd2, pan_speed, tilt_speed)
    if duration > 0:
        time.sleep(duration)
        stop()

    set_position(az, el)
    return f"Command sent to move to az={az}, el={el}"

def calibrate():
    print("[DEBUG] Calibrating to az=0, el=0")
    set_position(0, 0)
    return "Calibrated to 0,0"

def run_demo_sequence():
    steps = [(0, 0), (90, 0), (180, 0), (270, 0), (0, 45), (0, -45), (0, 0)]
    print("[DEBUG] Starting demo sequence")
    for az, el in steps:
        print(f"[DEBUG] Demo step: az={az}, el={el}")
        send_command(az, el)
        time.sleep(1)
    return "Demo sequence complete"