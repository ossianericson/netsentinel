"""
Regression tests for ui/topology_widget.py

Key scenario: mesh-only clients whose unit_name refers to the master node (not a
satellite) must appear in the rendered topology.  Before the fix they were silently
added to by_unit[master_name] which is never iterated during rendering.
"""
from __future__ import annotations

import pytest
from types import SimpleNamespace
from unittest.mock import patch

pytest.importorskip("PyQt6", reason="PyQt6 not installed")
pytest.importorskip("matplotlib", reason="matplotlib not installed")

import ui.topology_widget as tw
from ui.topology_widget import TopologyWidget


@pytest.fixture
def topology(qt_app):
    w = TopologyWidget()
    yield w
    try:
        w.deleteLater()
    except RuntimeError:
        pass  # already destroyed — safe to skip
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    if app:
        try:
            from PyQt6.QtCore import QCoreApplication, QEvent
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
        except Exception:
            pass  # non-fatal — best-effort cleanup
        for _ in range(3):
            app.processEvents()


def _make_mesh_setup():
    master = SimpleNamespace(role="master", name="Main", mac="aa:bb:cc:dd:ee:01")
    sat1   = SimpleNamespace(role="satellite", name="Sat-1", mac="aa:bb:cc:dd:ee:02")

    class _MC:
        mac       = "11:22:33:44:55:66"
        ip        = "192.168.1.50"
        name      = "MyPC"
        unit_name = "Main"   # connected to master, NOT a satellite

    mesh_enrichment = {"11:22:33:44:55:66": _MC()}
    # ARP scan did NOT discover local PC
    devices = [
        {"ip": "192.168.1.100", "mac": "bb:cc:dd:ee:ff:01",
         "hostname": "laptop", "risk_level": "CLEAN"},
    ]
    return master, sat1, mesh_enrichment, devices


def test_master_client_appears_in_unassigned(topology):
    """Mesh-only client on master node must be drawn (regression: was silently dropped)."""
    master, sat1, mesh_enrichment, devices = _make_mesh_setup()

    drawn_labels: list[str] = []
    original_scatter = tw._scatter

    def capturing_scatter(ax, pos, color, size, label, **kwargs):
        drawn_labels.append(label)
        original_scatter(ax, pos, color, size, label, **kwargs)

    with patch.object(tw, "_scatter", side_effect=capturing_scatter):
        topology.render(
            devices=devices,
            gateway_ip="192.168.1.1",
            mesh_units=[master, sat1],
            mesh_enrichment=mesh_enrichment,
        )

    assert any("MyPC" in lbl for lbl in drawn_labels), (
        "Mesh-only client connected to master node was not drawn. "
        "Fix: route master-connected mesh clients to unassigned pool."
    )


def test_node_clicked_emits_ip(topology):
    """Clicking on a device node emits node_clicked with the correct IP."""
    from unittest.mock import MagicMock
    devices = [
        {"ip": "192.168.1.10", "mac": "aa:bb:cc:dd:ee:01",
         "hostname": "mypc", "risk_level": "CLEAN"},
    ]
    topology.render(devices=devices, gateway_ip="192.168.1.1")

    # Device should be registered in _ip_map
    node_key = "aa:bb:cc:dd:ee:01"
    if node_key not in topology._pos_map:
        node_key = "192.168.1.10"
    assert node_key in topology._pos_map, "Device node missing from _pos_map after render"
    assert node_key in topology._ip_map,  "Device node missing from _ip_map after render"
    assert topology._ip_map[node_key] == "192.168.1.10"

    # Simulate a click exactly on the node (0 px offset)
    nx, ny = topology._pos_map[node_key]
    disp = topology._ax.transData.transform((nx, ny))

    emitted: list = []
    topology.node_clicked.connect(lambda ip: emitted.append(ip))

    event = MagicMock()
    event.button = 1
    event.inaxes = topology._ax
    event.xdata = nx
    event.ydata = ny
    event.x = float(disp[0])
    event.y = float(disp[1])

    topology._on_button_press(event)

    assert len(emitted) == 1, f"Expected node_clicked once, got: {emitted}"
    assert emitted[0] == "192.168.1.10"


def test_node_clicked_not_emitted_outside_axes(topology):
    """Click with inaxes=None never emits node_clicked."""
    from unittest.mock import MagicMock
    devices = [
        {"ip": "192.168.1.20", "mac": "bb:cc:dd:ee:ff:01",
         "hostname": "switch", "risk_level": "LOW"},
    ]
    topology.render(devices=devices, gateway_ip="192.168.1.1")

    emitted: list = []
    topology.node_clicked.connect(lambda ip: emitted.append(ip))

    event = MagicMock()
    event.button = 1
    event.inaxes = None

    topology._on_button_press(event)
    assert emitted == [], "No signal expected for out-of-axes click"


def test_pos_map_empty_before_render(topology):
    """_pos_map/_ip_map/_tooltip_map start empty and reset on clear()."""
    assert topology._pos_map == {}
    assert topology._ip_map == {}
    assert topology._tooltip_map == {}
    devices = [
        {"ip": "10.0.0.5", "mac": "cc:dd:ee:ff:00:01",
         "hostname": "cam", "risk_level": "MEDIUM"},
    ]
    topology.render(devices=devices, gateway_ip="10.0.0.1")
    assert topology._pos_map, "_pos_map should be populated after render"
    topology.clear()
    assert topology._pos_map == {}, "_pos_map should be empty after clear()"
    assert topology._ip_map == {}
    assert topology._hover_ann is None


def test_health_overlay_uses_satellite_parent_not_gateway(topology):
    """Edge health overlay lines for mesh clients must originate at their
    satellite parent, not the gateway (regression: after an app restart plus
    rescan, the Classic view drew colour-coded latency lines straight from the
    gateway to every mesh client, criss-crossing through the satellite nodes
    instead of following the same branch as the grey base tree)."""
    from modules.topology_layout import TopologyEdge

    master = SimpleNamespace(role="master", name="Main", mac="aa:bb:cc:dd:ee:01")
    sat1   = SimpleNamespace(role="satellite", name="Sat-1", mac="aa:bb:cc:dd:ee:02")

    devices = [
        {"ip": "192.168.1.60", "mac": "22:33:44:55:66:77",
         "hostname": "TabletOnSat", "risk_level": "CLEAN", "mesh_unit": "Sat-1"},
    ]
    edges = [TopologyEdge(
        src_ip="192.168.1.1", dst_ip="192.168.1.60",
        latency_ms=12.0, packet_loss=0.0, bandwidth_mbps=None, status="up",
    )]

    topology.render(
        devices=devices,
        gateway_ip="192.168.1.1",
        mesh_units=[master, sat1],
        edges=edges,
    )

    node_key = "22:33:44:55:66:77"
    assert node_key in topology._parent_pos, "Client missing from _parent_pos map"
    # Single satellite → deterministic position per _render_mesh's layout constants.
    assert topology._parent_pos[node_key] == (0.5, 0.42), (
        "Mesh client's overlay parent must be its satellite position"
    )
    assert topology._parent_pos[node_key] != topology._gw_pos, (
        "Mesh client's overlay parent must NOT be the gateway position"
    )


def test_satellite_client_still_groups_under_satellite(topology):
    """Mesh-only client on a satellite must still appear under that satellite."""
    master = SimpleNamespace(role="master", name="Main", mac="aa:bb:cc:dd:ee:01")
    sat1   = SimpleNamespace(role="satellite", name="Sat-1", mac="aa:bb:cc:dd:ee:02")

    class _MC:
        mac       = "22:33:44:55:66:77"
        ip        = "192.168.1.60"
        name      = "TabletOnSat"
        unit_name = "Sat-1"   # on a satellite

    mesh_enrichment = {"22:33:44:55:66:77": _MC()}
    # Must include at least one ARP device or render() exits early before mesh path
    devices = [
        {"ip": "192.168.1.10", "mac": "ff:ee:dd:cc:bb:01",
         "hostname": "laptop", "risk_level": "CLEAN"},
    ]

    drawn_labels: list[str] = []
    original_scatter = tw._scatter

    def capturing_scatter(ax, pos, color, size, label, **kwargs):
        drawn_labels.append(label)
        original_scatter(ax, pos, color, size, label, **kwargs)

    with patch.object(tw, "_scatter", side_effect=capturing_scatter):
        topology.render(
            devices=devices,
            gateway_ip="192.168.1.1",
            mesh_units=[master, sat1],
            mesh_enrichment=mesh_enrichment,
        )

    assert any("TabletOnSat" in lbl for lbl in drawn_labels), (
        "Mesh-only client on satellite was not drawn."
    )
