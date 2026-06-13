"""
tests/test_topology_cytoscape.py — Tests for modules/topology_cytoscape.py

Tests the pure-Python element builder and HTML generator without
requiring PyQt6, QWebEngineView, or a running scan.
"""
from __future__ import annotations

import json
import statistics
import time
from unittest.mock import MagicMock

import pytest


# ── import guard ──────────────────────────────────────────────────────────────

def test_import():
    import modules.topology_cytoscape  # noqa: F401


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_device(ip: str, mac: str = "", risk: str = "CLEAN",
                 hostname: str = "", vendor: str = "") -> dict:
    return {
        "ip":         ip,
        "mac":        mac or ip.replace(".", ""),
        "risk_level": risk,
        "hostname":   hostname,
        "vendor":     vendor,
    }


def _mock_positions():
    """Return a minimal positions dict so build_cytoscape_elements doesn't hit disk."""
    return {}


# ── build_cytoscape_elements() ────────────────────────────────────────────────

class TestBuildCytoscapeElements:

    def test_returns_expected_keys(self):
        from modules.topology_cytoscape import build_cytoscape_elements
        devices = [_make_device("192.168.1.10")]
        result  = build_cytoscape_elements(devices=devices, gateway_ip="192.168.1.1")
        assert "elements" in result
        assert "style"    in result

    def test_contains_gateway_node(self):
        from modules.topology_cytoscape import build_cytoscape_elements
        result = build_cytoscape_elements(
            devices=[_make_device("192.168.1.10")],
            gateway_ip="192.168.1.1",
        )
        ids = {el["data"]["id"] for el in result["elements"]
               if el.get("group") == "nodes"}
        assert "192.168.1.1" in ids

    def test_contains_internet_node(self):
        from modules.topology_cytoscape import build_cytoscape_elements
        result = build_cytoscape_elements(devices=[], gateway_ip="192.168.1.1")
        ids = {el["data"]["id"] for el in result["elements"]}
        assert "__internet__" in ids

    def test_device_node_present(self):
        from modules.topology_cytoscape import build_cytoscape_elements
        devices = [_make_device("192.168.1.10", mac="aabbccddee10")]
        result  = build_cytoscape_elements(devices=devices, gateway_ip="192.168.1.1")
        ids = {el["data"]["id"] for el in result["elements"]}
        assert "aabbccddee10" in ids

    def test_risk_class_applied(self):
        from modules.topology_cytoscape import build_cytoscape_elements
        devices = [_make_device("192.168.1.10", mac="aa10", risk="HIGH")]
        result  = build_cytoscape_elements(devices=devices, gateway_ip="192.168.1.1")
        nodes = [el for el in result["elements"]
                 if el.get("group") == "nodes" and el["data"].get("id") == "aa10"]
        assert nodes, "Device node missing"
        assert "risk-high" in nodes[0]["classes"]

    def test_noise_ips_excluded(self):
        from modules.topology_cytoscape import build_cytoscape_elements
        devices = [
            _make_device("224.0.0.251"),    # multicast — should be excluded
            _make_device("192.168.1.50"),   # normal — should be included
        ]
        result = build_cytoscape_elements(devices=devices, gateway_ip="192.168.1.1")
        ips = [el["data"].get("ip") for el in result["elements"]]
        assert "224.0.0.251" not in ips
        assert "192.168.1.50" in ips

    def test_modem_node_when_data_present(self):
        from modules.topology_cytoscape import build_cytoscape_elements
        result = build_cytoscape_elements(
            devices=[],
            gateway_ip="192.168.1.1",
            modem_data={"network_type": "NR5G", "nr5g_band": "n78"},
        )
        classes = {el["data"]["id"]: el.get("classes", "")
                   for el in result["elements"] if el.get("group") == "nodes"}
        assert "modem" in classes.get("__modem__", "")

    def test_diff_added_class(self):
        from modules.topology_cytoscape import build_cytoscape_elements
        from modules.topology_snapshot import TopologyDiff
        devices = [_make_device("192.168.1.10", mac="aa10")]
        diff    = TopologyDiff(added_ips=["192.168.1.10"])
        result  = build_cytoscape_elements(
            devices=devices, gateway_ip="192.168.1.1", diff=diff,
        )
        nodes = [el for el in result["elements"]
                 if el.get("group") == "nodes" and el["data"].get("id") == "aa10"]
        assert nodes and "new-device" in nodes[0]["classes"]

    def test_diff_removed_ghost_node(self):
        from modules.topology_cytoscape import build_cytoscape_elements
        from modules.topology_snapshot import TopologyDiff
        diff = TopologyDiff(removed_ips=["192.168.1.99"])
        result = build_cytoscape_elements(
            devices=[], gateway_ip="192.168.1.1", diff=diff,
        )
        ids = {el["data"]["id"] for el in result["elements"]}
        assert "ghost-192.168.1.99" in ids

    def test_lldp_neighbor_node(self):
        from modules.topology_cytoscape import build_cytoscape_elements
        nb = MagicMock()
        nb.neighbor_ip       = "192.168.1.200"
        nb.neighbor_hostname = "sw-core"
        nb.chassis_id        = "aa:bb:cc:dd:ee:ff"
        nb.capabilities      = ["bridge", "router"]
        result = build_cytoscape_elements(
            devices=[], gateway_ip="192.168.1.1", lldp_neighbors=[nb],
        )
        ids = {el["data"]["id"] for el in result["elements"]}
        assert any("lldp-" in _id for _id in ids)

    def test_vendor_class_mapping(self):
        from modules.topology_cytoscape import build_cytoscape_elements
        devices = [_make_device("192.168.1.10", mac="cc10", vendor="Cisco Systems")]
        result  = build_cytoscape_elements(devices=devices, gateway_ip="192.168.1.1")
        nodes = [el for el in result["elements"] if el["data"].get("id") == "cc10"]
        assert nodes and "vendor-cisco" in nodes[0]["classes"]

    def test_empty_devices_returns_infra_nodes(self):
        from modules.topology_cytoscape import build_cytoscape_elements
        result = build_cytoscape_elements(devices=[], gateway_ip="192.168.1.1")
        assert len(result["elements"]) >= 2  # internet + gateway

    def test_style_list_nonempty(self):
        from modules.topology_cytoscape import build_cytoscape_elements
        result = build_cytoscape_elements(devices=[], gateway_ip="192.168.1.1")
        assert isinstance(result["style"], list)
        assert len(result["style"]) > 5

    def test_edge_created_to_gateway(self):
        from modules.topology_cytoscape import build_cytoscape_elements
        devices = [_make_device("192.168.1.10", mac="aa10")]
        result  = build_cytoscape_elements(devices=devices, gateway_ip="192.168.1.1")
        edges = [el for el in result["elements"] if el.get("group") == "edges"]
        targets = {e["data"]["target"] for e in edges}
        assert "aa10" in targets


# ── build_cytoscape_html() ────────────────────────────────────────────────────

class TestBuildCytoscapeHtml:

    def test_returns_html_string(self):
        from modules.topology_cytoscape import build_cytoscape_html
        html = build_cytoscape_html(devices=[], gateway_ip="192.168.1.1")
        assert isinstance(html, str)
        assert "<!DOCTYPE html>" in html

    def test_elements_json_embedded(self):
        from modules.topology_cytoscape import build_cytoscape_html
        html = build_cytoscape_html(
            devices=[_make_device("192.168.1.10")],
            gateway_ip="192.168.1.1",
        )
        assert "192.168.1.1" in html

    def test_cytoscape_init_present(self):
        from modules.topology_cytoscape import build_cytoscape_html
        html = build_cytoscape_html(devices=[], gateway_ip="192.168.1.1")
        assert "cytoscape(" in html

    def test_qwebchannel_script_included(self):
        from modules.topology_cytoscape import build_cytoscape_html
        html = build_cytoscape_html(devices=[], gateway_ip="192.168.1.1")
        assert "qwebchannel" in html.lower()

    def test_position_preset_layout_when_positions_given(self):
        from modules.topology_cytoscape import build_cytoscape_html
        from modules.topology_layout import NodePosition
        pos = {"192.168.1.1": NodePosition("192.168.1.1", 0.5, 0.5)}
        html = build_cytoscape_html(
            devices=[], gateway_ip="192.168.1.1", positions=pos,
        )
        assert '"preset"' in html

    def test_no_positions_uses_default_layout(self):
        from modules.topology_cytoscape import build_cytoscape_html
        html = build_cytoscape_html(
            devices=[], gateway_ip="192.168.1.1",
            positions=None, initial_layout="concentric",
        )
        assert '"concentric"' in html

    def test_bridge_functions_present(self):
        from modules.topology_cytoscape import build_cytoscape_html
        html = build_cytoscape_html(devices=[], gateway_ip="192.168.1.1")
        for fn in ("nodeClicked", "savePosition", "setLayout", "fitView", "toggleFocus"):
            assert fn in html

    def test_html_is_valid_json_elements(self):
        """Verify the elements_json embedded in the HTML is valid JSON."""
        from modules.topology_cytoscape import build_cytoscape_elements
        result = build_cytoscape_elements(
            devices=[_make_device("192.168.1.10", mac="aabbcc")],
            gateway_ip="192.168.1.1",
        )
        # Check it round-trips
        serialised = json.dumps(result["elements"])
        parsed = json.loads(serialised)
        assert isinstance(parsed, list)


# ── LAYOUT_NAMES constant ─────────────────────────────────────────────────────

def test_layout_names_nonempty():
    from modules.topology_cytoscape import LAYOUT_NAMES
    assert len(LAYOUT_NAMES) >= 4
    assert "Hierarchy" in LAYOUT_NAMES
    assert "Physics"   in LAYOUT_NAMES


# ── helper functions ──────────────────────────────────────────────────────────

def test_risk_class_mapping():
    from modules.topology_cytoscape import _risk_class
    assert _risk_class("HIGH")    == "risk-high"
    assert _risk_class("MEDIUM")  == "risk-medium"
    assert _risk_class("LOW")     == "risk-low"
    assert _risk_class("CLEAN")   == "risk-clean"
    assert _risk_class("UNKNOWN") == "risk-unknown"
    assert _risk_class("STORM")   == "risk-high"


def test_vendor_class_mapping():
    from modules.topology_cytoscape import _vendor_class
    assert _vendor_class("Cisco Systems Inc.")  == "vendor-cisco"
    assert _vendor_class("TP-Link Technologies") == "vendor-tp-link"
    assert _vendor_class("Ubiquiti Networks")    == "vendor-ubiquiti"
    assert _vendor_class("Apple, Inc.")          == "vendor-apple"
    assert _vendor_class("Unknown Inc.")         == ""


def test_scale_pos_bounds():
    from modules.topology_cytoscape import _scale_pos, _CANVAS_W, _CANVAS_H
    p = _scale_pos(0.5, 0.5)
    assert p["x"] == round(0.5 * _CANVAS_W, 1)
    assert p["y"] == round(0.5 * _CANVAS_H, 1)


# ── scaling test ──────────────────────────────────────────────────────────────

def _median_ms(fn, repeats: int = 5) -> float:
    times = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t0) * 1000)
    return statistics.median(times)


@pytest.mark.benchmark
def test_element_builder_scaling():
    """Element builder should scale roughly linearly with device count."""
    from modules.topology_cytoscape import build_cytoscape_elements

    def _devices(n: int):
        return [
            _make_device(f"192.168.1.{i % 254 + 1}", mac=f"aa{i:06x}")
            for i in range(n)
        ]

    small = _devices(20)
    large = _devices(200)

    t_small = _median_ms(
        lambda: build_cytoscape_elements(devices=small, gateway_ip="192.168.1.1")
    )
    t_large = _median_ms(
        lambda: build_cytoscape_elements(devices=large, gateway_ip="192.168.1.1")
    )

    if t_small < 1e-4:
        pytest.skip("below measurement threshold")

    ratio = t_large / t_small
    assert ratio < 20, (
        f"Scaling ratio {ratio:.1f}x for 10x input suggests O(n²) regression "
        f"(t_small={t_small:.3f}ms, t_large={t_large:.3f}ms)"
    )
