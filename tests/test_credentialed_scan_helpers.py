"""Tests for modules/credentialed_scan_helpers.py — see also test_sprint20_splits.py."""


def test_import():
    import modules.credentialed_scan_helpers as m
    assert hasattr(m, "CredScanResult")
    assert hasattr(m, "_LINUX_CMDS")
    assert hasattr(m, "_WINDOWS_CMDS")
    assert hasattr(m, "_parse_linux")
    assert hasattr(m, "_parse_windows")


def test_cred_scan_result_instantiation():
    from modules.credentialed_scan_helpers import CredScanResult
    r = CredScanResult(host="10.0.0.1", os_type="linux")
    assert r.host == "10.0.0.1"
    assert r.failed_logins == 0
    assert r.software == []


def test_parse_linux_no_crash():
    from modules.credentialed_scan_helpers import _parse_linux
    result = _parse_linux({
        "uname -a": "Linux myhost 5.15 #1 SMP x86_64 GNU/Linux",
        "dpkg -l 2>/dev/null | awk 'NR>5{print $2,$3}' | head -200": "bash 5.1.16",
    })
    assert result.os_type == "linux"


def test_command_lists_non_empty():
    from modules.credentialed_scan_helpers import _LINUX_CMDS, _WINDOWS_CMDS
    assert len(_LINUX_CMDS) >= 10
    assert len(_WINDOWS_CMDS) >= 5


def test_paramiko_available_is_bool():
    from modules.credentialed_scan_helpers import PARAMIKO_AVAILABLE
    assert isinstance(PARAMIKO_AVAILABLE, bool)
