"""Phase 4 C5 — DNS_LATENCY (_AlertChecksMixin5).

DNS slowness had no rule type at all. `dns_ms` is measured by
`modules.network_logger.NetworkLogger` every cycle and reached the live log
table and nothing else — there is no `dns_sample` table, and `device_baseline`
reads `device_state`, which holds no DNS rows. So the baseline is in-memory
(`alert_baseline.RollingSeries`, the same one C2 added for the modem) and the
engine owns it: unlike the modem there is no logged history to prefer, so there
is nothing for a caller to resolve.

Three things have to hold together, and each has its own failure mode:

  * **mean + 2σ** catches a resolver that is slow *for this network*, which a
    fixed threshold cannot — a 4 ms LAN resolver and a 90 ms upstream one are
    both normal somewhere.
  * **An absolute floor** stops the same statistics being absurd in the other
    direction: on a resolver that answers in 2 ms ± 0.4 ms, mean + 2σ is 2.8 ms,
    and without a floor every third lookup is an "anomaly".
  * **Outage suppression** stops the rule restating a fact the user already has.
    DNS crawling because the gateway is down is a symptom of the outage, not an
    independent finding.
"""
from __future__ import annotations

from modules.alert_engine import AlertEngine, AlertRule
from modules.alert_engine_checks5 import (
    _DNS_ABSOLUTE_FLOOR_MS, _DNS_KEY, _DNS_MIN_SAMPLES,
)


def _engine(**kw):
    kw.setdefault("cooldown_s", 0)
    kw.setdefault("enabled", True)
    return AlertEngine(rules=[
        AlertRule(name="DNS Latency", rule_type="DNS_LATENCY", **kw)
    ])


def _warm(engine, value=20.0, n=None, ts=1000):
    """Feed a steady, unremarkable baseline so the rule has something to learn.

    Returns the ts just past the samples so callers can keep the clock moving.
    """
    n = _DNS_MIN_SAMPLES if n is None else n
    for i in range(n):
        # Alternate around the mean so stddev is small but non-zero: a zero
        # stddev makes mean + 2σ collapse onto the mean and every sample above
        # it an anomaly, which would pass these tests for the wrong reason.
        jitter = 1.0 if i % 2 else -1.0
        engine.evaluate_dns_latency_checks(value + jitter, ts=ts + i)
    return ts + n


def _slow(engine, n=1, value=None, ts=2000, **kw):
    value = (_DNS_ABSOLUTE_FLOOR_MS * 3) if value is None else value
    out = []
    for i in range(n):
        out += engine.evaluate_dns_latency_checks(value, ts=ts + i, **kw)
    return out


# ── Import / registration ────────────────────────────────────────────────────

def test_engine_exposes_the_check():
    assert hasattr(AlertEngine(rules=[]), "evaluate_dns_latency_checks")


# ── The baseline ─────────────────────────────────────────────────────────────

def test_no_alert_before_the_baseline_has_enough_samples():
    """A cold start must not alert off two data points."""
    engine = _engine()
    ts = _warm(engine, n=2)
    assert _slow(engine, n=3, ts=ts) == []


def test_alerts_once_the_baseline_is_warm():
    engine = _engine()
    ts = _warm(engine)
    fired = _slow(engine, n=2, ts=ts)
    assert len(fired) == 1
    assert fired[0].rule_type == "DNS_LATENCY"
    assert fired[0].severity == "WARNING"


def test_a_fast_resolver_does_not_alert_on_statistical_noise():
    """The floor's whole job. mean+2sigma here is ~2.8 ms; 5 ms is 'anomalous'
    and completely fine."""
    engine = _engine()
    ts = _warm(engine, value=2.0)
    assert _slow(engine, n=5, value=5.0, ts=ts) == [], (
        f"5 ms must not alert — it is under the {_DNS_ABSOLUTE_FLOOR_MS} ms floor "
        f"no matter how tight this resolver's distribution is"
    )


def test_an_all_zero_baseline_does_not_make_everything_an_anomaly():
    """The shape actually observed in production, and the floor's sharpest case.

    `_dns_latency_system()` calls `socket.getaddrinfo("google.com")`, which the
    OS DNS cache answers in 0.0 ms — measured live, 8/8 repeats at exactly 0.0.
    So a healthy Windows machine learns a baseline of flat zeros, where
    mean + 2*sigma is 0.0 and *any* positive measurement clears it. Without the
    floor the rule would alert on the first 1 ms lookup after warm-up.
    """
    engine = _engine()
    for i in range(_DNS_MIN_SAMPLES):
        engine.evaluate_dns_latency_checks(0.0, ts=1000 + i)
    assert _slow(engine, n=5, value=1.0, ts=2000) == []
    # ...and the floor still lets a genuinely slow lookup through.
    assert len(_slow(engine, n=2, value=900.0, ts=3000)) == 1


def test_a_slow_but_normal_resolver_does_not_alert():
    """Over the floor, but this is simply what this network's DNS looks like."""
    engine = _engine()
    ts = _warm(engine, value=_DNS_ABSOLUTE_FLOOR_MS + 100.0)
    assert _slow(engine, n=5, value=_DNS_ABSOLUTE_FLOOR_MS + 101.0, ts=ts) == []


def test_a_normal_sample_joins_the_baseline():
    engine = _engine()
    _warm(engine)
    before = len(engine._dns_series)
    engine.evaluate_dns_latency_checks(21.0, ts=9000)
    assert len(engine._dns_series) == before + 1


def test_a_slow_sample_does_not_join_the_baseline():
    """The baseline learns what normal looks like, not what the anomaly looks
    like. See test_a_sustained_episode_never_normalises_itself for the failure
    this prevents."""
    engine = _engine()
    _warm(engine)
    before = len(engine._dns_series)
    engine.evaluate_dns_latency_checks(_DNS_ABSOLUTE_FLOOR_MS * 3, ts=9000)
    assert len(engine._dns_series) == before


def test_a_sustained_episode_never_normalises_itself():
    """Measured on the real numbers: 20 samples at ~20 ms, then a steady 600 ms.
    If slow samples fed the baseline, mean + 2σ would cross 600 ms by the sixth
    cycle — the rule would alert, then announce 'DNS is back to normal' while
    DNS was still sitting at 600 ms."""
    engine = _engine()
    ts = _warm(engine)
    fired = _slow(engine, n=30, ts=ts)
    assert [a for a in fired if a.is_resolution] == [], (
        "a resolution fired while the condition was still true — the baseline "
        "drifted onto the anomaly"
    )


# ── The edge ─────────────────────────────────────────────────────────────────

def test_single_slow_lookup_does_not_alert():
    """One slow resolution is a blip. Two consecutive is a condition."""
    engine = _engine()
    ts = _warm(engine)
    assert _slow(engine, n=1, ts=ts) == []


def test_does_not_repeat_while_dns_stays_slow():
    engine = _engine()
    ts = _warm(engine)
    fired = _slow(engine, n=60, ts=ts)
    assert len(fired) == 1, (
        f"slow DNS must produce one alert, not one per cycle; got {len(fired)}"
    )


def test_recovery_fires_a_resolution():
    engine = _engine()
    ts = _warm(engine)
    _slow(engine, n=2, ts=ts)
    fired = engine.evaluate_dns_latency_checks(20.0, ts=ts + 500)
    assert len(fired) == 1
    assert fired[0].is_resolution is True
    assert fired[0].severity == "HEALTHY"


def test_recovery_without_a_prior_alert_is_silent():
    engine = _engine()
    ts = _warm(engine)
    _slow(engine, n=1, ts=ts)
    assert engine.evaluate_dns_latency_checks(20.0, ts=ts + 500) == []


def test_a_second_episode_can_alert_again():
    engine = _engine()
    ts = _warm(engine)
    _slow(engine, n=2, ts=ts)
    engine.evaluate_dns_latency_checks(20.0, ts=ts + 500)
    assert len(_slow(engine, n=2, ts=ts + 600)) == 1


# ── A failed probe is not a slow one ─────────────────────────────────────────

def test_probe_failure_does_not_alert():
    """-1.0 means the resolver did not answer. That is an outage, and
    HOST_DOWN/SERVICE_DOWN own it — 'DNS is slower than usual' would be a
    false claim about a resolver that returned nothing at all."""
    engine = _engine()
    ts = _warm(engine)
    assert _slow(engine, n=5, value=-1.0, ts=ts) == []


def test_probe_failure_does_not_pollute_the_baseline():
    engine = _engine()
    _warm(engine)
    before = len(engine._dns_series)
    engine.evaluate_dns_latency_checks(-1.0, ts=9000)
    assert len(engine._dns_series) == before


def test_probe_failure_does_not_close_an_open_episode():
    """Feeding -1.0 through as a healthy observation would silently end the
    episode, and the next slow sample would re-alert about the same one."""
    engine = _engine()
    ts = _warm(engine)
    assert len(_slow(engine, n=2, ts=ts)) == 1
    engine.evaluate_dns_latency_checks(-1.0, ts=ts + 100)
    assert _slow(engine, n=5, ts=ts + 200) == [], (
        "a failed probe must not re-arm the edge"
    )


def test_probe_failure_does_not_fire_a_resolution():
    engine = _engine()
    ts = _warm(engine)
    _slow(engine, n=2, ts=ts)
    assert engine.evaluate_dns_latency_checks(-1.0, ts=ts + 100) == []


# ── Outage suppression ───────────────────────────────────────────────────────

def test_suppressed_while_a_nominated_host_is_already_down():
    engine = _engine()
    ts = _warm(engine)
    engine._host_down_since["192.168.1.1"] = ts
    assert _slow(engine, n=10, ts=ts, outage_hosts=("192.168.1.1",)) == [], (
        "slow DNS during a gateway outage is a symptom, not a finding"
    )


def test_not_suppressed_by_an_unrelated_host_being_down():
    """`_host_down_since` holds every LAN device since C3 routed the LAN
    availability worker into the engine. One dead printer must not mute DNS."""
    engine = _engine()
    ts = _warm(engine)
    engine._host_down_since["192.168.1.57"] = ts   # the printer
    fired = _slow(engine, n=2, ts=ts, outage_hosts=("192.168.1.1", "8.8.8.8"))
    assert len(fired) == 1


def test_the_episode_re_arms_once_the_outage_clears():
    """Suppression is 'do not claim this now', not 'this episode is spent'. If
    DNS is still slow after the outage lifts, that is a genuine independent
    finding and has never been reported."""
    engine = _engine()
    ts = _warm(engine)
    engine._host_down_since["192.168.1.1"] = ts
    assert _slow(engine, n=10, ts=ts, outage_hosts=("192.168.1.1",)) == []
    del engine._host_down_since["192.168.1.1"]
    fired = _slow(engine, n=2, ts=ts + 100, outage_hosts=("192.168.1.1",))
    assert len(fired) == 1


def test_no_outage_hosts_means_no_suppression():
    engine = _engine()
    ts = _warm(engine)
    engine._host_down_since["192.168.1.1"] = ts
    assert len(_slow(engine, n=2, ts=ts)) == 1


# ── Rule plumbing ────────────────────────────────────────────────────────────

def test_disabled_rule_does_not_fire():
    engine = _engine(enabled=False)
    ts = _warm(engine)
    assert _slow(engine, n=5, ts=ts) == []


def test_baseline_is_learned_even_while_the_rule_is_disabled():
    """Enabling the rule must not then require another 20 minutes of warm-up."""
    engine = _engine(enabled=False)
    _warm(engine)
    assert len(engine._dns_series) == _DNS_MIN_SAMPLES


def test_alert_routes_to_the_dns_page():
    engine = _engine()
    ts = _warm(engine)
    fired = _slow(engine, n=2, ts=ts)
    assert fired[0].cta_page == "DNS & Stability"


def test_message_carries_the_measurement_and_the_normal():
    engine = _engine()
    ts = _warm(engine, value=20.0)
    fired = _slow(engine, n=2, value=640.0, ts=ts)
    assert "640" in fired[0].message
    assert fired[0].value == 640.0


def test_keyed_by_a_literal_not_a_device():
    engine = _engine()
    ts = _warm(engine)
    fired = _slow(engine, n=2, ts=ts)
    assert fired[0].host == _DNS_KEY


# ── The six registrations ────────────────────────────────────────────────────

def test_rule_type_is_registered():
    from modules.alert_types import RULE_TYPES
    assert "DNS_LATENCY" in RULE_TYPES


def test_static_coverage_tables_all_carry_the_new_type():
    from modules.alert_engine_routing import ACTION_STEPS, RULE_CTA
    from modules.alert_remediation import REMEDIATION
    from modules.alert_suppressor import _default_rules

    missing = [
        name for name, table in (
            ("RULE_CTA", RULE_CTA),
            ("ACTION_STEPS", ACTION_STEPS),
            ("REMEDIATION", REMEDIATION),
        ) if "DNS_LATENCY" not in table
    ]
    assert not missing, f"DNS_LATENCY missing from: {', '.join(missing)}"
    assert "DNS_LATENCY" in {r.rule_type for r in _default_rules()}


def test_notifications_page_offers_an_opt_in_control():
    """The sixth registration. Every built-in rule ships disabled, so a rule
    with no checkbox on the Notifications page can never be turned on."""
    from ui.pages.notif_channel_panels import _ALERT_RULE_DEFS
    assert "DNS_LATENCY" in {rule_type for _, rule_type, _ in _ALERT_RULE_DEFS}


def test_default_rule_ships_disabled():
    from modules.alert_suppressor import _default_rules
    rule = next(r for r in _default_rules() if r.rule_type == "DNS_LATENCY")
    assert rule.enabled is False


def test_is_neither_device_scoped_nor_security_relevant():
    """A network-wide metric keyed by a literal string — same class as
    MESH_DEGRADED and GRADE_REGRESSION (see alert_types.py)."""
    from modules.alert_types import DEVICE_SCOPED_RULE_TYPES, SECURITY_RELEVANT_RULE_TYPES
    assert "DNS_LATENCY" not in DEVICE_SCOPED_RULE_TYPES
    assert "DNS_LATENCY" not in SECURITY_RELEVANT_RULE_TYPES


def test_static_audit_reports_full_coverage():
    from modules.alert_audit import audit_static_coverage
    failures = [f for f in audit_static_coverage() if not f.ok]
    assert not failures, "; ".join(f.detail for f in failures)
