"""
Sanitizes network diagnostic text/data for public sharing (forum posts, PNG exports).

Never expose: public WAN IPs, private IPs (aliased instead), IPv6 addresses, MAC
addresses, SSIDs, the Windows account name, or hostnames. All output stays local
— this module makes no network calls.

Also the single redaction pass for the B2 diagnostic report, which is why the
last three of those were added: that report carries bounded tails of the crash
sinks, and this is a network scanner, so its logs are full of the user's LAN. One
sanitizer, extended — a second one would drift out of step with this one and the
divergence would only ever be discovered by a leak.
"""

from __future__ import annotations

import ipaddress
import re
from typing import Dict, Optional

_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_MAC_RE = re.compile(r"\b[0-9A-Fa-f]{2}(?:[:-][0-9A-Fa-f]{2}){5}\b")

# Candidate IPv6 literals. Every alternative requires either "::" or a full eight
# groups, which is what keeps a MAC (six groups, no "::") and a clock time
# ("23:59:59") from matching — a report whose timestamps have been redacted is
# unreadable. Candidates are still parsed in _replace_ipv6() before removal.
_IPV6_RE = re.compile(
    r"(?<![0-9A-Za-z:.])"
    r"(?:"
    r"(?:[0-9A-Fa-f]{1,4}:){7}[0-9A-Fa-f]{1,4}"                                     # 8 groups
    r"|(?:[0-9A-Fa-f]{1,4}:){1,7}:(?:[0-9A-Fa-f]{1,4}(?::[0-9A-Fa-f]{1,4}){0,6})?"  # x::y
    r"|::(?:[0-9A-Fa-f]{1,4}(?::[0-9A-Fa-f]{1,4}){0,7})?"                           # ::y
    r")"
    r"(?:%[0-9A-Za-z_.-]+)?"                                                        # zone index
    r"(?![0-9A-Za-z:.])"
)

# An SSID cannot be recognised by its own text — it is arbitrary — so the label in
# front of it is the only handle there is. `\b` before "ssid" is what keeps this
# off `BSSID`, whose value is a MAC and is already covered above; matching there
# would swallow the signal/radio/channel columns that follow it on the same line.
_SSID_RE = re.compile(
    r"(\bssid\s*\d*\s*[:=]\s*)"
    r"(\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\r\n,;)]+)",
    re.IGNORECASE,
)

# The Windows account name, which reaches a log through %LOCALAPPDATA% and so
# appears in nearly every traceback frame. Only the name is replaced: the rest of
# the path is the diagnostic. Both separators are matched because Python emits
# either, sometimes in the same file. Quotes are excluded from the name so a path
# ending a string literal does not take the closing quote with it.
_USER_PROFILE_RE = re.compile(
    r"([A-Za-z]:[\\/]Users[\\/])([^\\/:*?\"'<>|\r\n]+)",
    re.IGNORECASE,
)


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


def _replace_ipv6(m: re.Match) -> str:
    """Remove a candidate IPv6 literal, or leave it alone if it is not one.

    IPv6 is removed outright rather than aliased the way mask_ip() aliases IPv4.
    RFC 1918 makes "private, and therefore safe to keep in aliased form" a
    decidable property for IPv4; IPv6 has no equivalent. A SLAAC address carries
    the interface MAC in EUI-64 form and a global unicast address identifies one
    machine worldwide, so the only transform that does not leak is removal.

    The pattern is deliberately loose and this parse is the real gate: a run of
    hex and colons is ambiguous with plenty of non-addresses, and eating one of
    those is a silent loss of diagnostic text.
    """
    literal = m.group(0).split("%", 1)[0]  # the zone index is ours, not the address's
    try:
        ipaddress.IPv6Address(literal)
    except ValueError:
        return m.group(0)
    return "[IPv6 redacted]"


def _redact_names(text: str, names) -> str:
    """Remove supplied device/room names, whole-token and case-insensitively.

    Names are the one leak class with no pattern of their own: an IP has a shape,
    a MAC has a shape, an SSID has a label in front of it, but a device name is
    arbitrary text sitting in the middle of prose. So the caller supplies the
    list and this only ever removes strings it was told about — a redactor that
    guesses which words are names is one that eats the diagnostic.

    Longest first, because `Floor2 Kitchen` and `Kitchen` are both real node
    names on one network and replacing the short one first would leave
    `Floor2 [name redacted]` — still disclosing, and misleading as well.
    """
    ordered = sorted({n.strip() for n in names if n and n.strip()}, key=len, reverse=True)
    for name in ordered:
        # \b would not fire next to punctuation-heavy names, so the token edges
        # are asserted directly: no adjacent word character on either side. That
        # is what stops a device called "phone" redacting "headphones".
        pattern = re.compile(
            r"(?<![0-9A-Za-z_])" + re.escape(name) + r"(?![0-9A-Za-z_])",
            re.IGNORECASE,
        )
        text = pattern.sub("[name redacted]", text)
    return text


def sanitize_text(text: str, ip_map: Dict[str, str], names=None) -> str:
    """Scrub any IPv4, IPv6 or MAC address found in free text.

    *names* is an optional iterable of device/room names to remove as well. It
    defaults to None so the two already-shipped share-to-public callers
    (`diagnostic_card`, `forum_export`) keep the exact behaviour they were
    verified with.

    Order is load-bearing. Names go first, so they match against unmodified text
    rather than against a line another rule has already rewritten. MACs are then
    removed before IPv6 candidates are examined, so a MAC can never reach the
    address parser. An IPv4-mapped literal (``::ffff:192.168.1.5``) is caught by
    the IPv4 rule first, which is why its dotted tail is aliased even though the
    whole literal never matches here.
    """
    def _replace_ip(m: re.Match) -> str:
        alias = mask_ip(m.group(0), ip_map)
        return alias if alias else "[IP redacted]"

    if names:
        text = _redact_names(text, names)
    out = _IPV4_RE.sub(_replace_ip, text)
    out = _MAC_RE.sub("[MAC redacted]", out)
    out = _IPV6_RE.sub(_replace_ipv6, out)
    out = _SSID_RE.sub(r"\1[SSID redacted]", out)
    out = _USER_PROFILE_RE.sub(r"\g<1><user>", out)
    return out


def strip_hostname(hostname: str) -> str:
    """Hostnames are never shared — always returns an empty string."""
    return ""
