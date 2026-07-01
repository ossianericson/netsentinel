"""
Ultra-fast Combined Device Discovery

Runs passive and active discovery methods in parallel and merges the results
into a single deduplicated device list, much faster than any single method:

  Passive (no packets sent):
    - ARP cache read (instant)
    - mDNS/DNS-SD cache read via socket (zero-RTT if already populated)

  Active (probes sent):
    - ARP broadcast sweep (fastest — Layer 2, sub-second for /24)
    - ICMP ping sweep (works through NAT, reveals devices that ignore ARP)
    - TCP SYN probe to port 80/443 (finds devices that block ICMP)
    - mDNS query broadcast (discovers zero-conf devices: printers, Chromecast, etc.)

All four active methods run simultaneously in a thread pool.
Devices discovered by ANY method are included; duplicate IPs are merged
(later methods can add hostname / additional detail to entries first found
by ARP).

Requires: Scapy for ARP sweep + SYN probe (admin/root + Npcap on Windows).
Graceful fallback: if Scapy is unavailable, only ARP cache + ICMP ping are used.
"""

from __future__ import annotations

import concurrent.futures
import ipaddress
import platform
import re
import socket
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

SCAPY_AVAILABLE = False
try:
    from scapy.all import ARP, Ether, IP, TCP, srp, sr  # type: ignore
    SCAPY_AVAILABLE = True
except ImportError:
    pass  # non-fatal

ProgressCB = Optional[Callable[[str], None]]


# ── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class DiscoveredDevice:
    ip: str
    mac: str = ""
    hostname: str = ""
    discovery_methods: List[str] = field(default_factory=list)  # how it was found
    response_ms: float = 0.0     # latency to first response
    mdns_services: List[str] = field(default_factory=list)


@dataclass
class DiscoveryResult:
    devices: List[DiscoveredDevice] = field(default_factory=list)
    cidr: str = ""
    duration_s: float = 0.0
    methods_used: List[str] = field(default_factory=list)
    error: str = ""

    @property
    def count(self) -> int:
        return len(self.devices)

    @property
    def plain_verdict(self) -> str:
        if self.error:
            return f"⚠ Discovery failed: {self.error}"
        return (
            f"Found {self.count} device(s) on {self.cidr or 'network'} "
            f"in {self.duration_s:.1f} s "
            f"using: {', '.join(self.methods_used) or 'ARP cache only'}"
        )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_local_cidr() -> str:
    """Best-effort local /24 CIDR from the default route."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        # Assume /24 for discovery
        parts = ip.split(".")
        return f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"
    except Exception:
        return "192.168.1.0/24"


def _resolve_hostname(ip: str, timeout: float = 0.5) -> str:
    from modules.name_resolver import rdns
    return rdns(ip, timeout)


# ── Method 1: ARP cache (passive, instant) ────────────────────────────────────

def _arp_cache_scan() -> Dict[str, DiscoveredDevice]:
    devices: Dict[str, DiscoveredDevice] = {}
    system = platform.system()
    extra: dict = {"creationflags": subprocess.CREATE_NO_WINDOW} if system == "Windows" else {}
    try:
        raw = subprocess.check_output(["arp", "-a"], text=True, timeout=10, **extra)
        for line in raw.splitlines():
            m = re.search(r"(\d+\.\d+\.\d+\.\d+)\s+([\da-fA-F:–-]{17})", line)
            if m:
                ip  = m.group(1)
                mac = m.group(2).replace("-", ":").lower()
                if mac != "ff:ff:ff:ff:ff:ff" and not ip.startswith("224.") and not ip.endswith(".255"):
                    devices[ip] = DiscoveredDevice(ip=ip, mac=mac, discovery_methods=["arp-cache"])
    except Exception:
        pass  # non-fatal
    return devices


# ── Method 2: ARP broadcast sweep (active, requires Scapy + admin) ────────────

def _arp_sweep(cidr: str, timeout: float = 2.0) -> Dict[str, DiscoveredDevice]:
    if not SCAPY_AVAILABLE:
        return {}
    devices: Dict[str, DiscoveredDevice] = {}
    try:
        ans, _ = srp(
            Ether(dst="ff:ff:ff:ff:ff:ff") / ARP(pdst=cidr),
            timeout=timeout, verbose=False,
        )
        for sent, rcv in ans:
            ip  = rcv[ARP].psrc
            mac = rcv[ARP].hwsrc.lower()
            if ip not in devices:
                devices[ip] = DiscoveredDevice(ip=ip, mac=mac, discovery_methods=["arp-sweep"])
            else:
                devices[ip].mac = devices[ip].mac or mac
                if "arp-sweep" not in devices[ip].discovery_methods:
                    devices[ip].discovery_methods.append("arp-sweep")
    except Exception:
        pass  # non-fatal
    return devices


# ── Method 3: ICMP ping sweep (active, no admin on most systems) ─────────────

def _ping_single(ip: str, timeout: float) -> Optional[DiscoveredDevice]:
    from modules.utils_net import icmp_ping
    ms = icmp_ping(ip, timeout=timeout)
    if ms >= 0:
        return DiscoveredDevice(ip=ip, response_ms=ms, discovery_methods=["icmp-ping"])
    return None


def _icmp_sweep(hosts: List[str], timeout: float = 1.0, max_workers: int = 64) -> Dict[str, DiscoveredDevice]:
    devices: Dict[str, DiscoveredDevice] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_ping_single, ip, timeout): ip for ip in hosts}
        for fut in concurrent.futures.as_completed(futures):
            dev = fut.result()
            if dev:
                devices[dev.ip] = dev
    return devices


# ── Method 4: TCP SYN probe (active, requires Scapy + admin) ─────────────────

def _tcp_probe_host(ip: str, ports: List[int], timeout: float) -> Optional[DiscoveredDevice]:
    if not SCAPY_AVAILABLE:
        return None
    try:
        pkt = IP(dst=ip) / TCP(dport=ports, flags="S")
        ans, _ = sr(pkt, timeout=timeout, verbose=False)
        for sent, rcv in ans:
            if rcv.haslayer(TCP) and rcv[TCP].flags in (0x12, 0x14):  # SYN-ACK or RST
                return DiscoveredDevice(ip=ip, discovery_methods=["tcp-syn"])
    except Exception:
        pass  # non-fatal
    return None


def _tcp_sweep(hosts: List[str], ports: List[int] = None, timeout: float = 1.0, max_workers: int = 32) -> Dict[str, DiscoveredDevice]:
    if not SCAPY_AVAILABLE:
        return {}
    if ports is None:
        ports = [80, 443, 22, 8080]
    devices: Dict[str, DiscoveredDevice] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_tcp_probe_host, ip, ports, timeout): ip for ip in hosts}
        for fut in concurrent.futures.as_completed(futures):
            dev = fut.result()
            if dev:
                devices[dev.ip] = dev
    return devices


# ── Method 5: mDNS query (active, no admin) ───────────────────────────────────

_MDNS_ADDR = "224.0.0.251"
_MDNS_PORT = 5353

def _mdns_query(timeout: float = 2.0) -> Dict[str, DiscoveredDevice]:
    """Send mDNS PTR query for _services._dns-sd._udp.local and collect replies."""
    devices: Dict[str, DiscoveredDevice] = {}
    try:
        # Build a minimal mDNS query packet for PTR record
        # Transaction ID: 0, Flags: 0 (standard query), Questions: 1
        qname = b"\x09_services\x07_dns-sd\x04_udp\x05local\x00"
        query = (
            b"\x00\x00"  # Transaction ID
            b"\x00\x00"  # Flags: standard query
            b"\x00\x01"  # Questions: 1
            b"\x00\x00"  # Answer RRs: 0
            b"\x00\x00"  # Authority RRs: 0
            b"\x00\x00"  # Additional RRs: 0
            + qname
            + b"\x00\x0c"  # QTYPE: PTR (12)
            + b"\x80\x01"  # QCLASS: IN (unicast)
        )
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(timeout)
        sock.sendto(query, (_MDNS_ADDR, _MDNS_PORT))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                data, addr = sock.recvfrom(4096)
                ip = addr[0]
                if ip not in devices:
                    devices[ip] = DiscoveredDevice(ip=ip, discovery_methods=["mdns"])
                else:
                    if "mdns" not in devices[ip].discovery_methods:
                        devices[ip].discovery_methods.append("mdns")
            except socket.timeout:
                break
            except Exception:
                break
        sock.close()
    except Exception:
        pass  # non-fatal
    return devices


# ── Merge helper ──────────────────────────────────────────────────────────────

def _merge(base: Dict[str, DiscoveredDevice], additions: Dict[str, DiscoveredDevice]) -> None:
    for ip, dev in additions.items():
        if ip not in base:
            base[ip] = dev
        else:
            # Enrich existing entry with new data
            if not base[ip].mac and dev.mac:
                base[ip].mac = dev.mac
            if not base[ip].hostname and dev.hostname:
                base[ip].hostname = dev.hostname
            for method in dev.discovery_methods:
                if method not in base[ip].discovery_methods:
                    base[ip].discovery_methods.append(method)
            if dev.response_ms and not base[ip].response_ms:
                base[ip].response_ms = dev.response_ms


# ── Public API ────────────────────────────────────────────────────────────────

def discover(
    cidr: Optional[str] = None,
    *,
    passive_only: bool = False,
    resolve_hostnames: bool = True,
    timeout: float = 2.0,
    progress_cb: ProgressCB = None,
    stop_event: Optional[threading.Event] = None,
) -> DiscoveryResult:
    """
    Run all discovery methods in parallel and return a merged DiscoveryResult.

    cidr: e.g. "192.168.1.0/24". If None, auto-detected from local interface.
    passive_only: if True, skip all active probes (ARP cache + mDNS cache only).
    """
    stop = stop_event or threading.Event()
    t0   = time.monotonic()

    if cidr is None:
        cidr = _get_local_cidr()

    try:
        net   = ipaddress.IPv4Network(cidr, strict=False)
        hosts = [str(h) for h in net.hosts()]
    except ValueError as exc:
        return DiscoveryResult(cidr=cidr, error=str(exc))

    devices: Dict[str, DiscoveredDevice] = {}
    methods_used: List[str] = []

    # ── Stage 1: Passive (instant) ────────────────────────────────────────────
    if progress_cb:
        progress_cb("Reading ARP cache…")
    arp_cache = _arp_cache_scan()
    _merge(devices, arp_cache)
    if arp_cache:
        methods_used.append("arp-cache")

    if passive_only or stop.is_set():
        duration = time.monotonic() - t0
        return DiscoveryResult(
            devices=sorted(devices.values(), key=lambda d: ipaddress.ip_address(d.ip)),
            cidr=cidr, duration_s=duration, methods_used=methods_used,
        )

    # ── Stage 2: Active (parallel) ────────────────────────────────────────────
    if progress_cb:
        progress_cb(f"Running parallel active discovery on {cidr} ({len(hosts)} hosts)…")

    futures_map: dict = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures_map["arp-sweep"] = pool.submit(_arp_sweep, cidr, timeout)
        futures_map["icmp-ping"] = pool.submit(_icmp_sweep, hosts, timeout * 0.5)
        futures_map["tcp-syn"]   = pool.submit(_tcp_sweep,  hosts, [80, 443, 22, 8080], timeout * 0.5)
        futures_map["mdns"]      = pool.submit(_mdns_query, timeout)

        for name, fut in futures_map.items():
            if stop.is_set():
                break
            try:
                result_map = fut.result(timeout=timeout + 5)
                if result_map:
                    _merge(devices, result_map)
                    methods_used.append(name)
                    if progress_cb:
                        progress_cb(f"{name}: +{len(result_map)} host(s)")
            except Exception as exc:
                if progress_cb:
                    progress_cb(f"{name}: skipped ({exc})")

    # ── Stage 3: Multi-method name resolution ─────────────────────────────────
    if resolve_hostnames and not stop.is_set():
        if progress_cb:
            progress_cb(f"Resolving names for {len(devices)} device(s)…")
        try:
            from modules.name_resolver import resolve_batch
            name_results = resolve_batch(
                list(devices.values()),
                use_netbios=True, use_mdns=True, use_snmp=False, use_dhcp=True,
            )
            for ip, nr in name_results.items():
                if ip in devices:
                    if nr.hostname and not devices[ip].hostname:
                        devices[ip].hostname = nr.hostname
                    # Attach registry model as display hint via mdns_services list
                    if nr.model:
                        hint = f"model:{nr.model}"
                        if hint not in devices[ip].mdns_services:
                            devices[ip].mdns_services.insert(0, hint)
        except Exception:
            # Fallback to basic rDNS
            with concurrent.futures.ThreadPoolExecutor(max_workers=32) as pool:
                rf = {pool.submit(_resolve_hostname, ip, 0.5): ip
                      for ip, dev in devices.items() if not dev.hostname}
                for fut in concurrent.futures.as_completed(rf):
                    ip = rf[fut]
                    if stop.is_set():
                        break
                    try:
                        name = fut.result()
                        if name and ip in devices:
                            devices[ip].hostname = name
                    except Exception:
                        pass  # non-fatal

    duration = time.monotonic() - t0
    sorted_devs = sorted(devices.values(), key=lambda d: ipaddress.ip_address(d.ip))

    if progress_cb:
        progress_cb(f"Discovery complete — {len(sorted_devs)} device(s) in {duration:.1f} s")

    return DiscoveryResult(
        devices=sorted_devs,
        cidr=cidr,
        duration_s=duration,
        methods_used=methods_used,
    )
