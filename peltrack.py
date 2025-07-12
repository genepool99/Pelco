"""Peltrack: A Flask web and TCP server for controlling a Pelco-D rotor.

This module provides a web interface and EasyComm-compatible TCP server
for controlling an antenna rotator using the Pelco-D protocol.

Features:
- Web interface for manual control and calibration
- Real-time rotor position updates via WebSocket
- EasyComm TCP server for integration with Gpredict
"""

import eventlet
eventlet.monkey_patch()

import argparse
import logging
import threading
from flask import Flask, request
from flask_socketio import SocketIO

from pelco_commands import (
    calibrate,
    run_demo_sequence,
    send_command,
    nudge_elevation,
    set_horizon,
    stop,
    init_serial,
)
from state import get_position, set_position, get_config
from easycomm_server import start_server

HTML_PAGE = """
<!doctype html>
<html>
<head>
  <title>Peltrack</title>
  <meta name="description" content="Peltrack: Pelco-D rotor controller web interface">
  <script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
  <style>
    body { font-family: sans-serif; margin: 20px; }
    input { width: 80px; }
    button { margin: 4px; padding: 5px 10px; }
    .panel { display: flex; gap: 40px; margin-top: 20px; align-items: center; }
    .azimuth {
      width: 300px; height: 300px;
      border: 1px solid black;
      border-radius: 50%;
      position: relative;
    }
    .azimuth-label {
      position: absolute;
      top: 135px;
      left: 50%;
      transform: translateX(-50%);
      font-weight: bold;
      font-size: 16px;
    }
    .elevation {
      width: 50px; height: 300px;
      border: 1px solid black;
      position: relative;
    }
    .elevation-fill {
      position: absolute;
      left: 0; bottom: 0;
      width: 100%;
      background-color: lightblue;
    }
    .elevation-scale {
      position: absolute;
      top: 0;
      left: 55px;
      height: 100%;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }
    .elevation-scale span {
      font-size: 10px;
    }
    .label {
      font-size: 12px;
      text-align: center;
    }
    .controls { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 20px; }
    .group { display: flex; flex-direction: column; gap: 4px; margin-right: 20px; }
  </style>
</head>
<body>
  <h1>Peltrack Web Debug Interface</h1>
  <form method="post" id="mainForm">
    <input type="hidden" name="action" id="action">
    Azimuth: <input name="azimuth" type="number" step="0.1" value="{{az}}">
    Elevation: <input name="elevation" type="number" step="0.1" value="{{el}}"><br><br>
    <div class="controls">
      <div class="group">
        <button type="submit" onclick="setAction('set')">Send</button>
        <button type="submit" onclick="setAction('reset')">Reset Position</button>
        <button type="submit" onclick="setAction('calibrate')">Calibrate</button>
        <button type="submit" onclick="setAction('horizon')">Set Horizon (EL=0)</button>
        <button type="submit" onclick="setAction('demo')">Run Demo</button>
      </div>
      <div class="group">
        <button type="submit" onclick="setAction('nudge_up')">Nudge Up ↑ (small)</button>
        <button type="submit" onclick="setAction('nudge_up_big')">Nudge Up ↑↑ (big)</button>
        <button type="submit" onclick="setAction('nudge_down')">Nudge Down ↓ (small)</button>
        <button type="submit" onclick="setAction('nudge_down_big')">Nudge Down ↓↓ (big)</button>
      </div>
    </div>
  </form>

  <p><strong>Status:</strong> <span id="msg">{{msg}}</span></p>
  <p>Current Position: AZ=<span id="az">{{caz}}</span> EL=<span id="el">{{cel}}</span></p>
  <p><strong>Calibrated Speed:</strong> AZ={{az_speed}}&deg;/sec, EL={{el_speed}}&deg;/sec</p>

  <div class="panel">
    <div class="azimuth">
      <svg width="300" height="300">
        <circle cx="150" cy="150" r="145" fill="none" stroke="#ccc" stroke-width="1"/>
        <line id="az-line" x1="150" y1="150" x2="150" y2="50" stroke="red" stroke-width="2" />
        <circle cx="150" cy="150" r="3" fill="black" />
      </svg>
      <div class="azimuth-label">AZ: <span id="az-display">{{caz}}</span>°</div>
    </div>

    <div class="elevation">
      <div id="el-fill" class="elevation-fill" style="height: 0%"></div>
      <div class="elevation-scale">
        <span>+45°</span>
        <span>+30°</span>
        <span>+15°</span>
        <span>  0°</span>
        <span>-15°</span>
        <span>-30°</span>
        <span>-45°</span>
      </div>
      <div class="label">EL: <span id="el-display">{{cel}}</span>°</div>
    </div>
  </div>

  <script>
    if (window.history.replaceState) {
      window.history.replaceState(null, null, window.location.href);
    }

    function setAction(name) {
      document.getElementById("action").value = name;
    }

    const socket = io();

    function updateAzimuth(angle) {
      const radians = angle * Math.PI / 180;
      const length = 100;
      const x = 150 + length * Math.sin(radians);
      const y = 150 - length * Math.cos(radians);
      document.getElementById("az-line").setAttribute("x2", x);
      document.getElementById("az-line").setAttribute("y2", y);
      document.getElementById("az").textContent = angle.toFixed(1);
      document.getElementById("az-display").textContent = angle.toFixed(1);
    }

    function updateElevation(el) {
      const elPct = Math.min(1, Math.max(0, (el + 45) / 90));
      document.getElementById("el-fill").style.height = (elPct * 100) + "%";
      document.getElementById("el").textContent = el.toFixed(1);
      document.getElementById("el-display").textContent = el.toFixed(1);
    }

    socket.on("position", function (data) {
      if ("az" in data) updateAzimuth(data.az);
      if ("el" in data) updateElevation(data.el);
      if ("msg" in data) document.getElementById("msg").textContent = data.msg;
    });
  </script>
</body>
</html>
"""

app = Flask(__name__)
socketio = SocketIO(app, async_mode="eventlet")

def socketio_emit_position(msg=None):
    """Emit the current rotor position and optional message."""
    az, el = get_position()
    payload = {"az": az, "el": el}
    if msg:
        payload["msg"] = msg
    socketio.emit("position", payload)

@app.route("/", methods=["GET"])
def index():
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
    return html

@app.route("/", methods=["POST"])
def control():
    action = request.form.get("action")
    try:
        if action == "calibrate":
            msg = calibrate()
        elif action == "reset":
            set_position(0.0, 0.0)
            msg = "Position reset to 0° azimuth and 0° elevation."
        elif action == "demo":
            threading.Thread(
                target=run_demo_sequence,
                kwargs={"update_callback": socketio_emit_position},
                daemon=True
            ).start()
            msg = "Demo started"
        elif action == "set":
            az = float(request.form.get("azimuth"))
            el = float(request.form.get("elevation"))
            msg = send_command(az, el, update_callback=socketio_emit_position)
        elif action == "nudge_up":
            msg = nudge_elevation(1, 1.0)
        elif action == "nudge_down":
            msg = nudge_elevation(-1, 1.0)
        elif action == "nudge_up_big":
            msg = nudge_elevation(1, 2.0)
        elif action == "nudge_down_big":
            msg = nudge_elevation(-1, 2.0)
        elif action == "horizon":
            msg = set_horizon()
        elif action == "stop":
            stop()
            msg = "Rotor stopped."
        else:
            msg = f"Unknown command: {action}"
    except (ValueError, RuntimeError) as e:
        msg = f"Error: {str(e)}"

    socketio_emit_position(msg)
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
    return html

def start_easycomm_server():
    start_server(update_callback=socketio_emit_position)

def main():
    parser = argparse.ArgumentParser(description="Pelco-D Rotor Controller")
    parser.add_argument("--port", required=True, help="Serial port (e.g., COM4 or /dev/ttyUSB0)")
    parser.add_argument("--baud", type=int, default=2400, help="Baud rate (default: 2400)")
    args = parser.parse_args()

    init_serial(args.port, args.baud)

    thread = threading.Thread(target=start_easycomm_server, daemon=True)
    thread.start()

    logging.info("Starting web server at http://localhost:5000")
    socketio.run(app, host="0.0.0.0", port=5000)

if __name__ == "__main__":
    main()
