"""
MAC OUI Registry — maps 6-char OUI prefixes to specific vendor, product line,
and device-type labels.

Much more granular than a pure OUI→vendor lookup: where possible a specific
OUI is tied to a known product (e.g. "Google Chromecast 3rd Gen" rather than
just "Google LLC").

Usage::

    from modules.mac_registry import lookup

    info = lookup("f4:f5:d8:ab:cd:ef")
    # {"vendor": "Google", "model": "Google Nest Wifi Router",
    #  "device_type": "Router / Gateway", "product_line": "Google Nest"}

Returns an empty dict when the OUI is not in the registry (caller should fall
back to the offenders.json vendor string or raw OUI lookup).
"""

from __future__ import annotations

import re as _re
from typing import Dict

# Key  : lowercase 8-char OUI  "xx:xx:xx"
# Value: dict with vendor / model / device_type / product_line
_OUI_REGISTRY: Dict[str, Dict[str, str]] = {}

# ─────────────────────────────────────────────────────────────────────────────
# GOOGLE
# ─────────────────────────────────────────────────────────────────────────────
_GOOGLE: Dict[str, Dict[str, str]] = {
    # Chromecast (1st / 2nd gen, Ultra, Audio)
    "54:60:09": {"vendor": "Google", "model": "Chromecast (1st/2nd Gen)", "device_type": "Streaming Stick", "product_line": "Chromecast"},
    "a4:77:33": {"vendor": "Google", "model": "Chromecast / Chromecast Ultra", "device_type": "Streaming Stick", "product_line": "Chromecast"},

    # Google Home / Nest Audio / Nest Mini
    "b0:87:c1": {"vendor": "Google", "model": "Google Home (1st Gen)", "device_type": "Smart Speaker", "product_line": "Google Home"},
    "f4:f5:d8": {"vendor": "Google", "model": "Google Home / Nest Audio", "device_type": "Smart Speaker", "product_line": "Google Home"},
    "48:d6:d5": {"vendor": "Google", "model": "Google Home Mini / Nest Mini", "device_type": "Smart Speaker", "product_line": "Google Home"},
    "f0:ef:86": {"vendor": "Google", "model": "Nest Mini (2nd Gen)", "device_type": "Smart Speaker", "product_line": "Google Home"},
    "54:f5:55": {"vendor": "Google", "model": "Nest Audio", "device_type": "Smart Speaker", "product_line": "Google Home"},

    # Google Nest Hub / Hub Max
    "3c:5a:b4": {"vendor": "Google", "model": "Google Nest Hub / Hub Max", "device_type": "Smart Display", "product_line": "Google Nest"},
    "e8:aa:7a": {"vendor": "Google", "model": "Google Nest Hub (2nd Gen)", "device_type": "Smart Display", "product_line": "Google Nest"},
    "94:eb:2c": {"vendor": "Google", "model": "Google Nest Hub", "device_type": "Smart Display", "product_line": "Google Nest"},

    # Google Nest Wifi / Google Wifi (router role)
    "64:16:66": {"vendor": "Google / Nest Labs", "model": "Google Nest Wifi Point (AP)", "device_type": "Wireless Access Point", "product_line": "Google Nest Wifi"},
    "30:fd:38": {"vendor": "Google", "model": "Google Nest Wifi Point", "device_type": "Wireless Access Point", "product_line": "Google Nest Wifi"},
    "18:b4:30": {"vendor": "Google / Nest Labs", "model": "Nest Learning Thermostat", "device_type": "Smart Thermostat", "product_line": "Google Nest"},
    "00:1a:11": {"vendor": "Google", "model": "Google Device", "device_type": "IoT Device", "product_line": "Google"},
    "9c:28:b4": {"vendor": "Google", "model": "Google Nest Cam", "device_type": "IP Camera", "product_line": "Google Nest"},
    # Multi-product OUI: claims vendor and product line, but NOT a device_type.
    # An OUI is assigned to an organisation, not a product, and Google reuses
    # this one across the Nest range. It was entered as "Google Nest Doorbell"
    # -> Video Doorbell at 0.90, which outranks every other source, so the
    # reference network's Nest Wifi router rendered as a Video Doorbell
    # (owner-confirmed). A wrong specific label is worse than none: with no
    # device_type here the arbiter falls through to whatever real evidence the
    # scan found.
    # device_type is deliberately "" rather than absent: every entry carries the
    # same four keys, and "" is falsy, so consumers' existing
    # `reg.get("device_type", "") or <fallback>` already do the right thing.
    "f0:72:ea": {"vendor": "Google", "model": "Google Nest device", "device_type": "", "product_line": "Google Nest"},
    "1c:f2:9a": {"vendor": "Google", "model": "Google Pixel Phone", "device_type": "Android Device", "product_line": "Google Pixel"},
    "20:df:b9": {"vendor": "Google", "model": "Google Pixel Phone", "device_type": "Android Device", "product_line": "Google Pixel"},
    "d4:f5:47": {"vendor": "Google", "model": "Google Nest (generic)", "device_type": "Smart Home Hub", "product_line": "Google Nest"},
    "08:9e:08": {"vendor": "Google", "model": "Google Nest (generic)", "device_type": "IoT Device", "product_line": "Google Nest"},
    "e4:f0:42": {"vendor": "Google", "model": "Google Device", "device_type": "IoT Device", "product_line": "Google"},
    "7c:2e:bd": {"vendor": "Google", "model": "Google Device", "device_type": "IoT Device", "product_line": "Google"},
    "f8:8f:ca": {"vendor": "Google", "model": "Google Device", "device_type": "IoT Device", "product_line": "Google"},
    # Additional Chromecast / Cast-enabled device OUIs
    "b8:7b:d4": {"vendor": "Google", "model": "Chromecast / Google TV", "device_type": "Streaming Stick", "product_line": "Chromecast"},
    "88:3d:24": {"vendor": "Google", "model": "Chromecast (2nd Gen / Audio)", "device_type": "Streaming Stick", "product_line": "Chromecast"},
    "dc:28:a8": {"vendor": "Google", "model": "Chromecast / Google Device", "device_type": "Streaming Stick", "product_line": "Chromecast"},
}

# ─────────────────────────────────────────────────────────────────────────────
# TP-LINK
# ─────────────────────────────────────────────────────────────────────────────
_TPLINK: Dict[str, Dict[str, str]] = {
    # Deco mesh
    "50:c7:bf": {"vendor": "TP-Link", "model": "Deco Mesh Node", "device_type": "Mesh Network Node", "product_line": "Deco"},
    "60:32:b1": {"vendor": "TP-Link", "model": "Deco M4 / M5", "device_type": "Mesh Network Node", "product_line": "Deco"},
    "c0:4a:00": {"vendor": "TP-Link", "model": "Deco E4 / BE Series", "device_type": "Mesh Network Node", "product_line": "Deco"},
    "3c:64:cf": {"vendor": "TP-Link", "model": "Deco XE Series (WiFi 6E)", "device_type": "Mesh Network Node", "product_line": "Deco"},
    "60:83:e7": {"vendor": "TP-Link", "model": "Deco Series", "device_type": "Mesh Network Node", "product_line": "Deco"},
    "d8:0d:17": {"vendor": "TP-Link", "model": "Deco Series", "device_type": "Mesh Network Node", "product_line": "Deco"},

    # Archer routers
    "ec:08:6b": {"vendor": "TP-Link", "model": "Archer Router", "device_type": "Router / Gateway", "product_line": "Archer"},
    "10:27:f5": {"vendor": "TP-Link", "model": "Archer C / AX Series Router", "device_type": "Router / Gateway", "product_line": "Archer"},
    "b0:be:76": {"vendor": "TP-Link", "model": "Archer AX Series Router", "device_type": "Router / Gateway", "product_line": "Archer"},
    "90:f6:52": {"vendor": "TP-Link", "model": "Archer Router", "device_type": "Router / Gateway", "product_line": "Archer"},
    "80:8f:1d": {"vendor": "TP-Link", "model": "Archer Router", "device_type": "Router / Gateway", "product_line": "Archer"},
    "00:27:19": {"vendor": "TP-Link", "model": "TP-Link Router / AP", "device_type": "Router / Gateway", "product_line": "TP-Link"},
    "14:cc:20": {"vendor": "TP-Link", "model": "TP-Link Router / AP", "device_type": "Router / Gateway", "product_line": "TP-Link"},
    "b0:4e:26": {"vendor": "TP-Link", "model": "TP-Link Router", "device_type": "Router / Gateway", "product_line": "TP-Link"},
    "54:af:97": {"vendor": "TP-Link", "model": "TP-Link Router", "device_type": "Router / Gateway", "product_line": "TP-Link"},

    # TL-SG / TL-SF managed switches
    "50:3e:aa": {"vendor": "TP-Link", "model": "TL-SG / TL-SF Switch", "device_type": "Network Switch", "product_line": "TL-SG"},
    "ac:84:c6": {"vendor": "TP-Link", "model": "TL-SG1005 / SG108 Switch", "device_type": "Network Switch", "product_line": "TL-SG"},
    "f8:d1:11": {"vendor": "TP-Link", "model": "TP-Link Switch", "device_type": "Network Switch", "product_line": "TP-Link"},

    # Tapo cameras / smart plugs
    "30:de:4b": {"vendor": "TP-Link", "model": "Tapo Camera / Smart Device", "device_type": "IP Camera", "product_line": "Tapo"},
    "9c:a2:f4": {"vendor": "TP-Link", "model": "Tapo Smart Plug / Camera", "device_type": "IoT Device", "product_line": "Tapo"},
    "fc:ec:da": {"vendor": "TP-Link / Ubiquiti", "model": "Tapo / UniFi Device", "device_type": "IoT Device", "product_line": "Tapo"},

    # RE extenders
    "18:d6:c7": {"vendor": "TP-Link", "model": "RE Range Extender", "device_type": "Wireless Access Point", "product_line": "RE Extender"},
    "f4:ec:38": {"vendor": "TP-Link", "model": "RE Range Extender", "device_type": "Wireless Access Point", "product_line": "RE Extender"},
}

_OUI_REGISTRY.update(_GOOGLE)
_OUI_REGISTRY.update(_TPLINK)

# ─────────────────────────────────────────────────────────────────────────────
# APPLE
# ─────────────────────────────────────────────────────────────────────────────
_APPLE: Dict[str, Dict[str, str]] = {
    "00:17:f2": {"vendor": "Apple", "model": "AirPort Extreme (2007)", "device_type": "Router / Gateway", "product_line": "AirPort"},
    "00:1f:f3": {"vendor": "Apple", "model": "AirPort Express (1st/2nd Gen)", "device_type": "Wireless Access Point", "product_line": "AirPort"},
    "00:25:bc": {"vendor": "Apple", "model": "AirPort Time Capsule", "device_type": "File / NAS Server", "product_line": "AirPort"},
    "00:26:08": {"vendor": "Apple", "model": "AirPort Extreme", "device_type": "Router / Gateway", "product_line": "AirPort"},
    "00:23:12": {"vendor": "Apple", "model": "AirPort Express", "device_type": "Wireless Access Point", "product_line": "AirPort"},
    "68:9c:70": {"vendor": "Apple", "model": "Apple TV / HomePod", "device_type": "Smart Speaker / Display", "product_line": "Apple TV"},
    "2c:f0:a2": {"vendor": "Apple", "model": "Apple TV (3rd/4th Gen)", "device_type": "Streaming Stick", "product_line": "Apple TV"},
    "ac:3c:0b": {"vendor": "Apple", "model": "Apple TV HD / 4K", "device_type": "Streaming Stick", "product_line": "Apple TV"},
    "f0:d1:a9": {"vendor": "Apple", "model": "HomePod (1st Gen)", "device_type": "Smart Speaker", "product_line": "HomePod"},
    "28:6a:b8": {"vendor": "Apple", "model": "HomePod mini", "device_type": "Smart Speaker", "product_line": "HomePod"},
    "04:f7:e4": {"vendor": "Apple", "model": "HomePod / Apple TV", "device_type": "Smart Speaker", "product_line": "HomePod"},
    "7c:6d:62": {"vendor": "Apple", "model": "iPhone / iPad", "device_type": "iPhone / iPad", "product_line": "iOS Device"},
    "a8:66:7f": {"vendor": "Apple", "model": "iPhone / MacBook", "device_type": "iPhone / iPad", "product_line": "iOS Device"},
    "8c:85:90": {"vendor": "Apple", "model": "MacBook Air / Pro", "device_type": "macOS Device", "product_line": "Mac"},
    "a4:5e:60": {"vendor": "Apple", "model": "iPhone", "device_type": "iPhone / iPad", "product_line": "iOS Device"},
    "18:9e:fc": {"vendor": "Apple", "model": "iPhone / iPad", "device_type": "iPhone / iPad", "product_line": "iOS Device"},
    "dc:2b:61": {"vendor": "Apple", "model": "iPhone", "device_type": "iPhone / iPad", "product_line": "iOS Device"},
    "f0:b4:79": {"vendor": "Apple", "model": "iPad", "device_type": "iPhone / iPad", "product_line": "iOS Device"},
    "38:f9:d3": {"vendor": "Apple", "model": "MacBook Pro / Air", "device_type": "macOS Device", "product_line": "Mac"},
    "14:98:77": {"vendor": "Apple", "model": "Mac Mini / iMac", "device_type": "macOS Device", "product_line": "Mac"},
    "a8:20:66": {"vendor": "Apple", "model": "Apple Watch", "device_type": "Wearable", "product_line": "Apple Watch"},
}

# ─────────────────────────────────────────────────────────────────────────────
# AMAZON
# ─────────────────────────────────────────────────────────────────────────────
_AMAZON: Dict[str, Dict[str, str]] = {
    "00:fc:8b": {"vendor": "Amazon", "model": "Echo Dot (3rd/4th Gen)", "device_type": "Smart Speaker", "product_line": "Echo"},
    "34:d2:70": {"vendor": "Amazon", "model": "Echo Show / Echo Plus", "device_type": "Smart Display", "product_line": "Echo"},
    "4c:ef:c0": {"vendor": "Amazon", "model": "Echo (2nd/3rd Gen)", "device_type": "Smart Speaker", "product_line": "Echo"},
    "68:37:e9": {"vendor": "Amazon", "model": "Fire TV Stick", "device_type": "Streaming Stick", "product_line": "Fire TV"},
    "b4:7c:9c": {"vendor": "Amazon", "model": "Kindle / Fire Tablet", "device_type": "Tablet", "product_line": "Kindle / Fire"},
    "f0:27:2d": {"vendor": "Amazon", "model": "Ring Alarm / Device", "device_type": "Security Device", "product_line": "Ring"},
    "74:c2:46": {"vendor": "Amazon", "model": "Ring Camera / Doorbell", "device_type": "IP Camera", "product_line": "Ring"},
    "44:65:0d": {"vendor": "Amazon", "model": "Eero Router (Mesh)", "device_type": "Router / Gateway", "product_line": "Eero"},
    "f0:81:73": {"vendor": "Amazon", "model": "Eero Mesh Node", "device_type": "Mesh Network Node", "product_line": "Eero"},
    "fc:65:de": {"vendor": "Amazon", "model": "Eero 6 / Pro", "device_type": "Mesh Network Node", "product_line": "Eero"},
    "fc:a6:67": {"vendor": "Amazon", "model": "Echo Studio / Echo 4th Gen", "device_type": "Smart Speaker", "product_line": "Echo"},
    "40:b4:cd": {"vendor": "Amazon", "model": "Echo / Fire Device", "device_type": "Smart Speaker", "product_line": "Echo"},
}

_OUI_REGISTRY.update(_APPLE)
_OUI_REGISTRY.update(_AMAZON)

# ─────────────────────────────────────────────────────────────────────────────
# SAMSUNG
# ─────────────────────────────────────────────────────────────────────────────
_SAMSUNG: Dict[str, Dict[str, str]] = {
    # Smart TVs — Tizen, QLED, OLED, The Frame
    "8c:77:12": {"vendor": "Samsung", "model": "Samsung Smart TV", "device_type": "Smart TV", "product_line": "Samsung TV"},
    "18:89:5b": {"vendor": "Samsung", "model": "Samsung Smart TV", "device_type": "Smart TV", "product_line": "Samsung TV"},
    "f4:7b:5e": {"vendor": "Samsung", "model": "Samsung Smart TV (QLED)", "device_type": "Smart TV", "product_line": "Samsung QLED"},
    "00:12:fb": {"vendor": "Samsung", "model": "Samsung Smart TV", "device_type": "Smart TV", "product_line": "Samsung TV"},
    "78:1f:db": {"vendor": "Samsung", "model": "Samsung QLED / The Frame TV", "device_type": "Smart TV", "product_line": "Samsung QLED"},
    "50:85:69": {"vendor": "Samsung", "model": "Samsung Smart TV (Tizen)", "device_type": "Smart TV", "product_line": "Samsung TV"},
    "8c:c8:f4": {"vendor": "Samsung", "model": "Samsung Smart TV", "device_type": "Smart TV", "product_line": "Samsung TV"},
    "b0:c4:e7": {"vendor": "Samsung", "model": "Samsung OLED / MicroLED TV", "device_type": "Smart TV", "product_line": "Samsung TV"},
    # Galaxy phones — S / A / Z Series
    "78:bd:bc": {"vendor": "Samsung", "model": "Samsung Galaxy S/A Series", "device_type": "Android Device", "product_line": "Galaxy"},
    "8c:f5:a3": {"vendor": "Samsung", "model": "Samsung Galaxy Phone", "device_type": "Android Device", "product_line": "Galaxy"},
    "48:44:f7": {"vendor": "Samsung", "model": "Samsung Galaxy S Series", "device_type": "Android Device", "product_line": "Galaxy"},
    "e8:03:9a": {"vendor": "Samsung", "model": "Samsung Galaxy / SmartThings", "device_type": "Android Device", "product_line": "Galaxy"},
    "40:0e:85": {"vendor": "Samsung", "model": "Samsung Galaxy Phone", "device_type": "Android Device", "product_line": "Galaxy"},
    "08:08:c2": {"vendor": "Samsung", "model": "Samsung Galaxy Z Fold / Flip", "device_type": "Android Device", "product_line": "Galaxy Z"},
    "a0:b4:c8": {"vendor": "Samsung", "model": "Samsung Galaxy A Series", "device_type": "Android Device", "product_line": "Galaxy"},
    # Tablets
    "cc:07:ab": {"vendor": "Samsung", "model": "Samsung Galaxy Tab", "device_type": "Tablet", "product_line": "Galaxy Tab"},
    "f0:25:b7": {"vendor": "Samsung", "model": "Samsung Galaxy Tab S", "device_type": "Tablet", "product_line": "Galaxy Tab"},
    # SmartThings Hub
    "f8:04:2e": {"vendor": "Samsung", "model": "Samsung SmartThings Hub", "device_type": "Smart Home Hub", "product_line": "SmartThings"},
    "34:14:5f": {"vendor": "Samsung", "model": "Samsung SmartThings v2/v3", "device_type": "Smart Home Hub", "product_line": "SmartThings"},
    # Additional Samsung OUIs
    "4c:c9:5e": {"vendor": "Samsung", "model": "Samsung Smart TV / Device", "device_type": "Smart TV", "product_line": "Samsung TV"},
    "7c:64:56": {"vendor": "Samsung", "model": "Samsung Smart TV (QLED)", "device_type": "Smart TV", "product_line": "Samsung QLED"},
    "00:26:37": {"vendor": "Samsung", "model": "Samsung Device", "device_type": "Android Device", "product_line": "Samsung"},
    "84:25:db": {"vendor": "Samsung", "model": "Samsung Galaxy Phone", "device_type": "Android Device", "product_line": "Galaxy"},
    "50:32:75": {"vendor": "Samsung", "model": "Samsung Galaxy Phone", "device_type": "Android Device", "product_line": "Galaxy"},
}

# ─────────────────────────────────────────────────────────────────────────────
# NETGEAR
# ─────────────────────────────────────────────────────────────────────────────
_NETGEAR: Dict[str, Dict[str, str]] = {
    "00:1e:2a": {"vendor": "Netgear", "model": "Netgear Router / AP", "device_type": "Router / Gateway", "product_line": "Netgear"},
    "28:c6:8e": {"vendor": "Netgear", "model": "Nighthawk Router", "device_type": "Router / Gateway", "product_line": "Nighthawk"},
    "84:1b:5e": {"vendor": "Netgear", "model": "Orbi Satellite", "device_type": "Mesh Network Node", "product_line": "Orbi"},
    "a0:04:60": {"vendor": "Netgear", "model": "Orbi Router", "device_type": "Router / Gateway", "product_line": "Orbi"},
    "20:0c:c8": {"vendor": "Netgear", "model": "Netgear Router / Switch", "device_type": "Router / Gateway", "product_line": "Netgear"},
    "4c:60:de": {"vendor": "Netgear", "model": "Orbi WiFi 6 / Pro", "device_type": "Mesh Network Node", "product_line": "Orbi"},
    "9c:3d:cf": {"vendor": "Netgear", "model": "Netgear Switch / AP", "device_type": "Network Switch", "product_line": "Netgear"},
    "00:14:6c": {"vendor": "Netgear", "model": "Netgear Router (legacy)", "device_type": "Router / Gateway", "product_line": "Netgear"},
    "00:26:f2": {"vendor": "Netgear", "model": "Netgear Router", "device_type": "Router / Gateway", "product_line": "Netgear"},
    "44:94:fc": {"vendor": "Netgear", "model": "Netgear Managed Switch", "device_type": "Network Switch", "product_line": "Netgear"},
}

# ─────────────────────────────────────────────────────────────────────────────
# ASUS
# ─────────────────────────────────────────────────────────────────────────────
_ASUS: Dict[str, Dict[str, str]] = {
    "04:d9:f5": {"vendor": "Asus", "model": "ASUS RT Router", "device_type": "Router / Gateway", "product_line": "RT Series"},
    "08:60:6e": {"vendor": "Asus", "model": "ASUS Router / ZenWifi", "device_type": "Router / Gateway", "product_line": "ZenWifi"},
    "10:7b:44": {"vendor": "Asus", "model": "ASUS ZenWifi AX / AC", "device_type": "Mesh Network Node", "product_line": "ZenWifi"},
    "2c:4d:54": {"vendor": "Asus", "model": "ASUS RT-AX Series", "device_type": "Router / Gateway", "product_line": "RT Series"},
    "50:46:5d": {"vendor": "Asus", "model": "ASUS Router / PC NIC", "device_type": "Router / Gateway", "product_line": "Asus"},
    "70:4d:7b": {"vendor": "Asus", "model": "ASUS Router", "device_type": "Router / Gateway", "product_line": "RT Series"},
    "ac:9e:17": {"vendor": "Asus", "model": "ASUS RT-N / RT-AC Router", "device_type": "Router / Gateway", "product_line": "RT Series"},
    "f8:32:e4": {"vendor": "Asus", "model": "ASUS Router / NIC", "device_type": "Router / Gateway", "product_line": "Asus"},
}

_OUI_REGISTRY.update(_SAMSUNG)
_OUI_REGISTRY.update(_NETGEAR)
_OUI_REGISTRY.update(_ASUS)

# ─────────────────────────────────────────────────────────────────────────────
# LG ELECTRONICS
# ─────────────────────────────────────────────────────────────────────────────
_LG: Dict[str, Dict[str, str]] = {
    # Smart TVs — OLED, NanoCell, QNED, webOS
    "00:1e:75": {"vendor": "LG", "model": "LG Smart TV", "device_type": "Smart TV", "product_line": "LG TV"},
    "64:99:5d": {"vendor": "LG", "model": "LG Smart TV (webOS)", "device_type": "Smart TV", "product_line": "LG TV"},
    "c4:36:6c": {"vendor": "LG", "model": "LG OLED / NanoCell TV", "device_type": "Smart TV", "product_line": "LG OLED"},
    "10:68:3f": {"vendor": "LG", "model": "LG Smart TV (webOS)", "device_type": "Smart TV", "product_line": "LG TV"},
    "bc:f5:ac": {"vendor": "LG", "model": "LG Smart TV", "device_type": "Smart TV", "product_line": "LG TV"},
    "78:5d:c8": {"vendor": "LG", "model": "LG Smart TV", "device_type": "Smart TV", "product_line": "LG TV"},
    "a8:23:fe": {"vendor": "LG", "model": "LG Smart TV (webOS)", "device_type": "Smart TV", "product_line": "LG TV"},
    "00:1f:6b": {"vendor": "LG", "model": "LG TV / Monitor", "device_type": "Smart TV", "product_line": "LG TV"},
    "00:26:e2": {"vendor": "LG", "model": "LG Device", "device_type": "Smart TV", "product_line": "LG TV"},
    # LG phones (V / G Series)
    "e8:92:a4": {"vendor": "LG", "model": "LG G / V Series Phone", "device_type": "Android Device", "product_line": "LG Phone"},
}

# ─────────────────────────────────────────────────────────────────────────────
# SONY — Bravia TVs
# ─────────────────────────────────────────────────────────────────────────────
_SONY_TV: Dict[str, Dict[str, str]] = {
    "f8:d0:ac": {"vendor": "Sony", "model": "Sony Bravia TV", "device_type": "Smart TV", "product_line": "Bravia"},
    "ac:9b:0a": {"vendor": "Sony", "model": "Sony Bravia / OLED TV", "device_type": "Smart TV", "product_line": "Bravia"},
    "d8:d4:3c": {"vendor": "Sony", "model": "Sony Bravia TV", "device_type": "Smart TV", "product_line": "Bravia"},
    "00:01:4a": {"vendor": "Sony", "model": "Sony Device (legacy)", "device_type": "Smart TV", "product_line": "Sony"},
    "f0:bf:97": {"vendor": "Sony", "model": "Sony Bravia TV", "device_type": "Smart TV", "product_line": "Bravia"},
    "fc:0f:e6": {"vendor": "Sony", "model": "Sony Bravia / Home Theatre", "device_type": "Smart TV", "product_line": "Bravia"},
}

# ─────────────────────────────────────────────────────────────────────────────
# SONY INTERACTIVE ENTERTAINMENT — PlayStation
# ─────────────────────────────────────────────────────────────────────────────
_PLAYSTATION: Dict[str, Dict[str, str]] = {
    "00:04:1f": {"vendor": "Sony", "model": "PlayStation 2 / 3 (legacy)", "device_type": "Games Console", "product_line": "PlayStation"},
    "00:13:15": {"vendor": "Sony", "model": "PlayStation Portable (PSP)", "device_type": "Games Console", "product_line": "PlayStation"},
    "00:1d:0d": {"vendor": "Sony", "model": "PlayStation 3", "device_type": "Games Console", "product_line": "PlayStation"},
    "00:15:c1": {"vendor": "Sony", "model": "PlayStation 3", "device_type": "Games Console", "product_line": "PlayStation"},
    "70:9e:29": {"vendor": "Sony Interactive Entertainment", "model": "PlayStation 4", "device_type": "Games Console", "product_line": "PlayStation 4"},
    "a8:e3:ee": {"vendor": "Sony Interactive Entertainment", "model": "PlayStation 4 / PS4 Pro", "device_type": "Games Console", "product_line": "PlayStation 4"},
    "bc:60:a7": {"vendor": "Sony Interactive Entertainment", "model": "PlayStation 4 / PS4 Slim", "device_type": "Games Console", "product_line": "PlayStation 4"},
    "28:3f:69": {"vendor": "Sony Interactive Entertainment", "model": "PlayStation 4 Pro", "device_type": "Games Console", "product_line": "PlayStation 4"},
    "c8:63:f1": {"vendor": "Sony Interactive Entertainment", "model": "PlayStation 4 Slim", "device_type": "Games Console", "product_line": "PlayStation 4"},
    "0c:fe:45": {"vendor": "Sony Interactive Entertainment", "model": "PlayStation 5", "device_type": "Games Console", "product_line": "PlayStation 5"},
    "d4:4c:d6": {"vendor": "Sony Interactive Entertainment", "model": "PlayStation 5", "device_type": "Games Console", "product_line": "PlayStation 5"},
    "58:48:22": {"vendor": "Sony Interactive Entertainment", "model": "PlayStation 5 / PS5 Digital", "device_type": "Games Console", "product_line": "PlayStation 5"},
    "78:c8:81": {"vendor": "Sony Interactive Entertainment", "model": "PlayStation 4 / PS4 Pro", "device_type": "Games Console", "product_line": "PlayStation 4"},
    "f8:46:1c": {"vendor": "Sony Interactive Entertainment", "model": "PlayStation 4 Slim", "device_type": "Games Console", "product_line": "PlayStation 4"},
    "10:4f:a8": {"vendor": "Sony", "model": "PlayStation Vita", "device_type": "Games Console", "product_line": "PlayStation"},
    "00:1f:a7": {"vendor": "Sony", "model": "PlayStation 3 / Vita", "device_type": "Games Console", "product_line": "PlayStation"},
}

# ─────────────────────────────────────────────────────────────────────────────
# NINTENDO
# ─────────────────────────────────────────────────────────────────────────────
_NINTENDO: Dict[str, Dict[str, str]] = {
    "00:17:ab": {"vendor": "Nintendo", "model": "Nintendo DS / Wii", "device_type": "Games Console", "product_line": "Nintendo"},
    "00:1b:ea": {"vendor": "Nintendo", "model": "Nintendo Wii", "device_type": "Games Console", "product_line": "Nintendo"},
    "00:1f:32": {"vendor": "Nintendo", "model": "Nintendo DSi / Wii", "device_type": "Games Console", "product_line": "Nintendo"},
    "00:24:44": {"vendor": "Nintendo", "model": "Nintendo DSi", "device_type": "Games Console", "product_line": "Nintendo"},
    "98:b6:e9": {"vendor": "Nintendo", "model": "Nintendo 3DS / 2DS", "device_type": "Games Console", "product_line": "Nintendo 3DS"},
    "40:d2:8a": {"vendor": "Nintendo", "model": "Nintendo Switch", "device_type": "Games Console", "product_line": "Nintendo Switch"},
    "7c:bb:8a": {"vendor": "Nintendo", "model": "Nintendo Switch", "device_type": "Games Console", "product_line": "Nintendo Switch"},
    "b8:ae:6e": {"vendor": "Nintendo", "model": "Nintendo Switch (OLED)", "device_type": "Games Console", "product_line": "Nintendo Switch"},
    "78:a2:a0": {"vendor": "Nintendo", "model": "Nintendo Switch Lite", "device_type": "Games Console", "product_line": "Nintendo Switch"},
    "58:2f:40": {"vendor": "Nintendo", "model": "Nintendo Switch", "device_type": "Games Console", "product_line": "Nintendo Switch"},
    "e0:f6:b5": {"vendor": "Nintendo", "model": "Nintendo Switch 2", "device_type": "Games Console", "product_line": "Nintendo Switch"},
}

# ─────────────────────────────────────────────────────────────────────────────
# MICROSOFT — Xbox
# ─────────────────────────────────────────────────────────────────────────────
_XBOX: Dict[str, Dict[str, str]] = {
    "00:09:fa": {"vendor": "Microsoft", "model": "Xbox (Original)", "device_type": "Games Console", "product_line": "Xbox"},
    "00:17:fa": {"vendor": "Microsoft", "model": "Xbox 360", "device_type": "Games Console", "product_line": "Xbox 360"},
    "00:1d:d8": {"vendor": "Microsoft", "model": "Xbox 360", "device_type": "Games Console", "product_line": "Xbox 360"},
    "00:25:ae": {"vendor": "Microsoft", "model": "Xbox 360 (S/E)", "device_type": "Games Console", "product_line": "Xbox 360"},
    "28:18:78": {"vendor": "Microsoft", "model": "Xbox One", "device_type": "Games Console", "product_line": "Xbox One"},
    "7c:ed:8d": {"vendor": "Microsoft", "model": "Xbox One / Series", "device_type": "Games Console", "product_line": "Xbox One"},
    "98:5f:d3": {"vendor": "Microsoft", "model": "Xbox Series X / S", "device_type": "Games Console", "product_line": "Xbox Series"},
}

# ─────────────────────────────────────────────────────────────────────────────
# RASPBERRY PI
# ─────────────────────────────────────────────────────────────────────────────
# These lived inside _XBOX until v2.2.7, which is how d8:3a:dd — a Raspberry Pi
# Trading OUI — ended up carrying the Xbox entry's vendor and model. A Pi named
# "pinas" was reported as vendor Microsoft, type Games Console, and the
# heuristic classifier (which gets it right from the hostname alone) was never
# consulted, because a registry device_type is sticky. Keep the vendor families
# in their own blocks.
_RASPBERRY_PI: Dict[str, Dict[str, str]] = {
    "b8:27:eb": {"vendor": "Raspberry Pi", "model": "Raspberry Pi 1/2/3", "device_type": "Single Board Computer", "product_line": "Raspberry Pi"},
    "dc:a6:32": {"vendor": "Raspberry Pi", "model": "Raspberry Pi 4 / 400", "device_type": "Single Board Computer", "product_line": "Raspberry Pi"},
    "e4:5f:01": {"vendor": "Raspberry Pi", "model": "Raspberry Pi 4 / CM4", "device_type": "Single Board Computer", "product_line": "Raspberry Pi"},
    "28:cd:c1": {"vendor": "Raspberry Pi", "model": "Raspberry Pi Pico W / Zero 2 W", "device_type": "Single Board Computer", "product_line": "Raspberry Pi"},
    "d8:3a:dd": {"vendor": "Raspberry Pi", "model": "Raspberry Pi 4 / CM4", "device_type": "Single Board Computer", "product_line": "Raspberry Pi"},
    "2c:cf:67": {"vendor": "Raspberry Pi", "model": "Raspberry Pi 5", "device_type": "Single Board Computer", "product_line": "Raspberry Pi"},
}

# ─────────────────────────────────────────────────────────────────────────────
# ROKU — Streaming Devices
# ─────────────────────────────────────────────────────────────────────────────
_ROKU: Dict[str, Dict[str, str]] = {
    "cc:6d:a0": {"vendor": "Roku", "model": "Roku Streaming Stick", "device_type": "Streaming Stick", "product_line": "Roku"},
    "b8:3e:59": {"vendor": "Roku", "model": "Roku Express / Premiere", "device_type": "Streaming Stick", "product_line": "Roku"},
    "d4:e2:2e": {"vendor": "Roku", "model": "Roku Ultra / Streambar", "device_type": "Streaming Stick", "product_line": "Roku"},
    "08:05:81": {"vendor": "Roku", "model": "Roku TV", "device_type": "Smart TV", "product_line": "Roku TV"},
    "ac:3a:7a": {"vendor": "Roku", "model": "Roku Streaming Device", "device_type": "Streaming Stick", "product_line": "Roku"},
    "fc:9b:09": {"vendor": "Roku", "model": "Roku Ultra (2nd Gen)", "device_type": "Streaming Stick", "product_line": "Roku"},
}

# ─────────────────────────────────────────────────────────────────────────────
# SONOS — Smart Speakers / Audio
# ─────────────────────────────────────────────────────────────────────────────
_SONOS: Dict[str, Dict[str, str]] = {
    "b8:e9:37": {"vendor": "Sonos", "model": "Sonos One / Play:1", "device_type": "Smart Speaker / Audio", "product_line": "Sonos"},
    "5c:aa:fd": {"vendor": "Sonos", "model": "Sonos Play:3 / Play:5", "device_type": "Smart Speaker / Audio", "product_line": "Sonos"},
    "78:28:ca": {"vendor": "Sonos", "model": "Sonos Beam / Arc", "device_type": "Smart Speaker / Audio", "product_line": "Sonos"},
    "94:9f:3e": {"vendor": "Sonos", "model": "Sonos Move / Roam", "device_type": "Smart Speaker / Audio", "product_line": "Sonos"},
    "48:a6:b8": {"vendor": "Sonos", "model": "Sonos Era 100 / Era 300", "device_type": "Smart Speaker / Audio", "product_line": "Sonos"},
    "34:7e:a8": {"vendor": "Sonos", "model": "Sonos Device", "device_type": "Smart Speaker / Audio", "product_line": "Sonos"},
    "54:2a:1b": {"vendor": "Sonos", "model": "Sonos Device", "device_type": "Smart Speaker / Audio", "product_line": "Sonos"},
}

# ─────────────────────────────────────────────────────────────────────────────
# HP / HEWLETT-PACKARD — PCs and Printers
# ─────────────────────────────────────────────────────────────────────────────
_HP: Dict[str, Dict[str, str]] = {
    "7c:4d:8f": {"vendor": "HP", "model": "HP Desktop / Laptop", "device_type": "Windows PC", "product_line": "HP PC"},
    "3c:d9:2b": {"vendor": "HP", "model": "HP EliteBook / ProBook", "device_type": "Windows PC", "product_line": "HP PC"},
    "00:1e:0b": {"vendor": "HP", "model": "HP Desktop / Workstation", "device_type": "Windows PC", "product_line": "HP PC"},
    "34:64:a9": {"vendor": "HP", "model": "HP ZBook / EliteBook", "device_type": "Windows PC", "product_line": "HP PC"},
    "70:5a:0f": {"vendor": "HP", "model": "HP Device", "device_type": "Windows PC", "product_line": "HP PC"},
    "d4:c9:ef": {"vendor": "HP", "model": "HP Printer / Scanner", "device_type": "Print Server", "product_line": "HP Printer"},
    "a0:b3:cc": {"vendor": "HP", "model": "HP Device", "device_type": "Windows PC", "product_line": "HP PC"},
    "f4:ce:46": {"vendor": "HP", "model": "HP Desktop PC", "device_type": "Windows PC", "product_line": "HP PC"},
    "10:60:4b": {"vendor": "HP", "model": "HP Device", "device_type": "Windows PC", "product_line": "HP PC"},
}

# NOTE: there is deliberately no _LENOVO block. All eight entries it used to
# carry were ODM OUIs registered to LCFC, Wistron, Intel, Dell and Sony — the
# companies that actually build or supply the hardware — not to Lenovo. An ODM
# OUI appears across many unrelated brands, so it cannot identify a product;
# the IEEE fallback in mac_lookup.py answers those honestly instead.

_OUI_REGISTRY.update(_SONOS)
_OUI_REGISTRY.update(_HP)

_OUI_REGISTRY.update(_LG)
_OUI_REGISTRY.update(_SONY_TV)
_OUI_REGISTRY.update(_PLAYSTATION)
_OUI_REGISTRY.update(_NINTENDO)
_OUI_REGISTRY.update(_XBOX)
_OUI_REGISTRY.update(_RASPBERRY_PI)
_OUI_REGISTRY.update(_ROKU)


# ─────────────────────────────────────────────────────────────────────────────
# IEEE CONSISTENCY
# ─────────────────────────────────────────────────────────────────────────────
# This table is consulted BEFORE the IEEE database (classify_registry_first(),
# rogue_device.scan()) and its device_type is sticky — _apply_resolution() only
# reclassifies a device whose type is empty or "Unknown Device". So a wrong
# vendor here silently decides the device type too, and no later evidence can
# dislodge it. The table is a *refinement* of IEEE — a specific product behind
# an OUI IEEE only knows a company for — never an override of it.
#
# tests/test_mac_registry.py::test_no_entry_contradicts_ieee is the real gate
# and keeps the data itself correct. The runtime pass below is a safety net for
# the case CI cannot see: a machine whose scapy DB records an assignment this
# table disagrees with. It fails open — no scapy, no validation, table as-is.

# Words that carry no identity — dropped before comparing two vendor names.
_CORP_NOISE = frozenset({
    "inc", "corp", "corporation", "co", "ltd", "limited", "llc", "gmbh",
    "sas", "ab", "plc", "bv", "nv", "sa", "kg", "ag", "pte", "pty",
    "company", "holdings", "group", "the",
})

# Where IEEE and this table use different trade names for ONE company. Only
# real corporate identity belongs here — an ODM or chip vendor whose module
# ships inside another brand's product (AzureWave, Murata, Liteon, LCFC,
# Wistron) is a different company and must never be aliased away.
_VENDOR_ALIASES = {
    "hewlett": "hp",
    "hp": "hp",
    "asustek": "asus",
    "asus": "asus",
    "lge": "lg",          # IEEE registers LG Electronics as "Lge"
}

# A dict rather than a bare bool flag: CodeQL's py/unused-global-variable is a
# per-definition result, so a `_validated = True` store inside the run-once
# guard is reported as never-read -- it cannot model the NEXT call reading it.
# Mutating a container keeps every access a load, which is true of the code's
# intent anyway (RULE-LINT6).
_validation_state: dict[str, bool] = {"done": False}


def vendor_key(name: str) -> str:
    """The single token a vendor name is identified by, alias-resolved.

    Shared by the runtime check and its test so the two cannot drift.
    """
    cleaned = _re.sub(r"[^a-z0-9]+", " ", name.lower())
    tokens = [t for t in cleaned.split() if t and t not in _CORP_NOISE]
    if not tokens:
        return ""
    return _VENDOR_ALIASES.get(tokens[0], tokens[0])


def vendors_agree(curated: str, ieee: str) -> bool:
    """True when a curated vendor is consistent with the IEEE assignment.

    An entry may name several trade names for one OUI ("Google / Nest Labs",
    "TP-Link / Ubiquiti"); agreement on any one counts, since it is not
    asserting the others exclusively. An empty IEEE name means IEEE has no
    record, which is an absence of evidence, not a contradiction.
    """
    key = vendor_key(ieee)
    if not key:
        return True
    return any(vendor_key(part) == key for part in curated.split("/"))


def _validate_against_ieee() -> None:
    """Drop any entry whose vendor contradicts scapy's bundled IEEE manuf DB.

    Runs at most once, lazily. A wrong vendor makes the entry's model and
    device_type wrong too — "Microsoft" -> "Xbox Series X / S" -> "Games
    Console" is one causal chain, not three independent facts — so a
    conflicting entry is dropped whole rather than partially trusted.
    """
    if _validation_state["done"]:
        return
    _validation_state["done"] = True  # set first: a failed attempt must not retry on every lookup

    try:
        from scapy.all import conf as _scapy_conf   # noqa: PLC0415 — RULE-AH4 lazy
        manufdb = _scapy_conf.manufdb
    except Exception:
        return  # fail open — no IEEE data available, keep the table as authored

    for oui in list(_OUI_REGISTRY):
        query = f"{oui}:00:00:00"
        try:
            ieee = manufdb._get_manuf(query)
        except Exception:
            continue  # non-fatal — one unresolvable OUI must not void the table
        if not ieee or ieee in (query, oui):
            continue  # IEEE has no assignment on record
        if not vendors_agree(_OUI_REGISTRY[oui]["vendor"], ieee):
            del _OUI_REGISTRY[oui]


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

def lookup(mac: str) -> Dict[str, str]:
    """
    Look up a MAC address in the registry.

    Parameters
    ----------
    mac : str
        Any common MAC format: "aa:bb:cc:dd:ee:ff", "AA-BB-CC-DD-EE-FF", etc.

    Returns
    -------
    dict with keys vendor / model / device_type / product_line,
    or empty dict if the OUI is not found.
    """
    _validate_against_ieee()
    normalised = mac.lower().replace("-", ":").replace(".", ":")
    # Handle condensed formats (aabbccddeeff)
    if ":" not in normalised and len(normalised) == 12:
        normalised = ":".join(normalised[i:i+2] for i in range(0, 12, 2))
    oui = normalised[:8]  # "xx:xx:xx"
    return dict(_OUI_REGISTRY.get(oui, {}))


def vendor_from_mac(mac: str) -> str:
    """Shortcut — return just the vendor string, or empty string."""
    return lookup(mac).get("vendor", "")


def model_from_mac(mac: str) -> str:
    """Shortcut — return just the model string, or empty string."""
    return lookup(mac).get("model", "")


def all_ouis() -> Dict[str, Dict[str, str]]:
    """Return the full registry (read-only copy)."""
    _validate_against_ieee()
    return dict(_OUI_REGISTRY)
