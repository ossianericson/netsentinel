"""Tests for modules/digest_bullets.py — Sprint 4 overnight digest bullets.

Covers: SERVICE_DOWN + filtered-classification rollup, BASELINE_DROP rollup,
each gated on the *other* feature's own opt-in QSettings key (not Morning
Briefing's own enabled flag), the "nothing happened" fallback, and the
MAX_BULLETS flood/truncation case.
"""
from unittest.mock import MagicMock

from modules.alert_suppressor import rule_settings_key


def _make_store(alerts=None):
    store = MagicMock()
    store.get_recent_alerts.return_value = alerts or []
    return store


def _settings(values: dict):
    def _get(key, *a, **kw):
        return values.get(key)
    return _get


_SVC_KEY = rule_settings_key("Service Down")
_SPEED_KEY = "speedtest/scheduled_enabled"


# ── Import ────────────────────────────────────────────────────────────────────

def test_import():
    from modules.digest_bullets import build_digest_bullets, MAX_BULLETS
    assert build_digest_bullets
    assert MAX_BULLETS == 5


# ── Nothing happened fallback ──────────────────────────────────────────────────

def test_nothing_happened_returns_empty_list():
    from modules.digest_bullets import build_digest_bullets
    store = _make_store()
    get = _settings({_SVC_KEY: True, _SPEED_KEY: True})
    assert build_digest_bullets(store, get) == []


def test_both_features_disabled_returns_empty_even_with_alerts():
    from modules.digest_bullets import build_digest_bullets
    alerts = [{"rule_name": "Service Down", "host": "10.0.0.5:443", "message": "down"}]
    store = _make_store(alerts=alerts)
    get = _settings({})  # neither opt-in key set
    assert build_digest_bullets(store, get) == []


# ── Service health bullet ──────────────────────────────────────────────────────

def test_service_down_bullet_appears_when_enabled():
    from modules.digest_bullets import build_digest_bullets
    alerts = [{"rule_name": "Service Down", "host": "10.0.0.5:443", "message": "10.0.0.5:443 down."}]
    store = _make_store(alerts=alerts)
    get = _settings({_SVC_KEY: True})
    bullets = build_digest_bullets(store, get)
    assert any("10.0.0.5:443" in b for b in bullets)


def test_service_down_bullet_absent_when_rule_disabled():
    from modules.digest_bullets import build_digest_bullets
    alerts = [{"rule_name": "Service Down", "host": "10.0.0.5:443", "message": "down"}]
    store = _make_store(alerts=alerts)
    get = _settings({_SVC_KEY: False})
    assert build_digest_bullets(store, get) == []


def test_filtered_classification_is_called_out_distinctly():
    from modules.digest_bullets import build_digest_bullets
    from modules.service_escalation import layer_to_message
    _, filtered_msg = layer_to_message("filtered", "example.com", 443)
    alerts = [{"rule_name": "Service Down", "host": "example.com:443", "message": filtered_msg}]
    store = _make_store(alerts=alerts)
    get = _settings({_SVC_KEY: True})
    bullets = build_digest_bullets(store, get)
    assert any("filtered" in b.lower() and "not a real outage" in b for b in bullets)


def test_non_filtered_service_down_does_not_claim_filtered():
    from modules.digest_bullets import build_digest_bullets
    from modules.service_escalation import layer_to_message
    _, outage_msg = layer_to_message("remote_outage", "example.com", 443)
    alerts = [{"rule_name": "Service Down", "host": "example.com:443", "message": outage_msg}]
    store = _make_store(alerts=alerts)
    get = _settings({_SVC_KEY: True})
    bullets = build_digest_bullets(store, get)
    assert not any("filtered" in b.lower() for b in bullets)


def test_service_down_dedupes_by_host():
    from modules.digest_bullets import build_digest_bullets
    alerts = [
        {"rule_name": "Service Down", "host": "10.0.0.5:443", "message": "down"},
        {"rule_name": "Service Down", "host": "10.0.0.5:443", "message": "down again"},
    ]
    store = _make_store(alerts=alerts)
    get = _settings({_SVC_KEY: True})
    bullets = build_digest_bullets(store, get)
    assert len(bullets) == 1


# ── Speed trend bullet ─────────────────────────────────────────────────────────

def test_speed_trend_bullet_appears_when_scheduling_enabled():
    from modules.digest_bullets import build_digest_bullets
    alerts = [{"rule_name": "Baseline Speed Drop", "host": "speedtest",
               "message": "Download down 87% - 94 Mbps vs your usual ~741 Mbps"}]
    store = _make_store(alerts=alerts)
    get = _settings({_SPEED_KEY: True})
    bullets = build_digest_bullets(store, get)
    assert any("Speed trend" in b and "94 Mbps" in b for b in bullets)


def test_speed_trend_bullet_absent_when_scheduling_disabled():
    """Plan's explicit instruction: don't mention speed trends if scheduled testing is off."""
    from modules.digest_bullets import build_digest_bullets
    alerts = [{"rule_name": "Baseline Speed Drop", "host": "speedtest", "message": "big drop"}]
    store = _make_store(alerts=alerts)
    get = _settings({_SPEED_KEY: False})
    assert build_digest_bullets(store, get) == []


# ── Truncation / flood case ────────────────────────────────────────────────────

def test_flood_of_alerts_is_capped_at_max_bullets():
    from modules.digest_bullets import build_digest_bullets, MAX_BULLETS
    alerts = [
        {"rule_name": "Service Down", "host": f"10.0.0.{i}:443", "message": "down"}
        for i in range(20)
    ]
    store = _make_store(alerts=alerts)
    get = _settings({_SVC_KEY: True})
    bullets = build_digest_bullets(store, get)
    assert len(bullets) == MAX_BULLETS
    assert bullets[-1].startswith("+")
    assert "more" in bullets[-1]


def test_store_exceptions_degrade_gracefully():
    from modules.digest_bullets import build_digest_bullets
    store = MagicMock()
    store.get_recent_alerts.side_effect = RuntimeError("db error")
    get = _settings({_SVC_KEY: True, _SPEED_KEY: True})
    assert build_digest_bullets(store, get) == []
