"""Tests for modules/topology_cytoscape_html.py.

Covers the HTML/JS page builder that was split from topology_cytoscape.py
(RULE-AH1 LOC budget split).
"""
from __future__ import annotations

import json


def test_import():
    """Module imports without error."""
    from modules import topology_cytoscape_html as m  # noqa: F401


def test_build_cytoscape_html_returns_html():
    """build_cytoscape_html returns a non-empty HTML string."""
    from modules.topology_cytoscape_html import build_cytoscape_html

    devices = [{"ip": "192.168.1.10", "mac": "aa:bb:cc:dd:ee:01", "hostname": "laptop"}]
    html = build_cytoscape_html(devices, gateway_ip="192.168.1.1")

    assert isinstance(html, str)
    assert "<!DOCTYPE html>" in html
    assert "<div id=\"cy\"></div>" in html


def test_build_cytoscape_html_embeds_elements():
    """Returned HTML embeds a JSON-encoded element list."""
    from modules.topology_cytoscape_html import build_cytoscape_html

    devices = [{"ip": "10.0.0.5", "mac": "11:22:33:44:55:66", "hostname": "server"}]
    html = build_cytoscape_html(devices, gateway_ip="10.0.0.1")

    # The elements array is embedded as JSON in the JS; verify the IP appears
    assert "10.0.0.5" in html
    assert "10.0.0.1" in html


def test_build_cytoscape_html_uses_preset_when_positions_given():
    """Layout is 'preset' when saved positions are provided, algorithm otherwise."""
    from modules.topology_cytoscape_html import build_cytoscape_html
    from modules.topology_layout import NodePosition

    devices = [{"ip": "192.168.1.5", "mac": "aa:bb:cc:00:00:01"}]

    html_no_pos  = build_cytoscape_html(devices, initial_layout="cose")
    html_with_pos = build_cytoscape_html(
        devices,
        positions={"aa:bb:cc:00:00:01": NodePosition("aa:bb:cc:00:00:01", 0.5, 0.5)},
    )

    assert json.dumps("cose")   in html_no_pos
    assert json.dumps("preset") in html_with_pos


def test_build_elements_for_update_strips_positions():
    """build_elements_for_update returns elements with no 'position' key."""
    from modules.topology_cytoscape_html import build_elements_for_update

    devices = [{"ip": "192.168.1.20", "mac": "de:ad:be:ef:00:01", "hostname": "cam"}]
    elements = build_elements_for_update(devices, gateway_ip="192.168.1.1")

    assert isinstance(elements, list)
    assert len(elements) > 0
    for el in elements:
        assert "position" not in el, f"position key found in element: {el}"


def test_build_elements_for_update_includes_device_node():
    """Device IP appears as a node id in the element list."""
    from modules.topology_cytoscape_html import build_elements_for_update

    devices = [{"ip": "192.168.1.30", "mac": "ca:fe:ba:be:00:01"}]
    elements = build_elements_for_update(devices, gateway_ip="192.168.1.1")

    node_ids = {el["data"]["id"] for el in elements if el.get("group") == "nodes"}
    # Node ID is mac (or ip when mac is absent)
    assert "ca:fe:ba:be:00:01" in node_ids


def test_cytoscape_html_contains_lock_layout_function():
    """The JS page exposes the window.lockLayout function."""
    from modules.topology_cytoscape_html import build_cytoscape_html

    html = build_cytoscape_html([])
    assert "window.lockLayout" in html


def test_cytoscape_html_contains_update_topology_function():
    """The JS page exposes the window.updateTopology function for incremental updates."""
    from modules.topology_cytoscape_html import build_cytoscape_html

    html = build_cytoscape_html([])
    assert "window.updateTopology" in html


def test_set_preset_positions_does_not_defer_to_layout_running():
    """Regression: window.setPresetPositions() must not be gated by _layoutRunning.

    _runIncrementalLayout() kicks off an unanimated cose pass for any batch of
    6+ new nodes (e.g. mesh nodes or devices appearing right after a scan).
    Cytoscape's cose layout ticks across animation frames internally even with
    animate:false, so it is often still "running" the moment
    network_map_page.py calls setPresetPositions() right after
    window.updateTopology() to push a corrected geometric layout. If
    setPresetPositions deferred to _layoutRunning like setLayout()/
    resetLayout() do, that automatic resync would silently no-op, leaving
    devices spiraled in around the gateway until the user manually re-picked
    a layout from the toolbar.
    """
    from modules.topology_cytoscape_html import build_cytoscape_html

    html = build_cytoscape_html([])
    start = html.index("window.setPresetPositions = function")
    end   = html.index("};", start)
    fn_body = html[start:end]

    assert "if (layoutLocked || _layoutRunning)" not in fn_body, (
        "setPresetPositions must not gate on _layoutRunning — it must always "
        "be able to override an in-flight incremental physics pass"
    )
    # It may still reset _layoutRunning = false as part of forcibly clearing
    # the in-flight layout, but must never branch on its truthiness.
    import re
    assert not re.search(r"_layoutRunning\s*\)", fn_body), (
        "setPresetPositions must not branch on _layoutRunning"
    )
    assert "layoutLocked" in fn_body, (
        "setPresetPositions must still respect the user's explicit Lock Layout toggle"
    )


def test_active_layout_is_tracked_and_stoppable():
    """Regression: any layout that can race with setPresetPositions must be
    tracked in _activeLayout so it can be forcibly stopped, not just flagged."""
    from modules.topology_cytoscape_html import build_cytoscape_html

    html = build_cytoscape_html([])
    assert "var _activeLayout" in html
    assert "_activeLayout = newNodes.layout(" in html, (
        "_runIncrementalLayout's constrained cose pass must be tracked in "
        "_activeLayout so setPresetPositions can stop it"
    )
    assert "_activeLayout.stop()" in html


def test_cytoscape_html_gravity_setting():
    """The cose layout opts include gravity:120 to prevent rightward drift."""
    from modules.topology_cytoscape_html import build_cytoscape_html

    html = build_cytoscape_html([])
    assert "gravity" in html and "120" in html
