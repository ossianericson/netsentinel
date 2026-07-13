"""Regression tests for the 0x8001010d UIA/COM startup fault (RULE-WIN10).

Mechanism (proved with procdump + cdb — see docs/spikes/splash-uia-com-fault.md):
the FIRST WM_GETOBJECT a process ever answers makes Qt call
UiaReturnRawElementProvider, whose one-time UIAutomationCore init (CheckInit ->
DoInit) does a CoCreateInstance. WM_GETOBJECT is always delivered as an
input-synchronous cross-process SendMessage, and COM refuses outgoing calls from
a thread in that state -> RPC_E_CANTCALLOUT_ININPUTSYNCCALL, raised as SEH and
logged by faulthandler's vectored (first-chance) handler.

`warm_up_uia_provider()` performs that one-time init from a SAFE context (a
same-thread SendMessage is a direct WndProc call, so the thread is not inside an
input-synchronous call) during startup, before any client can connect.

Two tiers:
  * fast unit tests — no pywinauto, run in the normal suite / commit gate. They
    guard the wiring: the helper sends the right message, and app.py calls it.
  * `monkey`-marked end-to-end — launches the REAL app.py with LOCALAPPDATA
    redirected to a temp dir and attaches a pywinauto UIA client, then asserts
    the child's crash log never records 0x8001010d. This is the test that
    actually reproduces the bug; the unit tests cannot.  Run with:
        python -m pytest tests/test_uia_warmup.py -m monkey -v

A constructed Dashboard is useless here — the fault needs the real process and a
real UIA client, so the e2e case is a subprocess (also RULE-TP4-DASH).
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

pytest.importorskip("PyQt6")

if sys.platform != "win32":
    pytest.skip("UIA/COM fault is Windows-only", allow_module_level=True)

from ui.uia_warmup import (  # noqa: E402
    UIA_ROOT_OBJECT_ID,
    WM_GETOBJECT,
    warm_up_uia_provider,
)


# ── Fast unit tests (no pywinauto; run in the commit gate) ────────────────────

def test_constants_match_win32():
    """The two magic numbers the fix depends on. Wrong values = silent no-op."""
    assert WM_GETOBJECT == 0x003D
    assert UIA_ROOT_OBJECT_ID == -25


def test_warm_up_sends_wm_getobject_to_the_given_hwnd(monkeypatch):
    """The helper must SendMessage WM_GETOBJECT/UIA_ROOT_OBJECT_ID, not something else."""
    from ui import uia_warmup as mod

    sent: list[tuple] = []

    def fake_send(hwnd, msg, wparam, lparam):
        sent.append((hwnd, msg, wparam, lparam))
        return 65536  # non-zero = UIA returned a provider

    mod._reset_for_tests()
    monkeypatch.setattr(mod._user32, "SendMessageW", fake_send)

    assert warm_up_uia_provider(0x1234) is True
    assert sent == [(0x1234, WM_GETOBJECT, 0, UIA_ROOT_OBJECT_ID)]


def test_warm_up_reports_failure_when_qt_returns_no_provider(monkeypatch):
    """LRESULT 0 means Qt did not hand UIA a provider — the init did NOT happen.

    Callers rely on the False to retry on a later window; silently latching here
    would leave the process cold and the fault would still fire.
    """
    from ui import uia_warmup as mod

    mod._reset_for_tests()
    monkeypatch.setattr(mod._user32, "SendMessageW", lambda *a: 0)
    assert warm_up_uia_provider(0x1234) is False


def test_warm_up_is_idempotent_after_success(monkeypatch):
    """Only the first successful call does work; later calls are free no-ops."""
    from ui import uia_warmup as mod

    calls = []
    mod._reset_for_tests()
    monkeypatch.setattr(mod._user32, "SendMessageW", lambda *a: calls.append(a) or 65536)

    assert warm_up_uia_provider(1) is True
    assert warm_up_uia_provider(2) is True
    assert warm_up_uia_provider(3) is True
    assert len(calls) == 1, "warmup must not re-run once UIA core is initialised"


def test_warm_up_never_raises(monkeypatch):
    """Startup must survive a warmup failure — it is an optimisation, not a feature."""
    from ui import uia_warmup as mod

    mod._reset_for_tests()

    def boom(*_a):
        raise OSError("SendMessageW exploded")

    monkeypatch.setattr(mod._user32, "SendMessageW", boom)
    assert warm_up_uia_provider(0x1234) is False


def test_app_py_calls_the_warmup_during_startup():
    """Guard the wiring: deleting the call site silently reintroduces the fault.

    The unit tests above all pass against an app.py that never calls the helper,
    so without this guard the whole fix could be removed and the suite stay green.
    """
    tree = ast.parse((REPO / "app.py").read_text(encoding="utf-8"))
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "warm_up_uia_provider" in called, (
        "app.py must call warm_up_uia_provider() during startup — without it the "
        "first WM_GETOBJECT from any UIA client (chaos harness, Narrator, NVDA) "
        "raises 0x8001010d. See RULE-WIN10."
    )


# ── End-to-end: the test that actually reproduces the fault ──────────────────

@pytest.mark.monkey
@pytest.mark.slow
def test_real_app_logs_no_com_fault_when_a_uia_client_attaches(tmp_path):
    """RED before the fix, GREEN after.

    Launches the real app.py (a constructed Dashboard skips the startup path) with
    LOCALAPPDATA pointed at tmp_path, so get_app_data_dir() — and therefore
    faulthandler's crash log — lands in a throwaway directory that starts empty.
    Then attaches a UIA client, exactly as tools/monkey_test.py does.
    """
    pytest.importorskip("pywinauto")
    from pywinauto import Desktop

    env = dict(os.environ)
    env["LOCALAPPDATA"] = str(tmp_path)
    crash_log = tmp_path / "NetSentinel" / "netsentinel_crash.log"

    def _window_for_pid(pid: int):
        """Our window, via a PID-filtered Desktop scan — the way monkey_test.py does it.

        Deliberately NOT Application.top_window(): a bare top_window()/descendants()
        walk of this ~60-page app is unreliable and fails identically on unmodified
        HEAD, so building the assertion on it would misreport a flaky lookup as a
        poisoned UIA provider. Each windows() scan is itself cross-process UIA
        traffic, which is exactly the WM_GETOBJECT this test needs to provoke.
        """
        for w in Desktop(backend="uia").windows():
            try:
                if w.element_info.process_id == pid:
                    return w
            except Exception:  # noqa: BLE001
                continue  # a foreign window we cannot inspect — not ours; keep scanning
        return None

    app = subprocess.Popen([sys.executable, "app.py"], cwd=str(REPO), env=env)
    try:
        # The single-instance guard makes a second instance exit(0) immediately.
        time.sleep(5)
        if app.poll() is not None:
            pytest.skip(
                "app.py exited at once — a NetSentinel instance is already running "
                "(single-instance guard). Close it and re-run."
            )

        win = None
        deadline = time.time() + 90
        while win is None and time.time() < deadline:
            try:
                win = _window_for_pid(app.pid)
            except Exception:  # noqa: BLE001
                win = None  # transient UIA scan error — retry until the deadline
            if win is None:
                time.sleep(1.0)

        assert win is not None, (
            "no UIA window for the app's PID within 90s — the client could not see "
            "the app at all."
        )

        # THE assertion that matters. The warmup must silence the fault WITHOUT
        # breaking accessibility: one that registered a broken provider would still
        # satisfy the crash-log check below while leaving the app undriveable by the
        # monkey harness — the exact regression this test missed on its first draft.
        title = win.window_text()          # forces a cross-process WM_GETOBJECT
        assert title, (
            "UIA client resolved the window but could not read its title — the UIA "
            "provider is broken. The warmup must silence the fault WITHOUT breaking "
            "accessibility."
        )

        # Further WM_GETOBJECT traffic, to give the fault every chance to fire.
        # descendants() is driven but NOT asserted on — see _window_for_pid().
        for _ in range(8):
            try:
                win.descendants()
            except Exception:  # noqa: BLE001
                pass  # flaky on this app with and without the warmup — traffic only
            time.sleep(0.5)
        time.sleep(2)  # let faulthandler flush if it fired
    finally:
        app.terminate()
        try:
            app.wait(timeout=15)
        except subprocess.TimeoutExpired:
            app.kill()

    if not crash_log.exists():
        return  # nothing logged at all — the strongest possible pass

    text = crash_log.read_text(encoding="utf-8", errors="replace")
    assert "8001010d" not in text.lower(), (
        "0x8001010d (RPC_E_CANTCALLOUT_ININPUTSYNCCALL) was logged when a UIA "
        "client attached — the UIA provider warmup did not run or did not take. "
        f"Crash log:\n{text[:2000]}"
    )
