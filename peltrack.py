"""Peltrack: Flask web + EasyComm TCP server for Pelco-D rotor control.

Features:
- Web UI for manual control and calibration
- Real-time position/status via Socket.IO
- EasyComm-compatible TCP server for Gpredict/Hamlib
"""

# pylint: disable=wrong-import-position
from __future__ import annotations

import argparse
import logging
import threading
import json

import eventlet
eventlet.monkey_patch()

from flask import Flask, request
from flask_socketio import SocketIO

from state import (
    get_position,
    set_position,
    get_config,
    set_last_request,
    get_last_request,
)
from pelco_commands import (
    calibrate,
    run_demo_sequence,
    send_command,
    nudge_elevation,
    set_elevation_neutral,
    stop,
    init_serial,
    nudge_azimuth,
    set_azimuth_zero,
)
from easycomm_server import EasyCommServerManager
from page_template import HTML_PAGE

# ---------------------------------------------------------------------------
# Limits (from optional limits.json) — values are in *physical* degrees
# ---------------------------------------------------------------------------
LIMITS_FILE = "limits.json"
DEFAULT_LIMITS = {"az_min": 0.0, "az_max": 360.0, "el_min": 45.0, "el_max": 135.0}
try:
    with open(LIMITS_FILE, "r", encoding="utf-8") as f:
        LIMITS = json.load(f)
except (OSError, ValueError):
    logging.warning("Using default limits; failed to load limits.json")
    LIMITS = DEFAULT_LIMITS.copy()

# ---------------------------------------------------------------------------
# Flask + Socket.IO
# ---------------------------------------------------------------------------
app = Flask(__name__)
socketio = SocketIO(app, async_mode="eventlet")

# ---------------------------------------------------------------------------
# Elevation reference helpers
#   VERTICAL   : neutral at 90° (default Pelco-like)
#   HORIZONTAL : neutral at 0° (for antennas laid across the base)
# These helpers exist for future UI evolutions; the current UI primarily
# displays/animates physical elevation. Leave conversions minimal for now.
# ---------------------------------------------------------------------------
def _el_mode() -> str:
    """Return elevation reference mode ('VERTICAL' or 'HORIZONTAL')."""
    m = get_config("EL_REFERENCE")
    return str(m or "VERTICAL").upper()

def _phys_to_ui_el(el_phys: float) -> float:
    """Convert physical elevation degrees to UI reference, if needed."""
    return el_phys - 90.0 if _el_mode() == "HORIZONTAL" else el_phys

def _ui_to_phys_el(el_ui: float) -> float:
    """Convert UI elevation degrees to physical elevation, if needed."""
    return el_ui + 90.0 if _el_mode() == "HORIZONTAL" else el_ui

def _current_config_dict():
    """Collect current config values to inject into the UI template."""
    keys = [
        "AZIMUTH_SPEED_DPS",
        "ELEVATION_SPEED_DPS",
        "CALIBRATE_DOWN_DURATION_SEC",
        "CALIBRATE_UP_TRAVEL_DEGREES",
        "CALIBRATE_AZ_LEFT_DURATION_SEC",
        "TIME_SAFETY_FACTOR",
        "REZERO_EXTRA_SECS",
        "ZERO_OVERDRIVE_SEC",
        "EL_NEAR_STOP_DEG",
        "EL_BREAKAWAY_SEC_UP",
        "EL_BREAKAWAY_SEC_DOWN",
        "EL_BREAKAWAY_SPEED_BYTE",
        "EL_UP_NEAR_STOP_FACTOR",
        "EL_DOWN_NEAR_STOP_FACTOR",
        "EL_APPROACH_OVERSHOOT_DEG",
        "EL_REFERENCE",
    ]
    return {k: get_config(k) for k in keys}

# ---------------------------------------------------------------------------
# Socket emitter
# ---------------------------------------------------------------------------
def socketio_emit_position(msg=None) -> None:
    """Emit current position and status to all clients.

    Payload fields:
      - az, el: current *physical* az/el (floats)
      - el_ui : elevation in UI reference (for future UI use)
      - msg   : optional status message (string)
      - req_az, req_el, clamped: last request + whether it was clamped
    """
    az_phys, el_phys = get_position()
    payload = {
        "az": az_phys,
        "el": el_phys,                 # keep physical for current UI widgets
        "el_ui": _phys_to_ui_el(el_phys),
    }

    # Attach message (string or dict merges)
    if isinstance(msg, dict):
        payload.update(msg)
    elif isinstance(msg, str) and msg:
        payload["msg"] = msg

    # Include last-request info so UI can display “Req AZ/EL” and a clamp badge
    req_az, req_el, clamped = get_last_request()
    if req_az is not None:
        payload["req_az"] = float(req_az)
    if req_el is not None:
        payload["req_el"] = float(req_el)
    payload["clamped"] = bool(clamped)

    socketio.emit("position", payload)

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def index():
    """Render the control web interface with current rotor state and config."""
    az, el = get_position()
    az_speed = get_config("AZIMUTH_SPEED_DPS")
    el_speed = get_config("ELEVATION_SPEED_DPS")

    html = HTML_PAGE
    # Inject current (physical) positions for initial render; UI will live-update via socket.
    html = html.replace("{{az}}", f"{az:.1f}")
    html = html.replace("{{el}}", f"{el:.1f}")
    html = html.replace("{{msg}}", "")
    html = html.replace("{{caz}}", f"{az:.1f}")
    html = html.replace("{{cel}}", f"{el:.1f}")
    html = html.replace("{{az_speed}}", f"{float(az_speed):.1f}")
    html = html.replace("{{el_speed}}", f"{float(el_speed):.1f}")
    html = html.replace("{{az_min}}", f"{LIMITS['az_min']}")
    html = html.replace("{{az_max}}", f"{LIMITS['az_max']}")
    html = html.replace("{{el_min}}", f"{LIMITS['el_min']}")
    html = html.replace("{{el_max}}", f"{LIMITS['el_max']}")
    html = html.replace("{{el_ref}}", str(get_config("EL_REFERENCE") or "VERTICAL"))
    html = html.replace("{{config_json}}", json.dumps(_current_config_dict()))
    return html


@app.route("/", methods=["POST"])
def control():
    """Handle control form POST requests from the web UI."""
    action = request.form.get("action", "").strip().lower()
    try:
        if action == "calibrate":
            # Run calibration in a background thread so the HTTP request returns immediately.
            threading.Thread(
                target=calibrate,
                kwargs={"update_callback": socketio_emit_position},
                daemon=True,
            ).start()
            msg = "Calibration started…"

        elif action == "reset":
            set_position(0.0, 90.0)
            msg = "Position reset to 0° azimuth and 90° elevation (zenith)."

        elif action == "demo":
            threading.Thread(
                target=run_demo_sequence,
                kwargs={"update_callback": socketio_emit_position},
                daemon=True,
            ).start()
            msg = "Demo started…"

        elif action == "set":
            # Read requested (form) angles — currently in physical degrees for this UI.
            req_az = float(request.form.get("azimuth"))
            req_el = float(request.form.get("elevation"))

            # Clamp to limits (limits are physical)
            az = max(LIMITS["az_min"], min(LIMITS["az_max"], req_az))
            el = max(LIMITS["el_min"], min(LIMITS["el_max"], req_el))

            # Record original request + whether clamped (for UI display)
            set_last_request(req_az, req_el, clamped=((az != req_az) or (el != req_el)))

            msg = send_command(az, el, update_callback=socketio_emit_position)

        # Elevation nudges
        elif action == "nudge_up":
            msg = nudge_elevation(1, 1.0, update_callback=socketio_emit_position)
        elif action == "nudge_down":
            msg = nudge_elevation(-1, 1.0, update_callback=socketio_emit_position)
        elif action == "nudge_up_big":
            msg = nudge_elevation(1, 2.0, update_callback=socketio_emit_position)
        elif action == "nudge_down_big":
            msg = nudge_elevation(-1, 2.0, update_callback=socketio_emit_position)

        # Azimuth helpers
        elif action == "az_zero":
            msg = set_azimuth_zero(update_callback=socketio_emit_position)
        elif action == "nudge_left":
            msg = nudge_azimuth(-1, 1.0, update_callback=socketio_emit_position)
        elif action == "nudge_right":
            msg = nudge_azimuth(1, 1.0, update_callback=socketio_emit_position)
        elif action == "nudge_left_big":
            msg = nudge_azimuth(-1, 2.0, update_callback=socketio_emit_position)
        elif action == "nudge_right_big":
            msg = nudge_azimuth(1, 2.0, update_callback=socketio_emit_position)

        elif action == "horizon":
            msg = set_elevation_neutral(update_callback=socketio_emit_position)

        elif action == "stop":
            stop()
            msg = "Rotor stopped."

        else:
            msg = f"Unknown command: {action!r}"

    except (ValueError, RuntimeError) as e:
        msg = f"Error: {e}"

    # Always push a live update over the socket
    socketio_emit_position(msg)

    # Re-render page so inputs reflect current position (initial render only; sockets take over)
    az, el = get_position()
    az_speed = get_config("AZIMUTH_SPEED_DPS")
    el_speed = get_config("ELEVATION_SPEED_DPS")
    html = HTML_PAGE
    html = html.replace("{{az}}", f"{az:.1f}")
    html = html.replace("{{el}}", f"{el:.1f}")
    html = html.replace("{{msg}}", msg)
    html = html.replace("{{caz}}", f"{az:.1f}")
    html = html.replace("{{cel}}", f"{el:.1f}")
    html = html.replace("{{az_speed}}", f"{float(az_speed):.1f}")
    html = html.replace("{{el_speed}}", f"{float(el_speed):.1f}")
    html = html.replace("{{az_min}}", f"{LIMITS['az_min']}")
    html = html.replace("{{az_max}}", f"{LIMITS['az_max']}")
    html = html.replace("{{el_min}}", f"{LIMITS['el_min']}")
    html = html.replace("{{el_max}}", f"{LIMITS['el_max']}")
    html = html.replace("{{el_ref}}", str(get_config("EL_REFERENCE") or "VERTICAL"))
    html = html.replace("{{config_json}}", json.dumps(_current_config_dict()))
    return html

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    """Entry point for the Peltrack application."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    parser = argparse.ArgumentParser(description="Pelco-D Rotor Controller")
    parser.add_argument("--port", required=True, help="Serial port (e.g., COM4 or /dev/ttyUSB0)")
    parser.add_argument("--baud", type=int, default=2400, help="Baud rate (default: 2400)")
    args = parser.parse_args()

    # Serial and servers
    init_serial(args.port, args.baud)

    EasyCommServerManager.start(update_callback=socketio_emit_position)
    server = EasyCommServerManager.get_instance()

    logging.info("Starting web server at http://localhost:5000")
    try:
        socketio.run(app, host="0.0.0.0", port=5000)
    except KeyboardInterrupt:
        logging.info("Shutting down Peltrack.")
    finally:
        if server:
            server.stop()


if __name__ == "__main__":
    main()
