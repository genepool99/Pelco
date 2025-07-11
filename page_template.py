# page_template.py
PAGE = """
<!doctype html>
<title>Pelco-D Web Control</title>
<h1>Pelco-D Web Debug Interface</h1>
<form method=post>
  Azimuth: <input name=az type=number step=0.1 value="{{az}}"><br>
  Elevation: <input name=el type=number step=0.1 value="{{el}}"><br><br>
  <input type=submit value="Send">
  <button name="reset" value="1">Reset Position</button>
  <button name="calibrate" value="1">Calibrate</button>
  <button name="nudge_up_small">Nudge Up ↑ (small)</button>
  <button name="nudge_up_big">Nudge Up ↑↑ (big)</button>
  <button name="nudge_down_small">Nudge Down ↓ (small)</button>
  <button name="nudge_down_big">Nudge Down ↓↓ (big)</button>
  <button name="set_horizon" value="1">Set Horizon (EL=0)</button>
  <button name="run_demo" type="submit">Run Demo</button>
</form>
<p><strong>Status:</strong> {{msg}}</p>
<p>Current Position: AZ={{caz}} EL={{cel}}</p>
<div style="display: flex; gap: 40px; margin-top: 20px;">
  <div style="width: 300px; height: 300px; border: 1px solid black; border-radius: 50%; position: relative;">
    <svg width="300" height="300">
      <line x1="150" y1="150" x2="{{ 150 + 100 * cos(radians(caz)) }}" y2="{{ 150 - 100 * sin(radians(caz)) }}" stroke="red" stroke-width="2" />
      <circle cx="150" cy="150" r="3" fill="black" />
    </svg>
    <div style="position: absolute; left: 50%; top: 50%; transform: translate(-50%, -50%); font-size: 12px;">Azimuth</div>
  </div>

  <div style="width: 50px; height: 300px; border: 1px solid black; position: relative;">
    <div style="position: absolute; bottom: 0; left: 0; width: 100%; height: {{ (cel + 45) / 90 * 100 }}%; background-color: lightblue;"></div>
    <div style="position: absolute; bottom: 0; width: 100%; text-align: center; font-size: 12px;">Elevation</div>
  </div>
</div>
"""