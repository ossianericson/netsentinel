"""Tests for workers/snmp_trap_worker.py (RULE-T2)."""
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
    from workers.snmp_trap_worker import SnmpTrapWorker  # noqa: F401


def test_instantiation():
    from workers.snmp_trap_worker import SnmpTrapWorker
    w = SnmpTrapWorker(port=16200)   # high port to avoid admin requirement
    assert not w.isRunning()
    _cleanup(w)


def test_signals_exist():
    from workers.snmp_trap_worker import SnmpTrapWorker
    w = SnmpTrapWorker(port=16200)
    assert hasattr(w, "trap_received")
    assert hasattr(w, "error")
    assert hasattr(w, "status")
    _cleanup(w)


def test_start_stop_lifecycle():
    """Worker must stop within 5 s after stop() is called."""
    from workers.snmp_trap_worker import SnmpTrapWorker
    errors = []
    w = SnmpTrapWorker(port=16201)
    w.error.connect(errors.append)
    w.start()
    time.sleep(0.5)
    w.stop()
    finished = w.wait(5000)
    assert finished, "SnmpTrapWorker did not stop within 5 s"
    assert not w.isRunning()
    _cleanup(w)
    # Errors are allowed (port binding may fail in CI); thread must stop.
