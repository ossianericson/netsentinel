"""
Device-type classification rules — the _RULES table only.

Split out of device_classifier.py to keep that module inside the RULE-AH1 780-line
budget; the split this file performs is the one tests/test_module_loc.py has named
as the intended one for device_classifier.py since the 600 -> 780 raise.

Pure data. No logic lives here: device_classifier.py owns rule EVALUATION, this
file owns the rule TABLE, so a new device signature is a one-entry data edit that
never touches scoring.
"""

from __future__ import annotations

from modules.device_types import (
    TYPE_SMART_BULB,
    TYPE_SMART_PLUG,
    TYPE_SMART_SPEAKER,
    TYPE_SMART_THERMOSTAT,
)

# This file is pure data, so _RULES is read only by its importer
# (device_classifier.py) and never in its own module. CodeQL's
# py/unused-global-variable counts a cross-file import as no use at all and
# names __all__ as the way to declare the export deliberate (RULE-LINT6).
__all__ = ["_RULES"]



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
        # Anchored: unanchored "ad-" matched "iPad-2", "Brad-PC", "Vlad-PC" and
        # "Chad-Desktop", and an unanchored "dc" matches inside any word.
        "label": "Domain Controller",
        "hostname_re": r"\bdc\d*\b|domaincontroller|\bad[-_]|\bldap\b",
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
        # Anchored: unanchored "nas" matched "Jonas" and "Nasrin". The negative
        # lookahead keeps "nas1"/"nas-01" working while rejecting "nasrin" --
        # a plain \b would also reject "nas1", since a digit is a word char.
        "label": "File / NAS Server",
        "hostname_re": r"\bnas(?![a-z])|diskstation|readynas|mycloud",
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
        # The rule had no hostname pattern at all, so a device literally named
        # "office-printer" classified as Unknown Device unless a print port was
        # open or its vendor happened to match. None of these collide with a
        # person's name.
        "label": "Print Server",
        "hostname_re": r"printer|laserjet|officejet|deskjet|\bmfp\b|print[-_]?srv",
    },
    {
        # Printer companies: on a LAN, a device carrying one of these OUIs is a
        # printer. "hp|hewlett.packard" was here too, which made every HP laptop
        # and server a Print Server -- HP's LAN presence is mostly not printers,
        # unlike Brother or Lexmark. HP needs corroboration; see the rule below.
        "label": "Print Server",
        "vendor_re": r"brother|canon|epson|lexmark|ricoh|xerox|kyocera|konica|sharp",
    },
    {
        "label": "Print Server",
        "vendor_re": r"hp|hewlett.packard",
        "any_ports": {631, 9100},
    },
    {
        "label": "Print Server",
        "vendor_re": r"hp|hewlett.packard",
        "hostname_re": r"printer|laserjet|officejet|deskjet|\bmfp\b",
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
        # Anchored: unanchored "cam" matched "Camilla". "camera"/"ipcam" stay
        # unanchored -- they are long enough not to collide.
        "label": "IP Camera",
        "hostname_re": r"\bcam(?![a-z])|camera|ipcam|\bdvr\b|\bnvr\b|cctv",
    },
    # ── Nest device disambiguation ─────────────────────────────────────────────
    # These rules must precede the Video Doorbell rule.  Without them, any
    # device with vendor="Nest Labs" (Hub, Thermostat, Audio) would be
    # misclassified as a Video Doorbell by the first-match rule below.
    {
        "label": "Smart Home Hub / Display",
        "vendor_re": r"nest",
        "hostname_re": r"nest[\-_]?(hub|display|audio|mini)",
    },
    {
        "label": "Smart Thermostat",
        "vendor_re": r"nest",
        "any_ports": {9543},
    },
    {
        "label": "Smart Thermostat",
        "vendor_re": r"nest",
        "hostname_re": r"nest[\-_]?(thermostat|therm)",
    },
    # Nest Doorbell / Cam requires a video-streaming port to be confirmed.
    # Port 9543 is the Nest local API (thermostat); 554/8443 are video streams.
    {
        "label": "Video Doorbell / Intercom",
        "vendor_re": r"nest",
        "any_ports": {554, 8443},
    },
    {
        "label": "Video Doorbell / Intercom",
        "vendor_re": r"ring|arlo|doorbird|aiphone|2n",
    },
    # ── Smart Plugs ──────────────────────────────────────────────────────────
    # Allterco Robotics manufactures the Shelly family (plugs, relays, dimmers).
    {
        "label": TYPE_SMART_PLUG,
        "vendor_re": r"allterco",
    },
    {
        "label": TYPE_SMART_PLUG,
        "hostname_re": r"shellyplug|shelly1pm|shelly2pm|shelly[\-_]?em|shelly[\-_]?plug",
    },
    # TP-Link smart plugs (Kasa/Tapo) share the tp-link OUI with routers.
    # Port 9999 is the Kasa local-control API — not open on routers.
    {
        "label": TYPE_SMART_PLUG,
        "vendor_re": r"tp.?link|kasa",
        "any_ports": {9999},
    },
    {
        "label": TYPE_SMART_PLUG,
        "hostname_re": r"kasa[\-_]?plug|hs1\d{2}|ep\d{2,3}|kp\d{2,3}",
    },
    # ── Smart Bulbs ──────────────────────────────────────────────────────────
    {
        "label": TYPE_SMART_BULB,
        "vendor_re": r"lifx",
    },
    {
        "label": TYPE_SMART_BULB,
        "vendor_re": r"govee",
    },
    {
        "label": TYPE_SMART_BULB,
        "hostname_re": r"shellydimmer|shellyrgbw|shellyflood|shelly[\-_]?bulb",
    },
    # ── Smart Thermostats ────────────────────────────────────────────────────
    {
        "label": TYPE_SMART_THERMOSTAT,
        "vendor_re": r"ecobee",
    },
    {
        "label": TYPE_SMART_THERMOSTAT,
        "hostname_re": r"ecobee",
    },
    {
        "label": TYPE_SMART_THERMOSTAT,
        "vendor_re": r"tado",
    },
    {
        "label": TYPE_SMART_THERMOSTAT,
        "hostname_re": r"tado[\-_\.]",
    },
    # Honeywell thermostat disambiguation: must precede the Industrial / ICS
    # vendor rule which matches "honeywell" with no other discriminator.
    {
        "label": TYPE_SMART_THERMOSTAT,
        "vendor_re": r"honeywell",
        "hostname_re": r"tcc[\-_]?\d|hz[\-_]?therm|th\d{4}|lyric|evohome|t[6-9]\d{3}[\-_]",
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
        "label": TYPE_SMART_SPEAKER,
        "vendor_re": r"amazon|google|bose|harman|jbl|anker soundcore",
        "hostname_re": r"echo|alexa|nest|chromecast|home.?pod|google.?home",
    },
    {
        "label": TYPE_SMART_SPEAKER,
        "hostname_re": r"echo|alexa|chromecast|homepod",
    },
    {
        # Anchored: unanchored "tv" matched "natverk-printer" (Swedish for
        # "network"), and because rules are first-match-wins that also pre-empted
        # the Print Server rule further down the list.
        "label": "Smart TV",
        "vendor_re": r"samsung|lg|sony|tcl|hisense|vizio|panasonic|philips|roku|tivo|nvidia",
        "hostname_re": r"\btv(?![a-z])|smarttv|roku|firetv|appletv|shield",
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
        # Frontier Silicon makes the internet-radio / streaming-audio modules
        # inside other brands' speakers (Philips, Roberts, Pure, Hama), so the
        # IEEE vendor is the module maker and never the brand on the box. The
        # module only ever ships in audio products, which makes it a reliable
        # signal for the one thing this rule claims.
        "label": "Smart Speaker / Audio",
        "vendor_re": r"frontier silicon",
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
    # ── Wearables ─────────────────────────────────────────────────────────────
    {
        "label": "Wearable",
        "vendor_re": r"garmin|fitbit|polar electro|whoop|oura|suunto",
    },
    # ── Fallback by OS ────────────────────────────────────────────────────────
    {
        "label": "Network Device",
        "os_re": r"network device|router|switch",
    },
    # ── Generic computer, by NIC vendor ───────────────────────────────────────
    # LAST in the list deliberately: this fills the gap where nothing more
    # specific matched, and must never pre-empt a hostname or port rule above.
    #
    # The most common device class on any network had no classification path at
    # all -- "Windows PC" needs os_re "windows" AND ports {445,3389,5900}, none
    # of which a passive scan has, so Intel/Dell/Lenovo NICs all came back
    # Unknown Device at confidence 0.0.
    #
    # Membership is the point, not the convenience: every vendor here puts its
    # OUI on client NICs and does NOT sell consumer routers, so the vendor alone
    # really is evidence of a computer. ASUSTek is deliberately absent -- it
    # sells motherboards and some of the most common home routers on the same
    # OUIs, so the vendor proves nothing about which. HP is absent for the same
    # reason (laptops, printers and servers).
    {
        "label": "Computer / Workstation",
        "vendor_re": r"\bdell\b|\blenovo\b|intel corporate|micro-star|giga-?byte|"
                     r"\bclevo\b|\btoshiba\b|\bfujitsu\b|framework computer",
    },
]
