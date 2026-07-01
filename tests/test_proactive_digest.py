"""Tests for modules/proactive_digest.py (Sprint 2 foundation)."""
import time


def _settings(values: dict):
    def _get(key, *a, **kw):
        return values.get(key)
    def _set(key, val):
        values[key] = val
    return _get, _set


# ── Import ────────────────────────────────────────────────────────────────────

def test_import():
    from modules.proactive_digest import DigestConfig, is_due
    assert DigestConfig
    assert is_due


# ── Disabled by default ───────────────────────────────────────────────────────

def test_disabled_returns_false():
    from modules.proactive_digest import DigestConfig, is_due
    config = DigestConfig("d/enabled", "d/hour", "d/last_sent")
    get, set_ = _settings({})
    assert is_due(config, get, set_) is False


# ── Hour gating ───────────────────────────────────────────────────────────────

def test_before_configured_hour_returns_false(monkeypatch):
    from modules.proactive_digest import DigestConfig, is_due
    config = DigestConfig("d/enabled", "d/hour", "d/last_sent")
    get, set_ = _settings({"d/enabled": True, "d/hour": 8})
    fake_localtime = time.struct_time((2024, 1, 15, 7, 0, 0, 0, 15, 0))
    monkeypatch.setattr("time.localtime", lambda: fake_localtime)
    assert is_due(config, get, set_) is False


def test_at_or_after_configured_hour_returns_true(monkeypatch):
    from modules.proactive_digest import DigestConfig, is_due
    config = DigestConfig("d/enabled", "d/hour", "d/last_sent")
    get, set_ = _settings({"d/enabled": True, "d/hour": 8})
    fake_localtime = time.struct_time((2024, 1, 15, 9, 0, 0, 0, 15, 0))
    monkeypatch.setattr("time.localtime", lambda: fake_localtime)
    monkeypatch.setattr("time.strftime", lambda fmt, *a: "2024-01-15")
    assert is_due(config, get, set_) is True


# ── Already sent today (day-rollover) ─────────────────────────────────────────

def test_already_sent_today_returns_false(monkeypatch):
    from modules.proactive_digest import DigestConfig, is_due
    config = DigestConfig("d/enabled", "d/hour", "d/last_sent")
    today = "2024-01-15"
    get, set_ = _settings({"d/enabled": True, "d/hour": 8, "d/last_sent": today})
    fake_localtime = time.struct_time((2024, 1, 15, 9, 0, 0, 0, 15, 0))
    monkeypatch.setattr("time.localtime", lambda: fake_localtime)
    monkeypatch.setattr("time.strftime", lambda fmt, *a: today)
    assert is_due(config, get, set_) is False


def test_new_day_after_prior_send_returns_true(monkeypatch):
    from modules.proactive_digest import DigestConfig, is_due
    config = DigestConfig("d/enabled", "d/hour", "d/last_sent")
    state = {"d/enabled": True, "d/hour": 8, "d/last_sent": "2024-01-14"}
    get, set_ = _settings(state)
    fake_localtime = time.struct_time((2024, 1, 15, 9, 0, 0, 0, 15, 0))
    monkeypatch.setattr("time.localtime", lambda: fake_localtime)
    monkeypatch.setattr("time.strftime", lambda fmt, *a: "2024-01-15")
    assert is_due(config, get, set_) is True
    assert state["d/last_sent"] == "2024-01-15"


# ── Default hour fallback ─────────────────────────────────────────────────────

def test_missing_hour_uses_config_default(monkeypatch):
    from modules.proactive_digest import DigestConfig, is_due
    config = DigestConfig("d/enabled", "d/hour", "d/last_sent", default_hour=8)
    get, set_ = _settings({"d/enabled": True})
    fake_localtime = time.struct_time((2024, 1, 15, 9, 0, 0, 0, 15, 0))
    monkeypatch.setattr("time.localtime", lambda: fake_localtime)
    monkeypatch.setattr("time.strftime", lambda fmt, *a: "2024-01-15")
    assert is_due(config, get, set_) is True


# ── Two independent digests don't interfere ───────────────────────────────────

def test_two_digest_configs_track_independently(monkeypatch):
    from modules.proactive_digest import DigestConfig, is_due
    briefing = DigestConfig("briefing/enabled", "briefing/hour", "briefing/last_sent_day")
    other = DigestConfig("other/enabled", "other/hour", "other/last_sent_day")
    state = {
        "briefing/enabled": True, "briefing/hour": 8, "briefing/last_sent_day": "2024-01-15",
        "other/enabled": True, "other/hour": 8,
    }
    get, set_ = _settings(state)
    fake_localtime = time.struct_time((2024, 1, 15, 9, 0, 0, 0, 15, 0))
    monkeypatch.setattr("time.localtime", lambda: fake_localtime)
    monkeypatch.setattr("time.strftime", lambda fmt, *a: "2024-01-15")
    assert is_due(briefing, get, set_) is False
    assert is_due(other, get, set_) is True
    assert state["other/last_sent_day"] == "2024-01-15"
