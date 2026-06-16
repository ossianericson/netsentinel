"""Tests for modules/quiet_notifier.py (S4-5 all-quiet notification)."""
import time
from unittest.mock import MagicMock


def _make_store(alerts=None, devices=None):
    store = MagicMock()
    store.get_recent_alerts.return_value = alerts or []
    store.query_known_devices.return_value = devices or []
    return store


def _settings(values: dict):
    def _get(key, *a, **kw):
        return values.get(key)
    def _set(key, val):
        values[key] = val
    return _get, _set


# ── Import ────────────────────────────────────────────────────────────────────

def test_import():
    from modules.quiet_notifier import check_and_maybe_notify, QuietResult
    assert check_and_maybe_notify
    assert QuietResult


# ── Disabled by default ───────────────────────────────────────────────────────

def test_disabled_by_default_returns_none():
    from modules.quiet_notifier import check_and_maybe_notify
    store = _make_store()
    get, set_ = _settings({})    # no ENABLED_KEY set
    result = check_and_maybe_notify(store, get, set_)
    assert result is None


# ── Hour gating ───────────────────────────────────────────────────────────────

def test_before_configured_hour_returns_none(monkeypatch):
    from modules.quiet_notifier import check_and_maybe_notify, ENABLED_KEY, NOTIFY_HOUR_KEY
    store = _make_store()
    get, set_ = _settings({ENABLED_KEY: True, NOTIFY_HOUR_KEY: 8})
    # Simulate current hour = 7 (before configured 8am)
    fake_localtime = time.struct_time((2024, 1, 15, 7, 0, 0, 0, 15, 0))
    monkeypatch.setattr("time.localtime", lambda: fake_localtime)
    result = check_and_maybe_notify(store, get, set_)
    assert result is None


# ── Already sent today ────────────────────────────────────────────────────────

def test_already_sent_today_returns_none(monkeypatch):
    from modules.quiet_notifier import (
        check_and_maybe_notify, ENABLED_KEY, LAST_SENT_KEY, NOTIFY_HOUR_KEY,
    )
    store = _make_store()
    today = "2024-01-15"
    get, set_ = _settings({
        ENABLED_KEY: True,
        LAST_SENT_KEY: today,
        NOTIFY_HOUR_KEY: 8,
    })
    fake_localtime = time.struct_time((2024, 1, 15, 9, 0, 0, 0, 15, 0))
    monkeypatch.setattr("time.localtime", lambda: fake_localtime)
    monkeypatch.setattr("time.strftime", lambda fmt, *a: today)
    result = check_and_maybe_notify(store, get, set_)
    assert result is None


# ── Alerts fired yesterday — no quiet notification ────────────────────────────

def test_critical_alert_yesterday_returns_none(monkeypatch):
    from modules.quiet_notifier import check_and_maybe_notify, ENABLED_KEY, NOTIFY_HOUR_KEY
    alerts = [{"severity": "CRITICAL", "rule_name": "Host Down", "host": "8.8.8.8"}]
    store = _make_store(alerts=alerts)
    get, set_ = _settings({ENABLED_KEY: True, NOTIFY_HOUR_KEY: 8})
    fake_localtime = time.struct_time((2024, 1, 15, 9, 0, 0, 0, 15, 0))
    monkeypatch.setattr("time.localtime", lambda: fake_localtime)
    monkeypatch.setattr("time.strftime", lambda fmt, *a: "2024-01-15")
    result = check_and_maybe_notify(store, get, set_)
    assert result is None


# ── Quiet day — notification returned ────────────────────────────────────────

def test_quiet_day_returns_result(monkeypatch):
    from modules.quiet_notifier import check_and_maybe_notify, ENABLED_KEY, NOTIFY_HOUR_KEY, QuietResult
    store = _make_store(alerts=[])   # no alerts
    get, set_ = _settings({ENABLED_KEY: True, NOTIFY_HOUR_KEY: 8})
    fake_localtime = time.struct_time((2024, 1, 15, 9, 0, 0, 0, 15, 0))
    monkeypatch.setattr("time.localtime", lambda: fake_localtime)
    monkeypatch.setattr("time.strftime", lambda fmt, *a: "2024-01-15")
    result = check_and_maybe_notify(store, get, set_)
    assert isinstance(result, QuietResult)
    assert "healthy" in result.headline.lower()
    assert result.alert_count == 0


# ── Quiet day — HEALTHY alerts do not block ───────────────────────────────────

def test_healthy_alerts_do_not_block_quiet(monkeypatch):
    from modules.quiet_notifier import check_and_maybe_notify, ENABLED_KEY, NOTIFY_HOUR_KEY, QuietResult
    # HEALTHY severity should NOT count as a noisy alert
    alerts = [{"severity": "HEALTHY", "rule_name": "Host Down", "host": "8.8.8.8"}]
    store = _make_store(alerts=alerts)
    get, set_ = _settings({ENABLED_KEY: True, NOTIFY_HOUR_KEY: 8})
    fake_localtime = time.struct_time((2024, 1, 15, 9, 0, 0, 0, 15, 0))
    monkeypatch.setattr("time.localtime", lambda: fake_localtime)
    monkeypatch.setattr("time.strftime", lambda fmt, *a: "2024-01-15")
    result = check_and_maybe_notify(store, get, set_)
    assert isinstance(result, QuietResult)


# ── Last-sent key is persisted ────────────────────────────────────────────────

def test_last_sent_key_persisted(monkeypatch):
    from modules.quiet_notifier import check_and_maybe_notify, ENABLED_KEY, NOTIFY_HOUR_KEY, LAST_SENT_KEY
    state = {ENABLED_KEY: True, NOTIFY_HOUR_KEY: 8}
    get, set_ = _settings(state)
    store = _make_store(alerts=[])
    fake_localtime = time.struct_time((2024, 1, 15, 9, 0, 0, 0, 15, 0))
    monkeypatch.setattr("time.localtime", lambda: fake_localtime)
    monkeypatch.setattr("time.strftime", lambda fmt, *a: "2024-01-15")
    check_and_maybe_notify(store, get, set_)
    assert state.get(LAST_SENT_KEY) == "2024-01-15"
