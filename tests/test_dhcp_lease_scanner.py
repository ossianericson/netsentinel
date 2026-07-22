"""Tests for modules/dhcp_lease_scanner.py — reads local lease files, no network."""
from __future__ import annotations

import pytest


def test_import():
    from modules import dhcp_lease_scanner  # noqa: F401


def test_dhcp_lease_dataclass_fields():
    from modules.dhcp_lease_scanner import DhcpLease
    lease = DhcpLease(
        mac="aa:bb:cc:dd:ee:ff",
        ip="192.168.1.100",
        hostname="myhost",
        expires=None,
        server="192.168.1.1",
        source="test",
    )
    assert lease.ip == "192.168.1.100"
    assert lease.mac == "aa:bb:cc:dd:ee:ff"
    assert lease.hostname == "myhost"
    assert lease.source == "test"


def test_verdict_single_server():
    from modules.dhcp_lease_scanner import DhcpLease, verdict
    import time
    leases = [DhcpLease(mac="aa:bb:cc:00:00:01", ip="192.168.1.1",
                         hostname="router", expires=int(time.time()) + 3600,
                         server="192.168.1.1", source="arp")]
    result = verdict(leases)
    assert isinstance(result, str)
    assert len(result) > 0


def test_verdict_empty():
    from modules.dhcp_lease_scanner import verdict
    result = verdict([])
    assert isinstance(result, str)


def test_verdict_multiple_servers():
    from modules.dhcp_lease_scanner import DhcpLease, verdict
    import time
    exp = int(time.time()) + 3600
    leases = [
        DhcpLease(mac="aa:bb:cc:00:00:01", ip="192.168.1.1",
                  hostname="router", expires=exp, server="192.168.1.1", source="arp"),
        DhcpLease(mac="bb:cc:dd:00:00:02", ip="192.168.1.200",
                  hostname="rogue", expires=exp, server="192.168.1.200", source="arp"),
    ]
    result = verdict(leases)
    assert isinstance(result, str)


def test_scan_returns_list():
    from modules.dhcp_lease_scanner import scan
    leases = scan()
    assert isinstance(leases, list)
    for lease in leases:
        from modules.dhcp_lease_scanner import DhcpLease
        assert isinstance(lease, DhcpLease)


def test_scan_does_not_raise():
    from modules.dhcp_lease_scanner import scan
    try:
        scan()
    except Exception as exc:
        pytest.fail(f"scan() raised unexpectedly: {exc}")


def test_windows_arp_leases_survives_missing_create_no_window(monkeypatch):
    """`subprocess.CREATE_NO_WINDOW` is Windows-only.

    `_windows_arp_leases()` built its `creationflags` kwarg unconditionally at the
    top of the function — outside the try block — so on a platform without the
    attribute it raised AttributeError instead of returning []. That breaks both
    the module docstring's "safe to import on all platforms" contract and
    `scan()`'s documented "Never raises". Same shape as the smb_enumerator fix.
    """
    import subprocess as _sp
    from modules import dhcp_lease_scanner

    monkeypatch.delattr(_sp, "CREATE_NO_WINDOW", raising=False)
    monkeypatch.setattr(dhcp_lease_scanner, "get_arp_snapshot", lambda: {})

    def _no_ipconfig(*_a, **_k):
        raise OSError("ipconfig not available on this platform")

    monkeypatch.setattr(_sp, "check_output", _no_ipconfig)

    assert dhcp_lease_scanner._windows_arp_leases() == []
