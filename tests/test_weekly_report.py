"""Tests for modules/weekly_report.py (S8-3 weekly report card)."""
from unittest.mock import MagicMock


def _speed_row(dl):
    r = MagicMock()
    r.download_mbps = dl
    return r


def test_import():
    from modules.weekly_report import build_weekly_report_bullets
    assert build_weekly_report_bullets


def test_full_bullets_built_from_store_data():
    from modules.weekly_report import build_weekly_report_bullets
    store = MagicMock()
    store.query_uptime_table.return_value = [{"168.0": 99.6}]
    store.query_speed_test_history.return_value = [_speed_row(87.0), _speed_row(89.0)]
    store.query_device_events.return_value = [MagicMock(), MagicMock()]
    store.query_app_traffic_category_totals.return_value = {
        "Streaming": 680_000_000_000, "Web": 320_000_000_000,
    }
    bullets = build_weekly_report_bullets(store, plan_speed_mbps=100.0)
    assert len(bullets) == 4
    assert "uptime" in bullets[0]
    assert "99.6%" in bullets[0]
    assert "88 Mbps" in bullets[1] or "87 Mbps" in bullets[1] or "89 Mbps" in bullets[1]
    assert "plan: 100 Mbps" in bullets[1]
    assert "2 new device" in bullets[2]
    assert "streaming was 68%" in bullets[3]


def test_no_new_devices_says_so():
    from modules.weekly_report import build_weekly_report_bullets
    store = MagicMock()
    store.query_uptime_table.return_value = []
    store.query_speed_test_history.return_value = []
    store.query_device_events.return_value = []
    store.query_app_traffic_category_totals.return_value = {}
    bullets = build_weekly_report_bullets(store)
    assert any("No new devices" in b for b in bullets)


def test_zero_plan_speed_omits_plan_suffix():
    from modules.weekly_report import build_weekly_report_bullets
    store = MagicMock()
    store.query_uptime_table.return_value = []
    store.query_speed_test_history.return_value = [_speed_row(50.0)]
    store.query_device_events.return_value = []
    store.query_app_traffic_category_totals.return_value = {}
    bullets = build_weekly_report_bullets(store, plan_speed_mbps=0.0)
    speed_bullets = [b for b in bullets if "Speed averaged" in b]
    assert speed_bullets and "plan:" not in speed_bullets[0]


def test_bullets_skip_sections_with_no_data():
    from modules.weekly_report import build_weekly_report_bullets
    store = MagicMock()
    store.query_uptime_table.return_value = []
    store.query_speed_test_history.return_value = []
    store.query_device_events.return_value = []
    store.query_app_traffic_category_totals.return_value = {}
    bullets = build_weekly_report_bullets(store)
    assert len(bullets) == 1   # only the "no new devices" bullet survives
    assert "No new devices" in bullets[0]


def test_bullets_survive_store_exceptions():
    from modules.weekly_report import build_weekly_report_bullets
    store = MagicMock()
    store.query_uptime_table.side_effect = RuntimeError("db error")
    store.query_speed_test_history.side_effect = RuntimeError("db error")
    store.query_device_events.side_effect = RuntimeError("db error")
    store.query_app_traffic_category_totals.side_effect = RuntimeError("db error")
    bullets = build_weekly_report_bullets(store)
    assert bullets == []
