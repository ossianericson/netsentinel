"""
Device-type classifier.

Takes the data already available after a Module 1 scan — vendor string,
hostname, open ports, OS guess — and returns a concise human-readable
device-type label such as "IP Camera", "NAS", "Smart TV", or
"Domain Controller".

No network calls are made here; this is purely a classification step
over data that has already been collected.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


# ── Classification result type ────────────────────────────────────────────────

@dataclass
class ClassificationResult:
    """
    Rich return type from classify_with_evidence().

    device_type   : Human-readable label e.g. "Smart TV", "Games Console".
    vendor        : Vendor string passed in (may be empty).
    confidence    : 0.0–1.0 estimate of classification quality.
    evidence      : Which discriminators fired e.g. ["vendor", "hostname:bravia"].
    mac_randomized: True when the U/L bit indicates a locally administered MAC.
    """
    device_type: str
    vendor: str = ""
    confidence: float = 0.0
    evidence: list[str] = field(default_factory=list)
    mac_randomized: bool = False


def is_randomized_mac(mac: str) -> bool:
    """
    Return True when the MAC's U/L bit (second-least-significant bit of the
    first octet) is set, indicating a locally administered / OS-randomised
    address rather than a genuine burnt-in OUI.

    Accepts any common MAC format: XX:XX:XX:XX:XX:XX, XX-XX-XX-XX-XX-XX,
    XXXXXXXXXXXX, or mixed case.
    """
    normalized = mac.replace(":", "").replace("-", "").replace(".", "")
    if len(normalized) < 2:
        return False
    try:
        return bool(int(normalized[:2], 16) & 0x02)
    except ValueError:
        return False


# ── Label taxonomy ────────────────────────────────────────────────────────────

# Each rule is evaluated in order; first match wins.
# A rule is a dict with at least one of:
#   vendor_re   — regex matched against lowercase vendor string
#   hostname_re — regex matched against lowercase hostname
#   ports       — set of port numbers; ALL must be present in open_ports
#   any_ports   — set of port numbers; ANY one must be present in open_ports
#   os_re       — regex matched against lowercase os_family string
# and always:
#   label       — the device-type string to return

_RULES: list[dict] = [
    # ── Network infrastructure ───────────────────────────────────────────────
    {
        "label": "Router / Firewall",
        "vendor_re": r"cisco|juniper|fortinet|palo alto|ubiquiti|mikrotik|netgate|sonicwall|zyxel|draytek",
    },
    {
        "label": "Router / Gateway",
        "any_ports": {80, 443, 8080, 8443},
        "vendor_re": r"asus|netgear|tp.?link|d.?link|linksys|belkin|arris|motorola|sagemcom|technicolor|fritz|avm|huawei|zte|xiaomi",
    },
    {
        # Chip/component vendors (Liteon, Realtek, Azurewave, etc.) whose OUI
        # appears on a router's WiFi card rather than the router brand's OUI.
        # Presence of a web admin port is strong evidence this is router hardware.
        "label": "Router / Gateway",
        "vendor_re": r"liteon|realtek semiconductor|azurewave|alps electric|murata|fn-link|ampak|ralink technology",
        "any_ports": {80, 443, 8080, 8443},
    },
    {
        "label": "Network Switch",
        "vendor_re": r"cisco|netgear|hp|hewlett.packard|d.?link|trendnet|dell|extreme networks",
        "any_ports": {23, 22, 80, 443},
    },
    {
        "label": "Wireless Access Point",
        "vendor_re": r"ubiquiti|ruckus|aruba|meraki|cambium|engenius|aerohive",
    },
    # ── Servers ──────────────────────────────────────────────────────────────
    {
        "label": "Domain Controller",
        "hostname_re": r"dc\d*|domaincontroller|ad-|ldap",
    },
    {
        "label": "Domain Controller",
        "ports": {389, 445, 88},
    },
    {
        "label": "File / NAS Server",
        "vendor_re": r"synology|qnap|buffalo|western digital|wd|drobo|asustor|terramaster",
    },
    {
        "label": "File / NAS Server",
        "ports": {445, 548},
    },
    {
        "label": "File / NAS Server",
        "hostname_re": r"nas|diskstation|readynas|mycloud",
    },
    {
        "label": "Mail Server",
        "any_ports": {25, 465, 587},
        "any_ports_b": {110, 143, 993, 995},
    },
    {
        "label": "Print Server",
        "any_ports": {631, 9100},
    },
    {
        "label": "Print Server",
        "vendor_re": r"brother|canon|epson|hp|hewlett.packard|lexmark|ricoh|xerox|kyocera|konica|sharp",
    },
    {
        "label": "Web / App Server",
        "ports": {80, 443},
        "os_re": r"linux",
    },
    # ── Surveillance ─────────────────────────────────────────────────────────
    {
        "label": "IP Camera",
        "any_ports": {554, 8554},
    },
    {
        "label": "IP Camera",
        "vendor_re": r"hikvision|dahua|reolink|amcrest|axis|bosch|hanwha|foscam|vivotek|uniview|tiandy|cp plus",
    },
    {
        "label": "IP Camera",
        "hostname_re": r"cam|camera|ipcam|dvr|nvr|cctv",
    },
    {
        "label": "Video Doorbell / Intercom",
        "vendor_re": r"ring|nest|arlo|doorbird|aiphone|2n",
    },
    # ── Smart home & IoT ─────────────────────────────────────────────────────
    {
        "label": "Smart Home Hub",
        "vendor_re": r"philips hue|samsung smartthings|hub|insteon|lutron|wink|homey|hubitat",
    },
    {
        "label": "Smart Home Hub",
        "hostname_re": r"hub|smartthings|philipshue|hue.?bridge",
    },
    {
        "label": "IoT Device",
        "any_ports": {1883, 8883},
    },
    {
        "label": "IoT Device",
        "vendor_re": r"espressif|particle|arduino|seeed|sonoff|tasmota",
    },
    {
        "label": "Smart Speaker / Display",
        "vendor_re": r"amazon|google|sonos|bose|harman|jbl|anker soundcore",
        "hostname_re": r"echo|alexa|nest|chromecast|home.?pod|sonos|google.?home",
    },
    {
        "label": "Smart Speaker / Display",
        "hostname_re": r"echo|alexa|chromecast|homepod",
    },
    {
        "label": "Smart TV",
        "vendor_re": r"samsung|lg|sony|tcl|hisense|vizio|panasonic|philips|roku|tivo|nvidia",
        "hostname_re": r"tv|smarttv|roku|firetv|appletv|shield",
    },
    {
        "label": "Smart TV",
        "hostname_re": r"samsung.?tv|lgtv|lgwebos|webostv|sony.?bravia|roku|firetv|apple.?tv|shield",
    },
    {
        "label": "Streaming Stick",
        "vendor_re": r"amazon|google|roku|nvidia",
        "hostname_re": r"firestick|fire.?tv|chromecast|roku|shield",
    },
    # ── Desktop / laptop / mobile ─────────────────────────────────────────────
    {
        "label": "Windows PC",
        "os_re": r"windows",
        "any_ports": {445, 3389, 5900},
    },
    {
        "label": "Windows PC",
        "os_re": r"windows",
    },
    {
        "label": "macOS Device",
        "os_re": r"macos",
    },
    {
        "label": "macOS Device",
        "vendor_re": r"apple",
        "any_ports": {548, 5900, 22},
    },
    {
        "label": "Linux / Unix Host",
        "os_re": r"linux",
        "any_ports": {22},
    },
    # ── Tablets ───────────────────────────────────────────────────────────────
    {
        "label": "Tablet",
        "hostname_re": r"sm-t\d{3}|galaxy[\-_]?tab",
    },
    {
        "label": "Tablet",
        "vendor_re": r"amazon",
        "hostname_re": r"fire[\-_]?hd\d*|kindle[\-_]?fire",
    },
    # ── iPhone / iPad ─────────────────────────────────────────────────────────
    {
        "label": "iPhone / iPad",
        "vendor_re": r"apple",
        "hostname_re": r"iphone|ipad",
    },
    {
        "label": "iPhone / iPad",
        "vendor_re": r"apple",
    },
    {
        "label": "Android Device",
        "vendor_re": r"samsung|oneplus|google|xiaomi|oppo|vivo|realme|motorola|lenovo",
        "hostname_re": r"android|galaxy|pixel|oneplus",
    },
    {
        # Samsung model numbers (SM-G/SM-A/SM-S phones; SM-T already caught by Tablet rule)
        "label": "Android Device",
        "hostname_re": r"sm-[a-z]\d{2,}",
    },
    # ── VoIP / telephony ─────────────────────────────────────────────────────
    {
        "label": "VoIP Phone / ATA",
        "vendor_re": r"cisco|polycom|yealink|grandstream|snom|avaya|mitel|fanvil|sangoma",
    },
    {
        "label": "VoIP Phone / ATA",
        "any_ports": {5060, 5061},
    },
    # ── Industrial / embedded ─────────────────────────────────────────────────
    {
        "label": "Industrial / ICS Device",
        "vendor_re": r"siemens|schneider|allen.?bradley|rockwell|honeywell|emerson|abb|moxa|advantech",
    },
    {
        "label": "Industrial / ICS Device",
        "any_ports": {102, 502, 4840, 20000},
    },
    # ── Mesh nodes ────────────────────────────────────────────────────────────
    {
        "label": "Mesh Network Node",
        "vendor_re": r"eero|google|tp.?link|asus|netgear|linksys|orbi|deco|nest",
        "hostname_re": r"eero|nest|deco|orbi|velop|halo|nova|mesh",
    },
    {
        "label": "Mesh Network Node",
        "hostname_re": r"eero|deco|orbi|velop|halo|nova|nest.?wifi|google.?wifi",
    },
    # ── Games consoles ────────────────────────────────────────────────────────
    {
        "label": "Games Console",
        "vendor_re": r"sony interactive|playstation",
    },
    {
        "label": "Games Console",
        "hostname_re": r"ps[2345][\-_\.]|playstation|xbox|nintendo.?switch|\bwii\b",
    },
    {
        "label": "Games Console",
        "vendor_re": r"nintendo",
    },
    {
        # Standalone PS4/PS5 hostnames; existing rule requires a trailing separator
        "label": "Games Console",
        "hostname_re": r"\bps[45]\b|playstation[\-_][45]",
    },
    # ── Smart TV — additional hostname patterns ───────────────────────────────
    {
        "label": "Smart TV",
        "hostname_re": r"lgwebos|webostv|lg[\-_]?webos|android[\-_]?tv",
    },
    {
        "label": "Smart TV",
        "hostname_re": r"samsung[\-_]?tv|bravia|panasonictv|philipstv|hisense[\-_]?tv",
    },
    {
        "label": "Smart TV",
        "hostname_re": r"google[\-_]?tv|googletv",
    },
    # ── Audio — Sonos ─────────────────────────────────────────────────────────
    {
        "label": "Smart Speaker / Audio",
        "vendor_re": r"sonos",
    },
    {
        "label": "Smart Speaker / Audio",
        "hostname_re": r"sonos[\-_]?|sonosbeam|sonosone|sonosplay|sonosera",
    },
    # ── Streaming — generic streamer hostname ─────────────────────────────────
    {
        "label": "Streaming Stick",
        "hostname_re": r"\bstreamer\b|castdevice|cast[\-_]device",
    },
    # ── Single Board Computer ─────────────────────────────────────────────────
    {
        "label": "Single Board Computer",
        "vendor_re": r"raspberry pi|raspberrypi",
    },
    {
        "label": "Single Board Computer",
        "hostname_re": r"raspberrypi|raspberry[\-_]pi|\brpi\d*\b|libreelec|dietpi|armbian|orangepi|bananapi|odroid|rock[\-_]?pi",
    },
    # ── Fallback by OS ────────────────────────────────────────────────────────
    {
        "label": "Network Device",
        "os_re": r"network device|router|switch",
    },
]


# ── Public API ────────────────────────────────────────────────────────────────

_MESH_HOSTNAME_RE = re.compile(
    r"eero|deco|orbi|velop|halo|nova|nest.?wifi|google.?wifi|\bmesh\b",
    re.IGNORECASE,
)


def classify(
    vendor: str = "",
    hostname: str = "",
    open_ports: Optional[set[int]] = None,
    os_family: str = "",
    is_gateway: bool = False,
) -> str:
    """
    Return a human-readable device-type label.

    Parameters
    ----------
    vendor      Vendor / manufacturer string (from OUI or banner).
    hostname    Reverse-DNS hostname or NetBIOS name.
    open_ports  Set of open TCP port numbers.
    os_family   OS guess string, e.g. "Windows", "Linux/macOS".
    is_gateway  When True the device is known to be the network gateway —
                bypass OUI/hostname heuristics and return the router label
                directly.  Hostname is still checked for mesh-node patterns
                so a Deco/Eero gateway gets "Mesh Network Node" rather than
                the generic "Router / Gateway".

    Returns
    -------
    A label such as "IP Camera", "NAS Server", "Windows PC", or
    "Unknown Device" if no rule matches.
    """
    if open_ports is None:
        open_ports = set()

    # Gateway devices are definitively routers.  Bypass the OUI/hostname
    # classifier (which can be misled by chip-maker OUIs like Liteon) and
    # return the correct label immediately.
    if is_gateway:
        if _MESH_HOSTNAME_RE.search(hostname):
            return "Mesh Network Node"
        return "Router / Gateway"

    v = vendor.lower()
    h = hostname.lower()
    o = os_family.lower()

    for rule in _RULES:
        # Vendor match
        if "vendor_re" in rule and not re.search(rule["vendor_re"], v):
            # If vendor_re is specified but doesn't match, only skip if
            # there are no other discriminators in the rule
            if len([k for k in rule if k not in ("label", "vendor_re")]) == 0:
                continue

        # Hostname match
        if "hostname_re" in rule and not re.search(rule["hostname_re"], h):
            continue

        # OS match
        if "os_re" in rule and not re.search(rule["os_re"], o):
            continue

        # All-of ports
        if "ports" in rule and not rule["ports"].issubset(open_ports):
            continue

        # Any-of ports (primary)
        if "any_ports" in rule and not rule["any_ports"].intersection(open_ports):
            continue

        # Any-of ports (secondary — used in multi-any_ports rules like mail server)
        if "any_ports_b" in rule and not rule["any_ports_b"].intersection(open_ports):
            continue

        # All discriminators passed — check vendor_re wasn't required-but-failed
        if "vendor_re" in rule and not re.search(rule["vendor_re"], v):
            continue

        return rule["label"]

    return "Unknown Device"


def classify_with_evidence(
    vendor: str = "",
    hostname: str = "",
    open_ports: Optional[set[int]] = None,
    os_family: str = "",
    mac: str = "",
    is_gateway: bool = False,
) -> ClassificationResult:
    """
    Like classify() but returns a ClassificationResult with a confidence
    score and a list of which discriminators fired.

    Parameters
    ----------
    vendor      Vendor / manufacturer string (from OUI or banner).
    hostname    Reverse-DNS hostname or NetBIOS name.
    open_ports  Set of open TCP port numbers.
    os_family   OS guess string, e.g. "Windows", "Linux/macOS".
    mac         Raw MAC address; used to detect locally administered MACs.
    is_gateway  When True the device is known to be the network gateway —
                returns confidence=1.0 with evidence ["is_gateway"].

    Returns
    -------
    ClassificationResult — never None; falls back to device_type="Unknown Device".
    """
    if open_ports is None:
        open_ports = set()

    mac_rand = is_randomized_mac(mac) if mac else False

    if is_gateway:
        label = (
            "Mesh Network Node" if _MESH_HOSTNAME_RE.search(hostname)
            else "Router / Gateway"
        )
        return ClassificationResult(
            device_type=label,
            vendor=vendor,
            confidence=1.0,
            evidence=["is_gateway"],
            mac_randomized=mac_rand,
        )
    v = vendor.lower()
    h = hostname.lower()
    o = os_family.lower()

    for rule in _RULES:
        # Precompute which discriminators match for this rule
        v_match = bool(v and "vendor_re" in rule and re.search(rule["vendor_re"], v))
        h_match = bool(h and "hostname_re" in rule and re.search(rule["hostname_re"], h))
        o_match = bool(o and "os_re" in rule and re.search(rule["os_re"], o))
        p_match = bool("ports" in rule and rule["ports"].issubset(open_ports))
        ap_match = bool("any_ports" in rule and rule["any_ports"].intersection(open_ports))

        # Mirror the gating logic from classify() exactly
        if "vendor_re" in rule and not v_match:
            if len([k for k in rule if k not in ("label", "vendor_re")]) == 0:
                continue
        if "hostname_re" in rule and not h_match:
            continue
        if "os_re" in rule and not o_match:
            continue
        if "ports" in rule and not p_match:
            continue
        if "any_ports" in rule and not ap_match:
            continue
        if "any_ports_b" in rule and not rule["any_ports_b"].intersection(open_ports):
            continue
        if "vendor_re" in rule and not v_match:
            continue

        # Rule matched — build evidence list and compute confidence
        evidence: list[str] = []
        confidence = 0.0

        if v_match:
            # Vendor match is worth less when the MAC may be randomised
            boost = 0.20 if mac_rand else 0.40
            label = "vendor(randomized-mac-penalty)" if mac_rand else "vendor"
            evidence.append(label)
            confidence += boost
        if h_match:
            evidence.append(f"hostname:{hostname[:40]}")
            confidence += 0.30
        if o_match:
            evidence.append(f"os:{os_family}")
            confidence += 0.15
        if p_match:
            evidence.append(f"ports:{sorted(rule['ports'])}")
            confidence += 0.20
        if ap_match:
            matched_p = rule["any_ports"].intersection(open_ports)
            evidence.append(f"any-ports:{sorted(matched_p)}")
            confidence += 0.15
        if mac_rand:
            evidence.append("randomized-mac")

        return ClassificationResult(
            device_type=rule["label"],
            vendor=vendor,
            confidence=min(1.0, confidence),
            evidence=evidence,
            mac_randomized=mac_rand,
        )

    fallback_evidence: list[str] = ["no-rule-matched"]
    if mac_rand:
        fallback_evidence.append("randomized-mac")
    return ClassificationResult(
        device_type="Unknown Device",
        vendor=vendor,
        confidence=0.0,
        evidence=fallback_evidence,
        mac_randomized=mac_rand,
    )


def classify_from_observation(obs: object) -> ClassificationResult:
    """
    Return a ClassificationResult derived directly from a PassiveObservation.

    The observation's device_hint is already a resolved label (produced by the
    SSDP/mDNS classification tables), so we wrap it without further heuristics.
    Confidence is mapped from the string flag: "high" → 0.85, "low" → 0.40.
    """
    hint = getattr(obs, "device_hint", "") or ""
    confidence_str = getattr(obs, "confidence", "low")
    protocol = getattr(obs, "protocol", "")
    service_type = getattr(obs, "service_type", "")

    if not hint:
        return ClassificationResult(
            device_type="Unknown Device",
            confidence=0.0,
            evidence=[f"passive-{protocol}:no-hint"],
        )

    confidence = 0.85 if confidence_str == "high" else 0.40
    evidence = [f"passive-{protocol}:{service_type}"]
    return ClassificationResult(
        device_type=hint,
        confidence=confidence,
        evidence=evidence,
    )


def get_all_device_types() -> list:
    """Return sorted list of all valid device type labels for the UI dropdown."""
    types: set = {rule["label"] for rule in _RULES}
    types.update(["Router / Gateway", "Mesh Network Node", "Unknown Device"])
    return sorted(types)


def classify_device(device, is_gateway: bool = False) -> str:
    """
    Convenience wrapper that accepts a DeviceInfo dataclass instance or a
    plain dict (as returned by Module 1) and calls classify().
    """
    if isinstance(device, dict):
        vendor    = device.get("vendor", "")
        hostname  = device.get("hostname", "")
        os_family = device.get("os_family", "")
        ports     = set(device.get("open_ports", []))
    else:
        vendor    = getattr(device, "vendor",    "")
        hostname  = getattr(device, "hostname",  "")
        os_family = getattr(device, "os_family", "")
        ports     = set(getattr(device, "open_ports", []) or [])

    return classify(vendor=vendor, hostname=hostname,
                    open_ports=ports, os_family=os_family,
                    is_gateway=is_gateway)
