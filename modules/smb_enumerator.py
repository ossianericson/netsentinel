"""
Windows SMB / NetBIOS Enumerator

Enumerates Windows shares, users, domain membership, and active sessions
on a remote Windows host using only Python stdlib + optional impacket.

Two-tier approach:
  Tier 1 (no credentials): NetBIOS name query (UDP 137) + anonymous SMB
    session attempt — retrieves machine name, workgroup/domain, OS version.
  Tier 2 (with credentials): authenticated SMB — share list, user list,
    active sessions, local groups via SAMR/SRVSVC (requires impacket or
    subprocess wrappers around net.exe on Windows).

impacket is an optional dependency — if it is available it is used for
the richest data.  If not, falls back to:
  - UDP NetBIOS name query (stdlib only, zero deps)
  - subprocess calls to `net view` / `net user` / `net localgroup` when
    the scanner is running on Windows (same-OS fast path).

No new required pip packages — impacket is optional and listed in
requirements.txt as an optional comment.
"""

from __future__ import annotations

import platform
import re
import socket
import struct
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Callable, List, Optional

ProgressCB = Optional[Callable[[str], None]]

IMPACKET_AVAILABLE = False
try:
    from impacket.smbconnection import SMBConnection  # type: ignore
    IMPACKET_AVAILABLE = True
except ImportError:
    pass  # non-fatal


# ── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class SMBShare:
    name: str
    share_type: str = ""    # "DISK", "PRINTER", "IPC", "SPECIAL"
    comment: str = ""
    permissions: str = ""   # inferred: "READ", "READ/WRITE", "UNKNOWN"
    visible_anonymous: bool = False   # reachable via a no-credentials/null session


@dataclass
class SMBUser:
    username: str
    full_name: str = ""
    comment: str = ""
    last_logon: str = ""
    password_age: str = ""
    flags: str = ""


@dataclass
class SMBSession:
    client_ip: str
    username: str
    connected_since: str = ""
    idle_time: str = ""


@dataclass
class NetBIOSInfo:
    machine_name: str = ""
    workgroup: str = ""
    mac: str = ""
    is_domain_controller: bool = False


@dataclass
class SMBEnumResult:
    host: str
    netbios: NetBIOSInfo = field(default_factory=NetBIOSInfo)
    os_version: str = ""
    domain: str = ""
    shares: List[SMBShare] = field(default_factory=list)
    users: List[SMBUser] = field(default_factory=list)
    sessions: List[SMBSession] = field(default_factory=list)
    local_groups: List[str] = field(default_factory=list)
    is_domain_controller: bool = False
    anonymous_login: bool = False
    error: str = ""
    tier: int = 1   # 1 = unauthenticated, 2 = credentialed

    @property
    def risk_flags(self) -> List[str]:
        flags: List[str] = []
        if self.anonymous_login:
            flags.append("Anonymous SMB session allowed (null session)")
        disk_shares = [s for s in self.shares if s.share_type == "DISK"
                       and not s.name.upper().endswith("$")
                       and s.visible_anonymous]
        if disk_shares:
            flags.append(f"{len(disk_shares)} non-hidden disk share(s) exposed: "
                         + ", ".join(s.name for s in disk_shares))
        if self.is_domain_controller:
            flags.append("Host is a Domain Controller — high-value target")
        return flags

    @property
    def plain_verdict(self) -> str:
        if self.error:
            return f"⚠  SMB enum failed: {self.error}"
        parts = [
            f"Machine: {self.netbios.machine_name or self.host}",
            f"Domain/WG: {self.domain or self.netbios.workgroup or '—'}",
            f"OS: {self.os_version or '—'}",
            f"{len(self.shares)} share(s)",
        ]
        if self.tier >= 2:
            parts.append(f"{len(self.users)} user(s)")
        flags = self.risk_flags
        if flags:
            parts.append(f"⚠ {len(flags)} risk flag(s)")
        return " · ".join(parts)


# ── Tier 1 — NetBIOS UDP name query (stdlib, no deps) ─────────────────────────

def _netbios_name_query(host: str, timeout: float = 3.0) -> NetBIOSInfo:
    """
    Send a NetBIOS Name Service status query (UDP 137) and parse the reply.
    Works unauthenticated against any Windows host.
    """
    info = NetBIOSInfo()
    try:
        # NBSTAT query (transaction ID=0x1234, NBSTAT opcode)
        # RFC 1002 §4.2.18
        query = (
            b"\x12\x34"   # Transaction ID
            b"\x00\x00"   # Flags: 0 (query, not response, opcode QUERY)
            b"\x00\x01"   # Questions: 1
            b"\x00\x00\x00\x00\x00\x00"  # Answer/Auth/Addl RRs: 0
            # QNAME: encoded "*" (wildcard = all names)
            b"\x20"        # Length: 32 (encoded form of NBSTAT wildcard)
            b"CKAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"  # 32 bytes: encoded "*\x00"
            b"\x00"        # Null terminator
            b"\x00\x21"   # QTYPE: NBSTAT (0x0021)
            b"\x00\x01"   # QCLASS: IN
        )
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(timeout)
            sock.sendto(query, (host, 137))
            data, _ = sock.recvfrom(1024)

        # Parse NBSTAT response
        # After the 12-byte header, the answer section starts
        # Skip header (12) + qname (34) + qtype/qclass (4) + answer header (~12)
        # Easier: find the name count byte empirically
        # Header is 12 bytes; skip to answer
        offset = 56  # approximate start of name table in NBSTAT responses
        if len(data) < offset + 1:
            return info

        num_names = data[offset]
        offset += 1
        names: List[tuple] = []
        for _ in range(num_names):
            if offset + 18 > len(data):
                break
            raw_name = data[offset:offset + 15].decode("ascii", errors="replace").strip()
            name_type = data[offset + 15]
            flags_word = struct.unpack_from(">H", data, offset + 16)[0]
            offset += 18
            names.append((raw_name, name_type, flags_word))

        for name, ntype, flags in names:
            clean = name.strip()
            if ntype == 0x00 and not (flags & 0x8000):   # unique workstation/server name
                if not info.machine_name:
                    info.machine_name = clean
            if ntype == 0x00 and (flags & 0x8000):       # group = workgroup/domain
                info.workgroup = clean
            if ntype == 0x1C:                             # domain controller list
                info.workgroup = clean
                info.is_domain_controller = True

        # MAC address is the last 6 bytes of the name table
        if offset + 6 <= len(data):
            mac_bytes = data[offset:offset + 6]
            info.mac = ":".join(f"{b:02x}" for b in mac_bytes)

    except Exception:
        pass  # non-fatal
    return info


# ── Tier 1 — Anonymous SMB banner (TCP 445) ───────────────────────────────────

def _smb_anonymous_banner(host: str, timeout: float = 5.0) -> tuple:
    """
    Attempt a minimal SMB1/SMB2 negotiate to retrieve OS version and
    check if anonymous/null sessions are accepted.
    Returns (os_version: str, anonymous_ok: bool).
    """
    os_version = ""
    anonymous_ok = False
    try:
        # SMB2 Negotiate Request (minimal)
        smb2_negotiate = (
            b"\x00\x00\x00\x90"  # NetBIOS session header (length = 144)
            b"\xfeSMB"            # SMB2 magic
            b"\x40\x00"           # Header length
            b"\x00\x00"           # Credit charge
            b"\x00\x00\x00\x00"  # Status
            b"\x00\x00"           # Command: Negotiate (0)
            b"\x00\x00"           # Credits requested
            b"\x00\x00\x00\x00"  # Flags
            b"\x00\x00\x00\x00"  # Next command
            b"\x00\x00\x00\x00\x00\x00\x00\x00"  # Message ID (8 bytes)
            b"\x00\x00\x00\x00"  # Reserved (4 bytes)
            b"\x00\x00\x00\x00"  # Tree ID (4 bytes)
            b"\x00\x00\x00\x00\x00\x00\x00\x00"  # Session ID (8 bytes)
            b"\x00\x00\x00\x00\x00\x00\x00\x00"  # Signature part 1 (8 bytes)
            b"\x00\x00\x00\x00\x00\x00\x00\x00"  # Signature part 2 (8 bytes)
            b"\x24\x00"           # Structure size: 36
            b"\x02\x00"           # Dialect count: 2
            b"\x00\x00"           # Security mode
            b"\x00\x00"           # Reserved
            b"\x00\x00\x00\x00"  # Capabilities
            b"\x00\x00\x00\x00\x00\x00\x00\x00"  # Client GUID part 1
            b"\x00\x00\x00\x00\x00\x00\x00\x00"  # Client GUID part 2
            b"\x00\x00\x00\x00\x00\x00\x00\x00"  # Negotiate context
            b"\x02\x02"           # SMB 2.0.2
            b"\x10\x02"           # SMB 2.1
        )
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            sock.connect((host, 445))
            sock.sendall(smb2_negotiate)
            banner = sock.recv(256)

        # SMB2 negotiate response: dialect, capabilities, OS strings
        if len(banner) > 72 and banner[4:8] == b"\xfeSMB":
            # Dialect at offset 4+72 = 76 in the body
            dialect_offset = 76
            if len(banner) > dialect_offset + 2:
                dialect = struct.unpack_from("<H", banner, dialect_offset)[0]
                os_version = f"SMB2 dialect 0x{dialect:04x}"
            anonymous_ok = True   # We got a response = SMB is open

    except ConnectionRefusedError:
        pass  # non-fatal
    except Exception:
        pass  # non-fatal
    return os_version, anonymous_ok


# ── Tier 1 — net view subprocess (Windows only, authenticated) ─────────────

def _net_view_shares(host: str) -> List[SMBShare]:
    """Use `net view` (Windows only) to list shares. No credentials needed for open
    shares — every share returned here is by definition anonymously visible."""
    shares: List[SMBShare] = []
    if platform.system() != "Windows":
        return shares
    try:
        extra = {"creationflags": subprocess.CREATE_NO_WINDOW}
        raw = subprocess.check_output(
            ["net", "view", f"\\\\{host}", "/all"],
            text=True, timeout=15, stderr=subprocess.DEVNULL, **extra
        )
        for line in raw.splitlines():
            m = re.match(r"^(\S+)\s+(Disk|Print|Other)\s*(.*)", line, re.I)
            if m:
                shares.append(SMBShare(
                    name=m.group(1),
                    share_type=m.group(2).upper(),
                    comment=m.group(3).strip(),
                    visible_anonymous=True,
                ))
    except Exception:
        pass  # non-fatal
    return shares


# ── Tier 2 — impacket ─────────────────────────────────────────────────────────

def _impacket_enum(
    host: str,
    username: str,
    password: str,
    domain: str,
    timeout: float,
    progress: ProgressCB,
) -> SMBEnumResult:
    result = SMBEnumResult(host=host, tier=2)
    try:
        if progress:
            progress(f"Connecting to {host} via SMB as {domain}\\{username}…")
        conn = SMBConnection(host, host, timeout=int(timeout))
        conn.login(username, password, domain)
        result.os_version = conn.getServerOS() or ""
        result.domain     = conn.getServerDomain() or ""
        result.netbios.machine_name = conn.getServerName() or ""

        # Shares
        if progress:
            progress("Enumerating shares…")
        for share in conn.listShares():
            stype = share["shi1_type"]
            type_map = {0: "DISK", 1: "PRINTER", 2: "SPECIAL", 3: "IPC"}
            result.shares.append(SMBShare(
                name=share["shi1_netname"][:-1],
                share_type=type_map.get(stype, str(stype)),
                comment=(share["shi1_remark"][:-1] if share["shi1_remark"] else ""),
            ))

        # Anonymous check — also lists shares over the anonymous session so each
        # authenticated share can be marked visible_anonymous (F-88).
        anon_share_names: set = set()
        try:
            anon = SMBConnection(host, host, timeout=5)
            anon.login("", "")
            result.anonymous_login = True
            try:
                anon_share_names = {s["shi1_netname"][:-1] for s in anon.listShares()}
            except Exception:
                pass  # non-fatal — anonymous session may lack share-list rights
            anon.logoff()
        except Exception:
            result.anonymous_login = False

        for share in result.shares:
            share.visible_anonymous = share.name in anon_share_names

        conn.logoff()
    except Exception as exc:
        result.error = str(exc)
    return result


# ── Tier 2 — net.exe subprocess fallback (Windows only) ─────────────────────

def _net_exe_enum(host: str, username: str, password: str, domain: str,
                  progress: ProgressCB) -> SMBEnumResult:
    result = SMBEnumResult(host=host, tier=2)
    extra = {"creationflags": subprocess.CREATE_NO_WINDOW} if platform.system() == "Windows" else {}

    def _run(cmd: List[str]) -> str:
        try:
            return subprocess.check_output(cmd, text=True, timeout=20,
                                           stderr=subprocess.DEVNULL, **extra)
        except Exception:
            return ""

    # Establish authenticated session
    if progress:
        progress(f"net use \\\\{host} as {username}…")
    _run(["net", "use", f"\\\\{host}\\IPC$",
          password, f"/user:{domain}\\{username}" if domain else f"/user:{username}"])

    # Shares
    if progress:
        progress("net view…")
    raw = _run(["net", "view", f"\\\\{host}", "/all"])
    for line in raw.splitlines():
        m = re.match(r"^(\S+)\s+(Disk|Print|Other)\s*(.*)", line, re.I)
        if m:
            result.shares.append(SMBShare(
                name=m.group(1), share_type=m.group(2).upper(), comment=m.group(3).strip()
            ))

    # Users
    if progress:
        progress("net user…")
    raw = _run(["net", "user", f"/domain" if domain else ""])
    for line in raw.splitlines():
        for username_match in re.findall(r"\b([A-Za-z][A-Za-z0-9_$-]{1,19})\b", line):
            if username_match.lower() not in ("user", "accounts", "command", "the"):
                result.users.append(SMBUser(username=username_match))

    # Local groups
    raw = _run(["net", "localgroup"])
    for m in re.finditer(r"\*(\S+)", raw):
        result.local_groups.append(m.group(1))

    # Disconnect
    _run(["net", "use", f"\\\\{host}\\IPC$", "/delete"])

    # Anonymous visibility check (F-88) — now that the authenticated session is
    # torn down, a fresh credential-less net view probes what an unauthenticated
    # client can actually see. Reuses the Tier-1 no-credentials helper rather
    # than building separate anonymous-session logic for this path.
    anon_share_names = {s.name for s in _net_view_shares(host)}
    for share in result.shares:
        share.visible_anonymous = share.name in anon_share_names

    return result


# ── Public API ────────────────────────────────────────────────────────────────

def enumerate_smb(
    host: str,
    *,
    username: str = "",
    password: str = "",
    domain: str = "",
    timeout: float = 10.0,
    progress_cb: ProgressCB = None,
    stop_event: Optional[threading.Event] = None,
) -> SMBEnumResult:
    """
    Enumerate SMB on host.  Tier 1 if no credentials; Tier 2 if credentials given.
    """
    stop = stop_event or threading.Event()

    # ── Tier 1: Unauthenticated ───────────────────────────────────────────────
    if progress_cb:
        progress_cb(f"NetBIOS name query → {host}…")
    netbios = _netbios_name_query(host, timeout=min(timeout, 3.0))

    if progress_cb:
        progress_cb("SMB2 banner probe…")
    os_version, anonymous_ok = _smb_anonymous_banner(host, timeout=min(timeout, 5.0))

    if not username:
        # Tier 1 only
        shares = _net_view_shares(host) if platform.system() == "Windows" else []
        result = SMBEnumResult(
            host=host,
            netbios=netbios,
            os_version=os_version,
            domain=netbios.workgroup,
            shares=shares,
            anonymous_login=anonymous_ok,
            is_domain_controller=netbios.is_domain_controller,
            tier=1,
        )
        if progress_cb:
            progress_cb(result.plain_verdict)
        return result

    # ── Tier 2: Authenticated ─────────────────────────────────────────────────
    if stop.is_set():
        return SMBEnumResult(host=host, error="Cancelled", tier=1)

    if IMPACKET_AVAILABLE:
        result = _impacket_enum(host, username, password, domain, timeout, progress_cb)
    elif platform.system() == "Windows":
        result = _net_exe_enum(host, username, password, domain, progress_cb)
    else:
        result = SMBEnumResult(
            host=host,
            error="Tier-2 SMB enumeration requires impacket (pip install impacket) "
                  "or must be run from Windows with net.exe available.",
            tier=1,
        )

    # Merge tier-1 data
    if not result.netbios.machine_name:
        result.netbios = netbios
    if not result.os_version:
        result.os_version = os_version
    result.anonymous_login = result.anonymous_login or anonymous_ok
    result.is_domain_controller = result.is_domain_controller or netbios.is_domain_controller

    if progress_cb:
        progress_cb(result.plain_verdict)
    return result
