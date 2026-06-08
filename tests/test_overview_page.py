"""
Tests for ui/pages/overview_page.py

Covers:
  • Tile ID uniqueness
  • Tile build and body widget creation
  • DeviceCountTile.update_cycle
  • ServiceStatusTile.update_services
  • TlsStatusTile.refresh via MockStore
  • RttSummaryTile.update_cycle
  • NetworkGradeTile.update_grade
  • AlertFeedTile.push_alert + _redraw
  • EventFeedTile.refresh via MockStore
  • OverviewPage construction and tile presence
  • swap_tiles
  • _load_order / _save_order
  • edit mode toggle propagates to all tiles
  • on_cycle_done routes to device_count + rtt_summary
  • on_cert_done calls tls_status.refresh
  • on_svc_done calls service_status.update_services
  • on_alert calls alert_feed.push_alert
  • on_grade calls network_grade.update_grade
  • QSettings persistence round-trip
  • _refresh_store_tiles calls refresh on store-backed tiles
  • swap_tiles with unknown id is a no-op
  • swap_tiles same id is a no-op
"""

from dataclasses import dataclass
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Minimal Qt bootstrap — use offscreen if no display
# ---------------------------------------------------------------------------
try:
    from PyQt6.QtWidgets import QApplication  # noqa: F401
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)


# ---------------------------------------------------------------------------
# Stub MetricStore-like objects returned from mock queries
# ---------------------------------------------------------------------------
@dataclass
class FakeCert:
    host: str
    port: int
    days_remaining: Optional[int]
    is_expired: bool
    error: Optional[str] = None


@dataclass
class FakeSvc:
    host: str
    port: int
    label: Optional[str]
    up: bool
    rtt_ms: Optional[float] = None


@dataclass
class FakeEvent:
    ts: int
    ip: str
    mac: Optional[str]
    event_type: str
    detail: Optional[str] = None


class MockStore:
    def __init__(
        self,
        uptime_rows=None,
        cert_rows=None,
        event_rows=None,
    ):
        self._uptime_rows = uptime_rows or []
        self._cert_rows   = cert_rows   or []
        self._event_rows  = event_rows  or []

    def query_uptime_table(self, hours_list=None):
        return self._uptime_rows

    def query_cert_status(self, hours=168):
        return self._cert_rows

    def query_device_events(self, hours=24.0, ip=None, event_types=None):
        return self._event_rows

    def get_recent_alerts(self, hours=24.0, limit=200):
        return []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_overview(store=None):
    from ui.pages.overview_page import OverviewPage
    return OverviewPage(store=store)


# ---------------------------------------------------------------------------
# Tile registration
# ---------------------------------------------------------------------------
class TestTileRegistry:
    def test_all_tile_ids_unique(self):
        from ui.pages.overview_page import _TILE_CLASSES
        assert len(_TILE_CLASSES) == len(set(_TILE_CLASSES.keys()))

    def test_default_order_tiles_all_registered(self):
        from ui.pages.overview_page import _TILE_CLASSES, _DEFAULT_ORDER
        for tid in _DEFAULT_ORDER:
            assert tid in _TILE_CLASSES, f"'{tid}' not in _TILE_CLASSES"

    def test_tile_classes_have_tile_label(self):
        from ui.pages.overview_page import _TILE_CLASSES
        for tid, cls in _TILE_CLASSES.items():
            assert hasattr(cls, "TILE_LABEL"), f"{cls.__name__} missing TILE_LABEL"
            assert cls.TILE_LABEL, f"{cls.__name__} TILE_LABEL is empty"


# ---------------------------------------------------------------------------
# DeviceCountTile
# ---------------------------------------------------------------------------
class TestDeviceCountTile:
    def _make(self):
        from ui.pages.overview_page import DeviceCountTile
        return DeviceCountTile()

    def test_initial_placeholder(self):
        t = self._make()
        assert t._count_lbl.text() == "–"

    def test_update_cycle_total(self):
        t = self._make()
        t.update_cycle({"10.0.0.1": "UP", "10.0.0.2": "UP", "10.0.0.3": "DOWN"})
        assert t._count_lbl._target == 3

    def test_update_cycle_sub_label_up_down(self):
        t = self._make()
        t.update_cycle({"a": "UP", "b": "DOWN"})
        assert "1 up" in t._sub_lbl.text()
        assert "1" in t._sub_lbl.text()  # down

    def test_update_cycle_empty(self):
        t = self._make()
        t.update_cycle({})
        assert t._count_lbl._target == 0
        assert "No devices" in t._sub_lbl.text()

    def test_update_cycle_all_up(self):
        t = self._make()
        t.update_cycle({"x": "UP", "y": "UP"})
        assert "up" in t._sub_lbl.text()
        assert "down" not in t._sub_lbl.text()



# ---------------------------------------------------------------------------
# ServiceStatusTile
# ---------------------------------------------------------------------------
class TestServiceStatusTile:
    def _make(self):
        from ui.pages.overview_page import ServiceStatusTile
        return ServiceStatusTile()

    def test_initial_placeholders(self):
        t = self._make()
        assert t._up_lbl.text() == "–"
        assert t._dn_lbl.text() == "–"

    def test_update_services_dict(self):
        t = self._make()
        t.update_services([{"up": True}, {"up": False}, {"up": True}])
        assert t._up_lbl._target == 2
        assert t._dn_lbl._target == 1

    def test_update_services_dataclass(self):
        t = self._make()
        t.update_services([FakeSvc("h", 80, None, True), FakeSvc("h", 443, None, False)])
        assert t._up_lbl._target == 1
        assert t._dn_lbl._target == 1

    def test_update_services_all_down(self):
        t = self._make()
        t.update_services([{"up": False}, {"up": False}])
        assert t._up_lbl._target == 0
        assert t._dn_lbl._target == 2

    def test_update_services_empty(self):
        t = self._make()
        t.update_services([])
        assert t._up_lbl._target == 0


# ---------------------------------------------------------------------------
# TlsStatusTile
# ---------------------------------------------------------------------------
class TestTlsStatusTile:
    def _make(self, store=None):
        from ui.pages.overview_page import TlsStatusTile
        return TlsStatusTile(store=store)

    def test_initial_placeholders(self):
        t = self._make()
        assert t._ok_lbl.text() == "–"

    def test_refresh_all_ok(self):
        store = MockStore(cert_rows=[
            FakeCert("h1", 443, 90, False),
            FakeCert("h2", 443, 120, False),
        ])
        t = self._make(store)
        t.refresh()
        assert t._ok_lbl.text() == "2"
        assert t._expiring_lbl.text() == "0"
        assert t._expired_lbl.text() == "0"

    def test_refresh_expiring(self):
        store = MockStore(cert_rows=[FakeCert("h1", 443, 15, False)])
        t = self._make(store)
        t.refresh()
        assert t._expiring_lbl.text() == "1"
        assert t._ok_lbl.text() == "0"

    def test_refresh_expired(self):
        store = MockStore(cert_rows=[FakeCert("h1", 443, -1, True)])
        t = self._make(store)
        t.refresh()
        assert t._expired_lbl.text() == "1"

    def test_refresh_no_store_noop(self):
        t = self._make()
        t.refresh()  # must not raise

    def test_refresh_mixed(self):
        store = MockStore(cert_rows=[
            FakeCert("h1", 443, 90, False),
            FakeCert("h2", 443, 10, False),
            FakeCert("h3", 443, -1, True),
        ])
        t = self._make(store)
        t.refresh()
        assert t._ok_lbl.text() == "1"
        assert t._expiring_lbl.text() == "1"
        assert t._expired_lbl.text() == "1"


# ---------------------------------------------------------------------------
# RttSummaryTile
# ---------------------------------------------------------------------------
class TestRttSummaryTile:
    def _make(self):
        from ui.pages.overview_page import RttSummaryTile
        return RttSummaryTile()

    def test_initial_placeholder(self):
        t = self._make()
        assert t._rtt_lbl.text() == "–"

    def test_update_cycle_avg_rtt(self):
        t = self._make()
        t.update_cycle({"a": 20.0, "b": 40.0})
        assert "30" in t._rtt_lbl.text()

    def test_update_cycle_packet_loss_zero(self):
        from ui.styles import GREEN
        t = self._make()
        t.update_cycle({"a": 20.0, "b": 30.0})
        assert "0%" in t._loss_lbl.text()
        assert GREEN in t._loss_lbl.styleSheet()

    def test_update_cycle_packet_loss_partial(self):
        from ui.styles import RED
        t = self._make()
        t.update_cycle({"a": 20.0, "b": None})
        assert "50%" in t._loss_lbl.text()
        # 50 % loss is above the 10 % threshold — should be RED
        assert RED in t._loss_lbl.styleSheet()

    def test_update_cycle_all_lost(self):
        from ui.styles import RED
        t = self._make()
        t.update_cycle({"a": None, "b": None})
        assert t._rtt_lbl.text() == "–"
        assert "100%" in t._loss_lbl.text()
        assert RED in t._loss_lbl.styleSheet()

    def test_update_cycle_empty(self):
        t = self._make()
        t.update_cycle({})
        assert t._rtt_lbl.text() == "–"

    def test_update_cycle_high_rtt_red(self):
        from ui.styles import RED
        t = self._make()
        t.update_cycle({"a": 200.0})
        assert RED in t._rtt_lbl.styleSheet()


# ---------------------------------------------------------------------------
# NetworkGradeTile
# ---------------------------------------------------------------------------
class TestNetworkGradeTile:
    def _make(self):
        from ui.pages.overview_page import NetworkGradeTile
        return NetworkGradeTile()

    def test_initial_placeholder(self):
        t = self._make()
        assert t._grade_lbl.text() == "–"

    def test_grade_a_green(self):
        from ui.styles import GREEN
        t = self._make()
        t.update_grade("A", 95.0)
        assert t._grade_lbl.text() == "A"
        assert GREEN in t._grade_lbl.styleSheet()

    def test_grade_f_red(self):
        from ui.styles import RED
        t = self._make()
        t.update_grade("F", 20.0)
        assert t._grade_lbl.text() == "F"
        assert RED in t._grade_lbl.styleSheet()

    def test_grade_c_amber(self):
        from ui.styles import AMBER
        t = self._make()
        t.update_grade("C", 65.0)
        assert AMBER in t._grade_lbl.styleSheet()

    def test_grade_score_displayed(self):
        t = self._make()
        t.update_grade("B", 82.5)
        assert "82" in t._sub_lbl.text()

    def test_grade_no_score_empty_sub(self):
        t = self._make()
        t.update_grade("A", 0.0)
        assert t._sub_lbl.text() == ""

    def test_grade_lowercase_normalised(self):
        t = self._make()
        t.update_grade("b", 80.0)
        assert t._grade_lbl.text() == "B"


# ---------------------------------------------------------------------------
# AlertFeedTile
# ---------------------------------------------------------------------------
class TestAlertFeedTile:
    def _make(self):
        from ui.pages.overview_page import AlertFeedTile
        return AlertFeedTile()

    def _alert(self, sev="INFO", msg="test"):
        return {"severity": sev, "message": msg, "ts": 0}

    def test_initial_placeholders(self):
        t = self._make()
        assert t._rows[0].msg.text() == "–"

    def test_push_one_alert(self):
        t = self._make()
        t.push_alert(self._alert(msg="Port open"))
        assert "Port open" in t._rows[0].msg.text()

    def test_push_alert_dict(self):
        t = self._make()
        t.push_alert({"severity": "CRITICAL", "message": "Host down", "ts": 1})
        assert "Host down" in t._rows[0].msg.text()

    def test_push_alert_dataclass(self):
        alert = MagicMock()
        alert.severity = "WARNING"
        alert.message  = "High latency"
        alert.ts       = 100
        t = self._make()
        t.push_alert(alert)
        assert "High latency" in t._rows[0].msg.text()

    def test_max_five_alerts_kept(self):
        t = self._make()
        for i in range(8):
            t.push_alert(self._alert(msg=f"msg{i}"))
        assert len(t._alerts) == 5

    def test_latest_alert_first(self):
        t = self._make()
        t.push_alert(self._alert(msg="first"))
        t.push_alert(self._alert(msg="second"))
        assert "second" in t._rows[0].msg.text()

    def test_long_message_truncated(self):
        t = self._make()
        long_msg = "X" * 100
        t.push_alert(self._alert(msg=long_msg))
        assert len(t._rows[0].msg.text()) < 65

    def test_critical_severity_red_dot(self):
        from ui.styles import RED
        t = self._make()
        t.push_alert(self._alert(sev="CRITICAL"))
        assert RED in t._rows[0].bar.styleSheet()

    def test_warning_severity_amber_dot(self):
        from ui.styles import AMBER
        t = self._make()
        t.push_alert(self._alert(sev="WARNING"))
        assert AMBER in t._rows[0].bar.styleSheet()

    def test_empty_slots_remain_placeholder(self):
        t = self._make()
        t.push_alert(self._alert())  # only 1 alert
        assert t._rows[4].msg.text() == "–"

    def test_alert_clicked_signal_emits_rule_type_and_host(self):
        t = self._make()
        t.push_alert({"severity": "WARNING", "message": "Host down",
                      "ts": 0, "rule_type": "HOST_DOWN", "host": "10.0.0.1"})
        received = []
        t.alert_clicked.connect(lambda rt, h: received.append((rt, h)))
        t._rows[0].clicked.emit()
        assert received == [("HOST_DOWN", "10.0.0.1")]

    def test_alert_row_not_active_when_empty(self):
        t = self._make()
        assert not t._rows[0]._active

    def test_alert_row_active_after_push(self):
        t = self._make()
        t.push_alert(self._alert())
        assert t._rows[0]._active
        assert not t._rows[1]._active


# ---------------------------------------------------------------------------
# EventFeedTile
# ---------------------------------------------------------------------------
class TestEventFeedTile:
    def _make(self, store=None):
        from ui.pages.overview_page import EventFeedTile
        return EventFeedTile(store=store)

    def test_initial_no_store_shows_empty(self):
        t = self._make()
        # No store — _event_labels is empty until refresh is called
        assert hasattr(t, "_event_labels")

    def test_refresh_appeared(self):
        from ui.styles import GREEN
        events = [FakeEvent(ts=1700000000, ip="10.0.0.1", mac=None, event_type="APPEARED")]
        store  = MockStore(event_rows=events)
        t      = self._make(store)
        t.refresh()
        assert len(t._event_labels) >= 1
        assert "10.0.0.1" in t._event_labels[0].text()
        assert GREEN in t._event_labels[0].styleSheet()

    def test_refresh_disappeared(self):
        from ui.styles import RED
        events = [FakeEvent(ts=1700000000, ip="10.0.0.2", mac=None, event_type="DISAPPEARED")]
        store  = MockStore(event_rows=events)
        t      = self._make(store)
        t.refresh()
        assert RED in t._event_labels[0].styleSheet()

    def test_refresh_single_event_no_extra_rows(self):
        events = [FakeEvent(ts=1700000000, ip="10.0.0.1", mac=None, event_type="APPEARED")]
        store  = MockStore(event_rows=events)
        t      = self._make(store)
        t.refresh()
        assert len(t._event_labels) == 1

    def test_refresh_no_store_noop(self):
        t = self._make()
        t.refresh()  # must not raise

    def test_refresh_time_in_label(self):
        import datetime as dt
        ts     = int(dt.datetime(2024, 1, 15, 14, 30).timestamp())
        events = [FakeEvent(ts=ts, ip="10.0.0.1", mac=None, event_type="APPEARED")]
        store  = MockStore(event_rows=events)
        t      = self._make(store)
        t.refresh()
        assert "14:30" in t._event_labels[0].text()


# ---------------------------------------------------------------------------
# OverviewPage — construction
# ---------------------------------------------------------------------------
class TestOverviewPageConstruction:
    def test_all_default_tiles_present(self):
        from ui.pages.overview_page import _DEFAULT_ORDER
        page = _make_overview()
        for tid in _DEFAULT_ORDER:
            assert tid in page._tiles, f"tile '{tid}' not in page._tiles"

    def test_tile_order_matches_default_when_no_settings(self):
        from ui.pages.overview_page import _DEFAULT_ORDER
        with patch("ui.pages.overview_page.QSettings") as MockQS:
            MockQS.return_value.value.return_value = None
            page = _make_overview()
        assert page._tile_order == list(_DEFAULT_ORDER)

    def test_edit_button_exists(self):
        page = _make_overview()
        assert page._edit_btn is not None
        assert page._edit_btn.text() == "Edit Layout"

    def test_grid_container_exists(self):
        page = _make_overview()
        assert page._grid_container is not None

    def test_store_passed_to_tiles(self):
        store = MockStore()
        page  = _make_overview(store)
        assert page._store is store


# ---------------------------------------------------------------------------
# OverviewPage — swap_tiles
# ---------------------------------------------------------------------------
class TestSwapTiles:
    def test_swap_two_tiles(self):
        with patch("ui.pages.overview_page.QSettings") as MockQS:
            MockQS.return_value.value.return_value = None
            page = _make_overview()
        original_order = list(page._tile_order)
        a = original_order[0]
        b = original_order[1]
        page.swap_tiles(a, b)
        assert page._tile_order[0] == b
        assert page._tile_order[1] == a

    def test_swap_same_id_noop(self):
        with patch("ui.pages.overview_page.QSettings") as MockQS:
            MockQS.return_value.value.return_value = None
            page = _make_overview()
        before = list(page._tile_order)
        page.swap_tiles(before[0], before[0])
        assert page._tile_order == before

    def test_swap_unknown_src_noop(self):
        with patch("ui.pages.overview_page.QSettings") as MockQS:
            MockQS.return_value.value.return_value = None
            page = _make_overview()
        before = list(page._tile_order)
        page.swap_tiles("nonexistent", before[0])
        assert page._tile_order == before

    def test_swap_unknown_dst_noop(self):
        with patch("ui.pages.overview_page.QSettings") as MockQS:
            MockQS.return_value.value.return_value = None
            page = _make_overview()
        before = list(page._tile_order)
        page.swap_tiles(before[0], "nonexistent")
        assert page._tile_order == before

    def test_swap_saves_order(self):
        with patch("ui.pages.overview_page.QSettings") as MockQS:
            inst = MockQS.return_value
            inst.value.return_value = None
            page = _make_overview()
            a = page._tile_order[0]
            b = page._tile_order[1]
            page.swap_tiles(a, b)
            inst.setValue.assert_called()


# ---------------------------------------------------------------------------
# OverviewPage — edit mode
# ---------------------------------------------------------------------------
class TestEditMode:
    def _page(self):
        with patch("ui.pages.overview_page.QSettings") as MockQS:
            MockQS.return_value.value.return_value = None
            return _make_overview()

    def test_edit_mode_off_by_default(self):
        page = self._page()
        assert page._edit_mode is False
        assert page._edit_btn.text() == "Edit Layout"

    def test_enable_edit_mode(self):
        page = self._page()
        page._on_edit_toggled(True)
        assert page._edit_mode is True
        assert page._edit_btn.text() == "Save Layout"

    def test_disable_edit_mode(self):
        page = self._page()
        page._on_edit_toggled(True)
        page._on_edit_toggled(False)
        assert page._edit_mode is False
        assert page._edit_btn.text() == "Edit Layout"

    def test_edit_mode_propagates_to_tiles(self):
        page = self._page()
        page._on_edit_toggled(True)
        for tile in page._tiles.values():
            assert tile._edit_mode is True

    def test_disable_saves_order(self):
        with patch("ui.pages.overview_page.QSettings") as MockQS:
            inst = MockQS.return_value
            inst.value.return_value = None
            page = _make_overview()
            page._on_edit_toggled(True)
            page._on_edit_toggled(False)
            inst.setValue.assert_called()


# ---------------------------------------------------------------------------
# OverviewPage — data slots
# ---------------------------------------------------------------------------
class TestDataSlots:
    def _page(self):
        with patch("ui.pages.overview_page.QSettings") as MockQS:
            MockQS.return_value.value.return_value = None
            return _make_overview()

    def test_on_cycle_done_updates_device_count(self):
        page = self._page()
        page.on_cycle_done({"states": {"a": "UP", "b": "DOWN"}, "rtts": {}})
        assert page._tiles["device_count"]._count_lbl._target == 2

    def test_on_cycle_done_updates_rtt_summary(self):
        page = self._page()
        page.on_cycle_done({"states": {}, "rtts": {"a": 30.0}})
        assert "30" in page._tiles["rtt_summary"]._rtt_lbl.text()

    def test_on_cycle_done_empty_result(self):
        page = self._page()
        page.on_cycle_done({})  # must not raise

    def test_on_svc_done_updates_service_status(self):
        page = self._page()
        page.on_svc_done([{"up": True}, {"up": False}])
        assert page._tiles["service_status"]._up_lbl._target == 1

    def test_on_alert_updates_alert_feed(self):
        page = self._page()
        page.on_alert({"severity": "WARNING", "message": "Something bad", "ts": 0})
        assert "Something bad" in page._tiles["alert_feed"]._rows[0].msg.text()

    def test_on_grade_updates_network_grade(self):
        page = self._page()
        page.on_grade("A", 95.0)
        assert page._tiles["network_grade"]._grade_lbl.text() == "A"

    def test_on_cert_done_calls_tls_refresh(self):
        store = MockStore(cert_rows=[FakeCert("h", 443, 200, False)])
        with patch("ui.pages.overview_page.QSettings") as MockQS:
            MockQS.return_value.value.return_value = None
            page = _make_overview(store=store)
        page.on_cert_done([])
        assert page._tiles["tls_status"]._ok_lbl.text() == "1"


# ---------------------------------------------------------------------------
# OverviewPage — QSettings persistence
# ---------------------------------------------------------------------------
def _qs_mock(tile_order_csv=None, hidden_csv=None, layout_ver=None):
    """Return a QSettings mock with per-key value dispatch."""
    from ui.pages.overview_page import _LAYOUT_VER
    ver = str(layout_ver if layout_ver is not None else _LAYOUT_VER)

    def _value(key, default=None):
        if key == "overview/layout_version":
            return ver
        if key == "overview/hidden_tiles":
            return hidden_csv
        if key == "overview/tile_order":
            return tile_order_csv
        return default

    mock = MagicMock()
    mock.value.side_effect = _value
    return mock


class TestPersistence:
    def test_save_order_called_on_swap(self):
        with patch("ui.pages.overview_page.QSettings") as MockQS:
            MockQS.return_value = _qs_mock()
            page = _make_overview()
            a = page._tile_order[0]
            b = page._tile_order[1]
            page.swap_tiles(a, b)
            MockQS.return_value.setValue.assert_any_call(
                "overview/tile_order", ",".join(page._tile_order)
            )

    def test_load_order_from_settings(self):
        from ui.pages.overview_page import _DEFAULT_ORDER
        saved = ",".join(reversed(_DEFAULT_ORDER))
        with patch("ui.pages.overview_page.QSettings") as MockQS:
            MockQS.return_value = _qs_mock(tile_order_csv=saved)
            page = _make_overview()
        assert page._tile_order == list(reversed(_DEFAULT_ORDER))

    def test_load_order_strips_unknown_tile_ids(self):
        from ui.pages.overview_page import _DEFAULT_ORDER
        bad = "device_count,nonexistent_tile," + ",".join(_DEFAULT_ORDER[1:])
        with patch("ui.pages.overview_page.QSettings") as MockQS:
            MockQS.return_value = _qs_mock(tile_order_csv=bad)
            page = _make_overview()
        assert "nonexistent_tile" not in page._tile_order

    def test_load_order_appends_new_tiles_not_in_saved(self):
        from ui.pages.overview_page import _DEFAULT_ORDER
        partial = ",".join(t for t in _DEFAULT_ORDER if t != "event_feed")
        with patch("ui.pages.overview_page.QSettings") as MockQS:
            MockQS.return_value = _qs_mock(tile_order_csv=partial)
            page = _make_overview()
        assert "event_feed" in page._tile_order


# ---------------------------------------------------------------------------
# Layout migration
# ---------------------------------------------------------------------------
class TestLayoutMigration:
    def test_old_version_resets_to_default_order(self):
        from ui.pages.overview_page import _DEFAULT_ORDER
        stale = ",".join(reversed(_DEFAULT_ORDER))
        with patch("ui.pages.overview_page.QSettings") as MockQS:
            MockQS.return_value = _qs_mock(tile_order_csv=stale, layout_ver=1)
            page = _make_overview()
        assert page._tile_order == list(_DEFAULT_ORDER)

    def test_current_version_preserves_saved_order(self):
        from ui.pages.overview_page import _DEFAULT_ORDER
        saved = ",".join(reversed(_DEFAULT_ORDER))
        with patch("ui.pages.overview_page.QSettings") as MockQS:
            MockQS.return_value = _qs_mock(tile_order_csv=saved)
            page = _make_overview()
        assert page._tile_order == list(reversed(_DEFAULT_ORDER))

    def test_corrupt_version_value_treated_as_old(self):
        """Non-numeric layout_version falls back to 1 and triggers migration."""
        from ui.pages.overview_page import _DEFAULT_ORDER
        with patch("ui.pages.overview_page.QSettings") as MockQS:
            MockQS.return_value = _qs_mock(layout_ver="corrupt_string")
            page = _make_overview()
        assert page._tile_order == list(_DEFAULT_ORDER)


# ---------------------------------------------------------------------------
# Tile icons
# ---------------------------------------------------------------------------
class TestTileIcons:
    def test_all_tile_classes_have_tile_icon(self):
        from ui.pages.overview_page import _TILE_CLASSES
        for tid, cls in _TILE_CLASSES.items():
            assert hasattr(cls, "TILE_ICON"), f"{cls.__name__} missing TILE_ICON"
            assert isinstance(cls.TILE_ICON, str) and cls.TILE_ICON, \
                f"{cls.__name__}.TILE_ICON is empty"


# ---------------------------------------------------------------------------
# Uniform tile height
# ---------------------------------------------------------------------------
class TestTileHeight:
    def test_all_tiles_same_fixed_height(self):
        from ui.pages.overview_page import _TILE_CLASSES, _TILE_HEIGHT
        for tid, cls in _TILE_CLASSES.items():
            t = cls()
            assert t.minimumHeight() == _TILE_HEIGHT, \
                f"{cls.__name__} minimumHeight {t.minimumHeight()} != {_TILE_HEIGHT}"
            assert t.maximumHeight() == _TILE_HEIGHT, \
                f"{cls.__name__} maximumHeight {t.maximumHeight()} != {_TILE_HEIGHT}"


# ---------------------------------------------------------------------------
# _reflow ghost-widget fix
# ---------------------------------------------------------------------------
class TestReflowGhostFix:
    def test_tiles_not_in_order_are_hidden(self):
        with patch("ui.pages.overview_page.QSettings") as MockQS:
            MockQS.return_value = _qs_mock()
            page = _make_overview()
        for tid, tile in page._tiles.items():
            if tid in page._tile_order:
                assert not tile.isHidden(), f"{tid} should not be hidden"
            else:
                assert tile.isHidden(), f"{tid} should be hidden"

    def test_removed_tile_hidden_after_reflow(self):
        with patch("ui.pages.overview_page.QSettings") as MockQS:
            MockQS.return_value = _qs_mock()
            page = _make_overview()
        first = page._tile_order[0]
        page._remove_tile(first)
        assert not page._tiles[first].isVisible()


# ---------------------------------------------------------------------------
# Hero strip
# ---------------------------------------------------------------------------
class TestHeroStrip:
    def _page(self):
        with patch("ui.pages.overview_page.QSettings") as MockQS:
            MockQS.return_value = _qs_mock()
            return _make_overview()

    def test_hero_devices_updates_on_cycle_done(self):
        page = self._page()
        page.on_cycle_done({"states": {"a": "UP", "b": "UP", "c": "DOWN"}, "rtts": {}})
        assert "3" in page._hero_devices.text()

    def test_hero_devices_shows_down_count(self):
        page = self._page()
        page.on_cycle_done({"states": {"a": "DOWN"}, "rtts": {}})
        assert "↓" in page._hero_devices.text()

    def test_hero_grade_updates_on_grade(self):
        page = self._page()
        page.on_grade("B", 80.0)
        assert "B" in page._hero_grade.text()

    def test_hero_alerts_increments_on_alert(self):
        page = self._page()
        page.on_alert({"severity": "WARNING", "message": "test", "ts": 0})
        assert "1" in page._hero_alerts.text()
        page.on_alert({"severity": "INFO", "message": "test2", "ts": 1})
        assert "2" in page._hero_alerts.text()

    def test_hero_svc_updates_on_svc_done(self):
        page = self._page()
        page.on_svc_done([{"status": "UP"}, {"status": "DOWN"}])
        assert "1 up" in page._hero_svc.text()


# ---------------------------------------------------------------------------
# Alert navigation
# ---------------------------------------------------------------------------
class TestAlertNavigation:
    def _page(self):
        with patch("ui.pages.overview_page.QSettings") as MockQS:
            MockQS.return_value = _qs_mock()
            return _make_overview()

    def test_host_down_navigates_to_availability_history(self):
        page = self._page()
        received = []
        page.navigate_to.connect(received.append)
        page._on_alert_navigate("HOST_DOWN", "10.0.0.1")
        assert received == ["Availability History"]

    def test_service_alert_navigates_to_service_heartbeat(self):
        page = self._page()
        received = []
        page.navigate_to.connect(received.append)
        page._on_alert_navigate("SERVICE_DOWN", "")
        assert received == ["Service Heartbeat"]

    def test_cert_alert_navigates_to_tls_page(self):
        page = self._page()
        received = []
        page.navigate_to.connect(received.append)
        page._on_alert_navigate("CERT_EXPIRY", "")
        assert received == ["TLS & Exposure"]

    def test_rtt_alert_navigates_to_dns_stability(self):
        page = self._page()
        received = []
        page.navigate_to.connect(received.append)
        page._on_alert_navigate("RTT_THRESHOLD", "10.0.0.1")
        assert received == ["DNS & Stability"]

    def test_new_device_alert_navigates_to_devices(self):
        page = self._page()
        received = []
        page.navigate_to.connect(received.append)
        page._on_alert_navigate("NEW_DEVICE", "10.0.0.1")
        assert received == ["Devices"]

    def test_unknown_rule_type_navigates_to_devices_page(self):
        page = self._page()
        received = []
        page.navigate_to.connect(received.append)
        page._on_alert_navigate("", "")
        assert received == ["Devices"]


# ---------------------------------------------------------------------------
# Share Card button
# ---------------------------------------------------------------------------
class TestShareCard:
    def test_share_btn_enabled_by_default(self):
        with patch("ui.pages.overview_page.QSettings") as MockQS:
            MockQS.return_value = _qs_mock()
            page = _make_overview()
        assert page._share_btn.isEnabled()

    def test_share_btn_still_enabled_after_set_card_data(self):
        with patch("ui.pages.overview_page.QSettings") as MockQS:
            MockQS.return_value = _qs_mock()
            page = _make_overview()
        page.set_card_data(MagicMock())
        assert page._share_btn.isEnabled()
