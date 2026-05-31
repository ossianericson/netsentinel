"""Tests for modules/port_scanner.py — TCP connect-scan."""
import pytest
from modules.port_scanner import (
    PORT_NAMES, PortResult, PortScanResult, apply_politeness, scan,
)


def test_import():
    import modules.port_scanner as m
    assert hasattr(m, "scan")
    assert hasattr(m, "PORT_NAMES")
    assert hasattr(m, "PortResult")
    assert hasattr(m, "PortScanResult")


def test_port_names_is_dict():
    assert isinstance(PORT_NAMES, dict)
    assert 22 in PORT_NAMES
    assert 80 in PORT_NAMES
    assert 443 in PORT_NAMES


def test_port_result_fields():
    r = PortResult(port=80, name="HTTP", open=True, banner="")
    assert r.port == 80
    assert r.name == "HTTP"
    assert r.open is True


def test_port_scan_result_defaults():
    r = PortScanResult(host="192.168.1.1")
    assert r.host == "192.168.1.1"
    assert r.open_ports == []


def test_apply_politeness_normal():
    ports = list(range(1, 21))
    result = apply_politeness(ports, level="normal")
    assert isinstance(result, list)
    assert len(result) == len(ports)


def test_apply_politeness_paranoid():
    ports = list(range(1, 21))
    result = apply_politeness(ports, level="paranoid")
    assert isinstance(result, list)


def test_scan_unreachable_host_returns_result():
    result = scan("240.0.0.1", ports=[65432], timeout=0.1)
    assert isinstance(result, PortScanResult)
    assert result.host == "240.0.0.1"


def test_scan_result_open_ports_list():
    result = scan("240.0.0.1", ports=[65432], timeout=0.1)
    assert isinstance(result.open_ports, list)
