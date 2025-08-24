"""Control functions for a Pelco-D based rotor system.

Supports:
- Manual and programmatic control
- Estimated motion duration using configured speeds
- Real-time updates via callback injection (dict or str payloads)
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple, Union

import serial

from state import RotorState, DEVICE_ADDRESS

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)

# Callback payload may be a plain string or a dict with fields like:
#   {"msg": "...", "cal_progress": 0.42, "cal_stage": "moving fully down"}
UpdatePayload = Union[str, Dict[str, Any]]
UpdateCallback = Optional[Callable[[UpdatePayload], None]]

_THIS_DIR = os.path.dirname(__file__)
_LIMITS_PATH = os.path.join(_THIS_DIR, "limits.json")

_motion_lock = threading.RLock()
_cancel_event = threading.Event()

__all__ = [
    "init_serial",
    "send_pelco_d",
    "stop",
    "send_command",
    "nudge_elevation",
    "nudge_azimuth",
    "set_azimuth_zero",
    "set_elevation_neutral",
    "calibrate",
    "test_azimuth_speed",
    "test_elevation_speed",
    "run_demo_sequence",
    # helpers that UI/server may use:
    "el_user_to_phys",
    "el_phys_to_user",
]

# --------------------------- Helpers / limits ---------------------------

def _safety() -> float:
    """Return a timing safety factor to trim sleeps and reduce overshoot drift."""
    val = RotorState.get_config("TIME_SAFETY_FACTOR")
    try:
        fval = float(val)
        if 0.90 <= fval <= 1.00:
            return fval
    except (TypeError, ValueError):
        pass
    return 0.985  # default ~1.5% trim


def _load_limits() -> Tuple[float, float, float, float]:
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
    """Clamp v into [lo, hi]."""
    return max(lo, min(hi, v))


def _breakaway_tilt(direction: int) -> None:
    """Give the tilt axis a short, high-speed pulse to overcome stiction.

    The pulse is NOT counted toward progress timing.
    """
    if direction not in (-1, 1):
        return

    near_deg = float(_get_config_with_default("EL_NEAR_STOP_DEG", 8.0))
    kick_up = float(_get_config_with_default("EL_BREAKAWAY_SEC_UP", 0.6))
    kick_dn = float(_get_config_with_default("EL_BREAKAWAY_SEC_DOWN", 0.4))
    kick_spd = int(_get_config_with_default("EL_BREAKAWAY_SPEED_BYTE", 0x3F))

    _, el = RotorState.get_position()
    near_low = el <= (ELEVATION_MIN + near_deg)
    near_high = el >= (ELEVATION_MAX - near_deg)

    sec = 0.0
    if direction > 0 and near_low:
        sec = max(0.0, kick_up)
    elif direction < 0 and near_high:
        sec = max(0.0, kick_dn)

    if sec > 0.0:
        _pelco_move_axes(0, direction, tilt_speed=kick_spd)
        _sleep_with_cancel(sec)
        _stop_motor()


def _effective_el_speed(direction: int) -> float:
    """Return an adjusted elevation speed to account for gravity/drag near stops."""
    base = _get_config_with_default("ELEVATION_SPEED_DPS", 5.0)
    factor_up_near = float(_get_config_with_default("EL_UP_NEAR_STOP_FACTOR", 0.90))
    factor_down_near = float(_get_config_with_default("EL_DOWN_NEAR_STOP_FACTOR", 0.95))
    near_deg = float(_get_config_with_default("EL_NEAR_STOP_DEG", 8.0))

    _, el = RotorState.get_position()
    near_low = el <= (ELEVATION_MIN + near_deg)
    near_high = el >= (ELEVATION_MAX - near_deg)

    if direction > 0 and near_low:
        return base * factor_up_near
    if direction < 0 and near_high:
        return base * factor_down_near
    return base

# --- Elevation reference mapping --------------------------------------------

def _el_mode() -> str:
    """Return configured elevation reference mode."""
    m = RotorState.get_config("EL_REFERENCE")
    return str(m or "VERTICAL").upper()


def el_user_to_phys(el_ui: float) -> float:
    """Map UI elevation to physical elevation."""
    return el_ui + 90.0 if _el_mode() == "HORIZONTAL" else el_ui


def el_phys_to_user(el_phys: float) -> float:
    """Map physical elevation to UI elevation."""
    return el_phys - 90.0 if _el_mode() == "HORIZONTAL" else el_phys


# ------------------------ Serial / Pelco-D primitives ------------------------

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


def _stop_motor() -> None:
    """Send stop frame to motor without setting the cancel flag."""
    try:
        send_pelco_d(0x00, 0x00, 0x00, 0x00)
    except RuntimeError:
        # Serial may not be up yet; ignore
        pass


def stop() -> None:
    """User/emergency STOP: set cancel flag and send stop frame."""
    _cancel_event.set()
    _stop_motor()


def _get_config_with_default(key: str, default: float) -> float:
    """Return config value as float, or provided default."""
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


def _sleep_with_cancel(duration: float) -> float:
    """Sleep up to 'duration' seconds, returning early if stop/cancel is requested.

    Returns the actual seconds slept.
    """
    end = time.time() + max(0.0, duration)
    now = time.time()
    while now < end:
        if _cancel_event.is_set():
            break
        remaining = end - now
        time.sleep(min(0.05, remaining))
        now = time.time()
    return max(0.0, min(duration, now - (end - duration)))


def _pelco_move_axes(
    az_dir: int,
    el_dir: int,
    pan_speed: int = 0x20,
    tilt_speed: int = 0x20,
) -> None:
    """Move only the requested axes via Pelco-D.

    Args:
        az_dir: -1 left, 0 none, +1 right
        el_dir: -1 down, 0 none, +1 up
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
        _stop_motor()
        return

    data1 = pan_speed if az_dir != 0 else 0x00  # pan speed byte
    data2 = tilt_speed if el_dir != 0 else 0x00  # tilt speed byte
    send_pelco_d(0x00, cmd2, data1, data2)


# ------------------------------ High-level motion ------------------------------

def send_command(
    az_target: float,
    el_target: float,
    update_callback: UpdateCallback = None,
) -> str:
    """Move rotor to target az/el with safe axis-staggered timing + stiction handling."""
    with _motion_lock:
        _cancel_event.clear()

        # Requested vs clamped (for UI)
        req_az = float(az_target)
        req_el = float(el_target)
        az_target = _clamp(req_az, AZ_MIN, AZ_MAX)
        el_target = _clamp(req_el, ELEVATION_MIN, ELEVATION_MAX)
        was_clamped = (az_target != req_az) or (el_target != req_el)

        if update_callback:
            update_callback(
                {
                    "busy": True,
                    "req_az": req_az,
                    "req_el": req_el,
                    "clamped": was_clamped,
                }
            )

        # Current state
        az_current, el_current = RotorState.get_position()
        az_delta = az_target - az_current
        el_delta = el_target - el_current
        if az_delta == 0 and el_delta == 0:
            msg = "No movement needed"
            if update_callback:
                update_callback(
                    {
                        "busy": False,
                        "msg": msg,
                        "req_az": req_az,
                        "req_el": req_el,
                        "clamped": was_clamped,
                    }
                )
            return msg

        # Speeds (+ elevation effective speed near stops)
        az_speed = _get_config_with_default("AZIMUTH_SPEED_DPS", 10.0)
        el_dir = 1 if el_delta > 0 else (-1 if el_delta < 0 else 0)
        el_speed_eff = _effective_el_speed(el_dir)
        sf = _safety()

        # Timings (use effective elevation speed)
        az_time = (abs(az_delta) / az_speed) if az_speed > 0 else 0.0
        el_time = (abs(el_delta) / el_speed_eff) if el_speed_eff > 0 else 0.0
        az_time *= sf
        el_time *= sf

        az_dir = 1 if az_delta > 0 else (-1 if az_delta < 0 else 0)

        def progress(
            dt_both: float,
            dt_az_only: float,
            dt_el_only: float,
        ) -> tuple[float, float]:
            """Compute az/el degree progress given elapsed time on each phase."""
            paz = (az_dir * az_speed * dt_both) + (az_dir * az_speed * dt_az_only)
            pel = (el_dir * el_speed_eff * dt_both) + (el_dir * el_speed_eff * dt_el_only)
            return paz, pel

        partial_az = 0.0
        partial_el = 0.0
        return_msg = "Move interrupted"

        try:
            # 1) Elevation breakaway kick if starting near a stop and moving away.
            #    This time is intentionally NOT counted toward progress.
            if el_dir != 0:
                _breakaway_tilt(el_dir)
                if _cancel_event.is_set():
                    _stop_motor()
                    RotorState.set_position(az_current, el_current)
                    if update_callback:
                        update_callback(
                            {
                                "busy": False,
                                "msg": return_msg,
                                "req_az": req_az,
                                "req_el": req_el,
                                "clamped": was_clamped,
                            }
                        )
                    return return_msg

            # 2) Axis-staggered motion
            if az_dir != 0 and el_dir != 0:
                first = min(az_time, el_time)
                _pelco_move_axes(az_dir, el_dir)
                slept = _sleep_with_cancel(first)
                if slept < first or _cancel_event.is_set():
                    daz, delv = progress(slept, 0.0, 0.0)
                    partial_az += daz
                    partial_el += delv
                    # Cancellation path: set cancel flag already => keep as-is
                    _stop_motor()
                else:
                    if az_time > el_time:
                        _pelco_move_axes(az_dir, 0)
                        left = az_time - el_time
                        slept2 = _sleep_with_cancel(left)
                        daz, delv = progress(first, slept2, 0.0)
                    elif el_time > az_time:
                        _pelco_move_axes(0, el_dir)
                        left = el_time - az_time
                        slept2 = _sleep_with_cancel(left)
                        daz, delv = progress(first, 0.0, slept2)
                    else:
                        daz, delv = progress(first, 0.0, 0.0)

                    partial_az += daz
                    partial_el += delv
                    # Normal completion: DO NOT set cancel flag
                    _stop_motor()
                    return_msg = f"Moved to az={az_target:.1f}, el={el_target:.1f}"

            elif az_dir != 0:
                _pelco_move_axes(az_dir, 0)
                slept = _sleep_with_cancel(az_time)
                partial_az += az_dir * az_speed * slept
                _stop_motor()
                if slept >= az_time and not _cancel_event.is_set():
                    return_msg = f"Moved to az={az_target:.1f}, el={el_target:.1f}"

            else:
                _pelco_move_axes(0, el_dir)
                slept = _sleep_with_cancel(el_time)
                partial_el += el_dir * el_speed_eff * slept
                _stop_motor()
                if slept >= el_time and not _cancel_event.is_set():
                    return_msg = f"Moved to az={az_target:.1f}, el={el_target:.1f}"

            # 3) Optional approach normalization to hit EL=90° consistently
            if not _cancel_event.is_set() and abs(el_target - 90.0) < 0.05:
                overshoot = float(_get_config_with_default("EL_APPROACH_OVERSHOOT_DEG", 0.0))
                if overshoot > 0:
                    # approach from above: go up a tad, then down to 90
                    _pelco_move_axes(0, +1)
                    _sleep_with_cancel((overshoot / max(el_speed_eff, 1e-6)) * sf)
                    _stop_motor()
                    _pelco_move_axes(0, -1)
                    _sleep_with_cancel((overshoot / max(el_speed_eff, 1e-6)) * sf)
                    _stop_motor()

            # 4) Optional extra overdrive at AZ=0 to firmly hit the mechanical zero
            if not _cancel_event.is_set() and az_target == 0.0:
                over = _get_config_with_default("ZERO_OVERDRIVE_SEC", 0.0)
                if over > 0:
                    _pelco_move_axes(-1, 0)
                    _sleep_with_cancel(over)
                    _stop_motor()

        finally:
            # Final position: partials if canceled, else exact targets
            final_az = _clamp(az_current + partial_az, AZ_MIN, AZ_MAX)
            final_el = _clamp(el_current + partial_el, ELEVATION_MIN, ELEVATION_MAX)
            if not _cancel_event.is_set():
                final_az, final_el = az_target, el_target
            RotorState.set_position(final_az, final_el)
            if update_callback:
                update_callback(
                    {
                        "busy": False,
                        "msg": return_msg,
                        "req_az": req_az,
                        "req_el": req_el,
                        "clamped": was_clamped,
                    }
                )

        return return_msg


def nudge_elevation(
    direction: int,
    duration: float,
    update_callback: UpdateCallback = None,
) -> str:
    """Briefly nudge elevation up (+1) or down (-1) for a duration in seconds."""
    if direction not in (-1, 1):
        return "Invalid direction"
    with _motion_lock:
        _cancel_event.clear()
        if update_callback:
            update_callback({"busy": True})

        send_pelco_d(0x00, 0x08 if direction > 0 else 0x10, 0x00, 0x20)
        slept = _sleep_with_cancel(duration)
        _stop_motor()

        az, el = RotorState.get_position()
        el_speed = _get_config_with_default("ELEVATION_SPEED_DPS", 5.0)
        moved = direction * el_speed * slept
        new_el = _clamp(el + moved, ELEVATION_MIN, ELEVATION_MAX)
        RotorState.set_position(az, new_el)

        msg = f"Nudged elevation {'up' if direction > 0 else 'down'} for {slept:.2f}s"
        if update_callback:
            update_callback({"busy": False, "msg": msg})
        return msg


def nudge_azimuth(
    direction: int,
    duration: float,
    update_callback: UpdateCallback = None,
) -> str:
    """Briefly nudge azimuth right (+1) or left (-1) for a duration in seconds."""
    if direction not in (-1, 1):
        return "Invalid direction"
    with _motion_lock:
        _cancel_event.clear()
        if update_callback:
            update_callback({"busy": True})

        send_pelco_d(0x00, 0x02 if direction > 0 else 0x04, 0x20, 0x00)
        slept = _sleep_with_cancel(duration)
        _stop_motor()

        az, el = RotorState.get_position()
        az_speed = _get_config_with_default("AZIMUTH_SPEED_DPS", 10.0)
        moved = direction * az_speed * slept
        new_az = _clamp(az + moved, AZ_MIN, AZ_MAX)
        RotorState.set_position(new_az, el)

        msg = f"Nudged azimuth {'right' if direction > 0 else 'left'} for {slept:.2f}s"
        if update_callback:
            update_callback({"busy": False, "msg": msg})
        return msg


def set_azimuth_zero(update_callback: UpdateCallback = None) -> str:
    """Return azimuth to 0 degrees, keeping current elevation."""
    _, el = RotorState.get_position()
    return send_command(0.0, el, update_callback=update_callback)


def set_elevation_neutral(update_callback: UpdateCallback = None) -> str:
    """Go to UI neutral elevation: 90° in VERTICAL mode, 0° in HORIZONTAL mode."""
    az, _ = RotorState.get_position()
    ui_neutral = 0.0 if _el_mode() == "HORIZONTAL" else 90.0
    return send_command(az, ui_neutral, update_callback=update_callback)


# ------------------------- Calibration & tests (ticked) -------------------------

def calibrate(update_callback: UpdateCallback = None) -> str:
    """Calibrate both azimuth and elevation with live progress updates.

    Stages:
      1) Tilt fully down
      2) Tilt up by configured degrees
      3) Rotate azimuth fully left

    Progress fields (dict payload via update_callback):
      - cal_progress: float in [0..1]
      - cal_stage:    str label for current stage
    """
    with _motion_lock:
        _cancel_event.clear()
        if update_callback:
            update_callback(
                {
                    "busy": True,
                    "msg": "Calibrating: start",
                    "cal_progress": 0.0,
                    "cal_stage": "starting",
                }
            )

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
            """Sleep in small chunks, emit progress ticks, and honor STOP/cancel.

            Returns actual seconds slept for this stage.
            """
            remaining = max(0.0, float(duration))
            slept_total = 0.0
            _emit_progress(stage, elapsed_so_far, total)  # immediate tick
            while remaining > 0 and not _cancel_event.is_set():
                step = min(interval, remaining)
                actually_slept = _sleep_with_cancel(step)
                slept_total += actually_slept
                remaining -= actually_slept
                _emit_progress(stage, elapsed_so_far + slept_total, total)
                if actually_slept <= 0:
                    break
            return slept_total

        # Load timing/config values
        down_time = _get_config_with_default("CALIBRATE_DOWN_DURATION_SEC", 10)
        up_degrees = _get_config_with_default("CALIBRATE_UP_TRAVEL_DEGREES", 90)
        el_speed = _get_config_with_default("ELEVATION_SPEED_DPS", 5.0)
        az_time = _get_config_with_default("CALIBRATE_AZ_LEFT_DURATION_SEC", 40)

        up_secs = float(up_degrees) / el_speed if el_speed and el_speed > 0 else 0.0
        total_secs = (
            max(0.0, float(down_time))
            + max(0.0, up_secs)
            + max(0.0, float(az_time))
        )
        elapsed = 0.0

        logging.info(
            "Starting calibration: down=%.1fs, up=%sdeg(%.1fs), az_left=%.1fs",
            down_time,
            up_degrees,
            up_secs,
            az_time,
        )

        canceled = False

        # 1) Elevation down
        _pelco_move_axes(0, -1)
        slept = _sleep_with_ticks(
            down_time,
            "moving fully down",
            elapsed,
            total_secs,
        )
        elapsed += slept
        _stop_motor()
        if _cancel_event.is_set():
            canceled = True

        # 2) Elevation up
        if not canceled:
            _pelco_move_axes(0, +1)
            slept = _sleep_with_ticks(
                up_secs,
                f"tilting up ~{up_degrees}°",
                elapsed,
                total_secs,
            )
            elapsed += slept
            _stop_motor()
            if _cancel_event.is_set():
                canceled = True

        # 3) Azimuth left
        if not canceled:
            _pelco_move_axes(-1, 0)
            slept = _sleep_with_ticks(
                az_time,
                "rotating azimuth fully left",
                elapsed,
                total_secs,
            )
            elapsed += slept
            _stop_motor()
            if _cancel_event.is_set():
                canceled = True

        if canceled:
            msg = "Calibration canceled."
            if update_callback:
                update_callback(
                    {
                        "busy": False,
                        "msg": msg,
                        "cal_stage": "canceled",
                        "cal_progress": max(
                            0.0,
                            min(1.0, elapsed / total_secs if total_secs else 0.0),
                        ),
                    }
                )
            return msg

        # Finalize position at neutral/zenith
        RotorState.set_position(0.0, 90.0)

        # Emit final 100% + human message so UI force-syncs and can close the modal
        final_msg = (
            "✓ Calibration complete. Azimuth set to 0°, Elevation set to 90°."
        )
        if update_callback:
            update_callback(
                {
                    "busy": False,
                    "msg": final_msg,
                    "cal_stage": "complete",
                    "cal_progress": 1.0,
                }
            )
        return final_msg


def test_azimuth_speed(duration: int = 10) -> None:
    """Test azimuth speed by rotating right and measuring degrees."""
    logging.info("Rotating right for %d seconds. Measure degrees moved.", duration)
    send_pelco_d(0x00, 0x02, 0x20, 0x00)
    time.sleep(duration)
    _stop_motor()
    try:
        degrees = float(input("Enter degrees moved: "))
    except ValueError:
        logging.error("Invalid input.")
        return
    RotorState.set_config("AZIMUTH_SPEED_DPS", degrees / duration)
    logging.info("Saved AZIMUTH_SPEED_DPS = %.2f", degrees / duration)


def test_elevation_speed(duration: int = 10) -> None:
    """Test elevation speed by tilting up and measuring degrees."""
    logging.info("Tilting up for %d seconds. Measure degrees moved.", duration)
    send_pelco_d(0x00, 0x08, 0x00, 0x20)
    time.sleep(duration)
    _stop_motor()
    try:
        degrees = float(input("Enter degrees moved: "))
    except ValueError:
        logging.error("Invalid input.")
        return
    RotorState.set_config("ELEVATION_SPEED_DPS", degrees / duration)
    logging.info("Saved ELEVATION_SPEED_DPS = %.2f", degrees / duration)


def run_demo_sequence(update_callback: UpdateCallback = None) -> None:
    """Run a fixed set of positions to demo rotor movement (cancel-aware)."""
    with _motion_lock:
        _cancel_event.clear()
        if update_callback:
            update_callback({"busy": True, "msg": "Demo start"})

        steps = [(0, 90), (80, 60), (180, 45), (270, 135), (0, 90)]
        for az, el in steps:
            if _cancel_event.is_set():
                break
            send_command(az, el, update_callback=update_callback)
            _sleep_with_cancel(0.25)  # small settle between steps

        # Final ensure to neutral
        send_command(0, 90, update_callback=update_callback)

        if update_callback:
            update_callback({"busy": False, "msg": "Demo sequence completed."})
