"""
LLDP (Link Layer Discovery Protocol) and CDP neighbor scanner.

Passive mode (default): sniffs for LLDP frames already on the wire — works
on any interface where LLDP is active on connected managed switches.
Active mode (admin/Npcap required): sends an LLDP announcement frame first to
solicit responses from switches that only transmit on request.

Key decision: parse TLVs from raw bytes instead of scapy's LLDP contrib layer
stack.  This avoids version-specific scapy API surface while still using scapy
for the low-level capture (sniff/sendp).  The capture filter keeps CPU load low
even on busy links.
"""
from __future__ import annotations

import logging
import socket
from dataclasses import dataclass, field
from typing import Dict, List

log = logging.getLogger(__name__)

_LLDP_MULTICAST = "01:80:c2:00:00:0e"
_LLDP_ETHERTYPE  = 0x88CC

# LLDP TLV type numbers (RFC 8520 / IEEE 802.1AB)
_TLV_END        = 0
_TLV_CHASSIS_ID = 1
_TLV_PORT_ID    = 2
_TLV_TTL        = 3
_TLV_SYS_NAME   = 5
_TLV_SYS_DESC   = 6
_TLV_SYS_CAP    = 7
_TLV_MGMT_ADDR  = 8

# System-capability bit→name mapping (IEEE 802.1AB Table 9-4)
_CAP_NAMES: Dict[int, str] = {
    0: "other",
    1: "repeater",
    2: "bridge",
    3: "wlan-ap",
    4: "router",
    5: "telephone",
    6: "docsis",
    7: "station",
}


@dataclass
class LldpNeighbor:
    local_ip: str           # IP of the interface that received this frame
    neighbor_ip: str        # neighbor's management IP (empty if not advertised)
    neighbor_hostname: str  # from System Name TLV
    neighbor_port: str      # from Port ID TLV
    ttl: int                # from TTL TLV (seconds)
    chassis_id: str         # from Chassis ID TLV (MAC or string)
    capabilities: List[str] = field(default_factory=list)  # ["bridge", "router", …]

    @property
    def is_infrastructure(self) -> bool:
        """True when the neighbor advertises bridge or router capability."""
        return bool({"bridge", "router"} & set(self.capabilities))


# ── raw TLV parser ────────────────────────────────────────────────────────────

def _parse_lldp_tlvs(payload: bytes) -> dict:
    """
    Walk LLDP TLVs from raw *payload* bytes (everything after the Ethernet header).

    Returns a dict with keys: chassis_id, port_id, ttl, sys_name, sys_desc,
    capabilities (list[str]), mgmt_ip (str).
    """
    result: dict = {
        "chassis_id":   "",
        "port_id":      "",
        "ttl":          0,
        "sys_name":     "",
        "sys_desc":     "",
        "capabilities": [],
        "mgmt_ip":      "",
    }
    i = 0
    while i + 2 <= len(payload):
        header  = (payload[i] << 8) | payload[i + 1]
        tlv_type = (header >> 9) & 0x7F
        tlv_len  = header & 0x1FF
        i += 2
        if tlv_type == _TLV_END:
            break
        if i + tlv_len > len(payload):
            break
        value = payload[i: i + tlv_len]
        i += tlv_len

        try:
            if tlv_type == _TLV_CHASSIS_ID and tlv_len > 1:
                subtype = value[0]
                data    = value[1:]
                if subtype == 4 and len(data) >= 6:  # MAC address
                    result["chassis_id"] = ":".join(f"{b:02x}" for b in data[:6])
                else:
                    result["chassis_id"] = data.decode("utf-8", errors="replace").strip()

            elif tlv_type == _TLV_PORT_ID and tlv_len > 1:
                result["port_id"] = value[1:].decode("utf-8", errors="replace").strip()

            elif tlv_type == _TLV_TTL and tlv_len == 2:
                result["ttl"] = (value[0] << 8) | value[1]

            elif tlv_type == _TLV_SYS_NAME:
                result["sys_name"] = value.decode("utf-8", errors="replace").strip()

            elif tlv_type == _TLV_SYS_DESC:
                result["sys_desc"] = value.decode("utf-8", errors="replace").strip()

            elif tlv_type == _TLV_SYS_CAP and tlv_len >= 4:
                # Bytes 0-1: system capabilities; bytes 2-3: enabled capabilities
                enabled = (value[2] << 8) | value[3]
                caps = [name for bit, name in _CAP_NAMES.items() if enabled & (1 << bit)]
                result["capabilities"] = caps

            elif tlv_type == _TLV_MGMT_ADDR and tlv_len >= 3:
                addr_str_len = value[0]  # includes subtype byte
                addr_subtype = value[1]
                addr_bytes   = value[2: 2 + addr_str_len - 1]
                if addr_subtype == 1 and len(addr_bytes) == 4:   # IPv4
                    result["mgmt_ip"] = ".".join(str(b) for b in addr_bytes)
                elif addr_subtype == 2 and len(addr_bytes) == 16:  # IPv6
                    try:
                        result["mgmt_ip"] = socket.inet_ntop(socket.AF_INET6, addr_bytes)
                    except Exception:
                        pass  # non-fatal — leave mgmt_ip empty
        except Exception:
            pass  # non-fatal — skip malformed TLV, continue to next

    return result


# ── packet helpers ────────────────────────────────────────────────────────────

def _get_local_ip(iface: str) -> str:
    """Return the first IPv4 address bound to *iface*, or empty string."""
    try:
        from scapy.utils import get_if_addr
        addr = get_if_addr(iface)
        return addr if addr and addr != "0.0.0.0" else ""
    except Exception:
        return ""  # non-fatal — fall back to empty


def _send_lldp_frame(iface: str, local_mac: str) -> None:
    """
    Transmit a minimal LLDP announcement frame on *iface*.

    Requires admin / Npcap raw-send permission.  Failure is silently swallowed
    by the caller — active probing is best-effort.
    """
    from scapy.layers.l2 import Ether
    from scapy.sendrecv import sendp

    mac_bytes = bytes(int(b, 16) for b in local_mac.split(":"))

    def _tlv(tlv_type: int, value: bytes) -> bytes:
        length = len(value)
        header = ((tlv_type & 0x7F) << 9) | (length & 0x1FF)
        return bytes([(header >> 8) & 0xFF, header & 0xFF]) + value

    lldpdu = (
        _tlv(_TLV_CHASSIS_ID, b"\x04" + mac_bytes)
        + _tlv(_TLV_PORT_ID,  b"\x05" + b"NetSentinel")
        + _tlv(_TLV_TTL,      bytes([0, 30]))
        + _tlv(_TLV_END,      b"")
    )
    frame = Ether(dst=_LLDP_MULTICAST, src=local_mac, type=_LLDP_ETHERTYPE) / lldpdu
    sendp(frame, iface=iface, verbose=False, count=1)


# ── public API ────────────────────────────────────────────────────────────────

def scan_lldp_neighbors(
    iface: str,
    timeout: int = 10,
    passive: bool = True,
    progress_cb=None,
) -> List[LldpNeighbor]:
    """
    Discover LLDP neighbors on *iface*.

    passive=True  — sniff only; no frames sent.
    passive=False — send an LLDP frame first, then sniff (requires admin/Npcap).

    progress_cb(str) is called approximately every 3 seconds with a status
    message, making it easy to wire into a QThread progress signal.

    Returns a list of LldpNeighbor objects (possibly empty).
    Raises ImportError when scapy is not installed (caller handles gracefully).
    """
    from scapy.sendrecv import sniff
    from scapy.layers.l2 import Ether

    local_ip  = _get_local_ip(iface)
    neighbors: List[LldpNeighbor] = []
    seen_chassis: set = set()

    if not passive:
        try:
            from scapy.utils import get_if_hwaddr
            local_mac = get_if_hwaddr(iface)
            _send_lldp_frame(iface, local_mac)
            log.debug("LLDP: sent active announcement on %s", iface)
        except Exception as exc:
            log.debug("LLDP active send failed on %s: %s", iface, exc)

    if progress_cb:
        progress_cb(f"LLDP: listening on {iface} for {timeout}s…")

    # Sniff in short bursts so we can emit progress ticks
    collected = []
    slice_s   = min(3, timeout)
    elapsed   = 0
    while elapsed < timeout:
        batch = sniff(
            iface=iface,
            filter="ether proto 0x88cc",
            timeout=slice_s,
            store=True,
            count=0,
        )
        collected.extend(batch)
        elapsed += slice_s
        if progress_cb and elapsed < timeout:
            progress_cb(f"LLDP: {len(collected)} frame(s), {timeout - elapsed}s remaining…")

    for pkt in collected:
        try:
            if not pkt.haslayer(Ether):
                continue
            eth      = pkt[Ether]
            src_mac  = eth.src
            raw_lldp = bytes(eth.payload)
            tlvs     = _parse_lldp_tlvs(raw_lldp)
            chassis  = tlvs["chassis_id"] or src_mac
            if chassis in seen_chassis:
                continue
            seen_chassis.add(chassis)
            neighbors.append(LldpNeighbor(
                local_ip=local_ip,
                neighbor_ip=tlvs["mgmt_ip"],
                neighbor_hostname=tlvs["sys_name"] or tlvs["sys_desc"][:40] or chassis,
                neighbor_port=tlvs["port_id"],
                ttl=tlvs["ttl"],
                chassis_id=chassis,
                capabilities=tlvs["capabilities"],
            ))
        except Exception:
            pass  # non-fatal — skip malformed frames

    log.debug("LLDP scan on %s: found %d neighbor(s)", iface, len(neighbors))
    return neighbors
