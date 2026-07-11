"""Tests for workers/firewall_worker.py (RULE-T2).

FirewallWorker moves the blocking netsh subprocess calls in
modules/firewall_control.py off the GUI thread. One worker, three ops
("block" | "unblock" | "list"), a single result_ready(dict) signal.
"""
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
    from workers.firewall_worker import FirewallWorker  # noqa: F401


def test_instantiation():
    from workers.firewall_worker import FirewallWorker
    w = FirewallWorker(op="list")
    assert not w.isRunning()
    _cleanup(w)


def test_signal_exists():
    from workers.firewall_worker import FirewallWorker
    w = FirewallWorker(op="list")
    assert hasattr(w, "result_ready")
    assert hasattr(w, "error")
    _cleanup(w)


def test_start_stop_lifecycle_list_op(monkeypatch):
    from workers.firewall_worker import FirewallWorker
    monkeypatch.setattr(
        "modules.firewall_control.get_blocked_rules", lambda: ["chrome.exe"]
    )
    results = []
    w = FirewallWorker(op="list")
    w.result_ready.connect(results.append)
    w.start()
    finished = w.wait(5000)
    assert finished, "FirewallWorker did not finish within 5 s"
    assert not w.isRunning()
    app = QApplication.instance()
    for _ in range(5):
        app.processEvents()
    assert len(results) == 1
    assert results[0]["op"] == "list"
    assert results[0]["rules"] == ["chrome.exe"]
    _cleanup(w)


def test_block_op_dispatches_to_block_process(monkeypatch):
    from workers.firewall_worker import FirewallWorker
    monkeypatch.setattr(
        "modules.firewall_control.block_process",
        lambda exe_path, exe_name: (True, f"Blocked: {exe_name}"),
    )
    results = []
    w = FirewallWorker(op="block", exe_path="C:\\foo.exe", exe_name="foo.exe")
    w.result_ready.connect(results.append)
    w.start()
    w.wait(5000)
    app = QApplication.instance()
    for _ in range(5):
        app.processEvents()
    assert results[0]["op"] == "block"
    assert results[0]["ok"] is True
    assert results[0]["message"] == "Blocked: foo.exe"
    _cleanup(w)


def test_unblock_op_dispatches_to_unblock_process(monkeypatch):
    from workers.firewall_worker import FirewallWorker
    monkeypatch.setattr(
        "modules.firewall_control.unblock_process",
        lambda exe_name: (False, "Rule not found"),
    )
    results = []
    w = FirewallWorker(op="unblock", exe_name="foo.exe")
    w.result_ready.connect(results.append)
    w.start()
    w.wait(5000)
    app = QApplication.instance()
    for _ in range(5):
        app.processEvents()
    assert results[0]["op"] == "unblock"
    assert results[0]["ok"] is False
    assert results[0]["message"] == "Rule not found"
    _cleanup(w)
