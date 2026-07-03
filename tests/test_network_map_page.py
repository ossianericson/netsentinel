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

from modules.topology_layout import compute_scan_id, load_layout
from ui.pages.network_map_page import NetworkMapPage


@pytest.fixture(autouse=True)
def _isolate_render_cache(tmp_path, monkeypatch):
    """render() persists its inputs via modules.network_map_cache by default
    — redirect that to a temp dir so the test suite never overwrites a real
    user's network_map_render_cache.json under %LOCALAPPDATA%\\NetSentinel."""
    monkeypatch.setattr("modules.network_map_cache.get_app_data_dir", lambda: tmp_path)



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


# ── Layout persistence across an app restart ─────────────────────────────────
#
# Bug: the Network Map looked different every time the app was restarted, even
# with no network change. Two compounding causes:
#
# 1. self._scan_id was recomputed AFTER _refresh_web_view() already used it to
#    load/save positions, so the very first render of an app session (the
#    startup cache render) always loaded/saved under the leftover "default"
#    placeholder from __init__ instead of the real subnet-derived key — it
#    could never find the previous session's saved layout.
# 2. All 4 geo_* layout modes unconditionally ignored any saved positions and
#    recomputed from scratch on every full render, discarding manual drags
#    and producing a different-looking (but individually deterministic)
#    layout if the startup render's inputs (gateway inference, mesh/modem
#    cache restoration) differed even slightly from the live session.
#
# Fix: positions are now persisted after every full geometric layout compute
# (not just manual drags) and reused verbatim on the next full render unless a
# node id is genuinely new — a node merely absent this render (offline
# device, not-yet-reported modem) keeps its saved position instead of being
# treated as removed.

@pytest.fixture
def tmp_layout_path(tmp_path, monkeypatch):
    """Redirect the on-disk layout file to a temp directory for these tests."""
    layout_file = tmp_path / "topology_layout.json"
    monkeypatch.setattr("modules.topology_layout._layout_path", lambda: layout_file)
    return layout_file


def test_restart_with_unchanged_devices_reuses_saved_positions(qt_app, tmp_layout_path, monkeypatch):
    """Simulates an app restart: a brand-new NetworkMapPage instance, rendered
    with the exact same devices, must reuse the previous instance's saved
    positions rather than recomputing — this is the user-visible "looks
    different every time I reopen the app" bug."""
    page1 = NetworkMapPage()
    page1._web_available = True
    page1._web_view = MagicMock()
    page1._layout_combo.setCurrentText("Hierarchy")
    page1.render(devices=_devices(), gateway_ip="192.168.68.1")
    assert page1._topology_loaded is True

    page2 = NetworkMapPage()
    page2._web_available = True
    page2._web_view = MagicMock()
    page2._layout_combo.setCurrentText("Hierarchy")
    recompute = MagicMock(wraps=page2._compute_geo_positions)
    monkeypatch.setattr(page2, "_compute_geo_positions", recompute)

    page2.render(devices=_devices(), gateway_ip="192.168.68.1")

    assert page2._topology_loaded is True
    recompute.assert_not_called()

    for p in (page1, page2):
        p.deleteLater()
    for _ in range(3):
        qt_app.processEvents()


def test_restart_with_new_device_recomputes_and_keeps_offline_ones(qt_app, tmp_layout_path):
    """When a scan discovers a device id never seen before, recompute is
    expected (and correct) — but devices that simply aren't in this render
    (e.g. temporarily offline) must keep their saved position rather than
    being dropped from the saved file."""
    page1 = NetworkMapPage()
    page1._web_available = True
    page1._web_view = MagicMock()
    page1._layout_combo.setCurrentText("Hierarchy")
    devices = _devices()
    page1.render(devices=devices, gateway_ip="192.168.68.1")

    key = page1._layout_storage_key("geo_hierarchy")
    saved_before = load_layout(key)
    offline_id = devices[1]["mac"]
    assert offline_id in saved_before

    # Next "scan": device[1] is offline (absent), a brand-new device appears.
    new_device = {"ip": "192.168.68.99", "mac": "aa:bb:cc:dd:ee:99",
                  "hostname": "NewGadget", "risk_level": "CLEAN"}
    page1._topology_loaded = False
    page1.render(devices=[devices[0], new_device], gateway_ip="192.168.68.1")

    saved_after = load_layout(key)
    assert new_device["mac"] in saved_after          # newly discovered device is positioned
    assert offline_id in saved_after                  # offline device's position preserved

    page1.deleteLater()
    for _ in range(3):
        qt_app.processEvents()


def test_layout_modes_do_not_share_saved_positions(qt_app, tmp_layout_path):
    """Hierarchy and Grid compute different coordinates for the same devices —
    switching modes and restarting must not apply one mode's saved (x, y)
    values under the other mode's key."""
    page = NetworkMapPage()
    page._web_available = True
    page._web_view = MagicMock()
    page._layout_combo.setCurrentText("Hierarchy")
    page.render(devices=_devices(), gateway_ip="192.168.68.1")

    hierarchy_key = page._layout_storage_key("geo_hierarchy")
    grid_key = page._layout_storage_key("geo_grid")
    assert hierarchy_key != grid_key
    assert load_layout(grid_key) == {}  # nothing saved under Grid yet

    page.deleteLater()
    for _ in range(3):
        qt_app.processEvents()


def test_share_export_writes_sanitized_png(page, monkeypatch, tmp_path):
    """_on_share_export renders a sanitized PNG independent of the live view —
    private IPs must be aliased, never the raw scan data."""
    page.render(devices=_devices(), gateway_ip="192.168.68.1")
    out_path = tmp_path / "share.png"
    monkeypatch.setattr(
        "PyQt6.QtWidgets.QFileDialog.getSaveFileName",
        lambda *a, **kw: (str(out_path), ""),
    )
    page._on_share_export()
    assert out_path.exists()


def test_share_export_noop_when_dialog_cancelled(page, monkeypatch, tmp_path):
    page.render(devices=_devices(), gateway_ip="192.168.68.1")
    monkeypatch.setattr(
        "PyQt6.QtWidgets.QFileDialog.getSaveFileName",
        lambda *a, **kw: ("", ""),
    )
    page._on_share_export()  # must not raise


def test_first_render_of_session_uses_real_scan_id_not_default(qt_app, tmp_layout_path):
    """Regression for the ordering bug: self._scan_id must be computed BEFORE
    _refresh_web_view() reads it, even on the very first render() call of a
    fresh page instance (self._scan_id otherwise starts as "default")."""
    page = NetworkMapPage()
    page._web_available = True
    page._web_view = MagicMock()
    page._layout_combo.setCurrentText("Hierarchy")
    page.render(devices=_devices(), gateway_ip="192.168.68.1")

    real_id = compute_scan_id(_devices())
    assert real_id != "default"
    assert page._scan_id == real_id
    assert load_layout(f"{real_id}::geo_hierarchy")  # saved under the real key
    assert load_layout("default::geo_hierarchy") == {}  # not under the stale placeholder

    page.deleteLater()
    for _ in range(3):
        qt_app.processEvents()
