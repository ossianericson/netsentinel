"""
Module 8 — Quick Port Scanner

TCP connect-scan of common ports on a single target host.
No root / admin / raw sockets required — uses standard TCP connect().

Common ports covered include all services typical on home devices:
routers, NAS boxes, cameras, printers, smart home hubs, and PCs.
"""

import socket
from dataclasses import dataclass, field
from typing import List, Optional

from modules.utils_net import parallel_map


# ── Port directory ─────────────────────────────────────────────────────────────

PORT_NAMES: dict = {
    21:    "FTP",
    22:    "SSH",
    23:    "Telnet  ⚠ insecure",
    25:    "SMTP",
    53:    "DNS",
    80:    "HTTP",
    110:   "POP3",
    123:   "NTP",
    143:   "IMAP",
    443:   "HTTPS",
    445:   "SMB / Windows File Share  ⚠",
    548:   "AFP  (Apple File Share)",
    554:   "RTSP  (IP Camera stream)",
    587:   "SMTP-TLS",
    631:   "IPP  (Print server)",
    993:   "IMAPS",
    995:   "POP3S",
    1883:  "MQTT  (IoT broker)  ⚠",
    3389:  "RDP  (Remote Desktop)  ⚠",
    5000:  "UPnP / Dev server",
    5900:  "VNC  (Remote Control)  ⚠",
    7547:  "CWMP / TR-069  (ISP remote mgmt)  ⚠",
    8080:  "HTTP Alternate",
    8443:  "HTTPS Alternate",
    8888:  "HTTP Dev / Jupyter",
    9100:  "Network Printer  (RAW)",
    49152: "UPnP SSDP",
}

COMMON_PORTS: List[int] = sorted(PORT_NAMES.keys())

# Risk annotation: ports that are dangerous to expose on LAN
HIGH_RISK_PORTS = {23, 445, 1883, 3389, 5900, 7547}


# ── Scan modes ───────────────────────────────────────────────────────────────

# Each mode is a tuple of (connect_timeout_s, max_workers, inter_probe_delay_s)
# fast   — maximum concurrency, short timeout; may be logged by IDS
# normal — balanced default
# stealth — low concurrency, longer timeout, small delay between probes
SCAN_MODES: dict = {
    "fast":    {"timeout": 0.35, "workers": 100, "delay": 0.0},
    "normal":  {"timeout": 0.60, "workers":  50, "delay": 0.0},
    "stealth": {"timeout": 1.20, "workers":   8, "delay": 0.05},
}

# ── Politeness levels ─────────────────────────────────────────────────────────
# Controls inter-probe timing and port-order randomisation.
#
# aggressive — no delay, sequential port order (fastest, most detectable)
# normal     — no delay, sequential order (balanced default, same as before)
# polite     — small random jitter (0–100 ms), sequential order
# sneaky     — larger random jitter (0.5–3 s), randomised port order
# paranoid   — very long random jitter (5–15 s), randomised order, tiny batches
#
# The politeness level is independent of SCAN_MODES — you can combine
# e.g. "stealth" mode with "sneaky" politeness for maximum evasion.

import random as _random
import time as _time

POLITENESS_LEVELS: dict = {
    "aggressive": {"min_delay": 0.0,  "max_delay": 0.0,   "randomise_order": False, "batch": 100},
    "normal":     {"min_delay": 0.0,  "max_delay": 0.0,   "randomise_order": False, "batch": 50},
    "polite":     {"min_delay": 0.0,  "max_delay": 0.1,   "randomise_order": False, "batch": 20},
    "sneaky":     {"min_delay": 0.5,  "max_delay": 3.0,   "randomise_order": True,  "batch": 10},
    "paranoid":   {"min_delay": 5.0,  "max_delay": 15.0,  "randomise_order": True,  "batch": 1},
}

DEFAULT_POLITENESS = "normal"


def apply_politeness(ports: list, level: str = DEFAULT_POLITENESS) -> list:
    """
    Apply politeness settings to a port list.
    Returns the port list (possibly shuffled).
    Call politeness_delay() between each probe.
    """
    cfg = POLITENESS_LEVELS.get(level, POLITENESS_LEVELS["normal"])
    if cfg["randomise_order"]:
        ports = list(ports)
        _random.shuffle(ports)
    return ports


def politeness_delay(level: str = DEFAULT_POLITENESS) -> None:
    """Sleep for a random duration according to the politeness level."""
    cfg = POLITENESS_LEVELS.get(level, POLITENESS_LEVELS["normal"])
    lo, hi = cfg["min_delay"], cfg["max_delay"]
    if hi > 0:
        _time.sleep(_random.uniform(lo, hi))


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class PortResult:
    port: int
    name: str
    open: bool
    banner: str = ""
    service_version: str = ""   # e.g. "Apache/2.4.54", "OpenSSH 8.9p1"
    risk: str = "LOW"   # LOW / HIGH


@dataclass
class PortScanResult:
    host: str
    ip: str = ""
    open_ports: List[PortResult] = field(default_factory=list)
    scanned: int = 0
    scan_mode: str = "normal"
    error: str = ""
    plain_verdict: str = ""


# ── Scan logic ────────────────────────────────────────────────────────────────

import re as _re
import ssl as _ssl


def probe_service(sock: "socket.socket", port: int, ip: str, timeout: float) -> tuple[str, str]:
    """
    Protocol-aware service probe.  Returns (banner, service_version).

    banner          — raw first-line greeting (≤120 chars)
    service_version — extracted version string, e.g. "OpenSSH 8.9p1",
                      "Apache/2.4.54", "Microsoft-IIS/10.0"
    """
    banner  = ""
    version = ""
    t       = min(timeout, 0.5)
    sock.settimeout(t)

    try:
        # ── Greeting-banner ports (server speaks first) ───────────────────
        if port in (21, 22, 25, 110, 143, 554, 587, 993, 995, 1883):
            raw    = sock.recv(512)
            banner = raw.decode("utf-8", errors="replace").strip().splitlines()[0][:120]

            # SSH:   "SSH-2.0-OpenSSH_8.9p1 Ubuntu-3ubuntu0.1"
            m = _re.search(r"SSH-\S+-(\S+)", banner)
            if m:
                version = "OpenSSH " + m.group(1).replace("OpenSSH_", "")

            # FTP:   "220 vsftpd 3.0.5"  /  "220 FileZilla Server 1.7.1"
            if not version:
                m = _re.search(r"220[- ](.+)", banner)
                if m:
                    version = m.group(1).strip()[:60]

            # SMTP:  "220 mail.host.com ESMTP Postfix (Ubuntu)"
            if not version:
                m = _re.search(r"ESMTP\s+(\S+)", banner)
                if m:
                    version = m.group(1)

        # ── HTTP — send a minimal HEAD request ────────────────────────────
        elif port in (80, 8080, 8888):
            sock.sendall(b"HEAD / HTTP/1.0\r\nHost: " + ip.encode() + b"\r\n\r\n")
            raw    = sock.recv(1024)
            text   = raw.decode("utf-8", errors="replace")
            banner = text.splitlines()[0][:120] if text else ""
            # Server: Apache/2.4.54 (Ubuntu)
            m = _re.search(r"^Server:\s*(.+)$", text, _re.MULTILINE | _re.IGNORECASE)
            if m:
                version = m.group(1).strip()[:80]
            # X-Powered-By: PHP/8.1.2
            if not version:
                m = _re.search(r"X-Powered-By:\s*(.+)$", text, _re.MULTILINE | _re.IGNORECASE)
                if m:
                    version = m.group(1).strip()[:60]

        # ── HTTPS — TLS handshake + HEAD ─────────────────────────────────
        elif port in (443, 8443):
            try:
                ctx = _ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode    = _ssl.CERT_NONE  # banner-grab only — cert not evaluated
                ctx.minimum_version = _ssl.TLSVersion.TLSv1_2
                tls = ctx.wrap_socket(sock, server_hostname=ip)
                tls.sendall(b"HEAD / HTTP/1.0\r\nHost: " + ip.encode() + b"\r\n\r\n")
                raw  = tls.recv(1024)
                text = raw.decode("utf-8", errors="replace")
                m    = _re.search(r"^Server:\s*(.+)$", text, _re.MULTILINE | _re.IGNORECASE)
                if m:
                    version = m.group(1).strip()[:80]
                banner = text.splitlines()[0][:120] if text else "TLS"
            except Exception:
                banner = "TLS (version probe failed)"

        # ── SMB — NetBIOS session request ─────────────────────────────────
        elif port == 445:
            # Send a NetBIOS Session Request; Windows responds with SMB negotiate
            sock.sendall(bytes([0x00, 0x00, 0x00, 0x2f]) +
                         b"\xff\x53\x4d\x42\x72\x00\x00\x00\x00\x18\x01\x20" +
                         b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00" +
                         b"\x00\x00\xff\xfe\x00\x00\x00\x00\x00\x00\x00\x00" +
                         b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00")
            raw = sock.recv(256)
            if raw and len(raw) > 4:
                banner = f"SMB ({len(raw)} bytes)"
                if b"Windows" in raw:
                    version = "Windows SMB"
                elif b"Samba" in raw:
                    version = "Samba"

        # ── RDP ───────────────────────────────────────────────────────────
        elif port == 3389:
            # TPKT + X.224 connection request
            sock.sendall(b"\x03\x00\x00\x13\x0e\xe0\x00\x00\x00\x00\x00"
                         b"\x01\x00\x08\x00\x03\x00\x00\x00")
            raw = sock.recv(64)
            if raw:
                banner = "RDP"
                version = "Windows RDP"

        # ── VNC ───────────────────────────────────────────────────────────
        elif port == 5900:
            raw    = sock.recv(64)
            banner = raw.decode("utf-8", errors="replace").strip()[:80]
            m = _re.search(r"RFB (\d+\.\d+)", banner)
            if m:
                version = f"VNC RFB {m.group(1)}"

        # ── Telnet ────────────────────────────────────────────────────────
        elif port == 23:
            raw    = sock.recv(256)
            banner = raw.decode("utf-8", errors="replace").strip()[:80]
            version = "Telnet"

    except Exception:
        pass  # non-fatal

    return banner, version


def scan(
    host: str,
    ports: Optional[List[int]] = None,
    timeout: float = 0.6,
    mode: str = "normal",
    politeness: str = DEFAULT_POLITENESS,
) -> PortScanResult:
    """
    TCP connect scan.  Returns a PortScanResult with only open ports listed.
    No elevated privileges required.

    mode: "fast" | "normal" | "stealth"
      fast    — 100 concurrent threads, 0.35 s timeout.  Quickest but detectable.
      normal  — 50 concurrent threads, 0.60 s timeout.  Balanced default.
      stealth — 8 concurrent threads, 1.20 s timeout, 50 ms inter-probe delay.

    politeness: "aggressive" | "normal" | "polite" | "sneaky" | "paranoid"
      Controls inter-probe random jitter and port-order randomisation.
    """
    cfg = SCAN_MODES.get(mode, SCAN_MODES["normal"])
    _timeout  = timeout if timeout != 0.6 else cfg["timeout"]
    _workers  = cfg["workers"]
    _delay    = cfg["delay"]

    if ports is None:
        ports = COMMON_PORTS

    # Apply politeness — may shuffle port order
    ports = apply_politeness(list(ports), politeness)

    result = PortScanResult(host=host, scanned=len(ports), scan_mode=mode)

    try:
        result.ip = socket.gethostbyname(host)
    except Exception as exc:
        result.error = f"Cannot resolve {host}: {exc}"
        return result

    def _check(port: int) -> PortResult:
        if _delay:
            import time
            time.sleep(_delay)
        politeness_delay(politeness)
        name = PORT_NAMES.get(port, f"port {port}")
        risk = "HIGH" if port in HIGH_RISK_PORTS else "LOW"
        try:
            with socket.create_connection((result.ip, port), timeout=_timeout) as s:
                banner, version = probe_service(s, port, result.ip, _timeout)
                return PortResult(port=port, name=name, open=True,
                                  banner=banner, service_version=version, risk=risk)
        except Exception:
            return PortResult(port=port, name=name, open=False, risk=risk)

    for pr in parallel_map(_check, ports, workers=_workers):
        if pr.open:
            result.open_ports.append(pr)

    result.open_ports.sort(key=lambda p: p.port)

    # Plain-English verdict
    high_risk = [p for p in result.open_ports if p.risk == "HIGH"]
    if not result.open_ports:
        result.plain_verdict = f"No open ports found on {host} ({result.ip})."
    elif high_risk:
        names = ", ".join(f"{p.port} ({p.name.split()[0]})" for p in high_risk)
        result.plain_verdict = (
            f"⚠  {len(result.open_ports)} open port(s) — HIGH RISK: {names}.  "
            "These services should not be exposed on a home network."
        )
    else:
        result.plain_verdict = (
            f"✅  {len(result.open_ports)} open port(s), none flagged as high risk."
        )

    return result
