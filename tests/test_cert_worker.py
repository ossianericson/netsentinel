"""Tests for workers/cert_worker.py (RULE-T2)."""
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
    from workers.cert_worker import CertWorker  # noqa: F401


def test_instantiation(tmp_path):
    from modules.metric_store import MetricStore
    from workers.cert_worker import CertWorker
    store = MetricStore(str(tmp_path / "test.db"))
    w = CertWorker(store=store, targets=[], interval_s=3600)
    assert not w.isRunning()
    _cleanup(w)


def test_run_now_interrupts_sleep_early(tmp_path):
    """F-02: run_now() must wake the worker immediately instead of waiting out
    the full interval -- this is what lets the Security Scan panel's TLS &
    Exposure tool actually run on demand."""
    from modules.metric_store import MetricStore
    from workers.cert_worker import CertWorker
    store = MetricStore(str(tmp_path / "test.db"))
    w = CertWorker(store=store, targets=[], interval_s=3600)  # long interval
    checks = []
    w.check_done.connect(checks.append)
    w.start()
    time.sleep(0.3)  # let the first (immediate) check complete
    checks.clear()
    w.run_now()
    finished = False
    app = QApplication.instance()
    for _ in range(50):  # up to ~2.5s
        if app:
            app.processEvents()  # dispatch the cross-thread queued signal
        if checks:
            finished = True
            break
        time.sleep(0.05)
    w.stop()
    w.wait(3000)
    assert finished, "run_now() did not trigger a check within 2.5s (interval_s=3600)"
    _cleanup(w)


def test_start_stop_lifecycle(tmp_path):
    """Worker must stop within 3 s after stop() is called."""
    from modules.metric_store import MetricStore
    from workers.cert_worker import CertWorker
    store = MetricStore(str(tmp_path / "test.db"))
    errors = []
    w = CertWorker(store=store, targets=[], interval_s=3600)
    w.error.connect(errors.append)
    w.start()
    time.sleep(0.3)
    w.stop()
    finished = w.wait(3000)
    assert finished, "CertWorker did not stop within 3 s"
    assert not w.isRunning()
    _cleanup(w)
