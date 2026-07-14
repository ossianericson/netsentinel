"""
Module 1 — Rogue Device Fingerprinter

Scans the local ARP table and cross-references every MAC address against
the bundled OUI database to identify devices that are known to cause
Layer-2 network problems.
"""

import concurrent.futures
import json
import platform
import re
import socket
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from modules.utils_net import get_arp_snapshot, parallel_map

try:
    from modules.mac_registry import lookup as _mac_registry_lookup
except Exception:
    _mac_registry_lookup = None  # type: ignore

try:
    from modules.name_resolver import resolve as _resolve_name
except Exception:
    _resolve_name = None  # type: ignore

# Hostnames that definitively identify consumer/endpoint devices — impossible
# for a network gateway.  When the gateway IP resolves to one of these (e.g.
# via a stale mDNS cache collision), discard the hostname before classifying.
_CONSUMER_HOSTNAME_RE = re.compile(
    r"playstation|ps[2-5]\b|xbox|nintendo|\bswitch\b|\bwii\b|"
    r"iphone|ipad|ipod|android|galaxy|\bsm-[a-z]\d|"
    r"alexa|\becho\b|kindle|fire.?stick|fire.?tv|fire.?hd|"
    r"chromecast|\broku\b|shield.?tv|apple.?tv|"
    r"macbook|mac.?pro|mac.?mini",
    re.IGNORECASE,
)


@dataclass
class DeviceInfo:
    ip: str
    mac: str
    vendor: str = "Unknown"
    model: str = ""             # e.g. "iPhone 14", "Echo Dot" — from mac_registry OUI lookup
    hostname: str = ""
    known_issues: List[str] = field(default_factory=list)
    risk_level: str = "UNKNOWN"  # HIGH / MEDIUM / LOW / CLEAN / UNKNOWN
    is_link_local: bool = False
    connection_type: str = "Unknown"
    device_type: str = ""       # e.g. "IP Camera", "NAS", "Windows PC"
    os_family: str = ""         # e.g. "Windows", "Linux/macOS"
    verdict: str = ""
    forum_ref: str = ""
    remediation: str = ""
    # Open TCP/UDP ports — populated by port scan enrichment when available
    open_ports: List[int] = field(default_factory=list)
    # Mesh enrichment — populated by MeshWorker after the main ARP scan
    mesh_unit:      str   = ""   # e.g. "Floor2 Vardagsrum"
    mesh_band:      str   = ""   # "2.4G" | "5G" | "6G" | "Wired"
    mesh_up_kbps:   float = 0.0
    mesh_down_kbps: float = 0.0
    # Classification quality — populated by scan enrichment
    confidence:  float = 0.0   # 0.0–1.0 classifier confidence score
    is_gateway:  bool  = False  # True when this IP matches the detected gateway


def _resolve_hostname(ip: str) -> str:
    """Reverse DNS lookup with a 1-second timeout."""
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(socket.gethostbyaddr, ip)
            return fut.result(timeout=1.0)[0]
    except Exception:
        return ""


def _load_offenders(path: Path) -> list:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return []


def _get_arp_table() -> List[tuple]:
    """Return (ip, mac) pairs from the system ARP cache."""
    pairs: List[tuple] = list(get_arp_snapshot().items())
    return pairs


def _get_ipv6_routers() -> set:
    """
    Parse the IPv6 neighbour table and return the set of MAC addresses
    that are advertising themselves as routers ("Router" state).
    These are devices the OS has received an IPv6 Router Advertisement from.
    A non-gateway device with this flag is a rogue router.
    """
    system = platform.system()
    routers: set = set()
    extra = {}
    if system == "Windows":
        extra = {"creationflags": subprocess.CREATE_NO_WINDOW}
    try:
        if system == "Windows":
            raw = subprocess.check_output(
                ["netsh", "interface", "ipv6", "show", "neighbors"],
                text=True, timeout=8, **extra
            )
            # Lines like: fe80::f272:eaff:fe51:d3b8   f0-72-ea-51-d3-b8  Stale (Router)
            for line in raw.splitlines():
                if "Router" in line:
                    m = re.search(r"([\da-fA-F]{2}(?:-[\da-fA-F]{2}){5})", line)
                    if m:
                        routers.add(m.group(1).replace("-", ":").lower())
        else:
            raw = subprocess.check_output(
                ["ip", "-6", "neigh", "show"], text=True, timeout=8
            )
            # Linux: fe80::... dev eth0 lladdr aa:bb:cc:dd:ee:ff router REACHABLE
            for line in raw.splitlines():
                if " router " in line.lower():
                    m = re.search(r"([\da-fA-F]{2}(?::[\da-fA-F]{2}){5})", line)
                    if m:
                        routers.add(m.group(1).lower())
    except Exception:
        pass  # non-fatal
    return routers


def _get_default_gateway() -> Optional[str]:
    system = platform.system()
    extra = {}
    if system == "Windows":
        extra = {"creationflags": subprocess.CREATE_NO_WINDOW}
    try:
        if system == "Windows":
            raw = subprocess.check_output(["ipconfig"], text=True, timeout=5, **extra)
            for line in raw.splitlines():
                if "Default Gateway" in line:
                    m = re.search(r"(\d+\.\d+\.\d+\.\d+)", line)
                    if m:
                        return m.group(1)
        else:
            raw = subprocess.check_output(
                ["ip", "route", "show", "default"], text=True, timeout=5
            )
            m = re.search(r"default via (\d+\.\d+\.\d+\.\d+)", raw)
            if m:
                return m.group(1)
    except Exception:
        pass  # non-fatal
    return None


def _ensure_gateway_in_arp(gateway_ip: str, arp_entries: List[tuple]) -> List[tuple]:
    """
    If the gateway is not already in the ARP entries, trigger an ARP resolution
    so it is included in the scan results.  Uses ctypes SendARP on Windows and
    a no-data UDP connect on other platforms — no subprocess, no PIPE.
    """
    if any(ip == gateway_ip for ip, _ in arp_entries):
        return arp_entries

    system = platform.system()
    new_mac = ""

    if system == "Windows":
        try:
            import ctypes
            import struct
            ip_bytes = socket.inet_aton(gateway_ip)
            ip_int   = struct.unpack("I", ip_bytes)[0]
            mac_buf  = (ctypes.c_ubyte * 6)()
            mac_len  = ctypes.c_ulong(6)
            if ctypes.windll.iphlpapi.SendARP(ip_int, 0, mac_buf, ctypes.byref(mac_len)) == 0:
                new_mac = ":".join(f"{b:02x}" for b in mac_buf)
        except Exception:
            pass  # non-fatal — gateway may still appear on retry below

    if not new_mac:
        # Trigger OS ARP resolution with a zero-byte UDP connect — no data sent
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as _s:
                _s.settimeout(0.5)
                _s.connect((gateway_ip, 1))
        except Exception:
            pass  # non-fatal — ARP entry may still have been populated
        for ip, mac in _get_arp_table():
            if ip == gateway_ip:
                new_mac = mac
                break

    if new_mac:
        result = list(arp_entries)
        result.append((gateway_ip, new_mac))
        return result
    return arp_entries


def scan(offenders_path: Path) -> dict:
    """
    Run Module 1 scan.

    Returns:
        dict with keys: devices, gateway_ip, high_risk_count, total_count, plain_verdict
    """
    offenders = _load_offenders(offenders_path)
    arp_entries = _get_arp_table()
    gateway_ip = _get_default_gateway()
    # Ensure the gateway always appears even when the ARP cache has expired
    if gateway_ip:
        arp_entries = _ensure_gateway_in_arp(gateway_ip, arp_entries)
    ipv6_routers = _get_ipv6_routers()

    # Resolve the gateway MAC so we can exclude it from rogue-router checks
    gateway_mac: Optional[str] = None
    for ip, mac in arp_entries:
        if ip == gateway_ip:
            gateway_mac = mac
            break

    # Detect proxy-ARP IPs: router answers ARP for wireless clients that are
    # not directly reachable at Layer 2 (e.g. Deco mesh clients on a separate
    # wireless segment).  The MAC shown for these IPs is the router's own MAC,
    # so their real hardware address is unknowable from ARP alone.
    proxy_arp_ips: set = set()
    if gateway_mac:
        for _ip, _mac in arp_entries:
            if _mac == gateway_mac and _ip != gateway_ip:
                proxy_arp_ips.add(_ip)

    results: List[DeviceInfo] = []
    high_risk: List[DeviceInfo] = []

    # Resolve names only for IPs that will actually be processed (skip proxy-ARP IPs).
    _resolve_entries = [(ip, mac) for ip, mac in arp_entries if ip not in proxy_arp_ips]
    if _resolve_name is not None:
        from modules.name_resolver import resolve_batch
        resolved = resolve_batch(
            [{"ip": ip, "mac": mac} for ip, mac in _resolve_entries],
            use_netbios=True, use_mdns=True, use_snmp=False, use_dhcp=True,
        )
    else:
        hostnames = parallel_map(lambda t: _resolve_hostname(t[0]), _resolve_entries, workers=20)
        resolved = {ip: type("_N", (), {"hostname": h, "vendor": "", "model": "", "device_type": ""})()
                    for (ip, _), h in zip(_resolve_entries, hostnames)}

    for ip, mac in arp_entries:
        if ip in proxy_arp_ips:
            # Real device — real MAC unknown (router answered via proxy ARP).
            # Skip: the mesh/hardware plugin synthesizes this row with the correct
            # MAC from the router API.  proxy_arp_ips is returned in the result dict
            # so the enrichment layer can re-add an annotated row if no plugin is active.
            continue
        info = DeviceInfo(ip=ip, mac=mac)
        name_info = resolved.get(ip)
        info.hostname = getattr(name_info, "hostname", "") if name_info else ""
        # Enrich vendor/device_type from MAC registry — use vendor presence, not model,
        # so entries that have vendor but no specific model still enrich correctly.
        if name_info:
            _ni_vendor = getattr(name_info, "vendor", "") or ""
            _ni_dtype  = getattr(name_info, "device_type", "") or ""
            _ni_model  = getattr(name_info, "model", "") or ""
            if _ni_vendor:
                info.vendor = _ni_vendor
            if _ni_dtype and not info.device_type:
                info.device_type = _ni_dtype
            if _ni_model:
                info.model = _ni_model

        # --- Link-local detection (rogue DHCP indicator) ---
        if ip.startswith("169.254."):
            info.is_link_local = True
            info.risk_level = "HIGH"
            info.verdict = (
                f"Link-local address detected ({ip}). This device either failed to "
                "obtain a DHCP lease or is acting as a rogue DHCP/network host."
            )

        # --- Gateway label ---
        if ip == gateway_ip:
            info.connection_type = "Gateway (Router)"

        # --- OUI matching ---
        oui_matched = False
        mac_prefix = mac[:8].lower()  # "xx:xx:xx"
        for offender in offenders:
            matched = any(mac_prefix == oui.lower() for oui in offender.get("ouis", []))
            if matched:
                oui_matched = True
                info.vendor = offender.get("vendor", "Unknown Vendor")
                info.known_issues = offender.get("known_issues", [])
                info.forum_ref = offender.get("forum_reference", "")
                info.remediation = offender.get("remediation", "")
                # Gateway devices are legitimate by definition — don't flag them
                if ip == gateway_ip:
                    info.risk_level = "CLEAN"
                    info.verdict = f"Recognised vendor: {info.vendor}. This is your primary gateway — no action needed."
                else:
                    info.risk_level = offender.get("risk_level", "LOW")
                    issues_short = "; ".join(info.known_issues[:2])
                    info.verdict = (
                        f"Recognised vendor: {info.vendor}. "
                        f"Known network issues: {issues_short}. "
                        f"Risk: {info.risk_level}."
                    )
                break

        # --- IPv6 rogue router detection ---
        # Only flag UNKNOWN devices (not in offenders.json) as rogue routers via
        # IPv6 RA.  Known mesh nodes (TP-Link Deco, Google Nest, etc.) are already
        # characterised by the offenders database — trust that rating rather than
        # overriding a LOW device to HIGH just because it sends normal mesh RA frames.
        # Also guard against gateway_mac being None (can happen after ARP flush).
        if (
            mac in ipv6_routers
            and mac != gateway_mac
            and ip != gateway_ip        # extra safety when gateway_mac is None
            and not oui_matched         # unknown device → genuine rogue alert
        ):
            info.connection_type = "Rogue Router (IPv6 RA)"
            info.risk_level = "HIGH"
            rogue_prefix = (
                "\u26a0\ufe0f ROGUE ROUTER DETECTED via IPv6 Router Advertisement. "
                "This device is advertising itself as a network gateway but is NOT "
                "your primary router. This causes split routing, DNS failures, and "
                "periodic internet outages. "
            )
            info.verdict = rogue_prefix + (info.verdict or "Disconnect its Ethernet cable immediately.")

        # --- Default / clean ---
        if not info.verdict:
            info.risk_level = "CLEAN"
            info.verdict = "No known issues found for this device."

        # --- Device-type classification ---
        # Only run classifier when mac_registry didn't already provide a type.
        # This preserves accurate product-line labels (e.g. "Streaming Stick")
        # while still classifying unknown-OUI devices via vendor/hostname/ports.
        _is_gw = (ip == gateway_ip)
        info.is_gateway = _is_gw
        # Sanity-check the gateway hostname: mDNS/ARP cache collisions can
        # resolve a consumer-device name (e.g. "Playstation 4") for the gateway
        # IP.  Clear it before classification so the display and classifier both
        # get a clean slate.
        if _is_gw and info.hostname and _CONSUMER_HOSTNAME_RE.search(info.hostname):
            info.hostname = ""
        if not info.device_type or info.device_type == "Unknown Device":
            try:
                from modules.device_classifier import classify_registry_first
                info.device_type = classify_registry_first(
                    mac=mac,
                    vendor=info.vendor,
                    hostname=info.hostname,
                    os_family=info.os_family,
                    open_ports=set(info.open_ports),
                    is_gateway=_is_gw,
                )
            except Exception:
                info.device_type = "Unknown Device"

        if info.risk_level == "HIGH":
            high_risk.append(info)

        results.append(info)

    # --- Plain-English verdict ---
    if not results:
        plain_verdict = (
            "No devices found in the ARP table. "
            "Make sure you are connected to a local network."
        )
    elif high_risk:
        names = [f"{d.vendor} ({d.mac}) at {d.ip}" for d in high_risk]
        plain_verdict = (
            f"HIGH RISK: {len(high_risk)} device(s) on your network are "
            "known to cause network problems: "
            + "; ".join(names)
            + ". See individual results for remediation steps."
        )
    else:
        plain_verdict = (
            f"Scanned {len(results)} device(s). "
            "No high-risk devices detected in ARP table."
        )

    return {
        "devices": results,
        "gateway_ip": gateway_ip,
        "high_risk_count": len(high_risk),
        "total_count": len(results),
        "plain_verdict": plain_verdict,
        # IPs skipped because the router answered ARP on their behalf (proxy ARP).
        # The enrichment layer uses this set to re-add annotated rows for uncovered
        # IPs when no mesh/hardware plugin is active.
        "proxy_arp_ips": proxy_arp_ips,
    }
