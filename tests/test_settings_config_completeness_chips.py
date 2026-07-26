"""
Phase 3.4 -- repoint the two lying config-completeness chips.

tray/alerts_enabled was read but never written anywhere -> the "Notifications"
chip was permanently green regardless of actual state. digest/enabled +
digest/email were likewise read-only orphans -> the "Weekly Digest" chip was
permanently grey even after the real notif/weekly_digest_enabled toggle was
turned on. Both chips now derive from the real, live-written keys.
"""
from __future__ import annotations

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtCore import QSettings  # noqa: E402

from ui.pages.settings_page import SettingsPage  # noqa: E402
from modules.alert_suppressor import _default_rules, rule_settings_key  # noqa: E402

_CHANNEL_KEYS = ("toast", "webhook", "email", "pushover", "ntfy", "telegram")


def _clear_all():
    qs = QSettings("NetSentinel", "NetSentinel")
    for r in _default_rules():
        qs.remove(rule_settings_key(r.name))
    for k in _CHANNEL_KEYS:
        qs.remove(f"notif/{k}_enabled")
    qs.remove("notif/weekly_digest_enabled")
    qs.remove("tray/alerts_enabled")
    qs.remove("digest/enabled")
    qs.remove("digest/email")
    qs.sync()
    return qs


def _make_page():
    # "Configuration Status" is already built during __init__() (see the
    # card registry in settings_page.py) -- building it again here would
    # create a second, parentless QFrame that Python's GC then reaps,
    # cascade-deleting the QLabel chips underneath page._cfg_chips.
    return SettingsPage()


def _chip_stylesheet(page, key):
    return page._cfg_chips[key].styleSheet()


class TestNotificationsChip:
    def test_grey_when_no_rule_and_no_channel_enabled(self):
        _clear_all()
        try:
            page = _make_page()
            page.refresh_config_completeness()
            assert _chip_stylesheet(page, "notifications") == page._chip_style("grey")
        finally:
            _clear_all()

    def test_amber_when_only_a_rule_is_enabled(self):
        qs = _clear_all()
        try:
            qs.setValue(rule_settings_key("Host Down"), True)
            page = _make_page()
            page.refresh_config_completeness()
            assert _chip_stylesheet(page, "notifications") == page._chip_style("amber")
        finally:
            _clear_all()

    def test_amber_when_only_a_channel_is_enabled(self):
        qs = _clear_all()
        try:
            qs.setValue("notif/toast_enabled", True)
            page = _make_page()
            page.refresh_config_completeness()
            assert _chip_stylesheet(page, "notifications") == page._chip_style("amber")
        finally:
            _clear_all()

    def test_green_when_both_a_rule_and_a_channel_are_enabled(self):
        qs = _clear_all()
        try:
            qs.setValue(rule_settings_key("Host Down"), True)
            qs.setValue("notif/toast_enabled", True)
            page = _make_page()
            page.refresh_config_completeness()
            assert _chip_stylesheet(page, "notifications") == page._chip_style("green")
        finally:
            _clear_all()

    def test_ignores_the_dead_tray_alerts_enabled_key(self):
        """A stray tray/alerts_enabled=True must no longer force the chip green."""
        qs = _clear_all()
        try:
            qs.setValue("tray/alerts_enabled", True)
            page = _make_page()
            page.refresh_config_completeness()
            assert _chip_stylesheet(page, "notifications") == page._chip_style("grey")
        finally:
            _clear_all()


class TestDigestChip:
    def test_grey_when_disabled(self):
        _clear_all()
        try:
            page = _make_page()
            page.refresh_config_completeness()
            assert _chip_stylesheet(page, "digest") == page._chip_style("grey")
        finally:
            _clear_all()

    def test_green_when_weekly_digest_enabled(self):
        qs = _clear_all()
        try:
            qs.setValue("notif/weekly_digest_enabled", True)
            page = _make_page()
            page.refresh_config_completeness()
            assert _chip_stylesheet(page, "digest") == page._chip_style("green")
        finally:
            _clear_all()

    def test_ignores_the_dead_digest_email_and_enabled_keys(self):
        qs = _clear_all()
        try:
            qs.setValue("digest/enabled", True)
            qs.setValue("digest/email", "a@b.com")
            page = _make_page()
            page.refresh_config_completeness()
            assert _chip_stylesheet(page, "digest") == page._chip_style("grey")
        finally:
            _clear_all()
