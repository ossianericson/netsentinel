"""Tests for workers/service_worker.py (RULE-T2)."""
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
    from workers.service_worker import ServiceWorker  # noqa: F401


def test_instantiation(tmp_path):
    from modules.metric_store import MetricStore
    from workers.service_worker import ServiceWorker
    store = MetricStore(str(tmp_path / "test.db"))
    w = ServiceWorker(store=store, targets=[], interval_s=3600)
    assert not w.isRunning()
    _cleanup(w)


def test_signals_exist(tmp_path):
    from modules.metric_store import MetricStore
    from workers.service_worker import ServiceWorker
    store = MetricStore(str(tmp_path / "test.db"))
    w = ServiceWorker(store=store, targets=[])
    assert hasattr(w, "check_done")
    assert hasattr(w, "error")
    _cleanup(w)


def test_start_stop_lifecycle(tmp_path):
    """Worker with no targets must stop within 3 s after stop() is called."""
    from modules.metric_store import MetricStore
    from workers.service_worker import ServiceWorker
    store = MetricStore(str(tmp_path / "test.db"))
    errors = []
    w = ServiceWorker(store=store, targets=[], interval_s=3600)
    w.error.connect(errors.append)
    w.start()
    time.sleep(0.3)
    w.stop()
    finished = w.wait(3000)
    assert finished, "ServiceWorker did not stop within 3 s"
    assert not w.isRunning()
    _cleanup(w)
