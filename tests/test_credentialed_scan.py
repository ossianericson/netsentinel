"""
Tests for modules/credentialed_scan.py

Covers:
  - CredScanResult dataclass: fields, risk_flags, plain_verdict
  - _parse_windows: OS version, serial number, active sessions, software,
    services, users, listening ports, failed logins
  - _parse_linux: OS version, packages, services, users, listening ports,
    failed logins, sudo NOPASSWD, pending updates
"""
from __future__ import annotations

from unittest.mock import patch

from modules.credentialed_scan import (
    CredScanResult, SoftwareEntry, ServiceEntry, UserEntry,
    ListeningPort,
    _parse_windows, _parse_linux,
    _WINDOWS_CMDS,
    credentialed_ssh_scan,
)
from modules.credentialed_scan_helpers import SSHUnreachableError


# ── CredScanResult: defaults ──────────────────────────────────────────────────

def test_result_defaults():
    r = CredScanResult(host="10.0.0.1")
    assert r.host == "10.0.0.1"
    assert r.os_type == ""
    assert r.serial_number == ""
    assert r.active_sessions == []
    assert r.software == []
    assert r.services == []
    assert r.users == []
    assert r.failed_logins == 0
    assert r.sudo_nopasswd_entries == []


def test_result_risk_flags_empty():
    r = CredScanResult(host="x")
    assert r.risk_flags == []


def test_result_risk_flag_nopasswd():
    r = CredScanResult(host="x", sudo_nopasswd_entries=["alice ALL=(ALL) NOPASSWD:ALL"])
    flags = r.risk_flags
    assert any("NOPASSWD" in f for f in flags)


def test_result_risk_flag_failed_logins():
    r = CredScanResult(host="x", failed_logins=15)
    flags = r.risk_flags
    assert any("15" in f for f in flags)


def test_result_risk_flag_pending_updates():
    r = CredScanResult(host="x")
    r.patch_info.pending_updates = 20
    flags = r.risk_flags
    assert any("20" in f for f in flags)


def test_result_risk_flag_uid0_non_root():
    r = CredScanResult(host="x", users=[UserEntry(username="hacker", uid="0")])
    flags = r.risk_flags
    assert any("hacker" in f for f in flags)


def test_plain_verdict_error():
    r = CredScanResult(host="x", error="timeout")
    assert "Scan failed" in r.plain_verdict
    assert "timeout" in r.plain_verdict


def test_plain_verdict_ok():
    r = CredScanResult(
        host="x", os_type="windows",
        software=[SoftwareEntry(name="Python")],
        services=[ServiceEntry(name="svc")],
        users=[UserEntry(username="alice")],
        listening_ports=[ListeningPort(protocol="tcp", port=80)],
    )
    v = r.plain_verdict
    assert "1 packages" in v
    assert "1 services" in v
    assert "1 users" in v
    assert "1 listening" in v


def test_not_testable_defaults_false():
    r = CredScanResult(host="x")
    assert r.not_testable is False
    assert r.not_testable_reason == ""


def test_plain_verdict_not_testable():
    r = CredScanResult(host="10.0.0.9", not_testable=True, not_testable_reason="refused")
    v = r.plain_verdict
    assert "Could not test" in v
    assert "refused" in v
    assert "Scan failed" not in v


# ── credentialed_ssh_scan(): connection-refused vs auth-failure (Sprint 5b D) ──

class TestCredentialedSshScanNotTestable:
    """SSH connection-refused/unreachable is genuinely not_testable -- the host
    was never reached, so nothing about its credentials was confirmed. Wrong
    credentials (AuthenticationException) is a REAL, meaningful, testable
    result -- it must keep routing through the existing .error/plain-verdict
    path unchanged, per explicit user decision (Sprint 5b design question)."""

    def test_connection_refused_sets_not_testable(self):
        with patch("modules.credentialed_scan.PARAMIKO_AVAILABLE", True), \
             patch("modules.credentialed_scan._run_ssh_paramiko",
                   side_effect=SSHUnreachableError("Unable to connect to port 22")):
            result = credentialed_ssh_scan("10.0.0.9", password="x")

        assert result.not_testable is True
        assert result.not_testable_reason != ""
        assert "10.0.0.9" in result.not_testable_reason

    def test_authentication_failure_stays_plain_error_not_not_testable(self):
        """A real auth failure is a confirmed result, not a coverage gap."""
        with patch("modules.credentialed_scan.PARAMIKO_AVAILABLE", True), \
             patch("modules.credentialed_scan._run_ssh_paramiko",
                   side_effect=Exception("Authentication failed.")):
            result = credentialed_ssh_scan("10.0.0.9", password="wrong")

        assert result.not_testable is False
        assert result.error != ""

    def test_successful_probe_is_not_not_testable(self):
        with patch("modules.credentialed_scan.PARAMIKO_AVAILABLE", True), \
             patch("modules.credentialed_scan._run_ssh_paramiko",
                   return_value={"uname -s": "Linux"}), \
             patch("modules.credentialed_scan._parse_linux") as mock_parse:
            mock_parse.return_value = CredScanResult(host="")
            result = credentialed_ssh_scan("10.0.0.9", password="x")

        assert result.not_testable is False
        assert result.error == ""


# ── _WINDOWS_CMDS: serial and session commands present ───────────────────────

def test_windows_cmds_include_bios():
    assert any("bios" in c.lower() for c in _WINDOWS_CMDS)


def test_windows_cmds_include_query_session():
    assert any("query session" in c for c in _WINDOWS_CMDS)


# ── _parse_windows: OS version ────────────────────────────────────────────────

_WIN_OS = {
    "powershell -NoProfile -Command \"$o=Get-CimInstance Win32_OperatingSystem; Write-Output ('Caption='+$o.Caption); Write-Output ('Version='+$o.Version)\"": (
        "Caption=Microsoft Windows 11 Pro\r\n"
        "Version=10.0.22621\r\n"
    )
}

def test_parse_windows_os_version():
    r = _parse_windows(_WIN_OS)
    assert "Windows 11" in r.patch_info.os_version
    assert r.patch_info.kernel == "10.0.22621"


# ── _parse_windows: serial number ────────────────────────────────────────────

def test_parse_windows_serial_number():
    outputs = {
        "powershell -NoProfile -Command \"$b=Get-CimInstance Win32_BIOS; Write-Output ('SerialNumber='+$b.SerialNumber)\"":
            "SerialNumber=VMware-42 3a\r\n"
    }
    r = _parse_windows(outputs)
    assert r.serial_number == "VMware-42 3a"


def test_parse_windows_serial_number_empty():
    """Empty CIM output → serial_number stays blank, no crash."""
    outputs = {
        "powershell -NoProfile -Command \"$b=Get-CimInstance Win32_BIOS; Write-Output ('SerialNumber='+$b.SerialNumber)\"":
            "\r\n"
    }
    r = _parse_windows(outputs)
    assert r.serial_number == ""


def test_parse_windows_serial_number_not_present():
    """Key absent from outputs → serial_number stays blank."""
    r = _parse_windows({})
    assert r.serial_number == ""


# ── _parse_windows: active sessions ──────────────────────────────────────────

_QUERY_SESSION_OUTPUT = """\
 SESSIONNAME       USERNAME                 ID  STATE   TYPE        DEVICE
 services                                    0  Disc
 console           alice                     1  Active
                   bob                       2  Active
 rdp-tcp#0         carol                     3  Conn
"""


def test_parse_windows_active_sessions_found():
    outputs = {"query session": _QUERY_SESSION_OUTPUT}
    r = _parse_windows(outputs)
    assert "alice" in r.active_sessions


def test_parse_windows_active_sessions_multiple():
    outputs = {"query session": _QUERY_SESSION_OUTPUT}
    r = _parse_windows(outputs)
    # alice, bob, carol should all be captured
    assert len(r.active_sessions) >= 1


def test_parse_windows_active_sessions_excludes_disc():
    """The 'services' session with STATE=Disc should NOT appear."""
    outputs = {"query session": _QUERY_SESSION_OUTPUT}
    r = _parse_windows(outputs)
    assert "services" not in r.active_sessions


def test_parse_windows_no_sessions():
    """Only a disconnected session → active_sessions is empty."""
    output = (
        " SESSIONNAME       USERNAME                 ID  STATE   TYPE\n"
        " services                                    0  Disc\n"
    )
    outputs = {"query session": output}
    r = _parse_windows(outputs)
    assert r.active_sessions == []


def test_parse_windows_sessions_empty_output():
    outputs = {"query session": ""}
    r = _parse_windows(outputs)
    assert r.active_sessions == []


# ── _parse_windows: software ──────────────────────────────────────────────────

_WIN_PRODUCT = {
    "powershell -NoProfile -Command \"Get-CimInstance Win32_Product | ForEach-Object { Write-Output ('Name='+$_.Name); Write-Output ('Version='+$_.Version) }\"": (
        "Name=Python 3.11.0\r\nVersion=3.11.0\r\n"
        "Name=Git\r\nVersion=2.43.0\r\n"
    )
}

def test_parse_windows_software():
    r = _parse_windows(_WIN_PRODUCT)
    names = [s.name for s in r.software]
    assert "Python 3.11.0" in names
    assert "Git" in names
    assert all(s.source == "cim" for s in r.software)


# ── _parse_windows: services ──────────────────────────────────────────────────

_WIN_SC = {"sc query type= service state= running": (
    "SERVICE_NAME: wuauserv\r\n"
    "DISPLAY_NAME: Windows Update\r\n"
    "        TYPE               : 20  WIN32_SHARE_PROCESS\r\n"
    "        STATE              : 4  RUNNING\r\n"
    "SERVICE_NAME: Spooler\r\n"
    "        STATE              : 4  RUNNING\r\n"
)}

def test_parse_windows_services():
    r = _parse_windows(_WIN_SC)
    names = [s.name for s in r.services]
    assert "wuauserv" in names
    assert "Spooler" in names
    assert all(s.status == "running" for s in r.services)


# ── _parse_windows: users ─────────────────────────────────────────────────────

_WIN_USERS = {
    "powershell -NoProfile -Command \"Get-CimInstance Win32_UserAccount | ForEach-Object { Write-Output ('Name='+$_.Name); Write-Output ('SID='+$_.SID); Write-Output ('Disabled='+$_.Disabled) }\"": (
        "Name=alice\r\nSID=S-1-5-21-1234-1001\r\nDisabled=False\r\n"
        "Name=guest\r\nSID=S-1-5-21-1234-501\r\nDisabled=True\r\n"
    )
}

def test_parse_windows_users():
    r = _parse_windows(_WIN_USERS)
    names = [u.username for u in r.users]
    assert "alice" in names
    assert "guest" in names


# ── _parse_windows: listening ports ──────────────────────────────────────────

_WIN_NETSTAT = {"netstat -ano | findstr LISTENING": (
    "  TCP    0.0.0.0:80             0.0.0.0:0              LISTENING       4\n"
    "  TCP    0.0.0.0:443            0.0.0.0:0              LISTENING       4\n"
    "  TCP    [::]:22                [::]:0                 LISTENING       1234\n"
)}

def test_parse_windows_ports():
    r = _parse_windows(_WIN_NETSTAT)
    ports = [p.port for p in r.listening_ports]
    assert 80 in ports
    assert 443 in ports


# ── _parse_windows: failed logins ────────────────────────────────────────────

def test_parse_windows_failed_logins():
    outputs = {
        "powershell -NoProfile -Command \"Get-WinEvent -FilterHashtable @{LogName='Security';Id=4625": "7\n"
    }
    r = _parse_windows(outputs)
    assert r.failed_logins == 7


# ── _parse_linux: OS version ──────────────────────────────────────────────────

_LINUX_OS_RELEASE = {
    "cat /etc/os-release 2>/dev/null || cat /etc/issue": (
        'PRETTY_NAME="Ubuntu 22.04.3 LTS"\n'
        'NAME="Ubuntu"\n'
        'VERSION_ID="22.04"\n'
    ),
    "uname -a": "Linux homelab 5.15.0-91-generic #101-Ubuntu SMP x86_64 GNU/Linux",
}

def test_parse_linux_os_version():
    r = _parse_linux(_LINUX_OS_RELEASE)
    assert "Ubuntu 22.04" in r.patch_info.os_version


# ── _parse_linux: failed logins ───────────────────────────────────────────────

def test_parse_linux_failed_logins():
    outputs = {
        "grep 'Failed password' /var/log/auth.log 2>/dev/null | grep \"$(date +'%b %d')\" | wc -l": "3\n",
    }
    r = _parse_linux(outputs)
    assert r.failed_logins == 3


# ── _parse_linux: sudo NOPASSWD ───────────────────────────────────────────────

def test_parse_linux_sudo_nopasswd():
    outputs = {
        "grep -r NOPASSWD /etc/sudoers /etc/sudoers.d/ 2>/dev/null": (
            "alice ALL=(ALL) NOPASSWD:ALL\n"
        )
    }
    r = _parse_linux(outputs)
    assert len(r.sudo_nopasswd_entries) == 1
    assert "alice" in r.sudo_nopasswd_entries[0]
    assert "NOPASSWD" in r.risk_flags[0]


# ── _parse_linux: pending updates ────────────────────────────────────────────

def test_parse_linux_pending_updates():
    outputs = {
        "apt-get -s upgrade 2>/dev/null | grep '^Inst' | wc -l": "15\n"
    }
    r = _parse_linux(outputs)
    assert r.patch_info.pending_updates == 15
    assert any("15" in f for f in r.risk_flags)


# ── _parse_linux: empty outputs ───────────────────────────────────────────────

def test_parse_linux_empty_outputs_no_crash():
    r = _parse_linux({})
    assert r.os_type == "linux"
    assert r.software == []
    assert r.services == []


def test_parse_windows_empty_outputs_no_crash():
    r = _parse_windows({})
    assert r.os_type == "windows"
    assert r.serial_number == ""
    assert r.active_sessions == []
