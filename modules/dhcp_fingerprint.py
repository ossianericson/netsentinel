"""
dhcp_fingerprint.py — DHCP option mining for device OS and type identification.

Extracts option 60 (Vendor Class Identifier, VCI) and option 12 (hostname) from
DHCP client packets to produce a DhcpFingerprint.  VCI is the single most reliable
OS fingerprint on a network — "MSFT 5.0" is Windows; "android-dhcp-12" is Android
12; "udhcp 1.x" is embedded Linux (likely IoT or router firmware).  Zero extra
network traffic required: this data rides in every DHCPDISCOVER and DHCPREQUEST.

Public API
----------
fingerprint_vci(vci)            → DhcpFingerprint
fingerprint_from_options(opts)  → DhcpFingerprint
update_cache(fingerprints)      → None   (called after each DHCP scan)
get_option12_hostname(mac)      → str
get_fingerprint(mac)            → Optional[DhcpFingerprint]
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


# ── Result type ────────────────────────────────────────────────────────────────

@dataclass
class DhcpFingerprint:
    device_hint: str = ""   # "Windows PC" | "Android Device" | "IoT Device" | …
    os_hint:     str = ""   # "Windows 10+" | "Android 12" | "Embedded Linux" | …
    hostname:    str = ""   # DHCP option 12 — client-supplied hostname
    confidence:  str = ""   # "high" | "low"
    evidence:    str = ""   # human-readable: "VCI: MSFT 5.0"


# ── VCI pattern table ──────────────────────────────────────────────────────────
# Each entry: (pattern, device_hint, os_hint_template, confidence)
# Capture groups in the pattern may be referenced in os_hint_template as {1}, {2}.

_VCI_MAP: List[Tuple[str, str, str, str]] = [
    # Windows — "MSFT 5.0" (NT4+), "MSFT 5.0" is constant across all Win versions
    (r"^MSFT\s",                   "Windows PC",             "Windows",              "high"),
    # Android — "android-dhcp-12", "android-dhcp-13", etc.
    (r"^android-dhcp-(\d+)",       "Android Device",         "Android {1}",          "high"),
    # Generic Android fallback (older firmware omits version)
    (r"^android",                  "Android Device",         "Android",              "low"),
    # Apple iOS / iPadOS
    (r"^iPhone",                   "iPhone / iPad",          "iOS",                  "high"),
    (r"^iPadOS",                   "iPhone / iPad",          "iPadOS",               "high"),
    (r"^iPad",                     "iPhone / iPad",          "iPadOS",               "high"),
    # Apple macOS hardware names (MacBook Pro, MacBook Air, iMac, Mac mini…)
    (r"^MacBook",                  "Apple Mac",              "macOS",                "high"),
    (r"^iMac",                     "Apple Mac",              "macOS",                "high"),
    (r"^Mac\s",                    "Apple Mac",              "macOS",                "high"),
    # Generic Apple fallback
    (r"^Apple\b",                  "Apple Device",           "Apple OS",             "low"),
    # Linux — dhcpcd (used by Arch, Alpine, Void, Pi OS)
    (r"^dhcpcd-",                  "Linux / Unix Host",      "Linux",                "low"),
    # Linux — udhcpc / udhcpd (BusyBox; routers, IoT, embedded)
    (r"^udhcpc?[\s\-]",            "IoT Device",             "Embedded Linux",       "low"),
    # Raspberry Pi
    (r"^Raspbian",                 "Single Board Computer",  "Raspbian Linux",       "high"),
    (r"^rpi-",                     "Single Board Computer",  "Raspberry Pi OS",      "high"),
    # ESPHome / Tasmota (home automation microcontrollers)
    (r"^ESPHome",                  "IoT Device",             "ESPHome",              "high"),
    (r"^Tasmota",                  "IoT Device",             "Tasmota",              "high"),
    # OpenWrt / DD-WRT (router firmware)
    (r"^OpenWrt",                  "Router / Gateway",       "OpenWrt Linux",        "high"),
    (r"^DD-WRT",                   "Router / Gateway",       "DD-WRT Linux",         "high"),
    # Cisco IOS (network infrastructure)
    (r"^[Cc]isco",                 "Network Switch/Router",  "Cisco IOS",            "high"),
    # Apple AirPort
    (r"^AirPort",                  "Wireless Access Point",  "Apple AirPort",        "high"),
    # Amazon Kindle / Fire TV / Echo
    (r"^Kindle",                   "Tablet / E-Reader",      "Amazon OS",            "high"),
    (r"^FireTV",                   "Smart TV / Streaming",   "Amazon OS",            "high"),
    (r"^Echo",                     "Smart Speaker",          "Amazon OS",            "high"),
    (r"^amazon-",                  "Smart Home Device",      "Amazon OS",            "low"),
    # PXE boot (diskless clients, deployment stations)
    (r"^PXEClient",                "PXE Boot Client",        "Network Boot",         "high"),
    # Generic Linux / BSD fallback
    (r"^linux-",                   "Linux Host",             "Linux",                "low"),
    (r"^Linux\b",                  "Linux Host",             "Linux",                "low"),
    # FreeBSD / OpenBSD
    (r"^FreeBSD",                  "Linux / Unix Host",      "FreeBSD",              "high"),
    (r"^OpenBSD",                  "Linux / Unix Host",      "OpenBSD",              "high"),
    # Samsung Smart TV / Tizen
    (r"^Tizen",                    "Smart TV / Streaming",   "Tizen OS",             "high"),
    # Generic IoT / embedded fallback (lowercase udhcp without space/dash)
    (r"^udhcp",                    "IoT Device",             "Embedded Linux",       "low"),
]

# Pre-compile patterns once at import time
_VCI_COMPILED: List[Tuple[re.Pattern, str, str, str]] = [
    (re.compile(pat, re.IGNORECASE), dh, oh, conf)
    for pat, dh, oh, conf in _VCI_MAP
]


# ── Fingerprinting functions ───────────────────────────────────────────────────

def fingerprint_vci(vci: str) -> DhcpFingerprint:
    """
    Match a Vendor Class Identifier string against known patterns.

    Returns a DhcpFingerprint.  When no pattern matches, returns an empty
    fingerprint (confidence="") rather than raising.
    """
    if not vci:
        return DhcpFingerprint()
    for pattern, device_hint, os_hint_tmpl, confidence in _VCI_COMPILED:
        m = pattern.search(vci)
        if m:
            # Substitute capture groups into os_hint template: {1} → group(1)
            os_hint = os_hint_tmpl
            for i, g in enumerate(m.groups(), start=1):
                if g is not None:
                    os_hint = os_hint.replace(f"{{{i}}}", g)
            return DhcpFingerprint(
                device_hint=device_hint,
                os_hint=os_hint,
                confidence=confidence,
                evidence=f"VCI: {vci[:60]}",
            )
    return DhcpFingerprint(evidence=f"VCI: {vci[:60]}")


def fingerprint_from_options(options: dict) -> DhcpFingerprint:
    """
    Given a raw DHCP options dict (as returned by Scapy's option parsing),
    extract option 12 (hostname) and option 60 (VCI) and return a fingerprint.

    Accepts both Scapy string keys ("hostname", "vendor_class_id") and integer
    keys (12, 60) so callers are not coupled to Scapy's naming.
    """
    # Extract VCI — option 60
    vci: str = ""
    for key in ("vendor_class_id", 60):
        raw = options.get(key, b"")
        if raw:
            if isinstance(raw, bytes):
                vci = raw.decode("ascii", errors="replace").strip()
            else:
                vci = str(raw).strip()
            break

    # Extract hostname — option 12
    hostname: str = ""
    for key in ("hostname", 12):
        raw = options.get(key, b"")
        if raw:
            if isinstance(raw, bytes):
                hostname = raw.decode("ascii", errors="replace").strip()
            else:
                hostname = str(raw).strip()
            break

    fp = fingerprint_vci(vci)
    if hostname:
        fp.hostname = hostname
    return fp


# ── Module-level cache (populated by update_cache after each DHCP scan) ────────

_cache_lock = threading.Lock()
_mac_cache: Dict[str, DhcpFingerprint] = {}   # normalised MAC → DhcpFingerprint


def _norm_mac(mac: str) -> str:
    return mac.lower().replace("-", ":").strip()


def update_cache(fingerprints: Dict[str, DhcpFingerprint]) -> None:
    """
    Merge a {mac: DhcpFingerprint} dict into the module-level cache.

    Existing high-confidence entries are not overwritten by low-confidence ones.
    Called by dhcp_detector.scan() after each scan window completes.
    """
    if not fingerprints:
        return
    with _cache_lock:
        for mac, fp in fingerprints.items():
            key = _norm_mac(mac)
            if not key:
                continue
            existing = _mac_cache.get(key)
            if existing and existing.confidence == "high" and fp.confidence != "high":
                continue  # don't downgrade
            _mac_cache[key] = fp


def get_option12_hostname(mac: str) -> str:
    """Return the DHCP option 12 hostname for a MAC, or '' if not cached."""
    if not mac:
        return ""
    with _cache_lock:
        fp = _mac_cache.get(_norm_mac(mac))
    return fp.hostname if fp else ""


def get_fingerprint(mac: str) -> Optional[DhcpFingerprint]:
    """Return the cached DhcpFingerprint for a MAC, or None if not cached."""
    if not mac:
        return None
    with _cache_lock:
        return _mac_cache.get(_norm_mac(mac))


def clear_cache() -> None:
    """Clear the module-level fingerprint cache (used in tests)."""
    with _cache_lock:
        _mac_cache.clear()
