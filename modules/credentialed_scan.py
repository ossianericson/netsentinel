"""
Credentialed Deep Scan

Connects to a remote host using SSH (Linux/macOS/network gear) or WMI/PowerShell
(Windows) and collects:

  - Installed software list
  - Running services / processes
  - Local user accounts
  - Applied patches / OS version
  - Open listening ports (ss/netstat)
  - Sudoers / privilege escalation hints (Linux)
  - Failed login attempts (last 24 h)

─── CREDENTIAL HANDLING ────────────────────────────────────────────────────────

  1. In-memory only.
     SSH password and private-key path are accepted as function arguments and
     held only in local variables for the duration of the SSH session.
     They are never assigned to any attribute of CredScanResult or any other
     persistent object, and are never written to disk in any form.

  2. Not included in any report output.
     CredScanResult — the only object passed to report_exporter — contains no
     password, key material, or authentication token fields.  HTML, JSON, and
     CSV reports therefore cannot contain credential data.

  3. No outbound connections outside the target host.
     Every subprocess and paramiko call in this module connects exclusively to
     the host address passed by the caller.  No telemetry, proxying, or
     relay connections are made.  The target address is never modified by this
     module.

────────────────────────────────────────────────────────────────────────────────

Authentication options:
  - SSH: password or private-key file
  - Windows: username + password (invokes wmic/PowerShell via SSH or WinRM-style
    subprocesses on the local machine — does NOT require pywinrm)

  - Installed software list
  - Running services / processes
  - Local user accounts
  - Applied patches / OS version
  - Open listening ports (ss/netstat)
  - Sudoers / privilege escalation hints (Linux)
  - Failed login attempts (last 24 h)

Authentication options:
  - SSH: password or private-key file
  - Windows: username + password (invokes wmic/PowerShell via SSH or WinRM-style
    subprocesses on the local machine — does NOT require pywinrm)

No new pip dependencies required — uses stdlib subprocess + the optional
paramiko if available (graceful fallback to openssh subprocess if not).
"""

from __future__ import annotations

import platform
import re
import shutil
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
    pass

ProgressCB = Optional[Callable[[str], None]]


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
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
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
        client.connect(**connect_kwargs)

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
        "-o", "StrictHostKeyChecking=no",
        "-o", "BatchMode=no",
        "-o", f"ConnectTimeout={int(timeout)}",
        "-p", str(port),
    ]
    if key_path:
        base_args += ["-i", key_path]

    env_extra: dict = {}
    prefix: List[str] = []
    if password and not key_path:
        sshpass = shutil.which("sshpass")
        if sshpass:
            prefix = [sshpass, "-p", password]
        # If no sshpass we'll try anyway (may prompt — CI won't work but GUI use is fine)

    for cmd in commands:
        if stop.is_set():
            break
        if progress:
            progress(f"→ {cmd[:60]}")
        try:
            full = prefix + base_args + [f"{username}@{host}", cmd]
            proc = subprocess.run(
                full, capture_output=True, text=True,
                timeout=timeout + 5, env=None,
            )
            results[cmd] = proc.stdout if proc.stdout else proc.stderr
        except subprocess.TimeoutExpired:
            results[cmd] = "(timeout)"
        except Exception as exc:
            results[cmd] = f"(error: {exc})"
    return results


# ── Linux/macOS command set ───────────────────────────────────────────────────

_LINUX_CMDS: List[str] = [
    # OS identification
    "uname -a",
    "cat /etc/os-release 2>/dev/null || cat /etc/issue",
    # Installed packages (try common package managers)
    "dpkg -l 2>/dev/null | awk 'NR>5{print $2,$3}' | head -200",
    "rpm -qa --queryformat '%{NAME} %{VERSION}\\n' 2>/dev/null | head -200",
    # Running services
    "systemctl list-units --type=service --state=running --no-pager --no-legend 2>/dev/null | awk '{print $1,$4}' | head -100",
    "service --status-all 2>&1 | head -100",
    # Listening ports
    "ss -tlnup 2>/dev/null || netstat -tlnup 2>/dev/null",
    # Local users (non-system: uid>=1000 on Linux)
    "awk -F: '$3>=1000{print $1,$3,$6,$7}' /etc/passwd",
    # Last logins
    "last -n 20 2>/dev/null",
    # Failed logins last 24 h
    "grep 'Failed password' /var/log/auth.log 2>/dev/null | grep \"$(date +'%b %d')\" | wc -l",
    "grep 'Failed password' /var/log/secure 2>/dev/null | grep \"$(date +'%b %d')\" | wc -l",
    # Sudo NOPASSWD
    "grep -r NOPASSWD /etc/sudoers /etc/sudoers.d/ 2>/dev/null",
    # Pending updates (Ubuntu/Debian)
    "apt-get -s upgrade 2>/dev/null | grep '^Inst' | wc -l",
    # Pending updates (RHEL/CentOS)
    "yum check-update --quiet 2>/dev/null | grep -v '^$' | wc -l",
]


# ── Parser — Linux ────────────────────────────────────────────────────────────

def _parse_linux(outputs: dict[str, str]) -> CredScanResult:
    result = CredScanResult(host="", os_type="linux")

    # OS version
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

    # Installed packages (dpkg)
    for key in outputs:
        if "dpkg" in key:
            for line in outputs[key].splitlines():
                parts = line.split(None, 1)
                if len(parts) == 2:
                    result.software.append(SoftwareEntry(name=parts[0], version=parts[1], source="dpkg"))
            break
    # rpm fallback
    if not result.software:
        for key in outputs:
            if "rpm" in key:
                for line in outputs[key].splitlines():
                    parts = line.split(None, 1)
                    if len(parts) == 2:
                        result.software.append(SoftwareEntry(name=parts[0], version=parts[1], source="rpm"))
                break

    # Services (systemctl)
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

    # Listening ports
    for key in outputs:
        if "ss -t" in key or "netstat" in key:
            for line in outputs[key].splitlines():
                m = re.search(r'(tcp|udp).*?[*\d.]+:(\d+)\s', line, re.I)
                if m:
                    result.listening_ports.append(
                        ListeningPort(protocol=m.group(1).lower(), port=int(m.group(2)))
                    )
            break

    # Users
    for key in outputs:
        if "/etc/passwd" in key:
            for line in outputs[key].splitlines():
                parts = line.split(None, 3)
                if len(parts) >= 4:
                    result.users.append(UserEntry(
                        username=parts[0], uid=parts[1], home=parts[2], shell=parts[3]
                    ))
            break

    # Failed logins
    for key in outputs:
        if "Failed password" in key or "auth.log" in key or "secure" in key:
            try:
                result.failed_logins += int(outputs[key].strip() or "0")
            except ValueError:
                pass

    # Sudo NOPASSWD
    for key in outputs:
        if "NOPASSWD" in key:
            for line in outputs[key].splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    result.sudo_nopasswd_entries.append(line)
            break

    # Pending updates
    for key in outputs:
        if "apt-get" in key or "yum check" in key:
            try:
                n = int(outputs[key].strip() or "0")
                if n > 0:
                    result.patch_info.pending_updates = max(result.patch_info.pending_updates, n)
            except ValueError:
                pass

    return result


# ── Windows command set (via SSH to a Windows box with OpenSSH installed) ─────

_WINDOWS_CMDS: List[str] = [
    # OS version
    "wmic os get Caption,Version,LastBootUpTime /value",
    # Hardware serial number
    "wmic bios get SerialNumber /value",
    # Active interactive sessions (who is logged in right now)
    "query session",
    # Installed software
    "wmic product get Name,Version /value",
    # Running services
    "sc query type= service state= running",
    # Local users
    "wmic useraccount get Name,SID,Disabled /value",
    # Listening ports + process
    "netstat -ano | findstr LISTENING",
    # Pending updates (Windows Update COM object via PowerShell)
    'powershell -NoProfile -Command "(New-Object -ComObject Microsoft.Update.Session).CreateUpdateSearcher().Search(\'IsInstalled=0\').Updates | Select-Object -ExpandProperty Title | Measure-Object -Line | Select-Object -ExpandProperty Lines"',
    # Failed logins last 24 h
    "powershell -NoProfile -Command \"Get-WinEvent -FilterHashtable @{LogName='Security';Id=4625;StartTime=(Get-Date).AddHours(-24)} -ErrorAction SilentlyContinue | Measure-Object | Select-Object -ExpandProperty Count\"",
]


def _parse_windows(outputs: dict[str, str]) -> CredScanResult:
    result = CredScanResult(host="", os_type="windows")

    for key in outputs:
        if "wmic os" in key:
            txt = outputs[key]
            m = re.search(r'Caption=(.+)', txt)
            if m:
                result.patch_info.os_version = m.group(1).strip()
            m = re.search(r'Version=(.+)', txt)
            if m:
                result.patch_info.kernel = m.group(1).strip()
            break

    for key in outputs:
        if "wmic product" in key:
            name = ver = ""
            for line in outputs[key].splitlines():
                m = re.match(r'Name=(.+)', line)
                if m:
                    name = m.group(1).strip()
                m = re.match(r'Version=(.+)', line)
                if m:
                    ver = m.group(1).strip()
                if name and ver:
                    result.software.append(SoftwareEntry(name=name, version=ver, source="wmic"))
                    name = ver = ""
            break

    for key in outputs:
        if "sc query" in key:
            svc_name = ""
            for line in outputs[key].splitlines():
                m = re.match(r'SERVICE_NAME: (.+)', line)
                if m:
                    svc_name = m.group(1).strip()
                if svc_name and "RUNNING" in line:
                    result.services.append(ServiceEntry(name=svc_name, status="running"))
                    svc_name = ""
            break

    for key in outputs:
        if "wmic bios" in key:
            m = re.search(r'SerialNumber=(.+)', outputs[key])
            if m:
                result.serial_number = m.group(1).strip()
            break

    for key in outputs:
        if "query session" in key:
            sessions: List[str] = []
            for line in outputs[key].splitlines()[1:]:   # skip header
                line = line.strip()
                if not line:
                    continue
                # Format after split:
                #   4 tokens → [SESSIONNAME, USERNAME, ID, STATE]
                #   3 tokens → [USERNAME, ID, STATE]  (no session name col)
                parts = line.split()
                if len(parts) < 3:
                    continue
                state = parts[-1].lower()
                if state not in ("active", "conn"):
                    continue
                # USERNAME is the second-to-last-of-fixed columns:
                # 4 tokens: session username id state → parts[1]
                # 3 tokens: username id state        → parts[0]
                username_col = parts[1] if len(parts) >= 4 else parts[0]
                username_col = username_col.lstrip(">")
                if username_col and username_col not in ("0", "1", "2", "3", "4", "5"):
                    sessions.append(username_col)
            result.active_sessions = sessions
            break

    for key in outputs:
        if "wmic useraccount" in key:
            name = sid = disabled = ""
            for line in outputs[key].splitlines():
                m = re.match(r'Name=(.+)', line)
                if m:
                    name = m.group(1).strip()
                m = re.match(r'SID=(.+)', line)
                if m:
                    sid = m.group(1).strip()
                m = re.match(r'Disabled=(.+)', line)
                if m:
                    disabled = m.group(1).strip()
                if name and sid:
                    result.users.append(UserEntry(username=name, uid=sid))
                    name = sid = disabled = ""
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
            try:
                result.patch_info.pending_updates = int(outputs[key].strip() or "0")
            except ValueError:
                pass

    for key in outputs:
        if "4625" in key:
            try:
                result.failed_logins = int(outputs[key].strip() or "0")
            except ValueError:
                pass

    return result


# ── Public API ────────────────────────────────────────────────────────────────

def credentialed_ssh_scan(
    host: str,
    *,
    ssh_port: int = 22,
    username: str = "root",
    password: Optional[str] = None,
    key_path: Optional[str] = None,
    os_hint: str = "auto",
    timeout: float = 15.0,
    progress_cb: ProgressCB = None,
    stop_event: Optional[threading.Event] = None,
) -> CredScanResult:
    """
    Main entry point.  Connects via SSH and returns a CredScanResult.

    os_hint: "linux" | "windows" | "macos" | "auto" (detect from uname)
    """
    stop = stop_event or threading.Event()
    result = CredScanResult(host=host)

    if not PARAMIKO_AVAILABLE and not shutil.which("ssh"):
        result.error = (
            "Neither paramiko nor the system ssh binary is available. "
            "Install paramiko (pip install paramiko) or ensure openssh-client is installed."
        )
        return result

    # Detect OS
    probe_cmd = ["uname -s"]
    try:
        if PARAMIKO_AVAILABLE:
            probe = _run_ssh_paramiko(host, ssh_port, username, password, key_path,
                                      probe_cmd, timeout, progress_cb, stop)
        else:
            probe = _run_ssh_subprocess(host, ssh_port, username, password, key_path,
                                        probe_cmd, timeout, progress_cb, stop)
    except Exception as exc:
        result.error = str(exc)
        return result

    uname_out = probe.get("uname -s", "").strip().lower()
    if os_hint == "auto":
        if "linux" in uname_out:
            os_hint = "linux"
        elif "darwin" in uname_out:
            os_hint = "macos"
        elif "windows" in uname_out or "windows" in probe.get("uname -s", "").lower():
            os_hint = "windows"
        else:
            os_hint = "linux"   # best guess

    result.os_type = os_hint

    # Run full command set
    cmds = _WINDOWS_CMDS if os_hint == "windows" else _LINUX_CMDS
    if progress_cb:
        progress_cb(f"OS detected: {os_hint} — running {len(cmds)} commands…")

    try:
        if PARAMIKO_AVAILABLE:
            outputs = _run_ssh_paramiko(host, ssh_port, username, password, key_path,
                                        cmds, timeout, progress_cb, stop)
        else:
            outputs = _run_ssh_subprocess(host, ssh_port, username, password, key_path,
                                          cmds, timeout, progress_cb, stop)
    except Exception as exc:
        result.error = str(exc)
        return result

    # Parse
    if os_hint == "windows":
        parsed = _parse_windows(outputs)
    else:
        parsed = _parse_linux(outputs)

    # Merge parsed into result (keep host)
    result.os_type = parsed.os_type
    result.software = parsed.software
    result.services = parsed.services
    result.users = parsed.users
    result.patch_info = parsed.patch_info
    result.listening_ports = parsed.listening_ports
    result.failed_logins = parsed.failed_logins
    result.sudo_nopasswd_entries = parsed.sudo_nopasswd_entries
    result.raw_notes = parsed.raw_notes

    if progress_cb:
        progress_cb(f"Done — {result.plain_verdict}")
    return result
