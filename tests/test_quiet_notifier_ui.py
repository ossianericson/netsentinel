"""
Phase 2.5 -- wire the quiet-notifier UI.

modules/quiet_notifier.py (check_and_maybe_notify, called from app.py:1550-1561)
was a fully-implemented feature with NO UI control anywhere -- a user could
never discover or enable "all quiet" summaries. Adds a checkbox + hour spinbox
to the Morning Briefing card (notif_extra_channels.py), persisted via the real
ENABLED_KEY/NOTIFY_HOUR_KEY constants from modules.quiet_notifier so the two
modules can never drift on key spelling.
"""
from __future__ import annotations

import pytest

pytest.importorskip("PyQt6.QtWidgets")


def _make_page():
    from ui.pages.notifications_page import NotificationsPage
    return NotificationsPage()


def _clear_quiet_keys():
    from PyQt6.QtCore import QSettings
    from modules.quiet_notifier import ENABLED_KEY, NOTIFY_HOUR_KEY
    qs = QSettings("NetSentinel", "NetSentinel")
    qs.remove(ENABLED_KEY)
    qs.remove(NOTIFY_HOUR_KEY)
    qs.sync()
    return qs


class TestQuietNotifierControlsExist:
    def test_checkbox_and_spinbox_exist(self):
        _clear_quiet_keys()
        page = _make_page()
        assert hasattr(page, "_chk_quiet_notify")
        assert hasattr(page, "_spin_quiet_notify_hour")

    def test_defaults_match_module_defaults(self):
        _clear_quiet_keys()
        page = _make_page()
        assert page._chk_quiet_notify.isChecked() is False
        assert page._spin_quiet_notify_hour.value() == 8


class TestQuietNotifierPersistence:
    def test_settings_round_trip_uses_real_module_keys(self):
        from modules.quiet_notifier import ENABLED_KEY, NOTIFY_HOUR_KEY

        qs = _clear_quiet_keys()
        try:
            page_a = _make_page()
            page_a._chk_quiet_notify.setChecked(True)
            page_a._spin_quiet_notify_hour.setValue(21)

            assert qs.value(ENABLED_KEY, False, type=bool) is True
            assert int(qs.value(NOTIFY_HOUR_KEY, 8)) == 21

            page_b = _make_page()
            assert page_b._chk_quiet_notify.isChecked() is True
            assert page_b._spin_quiet_notify_hour.value() == 21
        finally:
            _clear_quiet_keys()

    def test_checking_the_box_does_not_touch_toast_settings(self):
        """The quiet-notifier tray call in app.py is deliberately ungated by
        notif/toast_enabled -- confirm this UI never writes that key."""
        qs = _clear_quiet_keys()
        qs.remove("notif/toast_enabled")
        try:
            page = _make_page()
            page._chk_quiet_notify.setChecked(True)
            assert not qs.contains("notif/toast_enabled")
        finally:
            _clear_quiet_keys()
