"""Tests for modules/utils_net.py — get_network_info, get_dhcp_info, get_interface_details."""
import pytest
from unittest.mock import patch, MagicMock

from modules.utils_net import get_network_info, get_dhcp_info, get_interface_details


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


def test_get_network_info_dns_deduplicated():
    info = get_network_info()
    dns = info["dns_servers"]
    assert len(dns) == len(set(dns)), "DNS servers should be deduplicated"


def test_get_network_info_importable_from_utils():
    from modules.utils import get_network_info as gni
    assert gni is get_network_info
