"""
Phase 7.8 -- welcome-overlay coherence.

_notif_desktop_chk defaulted checked and wrote notif/toast_enabled=True, but
every alert rule stayed off (RULES_OPT_IN default-disabled) -- a user who
never opened Notifications got a channel with nothing to deliver. Checking
the box now also opts into the 5 recommended rules, so the grant is actually
coherent.
"""
from __future__ import annotations

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtCore import QSettings  # noqa: E402
from PyQt6.QtWidgets import QApplication, QWidget  # noqa: E402

from ui.first_run_dialog import WelcomeOverlay  # noqa: E402
from ui.pages.notif_channel_panels import _RECOMMENDED_RULES  # noqa: E402
from modules.alert_suppressor import rule_settings_key  # noqa: E402


def _clear_keys(qs):
    qs.remove("notif/toast_enabled")
    for name in _RECOMMENDED_RULES:
        qs.remove(rule_settings_key(name))
    qs.sync()


def _make_overlay():
    """Returns (overlay, parent) -- the caller must keep BOTH referenced.
    overlay is a Qt-child of parent; parent going out of scope and being
    GC'd cascades a C++-level delete onto overlay too (RULE-WIN8)."""
    QApplication.instance() or QApplication([])
    parent = QWidget()
    parent.resize(1024, 768)
    return WelcomeOverlay(parent), parent


def _cleanup(overlay, parent):
    try:
        overlay.deleteLater()
    except RuntimeError:
        pass  # already destroyed — safe to skip
    try:
        parent.deleteLater()
    except RuntimeError:
        pass  # already destroyed — safe to skip
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


class TestCheckedGrantsCoherentChannel:
    def test_checkbox_label_names_what_it_grants(self):
        """The checkbox used to say only 'Desktop notifications (recommended)',
        implying it grants a delivery channel alone -- misleading now that
        checking it also opts into 5 alert rules."""
        overlay, parent = _make_overlay()
        try:
            label = overlay._notif_desktop_chk.text()
            assert label != "Desktop notifications (recommended)"
            assert label.strip() != ""
        finally:
            _cleanup(overlay, parent)

    def test_checked_enables_toast_and_the_five_recommended_rules(self):
        qs = QSettings("NetSentinel", "NetSentinel")
        _clear_keys(qs)
        overlay, parent = _make_overlay()
        try:
            overlay._notif_desktop_chk.setChecked(True)
            overlay._save_notif_prefs()

            assert qs.value("notif/toast_enabled", False, type=bool) is True
            for name in _RECOMMENDED_RULES:
                assert qs.value(rule_settings_key(name), False, type=bool) is True, (
                    f"{name} should be opted in when desktop notifications are enabled"
                )
        finally:
            _cleanup(overlay, parent)
            _clear_keys(qs)


class TestUncheckedGrantsNothing:
    def test_unchecked_disables_toast_and_writes_no_rule_keys(self):
        qs = QSettings("NetSentinel", "NetSentinel")
        _clear_keys(qs)
        overlay, parent = _make_overlay()
        try:
            overlay._notif_desktop_chk.setChecked(False)
            overlay._save_notif_prefs()

            assert qs.value("notif/toast_enabled", True, type=bool) is False
            for name in _RECOMMENDED_RULES:
                assert not qs.contains(rule_settings_key(name)), (
                    f"{name} must not be written when desktop notifications are declined"
                )
        finally:
            _cleanup(overlay, parent)
            _clear_keys(qs)
