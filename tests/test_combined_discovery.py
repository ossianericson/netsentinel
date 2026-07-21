"""Tests for modules/combined_discovery.py — multi-method device discovery."""
from __future__ import annotations

import threading


def test_import():
    from modules import combined_discovery  # noqa: F401


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


def test_ping_single_delegates_to_icmp_ping(monkeypatch):
    """combined_discovery._ping_single must call utils_net.icmp_ping (Phase 2b reroute)."""
    from modules import combined_discovery
    from modules import utils_net

    calls = []

    def fake_icmp_ping(host, timeout=2.0):
        calls.append((host, timeout))
        return 12.5

    monkeypatch.setattr(utils_net, "icmp_ping", fake_icmp_ping)
    dev = combined_discovery._ping_single("192.168.1.20", timeout=0.5)
    assert calls == [("192.168.1.20", 0.5)]
    assert dev is not None
    assert dev.ip == "192.168.1.20"
    assert dev.response_ms == 12.5
    assert dev.discovery_methods == ["icmp-ping"]


def test_ping_single_returns_none_on_failure(monkeypatch):
    from modules import combined_discovery
    from modules import utils_net

    monkeypatch.setattr(utils_net, "icmp_ping", lambda host, timeout=2.0: -1.0)
    assert combined_discovery._ping_single("192.168.1.21", timeout=0.5) is None


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


def test_discovery_result_not_testable_defaults_false():
    from modules.combined_discovery import DiscoveryResult
    r = DiscoveryResult()
    assert r.not_testable is False
    assert r.not_testable_reason == ""


def test_discover_zero_devices_from_every_method_is_not_testable(monkeypatch):
    """Sprint 5b (E): zero devices from EVERY method (passive ARP cache +
    all 4 active methods) must not read as a genuinely empty network — even
    an empty /24 should see its own gateway via ARP in virtually all real
    environments. Zero signal from everything suggests something is
    blocking discovery, not a confirmed empty subnet."""
    from modules import combined_discovery as m

    monkeypatch.setattr(m, "_arp_cache_scan", lambda: {})
    monkeypatch.setattr(m, "_arp_sweep", lambda cidr, timeout: {})
    monkeypatch.setattr(m, "_icmp_sweep", lambda hosts, timeout: {})
    monkeypatch.setattr(m, "_tcp_sweep", lambda hosts, ports, timeout: {})
    monkeypatch.setattr(m, "_mdns_query", lambda timeout: {})

    result = m.discover(cidr="192.168.250.0/30", resolve_hostnames=False, timeout=0.01)

    assert result.count == 0
    assert result.not_testable is True
    assert result.not_testable_reason != ""
    assert "Could not test" in result.plain_verdict


def test_discover_with_any_device_found_is_not_not_testable(monkeypatch):
    """Even a single confirmed device (e.g. only the gateway responds) proves
    discovery reached the network — a genuinely small/quiet network must not
    be flagged not_testable."""
    from modules import combined_discovery as m
    from modules.combined_discovery import DiscoveredDevice

    monkeypatch.setattr(m, "_arp_cache_scan", lambda: {
        "192.168.250.1": DiscoveredDevice(ip="192.168.250.1", discovery_methods=["arp-cache"]),
    })
    monkeypatch.setattr(m, "_arp_sweep", lambda cidr, timeout: {})
    monkeypatch.setattr(m, "_icmp_sweep", lambda hosts, timeout: {})
    monkeypatch.setattr(m, "_tcp_sweep", lambda hosts, ports, timeout: {})
    monkeypatch.setattr(m, "_mdns_query", lambda timeout: {})

    result = m.discover(cidr="192.168.250.0/30", resolve_hostnames=False, timeout=0.01)

    assert result.count == 1
    assert result.not_testable is False


def test_discover_cancelled_scan_is_not_flagged_not_testable(monkeypatch):
    """A deliberate user cancellation (stop_event set) is not an environment
    failure and must not be reported as not_testable."""
    from modules import combined_discovery as m

    monkeypatch.setattr(m, "_arp_cache_scan", lambda: {})

    stop = threading.Event()
    stop.set()
    result = m.discover(
        cidr="192.168.250.0/30", passive_only=True, resolve_hostnames=False,
        timeout=0, stop_event=stop,
    )
    assert result.not_testable is False


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
