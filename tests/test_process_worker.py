"""Tests for workers/process_worker.py (RULE-T2)."""
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

def test_import_snapshot():
    from workers.process_worker import ConnectionSnapshotWorker  # noqa: F401


def test_import_poller():
    from workers.process_worker import ConnectionPollerWorker  # noqa: F401


# ── ConnectionSnapshotWorker ──────────────────────────────────────────────────

def test_snapshot_instantiation():
    from workers.process_worker import ConnectionSnapshotWorker
    w = ConnectionSnapshotWorker()
    assert not w.isRunning()
    _cleanup(w)


def test_snapshot_lifecycle():
    """One-shot worker must complete within 5 s."""
    from workers.process_worker import ConnectionSnapshotWorker
    errors = []
    w = ConnectionSnapshotWorker()
    w.error.connect(errors.append)
    w.start()
    finished = w.wait(5000)
    assert finished, "ConnectionSnapshotWorker did not finish within 5 s"
    assert not w.isRunning()
    _cleanup(w)


# ── ConnectionPollerWorker ────────────────────────────────────────────────────

def test_poller_instantiation():
    from workers.process_worker import ConnectionPollerWorker
    w = ConnectionPollerWorker(interval=60)
    assert not w.isRunning()
    _cleanup(w)


def test_poller_start_stop_lifecycle():
    """Continuous poller must stop within 3 s after _running is set False."""
    from workers.process_worker import ConnectionPollerWorker
    errors = []
    w = ConnectionPollerWorker(interval=60)
    w.error.connect(errors.append)
    w.start()
    time.sleep(0.3)
    w._running = False
    finished = w.wait(3000)
    assert finished, "ConnectionPollerWorker did not stop within 3 s"
    assert not w.isRunning()
    _cleanup(w)
