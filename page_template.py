"""Peltrack web UI HTML template (mobile-friendly nudges + live config table)."""

__all__ = ["HTML_PAGE"]

HTML_PAGE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Peltrack</title>
  <meta name="description" content="Peltrack: Pelco-D rotor controller web interface">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>

  <!-- Inline SVG favicon (compass) -->
  <link rel="icon" type="image/svg+xml"
    href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Ccircle cx='32' cy='32' r='30' fill='%230b1220'/%3E%3Ccircle cx='32' cy='32' r='26' fill='none' stroke='%23e5e7eb' stroke-width='2'/%3E%3Cg stroke='%23e5e7eb' stroke-width='2'%3E%3Cline x1='32' y1='6' x2='32' y2='12'/%3E%3Cline x1='32' y1='52' x2='32' y2='58'/%3E%3Cline x1='6'  y1='32' x2='12' y2='32'/%3E%3Cline x1='52' y1='32' x2='58' y2='32'/%3E%3C/g%3E%3Cpolygon points='32,18 36,32 28,32' fill='%23ef4444'/%3E%3Cpolygon points='32,46 36,32 28,32' fill='%239ca3af'/%3E%3C/svg%3E" />

  <style>
    :root {
      --gap: 14px;
      --card-pad: 12px;
      --radius: 12px;
      --border: #d0d7de;
      --bg: #fafbfc;
      --fg: #1f2328;
      --muted: #57606a;

      /* Sizes tuned for 100% zoom @ 1280×720 */
      --dial: 280px;
      --bar-h: 300px;
      --btn-h: 48px;
      --btn-font: 17px;
      --input-font: 18px;

      /* Nudge pad */
      --pad-size: 72px;       /* big, touch-friendly */
      --pad-font: 22px;
      --pad-round: 12px;

      /* Button colors */
      --primary: #0ea5e9;   --primary-fg: #fff;     /* Send */
      --accent:  #6366f1;   --accent-fg:  #fff;     /* Return-to */
      --neutral: #e5e7eb;   --neutral-fg: #111827;  /* Reset, Demo */
      --secondary:#f3f4f6;  --secondary-fg:#111827; /* Misc */
      --warning: #f59e0b;   --warning-fg: #111827;  /* Calibrate */
      --danger:  #ef4444;   --danger-fg:  #fff;     /* STOP */
    }

    @media (max-width: 480px) {
      :root { --dial: 220px; --bar-h: 240px; --pad-size: 64px; --btn-font: 16px; --btn-h: 46px; }
    }

    * { box-sizing: border-box; }
    html, body { height: 100%; }
    body { margin: 0; font-family: system-ui,-apple-system,Segoe UI,Roboto,sans-serif; color: var(--fg); background: #fafbfc; }

    .wrap { display: grid; gap: var(--gap); padding: var(--gap); max-width: 1200px; margin: 0 auto; }
    header { display: grid; gap: 10px; }
    .brand { display: flex; align-items: center; gap: 12px; }
    .brand-icon { width: 56px; height: 56px; flex: 0 0 auto; }
    .brand-text .title { font-size: 28px; font-weight: 800; line-height: 1.1; }
    .brand-text .subtitle { font-size: 14px; color: var(--muted); margin-top: 2px; }

    .status-line { display: flex; flex-wrap: wrap; gap: 10px 16px; align-items: baseline; }
    .muted { color: var(--muted); }

    .badge { display: inline-block; padding: 4px 8px; border-radius: 999px; background: #fde68a; color: #7c2d12; border: 1px solid #f59e0b; font-size: 12px; font-weight: 600; }

    .af-grid { display: grid; grid-template-columns: 1.25fr 1fr; gap: var(--gap); align-items: start; }
    @media (max-width: 1000px) { .af-grid { grid-template-columns: 1fr; } }

    .card { background: #fff; border: 1px solid var(--border); border-radius: var(--radius); padding: var(--card-pad); }
    .ctrl-card { display: grid; gap: var(--gap); }

    .row { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: var(--gap); }
    .row-tight { grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: var(--gap); }

    label { display: grid; grid-template-columns: 1fr auto; align-items: center; gap: 8px; font-size: 15px; }
    input[type=number] { width: 140px; padding: 10px 12px; border: 1px solid var(--border); border-radius: 10px; font-size: var(--input-font); }
    input[type=number]::-webkit-outer-spin-button,
    input[type=number]::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }

    .btn { cursor: pointer; height: var(--btn-h); border: 1px solid var(--border); background: #fff; border-radius: 10px; font-size: var(--btn-font); padding: 0 14px; }
    .btn:hover { filter: brightness(0.98); }
    .btn-primary { background: var(--primary); color: var(--primary-fg); border-color: var(--primary); }
    .btn-accent  { background: var(--accent);  color: var(--accent-fg);  border-color: var(--accent); }
    .btn-warning { background: var(--warning); color: var(--warning-fg); border-color: var(--warning); }
    .btn-danger  { background: var(--danger);  color: var(--danger-fg); border-color: var(--danger); }
    .btn-neutral { background: var(--neutral); color: var(--neutral-fg); border-color: var(--neutral); }
    .btn-secondary { background: var(--secondary); color: var(--secondary-fg); border-color: var(--border); }
    .btn-block { width: 100%; }

    /* Nudge D-pad */
    .pad-wrap { display: grid; grid-template-columns: 1fr auto; gap: var(--gap); align-items: center; }
    @media (max-width: 740px) { .pad-wrap { grid-template-columns: 1fr; } }

    .pad { display: grid; grid-template-columns: var(--pad-size) var(--pad-size) var(--pad-size); grid-template-rows: var(--pad-size) var(--pad-size) var(--pad-size); gap: 10px; justify-content: start; align-items: start; }
    .pad .pbtn {
      display: inline-flex; align-items: center; justify-content: center;
      width: var(--pad-size); height: var(--pad-size);
      border-radius: var(--pad-round); border: 1px solid var(--border); background: #fff;
      font-size: var(--pad-font); user-select: none; -webkit-user-select: none; touch-action: manipulation;
    }
    .pad .pbtn:active { filter: brightness(0.94); }
    .pad .label { font-size: 12px; color: var(--muted); text-align: center; grid-column: 1 / -1; }

    .step-toggle { display: inline-grid; grid-auto-flow: column; gap: 8px; align-items: center; }
    .seg {
      display: inline-flex; align-items: center; justify-content: center;
      min-width: 84px; height: 36px; padding: 0 12px; border-radius: 999px;
      border: 1px solid var(--border); background: var(--secondary); cursor: pointer; font-size: 14px;
    }
    .seg.active { background: #1f2937; color: #fff; border-color: #1f2937; }

    .gauges { display: grid; gap: var(--gap); }
    .readouts { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--gap); }
    .readout { text-align: center; padding: 10px; border: 1px solid var(--border); border-radius: var(--radius); background: #fff; }
    .readout .big { font-size: 28px; font-weight: 700; }

    .azimuth { position: relative; width: var(--dial); height: var(--dial); border: 1px solid var(--border); border-radius: 50%; background: #fff; margin: 0 auto; }
    .azimuth svg { width: 100%; height: 100%; display: block; }
    .needle { stroke: #e31b4b; stroke-width: 2; }
    .center { fill: #000; }

    .elevation { display: grid; justify-items: center; align-content: start; gap: 6px; }
    .elevation svg { width: 160px; height: var(--bar-h); display: block; overflow: visible; }

    /* Progress bar */
    .progress { width: 100%; height: 12px; background: #e5e7eb; border: 1px solid #cbd5e1; border-radius: 999px; overflow: hidden; }
    .progress > .bar { width: 0%; height: 100%; background: #0ea5e9; transition: width 0.2s ease; }
    #cal-stage-line { font-size: 13px; color: #334155; }

    /* Modal */
    .modal { position: fixed; inset: 0; background: rgba(0,0,0,0.45); display: none; align-items: center; justify-content: center; z-index: 9999; }
    .modal.open { display: flex; }
    .modal-card { width: min(520px, 92vw); max-height: 80vh; overflow: auto; background: #fff; border-radius: 12px; border: 1px solid var(--border); padding: 16px; display: grid; gap: 10px; }
    .log { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 13px; white-space: pre-wrap; background: #f8fafc; border: 1px solid var(--border); padding: 10px; border-radius: 8px; }

    /* Config table */
    .cfg-table { width: 100%; border-collapse: collapse; }
    .cfg-table th, .cfg-table td { border: 1px solid var(--border); padding: 6px 8px; font-size: 14px; }
    .cfg-table th { background: #f3f4f6; text-align: left; }
    .cfg-wrap details { border: 1px solid var(--border); border-radius: var(--radius); padding: 10px; background: #fff; }
    .cfg-wrap summary { font-weight: 700; cursor: pointer; margin-bottom: 8px; }

    .footer { text-align: center; font-size: 12px; color: var(--muted); }
    .dimmed * { pointer-events: none; }
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <div class="brand">
        <svg class="brand-icon" viewBox="0 0 64 64" aria-hidden="true">
          <circle cx="32" cy="32" r="30" fill="#0b1220"></circle>
          <circle cx="32" cy="32" r="26" fill="none" stroke="#e5e7eb" stroke-width="2"></circle>
          <g stroke="#e5e7eb" stroke-width="2">
            <line x1="32" y1="6"  x2="32" y2="12"></line>
            <line x1="32" y1="52" x2="32" y2="58"></line>
            <line x1="6"  y1="32" x2="12" y2="32"></line>
            <line x1="52" y1="32" x2="58" y2="32"></line>
          </g>
          <polygon points="32,18 36,32 28,32" fill="#ef4444"></polygon>
          <polygon points="32,46 36,32 28,32" fill="#9ca3af"></polygon>
        </svg>
        <div class="brand-text">
          <div class="title">Peltrack</div>
          <div class="subtitle">Pelco-D Rotor Control</div>
        </div>
      </div>

      <div class="status-line">
        <div><strong>Status:</strong> <span id="msg" aria-live="polite">{{msg}}</span></div>
        <div><strong>AZ</strong> <span id="az">{{caz}}</span>°</div>
        <div><strong>EL</strong> <span id="el">{{cel}}</span>°</div>
        <div class="muted"><strong>Speed</strong> AZ {{az_speed}}°/s · EL {{el_speed}}°/s</div>
        <div class="muted"><strong>Limits</strong> AZ [<span id="lim-az-min">{{az_min}}</span>–<span id="lim-az-max">{{az_max}}</span>] · EL [<span id="lim-el-min">{{el_min}}</span>–<span id="lim-el-max">{{el_max}}</span>]</div>
        <div class="muted"><strong>EL ref</strong> <span id="el-ref">{{el_ref}}</span></div>
        <div><strong>Req AZ</strong> <span id="req-az">—</span>°</div>
        <div><strong>Req EL</strong> <span id="req-el">—</span>°</div>
        <span id="clamped" class="badge" style="display:none;">⚠︎ Clamped to limits</span>
      </div>
    </header>

    <div class="af-grid">
      <!-- Controls -->
      <form method="post" id="mainForm" class="card ctrl-card" autocomplete="off">
        <input type="hidden" name="action" id="action">

        <div class="row">
          <label>
            <span>Azimuth (°)</span>
            <input name="azimuth" type="number" step="0.1" inputmode="decimal" value="{{az}}">
          </label>
          <label>
            <span>Elevation (°)</span>
            <input name="elevation" type="number" step="0.1" inputmode="decimal" value="{{el}}">
          </label>
        </div>

        <!-- Primary / safety / return-to -->
        <div class="row">
          <button type="button" class="btn btn-primary" onclick="postAction('set')">Send</button>
          <button type="button" class="btn btn-neutral" onclick="postAction('reset')">Reset Pos</button>
          <button type="button" class="btn btn-warning" onclick="startCalibration()">Calibrate</button>
          <button type="button" class="btn btn-accent" onclick="postAction('horizon')">EL → neutral</button>
          <button type="button" class="btn btn-accent" onclick="postAction('az_zero')">AZ → 0°</button>
          <button type="button" class="btn btn-danger" onclick="postAction('stop')">STOP</button>
        </div>

        <!-- Nudge D-pad + step toggle + demo -->
        <div class="pad-wrap">
          <div class="pad" aria-label="Nudge pad">
            <div></div>
            <button type="button" class="pbtn" aria-label="Nudge up" onclick="nudge('up')">▲</button>
            <div></div>

            <button type="button" class="pbtn" aria-label="Nudge left" onclick="nudge('left')">◀</button>
            <div></div>
            <button type="button" class="pbtn" aria-label="Nudge right" onclick="nudge('right')">▶</button>

            <div></div>
            <button type="button" class="pbtn" aria-label="Nudge down" onclick="nudge('down')">▼</button>
            <div></div>

            <div class="label">Tap arrows to nudge AZ/EL</div>
          </div>

          <div style="display:grid; gap:10px;">
            <div class="step-toggle" role="group" aria-label="Nudge step">
              <div class="seg active" id="seg-small" onclick="setStep('small')" role="button" aria-pressed="true">Step: Small</div>
              <div class="seg" id="seg-big" onclick="setStep('big')" role="button" aria-pressed="false">Step: Big</div>
            </div>
            <button type="button" class="btn btn-neutral" onclick="postAction('demo')">Run Demo</button>
          </div>
        </div>
      </form>

      <!-- Monitoring -->
      <div class="gauges">
        <div class="readouts">
          <div class="readout"><div>Azimuth</div><div class="big" id="az-display">{{caz}}</div></div>
          <div class="readout"><div>Elevation</div><div class="big" id="el-display">{{cel}}</div></div>
        </div>

        <div class="card" style="display:grid; grid-template-columns: var(--dial) 180px; gap: var(--gap); justify-content:center;">
          <!-- Azimuth Dial -->
          <div class="azimuth" aria-label="Azimuth Dial">
            <svg id="az-svg" viewBox="0 0 300 300" preserveAspectRatio="xMidYMid meet">
              <g id="az-ticks"></g>
              <line id="az-line" class="needle" x1="150" y1="150" x2="150" y2="50"/>
              <circle class="center" cx="150" cy="150" r="3"/>
            </svg>
          </div>

          <!-- Elevation Panel: 0..180° full-range with limit band/markers -->
          <div class="elevation" aria-label="Elevation Bar" style="align-items:center;">
            <svg id="el-svg" width="160" height="300" viewBox="0 0 160 300">
              <rect x="40" y="0" width="60" height="300" fill="#f8fafc" stroke="#cbd5e1"/>
              <rect id="el-allowed" x="40" y="0" width="60" height="0" fill="#86efac" fill-opacity="0.35" stroke="none"/>
              <rect id="el-fill" x="40" y="300" width="60" height="0" fill="#a7d3ff"/>
              <line id="el-line" x1="40" x2="100" y1="150" y2="150" stroke="#1e66f5" stroke-width="2"/>
              <line id="el-min-line" x1="40" x2="100" y1="0"  y2="0"  stroke="#16a34a" stroke-width="2" stroke-dasharray="5 4"/>
              <line id="el-max-line" x1="40" x2="100" y1="0"  y2="0"  stroke="#16a34a" stroke-width="2" stroke-dasharray="5 4"/>
              <g id="el-ticks"></g>
              <text id="el-min-label" x="106" y="0" font-size="10" dominant-baseline="middle" text-anchor="start" fill="#065f46"></text>
              <text id="el-max-label" x="106" y="0" font-size="10" dominant-baseline="middle" text-anchor="start" fill="#065f46"></text>
            </svg>
          </div>
        </div>

        <!-- Configuration (auto-build from injected JSON) -->
        <div class="cfg-wrap">
          <details>
            <summary>Configuration (loaded)</summary>
            <div id="cfg-container"></div>
          </details>
        </div>
      </div>
    </div>

    <div class="footer">Peltrack - Avi Solomon [AE7ET]</div>
  </div>

  <!-- Calibration Modal -->
  <div id="cal-modal" class="modal" role="dialog" aria-modal="true" aria-labelledby="cal-title">
    <div class="modal-card">
      <h2 id="cal-title">Calibration in progress…</h2>
      <div class="progress" aria-hidden="true"><div id="cal-bar" class="bar"></div></div>
      <div id="cal-stage-line" aria-live="polite"></div>
      <div id="cal-log" class="log"></div>
      <button type="button" class="btn btn-neutral btn-block" onclick="closeCalibrationModal()">Hide</button>
    </div>
  </div>

  <!-- Injected config JSON for building the table -->
  <script id="cfg-data" type="application/json">{{config_json}}</script>

  <script>
  if (window.history.replaceState) { window.history.replaceState(null, null, window.location.href); }

  const form = document.getElementById('mainForm');
  const actionInput = document.getElementById('action');
  const azInput = document.querySelector('input[name="azimuth"]');
  const elInput = document.querySelector('input[name="elevation"]');
  const modal = document.getElementById('cal-modal');
  const logEl = document.getElementById('cal-log');
  const bar = document.getElementById('cal-bar');
  const stageLine = document.getElementById('cal-stage-line');

  // Limits (injected by backend)
  const AZ_MIN = Number("{{az_min}}");
  const AZ_MAX = Number("{{az_max}}");
  const EL_MIN = Number("{{el_min}}");
  const EL_MAX = Number("{{el_max}}");

  function setAction(name) { actionInput.value = name; }
  async function postAction(name) {
    setAction(name);
    try {
      const fd = new FormData(form);
      await fetch('/', { method: 'POST', body: fd, credentials: 'same-origin' });
    } catch (err) { console.error('POST failed', err); }
  }

  // Calibration modal helpers
  let modalCloseTimer = null;
  function openCalibrationModal() {
    document.body.classList.add('dimmed');
    modal.classList.add('open');
    logEl.textContent = '';
    setCalProgress(0, 'starting');
    if (modalCloseTimer) { clearTimeout(modalCloseTimer); modalCloseTimer = null; }
  }
  function closeCalibrationModal() {
    modal.classList.remove('open');
    document.body.classList.remove('dimmed');
  }
  function startCalibration() { openCalibrationModal(); postAction('calibrate'); }

  function setCalProgress(pct, stage) {
    const clamped = Math.max(0, Math.min(1, Number(pct) || 0));
    bar.style.width = Math.round(clamped * 100) + '%';
    if (stage) stageLine.textContent = 'Stage: ' + stage;
    if (!modal.classList.contains('open')) openCalibrationModal();
  }

  // Az compass ticks
  function buildAzimuthTicks() {
    const g = document.getElementById('az-ticks');
    const cx = 150, cy = 150, rOuter = 145;
    for (let deg = 0; deg < 360; deg += 10) {
      const rad = deg * Math.PI / 180;
      const isMajor = (deg % 30) === 0;
      const r1 = isMajor ? 135 : 140;
      const r2 = rOuter;
      const x1 = cx + r1 * Math.sin(rad);
      const y1 = cy - r1 * Math.cos(rad);
      const x2 = cx + r2 * Math.sin(rad);
      const y2 = cy - r2 * Math.cos(rad);

      const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
      line.setAttribute("x1", x1); line.setAttribute("y1", y1);
      line.setAttribute("x2", x2); line.setAttribute("y2", y2);
      line.setAttribute("stroke", "#94a3b8");
      line.setAttribute("stroke-width", isMajor ? "2" : "1");
      g.appendChild(line);

      if (isMajor) {
        const lx = cx + 122 * Math.sin(rad);
        const ly = cy - 122 * Math.cos(rad) + 4;
        const t = document.createElementNS("http://www.w3.org/2000/svg", "text");
        t.setAttribute("x", lx); t.setAttribute("y", ly);
        t.setAttribute("font-size", "10");
        t.setAttribute("text-anchor", "middle");
        t.textContent = String(deg);
        g.appendChild(t);
      }
    }
    const labels = [{d:0,txt:'N'},{d:90,txt:'E'},{d:180,txt:'S'},{d:270,txt:'W'}];
    labels.forEach(({d,txt}) => {
      const rad = d * Math.PI / 180;
      const lx = 150 + 100 * Math.sin(rad);
      const ly = 150 - 100 * Math.cos(rad) + 4;
      const t = document.createElementNS("http://www.w3.org/2000/svg", "text");
      t.setAttribute("x", lx); t.setAttribute("y", ly);
      t.setAttribute("font-size", "12"); t.setAttribute("font-weight", "600");
      t.setAttribute("text-anchor", "middle");
      t.textContent = txt;
      g.appendChild(t);
    });
    const ring = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    ring.setAttribute("cx", 150); ring.setAttribute("cy", 150); ring.setAttribute("r", 145);
    ring.setAttribute("fill", "none"); ring.setAttribute("stroke", "#cbd5e1"); ring.setAttribute("stroke-width", "1");
    g.appendChild(ring);
  }

  // Elevation helpers
  function mapElToY(deg) {
    const full = 300;
    const d = Math.max(0, Math.min(180, Number(deg) || 0));
    const h = (d / 180) * full;
    return full - h;
  }

  function buildElevationTicks() {
    const g = document.getElementById('el-ticks');
    const x1 = 105, x2 = 115;
    for (let deg = 0; deg <= 180; deg += 10) {
      const y = mapElToY(deg);
      const isMajor = (deg % 30) === 0;
      const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
      line.setAttribute("x1", isMajor ? x1-5 : x1); line.setAttribute("x2", x2);
      line.setAttribute("y1", y); line.setAttribute("y2", y);
      line.setAttribute("stroke", "#94a3b8"); line.setAttribute("stroke-width", isMajor ? "2" : "1");
      g.appendChild(line);

      if (isMajor) {
        const t = document.createElementNS("http://www.w3.org/2000/svg", "text");
        t.setAttribute("x", x2 + 6); t.setAttribute("y", y + 4);
        t.setAttribute("font-size", "10"); t.setAttribute("text-anchor", "start");
        t.textContent = String(deg) + "°";
        g.appendChild(t);
      }
    }

    // Allowed band & limit lines/labels
    const yMin = mapElToY(EL_MIN);
    const yMax = mapElToY(EL_MAX);
    const top = Math.min(yMin, yMax);
    const height = Math.abs(yMin - yMax);

    const allowed = document.getElementById('el-allowed');
    allowed.setAttribute('y', top); allowed.setAttribute('height', height);

    const minLine = document.getElementById('el-min-line');
    const maxLine = document.getElementById('el-max-line');
    minLine.setAttribute('y1', yMin); minLine.setAttribute('y2', yMin);
    maxLine.setAttribute('y1', yMax); maxLine.setAttribute('y2', yMax);

    const minLab = document.getElementById('el-min-label');
    const maxLab = document.getElementById('el-max-label');
    minLab.setAttribute('y', yMin);
    maxLab.setAttribute('y', yMax);
    minLab.textContent = "EL min " + EL_MIN + "°";
    maxLab.textContent = "EL max " + EL_MAX + "°";
  }

  // Visual updates
  function updateAzimuth(angle) {
    const radians = angle * Math.PI / 180;
    const len = 100;
    const x = 150 + len * Math.sin(radians);
    const y = 150 - len * Math.cos(radians);
    document.getElementById('az-line').setAttribute('x2', x);
    document.getElementById('az-line').setAttribute('y2', y);
    document.getElementById('az').textContent = angle.toFixed(1);
    document.getElementById('az-display').textContent = angle.toFixed(1);
    azInput.value = angle.toFixed(1);
  }

  function updateElevation(el) {
    const y = mapElToY(el);
    const h = 300 - y;
    document.getElementById('el-fill').setAttribute('y', y);
    document.getElementById('el-fill').setAttribute('height', h);
    document.getElementById('el-line').setAttribute('y1', y);
    document.getElementById('el-line').setAttribute('y2', y);
    document.getElementById('el').textContent = Number(el).toFixed(1);
    document.getElementById('el-display').textContent = Number(el).toFixed(1);
    elInput.value = Number(el).toFixed(1);
  }

  // Step toggle + nudge routing
  let stepMode = 'small';
  function setStep(mode) {
    stepMode = (mode === 'big') ? 'big' : 'small';
    document.getElementById('seg-small').classList.toggle('active', stepMode === 'small');
    document.getElementById('seg-big').classList.toggle('active', stepMode === 'big');
    document.getElementById('seg-small').setAttribute('aria-pressed', String(stepMode === 'small'));
    document.getElementById('seg-big').setAttribute('aria-pressed', String(stepMode === 'big'));
  }

  function nudge(dir) {
    const small = { left:'nudge_left', right:'nudge_right', up:'nudge_up', down:'nudge_down' };
    const big   = { left:'nudge_left_big', right:'nudge_right_big', up:'nudge_up_big', down:'nudge_down_big' };
    const map = (stepMode === 'big') ? big : small;
    const action = map[dir];
    if (action) postAction(action);
  }

  // Socket wiring
  const socket = io();
  socket.on('position', (data) => {
    if ('az' in data) updateAzimuth(data.az);
    if ('el' in data) updateElevation(data.el);

    if ('cal_progress' in data) { setCalProgress(data.cal_progress, data.cal_stage || ''); }

    if ('msg' in data) {
      document.getElementById('msg').textContent = data.msg;
      if (String(data.msg).startsWith('Calibrating:')) {
        openCalibrationModal(); logEl.textContent += (data.msg + "\\n");
      } else if (String(data.msg).includes('Calibration complete')) {
        logEl.textContent += (data.msg + "\\n");
        setCalProgress(1, 'complete');
        updateAzimuth(0); updateElevation(90);
        if (modalCloseTimer) clearTimeout(modalCloseTimer);
        modalCloseTimer = setTimeout(closeCalibrationModal, 2500);
      }
    }

    if ('req_az' in data) document.getElementById('req-az').textContent = Number(data.req_az).toFixed(1);
    if ('req_el' in data) document.getElementById('req-el').textContent = Number(data.req_el).toFixed(1);
    const badge = document.getElementById('clamped');
    if ('clamped' in data && data.clamped) { badge.style.display = 'inline-block'; } else { badge.style.display = 'none'; }
  });

  form.addEventListener('submit', (e) => { e.preventDefault(); postAction('set'); });

  // Build visuals and config table
  document.addEventListener('DOMContentLoaded', () => {
    buildAzimuthTicks();
    buildElevationTicks();

    try {
      const raw = document.getElementById('cfg-data').textContent || "{}";
      const cfg = JSON.parse(raw);
      const container = document.getElementById('cfg-container');
      const keys = Object.keys(cfg).sort((a,b)=>a.localeCompare(b));
      const tbl = document.createElement('table');
      tbl.className = 'cfg-table';
      const thead = document.createElement('thead');
      thead.innerHTML = '<tr><th>Key</th><th>Value</th></tr>';
      tbl.appendChild(thead);
      const tbody = document.createElement('tbody');
      keys.forEach(k => {
        const tr = document.createElement('tr');
        const tdK = document.createElement('td'); tdK.textContent = k;
        const tdV = document.createElement('td'); tdV.textContent = String(cfg[k]);
        tr.appendChild(tdK); tr.appendChild(tdV);
        tbody.appendChild(tr);
      });
      tbl.appendChild(tbody);
      container.innerHTML = '';
      container.appendChild(tbl);
    } catch (e) {
      console.warn('Failed to render config table:', e);
      const container = document.getElementById('cfg-container');
      container.textContent = 'No config data available.';
    }
  });
  </script>
</body>
</html>
"""
