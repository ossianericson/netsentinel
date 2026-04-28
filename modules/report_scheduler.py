"""
ReportScheduler — generates periodic status reports from MetricStore data (T2#9).

Builds a self-contained HTML summary covering:
  • Fleet availability (uptime % per device for 24h / 7d / 30d)
  • TLS certificate status
  • Service heartbeat status
  • Recent device events (last 24h)

Can generate on demand (generate_now) or be driven by a QTimer/worker.

Architecture rules observed:
  • Pure Python — no PyQt6, no ui/ imports (ARCH RULE 3).
  • MetricStore injected as constructor parameter.
  • Output is a Path; callers decide where to put it.
"""

from __future__ import annotations

import datetime
import html
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from modules.metric_store import MetricStore


# ── Minimal CSS shared with this module (light-mode, print-friendly) ─────────

_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Segoe UI', Arial, sans-serif; background: #F4F4F4;
       color: #1A1A2E; padding: 24px; max-width: 1200px; margin: 0 auto; }
h1  { color: #1A3A5C; font-size: 18px; margin-bottom: 4px; }
h2  { color: #1A3A5C; font-size: 14px; margin: 18px 0 8px; }
.subtitle { color: #5A6A7A; font-size: 11px; margin-bottom: 20px; }
.kpi-row { display: flex; gap: 12px; margin-bottom: 20px; flex-wrap: wrap; }
.kpi { background: #fff; border: 1px solid #D4D4D4; border-left: 3px solid #0078D4;
       padding: 8px 14px; min-width: 120px; }
.kpi .label { font-size: 9px; font-weight: bold; color: #5A6A7A; text-transform: uppercase; }
.kpi .value { font-size: 22px; font-weight: bold; color: #1A1A2E; }
.section { background: #fff; border: 1px solid #D4D4D4; margin-bottom: 14px; }
.section-title { background: #fff; border-bottom: 1px solid #ECECEC;
                 padding: 6px 12px; font-size: 13px; font-weight: bold; color: #1A1A2E; }
table { width: 100%; border-collapse: collapse; font-size: 11px; }
th { background: #1A3A5C; color: #fff; text-align: left;
     padding: 4px 8px; font-size: 11px; font-weight: bold; }
td { padding: 4px 8px; border-bottom: 1px solid #EAEAEA; vertical-align: middle; }
tr:nth-child(even) td { background: #F7F9FC; }
tr:hover td { background: #EEF4FF; }
.up     { color: #2E7D32; font-weight: bold; }
.down   { color: #D93025; font-weight: bold; }
.warn   { color: #F59E0B; font-weight: bold; }
.meta   { color: #9BA8B4; font-size: 10px; margin-top: 24px;
          border-top: 1px solid #D4D4D4; padding-top: 10px; }
@media print {
  body { background: #fff !important; padding: 12px; }
}
"""


# ── Report config ─────────────────────────────────────────────────────────────

@dataclass
class ReportConfig:
    """Configuration for a scheduled report."""
    output_dir:     Path         = field(default_factory=lambda: Path.home() / "NetSentinel-Reports")
    interval_hours: float        = 24.0     # 24 = daily, 168 = weekly
    formats:        List[str]    = field(default_factory=lambda: ["html"])
    enabled:        bool         = True
    max_reports:    int          = 30       # keep last N reports per format


# ── HTML generation ───────────────────────────────────────────────────────────

def generate_status_report(store: MetricStore) -> str:
    """
    Build a self-contained HTML status report from MetricStore data.
    Returns the HTML string.
    """
    ts_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ── Uptime table ──────────────────────────────────────────────────────────
    uptime_rows = store.query_uptime_table()

    total_devices = len(uptime_rows)
    healthy = degraded = critical = 0
    uptime_html_rows = ""
    for r in uptime_rows:
        pct_24  = r.get("24.0",  100.0)
        pct_7d  = r.get("168.0", 100.0)
        pct_30d = r.get("720.0", 100.0)
        worst   = min(pct_24, pct_7d, pct_30d)
        cls     = "up" if worst >= 99.0 else ("warn" if worst >= 95.0 else "down")
        if worst >= 99.0:
            healthy += 1
        elif worst >= 95.0:
            degraded += 1
        else:
            critical += 1
        hostname = html.escape(r.get("hostname") or "—")
        ip       = html.escape(r["ip"])
        uptime_html_rows += (
            f"<tr><td>{ip}</td><td>{hostname}</td>"
            f'<td class="{cls}">{pct_24:.1f}%</td>'
            f'<td class="{cls}">{pct_7d:.1f}%</td>'
            f'<td class="{cls}">{pct_30d:.1f}%</td></tr>'
        )
    uptime_section = (
        "<table><thead><tr>"
        "<th>IP</th><th>Hostname</th><th>24H</th><th>7D</th><th>30D</th>"
        f"</tr></thead><tbody>{uptime_html_rows}</tbody></table>"
        if uptime_html_rows else "<p style='padding:8px;color:#9BA8B4'>No availability data recorded yet.</p>"
    )

    # ── TLS cert status ───────────────────────────────────────────────────────
    cert_rows = store.query_cert_status(hours=168.0)
    cert_ok = cert_expiring = cert_expired = cert_error = 0
    cert_html_rows = ""
    for r in cert_rows:
        if r.error:
            cls = "warn"; status = "UNREACHABLE"; cert_error += 1
        elif r.is_expired:
            cls = "down"; status = "EXPIRED"; cert_expired += 1
        elif r.days_remaining is not None and r.days_remaining < 30:
            cls = "warn"; status = f"EXPIRING ({r.days_remaining}d)"; cert_expiring += 1
        else:
            cls = "up"; status = "OK"; cert_ok += 1
        cert_html_rows += (
            f'<tr><td>{html.escape(r.host)}</td><td>{r.port}</td>'
            f'<td class="{cls}">{status}</td>'
            f'<td>{html.escape(r.not_after or "—")}</td>'
            f'<td>{html.escape(r.issuer or "—")}</td></tr>'
        )
    cert_section = (
        "<table><thead><tr>"
        "<th>Host</th><th>Port</th><th>Status</th><th>Expires</th><th>Issuer</th>"
        f"</tr></thead><tbody>{cert_html_rows}</tbody></table>"
        if cert_html_rows else "<p style='padding:8px;color:#9BA8B4'>No certificate checks recorded yet.</p>"
    )

    # ── Service heartbeat ─────────────────────────────────────────────────────
    svc_rows = store.query_service_status(hours=24.0)
    svc_up = svc_down = 0
    svc_html_rows = ""
    for r in svc_rows:
        if r.up:
            cls = "up"; status = "UP"; svc_up += 1
        else:
            cls = "down"; status = "DOWN"; svc_down += 1
        rtt = f"{r.rtt_ms:.1f} ms" if r.rtt_ms is not None else "—"
        svc_html_rows += (
            f'<tr><td>{html.escape(r.label or f"{r.host}:{r.port}")}</td>'
            f'<td>{html.escape(r.host)}</td><td>{r.port}</td>'
            f'<td class="{cls}">{status}</td><td>{rtt}</td></tr>'
        )
    svc_section = (
        "<table><thead><tr>"
        "<th>Service</th><th>Host</th><th>Port</th><th>Status</th><th>RTT</th>"
        f"</tr></thead><tbody>{svc_html_rows}</tbody></table>"
        if svc_html_rows else "<p style='padding:8px;color:#9BA8B4'>No service checks recorded yet.</p>"
    )

    # ── Recent device events (last 24h) ───────────────────────────────────────
    events = store.query_device_events(hours=24.0)[:50]   # cap at 50
    event_html_rows = ""
    for e in events:
        when = datetime.datetime.fromtimestamp(e.ts).strftime("%H:%M:%S")
        cls  = {"JOINED": "up", "LEFT": "warn", "DOWN": "down",
                "DEGRADED": "warn", "RECOVERED": "up"}.get(e.event_type, "")
        event_html_rows += (
            f'<tr><td>{when}</td>'
            f'<td class="{cls}">{html.escape(e.event_type)}</td>'
            f'<td>{html.escape(e.ip)}</td>'
            f'<td>{html.escape(e.mac or "—")}</td>'
            f'<td>{html.escape(e.detail or "—")}</td></tr>'
        )
    event_section = (
        "<table><thead><tr>"
        "<th>Time</th><th>Event</th><th>IP</th><th>MAC</th><th>Detail</th>"
        f"</tr></thead><tbody>{event_html_rows}</tbody></table>"
        if event_html_rows else "<p style='padding:8px;color:#9BA8B4'>No device events in the last 24 hours.</p>"
    )

    # ── Fleet average uptime ──────────────────────────────────────────────────
    if uptime_rows:
        fleet_avg = sum(r.get("24.0", 100.0) for r in uptime_rows) / len(uptime_rows)
        fleet_str = f"{fleet_avg:.1f}%"
    else:
        fleet_str = "—"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>NetSentinel — Status Report {ts_str}</title>
<style>{_CSS}</style>
</head>
<body>
<h1>NetSentinel — Status Report</h1>
<p class="subtitle">Generated {ts_str}</p>

<div class="kpi-row">
  <div class="kpi"><div class="label">Devices Monitored</div><div class="value">{total_devices}</div></div>
  <div class="kpi"><div class="label">Healthy (≥99%)</div><div class="value">{healthy}</div></div>
  <div class="kpi"><div class="label">Degraded</div><div class="value">{degraded}</div></div>
  <div class="kpi"><div class="label">Critical (&lt;95%)</div><div class="value">{critical}</div></div>
  <div class="kpi"><div class="label">Fleet Avg Uptime</div><div class="value">{fleet_str}</div></div>
  <div class="kpi"><div class="label">Certs OK</div><div class="value">{cert_ok}</div></div>
  <div class="kpi"><div class="label">Services Up</div><div class="value">{svc_up}</div></div>
  <div class="kpi"><div class="label">Services Down</div><div class="value">{svc_down}</div></div>
</div>

<div class="section">
  <div class="section-title">Device Uptime</div>
  {uptime_section}
</div>

<div class="section">
  <div class="section-title">TLS Certificate Status</div>
  {cert_section}
</div>

<div class="section">
  <div class="section-title">Service Heartbeat Status</div>
  {svc_section}
</div>

<div class="section">
  <div class="section-title">Recent Device Events (last 24h)</div>
  {event_section}
</div>

<p class="meta">NetSentinel v1.2.0 &mdash; report generated {ts_str}</p>
</body>
</html>"""


# ── Scheduler ─────────────────────────────────────────────────────────────────

class ReportScheduler:
    """
    Generates periodic HTML status reports from MetricStore data.

    Parameters
    ----------
    store : MetricStore
        Injected MetricStore singleton.
    config : ReportConfig
        Schedule and output settings. Can be replaced via set_config().
    on_saved : callable | None
        Called with the Path of the saved report after each successful generation.
    """

    def __init__(
        self,
        store: MetricStore,
        config: Optional[ReportConfig] = None,
        on_saved=None,
    ):
        self._store    = store
        self._config   = config or ReportConfig()
        self._on_saved = on_saved
        self._last_run: float = 0.0

    def set_config(self, config: ReportConfig) -> None:
        self._config = config

    def get_config(self) -> ReportConfig:
        return self._config

    def is_due(self) -> bool:
        """Return True if the interval has elapsed since the last run."""
        if not self._config.enabled:
            return False
        elapsed = time.time() - self._last_run
        return elapsed >= self._config.interval_hours * 3600

    def generate_now(self) -> List[Path]:
        """
        Generate reports in all configured formats immediately.
        Returns a list of saved file paths.
        Creates the output directory if it does not exist.
        """
        if not self._config.enabled:
            return []

        out_dir = Path(self._config.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        ts_tag   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        saved: List[Path] = []

        for fmt in self._config.formats:
            fmt = fmt.lower()
            if fmt == "html":
                content = generate_status_report(self._store)
                path    = out_dir / f"netsentinel-report-{ts_tag}.html"
                path.write_text(content, encoding="utf-8")
                saved.append(path)
            # (csv / json formats can be added here in future)

        self._last_run = time.time()
        self._prune_old(out_dir)

        for path in saved:
            if self._on_saved:
                self._on_saved(path)

        return saved

    def run_if_due(self) -> List[Path]:
        """Generate reports only if the schedule interval has elapsed."""
        if self.is_due():
            return self.generate_now()
        return []

    # ── Housekeeping ──────────────────────────────────────────────────────────

    def _prune_old(self, out_dir: Path) -> None:
        """Delete oldest HTML reports beyond max_reports."""
        reports = sorted(out_dir.glob("netsentinel-report-*.html"))
        excess = len(reports) - self._config.max_reports
        for path in reports[:excess]:
            try:
                path.unlink()
            except OSError:
                pass
