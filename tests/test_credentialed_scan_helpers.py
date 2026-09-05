"""Tests for modules/credentialed_scan_helpers.py — see also test_sprint20_splits.py."""
import re


def test_import():
    from modules import credentialed_scan_helpers as m
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


def test_parse_linux_last_update_from_dpkg_log():
    from modules.credentialed_scan_helpers import _parse_linux
    result = _parse_linux({
        "uname -a": "Linux myhost 5.15 #1 SMP x86_64 GNU/Linux",
        "tail -n1 /var/log/dpkg.log 2>/dev/null":
            "2024-06-01 10:23:47 status installed bash:amd64 5.1-3ubuntu1",
    })
    assert result.patch_info.last_update == "2024-06-01 10:23:47"


def test_parse_linux_last_update_falls_back_to_rpm():
    from modules.credentialed_scan_helpers import _parse_linux
    result = _parse_linux({
        "uname -a": "Linux myhost 5.15 #1 SMP x86_64 GNU/Linux",
        "tail -n1 /var/log/dpkg.log 2>/dev/null": "",
        "rpm -qa --last 2>/dev/null | head -1":
            "bash-5.1.8-6.el9.x86_64              Wed 01 Jun 2024 10:23:45 AM UTC",
    })
    assert result.patch_info.last_update == "Wed 01 Jun 2024 10:23:45 AM UTC"


def test_parse_windows_last_update_from_hotfix():
    from modules.credentialed_scan_helpers import _parse_windows
    result = _parse_windows({
        "powershell -NoProfile -Command \"Get-HotFix | Sort-Object InstalledOn "
        "-Descending | Select-Object -First 1 -ExpandProperty InstalledOn\"":
            "6/1/2024 12:00:00 AM",
    })
    assert result.patch_info.last_update == "6/1/2024 12:00:00 AM"


# ── The Windows service list ──────────────────────────────────────────────────

def test_sc_query_uses_a_state_value_sc_actually_accepts():
    """`sc query state= running` is rejected by sc.exe — on every Windows, every locale.

    Measured on the development machine: `sc query type= service state= running`
    exits **87** with `ERROR: Invalid state= field` and prints no service data, so
    `CredScanResult.services` has always been empty on the Windows credentialed-scan
    path. `state=` takes `active`, `inactive` or `all` — `running` is not one of
    them; bare `sc query` works because it defaults to `type= service state= active`.

    Not a locale defect at all, which is why no amount of fixing the *parser* would
    have helped: the data never arrived.
    """
    from modules.credentialed_scan_helpers import _WINDOWS_CMDS

    sc_cmds = [c for c in _WINDOWS_CMDS if c.startswith("sc query")]
    assert sc_cmds, "the service-enumeration command disappeared"
    for cmd in sc_cmds:
        m = re.search(r"state=\s*(\S+)", cmd)
        if m:
            assert m.group(1) in ("active", "inactive", "all"), (
                "sc.exe rejects state= %r with exit 87" % m.group(1)
            )


def test_a_running_service_is_identified_by_its_numeric_state_code():
    """`STATE : 4  RUNNING` — the 4 is the answer, the word beside it is decoration.

    Verbatim shape from this machine's real `sc query`. Reading the number rather
    than the word costs nothing and removes a translated token from the path; it
    also tightens the match, because `state= active` returns START_PENDING (2) and
    PAUSED (7) services too, which "running" should not claim.

    No sample of a *translated* `sc query` was available — sc.exe printed English on
    this Swedish install — so this is taken on structure, not on an observed miss.
    """
    from modules.credentialed_scan_helpers import _parse_windows

    key = "sc query type= service state= active"
    out = {key: (
        "\nSERVICE_NAME: Spooler\n"
        "DISPLAY_NAME: Print Spooler\n"
        "        TYPE               : 10  WIN32_OWN_PROCESS  \n"
        "        STATE              : 4  WIRD_AUSGEFÜHRT \n"
        "                                (STOPPABLE, NOT_PAUSABLE, ACCEPTS_SHUTDOWN)\n"
        "        WIN32_EXIT_CODE    : 0  (0x0)\n"
    )}
    names = [s.name for s in _parse_windows(out).services]
    assert names == ["Spooler"], names


def test_a_service_that_is_not_running_is_not_reported_as_running():
    from modules.credentialed_scan_helpers import _parse_windows

    key = "sc query type= service state= active"
    out = {key: (
        "\nSERVICE_NAME: StartingUp\n"
        "        STATE              : 2  START_PENDING \n"
        "\nSERVICE_NAME: Spooler\n"
        "        STATE              : 4  RUNNING \n"
    )}
    names = [s.name for s in _parse_windows(out).services]
    assert names == ["Spooler"], names


def test_the_real_sc_query_block_still_parses():
    """Verbatim from `sc query` on the development machine — the shape must not move."""
    from modules.credentialed_scan_helpers import _parse_windows

    key = "sc query type= service state= active"
    out = {key: (
        "\nSERVICE_NAME: AIFrameworkService\n"
        "DISPLAY_NAME: AIFrameworkService\n"
        "        TYPE               : 10  WIN32_OWN_PROCESS  \n"
        "        STATE              : 4  RUNNING \n"
        "                                (STOPPABLE, NOT_PAUSABLE, ACCEPTS_SHUTDOWN)\n"
        "        WIN32_EXIT_CODE    : 0  (0x0)\n"
        "        SERVICE_EXIT_CODE  : 0  (0x0)\n"
        "        CHECKPOINT         : 0x0\n"
        "        WAIT_HINT          : 0x0\n"
    )}
    result = _parse_windows(out)
    assert [s.name for s in result.services] == ["AIFrameworkService"]
    assert result.services[0].status == "running"
