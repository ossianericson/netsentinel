"""Tests for modules/dhcp_lease_scanner.py — reads local lease files, no network."""
from __future__ import annotations

import pytest


def test_import():
    import modules.dhcp_lease_scanner  # noqa: F401


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
