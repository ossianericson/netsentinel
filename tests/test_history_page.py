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

    # Allow run() to fully return — signal is emitted before run() exits, so
    # isRunning() can still be True on Linux at the moment loop.quit() fires.
    w.wait(2000)

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


# ── Long-term rollup mode (Stability Sprint 2 / G4) ─────────────────────────
# Beyond the raw rtt_sample retention window, the worker must switch to
# daily_rollup so long-term trend views still have data.

def test_history_refresh_worker_raw_mode_below_retention_threshold():
    from ui.pages.history_page import _HistoryRefreshWorker

    store = MagicMock()
    store.query_all_rtt_hosts.return_value = ["192.168.1.1"]
    store.query_rtt_history.return_value = []
    store.query_device_state_history.return_value = []
    store.query_uptime_pct.return_value = None

    w = _HistoryRefreshWorker(store, window_h=168, selected="")  # 7d
    data = w._fetch()

    assert data["rollup_mode"] is False
    assert data["rollup_series"] == {}
    store.query_daily_rollup.assert_not_called()


def test_history_refresh_worker_switches_to_rollup_beyond_retention():
    from ui.pages.history_page import _HistoryRefreshWorker

    store = MagicMock()
    store.query_rollup_hosts.return_value = ["192.168.1.1"]
    store.query_daily_rollup.return_value = ["fake-rollup-point"]

    w = _HistoryRefreshWorker(store, window_h=2160, selected="")  # 90d
    data = w._fetch()

    assert data["rollup_mode"] is True
    assert data["rollup_series"] == {"192.168.1.1": ["fake-rollup-point"]}
    store.query_daily_rollup.assert_called_once_with("rtt_ms", host="192.168.1.1")
    # Raw per-sample queries must not run in rollup mode — they'd return
    # nothing useful past the raw retention window anyway.
    store.query_rtt_history.assert_not_called()


def test_history_refresh_worker_rollup_mode_finds_hosts_with_no_recent_raw_data():
    """A host whose raw rtt_sample rows have all aged past retention (so
    query_all_rtt_hosts finds nothing) must still surface in the 90d rollup
    view if it has daily_rollup history — this was a real bug caught by
    manual end-to-end verification: query_all_rtt_hosts()-only discovery
    silently dropped exactly this host."""
    from ui.pages.history_page import _HistoryRefreshWorker

    store = MagicMock()
    store.query_all_rtt_hosts.return_value = []  # no recent raw activity
    store.query_rollup_hosts.return_value = ["192.168.1.1"]
    store.query_daily_rollup.return_value = ["fake-rollup-point"]

    w = _HistoryRefreshWorker(store, window_h=2160, selected="")
    data = w._fetch()

    assert data["hosts"] == ["192.168.1.1"]
    assert data["rollup_series"] == {"192.168.1.1": ["fake-rollup-point"]}


def test_history_refresh_worker_rollup_mode_uses_rollup_host_discovery():
    """Host discovery in rollup mode must come from query_rollup_hosts(), not
    query_all_rtt_hosts() — the latter only sees rtt_sample, which is pruned
    at 30 days and would miss hosts with rollup-only history (see
    test_history_refresh_worker_rollup_mode_finds_hosts_with_no_recent_raw_data)."""
    from ui.pages.history_page import _HistoryRefreshWorker

    store = MagicMock()
    store.query_rollup_hosts.return_value = []
    store.query_daily_rollup.return_value = []

    w = _HistoryRefreshWorker(store, window_h=2160, selected="")
    w._fetch()

    store.query_rollup_hosts.assert_called_once_with("rtt_ms")
    store.query_all_rtt_hosts.assert_not_called()


def test_history_page_renders_rollup_data_without_error(qt_app):
    """RULE-T7 behavioral test: feeding rollup-mode data through the real
    _on_history_data -> _draw_rtt -> _draw_rtt_rollup / _update_kpis path
    must not raise, and the avg RTT KPI tile must reflect the weighted
    average across the fed-in daily_rollup points."""
    if qt_app is None:
        pytest.skip("No QApplication")

    from modules.metric_store_schema import RollupPoint
    from ui.pages.history_page import HistoryPage

    page = HistoryPage(store=None)
    data = {
        "window_h": 2160,
        "selected": "",
        "hosts": ["192.168.1.1"],
        "series_hosts": ["192.168.1.1"],
        "rtt_series": {},
        "state_series": {},
        "uptime": {},
        "rollup_mode": True,
        "rollup_series": {
            "192.168.1.1": [
                RollupPoint(day="2026-01-01", metric="rtt_ms", host="192.168.1.1",
                            min=10.0, avg=20.0, max=30.0, n=5),
                RollupPoint(day="2026-01-02", metric="rtt_ms", host="192.168.1.1",
                            min=15.0, avg=25.0, max=35.0, n=5),
            ]
        },
    }
    page._on_history_data(data)
    assert page._kpi_avg_rtt._val.text() == "22 ms"

    try:
        page.deleteLater()
    except RuntimeError:
        pass  # non-fatal
    for _ in range(3):
        qt_app.processEvents()


# ── Concurrent-refresh coalescing (2026-07-11 wild chaos hang) ─────────────────
# _HistoryRefreshWorker.run() never calls exec(), so hideEvent()'s
# worker.quit()/wait(300) is a no-op against it — the worker keeps running as
# an orphaned QThread. Rapid re-navigation to Availability History (routine
# under chaos-level clicking) could spin up several overlapping workers, each
# issuing up to 6 hosts x 3 MetricStore queries concurrently. That pile-up is
# the prime suspect for 4 of the 7 health-monitor hangs in the wild/moderate
# soak phases of run 20260711_002759, including the one that exhausted the
# restart budget and ended the run. Fix: _refresh() must coalesce instead of
# stacking a second concurrent worker.

def test_history_page_refresh_coalesces_concurrent_requests(qt_app, monkeypatch):
    """A second _refresh() call while a fetch is in flight must not start a
    second concurrent _HistoryRefreshWorker — it must be coalesced and run
    once the in-flight worker finishes."""
    if qt_app is None:
        pytest.skip("No QApplication")

    from ui.pages import history_page as hp_mod
    from PyQt6.QtCore import QThread, pyqtSignal

    created: list = []

    class _FakeWorker(QThread):
        result_ready = pyqtSignal(dict)

        def __init__(self, store, window_h, selected, parent=None):
            super().__init__(parent)
            self._running = False
            created.append(self)

        def start(self, *a, **kw):
            self._running = True

        def isRunning(self):
            return self._running

        def finish(self):
            self._running = False
            self.result_ready.emit({"hosts": []})
            self.finished.emit()

    monkeypatch.setattr(hp_mod, "_HistoryRefreshWorker", _FakeWorker)

    page = hp_mod.HistoryPage(store=None)  # store=None skips __init__'s own _refresh()
    monkeypatch.setattr(page, "isVisible", lambda: True)
    page._store = MagicMock()

    page._refresh()
    assert len(created) == 1, "first _refresh() must start a worker"

    page._refresh()  # a second request arrives while the first is still in flight
    assert len(created) == 1, (
        "a second concurrent worker must not be started while one is running "
        "— this is what stacked overlapping DB fetches under rapid "
        "re-navigation and hung the app"
    )

    created[0].finish()
    qt_app.processEvents()
    assert len(created) == 2, "the coalesced request must run once the first worker finishes"

    try:
        page.deleteLater()
    except RuntimeError:
        pass  # non-fatal — widget may already be cleaned up
    for _ in range(3):
        qt_app.processEvents()


# ── Worker leak on repeated navigation (RULE-WIN8) ──────────────────────────────
# _start_refresh_worker() reassigns self._refresh_worker to a fresh
# _HistoryRefreshWorker(parent=self) on every navigation into the page without
# ever deleteLater()-ing the previous one -- the RULE-WIN8 general-case shape
# (a parented QObject whose only Python handle is reassigned is not freed)
# applied to a worker QThread instead of a QDialog. Quantified live via
# docs/spikes/history-worker-leak-repro.py: confirmed real (live worker count
# grows exactly 1:1 with navigations, unbounded) but too small in magnitude
# (~1.5 KB/nav) to be the driver of the 2026-07-23 wild-soak RSS growth --
# still worth fixing on its own merits.

def test_history_page_does_not_leak_refresh_worker_across_repeated_refreshes(qt_app, monkeypatch):
    """Every stale _refresh_worker must be deleteLater()'d before being
    replaced by the next navigation's worker -- only the current (in-flight or
    just-finished) worker may remain undestroyed."""
    if qt_app is None:
        pytest.skip("No QApplication")

    from ui.pages import history_page as hp_mod
    from PyQt6.QtCore import QThread, pyqtSignal

    destroyed_flags: list = []

    class _FakeWorker(QThread):
        result_ready = pyqtSignal(dict)

        def __init__(self, store, window_h, selected, parent=None):
            super().__init__(parent)
            self._running = False
            flag = {"destroyed": False}
            destroyed_flags.append(flag)
            self.destroyed.connect(lambda _obj=None, f=flag: f.__setitem__("destroyed", True))

        def start(self, *a, **kw):
            self._running = True

        def isRunning(self):
            return self._running

        def finish(self):
            self._running = False
            self.result_ready.emit({"hosts": []})
            self.finished.emit()

    monkeypatch.setattr(hp_mod, "_HistoryRefreshWorker", _FakeWorker)

    page = hp_mod.HistoryPage(store=None)  # store=None skips __init__'s own _refresh()
    monkeypatch.setattr(page, "isVisible", lambda: True)
    page._store = MagicMock()

    from PyQt6.QtCore import QEvent

    for _ in range(5):
        page._refresh()
        page._refresh_worker.finish()
        # DeferredDelete events (from deleteLater()) are NOT flushed by a plain
        # processEvents() -- Qt special-cases them out of the generic "process
        # all posted events" pass, so they must be requested explicitly.
        qt_app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        qt_app.processEvents()

    for _ in range(3):
        qt_app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        qt_app.processEvents()

    assert len(destroyed_flags) == 5, "expected exactly one worker per refresh"
    assert all(f["destroyed"] for f in destroyed_flags[:-1]), (
        "a stale _refresh_worker was never deleteLater()'d after being replaced "
        "by the next navigation's worker -- RULE-WIN8 leak: the previous worker "
        "stays alive as a child of the page forever"
    )

    try:
        page.deleteLater()
    except RuntimeError:
        pass  # non-fatal — widget may already be cleaned up
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
