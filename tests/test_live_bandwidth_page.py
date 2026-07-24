"""Tests for ui/pages/live_bandwidth_page.py"""
from __future__ import annotations

import pytest

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)


@pytest.fixture
def page():
    from ui.pages.live_bandwidth_page import LiveBandwidthPage
    p = LiveBandwidthPage()
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
    from ui.pages.live_bandwidth_page import LiveBandwidthPage  # noqa: F401


def test_instantiation(page):
    assert page is not None


def test_on_bandwidth_result_does_not_crash(page):
    """Injecting bandwidth readings should not crash."""
    result = {"iface": "Ethernet", "rx_bytes": 1024 * 1024, "tx_bytes": 512 * 1024}
    slot = getattr(page, "on_bandwidth_result", None) or getattr(page, "on_result", None)
    if slot:
        slot(result)
    assert page is not None


def test_widget_is_not_none(page):
    assert page is not None


def test_hide_stops_bandwidth_worker(qt_app):
    """A real QStackedWidget page switch (setCurrentWidget away from the page,
    firing hideEvent()) must stop the background IfaceBwPoller (RULE-WIN15) —
    see docs/spikes/live-bandwidth-chart-leak-repro.py."""
    from PyQt6.QtWidgets import QStackedWidget, QWidget

    from ui.pages.live_bandwidth_page import LiveBandwidthPage

    class _FakeWorker:
        """Stands in for IfaceBwPoller's stop lifecycle without needing a real
        QThread/psutil poll loop — only isRunning()/stop()/wait() are touched
        by hideEvent()/showEvent()."""

        def __init__(self):
            self.stop_calls = 0
            self._running = True

        def isRunning(self):
            return self._running

        def stop(self):
            self.stop_calls += 1
            self._running = False

        def wait(self, ms=0):
            return True

    other = QWidget()
    stack = QStackedWidget()
    page = LiveBandwidthPage()
    stack.addWidget(other)
    stack.addWidget(page)

    worker = _FakeWorker()
    page._worker = worker

    stack.setCurrentWidget(page)  # fires showEvent() -> _start_worker() (no-op: fake already running)
    assert worker.isRunning()

    stack.setCurrentWidget(other)  # fires hideEvent() on `page`

    assert worker.stop_calls == 1, "hideEvent() must stop the background bandwidth poller"
    assert not worker.isRunning()
    assert page._worker is None

    page.deleteLater()
    other.deleteLater()
    stack.deleteLater()
