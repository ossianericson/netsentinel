"""
Sanitizes network diagnostic text/data for public sharing (forum posts, PNG exports).

Never expose: public WAN IPs, private IPs (aliased instead), MAC addresses,
or hostnames. All output stays local — this module makes no network calls.
"""

from __future__ import annotations

import ipaddress
import re
from typing import Dict, Optional

_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_MAC_RE = re.compile(r"\b[0-9A-Fa-f]{2}(?:[:-][0-9A-Fa-f]{2}){5}\b")


def mask_ip(ip: str, ip_map: Dict[str, str]) -> Optional[str]:
    """
    Return a stable 192.168.1.N alias for a private IP, or None for a public/
    invalid IP (callers should omit the value entirely in that case).
    """
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return None
    if not addr.is_private:
        return None
    if ip in ip_map:
        return ip_map[ip]
    alias = f"192.168.1.{(len(ip_map)) % 253 + 2}"
    ip_map[ip] = alias
    return alias


def vendor_only(vendor: Optional[str] = None, mac: str = "") -> str:
    """Return a device label with no MAC address — vendor name only."""
    if vendor:
        return f"{vendor} device"
    return "Unknown device"


def sanitize_text(text: str, ip_map: Dict[str, str]) -> str:
    """Scrub any IPv4 address or MAC address found in free text."""
    def _replace_ip(m: re.Match) -> str:
        alias = mask_ip(m.group(0), ip_map)
        return alias if alias else "[IP redacted]"

    out = _IPV4_RE.sub(_replace_ip, text)
    out = _MAC_RE.sub("[MAC redacted]", out)
    return out


def strip_hostname(hostname: str) -> str:
    """Hostnames are never shared — always returns an empty string."""
    return ""
