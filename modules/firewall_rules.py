"""
Ensures Windows Firewall outbound rules exist for speed test ports.

Called lazily on the first speed test run. No-op on non-Windows or when
rules are already present. Silent fallback when the process is not elevated.

Ports required by the Ookla protocol:
  TCP 443   — HTTPS (server list + results API)
  TCP 8080  — download/upload measurement streams
  UDP 8080  — download/upload measurement streams
  TCP 5060  — latency probe
  UDP 5060  — latency probe

Rule naming convention (shared with installer.iss and AppxManifest.xml):
  "NetSentinel Speedtest"         TCP  NetSentinel.exe / python.exe
  "NetSentinel Speedtest UDP"     UDP  NetSentinel.exe / python.exe
  "NetSentinel Ookla Speedtest"   TCP  speedtest.exe
  "NetSentinel Ookla Speedtest UDP" UDP speedtest.exe
"""

from __future__ import annotations

import logging
import platform
import subprocess
import sys
from pathlib import Path
from typing import Optional

_log = logging.getLogger(__name__)

_TCP_PORTS = "443,8080,5060"
_UDP_PORTS = "8080,5060"

_RULE_TCP       = "NetSentinel Speedtest"
_RULE_UDP       = "NetSentinel Speedtest UDP"
_RULE_OOKLA_TCP = "NetSentinel Ookla Speedtest"
_RULE_OOKLA_UDP = "NetSentinel Ookla Speedtest UDP"

# Module-level cache flags — avoid re-invoking netsh on every speed test run
_app_rules_done: bool = False
_ookla_rules_done: set[str] = set()


# ── Internal helpers ──────────────────────────────────────────────────────────

def _netsh(*args: str, timeout: int = 10) -> tuple[int, str]:
    """Run a netsh command invisibly. Returns (returncode, combined stdout+stderr)."""
    cmd = ["netsh"] + list(args)
    kw: dict = {}
    if sys.platform == "win32":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0  # SW_HIDE
        kw = {
            "creationflags": subprocess.CREATE_NO_WINDOW,
            "startupinfo": si,
        }
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            **kw,
        )
        return result.returncode, result.stdout + result.stderr
    except Exception as exc:  # noqa: BLE001
        _log.debug("netsh invocation error: %s", exc)
        return -1, str(exc)


def _rule_exists(name: str) -> bool:
    """Return True if a firewall rule with this exact name already exists."""
    # netsh exits non-zero ("No rules match the specified criteria") when the named
    # rule does not exist, so the return code alone answers this — and unlike the
    # previous "Rule Name:" text match it is the same on every Windows locale.
    # That match always failed on localized Windows ("Regelnamn:"/"Nombre de regla:"),
    # so _rule_exists() was permanently False and every process start redundantly
    # deleted and re-added the rules.
    rc, _out = _netsh(
        "advfirewall", "firewall", "show", "rule", f"name={name}"
    )
    return rc == 0


def _add_outbound_rules(
    rule_tcp: str,
    rule_udp: str,
    program: Optional[str],
) -> bool:
    """
    Delete any stale rules with the given names, then add fresh TCP + UDP
    outbound allow rules. Returns True if both additions succeed.
    """
    prog_args = [f"program={program}"] if program else []

    # Delete first so reinstalls are idempotent (ignore errors)
    _netsh("advfirewall", "firewall", "delete", "rule", f"name={rule_tcp}")
    _netsh("advfirewall", "firewall", "delete", "rule", f"name={rule_udp}")

    rc1, err1 = _netsh(
        "advfirewall", "firewall", "add", "rule",
        f"name={rule_tcp}", "dir=out", "action=allow", "protocol=TCP",
        *prog_args,
        f"remoteport={_TCP_PORTS}",
    )
    rc2, err2 = _netsh(
        "advfirewall", "firewall", "add", "rule",
        f"name={rule_udp}", "dir=out", "action=allow", "protocol=UDP",
        *prog_args,
        f"remoteport={_UDP_PORTS}",
    )

    if rc1 != 0:
        _log.debug("netsh TCP rule add failed (rc=%d): %s", rc1, err1.strip())
    if rc2 != 0:
        _log.debug("netsh UDP rule add failed (rc=%d): %s", rc2, err2.strip())

    return rc1 == 0 and rc2 == 0


# ── Public API ────────────────────────────────────────────────────────────────

def ensure_app_rules() -> bool:
    """
    Ensure outbound allow rules exist for the current process executable.

    Covers the Python-based speed test backends (speedtest-cli library and
    pure-Python HTTP streams) which run inside the main application process.

    - Frozen exe (PyInstaller): rules target NetSentinel.exe specifically.
    - Running from source (python app.py): rules target the python.exe interpreter.
    - Non-Windows: returns True immediately (no-op).
    - Not elevated: returns False, logs a warning, does NOT raise or prompt.

    Cached — netsh is invoked at most once per process lifetime.
    """
    global _app_rules_done
    if _app_rules_done or platform.system() != "Windows":
        return True
    _app_rules_done = True  # set before the check so parallel callers don't double-invoke

    if _rule_exists(_RULE_TCP):
        _log.debug("Speedtest firewall rules already present")
        return _app_rules_done

    program = str(Path(sys.executable).resolve())
    ok = _add_outbound_rules(_RULE_TCP, _RULE_UDP, program)
    if ok:
        _log.info("Speedtest firewall rules added for %s", program)
    else:
        _log.warning(
            "Could not add speedtest firewall rules for %s "
            "(admin/elevation required). Speed tests may be slow in restricted environments.",
            program,
        )
    return ok


def ensure_ookla_rules(speedtest_exe: Path) -> bool:
    """
    Ensure outbound allow rules exist for the Ookla speedtest.exe binary.

    Called when speedtest.exe has been located on disk, before the first CLI
    invocation. Idempotent — safe to call on every run; cached per exe path.

    - Non-Windows: returns True immediately (no-op).
    - Not elevated: returns False, logs a warning, does NOT raise or prompt.
    """
    key = str(speedtest_exe.resolve())
    if key in _ookla_rules_done or platform.system() != "Windows":
        return True
    _ookla_rules_done.add(key)

    if _rule_exists(_RULE_OOKLA_TCP):
        _log.debug("Ookla speedtest firewall rules already present")
        return True

    ok = _add_outbound_rules(_RULE_OOKLA_TCP, _RULE_OOKLA_UDP, key)
    if ok:
        _log.info("Ookla speedtest firewall rules added for %s", key)
    else:
        _log.warning(
            "Could not add Ookla speedtest firewall rules for %s "
            "(admin/elevation required). Ookla CLI may be blocked in restricted environments.",
            key,
        )
    return ok
