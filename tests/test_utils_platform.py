"""Tests for modules/utils_platform.py — get_ipv6_devices, ping_sweep_ipv6."""

from modules.utils_platform import get_ipv6_devices, ping_sweep_ipv6


def test_get_ipv6_devices_returns_list():
    devices = get_ipv6_devices()
    assert isinstance(devices, list)


def test_get_ipv6_devices_structure():
    devices = get_ipv6_devices()
    for d in devices:
        assert "ip6" in d
        assert "mac" in d
        assert "state" in d


def test_ping_sweep_ipv6_returns_list():
    results = ping_sweep_ipv6()
    assert isinstance(results, list)


def test_ping_sweep_ipv6_progress_cb_called():
    calls = []
    ping_sweep_ipv6(progress_cb=lambda msg: calls.append(msg))
    # At minimum the "reading neighbour cache" message should appear
    assert any("IPv6" in c for c in calls)


def test_get_ipv6_devices_importable_from_utils():
    from modules.utils import get_ipv6_devices as gid
    assert gid is get_ipv6_devices
