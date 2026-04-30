"""
Report Exporter — generates a self-contained HTML report of all scan findings.
Opens in any browser with no external dependencies.
"""

import datetime
import html
import json
from pathlib import Path
from string import Template as _Template
from typing import Any, Dict, Optional

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

_CSS = _Template("""
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Segoe UI', Arial, sans-serif; background: $EXPORT_BG; color: $EXPORT_TEXT; padding: 24px; }
h1 { color: $EXPORT_HEADING_FG; margin-bottom: 4px; font-size: 1.8rem; }
.subtitle { color: $EXPORT_META; font-size: 0.9rem; margin-bottom: 24px; }
.verdict-box { border-radius: 12px; padding: 18px 22px; margin-bottom: 24px; }
.verdict-box.red    { background: $EXPORT_RED_BG; border: 2px solid $EXPORT_RED_FG; }
.verdict-box.amber  { background: $EXPORT_AMBER_BG; border: 2px solid $EXPORT_AMBER_FG; }
.verdict-box.green  { background: $EXPORT_GREEN_BG; border: 2px solid $EXPORT_GREEN_FG; }
.verdict-box h2 { font-size: 1.1rem; margin-bottom: 8px; }
.verdict-box.red h2    { color: $EXPORT_RED_FG; }
.verdict-box.amber h2  { color: $EXPORT_AMBER_FG; }
.verdict-box.green h2  { color: $EXPORT_GREEN_FG; }
.verdict-box p { font-size: 0.95rem; line-height: 1.6; }
.module { background: $EXPORT_CARD; border-radius: 10px; padding: 18px; margin-bottom: 18px; border: 1px solid $EXPORT_BORDER; }
.module h3 { font-size: 1rem; color: $EXPORT_ACCENT_FG; margin-bottom: 12px; }
table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
th { background: $EXPORT_TH_BG; color: $EXPORT_ACCENT_FG; text-align: left; padding: 8px 10px; }
td { padding: 7px 10px; border-bottom: 1px solid $EXPORT_TH_BG; vertical-align: top; }
tr:hover td { background: $EXPORT_ROW_HOVER; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 20px; font-size: 0.75rem; font-weight: bold; }
.badge.HIGH   { background: $BADGE_HIGH_BG; color: $BADGE_HIGH_FG; }
.badge.MEDIUM { background: $BADGE_MEDIUM_BG; color: $BADGE_MEDIUM_FG; }
.badge.LOW    { background: $BADGE_LOW_BG; color: $BADGE_LOW_FG; }
.badge.CLEAN  { background: $BADGE_CLEAN_BG; color: $BADGE_CLEAN_FG; }
.badge.STORM  { background: $BADGE_HIGH_BG; color: $BADGE_HIGH_FG; }
.badge.WARNING { background: $BADGE_MEDIUM_BG; color: $BADGE_MEDIUM_FG; }
.badge.UNKNOWN { background: $BADGE_UNKNOWN_BG; color: $BADGE_UNKNOWN_FG; }
.meta { color: $EXPORT_META; font-size: 0.8rem; margin-top: 24px; border-top: 1px solid $EXPORT_TH_BG; padding-top: 12px; }
@media print {
  body { background: #fff !important; color: #111 !important; }
  .module, .verdict-box { border-color: #999 !important; background: #fff !important; }
  h1, h3, .module h3 { color: #111 !important; }
  .badge { border: 1px solid #999 !important; background: #eee !important; color: #111 !important; }
  th { background: #ddd !important; color: #111 !important; }
  td { border-bottom: 1px solid #ccc !important; color: #111 !important; }
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


def _badge(level: str) -> str:
    lv = (level or "UNKNOWN").upper()
    return f'<span class="badge {lv}">{lv}</span>'


def _module1_html(data: Optional[Dict]) -> str:
    if not data:
        return "<p>Module not run.</p>"
    devices = data.get("devices", [])
    if not devices:
        return "<p>No devices found in ARP table.</p>"
    rows = ""
    for d in devices:
        risk = getattr(d, "risk_level", d.get("risk_level", "UNKNOWN")) if not isinstance(d, dict) else d.get("risk_level", "UNKNOWN")
        ip   = getattr(d, "ip",  d.get("ip",  "?")) if not isinstance(d, dict) else d.get("ip", "?")
        mac  = getattr(d, "mac", d.get("mac", "?")) if not isinstance(d, dict) else d.get("mac", "?")
        vendor = getattr(d, "vendor", d.get("vendor", "Unknown")) if not isinstance(d, dict) else d.get("vendor", "Unknown")
        verdict = getattr(d, "verdict", d.get("verdict", "")) if not isinstance(d, dict) else d.get("verdict", "")
        rem = getattr(d, "remediation", d.get("remediation", "")) if not isinstance(d, dict) else d.get("remediation", "")
        rows += (
            f"<tr><td>{html.escape(ip)}</td><td>{html.escape(mac)}</td>"
            f"<td>{html.escape(vendor)}</td><td>{_badge(risk)}</td>"
            f"<td>{html.escape(verdict)}</td>"
            f"<td>{html.escape(rem) if rem else '—'}</td></tr>"
        )
    return (
        "<table><thead><tr>"
        "<th>IP</th><th>MAC</th><th>Vendor</th><th>Risk</th>"
        "<th>Verdict</th><th>Remediation</th>"
        f"</tr></thead><tbody>{rows}</tbody></table>"
    )


def _module2_html(data: Optional[Dict]) -> str:
    if not data:
        return "<p>Module not run.</p>"
    if data.get("error"):
        return f"<p>{html.escape(data['error'])}</p>"
    bpdus = data.get("bpdus", [])
    if not bpdus:
        return "<p>No BPDU frames detected during scan window.</p>"
    rows = ""
    for b in bpdus:
        src  = getattr(b, "src_mac", b.get("src_mac", "?"))       if not isinstance(b, dict) else b.get("src_mac", "?")
        rogue = getattr(b, "is_rogue", b.get("is_rogue", False))  if not isinstance(b, dict) else b.get("is_rogue", False)
        verdict = getattr(b, "verdict", b.get("verdict", ""))     if not isinstance(b, dict) else b.get("verdict", "")
        btype = getattr(b, "bpdu_type", b.get("bpdu_type", "?"))  if not isinstance(b, dict) else b.get("bpdu_type", "?")
        root_mac = getattr(b, "root_mac", b.get("root_mac", "")) if not isinstance(b, dict) else b.get("root_mac", "")
        hello = getattr(b, "hello_time", b.get("hello_time", 0)) if not isinstance(b, dict) else b.get("hello_time", 0)
        level = "HIGH" if rogue else "CLEAN"
        rows += (
            f"<tr><td>{html.escape(src)}</td><td>{html.escape(btype)}</td>"
            f"<td>{html.escape(root_mac)}</td><td>{hello:.1f}s</td>"
            f"<td>{_badge(level)}</td><td>{html.escape(verdict)}</td></tr>"
        )
    return (
        "<table><thead><tr><th>Source MAC</th><th>BPDU Type</th>"
        "<th>Root MAC</th><th>Hello Time</th><th>Status</th><th>Verdict</th>"
        f"</tr></thead><tbody>{rows}</tbody></table>"
    )


def _module3_html(data: Optional[Any]) -> str:
    if not data:
        return "<p>Module not run.</p>"
    plain = getattr(data, "plain_verdict", "") if not isinstance(data, dict) else data.get("plain_verdict", "")
    bps = getattr(data, "bcast_per_sec", 0) if not isinstance(data, dict) else data.get("bcast_per_sec", 0)
    mps = getattr(data, "mcast_per_sec", 0) if not isinstance(data, dict) else data.get("mcast_per_sec", 0)
    level = getattr(data, "storm_level", "UNKNOWN") if not isinstance(data, dict) else data.get("storm_level", "UNKNOWN")
    top5 = getattr(data, "top_sources", []) if not isinstance(data, dict) else data.get("top_sources", [])
    rows = "".join(
        f"<tr><td>{html.escape(mac)}</td><td>{count}</td></tr>"
        for mac, count in top5
    )
    return (
        f"<p><strong>Status:</strong> {_badge(level)} &nbsp; "
        f"Broadcast: {bps:.1f}/s &nbsp; Multicast: {mps:.1f}/s</p><br>"
        + (
            "<table><thead><tr><th>Source MAC</th><th>Broadcast Count</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
            if rows else ""
        )
    )


def _module4_html(data: Optional[Any]) -> str:
    if not data:
        return "<p>Module not run.</p>"
    networks = getattr(data, "networks", []) if not isinstance(data, dict) else data.get("networks", [])
    if not networks:
        error = getattr(data, "error", "") if not isinstance(data, dict) else data.get("error", "")
        return f"<p>{html.escape(error or 'No networks found.')}</p>"
    rows = ""
    for n in networks:
        ssid = getattr(n, "ssid", "") if not isinstance(n, dict) else n.get("ssid", "")
        bssid = getattr(n, "bssid", "") if not isinstance(n, dict) else n.get("bssid", "")
        ch = getattr(n, "channel", 0) if not isinstance(n, dict) else n.get("channel", 0)
        sig = getattr(n, "signal_dbm", 0) if not isinstance(n, dict) else n.get("signal_dbm", 0)
        hidden = getattr(n, "is_hidden", False) if not isinstance(n, dict) else n.get("is_hidden", False)
        rogue = getattr(n, "is_rogue_ssid", False) if not isinstance(n, dict) else n.get("is_rogue_ssid", False)
        conflict = getattr(n, "co_channel_conflict", False) if not isinstance(n, dict) else n.get("co_channel_conflict", False)
        verdict = getattr(n, "verdict", "") if not isinstance(n, dict) else n.get("verdict", "")
        level = "HIGH" if rogue else ("MEDIUM" if conflict else ("LOW" if hidden else "CLEAN"))
        ssid_display = ssid if ssid else "[HIDDEN]"
        rows += (
            f"<tr><td>{html.escape(ssid_display)}</td><td>{html.escape(bssid)}</td>"
            f"<td>{ch}</td><td>{sig}dBm</td>"
            f"<td>{_badge(level)}</td><td>{html.escape(verdict)}</td></tr>"
        )
    return (
        "<table><thead><tr><th>SSID</th><th>BSSID</th><th>CH</th>"
        "<th>Signal</th><th>Risk</th><th>Verdict</th>"
        f"</tr></thead><tbody>{rows}</tbody></table>"
    )


def _module5_html(data: Optional[Any]) -> str:
    if not data:
        return "<p>Module not run.</p>"
    outages = getattr(data, "micro_outages", []) if not isinstance(data, dict) else data.get("micro_outages", [])
    stp_sigs = getattr(data, "stp_signatures", []) if not isinstance(data, dict) else data.get("stp_signatures", [])
    dns_fail = getattr(data, "dns_only_failures", False) if not isinstance(data, dict) else data.get("dns_only_failures", False)
    rows = ""
    for o in outages:
        is_stp = any(s == o for s in stp_sigs)
        level = "HIGH" if is_stp else "MEDIUM"
        rows += (
            f"<tr><td>{html.escape(str(o.get('target','?')))}</td>"
            f"<td>{o.get('duration',0):.1f}s</td>"
            f"<td>{o.get('consecutive_drops',0)}</td>"
            f"<td>{'Yes — STP Reconvergence' if is_stp else 'No'}</td>"
            f"<td>{_badge(level)}</td></tr>"
        )
    table = (
        "<table><thead><tr><th>Target</th><th>Duration</th>"
        "<th>Consecutive Drops</th><th>STP Signature?</th><th>Severity</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>" if rows else "<p>No micro-outages detected.</p>"
    )
    dns_note = (
        "<p style='color:#f59e0b;margin-top:12px'>"
        "⚠ DNS-specific failure detected: pings succeeded but DNS timed out. "
        "Gateway DNS proxy is being disrupted.</p>"
        if dns_fail else ""
    )
    return table + dns_note


def _diagnostics_html(result) -> str:
    if not result:
        return "<p>Diagnostics not run.</p>"
    rows = ""
    for p in getattr(result, "ping_results", []):
        color = {"OK": "#22c55e", "SLOW": "#f59e0b", "FAIL": "#ef4444"}.get(p.status, "#888")
        rtt = f"{p.rtt_ms:.0f} ms" if p.rtt_ms >= 0 else "unreachable"
        rows += (f"<tr><td>{html.escape(p.host)}</td>"
                 f"<td style='color:{color}'>{p.status}</td>"
                 f"<td>{rtt}</td></tr>")
    ping_table = (
        "<table><thead><tr><th>Host</th><th>Status</th><th>RTT</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>" if rows else ""
    )
    verdict = getattr(result, "plain_verdict", "") or ""
    dns_leak = getattr(result, "dns_leak", None)
    leak_html = ""
    if dns_leak:
        color = "#ef4444" if dns_leak.leak_detected else "#22c55e"
        leak_html = (
            f"<p style='margin-top:10px;color:{color}'>"
            f"<strong>DNS Leak:</strong> {html.escape(dns_leak.plain_verdict)}</p>"
        )
    dl = getattr(result, "download_mbps", 0) or 0
    speed_html = f"<p><strong>Download speed:</strong> {dl:.1f} Mbps</p>" if dl > 0 else ""
    pub = getattr(result, "public_ip", "") or ""
    pub_html = f"<p><strong>Public IP:</strong> {html.escape(pub)}</p>" if pub else ""
    return ping_table + speed_html + pub_html + leak_html + (
        f"<p style='margin-top:8px;color:#888'>{html.escape(verdict)}</p>" if verdict else ""
    )


def _network_info_html(info: Optional[Dict]) -> str:
    if not info:
        return "<p>Network information not collected.</p>"
    lines = []
    for entry in info.get("local_ips", []):
        lines.append(f"<li><strong>Local IP:</strong> {html.escape(entry.get('ip',''))} "
                     f"(adapter: {html.escape(entry.get('adapter',''))})</li>")
    gw = info.get("gateway", "")
    if gw:
        lines.append(f"<li><strong>Gateway:</strong> {html.escape(gw)}</li>")
    for dns in info.get("dns_servers", []):
        lines.append(f"<li><strong>DNS Server:</strong> {html.escape(dns)}</li>")
    dhcp = info.get("dhcp", {})
    if dhcp.get("dhcp_server"):
        lines.append(f"<li><strong>DHCP Server:</strong> {html.escape(dhcp['dhcp_server'])}</li>")
    if dhcp.get("lease_expires"):
        lines.append(f"<li><strong>DHCP Lease Expires:</strong> {html.escape(dhcp['lease_expires'])}</li>")
    adapters = info.get("adapters", [])
    adp_rows = ""
    for a in adapters:
        connected = a.get("connected", False)
        st_color = "#22c55e" if connected else "#ef4444"
        st = "Connected" if connected else "Disconnected"
        sig = a.get("signal_pct", -1)
        sig_str = f"{sig}%" if sig >= 0 else "—"
        speed = a.get("speed_mbps", 0)
        adp_rows += (
            f"<tr><td>{html.escape(a.get('name',''))}</td>"
            f"<td>{html.escape(a.get('type',''))}</td>"
            f"<td>{html.escape(a.get('ipv4','—'))}</td>"
            f"<td>{speed} Mbps</td><td>{sig_str}</td>"
            f"<td style='color:{st_color}'>{st}</td></tr>"
        )
    adp_table = (
        "<table style='margin-top:10px'><thead><tr>"
        "<th>Adapter</th><th>Type</th><th>IP</th><th>Speed</th><th>WiFi</th><th>Status</th>"
        f"</tr></thead><tbody>{adp_rows}</tbody></table>" if adp_rows else ""
    )
    return f"<ul style='padding-left:18px'>{''.join(lines)}</ul>" + adp_table


def generate_html(
    module1_data=None,
    module2_data=None,
    module3_data=None,
    module4_data=None,
    module5_data=None,
    diagnostics_data=None,
    network_info_data=None,
    overall_verdict: str = "",
    overall_level: str = "CLEAN",
) -> str:
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    verdict_cls = {"HIGH": "red", "MEDIUM": "amber", "CLEAN": "green"}.get(
        overall_level, "amber"
    )
    icon = {"red": "🔴", "amber": "🟡", "green": "🟢"}.get(verdict_cls, "🟡")

    body = f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>NetSentinel — Report {ts}</title>
<style>{_CSS}</style>
</head>
<body>
<h1>NetSentinel</h1>
<p class="subtitle">Network Diagnostic Report — Generated {ts}</p>

<div class="verdict-box {verdict_cls}">
<h2>{icon} Overall Verdict</h2>
<p>{html.escape(overall_verdict or 'No verdict available.')}</p>
</div>

<div class="module">
<h3>Module 1 — Rogue Device Fingerprinter</h3>
{_module1_html(module1_data)}
</div>

<div class="module">
<h3>Module 2 — STP / BPDU Rogue Bridge Detector</h3>
{_module2_html(module2_data)}
</div>

<div class="module">
<h3>Module 3 — Broadcast &amp; Multicast Storm Analyser</h3>
{_module3_html(module3_data)}
</div>

<div class="module">
<h3>Module 4 — Hidden SSID &amp; Co-Channel Interference</h3>
{_module4_html(module4_data)}
</div>

<div class="module">
<h3>Module 5 — DNS Failure &amp; Micro-Outage Correlator</h3>
{_module5_html(module5_data)}
</div>

<div class="module">
<h3>Network Information</h3>
{_network_info_html(network_info_data)}
</div>

<div class="module">
<h3>Diagnostics</h3>
{_diagnostics_html(diagnostics_data)}
</div>

<p class="meta">
  NetSentinel &bull; Offline tool &bull;
  No data leaves your machine &bull; {ts}
</p>
</body>
</html>
"""
    return body


def save_report(
    output_path: Path,
    module1_data=None,
    module2_data=None,
    module3_data=None,
    module4_data=None,
    module5_data=None,
    diagnostics_data=None,
    network_info_data=None,
    overall_verdict: str = "",
    overall_level: str = "CLEAN",
) -> Path:
    content = generate_html(
        module1_data, module2_data, module3_data, module4_data, module5_data,
        diagnostics_data, network_info_data,
        overall_verdict, overall_level,
    )
    output_path.write_text(content, encoding="utf-8")
    return output_path


def save_pdf_report(
    output_path: Path,
    module1_data=None,
    module2_data=None,
    module3_data=None,
    module4_data=None,
    module5_data=None,
    diagnostics_data=None,
    network_info_data=None,
    overall_verdict: str = "",
    overall_level: str = "CLEAN",
) -> Path:
    """
    Generate a PDF report from the same HTML template as save_report().

    Strategy (tries in order):
      1. weasyprint — pure Python, best fidelity (pip install weasyprint)
      2. headless Microsoft Edge (Windows) — msedge.exe --headless --print-to-pdf
      3. headless Google Chrome / Chromium — chrome --headless --print-to-pdf
      4. Fallback — saves HTML and raises RuntimeError listing install options

    Returns the Path to the saved PDF on success.
    Raises RuntimeError if no PDF backend is available.
    """
    import subprocess
    import sys
    import tempfile

    html_content = generate_html(
        module1_data, module2_data, module3_data, module4_data, module5_data,
        diagnostics_data, network_info_data,
        overall_verdict, overall_level,
    )

    # ── Backend 1: weasyprint ───────────────────────────────────────────────
    try:
        import weasyprint  # type: ignore
        weasyprint.HTML(string=html_content).write_pdf(str(output_path))
        return output_path
    except ImportError:
        pass
    except Exception as exc:
        raise RuntimeError(f"weasyprint failed: {exc}") from exc

    # ── Backends 2 & 3: headless browser ───────────────────────────────────
    # Write HTML to a temp file so the browser can load it from disk
    with tempfile.NamedTemporaryFile(
        suffix=".html", delete=False, mode="w", encoding="utf-8"
    ) as tmp:
        tmp.write(html_content)
        tmp_html = tmp.name

    browser_candidates: list[str] = []
    if sys.platform == "win32":
        import os
        # Common Edge locations
        browser_candidates += [
            os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
            os.path.join(os.environ.get("ProgramFiles", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
            # Chrome
            os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(os.environ.get("ProgramFiles", ""), "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(os.environ.get("LocalAppData", ""), "Google", "Chrome", "Application", "chrome.exe"),
        ]
    elif sys.platform == "darwin":
        browser_candidates += [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "chromium-browser",
            "chromium",
        ]
    else:
        browser_candidates += ["google-chrome", "chromium-browser", "chromium", "microsoft-edge"]

    import os
    pdf_out = str(output_path)
    for browser in browser_candidates:
        if not os.path.isabs(browser) or os.path.isfile(browser):
            try:
                result = subprocess.run(
                    [
                        browser,
                        "--headless",
                        "--disable-gpu",
                        "--no-sandbox",
                        f"--print-to-pdf={pdf_out}",
                        f"file:///{tmp_html}",
                    ],
                    capture_output=True,
                    timeout=30,
                )
                if result.returncode == 0 and Path(pdf_out).exists():
                    return output_path
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
            except Exception:
                continue

    # Clean up temp file
    try:
        Path(tmp_html).unlink(missing_ok=True)
    except Exception:
        pass

    raise RuntimeError(
        "No PDF backend available.\n"
        "Install one of:\n"
        "  pip install weasyprint\n"
        "  OR install Google Chrome or Microsoft Edge"
    )


# ── JSON export ───────────────────────────────────────────────────────────────

def _device_to_dict(d) -> dict:
    """Convert a DeviceInfo object or plain dict to a JSON-serialisable dict."""
    if isinstance(d, dict):
        return d
    return {
        "ip":              getattr(d, "ip", ""),
        "mac":             getattr(d, "mac", ""),
        "hostname":        getattr(d, "hostname", ""),
        "vendor":          getattr(d, "vendor", ""),
        "device_type":     getattr(d, "device_type", ""),
        "os_family":       getattr(d, "os_family", ""),
        "risk_level":      getattr(d, "risk_level", ""),
        "connection_type": getattr(d, "connection_type", ""),
        "known_issues":    getattr(d, "known_issues", []),
        "verdict":         getattr(d, "verdict", ""),
        "remediation":     getattr(d, "remediation", ""),
        "forum_ref":       getattr(d, "forum_ref", ""),
    }


def generate_json(
    module1_data=None,
    module2_data=None,
    module3_data=None,
    module4_data=None,
    module5_data=None,
    diagnostics_data=None,
    network_info_data=None,
    overall_verdict: str = "",
    overall_level: str = "CLEAN",
) -> str:
    """
    Return a JSON string containing all scan findings.
    Compatible with standard security tooling for further processing.
    """
    ts = datetime.datetime.now().isoformat(timespec="seconds")

    payload: Dict[str, Any] = {
        "generated_at": ts,
        "tool": "NetSentinel",
        "overall_verdict": overall_verdict,
        "overall_level": overall_level,
    }

    # Module 1 — devices
    if module1_data:
        devices = module1_data.get("devices", [])
        payload["devices"] = [_device_to_dict(d) for d in devices]
        payload["high_risk_count"] = module1_data.get("high_risk_count", 0)
        payload["total_devices"]   = module1_data.get("total_count", 0)

    # Module 2 — BPDUs
    if module2_data:
        bpdus = module2_data.get("bpdus", [])
        payload["bpdus"] = [
            {
                "src_mac":         getattr(b, "src_mac", b.get("src_mac", "") if isinstance(b, dict) else ""),
                "is_rogue":        getattr(b, "is_rogue", b.get("is_rogue", False) if isinstance(b, dict) else False),
                "root_mac":        getattr(b, "root_mac", b.get("root_mac", "") if isinstance(b, dict) else ""),
                "bridge_priority": getattr(b, "bridge_priority", b.get("bridge_priority", 0) if isinstance(b, dict) else 0),
            }
            for b in bpdus
        ]
        payload["rogue_bpdu_count"] = module2_data.get("rogue_count", 0)

    # Module 3 — storm
    if module3_data:
        payload["broadcast_storm"] = {
            "bcast_per_sec": getattr(module3_data, "bcast_per_sec", 0) if not isinstance(module3_data, dict) else module3_data.get("bcast_per_sec", 0),
            "storm_level":   getattr(module3_data, "storm_level", "UNKNOWN") if not isinstance(module3_data, dict) else module3_data.get("storm_level", "UNKNOWN"),
            "verdict":       getattr(module3_data, "plain_verdict", "") if not isinstance(module3_data, dict) else module3_data.get("plain_verdict", ""),
        }

    # Network info
    if network_info_data:
        payload["network_info"] = {
            k: v for k, v in network_info_data.items()
            if isinstance(v, (str, int, float, bool, type(None)))
        }

    # Diagnostics
    if diagnostics_data:
        payload["diagnostics"] = {
            "verdict":     getattr(diagnostics_data, "plain_verdict", ""),
            "public_ip":   getattr(diagnostics_data, "public_ip", ""),
            "dns_leak":    getattr(diagnostics_data, "dns_leak_detected", False),
        }

    return json.dumps(payload, indent=2, ensure_ascii=False)


def save_json_report(
    output_path: Path,
    module1_data=None,
    module2_data=None,
    module3_data=None,
    module4_data=None,
    module5_data=None,
    diagnostics_data=None,
    network_info_data=None,
    overall_verdict: str = "",
    overall_level: str = "CLEAN",
) -> Path:
    content = generate_json(
        module1_data, module2_data, module3_data, module4_data, module5_data,
        diagnostics_data, network_info_data,
        overall_verdict, overall_level,
    )
    output_path.write_text(content, encoding="utf-8")
    return output_path


# ── CSV export ────────────────────────────────────────────────────────────────

def generate_csv_devices(module1_data) -> str:
    """
    Return a CSV string of all discovered devices from a Module 1 scan.
    One row per device; columns compatible with spreadsheet import.
    """
    import csv
    import io

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "IP Address", "Hostname", "MAC Address", "Vendor",
        "Device Type", "OS Family", "Risk Level",
        "Connection Type", "Known Issues", "Verdict", "Remediation",
    ])

    if module1_data:
        for d in module1_data.get("devices", []):
            dd = _device_to_dict(d)
            writer.writerow([
                dd.get("ip", ""),
                dd.get("hostname", ""),
                dd.get("mac", ""),
                dd.get("vendor", ""),
                dd.get("device_type", ""),
                dd.get("os_family", ""),
                dd.get("risk_level", ""),
                dd.get("connection_type", ""),
                " | ".join(dd.get("known_issues", [])),
                dd.get("verdict", ""),
                dd.get("remediation", ""),
            ])

    return buf.getvalue()


def save_csv_report(output_path: Path, module1_data) -> Path:
    """Save device list as CSV. Returns the output path."""
    output_path.write_text(generate_csv_devices(module1_data), encoding="utf-8")
    return output_path


# ── Nmap XML export ───────────────────────────────────────────────────────────

def generate_nmap_xml(
    module1_data,
    portscan_result=None,
    scan_args: str = "NetSentinel TCP connect scan",
) -> str:
    """
    Generate an Nmap-compatible XML report from scan data.

    The output is accepted by tools that consume Nmap XML:
    Metasploit (db_import), Burp Suite, Faraday, Dradis, etc.

    Parameters
    ----------
    module1_data    Device fingerprint result dict (from rogue_device scan).
    portscan_result PortScanResult object (optional) for open-port detail.
    scan_args       Label embedded in the XML scanner/args fields.
    """
    import xml.etree.ElementTree as ET
    from xml.dom import minidom
    import time as _time

    start_ts = int(_time.time())

    # Root <nmaprun>
    nmaprun = ET.Element("nmaprun")
    nmaprun.set("scanner", "NetSentinel")
    nmaprun.set("args", scan_args)
    nmaprun.set("start", str(start_ts))
    nmaprun.set("startstr", _time.strftime("%c", _time.localtime(start_ts)))
    nmaprun.set("version", "1.0.0")
    nmaprun.set("xmloutputversion", "1.04")

    # <scaninfo>
    si = ET.SubElement(nmaprun, "scaninfo")
    si.set("type", "connect")
    si.set("protocol", "tcp")
    si.set("numservices", "28")
    si.set("services", "21-23,25,53,80,110,143,443,445,587,631,993,995,1883,3389,5900,7547,8080,8443,8888,9100,49152")

    # Build a port→detail lookup from portscan_result if provided
    open_port_map: dict[int, dict] = {}
    if portscan_result is not None:
        for p in getattr(portscan_result, "open_ports", []):
            open_port_map[p.port] = {
                "name": getattr(p, "name", ""),
                "version": getattr(p, "service_version", ""),
                "banner": getattr(p, "banner", ""),
            }

    devices = []
    if module1_data:
        devices = module1_data.get("devices", [])

    for d in devices:
        dd = _device_to_dict(d)
        ip = dd.get("ip", "")
        if not ip:
            continue

        host_el = ET.SubElement(nmaprun, "host")
        host_el.set("starttime", str(start_ts))
        host_el.set("endtime", str(start_ts))

        # <status>
        status_el = ET.SubElement(host_el, "status")
        status_el.set("state", "up")
        status_el.set("reason", "arp-response")

        # <address> — IP
        addr_ip = ET.SubElement(host_el, "address")
        addr_ip.set("addr", ip)
        addr_ip.set("addrtype", "ipv4")

        # <address> — MAC
        mac = dd.get("mac", "")
        if mac:
            addr_mac = ET.SubElement(host_el, "address")
            addr_mac.set("addr", mac.upper())
            addr_mac.set("addrtype", "mac")
            vendor = dd.get("vendor", "")
            if vendor:
                addr_mac.set("vendor", vendor)

        # <hostnames>
        hostnames_el = ET.SubElement(host_el, "hostnames")
        hostname = dd.get("hostname", "")
        if hostname and hostname != ip:
            hn = ET.SubElement(hostnames_el, "hostname")
            hn.set("name", hostname)
            hn.set("type", "PTR")

        # <ports>
        ports_el = ET.SubElement(host_el, "ports")
        if open_port_map and dd.get("ip") == getattr(portscan_result, "ip", None):
            for portnum, pinfo in open_port_map.items():
                port_el = ET.SubElement(ports_el, "port")
                port_el.set("protocol", "tcp")
                port_el.set("portid", str(portnum))
                state_el = ET.SubElement(port_el, "state")
                state_el.set("state", "open")
                state_el.set("reason", "syn-ack")
                svc_el = ET.SubElement(port_el, "service")
                svc_el.set("name", pinfo.get("name", "unknown").split()[0].lower())
                ver = pinfo.get("version", "")
                if ver:
                    svc_el.set("version", ver)

        # <os> guess
        os_family = dd.get("os_family", "")
        if os_family:
            os_el = ET.SubElement(host_el, "os")
            osm = ET.SubElement(os_el, "osmatch")
            osm.set("name", os_family)
            osm.set("accuracy", "75")
            osc = ET.SubElement(osm, "osclass")
            osc.set("type", "general purpose")
            osc.set("vendor", "")
            osc.set("osfamily", os_family)
            osc.set("accuracy", "75")

        # <hostscript> — risk level as a script output
        risk_level = dd.get("risk_level", "")
        if risk_level:
            hscript = ET.SubElement(host_el, "hostscript")
            scr = ET.SubElement(hscript, "script")
            scr.set("id", "netsentinel-risk")
            scr.set("output", f"Risk: {risk_level}")

    # <runstats>
    rs = ET.SubElement(nmaprun, "runstats")
    fin = ET.SubElement(rs, "finished")
    fin.set("time", str(start_ts))
    fin.set("timestr", _time.strftime("%c", _time.localtime(start_ts)))
    fin.set("elapsed", "0")
    fin.set("summary", f"NetSentinel scan; {len(devices)} host(s) up")
    hosts_el = ET.SubElement(rs, "hosts")
    hosts_el.set("up", str(len(devices)))
    hosts_el.set("down", "0")
    hosts_el.set("total", str(len(devices)))

    # Pretty-print
    raw = ET.tostring(nmaprun, encoding="unicode")
    reparsed = minidom.parseString(raw)
    return reparsed.toprettyxml(indent="  ", encoding=None)


def save_nmap_xml_report(
    output_path: Path,
    module1_data,
    portscan_result=None,
) -> Path:
    """Save Nmap XML report. Returns the output path."""
    output_path.write_text(
        generate_nmap_xml(module1_data, portscan_result),
        encoding="utf-8",
    )
    return output_path


# ── ISP Accountability Report ─────────────────────────────────────────────────

from modules.colours import (
    EXPORT_BG, EXPORT_ISP_HEADER, EXPORT_HEADING_FG, EXPORT_TEXT, EXPORT_META,
    EXPORT_TH_BG, EXPORT_ACCENT_FG, EXPORT_BORDER, EXPORT_NOTE_BG,
    EXPORT_RED_FG,
    GRADE_A_BG, GRADE_A_FG, GRADE_A_BORDER,
    GRADE_B_BG, GRADE_B_FG, GRADE_B_BORDER,
    GRADE_C_BG, GRADE_C_FG, GRADE_C_BORDER,
    GRADE_D_BG, GRADE_D_FG, GRADE_D_BORDER,
    GRADE_F_BG, GRADE_F_FG, GRADE_F_BORDER,
)

_ISP_CSS = _CSS + _Template("""
.isp-header { background: $EXPORT_ISP_HEADER; border-bottom: 3px solid $EXPORT_HEADING_FG; padding: 24px 32px 16px; }
.isp-header h1 { color: $EXPORT_TEXT; font-size: 1.6rem; }
.isp-header .sub { color: $EXPORT_META; font-size: 0.85rem; margin-top: 4px; }
.grade-box { display:inline-block; width:90px; height:90px; border-radius:50%;
  line-height:90px; text-align:center; font-size:3rem; font-weight:bold; margin-right:24px;
  vertical-align:middle; }
.grade-A { background:$GRADE_A_BG; color:$GRADE_A_FG; border:3px solid $GRADE_A_BORDER; }
.grade-B { background:$GRADE_B_BG; color:$GRADE_B_FG; border:3px solid $GRADE_B_BORDER; }
.grade-C { background:$GRADE_C_BG; color:$GRADE_C_FG; border:3px solid $GRADE_C_BORDER; }
.grade-D { background:$GRADE_D_BG; color:$GRADE_D_FG; border:3px solid $GRADE_D_BORDER; }
.grade-F { background:$GRADE_F_BG; color:$GRADE_F_FG; border:3px solid $GRADE_F_BORDER; }
.dim-row { display:flex; align-items:center; padding:10px 0; border-bottom:1px solid $EXPORT_TH_BG; }
.dim-name { flex:0 0 200px; color:$EXPORT_ACCENT_FG; font-size:0.9rem; }
.dim-bar-wrap { flex:1; background:$EXPORT_TH_BG; border-radius:6px; height:12px; margin:0 16px; }
.dim-bar { height:12px; border-radius:6px; }
.dim-grade { flex:0 0 30px; font-weight:bold; font-size:1.1rem; text-align:center; }
.dim-val { flex:0 0 100px; color:$EXPORT_META; font-size:0.8rem; text-align:right; }
.hop-table { font-size:0.82rem; }
.hop-table .loss-high { color:$EXPORT_RED_FG; font-weight:bold; }
.section-title { color:$EXPORT_HEADING_FG; font-size:1rem; font-weight:bold;
  margin:20px 0 8px; padding-bottom:4px; border-bottom:1px solid $EXPORT_BORDER; }
.evidence-note { background:$EXPORT_NOTE_BG; border-left:3px solid $EXPORT_HEADING_FG;
  padding:10px 14px; font-size:0.85rem; color:$EXPORT_META; margin:12px 0; border-radius:0 8px 8px 0; }
""").substitute(
    EXPORT_ISP_HEADER=EXPORT_ISP_HEADER, EXPORT_HEADING_FG=EXPORT_HEADING_FG,
    EXPORT_TEXT=EXPORT_TEXT, EXPORT_META=EXPORT_META, EXPORT_TH_BG=EXPORT_TH_BG,
    EXPORT_ACCENT_FG=EXPORT_ACCENT_FG, EXPORT_BORDER=EXPORT_BORDER,
    EXPORT_NOTE_BG=EXPORT_NOTE_BG, EXPORT_RED_FG=EXPORT_RED_FG,
    GRADE_A_BG=GRADE_A_BG, GRADE_A_FG=GRADE_A_FG, GRADE_A_BORDER=GRADE_A_BORDER,
    GRADE_B_BG=GRADE_B_BG, GRADE_B_FG=GRADE_B_FG, GRADE_B_BORDER=GRADE_B_BORDER,
    GRADE_C_BG=GRADE_C_BG, GRADE_C_FG=GRADE_C_FG, GRADE_C_BORDER=GRADE_C_BORDER,
    GRADE_D_BG=GRADE_D_BG, GRADE_D_FG=GRADE_D_FG, GRADE_D_BORDER=GRADE_D_BORDER,
    GRADE_F_BG=GRADE_F_BG, GRADE_F_FG=GRADE_F_FG, GRADE_F_BORDER=GRADE_F_BORDER,
)


def generate_isp_report(
    log_summary=None,
    diag_result=None,
    mtr_result=None,
    benchmark_result=None,
    m1_result=None,
    public_ip: str = "",
    isp_name: str = "",
    account_ref: str = "",
) -> str:
    """
    Generate a self-contained HTML ISP Accountability Report designed to be
    attached to a support ticket or printed and handed to a technician.

    Bundles: network grade, traceroute hop table with loss %, ping stats,
    DNS latency, outage log, and a plain-English summary paragraph.

    Parameters
    ----------
    log_summary      : LogSummary (uptime, jitter, outages)
    diag_result      : DiagnosticsResult (ping, DNS, download, trace hops)
    mtr_result       : List[dict] with keys hop/ip/loss_pct/avg_rtt
    benchmark_result : BenchmarkResult from network_benchmark.grade()
    m1_result        : rogue_device scan dict
    public_ip        : Detected public IP (shown for ISP reference)
    isp_name         : Optional ISP name to include in report header
    account_ref      : Optional account/reference number
    """
    ts  = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    now = datetime.datetime.now().strftime("%A %d %B %Y, %H:%M")

    # ── Overall grade section ─────────────────────────────────────────────────
    if benchmark_result:
        grade_letter = benchmark_result.overall_grade
        grade_color  = benchmark_result.overall_color
        overall_txt  = html.escape(benchmark_result.overall_verdict)
        grade_css    = f"grade-{grade_letter}"
        score        = f"{benchmark_result.overall_score:.0f}/100"
    else:
        grade_letter = "N/A"
        grade_css    = "grade-F"
        grade_color  = "#888"
        overall_txt  = "No benchmark data available."
        score        = "—"

    # ── Dimension bars ────────────────────────────────────────────────────────
    dim_html = ""
    if benchmark_result and benchmark_result.dimensions:
        for d in benchmark_result.dimensions:
            bar_color = d.color
            dim_html += (
                f'<div class="dim-row">'
                f'<div class="dim-name">{html.escape(d.name)}</div>'
                f'<div class="dim-bar-wrap">'
                f'<div class="dim-bar" style="width:{d.score:.0f}%;background:{bar_color}"></div>'
                f'</div>'
                f'<div class="dim-grade" style="color:{bar_color}">{d.grade}</div>'
                f'<div class="dim-val">{html.escape(d.value_label)}</div>'
                f'</div>'
            )

    # ── Traceroute / MTR hop table ────────────────────────────────────────────
    trace_hops = getattr(diag_result, "trace_hops", []) if diag_result else []
    mtr_rows_html = ""
    if mtr_result:
        for hop in mtr_result:
            loss = hop.get("loss_pct", 0.0)
            cls  = 'loss-high' if loss > 10 else ''
            mtr_rows_html += (
                f"<tr><td>{hop.get('hop','?')}</td>"
                f"<td>{html.escape(hop.get('ip','*'))}</td>"
                f"<td class='{cls}'>{loss:.1f}%</td>"
                f"<td>{hop.get('avg_rtt',-1):.1f} ms</td>"
                f"<td>{hop.get('last_rtt',-1):.1f} ms</td></tr>"
            )
    elif trace_hops:
        for h in trace_hops:
            rtt  = getattr(h, "rtt_ms", -1)
            mtr_rows_html += (
                f"<tr><td>{getattr(h,'hop','?')}</td>"
                f"<td>{html.escape(getattr(h,'ip','*'))}</td>"
                f"<td>—</td>"
                f"<td>{'—' if rtt < 0 else f'{rtt:.1f} ms'}</td>"
                f"<td>—</td></tr>"
            )
    hop_section = ""
    if mtr_rows_html:
        hop_section = f"""
<div class="section-title">Network Path (Traceroute / MTR)</div>
<table class="hop-table">
<thead><tr><th>Hop</th><th>IP Address</th><th>Packet Loss</th>
<th>Avg RTT</th><th>Last RTT</th></tr></thead>
<tbody>{mtr_rows_html}</tbody>
</table>
<div class="evidence-note">
Packet loss at hop 1 (your router) = local fault.<br>
Packet loss first appearing at hop 2+ = ISP infrastructure issue.
</div>"""

    # ── Outage log ────────────────────────────────────────────────────────────
    outages = getattr(log_summary, "outages", []) if log_summary else []
    outage_rows = ""
    for o in outages:
        outage_rows += (
            f"<tr><td>{html.escape(o.host)}</td>"
            f"<td>{html.escape(o.start)}</td>"
            f"<td>{html.escape(o.end)}</td>"
            f"<td>{o.duration_s:.0f} s</td>"
            f"<td>{o.consecutive_fails}</td></tr>"
        )
    outage_section = ""
    if outage_rows:
        outage_section = f"""
<div class="section-title">Recorded Outages</div>
<table>
<thead><tr><th>Target</th><th>Start</th><th>End</th>
<th>Duration</th><th>Consecutive Fails</th></tr></thead>
<tbody>{outage_rows}</tbody>
</table>"""
    elif log_summary:
        outage_section = (
            '<div class="section-title">Recorded Outages</div>'
            '<p style="color:#22c55e">No outages recorded during the monitoring period.</p>'
        )

    # ── Key metrics summary ───────────────────────────────────────────────────
    uptime  = getattr(log_summary, "uptime_pct",   100.0) if log_summary else None
    avg_rtt = getattr(log_summary, "avg_rtt_ms",   -1.0)  if log_summary else -1.0
    jitter  = getattr(log_summary, "avg_jitter_ms",-1.0)  if log_summary else -1.0
    dl_mbps = getattr(diag_result, "download_mbps",-1.0)  if diag_result else -1.0

    def _fmt(val, suffix, default="Not measured"):
        return f"{val:.1f}{suffix}" if val and val > 0 else default

    metrics_rows = f"""
<tr><td>Uptime</td><td>{_fmt(uptime,'%') if uptime is not None else 'Not measured'}</td></tr>
<tr><td>Average Latency</td><td>{_fmt(avg_rtt,' ms')}</td></tr>
<tr><td>Average Jitter</td><td>{_fmt(jitter,' ms')}</td></tr>
<tr><td>Download Speed</td><td>{_fmt(dl_mbps,' Mbps')}</td></tr>
<tr><td>Public IP</td><td>{html.escape(public_ip or 'Not detected')}</td></tr>
<tr><td>ISP</td><td>{html.escape(isp_name or 'Not specified')}</td></tr>
<tr><td>Account Reference</td><td>{html.escape(account_ref or '—')}</td></tr>
"""

    # ── Assemble ──────────────────────────────────────────────────────────────
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>NetSentinel — ISP Report {ts}</title>
<style>{_ISP_CSS}</style>
</head>
<body>
<div class="isp-header">
  <h1>NetSentinel — ISP Accountability Report</h1>
  <div class="sub">Generated: {now} &nbsp;|&nbsp; This report was produced entirely offline. No data was sent to any server.</div>
</div>

<div class="module" style="margin-top:20px;display:flex;align-items:center">
  <div class="grade-box {grade_css}">{grade_letter}</div>
  <div>
    <div style="font-size:1.1rem;font-weight:bold;color:{grade_color}">
      Network Health Score: {score}
    </div>
    <div style="color:#ccc;margin-top:6px;max-width:600px">{overall_txt}</div>
  </div>
</div>

<div class="module">
  <div class="section-title">Performance Breakdown</div>
  {dim_html or '<p>No benchmark data — run scans first.</p>'}
</div>

<div class="module">
  <div class="section-title">Key Metrics Summary</div>
  <table><tbody>{metrics_rows}</tbody></table>
</div>

{f'<div class="module">{hop_section}</div>' if hop_section else ''}
{f'<div class="module">{outage_section}</div>' if outage_section else ''}

<div class="module">
  <div class="section-title">How to Use This Report</div>
  <ul style="padding-left:18px;line-height:1.9;color:#ccc;font-size:0.9rem">
    <li>Share this HTML file or print it to PDF (Ctrl+P → Save as PDF) and attach to your ISP support ticket.</li>
    <li>Point the technician to the <strong>Network Path</strong> table — packet loss first appearing at hop 2 or later is in the ISP's network.</li>
    <li>The <strong>Recorded Outages</strong> section provides timestamped evidence of every disconnection.</li>
    <li>The <strong>Network Health Score</strong> gives an at-a-glance summary of your connection quality.</li>
  </ul>
</div>

<p class="meta">
  NetSentinel &bull; Privacy-First Network Diagnostics &bull;
  All measurements taken locally &bull; {ts}
</p>
</body>
</html>"""


def save_isp_report(
    output_path: Path,
    log_summary=None,
    diag_result=None,
    mtr_result=None,
    benchmark_result=None,
    m1_result=None,
    public_ip: str = "",
    isp_name: str = "",
    account_ref: str = "",
) -> Path:
    """Save an ISP Accountability Report as HTML. Returns the output path."""
    content = generate_isp_report(
        log_summary=log_summary,
        diag_result=diag_result,
        mtr_result=mtr_result,
        benchmark_result=benchmark_result,
        m1_result=m1_result,
        public_ip=public_ip,
        isp_name=isp_name,
        account_ref=account_ref,
    )
    output_path.write_text(content, encoding="utf-8")
    return output_path



