"""Tests for workers/report_scheduler_worker.py (RULE-T2)."""
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


def test_import():
    from workers.report_scheduler_worker import ReportSchedulerWorker  # noqa: F401


def test_instantiation(tmp_path):
    from modules.metric_store import MetricStore
    from workers.report_scheduler_worker import ReportSchedulerWorker
    store = MetricStore(str(tmp_path / "test.db"))
    w = ReportSchedulerWorker(store=store)
    assert not w.isRunning()
    _cleanup(w)


def test_signals_exist(tmp_path):
    from modules.metric_store import MetricStore
    from workers.report_scheduler_worker import ReportSchedulerWorker
    store = MetricStore(str(tmp_path / "test.db"))
    w = ReportSchedulerWorker(store=store)
    assert hasattr(w, "report_saved")
    assert hasattr(w, "error")
    _cleanup(w)


def test_start_stop_lifecycle(tmp_path):
    """Worker must stop within 3 s after stop() is called."""
    from modules.metric_store import MetricStore
    from workers.report_scheduler_worker import ReportSchedulerWorker
    store = MetricStore(str(tmp_path / "test.db"))
    errors = []
    w = ReportSchedulerWorker(store=store)
    w.error.connect(errors.append)
    w.start()
    time.sleep(0.3)
    w.stop()
    finished = w.wait(3000)
    assert finished, "ReportSchedulerWorker did not stop within 3 s"
    assert not w.isRunning()
    _cleanup(w)
