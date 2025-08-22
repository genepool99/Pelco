"""Control functions for a Pelco-D based rotor system.

Supports:
- Manual and programmatic control
- Estimated motion duration using configured speeds
- Real-time updates via callback injection (dict or str payloads)
"""

from __future__ import annotations

import time
import os
import json
import logging
from typing import Optional, Callable, Union, Dict, Any

import serial

from state import RotorState, DEVICE_ADDRESS

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)

# Callback payload may be a plain string or a dict with fields like
#   { "msg": "...", "cal_progress": 0.42, "cal_stage": "moving fully down" }
UpdatePayload = Union[str, Dict[str, Any]]
UpdateCallback = Optional[Callable[[UpdatePayload], None]]

# --------------------------------------------------------------------
# Limits: load from limits.json with sensible fallbacks
# EL geometry: 90° = neutral (straight up), typical range 45–135°
# --------------------------------------------------------------------
_THIS_DIR = os.path.dirname(__file__)
_LIMITS_PATH = os.path.join(_THIS_DIR, "limits.json")


def _load_limits() -> tuple[float, float, float, float]:
    """Load az/el limits from limits.json with safe defaults."""
    az_min, az_max = 0.0, 360.0
    el_min, el_max = 45.0, 135.0
    try:
        with open(_LIMITS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError as err:
        logging.info(
            "limits.json not found (%s); using defaults AZ[0,360], EL[45,135].",
            err,
        )
        return az_min, az_max, el_min, el_max
    except (json.JSONDecodeError, OSError) as err:
        logging.warning("Failed to read/parse limits.json (%s); using defaults.", err)
        return az_min, az_max, el_min, el_max

    return (
        float(data.get("az_min", az_min)),
        float(data.get("az_max", az_max)),
        float(data.get("el_min", el_min)),
        float(data.get("el_max", el_max)),
    )


AZ_MIN, AZ_MAX, ELEVATION_MIN, ELEVATION_MAX = _load_limits()


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _wrap_az(az: float) -> float:
    """Wrap azimuth to [0, 360) then clamp to configured AZ range."""
    wrapped = az % 360.0
    return _clamp(wrapped, AZ_MIN, AZ_MAX)

def _pelco_move_axes(az_dir: int, el_dir: int,
                     pan_speed: int = 0x20, tilt_speed: int = 0x20) -> None:
    """
    Issue a Pelco-D frame that moves only the axes requested.
      az_dir: -1 left, 0 none, +1 right
      el_dir: -1 down, 0 none, +1 up
    Speeds are only applied to the axes that are moving; the other axis gets 0.
    """
    cmd2 = 0
    if az_dir > 0:
        cmd2 |= 0x02  # right
    elif az_dir < 0:
        cmd2 |= 0x04  # left
    if el_dir > 0:
        cmd2 |= 0x08  # up
    elif el_dir < 0:
        cmd2 |= 0x10  # down

    if cmd2 == 0:
        stop()
        return

    data1 = pan_speed if az_dir != 0 else 0x00  # pan speed byte
    data2 = tilt_speed if el_dir != 0 else 0x00  # tilt speed byte
    send_pelco_d(0x00, cmd2, data1, data2)


# --------------------------------------------------------------------
# Serial / Pelco-D primitives
# --------------------------------------------------------------------
def init_serial(port: str, baudrate: int) -> None:
    """Open a serial connection to the Pelco-D device."""
    ser = serial.Serial(port=port, baudrate=baudrate, timeout=1)
    RotorState.set_serial_port(ser)


def send_pelco_d(cmd1: int, cmd2: int, data1: int, data2: int = 0x00) -> None:
    """Send a Pelco-D command frame over serial."""
    ser = RotorState.get_serial_port()
    if not ser:
        raise RuntimeError("Serial port not initialized")

    with RotorState.lock:
        msg = bytearray(
            [
                0xFF,
                DEVICE_ADDRESS,
                cmd1,
                cmd2,
                data1,
                data2,
                (DEVICE_ADDRESS + cmd1 + cmd2 + data1 + data2) % 256,
            ]
        )
        ser.write(msg)
        logging.debug("Sent PELCO-D: %s", [hex(b) for b in msg])
        time.sleep(0.05)


def stop() -> None:
    """Immediately halt all rotor motion."""
    send_pelco_d(0x00, 0x00, 0x00, 0x00)


def _get_config_with_default(key: str, default: float) -> float:
    value = RotorState.get_config(key)
    if value is None:
        logging.warning("Config '%s' not set. Using default: %s", key, default)
        return default
    return float(value)


def _calculate_motion_time(delta: float, speed: float) -> float:
    """Return seconds needed to move `delta` degrees at `speed` deg/s."""
    if not speed or speed <= 0:
        return 0.0
    return abs(delta) / speed if delta else 0.0


# --------------------------------------------------------------------
# High-level motion
# --------------------------------------------------------------------
def send_command(az_target: float, el_target: float,
                 update_callback: UpdateCallback = None) -> str:
    """
    Move rotor to target azimuth/elevation with axis-safe timing:
    - Start both axes if both need motion.
    - After the shorter axis finishes, continue only the longer axis.
    - Stop, then set final position.
    """
    az_target = _clamp(float(az_target), AZ_MIN, AZ_MAX)
    el_target = _clamp(float(el_target), ELEVATION_MIN, ELEVATION_MAX)

    az_current, el_current = RotorState.get_position()
    az_delta = az_target - az_current
    el_delta = el_target - el_current
    if az_delta == 0 and el_delta == 0:
        msg = "No movement needed"
        if update_callback:
            update_callback(msg)
        return msg

    az_speed = _get_config_with_default("AZIMUTH_SPEED_DPS", 10.0)
    el_speed = _get_config_with_default("ELEVATION_SPEED_DPS", 5.0)

    az_time = _calculate_motion_time(az_delta, az_speed)
    el_time = _calculate_motion_time(el_delta, el_speed)

    # Direction flags
    az_dir = 1 if az_delta > 0 else (-1 if az_delta < 0 else 0)
    el_dir = 1 if el_delta > 0 else (-1 if el_delta < 0 else 0)

    # If both axes move, run them together for the shorter time,
    # then continue the longer axis alone.
    try:
        if az_dir != 0 and el_dir != 0:
            # start both
            _pelco_move_axes(az_dir, el_dir)
            first = min(az_time, el_time)
            time.sleep(first)

            # continue only the axis that still has time left
            if az_time > el_time:
                _pelco_move_axes(az_dir, 0)         # pan only
                time.sleep(az_time - el_time)
            elif el_time > az_time:
                _pelco_move_axes(0, el_dir)         # tilt only
                time.sleep(el_time - az_time)

            stop()
        elif az_dir != 0:
            _pelco_move_axes(az_dir, 0)
            time.sleep(az_time)
            stop()
        else:
            _pelco_move_axes(0, el_dir)
            time.sleep(el_time)
            stop()

        # small mechanical settle
        time.sleep(0.05)

    finally:
        # Update in-memory position to the commanded (clamped) target
        RotorState.set_position(az_target, el_target)

    msg = f"Moved to az={az_target:.1f}, el={el_target:.1f}"
    if update_callback:
        update_callback(msg)
    return msg

def nudge_elevation(
    direction: int,
    duration: float,
    update_callback: UpdateCallback = None,
) -> str:
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

    msg = (
        "Nudged elevation "
        f"{'up' if direction > 0 else 'down'} for {duration:.1f} seconds"
    )
    if update_callback:
        update_callback(msg)
    return msg


def nudge_azimuth(
    direction: int,
    duration: float,
    update_callback: UpdateCallback = None,
) -> str:
    """Briefly nudge azimuth right (+1) or left (-1) for a duration in seconds."""
    if direction not in (-1, 1):
        return "Invalid direction"

    # Right = 0x02, Left = 0x04; data1 carries pan speed, data2=0 for pan-only
    cmd2 = 0x02 if direction > 0 else 0x04
    send_pelco_d(0x00, cmd2, 0x20, 0x00)
    time.sleep(duration)
    stop()

    az, el = RotorState.get_position()
    az_speed = _get_config_with_default("AZIMUTH_SPEED_DPS", 10.0)
    delta = direction * az_speed * duration
    new_az = _wrap_az(az + delta)
    RotorState.set_position(new_az, el)

    msg = (
        "Nudged azimuth "
        f"{'right' if direction > 0 else 'left'} for {duration:.1f} seconds"
    )
    if update_callback:
        update_callback(msg)
    return msg


def set_azimuth_zero(update_callback: UpdateCallback = None) -> str:
    """Return azimuth to 0 degrees, keeping current elevation."""
    _, el = RotorState.get_position()
    return send_command(0.0, el, update_callback=update_callback)


def set_horizon(update_callback: UpdateCallback = None) -> str:
    """Return elevation to 90 degrees (neutral/zenith), keeping current azimuth."""
    az, _ = RotorState.get_position()
    return send_command(az, 90.0, update_callback=update_callback)


# --------------------------------------------------------------------
# Calibration & tests (with live progress)
# --------------------------------------------------------------------
def calibrate(update_callback: UpdateCallback = None) -> str:
    """Calibrate both azimuth and elevation with live progress updates.

    Stages:
      1) Tilt fully down
      2) Tilt up by configured degrees
      3) Rotate azimuth fully left

    Progress fields (in dict payloads via update_callback):
      - cal_progress: float in [0..1]
      - cal_stage:    str label for current stage
    """
    def _emit_progress(stage: str, elapsed_s: float, total_s: float) -> None:
        pct = 1.0 if total_s <= 0 else max(0.0, min(1.0, elapsed_s / total_s))
        if update_callback:
            update_callback(
                {
                    "msg": f"Calibrating: {stage}… {int(pct * 100)}%",
                    "cal_stage": stage,
                    "cal_progress": pct,
                }
            )

    def _sleep_with_ticks(
        duration: float,
        stage: str,
        elapsed_so_far: float,
        total: float,
        interval: float = 0.25,
    ) -> float:
        """Sleep in small chunks and emit progress ticks."""
        start = time.time()
        # emit immediately so the bar moves at stage start
        _emit_progress(stage, elapsed_so_far, total)
        while True:
            now = time.time()
            done = now - start
            if done >= duration:
                _emit_progress(stage, elapsed_so_far + duration, total)
                break
            _emit_progress(stage, elapsed_so_far + done, total)
            time.sleep(interval)
        return duration

    # --- Load timing/config values ---
    down_time = _get_config_with_default("CALIBRATE_DOWN_DURATION_SEC", 10)
    up_degrees = _get_config_with_default("CALIBRATE_UP_TRAVEL_DEGREES", 90)
    el_speed = _get_config_with_default("ELEVATION_SPEED_DPS", 5.0)
    az_time = _get_config_with_default("CALIBRATE_AZ_LEFT_DURATION_SEC", 40)

    up_secs = float(up_degrees) / el_speed if el_speed and el_speed > 0 else 0.0
    total_secs = (
        max(0.0, float(down_time)) +
        max(0.0, up_secs) +
        max(0.0, float(az_time))
    )
    elapsed = 0.0

    logging.info(
        "Starting calibration: down=%.1fs, up=%sdeg(%.1fs), az_left=%.1fs",
        down_time,
        up_degrees,
        up_secs,
        az_time,
    )

    # --- 1) Elevation down ---
    send_pelco_d(0x00, 0x10, 0x00, 0x20)  # Down
    elapsed += _sleep_with_ticks(
        max(0.0, float(down_time)),
        "moving fully down",
        elapsed,
        total_secs,
    )
    stop()

    # --- 2) Elevation up ---
    send_pelco_d(0x00, 0x08, 0x00, 0x20)  # Up
    elapsed += _sleep_with_ticks(
        max(0.0, float(up_secs)),
        f"tilting up ~{up_degrees}°",
        elapsed,
        total_secs,
    )
    stop()

    # --- 3) Azimuth left ---
    send_pelco_d(0x00, 0x04, 0x20, 0x00)  # Left
    elapsed += _sleep_with_ticks(
        max(0.0, float(az_time)),
        "rotating azimuth fully left",
        elapsed,
        total_secs,
    )
    stop()

    # Finalize position at neutral/zenith
    RotorState.set_position(0.0, 90.0)

    # Emit final 100% + human message so UI force-syncs and closes
    final_msg = (
        "✓ Calibration complete. "
        "Azimuth set to 0°, Elevation set to 90°."
    )
    if update_callback:
        update_callback({"msg": final_msg, "cal_stage": "complete", "cal_progress": 1.0})
    return final_msg


def test_azimuth_speed(duration: int = 10) -> None:
    """Test azimuth speed by rotating right and measuring degrees."""
    logging.info(
        "Rotating right for %d seconds. Measure degrees moved.",
        duration,
    )
    send_pelco_d(0x00, 0x02, 0x20, 0x00)
    time.sleep(duration)
    stop()
    try:
        degrees = float(input("Enter degrees moved: "))
    except ValueError:
        logging.error("Invalid input.")
        return
    RotorState.set_config("AZIMUTH_SPEED_DPS", degrees / duration)
    logging.info("Saved AZIMUTH_SPEED_DPS = %.2f", degrees / duration)


def test_elevation_speed(duration: int = 10) -> None:
    """Test elevation speed by tilting up and measuring degrees."""
    logging.info(
        "Tilting up for %d seconds. Measure degrees moved.",
        duration,
    )
    send_pelco_d(0x00, 0x08, 0x00, 0x20)
    time.sleep(duration)
    stop()
    try:
        degrees = float(input("Enter degrees moved: "))
    except ValueError:
        logging.error("Invalid input.")
        return
    RotorState.set_config("ELEVATION_SPEED_DPS", degrees / duration)
    logging.info("Saved ELEVATION_SPEED_DPS = %.2f", degrees / duration)


def run_demo_sequence(update_callback: UpdateCallback = None) -> None:
    """Run a fixed set of positions to demo rotor movement, with brief settles."""
    steps = [
        (0,   90),
        (80,  60),
        (180, 45),
        (270, 135),
        (0,   90),
    ]
    for az, el in steps:
        send_command(az, el, update_callback=update_callback)
        time.sleep(0.25)  # brief settle between steps

    # One last ensure at neutral in case of tiny timing drift on some heads
    send_command(0, 90, update_callback=update_callback)

    if update_callback:
        update_callback("Demo sequence completed.")
