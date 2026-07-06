"""Tests for modules/utils_net.py — get_network_info, get_dhcp_info, get_interface_details."""

import subprocess
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

from modules.utils_net import (
    get_network_info, get_dhcp_info, get_interface_details, icmp_ping,
    tcp_probe, get_arp_snapshot, parallel_map,
)


def test_get_network_info_returns_dict():
    info = get_network_info()
    assert isinstance(info, dict)
    assert "local_ips" in info
    assert "gateway" in info
    assert "dns_servers" in info
    assert "domain" in info
    assert isinstance(info["local_ips"], list)
    assert isinstance(info["dns_servers"], list)


def test_get_network_info_gateway_mac_key_present():
    info = get_network_info()
    assert "gateway_mac" in info


def test_get_dhcp_info_returns_dict():
    info = get_dhcp_info()
    assert isinstance(info, dict)
    assert "dhcp_enabled" in info
    assert "dhcp_server" in info
    assert "lease_duration_h" in info
    assert isinstance(info["dhcp_enabled"], bool)
    assert isinstance(info["lease_duration_h"], float)


def test_get_interface_details_returns_list():
    adapters = get_interface_details()
    assert isinstance(adapters, list)
    for a in adapters:
        assert "name" in a
        assert "type" in a
        assert "mac" in a
        assert "ipv4" in a


def _make_ping_run(rtt_line="time=12ms"):
    def _run(cmd, **kwargs):
        mock = MagicMock()
        mock.returncode = 0
        mock.stdout = rtt_line
        return mock
    return _run


def _mock_ping(rtt_line, system=None):
    """Patch subprocess.run with canned ping output; optionally pin the OS branch.

    icmp_ping selects its parse regex via platform.system(), so tests feeding
    OS-specific ping output must pin the platform or they fail on other CI OSes.
    """
    stack = ExitStack()
    if system is not None:
        stack.enter_context(
            patch("modules.utils_net.platform.system", return_value=system))
        if system == "Windows":
            # Absent on POSIX Python; icmp_ping reads it before the try block
            stack.enter_context(
                patch.object(subprocess, "CREATE_NO_WINDOW", 0, create=True))
    stack.enter_context(patch("subprocess.run", side_effect=_make_ping_run(rtt_line)))
    return stack


def test_icmp_ping_parses_rtt_from_output():
    with _mock_ping("time=12ms", system="Windows"):
        assert icmp_ping("8.8.8.8", timeout=2.0) == 12.0


def test_icmp_ping_sub_millisecond_reply():
    # "time<1ms" also matches the primary time[=<](\d+)ms regex (group="1"), so this
    # returns 1.0 — preserves the exact (pre-existing) behavior of the original
    # network_logger._ping_once this helper was extracted from.
    with _mock_ping("time<1ms", system="Windows"):
        assert icmp_ping("8.8.8.8", timeout=2.0) == 1.0


def test_icmp_ping_parses_posix_decimal_rtt():
    with _mock_ping("64 bytes from 8.8.8.8: icmp_seq=1 ttl=117 time=12.3 ms",
                    system="Linux"):
        assert icmp_ping("8.8.8.8", timeout=2.0) == 12.3


def test_icmp_ping_returns_negative_on_timeout():
    with patch("subprocess.run", side_effect=TimeoutError):
        assert icmp_ping("8.8.8.8", timeout=2.0) == -1.0


def test_icmp_ping_returns_negative_on_no_match():
    with patch("subprocess.run", side_effect=_make_ping_run("Request timed out.")):
        assert icmp_ping("8.8.8.8", timeout=2.0) == -1.0


def test_get_network_info_dns_deduplicated():
    info = get_network_info()
    dns = info["dns_servers"]
    assert len(dns) == len(set(dns)), "DNS servers should be deduplicated"


def test_get_network_info_importable_from_utils():
    from modules.utils import get_network_info as gni
    assert gni is get_network_info


# ── tcp_probe ─────────────────────────────────────────────────────────────────

def test_tcp_probe_returns_true_rtt_on_success():
    with patch("modules.utils_net.socket.create_connection") as mock_conn:
        mock_conn.return_value.__enter__ = lambda s: s
        mock_conn.return_value.__exit__ = MagicMock(return_value=False)
        ok, rtt, error = tcp_probe("example.com", 80)
    assert ok is True
    assert rtt >= 0
    assert error == ""


def test_tcp_probe_returns_false_on_connection_refused():
    with patch("modules.utils_net.socket.create_connection",
               side_effect=ConnectionRefusedError("refused")):
        ok, rtt, error = tcp_probe("localhost", 9)
    assert ok is False
    assert rtt == -1.0
    assert "refused" in error


def test_tcp_probe_returns_false_on_timeout():
    with patch("modules.utils_net.socket.create_connection",
               side_effect=TimeoutError("timed out")):
        ok, rtt, error = tcp_probe("10.0.0.254", 80, timeout=0.01)
    assert ok is False
    assert rtt == -1.0


# ── get_arp_snapshot ──────────────────────────────────────────────────────────

def test_get_arp_snapshot_returns_dict():
    snapshot = get_arp_snapshot()
    assert isinstance(snapshot, dict)


def test_get_arp_snapshot_parses_windows_output():
    windows_arp = (
        "Interface: 192.168.1.10 --- 0xe\n"
        "  Internet Address      Physical Address      Type\n"
        "  192.168.1.1            aa-bb-cc-dd-ee-ff     dynamic\n"
        "  192.168.1.255          ff-ff-ff-ff-ff-ff     static\n"
        "  224.0.0.251            01-00-5e-00-00-fb     static\n"
    )
    with patch("modules.utils_net.platform.system", return_value="Windows"), \
         patch("modules.utils_net.subprocess.check_output", return_value=windows_arp), \
         patch.object(subprocess, "CREATE_NO_WINDOW", 0, create=True):
        snapshot = get_arp_snapshot()
    assert snapshot == {"192.168.1.1": "aa:bb:cc:dd:ee:ff"}


def test_get_arp_snapshot_parses_posix_output():
    posix_arp = (
        "? (192.168.1.1) at aa:bb:cc:dd:ee:ff [ether] on eth0\n"
        "? (192.168.1.255) at ff:ff:ff:ff:ff:ff [ether] on eth0\n"
    )
    with patch("modules.utils_net.platform.system", return_value="Linux"), \
         patch("modules.utils_net.subprocess.check_output", return_value=posix_arp):
        snapshot = get_arp_snapshot()
    assert snapshot == {"192.168.1.1": "aa:bb:cc:dd:ee:ff"}


def test_get_arp_snapshot_falls_back_to_arp_a_on_posix():
    posix_arp_a = "192.168.1.1 (192.168.1.1) at aa:bb:cc:dd:ee:ff [ether] on eth0\n"

    def _fake_check_output(cmd, **kwargs):
        if cmd == ["arp", "-n"]:
            raise subprocess.CalledProcessError(1, cmd)
        return posix_arp_a

    with patch("modules.utils_net.platform.system", return_value="Linux"), \
         patch("modules.utils_net.subprocess.check_output", side_effect=_fake_check_output):
        snapshot = get_arp_snapshot()
    assert snapshot == {"192.168.1.1": "aa:bb:cc:dd:ee:ff"}


def test_get_arp_snapshot_returns_empty_dict_on_failure():
    with patch("modules.utils_net.subprocess.check_output", side_effect=OSError("no arp")):
        snapshot = get_arp_snapshot()
    assert snapshot == {}


# ── parallel_map ──────────────────────────────────────────────────────────────

def test_parallel_map_preserves_input_order():
    results = parallel_map(lambda n: n * 2, [1, 2, 3, 4, 5], workers=3)
    assert results == [2, 4, 6, 8, 10]


def test_parallel_map_empty_items_returns_empty_list():
    assert parallel_map(lambda n: n, [], workers=4) == []


def test_parallel_map_propagates_exceptions():
    import pytest

    def _boom(n):
        if n == 2:
            raise ValueError("boom")
        return n

    with pytest.raises(ValueError):
        parallel_map(_boom, [1, 2, 3], workers=2)


def test_parallel_map_runs_concurrently_not_serially():
    import time as _time

    def _slow(n):
        _time.sleep(0.1)
        return n

    t0 = _time.perf_counter()
    parallel_map(_slow, list(range(5)), workers=5)
    elapsed = _time.perf_counter() - t0
    assert elapsed < 0.4, "expected concurrent execution, looks serial"
