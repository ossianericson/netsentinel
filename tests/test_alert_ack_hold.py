"""
tests/test_alert_ack_hold.py — acknowledging an alert suppresses re-fires of the
same (rule, host) while the condition is still ongoing (Phase 3, notifications
rework).

Mechanism this covers. AlertEngine._fire_if_cooled() dedups on
`f"{rule.name}::{host}"` against `rule.cooldown_s` only — 300 s for most rules.
A condition that stays true (a service that is genuinely still down, a device
that is still gone) therefore re-alerts every 5 minutes forever, and
acknowledging does nothing to stop it: ack marks a *past row* in the DB, it
never touched the engine. Measured in the user's live DB: "Service Down"
fired 247 times with a 5.0-minute median gap for the same host, and 53 unacked
"Device Gone" alerts accumulated in 24 h.

Acking now records a hold on that (rule, host) key: nothing fires for
ack_hold_seconds (default 24 h, owner-configurable). A resolution event clears
the hold, so a genuinely new occurrence after recovery still alerts.

RULE-T3: these fail before the fix (no set_ack_hold_seconds/note_acknowledged/
load_ack_holds on AlertEngine).
"""
from __future__ import annotations

import time

from modules.alert_engine import AlertEngine
from modules.alert_types import AlertRule


RULE_NAME = "Service Down"
HOST = "192.168.68.61"


def _engine() -> AlertEngine:
    rule = AlertRule(
        name=RULE_NAME,
        rule_type="SERVICE_DOWN",
        host=None,
        cooldown_s=300,
        enabled=True,
    )
    return AlertEngine(store=None, rules=[rule])


def _rule(engine: AlertEngine) -> AlertRule:
    return engine._rules[0]


def _fire(engine: AlertEngine, now: int):
    return engine._fire_if_cooled(
        _rule(engine), HOST, now, "service down", "CRITICAL", None
    )


# ── Baseline: the cooldown behaviour that exists today ────────────────────────

def test_cooldown_alone_lets_an_ongoing_condition_refire_every_5_minutes():
    engine = _engine()
    now = int(time.time())

    assert _fire(engine, now) is not None
    assert _fire(engine, now + 60) is None, "inside cooldown"
    assert _fire(engine, now + 301) is not None, "cooldown expired — refires"


# ── Ack hold ──────────────────────────────────────────────────────────────────

def test_acknowledging_suppresses_the_next_refire():
    engine = _engine()
    now = int(time.time())
    assert _fire(engine, now) is not None

    engine.note_acknowledged(RULE_NAME, HOST, ts=now + 10)

    assert _fire(engine, now + 301) is None, (
        "an acknowledged, still-ongoing condition must not re-alert 5 minutes later"
    )
    assert _fire(engine, now + 3600 * 12) is None


def test_hold_expires_after_the_configured_window():
    engine = _engine()
    now = int(time.time())
    engine.note_acknowledged(RULE_NAME, HOST, ts=now)

    assert _fire(engine, now + 3600 * 23) is None
    assert _fire(engine, now + 3600 * 25) is not None, (
        "the hold is a mute, not a permanent block — the condition is still real"
    )


def test_ack_hold_window_is_configurable():
    engine = _engine()
    engine.set_ack_hold_seconds(3600)
    now = int(time.time())
    engine.note_acknowledged(RULE_NAME, HOST, ts=now)

    assert _fire(engine, now + 1800) is None
    assert _fire(engine, now + 3700) is not None


def test_ack_hold_of_zero_disables_the_feature():
    engine = _engine()
    engine.set_ack_hold_seconds(0)
    now = int(time.time())
    assert _fire(engine, now) is not None
    engine.note_acknowledged(RULE_NAME, HOST, ts=now)

    assert _fire(engine, now + 301) is not None, (
        "0 must restore the pre-fix cooldown-only behaviour"
    )


def test_hold_is_scoped_to_one_rule_and_host():
    engine = _engine()
    now = int(time.time())
    engine.note_acknowledged(RULE_NAME, HOST, ts=now)

    other = engine._fire_if_cooled(
        _rule(engine), "192.168.68.99", now + 301, "service down", "CRITICAL", None
    )
    assert other is not None, "acking one host must not mute a different host"


# ── Resolution clears the hold ────────────────────────────────────────────────

def test_resolution_clears_the_hold_so_a_new_occurrence_alerts_again():
    engine = _engine()
    now = int(time.time())
    engine.note_acknowledged(RULE_NAME, HOST, ts=now)
    assert _fire(engine, now + 301) is None

    engine.clear_ack_hold(RULE_NAME, HOST)

    assert _fire(engine, now + 302) is not None, (
        "once the condition resolves, the next occurrence is genuinely new"
    )


# ── Seeding from persisted acks ───────────────────────────────────────────────

def test_load_ack_holds_survives_a_restart():
    """_last_fired is in-memory only, so a restart used to wipe every hold.
    Holds are re-seeded from alert_fired.acked_ts — no schema change needed."""
    now = int(time.time())
    engine = _engine()

    engine.load_ack_holds([
        {"rule_name": RULE_NAME, "host": HOST, "acked_ts": now},
        {"rule_name": RULE_NAME, "host": "192.168.68.99", "acked_ts": None},
    ])

    assert _fire(engine, now + 301) is None
    other = engine._fire_if_cooled(
        _rule(engine), "192.168.68.99", now + 301, "down", "CRITICAL", None
    )
    assert other is not None, "an unacked row must not create a hold"


def test_load_ack_holds_keeps_the_most_recent_ack_per_key():
    now = int(time.time())
    engine = _engine()
    engine.set_ack_hold_seconds(3600)

    engine.load_ack_holds([
        {"rule_name": RULE_NAME, "host": HOST, "acked_ts": now - 7200},
        {"rule_name": RULE_NAME, "host": HOST, "acked_ts": now},
    ])

    assert _fire(engine, now + 60) is None, (
        "an older ack for the same key must not shadow the newest one"
    )


def test_load_ack_holds_tolerates_malformed_rows():
    engine = _engine()
    engine.load_ack_holds([
        {},
        {"rule_name": RULE_NAME},
        {"host": HOST, "acked_ts": "not-a-number"},
        None,
    ])
    assert _fire(engine, int(time.time())) is not None


# ── Resolutions are never muted ───────────────────────────────────────────────

def test_ack_hold_does_not_suppress_resolution_alerts():
    """_fire_resolution deliberately skips cooldown; it must skip the ack hold
    too, or a recovery notice gets swallowed by the ack of the outage."""
    engine = _engine()
    now = int(time.time())
    engine.note_acknowledged(RULE_NAME, HOST, ts=now)

    resolved = engine._fire_resolution(_rule(engine), HOST, now + 60, "service back up")

    assert resolved is not None
