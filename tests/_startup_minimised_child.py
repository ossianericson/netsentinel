"""Subprocess child for tests/test_startup_show_sequence.py (Phase 5.5).

NOT collected by pytest (leading-underscore filename). Mirrors
tests/_lazy_pages_child.py's contract exactly — see that file's docstring
for why a fully-constructed Dashboard must never be built in-process
(RULE-TP4-DASH): `main(name)` runs the named test body and calls
`os._exit(0)`/`os._exit(1)` on success/failure; the parent asserts on the
child's return code.
"""
from __future__ import annotations

import os
import sys
import traceback
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication

_APP: QApplication | None = None


def _ensure_app() -> QApplication:
    global _APP
    if _APP is None:
        _APP = QApplication.instance() or QApplication(["netsentinel-test", "-platform", "offscreen"])
    return _APP


@contextmanager
def _reset_nav_restore_state():
    """See tests/_lazy_pages_child.py's identical helper for why this matters."""
    from ui.app_settings import settings_path
    qs = QSettings(str(settings_path()), QSettings.Format.IniFormat)
    saved_section = qs.value("nav/last_section", "")
    saved_page = qs.value("nav/last_page", "")
    qs.setValue("nav/last_section", "")
    qs.setValue("nav/last_page", "")
    qs.sync()
    try:
        yield
    finally:
        qs.setValue("nav/last_section", saved_section)
        qs.setValue("nav/last_page", saved_page)
        qs.sync()


def _onscreen_test_rect() -> tuple[int, int, int, int]:
    """A window rect guaranteed to fit inside the current primaryScreen's
    availableGeometry(), so seeding it through restore_settings()'s
    off-screen clamp (_clamp_rect_to_screen() in ui/app_settings.py) is a
    no-op. Used by fixtures asserting pass-through plumbing rather than the
    clamp itself — the offscreen Qt platform's virtual screen can be smaller
    than a real desktop's, so a hardcoded 1440x900 is not always on-screen."""
    from PyQt6.QtWidgets import QApplication
    avail = QApplication.instance().primaryScreen().availableGeometry()
    nw = min(1440, max(100, avail.width() - 20))
    nh = min(900, max(100, avail.height() - 20))
    nx = avail.x() + 10
    ny = avail.y() + 10
    return nx, ny, nw, nh


@contextmanager
def _seed_maximized_last_session():
    """Force restore_settings() down its was_maximized branch — the only
    branch that ever calls showMaximized(), and therefore the only one the
    tray-only-launch bug (RULE-STARTUP1) can affect."""
    from ui.app_settings import settings_path
    qs = QSettings(str(settings_path()), QSettings.Format.IniFormat)
    keys = ("window/maximized", "window/normal_x", "window/normal_y",
            "window/normal_width", "window/normal_height")
    saved = {k: qs.value(k) for k in keys}
    nx, ny, nw, nh = _onscreen_test_rect()
    qs.setValue("window/maximized", "True")
    qs.setValue("window/normal_x", nx)
    qs.setValue("window/normal_y", ny)
    qs.setValue("window/normal_width", nw)
    qs.setValue("window/normal_height", nh)
    qs.sync()
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                qs.remove(k)
            else:
                qs.setValue(k, v)
        qs.sync()


@contextmanager
def _seed_offscreen_maximized_last_session():
    """Force restore_settings() down its was_maximized branch with a rect
    saved under a different monitor arrangement than the one connected now —
    regression coverage for the off-screen-restore bug (RULE-T3)."""
    from ui.app_settings import settings_path
    qs = QSettings(str(settings_path()), QSettings.Format.IniFormat)
    keys = ("window/maximized", "window/normal_x", "window/normal_y",
            "window/normal_width", "window/normal_height")
    saved = {k: qs.value(k) for k in keys}
    qs.setValue("window/maximized", "True")
    qs.setValue("window/normal_x", 90000)
    qs.setValue("window/normal_y", 90000)
    qs.setValue("window/normal_width", 1440)
    qs.setValue("window/normal_height", 900)
    qs.sync()
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                qs.remove(k)
            else:
                qs.setValue(k, v)
        qs.sync()


def test_offscreen_normal_rect_gets_clamped_onto_current_screen() -> None:
    """THE RED TEST (RULE-T3): before the fix, restore_settings() fed the raw
    saved window/normal_x/y straight into _pending_maximize_restore_rect (and
    from there into the native SetWindowPlacement call) with no check against
    which screens are actually connected now — a rect saved under a different
    monitor arrangement restored the window off-screen. Reported via a chaos
    harness's ShowWindow(hwnd, SW_RESTORE) call un-maximizing onto the stale
    rect; the underlying gap exists independent of the harness."""
    _ensure_app()
    from PyQt6.QtWidgets import QApplication
    from ui.dashboard import Dashboard

    with _reset_nav_restore_state(), _seed_offscreen_maximized_last_session():
        dash = Dashboard(store=None, start_minimised=True)

    rect = dash._pending_maximize_restore_rect
    assert rect is not None
    rnx, rny, rnw, rnh = rect
    screen = QApplication.primaryScreen()
    assert screen is not None
    avail = screen.availableGeometry()
    rnx_i, rny_i = int(rnx), int(rny)
    # QRect.right()/bottom() are inclusive edges (x + width - 1), so contain
    # the rect via x + w <= left + width rather than x <= right() - w.
    assert avail.left() <= rnx_i and rnx_i + rnw <= avail.left() + avail.width()
    assert avail.top() <= rny_i and rny_i + rnh <= avail.top() + avail.height()

    dash.close()


def test_start_minimised_true_not_visible_pending_maximized() -> None:
    """THE RED TEST (RULE-T3): before the fix, restore_settings() called
    window.showMaximized() unconditionally, so a tray-only launch whose last
    session was maximized showed a full window anyway — the reported bug."""
    _ensure_app()
    from ui.dashboard import Dashboard

    with _reset_nav_restore_state(), _seed_maximized_last_session():
        dash = Dashboard(store=None, start_minimised=True)

    assert dash.isVisible() is False
    assert dash._pending_show_maximized is True
    # nx/ny come straight off QSettings (IniFormat stores/reads text); nw/nh
    # are int-cast in restore_settings() before this tuple is built — the
    # same shape the placement-rect fixup normalizes internally. The seeded
    # rect is on-screen by construction (_onscreen_test_rect()), so the
    # off-screen clamp is a no-op here and the values must round-trip exactly.
    rect = dash._pending_maximize_restore_rect
    assert rect is not None
    rnx, rny, rnw, rnh = rect
    assert (int(rnx), int(rny), rnw, rnh) == _onscreen_test_rect()

    dash.close()


def test_start_minimised_false_still_maximized_and_visible() -> None:
    """Guards the atomic splash->app transition (RULE-WIN12/RULE-STARTUP1):
    a normal launch must be completely unaffected by the start_minimised
    plumbing — still shown maximized during construction, no deferral."""
    _ensure_app()
    from ui.dashboard import Dashboard

    with _reset_nav_restore_state(), _seed_maximized_last_session():
        dash = Dashboard(store=None, start_minimised=False)

    assert dash.isVisible() is True
    assert dash.isMaximized() is True
    assert dash._pending_show_maximized is False

    dash.close()


_TESTS = {
    "test_start_minimised_true_not_visible_pending_maximized": test_start_minimised_true_not_visible_pending_maximized,
    "test_start_minimised_false_still_maximized_and_visible": test_start_minimised_false_still_maximized_and_visible,
    "test_offscreen_normal_rect_gets_clamped_onto_current_screen": test_offscreen_normal_rect_gets_clamped_onto_current_screen,
}


def main(name: str) -> None:
    fn = _TESTS.get(name)
    if fn is None:
        sys.stderr.write(f"unknown test: {name!r}; valid: {sorted(_TESTS)}\n")
        os._exit(2)
    try:
        fn()
    except (Exception, KeyboardInterrupt, SystemExit):  # noqa: BLE001 — report ANY failure via exit code
        traceback.print_exc()
        sys.stderr.flush()
        os._exit(1)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.stderr.write("usage: _startup_minimised_child.py <test_name>\n")
        os._exit(2)
    main(sys.argv[1])
