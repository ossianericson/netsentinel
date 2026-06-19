"""
Name Resolver — multi-method device name lookup.

Resolution order (fastest / most-reliable first):
  1. mac_registry   — local curated OUI→model database (zero latency)
  2. Reverse DNS    — PTR record via system resolver
  3. NetBIOS/WINS   — nbtstat (Windows) or nmblookup (Linux/macOS)
  4. mDNS           — query _services._dns-sd._udp.local for device name
  5. SNMP sysName   — SNMP v2c public community read (optional, no admin needed)
  6. DHCP lease file — parse OS DHCP lease files for offered hostnames

All methods run with short timeouts. The caller gets a ``ResolvedName``
with the best available display name and the source used.
"""

from __future__ import annotations

import concurrent.futures
import platform
import re
import socket
import subprocess
from dataclasses import dataclass, field

from modules.device_classifier import is_randomized_mac
from modules.mac_registry import lookup as mac_lookup


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

def _rdns(ip: str, timeout: float = 1.0) -> str:
    """Reverse DNS lookup."""
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(socket.gethostbyaddr, ip).result(timeout=timeout)[0]
    except Exception:
        return ""


def _netbios(ip: str) -> str:
    """NetBIOS name via nbtstat (Windows) or nmblookup (Linux)."""
    system = platform.system()
    extra: dict = {"creationflags": subprocess.CREATE_NO_WINDOW} if system == "Windows" else {}
    try:
        if system == "Windows":
            out = subprocess.check_output(
                ["nbtstat", "-A", ip], text=True, timeout=3, **extra
            )
            # Look for lines like "  DESKTOP-ABC    <00>  UNIQUE  Registered"
            for line in out.splitlines():
                m = re.match(r"\s+(\S+)\s+<00>\s+UNIQUE", line)
                if m:
                    name = m.group(1).strip()
                    if name and name.upper() not in ("__MSBROWSE__", "\\x01\\x02"):
                        return name
        else:
            out = subprocess.check_output(
                ["nmblookup", "-A", ip], text=True, timeout=3
            )
            for line in out.splitlines():
                m = re.match(r"\s+(\S+)\s+<00>", line)
                if m:
                    return m.group(1).strip()
    except Exception:
        pass  # non-fatal
    return ""


def _mdns_name(ip: str) -> str:
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

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(1.5)
        sock.sendto(packet, ("224.0.0.251", 5353))
        data, _ = sock.recvfrom(512)
        sock.close()
        # Very naive parse: find a label sequence after the answer section
        # Look for readable ASCII hostname segments
        text = data[12:]
        names = re.findall(rb"[\x01-\x3f]([\x20-\x7e]{2,})", text)
        for n in names:
            s = n.decode(errors="ignore")
            if "." in s or len(s) > 3:
                return s.strip()
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

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(1.5)
        sock.sendto(msg, (ip, 161))
        resp, _ = sock.recvfrom(1024)
        sock.close()
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
) -> ResolvedName:
    """
    Resolve the best available name for a device.

    Parameters
    ----------
    ip            : Device IP address.
    mac           : Device MAC address (optional but greatly improves results).
    use_netbios   : Query NetBIOS (Windows nbtstat / Linux nmblookup).
    use_mdns      : Query mDNS multicast (works for Chromecasts, printers, etc.).
    use_snmp      : Query SNMP sysName (off by default — can trigger IDS alerts).
    use_dhcp      : Parse local DHCP lease files.
    snmp_community: SNMP community string.

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
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures["rdns"]   = pool.submit(_rdns, ip)
        if use_netbios:
            futures["netbios"] = pool.submit(_netbios, ip)
        if use_mdns:
            futures["mdns"]    = pool.submit(_mdns_name, ip)
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


def resolve_batch(
    devices: list,
    mac_key: str = "mac",
    ip_key: str = "ip",
    **kwargs,
) -> dict:
    """
    Resolve names for a list of dicts (or objects with .ip / .mac attributes).

    Returns {ip: ResolvedName} dict.
    """
    results: dict = {}

    def _get(obj, key):
        if isinstance(obj, dict):
            return obj.get(key, "")
        return getattr(obj, key, "")

    with concurrent.futures.ThreadPoolExecutor(max_workers=30) as pool:
        fmap = {
            pool.submit(resolve, _get(d, ip_key), _get(d, mac_key), **kwargs): _get(d, ip_key)
            for d in devices
        }
        for fut in concurrent.futures.as_completed(fmap):
            ip = fmap[fut]
            try:
                results[ip] = fut.result()
            except Exception:
                results[ip] = ResolvedName(ip=ip)
    return results
