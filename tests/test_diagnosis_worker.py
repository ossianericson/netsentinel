"""Tests for workers/diagnosis_worker.py (RULE-T2)."""
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
    from workers.diagnosis_worker import DiagnosisWorker  # noqa: F401


def test_instantiation():
    from workers.diagnosis_worker import DiagnosisWorker
    w = DiagnosisWorker()
    assert not w.isRunning()
    _cleanup(w)


def test_instantiation_with_args():
    from workers.diagnosis_worker import DiagnosisWorker
    w = DiagnosisWorker(
        gateway_ip="192.168.1.1",
        gateway_mac="aa:bb:cc:dd:ee:ff",
        symptom="slow",
    )
    assert w._gateway_ip == "192.168.1.1"
    assert w._symptom == "slow"
    assert not w.isRunning()
    _cleanup(w)


def test_signals_exist():
    from workers.diagnosis_worker import DiagnosisWorker
    w = DiagnosisWorker()
    assert hasattr(w, "progress")
    assert hasattr(w, "finished")
    _cleanup(w)


def test_stop_sets_event():
    from workers.diagnosis_worker import DiagnosisWorker
    w = DiagnosisWorker()
    assert not w._stop.is_set()
    w.stop()
    assert w._stop.is_set()
    _cleanup(w)


def test_start_stop_lifecycle():
    """Worker must stop within 5 s after stop() is called."""
    from workers.diagnosis_worker import DiagnosisWorker
    w = DiagnosisWorker(symptom="slow")
    w.start()
    time.sleep(0.3)
    w.stop()
    finished = w.wait(5000)
    assert finished, "DiagnosisWorker did not stop within 5 s"
    assert not w.isRunning()
    _cleanup(w)
