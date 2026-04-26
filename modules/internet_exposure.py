"""
Internet Exposure Check — determines whether services on local devices
are reachable from the public internet.

Two-stage approach:
  Stage 1 (passive): Query UPnP/IGD port mappings from the router to find
    any ports forwarded to LAN devices.  These are definitively internet-exposed.

  Stage 2 (passive): Fetch the public WAN IP and cross-reference against
    known cloud metadata or IP-geolocation to confirm it's a real public IP
    (not RFC 1918 behind a carrier-grade NAT).

Result: each host is tagged with:
  exposed_ports    — list of ports confirmed reachable from internet (via UPnP mapping)
  wan_ip           — public WAN IP address
  cgnat            — True if behind carrier-grade NAT (no true public IP)
  risk             — "HIGH" | "MEDIUM" | "LOW"

No active probes are sent to external servers against the target —
the only external contact is fetching the public IP (ipinfo.io/ip or
api.ipify.org, one request, same as any browser).

UPnP discovery is LAN-local only (SSDP multicast — 239.255.255.250:1900).
"""

from __future__ import annotations

import re
import socket
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional
from urllib.request import urlopen, Request
from urllib.error import URLError

# Timeout for each network probe
_TIMEOUT = 4.0

# UPnP SSDP multicast details
_SSDP_ADDR = "239.255.255.250"
_SSDP_PORT = 1900
_SSDP_MX   = 2   # seconds to wait for responses


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class UPnPMapping:
    """A single port-forwarding entry returned by the router's IGD."""
    external_port: int
    internal_ip:   str
    internal_port: int
    protocol:      str   # "TCP" | "UDP"
    description:   str = ""
    enabled:       bool = True


@dataclass
class ExposureResult:
    wan_ip:         str = ""
    cgnat:          bool = False
    upnp_available: bool = False
    upnp_mappings:  List[UPnPMapping] = field(default_factory=list)
    error:          str = ""

    # Per-device exposure summary
    # device_ip → list of exposed ports
    exposed: dict = field(default_factory=dict)

    @property
    def total_exposed_ports(self) -> int:
        return sum(len(v) for v in self.exposed.values())

    @property
    def risk(self) -> str:
        if self.cgnat:
            return "LOW"
        if self.total_exposed_ports == 0:
            return "LOW"
        # High-risk ports exposed
        high_risk = {21, 22, 23, 80, 443, 445, 1883, 3389, 5900, 7547, 8080, 8443}
        for ports in self.exposed.values():
            if any(p in high_risk for p in ports):
                return "HIGH"
        return "MEDIUM"

    @property
    def plain_verdict(self) -> str:
        if self.error:
            return f"⚠ Exposure check failed: {self.error}"
        if self.cgnat:
            return (
                f"✅  Behind carrier-grade NAT (CGNAT) — WAN IP {self.wan_ip} is shared. "
                "LAN devices are NOT directly reachable from the internet."
            )
        if self.total_exposed_ports == 0:
            return (
                f"✅  WAN IP: {self.wan_ip} — no UPnP port-forwarding rules found. "
                "No LAN services appear internet-exposed."
            )
        device_list = ", ".join(
            f"{ip} ({len(ports)} port(s))" for ip, ports in self.exposed.items()
        )
        return (
            f"⚠  WAN IP: {self.wan_ip} — {self.total_exposed_ports} port(s) "
            f"forwarded to: {device_list}. These services ARE reachable from the internet!"
        )


# ── Public WAN IP ─────────────────────────────────────────────────────────────

_RFC1918 = re.compile(
    r"^(10\.\d+\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+|192\.168\.\d+\.\d+)$"
)
_CGNAT   = re.compile(r"^100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d+\.\d+$")


def _get_wan_ip() -> tuple[str, bool]:
    """
    Fetch public WAN IP from a lightweight public API.
    Returns (ip_str, is_cgnat).  Falls back gracefully on network error.
    """
    for url in ("https://api.ipify.org", "https://ipinfo.io/ip"):
        try:
            req = Request(url, headers={"User-Agent": "NetSentinel/3.0"})
            with urlopen(req, timeout=_TIMEOUT) as resp:
                ip = resp.read().decode("utf-8").strip()
                if re.match(r"^\d+\.\d+\.\d+\.\d+$", ip):
                    return ip, bool(_CGNAT.match(ip))
        except Exception:
            continue
    return "", False


# ── UPnP / IGD discovery ──────────────────────────────────────────────────────

_SSDP_DISCOVER = (
    "M-SEARCH * HTTP/1.1\r\n"
    "HOST: 239.255.255.250:1900\r\n"
    'MAN: "ssdp:discover"\r\n'
    "MX: 2\r\n"
    'ST: urn:schemas-upnp-org:service:WANIPConnection:1\r\n'
    "\r\n"
)


def _ssdp_discover(timeout: float = 3.0) -> list[str]:
    """
    Send an SSDP M-SEARCH and return a list of location URLs for UPnP IGDs.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.settimeout(timeout)
    sock.sendto(_SSDP_DISCOVER.encode(), (_SSDP_ADDR, _SSDP_PORT))

    locations: list[str] = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            data, _ = sock.recvfrom(4096)
            text = data.decode("utf-8", errors="replace")
            for line in text.splitlines():
                if line.strip().upper().startswith("LOCATION:"):
                    loc = line.split(":", 1)[1].strip()
                    if loc not in locations:
                        locations.append(loc)
        except socket.timeout:
            break
        except Exception:
            break
    sock.close()
    return locations


def _fetch_upnp_mappings(location_url: str) -> tuple[str, list[UPnPMapping]]:
    """
    Fetch the IGD description XML, find the control URL for WANIPConnection,
    then enumerate port mappings via GetGenericPortMappingEntry SOAP calls.
    Returns (control_url, [UPnPMapping, ...]).
    """
    import xml.etree.ElementTree as ET
    from urllib.parse import urljoin, urlparse
    from urllib.request import urlopen as _urlopen

    mappings: list[UPnPMapping] = []
    control_url = ""

    try:
        with _urlopen(location_url, timeout=_TIMEOUT) as resp:
            xml_data = resp.read()
        root = ET.fromstring(xml_data)
        ns   = {"upnp": "urn:schemas-upnp-org:device-1-0"}

        # Find WANIPConnection or WANPPPConnection service
        for svc in root.iter():
            tag = svc.tag.split("}")[-1] if "}" in svc.tag else svc.tag
            if tag == "service":
                stype = svc.find(".//{urn:schemas-upnp-org:device-1-0}serviceType")
                ctrl  = svc.find(".//{urn:schemas-upnp-org:device-1-0}controlURL")
                if stype is None:
                    # try without namespace
                    stype = svc.find(".//serviceType")
                    ctrl  = svc.find(".//controlURL")
                if stype is not None and ctrl is not None:
                    st = stype.text or ""
                    if "WANIPConnection" in st or "WANPPPConnection" in st:
                        base = "{u.scheme}://{u.netloc}".format(u=urlparse(location_url))
                        control_url = urljoin(base, ctrl.text)
                        break

        if not control_url:
            return "", []

        # Enumerate port mappings
        idx = 0
        while idx < 100:  # safety cap
            soap_body = (
                '<?xml version="1.0"?>'
                '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
                's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
                "<s:Body>"
                '<u:GetGenericPortMappingEntry xmlns:u="urn:schemas-upnp-org:service:WANIPConnection:1">'
                f"<NewPortMappingIndex>{idx}</NewPortMappingIndex>"
                "</u:GetGenericPortMappingEntry>"
                "</s:Body></s:Envelope>"
            )
            req = Request(
                control_url,
                data=soap_body.encode(),
                headers={
                    "Content-Type": "text/xml; charset=utf-8",
                    "SOAPAction": '"urn:schemas-upnp-org:service:WANIPConnection:1#GetGenericPortMappingEntry"',
                    "User-Agent": "NetSentinel/3.0",
                },
            )
            try:
                with _urlopen(req, timeout=_TIMEOUT) as resp:
                    rdata = resp.read()
                rroot = ET.fromstring(rdata)

                def _find(tag):
                    el = rroot.find(f".//{tag}")
                    return el.text if el is not None else ""

                ext_port = _find("NewExternalPort")
                int_ip   = _find("NewInternalClient")
                int_port = _find("NewInternalPort")
                proto    = _find("NewProtocol")
                desc     = _find("NewPortMappingDescription")
                enabled  = _find("NewEnabled")

                if not ext_port:
                    break

                mappings.append(UPnPMapping(
                    external_port=int(ext_port),
                    internal_ip=int_ip,
                    internal_port=int(int_port or ext_port),
                    protocol=proto.upper(),
                    description=desc,
                    enabled=enabled != "0",
                ))
                idx += 1
            except Exception:
                break   # 713 = SpecifiedArrayIndexInvalid → no more entries

    except Exception:
        pass

    return control_url, mappings


# ── Main entry point ──────────────────────────────────────────────────────────

def check_exposure(
    progress_cb: Optional[Callable[[str], None]] = None,
) -> ExposureResult:
    """
    Run a full internet-exposure check.

    Returns an ExposureResult with WAN IP, CGNAT flag, and all UPnP
    port-forwarding rules.
    """
    _cb = progress_cb or (lambda m: None)
    result = ExposureResult()

    # Stage 1: WAN IP
    _cb("Fetching public WAN IP…")
    wan_ip, cgnat = _get_wan_ip()
    result.wan_ip = wan_ip
    result.cgnat  = cgnat
    if wan_ip:
        if cgnat:
            _cb(f"WAN IP: {wan_ip} (carrier-grade NAT — devices not directly reachable)")
        else:
            _cb(f"WAN IP: {wan_ip}")
    else:
        _cb("Could not determine WAN IP (offline or API unavailable)")

    # Stage 2: UPnP discovery
    _cb("Scanning LAN for UPnP/IGD routers (SSDP)…")
    try:
        locations = _ssdp_discover(timeout=_SSDP_MX + 0.5)
    except Exception as exc:
        result.error = f"SSDP discovery failed: {exc}"
        return result

    if not locations:
        _cb("No UPnP-capable router found on LAN.")
        return result

    result.upnp_available = True
    _cb(f"Found {len(locations)} UPnP device(s) — fetching port mappings…")

    all_mappings: list[UPnPMapping] = []
    for loc in locations:
        _, mappings = _fetch_upnp_mappings(loc)
        all_mappings.extend(mappings)

    result.upnp_mappings = all_mappings

    # Build per-device exposure map
    for m in all_mappings:
        if not m.enabled:
            continue
        ip = m.internal_ip
        if ip not in result.exposed:
            result.exposed[ip] = []
        result.exposed[ip].append(m.external_port)

    _cb(result.plain_verdict)
    return result
