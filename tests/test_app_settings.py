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
from PyQt6.QtCore import QRect, QSettings

from ui.app_settings import apply_exact_geometry, fix_maximized_restore_rect

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


# --- Off-screen restore-rect clamp (RULE-T3 regression coverage) ---
#
# A rect saved under one monitor arrangement (docked to external displays)
# can reference coordinates no longer on any connected screen once the
# arrangement changes (undocked, RDP, resolution change). Nothing validated
# the saved window/normal_x/y or window/geo_x/y against currently-connected
# screens before feeding them into setGeometry()/SetWindowPlacement, so the
# window could restore partly or wholly off-screen. Reported via a chaos
# harness's SW_RESTORE call un-maximizing the window onto a stale rect.

def test_clamp_rect_to_screen_leaves_onscreen_rect_unchanged():
    from ui.app_settings import _clamp_rect_to_screen
    screen = MagicMock()
    screen.availableGeometry.return_value = QRect(0, 0, 1920, 1080)
    with patch("PyQt6.QtWidgets.QApplication.screenAt", return_value=screen):
        result = _clamp_rect_to_screen(100, 50, 1440, 900)
    assert result == (100, 50, 1440, 900)


def test_clamp_rect_to_screen_moves_offscreen_rect_onto_current_screen():
    from ui.app_settings import _clamp_rect_to_screen
    screen = MagicMock()
    screen.availableGeometry.return_value = QRect(0, 0, 1920, 1080)
    # screenAt() returns None for a point off every connected screen — the
    # helper must fall back to primaryScreen().
    with patch("PyQt6.QtWidgets.QApplication.screenAt", return_value=None), \
         patch("PyQt6.QtWidgets.QApplication.primaryScreen", return_value=screen):
        x, y, w, h = _clamp_rect_to_screen(9000, 9000, 1440, 900)
    # QRect.right()/bottom() are inclusive edges — contain via x+w rather
    # than comparing x against right() directly (off-by-one at the boundary).
    assert 0 <= x and x + w <= 1920
    assert 0 <= y and y + h <= 1080


def test_clamp_rect_to_screen_shrinks_oversized_rect():
    from ui.app_settings import _clamp_rect_to_screen
    screen = MagicMock()
    screen.availableGeometry.return_value = QRect(0, 0, 1920, 1080)
    with patch("PyQt6.QtWidgets.QApplication.screenAt", return_value=screen):
        x, y, w, h = _clamp_rect_to_screen(0, 0, 3440, 1440)
    assert w <= 1920
    assert h <= 1080


def test_clamp_rect_to_screen_returns_input_when_no_screen_available():
    from ui.app_settings import _clamp_rect_to_screen
    with patch("PyQt6.QtWidgets.QApplication.screenAt", return_value=None), \
         patch("PyQt6.QtWidgets.QApplication.primaryScreen", return_value=None):
        result = _clamp_rect_to_screen(9000, 9000, 1440, 900)
    assert result == (9000, 9000, 1440, 900)


def test_apply_exact_geometry_clamps_offscreen_saved_rect(tmp_path):
    s = QSettings(str(tmp_path / "test.ini"), QSettings.Format.IniFormat)
    s.setValue("window/geo_x", 9000)
    s.setValue("window/geo_y", 9000)
    s.setValue("window/geo_w", 1440)
    s.setValue("window/geo_h", 900)
    s.sync()

    window = MagicMock()
    screen = MagicMock()
    screen.availableGeometry.return_value = QRect(0, 0, 1920, 1080)
    with patch("PyQt6.QtWidgets.QApplication.screenAt", return_value=None), \
         patch("PyQt6.QtWidgets.QApplication.primaryScreen", return_value=screen):
        applied = apply_exact_geometry(window, s)

    assert applied is True
    window.setGeometry.assert_called_once()
    x, y, w, h = window.setGeometry.call_args[0]
    assert 0 <= x and x + w <= 1920
    assert 0 <= y and y + h <= 1080


def test_apply_exact_geometry_does_not_alter_onscreen_rect(tmp_path):
    s = QSettings(str(tmp_path / "test.ini"), QSettings.Format.IniFormat)
    s.setValue("window/geo_x", 100)
    s.setValue("window/geo_y", 50)
    s.setValue("window/geo_w", 1440)
    s.setValue("window/geo_h", 900)
    s.sync()

    window = MagicMock()
    screen = MagicMock()
    screen.availableGeometry.return_value = QRect(0, 0, 1920, 1080)
    with patch("PyQt6.QtWidgets.QApplication.screenAt", return_value=screen):
        apply_exact_geometry(window, s)

    window.setGeometry.assert_called_once_with(100, 50, 1440, 900)
