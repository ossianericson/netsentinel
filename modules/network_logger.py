"""
Network Logger — long-term background connectivity monitor.

Pings a configurable list of hosts at a user-defined interval and writes
timestamped CSV log entries so the user can reconstruct the exact times
and duration of any outage, even days after the fact.

Optional per-cycle checks (each individually opt-in):
  • Jitter        — 3 pings per host, logs min/avg/max/jitter
  • DNS latency   — resolves google.com via system DNS, logs ms
  • HTTP check    — GET connectivitycheck.gstatic.com/generate_204, logs status+ms
  • ARP watch     — snapshots IP→MAC table each cycle, alerts on changes

Log format (CSV, columns depend on enabled options):
  timestamp, host, rtt_ms, status [, jitter_ms, dns_ms, http_status, http_ms, arp_event]

Example row (all options on):
  2026-04-26T14:32:01,8.8.8.8,12.4,OK,3.1,18.2,204,45.0,
  2026-04-26T14:33:01,8.8.8.8,-1,FAIL,,,-1,-1,NEW_DEVICE 192.168.68.99=aa:bb:cc:dd:ee:ff
"""

import csv
import platform
import re
import socket
import struct
import subprocess
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class LogEntry:
    timestamp: str
    host: str
    rtt_ms: float          # -1 = unreachable
    status: str            # OK / SLOW / FAIL
    # Optional fields — only populated when the corresponding option is enabled
    jitter_ms: float = -1.0   # stddev of 3 pings (-1 = not measured)
    dns_ms: float = -1.0      # system DNS resolve latency (-1 = not measured)
    http_status: int = -1     # HTTP status code (-1 = not measured)
    http_ms: float = -1.0     # HTTP latency ms
    arp_event: str = ""       # empty or "NEW ip=mac" / "CHANGED ip old->new"


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


# ── Default targets ───────────────────────────────────────────────────────────

DEFAULT_TARGETS = ["8.8.8.8", "1.1.1.1", "google.com"]
SLOW_THRESHOLD_MS = 150.0


# ── Internal helpers ──────────────────────────────────────────────────────────

def _default_log_dir() -> Path:
    """Return the directory where log files are stored (~/Documents/NetSentinel/logs)."""
    docs = Path.home() / "Documents" / "NetSentinel" / "logs"
    docs.mkdir(parents=True, exist_ok=True)
    return docs


def _log_path_for_session() -> Path:
    ts = time.strftime("%Y%m%d_%H%M%S")
    return _default_log_dir() / f"netlog_{ts}.csv"


def _ping_once(host: str) -> float:
    """Ping host once.  Returns RTT in ms or -1 on failure."""
    system = platform.system()
    extra: dict = {"creationflags": subprocess.CREATE_NO_WINDOW} if system == "Windows" else {}
    try:
        if system == "Windows":
            r = subprocess.run(
                ["ping", "-n", "1", "-w", "2000", host],
                capture_output=True, text=True, timeout=4, **extra,
            )
            m = re.search(r"time[=<](\d+)ms", r.stdout)
            if m:
                return float(m.group(1))
            if "time<1ms" in r.stdout:
                return 0.5
        else:
            r = subprocess.run(
                ["ping", "-c", "1", "-W", "2", host],
                capture_output=True, text=True, timeout=4,
            )
            m = re.search(r"time=([\d.]+)\s*ms", r.stdout)
            if m:
                return float(m.group(1))
    except Exception:
        pass
    return -1.0


def _ping_jitter(host: str, count: int = 3) -> Tuple[float, float]:
    """
    Ping `host` `count` times, return (avg_rtt_ms, jitter_ms).
    jitter_ms = standard deviation of successful samples.
    Returns (-1, -1) if all pings fail.
    """
    import math
    rtts = [_ping_once(host) for _ in range(count)]
    good = [r for r in rtts if r >= 0]
    if not good:
        return -1.0, -1.0
    avg = sum(good) / len(good)
    if len(good) < 2:
        return avg, 0.0
    variance = sum((r - avg) ** 2 for r in good) / (len(good) - 1)
    return avg, math.sqrt(variance)


def _dns_latency_system(domain: str = "google.com") -> float:
    """Measure system DNS resolution latency in ms. Returns -1 on failure."""
    try:
        t0 = time.monotonic()
        socket.getaddrinfo(domain, None)
        return (time.monotonic() - t0) * 1000
    except Exception:
        return -1.0


def _http_check_204() -> Tuple[int, float]:
    """
    GET connectivitycheck.gstatic.com/generate_204 — the same endpoint Android
    uses for captive portal detection.  Returns (status_code, latency_ms).
    """
    url = "http://connectivitycheck.gstatic.com/generate_204"
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "NetSentinel/2.0"}
        )
        t0 = time.monotonic()
        with urllib.request.urlopen(req, timeout=5) as resp:
            resp.read(512)
            return resp.status, (time.monotonic() - t0) * 1000
    except urllib.error.HTTPError as exc:
        return exc.code, -1.0
    except Exception:
        return 0, -1.0


def _get_arp_snapshot() -> Dict[str, str]:
    """Return {ip: mac} from the current ARP table."""
    system = platform.system()
    extra: dict = {"creationflags": subprocess.CREATE_NO_WINDOW} if system == "Windows" else {}
    result: Dict[str, str] = {}
    try:
        if system == "Windows":
            raw = subprocess.check_output(["arp", "-a"], text=True, timeout=6, **extra)
            for line in raw.splitlines():
                m = re.search(r"(\d+\.\d+\.\d+\.\d+)\s+([\da-fA-F-]{17})", line)
                if m:
                    ip = m.group(1)
                    mac = m.group(2).replace("-", ":").lower()
                    if mac != "ff:ff:ff:ff:ff:ff":
                        result[ip] = mac
        else:
            raw = subprocess.check_output(["arp", "-n"], text=True, timeout=6)
            for line in raw.splitlines():
                m = re.search(r"(\d+\.\d+\.\d+\.\d+)\s+\S+\s+([\da-fA-F:]{17})", line)
                if m:
                    result[m.group(1)] = m.group(2).lower()
    except Exception:
        pass
    return result

class NetworkLogger:
    """
    Long-term background ping logger with optional per-cycle extras.

    Options (all default OFF except ping):
        enable_jitter  — ping each host 3× per cycle, compute jitter (stddev)
        enable_dns     — measure system DNS resolution latency each cycle
        enable_http    — HTTP GET /generate_204 each cycle (captive portal check)
        enable_arp     — snapshot ARP table each cycle; alert on new/changed entries

    Each option adds overhead — choose only what you need for long unattended runs.
    """

    def __init__(
        self,
        interval_s: int = 60,
        targets: Optional[List[str]] = None,
        log_path: Optional[Path] = None,
        slow_threshold_ms: float = SLOW_THRESHOLD_MS,
        enable_jitter: bool = False,
        enable_dns: bool = False,
        enable_http: bool = False,
        enable_arp: bool = False,
    ):
        self.interval_s = interval_s
        self.targets = targets or list(DEFAULT_TARGETS)
        self.log_path = log_path or _log_path_for_session()
        self.slow_threshold_ms = slow_threshold_ms
        self.enable_jitter = enable_jitter
        self.enable_dns = enable_dns
        self.enable_http = enable_http
        self.enable_arp = enable_arp

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._entries: List[LogEntry] = []
        self._lock = threading.Lock()
        self._on_entry: Optional[Callable[[LogEntry], None]] = None
        self._arp_baseline: Dict[str, str] = {}

    def start(self, on_entry: Optional[Callable[[LogEntry], None]] = None):
        """Start the logging loop in a background thread."""
        self._on_entry = on_entry
        self._stop_event.clear()
        # Build CSV header dynamically based on enabled options
        headers = ["timestamp", "host", "rtt_ms", "status"]
        if self.enable_jitter:
            headers.append("jitter_ms")
        if self.enable_dns:
            headers.append("dns_ms")
        if self.enable_http:
            headers += ["http_status", "http_ms"]
        if self.enable_arp:
            headers.append("arp_event")
        with open(self.log_path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(headers)
        # Seed ARP baseline before first cycle
        if self.enable_arp:
            self._arp_baseline = _get_arp_snapshot()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="NetLogger")
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=max(self.interval_s + 5, 10))

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def log_file(self) -> Path:
        return self.log_path

    # ── Main loop ─────────────────────────────────────────────────────────────

    def _loop(self):
        while not self._stop_event.is_set():
            cycle_start = time.monotonic()

            # ── Per-cycle once: DNS, HTTP, ARP (not per-host) ────────────────
            dns_ms: float = -1.0
            http_status: int = -1
            http_ms: float = -1.0
            arp_event: str = ""

            if self.enable_dns and not self._stop_event.is_set():
                dns_ms = _dns_latency_system("google.com")

            if self.enable_http and not self._stop_event.is_set():
                http_status, http_ms = _http_check_204()

            if self.enable_arp and not self._stop_event.is_set():
                current_arp = _get_arp_snapshot()
                events = []
                for ip, mac in current_arp.items():
                    if ip not in self._arp_baseline:
                        events.append(f"NEW {ip}={mac}")
                    elif self._arp_baseline[ip] != mac:
                        events.append(f"CHANGED {ip} {self._arp_baseline[ip]}->{mac}")
                self._arp_baseline = current_arp
                arp_event = " | ".join(events)

            # ── Per-host ping ────────────────────────────────────────────────
            for host in self.targets:
                if self._stop_event.is_set():
                    break

                ts = time.strftime("%Y-%m-%dT%H:%M:%S")

                if self.enable_jitter:
                    rtt, jitter = _ping_jitter(host, count=3)
                else:
                    rtt = _ping_once(host)
                    jitter = -1.0

                if rtt < 0:
                    status = "FAIL"
                elif rtt > self.slow_threshold_ms:
                    status = "SLOW"
                else:
                    status = "OK"

                entry = LogEntry(
                    timestamp=ts, host=host, rtt_ms=rtt, status=status,
                    jitter_ms=jitter, dns_ms=dns_ms,
                    http_status=http_status, http_ms=http_ms,
                    arp_event=arp_event,
                )

                # Persist row
                row = [ts, host, f"{rtt:.1f}" if rtt >= 0 else "-1", status]
                if self.enable_jitter:
                    row.append(f"{jitter:.1f}" if jitter >= 0 else "")
                if self.enable_dns:
                    row.append(f"{dns_ms:.1f}" if dns_ms >= 0 else "")
                if self.enable_http:
                    row += [str(http_status) if http_status >= 0 else "",
                            f"{http_ms:.1f}" if http_ms >= 0 else ""]
                if self.enable_arp:
                    row.append(arp_event)

                with open(self.log_path, "a", newline="", encoding="utf-8") as f:
                    csv.writer(f).writerow(row)

                with self._lock:
                    self._entries.append(entry)

                if self._on_entry:
                    try:
                        self._on_entry(entry)
                    except Exception:
                        pass

                # DNS/HTTP/ARP are cycle-level — only emit for first host
                dns_ms = -1.0
                http_status = -1
                http_ms = -1.0
                arp_event = ""

            elapsed = time.monotonic() - cycle_start
            remaining = self.interval_s - elapsed
            if remaining > 0:
                self._stop_event.wait(remaining)

    def get_summary(self) -> LogSummary:
        with self._lock:
            entries = list(self._entries)
        return _compute_summary(entries, str(self.log_path))


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
    except Exception:
        pass
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

    # ARP events
    summary.arp_events = [
        f"{e.timestamp}  {e.arp_event}"
        for e in entries if e.arp_event
    ]

    # Detect outages per host
    hosts = sorted(set(e.host for e in entries))
    for host in hosts:
        host_entries = [e for e in entries if e.host == host]
        for is_fail, group in groupby(host_entries, key=lambda e: e.status == "FAIL"):
            if not is_fail:
                continue
            group_list = list(group)
            try:
                # Estimate interval from timestamp gaps
                all_ts = []
                for e in host_entries:
                    try:
                        all_ts.append(_dt.datetime.fromisoformat(e.timestamp))
                    except Exception:
                        pass
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
            except Exception:
                pass

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

    # ── 1. Outage count / uptime ─────────────────────────────────────────────
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

    # ── 2. Time-of-day clustering ────────────────────────────────────────────
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
        except Exception:
            pass

    # ── 3. All targets hit simultaneously ────────────────────────────────────
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

    # ── 4. Periodic outage pattern ───────────────────────────────────────────
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
        except Exception:
            pass

    # ── 5. DNS vs ping latency ratio ─────────────────────────────────────────
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

    # ── 6. Jitter severity ───────────────────────────────────────────────────
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

    # ── 7. Slow pings ────────────────────────────────────────────────────────
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

    # ── 8. ARP events ────────────────────────────────────────────────────────
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

    # ── 9. DNS-only failures (google.com fails, 8.8.8.8 succeeds) ───────────
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

    # ── 10. Clean bill ───────────────────────────────────────────────────────
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

    # Sort: HIGH first, then WARN, then INFO
    _order = {"HIGH": 0, "WARN": 1, "INFO": 2}
    findings.sort(key=lambda f: _order.get(f.severity, 3))
    return findings

