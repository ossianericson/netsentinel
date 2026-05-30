"""
Report Exporter — public API for all NetSentinel report formats.

HTML generation helpers live in modules/report_html.py.
PDF generation lives in modules/report_pdf.py.
This file contains: JSON, CSV, Nmap XML, ISP report, diagnostic card, lab report.

Backwards-compat re-exports: generate_html, save_pdf_report are still importable
from this module.
"""

import datetime
import html
import json
from pathlib import Path
from string import Template as _Template
from typing import Any, Dict, Optional

# Re-exports for backwards compatibility — callers that do
# `from modules.report_exporter import generate_html` continue to work.
from modules.report_html import (
    generate_html,
    _CSS,
    _badge,
)
from modules.report_pdf import save_pdf_report  # noqa: F401 (re-export)

from modules.colours import (
    EXPORT_BG, EXPORT_TEXT, EXPORT_HEADING_FG, EXPORT_META,
    EXPORT_GREEN_FG, EXPORT_AMBER_FG, EXPORT_RED_FG,
    EXPORT_CARD, EXPORT_BORDER, EXPORT_ACCENT_FG,
    EXPORT_TH_BG, EXPORT_ISP_HEADER, EXPORT_NOTE_BG,
    GRADE_A_BG, GRADE_A_FG, GRADE_A_BORDER,
    GRADE_B_BG, GRADE_B_FG, GRADE_B_BORDER,
    GRADE_C_BG, GRADE_C_FG, GRADE_C_BORDER,
    GRADE_D_BG, GRADE_D_FG, GRADE_D_BORDER,
    GRADE_F_BG, GRADE_F_FG, GRADE_F_BORDER,
)


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
    """Return a JSON string containing all scan findings."""
    ts = datetime.datetime.now().isoformat(timespec="seconds")

    payload: Dict[str, Any] = {
        "generated_at": ts,
        "tool": "NetSentinel",
        "overall_verdict": overall_verdict,
        "overall_level": overall_level,
    }

    if module1_data:
        devices = module1_data.get("devices", [])
        payload["devices"] = [_device_to_dict(d) for d in devices]
        payload["high_risk_count"] = module1_data.get("high_risk_count", 0)
        payload["total_devices"]   = module1_data.get("total_count", 0)

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

    if module3_data:
        payload["broadcast_storm"] = {
            "bcast_per_sec": getattr(module3_data, "bcast_per_sec", 0) if not isinstance(module3_data, dict) else module3_data.get("bcast_per_sec", 0),
            "storm_level":   getattr(module3_data, "storm_level", "UNKNOWN") if not isinstance(module3_data, dict) else module3_data.get("storm_level", "UNKNOWN"),
            "verdict":       getattr(module3_data, "plain_verdict", "") if not isinstance(module3_data, dict) else module3_data.get("plain_verdict", ""),
        }

    if network_info_data:
        payload["network_info"] = {
            k: v for k, v in network_info_data.items()
            if isinstance(v, (str, int, float, bool, type(None)))
        }

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
    """Return a CSV string of all discovered devices from a Module 1 scan."""
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
    """Generate an Nmap-compatible XML report from scan data."""
    import xml.etree.ElementTree as ET
    from xml.dom import minidom
    import time as _time

    start_ts = int(_time.time())

    nmaprun = ET.Element("nmaprun")
    nmaprun.set("scanner", "NetSentinel")
    nmaprun.set("args", scan_args)
    nmaprun.set("start", str(start_ts))
    nmaprun.set("startstr", _time.strftime("%c", _time.localtime(start_ts)))
    nmaprun.set("version", "1.0.0")
    nmaprun.set("xmloutputversion", "1.04")

    si = ET.SubElement(nmaprun, "scaninfo")
    si.set("type", "connect")
    si.set("protocol", "tcp")
    si.set("numservices", "28")
    si.set("services", "21-23,25,53,80,110,143,443,445,587,631,993,995,1883,3389,5900,7547,8080,8443,8888,9100,49152")

    open_port_map: dict = {}
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

        status_el = ET.SubElement(host_el, "status")
        status_el.set("state", "up")
        status_el.set("reason", "arp-response")

        addr_ip = ET.SubElement(host_el, "address")
        addr_ip.set("addr", ip)
        addr_ip.set("addrtype", "ipv4")

        mac = dd.get("mac", "")
        if mac:
            addr_mac = ET.SubElement(host_el, "address")
            addr_mac.set("addr", mac.upper())
            addr_mac.set("addrtype", "mac")
            vendor = dd.get("vendor", "")
            if vendor:
                addr_mac.set("vendor", vendor)

        hostnames_el = ET.SubElement(host_el, "hostnames")
        hostname = dd.get("hostname", "")
        if hostname and hostname != ip:
            hn = ET.SubElement(hostnames_el, "hostname")
            hn.set("name", hostname)
            hn.set("type", "PTR")

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

        risk_level = dd.get("risk_level", "")
        if risk_level:
            hscript = ET.SubElement(host_el, "hostscript")
            scr = ET.SubElement(hscript, "script")
            scr.set("id", "netsentinel-risk")
            scr.set("output", f"Risk: {risk_level}")

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
    Generate a self-contained HTML ISP Accountability Report.

    Bundles: network grade, traceroute hop table with loss %, ping stats,
    DNS latency, outage log, and a plain-English summary paragraph.
    """
    ts  = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    now = datetime.datetime.now().strftime("%A %d %B %Y, %H:%M")

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


# ── Diagnostic card (compact shareable summary) ───────────────────────────────

def generate_card_html(card_data: dict) -> str:
    """Render a CardData.to_dict() as a compact self-contained HTML share card."""
    grade        = html.escape(str(card_data.get("grade", "N/A")))
    score        = card_data.get("score", 0.0)
    isp          = html.escape(str(card_data.get("isp", "–")))
    findings     = card_data.get("findings", [])
    device_count = card_data.get("device_count", 0)
    generated_at = html.escape(str(card_data.get("generated_at", "")))

    from modules.colours import EXPORT_GREEN_FG as _GF, EXPORT_AMBER_FG as _AF, EXPORT_RED_FG as _RF
    _gc = {"A": _GF, "B": _GF, "C": _AF, "D": _RF, "F": _RF}.get(grade, EXPORT_ACCENT_FG)

    finding_rows = "".join(
        f'<li style="margin-bottom:6px">{html.escape(str(f))}</li>'
        for f in findings
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>NetSentinel — Network Health Card</title>
<style>
{_CSS}
.card-outer {{
  max-width:520px; margin:40px auto;
  background:{EXPORT_CARD}; border:1px solid {EXPORT_BORDER};
  border-radius:12px; padding:28px 28px 20px; font-family:'Segoe UI',Arial,sans-serif;
}}
.grade-circle {{
  display:inline-flex; align-items:center; justify-content:center;
  width:72px; height:72px; border-radius:50%;
  border:3px solid {_gc}; color:{_gc};
  font-size:2.2rem; font-weight:bold; background:{EXPORT_BG};
  float:left; margin-right:18px;
}}
</style>
</head>
<body>
<div class="card-outer">
  <div class="grade-circle">{grade}</div>
  <div style="font-size:1rem;font-weight:bold;color:{EXPORT_HEADING_FG}">NetSentinel — Network Health Card</div>
  <div style="font-size:.85rem;color:{EXPORT_META}">{isp}</div>
  <div style="font-size:.8rem;color:{EXPORT_META}">Score {score:.0f}/100 &nbsp;·&nbsp; {device_count} device(s) &nbsp;·&nbsp; {generated_at}</div>
  <hr style="border:none;border-top:1px solid {EXPORT_BORDER};margin:18px 0 12px;clear:both">
  <ul style="padding-left:18px;margin:0">{finding_rows}</ul>
  <div style="font-size:.72rem;color:{EXPORT_META};margin-top:16px;border-top:1px solid {EXPORT_BORDER};padding-top:10px">
    Generated by <a href="https://github.com/ossianericson/netsentinel">NetSentinel</a> — free, open-source network troubleshooting
  </div>
</div>
</body>
</html>"""


def save_card_html(card_data: dict, output_path: Path) -> Path:
    """Write the diagnostic card as HTML. Returns the output path."""
    output_path.write_text(generate_card_html(card_data), encoding="utf-8")
    return output_path


# ── Lab / scenario mode report ────────────────────────────────────────────────

def generate_lab_html(result: dict) -> str:
    """Render a LabResult.to_dict() as a self-contained HTML report."""
    ts = result.get("completed_at", "")
    title = html.escape(result.get("scenario_title", "Lab Exercise"))
    verdict = result.get("verdict", "INCOMPLETE")
    steps_done = result.get("steps_completed", 0)
    steps_total = result.get("steps_total", 0)
    hints_used = result.get("hints_used", 0)
    machine_fp = result.get("machine_fp", "")
    findings = result.get("findings", [])

    verdict_cls = {"PASS": "green", "PARTIAL": "amber", "INCOMPLETE": "amber"}.get(verdict, "amber")
    verdict_icon = {"green": "✓", "amber": "△"}.get(verdict_cls, "△")

    rows_html = ""
    for f in findings:
        cells = "".join(
            f"<td>{html.escape(str(v))}</td>" for v in f.values()
        )
        rows_html += f"<tr>{cells}</tr>"

    headers_html = ""
    if findings:
        headers_html = "".join(
            f"<th>{html.escape(str(k))}</th>" for k in findings[0].keys()
        )

    findings_section = ""
    if findings:
        findings_section = f"""
<div class="module">
  <h3>Findings</h3>
  <table><thead><tr>{headers_html}</tr></thead><tbody>{rows_html}</tbody></table>
</div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>NetSentinel — Lab Report: {title}</title>
<style>{_CSS}</style>
</head>
<body>
<h1>NetSentinel — Lab Report</h1>
<p class="subtitle">{title} &mdash; {ts}</p>
<div class="verdict-box {verdict_cls}">
  <h2>{verdict_icon} {verdict}</h2>
  <p>Steps completed: {steps_done} / {steps_total} &nbsp;&nbsp;|&nbsp;&nbsp; Hints used: {hints_used}</p>
</div>
{findings_section}
<p class="meta">Machine fingerprint: {machine_fp} &nbsp;&nbsp;|&nbsp;&nbsp;
Generated by <a href="https://github.com/ossianericson/netsentinel">NetSentinel</a></p>
</body>
</html>"""


def save_lab_report(result: dict, output_path: Path) -> Path:
    """Write a lab result HTML report. Returns the output path."""
    output_path.write_text(generate_lab_html(result), encoding="utf-8")
    return output_path
