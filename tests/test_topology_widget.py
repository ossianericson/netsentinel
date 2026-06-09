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

    def capturing_scatter(ax, pos, color, size, label):
        drawn_labels.append(label)
        original_scatter(ax, pos, color, size, label)

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

    def capturing_scatter(ax, pos, color, size, label):
        drawn_labels.append(label)
        original_scatter(ax, pos, color, size, label)

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
