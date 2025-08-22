"""Peltrack: A Flask web and TCP server for controlling a Pelco-D rotor.

This module provides a web interface and EasyComm-compatible TCP server
for controlling an antenna rotator using the Pelco-D protocol.

Features:
- Web interface for manual control and calibration
- Real-time rotor position updates via WebSocket
- EasyComm TCP server for integration with Gpredict
"""

# pylint: disable=wrong-import-position
import argparse
import logging
import threading
import json

import eventlet
eventlet.monkey_patch()

from flask_socketio import SocketIO
from flask import Flask, request

from state import get_position, set_position, get_config
from pelco_commands import (
    calibrate,
    run_demo_sequence,
    send_command,
    nudge_elevation,
    set_horizon,
    stop,
    init_serial,
    nudge_azimuth,
    set_azimuth_zero,
)
from easycomm_server import EasyCommServerManager
from page_template import HTML_PAGE

# Load movement limits from limits.json if it exists
LIMITS_FILE = "limits.json"
DEFAULT_LIMITS = {"az_min": 0, "az_max": 360, "el_min": 45, "el_max": 135}
try:
    with open(LIMITS_FILE, "r", encoding="utf-8") as f:
        LIMITS = json.load(f)
except (OSError, ValueError):
    logging.warning("Using default limits; failed to load limits.json")
    LIMITS = DEFAULT_LIMITS.copy()

# Flask app and WebSocket setup
app = Flask(__name__)
socketio = SocketIO(app, async_mode="eventlet")


def socketio_emit_position(msg=None):
    """
    Emit the current rotor position via WebSocket.
    `msg` can be a string or a dict with additional fields (e.g., cal_progress).
    """
    az, el = get_position()
    payload = {"az": az, "el": el}

    if isinstance(msg, dict):
        payload.update(msg)
    elif isinstance(msg, str) and msg:
        payload["msg"] = msg

    socketio.emit("position", payload)


@app.route("/", methods=["GET"])
def index():
    """Render the control web interface with current rotor state and config values."""
    az, el = get_position()
    az_speed = get_config("AZIMUTH_SPEED_DPS")
    el_speed = get_config("ELEVATION_SPEED_DPS")
    html = HTML_PAGE
    html = html.replace("{{az}}", f"{az:.1f}")
    html = html.replace("{{el}}", f"{el:.1f}")
    html = html.replace("{{msg}}", "")
    html = html.replace("{{caz}}", f"{az:.1f}")
    html = html.replace("{{cel}}", f"{el:.1f}")
    html = html.replace("{{az_speed}}", f"{az_speed:.1f}")
    html = html.replace("{{el_speed}}", f"{el_speed:.1f}")
    html = html.replace("{{az_min}}", f"{LIMITS['az_min']}")
    html = html.replace("{{az_max}}", f"{LIMITS['az_max']}")
    html = html.replace("{{el_min}}", f"{LIMITS['el_min']}")
    html = html.replace("{{el_max}}", f"{LIMITS['el_max']}")
    return html


@app.route("/", methods=["POST"])
def control():
    """Handle control form POST requests from the web UI."""
    action = request.form.get("action")
    try:
        if action == "calibrate":
            msg = calibrate(update_callback=socketio_emit_position)

        elif action == "reset":
            set_position(0.0, 90.0)
            msg = "Position reset to 0° azimuth and 90° elevation (zenith)."

        elif action == "demo":
            threading.Thread(
                target=run_demo_sequence,
                kwargs={"update_callback": socketio_emit_position},
                daemon=True,
            ).start()
            msg = "Demo started"

        elif action == "set":
            az = float(request.form.get("azimuth"))
            el = float(request.form.get("elevation"))
            az = min(max(az, LIMITS["az_min"]), LIMITS["az_max"])
            el = min(max(el, LIMITS["el_min"]), LIMITS["el_max"])
            msg = send_command(az, el, update_callback=socketio_emit_position)

        # Elevation nudges (ensure UI updates via callback)
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
            msg = set_horizon(update_callback=socketio_emit_position)

        elif action == "stop":
            stop()
            msg = "Rotor stopped."

        else:
            msg = f"Unknown command: {action}"

    except (ValueError, RuntimeError) as e:
        msg = f"Error: {str(e)}"

    # Always push a live update over the socket
    socketio_emit_position(msg)

    # Re-render page so inputs reflect current position
    az, el = get_position()
    az_speed = get_config("AZIMUTH_SPEED_DPS")
    el_speed = get_config("ELEVATION_SPEED_DPS")
    html = HTML_PAGE
    html = html.replace("{{az}}", f"{az:.1f}")
    html = html.replace("{{el}}", f"{el:.1f}")
    html = html.replace("{{msg}}", msg)
    html = html.replace("{{caz}}", f"{az:.1f}")
    html = html.replace("{{cel}}", f"{el:.1f}")
    html = html.replace("{{az_speed}}", f"{az_speed:.1f}")
    html = html.replace("{{el_speed}}", f"{el_speed:.1f}")
    html = html.replace("{{az_min}}", f"{LIMITS['az_min']}")
    html = html.replace("{{az_max}}", f"{LIMITS['az_max']}")
    html = html.replace("{{el_min}}", f"{LIMITS['el_min']}")
    html = html.replace("{{el_max}}", f"{LIMITS['el_max']}")
    return html


def main():
    """Entry point for the Peltrack application."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )
    parser = argparse.ArgumentParser(description="Pelco-D Rotor Controller")
    parser.add_argument("--port", required=True, help="Serial port (e.g., COM4 or /dev/ttyUSB0)")
    parser.add_argument("--baud", type=int, default=2400, help="Baud rate (default: 2400)")
    args = parser.parse_args()

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
