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
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from modules.adaptive_timing import derive_profile, measure_gateway_rtt
from modules.utils_net import get_arp_snapshot, parallel_map

try:
    from modules.mac_registry import lookup as _mac_registry_lookup
except Exception:
    _mac_registry_lookup = None  # type: ignore

try:
    from modules.name_resolver import resolve as _resolve_name, ResolvedName
except Exception:
    _resolve_name = None  # type: ignore
    ResolvedName = None  # type: ignore

# Part 2/L8: re-resolve a device's name at most once per week. A caller-supplied
# known_devices snapshot lets scan() skip the network probe for a MAC resolved
# more recently than this — see scan()'s known_devices param.
_HOSTNAME_CACHE_TTL_S = 7 * 24 * 3600

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
    # Part 2/L8: True once this scan actively resolved this device's name (a
    # real resolve_batch probe ran) — False when the hostname came from the
    # persisted TTL cache instead. device_tracker.process_scan() uses this to
    # decide whether to stamp known_device.hostname_resolved_at.
    name_resolved_fresh: bool = False


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


def _log_scan_timing(setup: float, phase1: float, phase2: float, device_count: int) -> None:
    """Part 2/L9: best-effort per-phase timing to a local log so a future
    "it was slow at the office" report is diagnosable from a pasted log file
    instead of memory. Never raises — telemetry must never affect scan results."""
    try:
        import logging as _logging
        from modules.utils import get_app_data_dir
        logger = _logging.getLogger("netsentinel.scan_timing")
        if not logger.handlers:
            path = get_app_data_dir() / "netsentinel_scan_timing.log"
            handler = _logging.FileHandler(str(path), mode="a", encoding="utf-8")
            handler.setFormatter(_logging.Formatter("%(asctime)s %(message)s"))
            logger.addHandler(handler)
            logger.setLevel(_logging.INFO)
            logger.propagate = False
        logger.info(
            "devices=%d setup=%.2fs phase1_skeleton=%.2fs phase2_resolve=%.2fs total=%.2fs",
            device_count, setup, phase1, phase2, setup + phase1 + phase2,
        )
    except Exception:
        pass  # non-fatal — timing telemetry must never break a scan


def scan(
    offenders_path: Path,
    progress_cb=None,
    device_cb=None,
    known_devices: Optional[Dict[str, Any]] = None,
    scope_cidr: Optional[str] = None,
) -> dict:
    """
    Run Module 1 scan.

    progress_cb(str), if given, is forwarded to name resolution — the slowest
    phase on a large ARP table — so the caller can report real "n/total" progress
    instead of appearing stuck (Part 1/C1).

    device_cb(DeviceInfo), if given, streams each device the moment its ARP
    entry is known (Part 2/L7) — before name resolution — so a caller can show
    a live-preview row immediately instead of waiting for the whole ARP table
    to resolve. It is called a second time for the same device once its name
    resolves, with hostname/device_type updated in place. A raised exception
    inside device_cb is swallowed — it is UI feedback, not load-bearing.

    known_devices (Part 2/L8), if given, is a {mac: obj} snapshot (duck-typed —
    only `.hostname` and `.hostname_resolved_at` are read; no MetricStore import
    here) used to skip re-resolving a MAC whose name was actively resolved
    within the last 7 days. A blank cached hostname counts as a valid cache hit
    too, so a consistently-silent device isn't re-probed every scan. Omitting
    this param (the default) reproduces pre-L8 behaviour exactly — every
    device is resolved and marked name_resolved_fresh=True.

    scope_cidr (Part 2/L5), if given, bounds the ARP-table pass to that CIDR —
    entries outside it (a different VLAN/subnet the caller never asked to touch)
    are excluded from devices/total_count/high_risk_count and get no resolution
    work, but are never silently dropped: each becomes a minimal DeviceInfo stub
    in the returned out_of_scope_devices list. Omitting this param (the default)
    reproduces pre-L5 behaviour exactly — every ARP entry is processed regardless
    of subnet.

    Returns:
        dict with keys: devices, gateway_ip, high_risk_count, total_count,
        plain_verdict, out_of_scope_devices
    """
    _t_start = time.monotonic()
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

    # Part 2/L5: partition into in-scope vs out-of-scope BEFORE any per-device
    # work — out-of-scope entries never get OUI lookup, risk classification, or
    # name resolution spent on them, but are reported (not dropped) below.
    if scope_cidr:
        from modules.network_environment import partition_by_scope
        _in_scope_pairs, _out_of_scope_pairs = partition_by_scope(arp_entries, scope_cidr)
    else:
        _in_scope_pairs, _out_of_scope_pairs = list(arp_entries), []

    out_of_scope_devices: List[DeviceInfo] = [
        DeviceInfo(
            ip=_ip, mac=_mac, risk_level="UNKNOWN",
            verdict=(
                f"Outside declared scan scope ({scope_cidr}) — seen in ARP but not "
                "actively scanned. Adjust in Settings → Network Scanning to include it."
            ),
        )
        for _ip, _mac in _out_of_scope_pairs
    ]

    results: List[DeviceInfo] = []
    high_risk: List[DeviceInfo] = []
    info_by_ip: dict = {}
    oui_matched_ips: set = set()
    # Part 2/L8: (ip, cached_hostname) pairs whose name resolution can be
    # skipped this scan — populated during Phase 1, applied right after
    # _apply_resolution() is defined (below), before the resolve_batch call.
    _cache_hits: List[tuple] = []
    _now = int(time.time())
    _t_setup = time.monotonic()

    # ── Phase 1 (Part 2/L7): build every device's skeleton from ARP + OUI data
    # only — nothing here waits on name resolution, so device_cb can stream a
    # complete-enough-to-display row the instant the ARP table is known. ──────
    for ip, mac in _in_scope_pairs:
        if ip in proxy_arp_ips:
            # Real device — real MAC unknown (router answered via proxy ARP).
            # Skip: the mesh/hardware plugin synthesizes this row with the correct
            # MAC from the router API.  proxy_arp_ips is returned in the result dict
            # so the enrichment layer can re-add an annotated row if no plugin is active.
            continue
        info = DeviceInfo(ip=ip, mac=mac)

        # --- Part 2/L8: hostname TTL cache hit? ---
        # A blank cached hostname counts as a valid hit too — a device that
        # consistently fails to resolve (e.g. VPN-blocked) shouldn't be
        # re-probed every scan just because the cached value is empty.
        if known_devices:
            _kd = known_devices.get(mac.lower())
            _kd_resolved_at = getattr(_kd, "hostname_resolved_at", None) if _kd else None
            if _kd_resolved_at is not None and (_now - _kd_resolved_at) < _HOSTNAME_CACHE_TTL_S:
                _cache_hits.append((ip, getattr(_kd, "hostname", "") or ""))

        # --- Instant vendor/model/device_type from the MAC OUI registry ---
        # Same source resolve() uses internally (mac_lookup) — safe to call
        # directly here rather than waiting for the (slower) resolve_batch pass.
        if _mac_registry_lookup is not None:
            try:
                _reg = _mac_registry_lookup(mac) or {}
            except Exception:
                _reg = {}
            if _reg.get("vendor"):
                info.vendor = _reg["vendor"]
            if _reg.get("device_type"):
                info.device_type = _reg["device_type"]
            if _reg.get("model"):
                info.model = _reg["model"]

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
        if oui_matched:
            oui_matched_ips.add(ip)

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

        info.is_gateway = (ip == gateway_ip)

        if info.risk_level == "HIGH":
            high_risk.append(info)

        results.append(info)
        info_by_ip[ip] = info

        if device_cb:
            try:
                device_cb(info)
            except Exception:
                pass  # non-fatal — a broken UI callback must not abort scanning

    _t_phase1 = time.monotonic()

    # ── Phase 2: apply the resolved name to each device in place, re-running
    # device-type classification (which needs the hostname) and streaming the
    # update via device_cb again. Idempotent — safe to call twice for the same
    # ip (once live via resolve_batch's on_result, once authoritatively below
    # from the returned dict), which also keeps this correct for callers that
    # mock resolve_batch's return value without exercising on_result. ─────────
    def _apply_resolution(ip: str, name_info, fresh: bool = True) -> None:
        info = info_by_ip.get(ip)
        if info is None:
            return
        info.name_resolved_fresh = fresh
        info.hostname = getattr(name_info, "hostname", "") if name_info else ""
        if name_info:
            _ni_vendor = getattr(name_info, "vendor", "") or ""
            _ni_dtype  = getattr(name_info, "device_type", "") or ""
            _ni_model  = getattr(name_info, "model", "") or ""
            # Offenders.json (phase 1) always wins over the generic mac-registry
            # vendor resolve() derives — matches the pre-streaming single-pass order.
            if _ni_vendor and ip not in oui_matched_ips:
                info.vendor = _ni_vendor
            if _ni_dtype and not info.device_type:
                info.device_type = _ni_dtype
            if _ni_model:
                info.model = _ni_model

        # Sanity-check the gateway hostname: mDNS/ARP cache collisions can
        # resolve a consumer-device name (e.g. "Playstation 4") for the gateway
        # IP.  Clear it before classification so the display and classifier both
        # get a clean slate.
        if info.is_gateway and info.hostname and _CONSUMER_HOSTNAME_RE.search(info.hostname):
            info.hostname = ""

        # --- Device-type classification ---
        # Only run classifier when mac_registry didn't already provide a type.
        # This preserves accurate product-line labels (e.g. "Streaming Stick")
        # while still classifying unknown-OUI devices via vendor/hostname/ports.
        if not info.device_type or info.device_type == "Unknown Device":
            try:
                from modules.device_classifier import classify_registry_first
                info.device_type = classify_registry_first(
                    mac=info.mac,
                    vendor=info.vendor,
                    hostname=info.hostname,
                    os_family=info.os_family,
                    open_ports=set(info.open_ports),
                    is_gateway=info.is_gateway,
                )
            except Exception:
                info.device_type = "Unknown Device"

        if device_cb:
            try:
                device_cb(info)
            except Exception:
                pass  # non-fatal — a broken UI callback must not abort scanning

    # Part 2/L8: apply cached hostnames now that _apply_resolution() exists —
    # fresh=False means device_tracker.process_scan() will NOT re-stamp
    # known_device.hostname_resolved_at, so the TTL clock keeps counting from
    # the original resolution rather than resetting on every cache-hit scan.
    _cache_hit_ips = {ip for ip, _ in _cache_hits}
    if ResolvedName is not None:
        for _ip, _cached_hostname in _cache_hits:
            _apply_resolution(_ip, ResolvedName(ip=_ip, hostname=_cached_hostname), fresh=False)

    # Resolve names only for IPs that will actually be processed (skip proxy-ARP
    # IPs, Part 2/L8 cache hits — applied above — and Part 2/L5 out-of-scope
    # entries, which get no resolution work spent on them at all).
    _resolve_entries = [
        (ip, mac) for ip, mac in _in_scope_pairs
        if ip not in proxy_arp_ips and ip not in _cache_hit_ips
    ]
    if _resolve_name is not None:
        from modules.name_resolver import resolve_batch
        # Adaptive timeouts derived from measured gateway RTT (Part 2/L1) — on a
        # home LAN this reproduces today's hard-coded constants unchanged; over a
        # VPN/corporate network it relaxes rDNS/NetBIOS/mDNS timeouts so a slow
        # but real reply isn't recorded as a blank hostname.
        _rtt = measure_gateway_rtt(gateway_ip)
        _profile = derive_profile(_rtt)
        if progress_cb:
            progress_cb(_profile.label)
        resolved = resolve_batch(
            [{"ip": ip, "mac": mac} for ip, mac in _resolve_entries],
            use_netbios=True, use_mdns=True, use_snmp=False, use_dhcp=True,
            progress_cb=progress_cb, timing_profile=_profile,
            on_result=_apply_resolution,
        )
    else:
        hostnames = parallel_map(lambda t: _resolve_hostname(t[0]), _resolve_entries, workers=20)
        resolved = {ip: type("_N", (), {"hostname": h, "vendor": "", "model": "", "device_type": ""})()
                    for (ip, _), h in zip(_resolve_entries, hostnames)}

    # Authoritative final pass over the returned dict — guarantees correctness
    # even if on_result never fired for some entry (fallback path above, or a
    # caller that mocks resolve_batch's return value without calling on_result).
    for ip, _mac in _resolve_entries:
        _apply_resolution(ip, resolved.get(ip))

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

    if out_of_scope_devices:
        plain_verdict += (
            f" {len(out_of_scope_devices)} device(s) seen in ARP outside your "
            f"declared scan scope ({scope_cidr}) were not scanned — adjust in "
            "Settings → Network Scanning to include them."
        )

    _t_phase2 = time.monotonic()
    _log_scan_timing(
        setup=_t_setup - _t_start, phase1=_t_phase1 - _t_setup, phase2=_t_phase2 - _t_phase1,
        device_count=len(results),
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
        # Part 2/L5: entries excluded by scope_cidr — never silently dropped.
        "out_of_scope_devices": out_of_scope_devices,
    }
