"""
Credentialed Deep Scan — public entry point.

Dataclasses, SSH backends, and output parsers live in
modules/credentialed_scan_helpers.py (S20-2 sprint split).

─── CREDENTIAL HANDLING ────────────────────────────────────────────────────────

  1. In-memory only.
     SSH password and private-key path are accepted as function arguments and
     held only in local variables for the duration of the SSH session.
     They are never assigned to any attribute of CredScanResult or any other
     persistent object, and are never written to disk in any form.

  2. Not included in any report output.
     CredScanResult — the only object passed to report_exporter — contains no
     password, key material, or authentication token fields.

  3. No outbound connections outside the target host.

Authentication options:
  - SSH: password or private-key file
  - Windows: username + password (invokes PowerShell via SSH — no pywinrm needed)
"""

from __future__ import annotations

import threading
from typing import Optional

from modules.credentialed_scan_helpers import (
    PARAMIKO_AVAILABLE, ProgressCB,
    SoftwareEntry, ServiceEntry, UserEntry, PatchInfo,
    ListeningPort, CredScanResult,
    _run_ssh_paramiko, _run_ssh_subprocess,
    _LINUX_CMDS, _WINDOWS_CMDS,
    _parse_linux, _parse_windows,
)

# Re-export all public names so existing callers continue to work.
__all__ = [
    "PARAMIKO_AVAILABLE", "ProgressCB",
    "SoftwareEntry", "ServiceEntry", "UserEntry", "PatchInfo",
    "ListeningPort", "CredScanResult",
    "credentialed_ssh_scan",
]


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
    import shutil
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
