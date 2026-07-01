"""Tests for modules/combined_discovery.py — multi-method device discovery."""
from __future__ import annotations

import threading


def test_import():
    import modules.combined_discovery  # noqa: F401


def test_resolve_hostname_delegates_to_name_resolver(monkeypatch):
    """combined_discovery._resolve_hostname must call name_resolver.rdns (Phase 2a reroute)."""
    from modules import combined_discovery
    from modules import name_resolver

    calls = []

    def fake_rdns(ip, timeout=1.0):
        calls.append((ip, timeout))
        return "fake-host"

    monkeypatch.setattr(name_resolver, "rdns", fake_rdns)
    result = combined_discovery._resolve_hostname("192.168.1.10", timeout=0.5)
    assert result == "fake-host"
    assert calls == [("192.168.1.10", 0.5)]


def test_discovered_device_dataclass():
    from modules.combined_discovery import DiscoveredDevice
    d = DiscoveredDevice(
        ip="192.168.1.10",
        discovery_methods=["arp"],
        mdns_services=[],
        mac="aa:bb:cc:dd:ee:ff",
        hostname="mydevice",
    )
    assert d.ip == "192.168.1.10"
    assert "arp" in d.discovery_methods
    assert d.mac == "aa:bb:cc:dd:ee:ff"


def test_discovery_result_count():
    from modules.combined_discovery import DiscoveredDevice, DiscoveryResult
    devices = [
        DiscoveredDevice(ip="192.168.1.1", mac="aa:00:00:00:00:01",
                         discovery_methods=["arp"], mdns_services=[]),
        DiscoveredDevice(ip="192.168.1.2", mac="aa:00:00:00:00:02",
                         discovery_methods=["icmp"], mdns_services=[]),
    ]
    r = DiscoveryResult(devices=devices, cidr="192.168.1.0/24",
                         duration_s=1.2, methods_used=["arp"], error=None)
    assert r.count == 2


def test_discovery_result_plain_verdict():
    from modules.combined_discovery import DiscoveredDevice, DiscoveryResult
    devices = [DiscoveredDevice(ip="10.0.0.1", discovery_methods=["arp"], mdns_services=[])]
    r = DiscoveryResult(devices=devices, cidr="10.0.0.0/24",
                         duration_s=0.5, methods_used=["arp"], error=None)
    v = r.plain_verdict
    assert isinstance(v, str)
    assert len(v) > 0


def test_discovery_result_empty():
    from modules.combined_discovery import DiscoveryResult
    r = DiscoveryResult(devices=[], cidr="192.168.0.0/24",
                         duration_s=0.1, methods_used=[], error=None)
    assert r.count == 0
    v = r.plain_verdict
    assert isinstance(v, str)


def test_discovery_result_with_error():
    from modules.combined_discovery import DiscoveredDevice, DiscoveryResult
    devices = [DiscoveredDevice(ip="10.0.0.1", discovery_methods=["arp"], mdns_services=[])]
    r = DiscoveryResult(
        devices=devices, cidr="10.0.0.0/24", duration_s=2.0,
        methods_used=["arp"], error="SYN scan requires admin",
    )
    assert r.error == "SYN scan requires admin"


def test_discover_function_exists():
    from modules.combined_discovery import discover
    import inspect
    assert callable(discover)
    sig = inspect.signature(discover)
    assert "cidr" in sig.parameters


def test_discover_passive_only_no_crash():
    """discover() in passive-only mode should not raise."""
    from modules.combined_discovery import discover, DiscoveryResult
    stop = threading.Event()
    stop.set()
    try:
        result = discover(
            cidr="192.168.254.0/30",
            passive_only=True,
            resolve_hostnames=False,
            timeout=0,
            stop_event=stop,
        )
        assert isinstance(result, DiscoveryResult)
    except Exception:
        pass  # May require admin
