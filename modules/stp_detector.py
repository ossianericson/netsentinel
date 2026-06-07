"""
Module 2 — STP / BPDU Rogue Bridge Detector

Uses Scapy raw packet capture to listen for 802.1D / RSTP / MSTP BPDUs.
Requires administrator / root privileges and Scapy + Npcap (Windows).

Gracefully degrades if Scapy is unavailable or privileges are insufficient.
"""

import struct
import threading
from dataclasses import dataclass, field
from typing import Callable, List, Optional

SCAPY_AVAILABLE = False
try:
    from scapy.all import (  # type: ignore
        AsyncSniffer,
        Ether,
        conf as scapy_conf,
    )
    SCAPY_AVAILABLE = True
except ImportError:
    pass  # non-fatal

# STP multicast destination MAC
STP_MULTICAST = "01:80:c2:00:00:00"
STP_DSAP_SSAP = 0x42


@dataclass
class BPDUInfo:
    src_mac: str
    interface: str
    bpdu_type: str           # "Config", "TCN", "RST", "MST"
    root_priority: int = 0
    root_mac: str = ""
    bridge_priority: int = 0
    bridge_mac: str = ""
    hello_time: float = 0.0
    max_age: float = 0.0
    forward_delay: float = 0.0
    root_path_cost: int = 0
    is_rogue: bool = False
    verdict: str = ""


def _parse_bpdu(raw_payload: bytes, src_mac: str, iface: str) -> Optional[BPDUInfo]:
    """Parse raw LLC+BPDU bytes after the Ethernet header."""
    try:
        # Expect LLC header: DSAP, SSAP, Control (3 bytes)
        if len(raw_payload) < 3:
            return None
        dsap, ssap = raw_payload[0], raw_payload[1]
        if dsap != STP_DSAP_SSAP or ssap != STP_DSAP_SSAP:
            return None

        bpdu = raw_payload[3:]  # skip LLC
        if len(bpdu) < 4:
            return None

        proto_id = struct.unpack_from(">H", bpdu, 0)[0]  # should be 0x0000
        version = bpdu[2]
        bpdu_type_raw = bpdu[3]

        type_map = {0x00: "Config", 0x80: "TCN", 0x02: "RST", 0x03: "MST"}
        bpdu_type = type_map.get(bpdu_type_raw, f"Unknown(0x{bpdu_type_raw:02x})")

        info = BPDUInfo(src_mac=src_mac, interface=iface, bpdu_type=bpdu_type)

        if bpdu_type == "Config" and len(bpdu) >= 35:
            root_pri = struct.unpack_from(">H", bpdu, 5)[0]
            root_mac_bytes = bpdu[7:13]
            root_mac = ":".join(f"{b:02x}" for b in root_mac_bytes)
            root_cost = struct.unpack_from(">I", bpdu, 13)[0]
            bridge_pri = struct.unpack_from(">H", bpdu, 17)[0]
            bridge_mac_bytes = bpdu[19:25]
            bridge_mac = ":".join(f"{b:02x}" for b in bridge_mac_bytes)
            msg_age = struct.unpack_from(">H", bpdu, 27)[0] / 256.0
            max_age = struct.unpack_from(">H", bpdu, 29)[0] / 256.0
            hello_time = struct.unpack_from(">H", bpdu, 31)[0] / 256.0
            fwd_delay = struct.unpack_from(">H", bpdu, 33)[0] / 256.0

            info.root_priority = root_pri
            info.root_mac = root_mac
            info.root_path_cost = root_cost
            info.bridge_priority = bridge_pri
            info.bridge_mac = bridge_mac
            info.hello_time = hello_time
            info.max_age = max_age
            info.forward_delay = fwd_delay

        elif bpdu_type in ("RST", "MST") and len(bpdu) >= 36:
            root_pri = struct.unpack_from(">H", bpdu, 5)[0]
            root_mac_bytes = bpdu[7:13]
            root_mac = ":".join(f"{b:02x}" for b in root_mac_bytes)
            root_cost = struct.unpack_from(">I", bpdu, 13)[0]
            bridge_pri = struct.unpack_from(">H", bpdu, 17)[0]
            bridge_mac_bytes = bpdu[19:25]
            bridge_mac = ":".join(f"{b:02x}" for b in bridge_mac_bytes)
            hello_time = struct.unpack_from(">H", bpdu, 31)[0] / 256.0
            max_age = struct.unpack_from(">H", bpdu, 29)[0] / 256.0
            fwd_delay = struct.unpack_from(">H", bpdu, 33)[0] / 256.0

            info.root_priority = root_pri
            info.root_mac = root_mac
            info.root_path_cost = root_cost
            info.bridge_priority = bridge_pri
            info.bridge_mac = bridge_mac
            info.hello_time = hello_time
            info.max_age = max_age
            info.forward_delay = fwd_delay

        return info
    except Exception:
        return None


class STPSniffer:
    """
    Async BPDU sniffer.  Call start(), then stop() after desired duration.
    Fires on_bpdu callback for each detected BPDU.
    """

    def __init__(
        self,
        gateway_mac: Optional[str],
        on_bpdu: Callable[[BPDUInfo], None],
        on_error: Callable[[str], None],
        timeout: int = 30,
    ):
        self.gateway_mac = (gateway_mac or "").lower()
        self.on_bpdu = on_bpdu
        self.on_error = on_error
        self.timeout = timeout
        self._sniffer = None
        self._seen: List[str] = []

    def _handle_packet(self, pkt):
        try:
            if not pkt.haslayer(Ether):
                return
            eth = pkt[Ether]
            if eth.dst.lower() != STP_MULTICAST:
                return
            # raw payload after Ethernet header
            raw = bytes(pkt)[14:]
            info = _parse_bpdu(raw, eth.src.lower(), pkt.sniffed_on or "?")
            if info is None:
                return

            # Determine if rogue
            if self.gateway_mac and info.root_mac:
                if info.root_mac != self.gateway_mac:
                    info.is_rogue = True
                    info.verdict = (
                        f"ROGUE ROOT BRIDGE: Device {info.src_mac} is advertising "
                        f"itself as the network master (Root Bridge ID: {info.root_mac}, "
                        f"Priority: {info.root_priority}). "
                        f"Your router's uplink port is being blocked every "
                        f"{info.hello_time:.0f}s causing {info.forward_delay:.0f}s outages. "
                        "FIX: Unplug this device's Ethernet cable immediately."
                    )
                else:
                    info.verdict = (
                        f"STP BPDU from {info.src_mac} — Root Bridge matches gateway. "
                        f"Hello Time: {info.hello_time:.1f}s, Forward Delay: {info.forward_delay:.1f}s."
                    )
            else:
                info.verdict = (
                    f"STP BPDU from {info.src_mac} (type: {info.bpdu_type}). "
                    f"Root: {info.root_mac}, Priority: {info.root_priority}."
                )

            self.on_bpdu(info)
        except Exception:
            pass  # non-fatal

    def start(self):
        if not SCAPY_AVAILABLE:
            self.on_error(
                "Scapy is not installed. Install it with: pip install scapy\n"
                "On Windows you also need Npcap from https://npcap.com"
            )
            return
        try:
            self._sniffer = AsyncSniffer(
                filter="ether dst 01:80:c2:00:00:00",
                prn=self._handle_packet,
                store=False,
                timeout=self.timeout,
            )
            self._sniffer.start()
        except Exception as exc:
            self.on_error(
                f"Failed to start packet capture: {exc}\n"
                "Make sure you are running as Administrator/root and Npcap is installed."
            )

    def stop(self):
        try:
            if self._sniffer:
                self._sniffer.stop()
        except Exception:
            pass  # non-fatal


def scan(
    gateway_mac: Optional[str],
    on_bpdu: Callable[[BPDUInfo], None],
    on_error: Callable[[str], None],
    duration: int = 30,
    progress_cb: Optional[Callable[[str], None]] = None,
    stop_event: Optional[threading.Event] = None,
) -> dict:
    """
    Blocking scan — listens for BPDUs for `duration` seconds.
    Fires callbacks for each event.  Returns summary dict.
    """
    if not SCAPY_AVAILABLE:
        msg = (
            "Scapy is not installed.\n"
            "Install: pip install scapy\n"
            "Windows also needs Npcap: https://npcap.com\n"
            "Then restart the tool as Administrator."
        )
        on_error(msg)
        return {"error": msg, "bpdus": []}

    found: List[BPDUInfo] = []
    lock = threading.Lock()

    def _collect(info: BPDUInfo):
        with lock:
            found.append(info)
        on_bpdu(info)

    sniffer = STPSniffer(
        gateway_mac=gateway_mac,
        on_bpdu=_collect,
        on_error=on_error,
        timeout=duration,
    )
    if progress_cb:
        progress_cb(f"Listening for STP/BPDU frames for {duration} seconds...")
    sniffer.start()

    # Wait for sniffer timeout — check stop_event each second for cooperative cancellation
    import time
    for i in range(duration):
        if stop_event and stop_event.is_set():
            if progress_cb:
                progress_cb("STP scan cancelled.")
            break
        time.sleep(1)
        if progress_cb:
            remaining = duration - i - 1
            progress_cb(f"STP scan: {remaining}s remaining...")

    sniffer.stop()

    rogue = [b for b in found if b.is_rogue]
    if rogue:
        plain = (
            f"CONFIRMED THREAT: {len(rogue)} rogue Root Bridge device(s) detected. "
            + " | ".join(b.verdict for b in rogue[:3])
        )
    elif found:
        plain = (
            f"{len(found)} BPDU frame(s) captured. "
            "All Root Bridge IDs match the gateway — no rogue bridges detected."
        )
    else:
        plain = (
            "No STP/BPDU frames detected during the scan window. "
            "This is normal if your network has no managed switches."
        )

    return {
        "bpdus": found,
        "rogue_count": len(rogue),
        "total_bpdus": len(found),
        "plain_verdict": plain,
    }
