"""
SYN Stealth Scanner — Scapy-based raw-socket port scanner.

Unlike a TCP connect scan, SYN scan never completes the three-way handshake:
  1. Send SYN
  2. If SYN-ACK received  → port OPEN  (immediately send RST to clean up)
  3. If RST received      → port CLOSED
  4. No response (timeout)→ port FILTERED

Advantages over TCP connect:
  - Not logged by most application-level logging (connection never established)
  - Significantly faster — no OS TCP stack overhead, no TIME_WAIT state
  - Controllable send rate via packets-per-second throttle
  - Full port range possible (1–65535)

Requirements:
  - Scapy
  - Administrator / root privileges
  - Windows: Npcap installed

UDP scan is also provided here.  UDP is harder — no response can mean open OR
filtered, so we mark those ports as "open|filtered" (matching Nmap convention).
"""

from __future__ import annotations

import concurrent.futures
import random
import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from modules.port_scanner import probe_service

# Top-1000 most common ports (subset shown; full list loaded from data below)
# Source: derived from nmap-services frequency ordering
_TOP_1000 = [
    # Top 100 most common
    80, 23, 443, 21, 22, 25, 3389, 110, 445, 139,
    143, 53, 135, 3306, 8080, 1723, 111, 995, 993, 5900,
    1025, 587, 8888, 199, 1720, 465, 548, 113, 81, 6001,
    10000, 514, 5060, 179, 1026, 2000, 8443, 8000, 32768, 49152,
    2001, 515, 8008, 49154, 1027, 5666, 646, 5000, 631, 49153,
    8081, 2049, 88, 79, 5632, 25565, 1028, 389, 873, 1755,
    2717, 4899, 9100, 119, 37, 1029, 3128, 563, 901, 49155,
    6667, 3986, 1110, 9000, 30, 8090, 777, 616, 3000, 8181,
    8282, 1433, 7070, 512, 513, 2121, 8192, 9999, 7000, 5009,
    23052, 3031, 8001, 10010, 2869, 3052, 1234, 5901, 1270, 36,
    # 101-200
    49156, 1080, 5100, 7680, 7777, 2500, 1900, 9001, 3737, 8200,
    2323, 3784, 3801, 9090, 4848, 8019, 4040, 4158, 8088, 2222,
    2602, 1944, 2998, 4279, 2030, 5999, 2111, 8009, 3306, 6646,
    2126, 6543, 4000, 3916, 10001, 3995, 2376, 5985, 5986, 623,
    5985, 49157, 49158, 8787, 8888, 7001, 7002, 8400, 8402, 9898,
    # 201-300
    1099, 1098, 3009, 4001, 5001, 6001, 7001, 8001, 9001, 10001,
    1111, 2222, 3333, 4444, 5555, 6666, 7777, 8888, 9999, 11211,
    27017, 27018, 27019, 28017, 6379, 5432, 1521, 1433, 3306, 5984,
    9200, 9300, 5601, 8983, 2181, 8888, 3000, 4200, 4848, 8080,
    8443, 9090, 9091, 9092, 9093, 9094, 9095, 9096, 9097, 9098,
    # More common service ports
    17, 19, 20, 21, 22, 23, 25, 37, 43, 49,
    53, 69, 70, 79, 80, 88, 102, 110, 111, 113,
    119, 123, 135, 137, 138, 139, 143, 161, 162, 179,
    194, 199, 389, 443, 445, 464, 465, 500, 502, 512,
    513, 514, 515, 520, 548, 554, 563, 587, 593, 631,
    636, 646, 873, 902, 989, 990, 993, 995, 1080, 1099,
    1194, 1433, 1434, 1521, 1723, 1812, 1813, 1883, 1900, 2049,
    2082, 2083, 2095, 2096, 2181, 2375, 2376, 3000, 3128, 3268,
    3269, 3306, 3389, 3690, 4444, 4848, 5000, 5004, 5005, 5060,
    5061, 5432, 5631, 5666, 5800, 5900, 5901, 5938, 5984, 5985,
    5986, 6000, 6379, 6443, 6660, 6667, 7001, 7443, 7474, 8000,
    8008, 8009, 8080, 8081, 8088, 8443, 8888, 9000, 9090, 9100,
    9200, 9418, 10000, 11211, 27017, 49152, 49153, 49154, 49155,
]

# Deduplicate and sort
TOP_1000_PORTS: List[int] = sorted(set(_TOP_1000))


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class SYNPortResult:
    port:            int
    state:           str   # "open" | "closed" | "filtered" | "open|filtered"
    proto:           str   # "tcp" | "udp"
    service:         str = ""
    banner:          str = ""   # e.g. "SSH-2.0-OpenSSH_8.9p1"
    service_version: str = ""   # e.g. "OpenSSH 8.9p1", "Apache/2.4.54"


@dataclass
class SYNScanResult:
    host:         str
    ip:           str = ""
    open_ports:   List[SYNPortResult] = field(default_factory=list)
    filtered:     int = 0
    closed:       int = 0
    total_probed: int = 0
    scan_type:    str = "syn"   # "syn" | "udp"
    duration_s:   float = 0.0
    error:        str = ""
    plain_verdict: str = ""
    requires_admin: bool = True
    not_testable: bool = False
    not_testable_reason: str = ""


# ── Service name lookup (common ports) ───────────────────────────────────────

_SERVICE_NAMES: dict[int, str] = {
    21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP", 53: "DNS",
    69: "TFTP", 80: "HTTP", 88: "Kerberos", 110: "POP3", 111: "RPC",
    123: "NTP", 135: "MSRPC", 137: "NetBIOS-NS", 139: "NetBIOS",
    143: "IMAP", 161: "SNMP", 162: "SNMP-Trap", 179: "BGP",
    389: "LDAP", 443: "HTTPS", 445: "SMB", 465: "SMTPS",
    500: "IKE/VPN", 502: "Modbus", 514: "Syslog", 515: "LPD",
    548: "AFP", 554: "RTSP", 587: "SMTP-TLS", 631: "IPP",
    636: "LDAPS", 873: "rsync", 993: "IMAPS", 995: "POP3S",
    1080: "SOCKS", 1194: "OpenVPN", 1433: "MSSQL", 1434: "MSSQL-UDP",
    1521: "Oracle", 1723: "PPTP", 1883: "MQTT", 1900: "UPnP/SSDP",
    2049: "NFS", 2375: "Docker", 2376: "Docker-TLS", 3000: "Dev/Grafana",
    3306: "MySQL", 3389: "RDP", 3690: "SVN", 4444: "Metasploit/Shell",
    4848: "GlassFish", 5432: "PostgreSQL", 5900: "VNC", 5985: "WinRM",
    5986: "WinRM-HTTPS", 6379: "Redis", 6443: "Kubernetes API",
    7001: "WebLogic", 7474: "Neo4j", 8080: "HTTP-Alt", 8443: "HTTPS-Alt",
    8888: "Jupyter/Dev", 9000: "SonarQube/PHP-FPM", 9090: "Prometheus",
    9200: "Elasticsearch", 9418: "Git", 10000: "Webmin",
    11211: "Memcached", 27017: "MongoDB", 49152: "UPnP",
    7547: "TR-069/CWMP", 5060: "SIP", 5061: "SIP-TLS",
}

# High-risk ports for SYN scan
_HIGH_RISK = {
    23, 445, 1883, 3389, 5900, 7547, 4444, 6379, 11211,
    27017, 5432, 3306, 1521, 2375, 5985, 5986, 7001,
}


def _grab_banners(open_ports: List["SYNPortResult"], ip: str, timeout: float) -> None:
    """
    Secondary pass: for each SYN-confirmed open port, complete a short-lived
    TCP connect and reuse modules/port_scanner.py's protocol-aware
    probe_service() to fill in banner/service_version.

    A SYN scan alone cannot banner-grab (it never completes the handshake),
    so this brief connect-and-probe step is what makes "Port Scan (TCP)"
    competitive with the no-admin TCP-connect scanner's banner output.
    Any per-port failure is swallowed — the port is already confirmed open
    from the SYN response, so a failed probe must not affect scan results.
    """
    _t = min(timeout, 1.0)

    def _probe(p: "SYNPortResult") -> None:
        try:
            with socket.create_connection((ip, p.port), timeout=_t) as sock:
                banner, version = probe_service(sock, p.port, ip, _t)
                p.banner = banner
                p.service_version = version
        except Exception:
            pass  # port confirmed open via SYN-ACK; a failed banner probe is non-fatal

    if not open_ports:
        return
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(20, len(open_ports))) as ex:
        list(ex.map(_probe, open_ports))


# ── SYN scan ─────────────────────────────────────────────────────────────────

def syn_scan(
    host: str,
    ports: Optional[List[int]] = None,
    rate_pps: int = 500,
    timeout: float = 1.0,
    politeness: str = "normal",
    progress_cb: Optional[Callable[[str], None]] = None,
    stop_event: Optional[threading.Event] = None,
) -> SYNScanResult:
    """
    SYN stealth scan using Scapy.

    Parameters
    ----------
    host        Target IP or hostname.
    ports       List of ports to scan. Defaults to TOP_1000_PORTS.
    rate_pps    Maximum packets per second to send (default 500).
    timeout     Seconds to wait for responses after last probe sent.
    politeness  "aggressive" | "normal" | "polite" | "sneaky" | "paranoid"
                Controls inter-probe random jitter and port-order randomisation.
    progress_cb Optional callback for status messages.
    stop_event  Optional threading.Event to cancel the scan.
    """
    import socket as _socket

    result = SYNScanResult(host=host, scan_type="syn", requires_admin=True)
    t_start = time.monotonic()

    try:
        result.ip = _socket.gethostbyname(host)
    except Exception as exc:
        result.error = f"Cannot resolve {host}: {exc}"
        return result

    if ports is None:
        ports = TOP_1000_PORTS

    result.total_probed = len(ports)

    try:
        from scapy.all import IP, TCP, sr, conf, RandShort
        conf.verb = 0   # suppress Scapy output
    except ImportError:
        result.error = "Scapy not available. Install scapy to use SYN scan."
        return result

    if progress_cb:
        progress_cb(f"SYN scanning {result.ip} — {len(ports)} ports at {rate_pps} pps…")

    # Apply politeness — may shuffle port order
    _politeness_cfg = {
        "aggressive": (0.0, 0.0,  False),
        "normal":     (0.0, 0.0,  False),
        "polite":     (0.0, 0.1,  False),
        "sneaky":     (0.5, 3.0,  True),
        "paranoid":   (5.0, 15.0, True),
    }
    _plo, _phi, _shuffle = _politeness_cfg.get(politeness, (0.0, 0.0, False))
    if _shuffle:
        ports = list(ports)
        random.shuffle(ports)

    # Build packet list
    src_port = int(RandShort())
    packets = [
        IP(dst=result.ip) / TCP(sport=src_port, dport=port, flags="S")
        for port in ports
    ]

    # Rate-limited send — split into chunks
    delay_per_pkt = 1.0 / rate_pps if rate_pps > 0 else 0
    # Add politeness jitter on top of rate-limit delay
    if _phi > 0:
        delay_per_pkt = max(delay_per_pkt, random.uniform(_plo, _phi))

    answered, _ = [], []

    try:
        # Use Scapy's sr() with a modest timeout per batch
        answered, unanswered = sr(
            packets,
            timeout=timeout,
            retry=0,
            verbose=False,
            inter=delay_per_pkt,
        )
    except Exception as exc:
        result.error = f"SYN scan failed (admin required on Windows): {exc}"
        result.duration_s = time.monotonic() - t_start
        return result

    # Process responses
    open_ports = []
    filtered_count = 0
    closed_count = 0

    # Map port → response
    port_states: dict[int, str] = {}
    for sent, recv in answered:
        dport = sent[TCP].dport
        if recv.haslayer(TCP):
            tcp_flags = recv[TCP].flags
            if tcp_flags & 0x12:  # SYN-ACK → open
                port_states[dport] = "open"
            elif tcp_flags & 0x14:  # RST-ACK or RST → closed
                port_states[dport] = "closed"

    # Unanswered → filtered
    for sent in unanswered:
        dport = sent[TCP].dport
        if dport not in port_states:
            port_states[dport] = "filtered"

    for port, state in port_states.items():
        if state == "open":
            service = _SERVICE_NAMES.get(port, f"port {port}")
            open_ports.append(SYNPortResult(
                port=port, state="open", proto="tcp", service=service
            ))
        elif state == "filtered":
            filtered_count += 1
        else:
            closed_count += 1

    open_ports.sort(key=lambda p: p.port)
    if progress_cb and open_ports:
        progress_cb(f"Grabbing banners on {len(open_ports)} open port(s)…")
    _grab_banners(open_ports, ip=result.ip, timeout=timeout)
    result.open_ports   = open_ports
    result.filtered     = filtered_count
    result.closed       = closed_count
    result.duration_s   = time.monotonic() - t_start

    if result.total_probed > 0 and not open_ports and closed_count == 0 and filtered_count == result.total_probed:
        result.not_testable = True
        result.not_testable_reason = (
            f"All {result.total_probed} probed port(s) were filtered — no response of any kind "
            f"came back from {host}. A firewall between NetSentinel and this host may be silently "
            "dropping every probe, so this scan cannot confirm the host has no open ports."
        )

    # Plain-English verdict
    high_risk_open = [p for p in open_ports if p.port in _HIGH_RISK]
    if result.not_testable:
        result.plain_verdict = (
            f"⚠ Could not test {host} — {result.not_testable_reason}"
        )
    elif not open_ports:
        result.plain_verdict = (
            f"SYN scan complete — no open ports found on {host} "
            f"({filtered_count} filtered, {result.duration_s:.1f}s)"
        )
    elif high_risk_open:
        names = ", ".join(f"{p.port} ({p.service})" for p in high_risk_open)
        result.plain_verdict = (
            f"⚠  {len(open_ports)} open TCP port(s) — HIGH RISK: {names}. "
            f"{filtered_count} filtered. ({result.duration_s:.1f}s)"
        )
    else:
        result.plain_verdict = (
            f"✅  {len(open_ports)} open TCP port(s), none high-risk. "
            f"{filtered_count} filtered. ({result.duration_s:.1f}s)"
        )

    if progress_cb:
        progress_cb(result.plain_verdict)

    return result


# ── UDP scan ─────────────────────────────────────────────────────────────────

# Key UDP ports worth checking
UDP_PORTS: List[int] = [
    53,   # DNS
    67,   # DHCP server
    68,   # DHCP client
    69,   # TFTP
    123,  # NTP
    137,  # NetBIOS Name Service
    138,  # NetBIOS Datagram
    161,  # SNMP
    162,  # SNMP Trap
    500,  # IKE/VPN
    514,  # Syslog
    520,  # RIP
    1194, # OpenVPN
    1434, # MSSQL Browser
    1900, # UPnP/SSDP
    4500, # NAT-T IKE
    5060, # SIP
    5353, # mDNS
    5683, # CoAP (IoT)
]


def udp_scan(
    host: str,
    ports: Optional[List[int]] = None,
    timeout: float = 2.0,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> SYNScanResult:
    """
    UDP scan using Scapy.

    Open|filtered: no response (common for UDP — firewall or open service)
    Closed:        ICMP port-unreachable received
    """
    import socket as _socket

    result = SYNScanResult(host=host, scan_type="udp", requires_admin=True)
    t_start = time.monotonic()

    try:
        result.ip = _socket.gethostbyname(host)
    except Exception as exc:
        result.error = f"Cannot resolve {host}: {exc}"
        return result

    if ports is None:
        ports = UDP_PORTS

    result.total_probed = len(ports)

    try:
        from scapy.all import IP, UDP, ICMP, sr, conf
        conf.verb = 0
    except ImportError:
        result.error = "Scapy not available."
        return result

    if progress_cb:
        progress_cb(f"UDP scanning {result.ip} — {len(ports)} ports…")

    packets = [IP(dst=result.ip) / UDP(dport=port) for port in ports]

    try:
        answered, unanswered = sr(packets, timeout=timeout, retry=1, verbose=False)
    except Exception as exc:
        result.error = f"UDP scan failed: {exc}"
        result.duration_s = time.monotonic() - t_start
        return result

    open_ports = []
    closed_count = 0

    for sent, recv in answered:
        dport = sent[UDP].dport
        if recv.haslayer(ICMP) and recv[ICMP].type == 3:
            # ICMP port unreachable → closed
            closed_count += 1
        else:
            # Any other response → open
            service = _SERVICE_NAMES.get(dport, f"udp/{dport}")
            open_ports.append(SYNPortResult(
                port=dport, state="open", proto="udp", service=service
            ))

    # No response → open|filtered
    for sent in unanswered:
        dport = sent[UDP].dport
        service = _SERVICE_NAMES.get(dport, f"udp/{dport}")
        open_ports.append(SYNPortResult(
            port=dport, state="open|filtered", proto="udp", service=service
        ))

    open_ports.sort(key=lambda p: p.port)
    result.open_ports = open_ports
    result.closed     = closed_count
    result.duration_s = time.monotonic() - t_start

    definite_open = [p for p in open_ports if p.state == "open"]

    # Ordinary UDP open|filtered ambiguity (no response) is expected and NOT
    # itself a not_testable signal. But zero ICMP-closed AND zero explicit-open
    # across the ENTIRE scan means no packet got a response in either
    # direction — the UDP equivalent of syn_scan()'s "100% filtered" check —
    # which suggests a firewall dropping everything rather than a confirmed
    # picture of this host's UDP ports.
    if result.total_probed > 0 and closed_count == 0 and not definite_open:
        result.not_testable = True
        result.not_testable_reason = (
            f"None of the {result.total_probed} probed UDP port(s) produced any response "
            f"— no ICMP port-unreachable and no data back — from {host}. A firewall between "
            "NetSentinel and this host may be silently dropping every probe in both "
            "directions, so this scan cannot confirm anything about this host's UDP ports."
        )

    if result.not_testable:
        result.plain_verdict = f"⚠ Could not test {host} — {result.not_testable_reason}"
    else:
        result.plain_verdict = (
            f"UDP scan: {len(definite_open)} open, "
            f"{len(open_ports) - len(definite_open)} open|filtered, "
            f"{closed_count} closed. ({result.duration_s:.1f}s)"
        )

    if progress_cb:
        progress_cb(result.plain_verdict)

    return result
