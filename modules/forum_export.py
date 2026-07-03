"""
Forum-ready Markdown export — turns a diagnosis or service-diagnostics result
into a pristine, sanitized Markdown post suitable for pasting into a public
forum thread (r/HomeNetworking, Discord, etc).

Sanitization is mandatory and automatic: private IPs are aliased, public IPs
are omitted, MAC addresses are stripped, hostnames are never included.
See modules/report_sanitizer.py.
"""

from __future__ import annotations

from typing import List

from modules.report_sanitizer import sanitize_text

_FOOTER = "\n---\n*Diagnostics compiled by NetSentinel (free, Microsoft Store)*\n"


def _metrics_table(rows: List[tuple]) -> str:
    if not rows:
        return ""
    lines = ["| Metric | Value |", "|---|---|"]
    lines += [f"| {name} | {value} |" for name, value in rows]
    return "\n".join(lines) + "\n"


def build_diagnosis_markdown(result, symptom: str = "") -> str:
    """Build a forum-ready Markdown post from a CorrelationResult."""
    ip_map: dict = {}
    title = f"NetSentinel Diagnosis: {symptom}" if symptom else "NetSentinel Diagnosis: What's Wrong?"

    metrics = getattr(result, "metrics", {}) or {}
    rows = []
    if "ping_ms" in metrics:
        rows.append(("Ping", f"{metrics['ping_ms']:.1f} ms"))
    if "jitter_ms" in metrics:
        rows.append(("Jitter", f"{metrics['jitter_ms']:.1f} ms"))
    if "loss_pct" in metrics:
        rows.append(("Packet loss", f"{metrics['loss_pct']:.1f}%"))
    if "dns_ms" in metrics:
        rows.append(("DNS resolve", f"{metrics['dns_ms']:.1f} ms"))
    if "download_mbps" in metrics:
        rows.append(("Download speed", f"{metrics['download_mbps']:.1f} Mbps"))

    parts = [f"## {title}\n"]
    summary = sanitize_text(getattr(result, "plain_summary", "") or "", ip_map)
    if summary:
        parts.append(f"**Verdict:** {summary}\n")
    table = _metrics_table(rows)
    if table:
        parts.append(table)

    findings = getattr(result, "findings", []) or []
    if findings:
        parts.append("### Findings\n")
        for f in findings:
            headline = sanitize_text(getattr(f, "headline", ""), ip_map)
            remediation = sanitize_text(getattr(f, "remediation", ""), ip_map)
            severity = getattr(f, "severity", "")
            parts.append(f"**{headline}** _({severity})_\n")
            if remediation:
                parts.append(f"> {remediation}\n")

    parts.append(_FOOTER)
    return "\n".join(parts)


def build_service_diagnostics_markdown(result) -> str:
    """Build a forum-ready Markdown post from a ServiceDiagnosticResult."""
    ip_map: dict = {}
    service_name = getattr(result, "service_name", "Service")

    rows = []
    for p in getattr(result, "dns_probes", []) or []:
        if getattr(p, "rtt_ms", -1) >= 0:
            rows.append((f"DNS resolve ({p.hostname})", f"{p.rtt_ms:.1f} ms"))
    for p in getattr(result, "tcp_probes", []) or []:
        if getattr(p, "rtt_ms", -1) >= 0:
            rows.append((f"TCP connect (port {p.port})", f"{p.rtt_ms:.1f} ms"))
    for p in getattr(result, "https_probes", []) or []:
        if getattr(p, "rtt_ms", -1) >= 0:
            rows.append(("HTTPS response", f"{p.rtt_ms:.1f} ms"))
    icmp = getattr(result, "icmp_result", None)
    if icmp is not None:
        rows.append(("ICMP avg / jitter / loss",
                      f"{icmp.avg_ms:.1f} ms / {icmp.jitter_ms:.1f} ms / {icmp.loss_pct:.1f}%"))

    parts = [f"## NetSentinel Service Diagnostics: {service_name}\n"]
    failure_layer = getattr(result, "failure_layer", "none")
    if failure_layer and failure_layer != "none":
        parts.append(f"**Failure layer:** `{failure_layer}`\n")
    summary = sanitize_text(getattr(result, "summary", "") or "", ip_map)
    if summary:
        parts.append(f"**Verdict:** {summary}\n")
    table = _metrics_table(rows)
    if table:
        parts.append(table)

    parts.append(_FOOTER)
    return "\n".join(parts)
