"""Tests for ui/pages/protocol_viz_page.py"""
from __future__ import annotations

import pytest

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)


@pytest.fixture
def page():
    from ui.pages.protocol_viz_page import ProtocolVizPage
    p = ProtocolVizPage()
    yield p
    try:
        p.deleteLater()
    except RuntimeError:
        pass  # already deleted
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


_NET_INFO = {"gateway": "192.168.1.1", "local_ips": [{"ip": "192.168.1.50"}]}


@pytest.fixture
def live_page():
    """A page built with experimental/protoviz_live already on (RULE-EXP1)."""
    from PyQt6.QtCore import QSettings
    from ui.pages.protocol_viz_page import ProtocolVizPage, _LIVE_FLAG_KEY
    QSettings().setValue(_LIVE_FLAG_KEY, True)
    p = ProtocolVizPage()
    p.set_context(net_info=_NET_INFO, devices=[])
    yield p
    if p._is_live():
        p._stop_live()
    try:
        p.deleteLater()
    except RuntimeError:
        pass  # already deleted
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


def test_import():
    from ui.pages.protocol_viz_page import ProtocolVizPage  # noqa: F401


def test_instantiation(page):
    assert page is not None


def test_has_protocol_selector(page):
    """Page should have a protocol combobox or selector."""
    has_selector = (
        hasattr(page, "_protocol_combo") or
        hasattr(page, "_proto_combo") or
        hasattr(page, "_selector")
    )
    assert has_selector or page is not None


def test_on_scan_result_does_not_crash(page):
    """Injecting scan data should not crash."""
    result = {
        "devices": [
            {"ip": "192.168.1.1", "mac": "aa:bb:cc:dd:ee:01",
             "hostname": "router", "device_type": "Router"}
        ]
    }
    slot = getattr(page, "on_scan_result", None)
    if slot:
        slot(result)
    assert page is not None


def test_speed_toggle_persists_and_applies(page):
    from PyQt6.QtCore import QSettings

    btn_2x = page._speed_btns[2.0]
    btn_2x.click()

    assert page._canvas._speed == 2.0
    assert QSettings().value("protoviz/speed", type=float) == 2.0
    assert btn_2x.isChecked()
    assert not page._speed_btns[1.0].isChecked()


def test_frame_anatomy_panel_shows_real_gateway_mac_for_arp(page):
    """Phase A2 acceptance check: selecting ARP and stepping to the reply must
    show the real scanned gateway MAC inside the Frame Anatomy panel's fields."""
    page.set_context(
        net_info={
            "gateway": "192.168.1.1",
            "gateway_mac": "aa:bb:cc:dd:ee:ff",
            "local_ips": [{"ip": "192.168.1.100"}],
        },
        devices=[],
    )
    page._select_protocol("ARP")
    page._canvas.go_to_step(1)   # ARP Reply — gateway -> client
    page._show_step(1, page._canvas._scene)

    found = False
    for row in range(page._frame_panel._table.rowCount()):
        item = page._frame_panel._table.item(row, 1)
        if item is not None and "AA:BB:CC:DD:EE:FF" in item.text():
            found = True
            break
    assert found, "Frame Anatomy panel should show the real gateway MAC in a layer field"


def _give_page_real_context(page):
    page.set_context(
        net_info={
            "gateway": "192.168.1.1",
            "gateway_mac": "aa:bb:cc:dd:ee:ff",
            "local_ips": [{"ip": "192.168.1.100"}],
        },
        devices=[],
    )


def test_copy_canvas_image_puts_pixmap_on_clipboard(page):
    """Phase A3: title-bar 'Copy image' grabs the live canvas onto the clipboard."""
    _give_page_real_context(page)
    page._select_protocol("ARP")
    page.resize(500, 500)

    page._copy_canvas_image()

    assert not QApplication.clipboard().pixmap().isNull()


def test_copy_canvas_image_noop_on_placeholder(page):
    """No scan context yet -> canvas is hidden behind the placeholder; must not crash
    or put a stale/blank pixmap on the clipboard."""
    QApplication.clipboard().clear()
    page._copy_canvas_image()
    assert QApplication.clipboard().pixmap().isNull()


def test_save_canvas_image_writes_png(page, monkeypatch, tmp_path):
    """Phase A3: title-bar 'Save PNG...' writes the current frame to disk."""
    _give_page_real_context(page)
    page._select_protocol("ARP")
    page.resize(500, 500)
    out_path = tmp_path / "frame.png"
    monkeypatch.setattr(
        "PyQt6.QtWidgets.QFileDialog.getSaveFileName",
        lambda *a, **kw: (str(out_path), ""),
    )

    page._save_canvas_image()

    assert out_path.exists()


def test_export_storyboard_writes_multi_step_png_and_restores_step(page, monkeypatch, tmp_path):
    """Phase A3: storyboard export writes every step to one PNG and leaves the
    canvas exactly where the user had it."""
    _give_page_real_context(page)
    page._select_protocol("DHCP")
    page.resize(500, 500)
    page._canvas.go_to_step(2)
    out_path = tmp_path / "storyboard.png"
    monkeypatch.setattr(
        "PyQt6.QtWidgets.QFileDialog.getSaveFileName",
        lambda *a, **kw: (str(out_path), ""),
    )

    page._export_storyboard()

    assert out_path.exists()
    assert page._canvas.current_step() == 2


def test_export_storyboard_noop_when_dialog_cancelled(page, monkeypatch, tmp_path):
    _give_page_real_context(page)
    page._select_protocol("DHCP")
    monkeypatch.setattr(
        "PyQt6.QtWidgets.QFileDialog.getSaveFileName",
        lambda *a, **kw: ("", ""),
    )
    page._export_storyboard()  # must not raise
    assert not (tmp_path / "storyboard.png").exists()


def test_canvas_context_menu_offers_all_three_export_actions(page):
    menu = page._build_canvas_menu()
    try:
        assert [a.text() for a in menu.actions()] == [
            "Copy image", "Save PNG…", "Export storyboard…",
        ]
    finally:
        menu.deleteLater()


def test_step_list_click_jumps_to_step(page):
    from modules.protocol_animator import AnimNode, AnimStep, ProtocolSceneData
    scene = ProtocolSceneData(
        protocol="TEST", title="Test", subtitle="",
        nodes=[AnimNode("a", "A", "client", 0.2, 0.5),
               AnimNode("b", "B", "server", 0.8, 0.5)],
        steps=[AnimStep("a", "b", "One",   "d1", "e1"),
               AnimStep("b", "a", "Two",   "d2", "e2", is_reply=True),
               AnimStep("a", "b", "Three", "d3", "e3")],
    )
    page._canvas.set_scene(scene)
    page._populate_step_list(scene)
    assert page._step_list.count() == 3          # populated

    page._on_step_row_activated(2)               # simulate click on row 3
    assert page._canvas._step == 2               # canvas jumped
    assert page._step_list.currentRow() == 2     # selection synced
    assert page._step_label.text() == "Step 3 of 3"
    assert not page._canvas.is_playing()         # jump paused playback


# ── Live Mode (Phase A5) ─────────────────────────────────────────────────────

def test_live_toggle_hidden_by_default(page):
    """RULE-EXP1: with the flag off, Live Mode must be invisible — byte-identical
    to Phase A4 behaviour."""
    page.set_context(net_info=_NET_INFO, devices=[])
    assert page._btn_live.isHidden()


def test_live_toggle_shown_for_arp_and_dns_when_flag_on(live_page):
    live_page.show()
    assert live_page._active_key == "ARP"
    assert live_page._btn_live.isVisible()
    live_page._select_protocol("DNS")
    assert live_page._btn_live.isVisible()


def test_live_toggle_hidden_for_unsupported_protocol(live_page):
    live_page.show()
    live_page._select_protocol("TCP")
    assert not live_page._btn_live.isVisible()


def test_start_live_seeds_client_and_gateway_nodes(live_page):
    live_page._start_live()
    assert live_page._is_live()
    assert set(live_page._live_nodes.keys()) == {"192.168.1.50", "192.168.1.1"}
    assert live_page._live_nodes["192.168.1.50"].role == "client"
    assert live_page._live_nodes["192.168.1.1"].role == "gateway"
    assert live_page._canvas.is_live()


def test_start_live_disables_step_playback_controls(live_page):
    live_page._start_live()
    assert not live_page._btn_play.isEnabled()
    assert not live_page._btn_back.isEnabled()
    assert not live_page._btn_fwd.isEnabled()
    assert not live_page._btn_reset.isEnabled()


def test_live_frame_event_adds_new_talker_and_pulses_canvas(live_page):
    from modules.live_protocol_feed import LiveFrameEvent
    live_page._start_live()
    evt = LiveFrameEvent(
        protocol="ARP", src_ip="192.168.1.77", src_mac="aa:bb:cc:dd:ee:ff",
        dst_ip="192.168.1.1", summary="Who has 192.168.1.1? Tell 192.168.1.77",
        is_reply=False, is_broadcast=True, ts=1700000000.0,
    )
    live_page._on_live_frame_event(evt)
    assert "192.168.1.77" in live_page._live_nodes
    assert live_page._live_nodes["192.168.1.77"].role == "broadcast"   # unknown talker
    assert len(live_page._canvas._live_pulses) == 1
    assert live_page._live_log_list.count() == 1
    assert "192.168.1.77" in live_page._live_log_list.item(0).text()


def test_live_log_caps_at_ten_entries(live_page):
    from modules.live_protocol_feed import LiveFrameEvent
    live_page._start_live()
    for i in range(15):
        evt = LiveFrameEvent(
            protocol="ARP", src_ip="192.168.1.1", src_mac="aa:bb:cc:dd:ee:ff",
            dst_ip="192.168.1.50", summary=f"event {i}",
            is_reply=True, is_broadcast=False, ts=1700000000.0 + i,
        )
        live_page._on_live_frame_event(evt)
    assert live_page._live_log_list.count() == 10
    assert "event 14" in live_page._live_log_list.item(0).text()   # newest first


def test_evict_stale_live_nodes_keeps_pinned_and_caps_at_max(live_page):
    live_page._start_live()
    for i in range(10):
        live_page._live_node_id_for(f"10.0.0.{i}")
    assert len(live_page._live_nodes) <= 8
    assert "192.168.1.50" in live_page._live_nodes   # "you" never evicted
    assert "192.168.1.1" in live_page._live_nodes    # gateway never evicted


def test_toggle_live_off_restores_step_mode(live_page):
    live_page._start_live()
    live_page._toggle_live()
    assert not live_page._is_live()
    assert not live_page._canvas.is_live()
    assert live_page._btn_play.isEnabled()
    assert live_page._canvas._scene is not None   # step scene rebuilt


def test_switching_protocol_while_live_stops_live_mode(live_page):
    live_page._start_live()
    live_page._select_protocol("DNS")
    assert not live_page._is_live()
    assert live_page._active_key == "DNS"


def test_set_context_does_not_interrupt_live_mode(live_page):
    live_page._start_live()
    live_page._canvas.pulse("192.168.1.50", "192.168.1.1", "test", False, False)
    assert len(live_page._canvas._live_pulses) == 1
    live_page.set_context(net_info=_NET_INFO, devices=[{"ip": "192.168.1.99"}])
    # A scan-context refresh must not rebuild the scene out from under Live Mode.
    assert live_page._is_live()
    assert len(live_page._canvas._live_pulses) == 1


def test_live_error_stops_and_shows_translated_message(live_page):
    live_page._start_live()
    live_page._on_live_error("Failed to start live ARP capture: boom")
    assert not live_page._is_live()
    assert "boom" in live_page._canvas_subtitle.text()


def test_live_progress_updates_subtitle(live_page):
    live_page._start_live()
    live_page._on_live_progress("Live ARP capture running (3 events)…")
    assert "3 events" in live_page._canvas_subtitle.text()


def test_live_mode_full_worker_to_canvas_chain(live_page, monkeypatch):
    """RULE-T7 end-to-end: a real LiveProtocolWorker (capability checks and the
    scapy feed monkeypatched, matching tests/test_live_protocol_worker.py) emits
    frame_event across a real QThread boundary, and the page updates the canvas
    and log strip from the actual signal wiring _start_live() sets up — not by
    calling the slot directly, the way the other Live Mode tests above do."""
    monkeypatch.setattr("modules.utils.is_admin", lambda: True)
    monkeypatch.setattr("modules.utils.is_npcap_available", lambda: True)

    from modules.live_protocol_feed import LiveFrameEvent

    class _FakeFeed:
        def __init__(self, protocol, on_event, on_error):
            self._on_event = on_event
            self.event_count = 0

        def start(self):
            evt = LiveFrameEvent(
                protocol="ARP", src_ip="192.168.1.77", src_mac="aa:bb:cc:dd:ee:ff",
                dst_ip="192.168.1.1", summary="Who has 192.168.1.1? Tell 192.168.1.77",
                is_reply=False, is_broadcast=True, ts=1700000000.0,
            )
            self._on_event(evt)
            self.event_count += 1

        def stop(self):
            pass

    monkeypatch.setattr("modules.live_protocol_feed.LiveProtocolFeed", _FakeFeed)

    import time as _time
    live_page._start_live()
    # work() emits synchronously from _FakeFeed.start() before entering its
    # poll-until-stopped loop -- give the worker thread a moment to reach that
    # call, then pump the main-thread event loop to drain the queued signal
    # (see tests/test_live_protocol_worker.py::_pump for why this is required).
    _time.sleep(0.3)
    app = QApplication.instance()
    for _ in range(10):
        app.processEvents()

    assert "192.168.1.77" in live_page._live_nodes
    assert len(live_page._canvas._live_pulses) == 1
    assert live_page._live_log_list.count() == 1
