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

Dataclasses, file reader, summary computation, and analysis engine live in
modules/network_log_writer.py (S20-6 sprint split).
"""

import csv
import socket
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from modules.network_log_writer import (
    LogEntry, LogSummary, OutageSummary,
    AnalysisFinding,
    _log_path_for_session,
    load_log_file, list_log_files,
    _compute_summary, analyse_log,
)
from modules.utils_net import get_arp_snapshot, icmp_ping

# Re-export all public names so existing callers continue to work.
__all__ = [
    "LogEntry", "LogSummary", "OutageSummary", "AnalysisFinding",
    "NetworkLogger", "load_log_file", "list_log_files", "analyse_log",
    "DEFAULT_TARGETS", "SLOW_THRESHOLD_MS",
]


# ── Default targets ───────────────────────────────────────────────────────────

DEFAULT_TARGETS = ["8.8.8.8", "1.1.1.1", "google.com"]
SLOW_THRESHOLD_MS = 150.0


# ── Internal helpers ──────────────────────────────────────────────────────────

def _ping_once(host: str) -> float:
    """Ping host once.  Returns RTT in ms or -1 on failure."""
    return icmp_ping(host, timeout=2.0)


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
    return get_arp_snapshot()


class NetworkLogger:
    """
    Long-term background ping logger with optional per-cycle extras.

    Options (all default OFF except ping):
        enable_jitter  — ping each host 3× per cycle, compute jitter (stddev)
        enable_dns     — measure system DNS resolution latency each cycle
        enable_http    — HTTP GET /generate_204 each cycle (captive portal check)
        enable_arp     — snapshot ARP table each cycle; alert on new/changed entries
        rotation_hours — start a new CSV file after this many hours (0 = no rotation,
                         default 12).
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
        rotation_hours: int = 12,
    ):
        self.interval_s = interval_s
        self.targets = targets or list(DEFAULT_TARGETS)
        self.log_path = log_path or _log_path_for_session()
        self.slow_threshold_ms = slow_threshold_ms
        self.enable_jitter = enable_jitter
        self.enable_dns = enable_dns
        self.enable_http = enable_http
        self.enable_arp = enable_arp
        self.rotation_hours = rotation_hours

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._entries: List[LogEntry] = []
        self._lock = threading.Lock()
        self._on_entry: Optional[Callable[[LogEntry], None]] = None
        self._on_rotate: Optional[Callable[[Path, int], None]] = None
        self._arp_baseline: Dict[str, str] = {}
        self._file_start_time: float = 0.0
        self._segment: int = 1

    def _build_headers(self) -> List[str]:
        headers = ["timestamp", "host", "rtt_ms", "status"]
        if self.enable_jitter:
            headers.append("jitter_ms")
        if self.enable_dns:
            headers.append("dns_ms")
        if self.enable_http:
            headers += ["http_status", "http_ms"]
        if self.enable_arp:
            headers.append("arp_event")
        return headers

    def _maybe_rotate(self) -> None:
        if not self.rotation_hours or not self._file_start_time:
            return
        if time.time() - self._file_start_time < self.rotation_hours * 3600:
            return
        new_path = _log_path_for_session()
        with open(new_path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(self._build_headers())
        self.log_path = new_path
        self._file_start_time = time.time()
        self._segment += 1
        if self._on_rotate:
            try:
                self._on_rotate(new_path, self._segment)
            except Exception:
                pass  # non-fatal

    def start(
        self,
        on_entry: Optional[Callable[[LogEntry], None]] = None,
        on_rotate: Optional[Callable[[Path, int], None]] = None,
    ):
        """Start the logging loop in a background thread."""
        self._on_entry = on_entry
        self._on_rotate = on_rotate
        self._stop_event.clear()
        self._segment = 1
        self._file_start_time = time.time()
        with open(self.log_path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(self._build_headers())
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
            self._maybe_rotate()
            cycle_start = time.monotonic()

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
                        pass  # non-fatal

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
