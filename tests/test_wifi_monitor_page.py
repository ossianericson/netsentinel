"""Regression test for WiFiMonitorPage._start()."""
from __future__ import annotations

import pytest

from ui.pages.wifi_monitor_page import WiFiMonitorPage


class _FakeWorker:
    """Stand-in for WiFiMonitorWorker that never touches real hardware."""

    frame_captured = None
    status = None
    error = None
    unsupported = None

    def __init__(self, iface: str = "", parent=None):
        self.iface = iface

        class _Signal:
            def connect(self, *_a, **_kw):
                pass

        self.frame_captured = _Signal()
        self.status = _Signal()
        self.error = _Signal()
        self.unsupported = _Signal()

    def start(self):
        pass

    def isRunning(self):
        return False

    def stop(self):
        pass

    def wait(self, *_a, **_kw):
        pass

    @staticmethod
    def list_interfaces():
        return ["Wi-Fi"]


@pytest.fixture
def wifi_page(qt_app, monkeypatch):
    monkeypatch.setattr(
        "workers.wifi_monitor_worker.WiFiMonitorWorker", _FakeWorker
    )
    page = WiFiMonitorPage()
    page._iface_combo.clear()
    page._iface_combo.addItem("Wi-Fi")
    yield page
    try:
        page.deleteLater()
    except RuntimeError:
        pass  # underlying C++ widget already deleted
    qt_app.processEvents()


def test_start_monitoring_does_not_raise(wifi_page):
    """Clicking Start Monitoring must not crash (regression: RULE-T3).

    Previously _start() passed the *resolved* colour value (_s.GREEN, e.g.
    "#2E7D32") where _set_status() expects the *attribute name* ("GREEN"),
    causing getattr(styles, "#2E7D32") to raise AttributeError every time —
    confirmed twice in the 2026-07-13 systematic sweep (08:57 and 09:58).
    """
    wifi_page._start()
    assert wifi_page._status_lbl.text().startswith("Starting monitor mode")


def test_stop_monitoring_does_not_raise(wifi_page):
    """Clicking Stop Monitoring must not crash (regression: RULE-T3).

    Same bug class as _start(): _stop() passed the *resolved* colour value
    (_s.TEXT_SECONDARY) instead of the attribute name ("TEXT_SECONDARY"),
    which would raise AttributeError inside _set_status()'s getattr(_s, cn).
    """
    wifi_page._start()
    wifi_page._stop()
    assert wifi_page._status_lbl.text() == "Capture stopped."
