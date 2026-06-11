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
from typing import Optional


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
        "vendor_re": r"espressif|particle|arduino|raspberry pi foundation|seeed|sonoff|tasmota",
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
    # ── Smart TV — additional hostname patterns ───────────────────────────────
    {
        "label": "Smart TV",
        "hostname_re": r"lgwebos|webostv|lg[\-_]?webos|android[\-_]?tv",
    },
    {
        "label": "Smart TV",
        "hostname_re": r"samsung[\-_]?tv|bravia|panasonictv|philipstv|hisense[\-_]?tv",
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
    # ── Fallback by OS ────────────────────────────────────────────────────────
    {
        "label": "Network Device",
        "os_re": r"network device|router|switch",
    },
]


# ── Public API ────────────────────────────────────────────────────────────────

def classify(
    vendor: str = "",
    hostname: str = "",
    open_ports: Optional[set[int]] = None,
    os_family: str = "",
) -> str:
    """
    Return a human-readable device-type label.

    Parameters
    ----------
    vendor      Vendor / manufacturer string (from OUI or banner).
    hostname    Reverse-DNS hostname or NetBIOS name.
    open_ports  Set of open TCP port numbers.
    os_family   OS guess string, e.g. "Windows", "Linux/macOS".

    Returns
    -------
    A label such as "IP Camera", "NAS Server", "Windows PC", or
    "Unknown Device" if no rule matches.
    """
    if open_ports is None:
        open_ports = set()

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


def classify_device(device) -> str:
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
                    open_ports=ports, os_family=os_family)
