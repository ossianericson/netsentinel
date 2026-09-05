"""
Credentialed scan — shared dataclasses, SSH backends, and output parsers.

Extracted from modules/credentialed_scan.py (S20-2 sprint split).
All public names remain importable from modules.credentialed_scan for
backwards compatibility via re-exports in that module.
"""

from __future__ import annotations

import contextlib
import re
import shutil
import socket
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Callable, List, Optional

# Optional: paramiko for in-process SSH without requiring the openssh binary
PARAMIKO_AVAILABLE = False
try:
    import paramiko  # type: ignore
    PARAMIKO_AVAILABLE = True
except ImportError:
    PARAMIKO_AVAILABLE = False  # optional dependency

ProgressCB = Optional[Callable[[str], None]]

# Public API — _LINUX_CMDS/_WINDOWS_CMDS are imported by credentialed_scan.py
__all__ = [
    "PARAMIKO_AVAILABLE", "ProgressCB",
    "SoftwareEntry", "ServiceEntry", "UserEntry", "PatchInfo",
    "ListeningPort", "CredScanResult", "SSHUnreachableError",
    "_LINUX_CMDS", "_WINDOWS_CMDS",
    "_parse_linux", "_parse_windows",
    "_run_ssh_paramiko", "_run_ssh_subprocess",
]


class SSHUnreachableError(Exception):
    """The SSH connection itself could not be established (refused,
    unreachable, timed out, or DNS failure) — distinct from an authentication
    failure, which means the host WAS reached and the scan produced a real,
    meaningful (if negative) result. Always importable regardless of whether
    paramiko is installed, so callers never need a conditional import to
    catch it specifically."""


# ── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class SoftwareEntry:
    name: str
    version: str = ""
    source: str = ""    # "apt", "rpm", "pip", "wmic", "registry", etc.


@dataclass
class ServiceEntry:
    name: str
    status: str = ""    # "running" | "stopped" | "unknown"
    pid: int = 0


@dataclass
class UserEntry:
    username: str
    uid: str = ""
    home: str = ""
    shell: str = ""
    groups: str = ""
    last_login: str = ""


@dataclass
class PatchInfo:
    os_version: str = ""
    kernel: str = ""
    last_update: str = ""
    pending_updates: int = 0
    pending_update_names: List[str] = field(default_factory=list)


@dataclass
class ListeningPort:
    protocol: str       # "tcp" | "udp"
    port: int
    address: str = ""
    process: str = ""


@dataclass
class CredScanResult:
    host: str
    os_type: str = ""   # "linux" | "windows" | "macos" | "unknown"
    error: str = ""
    not_testable:        bool = False
    not_testable_reason: str  = ""

    software: List[SoftwareEntry] = field(default_factory=list)
    services: List[ServiceEntry] = field(default_factory=list)
    users: List[UserEntry] = field(default_factory=list)
    patch_info: PatchInfo = field(default_factory=PatchInfo)
    listening_ports: List[ListeningPort] = field(default_factory=list)
    failed_logins: int = 0
    sudo_nopasswd_entries: List[str] = field(default_factory=list)
    raw_notes: List[str] = field(default_factory=list)
    # Windows-specific enrichment
    serial_number: str = ""      # wmic bios get serialnumber
    active_sessions: List[str] = field(default_factory=list)  # query session output

    @property
    def risk_flags(self) -> List[str]:
        flags: List[str] = []
        if self.sudo_nopasswd_entries:
            flags.append(f"NOPASSWD sudo for: {', '.join(self.sudo_nopasswd_entries)}")
        if self.failed_logins >= 10:
            flags.append(f"{self.failed_logins} failed login attempts in last 24 h")
        if self.patch_info.pending_updates >= 10:
            flags.append(f"{self.patch_info.pending_updates} pending updates")
        root_shell_users = [u for u in self.users if u.uid == "0" and u.username != "root"]
        if root_shell_users:
            flags.append(f"UID-0 non-root users: {', '.join(u.username for u in root_shell_users)}")
        return flags

    @property
    def plain_verdict(self) -> str:
        if self.not_testable:
            return f"⚠ Could not test {self.host} — {self.not_testable_reason}"
        if self.error:
            return f"⚠  Scan failed: {self.error}"
        parts = [
            f"OS: {self.os_type or 'unknown'}",
            f"{len(self.software)} packages",
            f"{len(self.services)} services",
            f"{len(self.users)} users",
            f"{len(self.listening_ports)} listening ports",
        ]
        flags = self.risk_flags
        if flags:
            parts.append(f"⚠ {len(flags)} risk flag(s)")
        return " · ".join(parts)


# ── SSH backend ───────────────────────────────────────────────────────────────

def _run_ssh_paramiko(
    host: str,
    port: int,
    username: str,
    password: Optional[str],
    key_path: Optional[str],
    commands: List[str],
    timeout: float,
    progress: ProgressCB,
    stop: threading.Event,
) -> dict[str, str]:
    """Run a list of shell commands via paramiko SSH. Returns {cmd: output}."""
    results: dict[str, str] = {}
    client = paramiko.SSHClient()
    # Credential scan tool connects to arbitrary LAN devices by design;
    # WarningPolicy logs unknown keys without silently trusting them.
    client.set_missing_host_key_policy(paramiko.WarningPolicy())  # lgtm[py/paramiko-missing-host-key-validation]
    try:
        connect_kwargs: dict = {"hostname": host, "port": port, "username": username,
                                "timeout": timeout, "banner_timeout": timeout,
                                "auth_timeout": timeout}
        if key_path:
            connect_kwargs["key_filename"] = key_path
        else:
            connect_kwargs["password"] = password
            connect_kwargs["look_for_keys"] = False
            connect_kwargs["allow_agent"] = False

        if progress:
            progress(f"SSH connecting to {host}:{port} as {username}…")
        try:
            client.connect(**connect_kwargs)
        except (paramiko.ssh_exception.NoValidConnectionsError,
                socket.timeout, socket.gaierror, TimeoutError) as exc:
            # The host was never reached — refused, unreachable, timed out, or
            # unresolvable. Distinct from AuthenticationException below, which
            # means the host WAS reached and answered.
            raise SSHUnreachableError(str(exc)) from exc

        for cmd in commands:
            if stop.is_set():
                break
            if progress:
                progress(f"→ {cmd[:60]}")
            _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
            out = stdout.read().decode("utf-8", errors="replace")
            err = stderr.read().decode("utf-8", errors="replace")
            results[cmd] = out if out else err
    finally:
        client.close()
    return results


def _run_ssh_subprocess(
    host: str,
    port: int,
    username: str,
    password: Optional[str],
    key_path: Optional[str],
    commands: List[str],
    timeout: float,
    progress: ProgressCB,
    stop: threading.Event,
) -> dict[str, str]:
    """Run commands via the system openssh binary (sshpass for password auth)."""
    results: dict[str, str] = {}
    ssh_bin = shutil.which("ssh")
    if not ssh_bin:
        raise RuntimeError("Neither paramiko nor openssh binary is available.")

    base_args = [
        ssh_bin,
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "BatchMode=no",
        "-o", f"ConnectTimeout={int(timeout)}",
        "-p", str(port),
    ]
    if key_path:
        base_args += ["-i", key_path]

    # Pass password via SSHPASS env var (not CLI arg) to keep it out of
    # process listings visible to other users via `ps aux` / Process Monitor.
    env_extra: dict = {}
    prefix: List[str] = []
    if password and not key_path:
        sshpass = shutil.which("sshpass")
        if sshpass:
            prefix = [sshpass, "-e"]           # -e reads from $SSHPASS env var
            env_extra["SSHPASS"] = password    # never appears in process args

    for cmd in commands:
        if stop.is_set():
            break
        if progress:
            progress(f"→ {cmd[:60]}")
        try:
            full = prefix + base_args + [f"{username}@{host}", cmd]
            run_env = {**__import__("os").environ, **env_extra} if env_extra else None
            # encoding is named deliberately (RULE-WIN21): the frozen build injects
            # the OEM console codepage into every unnamed text-mode child, which is
            # right for netsh/ipconfig and wrong here. ssh forwards the *remote's*
            # bytes verbatim and a modern Linux host is UTF-8 — nothing about the
            # local user's locale is involved, so decoding a GECOS field or an
            # os-release name as cp437/cp850 corrupts it on en-US too.
            # _run_ssh_paramiko, this function's other backend, already decodes utf-8.
            proc = subprocess.run(
                full, capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                timeout=timeout + 5, env=run_env,
            )
            results[cmd] = proc.stdout if proc.stdout else proc.stderr
        except subprocess.TimeoutExpired:
            results[cmd] = "(timeout)"
        except Exception as exc:
            results[cmd] = f"(error: {exc})"
    return results


# ── Linux/macOS command set ───────────────────────────────────────────────────

_LINUX_CMDS: List[str] = [
    "uname -a",
    "cat /etc/os-release 2>/dev/null || cat /etc/issue",
    "dpkg -l 2>/dev/null | awk 'NR>5{print $2,$3}' | head -200",
    "rpm -qa --queryformat '%{NAME} %{VERSION}\\n' 2>/dev/null | head -200",
    "systemctl list-units --type=service --state=running --no-pager --no-legend 2>/dev/null | awk '{print $1,$4}' | head -100",
    "service --status-all 2>&1 | head -100",
    "ss -tlnup 2>/dev/null || netstat -tlnup 2>/dev/null",
    "awk -F: '$3>=1000{print $1,$3,$6,$7}' /etc/passwd",
    "last -n 20 2>/dev/null",
    "grep 'Failed password' /var/log/auth.log 2>/dev/null | grep \"$(date +'%b %d')\" | wc -l",
    "grep 'Failed password' /var/log/secure 2>/dev/null | grep \"$(date +'%b %d')\" | wc -l",
    "grep -r NOPASSWD /etc/sudoers /etc/sudoers.d/ 2>/dev/null",
    "apt-get -s upgrade 2>/dev/null | grep '^Inst' | wc -l",
    "yum check-update --quiet 2>/dev/null | grep -v '^$' | wc -l",
    "tail -n1 /var/log/dpkg.log 2>/dev/null",
    "rpm -qa --last 2>/dev/null | head -1",
]


# ── Parser — Linux ────────────────────────────────────────────────────────────

def _parse_linux(outputs: dict[str, str]) -> CredScanResult:
    result = CredScanResult(host="", os_type="linux")

    for key in outputs:
        if "os-release" in key or "uname" in key:
            txt = outputs[key]
            m = re.search(r'PRETTY_NAME="([^"]+)"', txt)
            if m:
                result.patch_info.os_version = m.group(1)
            m = re.search(r'Linux (\S+)', txt)
            if m:
                result.patch_info.kernel = m.group(1)
            break

    for key in outputs:
        if "dpkg" in key:
            for line in outputs[key].splitlines():
                parts = line.split(None, 1)
                if len(parts) == 2:
                    result.software.append(SoftwareEntry(name=parts[0], version=parts[1], source="dpkg"))
            break
    if not result.software:
        for key in outputs:
            if "rpm" in key:
                for line in outputs[key].splitlines():
                    parts = line.split(None, 1)
                    if len(parts) == 2:
                        result.software.append(SoftwareEntry(name=parts[0], version=parts[1], source="rpm"))
                break

    for key in outputs:
        if "systemctl" in key:
            for line in outputs[key].splitlines():
                parts = line.split(None, 1)
                if parts:
                    result.services.append(ServiceEntry(name=parts[0], status="running"))
            break
    if not result.services:
        for key in outputs:
            if "service --status" in key:
                for line in outputs[key].splitlines():
                    m = re.match(r'\s*\[([+\-\?])\]\s+(\S+)', line)
                    if m:
                        status = {"+"  : "running", "-": "stopped"}.get(m.group(1), "unknown")
                        result.services.append(ServiceEntry(name=m.group(2), status=status))
                break

    for key in outputs:
        if "ss -t" in key or "netstat" in key:
            for line in outputs[key].splitlines():
                m = re.search(r'(tcp|udp).*?[*\d.]+:(\d+)\s', line, re.I)
                if m:
                    result.listening_ports.append(
                        ListeningPort(protocol=m.group(1).lower(), port=int(m.group(2)))
                    )
            break

    for key in outputs:
        if "/etc/passwd" in key:
            for line in outputs[key].splitlines():
                parts = line.split(None, 3)
                if len(parts) >= 4:
                    result.users.append(UserEntry(
                        username=parts[0], uid=parts[1], home=parts[2], shell=parts[3]
                    ))
            break

    for key in outputs:
        if "Failed password" in key or "auth.log" in key or "secure" in key:
            with contextlib.suppress(ValueError):
                result.failed_logins += int(outputs[key].strip() or "0")

    for key in outputs:
        if "NOPASSWD" in key:
            for line in outputs[key].splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    result.sudo_nopasswd_entries.append(line)
            break

    for key in outputs:
        if "apt-get" in key or "yum check" in key:
            with contextlib.suppress(ValueError):
                n = int(outputs[key].strip() or "0")
                if n > 0:
                    result.patch_info.pending_updates = max(result.patch_info.pending_updates, n)

    for key in outputs:
        if "dpkg.log" in key:
            m = re.match(r'^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})', outputs[key].strip())
            if m:
                result.patch_info.last_update = m.group(1)
            break
    if not result.patch_info.last_update:
        for key in outputs:
            if "rpm -qa --last" in key:
                m = re.match(r'^\S+\s+(.+)$', outputs[key].strip())
                if m:
                    result.patch_info.last_update = m.group(1).strip()
                break

    return result


# ── Windows command set (via SSH to a Windows box with OpenSSH installed) ─────

_WINDOWS_CMDS: List[str] = [
    "powershell -NoProfile -Command \"$o=Get-CimInstance Win32_OperatingSystem; Write-Output ('Caption='+$o.Caption); Write-Output ('Version='+$o.Version)\"",
    "powershell -NoProfile -Command \"$b=Get-CimInstance Win32_BIOS; Write-Output ('SerialNumber='+$b.SerialNumber)\"",
    "query session",
    "powershell -NoProfile -Command \"Get-CimInstance Win32_Product | ForEach-Object { Write-Output ('Name='+$_.Name); Write-Output ('Version='+$_.Version) }\"",
    # state= takes active|inactive|all. "running" is not one of them: sc.exe
    # exits 87 with "ERROR: Invalid state= field" and prints nothing, so the
    # service list has been empty on every Windows, every locale. Measured.
    "sc query type= service state= active",
    "powershell -NoProfile -Command \"Get-CimInstance Win32_UserAccount | ForEach-Object { Write-Output ('Name='+$_.Name); Write-Output ('SID='+$_.SID); Write-Output ('Disabled='+$_.Disabled) }\"",
    "netstat -ano | findstr LISTENING",
    'powershell -NoProfile -Command "(New-Object -ComObject Microsoft.Update.Session).CreateUpdateSearcher().Search(\'IsInstalled=0\').Updates | Select-Object -ExpandProperty Title | Measure-Object -Line | Select-Object -ExpandProperty Lines"',
    "powershell -NoProfile -Command \"Get-WinEvent -FilterHashtable @{LogName='Security';Id=4625;StartTime=(Get-Date).AddHours(-24)} -ErrorAction SilentlyContinue | Measure-Object | Select-Object -ExpandProperty Count\"",
    "powershell -NoProfile -Command \"Get-HotFix | Sort-Object InstalledOn -Descending | Select-Object -First 1 -ExpandProperty InstalledOn\"",
]


def _parse_windows(outputs: dict[str, str]) -> CredScanResult:
    result = CredScanResult(host="", os_type="windows")

    for key in outputs:
        if "Win32_OperatingSystem" in key:
            txt = outputs[key]
            m = re.search(r'Caption=(.+)', txt)
            if m:
                result.patch_info.os_version = m.group(1).strip()
            m = re.search(r'Version=(.+)', txt)
            if m:
                result.patch_info.kernel = m.group(1).strip()
            break

    for key in outputs:
        if "Win32_Product" in key:
            name = ver = ""
            for line in outputs[key].splitlines():
                m = re.match(r'Name=(.+)', line)
                if m:
                    name = m.group(1).strip()
                m = re.match(r'Version=(.+)', line)
                if m:
                    ver = m.group(1).strip()
                if name and ver:
                    result.software.append(SoftwareEntry(name=name, version=ver, source="cim"))
                    name = ver = ""
            break

    for key in outputs:
        if "sc query" in key:
            svc_name = ""
            for line in outputs[key].splitlines():
                m = re.match(r'SERVICE_NAME: (.+)', line)
                if m:
                    svc_name = m.group(1).strip()
                # `STATE : 4  RUNNING` — read the code, not the word beside it.
                # 4 is SERVICE_RUNNING and is untranslated; it also excludes the
                # START_PENDING (2) and PAUSED (7) services that state= active
                # returns, which "running" should not claim.
                if svc_name and re.search(r"STATE\s*:\s*4\b", line):
                    result.services.append(ServiceEntry(name=svc_name, status="running"))
                    svc_name = ""
            break

    for key in outputs:
        if "Win32_BIOS" in key:
            m = re.search(r'SerialNumber=(.+)', outputs[key])
            if m:
                result.serial_number = m.group(1).strip()
            break

    for key in outputs:
        if "query session" in key:
            sessions: List[str] = []
            for line in outputs[key].splitlines()[1:]:
                line = line.strip()
                if not line:
                    continue
                parts = line.split()
                if len(parts) < 3:
                    continue
                state = parts[-1].lower()
                if state not in ("active", "conn"):
                    continue
                username_col = parts[1] if len(parts) >= 4 else parts[0]
                username_col = username_col.lstrip(">")
                if username_col and username_col not in ("0", "1", "2", "3", "4", "5"):
                    sessions.append(username_col)
            result.active_sessions = sessions
            break

    for key in outputs:
        if "Win32_UserAccount" in key:
            name = sid = ""
            for line in outputs[key].splitlines():
                m = re.match(r'Name=(.+)', line)
                if m:
                    name = m.group(1).strip()
                m = re.match(r'SID=(.+)', line)
                if m:
                    sid = m.group(1).strip()
                if name and sid:
                    result.users.append(UserEntry(username=name, uid=sid))
                    name = sid = ""
            break

    for key in outputs:
        if "netstat -ano" in key:
            for line in outputs[key].splitlines():
                m = re.search(r'(TCP|UDP)\s+[0-9.*:]+:(\d+)\s+[0-9.*:]+\s+LISTENING\s+(\d+)', line, re.I)
                if m:
                    result.listening_ports.append(
                        ListeningPort(protocol=m.group(1).lower(), port=int(m.group(2)), process=m.group(3))
                    )
            break

    for key in outputs:
        if "Measure-Object" in key or "Measure-Line" in key:
            with contextlib.suppress(ValueError):
                result.patch_info.pending_updates = int(outputs[key].strip() or "0")

    for key in outputs:
        if "4625" in key:
            with contextlib.suppress(ValueError):
                result.failed_logins = int(outputs[key].strip() or "0")

    for key in outputs:
        if "Get-HotFix" in key:
            txt = outputs[key].strip()
            if txt:
                result.patch_info.last_update = txt.splitlines()[0].strip()
            break

    return result
