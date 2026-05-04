"""
web_dashboard — generates the self-contained HTML for GET /dashboard.

build_html(api_key) returns a single HTML string with all CSS and JS inlined.
The API key is embedded in the JS so browser fetch calls authenticate without
requiring the user to enter credentials.  The page auto-refreshes every 30 s
and exposes a manual Refresh button.
"""
from __future__ import annotations

import html as _html


def build_html(api_key: str) -> str:
    safe_key = _html.escape(api_key, quote=True)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NetSentinel Dashboard</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  :root {{
    --bg:       #0D1117;
    --surface:  #161B22;
    --border:   #30363D;
    --accent:   #2F81F7;
    --text:     #E6EDF3;
    --muted:    #8B949E;
    --green:    #3FB950;
    --amber:    #E3B341;
    --red:      #F85149;
    --radius:   8px;
  }}
  body {{ background: var(--bg); color: var(--text); font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
  a {{ color: var(--accent); text-decoration: none; }}

  /* ── Layout ── */
  header {{ background: #010409; border-bottom: 1px solid var(--border); padding: 0 24px; display: flex; align-items: center; justify-content: space-between; height: 52px; }}
  header h1 {{ font-size: 16px; font-weight: 600; letter-spacing: .4px; }}
  header .meta {{ display: flex; align-items: center; gap: 16px; color: var(--muted); font-size: 12px; }}
  .countdown {{ font-variant-numeric: tabular-nums; }}
  button#refresh {{ background: var(--surface); border: 1px solid var(--border); color: var(--text); border-radius: var(--radius); padding: 4px 12px; font-size: 12px; cursor: pointer; transition: background .15s; }}
  button#refresh:hover {{ background: #21262D; }}

  main {{ padding: 24px; display: grid; gap: 20px; grid-template-columns: 220px 1fr; grid-template-rows: auto auto; }}
  @media (max-width: 700px) {{ main {{ grid-template-columns: 1fr; }} }}

  /* ── Cards ── */
  .card {{ background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; }}
  .card-header {{ padding: 12px 16px; border-bottom: 1px solid var(--border); font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: .6px; color: var(--muted); }}

  /* ── Grade card ── */
  #grade-card {{ display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 28px 16px; gap: 10px; }}
  .grade-circle {{ width: 96px; height: 96px; border-radius: 50%; border: 3px solid currentColor; display: flex; align-items: center; justify-content: center; font-size: 44px; font-weight: 700; }}
  .grade-score {{ font-size: 15px; font-weight: 600; }}
  .grade-verdict {{ font-size: 12px; color: var(--muted); text-align: center; max-width: 180px; line-height: 1.4; }}
  .grade-ts {{ font-size: 11px; color: var(--muted); }}

  /* Grade colour helpers */
  .g-A {{ color: #4ade80; }} .g-B {{ color: #4ade80; }} .g-C {{ color: var(--amber); }}
  .g-D {{ color: var(--red); }} .g-F {{ color: #ff4444; }} .g-na {{ color: var(--muted); }}

  /* ── Devices card ── */
  #devices-card {{ grid-column: 2; grid-row: 1 / 3; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{ background: #1C2128; color: var(--muted); font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .5px; padding: 8px 12px; text-align: left; border-bottom: 1px solid var(--border); }}
  td {{ padding: 7px 12px; border-bottom: 1px solid #21262D; vertical-align: middle; }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover td {{ background: #1C2128; }}
  .dot {{ display: inline-block; width: 7px; height: 7px; border-radius: 50%; margin-right: 6px; }}
  .dot-up {{ background: var(--green); }} .dot-down {{ background: var(--red); }} .dot-unknown {{ background: var(--muted); }}
  .badge {{ display: inline-block; padding: 1px 7px; border-radius: 20px; font-size: 11px; font-weight: 600; }}
  .badge-auth {{ background: #1a3a1a; color: var(--green); }}
  .badge-unauth {{ background: #3b0000; color: var(--red); }}
  .mono {{ font-family: "SFMono-Regular", Consolas, monospace; font-size: 12px; color: var(--muted); }}

  /* ── Alerts card ── */
  #alerts-card {{ grid-column: 1; grid-row: 2; }}
  .alert-row {{ padding: 9px 16px; border-bottom: 1px solid #21262D; font-size: 12px; }}
  .alert-row:last-child {{ border-bottom: none; }}
  .alert-sev {{ font-weight: 700; font-size: 11px; }}
  .sev-CRITICAL {{ color: #ff4444; }} .sev-HIGH {{ color: var(--red); }}
  .sev-WARNING {{ color: var(--amber); }} .sev-INFO {{ color: var(--accent); }}
  .alert-msg {{ margin-top: 2px; color: var(--text); }}
  .alert-time {{ color: var(--muted); font-size: 11px; }}

  .empty {{ padding: 28px 16px; color: var(--muted); text-align: center; font-size: 13px; }}
  .spinner {{ display: inline-block; width: 14px; height: 14px; border: 2px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: spin .7s linear infinite; vertical-align: middle; margin-right: 6px; }}
  @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
</style>
</head>
<body>
<header>
  <h1>NetSentinel</h1>
  <div class="meta">
    <span>Last updated: <span id="last-updated">—</span></span>
    <span>Auto-refresh in <span class="countdown" id="countdown">30</span>s</span>
    <button id="refresh">Refresh</button>
  </div>
</header>

<main>
  <!-- Grade -->
  <div class="card" id="grade-card-wrap">
    <div class="card-header">Network Grade</div>
    <div id="grade-card"><span class="spinner"></span> Loading…</div>
  </div>

  <!-- Devices -->
  <div class="card" id="devices-card">
    <div class="card-header">Devices (<span id="device-count">…</span>)</div>
    <div id="devices-body"><div class="empty"><span class="spinner"></span> Loading…</div></div>
  </div>

  <!-- Alerts -->
  <div class="card" id="alerts-card">
    <div class="card-header">Recent Alerts (24 h)</div>
    <div id="alerts-body"><div class="empty"><span class="spinner"></span> Loading…</div></div>
  </div>
</main>

<script>
const API_KEY = "{safe_key}";
const HDR = {{"X-API-Key": API_KEY}};
let _timer, _countdown, _countdownVal = 30;

function fmt(ts) {{
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleString();
}}
function ago(ts) {{
  if (!ts) return "—";
  const s = Math.floor(Date.now() / 1000) - ts;
  if (s < 60) return s + "s ago";
  if (s < 3600) return Math.floor(s/60) + "m ago";
  if (s < 86400) return Math.floor(s/3600) + "h ago";
  return Math.floor(s/86400) + "d ago";
}}
function esc(s) {{
  return String(s ?? "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}}

async function loadGrade() {{
  const r = await fetch("/grade", {{headers: HDR}});
  const d = await r.json();
  const el = document.getElementById("grade-card");
  if (!d.grade) {{
    el.innerHTML = `<div class="grade-circle g-na" style="border-color:var(--muted)">—</div>
      <div class="grade-verdict">No grade yet — run Network Grade in the app</div>`;
    return;
  }}
  const gc = ["A","B"].includes(d.grade) ? "g-A" : d.grade === "C" ? "g-C" : d.grade === "D" ? "g-D" : d.grade === "F" ? "g-F" : "g-na";
  el.innerHTML = `
    <div class="grade-circle ${{gc}}">${{esc(d.grade)}}</div>
    <div class="grade-score ${{gc}}">${{d.score !== null ? Math.round(d.score) + " / 100" : ""}}</div>
    <div class="grade-verdict">${{esc(d.verdict)}}</div>
    <div class="grade-ts">Graded ${{ago(d.ts)}}</div>`;
}}

async function loadDevices() {{
  const r = await fetch("/devices", {{headers: HDR}});
  const devs = await r.json();
  document.getElementById("device-count").textContent = devs.length;
  const el = document.getElementById("devices-body");
  if (!devs.length) {{ el.innerHTML = `<div class="empty">No devices found — run a scan first</div>`; return; }}
  const rows = devs.map(d => {{
    const dot = d.last_seen && (Date.now()/1000 - d.last_seen < 600)
      ? `<span class="dot dot-up"></span>` : `<span class="dot dot-unknown"></span>`;
    const auth = d.is_authorized
      ? `<span class="badge badge-auth">authorized</span>`
      : `<span class="badge badge-unauth">unknown</span>`;
    const name = esc(d.custom_name || d.hostname || "—");
    return `<tr>
      <td>${{dot}}${{name}}</td>
      <td class="mono">${{esc(d.ip || "—")}}</td>
      <td class="mono">${{esc(d.mac || "—")}}</td>
      <td>${{esc(d.vendor || "—")}}</td>
      <td>${{auth}}</td>
      <td class="mono" style="color:var(--muted)">${{ago(d.last_seen)}}</td>
    </tr>`;
  }}).join("");
  el.innerHTML = `<table>
    <thead><tr><th>Name / Host</th><th>IP</th><th>MAC</th><th>Vendor</th><th>Status</th><th>Last seen</th></tr></thead>
    <tbody>${{rows}}</tbody>
  </table>`;
}}

async function loadAlerts() {{
  const r = await fetch("/alerts?hours=24", {{headers: HDR}});
  const alerts = await r.json();
  const el = document.getElementById("alerts-body");
  if (!alerts.length) {{ el.innerHTML = `<div class="empty">No alerts in the last 24 h</div>`; return; }}
  el.innerHTML = alerts.slice(0, 20).map(a => `
    <div class="alert-row">
      <div><span class="alert-sev sev-${{esc(a.severity || "WARNING")}}">${{esc(a.severity || "WARNING")}}</span>
        <span class="alert-time" style="margin-left:8px">${{ago(a.ts)}}</span></div>
      <div class="alert-msg">${{esc(a.message || a.rule_name || "—")}}</div>
    </div>`).join("");
}}

async function refresh() {{
  document.getElementById("last-updated").textContent = new Date().toLocaleTimeString();
  await Promise.all([loadGrade(), loadDevices(), loadAlerts()]);
}}

function startCountdown() {{
  clearInterval(_countdown);
  _countdownVal = 30;
  document.getElementById("countdown").textContent = _countdownVal;
  _countdown = setInterval(() => {{
    _countdownVal--;
    document.getElementById("countdown").textContent = _countdownVal;
    if (_countdownVal <= 0) {{ refresh(); startCountdown(); }}
  }}, 1000);
}}

document.getElementById("refresh").addEventListener("click", () => {{ refresh(); startCountdown(); }});

refresh();
startCountdown();
</script>
</body>
</html>"""
