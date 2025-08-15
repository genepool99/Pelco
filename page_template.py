"""Peltrack web UI HTML template (compass icon, fixed elevation labels, above-the-fold)."""

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
    href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Ccircle cx='32' cy='32' r='30' fill='%230b1220'/%3E%3Ccircle cx='32' cy='32' r='26' fill='none' stroke='%23e5e7eb' stroke-width='2'/%3E%3Cg stroke='%23e5e7eb' stroke-width='2'%3E%3Cline x1='32' y1='6' x2='32' y2='12'/%3E%3Cline x1='32' y1='52' x2='32' y2='58'/%3E%3Cline x1='6' y1='32' x2='12' y2='32'/%3E%3Cline x1='52' y1='32' x2='58' y2='32'/%3E%3C/g%3E%3Cpolygon points='32,18 36,32 28,32' fill='%23ef4444'/%3E%3Cpolygon points='32,46 36,32 28,32' fill='%239ca3af'/%3E%3C/svg%3E" />

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
      --dial: 280px;      /* azimuth dial size */
      --bar-h: 300px;     /* elevation bar height */
      --btn-h: 44px;      /* larger touch area */
      --btn-font: 16px;
      --input-font: 18px;

      /* Button colors */
      --primary: #0ea5e9;   /* Send */
      --primary-fg: #fff;
      --accent: #6366f1;    /* Return-to actions */
      --accent-fg: #fff;
      --neutral: #e5e7eb;   /* Reset, Demo */
      --neutral-fg: #111827;
      --secondary: #f3f4f6; /* Nudges */
      --secondary-fg: #111827;
      --warning: #f59e0b;   /* Calibrate */
      --warning-fg: #111827;
      --danger: #ef4444;    /* Stop */
      --danger-fg: #fff;
    }

    @media (max-width: 480px) {
      :root { --dial: 220px; --bar-h: 240px; --btn-font: 16px; --btn-h: 46px; }
    }

    * { box-sizing: border-box; }
    html, body { height: 100%; }
    body { margin: 0; font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; color: var(--fg); background: var(--bg); }

    /* Shell */
    .wrap { display: grid; gap: var(--gap); padding: var(--gap); max-width: 1200px; margin: 0 auto; }
    header { display: grid; gap: 10px; }
    .brand { display: flex; align-items: center; gap: 12px; }
    .brand-icon { width: 56px; height: 56px; flex: 0 0 auto; }
    .brand-text .title { font-size: 28px; font-weight: 800; line-height: 1.1; }
    .brand-text .subtitle { font-size: 14px; color: var(--muted); margin-top: 2px; }

    .status-line { display: flex; flex-wrap: wrap; gap: 10px 16px; align-items: baseline; }
    .muted { color: var(--muted); }

    .badge {
      display: inline-block;
      padding: 4px 8px;
      border-radius: 999px;
      background: #fde68a;
      color: #7c2d12;
      border: 1px solid #f59e0b;
      font-size: 12px;
      font-weight: 600;
    }

    /* Above-the-fold grid: controls left, gauges right */
    .af-grid { display: grid; grid-template-columns: 1.3fr 1fr; gap: var(--gap); align-items: start; }
    @media (max-width: 1000px) { .af-grid { grid-template-columns: 1fr; } }

    /* Cards */
    .card { background: #fff; border: 1px solid var(--border); border-radius: var(--radius); padding: var(--card-pad); }
    .ctrl-card { display: grid; gap: var(--gap); }

    /* Controls */
    .row { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: var(--gap); }
    .row-tight { grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: var(--gap); }

    label { display: grid; grid-template-columns: 1fr auto; align-items: center; gap: 8px; font-size: 15px; }
    input[type=number] {
      width: 140px; padding: 10px 12px; border: 1px solid var(--border);
      border-radius: 10px; font-size: var(--input-font);
    }
    input[type=number]::-webkit-outer-spin-button, input[type=number]::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }

    .btn {
      cursor: pointer; height: var(--btn-h); border: 1px solid var(--border);
      background: #fff; border-radius: 10px; font-size: var(--btn-font); padding: 0 14px;
    }
    .btn:hover { filter: brightness(0.98); }

    .btn-primary { background: var(--primary); color: var(--primary-fg); border-color: var(--primary); }
    .btn-accent  { background: var(--accent);  color: var(--accent-fg);  border-color: var(--accent); }
    .btn-warning { background: var(--warning); color: var(--warning-fg); border-color: var(--warning); }
    .btn-danger  { background: var(--danger);  color: var(--danger-fg);  border-color: var(--danger); }
    .btn-neutral { background: var(--neutral); color: var(--neutral-fg); border-color: var(--neutral); }
    .btn-secondary { background: var(--secondary); color: var(--secondary-fg); border-color: var(--border); }
    .btn-block { width: 100%; }

    /* Gauges */
    .gauges { display: grid; gap: var(--gap); }
    .readouts { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--gap); }
    .readout { text-align: center; padding: 10px; border: 1px solid var(--border); border-radius: var(--radius); background: #fff; }
    .readout .big { font-size: 28px; font-weight: 700; }

    .azimuth { position: relative; width: var(--dial); height: var(--dial); border: 1px solid var(--border); border-radius: 50%; background: #fff; margin: 0 auto; }
    .azimuth svg { width: 100%; height: 100%; display: block; }
    .needle { stroke: #e31b4b; stroke-width: 2; }
    .center { fill: #000; }

    .elevation { display: grid; justify-items: center; align-content: start; gap: 6px; }
    /* Wider SVG + overflow visible so labels never clip */
    .elevation svg { width: 140px; height: var(--bar-h); display: block; overflow: visible; }

    /* Progress bar */
    .progress { width: 100%; height: 12px; background: #e5e7eb; border: 1px solid #cbd5e1; border-radius: 999px; overflow: hidden; }
    .progress > .bar { width: 0%; height: 100%; background: #0ea5e9; transition: width 0.2s ease; }
    #cal-stage-line { font-size: 13px; color: #334155; }

    /* Blocking modal for calibration */
    .modal {
      position: fixed; inset: 0; background: rgba(0,0,0,0.45);
      display: none; align-items: center; justify-content: center; z-index: 9999;
    }
    .modal.open { display: flex; }
    .modal-card {
      width: min(520px, 92vw); max-height: 80vh; overflow: auto;
      background: #fff; border-radius: 12px; border: 1px solid var(--border);
      padding: 16px; display: grid; gap: 10px;
    }
    .log { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 13px; white-space: pre-wrap; background: #f8fafc; border: 1px solid var(--border); padding: 10px; border-radius: 8px; }

    .footer { text-align: center; font-size: 12px; color: var(--muted); }
    .dimmed * { pointer-events: none; }
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <!-- Brand with compass icon -->
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
        <!-- Optional: requested vs actual if backend provides req_* / clamped -->
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

        <!-- Primary / safety / return-to / config-affecting -->
        <div class="row">
          <button type="button" class="btn btn-primary" onclick="postAction('set')">Send</button>
          <button type="button" class="btn btn-neutral" onclick="postAction('reset')">Reset Pos</button>
          <button type="button" class="btn btn-warning" onclick="startCalibration()">Calibrate</button>
          <button type="button" class="btn btn-accent" onclick="postAction('horizon')">EL → 90°</button>
          <button type="button" class="btn btn-accent" onclick="postAction('az_zero')">AZ → 0°</button>
          <button type="button" class="btn btn-danger" onclick="postAction('stop')">STOP</button>
        </div>

        <!-- Nudges / demo -->
        <div class="row row-tight">
          <button type="button" class="btn btn-secondary" onclick="postAction('nudge_left')">AZ ← small</button>
          <button type="button" class="btn btn-secondary" onclick="postAction('nudge_right')">AZ → small</button>
          <button type="button" class="btn btn-secondary" onclick="postAction('nudge_left_big')">AZ ⇤ big</button>
          <button type="button" class="btn btn-secondary" onclick="postAction('nudge_right_big')">AZ ⇥ big</button>
          <button type="button" class="btn btn-secondary" onclick="postAction('nudge_up')">EL ↑ small</button>
          <button type="button" class="btn btn-secondary" onclick="postAction('nudge_down')">EL ↓ small</button>
          <button type="button" class="btn btn-secondary" onclick="postAction('nudge_up_big')">EL ↑↑ big</button>
          <button type="button" class="btn btn-secondary" onclick="postAction('nudge_down_big')">EL ↓↓ big</button>
          <button type="button" class="btn btn-neutral" onclick="postAction('demo')">Run Demo</button>
        </div>
      </form>

      <!-- Monitoring -->
      <div class="gauges">
        <div class="readouts">
          <div class="readout"><div>Azimuth</div><div class="big" id="az-display">{{caz}}</div></div>
          <div class="readout"><div>Elevation</div><div class="big" id="el-display">{{cel}}</div></div>
        </div>

        <div class="card" style="display:grid; grid-template-columns: var(--dial) 160px; gap: var(--gap); justify-content:center;">
          <!-- Azimuth Dial -->
          <div class="azimuth" aria-label="Azimuth Dial">
            <svg id="az-svg" viewBox="0 0 300 300" preserveAspectRatio="xMidYMid meet">
              <g id="az-ticks"></g>
              <line id="az-line" class="needle" x1="150" y1="150" x2="150" y2="50"/>
              <circle class="center" cx="150" cy="150" r="3"/>
            </svg>
          </div>

          <!-- Elevation Panel (wider so labels don't clip) -->
          <div class="elevation" aria-label="Elevation Bar" style="align-items:center;">
            <svg id="el-svg" width="140" height="300" viewBox="0 0 140 300">
              <rect x="30" y="0" width="60" height="300" fill="#f8fafc" stroke="#cbd5e1"/>
              <rect id="el-fill" x="30" y="0" width="60" height="0" fill="#a7d3ff"/>
              <line id="el-line" x1="30" x2="90" y1="150" y2="150" stroke="#1e66f5" stroke-width="2"/>
              <g id="el-ticks"></g>
            </svg>
          </div>
        </div>
      </div>
    </div>

    <div class="footer">Peltrack - Avi Solomon [AE7ET]</div>
  </div>

  <!-- Blocking Modal -->
  <div id="cal-modal" class="modal" role="dialog" aria-modal="true" aria-labelledby="cal-title">
    <div class="modal-card">
      <h2 id="cal-title">Calibration in progress…</h2>
      <div class="progress" aria-hidden="true"><div id="cal-bar" class="bar"></div></div>
      <div id="cal-stage-line" aria-live="polite"></div>
      <div id="cal-log" class="log"></div>
      <button type="button" class="btn btn-neutral btn-block" onclick="closeCalibrationModal()">Hide</button>
    </div>
  </div>

  <script>
  if (window.history.replaceState) {
    window.history.replaceState(null, null, window.location.href);
  }

  const form = document.getElementById('mainForm');
  const actionInput = document.getElementById('action');
  const azInput = document.querySelector('input[name="azimuth"]');
  const elInput = document.querySelector('input[name="elevation"]');
  const modal = document.getElementById('cal-modal');
  const logEl = document.getElementById('cal-log');
  const bar = document.getElementById('cal-bar');
  const stageLine = document.getElementById('cal-stage-line');

  function setAction(name) { actionInput.value = name; }
  async function postAction(name) {
    setAction(name);
    try {
      const fd = new FormData(form);
      await fetch('/', { method: 'POST', body: fd, credentials: 'same-origin' });
      // Socket "position" event will update UI
    } catch (err) {
      console.error('POST failed', err);
    }
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
  function startCalibration() {
    openCalibrationModal();
    postAction('calibrate');
  }

  function setCalProgress(pct, stage) {
    const clamped = Math.max(0, Math.min(1, Number(pct) || 0));
    bar.style.width = Math.round(clamped * 100) + '%';
    if (stage) stageLine.textContent = 'Stage: ' + stage;
    if (!modal.classList.contains('open')) openCalibrationModal();
  }

  // Build compass ticks/labels (every 10°, label every 30° + N/E/S/W)
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
    // Cardinal letters
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
    // Outer ring
    const ring = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    ring.setAttribute("cx", 150); ring.setAttribute("cy", 150); ring.setAttribute("r", 145);
    ring.setAttribute("fill", "none"); ring.setAttribute("stroke", "#cbd5e1"); ring.setAttribute("stroke-width", "1");
    g.appendChild(ring);
  }

  // Elevation ticks: 45..135 step 15, labels on right (wider SVG, no clipping)
  function buildElevationTicks() {
    const g = document.getElementById('el-ticks');
    const full = 300;
    const x1 = 100, x2 = 110;          // tick lines inside 140-wide viewBox
    for (let deg = 45; deg <= 135; deg += 15) {
      const pct = 1 - (deg - 45) / 90;   // 1 at 45°, 0 at 135°
      const y = full - pct * full;
      const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
      line.setAttribute("x1", x1); line.setAttribute("x2", x2);
      line.setAttribute("y1", y);  line.setAttribute("y2", y);
      line.setAttribute("stroke", "#94a3b8"); line.setAttribute("stroke-width", "2");
      g.appendChild(line);

      const t = document.createElementNS("http://www.w3.org/2000/svg", "text");
      t.setAttribute("x", x2 + 6); t.setAttribute("y", y + 4);
      t.setAttribute("font-size", "10");
      t.setAttribute("text-anchor", "start");
      t.textContent = String(deg) + "°";
      g.appendChild(t);
    }
  }

  // Visual updates
  function updateAzimuth(angle) {
    const radians = angle * Math.PI / 180;
    const len = 100; // SVG units
    const x = 150 + len * Math.sin(radians);
    const y = 150 - len * Math.cos(radians);
    const line = document.getElementById('az-line');
    line.setAttribute('x2', x);
    line.setAttribute('y2', y);
    document.getElementById('az').textContent = angle.toFixed(1);
    document.getElementById('az-display').textContent = angle.toFixed(1);
    azInput.value = angle.toFixed(1); // keep input synced
  }

  function updateElevation(el) {
    const clamped = Math.max(45, Math.min(135, el));
    const full = 300; // SVG height
    const pct = 1 - (clamped - 45) / 90; // 1 @45°, 0 @135°
    const h = pct * full;
    const y = full - h;
    document.getElementById('el-fill').setAttribute('y', y);
    document.getElementById('el-fill').setAttribute('height', h);
    document.getElementById('el-line').setAttribute('y1', y);
    document.getElementById('el-line').setAttribute('y2', y);
    document.getElementById('el').textContent = el.toFixed(1);
    document.getElementById('el-display').textContent = el.toFixed(1);
    elInput.value = el.toFixed(1); // keep input synced
  }

  // Socket wiring
  const socket = io();
  socket.on('position', (data) => {
    if ('az' in data) updateAzimuth(data.az);
    if ('el' in data) updateElevation(data.el);

    if ('cal_progress' in data) {
      setCalProgress(data.cal_progress, data.cal_stage || '');
    }

    if ('msg' in data) {
      document.getElementById('msg').textContent = data.msg;
      // Calibration modal logging + forced sync on completion (fix EL=0 bug)
      if (String(data.msg).startsWith('Calibrating:')) {
        openCalibrationModal();
        logEl.textContent += (data.msg + "\\n");
      } else if (String(data.msg).includes('Calibration complete')) {
        logEl.textContent += (data.msg + "\\n");
        setCalProgress(1, 'complete');
        // Force-sync EL=90° and AZ=0° in case any client missed the final state
        updateAzimuth(0);
        updateElevation(90);
        if (modalCloseTimer) clearTimeout(modalCloseTimer);
        modalCloseTimer = setTimeout(closeCalibrationModal, 2500);
      }
    }

    // Optional: show requested/clamped info if backend provides it
    if ('req_az' in data) document.getElementById('req-az').textContent = Number(data.req_az).toFixed(1);
    if ('req_el' in data) document.getElementById('req-el').textContent = Number(data.req_el).toFixed(1);
    const badge = document.getElementById('clamped');
    if ('clamped' in data && data.clamped) { badge.style.display = 'inline-block'; } else { badge.style.display = 'none'; }
  });

  // Intercept Enter on inputs to use fetch
  form.addEventListener('submit', (e) => { e.preventDefault(); postAction('set'); });

  // Build tick marks once
  document.addEventListener('DOMContentLoaded', () => {
    buildAzimuthTicks();
    buildElevationTicks();
  });
  </script>
</body>
</html>
"""
