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
    """DhcpLeaseWorker is one-shot; must complete and stop on its own.

    10 s (not 5 s) because work() now enriches missing hostnames via
    name_resolver, which is bounded by its own 6 s internal timeout.
    """
    from workers.dhcp_lease_worker import DhcpLeaseWorker
    errors = []
    w = DhcpLeaseWorker()
    w.error.connect(errors.append)
    w.start()
    finished = w.wait(10000)
    assert finished, "DhcpLeaseWorker did not finish within 10 s"
    assert not w.isRunning()
    _cleanup(w)
    # Errors are allowed (no DHCP data in CI); thread must still complete.


def test_signals_exist():
    from workers.dhcp_lease_worker import DhcpLeaseWorker
    w = DhcpLeaseWorker()
    assert hasattr(w, "result_ready")
    assert hasattr(w, "error")
    _cleanup(w)


def test_work_enriches_missing_hostnames_via_name_resolver(monkeypatch):
    """Regression: Windows ARP-derived leases have no hostname (RULE-T3).

    _windows_arp_leases() builds DhcpLease records straight from the ARP
    cache with hostname="" — the DHCP Leases page then shows a blank
    hostname column for every row. The worker must enrich empty hostnames
    via name_resolver before emitting.
    """
    from workers.dhcp_lease_worker import DhcpLeaseWorker
    from modules.dhcp_lease_scanner import DhcpLease
    from modules.name_resolver import ResolvedName

    raw_leases = [
        DhcpLease(mac="aa:bb:cc:dd:ee:01", ip="192.168.1.10",
                  hostname="", source="ARP cache (Windows)"),
        DhcpLease(mac="aa:bb:cc:dd:ee:02", ip="192.168.1.11",
                  hostname="already-set", source="ARP cache (Windows)"),
    ]
    monkeypatch.setattr("workers.dhcp_lease_worker._scan", lambda: raw_leases)

    def _fake_resolve_batch(devices, mac_key="mac", ip_key="ip", **kwargs):
        return {
            "192.168.1.10": ResolvedName(ip="192.168.1.10", display_name="laptop-01"),
            "192.168.1.11": ResolvedName(ip="192.168.1.11", display_name="should-not-be-used"),
        }
    monkeypatch.setattr(
        "modules.name_resolver.resolve_batch", _fake_resolve_batch
    )

    emitted = []
    w = DhcpLeaseWorker()
    w.result_ready.connect(emitted.append)
    w.work()

    assert len(emitted) == 1
    leases = emitted[0]
    by_ip = {lease.ip: lease for lease in leases}
    assert by_ip["192.168.1.10"].hostname == "laptop-01", (
        "empty hostname must be filled in from name_resolver.resolve_batch()"
    )
    assert by_ip["192.168.1.11"].hostname == "already-set", (
        "a lease that already has a hostname must not be overwritten"
    )


def test_enrichment_gives_up_after_timeout_instead_of_blocking(monkeypatch):
    """A slow/large resolve_batch() must not block the worker indefinitely."""
    import time
    from workers.dhcp_lease_worker import _enrich_missing_hostnames
    from modules.dhcp_lease_scanner import DhcpLease

    def _slow_resolve_batch(devices, mac_key="mac", ip_key="ip", **kwargs):
        time.sleep(2.0)
        return {}
    monkeypatch.setattr("modules.name_resolver.resolve_batch", _slow_resolve_batch)

    leases = [DhcpLease(mac="aa:bb:cc:dd:ee:03", ip="192.168.1.12", hostname="")]
    t0 = time.time()
    _enrich_missing_hostnames(leases, timeout=0.3)
    elapsed = time.time() - t0

    assert elapsed < 1.0, f"enrichment did not honour the timeout bound ({elapsed:.2f}s)"
    assert leases[0].hostname == ""  # timed out; left blank rather than blocking
