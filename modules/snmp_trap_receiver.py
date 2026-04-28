"""
SNMP Trap Receiver — passive UDP listener for SNMPv1 and SNMPv2c traps (T2#10).

Uses only the Python standard library — no pysnmp dependency — so it works
inside a PyInstaller bundle with no extra packages.

Implements a minimal BER/ASN.1 decoder sufficient to extract:
  • Source IP / port
  • SNMP version (v1 / v2c)
  • Community string
  • Trap OID (v2c: snmpTrapOID.0)
  • Trap type mnemonic (v1 generic traps 0–6)
  • Variable bindings (OID → string value)
  • Timestamp

Port 162 requires administrator/root on most OSes.  When not elevated the
receiver falls back to a random high port and records that in `listen_port`.

Architecture rules:
  • Pure Python — zero PyQt imports (ARCH RULE 3)
  • No blocking I/O outside the worker thread
"""

from __future__ import annotations

import socket
import struct
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple


# ── Constants ─────────────────────────────────────────────────────────────────

SNMP_TRAP_PORT   = 162
FALLBACK_PORT    = 16200     # used when not admin
SOCKET_TIMEOUT   = 1.0       # seconds — allows clean shutdown check

# Generic trap type names (SNMPv1)
_V1_TRAP_TYPES = {
    0: "coldStart",
    1: "warmStart",
    2: "linkDown",
    3: "linkUp",
    4: "authenticationFailure",
    5: "egpNeighborLoss",
    6: "enterpriseSpecific",
}


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class SnmpTrap:
    ts:          int                  # Unix timestamp
    src_ip:      str
    src_port:    int
    version:     str                  # "v1" | "v2c"
    community:   str
    trap_oid:    str                  # dotted OID string
    trap_type:   str                  # human-readable type name
    varbinds:    List[Tuple[str,str]] = field(default_factory=list)
    raw_error:   str                  = ""


# ── Minimal BER decoder ───────────────────────────────────────────────────────

class _BerDecodeError(Exception):
    pass


def _encode_oid(oid_str: str) -> bytes:
    """Encode a dotted OID string to BER bytes."""
    parts = [int(x) for x in oid_str.strip(".").split(".")]
    encoded = [40 * parts[0] + parts[1]]
    for part in parts[2:]:
        if part == 0:
            encoded.append(0)
        else:
            buf = []
            while part:
                buf.append(part & 0x7F)
                part >>= 7
            buf.reverse()
            for i, b in enumerate(buf):
                encoded.append(b | (0x80 if i < len(buf) - 1 else 0))
    return bytes(encoded)


def _read_length(data: bytes, offset: int) -> Tuple[int, int]:
    """Return (length, new_offset)."""
    if offset >= len(data):
        raise _BerDecodeError("unexpected end of data reading length")
    first = data[offset]
    offset += 1
    if first < 0x80:
        return first, offset
    num_bytes = first & 0x7F
    if offset + num_bytes > len(data):
        raise _BerDecodeError("truncated length encoding")
    length = int.from_bytes(data[offset:offset + num_bytes], "big")
    return length, offset + num_bytes


def _read_tlv(data: bytes, offset: int) -> Tuple[int, bytes, int]:
    """Return (tag, value_bytes, new_offset)."""
    if offset >= len(data):
        raise _BerDecodeError("unexpected end reading TLV")
    tag = data[offset]
    offset += 1
    length, offset = _read_length(data, offset)
    if offset + length > len(data):
        raise _BerDecodeError(f"TLV value truncated: need {length}, have {len(data)-offset}")
    value = data[offset:offset + length]
    return tag, value, offset + length


def _decode_oid(raw: bytes) -> str:
    """Decode BER OID bytes to dotted string."""
    if not raw:
        return "0.0"
    parts = [raw[0] // 40, raw[0] % 40]
    i = 1
    while i < len(raw):
        val = 0
        while i < len(raw):
            b = raw[i]
            i += 1
            val = (val << 7) | (b & 0x7F)
            if not (b & 0x80):
                break
        parts.append(val)
    return ".".join(str(p) for p in parts)


def _decode_value(tag: int, raw: bytes) -> str:
    """Best-effort value decode to string."""
    try:
        if tag == 0x02:   # INTEGER
            return str(int.from_bytes(raw, "big", signed=True))
        if tag == 0x04:   # OCTET STRING
            try:
                return raw.decode("utf-8", errors="replace")
            except Exception:
                return raw.hex()
        if tag == 0x06:   # OID
            return _decode_oid(raw)
        if tag == 0x40:   # IpAddress
            return ".".join(str(b) for b in raw)
        if tag == 0x41:   # Counter32
            return str(int.from_bytes(raw, "big"))
        if tag == 0x42:   # Gauge32 / Unsigned32
            return str(int.from_bytes(raw, "big"))
        if tag == 0x43:   # TimeTicks
            ticks = int.from_bytes(raw, "big")
            return f"{ticks // 100}s ({ticks} hundredths)"
        if tag == 0x44:   # Opaque
            return raw.hex()
        if tag == 0x46:   # Counter64
            return str(int.from_bytes(raw, "big"))
        if tag == 0x05:   # NULL
            return ""
        return raw.hex()
    except Exception:
        return raw.hex()


# ── Trap decoders ─────────────────────────────────────────────────────────────

def _decode_varbinds(varbind_list_bytes: bytes) -> List[Tuple[str, str]]:
    """Decode the VarBindList sequence into (oid, value) pairs."""
    result: List[Tuple[str, str]] = []
    offset = 0
    while offset < len(varbind_list_bytes):
        tag, vb_bytes, offset = _read_tlv(varbind_list_bytes, offset)
        if tag != 0x30:
            continue
        vb_offset = 0
        oid_tag, oid_raw, vb_offset = _read_tlv(vb_bytes, vb_offset)
        oid_str = _decode_oid(oid_raw) if oid_tag == 0x06 else oid_raw.hex()
        if vb_offset < len(vb_bytes):
            val_tag, val_raw, _ = _read_tlv(vb_bytes, vb_offset)
            val_str = _decode_value(val_tag, val_raw)
        else:
            val_str = ""
        result.append((oid_str, val_str))
    return result


def _decode_v1_trap(pdu_bytes: bytes) -> Tuple[str, str, List[Tuple[str, str]]]:
    """
    Decode SNMPv1 Trap-PDU (tag 0xA4).
    Returns (trap_oid, trap_type_name, varbinds).
    """
    offset = 0
    # enterprise OID
    tag, ent_raw, offset = _read_tlv(pdu_bytes, offset)
    enterprise_oid = _decode_oid(ent_raw) if tag == 0x06 else "?"
    # agent-addr (IpAddress)
    _, _, offset = _read_tlv(pdu_bytes, offset)
    # generic-trap (INTEGER)
    tag, raw, offset = _read_tlv(pdu_bytes, offset)
    generic = int.from_bytes(raw, "big") if tag == 0x02 else 0
    # specific-trap (INTEGER)
    tag, raw, offset = _read_tlv(pdu_bytes, offset)
    specific = int.from_bytes(raw, "big") if tag == 0x02 else 0
    # time-stamp (TimeTicks)
    _, _, offset = _read_tlv(pdu_bytes, offset)
    # varbind list
    _, vbl_bytes, _ = _read_tlv(pdu_bytes, offset)
    varbinds = _decode_varbinds(vbl_bytes)

    trap_type = _V1_TRAP_TYPES.get(generic, f"enterprise({specific})")
    trap_oid  = f"{enterprise_oid}.{specific}" if generic == 6 else enterprise_oid
    return trap_oid, trap_type, varbinds


def _decode_v2c_trap(pdu_bytes: bytes) -> Tuple[str, str, List[Tuple[str, str]]]:
    """
    Decode SNMPv2c Trap-PDU (tag 0xA7).
    Returns (trap_oid, trap_type_name, varbinds).
    """
    offset = 0
    # request-id
    _, _, offset = _read_tlv(pdu_bytes, offset)
    # error-status
    _, _, offset = _read_tlv(pdu_bytes, offset)
    # error-index
    _, _, offset = _read_tlv(pdu_bytes, offset)
    # varbind list sequence
    _, vbl_bytes, _ = _read_tlv(pdu_bytes, offset)
    varbinds = _decode_varbinds(vbl_bytes)

    # snmpTrapOID.0 is the second varbind (index 1)
    trap_oid = varbinds[1][1] if len(varbinds) > 1 else "unknown"
    # Use last component of OID as a mnemonic
    trap_type = trap_oid.rsplit(".", 1)[-1] if trap_oid else "unknown"
    return trap_oid, trap_type, varbinds


def decode_trap_packet(data: bytes, src_ip: str, src_port: int) -> SnmpTrap:
    """
    Decode a raw UDP payload into an SnmpTrap.
    Returns a trap with raw_error set on any parse failure.
    """
    ts = int(time.time())
    try:
        offset = 0
        # Top-level SEQUENCE
        tag, msg_bytes, _ = _read_tlv(data, offset)
        if tag != 0x30:
            raise _BerDecodeError(f"expected SEQUENCE (0x30), got 0x{tag:02X}")
        offset = 0
        # version INTEGER
        tag, raw, offset = _read_tlv(msg_bytes, offset)
        version_int = int.from_bytes(raw, "big") if tag == 0x02 else 0
        version = "v1" if version_int == 0 else "v2c" if version_int == 1 else f"v{version_int}"
        # community OCTET STRING
        tag, raw, offset = _read_tlv(msg_bytes, offset)
        community = raw.decode("utf-8", errors="replace") if tag == 0x04 else "?"
        # PDU
        pdu_tag, pdu_bytes, _ = _read_tlv(msg_bytes, offset)

        if pdu_tag == 0xA4:   # SNMPv1 Trap-PDU
            trap_oid, trap_type, varbinds = _decode_v1_trap(pdu_bytes)
            version = "v1"
        elif pdu_tag == 0xA7:  # SNMPv2c InformRequest
            trap_oid, trap_type, varbinds = _decode_v2c_trap(pdu_bytes)
        elif pdu_tag in (0xA2, 0xA3, 0xA5, 0xA6, 0xA7, 0xA8):
            # Other PDU types — decode as v2c-style
            trap_oid, trap_type, varbinds = _decode_v2c_trap(pdu_bytes)
        else:
            raise _BerDecodeError(f"unexpected PDU tag 0x{pdu_tag:02X}")

        return SnmpTrap(
            ts=ts, src_ip=src_ip, src_port=src_port,
            version=version, community=community,
            trap_oid=trap_oid, trap_type=trap_type,
            varbinds=varbinds,
        )
    except Exception as exc:
        return SnmpTrap(
            ts=ts, src_ip=src_ip, src_port=src_port,
            version="?", community="?",
            trap_oid="?", trap_type="?",
            raw_error=str(exc),
        )


# ── Receiver ──────────────────────────────────────────────────────────────────

class SnmpTrapReceiver:
    """
    Passive UDP SNMP trap receiver.

    Parameters
    ----------
    port : int
        UDP port to listen on.  Default 162 (requires admin).
        Pass 0 to let the OS assign a port (testing).
    bind_address : str
        Interface to bind to.  Default "" = all interfaces.
    on_trap : callable | None
        Called with each decoded SnmpTrap from the receiver thread.
    """

    def __init__(
        self,
        port: int = SNMP_TRAP_PORT,
        bind_address: str = "",
        on_trap: Optional[Callable[[SnmpTrap], None]] = None,
    ):
        self._port         = port
        self._bind_address = bind_address
        self._on_trap      = on_trap
        self._sock: Optional[socket.socket] = None
        self.listen_port: int = port   # updated after bind

    def open(self) -> int:
        """
        Open the UDP socket.  Falls back to FALLBACK_PORT if port 162 fails.
        Returns the actual bound port.
        """
        for attempt_port in (self._port, FALLBACK_PORT):
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.settimeout(SOCKET_TIMEOUT)
                sock.bind((self._bind_address, attempt_port))
                actual_port = sock.getsockname()[1]
                self._sock = sock
                self.listen_port = actual_port
                return actual_port
            except OSError:
                if attempt_port == FALLBACK_PORT:
                    raise
        return self.listen_port   # unreachable

    def receive_one(self) -> Optional[SnmpTrap]:
        """
        Block up to SOCKET_TIMEOUT seconds for one trap.
        Returns the decoded SnmpTrap, or None on timeout.
        """
        if not self._sock:
            raise RuntimeError("call open() before receive_one()")
        try:
            data, (src_ip, src_port) = self._sock.recvfrom(65535)
            trap = decode_trap_packet(data, src_ip, src_port)
            if self._on_trap:
                self._on_trap(trap)
            return trap
        except socket.timeout:
            return None

    def close(self) -> None:
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
