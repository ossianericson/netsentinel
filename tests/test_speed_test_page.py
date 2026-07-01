"""RULE-T7 behavioral test: automatic speed test toggle on SpeedTestPage (Sprint 3)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytest.importorskip("PyQt6.QtWidgets")


@pytest.fixture
def page(monkeypatch):
    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QApplication
    from ui.pages.speed_test_page import SpeedTestPage

    # showEvent() would otherwise call _fetch_servers(), spawning a real
    # FetchServersWorker QThread that outlives teardown (RULE-WIN6).
    monkeypatch.setattr(SpeedTestPage, "_fetch_servers", lambda self: None)

    qs = QSettings("NetSentinel", "NetSentinel")
    qs.remove("speedtest/scheduled_enabled")
    qs.remove("speedtest/scheduled_interval_hours")

    store = MagicMock()
    p = SpeedTestPage(store=store)
    app = QApplication.instance()
    if app:
        app.processEvents()
    yield p
    try:
        p.deleteLater()
    except RuntimeError:
        pass  # non-fatal — widget may have already been destroyed
    if app:
        for _ in range(3):
            app.processEvents()
    qs.remove("speedtest/scheduled_enabled")
    qs.remove("speedtest/scheduled_interval_hours")


def test_auto_speedtest_defaults_off(page):
    assert page._chk_auto_speedtest.isChecked() is False


def test_enabling_toggle_emits_signal_and_persists(page):
    from PyQt6.QtCore import QSettings

    emitted = []
    page.auto_speedtest_changed.connect(lambda enabled, hours: emitted.append((enabled, hours)))

    page._auto_interval_combo.setCurrentIndex(0)  # 1 hour
    page._chk_auto_speedtest.setChecked(True)

    assert emitted[-1] == (True, 1)
    qs = QSettings("NetSentinel", "NetSentinel")
    assert qs.value("speedtest/scheduled_enabled", False, type=bool) is True
    assert int(qs.value("speedtest/scheduled_interval_hours", 6)) == 1


def test_disabling_toggle_persists_across_reload(monkeypatch):
    from PyQt6.QtCore import QSettings
    from ui.pages.speed_test_page import SpeedTestPage

    monkeypatch.setattr(SpeedTestPage, "_fetch_servers", lambda self: None)
    store = MagicMock()

    page_a = SpeedTestPage(store=store)
    page_a._chk_auto_speedtest.setChecked(True)
    page_a._auto_interval_combo.setCurrentIndex(3)  # 12 hours
    page_a._chk_auto_speedtest.setChecked(False)

    page_b = SpeedTestPage(store=store)
    assert page_b._chk_auto_speedtest.isChecked() is False

    qs = QSettings("NetSentinel", "NetSentinel")
    qs.remove("speedtest/scheduled_enabled")
    qs.remove("speedtest/scheduled_interval_hours")
    page_a.deleteLater()
    page_b.deleteLater()
