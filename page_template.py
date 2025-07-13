"""
This file contains the HTML template for the Peltrack control panel.
"""

HTML_PAGE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
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
    .elevation svg {
      display: block;
    }
    .label {
      font-size: 12px;
      text-align: center;
    }
    .controls { display: flex; flex-wrap: wrap; gap: 16px; margin-top: 20px; }
    .group {
      display: flex;
      flex-direction: column;
      gap: 6px;
      margin-right: 20px;
    }
  </style>
</head>
<body>
  <h1>Peltrack Control Panel</h1>

  <form method="post" id="mainForm">
    <input type="hidden" name="action" id="action">

    <label>
      Azimuth:
      <input name="azimuth" type="number" step="0.1" value="{{az}}">
    </label>
    <label>
      Elevation:
      <input name="elevation" type="number" step="0.1" value="{{el}}">
    </label>

    <div class="controls">
      <div class="group">
        <button type="submit" onclick="setAction('set')">Send</button>
        <button type="submit" onclick="setAction('reset')">Reset Position</button>
        <button type="submit" onclick="setAction('calibrate')">Calibrate</button>
        <button type="submit" onclick="setAction('horizon')">Set Zenith (EL=90°)</button>
        <button type="submit" onclick="setAction('demo')">Run Demo</button>
      </div>
      <div class="group">
        <button type="submit" onclick="setAction('nudge_up')">Nudge Up ↑</button>
        <button type="submit" onclick="setAction('nudge_up_big')">Nudge Up ↑↑</button>
        <button type="submit" onclick="setAction('nudge_down')">Nudge Down ↓</button>
        <button type="submit" onclick="setAction('nudge_down_big')">Nudge Down ↓↓</button>
      </div>
    </div>
  </form>

  <p><strong>Status:</strong> <span id="msg">{{msg}}</span></p>
  <p>Current Position: AZ = <span id="az">{{caz}}</span>° &nbsp; EL = <span id="el">{{cel}}</span>°</p>
  <p><strong>Calibrated Speed:</strong> AZ = {{az_speed}}°/s, EL = {{el_speed}}°/s</p>

  <div class="panel">
    <div class="azimuth" aria-label="Azimuth Dial">
      <svg width="300" height="300">
        <circle cx="150" cy="150" r="145" fill="none" stroke="#ccc" stroke-width="1"/>

        <!-- Ticks and Labels -->
        <g font-family="sans-serif" font-size="10" fill="black" stroke="black">
          <line x1="150" y1="5" x2="150" y2="15" stroke-width="2"/>
          <text x="150" y="25" text-anchor="middle">N</text>
          <line x1="222" y1="27" x2="215" y2="41" stroke-width="1"/>
          <line x1="246" y1="54" x2="237" y2="63" stroke-width="2"/>
          <text x="240" y="50" text-anchor="start">NE</text>
          <line x1="270" y1="78" x2="257" y2="85" stroke-width="1"/>
          <line x1="295" y1="150" x2="285" y2="150" stroke-width="2"/>
          <text x="272" y="153" text-anchor="start">E</text>
          <line x1="270" y1="222" x2="257" y2="215" stroke-width="1"/>
          <line x1="246" y1="246" x2="237" y2="237" stroke-width="2"/>
          <text x="240" y="260" text-anchor="start">SE</text>
          <line x1="222" y1="270" x2="215" y2="257" stroke-width="1"/>
          <line x1="150" y1="295" x2="150" y2="285" stroke-width="2"/>
          <text x="150" y="280" text-anchor="middle">S</text>
          <line x1="78" y1="270" x2="85" y2="257" stroke-width="1"/>
          <line x1="54" y1="246" x2="63" y2="237" stroke-width="2"/>
          <text x="40" y="260" text-anchor="end">SW</text>
          <line x1="30" y1="222" x2="43" y2="215" stroke-width="1"/>
          <line x1="5" y1="150" x2="15" y2="150" stroke-width="2"/>
          <text x="28" y="153" text-anchor="end">W</text>
          <line x1="30" y1="78" x2="43" y2="85" stroke-width="1"/>
          <line x1="54" y1="54" x2="63" y2="63" stroke-width="2"/>
          <text x="40" y="50" text-anchor="end">NW</text>
          <line x1="78" y1="30" x2="85" y2="43" stroke-width="1"/>
        </g>

        <!-- Rotor -->
        <line id="az-line" x1="150" y1="150" x2="150" y2="50" stroke="red" stroke-width="2"/>
        <circle cx="150" cy="150" r="3" fill="black"/>
      </svg>
      <div class="azimuth-label">AZ: <span id="az-display">{{caz}}</span>°</div>
    </div>

    <!-- Elevation Panel -->
    <div class="elevation" aria-label="Elevation Bar">
      <svg id="el-svg" width="60" height="300">
        <rect x="5" y="0" width="50" height="300" fill="#f0f0f0" stroke="black"/>
        <rect id="el-fill" x="5" y="0" width="50" height="0" fill="lightblue"/>
        <line id="el-line" x1="5" x2="55" y1="150" y2="150" stroke="blue" stroke-width="2"/>
        <text id="el-text" x="30" y="20" text-anchor="middle" font-size="12">EL</text>
      </svg>
      <div class="label">EL: <span id="el-display">{{cel}}</span>°</div>
    </div>
  </div>

  <script>
  if (window.history.replaceState) {
    window.history.replaceState(null, null, window.location.href);
  }

  function setAction(name) {
    document.getElementById("action").value = name;
    console.log("Set action to:", name);
  }

  const socket = io();

  function updateAzimuth(angle) {
    console.log("[Azimuth] Incoming:", angle);
    const radians = angle * Math.PI / 180;
    const length = 100;
    const x = 150 + length * Math.sin(radians);
    const y = 150 - length * Math.cos(radians);

    const line = document.getElementById("az-line");
    line.setAttribute("x2", x);
    line.setAttribute("y2", y);

    document.getElementById("az").textContent = angle.toFixed(1);
    document.getElementById("az-display").textContent = angle.toFixed(1);
  }

  function updateElevation(el) {
    console.log("[Elevation] Incoming:", el);
    const clampedEl = Math.max(45, Math.min(135, el));
    const elPct = 1 - (clampedEl - 45) / 90;
    const fillHeight = elPct * 300;
    const yFill = 300 - fillHeight;

    const fillRect = document.getElementById("el-fill");
    fillRect.setAttribute("y", yFill);
    fillRect.setAttribute("height", fillHeight);

    const line = document.getElementById("el-line");
    line.setAttribute("y1", yFill);
    line.setAttribute("y2", yFill);

    document.getElementById("el").textContent = el.toFixed(1);
    document.getElementById("el-display").textContent = el.toFixed(1);
    console.log(`[Elevation] Y: ${yFill.toFixed(1)}, Height: ${fillHeight.toFixed(1)}`);
  }

  socket.on("position", function (data) {
    console.log("[WebSocket] Received position update:", data);
    if ("az" in data) updateAzimuth(data.az);
    if ("el" in data) updateElevation(data.el);
    if ("msg" in data) {
      console.log("[Message] Server says:", data.msg);
      document.getElementById("msg").textContent = data.msg;
    }
  });
</script>

</body>
</html>
"""
