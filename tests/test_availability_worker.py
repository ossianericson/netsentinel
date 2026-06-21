"""Tests for workers/availability_worker.py (RULE-T2)."""
import time
import pytest

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)


def _cleanup(w):
    app = QApplication.instance()
    try:
        w.deleteLater()
    except RuntimeError:
        pass  # non-fatal — already deleted
    if app:
        for _ in range(3):
            app.processEvents()


# ── Import guard ──────────────────────────────────────────────────────────────

def test_import():
    from workers.availability_worker import AvailabilityWorker  # noqa: F401


# ── Instantiation ─────────────────────────────────────────────────────────────

def test_instantiation(tmp_path):
    from modules.metric_store import MetricStore
    from workers.availability_worker import AvailabilityWorker
    store = MetricStore(str(tmp_path / "test.db"))
    w = AvailabilityWorker(store=store, interval_s=3600)
    assert not w.isRunning()
    _cleanup(w)


# ── Start / stop lifecycle ────────────────────────────────────────────────────

def test_start_stop_lifecycle(tmp_path):
    """Worker must start and stop cleanly when stop() is called."""
    from unittest.mock import MagicMock
    from modules.metric_store import MetricStore
    from workers.availability_worker import AvailabilityWorker
    store = MetricStore(str(tmp_path / "test.db"))
    errors = []
    w = AvailabilityWorker(store=store, interval_s=3600)
    w.error.connect(errors.append)
    # Prevent real network I/O on CI — run_cycle blocks for seconds on Linux runners
    mock_result = MagicMock()
    mock_result.ts = 0
    mock_result.states = {}
    mock_result.rtts = {}
    mock_result.changes = []
    w._monitor.run_cycle = MagicMock(return_value=mock_result)
    w.start()
    time.sleep(0.3)
    w.stop()
    finished = w.wait(5000)  # 5 s absorbs worst-case 1-s sleep iteration on CI
    assert finished, "AvailabilityWorker did not stop within 5 s"
    assert not w.isRunning()
    _cleanup(w)
