"""
Service Diagnostics Probes — low-level network probes used by DiagnosticEngine.

Each probe runs one measurement and returns a structured result.
Pure Python — no admin privileges required, no PyQt6 imports.
"""
from __future__ import annotations

import platform
import re
import socket
import struct
import subprocess
import time
from dataclasses import dataclass, field
from typing import List, Optional


# ── DNS probe ─────────────────────────────────────────────────────────────────

@dataclass
class DnsProbeResult:
    hostname: str
    ipv4: str = ""       # empty = unresolved
    ipv6: str = ""
    rtt_ms: float = -1.0  # -1 = failed
    error: str = ""


def dns_probe(hostname: str, server: Optional[str] = None) -> DnsProbeResult:
    """Resolve hostname, measuring round-trip time. Optionally query a specific DNS server."""
    result = DnsProbeResult(hostname=hostname)
    t0 = time.monotonic()
    try:
        if server:
            result.ipv4 = _raw_dns_a(hostname, server)
        else:
            result.ipv4 = socket.gethostbyname(hostname)
        result.rtt_ms = (time.monotonic() - t0) * 1000
    except Exception as exc:
        result.error = str(exc)
        result.rtt_ms = -1.0

    # IPv6 best-effort via system resolver
    try:
        infos = socket.getaddrinfo(hostname, None, socket.AF_INET6)
        if infos:
            result.ipv6 = infos[0][4][0]
    except Exception:
        pass  # no AAAA record or IPv6 not available — non-fatal

    return result


def _raw_dns_a(domain: str, server: str) -> str:
    """Send a minimal A-record DNS query directly to server. Returns resolved IPv4 or raises."""
    tid = 0x1A2B
    flags = 0x0100  # RD bit set
    query = struct.pack(">HHHHHH", tid, flags, 1, 0, 0, 0)
    for label in domain.rstrip(".").split("."):
        query += bytes([len(label)]) + label.encode()
    query += b"\x00"
    query += struct.pack(">HH", 1, 1)  # QTYPE A, QCLASS IN
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(2.5)
        s.sendto(query, (server, 53))
        data, _ = s.recvfrom(512)
    pos = 12
    while pos < len(data) and data[pos] != 0:
        pos += data[pos] + 1
    pos += 5  # null + QTYPE + QCLASS
    if pos + 12 <= len(data):
        pos += 10  # name ptr + TYPE + CLASS + TTL
        rdlen = struct.unpack(">H", data[pos: pos + 2])[0]
        pos += 2
        if rdlen == 4 and pos + 4 <= len(data):
            return ".".join(str(b) for b in data[pos: pos + 4])
    raise OSError("No A record in DNS response")


# ── TCP probe ─────────────────────────────────────────────────────────────────

@dataclass
class TcpProbeResult:
    host: str
    port: int
    up: bool = False
    rtt_ms: float = -1.0
    error: str = ""


def tcp_probe(host: str, port: int, timeout: float = 5.0) -> TcpProbeResult:
    """Attempt a TCP connection and measure connect latency."""
    result = TcpProbeResult(host=host, port=port)
    try:
        t0 = time.monotonic()
        with socket.create_connection((host, port), timeout=timeout):
            result.rtt_ms = (time.monotonic() - t0) * 1000
        result.up = True
    except OSError as exc:
        result.error = str(exc)
    return result


# ── HTTPS probe ───────────────────────────────────────────────────────────────

@dataclass
class HttpsProbeResult:
    url: str
    up: bool = False
    status_code: int = 0
    rtt_ms: float = -1.0
    error: str = ""


def https_probe(url: str, timeout: float = 8.0) -> HttpsProbeResult:
    """Make an HTTPS GET request and measure response time."""
    import urllib.error
    import urllib.request
    result = HttpsProbeResult(url=url)
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "NetSentinel/2.0 (connectivity-check)"},
        )
        t0 = time.monotonic()
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read(512)
            result.rtt_ms = (time.monotonic() - t0) * 1000
            result.status_code = resp.status
        result.up = True
    except Exception as exc:
        import urllib.error as _ue
        if isinstance(exc, _ue.HTTPError):
            result.status_code = exc.code
            result.up = exc.code < 500  # 4xx = reachable; 5xx = server error
            result.error = f"HTTP {exc.code}"
        else:
            result.error = str(exc)
    return result


# ── ICMP probe (ping statistics) ──────────────────────────────────────────────

@dataclass
class IcmpProbeResult:
    host: str
    min_ms: float = -1.0
    avg_ms: float = -1.0
    max_ms: float = -1.0
    loss_pct: float = 100.0
    jitter_ms: float = -1.0
    error: str = ""


def icmp_probe(host: str, count: int = 4) -> IcmpProbeResult:
    """Run a ping and return latency statistics."""
    result = IcmpProbeResult(host=host)
    system = platform.system()
    extra: dict = (
        {"creationflags": subprocess.CREATE_NO_WINDOW} if system == "Windows" else {}
    )
    try:
        if system == "Windows":
            cmd = ["ping", "-n", str(count), "-w", "2000", host]
        else:
            cmd = ["ping", "-c", str(count), "-W", "2", host]
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=count * 3 + 5,
            **extra,
        )
        _parse_ping_output(r.stdout, result, system)
    except Exception as exc:
        result.error = str(exc)
    return result


def _parse_ping_output(output: str, result: IcmpProbeResult, system: str) -> None:
    if system == "Windows":
        m = re.search(
            r"Minimum\s*=\s*(\d+)ms.*?Maximum\s*=\s*(\d+)ms.*?Average\s*=\s*(\d+)ms",
            output,
            re.DOTALL,
        )
        if m:
            result.min_ms = float(m.group(1))
            result.max_ms = float(m.group(2))
            result.avg_ms = float(m.group(3))
            result.jitter_ms = result.max_ms - result.min_ms
        loss_m = re.search(r"(\d+)%\s+loss", output)
        if loss_m:
            result.loss_pct = float(loss_m.group(1))
        elif result.avg_ms >= 0:
            result.loss_pct = 0.0
    else:
        m = re.search(
            r"min/avg/max(?:/mdev)?\s*=\s*([\d.]+)/([\d.]+)/([\d.]+)(?:/([\d.]+))?",
            output,
        )
        if m:
            result.min_ms = float(m.group(1))
            result.avg_ms = float(m.group(2))
            result.max_ms = float(m.group(3))
            result.jitter_ms = (
                float(m.group(4)) if m.group(4) else result.max_ms - result.min_ms
            )
        loss_m = re.search(r"(\d+(?:\.\d+)?)%\s+packet\s+loss", output)
        if loss_m:
            result.loss_pct = float(loss_m.group(1))
        elif result.avg_ms >= 0:
            result.loss_pct = 0.0


# ── Traceroute probe ──────────────────────────────────────────────────────────

@dataclass
class TraceHop:
    hop: int
    ip: str
    rtt_ms: float = -1.0


@dataclass
class TracerouteResult:
    host: str
    hops: List[TraceHop] = field(default_factory=list)
    hop_count: int = 0
    reached: bool = False
    anomalies: List[str] = field(default_factory=list)


def traceroute_probe(host: str, max_hops: int = 15) -> TracerouteResult:
    """Run a traceroute and detect routing anomalies."""
    result = TracerouteResult(host=host)
    system = platform.system()
    extra: dict = (
        {"creationflags": subprocess.CREATE_NO_WINDOW} if system == "Windows" else {}
    )
    try:
        if system == "Windows":
            cmd = ["tracert", "-d", "-w", "1000", "-h", str(max_hops), host]
        else:
            cmd = ["traceroute", "-n", "-w", "2", "-m", str(max_hops), host]
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=max_hops * 5 + 10,
            **extra,
        )
        _parse_traceroute(r.stdout, result, system)
    except Exception as exc:
        result.anomalies.append(f"Traceroute failed: {exc}")
    return result


def _parse_traceroute(output: str, result: TracerouteResult, system: str) -> None:
    if system == "Windows":
        # tracert: "  1    <1 ms    <1 ms    <1 ms  192.168.1.1"
        pattern = re.compile(
            r"^\s*(\d+)\s+"
            r"(?:(?:<?\d+\s+ms\s+){1,3})?"
            r"([\d.]+|\*)\s*$",
            re.MULTILINE,
        )
    else:
        pattern = re.compile(
            r"^\s*(\d+)\s+(?:([\d.]+)\s+ms\s+)?([\d.]+|\*)",
            re.MULTILINE,
        )

    prev_ip = ""
    timeout_run = 0
    for m in pattern.finditer(output):
        hop_n = int(m.group(1))
        ip = m.group(2) if system != "Windows" and m.lastindex >= 3 else m.group(m.lastindex)
        rtt_raw = m.group(2) if system != "Windows" and m.lastindex >= 2 else None
        rtt = float(rtt_raw.lstrip("<")) if rtt_raw and rtt_raw not in ("*", "") else -1.0
        result.hops.append(TraceHop(hop=hop_n, ip=ip, rtt_ms=rtt))

        if ip == "*":
            timeout_run += 1
        else:
            if ip == prev_ip and prev_ip:
                result.anomalies.append(
                    f"Routing loop detected at hop {hop_n} ({ip})"
                )
            timeout_run = 0
        prev_ip = ip

    if result.hops:
        result.hop_count = len(result.hops)
        last_ip = result.hops[-1].ip
        if last_ip not in ("*", ""):
            try:
                resolved = socket.gethostbyname(host)
                result.reached = last_ip == resolved
            except Exception:
                pass  # can't confirm — non-fatal

    if timeout_run >= 3:
        result.anomalies.append(
            f"Path terminated early — last {timeout_run} hops timed out"
        )
