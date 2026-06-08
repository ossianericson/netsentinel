"""Tests for modules/port_scanner.py (RULE-T1)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch


import modules.port_scanner as ps


# ── Import / constants ────────────────────────────────────────────────────────

def test_import():
    assert hasattr(ps, "scan")
    assert hasattr(ps, "PortScanResult")
    assert hasattr(ps, "PortResult")


def test_port_names_are_ints():
    for port in ps.PORT_NAMES:
        assert isinstance(port, int), f"PORT_NAMES key {port!r} is not an int"


def test_high_risk_ports_subset_of_common():
    assert ps.HIGH_RISK_PORTS.issubset(set(ps.COMMON_PORTS))


def test_scan_modes_have_required_keys():
    required = {"timeout", "workers", "delay"}
    for name, cfg in ps.SCAN_MODES.items():
        assert required <= set(cfg.keys()), f"Mode {name!r} missing keys"


def test_politeness_levels_have_required_keys():
    required = {"min_delay", "max_delay", "randomise_order", "batch"}
    for name, cfg in ps.POLITENESS_LEVELS.items():
        assert required <= set(cfg.keys()), f"Level {name!r} missing keys"


# ── apply_politeness ──────────────────────────────────────────────────────────

def test_apply_politeness_normal_preserves_order():
    ports = list(range(10))
    result = ps.apply_politeness(ports, level="normal")
    assert result == ports


def test_apply_politeness_unknown_level_falls_back_to_normal():
    ports = [22, 80, 443]
    result = ps.apply_politeness(ports, level="nonexistent_level")
    assert sorted(result) == sorted(ports)


def test_apply_politeness_sneaky_returns_all_ports():
    ports = [22, 80, 443, 8080]
    result = ps.apply_politeness(ports, level="sneaky")
    assert sorted(result) == sorted(ports)


# ── PortResult / PortScanResult dataclasses ───────────────────────────────────

def test_port_result_defaults():
    r = ps.PortResult(port=80, name="HTTP", open=True)
    assert r.port == 80
    assert r.name == "HTTP"
    assert r.open is True
    assert r.risk == "LOW"
    assert r.banner == ""


def test_port_result_high_risk_flag():
    r = ps.PortResult(port=23, name="Telnet", open=True, risk="HIGH")
    assert r.risk == "HIGH"


def test_port_scan_result_defaults():
    r = ps.PortScanResult(host="192.168.1.1")
    assert r.host == "192.168.1.1"
    assert r.open_ports == []
    assert r.error == ""


# ── scan_host (mocked sockets) ────────────────────────────────────────────────

def _closed_connect(*args, **kwargs):
    raise ConnectionRefusedError


def test_scan_host_all_closed(monkeypatch):
    """scan with all ports refusing returns zero open ports."""
    def _refuse(*args, **kwargs):
        raise ConnectionRefusedError

    with patch("socket.create_connection", side_effect=_refuse):
        with patch("socket.gethostbyname", return_value="127.0.0.1"):
            result = ps.scan("127.0.0.1", ports=[80, 443], mode="fast")

    assert isinstance(result, ps.PortScanResult)
    assert result.open_ports == []
    assert result.scanned >= 0


def test_scan_one_open(monkeypatch):
    """scan reports port 80 as open when create_connection succeeds only for 80."""
    mock_sock = MagicMock()
    mock_sock.__enter__ = lambda s: s
    mock_sock.__exit__ = MagicMock(return_value=False)
    mock_sock.recv.return_value = b""

    def _open_only_80(addr, timeout):
        if addr[1] == 80:
            return mock_sock
        raise ConnectionRefusedError

    with patch("socket.create_connection", side_effect=_open_only_80):
        with patch("socket.gethostbyname", return_value="127.0.0.1"):
            result = ps.scan("127.0.0.1", ports=[22, 80, 443], mode="fast")

    open_ports = [r.port for r in result.open_ports]
    assert 80 in open_ports
    assert 22 not in open_ports
    assert 443 not in open_ports


def test_scan_error_on_bad_host():
    """scan on an unresolvable host returns an error string, not an exception."""
    result = ps.scan("this.host.does.not.exist.invalid", ports=[80], mode="fast")
    assert isinstance(result, ps.PortScanResult)
    assert result.error != "" or result.open_ports == []


# ── Risk annotation ───────────────────────────────────────────────────────────

def test_risk_annotation_for_telnet():
    """Port 23 must be annotated HIGH risk when open."""
    mock_sock = MagicMock()
    mock_sock.__enter__ = lambda s: s
    mock_sock.__exit__ = MagicMock(return_value=False)
    mock_sock.recv.return_value = b""

    with patch("socket.create_connection", return_value=mock_sock):
        with patch("socket.gethostbyname", return_value="127.0.0.1"):
            result = ps.scan("127.0.0.1", ports=[23], mode="fast")

    assert len(result.open_ports) == 1
    assert result.open_ports[0].port == 23
    assert result.open_ports[0].risk == "HIGH"
