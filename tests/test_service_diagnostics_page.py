"""
Tests for ui/pages/service_diagnostics_page.py — bandwidth overlay note (S6-6).

Covers:
  • ServiceDiagnosticsPage constructs without error
  • _update_bandwidth_overlay() hides the label when there is no store
  • _update_bandwidth_overlay() hides the label when failure_layer != "none"
  • _update_bandwidth_overlay() shows the note when diagnostics pass and
    other devices are actively generating traffic
"""
from __future__ import annotations

import pytest

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)

from modules.metric_store import MetricStore
from modules.service_diagnostics import ServiceDiagnosticResult
from ui.pages.service_diagnostics_page import ServiceDiagnosticsPage

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


@pytest.fixture
def store(tmp_path):
    s = MetricStore(db_path=tmp_path / "test.db")
    yield s
    s.close()


def _make_page(store=None) -> ServiceDiagnosticsPage:
    page = ServiceDiagnosticsPage(store=store)
    _created_pages.append(page)
    return page


def test_constructs_without_error():
    page = _make_page()
    assert page is not None


def test_overlay_hidden_without_store():
    page = _make_page(store=None)
    result = ServiceDiagnosticResult(service_id="netflix", service_name="Netflix", failure_layer="none")
    page._update_bandwidth_overlay(result)
    assert page._bandwidth_overlay_lbl.isVisible() is False


def test_overlay_hidden_when_failure_layer_identified(store):
    store.record_app_traffic_sample("aa:bb", "TV", "Streaming", "HTTPS", 1000, 10.0)
    page = _make_page(store=store)
    result = ServiceDiagnosticResult(service_id="netflix", service_name="Netflix", failure_layer="isp")
    page._update_bandwidth_overlay(result)
    assert page._bandwidth_overlay_lbl.isVisible() is False


def test_overlay_shown_when_healthy_and_devices_active(store):
    store.record_app_traffic_sample("aa:bb", "TV", "Streaming", "HTTPS", 1000, 10.0)
    store.record_app_traffic_sample("cc:dd", "Laptop", "Web", "HTTPS", 1000, 10.0)
    page = _make_page(store=store)
    page.show()
    page._stack.setCurrentIndex(1)   # results page — empty state (index 0) hides all children
    result = ServiceDiagnosticResult(service_id="netflix", service_name="Netflix", failure_layer="none")
    page._update_bandwidth_overlay(result)
    assert page._bandwidth_overlay_lbl.isVisible() is True
    assert "Netflix" in page._bandwidth_overlay_lbl.text()


def test_copy_forum_markdown_populates_clipboard():
    page = _make_page()
    page._last_result = ServiceDiagnosticResult(
        service_id="netflix", service_name="Netflix", failure_layer="none",
        summary="Netflix is reachable and healthy.",
    )
    page._copy_forum_markdown()
    clip = QApplication.clipboard().text()
    assert "Netflix" in clip
    assert "NetSentinel" in clip


def test_copy_forum_markdown_noop_without_result():
    page = _make_page()
    page._last_result = None
    page._copy_forum_markdown()  # must not raise
