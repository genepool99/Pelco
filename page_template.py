"""
This file contains the HTML template for the Peltrack control panel.
"""

HTML_PAGE = """
<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <title>Peltrack</title>
  <meta name=\"description\" content=\"Peltrack: Pelco-D rotor controller web interface\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1, viewport-fit=cover\">
  <script src=\"https://cdn.socket.io/4.7.2/socket.io.min.js\"></script>
  <style>
    :root {
      --gap: 16px;
      --dial-size: 300px;   /* azimuth dial */
      --el-height: 300px;   /* elevation bar height */
      --radius: calc(var(--dial-size) / 2);
      --panel-pad: 12px;
      --card-bg: #f8f8f8;
      --border: #d9d9d9;
      --text: #222;
      --muted: #666;
    }

    @media (max-width: 1280px), (max-height: 720px) {
      :root {
        --gap: 12px;
        --dial-size: 240px;
        --el-height: 240px;
      }
      h1 { font-size: 20px; }
      body { margin: 12px; }
      .azimuth-label { font-size: 12px; }
      /* Hide diagonal labels to declutter */
      .azimuth .diag { display: none; }
    }

    * { box-sizing: border-box; }
    body { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; margin: 20px; color: var(--text); }
    h1 { margin: 0 0 10px; }

    /* Layout */
    .container { display: grid; gap: var(--gap); }
    .panel { display: flex; flex-wrap: wrap; gap: var(--gap); align-items: center; }

    /* Cards */
    .card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 10px; padding: var(--panel-pad); }

    /* Form */
    form { display: grid; gap: var(--gap); }
    .toolbar { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: var(--gap); }
    .controls { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: var(--gap); }
    .group { display: grid; gap: 8px; }

    label { display: grid; grid-template-columns: 1fr auto; align-items: center; gap: 8px; font-size: 14px; }
    input[type=number] { width: 110px; padding: 6px 8px; border: 1px solid var(--border); border-radius: 8px; font-size: 14px; }

    button { cursor: pointer; border: 1px solid var(--border); background: white; border-radius: 10px; padding: 8px 12px; font-size: 14px; }
    button:hover { background: #fffefe; }

    .status { display: flex; flex-wrap: wrap; gap: 8px 16px; align-items: baseline; }
    .muted { color: var(--muted); }

    /* Azimuth Dial */
    .azimuth { position: relative; width: var(--dial-size); height: var(--dial-size); border: 1px solid #ccc; border-radius: 50%; background: #fff; }
    .azimuth svg { width: 100%; height: 100%; display: block; }
    .azimuth-label { position: absolute; bottom: 8px; left: 50%; transform: translateX(-50%); font-weight: 600; font-size: 14px; }

    /* Elevation Bar */
    .elevation { display: grid; justify-items: center; align-content: start; gap: 6px; }
    .elevation svg { width: 60px; height: var(--el-height); display: block; }
    .label { font-size: 12px; text-align: center; }

    /* Helpers */
    .grid-2 { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--gap); }

    @media (max-width: 720px) {
      .grid-2 { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class=\"container\">
    <h1>Peltrack Control Panel</h1>

    <form method=\"post\" id=\"mainForm\" class=\"card\">
      <input type=\"hidden\" name=\"action\" id=\"action\">

      <div class=\"toolbar grid-2\">
        <label>
          <span>Azimuth</span>
          <input name=\"azimuth\" type=\"number\" step=\"0.1\" value=\"{{az}}\">
        </label>
        <label>
          <span>Elevation</span>
          <input name=\"elevation\" type=\"number\" step=\"0.1\" value=\"{{el}}\">
        </label>
      </div>

      <div class=\"controls\">
        <div class=\"group card\">
          <button type=\"submit\" onclick=\"setAction('set')\">Send</button>
          <button type=\"submit\" onclick=\"setAction('reset')\">Reset Position</button>
          <button type=\"submit\" onclick=\"setAction('calibrate')\">Calibrate</button>
          <button type=\"submit\" onclick=\"setAction('horizon')\">Set Zenith (EL=90°)</button>
          <button type=\"submit\" onclick=\"setAction('demo')\">Run Demo</button>
        </div>
        <div class=\"group card\">
          <button type=\"submit\" onclick=\"setAction('nudge_up')\">Nudge Up ↑</button>
          <button type=\"submit\" onclick=\"setAction('nudge_up_big')\">Nudge Up ↑↑</button>
          <button type=\"submit\" onclick=\"setAction('nudge_down')\">Nudge Down ↓</button>
          <button type=\"submit\" onclick=\"setAction('nudge_down_big')\">Nudge Down ↓↓</button>
          <button type=\"submit\" onclick=\"setAction('stop')\">Stop</button>
        </div>
      </div>
    </form>

    <div class=\"status\">
      <p><strong>Status:</strong> <span id=\"msg\" aria-live=\"polite\">{{msg}}</span></p>
      <p>Current Position: AZ = <span id=\"az\">{{caz}}</span>° &nbsp; EL = <span id=\"el\">{{cel}}</span>°</p>
      <p class=\"muted\"><strong>Calibrated Speed</strong>: AZ = {{az_speed}}°/s, EL = {{el_speed}}°/s</p>
    </div>

    <div class=\"panel\">
      <!-- Azimuth Dial -->
      <div class=\"azimuth card\" aria-label=\"Azimuth Dial\">
        <svg viewBox=\"0 0 300 300\" preserveAspectRatio=\"xMidYMid meet\">
          <circle cx=\"150\" cy=\"150\" r=\"145\" fill=\"none\" stroke=\"#ccc\" stroke-width=\"1\"/>

          <!-- Ticks and Labels -->
          <g font-family=\"sans-serif\" font-size=\"10\" fill=\"black\" stroke=\"black\">
            <line x1=\"150\" y1=\"5\" x2=\"150\" y2=\"15\" stroke-width=\"2\"/>
            <text x=\"150\" y=\"25\" text-anchor=\"middle\">N</text>

            <line x1=\"222\" y1=\"27\" x2=\"215\" y2=\"41\" stroke-width=\"1\"/>
            <line x1=\"246\" y1=\"54\" x2=\"237\" y2=\"63\" stroke-width=\"2\"/>
            <text class=\"diag\" x=\"240\" y=\"50\" text-anchor=\"start\">NE</text>

            <line x1=\"270\" y1=\"78\" x2=\"257\" y2=\"85\" stroke-width=\"1\"/>
            <line x1=\"295\" y1=\"150\" x2=\"285\" y2=\"150\" stroke-width=\"2\"/>
            <text x=\"272\" y=\"153\" text-anchor=\"start\">E</text>

            <line x1=\"270\" y1=\"222\" x2=\"257\" y2=\"215\" stroke-width=\"1\"/>
            <line x1=\"246\" y1=\"246\" x2=\"237\" y2=\"237\" stroke-width=\"2\"/>
            <text class=\"diag\" x=\"240\" y=\"260\" text-anchor=\"start\">SE</text>

            <line x1=\"222\" y1=\"270\" x2=\"215\" y2=\"257\" stroke-width=\"1\"/>
            <line x1=\"150\" y1=\"295\" x2=\"150\" y2=\"285\" stroke-width=\"2\"/>
            <text x=\"150\" y=\"280\" text-anchor=\"middle\">S</text>

            <line x1=\"78\" y1=\"270\" x2=\"85\" y2=\"257\" stroke-width=\"1\"/>
            <line x1=\"54\" y1=\"246\" x2=\"63\" y2=\"237\" stroke-width=\"2\"/>
            <text class=\"diag\" x=\"40\" y=\"260\" text-anchor=\"end\">SW</text>

            <line x1=\"30\" y1=\"222\" x2=\"43\" y2=\"215\" stroke-width=\"1\"/>
            <line x1=\"5\" y1=\"150\" x2=\"15\" y2=\"150\" stroke-width=\"2\"/>
            <text x=\"28\" y=\"153\" text-anchor=\"end\">W</text>

            <line x1=\"30\" y1=\"78\" x2=\"43\" y2=\"85\" stroke-width=\"1\"/>
            <line x1=\"54\" y1=\"54\" x2=\"63\" y2=\"63\" stroke-width=\"2\"/>
            <text class=\"diag\" x=\"40\" y=\"50\" text-anchor=\"end\">NW</text>
            <line x1=\"78\" y1=\"30\" x2=\"85\" y2=\"43\" stroke-width=\"1\"/>
          </g>

          <!-- Rotor -->
          <line id=\"az-line\" x1=\"150\" y1=\"150\" x2=\"150\" y2=\"50\" stroke=\"red\" stroke-width=\"2\"/>
          <circle cx=\"150\" cy=\"150\" r=\"3\" fill=\"black\"/>
        </svg>
        <div class=\"azimuth-label\">AZ: <span id=\"az-display\">{{caz}}</span>°</div>
      </div>

      <!-- Elevation Panel -->
      <div class=\"elevation card\" aria-label=\"Elevation Bar\">
        <svg id=\"el-svg\" width=\"60\" height=\"300\">
          <rect x=\"5\" y=\"0\" width=\"50\" height=\"300\" fill=\"#f0f0f0\" stroke=\"black\"/>
          <rect id=\"el-fill\" x=\"5\" y=\"0\" width=\"50\" height=\"0\" fill=\"lightblue\"/>
          <line id=\"el-line\" x1=\"5\" x2=\"55\" y1=\"150\" y2=\"150\" stroke=\"blue\" stroke-width=\"2\"/>
          <text id=\"el-text\" x=\"30\" y=\"20\" text-anchor=\"middle\" font-size=\"12\">EL</text>
        </svg>
        <div class=\"label\">EL: <span id=\"el-display\">{{cel}}</span>°</div>
      </div>
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
    const radians = angle * Math.PI / 180;
    const length = 100; // in SVG user units (viewBox coords)
    const x = 150 + length * Math.sin(radians);
    const y = 150 - length * Math.cos(radians);

    const line = document.getElementById("az-line");
    line.setAttribute("x2", x);
    line.setAttribute("y2", y);

    document.getElementById("az").textContent = angle.toFixed(1);
    document.getElementById("az-display").textContent = angle.toFixed(1);
  }

  function updateElevation(el) {
    const clampedEl = Math.max(45, Math.min(135, el));
    // Map 45..135 => 300..0 (SVG user units)
    const elPct = 1 - (clampedEl - 45) / 90; // 1 at 45°, 0 at 135°
    const full = 300; // matches SVG height
    const fillHeight = elPct * full;
    const yFill = full - fillHeight;

    const fillRect = document.getElementById("el-fill");
    fillRect.setAttribute("y", yFill);
    fillRect.setAttribute("height", fillHeight);

    const line = document.getElementById("el-line");
    line.setAttribute("y1", yFill);
    line.setAttribute("y2", yFill);

    document.getElementById("el").textContent = el.toFixed(1);
    document.getElementById("el-display").textContent = el.toFixed(1);
  }

  socket.on("position", function (data) {
    if ("az" in data) updateAzimuth(data.az);
    if ("el" in data) updateElevation(data.el);
    if ("msg" in data) {
      document.getElementById("msg").textContent = data.msg;
    }
  });
  </script>

</body>
</html>
"""
