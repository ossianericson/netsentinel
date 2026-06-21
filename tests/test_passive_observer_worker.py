"""Tests for workers/passive_observer_worker.py (RULE-T2)."""
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
    from workers.passive_observer_worker import PassiveObserverWorker  # noqa: F401


def test_instantiation():
    from workers.passive_observer_worker import PassiveObserverWorker
    w = PassiveObserverWorker()
    assert not w.isRunning()
    _cleanup(w)


def test_signals_exist():
    from workers.passive_observer_worker import PassiveObserverWorker
    w = PassiveObserverWorker()
    assert hasattr(w, "observation_ready")
    assert hasattr(w, "error")
    _cleanup(w)


def test_start_stop_lifecycle():
    """Worker must stop within 3 s after stop() is called."""
    from workers.passive_observer_worker import PassiveObserverWorker
    errors = []
    w = PassiveObserverWorker()
    w.error.connect(errors.append)
    w.start()
    time.sleep(0.3)
    w.stop()
    finished = w.wait(3000)
    assert finished, "PassiveObserverWorker did not stop within 3 s"
    assert not w.isRunning()
    _cleanup(w)
    # Errors are allowed (SSDP/mDNS sockets may fail in CI).
