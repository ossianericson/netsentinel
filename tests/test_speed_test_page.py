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


# ── Location override (wrong-country server list fix) ──────────────────────────
#
# All tests below construct their own page (not the shared `page` fixture) so
# each can control QSettings state precisely and clean it up afterward.

def test_preferred_location_restored_from_settings(monkeypatch):
    from PyQt6.QtCore import QSettings
    from ui.pages.speed_test_page import SpeedTestPage

    monkeypatch.setattr(SpeedTestPage, "_fetch_servers", lambda self: None)
    qs = QSettings("NetSentinel", "NetSentinel")
    qs.setValue("speed_test/preferred_location", "Stockholm, Sweden")

    store = MagicMock()
    p = SpeedTestPage(store=store)

    assert p._location_box.text() == "Stockholm, Sweden"
    assert p._preferred_location == "Stockholm, Sweden"

    qs.remove("speed_test/preferred_location")
    p.deleteLater()


def test_location_search_saves_preference_and_refetches(monkeypatch):
    from PyQt6.QtCore import QSettings
    from ui.pages.speed_test_page import SpeedTestPage

    monkeypatch.setattr(SpeedTestPage, "_fetch_servers", lambda self: None)
    qs = QSettings("NetSentinel", "NetSentinel")
    qs.remove("speed_test/preferred_location")
    qs.remove("speed_test/preferred_server_id")

    store = MagicMock()
    p = SpeedTestPage(store=store)

    fetch_calls = []
    monkeypatch.setattr(p, "_fetch_servers", lambda: fetch_calls.append(1))

    p._location_box.setText("Sweden")
    p._on_location_search()

    assert fetch_calls == [1]
    assert qs.value("speed_test/preferred_location", "", type=str) == "Sweden"
    assert p._preferred_location == "Sweden"

    qs.remove("speed_test/preferred_location")
    qs.remove("speed_test/preferred_server_id")
    p.deleteLater()


def test_location_search_clears_stale_server_pin(monkeypatch):
    """Searching a new location must drop any previously pinned server id — a
    Finland pin from before makes no sense once the candidate list is Sweden."""
    from PyQt6.QtCore import QSettings
    from ui.pages.speed_test_page import SpeedTestPage

    monkeypatch.setattr(SpeedTestPage, "_fetch_servers", lambda self: None)
    qs = QSettings("NetSentinel", "NetSentinel")
    qs.setValue("speed_test/preferred_server_id", "helsinki-99")

    store = MagicMock()
    p = SpeedTestPage(store=store)
    p._location_box.setText("Sweden")
    p._on_location_search()

    assert p._selected_server_id is None
    assert qs.value("speed_test/preferred_server_id", "", type=str) == ""

    qs.remove("speed_test/preferred_location")
    qs.remove("speed_test/preferred_server_id")
    p.deleteLater()


def test_clearing_location_box_reverts_to_auto_detect(monkeypatch):
    from PyQt6.QtCore import QSettings
    from ui.pages.speed_test_page import SpeedTestPage

    monkeypatch.setattr(SpeedTestPage, "_fetch_servers", lambda self: None)
    qs = QSettings("NetSentinel", "NetSentinel")
    qs.setValue("speed_test/preferred_location", "Sweden")

    store = MagicMock()
    p = SpeedTestPage(store=store)
    monkeypatch.setattr(p, "_fetch_servers", lambda: None)

    p._location_box.setText("")
    p._on_location_search()

    assert p._preferred_location == ""
    assert qs.value("speed_test/preferred_location", "", type=str) == ""

    qs.remove("speed_test/preferred_location")
    p.deleteLater()


def test_reset_location_clears_both_preferences(monkeypatch):
    from PyQt6.QtCore import QSettings
    from ui.pages.speed_test_page import SpeedTestPage

    monkeypatch.setattr(SpeedTestPage, "_fetch_servers", lambda self: None)
    qs = QSettings("NetSentinel", "NetSentinel")
    qs.setValue("speed_test/preferred_location", "Sweden")
    qs.setValue("speed_test/preferred_server_id", "42")

    store = MagicMock()
    p = SpeedTestPage(store=store)
    fetch_calls = []
    monkeypatch.setattr(p, "_fetch_servers", lambda: fetch_calls.append(1))

    p._on_reset_location()

    assert fetch_calls == [1]
    assert p._preferred_location == ""
    assert p._selected_server_id is None
    assert qs.value("speed_test/preferred_location", "", type=str) == ""
    assert qs.value("speed_test/preferred_server_id", "", type=str) == ""
    assert p._location_box.text() == ""

    p.deleteLater()


def test_selecting_server_persists_preferred_id(monkeypatch):
    from PyQt6.QtCore import QSettings
    from ui.pages.speed_test_page import SpeedTestPage

    monkeypatch.setattr(SpeedTestPage, "_fetch_servers", lambda self: None)
    qs = QSettings("NetSentinel", "NetSentinel")
    qs.remove("speed_test/preferred_server_id")

    store = MagicMock()
    p = SpeedTestPage(store=store)

    p._populate_server_list([
        {"id": "7", "name": "Telia", "city": "Stockholm", "country": "Sweden",
         "host": "h:8080", "latency_ms": 5.0},
    ])
    p._server_list.setCurrentRow(0)

    assert p._selected_server_id == "7"
    assert qs.value("speed_test/preferred_server_id", "", type=str) == "7"

    qs.remove("speed_test/preferred_server_id")
    p.deleteLater()


def test_servers_ready_restores_saved_preferred_server(monkeypatch):
    """If the saved preferred server id is present in a freshly fetched list, it
    must be pre-selected instead of defaulting to row 0 — and doing so must not
    re-persist a 'new' preference (would defeat the whole point of remembering it)."""
    from PyQt6.QtCore import QSettings, Qt
    from ui.pages.speed_test_page import SpeedTestPage

    monkeypatch.setattr(SpeedTestPage, "_fetch_servers", lambda self: None)
    qs = QSettings("NetSentinel", "NetSentinel")
    qs.setValue("speed_test/preferred_server_id", "7")

    store = MagicMock()
    p = SpeedTestPage(store=store)

    p._on_servers_ready([
        {"id": "5", "name": "A", "city": "X", "country": "Y", "host": "h:8080", "latency_ms": 20.0},
        {"id": "7", "name": "Telia", "city": "Stockholm", "country": "Sweden",
         "host": "h:8080", "latency_ms": 5.0},
    ])

    assert p._server_list.currentItem().data(Qt.ItemDataRole.UserRole) == "7"
    assert p._selected_server_id == "7"

    qs.remove("speed_test/preferred_server_id")
    p.deleteLater()
