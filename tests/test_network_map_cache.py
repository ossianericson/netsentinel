"""Tests for modules/network_map_cache.py — Network Map live-render persistence."""

import json

import pytest


def test_module_imports():
    from modules.network_map_cache import load_render_cache, save_render_cache
    assert save_render_cache is not None
    assert load_render_cache is not None


@pytest.fixture
def tmp_cache_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "modules.network_map_cache.get_app_data_dir",
        lambda: tmp_path,
    )
    return tmp_path


# ── save_render_cache / load_render_cache round-trip ──────────────────────────

def test_roundtrip_preserves_risk_level_and_mesh_unit(tmp_cache_dir):
    """The bug this module fixes: cached startup devices had risk_level
    force-reset to UNKNOWN and no mesh_unit, making every Network Map node
    render grey and some devices fall back to a flat gateway parent."""
    from modules.network_map_cache import load_render_cache, save_render_cache

    devices = [
        {"ip": "192.168.1.10", "mac": "aa:bb:cc:dd:ee:01", "risk_level": "HIGH",
         "device_type": "IP Camera", "mesh_unit": "Kitchen"},
        {"ip": "192.168.1.11", "mac": "aa:bb:cc:dd:ee:02", "risk_level": "CLEAN",
         "device_type": "Smart TV", "mesh_unit": ""},
    ]
    save_render_cache(
        devices=devices,
        gateway_ip="192.168.1.1",
        gateway_mac="aa:bb:cc:dd:ee:00",
        modem_data={"network_type": "5G NR"},
        edges=None,
    )

    cached = load_render_cache()
    assert cached is not None
    by_ip = {d["ip"]: d for d in cached["devices"]}
    assert by_ip["192.168.1.10"]["risk_level"] == "HIGH"
    assert by_ip["192.168.1.10"]["mesh_unit"] == "Kitchen"
    assert by_ip["192.168.1.11"]["risk_level"] == "CLEAN"
    assert cached["gateway_ip"] == "192.168.1.1"
    assert cached["gateway_mac"] == "aa:bb:cc:dd:ee:00"
    assert cached["modem_data"] == {"network_type": "5G NR"}


def test_roundtrip_with_dataclass_devices_and_edges(tmp_cache_dir):
    """Live scans pass DeviceInfo dataclass instances and TopologyEdge
    dataclass instances, not plain dicts — both must serialise cleanly."""
    from modules.network_map_cache import load_render_cache, save_render_cache
    from modules.rogue_device import DeviceInfo
    from modules.topology_layout import TopologyEdge

    devices = [
        DeviceInfo(ip="10.0.0.5", mac="11:22:33:44:55:66", risk_level="MEDIUM",
                   mesh_unit="Vardagsrum"),
    ]
    edges = [
        TopologyEdge(src_ip="10.0.0.1", dst_ip="10.0.0.5", latency_ms=12.5,
                     packet_loss=0.0, bandwidth_mbps=None, status="up"),
    ]
    save_render_cache(
        devices=devices, gateway_ip="10.0.0.1", gateway_mac=None,
        modem_data=None, edges=edges,
    )

    cached = load_render_cache()
    assert cached is not None
    assert cached["devices"][0]["risk_level"] == "MEDIUM"
    assert cached["devices"][0]["mesh_unit"] == "Vardagsrum"
    # Edges must be real TopologyEdge instances — topology_cytoscape.py reads
    # edge fields via direct attribute access (e.dst_ip), not dict.get().
    restored_edge = cached["edges"][0]
    assert isinstance(restored_edge, TopologyEdge)
    assert restored_edge.dst_ip == "10.0.0.5"
    assert restored_edge.latency_ms == 12.5


def test_load_missing_cache_returns_none(tmp_cache_dir):
    from modules.network_map_cache import load_render_cache
    assert load_render_cache() is None


def test_load_corrupt_cache_returns_none(tmp_cache_dir):
    from modules.network_map_cache import load_render_cache
    (tmp_cache_dir / "network_map_render_cache.json").write_text(
        "{not valid json", encoding="utf-8"
    )
    assert load_render_cache() is None


def test_load_empty_devices_returns_none(tmp_cache_dir):
    """An empty device list must not overwrite a real cache with a no-op
    render — load_render_cache returning None signals 'fall back to the
    existing reconstruction path' to the caller."""
    from modules.network_map_cache import load_render_cache
    (tmp_cache_dir / "network_map_render_cache.json").write_text(
        json.dumps({"devices": [], "gateway_ip": None, "gateway_mac": None,
                    "modem_data": None, "edges": []}),
        encoding="utf-8",
    )
    assert load_render_cache() is None


def test_save_handles_unwritable_dir_without_raising(tmp_path, monkeypatch):
    """save_render_cache must never raise — it is best-effort persistence."""
    from modules.network_map_cache import save_render_cache
    monkeypatch.setattr(
        "modules.network_map_cache.get_app_data_dir",
        lambda: tmp_path / "does" / "not" / "exist",
    )
    save_render_cache(
        devices=[{"ip": "1.2.3.4"}], gateway_ip=None, gateway_mac=None,
        modem_data=None, edges=None,
    )  # must not raise
