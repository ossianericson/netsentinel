"""
Regression tests for ui/pages/network_map_page.py

Bug: scan results, mesh enrichment, and LLDP data each reach the interactive
Cytoscape view via separate NetworkMapPage.render() calls, with no guaranteed
ordering between them. Whichever group of nodes is rendered first gets the
full Python geo_hierarchy (etc.) layout; whichever lands later was, before
this fix, applied via the incremental update path (window.updateTopology()),
which only spirals the *new* node ids in around the gateway via JS — it never
re-runs the Python hierarchy algorithm. So devices were left mis-parented
directly under the gateway instead of nested under their real mesh node,
regardless of whether mesh data arrived before or after the device list. The
Classic (matplotlib) view was unaffected because it always fully redraws from
the current data on every render() call.

A single direct reapplication of the current layout mode right after the
incremental update was NOT enough in practice (confirmed against a live scan
with TP-Link Deco mesh nodes) — only manually switching the Layout dropdown
to a different mode and back reliably fixed the positions. So the fix
automates exactly that action: NetworkMapPage tracks the node ids present in
the live graph (_known_node_ids); any incremental update introducing ids
outside that set applies a different geo_ layout first, then the original
one a moment later via _cycle_geometric_layout(), reproducing the manual
away-then-back sequence instead of a single resync call.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("PyQt6", reason="PyQt6 not installed")

from PyQt6.QtTest import QTest

from ui.pages.network_map_page import NetworkMapPage


@pytest.fixture
def page(qt_app):
    p = NetworkMapPage()
    # Simulate an available interactive view without a real QWebEngineView —
    # the production setHtml()/runJavaScript() calls are not under test here.
    p._web_available = True
    p._web_view = MagicMock()
    p._layout_combo.setCurrentText("Hierarchy")
    yield p
    try:
        p.deleteLater()
    except RuntimeError:
        pass  # already destroyed — safe to skip
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


def _devices():
    return [
        {"ip": "192.168.68.51", "mac": "aa:bb:cc:dd:ee:01",
         "hostname": "Chromecast-Audio", "risk_level": "CLEAN"},
        {"ip": "192.168.68.60", "mac": "aa:bb:cc:dd:ee:02",
         "hostname": "iPhone", "risk_level": "CLEAN"},
    ]


def _mesh_units():
    return [
        SimpleNamespace(role="master", name="Kontor", mac="aa:bb:cc:dd:ee:f0"),
        SimpleNamespace(role="satellite", name="Kitchen", mac="aa:bb:cc:dd:ee:f1"),
    ]


def _wait_for_cycle(timeout_ms: int = 600) -> None:
    """Pump the Qt event loop long enough for _cycle_geometric_layout's
    deferred QTimer (250ms) to fire."""
    QTest.qWait(timeout_ms)


def test_mesh_arriving_after_devices_cycles_layout_away_and_back(page, monkeypatch):
    """Order A: scan devices render first, mesh enrichment lands a beat later."""
    apply_calls = []
    monkeypatch.setattr(page, "_apply_geometric_layout", lambda mode: apply_calls.append(mode))

    page.render(devices=_devices(), gateway_ip="192.168.68.1")
    assert page._topology_loaded is True
    assert apply_calls == []

    # Mesh enrichment lands — these node ids are new to the graph.
    page.render(
        devices=_devices(),
        gateway_ip="192.168.68.1",
        mesh_units=_mesh_units(),
        mesh_enrichment={},
    )
    _wait_for_cycle()
    assert apply_calls == ["geo_radial", "geo_hierarchy"]

    # Steady-state refresh with the same nodes must NOT re-trigger the cycle
    # (would discard any positions the user dragged in the meantime).
    apply_calls.clear()
    page.render(
        devices=_devices(),
        gateway_ip="192.168.68.1",
        mesh_units=_mesh_units(),
        mesh_enrichment={},
    )
    _wait_for_cycle()
    assert apply_calls == []


def test_devices_arriving_after_mesh_cycles_layout_away_and_back(page, monkeypatch):
    """Order B (the reported live-app failure): mesh nodes render first, sparse
    and clustered with no children yet; the real device list shows up a beat
    later as an incremental "add" and was spiraled flat around the gateway
    instead of being nested under its mesh parent."""
    apply_calls = []
    monkeypatch.setattr(page, "_apply_geometric_layout", lambda mode: apply_calls.append(mode))

    page.render(devices=[], gateway_ip="192.168.68.1", mesh_units=_mesh_units(), mesh_enrichment={})
    assert page._topology_loaded is True
    assert apply_calls == []

    # Real ARP-scanned devices arrive afterward — new node ids relative to the
    # mesh-only graph built above.
    page.render(
        devices=_devices(),
        gateway_ip="192.168.68.1",
        mesh_units=_mesh_units(),
        mesh_enrichment={},
    )
    _wait_for_cycle()
    assert apply_calls == ["geo_radial", "geo_hierarchy"]


def test_mesh_present_from_first_render_does_not_cycle(page, monkeypatch):
    apply_calls = []
    monkeypatch.setattr(page, "_apply_geometric_layout", lambda mode: apply_calls.append(mode))

    # Cold-start render already includes mesh data (e.g. cached snapshot) —
    # the full HTML build already bakes mesh into the layout, so no separate
    # cycle should ever be needed.
    page.render(
        devices=_devices(),
        gateway_ip="192.168.68.1",
        mesh_units=_mesh_units(),
        mesh_enrichment={},
    )
    _wait_for_cycle()
    assert apply_calls == []

    page.render(
        devices=_devices(),
        gateway_ip="192.168.68.1",
        mesh_units=_mesh_units(),
        mesh_enrichment={},
    )
    _wait_for_cycle()
    assert apply_calls == []


def test_pure_data_refresh_does_not_cycle(page, monkeypatch):
    """Re-rendering the exact same node set (e.g. an RTT/label-only refresh)
    must not discard user-dragged positions with an unsolicited layout cycle."""
    apply_calls = []
    monkeypatch.setattr(page, "_apply_geometric_layout", lambda mode: apply_calls.append(mode))

    page.render(devices=_devices(), gateway_ip="192.168.68.1")
    page.render(devices=_devices(), gateway_ip="192.168.68.1")
    _wait_for_cycle()
    assert apply_calls == []


def test_reset_layout_clears_known_node_ids_before_rebuilding(page, monkeypatch):
    apply_calls = []
    monkeypatch.setattr(page, "_apply_geometric_layout", lambda mode: apply_calls.append(mode))
    page.render(
        devices=_devices(),
        gateway_ip="192.168.68.1",
        mesh_units=_mesh_units(),
        mesh_enrichment={},
    )
    assert page._known_node_ids

    # Reset Layout clears tracked node ids, then immediately re-renders from
    # the last known kwargs — the rebuilt HTML bakes mesh data in directly (no
    # incremental update involved), so no separate layout cycle fires.
    page.reset_layout()
    _wait_for_cycle()
    assert page._topology_loaded is True
    assert page._known_node_ids
    assert apply_calls == []


def test_cycle_geometric_layout_applies_other_mode_then_original(page, monkeypatch):
    """Unit-level check of the helper itself: it must call _apply_geometric_layout
    with a *different* geo_ mode immediately, then the requested mode shortly after —
    not the same mode twice, and not the requested mode first."""
    apply_calls = []
    monkeypatch.setattr(page, "_apply_geometric_layout", lambda mode: apply_calls.append(mode))

    page._cycle_geometric_layout("geo_hierarchy")
    assert apply_calls == ["geo_radial"]  # immediate "away" call only, so far

    _wait_for_cycle()
    assert apply_calls == ["geo_radial", "geo_hierarchy"]
