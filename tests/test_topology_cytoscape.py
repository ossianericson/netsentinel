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
    from modules.topology_cytoscape import build_cytoscape_elements
    assert build_cytoscape_elements is not None


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
        from modules.topology_cytoscape_html import build_cytoscape_html
        html = build_cytoscape_html(devices=[], gateway_ip="192.168.1.1")
        assert isinstance(html, str)
        assert "<!DOCTYPE html>" in html

    def test_elements_json_embedded(self):
        from modules.topology_cytoscape_html import build_cytoscape_html
        html = build_cytoscape_html(
            devices=[_make_device("192.168.1.10")],
            gateway_ip="192.168.1.1",
        )
        assert "192.168.1.1" in html

    def test_cytoscape_init_present(self):
        from modules.topology_cytoscape_html import build_cytoscape_html
        html = build_cytoscape_html(devices=[], gateway_ip="192.168.1.1")
        assert "cytoscape(" in html

    def test_qwebchannel_script_included(self):
        from modules.topology_cytoscape_html import build_cytoscape_html
        html = build_cytoscape_html(devices=[], gateway_ip="192.168.1.1")
        assert "qwebchannel" in html.lower()

    def test_position_preset_layout_when_positions_given(self):
        from modules.topology_cytoscape_html import build_cytoscape_html
        from modules.topology_layout import NodePosition
        pos = {"192.168.1.1": NodePosition("192.168.1.1", 0.5, 0.5)}
        html = build_cytoscape_html(
            devices=[], gateway_ip="192.168.1.1", positions=pos,
        )
        assert '"preset"' in html

    def test_no_positions_uses_default_layout(self):
        from modules.topology_cytoscape_html import build_cytoscape_html
        html = build_cytoscape_html(
            devices=[], gateway_ip="192.168.1.1",
            positions=None, initial_layout="concentric",
        )
        assert '"concentric"' in html

    def test_bridge_functions_present(self):
        from modules.topology_cytoscape_html import build_cytoscape_html
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


# ── mesh edge routing regression tests ───────────────────────────────────────
# These guard against the bug where edge IDs always used gw_id instead of the
# actual src_id, preventing incremental updateTopology() from rewiring clients
# from the flat gateway edge to their satellite parent node.

class TestMeshEdgeRouting:

    def _make_units(self):
        from types import SimpleNamespace
        master = SimpleNamespace(name="MasterDeco", role="master", mac="aa:bb:cc:00:00:01")
        sat    = SimpleNamespace(name="SatDeco",    role="slave",  mac="aa:bb:cc:00:00:02")
        return [master, sat]

    def test_flat_device_edge_uses_gateway_id(self):
        """Without mesh data, edge source and edge ID both reference the gateway.
        Gateway Cytoscape node ID is always the IP (not MAC) per gw_id=gateway_ip."""
        from modules.topology_cytoscape import build_cytoscape_elements
        devices = [_make_device("192.168.1.100", mac="aa:bb:cc:00:01:00")]
        result  = build_cytoscape_elements(
            devices=devices,
            gateway_ip="192.168.1.1",
            gateway_mac="aa:bb:cc:00:00:01",
        )
        edges = [e for e in result["elements"] if e.get("group") == "edges"]
        client_edge = next(
            (e for e in edges if e["data"].get("target") == "aa:bb:cc:00:01:00"), None
        )
        assert client_edge is not None, "Client node has no edge"
        gw_id = "192.168.1.1"  # gw_id = gateway_ip in topology_cytoscape.py
        assert client_edge["data"]["source"] == gw_id
        assert client_edge["data"]["id"] == f"e-{gw_id}-aa:bb:cc:00:01:00"

    def test_mesh_client_edge_source_is_satellite(self):
        """Mesh client must have an edge from its satellite node, not the gateway.
        The edge ID must encode the satellite so window.updateTopology() can rewire."""
        from modules.topology_cytoscape import build_cytoscape_elements
        devices = [{
            "ip":         "192.168.1.100",
            "mac":        "aa:bb:cc:00:01:00",
            "hostname":   "my-phone",
            "risk_level": "CLEAN",
            "mesh_unit":  "SatDeco",
        }]
        result = build_cytoscape_elements(
            devices=devices,
            gateway_ip="192.168.1.1",
            gateway_mac="aa:bb:cc:00:00:01",
            mesh_units=self._make_units(),
        )
        edges = [e for e in result["elements"] if e.get("group") == "edges"]
        client_edge = next(
            (e for e in edges if e["data"].get("target") == "aa:bb:cc:00:01:00"), None
        )
        assert client_edge is not None, "Mesh client has no edge"
        sat_id = "aa:bb:cc:00:00:02"
        assert client_edge["data"]["source"] == sat_id, (
            f"Expected source={sat_id!r}, got {client_edge['data']['source']!r}"
        )
        assert client_edge["data"]["id"] == f"e-{sat_id}-aa:bb:cc:00:01:00", (
            "Edge ID must encode the actual source node for incremental rewiring"
        )

    def test_mesh_edge_id_differs_from_flat_edge_id(self):
        """The satellite-edge ID must differ from the flat-edge ID so that
        window.updateTopology() removes the old flat edge and inserts the new one.
        Cytoscape edges are source/target-immutable; only ID removal/re-add works."""
        from modules.topology_cytoscape import build_cytoscape_elements
        dev_mac = "aa:bb:cc:00:01:00"
        gw_mac  = "aa:bb:cc:00:00:01"

        flat_result = build_cytoscape_elements(
            devices=[_make_device("192.168.1.100", mac=dev_mac)],
            gateway_ip="192.168.1.1", gateway_mac=gw_mac,
        )
        mesh_result = build_cytoscape_elements(
            devices=[{"ip": "192.168.1.100", "mac": dev_mac, "risk_level": "CLEAN",
                      "hostname": "", "vendor": "", "mesh_unit": "SatDeco"}],
            gateway_ip="192.168.1.1", gateway_mac=gw_mac,
            mesh_units=self._make_units(),
        )

        def _client_edge_id(res):
            for e in res["elements"]:
                if e.get("group") == "edges" and e["data"].get("target") == dev_mac:
                    return e["data"]["id"]
            return None

        flat_id = _client_edge_id(flat_result)
        mesh_id = _client_edge_id(mesh_result)
        assert flat_id is not None, "Flat result has no client edge"
        assert mesh_id is not None, "Mesh result has no client edge"
        assert flat_id != mesh_id, (
            f"Flat edge ID {flat_id!r} must differ from mesh edge ID {mesh_id!r} "
            "so incremental updateTopology() can swap them"
        )

    def test_unassigned_device_stays_on_gateway(self):
        """Devices with no mesh_unit remain connected to the gateway even in mesh mode."""
        from modules.topology_cytoscape import build_cytoscape_elements
        devices = [{"ip": "192.168.1.50", "mac": "aa:bb:cc:00:02:00",
                    "hostname": "", "risk_level": "CLEAN", "mesh_unit": ""}]
        result = build_cytoscape_elements(
            devices=devices,
            gateway_ip="192.168.1.1",
            gateway_mac="aa:bb:cc:00:00:01",
            mesh_units=self._make_units(),
        )
        edges = [e for e in result["elements"] if e.get("group") == "edges"]
        client_edge = next(
            (e for e in edges if e["data"].get("target") == "aa:bb:cc:00:02:00"), None
        )
        assert client_edge is not None, "Unassigned device has no edge"
        assert client_edge["data"]["source"] == "192.168.1.1", (
            "Unassigned device must stay connected to gateway (gw_id = gateway_ip)"
        )


# ── synthesize_mesh_only_clients() ────────────────────────────────────────────
# Part A fix: a mesh Wi-Fi client (e.g. the scanning PC itself) never answers
# ARP, so it is absent from `devices` but present in `mesh_enrichment`. Both
# map builders must consume the same synthesized stub list so they can never
# show a different device set (mirrors the Classic proof in
# tests/test_topology_widget.py:41-82).

class TestSynthesizeMeshOnlyClients:

    def _make_units(self):
        from types import SimpleNamespace
        master = SimpleNamespace(name="MasterDeco", role="master", mac="aa:bb:cc:00:00:01")
        sat    = SimpleNamespace(name="SatDeco",    role="slave",  mac="aa:bb:cc:00:00:02")
        return [master, sat]

    def _mesh_client(self, mac, ip, name, unit_name):
        from types import SimpleNamespace
        return SimpleNamespace(mac=mac, ip=ip, name=name, unit_name=unit_name)

    def test_mesh_only_client_is_appended(self):
        from modules.topology_cytoscape import synthesize_mesh_only_clients
        devices = [_make_device("192.168.1.100", mac="bb:cc:dd:ee:ff:01")]
        mesh_enrichment = {
            "11:22:33:44:55:66": self._mesh_client(
                "11:22:33:44:55:66", "192.168.1.50", "MyPC", "SatDeco"
            ),
        }
        out = synthesize_mesh_only_clients(devices, mesh_enrichment, self._make_units())
        stub = next(
            (d for d in out if isinstance(d, dict) and d.get("mac") == "11:22:33:44:55:66"),
            None,
        )
        assert stub is not None, "Mesh-only client was not synthesized"
        assert stub["hostname"] == "MyPC"
        assert stub["mesh_unit"] == "SatDeco"

    def test_already_covered_mac_not_duplicated(self):
        from modules.topology_cytoscape import synthesize_mesh_only_clients
        devices = [_make_device("192.168.1.50", mac="11:22:33:44:55:66")]
        mesh_enrichment = {
            "11:22:33:44:55:66": self._mesh_client(
                "11:22:33:44:55:66", "192.168.1.50", "MyPC", "SatDeco"
            ),
        }
        out = synthesize_mesh_only_clients(devices, mesh_enrichment, self._make_units())
        assert len(out) == 1, "ARP-visible device must not get a duplicate stub"

    def test_infra_mac_not_synthesized_as_client(self):
        """A mesh unit's own MAC appearing in mesh_enrichment (satellite
        reporting itself) must never become a synthesized client node."""
        from modules.topology_cytoscape import synthesize_mesh_only_clients
        devices = [_make_device("192.168.1.100", mac="bb:cc:dd:ee:ff:01")]
        mesh_enrichment = {
            "aa:bb:cc:00:00:02": self._mesh_client(
                "aa:bb:cc:00:00:02", "192.168.1.2", "SatDeco", "SatDeco"
            ),
        }
        out = synthesize_mesh_only_clients(devices, mesh_enrichment, self._make_units())
        assert len(out) == 1

    def test_returns_input_unchanged_without_mesh_data(self):
        from modules.topology_cytoscape import synthesize_mesh_only_clients
        devices = [_make_device("192.168.1.100", mac="bb:cc:dd:ee:ff:01")]
        assert synthesize_mesh_only_clients(devices, {}, []) is devices
        assert synthesize_mesh_only_clients(devices, None, None) is devices
        assert synthesize_mesh_only_clients(devices, {"x": object()}, None) is devices


class TestSynthesizedClientFeedsCytoscapeElements:
    """Confirms the augmented list produced by synthesize_mesh_only_clients()
    flows correctly through build_cytoscape_elements(): a real node + an edge
    to the correct satellite parent, exactly like an ARP-discovered device."""

    def test_mesh_only_client_becomes_node_with_satellite_edge(self):
        from modules.topology_cytoscape import (
            build_cytoscape_elements,
            synthesize_mesh_only_clients,
        )
        from types import SimpleNamespace

        master = SimpleNamespace(name="MasterDeco", role="master", mac="aa:bb:cc:00:00:01")
        sat    = SimpleNamespace(name="SatDeco",    role="slave",  mac="aa:bb:cc:00:00:02")
        mesh_units = [master, sat]
        mc = SimpleNamespace(mac="11:22:33:44:55:66", ip="192.168.1.50",
                              name="MyPC", unit_name="SatDeco")
        mesh_enrichment = {"11:22:33:44:55:66": mc}
        devices = [_make_device("192.168.1.100", mac="bb:cc:dd:ee:ff:01")]

        augmented = synthesize_mesh_only_clients(devices, mesh_enrichment, mesh_units)
        result = build_cytoscape_elements(
            devices=augmented,
            gateway_ip="192.168.1.1",
            gateway_mac="aa:bb:cc:00:00:01",
            mesh_units=mesh_units,
            mesh_enrichment=mesh_enrichment,
        )

        node_ids = {el["data"]["id"] for el in result["elements"] if el.get("group") == "nodes"}
        assert "11:22:33:44:55:66" in node_ids, "Mesh-only client is missing a node"

        edges = [el for el in result["elements"] if el.get("group") == "edges"]
        client_edge = next(
            (e for e in edges if e["data"].get("target") == "11:22:33:44:55:66"), None
        )
        assert client_edge is not None, "Mesh-only client has no edge"
        assert client_edge["data"]["source"] == "aa:bb:cc:00:00:02", (
            "Mesh-only client must attach to its satellite, not the gateway"
        )
