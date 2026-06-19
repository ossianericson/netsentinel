"""
passive_observer.py — Passive SSDP / mDNS listener for device classification.

Runs a continuous background UDP listener that captures:
  - SSDP NOTIFY / M-SEARCH RESPONSE packets on 239.255.255.250:1900
  - mDNS PTR responses on 224.0.0.251:5353

No packets are transmitted; no Npcap / admin rights required.
Observations are correlated against DeviceInfo objects in the post-scan
enrichment step to upgrade "Unknown Device" classifications.
"""
from __future__ import annotations

import logging
import socket
import struct
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

_log = logging.getLogger(__name__)

# ── Classification tables ──────────────────────────────────────────────────────

# SSDP NT/ST field → (device_hint, confidence)
_SSDP_HINTS: dict[str, tuple[str, str]] = {
    "urn:schemas-upnp-org:device:internetgatewaydevice":  ("Router / Gateway",         "high"),
    "urn:schemas-upnp-org:device:wanaccessdevice":        ("Router / Gateway",         "high"),
    "urn:schemas-upnp-org:device:wanconnectiondevice":    ("Router / Gateway",         "high"),
    "urn:schemas-upnp-org:device:wlanconnectionmanager":  ("Wireless Access Point",    "high"),
    "urn:schemas-upnp-org:device:wlanaccesspoint":        ("Wireless Access Point",    "high"),
    "urn:schemas-upnp-org:device:mediarenderer":          ("Smart TV",                 "high"),
    "urn:schemas-upnp-org:device:mediaserver":            ("File / NAS Server",        "low"),
    "urn:schemas-upnp-org:device:printer":                ("Print Server",             "high"),
    "urn:schemas-upnp-org:device:printbasic":             ("Print Server",             "high"),
    "urn:schemas-upnp-org:device:scanner":                ("Print Server",             "low"),
    "urn:schemas-upnp-org:device:basic":                  ("IoT Device",               "low"),
    "urn:schemas-upnp-org:device:binarylight":            ("IoT Device",               "high"),
    "urn:schemas-upnp-org:device:dimminglamp":            ("IoT Device",               "high"),
    "urn:schemas-upnp-org:device:switchpower":            ("IoT Device",               "high"),
    "urn:schemas-upnp-org:device:hvac":                   ("IoT Device",               "high"),
    "urn:schemas-upnp-org:device:digitalsecuritycamera":  ("IP Camera",                "high"),
    "urn:schemas-upnp-org:device:remoteuiclient":         ("Smart TV",                 "low"),
    "upnp:rootdevice":                                    ("",                         "low"),
    "schemas-upnp-org:device:basic":                      ("IoT Device",               "low"),
}

# mDNS service type → (device_hint, confidence)
_MDNS_HINTS: dict[str, tuple[str, str]] = {
    "_printer._tcp":        ("Print Server",             "high"),
    "_ipp._tcp":            ("Print Server",             "high"),
    "_ipps._tcp":           ("Print Server",             "high"),
    "_pdl-datastream._tcp": ("Print Server",             "high"),
    "_googlecast._tcp":     ("Streaming Stick",          "high"),
    "_airplay._tcp":        ("Smart TV",                 "high"),
    "_raop._tcp":           ("Smart TV",                 "high"),
    "_homekit._tcp":        ("IoT Device",               "high"),
    "_hap._tcp":            ("IoT Device",               "high"),
    "_matter._tcp":         ("IoT Device",               "high"),
    "_smb._tcp":            ("File / NAS Server",        "low"),
    "_afpovertcp._tcp":     ("File / NAS Server",        "low"),
    "_nfs._tcp":            ("File / NAS Server",        "low"),
    "_ftp._tcp":            ("File / NAS Server",        "low"),
    "_daap._tcp":           ("File / NAS Server",        "low"),
    "_workstation._tcp":    ("Windows PC / Linux Host",  "low"),
    "_ssh._tcp":            ("Linux / Unix Host",        "low"),
    "_sftp-ssh._tcp":       ("Linux / Unix Host",        "low"),
    "_rdp._tcp":            ("Windows PC",               "high"),
    "_rfb._tcp":            ("Linux / Unix Host",        "low"),
    "_http._tcp":           ("",                         "low"),
    "_https._tcp":          ("",                         "low"),
    "_spotify-connect._tcp":("Smart Speaker / Audio",   "high"),
    "_sonos._tcp":          ("Smart Speaker / Audio",   "high"),
    "_sleep-proxy._udp":    ("macOS Device",             "high"),
    "_apple-mobdev2._tcp":  ("iPhone / iPad",            "high"),
    "_uscan._tcp":          ("Print Server",             "high"),
    "_uscans._tcp":         ("Print Server",             "high"),
    "_xbox._tcp":           ("Games Console",            "high"),
    "_psn._tcp":            ("Games Console",            "high"),
    "_nintendo._tcp":       ("Games Console",            "high"),
    "_miio._udp":           ("IoT Device",               "high"),  # Xiaomi IoT
    "_ewelink._tcp":        ("IoT Device",               "high"),  # Sonoff/eWeLink
    "_hue._tcp":            ("Smart Home Hub",           "high"),  # Philips Hue
    "_mosquitto._tcp":      ("IoT Device",               "low"),
}


# ── Dataclass ──────────────────────────────────────────────────────────────────

@dataclass
class PassiveObservation:
    """A single device type hint captured passively from the network."""
    ip: str
    mac: str = ""               # filled by ARP cache lookup after observation
    protocol: str = ""          # "ssdp" | "mdns"
    service_type: str = ""      # "_printer._tcp" | "MediaRenderer" | etc.
    device_hint: str = ""       # classification label this implies
    confidence: str = ""        # "high" | "low"
    raw_summary: str = ""       # human-readable description
    observed_at: float = field(default_factory=time.time)


# ── Internal state ─────────────────────────────────────────────────────────────

_observations: dict[str, PassiveObservation] = {}   # key: f"{ip}|{service_type}"
_obs_lock = threading.Lock()
_stop_event = threading.Event()
_threads: list[threading.Thread] = []


# ── ARP cache helper ───────────────────────────────────────────────────────────

def _mac_from_arp_cache(ip: str) -> str:
    """Return MAC for *ip* from the OS ARP cache, or '' if not found."""
    try:
        import subprocess
        out = subprocess.check_output(
            ["arp", "-a", ip], timeout=2, stderr=subprocess.DEVNULL
        ).decode(errors="replace")
        for line in out.splitlines():
            if ip in line:
                parts = line.split()
                for p in parts:
                    # Look for MAC-like tokens: xx-xx-xx-xx-xx-xx or xx:xx:xx:xx:xx:xx
                    if len(p) in (17, 14) and (("-" in p and p.count("-") == 5) or
                                                (":" in p and p.count(":") == 5)):
                        return p.replace("-", ":").upper()
    except Exception:
        pass  # non-fatal — MAC lookup is best-effort
    return ""


# ── SSDP listener ──────────────────────────────────────────────────────────────

_SSDP_GROUP = "239.255.255.250"
_SSDP_PORT  = 1900


def _parse_ssdp(data: bytes, src_ip: str, callback: Callable[[PassiveObservation], None]) -> None:
    """Extract ST/NT from SSDP packets and fire callback when a known type is found."""
    try:
        text = data.decode("utf-8", errors="replace")
    except Exception:
        return

    service_type = ""
    for line in text.splitlines():
        lower = line.lower()
        if lower.startswith("nt:") or lower.startswith("st:") or lower.startswith("usn:"):
            val = line.split(":", 1)[1].strip().lower()
            # Prefer NT/ST over USN
            if lower.startswith("nt:") or lower.startswith("st:"):
                service_type = val
                break

    if not service_type:
        return

    # Match against our table
    hint, confidence = "", ""
    for key, (h, c) in _SSDP_HINTS.items():
        if key in service_type:
            hint, confidence = h, c
            break

    if not hint:
        return

    # Extract a readable type fragment for the summary
    pretty = service_type.split(":")[-1].replace("-", " ").title()
    raw_summary = f"UPnP/SSDP {pretty}"

    _record(src_ip, "ssdp", service_type, hint, confidence, raw_summary, callback)


def _ssdp_listener(callback: Callable[[PassiveObservation], None]) -> None:
    """Bind to SSDP multicast group and forward received datagrams to _parse_ssdp."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)  # type: ignore[attr-defined]
        except AttributeError:
            pass  # SO_REUSEPORT not available on Windows — not needed
        sock.bind(("", _SSDP_PORT))  # lgtm[py/bind-socket-all-network-interfaces] — SSDP multicast requires binding to all interfaces
        mreq = struct.pack("4sL", socket.inet_aton(_SSDP_GROUP), socket.INADDR_ANY)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        sock.settimeout(1.0)
    except Exception as exc:
        _log.warning("SSDP listener could not bind: %s", exc)
        return

    _log.debug("SSDP listener started on %s:%d", _SSDP_GROUP, _SSDP_PORT)
    while not _stop_event.is_set():
        try:
            data, (src_ip, _) = sock.recvfrom(4096)
            _parse_ssdp(data, src_ip, callback)
        except socket.timeout:
            pass  # expected — check stop_event
        except OSError:
            break  # socket closed

    try:
        sock.close()
    except Exception:
        pass  # socket may already be closed
    _log.debug("SSDP listener stopped")


# ── mDNS listener ─────────────────────────────────────────────────────────────

_MDNS_GROUP = "224.0.0.251"
_MDNS_PORT  = 5353


def _parse_mdns(data: bytes, src_ip: str, callback: Callable[[PassiveObservation], None]) -> None:
    """
    Minimal mDNS PTR record parser.

    DNS packet layout (RFC 1035):
      2B  transaction ID
      2B  flags
      2B  QDCOUNT, 2B ANCOUNT, 2B NSCOUNT, 2B ARCOUNT
      then questions, then answers (variable length)

    We only care about Answer section PTR records (type=12) whose RDATA
    is a service instance name like "_printer._tcp.local."
    """
    if len(data) < 12:
        return

    try:
        ancount = struct.unpack_from("!H", data, 6)[0]
        if ancount == 0:
            return

        # Skip the question section to reach the answer section
        offset = 12
        qdcount = struct.unpack_from("!H", data, 4)[0]
        for _ in range(qdcount):
            # Skip QNAME (sequence of length-prefixed labels, 0-terminated)
            offset = _skip_dns_name(data, offset)
            if offset < 0:
                return
            offset += 4  # QTYPE + QCLASS

        # Walk answer records
        for _ in range(ancount):
            offset = _skip_dns_name(data, offset)
            if offset < 0 or offset + 10 > len(data):
                return
            rtype, _cls, _ttl, rdlen = struct.unpack_from("!HHIH", data, offset)
            offset += 10
            if offset + rdlen > len(data):
                return
            rdata = data[offset: offset + rdlen]
            offset += rdlen

            if rtype != 12:   # PTR
                continue

            # Decode the PTR target: the service instance name
            svc_name = _decode_dns_name(data, _ptr_offset(data, rdata))
            if not svc_name:
                continue

            # Extract the service type part (e.g. "_printer._tcp" from
            # "My Printer._printer._tcp.local.")
            parts = svc_name.lower().rstrip(".").split(".")
            # Service type is the segment pair starting with "_"
            for i, p in enumerate(parts):
                if p.startswith("_") and i + 1 < len(parts):
                    candidate = f"{p}.{parts[i + 1]}"
                    if candidate in _MDNS_HINTS:
                        hint, confidence = _MDNS_HINTS[candidate]
                        if hint:
                            raw_summary = f"mDNS {candidate}"
                            _record(src_ip, "mdns", candidate, hint, confidence,
                                    raw_summary, callback)
                        break

    except Exception:
        pass  # malformed packet — ignore silently


def _ptr_offset(packet: bytes, rdata: bytes) -> int:
    """Return the byte offset within *packet* where *rdata* begins."""
    # Find the rdata slice position in the original packet
    rdata_start = packet.find(bytes(rdata))
    return max(0, rdata_start)


def _skip_dns_name(data: bytes, offset: int) -> int:
    """Advance *offset* past a DNS name (handles compression pointers). Returns new offset."""
    while offset < len(data):
        length = data[offset]
        if length == 0:
            return offset + 1
        if (length & 0xC0) == 0xC0:
            return offset + 2  # compression pointer — 2 bytes total
        offset += 1 + length
    return -1


def _decode_dns_name(data: bytes, offset: int) -> str:
    """Decode a DNS name starting at *offset* (with compression pointer support)."""
    labels: list[str] = []
    visited: set[int] = set()
    while offset < len(data):
        if offset in visited:
            break  # loop guard
        visited.add(offset)
        length = data[offset]
        if length == 0:
            break
        if (length & 0xC0) == 0xC0:
            if offset + 1 >= len(data):
                break
            ptr = ((length & 0x3F) << 8) | data[offset + 1]
            offset = ptr
            continue
        offset += 1
        try:
            labels.append(data[offset: offset + length].decode("utf-8", errors="replace"))
        except Exception:
            break
        offset += length
    return ".".join(labels)


def _mdns_listener(callback: Callable[[PassiveObservation], None]) -> None:
    """Bind to mDNS multicast group and forward datagrams to _parse_mdns."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)  # type: ignore[attr-defined]
        except AttributeError:
            pass  # not available on Windows
        sock.bind(("", _MDNS_PORT))  # lgtm[py/bind-socket-all-network-interfaces] — mDNS multicast requires binding to all interfaces
        mreq = struct.pack("4sL", socket.inet_aton(_MDNS_GROUP), socket.INADDR_ANY)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        sock.settimeout(1.0)
    except Exception as exc:
        _log.warning("mDNS listener could not bind: %s", exc)
        return

    _log.debug("mDNS listener started on %s:%d", _MDNS_GROUP, _MDNS_PORT)
    while not _stop_event.is_set():
        try:
            data, (src_ip, _) = sock.recvfrom(4096)
            _parse_mdns(data, src_ip, callback)
        except socket.timeout:
            pass  # expected
        except OSError:
            break  # socket closed

    try:
        sock.close()
    except Exception:
        pass  # socket may already be closed
    _log.debug("mDNS listener stopped")


# ── Observation store ──────────────────────────────────────────────────────────

def _record(
    ip: str,
    protocol: str,
    service_type: str,
    device_hint: str,
    confidence: str,
    raw_summary: str,
    callback: Callable[[PassiveObservation], None],
) -> None:
    """Store or update an observation and call *callback* for new/upgraded entries."""
    key = f"{ip}|{service_type}"
    obs = PassiveObservation(
        ip=ip,
        protocol=protocol,
        service_type=service_type,
        device_hint=device_hint,
        confidence=confidence,
        raw_summary=raw_summary,
        observed_at=time.time(),
    )
    with _obs_lock:
        existing = _observations.get(key)
        # Only fire callback if this is new or the confidence improved
        _confidence_rank = {"high": 1, "low": 0}
        new_rank = _confidence_rank.get(confidence, 0)
        old_rank = _confidence_rank.get(existing.confidence if existing else "", -1)
        if existing is None or new_rank > old_rank:
            _observations[key] = obs
            try:
                callback(obs)
            except Exception:
                pass  # non-fatal — callback errors must not crash the listener


# ── Public API ─────────────────────────────────────────────────────────────────

def start_passive_observation(
    on_observation: Callable[[PassiveObservation], None],
) -> list[threading.Thread]:
    """
    Start background SSDP + mDNS listeners.

    Parameters
    ----------
    on_observation
        Called (from a background thread) each time a new or improved
        observation is recorded.  Must be thread-safe (e.g. emit a Qt signal).

    Returns
    -------
    List of started daemon threads (two: SSDP + mDNS).
    Callers can store them but generally just need to call stop_passive_observation().
    """
    global _threads
    _stop_event.clear()
    _observations.clear()

    t_ssdp = threading.Thread(
        target=_ssdp_listener,
        args=(on_observation,),
        daemon=True,
        name="PassiveObserver-SSDP",
    )
    t_mdns = threading.Thread(
        target=_mdns_listener,
        args=(on_observation,),
        daemon=True,
        name="PassiveObserver-mDNS",
    )
    t_ssdp.start()
    t_mdns.start()
    _threads = [t_ssdp, t_mdns]
    return _threads


def stop_passive_observation() -> None:
    """Signal the background listeners to exit and wait for them to finish."""
    _stop_event.set()
    for t in _threads:
        t.join(timeout=3.0)


def get_observations() -> list[PassiveObservation]:
    """Return all observations recorded since start, deduplicated by (ip, service_type)."""
    with _obs_lock:
        return list(_observations.values())


def enrich_mac(obs: PassiveObservation) -> PassiveObservation:
    """
    Attempt to fill obs.mac from the OS ARP cache.
    Returns the same object (mutated in-place) so callers can chain the call.
    """
    if not obs.mac:
        obs.mac = _mac_from_arp_cache(obs.ip)
    return obs
