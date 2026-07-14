"""Tests for workers/dns_benchmark_worker.py (RULE-T2, F-23)."""
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
    from workers.dns_benchmark_worker import DnsBenchmarkWorker  # noqa: F401


def test_instantiation():
    from workers.dns_benchmark_worker import DnsBenchmarkWorker
    w = DnsBenchmarkWorker()
    assert not w.isRunning()
    _cleanup(w)


def test_start_stop_lifecycle():
    """Worker must stop within 3 s (RULE-T2)."""
    from workers.dns_benchmark_worker import DnsBenchmarkWorker
    w = DnsBenchmarkWorker()
    w.start()
    time.sleep(0.2)
    w.stop()
    finished = w.wait(3000)
    assert finished, "DnsBenchmarkWorker did not stop within 3 s"
    assert not w.isRunning()
    _cleanup(w)


def test_emits_result_with_four_resolvers(monkeypatch):
    """result() must be a list of DnsResult, one per configured resolver."""
    from modules.network_diagnostics import DnsResult
    from workers.dns_benchmark_worker import DnsBenchmarkWorker

    fake = [
        DnsResult(server="System DNS", domain="google.com", latency_ms=5.0, resolved_ip="1.2.3.4", status="OK"),
        DnsResult(server="Cloudflare", domain="google.com", latency_ms=8.0, resolved_ip="1.2.3.4", status="OK"),
        DnsResult(server="Google",     domain="google.com", latency_ms=9.0, resolved_ip="1.2.3.4", status="OK"),
        DnsResult(server="Quad9",      domain="google.com", latency_ms=12.0, resolved_ip="1.2.3.4", status="OK"),
    ]
    monkeypatch.setattr("modules.network_diagnostics.run_dns_benchmark", lambda: fake)

    w = DnsBenchmarkWorker()
    received = []
    w.result.connect(received.append)
    w.start()
    finished = w.wait(5000)
    app = QApplication.instance()
    if app:
        for _ in range(5):
            app.processEvents()
    assert finished
    assert len(received) == 1
    assert [r.server for r in received[0]] == ["System DNS", "Cloudflare", "Google", "Quad9"]
    _cleanup(w)
