"""Tests for workers/syslog_worker.py (RULE-T2)."""
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
    from workers.syslog_worker import SyslogWorker  # noqa: F401


def test_instantiation():
    from workers.syslog_worker import SyslogWorker
    w = SyslogWorker(port=15140)   # high port to avoid admin requirement
    assert not w.isRunning()
    _cleanup(w)


def test_signals_exist():
    from workers.syslog_worker import SyslogWorker
    w = SyslogWorker(port=15140)
    assert hasattr(w, "message_received")
    assert hasattr(w, "error")
    assert hasattr(w, "status")
    _cleanup(w)


def test_start_stop_lifecycle():
    """Worker must stop within 5 s after stop() is called."""
    from workers.syslog_worker import SyslogWorker
    errors = []
    w = SyslogWorker(port=15141)
    w.error.connect(errors.append)
    w.start()
    time.sleep(0.5)
    w.stop()
    finished = w.wait(5000)
    assert finished, "SyslogWorker did not stop within 5 s"
    assert not w.isRunning()
    _cleanup(w)
    # Errors are allowed (port binding may fail in CI); thread must stop.


def test_bound_reports_the_port_actually_bound():
    """S4.4e — the port as a number, so app.py can tell a fallback from a random port
    without parsing the localized-looking status text."""
    from workers.syslog_worker import SyslogWorker

    app = QApplication.instance()
    w = SyslogWorker(port=0, bind_address="127.0.0.1")
    bound = []
    w.bound.connect(bound.append)
    assert w.listen_port == 0, "nothing is bound before the thread runs"
    w.start()
    deadline = time.monotonic() + 5
    while not bound and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.02)
    port_while_running = w.listen_port
    w.stop()
    assert w.wait(5000)
    _cleanup(w)

    assert len(bound) == 1 and bound[0] > 0
    assert port_while_running == bound[0]
