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
from typing import Any, Dict, Optional

# Re-exports for backwards compatibility — callers that do
# `from modules.report_exporter import generate_html` continue to work.
from modules.report_html import (
    generate_html,
    _CSS,
    _badge,
)
from modules.report_pdf import save_pdf_report
from modules.report_isp import generate_isp_report, save_isp_report

__all__ = [
    "save_report", "save_json_report", "save_csv_report",
    "save_lab_report",
    "generate_html", "save_pdf_report",
    "generate_isp_report", "save_isp_report",
]

from modules.colours import (
    EXPORT_BG, EXPORT_TEXT, EXPORT_HEADING_FG, EXPORT_META,
    EXPORT_GREEN_FG, EXPORT_AMBER_FG, EXPORT_RED_FG,
    EXPORT_CARD, EXPORT_BORDER, EXPORT_ACCENT_FG,
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
