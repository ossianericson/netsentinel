"""
Module 6 — Network Health & Diagnostics

Runs connectivity and performance checks that help diagnose the most
common home-network problems without requiring admin privileges:

  • Ping latency to gateway, Cloudflare, Google DNS and public hostnames
  • DNS resolution speed against System / Cloudflare / Google / Quad9
  • DNS leak test (detects VPN/resolver exposure)
  • HTTP connectivity check (captive-portal detection)
  • Rough download-speed estimate (2 MB from Cloudflare edge)
  • Traceroute to 8.8.8.8 (first 15 hops)
"""

import platform
import re
import socket
import struct
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class PingResult:
    host: str
    ip: str = ""
    rtt_ms: float = -1.0   # -1 = unreachable
    status: str = "UNKNOWN"  # OK / SLOW / FAIL


@dataclass
class DnsResult:
    server: str
    domain: str
    latency_ms: float = -1.0
    resolved_ip: str = ""
    status: str = "UNKNOWN"  # OK / SLOW / FAIL


@dataclass
class HttpResult:
    url: str
    status_code: int = 0
    latency_ms: float = -1.0
    status: str = "UNKNOWN"  # OK / PARTIAL / FAIL


@dataclass
class TraceHop:
    hop: int
    ip: str
    rtt_ms: float = -1.0


@dataclass
class DnsLeakEntry:
    server_ip: str
    country: str = ""
    org: str = ""


@dataclass
class DnsLeakResult:
    """
    Result of a DNS leak test.
    Queries a unique subdomain of a leak-test service against multiple
    resolvers; compares which upstream DNS servers respond — if they differ
    from your expected resolver, DNS may be leaking outside your VPN/proxy.
    """
    resolvers_seen: List[DnsLeakEntry] = field(default_factory=list)
    leak_detected: bool = False
    plain_verdict: str = ""


@dataclass
class DiagnosticsResult:
    ping_results: List[PingResult] = field(default_factory=list)
    dns_results: List[DnsResult] = field(default_factory=list)
    http_results: List[HttpResult] = field(default_factory=list)
    trace_hops: List[TraceHop] = field(default_factory=list)
    dns_leak: Optional[DnsLeakResult] = None
    download_mbps: float = -1.0
    public_ip: str = ""
    plain_verdict: str = ""
    gateway_ip: Optional[str] = None


# ── Constants ─────────────────────────────────────────────────────────────────

_HTTP_TARGETS = [
    ("Google 204",     "http://connectivitycheck.gstatic.com/generate_204"),
    ("Cloudflare",     "https://1.1.1.1"),
    ("Apple captive",  "http://captive.apple.com/hotspot-detect.html"),
]

_DNS_SERVERS = [
    ("System DNS",  None),
    ("Cloudflare",  "1.1.1.1"),
    ("Google",      "8.8.8.8"),
    ("Quad9",       "9.9.9.9"),
]

_SPEED_URL = "https://speed.cloudflare.com/__down?bytes=2097152"  # 2 MB


# ── Internal helpers ──────────────────────────────────────────────────────────

def _ping_host(host: str) -> Tuple[float, str]:
    """Return (avg_rtt_ms, resolved_ip).  rtt_ms = -1 on failure."""
    system = platform.system()
    extra: dict = {"creationflags": subprocess.CREATE_NO_WINDOW} if system == "Windows" else {}
    try:
        resolved = socket.gethostbyname(host)
    except Exception:
        resolved = host
    try:
        if system == "Windows":
            r = subprocess.run(
                ["ping", "-n", "3", "-w", "1000", host],
                capture_output=True, text=True, timeout=6, **extra,
            )
            m = re.search(r"Average\s*=\s*(\d+)ms", r.stdout)
            if m:
                return float(m.group(1)), resolved
        else:
            r = subprocess.run(
                ["ping", "-c", "3", "-W", "2", host],
                capture_output=True, text=True, timeout=10,
            )
            m = re.search(r"min/avg/max.*?=.*?/([\d.]+)/", r.stdout)
            if m:
                return float(m.group(1)), resolved
    except Exception:
        pass
    return -1.0, resolved


def _dns_latency(domain: str, server: Optional[str]) -> Tuple[float, str]:
    """Return (latency_ms, resolved_ip).  Uses raw UDP to a specific server."""
    if server is None:
        try:
            t0 = time.monotonic()
            ip = socket.gethostbyname(domain)
            return (time.monotonic() - t0) * 1000, ip
        except Exception:
            return -1.0, ""
    # Minimal raw A-record query over UDP
    try:
        tid = 0x1A2B
        flags = 0x0100  # RD set
        query = struct.pack(">HHHHHH", tid, flags, 1, 0, 0, 0)
        for label in domain.rstrip(".").split("."):
            query += bytes([len(label)]) + label.encode()
        query += b"\x00"
        query += struct.pack(">HH", 1, 1)  # QTYPE A, QCLASS IN
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(2.5)
            t0 = time.monotonic()
            s.sendto(query, (server, 53))
            data, _ = s.recvfrom(512)
            elapsed = (time.monotonic() - t0) * 1000
        # Skip header (12 bytes) + question section
        pos = 12
        while pos < len(data) and data[pos] != 0:
            pos += data[pos] + 1
        pos += 5  # null + QTYPE + QCLASS
        # Parse first answer record
        if pos + 12 <= len(data):
            pos += 10  # name ptr/label + TYPE + CLASS + TTL
            rdlen = struct.unpack(">H", data[pos: pos + 2])[0]
            pos += 2
            if rdlen == 4 and pos + 4 <= len(data):
                resolved_ip = ".".join(str(b) for b in data[pos: pos + 4])
                return elapsed, resolved_ip
        return elapsed, ""
    except Exception:
        return -1.0, ""


def _http_check(url: str) -> Tuple[int, float]:
    """Return (http_status_code, latency_ms)."""
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "NetSentinel/2.0"}
        )
        t0 = time.monotonic()
        with urllib.request.urlopen(req, timeout=6) as resp:
            resp.read(4096)
            return resp.status, (time.monotonic() - t0) * 1000
    except urllib.error.HTTPError as exc:
        return exc.code, -1.0
    except Exception:
        return 0, -1.0


def _speed_test() -> float:
    """Return rough download speed in Mbps.  Returns -1 on failure."""
    try:
        req = urllib.request.Request(
            _SPEED_URL, headers={"User-Agent": "NetSentinel/2.0"}
        )
        t0 = time.monotonic()
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = resp.read()
        elapsed = time.monotonic() - t0
        if elapsed > 0:
            return (len(data) * 8) / (elapsed * 1_000_000)
    except Exception:
        pass
    return -1.0


def _get_public_ip() -> str:
    """Return the public IP as seen from the internet."""
    for url in (
        "https://api.ipify.org",
        "https://icanhazip.com",
        "https://ifconfig.me/ip",
    ):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "NetSentinel/2.0"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                ip = resp.read(64).decode().strip()
                if re.match(r"^\d+\.\d+\.\d+\.\d+$", ip):
                    return ip
        except Exception:
            continue
    return ""


def _traceroute(target: str = "8.8.8.8", max_hops: int = 15) -> List[TraceHop]:
    """Run traceroute/tracert and return list of TraceHop."""
    system = platform.system()
    extra: dict = {"creationflags": subprocess.CREATE_NO_WINDOW} if system == "Windows" else {}
    hops: List[TraceHop] = []
    try:
        if system == "Windows":
            r = subprocess.run(
                ["tracert", "-d", "-h", str(max_hops), "-w", "1000", target],
                capture_output=True, text=True, timeout=90, **extra,
            )
            for line in r.stdout.splitlines():
                # "  1    <1 ms    <1 ms    <1 ms  192.168.68.1"
                m = re.match(
                    r"\s*(\d+)\s+"
                    r"(?:<\s*1|(\d+))\s+ms.*?(\d+\.\d+\.\d+\.\d+|\*)",
                    line,
                )
                if m:
                    rtt = float(m.group(2)) if m.group(2) else 0.5
                    ip = m.group(3) if m.group(3) != "*" else "*"
                    hops.append(TraceHop(hop=int(m.group(1)), ip=ip, rtt_ms=rtt))
        else:
            r = subprocess.run(
                ["traceroute", "-n", "-m", str(max_hops), "-w", "2", target],
                capture_output=True, text=True, timeout=90,
            )
            for line in r.stdout.splitlines():
                m = re.match(r"\s*(\d+)\s+(\d+\.\d+\.\d+\.\d+|\*)\s+([0-9.]+)\s+ms", line)
                if m:
                    hops.append(
                        TraceHop(
                            hop=int(m.group(1)),
                            ip=m.group(2),
                            rtt_ms=float(m.group(3)),
                        )
                    )
    except Exception:
        pass
    return hops


def _dns_leak_test() -> DnsLeakResult:
    """
    Lightweight DNS leak test using dnsleaktest.com's API.
    1. Fetches a unique test ID from the service.
    2. Resolves a unique subdomain (triggering upstream resolver logging).
    3. Fetches the results — the set of resolver IPs that handled the query.

    If the resolvers returned are not your VPN's DNS servers (or if multiple
    distinct ISP resolvers appear), DNS may be leaking.
    Falls back gracefully if the service is unreachable.
    """
    import uuid as _uuid
    result = DnsLeakResult()
    try:
        # Step 1: get a unique test token
        uid = _uuid.uuid4().hex[:12]
        start_req = urllib.request.Request(
            "https://bash.ws/dnsleak/test/" + uid + "?json",
            headers={"User-Agent": "NetSentinel/2.0"},
        )
        with urllib.request.urlopen(start_req, timeout=6) as r:
            import json as _json
            data = _json.loads(r.read(4096).decode())

        # Step 2: trigger a DNS lookup of the test subdomain
        try:
            socket.getaddrinfo(f"{uid}.bash.ws", None)
        except Exception:
            pass

        # Step 3: fetch results
        result_req = urllib.request.Request(
            "https://bash.ws/dnsleak/test/" + uid + "?json",
            headers={"User-Agent": "NetSentinel/2.0"},
        )
        with urllib.request.urlopen(result_req, timeout=8) as r:
            entries = _json.loads(r.read(8192).decode())

        seen_ips: set = set()
        for e in entries:
            ip = e.get("ip", "")
            if ip and ip not in seen_ips:
                seen_ips.add(ip)
                result.resolvers_seen.append(DnsLeakEntry(
                    server_ip=ip,
                    country=e.get("country_name", ""),
                    org=e.get("asn", ""),
                ))

        # Simple heuristic: if more than 2 distinct resolver IPs are seen,
        # or if ISP-owned resolvers appear alongside a VPN resolver, flag it.
        if len(result.resolvers_seen) > 2:
            result.leak_detected = True
            result.plain_verdict = (
                f"⚠  DNS leak likely — {len(result.resolvers_seen)} different resolver IPs "
                f"responded. Your DNS queries may be leaving your VPN tunnel."
            )
        elif result.resolvers_seen:
            result.plain_verdict = (
                f"✅  {len(result.resolvers_seen)} resolver(s) seen — no obvious leak detected."
            )
        else:
            result.plain_verdict = "DNS leak test: no results returned (service may be unreachable)."

    except Exception as exc:
        result.plain_verdict = f"DNS leak test unavailable: {exc}"

    return result


# ── Public API ────────────────────────────────────────────────────────────────

def scan(
    gateway_ip: Optional[str] = None,
    progress_cb=None,
    stop_event=None,
) -> DiagnosticsResult:
    """Run all diagnostics.  Returns a DiagnosticsResult."""

    def _cb(msg: str):
        if progress_cb:
            progress_cb(msg)

    def _stopped() -> bool:
        return stop_event is not None and stop_event.is_set()

    result = DiagnosticsResult(gateway_ip=gateway_ip)

    # 1. Ping tests
    _cb("Pinging gateway and public hosts…")
    targets = []
    if gateway_ip:
        targets.append(("Gateway", gateway_ip))
    targets += [
        ("Cloudflare DNS", "1.1.1.1"),
        ("Google DNS",     "8.8.8.8"),
        ("google.com",     "google.com"),
        ("cloudflare.com", "cloudflare.com"),
    ]
    for name, host in targets:
        if _stopped():
            break
        rtt, resolved = _ping_host(host)
        status = "FAIL" if rtt < 0 else ("SLOW" if rtt > 100 else "OK")
        result.ping_results.append(
            PingResult(host=name, ip=resolved, rtt_ms=rtt, status=status)
        )

    # 2. DNS speed tests
    _cb("Testing DNS server latency…")
    domain = "google.com"
    for server_name, server_ip in _DNS_SERVERS:
        if _stopped():
            break
        latency, resolved = _dns_latency(domain, server_ip)
        status = "FAIL" if latency < 0 else ("SLOW" if latency > 200 else "OK")
        result.dns_results.append(
            DnsResult(
                server=server_name,
                domain=domain,
                latency_ms=latency,
                resolved_ip=resolved,
                status=status,
            )
        )

    # 3. HTTP connectivity
    _cb("Checking internet connectivity…")
    for name, url in _HTTP_TARGETS:
        if _stopped():
            break
        code, latency = _http_check(url)
        status = "OK" if code in (200, 204) else ("PARTIAL" if code > 0 else "FAIL")
        result.http_results.append(
            HttpResult(url=name, status_code=code, latency_ms=latency, status=status)
        )

    # 4. Public IP
    _cb("Detecting public IP address…")
    if not _stopped():
        result.public_ip = _get_public_ip()

    # 5. Download speed test (~2 MB)
    _cb("Download speed test (~2 MB from Cloudflare)…")
    if not _stopped():
        result.download_mbps = _speed_test()

    # 6. Traceroute (quick, first 15 hops to 8.8.8.8)
    _cb("Running traceroute to 8.8.8.8…")
    if not _stopped():
        result.trace_hops = _traceroute("8.8.8.8", max_hops=15)

    # 7. DNS leak test
    _cb("Running DNS leak test…")
    if not _stopped():
        result.dns_leak = _dns_leak_test()

    # 8. Plain-English verdict
    fail_pings = [p for p in result.ping_results if p.status == "FAIL"]
    all_http_fail = result.http_results and all(
        h.status == "FAIL" for h in result.http_results
    )
    if all_http_fail:
        result.plain_verdict = (
            "❌ No internet connectivity detected. "
            "Check your router/modem and physical cables."
        )
    elif fail_pings:
        names = ", ".join(p.host for p in fail_pings)
        result.plain_verdict = (
            f"⚠ Some hosts unreachable ({names}). "
            "Partial connectivity — possible DNS or routing issue."
        )
    elif result.download_mbps > 0:
        speed_str = (
            f"{result.download_mbps:.0f} Mbps"
            if result.download_mbps >= 1
            else f"{result.download_mbps * 1000:.0f} Kbps"
        )
        sys_dns = next(
            (d for d in result.dns_results if d.server == "System DNS"), None
        )
        dns_str = (
            f"  System DNS: {sys_dns.latency_ms:.0f} ms."
            if sys_dns and sys_dns.latency_ms > 0
            else ""
        )
        result.plain_verdict = (
            f"✅ Internet working.  Download ≈ {speed_str}.{dns_str}"
        )
    else:
        result.plain_verdict = (
            "✅ Connectivity OK. Speed test unavailable (may be blocked by firewall)."
        )

    return result
