"""
OS Fingerprinting — TTL + TCP window + TCP options stack heuristic.

Two-tier approach:
  Tier 1 (no admin): TTL from ping + HTTP/SSH banner grab.
  Tier 2 (admin, Scapy): Send a SYN probe, read back:
    - TCP initial window size
    - TCP options order (MSS, SACK, TS, WS, NOP)
    - DF (don't-fragment) bit
    - TTL from IP layer (more accurate than ping)
  Combine all signals for a High-confidence OS guess.

Window size fingerprints:
  65535  → Windows XP / Vista / 7 / network devices
  64240  → Windows 10/11 / Server 2016+
  65535  → macOS, BSD
   5840  → Linux 2.4 kernel
  29200  → Linux 3.x / 4.x
  65535  → FreeBSD / OpenBSD
  14600  → Linux (some distros)

TTL starting values (typical):
  255 → Cisco IOS / network device
  128 → Windows
   64 → Linux / macOS / Android / iOS
"""

import concurrent.futures
import platform
import socket
import subprocess
from dataclasses import dataclass
from typing import List, Optional


# ── OS guess table ────────────────────────────────────────────────────────────

def _ttl_to_os(ttl: int) -> str:
    """Map observed TTL to likely OS family (accounts for up to 30 hops)."""
    if ttl >= 240:
        return "Network Device (Cisco/Juniper)"
    if ttl >= 100:
        return "Windows"
    if ttl >= 50:
        return "Linux / macOS / Android"
    if ttl >= 40:
        return "macOS (older)"
    return "Unknown"


def _banner_to_os(banner: str) -> Optional[str]:
    """Guess OS from a service banner string."""
    b = banner.lower()
    if "windows" in b or "microsoft" in b or "iis" in b:
        return "Windows"
    if "ubuntu" in b or "debian" in b or "centos" in b or "fedora" in b:
        return "Linux"
    if "darwin" in b or "macos" in b or "apple" in b:
        return "macOS"
    if "android" in b:
        return "Android"
    if "openwrt" in b or "dd-wrt" in b or "tomato" in b:
        return "Linux (Router firmware)"
    if "cisco" in b or "junos" in b or "routeros" in b:
        return "Network Device"
    if "synology" in b or "qnap" in b or "freenas" in b or "truenas" in b:
        return "NAS"
    return None


# ── TCP stack fingerprint (Scapy / admin) ─────────────────────────────────────

_DEFAULT_PROBE_PORTS: tuple[int, ...] = (80, 443, 22, 8080)


def _merge_ports(known: Optional[List[int]]) -> List[int]:
    """Known-open ports (from a prior port scan) first, then the fixed fallback
    set, deduped — probing confirmed-open ports first finds a match faster and
    more accurately, while still falling back if nothing was scanned yet."""
    return list(dict.fromkeys(list(known or []) + list(_DEFAULT_PROBE_PORTS)))


def _tcp_stack_fingerprint(ip: str, ports: Optional[List[int]] = None) -> dict:
    """
    Send a SYN to each candidate port (known-open ports first, then the fixed
    80/443/22/8080 fallback) and read back TCP/IP fields.
    Returns dict with keys: window, options_order, df_bit, ttl_ip.
    Returns {} if Scapy is unavailable or insufficient privileges.
    """
    try:
        from scapy.all import IP, TCP, sr1, conf
        conf.verb = 0
    except ImportError:
        return {}

    for port in _merge_ports(ports):
        try:
            pkt = IP(dst=ip) / TCP(dport=port, flags="S",
                                    options=[("MSS", 1460), ("SAckOK", b""),
                                             ("Timestamp", (0, 0)), ("NOP", None),
                                             ("WScale", 8)])
            reply = sr1(pkt, timeout=1.5, verbose=False)
            if reply and reply.haslayer(TCP) and (reply[TCP].flags & 0x12):
                # SYN-ACK received
                opts = [opt[0] for opt in reply[TCP].options if isinstance(opt, tuple)]
                df = bool(reply[IP].flags & 0x02)
                return {
                    "window":        reply[TCP].window,
                    "options_order": opts,
                    "df_bit":        df,
                    "ttl_ip":        reply[IP].ttl,
                    "probe_port":    port,
                }
        except Exception:
            continue
    return {}


def _window_to_os(window: int, ttl: int, opts: list) -> tuple[str, str]:
    """
    Combine TCP window + TTL + option order into (os_family, confidence).
    Returns ("Unknown", "Low") if not enough signal.
    """
    # Windows fingerprints
    if window in (64240, 65535, 8192) and ttl >= 100:
        if window == 64240:
            return "Windows 10/11 or Server 2016+", "High"
        if window == 8192:
            return "Windows XP/Vista/7", "High"
        return "Windows", "High"
    # Linux fingerprints
    if ttl < 70:
        if window in (29200, 5840, 14600, 43440, 65535):
            # Also check options order: Linux typically MSS,SACK,TS,NOP,WS
            if "Timestamp" in opts:
                return "Linux", "High"
            return "Linux / macOS", "Medium"
        if window == 65535 and "Timestamp" in opts:
            return "macOS / BSD", "High"
        if window == 65535:
            return "Linux / macOS / BSD", "Medium"
    # Network device
    if ttl >= 240:
        return "Network Device (Cisco/Juniper)", "High"
    # Fallback to TTL only
    return _ttl_to_os(ttl), "Medium"


# ── Per-host fingerprint ──────────────────────────────────────────────────────

@dataclass
class OSGuess:
    ip: str
    ttl: int = 0
    os_family: str = "Unknown"
    confidence: str = "Low"   # Low / Medium / High
    banner_hint: str = ""
    tcp_window: str = ""       # NEW — shown in Recon OS tab
    not_testable: bool = False
    not_testable_reason: str = ""


def _ping_ttl(ip: str) -> int:
    """Return the TTL from a ping reply, or 0 on failure."""
    system = platform.system()
    extra: dict = {"creationflags": subprocess.CREATE_NO_WINDOW} if system == "Windows" else {}
    try:
        if system == "Windows":
            out = subprocess.check_output(
                ["ping", "-n", "1", "-w", "500", ip],
                text=True, timeout=3, **extra
            )
            import re
            m = re.search(r"TTL[=\s]+(\d+)", out, re.IGNORECASE)
            return int(m.group(1)) if m else 0
        else:
            out = subprocess.check_output(
                ["ping", "-c", "1", "-W", "1", ip],
                text=True, timeout=3
            )
            import re
            m = re.search(r"ttl[=\s]*(\d+)", out, re.IGNORECASE)
            return int(m.group(1)) if m else 0
    except Exception:
        return 0


def _grab_banner(ip: str) -> str:
    """Try to grab a one-line banner from common ports."""
    for port in (22, 80, 443, 8080):
        try:
            with socket.create_connection((ip, port), timeout=1.5) as s:
                if port in (80, 8080):
                    s.sendall(b"HEAD / HTTP/1.0\r\nHost: " + ip.encode() + b"\r\n\r\n")
                data = s.recv(256)
                banner = data.decode("utf-8", errors="replace").strip()
                if banner:
                    return banner[:200]
        except Exception:
            continue
    return ""


def fingerprint_host(ip: str, ports: Optional[List[int]] = None) -> OSGuess:
    """Fingerprint a single host — combines TTL, banner, and TCP stack analysis.

    `ports`, when given (e.g. from a prior port scan), are probed before the
    fixed 80/443/22/8080 fallback set (see `_merge_ports`).
    """
    guess = OSGuess(ip=ip)

    # Tier 1: TTL via ping (no admin required)
    ttl = _ping_ttl(ip)
    guess.ttl = ttl
    if ttl > 0:
        guess.os_family  = _ttl_to_os(ttl)
        guess.confidence = "Medium"

    # Tier 1: banner grab
    banner = _grab_banner(ip)
    guess.banner_hint = banner[:120] if banner else ""
    if banner:
        os_from_banner = _banner_to_os(banner)
        if os_from_banner:
            guess.os_family  = os_from_banner
            guess.confidence = "High"

    # Tier 2: TCP stack fingerprint (requires admin + Scapy)
    stack = _tcp_stack_fingerprint(ip, ports=ports)
    if stack:
        window  = stack.get("window", 0)
        opts    = stack.get("options_order", [])
        ttl_ip  = stack.get("ttl_ip", ttl) or ttl
        if ttl_ip:
            guess.ttl = ttl_ip
        if window:
            guess.tcp_window = str(window)
            # Only upgrade confidence if banner didn't already give High
            if guess.confidence != "High":
                os_family, confidence = _window_to_os(window, ttl_ip, opts)
                guess.os_family  = os_family
                guess.confidence = confidence
            else:
                # Cross-check: if banner OS and TCP stack OS agree → confirm
                stack_os, _ = _window_to_os(window, ttl_ip, opts)
                if any(part in stack_os for part in ("Windows", "Linux", "macOS")):
                    if any(part in guess.os_family for part in ("Windows", "Linux", "macOS")):
                        guess.confidence = "High"

    if guess.ttl <= 0 and not banner and not stack:
        guess.not_testable = True
        guess.not_testable_reason = (
            "Ping, banner grab, and TCP-stack fingerprinting all received no response — "
            "OS could not be determined. This is not a confirmed unusual/unknown OS."
        )

    return guess


def fingerprint_hosts(
    ips: List[str],
    progress_cb=None,
    max_workers: int = 30,
    port_map: Optional[dict] = None,
) -> dict:
    """
    Fingerprint a list of hosts concurrently.
    `port_map`, when given, is {ip: [known-open ports]} from a prior port
    scan — those ports are probed before the fixed fallback set per host.
    Returns {ip: OSGuess}.
    """
    results: dict = {}
    _cb = progress_cb or (lambda m: None)
    _cb(f"OS fingerprinting {len(ips)} host(s)…")
    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(fingerprint_host, ip, (port_map or {}).get(ip)): ip
            for ip in ips
        }
        for fut in concurrent.futures.as_completed(futures):
            ip = futures[fut]
            try:
                results[ip] = fut.result()
            except Exception:
                results[ip] = OSGuess(ip=ip)
            done += 1
            if done % 10 == 0:
                _cb(f"OS fingerprinting: {done}/{len(ips)} done…")
    _cb(f"OS fingerprinting complete — {len(results)} host(s).")
    return results

