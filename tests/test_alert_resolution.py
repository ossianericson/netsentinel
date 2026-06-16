"""Tests for S4-1 (resolution tier), S4-3 (consolidation), S4-4 (action steps)."""
import time

from modules.alert_engine import AlertEngine, AlertRule, AlertFired


def _engine(**kwargs):
    """Create a minimal AlertEngine with one rule of the given type."""
    rule_type = kwargs.pop("rule_type", "HOST_DOWN")
    rules = [AlertRule(name="Test", rule_type=rule_type, cooldown_s=0, enabled=True, **kwargs)]
    return AlertEngine(rules=rules)


# ── S4-1: resolution tier ─────────────────────────────────────────────────────

def test_healthy_alert_fires_on_recovery():
    """A HEALTHY resolution alert should fire when a DOWN host becomes UP."""
    eng = _engine(rule_type="HOST_DOWN")
    now = int(time.time())

    # First cycle: host goes DOWN
    eng.evaluate_cycle({"ts": now, "states": {"192.168.1.1": "DOWN"}, "rtts": {}})
    # host should be tracked as down
    assert "192.168.1.1" in eng._host_down_since

    # Second cycle: host comes UP
    fired = eng.evaluate_cycle({"ts": now + 120, "states": {"192.168.1.1": "UP"}, "rtts": {}})

    healthy = [a for a in fired if a.severity == "HEALTHY"]
    assert len(healthy) == 1, f"Expected 1 HEALTHY alert, got: {fired}"
    assert healthy[0].is_resolution is True
    assert healthy[0].downtime_s == 120


def test_healthy_alert_includes_duration():
    """Resolution message should mention how long the host was down."""
    eng = _engine(rule_type="HOST_DOWN")
    now = int(time.time())
    eng.evaluate_cycle({"ts": now, "states": {"host1": "DOWN"}, "rtts": {}})
    fired = eng.evaluate_cycle({"ts": now + 300, "states": {"host1": "UP"}, "rtts": {}})
    healthy = [a for a in fired if a.severity == "HEALTHY"]
    assert healthy
    assert "5m" in healthy[0].message or "300" in healthy[0].message


def test_no_healthy_if_host_never_was_down():
    """If the host was never tracked as down, no resolution alert should fire."""
    eng = _engine(rule_type="HOST_DOWN")
    now = int(time.time())
    fired = eng.evaluate_cycle({"ts": now, "states": {"192.168.1.1": "UP"}, "rtts": {}})
    healthy = [a for a in fired if a.severity == "HEALTHY"]
    assert healthy == []


def test_service_resolution_on_recovery():
    """SERVICE_DOWN resolution fires when a service comes back up."""
    eng = _engine(rule_type="SERVICE_DOWN")

    service_result_down = [{"host": "192.168.1.1", "port": 80, "up": False, "label": "HTTP"}]
    service_result_up   = [{"host": "192.168.1.1", "port": 80, "up": True,  "label": "HTTP"}]

    eng.evaluate_service_checks(service_result_down)
    assert "192.168.1.1:80" in eng._service_down_since

    fired = eng.evaluate_service_checks(service_result_up)
    healthy = [a for a in fired if a.severity == "HEALTHY"]
    assert len(healthy) == 1
    assert healthy[0].is_resolution is True


def test_service_no_resolution_if_never_down():
    """If a service was never flagged as down, no resolution fires."""
    eng = _engine(rule_type="SERVICE_DOWN")
    result_up = [{"host": "192.168.1.1", "port": 80, "up": True, "label": "HTTP"}]
    fired = eng.evaluate_service_checks(result_up)
    assert not any(a.severity == "HEALTHY" for a in fired)


# ── S4-3: alert consolidation ─────────────────────────────────────────────────

def test_consolidation_fires_for_5_simultaneous_down():
    """5 simultaneous HOST_DOWN alerts should consolidate into one."""
    eng = AlertEngine(rules=[
        AlertRule(name="Host Down", rule_type="HOST_DOWN", cooldown_s=0, enabled=True)
    ])
    eng.set_consolidation_threshold(5)
    now = int(time.time())
    states = {f"192.168.1.{i}": "DOWN" for i in range(1, 6)}
    fired = eng.evaluate_cycle({"ts": now, "states": states, "rtts": {}})

    # Should be one consolidated alert, not 5 individual ones
    critical = [a for a in fired if a.severity == "CRITICAL" and not a.is_resolution]
    assert len(critical) == 1
    assert "simultaneously" in critical[0].message
    assert critical[0].host == "(network)"


def test_no_consolidation_below_threshold():
    """4 simultaneous HOST_DOWN alerts (below threshold of 5) should fire individually."""
    eng = AlertEngine(rules=[
        AlertRule(name="Host Down", rule_type="HOST_DOWN", cooldown_s=0, enabled=True)
    ])
    eng.set_consolidation_threshold(5)
    now = int(time.time())
    states = {f"192.168.1.{i}": "DOWN" for i in range(1, 5)}
    fired = eng.evaluate_cycle({"ts": now, "states": states, "rtts": {}})

    critical = [a for a in fired if a.severity == "CRITICAL" and not a.is_resolution]
    assert len(critical) == 4
    assert all(a.host != "(network)" for a in critical)


def test_consolidation_threshold_configurable():
    """set_consolidation_threshold changes the consolidation point."""
    eng = AlertEngine(rules=[
        AlertRule(name="Host Down", rule_type="HOST_DOWN", cooldown_s=0, enabled=True)
    ])
    eng.set_consolidation_threshold(3)
    now = int(time.time())
    states = {"a": "DOWN", "b": "DOWN", "c": "DOWN"}
    fired = eng.evaluate_cycle({"ts": now, "states": states, "rtts": {}})

    critical = [a for a in fired if a.severity == "CRITICAL" and not a.is_resolution]
    assert len(critical) == 1
    assert "simultaneously" in critical[0].message


# ── S4-4: plain-English action steps ─────────────────────────────────────────

def test_rtt_alert_has_action_step():
    """RTT alerts should include → action step text."""
    eng = AlertEngine(rules=[
        AlertRule(name="High RTT", rule_type="RTT_THRESHOLD",
                  threshold_ms=100.0, cooldown_s=0, enabled=True)
    ])
    now = int(time.time())
    fired = eng.evaluate_cycle({"ts": now, "states": {"8.8.8.8": "UP"}, "rtts": {"8.8.8.8": 200.0}})
    assert fired
    assert "→" in fired[0].message


def test_host_down_alert_has_action_step():
    """HOST_DOWN alerts should include → action step text."""
    eng = _engine(rule_type="HOST_DOWN")
    now = int(time.time())
    fired = eng.evaluate_cycle({"ts": now, "states": {"host1": "DOWN"}, "rtts": {}})
    down_alerts = [a for a in fired if a.rule_type == "HOST_DOWN" and not a.is_resolution]
    assert down_alerts
    assert "→" in down_alerts[0].message


def test_service_down_alert_has_action_step():
    """SERVICE_DOWN alerts should include action steps."""
    eng = _engine(rule_type="SERVICE_DOWN")
    result_down = [{"host": "192.168.1.1", "port": 443, "up": False, "label": "HTTPS"}]
    fired = eng.evaluate_service_checks(result_down)
    critical = [a for a in fired if a.severity == "CRITICAL"]
    assert critical
    assert "→" in critical[0].message


def test_cert_expiry_alert_has_action_step():
    """CERT_EXPIRY alerts should include → action step text."""
    eng = AlertEngine(rules=[
        AlertRule(name="Cert Expiring", rule_type="CERT_EXPIRY",
                  threshold_days=30, cooldown_s=0, enabled=True)
    ])
    result = [{"host": "example.com", "port": 443,
               "is_expired": False, "days_remaining": 10, "error": None}]
    fired = eng.evaluate_cert_checks(result)
    assert fired
    assert "→" in fired[0].message


# ── AlertFired dataclass fields ───────────────────────────────────────────────

def test_alert_fired_has_resolution_fields():
    """AlertFired should have is_resolution and downtime_s fields."""
    a = AlertFired(
        rule_name="Test", rule_type="HOST_DOWN", host="x",
        message="back", severity="HEALTHY", ts=0,
        is_resolution=True, downtime_s=120,
    )
    assert a.is_resolution is True
    assert a.downtime_s == 120


def test_alert_fired_defaults_not_resolution():
    """Normal AlertFired should default to is_resolution=False."""
    a = AlertFired(
        rule_name="Test", rule_type="HOST_DOWN", host="x",
        message="down", severity="CRITICAL", ts=0,
    )
    assert a.is_resolution is False
    assert a.downtime_s is None
