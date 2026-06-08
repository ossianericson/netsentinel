"""
Home Automation Detector — identifies HA devices on the local network
using port-based probing and OUI prefix matching.

Detects:
  home_assistant   — port 8123 / 8124
  hue_bridge       — port 80, OUI 00:17:88 / EC:B5:FA / 00:1a:22
  mqtt_broker      — port 1883 / 8883 (Mosquitto, etc.)
  sonos            — port 1400
  apple_homepod    — mDNS / Bonjour OUI patterns
  shelly           — port 80, /shelly endpoint responds
  smart_tv         — port 8009 (Chromecast), 55000 (Samsung), 1925 (Philips TV)
  zigbee2mqtt      — port 1880 (Node-RED), often co-located with mqtt
  synology_srm     — port 8001 (Synology Router Manager)
  eero             — OUI-based
  ring             — OUI-based
  nest_hub         — OUI-based (Google / Nest Labs)

Usage::

    from modules.ha_detector import scan
    results = scan(["192.168.1.1", "192.168.1.42"], progress_cb=print)
    for r in results:
        print(r.ip, r.ha_type, r.confidence)
"""

from __future__ import annotations

import socket
import urllib.request
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional


# ── Detection result ─────────────────────────────────────────────────────────

@dataclass
class HaMatch:
    ip:         str
    mac:        Optional[str]
    ha_type:    str
    confidence: str          # "high" | "medium" | "low"
    detail:     Optional[str]
    label:      str          # human-readable label shown in UI


# ── OUI → HA type mapping ─────────────────────────────────────────────────────
# OUIs in lowercase colon format, 8 chars

_OUI_SIGNATURES: Dict[str, dict] = {
    # Philips Hue
    "00:17:88": {"ha_type": "hue_bridge",    "confidence": "high",   "label": "Philips Hue Bridge"},
    "ec:b5:fa": {"ha_type": "hue_bridge",    "confidence": "high",   "label": "Philips Hue Bridge"},
    "00:1a:22": {"ha_type": "hue_bridge",    "confidence": "medium", "label": "Philips Hue (older)"},
    # Sonos
    "78:28:ca": {"ha_type": "sonos",         "confidence": "high",   "label": "Sonos Speaker"},
    "94:9f:3e": {"ha_type": "sonos",         "confidence": "high",   "label": "Sonos Speaker"},
    "b8:e9:37": {"ha_type": "sonos",         "confidence": "high",   "label": "Sonos Speaker"},
    "5c:aa:fd": {"ha_type": "sonos",         "confidence": "high",   "label": "Sonos Speaker"},
    "48:a6:b8": {"ha_type": "sonos",         "confidence": "high",   "label": "Sonos Speaker"},
    # Apple HomePod
    "3c:7d:0a": {"ha_type": "apple_homepod", "confidence": "high",   "label": "Apple HomePod"},
    "a8:51:5b": {"ha_type": "apple_homepod", "confidence": "high",   "label": "Apple HomePod"},
    "f8:ff:c2": {"ha_type": "apple_homepod", "confidence": "medium", "label": "Apple HomePod"},
    # eero
    "f0:a7:31": {"ha_type": "eero",          "confidence": "high",   "label": "Amazon eero"},
    "74:75:48": {"ha_type": "eero",          "confidence": "high",   "label": "Amazon eero"},
    # Ring
    "b0:09:da": {"ha_type": "ring",          "confidence": "high",   "label": "Ring Doorbell/Camera"},
    "4c:49:e3": {"ha_type": "ring",          "confidence": "high",   "label": "Ring Doorbell/Camera"},
    # Nest / Google Home
    "18:b4:30": {"ha_type": "nest_thermostat","confidence": "high",  "label": "Nest Thermostat"},
    "64:16:66": {"ha_type": "google_nest",   "confidence": "high",   "label": "Google Nest Wifi"},
    "f4:f5:d8": {"ha_type": "google_nest",   "confidence": "high",   "label": "Google Home/Nest"},
    # Shelly
    "84:0d:8e": {"ha_type": "shelly",        "confidence": "high",   "label": "Shelly Smart Device"},
    "98:f4:ab": {"ha_type": "shelly",        "confidence": "high",   "label": "Shelly Smart Device"},
    "e8:68:e7": {"ha_type": "shelly",        "confidence": "high",   "label": "Shelly Smart Device"},
    # Samsung SmartThings
    "d0:52:a8": {"ha_type": "smartthings",   "confidence": "medium", "label": "Samsung SmartThings"},
    "00:21:d1": {"ha_type": "smartthings",   "confidence": "medium", "label": "Samsung SmartThings"},
}

# ── Port-based signatures ─────────────────────────────────────────────────────

@dataclass
class _PortSig:
    port:       int
    ha_type:    str
    confidence: str
    label:      str
    # Optional URL path to fetch and check against (None = open port is enough)
    probe_path: Optional[str] = None
    probe_text: Optional[str] = None   # substring that must appear in response

_PORT_SIGNATURES: List[_PortSig] = [
    _PortSig(8123, "home_assistant", "high",   "Home Assistant",    "/",          "Home Assistant"),
    _PortSig(8124, "home_assistant", "high",   "Home Assistant",    "/",          "Home Assistant"),
    _PortSig(1883, "mqtt_broker",    "high",   "MQTT Broker",       None,         None),
    _PortSig(8883, "mqtt_broker",    "high",   "MQTT Broker (TLS)", None,         None),
    _PortSig(1400, "sonos",          "high",   "Sonos Speaker",     "/xml/device_description.xml", "Sonos"),
    _PortSig(8001, "synology",       "medium", "Synology Router",   None,         None),
    _PortSig(1880, "node_red",       "medium", "Node-RED",          "/",          "Node-RED"),
    _PortSig(8009, "chromecast",     "high",   "Chromecast",        None,         None),
    _PortSig(55000, "samsung_tv",    "high",   "Samsung Smart TV",  None,         None),
    _PortSig(1925, "philips_tv",     "medium", "Philips Smart TV",  None,         None),
]

# Category mapping: ha_type → known_device.category value
_TYPE_TO_CATEGORY: Dict[str, str] = {
    "home_assistant":  "smart_hub",
    "hue_bridge":      "lighting",
    "mqtt_broker":     "smart_hub",
    "sonos":           "media_player",
    "apple_homepod":   "media_player",
    "eero":            "home_automation",
    "ring":            "security",
    "nest_thermostat": "thermostat",
    "google_nest":     "smart_hub",
    "shelly":          "smart_plug",
    "smartthings":     "smart_hub",
    "synology":        "home_automation",
    "node_red":        "smart_hub",
    "chromecast":      "media_player",
    "samsung_tv":      "smart_tv",
    "philips_tv":      "smart_tv",
}

HA_TYPE_LABELS: Dict[str, str] = {
    k: s["label"] for k, s in _OUI_SIGNATURES.items()
} | {sig.ha_type: sig.label for sig in _PORT_SIGNATURES}


def ha_category(ha_type: str) -> str:
    """Map a ha_type string to a known_device.category value."""
    return _TYPE_TO_CATEGORY.get(ha_type, "home_automation")


# ── OUI lookup helper ─────────────────────────────────────────────────────────

def _oui_match(mac: Optional[str]) -> Optional[dict]:
    if not mac:
        return None
    oui = mac.lower()[:8]
    return _OUI_SIGNATURES.get(oui)


# ── TCP port probe ────────────────────────────────────────────────────────────

def _tcp_open(ip: str, port: int, timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError:
        return False


def _http_probe(ip: str, port: int, path: str, timeout: float = 2.5) -> Optional[str]:
    """
    Fetch http://ip:port/path and return response text (≤4KB).
    Returns None on any error.
    """
    url = f"http://{ip}:{port}{path}"
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "NetSentinel/1.0"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read(4096).decode("utf-8", errors="replace")
    except Exception:
        return None


# ── Main scan function ────────────────────────────────────────────────────────

def scan(
    hosts: List[dict],
    progress_cb: Optional[Callable[[str], None]] = None,
    port_timeout: float = 1.5,
    http_timeout: float = 3.0,
) -> List[HaMatch]:
    """
    Scan a list of host dicts (keys: ip, mac) for HA device signatures.

    Returns a list of HaMatch objects for every detected HA device.
    A host may produce multiple matches (e.g. MQTT broker on Home Assistant).

    Parameters
    ----------
    hosts : list[dict]
        Each dict must have at least "ip". Optional "mac" key.
    progress_cb : callable | None
        Called with a status string at key milestones.
    port_timeout : float
        TCP connect timeout per port.
    http_timeout : float
        HTTP probe timeout per request.
    """
    results: List[HaMatch] = []
    seen: set[tuple[str, str]] = set()  # (ip, ha_type) dedup

    def _emit(msg: str) -> None:
        if progress_cb:
            progress_cb(msg)

    _emit(f"Scanning {len(hosts)} hosts for home automation devices…")

    for host in hosts:
        ip  = host.get("ip", "")
        mac = host.get("mac")
        if not ip:
            continue

        # ── OUI-based detection (instant, no network) ─────────────────────
        oui_info = _oui_match(mac)
        if oui_info:
            key = (ip, oui_info["ha_type"])
            if key not in seen:
                seen.add(key)
                results.append(HaMatch(
                    ip=ip, mac=mac,
                    ha_type=oui_info["ha_type"],
                    confidence=oui_info["confidence"],
                    label=oui_info["label"],
                    detail=f"OUI match: {mac[:8] if mac else '?'}",
                ))

        # ── Port-based detection ──────────────────────────────────────────
        for sig in _PORT_SIGNATURES:
            key = (ip, sig.ha_type)
            if key in seen:
                continue
            if not _tcp_open(ip, sig.port, port_timeout):
                continue
            # Port is open — optionally verify with HTTP probe
            if sig.probe_path and sig.probe_text:
                body = _http_probe(ip, sig.port, sig.probe_path, http_timeout)
                if body is None or sig.probe_text.lower() not in body.lower():
                    # Port open but didn't match banner — lower confidence
                    seen.add(key)
                    results.append(HaMatch(
                        ip=ip, mac=mac,
                        ha_type=sig.ha_type,
                        confidence="low",
                        label=sig.label,
                        detail=f"Port {sig.port} open (banner not confirmed)",
                    ))
                    continue
                confidence = sig.confidence
                detail = f"Port {sig.port} open, banner confirmed"
            else:
                confidence = sig.confidence
                detail = f"Port {sig.port} open"

            seen.add(key)
            results.append(HaMatch(
                ip=ip, mac=mac,
                ha_type=sig.ha_type,
                confidence=confidence,
                label=sig.label,
                detail=detail,
            ))

    _emit(f"HA scan complete — {len(results)} signature(s) found")
    return results
