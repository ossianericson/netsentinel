"""
Network Documentation Generator — one-click "Document My Network".

Produces a self-contained HTML report with:
  1. Network diagram  — PNG exported from the topology widget (optional)
  2. Device inventory — hostname, IP, MAC, vendor, OS, role, last-seen, risk
  3. Open port inventory — per-host port list (if port data supplied)
  4. TLS certificate inventory — expiry dates (if cert data supplied)

Output: get_app_data_dir() / "reports" / "netdoc_<timestamp>.html"

Usage::

    from modules.net_doc_generator import generate_network_doc
    path = generate_network_doc(
        devices      = list_of_device_dicts,
        port_data    = {ip: [port_dict, ...]},   # optional
        cert_data    = [cert_dict, ...],          # optional
        topology_png = Path("..."),               # optional
    )
    import webbrowser; webbrowser.open(path.as_uri())
"""

from __future__ import annotations

import datetime
import html
import json
from pathlib import Path
from string import Template as _Template
from typing import Any, Dict, List, Optional

from modules.utils import get_app_data_dir
from modules.colours import (
    EXPORT_BG, EXPORT_TEXT, EXPORT_HEADING_FG, EXPORT_META,
    EXPORT_RED_BG, EXPORT_AMBER_BG, EXPORT_GREEN_BG,
    EXPORT_RED_FG, EXPORT_AMBER_FG, EXPORT_GREEN_FG,
    EXPORT_CARD, EXPORT_BORDER, EXPORT_ACCENT_FG,
    EXPORT_TH_BG, EXPORT_ROW_HOVER,
    BADGE_HIGH_BG, BADGE_HIGH_FG, BADGE_MEDIUM_BG, BADGE_MEDIUM_FG,
    BADGE_LOW_BG, BADGE_LOW_FG, BADGE_CLEAN_BG, BADGE_CLEAN_FG,
    BADGE_UNKNOWN_BG, BADGE_UNKNOWN_FG,
)


# ── CSS ───────────────────────────────────────────────────────────────────────

_CSS = _Template("""
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: 'Segoe UI', Arial, sans-serif;
  background: $EXPORT_BG;
  color: $EXPORT_TEXT;
  padding: 28px 32px;
  max-width: 1280px;
  margin: 0 auto;
}
h1 { color: $EXPORT_HEADING_FG; margin-bottom: 4px; font-size: 1.7rem; }
.subtitle { color: $EXPORT_META; font-size: 0.9rem; margin-bottom: 28px; }
.section {
  background: $EXPORT_CARD;
  border: 1px solid $EXPORT_BORDER;
  border-radius: 0;
  margin-bottom: 22px;
  overflow: hidden;
}
.section-hdr {
  background: $EXPORT_TH_BG;
  color: $EXPORT_ACCENT_FG;
  font-size: 0.85rem;
  font-weight: bold;
  letter-spacing: 0.5px;
  padding: 8px 14px;
  text-transform: uppercase;
}
.section-body { padding: 14px; }
table { width: 100%; border-collapse: collapse; font-size: 0.83rem; }
th {
  background: $EXPORT_TH_BG;
  color: $EXPORT_ACCENT_FG;
  text-align: left;
  padding: 7px 10px;
  white-space: nowrap;
}
td { padding: 6px 10px; border-bottom: 1px solid $EXPORT_BORDER; vertical-align: top; }
tr:hover td { background: $EXPORT_ROW_HOVER; }
.badge {
  display: inline-block; padding: 1px 7px;
  border-radius: 3px; font-size: 0.72rem; font-weight: bold;
}
.badge.HIGH    { background: $BADGE_HIGH_BG;    color: $BADGE_HIGH_FG; }
.badge.MEDIUM  { background: $BADGE_MEDIUM_BG;  color: $BADGE_MEDIUM_FG; }
.badge.LOW     { background: $BADGE_LOW_BG;     color: $BADGE_LOW_FG; }
.badge.CLEAN   { background: $BADGE_CLEAN_BG;   color: $BADGE_CLEAN_FG; }
.badge.STORM   { background: $BADGE_HIGH_BG;    color: $BADGE_HIGH_FG; }
.badge.WARNING { background: $BADGE_MEDIUM_BG;  color: $BADGE_MEDIUM_FG; }
.badge.UNKNOWN { background: $BADGE_UNKNOWN_BG; color: $BADGE_UNKNOWN_FG; }
.ok   { color: $EXPORT_GREEN_FG; font-weight: bold; }
.warn { color: $EXPORT_AMBER_FG; font-weight: bold; }
.err  { color: $EXPORT_RED_FG;   font-weight: bold; }
img.topo { max-width: 100%; border: 1px solid $EXPORT_BORDER; }
.meta {
  color: $EXPORT_META; font-size: 0.78rem;
  margin-top: 24px; border-top: 1px solid $EXPORT_BORDER; padding-top: 10px;
}
@media print {
  body { background:#fff !important; color:#111 !important; padding: 10px; }
  .section { border-color:#aaa !important; background:#fff !important; }
  .section-hdr { background:#ddd !important; color:#111 !important; }
  th { background:#ddd !important; color:#111 !important; }
  td { border-color:#ccc !important; color:#111 !important; }
  .badge { border:1px solid #999 !important; background:#eee !important; color:#111 !important; }
}
""").substitute(
    EXPORT_BG=EXPORT_BG, EXPORT_TEXT=EXPORT_TEXT,
    EXPORT_HEADING_FG=EXPORT_HEADING_FG, EXPORT_META=EXPORT_META,
    EXPORT_RED_BG=EXPORT_RED_BG, EXPORT_AMBER_BG=EXPORT_AMBER_BG,
    EXPORT_GREEN_BG=EXPORT_GREEN_BG, EXPORT_RED_FG=EXPORT_RED_FG,
    EXPORT_AMBER_FG=EXPORT_AMBER_FG, EXPORT_GREEN_FG=EXPORT_GREEN_FG,
    EXPORT_CARD=EXPORT_CARD, EXPORT_BORDER=EXPORT_BORDER,
    EXPORT_ACCENT_FG=EXPORT_ACCENT_FG, EXPORT_TH_BG=EXPORT_TH_BG,
    EXPORT_ROW_HOVER=EXPORT_ROW_HOVER,
    BADGE_HIGH_BG=BADGE_HIGH_BG, BADGE_HIGH_FG=BADGE_HIGH_FG,
    BADGE_MEDIUM_BG=BADGE_MEDIUM_BG, BADGE_MEDIUM_FG=BADGE_MEDIUM_FG,
    BADGE_LOW_BG=BADGE_LOW_BG, BADGE_LOW_FG=BADGE_LOW_FG,
    BADGE_CLEAN_BG=BADGE_CLEAN_BG, BADGE_CLEAN_FG=BADGE_CLEAN_FG,
    BADGE_UNKNOWN_BG=BADGE_UNKNOWN_BG, BADGE_UNKNOWN_FG=BADGE_UNKNOWN_FG,
)


# ── HTML helpers ──────────────────────────────────────────────────────────────

def _e(v: Any) -> str:
    return html.escape(str(v) if v is not None else "")


def _badge(level: str) -> str:
    lv = (level or "UNKNOWN").upper()
    return f'<span class="badge {lv}">{lv}</span>'


def _section(title: str, body: str) -> str:
    return (
        f'<div class="section">'
        f'<div class="section-hdr">{_e(title)}</div>'
        f'<div class="section-body">{body}</div>'
        f'</div>'
    )


# ── Section generators ────────────────────────────────────────────────────────

def _topology_section(topology_png: Path) -> str:
    """Embed topology PNG as a base64 data URI so the HTML is self-contained."""
    import base64
    try:
        data = topology_png.read_bytes()
        b64  = base64.b64encode(data).decode()
        img  = f'<img class="topo" src="data:image/png;base64,{b64}" alt="Network Topology" />'
    except Exception as exc:
        img  = f'<p class="warn">Could not embed topology image: {_e(exc)}</p>'
    return _section("Network Diagram", img)


def _inventory_section(devices: List[Dict]) -> str:
    if not devices:
        return _section("Device Inventory", "<p>No devices found.</p>")

    rows = ""
    for d in devices:
        def _g(k: str, default: str = "—") -> str:
            v = d.get(k) if isinstance(d, dict) else getattr(d, k, None)
            return _e(v) if v else default
        ip       = _g("ip")
        mac      = _g("mac")
        hostname = _g("hostname")
        vendor   = _g("vendor")
        os_name  = _g("os")
        role     = _g("role")
        last_seen= _g("last_seen")
        risk     = (d.get("risk_level") if isinstance(d, dict) else getattr(d, "risk_level", "UNKNOWN")) or "UNKNOWN"
        rows += (
            f"<tr><td>{ip}</td><td>{mac}</td><td>{hostname}</td>"
            f"<td>{vendor}</td><td>{os_name}</td><td>{role}</td>"
            f"<td>{last_seen}</td><td>{_badge(risk)}</td></tr>"
        )
    table = (
        "<table><thead><tr>"
        "<th>IP</th><th>MAC</th><th>Hostname</th><th>Vendor</th>"
        "<th>OS</th><th>Role</th><th>Last Seen</th><th>Risk</th>"
        f"</tr></thead><tbody>{rows}</tbody></table>"
    )
    return _section(f"Device Inventory ({len(devices)} devices)", table)


def _ports_section(port_data: Dict[str, List[Dict]]) -> str:
    if not port_data:
        return _section("Open Port Inventory", "<p>No port scan data available. Run a SYN port scan first.</p>")

    rows = ""
    for ip, ports in sorted(port_data.items()):
        for p in ports:
            port_num = _e(p.get("port", p.get("portid", "?")))
            proto    = _e(p.get("protocol", p.get("proto", "tcp")))
            service  = _e(p.get("service", p.get("name", "")))
            state    = _e(p.get("state", "open"))
            banner   = _e(p.get("banner", p.get("product", "")))
            rows += (
                f"<tr><td>{_e(ip)}</td><td>{port_num}</td><td>{proto}</td>"
                f"<td>{service}</td><td>{state}</td><td>{banner}</td></tr>"
            )
    total = sum(len(v) for v in port_data.values())
    table = (
        "<table><thead><tr>"
        "<th>IP</th><th>Port</th><th>Proto</th>"
        "<th>Service</th><th>State</th><th>Banner / Product</th>"
        f"</tr></thead><tbody>{rows}</tbody></table>"
    )
    return _section(f"Open Port Inventory ({total} open ports across {len(port_data)} hosts)", table)


def _certs_section(cert_data: List[Dict]) -> str:
    if not cert_data:
        return _section("Certificate Inventory", "<p>No certificate data available. Run TLS certificate monitoring first.</p>")

    now  = datetime.datetime.now(tz=datetime.timezone.utc)
    rows = ""
    for c in cert_data:
        host    = _e(c.get("host", c.get("ip", "?")))
        cn      = _e(c.get("cn", c.get("common_name", "?")))
        issuer  = _e(c.get("issuer", "?"))
        expiry  = c.get("expiry") or c.get("not_after") or ""
        days    = c.get("days_remaining")

        if days is None and expiry:
            try:
                exp_dt = datetime.datetime.fromisoformat(str(expiry).replace("Z", "+00:00"))
                days   = (exp_dt - now).days
            except Exception:
                pass

        if days is not None:
            if days < 0:
                status = f'<span class="err">Expired {abs(days)}d ago</span>'
            elif days <= 30:
                status = f'<span class="warn">Expires in {days}d</span>'
            else:
                status = f'<span class="ok">Valid ({days}d left)</span>'
        else:
            status = "—"

        rows += (
            f"<tr><td>{host}</td><td>{cn}</td><td>{issuer}</td>"
            f"<td>{_e(expiry)}</td><td>{status}</td></tr>"
        )
    table = (
        "<table><thead><tr>"
        "<th>Host</th><th>Common Name</th><th>Issuer</th>"
        "<th>Expiry</th><th>Status</th>"
        f"</tr></thead><tbody>{rows}</tbody></table>"
    )
    return _section(f"Certificate Inventory ({len(cert_data)} certificates)", table)


# ── Public API ────────────────────────────────────────────────────────────────

def generate_network_doc(
    devices:      List[Dict]       = (),
    port_data:    Dict[str, List]  = None,
    cert_data:    List[Dict]       = (),
    topology_png: Optional[Path]   = None,
    title:        str              = "Network Documentation",
) -> Path:
    """
    Generate a self-contained HTML network documentation file.

    Parameters
    ----------
    devices      : list of device dicts from the scan result.
    port_data    : {ip: [port_dict, ...]} from the SYN scanner (optional).
    cert_data    : list of cert dicts from cert_monitor (optional).
    topology_png : path to a PNG exported from TopologyWidget (optional).
    title        : custom report title.

    Returns
    -------
    Path to the generated HTML file in get_app_data_dir() / "reports".
    """
    port_data = port_data or {}
    now_str   = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ts_file   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    sections_html = ""
    if topology_png and topology_png.exists():
        sections_html += _topology_section(topology_png)
    sections_html += _inventory_section(list(devices))
    if port_data:
        sections_html += _ports_section(port_data)
    if cert_data:
        sections_html += _certs_section(list(cert_data))

    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>{_e(title)}</title>
<style>{_CSS}</style>
</head>
<body>
<h1>{_e(title)}</h1>
<p class="subtitle">Generated by NetSentinel &nbsp;·&nbsp; {_e(now_str)}</p>
{sections_html}
<p class="meta">
  {len(list(devices))} device(s) &nbsp;·&nbsp;
  {sum(len(v) for v in port_data.values())} open port(s) &nbsp;·&nbsp;
  {len(list(cert_data))} certificate(s) &nbsp;·&nbsp;
  Generated: {_e(now_str)}
</p>
</body>
</html>"""

    out_dir = get_app_data_dir() / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"netdoc_{ts_file}.html"
    out_path.write_text(html_doc, encoding="utf-8")
    return out_path
