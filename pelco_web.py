"""
Flask-based web interface for controlling a Pelco-D rotor system.
Also starts a TCP server for Gpredict using the EasyComm protocol.
"""

import argparse
import logging
import math
import threading

from flask import Flask, request, render_template_string

from easycomm_server import start_server
from state import get_position, set_position, get_config
from pelco_commands import (
    nudge_elevation,
    set_horizon,
    calibrate,
    init_serial,
    send_command,
    run_demo_sequence,
)
from page_template import PAGE

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

app = Flask(__name__)


@app.route("/", methods=["GET", "POST"])
def web_control():
    """
    Main route for the control interface.
    Handles both GET and POST (form) submissions to update or move the rotor.
    """
    az, el = get_position()
    status = "Ready"

    if request.method == "POST":
        form = request.form
        logger.info("Form submission: %s", dict(form))

        if "reset" in form:
            set_position(0, 0)
            status = "Position reset"

        elif "calibrate" in form:
            logger.info("Starting calibration sequence")
            status = calibrate()

        elif "nudge_up_small" in form:
            status = nudge_elevation(1, duration=0.15)

        elif "nudge_down_small" in form:
            status = nudge_elevation(-1, duration=0.15)

        elif "nudge_up_big" in form:
            status = nudge_elevation(1, duration=1)

        elif "nudge_down_big" in form:
            status = nudge_elevation(-1, duration=1)

        elif "set_horizon" in form:
            status = set_horizon()

        elif "run_demo" in form:
            logger.info("Running demo sequence")
            status = run_demo_sequence()

        else:
            try:
                az = float(form["az"])
                el = float(form["el"])
                status = send_command(az, el)
            except ValueError:
                logger.warning("Invalid az/el input")
                status = "Invalid input. Please enter numeric values."

        logger.info("Status: %s", status)

    az, el = get_position()
    az_speed = get_config("AZIMUTH_SPEED_DPS")
    el_speed = get_config("ELEVATION_SPEED_DPS")

    return render_template_string(
        PAGE,
        az=az,
        el=el,
        caz=az,
        cel=el,
        msg=status,
        cos=math.cos,
        sin=math.sin,
        radians=math.radians,
        az_speed=az_speed,
        el_speed=el_speed,
    )


def main():
    """
    Entry point. Initializes serial, starts TCP server and web interface.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True, help="Serial port, e.g., COM15")
    parser.add_argument("--baud", default=2400, type=int, help="Baud rate")
    args = parser.parse_args()

    logger.info("Initializing serial on port %s @ %d baud", args.port, args.baud)
    init_serial(args.port, args.baud)

    # Start TCP server for Gpredict
    threading.Thread(target=start_server, daemon=True).start()
    logger.info("EasyComm TCP server started on port 4533")

    # Start Flask app
    logger.info("Starting Flask web interface at http://127.0.0.1:5000")
    app.run(debug=True, use_reloader=False)


if __name__ == "__main__":
    main()
