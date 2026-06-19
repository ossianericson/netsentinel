"""Tests for modules/morning_briefing.py (S8-1 morning briefing)."""
import time
from unittest.mock import MagicMock


def _make_store(alerts=None, joined=None, speed_rows=None):
    store = MagicMock()
    store.get_recent_alerts.return_value = alerts or []
    store.query_device_events.return_value = joined or []
    store.query_speed_test_history.return_value = speed_rows or []
    return store


def _settings(values: dict):
    def _get(key, *a, **kw):
        return values.get(key)
    def _set(key, val):
        values[key] = val
    return _get, _set


# ── Import ────────────────────────────────────────────────────────────────────

def test_import():
    from modules.morning_briefing import check_and_build_briefing, BriefingResult
    assert check_and_build_briefing
    assert BriefingResult


# ── Disabled by default ───────────────────────────────────────────────────────

def test_disabled_by_default_returns_none():
    from modules.morning_briefing import check_and_build_briefing
    store = _make_store()
    get, set_ = _settings({})
    assert check_and_build_briefing(store, get, set_) is None


# ── Hour gating ───────────────────────────────────────────────────────────────

def test_before_configured_hour_returns_none(monkeypatch):
    from modules.morning_briefing import check_and_build_briefing, ENABLED_KEY, HOUR_KEY
    store = _make_store()
    get, set_ = _settings({ENABLED_KEY: True, HOUR_KEY: 8})
    fake_localtime = time.struct_time((2024, 1, 15, 7, 0, 0, 0, 15, 0))
    monkeypatch.setattr("time.localtime", lambda: fake_localtime)
    assert check_and_build_briefing(store, get, set_) is None


# ── Already sent today ────────────────────────────────────────────────────────

def test_already_sent_today_returns_none(monkeypatch):
    from modules.morning_briefing import check_and_build_briefing, ENABLED_KEY, HOUR_KEY, LAST_SENT_KEY
    store = _make_store()
    today = "2024-01-15"
    get, set_ = _settings({ENABLED_KEY: True, HOUR_KEY: 8, LAST_SENT_KEY: today})
    fake_localtime = time.struct_time((2024, 1, 15, 9, 0, 0, 0, 15, 0))
    monkeypatch.setattr("time.localtime", lambda: fake_localtime)
    monkeypatch.setattr("time.strftime", lambda fmt, *a: today)
    assert check_and_build_briefing(store, get, set_) is None


# ── Due briefing returns three bullets ────────────────────────────────────────

def test_due_briefing_returns_three_bullets(monkeypatch):
    from modules.morning_briefing import check_and_build_briefing, ENABLED_KEY, HOUR_KEY, BriefingResult
    store = _make_store()
    get, set_ = _settings({ENABLED_KEY: True, HOUR_KEY: 8})
    fake_localtime = time.struct_time((2024, 1, 15, 9, 0, 0, 0, 15, 0))
    monkeypatch.setattr("time.localtime", lambda: fake_localtime)
    monkeypatch.setattr("time.strftime", lambda fmt, *a: "2024-01-15")
    result = check_and_build_briefing(store, get, set_)
    assert isinstance(result, BriefingResult)
    assert len(result.bullets) == 3


def test_last_sent_key_persisted(monkeypatch):
    from modules.morning_briefing import check_and_build_briefing, ENABLED_KEY, HOUR_KEY, LAST_SENT_KEY
    state = {ENABLED_KEY: True, HOUR_KEY: 8}
    get, set_ = _settings(state)
    store = _make_store()
    fake_localtime = time.struct_time((2024, 1, 15, 9, 0, 0, 0, 15, 0))
    monkeypatch.setattr("time.localtime", lambda: fake_localtime)
    monkeypatch.setattr("time.strftime", lambda fmt, *a: "2024-01-15")
    check_and_build_briefing(store, get, set_)
    assert state.get(LAST_SENT_KEY) == "2024-01-15"


# ── Bullet content ─────────────────────────────────────────────────────────────

def test_overnight_bullet_reports_new_devices_and_alerts():
    from modules.morning_briefing import build_briefing_bullets
    joined = [MagicMock(), MagicMock()]
    alerts = [{"severity": "WARNING"}]
    store = _make_store(alerts=alerts, joined=joined)
    bullets = build_briefing_bullets(store)
    assert any("2 new device" in b for b in bullets)
    assert any("1 alert" in b for b in bullets)


def test_overnight_bullet_quiet_when_nothing_happened():
    from modules.morning_briefing import build_briefing_bullets
    store = _make_store()
    bullets = build_briefing_bullets(store)
    assert any("nothing unusual" in b for b in bullets)


def test_quick_stat_bullet_uses_latest_speed_test():
    from modules.morning_briefing import build_briefing_bullets
    speed_row = MagicMock()
    speed_row.download_mbps = 123.4
    store = _make_store(speed_rows=[speed_row])
    bullets = build_briefing_bullets(store)
    assert any("123 Mbps" in b for b in bullets)


def test_quick_stat_bullet_no_recent_speed_test():
    from modules.morning_briefing import build_briefing_bullets
    store = _make_store(speed_rows=[])
    bullets = build_briefing_bullets(store)
    assert any("No speed test" in b for b in bullets)


def test_bullets_survive_store_exceptions():
    """All bullet builders must degrade gracefully when store queries raise."""
    from modules.morning_briefing import build_briefing_bullets
    store = MagicMock()
    store.get_recent_alerts.side_effect = RuntimeError("db error")
    store.query_device_events.side_effect = RuntimeError("db error")
    store.query_speed_test_history.side_effect = RuntimeError("db error")
    bullets = build_briefing_bullets(store)
    assert len(bullets) == 3
