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

import time
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
    # RULE-WIN4: _bw_worker no longer stops on hideEvent() (see
    # network_map_page.py's hideEvent()-removal note) so it can legitimately
    # still be a real, running QThread here if a test drove a real
    # showEvent()/setCurrentWidget() cycle. Stop it before deleteLater() —
    # destroying a parented widget while its QThread child is still running
    # corrupts the heap instead of raising a catchable Python error.
    try:
        p._stop_bw_worker()
    except RuntimeError:
        pass  # already destroyed — safe to skip
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


def _wait_for(predicate, timeout_ms: int = 3000) -> bool:
    """Pump the Qt event loop until ``predicate()`` is true, or the deadline
    passes. Returns whether it became true.

    Prefer this over a fixed QTest.qWait() for anything gated on a deferred
    QTimer: showEvent()'s fit is scheduled 200ms out, so a flat qWait(250)
    leaves a 50ms margin that a contended CI runner can miss — which is
    exactly how test_show_event_skips_redundant_fit_when_no_new_data failed
    on macOS in the v2.1.x/v2.2.1 release run while passing on the identical
    code in the v2.2.0 run 2.5h earlier. Polling to a generous deadline
    removes the timing dependency without weakening the assertion: a fit that
    genuinely never fires still fails the test, it just takes longer to say so.
    """
    deadline = time.monotonic() + timeout_ms / 1000.0
    while time.monotonic() < deadline:
        QTest.qWait(20)
        if predicate():
            return True
    return False


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


# ── Mesh-only client parity between Interactive and Classic views ────────────
#
# Bug: a mesh Wi-Fi client (e.g. the scanning PC itself) never answers ARP, so
# it is absent from the scanned `devices` list but present in `mesh_enrichment`.
# The Classic (matplotlib) map synthesized a stub node for it; the Interactive
# (Cytoscape) map did not, so the local PC (and any other mesh-only client)
# was invisible on the Interactive tab only. Fix: render() now augments
# `devices` once via synthesize_mesh_only_clients() before either view
# consumes it, so both always show the identical device set.

def test_mesh_only_client_appears_in_both_interactive_and_classic_views(page):
    mesh_units = [
        SimpleNamespace(role="master", name="Kontor", mac="aa:bb:cc:dd:ee:f0"),
        SimpleNamespace(role="satellite", name="Kitchen", mac="aa:bb:cc:dd:ee:f1"),
    ]
    mc = SimpleNamespace(mac="11:22:33:44:55:66", ip="192.168.68.50",
                          name="MyPC", unit_name="Kitchen")
    mesh_enrichment = {"11:22:33:44:55:66": mc}

    page.render(
        devices=_devices(),
        gateway_ip="192.168.68.1",
        mesh_units=mesh_units,
        mesh_enrichment=mesh_enrichment,
    )

    # Interactive: the augmented device list (what feeds Cytoscape) must
    # include the mesh-only client.
    interactive_macs = {
        d.get("mac") if isinstance(d, dict) else getattr(d, "mac", "")
        for d in page._last_render_kwargs["devices"]
    }
    assert "11:22:33:44:55:66" in interactive_macs, (
        "Mesh-only client missing from the list that feeds the Interactive view"
    )

    # Classic: TopologyWidget must have drawn a node for the same client.
    assert "11:22:33:44:55:66" in page._classic_widget._pos_map, (
        "Mesh-only client missing from the Classic view"
    )


# ── RULE-WIN15: background bandwidth worker must stop when the page is hidden ─
#
# Bug: showEvent() defaults Traffic Overlay to checked on first show, starting
# a BandwidthOverlayWorker (Scapy sniffer QThread) that pushes a
# runJavaScript() update into the Interactive view every 5s forever.
# network_map_page.py had no hideEvent() override, so navigating away left the
# worker running (and, for a real QWebEngineView, growing the renderer
# process — see docs/spikes/network-map-bandwidth-worker-leak-repro.py) for
# the rest of the app session.

def test_hide_stops_bandwidth_worker(qt_app):
    """A real QStackedWidget page switch (setCurrentWidget away from the page,
    firing hideEvent()) must stop the background bandwidth worker."""
    from PyQt6.QtWidgets import QStackedWidget, QWidget

    class _FakeWorker:
        """Stands in for BandwidthOverlayWorker's stop lifecycle without
        needing a real QThread/Scapy — only isRunning()/stop()/wait() are
        touched by hideEvent()."""

        def __init__(self):
            self.stop_calls = 0
            self._running = True

        def isRunning(self):
            return self._running

        def stop(self):
            self.stop_calls += 1
            self._running = False

        def wait(self, ms=0):
            return True

    other = QWidget()
    stack = QStackedWidget()
    page = NetworkMapPage()
    stack.addWidget(other)
    stack.addWidget(page)

    worker = _FakeWorker()
    page._bw_worker = worker
    page._traffic_overlay = True

    stack.setCurrentWidget(page)
    assert worker.isRunning()

    stack.setCurrentWidget(other)  # fires hideEvent() on `page`

    assert worker.stop_calls == 1, "hideEvent() must stop the background bandwidth worker"
    assert not worker.isRunning()

    page.deleteLater()
    other.deleteLater()
    stack.deleteLater()
    for _ in range(3):
        qt_app.processEvents()


# ── Worker construct/discard leak (RULE-WIN8) ─────────────────────────────────
#
# _stop_bw_worker() (called from _on_traffic_toggled(False), no longer from
# hideEvent() -- see that method's removal note) only ever dropped the Python
# reference (self._bw_worker = None); it never deleteLater()'d the discarded
# QThread. Since the worker is constructed with parent=self, the C++ object
# survives as a permanent child of the page every time Traffic Overlay is
# toggled off and back on (RULE-WIN8).

def test_bandwidth_worker_deleted_after_stop_not_leaked(page, monkeypatch):
    """Every BandwidthOverlayWorker discarded by _stop_bw_worker() must be
    deleteLater()'d — otherwise each show/hide cycle leaks one permanently."""
    from PyQt6.QtCore import QObject

    constructed: list = []

    class _FakeSignal:
        def __init__(self):
            self._slots: list = []

        def connect(self, slot):
            self._slots.append(slot)

        def emit(self, *args):
            for s in list(self._slots):
                s(*args)

    class _FakeWorker(QObject):
        def __init__(self, interval_s=5.0, parent=None):
            super().__init__(parent)
            self.snapshot_ready = _FakeSignal()
            self.error = _FakeSignal()
            self.finished = _FakeSignal()
            self._running = False
            self._finished_emitted = False
            self.delete_later_called = False
            constructed.append(self)

        def start(self):
            self._running = True

        def isRunning(self):
            return self._running

        def stop(self):
            self._running = False

        def wait(self, ms=0):
            # Real QThread.wait() blocks until the thread's run() has
            # returned, and Qt has already emitted finished() by then.
            if not self._finished_emitted:
                self._finished_emitted = True
                self.finished.emit()
            return True

        def deleteLater(self):
            self.delete_later_called = True

    monkeypatch.setattr("ui.pages.network_map_page.BandwidthOverlayWorker", _FakeWorker)

    for _ in range(5):
        page._start_bw_worker()
        page._stop_bw_worker()

    assert len(constructed) == 5
    assert all(w.delete_later_called for w in constructed), (
        "every discarded BandwidthOverlayWorker must be deleteLater()'d — "
        "otherwise it leaks as a permanent QThread child of the page "
        "(RULE-WIN8)"
    )


# ── Page-isolation soak follow-up: redundant full-topology re-push ────────────
#
# BandwidthOverlayWorker fires every 5s regardless of whether the traffic
# picture actually changed; _on_bw_snapshot() unconditionally called
# _refresh_web_view(), which re-serializes the ENTIRE topology (nodes, edges,
# segments, LLDP) and re-pushes it into the WebEngine view via
# runJavaScript(window.updateTopology(...)) even when nothing changed (e.g.
# an idle network snapshotting the same empty/unchanged bandwidth map every
# tick). RULE-WIN15's own repro already measured this exact call shape as a
# real, unbounded ~46KB/push growth in the renderer process.

def test_bandwidth_snapshot_skips_refresh_when_unchanged(page, monkeypatch):
    page.render(devices=_devices(), gateway_ip="192.168.68.1")
    page._traffic_overlay = True

    refresh_calls: list = []
    monkeypatch.setattr(page, "_refresh_web_view", lambda **kw: refresh_calls.append(kw))

    snap = SimpleNamespace(
        entries=[SimpleNamespace(mac="aa:bb:cc:dd:ee:01", total_bps=500.0)]
    )
    page._on_bw_snapshot(snap)
    assert len(refresh_calls) == 1

    # Identical snapshot next tick — must not trigger a second full re-push.
    page._on_bw_snapshot(snap)
    assert len(refresh_calls) == 1, (
        "an unchanged bandwidth snapshot must not re-trigger a full "
        "topology re-serialize + runJavaScript push"
    )

    # A genuinely different snapshot must still refresh.
    snap2 = SimpleNamespace(
        entries=[SimpleNamespace(mac="aa:bb:cc:dd:ee:01", total_bps=999.0)]
    )
    page._on_bw_snapshot(snap2)
    assert len(refresh_calls) == 2


# ── Page-isolation soak follow-up: redundant fit_view() on every revisit ──────
#
# showEvent() unconditionally scheduled a QTimer -> fit_view() ->
# runJavaScript(window.fitView...) call every single time the page became
# visible, regardless of whether any new scan data had arrived since the
# last visit. On a rapid navigate-away-and-back harness (~200 visits over 20
# minutes) that is ~200 redundant JS pushes into the WebEngine renderer, each
# with a real unbounded per-call cost per RULE-WIN15's own spike. Network Map
# is the only one of the 5 page-isolation-tested pages with a QWebEngineView
# at all, and disabling admin (so BandwidthOverlayWorker fails once and never
# restarts) ruled that mechanism out as the driver of the still-measured
# ~210-223 MB/hr excess -- this repeated fit_view() call is the only thing
# left that fires on literally every visit.

def test_show_event_skips_redundant_fit_when_no_new_data(page, monkeypatch):
    from PyQt6.QtWidgets import QStackedWidget, QWidget

    page.render(devices=_devices(), gateway_ip="192.168.68.1")
    assert page._topology_loaded is True

    fit_calls: list = []
    monkeypatch.setattr(page, "fit_view", lambda: fit_calls.append(page._scan_id))

    other = QWidget()
    stack = QStackedWidget()
    stack.addWidget(other)
    stack.addWidget(page)
    stack.show()  # a never-shown QStackedWidget does not reliably deliver
                  # showEvent()/hideEvent() to its children (see
                  # test_protocol_canvas.py::test_hide_show_propagates_through_nested_stacked_widget)

    for i in range(5):
        stack.setCurrentWidget(page)   # fires showEvent()
        if i == 0:
            # Wait for the first fit to actually land rather than sleeping a
            # fixed 250ms, so the count below means "the 4 revisits added
            # nothing" instead of "one fit landed somewhere in 1250ms".
            assert _wait_for(lambda: len(fit_calls) == 1), (
                "the first show with fresh scan data must schedule a fit"
            )
        else:
            QTest.qWait(250)           # let the 200ms QTimer fire
        stack.setCurrentWidget(other)  # fires hideEvent()

    assert len(fit_calls) == 1, (
        "fit_view() must only re-fire when new scan data has arrived since "
        "the last fit — not on every single revisit with unchanged data"
    )

    # New data (a different scan_id -- compute_scan_id() keys off /24 subnets,
    # so the new device must be in a different subnet to actually change it)
    # arriving must still trigger a re-fit.
    page.render(
        devices=_devices() + [{"ip": "10.0.0.5", "mac": "aa:bb:cc:dd:ee:99"}],
        gateway_ip="192.168.68.1",
    )
    assert page._scan_id != fit_calls[0], "test setup: scan_id must actually change"
    stack.setCurrentWidget(other)
    stack.setCurrentWidget(page)
    assert _wait_for(lambda: len(fit_calls) == 2), (
        "a revisit after new scan data arrived must re-fit — "
        f"fit_view() fired {len(fit_calls)} time(s), expected 2"
    )

    other.deleteLater()
    stack.deleteLater()
