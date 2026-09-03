"""
dhcp_lease_scanner.py — DHCP lease inventory reader.

Reads DHCP lease data from the local machine's lease files (Linux/macOS)
or from the Windows ARP cache + ipconfig (Windows fallback) and returns a
structured list of lease records.

This module is safe to import on all platforms; it returns an empty list
when lease files are not present or accessible.

Returned list items are DhcpLease dataclasses:
  mac         — MAC address (lowercase, colon-separated)
  ip          — IPv4 address
  hostname    — hostname offered by DHCP server (empty if not in file)
  expires     — Unix timestamp of lease expiry (0 = unknown / infinite)
  server      — DHCP server IP that issued the lease (empty if unknown)
  source      — human label of where the record came from

Not a name_resolver duplicate: this parses DHCP lease *files* for
authoritative lease records (mac/ip/hostname/expiry/server), a different
problem than name_resolver's live best-effort hostname lookup.
"""

from __future__ import annotations

import platform
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List

from modules.utils_net import get_arp_snapshot


@dataclass
class DhcpLease:
    mac:      str = ""
    ip:       str = ""
    hostname: str = ""
    expires:  int = 0          # Unix timestamp; 0 = unknown
    server:   str = ""
    source:   str = ""


# ── dnsmasq lease file parser ─────────────────────────────────────────────────


def _read_dhcp_lease_from_registry() -> tuple:
    """Return (dhcp_server, lease_terminates_epoch) from the Windows registry.

    Locale-independent by construction: these are typed registry values, not text
    to be parsed. ``LeaseTerminatesTime`` is a REG_DWORD holding a Unix epoch, so
    there is no date format to get wrong. Returns ("", 0) on any failure or on a
    non-Windows platform (RULE-WIN1: prefer winreg over subprocess for this data).
    """
    if platform.system() != "Windows":
        return "", 0
    try:
        import winreg as _wr
    except ImportError:
        return "", 0

    ifaces = r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces"
    best_server, best_expiry = "", 0
    try:
        with _wr.OpenKey(_wr.HKEY_LOCAL_MACHINE, ifaces) as root:
            for i in range(_wr.QueryInfoKey(root)[0]):
                try:
                    guid = _wr.EnumKey(root, i)
                    with _wr.OpenKey(root, guid) as k:
                        def _v(name):
                            try:
                                return _wr.QueryValueEx(k, name)[0]
                            except OSError:
                                return None
                        # Only adapters holding a real lease are of interest.
                        if not _v("DhcpIPAddress"):
                            continue
                        expiry = _v("LeaseTerminatesTime") or 0
                        server = _v("DhcpServer") or ""
                        # Prefer the adapter whose lease runs longest — on a box
                        # with several adapters this is the active one.
                        if int(expiry) > best_expiry:
                            best_expiry = int(expiry)
                            best_server = str(server)
                except (OSError, ValueError, TypeError):
                    continue  # skip an adapter subkey we cannot read
    except OSError:
        return "", 0
    return best_server, best_expiry


def _parse_dnsmasq(path: Path) -> List[DhcpLease]:
    """
    dnsmasq format (one lease per line):
      <expiry_ts> <mac> <ip> <hostname> <client-id>
    """
    leases: List[DhcpLease] = []
    try:
        for line in path.read_text(errors="ignore").splitlines():
            parts = line.split()
            if len(parts) < 4:
                continue
            try:
                expires = int(parts[0])
            except ValueError:
                expires = 0
            mac      = parts[1].lower()
            ip       = parts[2]
            hostname = parts[3] if parts[3] != "*" else ""
            leases.append(DhcpLease(
                mac=mac, ip=ip, hostname=hostname,
                expires=expires, source=str(path),
            ))
    except Exception:
        pass  # non-fatal
    return leases


# ── dhclient lease file parser ────────────────────────────────────────────────

def _parse_dhclient(path: Path) -> List[DhcpLease]:
    """
    dhclient format: blocks starting with 'lease {' containing key-value lines.
    """
    leases: List[DhcpLease] = []
    try:
        content = path.read_text(errors="ignore")
    except Exception:
        return leases

    for block in re.split(r"lease\s*\{", content):
        ip_m       = re.search(r"fixed-address\s+([\d.]+)\s*;", block)
        if not ip_m:
            continue
        ip         = ip_m.group(1)
        mac_m      = re.search(r"hardware\s+ethernet\s+([\da-f:]+)\s*;", block, re.I)
        mac        = mac_m.group(1).lower() if mac_m else ""
        host_m     = re.search(r'option\s+host-name\s+"([^"]+)"', block)
        hostname   = host_m.group(1) if host_m else ""
        server_m   = re.search(r"option\s+dhcp-server-identifier\s+([\d.]+)\s*;", block)
        server     = server_m.group(1) if server_m else ""
        exp_m      = re.search(r"expire\s+\d+\s+\S+\s+(\S+)\s*;", block)
        expires    = 0
        if exp_m:
            try:
                import datetime
                dt = datetime.datetime.strptime(exp_m.group(1), "%Y/%m/%d %H:%M:%S")
                expires = int(dt.timestamp())
            except Exception:
                pass  # non-fatal
        leases.append(DhcpLease(
            mac=mac, ip=ip, hostname=hostname,
            expires=expires, server=server, source=str(path),
        ))
    return leases


# ── Windows fallback — ARP table + ipconfig ───────────────────────────────────

def _windows_arp_leases() -> List[DhcpLease]:
    """
    Windows doesn't expose raw DHCP lease files.  We read the ARP cache to
    enumerate IP↔MAC pairs, and use ipconfig /all to find the DHCP server
    and our own lease expiry.  Only the gateway-side lease info is available;
    other clients on the subnet are not visible from this host.
    """
    leases: List[DhcpLease] = []
    # CREATE_NO_WINDOW is Windows-only — getattr fallback keeps this importable
    # and callable on macOS/Linux (matches service_diagnostics_probes.py /
    # smb_enumerator.py).
    extra = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    try:
        server   = ""
        expires  = 0
        # Try to get DHCP server + lease expiry from ipconfig /all
        try:
            cfg = subprocess.check_output(
                ["ipconfig", "/all"], text=True, timeout=10, **extra
            )
            # "DHCP Server" is localized ("Servidor DHCP", "DHCP-server"), but the
            # DHCP acronym itself survives translation in every locale Windows
            # ships, so anchor on it plus an IPv4-shaped value.
            s_m = re.search(
                r"DHCP[^\n]*?[.:\s]\s*(\d{1,3}(?:\.\d{1,3}){3})", cfg
            )
            if s_m:
                server = s_m.group(1)
        except Exception:
            pass  # non-fatal

        # Lease expiry comes from the registry, never from ipconfig text. The
        # "Lease Expires" label is localized AND its value carries localized month
        # names, which strptime (C locale) cannot parse in any format — so the old
        # format list produced expires=0 on every non-English install, and its
        # entries also omitted en-AU's "%A, %d %B %Y", breaking Australia even in
        # English. LeaseTerminatesTime is a REG_DWORD epoch: no parsing, no locale.
        reg_server, reg_expires = _read_dhcp_lease_from_registry()
        if reg_expires:
            expires = reg_expires
        if reg_server and not server:
            server = reg_server

        # Parse ARP table
        for ip, mac in get_arp_snapshot().items():
            leases.append(DhcpLease(
                mac=mac, ip=ip,
                expires=expires, server=server,
                source="ARP cache (Windows)",
            ))
    except Exception:
        pass  # non-fatal
    return leases


# ── Linux / macOS nmcli enrichment ───────────────────────────────────────────

def _nmcli_leases() -> List[DhcpLease]:
    """Try nmcli to get active DHCP leases on Linux with NetworkManager."""
    leases: List[DhcpLease] = []
    try:
        out = subprocess.check_output(
            ["nmcli", "-f", "DHCP4.OPTION", "device", "show"],
            text=True, timeout=8, stderr=subprocess.DEVNULL,
        )
        # Each DHCP4.OPTION block contains key=value pairs
        block_ip      = ""
        block_server  = ""
        block_expires = 0
        for line in out.splitlines():
            m = re.search(r"DHCP4\.OPTION.*ip_address\s*=\s*([\d.]+)", line)
            if m:
                block_ip = m.group(1)
            m = re.search(r"DHCP4\.OPTION.*dhcp_server_identifier\s*=\s*([\d.]+)", line)
            if m:
                block_server = m.group(1)
            m = re.search(r"DHCP4\.OPTION.*expiry\s*=\s*(\d+)", line)
            if m:
                block_expires = int(m.group(1))
        if block_ip:
            leases.append(DhcpLease(
                ip=block_ip, server=block_server,
                expires=block_expires, source="nmcli",
            ))
    except Exception:
        pass  # non-fatal
    return leases


# ── Public entry point ────────────────────────────────────────────────────────

_LINUX_LEASE_FILES = [
    Path("/var/lib/misc/dnsmasq.leases"),
    Path("/var/lib/dnsmasq/dnsmasq.leases"),
    Path("/tmp/dhcp.leases"),
    Path("/var/lib/dhcp/dhclient.leases"),
    Path("/var/lib/dhcpcd/dhcpcd.leases"),
    Path("/var/lib/NetworkManager/dhclient-*.conf"),
]


def scan() -> List[DhcpLease]:
    """
    Return a deduplicated list of DhcpLease records from all available sources
    on the current platform.  Never raises; returns an empty list on failure.
    """
    system   = platform.system()
    leases: List[DhcpLease] = []
    seen_ips: set = set()

    if system == "Windows":
        leases.extend(_windows_arp_leases())
    else:
        # dnsmasq
        for p in [
            Path("/var/lib/misc/dnsmasq.leases"),
            Path("/var/lib/dnsmasq/dnsmasq.leases"),
            Path("/tmp/dhcp.leases"),
        ]:
            if p.exists():
                leases.extend(_parse_dnsmasq(p))

        # dhclient
        for p in [
            Path("/var/lib/dhcp/dhclient.leases"),
            Path("/var/lib/dhcpcd/dhcpcd.leases"),
        ]:
            if p.exists():
                leases.extend(_parse_dhclient(p))

        # nmcli enrichment
        leases.extend(_nmcli_leases())

    # Deduplicate by IP (keep first occurrence)
    deduped: List[DhcpLease] = []
    for lease in leases:
        if lease.ip and lease.ip not in seen_ips:
            seen_ips.add(lease.ip)
            deduped.append(lease)

    return deduped


def verdict(leases: List[DhcpLease]) -> str:
    """Plain-English summary for the page status bar."""
    if not leases:
        return "No DHCP lease data found on this system."
    active = [l for l in leases if l.expires == 0 or l.expires > time.time()]
    return (
        f"{len(leases)} lease(s) found "
        f"({len(active)} active)."
    )
