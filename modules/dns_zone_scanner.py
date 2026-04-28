"""
dns_zone_scanner.py — DNS zone mapping (item 18).

Two discovery modes:
  1. AXFR zone transfer — attempts a full zone transfer from a specified
     DNS server for a given domain.  Most external/ISP resolvers block this;
     it works on internal BIND/PowerDNS/Unbound servers that allow AXFR.
  2. mDNS service enumeration — queries _services._dns-sd._udp.local on the
     LAN to enumerate Bonjour/Avahi service types, then resolves each type
     to get concrete PTR/SRV/A records.

Returns a DnsZoneResult with:
  records   — list of DnsRecord (name, rtype, value, ttl)
  services  — list of MdnsService (service_type, instance, host, ip, port)
  verdict   — plain-English summary
  level     — "CLEAN" | "LOW" | "HIGH"
"""

from __future__ import annotations

import socket
import struct
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class DnsRecord:
    name:  str = ""
    rtype: str = ""    # A, AAAA, CNAME, MX, PTR, SRV, TXT, NS, SOA, …
    value: str = ""
    ttl:   int = 0


@dataclass
class MdnsService:
    service_type: str = ""
    instance:     str = ""
    host:         str = ""
    ip:           str = ""
    port:         int = 0
    txt:          str = ""


@dataclass
class DnsZoneResult:
    records:  List[DnsRecord]   = field(default_factory=list)
    services: List[MdnsService] = field(default_factory=list)
    verdict:  str               = ""
    level:    str               = "CLEAN"
    axfr_ok:  bool              = False


# ── Minimal DNS message parser ────────────────────────────────────────────────

_QTYPE_NAMES = {
    1: "A", 2: "NS", 5: "CNAME", 6: "SOA", 12: "PTR",
    15: "MX", 16: "TXT", 28: "AAAA", 33: "SRV",
}


def _decode_name(data: bytes, offset: int) -> tuple[str, int]:
    """Decode a DNS name with pointer compression support."""
    labels: list[str] = []
    visited: set[int] = set()
    while offset < len(data):
        if offset in visited:
            break
        visited.add(offset)
        length = data[offset]
        if length == 0:
            offset += 1
            break
        if (length & 0xC0) == 0xC0:
            if offset + 1 >= len(data):
                break
            ptr = ((length & 0x3F) << 8) | data[offset + 1]
            sub, _ = _decode_name(data, ptr)
            labels.append(sub)
            offset += 2
            break
        labels.append(data[offset + 1: offset + 1 + length].decode(errors="replace"))
        offset += 1 + length
    return ".".join(labels), offset


def _parse_rdata(rtype: int, data: bytes, offset: int, rdlen: int) -> str:
    end = offset + rdlen
    try:
        if rtype == 1:   # A
            if rdlen == 4:
                return socket.inet_ntoa(data[offset:end])
        elif rtype == 28:  # AAAA
            if rdlen == 16:
                return socket.inet_ntop(socket.AF_INET6, data[offset:end])
        elif rtype in (2, 5, 12):  # NS, CNAME, PTR
            name, _ = _decode_name(data, offset)
            return name
        elif rtype == 15:  # MX
            pref = struct.unpack_from(">H", data, offset)[0]
            name, _ = _decode_name(data, offset + 2)
            return f"{pref} {name}"
        elif rtype == 16:  # TXT
            txts = []
            pos = offset
            while pos < end:
                slen = data[pos]; pos += 1
                txts.append(data[pos:pos + slen].decode(errors="replace"))
                pos += slen
            return " | ".join(txts)
        elif rtype == 33:  # SRV
            priority, weight, port = struct.unpack_from(">HHH", data, offset)
            target, _ = _decode_name(data, offset + 6)
            return f"{priority} {weight} {port} {target}"
        elif rtype == 6:   # SOA
            mname, pos2 = _decode_name(data, offset)
            rname, _    = _decode_name(data, pos2)
            return f"{mname} {rname}"
    except Exception:
        pass
    return data[offset:end].hex()


def _parse_dns_response(data: bytes) -> List[DnsRecord]:
    """Parse all Answer/Authority/Additional RRs from a raw DNS message."""
    records: List[DnsRecord] = []
    if len(data) < 12:
        return records
    try:
        _, flags, qdcount, ancount, nscount, arcount = struct.unpack_from(">HHHHHH", data, 0)
        offset = 12
        # Skip questions
        for _ in range(qdcount):
            _, offset = _decode_name(data, offset)
            offset += 4   # QTYPE + QCLASS
        # Parse RR sections
        for _ in range(ancount + nscount + arcount):
            if offset >= len(data):
                break
            name, offset = _decode_name(data, offset)
            if offset + 10 > len(data):
                break
            rtype, rclass, ttl, rdlen = struct.unpack_from(">HHIH", data, offset)
            offset += 10
            if rclass not in (1, 32769):   # IN or cache-flush
                offset += rdlen
                continue
            rdata = _parse_rdata(rtype, data, offset, rdlen)
            offset += rdlen
            records.append(DnsRecord(
                name=name,
                rtype=_QTYPE_NAMES.get(rtype, str(rtype)),
                value=rdata,
                ttl=ttl,
            ))
    except Exception:
        pass
    return records


# ── AXFR zone transfer ────────────────────────────────────────────────────────

def axfr_transfer(
    server: str,
    domain: str,
    timeout: float = 10.0,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> List[DnsRecord]:
    """
    Attempt a DNS zone transfer (AXFR) for *domain* from *server*.

    Uses raw TCP DNS (port 53) so no external library is needed.
    Returns an empty list if the server refuses or the network is unreachable.
    """
    records: List[DnsRecord] = []
    if progress_cb:
        progress_cb(f"Attempting AXFR for {domain} from {server}…")
    try:
        # Build AXFR query
        qname = b"".join(
            bytes([len(part)]) + part.encode()
            for part in domain.rstrip(".").split(".")
        ) + b"\x00"
        query_body = (
            b"\x00\x01"   # ID
            b"\x00\x00"   # Flags: standard query
            b"\x00\x01"   # QDCOUNT: 1
            b"\x00\x00"   # ANCOUNT
            b"\x00\x00"   # NSCOUNT
            b"\x00\x00"   # ARCOUNT
            + qname
            + b"\x00\xfc"  # QTYPE: AXFR (252)
            + b"\x00\x01"  # QCLASS: IN
        )
        # TCP: 2-byte length prefix
        msg = struct.pack(">H", len(query_body)) + query_body

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((server, 53))
        sock.sendall(msg)

        buf = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buf += chunk
        sock.close()

        # Parse multi-message TCP response (each prefixed with 2-byte length)
        pos = 0
        soa_count = 0
        while pos + 2 <= len(buf):
            msg_len = struct.unpack_from(">H", buf, pos)[0]
            pos += 2
            if pos + msg_len > len(buf):
                break
            recs = _parse_dns_response(buf[pos: pos + msg_len])
            pos += msg_len
            for r in recs:
                if r.rtype == "SOA":
                    soa_count += 1
                    if soa_count == 2:
                        break   # AXFR ends at second SOA
                records.append(r)
            if soa_count == 2:
                break

    except Exception:
        pass

    if progress_cb:
        progress_cb(f"AXFR complete: {len(records)} record(s) received.")
    return records


# ── mDNS service enumeration ──────────────────────────────────────────────────

_MDNS_ADDR = "224.0.0.251"
_MDNS_PORT = 5353


def _build_mdns_query(qname_encoded: bytes, qtype: int = 12) -> bytes:
    return (
        b"\x00\x00"   # ID
        b"\x00\x00"   # Flags
        b"\x00\x01"   # Questions: 1
        b"\x00\x00" * 3
        + qname_encoded
        + struct.pack(">HH", qtype, 0x8001)   # QTYPE, QCLASS unicast
    )


def _encode_qname(name: str) -> bytes:
    out = b""
    for label in name.rstrip(".").split("."):
        encoded = label.encode()
        out += bytes([len(encoded)]) + encoded
    return out + b"\x00"


def mdns_enumerate(
    timeout: float = 3.0,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> List[MdnsService]:
    """
    Query _services._dns-sd._udp.local to get the list of service types on
    the LAN, then query each type for PTR records, and SRV/A records per
    instance.  Returns a list of MdnsService objects.
    """
    if progress_cb:
        progress_cb("Enumerating mDNS services…")

    services: List[MdnsService] = []

    try:
        # Step 1: get service types from _services._dns-sd._udp.local
        q = _encode_qname("_services._dns-sd._udp.local")
        query = _build_mdns_query(q)

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(timeout)
        sock.sendto(query, (_MDNS_ADDR, _MDNS_PORT))

        service_types: list[str] = []
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                data, _ = sock.recvfrom(4096)
                for rec in _parse_dns_response(data):
                    if rec.rtype == "PTR" and rec.value and rec.value not in service_types:
                        service_types.append(rec.value)
            except socket.timeout:
                break
            except Exception:
                break
        sock.close()

        if progress_cb:
            progress_cb(f"Found {len(service_types)} service type(s), resolving instances…")

        # Step 2: query each service type for instances (PTR records)
        instance_to_type: dict[str, str] = {}
        for stype in service_types:
            try:
                q2   = _encode_qname(stype)
                msg2 = _build_mdns_query(q2)
                s2   = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
                s2.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s2.settimeout(min(timeout, 2.0))
                s2.sendto(msg2, (_MDNS_ADDR, _MDNS_PORT))
                ddl = time.monotonic() + min(timeout, 2.0)
                while time.monotonic() < ddl:
                    try:
                        data2, _ = s2.recvfrom(4096)
                        for rec in _parse_dns_response(data2):
                            if rec.rtype == "PTR" and rec.value:
                                instance_to_type[rec.value] = stype
                    except socket.timeout:
                        break
                    except Exception:
                        break
                s2.close()
            except Exception:
                pass

        # Step 3: for each instance, gather SRV + A/AAAA
        instance_details: dict[str, dict] = {}
        for instance in instance_to_type:
            try:
                q3   = _encode_qname(instance)
                msg3 = _build_mdns_query(q3, qtype=255)  # ANY
                s3   = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
                s3.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s3.settimeout(min(timeout, 2.0))
                s3.sendto(msg3, (_MDNS_ADDR, _MDNS_PORT))
                info: dict = {"host": "", "ip": "", "port": 0, "txt": ""}
                ddl = time.monotonic() + min(timeout, 2.0)
                while time.monotonic() < ddl:
                    try:
                        data3, addr3 = s3.recvfrom(4096)
                        for rec in _parse_dns_response(data3):
                            if rec.rtype == "SRV":
                                parts = rec.value.split()
                                if len(parts) >= 4:
                                    try:
                                        info["port"] = int(parts[2])
                                    except ValueError:
                                        pass
                                    info["host"] = parts[3]
                            elif rec.rtype == "A":
                                info["ip"] = rec.value
                            elif rec.rtype == "TXT":
                                info["txt"] = rec.value
                        if not info["ip"]:
                            info["ip"] = addr3[0]
                    except socket.timeout:
                        break
                    except Exception:
                        break
                s3.close()
                instance_details[instance] = info
            except Exception:
                pass

        # Build MdnsService list
        for instance, stype in instance_to_type.items():
            info = instance_details.get(instance, {})
            services.append(MdnsService(
                service_type=stype,
                instance=instance,
                host=info.get("host", ""),
                ip=info.get("ip", ""),
                port=info.get("port", 0),
                txt=info.get("txt", ""),
            ))

    except Exception:
        pass

    if progress_cb:
        progress_cb(f"mDNS enumeration complete: {len(services)} service(s).")
    return services


# ── Public entry point ────────────────────────────────────────────────────────

def scan(
    axfr_server: str = "",
    axfr_domain: str = "",
    axfr_timeout: float = 10.0,
    mdns_timeout: float = 3.0,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> DnsZoneResult:
    """
    Run AXFR (if server + domain provided) and mDNS enumeration in sequence.
    Returns a DnsZoneResult.  Never raises.
    """
    result = DnsZoneResult()

    # AXFR
    if axfr_server and axfr_domain:
        try:
            result.records = axfr_transfer(axfr_server, axfr_domain, axfr_timeout, progress_cb)
            result.axfr_ok = len(result.records) > 0
        except Exception:
            pass

    # mDNS
    try:
        result.services = mdns_enumerate(mdns_timeout, progress_cb)
    except Exception:
        pass

    # Verdict
    n_rec  = len(result.records)
    n_svc  = len(result.services)
    if n_rec == 0 and n_svc == 0:
        result.verdict = "No DNS zone data found. Try providing a DNS server for AXFR."
        result.level   = "LOW"
    elif not result.axfr_ok and axfr_server:
        result.verdict = (
            f"AXFR refused by {axfr_server}. "
            f"{n_svc} mDNS service(s) discovered on the LAN."
        )
        result.level = "LOW"
    else:
        result.verdict = (
            f"{n_rec} DNS record(s) via AXFR, "
            f"{n_svc} mDNS service(s) on LAN."
        )
        result.level = "CLEAN"

    return result
