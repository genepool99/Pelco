import argparse
from flask import Flask, request, render_template_string
import math
from state import get_position, set_position
from pelco_commands import (
    nudge_elevation,
    set_horizon,
    calibrate,
    init_serial,
    send_command,
    run_demo_sequence,
)
from page_template import PAGE

app = Flask(__name__)

@app.route("/", methods=["GET", "POST"])
def web_control():
    az, el = get_position()
    status = "Ready"

    if request.method == "POST":
        form = request.form

        if "reset" in form:
            set_position(0, 0)
            status = "Position reset"

        elif "calibrate" in form:
            status = calibrate()

        elif "nudge_up_small" in form:
            status = nudge_elevation(1, duration=0.15)

        elif "nudge_down_small" in form:
            status = nudge_elevation(-1, duration=0.15)

        elif "nudge_up_big" in form:
            status = nudge_elevation(1, duration=0.6)

        elif "nudge_down_big" in form:
            status = nudge_elevation(-1, duration=0.6)

        elif "set_horizon" in form:
            status = set_horizon()

        elif "run_demo" in form:
            status = run_demo_sequence()

        else:
            try:
                az = float(form["az"])
                el = float(form["el"])
                status = send_command(az, el)
            except ValueError:
                status = "Invalid input. Please enter numeric values."

    az, el = get_position()
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
    )

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True, help="Serial port, e.g., COM15")
    parser.add_argument("--baud", default=2400, type=int, help="Baud rate")
    args = parser.parse_args()
    init_serial(args.port, args.baud)
    app.run(debug=True, use_reloader=False)

if __name__ == "__main__":
    main()