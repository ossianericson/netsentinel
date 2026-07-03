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


@dataclass
class DhcpLease:
    mac:      str = ""
    ip:       str = ""
    hostname: str = ""
    expires:  int = 0          # Unix timestamp; 0 = unknown
    server:   str = ""
    source:   str = ""


# ── dnsmasq lease file parser ─────────────────────────────────────────────────

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
    extra = {"creationflags": subprocess.CREATE_NO_WINDOW}
    try:
        arp_out = subprocess.check_output(
            ["arp", "-a"], text=True, timeout=8, **extra
        )
        server   = ""
        expires  = 0
        # Try to get DHCP server + lease expiry from ipconfig /all
        try:
            cfg = subprocess.check_output(
                ["ipconfig", "/all"], text=True, timeout=10, **extra
            )
            s_m = re.search(r"DHCP Server\s*[.:]+\s*([\d.]+)", cfg)
            if s_m:
                server = s_m.group(1)
            e_m = re.search(r"Lease Expires\s*[.:]+\s*(.+)", cfg)
            if e_m:
                import datetime
                for fmt in (
                    "%A, %B %d, %Y %I:%M:%S %p",
                    "%d/%m/%Y %H:%M:%S",
                    "%m/%d/%Y %H:%M:%S",
                ):
                    try:
                        dt = datetime.datetime.strptime(e_m.group(1).strip(), fmt)
                        expires = int(dt.timestamp())
                        break
                    except ValueError:
                        pass  # non-fatal
        except Exception:
            pass  # non-fatal

        # Parse ARP table
        for line in arp_out.splitlines():
            parts = line.split()
            if len(parts) >= 2:
                ip_m  = re.match(r"(\d+\.\d+\.\d+\.\d+)", parts[0])
                mac_m = re.search(
                    r"([\da-f]{2}[-:][\da-f]{2}[-:][\da-f]{2}"
                    r"[-:][\da-f]{2}[-:][\da-f]{2}[-:][\da-f]{2})",
                    " ".join(parts[1:]), re.I,
                )
                if ip_m and mac_m:
                    mac = mac_m.group(1).replace("-", ":").lower()
                    leases.append(DhcpLease(
                        mac=mac, ip=ip_m.group(1),
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
