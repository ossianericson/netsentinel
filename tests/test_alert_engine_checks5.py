"""Phase 4 C4 — INFRA_UNREACHABLE (_AlertChecksMixin5).

`PluginPollingWorker` emits `error(str)` when a registered piece of
infrastructure — modem, router, AP, switch — stops answering. That signal
reached the plugin card's health counter and nothing else, so the modem could
be unplugged and the app would grey out a card without ever alerting.

The rule is edge-triggered through `modules.evidence.EvidenceGate` rather than a
hand-rolled streak dict: one alert per outage episode, a resolution when it
comes back, and nothing at all for a single transient poll failure.
"""
from __future__ import annotations

from modules.alert_engine import AlertEngine, AlertRule


def _engine(**kw):
    kw.setdefault("cooldown_s", 0)
    kw.setdefault("enabled", True)
    return AlertEngine(rules=[
        AlertRule(name="Infra Unreachable", rule_type="INFRA_UNREACHABLE", **kw)
    ])


def _down(engine, key="modem-1", n=1, label="ZTE MC889", reason="timeout", ts=1000):
    out = []
    for i in range(n):
        out += engine.evaluate_infra_unreachable_checks(
            key, True, label=label, reason=reason, ts=ts + i * 30,
        )
    return out


def _up(engine, key="modem-1", label="ZTE MC889", ts=2000):
    return engine.evaluate_infra_unreachable_checks(key, False, label=label, ts=ts)


# ── Import / registration ────────────────────────────────────────────────────

def test_import():
    from modules.alert_engine_checks5 import _AlertChecksMixin5
    assert _AlertChecksMixin5


def test_engine_exposes_the_check():
    assert hasattr(AlertEngine(rules=[]), "evaluate_infra_unreachable_checks")


# ── The edge ─────────────────────────────────────────────────────────────────

def test_single_failed_poll_does_not_alert():
    """One timeout is a blip, not an outage."""
    assert _down(_engine(), n=1) == []


def test_fires_once_the_streak_is_confirmed():
    engine = _engine()
    fired = _down(engine, n=2)
    assert len(fired) == 1
    assert fired[0].rule_type == "INFRA_UNREACHABLE"
    assert fired[0].severity == "CRITICAL"
    assert "ZTE MC889" in fired[0].message


def test_does_not_repeat_while_the_outage_continues():
    """The Phase 0 defect this whole program exists to stop."""
    engine = _engine()
    fired = _down(engine, n=40)
    assert len(fired) == 1, (
        f"an outage must produce one alert, not one per poll; got {len(fired)}"
    )


def test_recovery_fires_a_resolution():
    engine = _engine()
    _down(engine, n=2)
    fired = _up(engine)
    assert len(fired) == 1
    assert fired[0].is_resolution is True
    assert fired[0].severity == "HEALTHY"


def test_recovery_without_a_prior_alert_is_silent():
    """A blip that self-heals must not produce a 'back online' claim."""
    engine = _engine()
    _down(engine, n=1)
    assert _up(engine) == []


def test_a_second_outage_can_alert_again():
    engine = _engine()
    _down(engine, n=2)
    _up(engine)
    fired = _down(engine, n=2, ts=3000)
    assert len(fired) == 1, "a genuinely new episode must be allowed to speak"


def test_healthy_polls_do_not_accumulate_state():
    """The gate sees every poll for the life of the process — no leak."""
    engine = _engine()
    for i in range(50):
        engine.evaluate_infra_unreachable_checks(f"dev-{i}", False, ts=1000 + i)
    assert engine._infra_gate is None or engine._infra_gate.tracked_keys() == 0


def test_each_device_tracks_its_own_episode():
    engine = _engine()
    _down(engine, key="modem-1", n=2)
    fired = _down(engine, key="router-1", n=2, label="Deco XE75")
    assert len(fired) == 1
    assert "Deco XE75" in fired[0].message


# ── Rule plumbing ────────────────────────────────────────────────────────────

def test_disabled_rule_does_not_fire():
    assert _down(_engine(enabled=False), n=5) == []


def test_rule_host_filter_is_respected():
    engine = _engine(host="router-1")
    assert _down(engine, key="modem-1", n=5) == []
    assert len(_down(engine, key="router-1", n=2)) == 1


def test_alert_routes_to_the_hardware_page():
    fired = _down(_engine(), n=2)
    assert fired[0].cta_page == "Hardware"


def test_reason_is_carried_into_the_message():
    fired = _down(_engine(), n=2, reason="connection refused")
    assert "connection refused" in fired[0].message


# ── The five registrations (audit_static_coverage asserts these too) ─────────

def test_rule_type_is_registered():
    from modules.alert_types import RULE_TYPES
    assert "INFRA_UNREACHABLE" in RULE_TYPES


def test_static_coverage_tables_all_carry_the_new_type():
    from modules.alert_engine_routing import ACTION_STEPS, RULE_CTA
    from modules.alert_remediation import REMEDIATION
    from modules.alert_suppressor import _default_rules

    missing = [
        name for name, table in (
            ("RULE_CTA", RULE_CTA),
            ("ACTION_STEPS", ACTION_STEPS),
            ("REMEDIATION", REMEDIATION),
        ) if "INFRA_UNREACHABLE" not in table
    ]
    assert not missing, f"INFRA_UNREACHABLE missing from: {', '.join(missing)}"
    assert "INFRA_UNREACHABLE" in {r.rule_type for r in _default_rules()}


def test_default_rule_ships_disabled():
    from modules.alert_suppressor import _default_rules
    rule = next(r for r in _default_rules() if r.rule_type == "INFRA_UNREACHABLE")
    assert rule.enabled is False, "every built-in rule is opt-in (see _default_rules)"


def test_is_neither_device_scoped_nor_security_relevant():
    """Keyed by a plugin instance, not a LAN device — same class as MESH_DEGRADED."""
    from modules.alert_types import DEVICE_SCOPED_RULE_TYPES, SECURITY_RELEVANT_RULE_TYPES
    assert "INFRA_UNREACHABLE" not in DEVICE_SCOPED_RULE_TYPES
    assert "INFRA_UNREACHABLE" not in SECURITY_RELEVANT_RULE_TYPES


def test_static_audit_reports_full_coverage():
    from modules.alert_audit import audit_static_coverage
    failures = [f for f in audit_static_coverage() if not f.ok]
    assert not failures, "; ".join(f.detail for f in failures)
