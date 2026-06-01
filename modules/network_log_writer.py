"""
Network log dataclasses, file reader, summary computation, and analysis engine.

Extracted from modules/network_logger.py (S20-6 sprint split).
All public names remain importable from modules.network_logger for
backwards compatibility via re-exports in that module.
"""

import csv
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List
import time

_log = logging.getLogger(__name__)


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class LogEntry:
    timestamp: str
    host: str
    rtt_ms: float          # -1 = unreachable
    status: str            # OK / SLOW / FAIL
    jitter_ms: float = -1.0
    dns_ms: float = -1.0
    http_status: int = -1
    http_ms: float = -1.0
    arp_event: str = ""


@dataclass
class OutageSummary:
    host: str
    start: str
    end: str
    duration_s: float
    peak_latency_ms: float
    consecutive_fails: int


@dataclass
class LogSummary:
    entries: List[LogEntry] = field(default_factory=list)
    outages: List[OutageSummary] = field(default_factory=list)
    arp_events: List[str] = field(default_factory=list)
    total_pings: int = 0
    failed_pings: int = 0
    slow_pings: int = 0
    avg_rtt_ms: float = 0.0
    avg_jitter_ms: float = 0.0
    avg_dns_ms: float = 0.0
    uptime_pct: float = 100.0
    log_path: str = ""


# ── Path helper ───────────────────────────────────────────────────────────────

def _default_log_dir() -> Path:
    """Return the directory where log files are stored (~/Documents/NetSentinel/logs)."""
    docs = Path.home() / "Documents" / "NetSentinel" / "logs"
    docs.mkdir(parents=True, exist_ok=True)
    return docs


def _log_path_for_session() -> Path:
    ts = time.strftime("%Y%m%d_%H%M%S")
    return _default_log_dir() / f"netlog_{ts}.csv"


# ── Log file reader ───────────────────────────────────────────────────────────

def load_log_file(path: Path) -> LogSummary:
    """Load and summarise an existing CSV log file."""
    entries: List[LogEntry] = []
    try:
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    rtt = float(row.get("rtt_ms", "-1") or "-1")
                    entries.append(LogEntry(
                        timestamp=row.get("timestamp", ""),
                        host=row.get("host", "?"),
                        rtt_ms=rtt,
                        status=row.get("status", "UNKNOWN"),
                        jitter_ms=float(row.get("jitter_ms", "-1") or "-1"),
                        dns_ms=float(row.get("dns_ms", "-1") or "-1"),
                        http_status=int(row.get("http_status", "-1") or "-1"),
                        http_ms=float(row.get("http_ms", "-1") or "-1"),
                        arp_event=row.get("arp_event", ""),
                    ))
                except (ValueError, KeyError):
                    continue
    except Exception as exc:
        _log.debug("could not read log file %s: %s", path, exc)
    return _compute_summary(entries, str(path))


def list_log_files() -> List[Path]:
    """Return sorted list of all log files, newest first."""
    return sorted(_default_log_dir().glob("netlog_*.csv"), reverse=True)


# ── Summary computation ───────────────────────────────────────────────────────

def _compute_summary(entries: List[LogEntry], log_path: str) -> LogSummary:
    import datetime as _dt
    from itertools import groupby

    summary = LogSummary(entries=entries, log_path=log_path)
    if not entries:
        return summary

    summary.total_pings = len(entries)
    summary.failed_pings = sum(1 for e in entries if e.status == "FAIL")
    summary.slow_pings = sum(1 for e in entries if e.status == "SLOW")

    good_rtts = [e.rtt_ms for e in entries if e.rtt_ms >= 0]
    summary.avg_rtt_ms = sum(good_rtts) / len(good_rtts) if good_rtts else 0.0

    good_jitter = [e.jitter_ms for e in entries if e.jitter_ms >= 0]
    summary.avg_jitter_ms = sum(good_jitter) / len(good_jitter) if good_jitter else 0.0

    good_dns = [e.dns_ms for e in entries if e.dns_ms >= 0]
    summary.avg_dns_ms = sum(good_dns) / len(good_dns) if good_dns else 0.0

    ok_count = summary.total_pings - summary.failed_pings
    summary.uptime_pct = (ok_count / summary.total_pings * 100) if summary.total_pings else 100.0

    summary.arp_events = [
        f"{e.timestamp}  {e.arp_event}"
        for e in entries if e.arp_event
    ]

    hosts = sorted(set(e.host for e in entries))
    for host in hosts:
        host_entries = [e for e in entries if e.host == host]
        for is_fail, group in groupby(host_entries, key=lambda e: e.status == "FAIL"):
            if not is_fail:
                continue
            group_list = list(group)
            try:
                all_ts = []
                for e in host_entries:
                    try:
                        all_ts.append(_dt.datetime.fromisoformat(e.timestamp))
                    except Exception as exc:
                        _log.debug("bad timestamp %r: %s", e.timestamp, exc)
                if len(all_ts) > 1:
                    gaps = [(all_ts[i+1] - all_ts[i]).total_seconds()
                            for i in range(len(all_ts) - 1)]
                    interval = sum(gaps) / len(gaps)
                else:
                    interval = 60.0
                duration_s = len(group_list) * interval
                peak = max((e.rtt_ms for e in group_list if e.rtt_ms >= 0), default=0.0)
                summary.outages.append(OutageSummary(
                    host=host,
                    start=group_list[0].timestamp,
                    end=group_list[-1].timestamp,
                    duration_s=duration_s,
                    peak_latency_ms=peak,
                    consecutive_fails=len(group_list),
                ))
            except Exception as exc:
                _log.debug("outage group calculation failed: %s", exc)

    return summary


# ── Automatic log analysis ────────────────────────────────────────────────────

@dataclass
class AnalysisFinding:
    severity: str   # "HIGH" / "WARN" / "INFO"
    category: str   # "Outages" / "Latency" / "DNS" / "Jitter" / "ARP" / "Pattern" / "Clean"
    title: str
    detail: str


def analyse_log(summary: LogSummary) -> List[AnalysisFinding]:
    """
    Inspect a LogSummary and return plain-English diagnostic findings sorted
    by severity (HIGH first).  Always returns at least one INFO finding.
    """
    import statistics as _stats
    import datetime as _dt

    findings: List[AnalysisFinding] = []
    n_out = len(summary.outages)

    if n_out > 0:
        total_s = sum(o.duration_s for o in summary.outages)
        longest_s = max(o.duration_s for o in summary.outages)
        sev = "HIGH" if n_out >= 5 or summary.uptime_pct < 95 else "WARN"
        findings.append(AnalysisFinding(
            severity=sev, category="Outages",
            title=f"{n_out} outage(s) — {summary.uptime_pct:.1f}% uptime",
            detail=(
                f"Total downtime: {total_s / 60:.1f} min.  "
                f"Longest single outage: {longest_s / 60:.1f} min."
            ),
        ))

    if n_out >= 2:
        try:
            hours = []
            for o in summary.outages:
                for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
                    try:
                        hours.append(_dt.datetime.strptime(o.start, fmt).hour)
                        break
                    except ValueError:
                        continue
            if hours:
                from collections import Counter as _Counter
                buckets = _Counter((h // 3) * 3 for h in hours)
                peak_start, peak_count = buckets.most_common(1)[0]
                if peak_count / n_out >= 0.5:
                    findings.append(AnalysisFinding(
                        severity="WARN", category="Pattern",
                        title=f"Outages concentrated {peak_start:02d}:00–{peak_start+3:02d}:00",
                        detail=(
                            f"{peak_count}/{n_out} outages occurred in this 3-hour window.  "
                            "Possible ISP maintenance window or a scheduled task causing traffic disruption."
                        ),
                    ))
        except Exception as exc:
            _log.debug("time-of-day analysis failed: %s", exc)

    if n_out >= 1:
        tracked_hosts = {e.host for e in summary.entries}
        outage_hosts  = {o.host for o in summary.outages}
        if len(tracked_hosts) > 1 and tracked_hosts == outage_hosts:
            findings.append(AnalysisFinding(
                severity="WARN", category="Outages",
                title="All monitored hosts affected simultaneously",
                detail=(
                    "Every tracked host had outages.  "
                    "Points to an upstream ISP issue or gateway restart rather than a per-host routing problem."
                ),
            ))

    if n_out >= 3:
        try:
            starts = []
            for o in summary.outages:
                for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
                    try:
                        starts.append(_dt.datetime.strptime(o.start, fmt))
                        break
                    except ValueError:
                        continue
            if len(starts) >= 3:
                starts.sort()
                gaps = [(starts[i + 1] - starts[i]).total_seconds() for i in range(len(starts) - 1)]
                mean_gap = _stats.mean(gaps)
                stdev_gap = _stats.stdev(gaps) if len(gaps) > 1 else 0.0
                if mean_gap > 60 and stdev_gap < mean_gap * 0.25:
                    findings.append(AnalysisFinding(
                        severity="WARN", category="Pattern",
                        title=f"Outages recurring every ~{mean_gap / 60:.0f} minutes",
                        detail=(
                            f"Gap between outages: {mean_gap / 60:.0f} min ± {stdev_gap / 60:.0f} min.  "
                            "Possible causes: STP reconvergence cycle, DHCP renewal loop, or a device rebooting on schedule."
                        ),
                    ))
        except Exception as exc:
            _log.debug("recurrence analysis failed: %s", exc)

    if summary.avg_dns_ms > 0 and summary.avg_rtt_ms > 0:
        ratio = summary.avg_dns_ms / summary.avg_rtt_ms
        if ratio > 5:
            findings.append(AnalysisFinding(
                severity="WARN", category="DNS",
                title=f"DNS latency is {ratio:.0f}× the ping RTT",
                detail=(
                    f"Avg DNS: {summary.avg_dns_ms:.0f} ms  vs  avg RTT: {summary.avg_rtt_ms:.0f} ms.  "
                    "Possible DNS hijacking, captive portal, or ISP DNS throttling.  "
                    "Try switching to 8.8.8.8 or 1.1.1.1."
                ),
            ))
        elif ratio > 3:
            findings.append(AnalysisFinding(
                severity="INFO", category="DNS",
                title=f"DNS latency slightly elevated ({summary.avg_dns_ms:.0f} ms)",
                detail=f"DNS is {ratio:.1f}× the ping RTT.  Not critical; consider a faster resolver.",
            ))

    if summary.avg_jitter_ms > 0:
        if summary.avg_jitter_ms >= 50:
            findings.append(AnalysisFinding(
                severity="HIGH", category="Jitter",
                title=f"Very high jitter — {summary.avg_jitter_ms:.0f} ms average",
                detail=(
                    "Jitter ≥ 50 ms severely degrades VoIP, video calls, and gaming.  "
                    "Check for Wi-Fi interference, bandwidth saturation, or a congested upstream link."
                ),
            ))
        elif summary.avg_jitter_ms >= 20:
            findings.append(AnalysisFinding(
                severity="WARN", category="Jitter",
                title=f"Elevated jitter — {summary.avg_jitter_ms:.0f} ms average",
                detail=(
                    "Jitter ≥ 20 ms can cause choppy VoIP and inconsistent gaming.  "
                    "Check for Wi-Fi interference or bandwidth contention."
                ),
            ))

    if summary.total_pings > 0:
        slow_pct = (summary.slow_pings / summary.total_pings) * 100
        if slow_pct >= 20:
            sev = "HIGH" if slow_pct >= 50 else "WARN"
            findings.append(AnalysisFinding(
                severity=sev, category="Latency",
                title=f"{slow_pct:.0f}% of pings exceeded the slow threshold",
                detail=(
                    f"{summary.slow_pings}/{summary.total_pings} pings were slow.  "
                    "Persistent high latency suggests chronic congestion, a poor WAN route, or ISP throttling."
                ),
            ))

    if summary.arp_events:
        n = len(summary.arp_events)
        findings.append(AnalysisFinding(
            severity="HIGH" if n >= 3 else "WARN", category="ARP",
            title=f"{n} ARP table change(s) detected",
            detail=(
                "ARP changes can mean a new device joined, a device was replaced, or active ARP spoofing.  "
                f"Events: {'; '.join(summary.arp_events[:5])}"
                + (" … (truncated)" if n > 5 else "")
            ),
        ))

    all_hosts = {e.host for e in summary.entries}
    if "google.com" in all_hosts and "8.8.8.8" in all_hosts:
        name_fails = sum(1 for e in summary.entries if e.host == "google.com" and e.status == "FAIL")
        ip_fails   = sum(1 for e in summary.entries if e.host == "8.8.8.8"   and e.status == "FAIL")
        name_total = sum(1 for e in summary.entries if e.host == "google.com")
        ip_total   = sum(1 for e in summary.entries if e.host == "8.8.8.8")
        if name_total and ip_total:
            name_fail_pct = (name_fails / name_total) * 100
            ip_fail_pct   = (ip_fails   / ip_total)   * 100
            if name_fail_pct >= 20 and ip_fail_pct < 5:
                findings.append(AnalysisFinding(
                    severity="HIGH", category="DNS",
                    title="DNS resolution failing while IP connectivity is fine",
                    detail=(
                        f"google.com failed {name_fail_pct:.0f}% of the time; "
                        f"8.8.8.8 only failed {ip_fail_pct:.0f}%.  "
                        "Your internet is working but DNS is broken.  "
                        "Try ipconfig /flushdns or change router DNS to 8.8.8.8."
                    ),
                ))

    if not findings:
        findings.append(AnalysisFinding(
            severity="INFO", category="Clean",
            title="No significant issues detected",
            detail=(
                f"Connection appears stable over this log period.  "
                f"Uptime: {summary.uptime_pct:.1f}%,  avg RTT: {summary.avg_rtt_ms:.0f} ms,  "
                f"total pings: {summary.total_pings}."
            ),
        ))

    _order = {"HIGH": 0, "WARN": 1, "INFO": 2}
    findings.sort(key=lambda f: _order.get(f.severity, 3))
    return findings
