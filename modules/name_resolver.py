"""
Name Resolver — multi-method device name lookup.

Resolution order (fastest / most-reliable first):
  1. mac_registry   — local curated OUI→model database (zero latency)
  2. Reverse DNS    — PTR record via system resolver
  3. NetBIOS/WINS   — direct NBSTAT (RFC 1002) UDP query to port 137
  4. mDNS           — query _services._dns-sd._udp.local for device name
  5. SNMP sysName   — SNMP v2c public community read (optional, no admin needed)
  6. DHCP lease file — parse OS DHCP lease files for offered hostnames

All methods run with short timeouts, adaptively scaled from the measured gateway
RTT when the caller supplies a TimingProfile (modules.adaptive_timing, Part 2/L1)
— unscaled otherwise. The caller gets a ``ResolvedName`` with the best available
display name and the source used.
"""

from __future__ import annotations

import concurrent.futures
import platform
import re
import socket
import threading
from contextlib import nullcontext
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from modules.device_classifier import is_randomized_mac
from modules.mac_registry import lookup as mac_lookup

if TYPE_CHECKING:
    from modules.adaptive_timing import TimingProfile


# ── Result type ────────────────────────────────────────────────────────────────

@dataclass
class ResolvedName:
    ip: str
    mac: str = ""
    display_name: str = ""   # best name found
    hostname: str = ""       # raw DNS/NetBIOS/mDNS hostname
    vendor: str = ""
    model: str = ""
    device_type: str = ""
    product_line: str = ""
    source: str = ""         # which method provided display_name
    all_names: list = field(default_factory=list)  # all names found
    mac_randomized: bool = False  # True when U/L bit indicates a randomised MAC

    @property
    def label(self) -> str:
        """
        Human-readable one-liner:
        e.g. "Google Nest Hub (192.168.1.5)" or "living-room-pc (192.168.1.20)"
        """
        name = self.display_name or self.ip
        return f"{name} [{self.ip}]"


# ── Method helpers ─────────────────────────────────────────────────────────────

def _rdns(ip: str, timeout: float = 1.0, _retry: bool = True) -> str:
    """Reverse DNS lookup.

    Retries once, with the same timeout, on a genuine timeout only — a slow
    VPN/corporate DNS hop can miss the deadline for a host that answers the
    very next try (Part 2/L1's retry-once companion, Sprint 2b). A real
    negative answer (socket.herror/gaierror — NXDOMAIN or similar) returns
    fast and is never retried, since retrying it wastes time without
    changing the outcome.

    Uses a manually-managed executor rather than `with` so a reported
    timeout is honest: `ThreadPoolExecutor.__exit__` calls
    `shutdown(wait=True)` even when `.result(timeout=)` already raised
    TimeoutError, which previously meant this function silently blocked
    until the abandoned background call actually finished instead of
    returning at `timeout` seconds. `shutdown(wait=False)` lets that call
    finish on its own without blocking this function.
    """
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        return ex.submit(socket.gethostbyaddr, ip).result(timeout=timeout)[0]
    except concurrent.futures.TimeoutError:
        if _retry:
            return _rdns(ip, timeout, _retry=False)
        return ""
    except Exception:
        return ""  # genuine negative answer (NXDOMAIN etc.) — no retry
    finally:
        ex.shutdown(wait=False)  # non-fatal — abandoned call is bounded by the OS resolver


def rdns(ip: str, timeout: float = 1.0) -> str:
    """Public reverse DNS lookup — canonical entry point for callers outside this module."""
    return _rdns(ip, timeout)


_NBSTAT_WILDCARD_NAME = b"*" + b"\x00" * 15  # 16-byte NetBIOS "adapter status" query name


def _encode_netbios_name(name16: bytes) -> bytes:
    """First-level NetBIOS name encoding (RFC 1001 §14.1): each nibble -> 'A'-'P'."""
    encoded = bytearray()
    for b in name16:
        encoded.append(0x41 + (b >> 4))
        encoded.append(0x41 + (b & 0x0F))
    return bytes(encoded)


def _build_nbstat_query() -> bytes:
    """Build a NODE STATUS (NBSTAT) request — the same query `nbtstat -A` sends,
    as a single UDP datagram instead of a subprocess (Part 2/L2a)."""
    header = b"\x00\x00" + b"\x00\x00" + b"\x00\x01" + b"\x00\x00" + b"\x00\x00" + b"\x00\x00"
    encoded_name = _encode_netbios_name(_NBSTAT_WILDCARD_NAME)
    question_name = bytes([len(encoded_name)]) + encoded_name + b"\x00"
    question = question_name + b"\x00\x21" + b"\x00\x01"  # QTYPE=NBSTAT, QCLASS=IN
    return header + question


def _parse_nbstat_response(data: bytes) -> str:
    """Extract the first UNIQUE <00> (workstation/computer) name from a NODE
    STATUS response — the same target `nbtstat -A`'s `<00> UNIQUE` regex picked."""
    if len(data) < 14:
        return ""
    ancount = int.from_bytes(data[6:8], "big")
    if ancount < 1:
        return ""
    # RR_NAME echoes the query name — either uncompressed (34 bytes, the normal
    # case for this query type) or as a 2-byte DNS compression pointer.
    offset = 12 + 2 if data[12] == 0xC0 else 12 + 34
    offset += 2 + 2 + 4 + 2  # RR_TYPE + RR_CLASS + TTL + RDLENGTH
    if offset >= len(data):
        return ""
    num_names = data[offset]
    offset += 1
    if num_names > 40:  # sanity guard against a malformed/garbage offset
        return ""
    for _ in range(num_names):
        if offset + 18 > len(data):
            break
        raw_name = data[offset:offset + 15]
        suffix = data[offset + 15]
        flags = int.from_bytes(data[offset + 16:offset + 18], "big")
        offset += 18
        group = bool(flags & 0x8000)
        if suffix == 0x00 and not group:
            name = raw_name.decode("ascii", errors="ignore").strip()
            if name:
                return name
    return ""


def _netbios(ip: str, timeout: float = 3.0) -> str:
    """NetBIOS name via a direct NBSTAT (RFC 1002) UDP query to port 137.

    Replaces the previous nbtstat/nmblookup subprocess-per-host spawn — at
    hundreds of devices, OS process creation was plausibly the dominant cost
    of the multi-minute wait (Part 2/L2a). A single UDP datagram is
    cross-platform, so the Windows/Linux branch is gone too.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(timeout)
            sock.sendto(_build_nbstat_query(), (ip, 137))
            data, _ = sock.recvfrom(1024)
        return _parse_nbstat_response(data)
    except Exception:
        return ""  # non-fatal — host may not run NetBIOS, or the query timed out


_MDNS_ZONE_LABELS = {"in-addr", "arpa", "ip6", "local"}


def _mdns_name(ip: str, timeout: float = 1.5) -> str:
    """
    Query mDNS for the .local hostname of an IP by sending a reverse PTR query
    to the multicast address 224.0.0.251:5353.
    """
    try:
        # Build a minimal mDNS PTR query for the in-addr.arpa name
        parts = ip.split(".")
        arpa = ".".join(reversed(parts)) + ".in-addr.arpa"
        # Encode as a DNS question
        labels = arpa.split(".")
        question = b""
        for label in labels:
            enc = label.encode()
            question += bytes([len(enc)]) + enc
        question += b"\x00\x00\x0c\x00\x01"  # type PTR, class IN
        # Transaction ID 0, flags QR=0 (query), 1 question
        header = b"\x00\x00\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00"
        packet = header + question

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(timeout)
            sock.sendto(packet, ("224.0.0.251", 5353))
            data, _ = sock.recvfrom(512)
        # Very naive parse: find a label sequence after the answer section
        # Look for readable ASCII hostname segments
        text = data[12:]
        names = re.findall(rb"[\x01-\x3f]([\x20-\x7e]{2,})", text)
        for n in names:
            s = n.decode(errors="ignore").strip()
            # A responder without a real answer can echo the outgoing PTR
            # question (".in-addr.arpa") back in the payload — those are
            # reverse-DNS zone labels, never a real hostname.
            if s.lower() in _MDNS_ZONE_LABELS:
                continue
            if "." in s or len(s) > 3:
                return s
    except Exception:
        pass  # non-fatal
    return ""


def _snmp_sysname(ip: str, community: str = "public") -> str:
    """SNMP v2c get sysName.0 — no admin needed on most devices."""
    try:
        # OID 1.3.6.1.2.1.1.5.0 = sysName.0
        # Hand-craft a minimal SNMPv2c GetRequest PDU
        def _ber_len(n: int) -> bytes:
            if n < 0x80:
                return bytes([n])
            b = n.to_bytes((n.bit_length() + 7) // 8, "big")
            return bytes([0x80 | len(b)]) + b

        def _oid(oid_str: str) -> bytes:
            parts = list(map(int, oid_str.split(".")))
            body = bytes([40 * parts[0] + parts[1]])
            for p in parts[2:]:
                if p == 0:
                    body += b"\x00"
                else:
                    enc = []
                    while p:
                        enc.append(p & 0x7f)
                        p >>= 7
                    enc.reverse()
                    for i, b_ in enumerate(enc):
                        body += bytes([b_ | (0x80 if i < len(enc) - 1 else 0)])
            return b"\x06" + _ber_len(len(body)) + body

        com = community.encode()
        oid_bytes = _oid("1.3.6.1.2.1.1.5.0")
        # Null value
        null = b"\x05\x00"
        varbind = b"\x30" + _ber_len(len(oid_bytes) + len(null)) + oid_bytes + null
        varbindlist = b"\x30" + _ber_len(len(varbind)) + varbind
        # GetRequest PDU: type 0xa0, req_id, error=0, error_idx=0
        req_id = b"\x02\x01\x01"
        error  = b"\x02\x01\x00"
        erridx = b"\x02\x01\x00"
        pdu_inner = req_id + error + erridx + varbindlist
        pdu = b"\xa0" + _ber_len(len(pdu_inner)) + pdu_inner
        com_str = b"\x04" + _ber_len(len(com)) + com
        version = b"\x02\x01\x01"  # version 2c = 1
        msg_inner = version + com_str + pdu
        msg = b"\x30" + _ber_len(len(msg_inner)) + msg_inner

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(1.5)
            sock.sendto(msg, (ip, 161))
            resp, _ = sock.recvfrom(1024)
        # Parse: find OctetString value after the last OID
        idx = resp.rfind(b"\x04")
        if idx != -1 and idx + 2 < len(resp):
            slen = resp[idx + 1]
            val = resp[idx + 2: idx + 2 + slen].decode(errors="ignore").strip()
            if val and len(val) > 1:
                return val
    except Exception:
        pass  # non-fatal
    return ""


def _dhcp_option12_name(mac: str) -> str:
    """Look up DHCP option 12 hostname from the fingerprint cache (instant, no I/O)."""
    if not mac:
        return ""
    try:
        from modules.dhcp_fingerprint import get_option12_hostname
        return get_option12_hostname(mac)
    except Exception:
        return ""  # non-fatal


def _dhcp_lease_name(ip: str) -> str:
    """Parse OS DHCP lease files for a hostname associated with the IP."""
    system = platform.system()
    candidates = []
    if system == "Windows":
        # Windows stores DHCP leases in the registry — skip file parsing
        return ""
    # Linux
    for path in [
        "/var/lib/dhcp/dhclient.leases",
        "/var/lib/dhcpcd/dhcpcd.leases",
        "/tmp/dhcp.leases",
        "/var/lib/misc/dnsmasq.leases",
    ]:
        try:
            with open(path) as f:
                content = f.read()
            # dnsmasq format: timestamp mac ip hostname client-id
            for line in content.splitlines():
                parts = line.split()
                if len(parts) >= 4 and parts[2] == ip:
                    name = parts[3]
                    if name and name != "*":
                        candidates.append(name)
            # dhclient format
            blocks = re.split(r"lease\s*\{", content)
            for block in blocks:
                if f"fixed-address {ip}" in block:
                    m = re.search(r'option host-name "([^"]+)"', block)
                    if m:
                        candidates.append(m.group(1))
        except Exception:
            pass  # non-fatal
    return candidates[0] if candidates else ""


# ── Public API ─────────────────────────────────────────────────────────────────

def resolve(
    ip: str,
    mac: str = "",
    use_netbios: bool = True,
    use_mdns: bool = True,
    use_snmp: bool = False,
    use_dhcp: bool = True,
    snmp_community: str = "public",
    timing_profile: "TimingProfile | None" = None,
    executor: concurrent.futures.Executor | None = None,
) -> ResolvedName:
    """
    Resolve the best available name for a device.

    Parameters
    ----------
    ip            : Device IP address.
    mac           : Device MAC address (optional but greatly improves results).
    use_netbios   : Query NetBIOS via a direct NBSTAT UDP probe.
    use_mdns      : Query mDNS multicast (works for Chromecasts, printers, etc.).
    use_snmp      : Query SNMP sysName (off by default — can trigger IDS alerts).
    use_dhcp      : Parse local DHCP lease files.
    snmp_community: SNMP community string.
    timing_profile: Gateway-RTT-derived timeouts (modules.adaptive_timing, Part 2/L1).
                    None (the default) uses each probe's own hard-coded timeout,
                    reproducing pre-Sprint-2 behaviour exactly.
    executor      : Shared thread pool for the parallel name-lookup probes
                    (resolve_batch, Part 2/L2b). None (the default) makes
                    resolve() spin up and tear down its own short-lived pool,
                    exactly as before — standalone callers are unaffected.
                    When given, resolve() never shuts it down; the caller
                    that created it owns its lifecycle.

    Returns
    -------
    ResolvedName instance.
    """
    result = ResolvedName(ip=ip, mac=mac)
    result.mac_randomized = is_randomized_mac(mac) if mac else False

    # ── Step 1: MAC registry (instant) ──────────────────────────────────────
    if mac:
        info = mac_lookup(mac)
        if info:
            result.vendor      = info.get("vendor", "")
            result.model       = info.get("model", "")
            result.device_type = info.get("device_type", "")
            result.product_line = info.get("product_line", "")

    # ── Steps 2-6: name lookups in parallel ──────────────────────────────────
    futures: dict = {}
    pool_cm = (
        nullcontext(executor) if executor is not None
        else concurrent.futures.ThreadPoolExecutor(max_workers=6)
    )
    with pool_cm as pool:
        rdns_timeout    = timing_profile.rdns_timeout    if timing_profile else 1.0
        netbios_timeout = timing_profile.netbios_timeout if timing_profile else 3.0
        mdns_timeout    = timing_profile.mdns_timeout    if timing_profile else 1.5
        futures["rdns"]   = pool.submit(_rdns, ip, timeout=rdns_timeout)
        if use_netbios:
            futures["netbios"] = pool.submit(_netbios, ip, timeout=netbios_timeout)
        if use_mdns:
            futures["mdns"]    = pool.submit(_mdns_name, ip, timeout=mdns_timeout)
        if use_snmp:
            futures["snmp"]    = pool.submit(_snmp_sysname, ip, snmp_community)
        if use_dhcp:
            futures["dhcp"]    = pool.submit(_dhcp_lease_name, ip)

    names: dict = {k: v.result() for k, v in futures.items()}

    # DHCP option 12 hostname — instant cache lookup, added after async futures
    if mac:
        opt12 = _dhcp_option12_name(mac)
        if opt12:
            names["dhcp-option12"] = opt12

    # Collect non-empty names
    for src in ("rdns", "netbios", "mdns", "dhcp-option12", "snmp", "dhcp"):
        n = names.get(src, "")
        if n:
            result.all_names.append((src, n))
            if not result.hostname:
                result.hostname = n

    # ── Step 3: pick best display name ───────────────────────────────────────
    # Priority: model from registry > NetBIOS (usually friendly) >
    #           mDNS > DHCP option 12 > DHCP lease > rDNS (often just IP reversed)
    if result.model:
        result.display_name = result.model
        result.source = "mac-registry"
    elif names.get("netbios"):
        result.display_name = names["netbios"]
        result.source = "netbios"
    elif names.get("mdns"):
        result.display_name = names["mdns"]
        result.source = "mdns"
    elif names.get("dhcp-option12"):
        result.display_name = names["dhcp-option12"]
        result.source = "dhcp-option12"
    elif names.get("dhcp"):
        result.display_name = names["dhcp"]
        result.source = "dhcp"
    elif names.get("rdns"):
        result.display_name = names["rdns"]
        result.source = "rdns"
    elif names.get("snmp"):
        result.display_name = names["snmp"]
        result.source = "snmp"
    else:
        result.display_name = ip
        result.source = "ip-fallback"

    return result


_SHARED_PROBE_POOL_SIZE = 32  # fixed — deliberately does NOT scale with device count
                               # (Part 2/L2b: replaces one 6-worker probe pool per
                               # device with one shared bounded queue for the whole
                               # batch, so a 715-device and a 15-device batch exert
                               # the same peak thread load)


def resolve_batch(
    devices: list,
    mac_key: str = "mac",
    ip_key: str = "ip",
    progress_cb=None,
    on_result=None,
    **kwargs,
) -> dict:
    """
    Resolve names for a list of dicts (or objects with .ip / .mac attributes).

    Returns {ip: ResolvedName} dict. If given, progress_cb(str) is called
    periodically with a real "Identifying devices: n/total" message as
    results complete — same throttled idiom as ping_sweep_subnet.

    If given, on_result(ip, ResolvedName) is called once per device the
    instant THAT device's resolution finishes (success or fallback), from
    whichever worker thread completed it — for callers that want to stream
    each result live (Part 2/L7) instead of waiting for the whole batch to
    return. A raised exception inside on_result is swallowed — it is UI
    feedback, not load-bearing, and must never abort the rest of the batch.

    Every device's name-lookup probes (rdns/netbios/mdns/snmp/dhcp) share one
    bounded pool (_SHARED_PROBE_POOL_SIZE) for the whole batch, instead of each
    device spinning up its own inner pool — the previous 30-outer x 6-inner
    design let peak thread load scale with device count (up to ~180 probe
    threads); one shared queue keeps peak load flat regardless of batch size.
    """
    from modules.utils_net import parallel_map

    def _get(obj, key):
        if isinstance(obj, dict):
            return obj.get(key, "")
        return getattr(obj, key, "")

    total = len(devices)
    if total == 0:
        return {}

    _lock = threading.Lock()
    done_count = [0]

    with concurrent.futures.ThreadPoolExecutor(max_workers=_SHARED_PROBE_POOL_SIZE) as shared_probe_pool:

        def _resolve_safe(d):
            ip = _get(d, ip_key)
            try:
                name = resolve(ip, _get(d, mac_key), executor=shared_probe_pool, **kwargs)
            except Exception:
                name = ResolvedName(ip=ip)

            if on_result:
                try:
                    on_result(ip, name)
                except Exception:
                    pass  # non-fatal — a broken caller callback must not abort the batch

            if progress_cb:
                with _lock:
                    done_count[0] += 1
                    _count = done_count[0]
                if _count % 10 == 0 or _count == total:
                    progress_cb(f"Identifying devices: {_count}/{total}…")

            return ip, name

        pairs = parallel_map(_resolve_safe, devices, workers=30)

    return dict(pairs)
