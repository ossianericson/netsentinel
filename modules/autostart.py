"""
modules/autostart.py — Autostart backend selector + shared interface
======================================================================
Chooses between the WinRT StartupTask backend (Store/MSIX builds, where the
classic Run key is not the sanctioned autostart surface) and the legacy HKCU
Run-key backend (winget/portable installs). Run-key logic moved here from
ui/system_tray.py (ARCH RULE 1: pure Python, no PyQt).

autostart_state()/set_autostart() return the state that ACTUALLY resulted, never
the requested one - DisabledByUser/DisabledByPolicy/EnabledByPolicy cannot be
overridden programmatically. can_user_change_autostart() gives the UI a
user-facing reason. This is the structural fix for the "lying checkbox" bug:
see docs/spikes/startup-task-winrt.md's RULE-REQ2 paragraph for why the old
unconditional set_run_on_startup() call was replaced rather than patched.

For the "startup_task" backend, callers must be on a worker thread that has
already called modules.startup_task.ro_initialize() - see
workers/autostart_worker.py. This module itself never touches COM apartment
state directly.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from modules.utils import is_store_app

_STARTUP_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_STARTUP_NAME = "NetSentinel"

# Must match uap5:StartupTask's TaskId in packaging/AppxManifest.xml — a
# mismatch means GetAsync() fails with ERROR_NOT_FOUND even inside a real
# packaged build, identical to the unpackaged "no manifest entry" case
# measured in docs/spikes/startup-task-winrt.md, for a different reason.
STARTUP_TASK_ID = "NetSentinelLogger"


@dataclass
class AutostartState:
    backend: str                      # "startup_task" | "run_key" | "none"
    enabled: bool
    can_change: bool
    reason: str                       # user-facing explanation when can_change is False
    raw_state: Optional[int] = None   # startup_task.STATE_* - "startup_task" backend only
    hresult: Optional[int] = None     # "startup_task" backend only


def autostart_backend() -> str:
    if sys.platform != "win32":
        return "none"
    return "startup_task" if is_store_app() else "run_key"


# ── Run-key backend (moved from ui/system_tray.py) ──────────────────────────

def get_run_on_startup() -> bool:
    """Return True if the startup registry entry exists (Windows only)."""
    if sys.platform != "win32":
        return False
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _STARTUP_KEY, 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, _STARTUP_NAME)
        winreg.CloseKey(key)
        return True
    except (OSError, ImportError):
        return False


def set_run_on_startup(enabled: bool) -> None:
    """Add or remove the HKCU Run registry entry (Windows only, no-op elsewhere)."""
    if sys.platform != "win32":
        return
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _STARTUP_KEY, 0, winreg.KEY_SET_VALUE)
        if enabled:
            exe = _resolve_exe_path()
            winreg.SetValueEx(key, _STARTUP_NAME, 0, winreg.REG_SZ, f'"{exe}" --startup-logger')
        else:
            try:
                winreg.DeleteValue(key, _STARTUP_NAME)
            except OSError:
                pass  # already absent
        winreg.CloseKey(key)
    except (OSError, ImportError):
        pass  # non-fatal


def _resolve_exe_path() -> str:
    """Return the path to NetSentinel.exe (packaged) or python + app.py (dev)."""
    if getattr(sys, "frozen", False):
        return sys.executable  # PyInstaller single-exe
    root = Path(__file__).parent.parent
    app_py = root / "app.py"
    return f"{sys.executable} {app_py}"


# ── Shared interface ─────────────────────────────────────────────────────

def can_user_change_autostart(raw_state: Optional[int]) -> Tuple[bool, str]:
    """Given a StartupTaskState (or None), can the app change it programmatically?"""
    from modules import startup_task as _st
    if raw_state == _st.STATE_DISABLED_BY_POLICY:
        return False, "Your organization's policy has disabled this for NetSentinel."
    if raw_state == _st.STATE_ENABLED_BY_POLICY:
        return False, "Your organization's policy has enabled this for NetSentinel."
    if raw_state == _st.STATE_DISABLED_BY_USER:
        return False, "You turned this off in Windows Settings > Apps > Startup. Change it there."
    return True, ""


def _startup_task_state_to_autostart_state(hr: int, raw_state: Optional[int]) -> AutostartState:
    from modules import startup_task as _st
    can_change, reason = can_user_change_autostart(raw_state)
    enabled = raw_state in (_st.STATE_ENABLED, _st.STATE_ENABLED_BY_POLICY)
    return AutostartState(backend="startup_task", enabled=enabled, can_change=can_change,
                           reason=reason, raw_state=raw_state, hresult=hr)


def autostart_state() -> AutostartState:
    """
    Synchronous for the run_key/none backends. For "startup_task", the caller
    must already be on a worker thread with RoInitialize done (see
    workers/autostart_worker.py).
    """
    backend = autostart_backend()
    if backend == "none":
        return AutostartState(backend="none", enabled=False, can_change=False,
                               reason="Autostart is only available on Windows")
    if backend == "run_key":
        return AutostartState(backend="run_key", enabled=get_run_on_startup(), can_change=True, reason="")

    from modules import startup_task as _st
    hr, state = _st.get_task_state(STARTUP_TASK_ID)
    return _startup_task_state_to_autostart_state(hr, state)


def set_autostart(enabled: bool) -> AutostartState:
    """Returns the state that ACTUALLY resulted, never the requested one."""
    backend = autostart_backend()
    if backend == "none":
        return AutostartState(backend="none", enabled=False, can_change=False,
                               reason="Autostart is only available on Windows")
    if backend == "run_key":
        set_run_on_startup(enabled)
        return AutostartState(backend="run_key", enabled=get_run_on_startup(), can_change=True, reason="")

    from modules import startup_task as _st
    if enabled:
        hr, state = _st.request_enable(STARTUP_TASK_ID)
    else:
        hr, state = _st.disable_task(STARTUP_TASK_ID)
    return _startup_task_state_to_autostart_state(hr, state)
