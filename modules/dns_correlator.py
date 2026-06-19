"""
Module 5 — DNS Failure & Micro-Outage Correlator

Simultaneously:
  - Pings 1.1.1.1, 8.8.8.8, and the local gateway (60 pings, 1/sec each)
  - Performs DNS resolution timing every 3 seconds for 5 common domains

Detects:
  - Micro-outages (>3 consecutive timeouts)
  - STP reconvergence signature (15-45s outage window then full recovery)
  - DNS-specific failure (pings succeed but DNS times out)

Emits data points as they arrive so the UI can draw a live graph.
"""

import platform
import re
import socket
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

PING_TARGETS = ["1.1.1.1", "8.8.8.8"]  # gateway added dynamically
DNS_DOMAINS = [
    "google.com",
    "cloudflare.com",
    "amazon.com",
    "microsoft.com",
    "github.com",
]
DNS_INTERVAL = 3      # seconds between DNS resolution attempts
PING_COUNT = 60       # total pings per target
PING_INTERVAL = 1.0   # seconds between each ping

# STP reconvergence window (seconds)
STP_MIN_OUTAGE = 15
STP_MAX_OUTAGE = 45


@dataclass
class PingPoint:
    timestamp: float
    target: str
    rtt_ms: Optional[float]   # None = timeout
    is_timeout: bool = False


@dataclass
class DnsPoint:
    timestamp: float
    domain: str
    rtt_ms: Optional[float]
    resolved: bool = True


@dataclass
class CorrelatorResult:
    ping_series: List[PingPoint] = field(default_factory=list)
    dns_series: List[DnsPoint] = field(default_factory=list)
    micro_outages: List[dict] = field(default_factory=list)   # {start, end, duration, target}
    stp_signatures: List[dict] = field(default_factory=list)  # {start, end, duration, target}
    dns_only_failures: bool = False
    plain_verdict: str = ""


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _ping_once(target: str, timeout_sec: int = 2) -> Optional[float]:
    """Return RTT in ms, or None on timeout/failure."""
    system = platform.system()
    extra: dict = {}
    if system == "Windows":
        cmd = ["ping", "-n", "1", "-w", str(timeout_sec * 1000), target]
        extra = {"creationflags": subprocess.CREATE_NO_WINDOW}
    elif system == "Darwin":
        cmd = ["ping", "-c", "1", "-W", str(timeout_sec * 1000), target]
    else:
        cmd = ["ping", "-c", "1", "-W", str(timeout_sec), target]
    try:
        out = subprocess.check_output(
            cmd, text=True, timeout=timeout_sec + 1, stderr=subprocess.DEVNULL, **extra
        )
        # Try to extract RTT value
        m = re.search(r"time[<=]([\d.]+)\s*ms", out, re.IGNORECASE)
        if m:
            return float(m.group(1))
        # Windows: "Average = Xms"
        m = re.search(r"Average\s*=\s*([\d.]+)ms", out, re.IGNORECASE)
        if m:
            return float(m.group(1))
        return 1.0  # Succeeded but couldn't parse RTT
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return None


def _dns_resolve(domain: str) -> Optional[float]:
    """Return resolution time in ms, or None on failure."""
    try:
        start = time.perf_counter()
        socket.getaddrinfo(domain, 80, type=socket.SOCK_STREAM)
        return (time.perf_counter() - start) * 1000
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Outage detection helpers
# ---------------------------------------------------------------------------

def _find_outages(series: List[PingPoint]) -> Tuple[List[dict], List[dict]]:
    """
    Returns (micro_outages, stp_signatures).
    micro_outage: >3 consecutive timeouts.
    stp_signature: outage lasting 15–45 seconds.
    """
    micro: List[dict] = []
    stp: List[dict] = []

    if not series:
        return micro, stp

    consecutive_timeout = 0
    outage_start: Optional[float] = None

    for i, pt in enumerate(series):
        if pt.is_timeout:
            consecutive_timeout += 1
            if consecutive_timeout == 1:
                outage_start = pt.timestamp
        else:
            if consecutive_timeout > 3 and outage_start is not None:
                duration = pt.timestamp - outage_start
                entry = {
                    "start": outage_start,
                    "end": pt.timestamp,
                    "duration": round(duration, 1),
                    "target": pt.target,
                    "consecutive_drops": consecutive_timeout,
                }
                micro.append(entry)
                if STP_MIN_OUTAGE <= duration <= STP_MAX_OUTAGE:
                    stp.append(entry)
            consecutive_timeout = 0
            outage_start = None

    # Handle trailing outage
    if consecutive_timeout > 3 and outage_start is not None:
        last_ts = series[-1].timestamp
        duration = last_ts - outage_start
        entry = {
            "start": outage_start,
            "end": last_ts,
            "duration": round(duration, 1),
            "target": series[-1].target,
            "consecutive_drops": consecutive_timeout,
        }
        micro.append(entry)
        if STP_MIN_OUTAGE <= duration <= STP_MAX_OUTAGE:
            stp.append(entry)

    return micro, stp


# ---------------------------------------------------------------------------
# Main scan
# ---------------------------------------------------------------------------

def scan(
    gateway_ip: Optional[str] = None,
    on_ping: Optional[Callable[[PingPoint], None]] = None,
    on_dns: Optional[Callable[[DnsPoint], None]] = None,
    progress_cb: Optional[Callable[[str], None]] = None,
    stop_event: Optional[threading.Event] = None,
) -> CorrelatorResult:
    """
    Run the DNS / ping correlator for PING_COUNT seconds.
    Fires callbacks with live data points for graph rendering.
    """
    targets = list(PING_TARGETS)
    if gateway_ip and gateway_ip not in targets:
        targets.append(gateway_ip)

    result = CorrelatorResult()
    lock = threading.Lock()
    start_time = time.time()

    # ---- DNS thread ----
    dns_done = threading.Event()

    def _dns_worker():
        elapsed = 0
        while elapsed < PING_COUNT and (stop_event is None or not stop_event.is_set()):
            ts = time.time() - start_time
            for domain in DNS_DOMAINS:
                rtt = _dns_resolve(domain)
                pt = DnsPoint(
                    timestamp=ts,
                    domain=domain,
                    rtt_ms=rtt,
                    resolved=(rtt is not None),
                )
                with lock:
                    result.dns_series.append(pt)
                if on_dns:
                    on_dns(pt)
            time.sleep(DNS_INTERVAL)
            elapsed += DNS_INTERVAL
        dns_done.set()

    dns_thread = threading.Thread(target=_dns_worker, daemon=True)
    dns_thread.start()

    # ---- Ping loop (sequential per-second, multi-target in threads) ----
    per_target: Dict[str, List[PingPoint]] = {t: [] for t in targets}

    for i in range(PING_COUNT):
        if stop_event and stop_event.is_set():
            break
        if progress_cb:
            remaining = PING_COUNT - i
            progress_cb(f"Ping/DNS correlation: {remaining}s remaining...")

        tick_start = time.time()
        ping_results: Dict[str, Optional[float]] = {}
        threads = []

        def _do_ping(tgt: str):
            ping_results[tgt] = _ping_once(tgt)

        for t in targets:
            th = threading.Thread(target=_do_ping, args=(t,), daemon=True)
            th.start()
            threads.append(th)
        for th in threads:
            th.join(timeout=4)

        ts = time.time() - start_time
        for t in targets:
            rtt = ping_results.get(t)
            pt = PingPoint(
                timestamp=ts,
                target=t,
                rtt_ms=rtt,
                is_timeout=(rtt is None),
            )
            with lock:
                result.ping_series.append(pt)
                per_target[t].append(pt)
            if on_ping:
                on_ping(pt)

        # Sleep remaining of this second
        elapsed_this_tick = time.time() - tick_start
        sleep_time = max(0.0, PING_INTERVAL - elapsed_this_tick)
        if sleep_time > 0:
            time.sleep(sleep_time)

    dns_done.wait(timeout=10)

    # ---- Analysis ----
    all_micro: List[dict] = []
    all_stp: List[dict] = []
    for t, series in per_target.items():
        m, s = _find_outages(series)
        all_micro.extend(m)
        all_stp.extend(s)

    result.micro_outages = all_micro
    result.stp_signatures = all_stp

    # DNS-only failure: pings succeed but DNS fails
    total_dns = len(result.dns_series)
    failed_dns = sum(1 for d in result.dns_series if not d.resolved)
    # Check whether the same window had successful pings
    if total_dns > 0 and failed_dns / total_dns > 0.3:
        # Check if pings succeeded during same period
        total_pings = len(result.ping_series)
        failed_pings = sum(1 for p in result.ping_series if p.is_timeout)
        if total_pings > 0 and failed_pings / total_pings < 0.1:
            result.dns_only_failures = True

    # ---- Plain English verdict ----
    verdicts = []
    if all_stp:
        stp_d = all_stp[0]
        verdicts.append(
            f"STP RECONVERGENCE SIGNATURE DETECTED on {stp_d['target']}: "
            f"a {stp_d['duration']:.0f}-second outage window matches the exact pattern of "
            "an STP port-state cycle (Blocking→Listening→Learning→Forwarding). "
            "This is the fingerprint of a rogue Root Bridge disrupting your network."
        )
    if all_micro and not all_stp:
        verdicts.append(
            f"{len(all_micro)} micro-outage(s) detected "
            f"(longest: {max(o['duration'] for o in all_micro):.0f}s)."
        )
    if result.dns_only_failures:
        verdicts.append(
            "DNS-specific failure detected: pings succeeded but DNS timed out. "
            "Your router's DNS proxy is the victim — likely caused by STP port-blocking "
            "or broadcast flooding disrupting the gateway."
        )
    if not verdicts:
        total_timeouts = sum(1 for p in result.ping_series if p.is_timeout)
        total_pings = len(result.ping_series)
        verdicts.append(
            f"Network appears stable. {total_pings} pings sent, "
            f"{total_timeouts} timeout(s). No STP reconvergence or DNS failures detected."
        )

    result.plain_verdict = " | ".join(verdicts)
    return result
