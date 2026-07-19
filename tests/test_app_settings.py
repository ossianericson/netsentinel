"""
tests/test_app_settings.py — regression coverage for the maximized-restore
placement fix.

The WINDOWPLACEMENT rcNormal correction used to run via a
QTimer.singleShot(0, ...) in app.py, one event-loop tick AFTER _splash.close()
revealed the deliberately-unpainted maximized window (see the comments in
ui/app_settings.py::restore_settings()). That native SetWindowPlacement call
could force a frame/NC recalculation while Qt's first paint was still in
flight; under normal load the gap was invisible, but under chaos/monkey-test
CPU contention it could expose the unpainted backbuffer as a solid
white/black flash on every 2nd+ app launch (never on a fresh install, since
window/maximized only ever saves True after a prior maximized close) — and
it raises no exception, so it never appears in netsentinel_crash.log or
netsentinel_exceptions.log.

The fix moves the correction onto the window's native handle, still inside
restore_settings() itself but AFTER window.showMaximized() rather than
before — calling it before forces window.winId() to create the native HWND
ahead of Qt's own show() call, which collapses the window to its minimum
size (see reapply_geometry_after_chrome()'s docstring in the same file) and
desyncs any coordinate-based automation from the window's real bounds. A
first attempt at this fix placed the call before showMaximized() and caused
exactly that: a chaos/monkey run got permanently stuck on one page, never
advancing, with no exception anywhere. These tests guard the corrected
ordering.
"""
import platform
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ui.app_settings import fix_maximized_restore_rect

_REPO_ROOT = Path(__file__).resolve().parent.parent


def test_app_py_no_longer_defers_the_placement_fix_past_the_reveal():
    """
    app.py must not schedule the WINDOWPLACEMENT correction after the window
    is shown / the splash closes — that deferred-past-reveal call is the
    mechanism that produced the white/black flash under monkey testing.
    """
    src = (_REPO_ROOT / "app.py").read_text(encoding="utf-8")
    assert "_pending_normal_geo" not in src
    assert "_fix_geo" not in src


def test_restore_settings_calls_the_fix_after_show_maximized():
    """
    Source-order guard: fix_maximized_restore_rect(...) must be called AFTER
    window.showMaximized() inside restore_settings(). Calling it before forces
    window.winId() to create the native HWND ahead of Qt's own show() call,
    which collapses the window to its minimum size (see
    reapply_geometry_after_chrome()'s docstring) — this desynced pywinauto's
    coordinate-based automation from the window's real bounds and caused a
    chaos/monkey run to get permanently stuck on one page, never advancing.
    """
    src = (_REPO_ROOT / "ui" / "app_settings.py").read_text(encoding="utf-8")
    body = src[src.index("def restore_settings("):]
    fix_pos = body.index("fix_maximized_restore_rect(")
    show_pos = body.index("window.showMaximized()")
    assert show_pos < fix_pos, "the placement fix must run after showMaximized(), not before"


@pytest.mark.skipif(platform.system() != "Windows", reason="ctypes.windll is Windows-only")
def test_fix_maximized_restore_rect_reads_then_writes_window_placement():
    window = MagicMock()
    window.winId.return_value = 12345
    with patch("ctypes.windll.user32.GetWindowPlacement") as mock_get, \
         patch("ctypes.windll.user32.SetWindowPlacement") as mock_set:
        fix_maximized_restore_rect(window, 100, 50, 1440, 900)
    mock_get.assert_called_once()
    mock_set.assert_called_once()


def test_fix_maximized_restore_rect_is_a_noop_off_windows(monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    window = MagicMock()
    fix_maximized_restore_rect(window, 100, 50, 1440, 900)
    window.winId.assert_not_called()


def test_fix_maximized_restore_rect_swallows_bad_input():
    window = MagicMock()
    # Must not raise even with garbage coordinates.
    fix_maximized_restore_rect(window, "not-a-number", None, 1440, 900)
