"""Tests for modules/utils_net.py — get_network_info, get_dhcp_info, get_interface_details."""

import subprocess
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

from modules.utils_net import (
    get_network_info, get_dhcp_info, get_interface_details, icmp_ping,
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
