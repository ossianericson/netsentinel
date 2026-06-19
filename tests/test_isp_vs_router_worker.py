"""Tests for workers/isp_vs_router_worker.py"""
from __future__ import annotations

from unittest.mock import patch

import pytest

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)

from workers.isp_vs_router_worker import IspVsRouterWorker
from modules.isp_vs_router_test import HopResult, IspVsRouterResult


@pytest.fixture
def worker():
    w = IspVsRouterWorker(gateway_ip="192.168.1.1")
    yield w
    try:
        if w.isRunning():
            w.stop()
        w.deleteLater()
    except RuntimeError:
        pass  # widget already deleted by Qt
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


def _make_result() -> IspVsRouterResult:
    hops = [
        HopResult("router", "Your router", "192.168.1.1", True, 2.0),
        HopResult("google_dns", "Google DNS", "8.8.8.8", True, 15.0),
        HopResult("cloudflare", "Cloudflare", "1.1.1.1", True, 16.0),
        HopResult("opendns", "OpenDNS", "208.67.222.222", True, 18.0),
    ]
    return IspVsRouterResult(hops=hops, verdict="All clear", plain_answer="OK", category="all_ok")


def test_worker_instantiation():
    w = IspVsRouterWorker(gateway_ip="10.0.0.1")
    assert not w.isRunning()
    try:
        w.deleteLater()
    except RuntimeError:
        pass  # widget already deleted by Qt
    app = QApplication.instance()
    if app:
        for _ in range(2):
            app.processEvents()


def test_worker_start_stop_lifecycle():
    """RULE-T2: worker starts, stops, and is not running after stop()."""
    _fake = _make_result()
    with patch("workers.isp_vs_router_worker.run_isp_vs_router_test", return_value=_fake):
        w = IspVsRouterWorker(gateway_ip="192.168.0.1")
        w.start()
        w.wait(3000)
        assert not w.isRunning()
        try:
            w.deleteLater()
        except RuntimeError:
            pass  # widget already deleted by Qt
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


def test_worker_emits_result_ready():
    """Worker emits result_ready with an IspVsRouterResult."""
    _fake = _make_result()
    received = []
    app = QApplication.instance()

    with patch("workers.isp_vs_router_worker.run_isp_vs_router_test", return_value=_fake):
        w = IspVsRouterWorker(gateway_ip="192.168.0.1")
        w.result_ready.connect(received.append)
        w.start()
        w.wait(3000)
        # Pump the event loop so queued cross-thread signals are delivered
        if app:
            for _ in range(5):
                app.processEvents()

    assert len(received) == 1
    assert isinstance(received[0], IspVsRouterResult)

    try:
        w.deleteLater()
    except RuntimeError:
        pass  # widget already deleted by Qt
    if app:
        for _ in range(3):
            app.processEvents()


def test_worker_emits_error_on_exception():
    """Worker emits error(str) when the test function raises."""
    errors = []
    app = QApplication.instance()

    def _raise(*args, **kwargs):
        raise RuntimeError("network unreachable")

    with patch("workers.isp_vs_router_worker.run_isp_vs_router_test", side_effect=_raise):
        w = IspVsRouterWorker(gateway_ip="192.168.0.1")
        w.error.connect(errors.append)
        w.start()
        w.wait(3000)
        if app:
            for _ in range(5):
                app.processEvents()

    assert len(errors) == 1
    assert "network unreachable" in errors[0]

    try:
        w.deleteLater()
    except RuntimeError:
        pass  # widget already deleted by Qt
    if app:
        for _ in range(3):
            app.processEvents()
