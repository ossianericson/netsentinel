"""RULE-T7 behavioral test: speed-drop banner + signal on SpeedTestPage."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from modules.metric_store_schema import SpeedTestPoint
from modules.speed_tester_backends import SpeedTestResult
from ui.pages.speed_test_page import SpeedTestPage


def _history_point(ts: float, download_mbps: float) -> SpeedTestPoint:
    return SpeedTestPoint(
        ts=int(ts),
        download_mbps=download_mbps,
        upload_mbps=50.0,
        ping_ms=10.0,
        server_name="test",
        server_city="",
        server_country="",
    )


@pytest.fixture
def page(monkeypatch):
    from PyQt6.QtWidgets import QApplication

    # showEvent() would otherwise call _fetch_servers(), spawning a real
    # FetchServersWorker QThread that outlives teardown and later corrupts
    # the heap when it emits into a deleted widget (RULE-WIN6).
    monkeypatch.setattr(SpeedTestPage, "_fetch_servers", lambda self: None)

    store = MagicMock()
    p = SpeedTestPage(store=store)
    p.show()  # _on_result_ready gates UI updates behind isVisible()
    app = QApplication.instance()
    if app:
        app.processEvents()
    yield p, store
    try:
        p.deleteLater()
    except RuntimeError:
        pass  # non-fatal — widget may have already been destroyed
    if app:
        for _ in range(3):
            app.processEvents()


def test_severe_drop_shows_banner_and_emits_signal(page):
    p, store = page
    now = 1_700_000_000.0
    # Newest-first history: current test already recorded (94 Mbps) + 4 prior fast tests
    store.query_speed_test_history.return_value = [
        _history_point(now, 94.0),
        _history_point(now - 3600, 740.0),
        _history_point(now - 7200, 735.0),
        _history_point(now - 10800, 742.0),
        _history_point(now - 14400, 745.0),
    ]

    emitted: list = []
    p.speed_drop_detected.connect(lambda payload: emitted.append(payload))

    result = SpeedTestResult(
        download_mbps=94.0, upload_mbps=40.0, ping_ms=12.0,
        server_name="Test ISP", server_city="Testville", server_country="US",
        backend="test",
    )
    p._on_result_ready(result)

    assert p._drop_banner.isVisible()
    assert "94" in p._drop_banner.text()
    assert len(emitted) == 1
    assert emitted[0]["severity"] == "High"


def test_normal_result_hides_banner(page):
    p, store = page
    now = 1_700_000_000.0
    store.query_speed_test_history.return_value = [
        _history_point(now, 730.0),
        _history_point(now - 3600, 740.0),
        _history_point(now - 7200, 735.0),
        _history_point(now - 10800, 742.0),
    ]

    emitted: list = []
    p.speed_drop_detected.connect(lambda payload: emitted.append(payload))

    result = SpeedTestResult(
        download_mbps=730.0, upload_mbps=40.0, ping_ms=12.0,
        server_name="Test ISP", server_city="Testville", server_country="US",
        backend="test",
    )
    p._on_result_ready(result)

    assert not p._drop_banner.isVisible()
    assert emitted == []
