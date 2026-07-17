"""
protocol_frames — shared FrameLayer constructor helpers for the ten protocol_animator
scene builders (Phase A2 — Frame Anatomy inspector).

Pure functions, no PyQt imports. Each constructor returns a FrameLayer with a
fixed, consistent field-name vocabulary (Src MAC/Dst MAC, Src IP/Dst IP, Src
Port/Dst Port, TTL, Flags, Seq/Ack, EtherType) so the Frame Anatomy panel reads
the same across every protocol.

FrameLayer is defined in this module (not protocol_animator.py, which imports
it from here) so this module has zero dependency — at any level, including
TYPE_CHECKING — on protocol_animator.py, which imports these constructors at
module level. A prior version dodged the cycle with a TYPE_CHECKING-guarded
back-import, which satisfies our own tools/check_import_lint.py (it exempts
TYPE_CHECKING blocks) but not CodeQL's py/unsafe-cyclic-import query, which
does not grant the same exemption.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class FrameLayer:
    name:   str                    # "Ethernet II", "IPv4", "UDP", "DHCP"
    fields: List[tuple[str, str]]  # [("Src MAC", "AA:BB:…"), ("EtherType", "0x0806")]


def _mac_or_placeholder(mac: str) -> str:
    return (mac or "??:??:??:??:??:??").upper()


def _ip_or_placeholder(ip: str) -> str:
    return ip or "0.0.0.0"


def ethernet_layer(
    src_mac: str, dst_mac: str, ethertype: str, ethertype_label: str = ""
) -> FrameLayer:
    et = f"{ethertype} ({ethertype_label})" if ethertype_label else ethertype
    return FrameLayer("Ethernet II", [
        ("Src MAC", _mac_or_placeholder(src_mac)),
        ("Dst MAC", _mac_or_placeholder(dst_mac)),
        ("EtherType", et),
    ])


def ipv4_layer(
    src_ip: str, dst_ip: str, ttl: int = 64, proto: str = "", flags: str = ""
) -> FrameLayer:
    fields = [
        ("Src IP", _ip_or_placeholder(src_ip)),
        ("Dst IP", _ip_or_placeholder(dst_ip)),
        ("TTL", str(ttl)),
    ]
    if proto:
        fields.append(("Protocol", proto))
    if flags:
        fields.append(("Flags", flags))
    return FrameLayer("IPv4", fields)


def udp_layer(src_port, dst_port, length: Optional[int] = None) -> FrameLayer:
    fields = [("Src Port", str(src_port)), ("Dst Port", str(dst_port))]
    if length is not None:
        fields.append(("Length", str(length)))
    return FrameLayer("UDP", fields)


def tcp_layer(src_port, dst_port, flags: str, seq, ack=None) -> FrameLayer:
    fields = [
        ("Src Port", str(src_port)),
        ("Dst Port", str(dst_port)),
        ("Flags", flags),
        ("Seq", str(seq)),
    ]
    if ack is not None:
        fields.append(("Ack", str(ack)))
    return FrameLayer("TCP", fields)


def find_mac_for_ip(devices: list, ip: str) -> str:
    """Look up a real MAC from the scan's device list for *ip*, or "" if unknown.

    Mirrors the dict/attr dual-access pattern already used inline throughout
    protocol_animator.py — devices may be plain dicts (from a scan result payload)
    or DeviceInfo-like objects (modules/rogue_device.py).
    """
    if not ip:
        return ""
    for d in (devices or []):
        d_ip = d.get("ip", "") if isinstance(d, dict) else getattr(d, "ip", "")
        if d_ip == ip:
            d_mac = d.get("mac", "") if isinstance(d, dict) else getattr(d, "mac", "")
            return d_mac or ""
    return ""
