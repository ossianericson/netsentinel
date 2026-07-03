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


def build_isp_forum_markdown(log_summary=None, diag_result=None,
                             benchmark_result=None, isp_name: str = "") -> str:
    """Build a forum-ready Markdown post presenting the evidence a user would
    take to r/HomeNetworking when complaining about their ISP.

    Sourced from the same measurements as the ISP complaint email
    (report_isp.generate_isp_complaint_text) but formatted as a Markdown post.
    The public WAN IP is never included; all free text is scrubbed via
    report_sanitizer.
    """
    ip_map: dict = {}

    uptime  = getattr(log_summary, "uptime_pct",    None) if log_summary else None
    avg_rtt = getattr(log_summary, "avg_rtt_ms",    -1.0) if log_summary else -1.0
    jitter  = getattr(log_summary, "avg_jitter_ms", -1.0) if log_summary else -1.0
    dl_mbps = getattr(diag_result, "download_mbps", -1.0) if diag_result else -1.0
    outages = getattr(log_summary, "outages",       [])   if log_summary else []

    rows = []
    if uptime is not None:
        rows.append(("Uptime", f"{uptime:.1f}%"))
    if avg_rtt and avg_rtt > 0:
        rows.append(("Average latency", f"{avg_rtt:.1f} ms"))
    if jitter and jitter > 0:
        rows.append(("Average jitter", f"{jitter:.1f} ms"))
    if dl_mbps and dl_mbps > 0:
        rows.append(("Download speed", f"{dl_mbps:.1f} Mbps"))
    rows.append(("Recorded outages", str(len(outages)) if outages else "0"))

    title = f"My ISP ({isp_name}) — measured evidence" if isp_name else "My ISP — measured evidence"
    parts = [f"## {title}\n"]

    if benchmark_result is not None:
        grade = getattr(benchmark_result, "overall_grade", "")
        bscore = getattr(benchmark_result, "overall_score", None)
        if grade:
            score_txt = f"{bscore:.0f}/100" if isinstance(bscore, (int, float)) else ""
            parts.append(f"**NetSentinel network health grade:** {grade} ({score_txt})\n")

    parts.append(
        "I measured my connection locally with NetSentinel and recorded the "
        "following. Sharing in case anyone has seen the same pattern:\n"
    )
    parts.append(_metrics_table(rows))
    parts.append(sanitize_text(
        "Packet loss first appearing at hop 2 or later is inside the ISP network, "
        "not my home wiring.\n", ip_map))
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
