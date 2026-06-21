"""Tests for workers/rest_api_worker.py (RULE-T2)."""
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
    from workers.rest_api_worker import RestApiWorker  # noqa: F401


def test_instantiation(tmp_path):
    from modules.metric_store import MetricStore
    from workers.rest_api_worker import RestApiWorker
    store = MetricStore(str(tmp_path / "test.db"))
    w = RestApiWorker(store=store)
    assert not w.isRunning()
    _cleanup(w)


def test_signals_exist(tmp_path):
    from modules.metric_store import MetricStore
    from workers.rest_api_worker import RestApiWorker
    store = MetricStore(str(tmp_path / "test.db"))
    w = RestApiWorker(store=store)
    assert hasattr(w, "started_ok")
    assert hasattr(w, "stopped")
    assert hasattr(w, "error")
    _cleanup(w)


def test_set_bind(tmp_path):
    from modules.metric_store import MetricStore
    from workers.rest_api_worker import RestApiWorker
    store = MetricStore(str(tmp_path / "test.db"))
    w = RestApiWorker(store=store)
    w.set_bind("127.0.0.1", 19765)
    assert w._host == "127.0.0.1"
    assert w._port == 19765
    _cleanup(w)


def test_start_stop_lifecycle(tmp_path):
    """Worker must stop within 5 s after stop() is called."""
    from modules.metric_store import MetricStore
    from workers.rest_api_worker import RestApiWorker
    store = MetricStore(str(tmp_path / "test.db"))
    errors = []
    w = RestApiWorker(store=store)
    w.set_bind("127.0.0.1", 19766)
    w.error.connect(errors.append)
    w.start()
    time.sleep(0.5)
    w.stop()
    finished = w.wait(5000)
    assert finished, "RestApiWorker did not stop within 5 s"
    assert not w.isRunning()
    _cleanup(w)
    # Errors are allowed (Flask not installed, port conflict); thread must stop.
