"""
Regression tests for HistoryPage and _HistoryRefreshWorker.

P1 regression: _refresh() must not block the main thread for 7d queries.
The fix routes all MetricStore queries through _HistoryRefreshWorker (QThread).
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytest.importorskip("PyQt6.QtWidgets")


# ── _HistoryRefreshWorker ─────────────────────────────────────────────────────

def test_history_refresh_worker_importable():
    from ui.pages.history_page import _HistoryRefreshWorker
    assert _HistoryRefreshWorker is not None


def test_history_refresh_worker_returns_dict_with_required_keys():
    """Worker _fetch() must return all keys the UI expects."""
    from ui.pages.history_page import _HistoryRefreshWorker

    store = MagicMock()
    store.query_all_rtt_hosts.return_value = []

    w = _HistoryRefreshWorker(store, window_h=1, selected="")
    data = w._fetch()

    required_keys = {"window_h", "selected", "hosts", "series_hosts",
                     "rtt_series", "state_series", "uptime"}
    assert required_keys.issubset(data.keys()), (
        f"Missing keys: {required_keys - data.keys()}"
    )

    try:
        w.deleteLater()
    except RuntimeError:
        pass  # non-fatal — worker may already be cleaned up


def test_history_refresh_worker_single_host_selection():
    """Worker must only fetch series data for the selected host, not all hosts."""
    from ui.pages.history_page import _HistoryRefreshWorker

    store = MagicMock()
    store.query_all_rtt_hosts.return_value = ["192.168.1.1", "192.168.1.2"]
    store.query_rtt_history.return_value = []
    store.query_device_state_history.return_value = []
    store.query_uptime_pct.return_value = None

    w = _HistoryRefreshWorker(store, window_h=24, selected="192.168.1.1")
    data = w._fetch()

    assert data["series_hosts"] == ["192.168.1.1"]
    # Should only have called rtt_history for the selected host
    store.query_rtt_history.assert_called_once_with("192.168.1.1", hours=24)

    try:
        w.deleteLater()
    except RuntimeError:
        pass  # non-fatal


def test_history_refresh_worker_caps_series_hosts():
    """Worker must cap chart series at _CHART_HOST_LIMIT when 'all hosts' selected."""
    from ui.pages.history_page import _HistoryRefreshWorker

    store = MagicMock()
    many_hosts = [f"10.0.0.{i}" for i in range(20)]
    store.query_all_rtt_hosts.return_value = many_hosts
    store.query_rtt_history.return_value = []
    store.query_device_state_history.return_value = []
    store.query_uptime_pct.return_value = None

    w = _HistoryRefreshWorker(store, window_h=1, selected="(all hosts)")
    data = w._fetch()

    limit = _HistoryRefreshWorker._CHART_HOST_LIMIT
    assert len(data["series_hosts"]) <= limit, (
        f"series_hosts ({len(data['series_hosts'])}) exceeded limit ({limit})"
    )
    # Total host count still reflects all hosts
    assert len(data["hosts"]) == 20

    try:
        w.deleteLater()
    except RuntimeError:
        pass  # non-fatal


def test_history_refresh_worker_run_lifecycle(qt_app):
    """Worker must start, emit result_ready, and stop cleanly (RULE-T2)."""
    if qt_app is None:
        pytest.skip("No QApplication")

    from PyQt6.QtCore import QEventLoop, QTimer
    from ui.pages.history_page import _HistoryRefreshWorker

    store = MagicMock()
    store.query_all_rtt_hosts.return_value = []

    received: list = []
    loop = QEventLoop()

    def _on_result(data):
        received.append(data)
        loop.quit()

    w = _HistoryRefreshWorker(store, window_h=1, selected="")
    w.result_ready.connect(_on_result)
    w.start()

    # Run event loop to allow cross-thread signal delivery; quit on timeout
    _guard = QTimer()
    _guard.setSingleShot(True)
    _guard.timeout.connect(loop.quit)
    _guard.start(4000)
    loop.exec()

    assert not w.isRunning(), "Worker still running after result_ready"
    assert len(received) == 1, "result_ready must be emitted exactly once"
    assert isinstance(received[0], dict)

    try:
        _guard.stop()
        w.deleteLater()
    except RuntimeError:
        pass  # non-fatal
    if qt_app:
        for _ in range(3):
            qt_app.processEvents()


def test_history_refresh_worker_error_still_emits_result(qt_app):
    """Worker must emit result_ready even when the store raises (P1 regression)."""
    if qt_app is None:
        pytest.skip("No QApplication")

    from PyQt6.QtCore import QEventLoop, QTimer
    from ui.pages.history_page import _HistoryRefreshWorker

    store = MagicMock()
    store.query_all_rtt_hosts.side_effect = RuntimeError("DB locked")

    received: list = []
    loop = QEventLoop()

    def _on_result(data):
        received.append(data)
        loop.quit()

    w = _HistoryRefreshWorker(store, window_h=168, selected="")
    w.result_ready.connect(_on_result)
    w.start()

    _guard = QTimer()
    _guard.setSingleShot(True)
    _guard.timeout.connect(loop.quit)
    _guard.start(4000)
    loop.exec()

    assert len(received) == 1, "result_ready must fire even on DB error"
    assert received[0]["hosts"] == [], "error fallback must return empty hosts"

    try:
        _guard.stop()
        w.deleteLater()
    except RuntimeError:
        pass  # non-fatal
    if qt_app:
        for _ in range(3):
            qt_app.processEvents()


# ── HistoryPage smoke ─────────────────────────────────────────────────────────

def test_history_page_no_blocking_refresh_attribute(qt_app):
    """HistoryPage._refresh must dispatch to a worker (not block main thread)."""
    if qt_app is None:
        pytest.skip("No QApplication")

    import inspect
    from ui.pages.history_page import HistoryPage

    src = inspect.getsource(HistoryPage._refresh)
    # The synchronous store query calls must NOT appear directly in _refresh
    assert "query_rtt_history" not in src, (
        "_refresh() must not call query_rtt_history directly — use the worker"
    )
    assert "query_device_state_history" not in src, (
        "_refresh() must not call query_device_state_history directly — use the worker"
    )
