"""Tests for modules/topology_share.py (TDD — written before implementation)."""

import types

from modules.topology_share import _prepare_render_data, render_sanitized_topology_png


def _devices():
    return [
        types.SimpleNamespace(ip="192.168.1.50", mac="aa:bb:cc:dd:ee:01", vendor="Acme", hostname="my-laptop"),
        types.SimpleNamespace(ip="192.168.1.60", mac="aa:bb:cc:dd:ee:02", vendor="TP-Link", hostname="router2"),
    ]


def test_prepare_render_data_masks_ips():
    data = _prepare_render_data(_devices(), gateway_ip="192.168.1.1", gateway_mac="aa:bb:cc:00:00:01", edges=[])
    all_labels = " ".join(n["label"] for n in data["nodes"])
    assert "192.168.1.50" not in all_labels
    assert "192.168.1.60" not in all_labels
    assert "192.168.1.1" not in all_labels


def test_prepare_render_data_strips_mac_and_hostname():
    data = _prepare_render_data(_devices(), gateway_ip="192.168.1.1", gateway_mac="aa:bb:cc:00:00:01", edges=[])
    all_labels = " ".join(n["label"] for n in data["nodes"])
    assert "aa:bb:cc:dd:ee:01" not in all_labels.lower()
    assert "my-laptop" not in all_labels
    assert "router2" not in all_labels


def test_prepare_render_data_uses_vendor_name():
    data = _prepare_render_data(_devices(), gateway_ip="192.168.1.1", gateway_mac="aa:bb:cc:00:00:01", edges=[])
    all_labels = " ".join(n["label"] for n in data["nodes"])
    assert "Acme" in all_labels
    assert "TP-Link" in all_labels


def test_prepare_render_data_includes_gateway_node():
    data = _prepare_render_data(_devices(), gateway_ip="192.168.1.1", gateway_mac="aa:bb:cc:00:00:01", edges=[])
    assert any(n["is_gateway"] for n in data["nodes"])


def test_prepare_render_data_accepts_dict_devices():
    dict_devices = [
        {"ip": "192.168.1.70", "mac": "aa:bb:cc:dd:ee:03", "vendor": "Google", "hostname": "chromecast"},
    ]
    data = _prepare_render_data(dict_devices, gateway_ip="192.168.1.1", gateway_mac=None, edges=[])
    all_labels = " ".join(n["label"] for n in data["nodes"])
    assert "192.168.1.70" not in all_labels
    assert "chromecast" not in all_labels
    assert "Google" in all_labels


def test_render_sanitized_topology_png_writes_file(tmp_path):
    out = tmp_path / "share.png"
    result = render_sanitized_topology_png(
        _devices(), gateway_ip="192.168.1.1", gateway_mac="aa:bb:cc:00:00:01",
        edges=[], output_path=out,
    )
    assert result == out
    assert out.exists()
    assert out.stat().st_size > 0
