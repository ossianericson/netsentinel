"""Tests for workers/dhcp_lease_worker.py (RULE-T2)."""
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
    from workers.dhcp_lease_worker import DhcpLeaseWorker  # noqa: F401


def test_instantiation():
    from workers.dhcp_lease_worker import DhcpLeaseWorker
    w = DhcpLeaseWorker()
    assert not w.isRunning()
    _cleanup(w)


def test_start_stop_lifecycle():
    """DhcpLeaseWorker is one-shot; must complete and stop on its own."""
    from workers.dhcp_lease_worker import DhcpLeaseWorker
    errors = []
    w = DhcpLeaseWorker()
    w.error.connect(errors.append)
    w.start()
    finished = w.wait(5000)
    assert finished, "DhcpLeaseWorker did not finish within 5 s"
    assert not w.isRunning()
    _cleanup(w)
    # Errors are allowed (no DHCP data in CI); thread must still complete.


def test_signals_exist():
    from workers.dhcp_lease_worker import DhcpLeaseWorker
    w = DhcpLeaseWorker()
    assert hasattr(w, "result_ready")
    assert hasattr(w, "error")
    _cleanup(w)
