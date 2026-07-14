"""Tests for ui/pages/maintenance_page.py"""
from __future__ import annotations

import pytest

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)


@pytest.fixture
def page():
    from ui.pages.maintenance_page import MaintenancePage
    p = MaintenancePage()
    yield p
    try:
        p.deleteLater()
    except RuntimeError:
        pass  # already deleted
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


def test_import():
    from ui.pages.maintenance_page import MaintenancePage  # noqa: F401


def test_instantiation(page):
    assert page is not None


def test_widget_is_not_none(page):
    assert page is not None


def test_loads_without_windows(page):
    """Page should render correctly when no maintenance windows exist."""
    refresh = getattr(page, "_load_windows", None) or getattr(page, "refresh", None)
    if refresh:
        refresh()
    assert page is not None


# ── F-40 claims-audit: recurring daily windows ──────────────────────────────
#
# ui/help.py's Maintenance Windows entry claims "Windows are one-time or
# recurring -- set a recurring window for regular router reboots or backup
# jobs." modules/maintenance_window.py's MaintenanceWindow dataclass already
# has daily_start_hour/daily_end_hour fields and is_currently_active() already
# handles them (including overnight wraparound) -- but _WindowDialog never
# exposed them, so every UI-created window was one-time only.

def _teardown_widget(w):
    try:
        w.deleteLater()
    except RuntimeError:
        pass  # already deleted
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


def test_window_dialog_get_window_supports_recurring():
    from ui.pages.maintenance_page import _WindowDialog

    dlg = _WindowDialog()
    try:
        dlg._recurring_chk.setChecked(True)
        dlg._recur_start_hour.setValue(22)
        dlg._recur_end_hour.setValue(6)
        w = dlg.get_window()
        assert w.daily_start_hour == 22
        assert w.daily_end_hour == 6
    finally:
        _teardown_widget(dlg)


def test_window_dialog_defaults_to_non_recurring():
    from ui.pages.maintenance_page import _WindowDialog

    dlg = _WindowDialog()
    try:
        w = dlg.get_window()
        assert w.daily_start_hour is None
        assert w.daily_end_hour is None
    finally:
        _teardown_widget(dlg)


def test_window_dialog_edit_prepopulates_recurring_fields():
    from ui.pages.maintenance_page import _WindowDialog
    from modules.maintenance_window import MaintenanceWindow

    existing = MaintenanceWindow(
        label="Nightly quiet hours", start_ts=0, end_ts=3600,
        daily_start_hour=23, daily_end_hour=7,
    )
    dlg = _WindowDialog(window=existing)
    try:
        assert dlg._recurring_chk.isChecked() is True
        assert dlg._recur_start_hour.value() == 23
        assert dlg._recur_end_hour.value() == 7
    finally:
        _teardown_widget(dlg)


def test_window_status_recurring_active_now():
    """_window_status() must report a currently-in-range recurring window as
    Active, not derive status from its (ignored, dummy) absolute start/end
    timestamps."""
    import time as _time
    from ui.pages.maintenance_page import _window_status
    from modules.maintenance_window import MaintenanceWindow

    hour = _time.localtime().tm_hour
    w = MaintenanceWindow(
        label="Always active now", start_ts=0, end_ts=1,  # dummy, must be ignored
        daily_start_hour=hour, daily_end_hour=(hour + 1) % 24,
    )
    status, _color = _window_status(w)
    assert status == "Active"


def test_window_status_recurring_shows_recurring_label_when_not_active():
    """A recurring window outside its daily range must not read 'Expired' or
    'Scheduled' (those imply a one-off absolute window that has passed or not
    yet begun -- meaningless for a window that recurs every day)."""
    import time as _time
    from ui.pages.maintenance_page import _window_status
    from modules.maintenance_window import MaintenanceWindow

    hour = _time.localtime().tm_hour
    out_of_range_start = (hour + 2) % 24
    out_of_range_end = (hour + 3) % 24
    w = MaintenanceWindow(
        label="Not active now", start_ts=0, end_ts=1,
        daily_start_hour=out_of_range_start, daily_end_hour=out_of_range_end,
    )
    status, _color = _window_status(w)
    assert status not in ("Expired", "Scheduled")
