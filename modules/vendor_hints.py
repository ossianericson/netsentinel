"""
vendor_hints — derive a vendor from signals other than the OUI.

A locally-administered ("privacy") MAC carries no OUI, so vendor lookup can
never answer for it however large the OUI database grows. That is not a rare
edge: 8 of 30 devices on the reference network use one, and they are stable —
iOS and Android randomise per-SSID and then keep that address. device_identity
already argues this for *identity* ("Ossians-iPhone-2022 is both randomised and
perfectly identifiable"); this module is the missing *vendor* half.

Live case that motivated it: 6a:94:29:ec:8f:4d / "Chromecast-Audio-Vardagsrum"
showed vendor "Unknown" beside an identical Chromecast that happened to carry a
real OUI and so showed "Google" — the same device, two different answers,
decided entirely by which MAC the unit shipped with.

Hostname is the only hint implemented today. It is deliberately weaker evidence
than an OUI: callers must use it only to fill a genuine blank, never to
overwrite a vendor an OUI already supplied (see rogue_device._apply_resolution).

Pure Python — no PyQt, no DB access, no network (ARCH RULE 1).
"""
from __future__ import annotations

import re

__all__ = ["vendor_from_hostname"]


# Deliberately conservative. Every pattern is an unambiguous product or brand
# name, anchored on word boundaries so "greenest-server" does not read as Nest
# and "echolocation-pc" does not read as Echo. First match wins.
#
# OS names are absent by design: LibreELEC, DietPi, Armbian and OpenWrt all run
# on hardware from many makers, so inferring a vendor from one would be the same
# over-claim as trusting an ODM's OUI for a product identity — which is exactly
# the defect that put a Raspberry Pi under a Microsoft Xbox entry.
_HOSTNAME_VENDOR: list[tuple[str, str]] = [
    (r"chromecast|googlecast|google.?home|google.?nest|\bnest[\-_]?(hub|mini|audio|cam|wifi|thermostat|doorbell|protect)\b|\bpixel\b", "Google"),
    (r"\becho\b|echo[\-_]?(dot|show|studio|plus|pop)|\balexa\b|fire.?tv|fire.?stick|fire.?hd|\bkindle\b|\beero\b|\bamazon\b", "Amazon"),
    (r"\biphone\b|\bipad\b|\bipod\b|macbook|\bimac\b|mac.?mini|mac.?pro|apple.?tv|homepod|airport.?(express|extreme)", "Apple"),
    (r"raspberrypi|raspberry[\-_]?pi|\brpi\d*\b", "Raspberry Pi"),
    (r"\bgalaxy\b|\bsm-[a-z]\d{2,}|smartthings|\bsamsung\b", "Samsung"),
    (r"playstation|\bps[45]\b|\bbravia\b", "Sony"),
    (r"\bxbox\b", "Microsoft"),
    (r"nintendo|\bwii\b|switch[\-_]?(oled|lite)", "Nintendo"),
    (r"\bshield[\-_]?tv\b|\bnvidia\b", "NVIDIA"),
    (r"\bsonos\b", "Sonos"),
    (r"\broku\b", "Roku"),
    (r"\bdeco\b|\btapo\b|\bkasa\b|tp.?link", "TP-Link"),
    (r"\borbi\b|netgear", "Netgear"),
    (r"synology|diskstation", "Synology"),
    (r"\bqnap\b", "QNAP"),
    (r"\bhue\b|hue.?bridge|philips", "Philips"),
    (r"\bshelly", "Shelly"),
    (r"\becobee\b", "ecobee"),
    (r"\bsonoff\b", "Sonoff"),
    (r"\bunifi\b|ubiquiti|\budm\b", "Ubiquiti"),
    (r"\bfritz\b|fritz.?box", "AVM"),
]

_HOSTNAME_VENDOR_RES: list[tuple] = [
    (re.compile(pattern, re.IGNORECASE), vendor)
    for pattern, vendor in _HOSTNAME_VENDOR
]


def vendor_from_hostname(hostname: str) -> str:
    """Return the vendor an unambiguous product name in *hostname* implies.

    Returns "" when nothing matches — including for OS names, which say what a
    device runs rather than who built it. This is weaker evidence than an OUI
    and callers should treat it as such: use it only when OUI lookup produced
    nothing, and never to overwrite a vendor a real OUI supplied.
    """
    if not hostname or not hostname.strip():
        return ""
    for pattern, vendor in _HOSTNAME_VENDOR_RES:
        if pattern.search(hostname):
            return vendor
    return ""
