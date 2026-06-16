"""
Tests for ui/pages/app_traffic_page.py — top_host_changed signal (S5-4)

Covers:
  • AppTrafficPage constructs without error
  • _emit_top_host() does nothing when there are no snapshots
  • _emit_top_host() emits the highest-byte host with the correct share_pct
"""
from __future__ import annotations

import pytest

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)

from modules.app_traffic_classifier import AppHostSnapshot
from ui.pages.app_traffic_page import AppTrafficPage

_created_pages: list = []


@pytest.fixture(autouse=True)
def _cleanup_pages():
    yield
    app = QApplication.instance()
    for page in _created_pages:
        try:
            page.deleteLater()
        except RuntimeError:
            pass  # already destroyed — safe to skip
    if app:
        try:
            from PyQt6.QtCore import QCoreApplication, QEvent
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
        except Exception:
            pass  # non-fatal
        for _ in range(3):
            app.processEvents()
    _created_pages.clear()


def _make_page() -> AppTrafficPage:
    page = AppTrafficPage()
    _created_pages.append(page)
    return page


def test_constructs_without_error():
    page = _make_page()
    assert page is not None


def test_emit_top_host_noop_when_no_snapshots():
    page = _make_page()
    received = []
    page.top_host_changed.connect(received.append)
    page._emit_top_host()
    assert received == []


def test_emit_top_host_reports_highest_consumer():
    page = _make_page()
    page._snapshots = {
        "Quiet Device": AppHostSnapshot(mac="aa:bb", label="Quiet Device", total_bytes=10_000),
        "John's MacBook": AppHostSnapshot(mac="cc:dd", label="John's MacBook", total_bytes=90_000),
    }
    received = []
    page.top_host_changed.connect(received.append)
    page._emit_top_host()
    assert len(received) == 1
    payload = received[0]
    assert payload["label"] == "John's MacBook"
    assert payload["bytes_total"] == 90_000
    assert payload["share_pct"] == pytest.approx(90.0)
