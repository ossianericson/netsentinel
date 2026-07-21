"""
tests/test_settings_startup_card.py — RULE-T7 behavioral test for the
Settings "Start NetSentinel automatically" checkbox (Phase 5).

Drives the real SettingsPage card (no Dashboard, RULE-TP4-DASH does not
apply — this is a plain QWidget) through the full toggle -> AutostartWorker
-> result_ready chain (RULE-T5), asserting the checkbox ends up disabled with
a tooltip naming Windows Settings when Windows reports DisabledByUser — the
state that can't be overridden programmatically and needs to say so honestly.
"""
from __future__ import annotations

import importlib.util

import pytest

if importlib.util.find_spec("PyQt6") is None:
    pytest.skip("PyQt6 not available", allow_module_level=True)

from PyQt6.QtWidgets import QApplication

from modules import autostart, startup_task
from ui.pages.settings_page import SettingsPage


def _pump():
    app = QApplication.instance()
    for _ in range(5):
        app.processEvents()


def test_disabled_by_user_locks_checkbox_with_windows_settings_tooltip(monkeypatch):
    monkeypatch.setattr(autostart, "autostart_backend", lambda: "startup_task")
    monkeypatch.setattr(
        startup_task, "get_task_state",
        lambda task_id: (0, startup_task.STATE_DISABLED_BY_USER),
    )

    page = SettingsPage()
    page._start_autostart_worker()  # simulate the showEvent()-triggered query

    assert page._autostart_worker is not None
    assert page._autostart_worker.wait(5000)
    _pump()

    assert page._chk_startup.isChecked() is False
    assert page._chk_startup.isEnabled() is False
    tooltip = page._chk_startup.toolTip()
    assert "Windows Settings" in tooltip

    page.deleteLater()
    _pump()


def test_disabled_by_policy_locks_checkbox_with_policy_tooltip(monkeypatch):
    monkeypatch.setattr(autostart, "autostart_backend", lambda: "startup_task")
    monkeypatch.setattr(
        startup_task, "get_task_state",
        lambda task_id: (0, startup_task.STATE_DISABLED_BY_POLICY),
    )

    page = SettingsPage()
    page._start_autostart_worker()
    assert page._autostart_worker.wait(5000)
    _pump()

    assert page._chk_startup.isEnabled() is False
    assert "policy" in page._chk_startup.toolTip().lower()

    page.deleteLater()
    _pump()


def test_enabled_state_leaves_checkbox_checked_and_editable(monkeypatch):
    monkeypatch.setattr(autostart, "autostart_backend", lambda: "startup_task")
    monkeypatch.setattr(
        startup_task, "get_task_state",
        lambda task_id: (0, startup_task.STATE_ENABLED),
    )

    page = SettingsPage()
    page._start_autostart_worker()
    assert page._autostart_worker.wait(5000)
    _pump()

    assert page._chk_startup.isChecked() is True
    assert page._chk_startup.isEnabled() is True
    assert page._chk_startup.toolTip() == ""

    page.deleteLater()
    _pump()


def test_in_flight_state_shows_asking_windows_tooltip(monkeypatch):
    """RULE-UX2: the checkbox must show a visible in-flight state, not just
    silently sit there while the WinRT call is outstanding."""
    monkeypatch.setattr(autostart, "autostart_backend", lambda: "run_key")
    monkeypatch.setattr(autostart, "set_run_on_startup", lambda enabled: None)
    monkeypatch.setattr(autostart, "get_run_on_startup", lambda: True)

    page = SettingsPage()
    page._on_startup_toggled(True)

    assert page._chk_startup.isEnabled() is False
    assert "Asking Windows…" in page._chk_startup.toolTip()

    assert page._autostart_worker.wait(5000)
    _pump()
    page.deleteLater()
    _pump()
