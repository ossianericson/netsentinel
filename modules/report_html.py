"""
HTML report generation helpers for NetSentinel scan reports.

Contains: CSS template, per-module HTML builders, and generate_html().
Extracted from modules/report_exporter.py (S2-2 sprint split).
All symbols are re-exported from modules/report_exporter for backwards compatibility.
"""

import datetime
import html
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
:root { color-scheme: dark; }
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
.verdict-box p { font-size: 0.95rem; line-height: 1.6; color: $EXPORT_TEXT; }
.module { background: $EXPORT_CARD; border-radius: 10px; padding: 18px; margin-bottom: 18px; border: 1px solid $EXPORT_BORDER; }
.module h3 { font-size: 1rem; color: $EXPORT_ACCENT_FG; margin-bottom: 12px; }
table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
th { background: $EXPORT_TH_BG; color: $EXPORT_ACCENT_FG; text-align: left; padding: 8px 10px; }
td { padding: 7px 10px; border-bottom: 1px solid $EXPORT_TH_BG; vertical-align: top; color: $EXPORT_TEXT; background: $EXPORT_CARD; }
tr:hover td { background: $EXPORT_ROW_HOVER; color: $EXPORT_TEXT; }
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
