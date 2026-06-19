"""
SNMP basic poller (SNMPv1/v2c, community=public).

Uses only the standard library — no pysnmp dependency.
Implements a minimal SNMP GET via raw UDP so it works in PyInstaller
bundles without additional packages.

Polls a small set of informational OIDs:
  sysDescr   .1.3.6.1.2.1.1.1.0  — device description / OS
  sysUpTime  .1.3.6.1.2.1.1.3.0  — uptime in hundredths of a second
  sysName    .1.3.6.1.2.1.1.5.0  — configured hostname
  sysContact .1.3.6.1.2.1.1.4.0  — contact info
  ifNumber   .1.3.6.1.2.1.2.1.0  — number of interfaces
"""

import socket
import struct
from dataclasses import dataclass
from typing import Dict, List, Optional


# ── BER/ASN.1 minimal encoder/decoder ────────────────────────────────────────

def _encode_oid(oid_str: str) -> bytes:
    """Encode a dotted OID string to BER."""
    parts = [int(x) for x in oid_str.strip(".").split(".")]
    # First two components are encoded as 40*x + y
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


def _ber_length(data: bytes) -> bytes:
    n = len(data)
    if n < 0x80:
        return bytes([n])
    if n < 0x100:
        return bytes([0x81, n])
    return bytes([0x82, (n >> 8) & 0xFF, n & 0xFF])


def _ber_tlv(tag: int, value: bytes) -> bytes:
    return bytes([tag]) + _ber_length(value) + value


def _build_snmp_get(oid_str: str, community: str = "public", request_id: int = 1) -> bytes:
    """Build a minimal SNMPv2c GET-REQUEST packet."""
    oid_bytes   = _encode_oid(oid_str)
    oid_tlv     = _ber_tlv(0x06, oid_bytes)          # OID tag
    null_tlv    = bytes([0x05, 0x00])                  # NULL value
    varbind     = _ber_tlv(0x30, oid_tlv + null_tlv)  # SEQUENCE
    varbind_list= _ber_tlv(0x30, varbind)              # SEQUENCE

    req_id_bytes = struct.pack(">I", request_id)
    req_id_tlv   = _ber_tlv(0x02, req_id_bytes.lstrip(b"\x00") or b"\x00")
    error_tlv    = _ber_tlv(0x02, b"\x00")
    error_idx    = _ber_tlv(0x02, b"\x00")

    pdu = _ber_tlv(0xA0, req_id_tlv + error_tlv + error_idx + varbind_list)  # GetRequest PDU

    version  = _ber_tlv(0x02, b"\x01")               # version = 2c (integer 1)
    comm     = _ber_tlv(0x04, community.encode())     # community string
    message  = _ber_tlv(0x30, version + comm + pdu)   # top SEQUENCE
    return message


def _decode_string(data: bytes, offset: int) -> str:
    """Decode a BER-encoded octet string or integer starting at offset."""
    tag = data[offset]
    offset += 1
    length_byte = data[offset]
    offset += 1
    if length_byte & 0x80:
        num_bytes = length_byte & 0x7F
        length = int.from_bytes(data[offset:offset + num_bytes], "big")
        offset += num_bytes
    else:
        length = length_byte
    value = data[offset:offset + length]
    if tag == 0x02:   # Integer
        return str(int.from_bytes(value, "big"))
    if tag in (0x43, 0x41):  # TimeTicks / Counter
        ticks = int.from_bytes(value, "big")
        seconds = ticks // 100
        h, r = divmod(seconds, 3600)
        m, s = divmod(r, 60)
        return f"{h}h {m}m {s}s"
    # Octet string / OctetString
    try:
        return value.decode("utf-8", errors="replace").strip()
    except Exception:
        return repr(value)


def _snmp_get_single(host: str, oid: str, community: str, timeout: float) -> str:
    """Send one SNMP GET and return the value string."""
    pkt = _build_snmp_get(oid, community)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(timeout)
            s.sendto(pkt, (host, 161))
            resp, _ = s.recvfrom(4096)
        # Walk to the varbind value: skip outer SEQUENCE → version → community → PDU → varbinds
        # This is a simplified parser — works for standard OID responses
        return _decode_last_value(resp)
    except Exception as exc:
        return f"<error: {exc}>"


def _decode_last_value(resp: bytes) -> str:
    """Extract the last value in the varbind list of an SNMP response."""
    try:
        # Find the last OctetString or Integer in the response
        # Simple approach: skip past the OID tag (0x06) and find the next value tag
        i = 0
        last_value = ""
        while i < len(resp) - 2:
            tag = resp[i]
            i += 1
            length_byte = resp[i]
            i += 1
            if length_byte & 0x80:
                n = length_byte & 0x7F
                length = int.from_bytes(resp[i:i + n], "big")
                i += n
            else:
                length = length_byte
            if tag in (0x04, 0x02, 0x41, 0x42, 0x43, 0x44, 0x45, 0x46):
                value = resp[i:i + length]
                if tag == 0x04:
                    last_value = value.decode("utf-8", errors="replace").strip()
                elif tag in (0x41, 0x43):   # Counter32 / TimeTicks
                    ticks = int.from_bytes(value, "big")
                    if tag == 0x43:
                        sec = ticks // 100
                        h, r = divmod(sec, 3600)
                        m, s = divmod(r, 60)
                        last_value = f"{h}h {m}m {s}s"
                    else:
                        last_value = str(ticks)
                else:
                    last_value = str(int.from_bytes(value, "big"))
            i += length
        return last_value or "<no value>"
    except Exception as exc:
        return f"<parse error: {exc}>"


# ── Data class ────────────────────────────────────────────────────────────────

@dataclass
class SNMPResult:
    host: str
    reachable: bool = False
    sys_descr: str = ""
    sys_name: str = ""
    sys_uptime: str = ""
    sys_contact: str = ""
    if_count: str = ""
    community: str = "public"
    error: str = ""
    plain_verdict: str = ""


# ── Public poll entry point ───────────────────────────────────────────────────

POLL_OIDS: Dict[str, str] = {
    "sys_descr":   "1.3.6.1.2.1.1.1.0",
    "sys_uptime":  "1.3.6.1.2.1.1.3.0",
    "sys_name":    "1.3.6.1.2.1.1.5.0",
    "sys_contact": "1.3.6.1.2.1.1.4.0",
    "if_count":    "1.3.6.1.2.1.2.1.0",
}


def poll(
    host: str,
    community: str = "public",
    timeout: float = 2.0,
    progress_cb=None,
) -> SNMPResult:
    """Poll a single host for basic SNMP info."""
    _cb = progress_cb or (lambda m: None)
    result = SNMPResult(host=host, community=community)

    _cb(f"SNMP polling {host}…")
    for field_name, oid in POLL_OIDS.items():
        val = _snmp_get_single(host, oid, community, timeout)
        if "<error" not in val:
            result.reachable = True
        setattr(result, field_name, val)

    if result.reachable:
        result.plain_verdict = (
            f"SNMP OK on {host}: {result.sys_name or '?'} — "
            f"{result.sys_descr[:80] if result.sys_descr else 'no description'} — "
            f"uptime {result.sys_uptime}"
        )
    else:
        result.error = f"No SNMP response from {host} (community='{community}', port 161)"
        result.plain_verdict = (
            f"No SNMP response from {host}. "
            "Device may not have SNMP enabled or community string may be wrong."
        )
    return result


# ── ifTable error polling ─────────────────────────────────────────────────────

# OID base paths for ifTable (RFC 1213 MIB-II)
_IF_DESCR_BASE    = "1.3.6.1.2.1.2.2.1.2"    # ifDescr
_IF_IN_ERRORS     = "1.3.6.1.2.1.2.2.1.14"   # ifInErrors
_IF_OUT_ERRORS    = "1.3.6.1.2.1.2.2.1.20"   # ifOutErrors
_IF_IN_DISCARDS   = "1.3.6.1.2.1.2.2.1.13"   # ifInDiscards
_IF_OUT_DISCARDS  = "1.3.6.1.2.1.2.2.1.19"   # ifOutDiscards


def _snmp_get_int(host: str, oid: str, community: str, timeout: float) -> Optional[int]:
    """GET a single Counter32/Integer OID and return it as int, or None on error."""
    raw = _snmp_get_single(host, oid, community, timeout)
    if "<error" in raw or "<parse" in raw or "<no" in raw:
        return None
    try:
        return int(raw.replace(",", "").strip())
    except ValueError:
        return None


@dataclass
class IfErrorEntry:
    """Per-interface error and discard counters from SNMP ifTable."""
    if_index:    int
    if_descr:    str     = ""
    in_errors:   int     = 0
    out_errors:  int     = 0
    in_discards: int     = 0
    out_discards: int    = 0

    @property
    def total_issues(self) -> int:
        return self.in_errors + self.out_errors + self.in_discards + self.out_discards

    @property
    def has_issues(self) -> bool:
        return self.total_issues > 0


def poll_if_errors(
    host: str,
    community: str = "public",
    timeout: float = 2.0,
    max_interfaces: int = 64,
) -> List[IfErrorEntry]:
    """Poll per-interface error and discard counters via SNMP GET.

    Uses ifNumber to bound the index range, then GETs each OID individually.
    Returns a list of IfErrorEntry sorted by ifIndex.  Empty list if host
    does not respond or SNMP is not enabled.
    """
    if_count_str = _snmp_get_single(host, "1.3.6.1.2.1.2.1.0", community, timeout)
    try:
        n = min(int(if_count_str), max_interfaces)
    except (ValueError, TypeError):
        n = max_interfaces

    entries: List[IfErrorEntry] = []
    for idx in range(1, n + 1):
        descr_raw = _snmp_get_single(host, f"{_IF_DESCR_BASE}.{idx}", community, timeout)
        if "<error" in descr_raw:
            continue  # interface index may not exist — skip
        descr = descr_raw if "<" not in descr_raw else f"if{idx}"
        entry = IfErrorEntry(
            if_index    = idx,
            if_descr    = descr,
            in_errors   = _snmp_get_int(host, f"{_IF_IN_ERRORS}.{idx}",   community, timeout) or 0,
            out_errors  = _snmp_get_int(host, f"{_IF_OUT_ERRORS}.{idx}",  community, timeout) or 0,
            in_discards = _snmp_get_int(host, f"{_IF_IN_DISCARDS}.{idx}", community, timeout) or 0,
            out_discards= _snmp_get_int(host, f"{_IF_OUT_DISCARDS}.{idx}",community, timeout) or 0,
        )
        entries.append(entry)
    return entries


def poll_hosts(
    hosts: List[str],
    community: str = "public",
    timeout: float = 2.0,
    progress_cb=None,
) -> List[SNMPResult]:
    """Poll multiple hosts and return a list of results."""
    import concurrent.futures
    _cb = progress_cb or (lambda m: None)
    results: List[SNMPResult] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
        futures = {pool.submit(poll, h, community, timeout): h for h in hosts}
        for fut in concurrent.futures.as_completed(futures):
            try:
                results.append(fut.result())
            except Exception as exc:
                results.append(SNMPResult(host=futures[fut], error=str(exc)))
    results.sort(key=lambda r: r.host)
    return results
