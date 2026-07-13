"""
Tests for ServicePage's add-time reachability guard.

A target that was never reachable (typo, or an automated fuzz click landing
in the add-service field with the port spinbox's 443 default) used to be
persisted unconditionally and then fire a CRITICAL Service Down alert
forever. _probe_and_add() must hard-block persisting a target whose
reachability probe fails, and must persist it when the probe succeeds.
"""
from __future__ import annotations

import time

import pytest

try:
    from PyQt6.QtWidgets import QApplication
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

pytestmark_qt = pytest.mark.skipif(not _HAS_QT, reason="PyQt6 not available")


def _pump_until(app, condition, timeout_s=3.0):
    deadline = time.time() + timeout_s
    while not condition() and time.time() < deadline:
        app.processEvents()
        time.sleep(0.005)
    return condition()


@pytest.fixture
def _service_page(monkeypatch):
    if not _HAS_QT:
        pytest.skip("PyQt6 not available")
    app = QApplication.instance()
    # Never touch a real socket in tests — the probe result is fully
    # controlled per-test via monkeypatching this module attribute.
    monkeypatch.setattr("ui.pages.service_page.check_tcp", lambda host, port, timeout=3.0: (True, 1.0, ""))
    # Never touch the real QSettings-backed target list — a leaked write here
    # would pollute the user's actual Service Heartbeat monitors (RULE-WIN6).
    monkeypatch.setattr("ui.pages.service_page.ServicePage._load_targets", lambda self: [])
    monkeypatch.setattr("ui.pages.service_page.ServicePage._save_targets", lambda self: None)
    from ui.pages.service_page import ServicePage
    page = ServicePage(store=None)
    yield page
    try:
        page.deleteLater()
    except RuntimeError:
        pass  # already deleted
    if app:
        for _ in range(3):
            app.processEvents()


@pytestmark_qt
def test_unreachable_target_is_not_persisted(_service_page, monkeypatch):
    """A failed reachability probe must hard-block the add — nothing persists."""
    page = _service_page
    monkeypatch.setattr("ui.pages.service_page.check_tcp", lambda host, port, timeout=3.0: (False, None, "refused"))
    app = QApplication.instance()

    results = []
    started = page._probe_and_add("10.0.0.9", 443, "", results.append)
    assert started is True

    assert _pump_until(app, lambda: len(results) == 1), "probe result never arrived"
    assert results == [False]
    assert page._configured == []


@pytestmark_qt
def test_reachable_target_is_persisted(_service_page, monkeypatch):
    """A successful reachability probe adds the target to _configured and QSettings."""
    page = _service_page
    monkeypatch.setattr("ui.pages.service_page.check_tcp", lambda host, port, timeout=3.0: (True, 5.0, ""))
    app = QApplication.instance()

    results = []
    started = page._probe_and_add("192.168.1.1", 443, "Router", results.append)
    assert started is True

    assert _pump_until(app, lambda: len(results) == 1), "probe result never arrived"
    assert results == [True]
    assert page._configured == [{"host": "192.168.1.1", "port": 443, "label": "Router"}]


@pytestmark_qt
def test_blank_host_does_not_start_a_probe(_service_page):
    """Existing behaviour preserved: a blank host is rejected synchronously."""
    page = _service_page
    results = []
    started = page._probe_and_add("   ", 443, "", results.append)
    assert started is False
    assert results == []
    assert page._configured == []


@pytestmark_qt
def test_duplicate_target_does_not_start_a_probe(_service_page):
    """Existing behaviour preserved: adding an already-configured host:port is a no-op."""
    page = _service_page
    page._configured = [{"host": "192.168.1.1", "port": 443, "label": "Router"}]
    results = []
    started = page._probe_and_add("192.168.1.1", 443, "Router again", results.append)
    assert started is False
    assert results == []
    assert page._configured == [{"host": "192.168.1.1", "port": 443, "label": "Router"}]
