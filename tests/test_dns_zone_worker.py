"""Tests for workers/dns_zone_worker.py (RULE-T2)."""
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
    from workers.dns_zone_worker import DnsZoneWorker  # noqa: F401


def test_instantiation():
    from workers.dns_zone_worker import DnsZoneWorker
    w = DnsZoneWorker()
    assert not w.isRunning()
    _cleanup(w)


def test_instantiation_with_args():
    from workers.dns_zone_worker import DnsZoneWorker
    w = DnsZoneWorker(
        axfr_server="192.168.1.1",
        axfr_domain="example.local",
        axfr_timeout=5.0,
        mdns_timeout=2.0,
    )
    assert w._axfr_server == "192.168.1.1"
    assert w._axfr_domain == "example.local"
    assert not w.isRunning()
    _cleanup(w)


def test_signals_exist():
    from workers.dns_zone_worker import DnsZoneWorker
    w = DnsZoneWorker()
    assert hasattr(w, "result_ready")
    assert hasattr(w, "progress")
    assert hasattr(w, "error")
    _cleanup(w)


def test_start_stop_lifecycle():
    """DnsZoneWorker is one-shot; must complete within a short timeout."""
    from workers.dns_zone_worker import DnsZoneWorker
    errors = []
    w = DnsZoneWorker(axfr_timeout=1.0, mdns_timeout=1.0)
    w.error.connect(errors.append)
    w.start()
    finished = w.wait(10000)
    assert finished, "DnsZoneWorker did not finish within 10 s"
    assert not w.isRunning()
    _cleanup(w)
    # Errors and empty results are expected in CI (no real DNS server).
