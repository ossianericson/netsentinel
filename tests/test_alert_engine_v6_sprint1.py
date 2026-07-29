"""
Tests for the V6 Sprint 1 alert rule types — JITTER_HIGH, MESH_DEGRADED,
MODEM_SIGNAL_DROP, GRADE_REGRESSION, IP_CHURN — added to
modules/alert_engine_checks.py (_AlertChecksMixin).

See BACKLOG-V6.md Sprint 1 for the acceptance criteria these encode.
"""
from modules.alert_engine import AlertEngine, AlertRule


# ── JITTER_HIGH ────────────────────────────────────────────────────────────────

def test_jitter_high_fires_on_sustained_jitter():
    engine = AlertEngine(rules=[
        AlertRule(name="jitter", rule_type="JITTER_HIGH", threshold_ms=20.0, cooldown_s=0)
    ])
    fired = engine.evaluate_jitter_checks({"192.168.1.1": [25.0, 30.0, 28.0]})
    assert len(fired) == 1
    assert fired[0].rule_type == "JITTER_HIGH"
    assert fired[0].host == "192.168.1.1"
    assert fired[0].cta_page == "Network Logger"


def test_jitter_high_no_fire_below_threshold():
    engine = AlertEngine(rules=[
        AlertRule(name="jitter", rule_type="JITTER_HIGH", threshold_ms=20.0, cooldown_s=0)
    ])
    fired = engine.evaluate_jitter_checks({"192.168.1.1": [5.0, 8.0, 6.0]})
    assert fired == []


def test_jitter_high_ignores_single_spike():
    """A single high sample (below the 3-sample minimum) must not fire."""
    engine = AlertEngine(rules=[
        AlertRule(name="jitter", rule_type="JITTER_HIGH", threshold_ms=20.0, cooldown_s=0)
    ])
    fired = engine.evaluate_jitter_checks({"192.168.1.1": [50.0]})
    assert fired == []


def test_jitter_high_resolution_when_back_to_normal():
    engine = AlertEngine(rules=[
        AlertRule(name="jitter", rule_type="JITTER_HIGH", threshold_ms=20.0, cooldown_s=0)
    ])
    engine.evaluate_jitter_checks({"192.168.1.1": [25.0, 30.0, 28.0]})
    fired = engine.evaluate_jitter_checks({"192.168.1.1": [5.0, 6.0, 4.0]})
    assert len(fired) == 1
    assert fired[0].is_resolution is True
    assert fired[0].severity == "HEALTHY"


def test_jitter_high_disabled_rule_does_not_fire():
    engine = AlertEngine(rules=[
        AlertRule(name="jitter", rule_type="JITTER_HIGH", threshold_ms=20.0, cooldown_s=0, enabled=False)
    ])
    fired = engine.evaluate_jitter_checks({"192.168.1.1": [25.0, 30.0, 28.0]})
    assert fired == []


# ── MESH_DEGRADED ──────────────────────────────────────────────────────────────

def test_mesh_degraded_fires_on_node_drop():
    engine = AlertEngine(rules=[
        AlertRule(name="mesh", rule_type="MESH_DEGRADED", cooldown_s=0)
    ])
    fired = engine.evaluate_mesh_checks(unit_count=3, online_count=2, worst_unit="Bedroom", worst_rssi=-50.0)
    assert len(fired) == 1
    assert fired[0].rule_type == "MESH_DEGRADED"
    assert fired[0].cta_page == "Hardware"


def test_mesh_degraded_fires_on_weak_rssi():
    engine = AlertEngine(rules=[
        AlertRule(name="mesh", rule_type="MESH_DEGRADED", cooldown_s=0)
    ])
    fired = engine.evaluate_mesh_checks(unit_count=3, online_count=3, worst_unit="Attic", worst_rssi=-80.0)
    assert len(fired) == 1


def test_mesh_degraded_no_fire_when_healthy():
    engine = AlertEngine(rules=[
        AlertRule(name="mesh", rule_type="MESH_DEGRADED", cooldown_s=0)
    ])
    fired = engine.evaluate_mesh_checks(unit_count=3, online_count=3, worst_unit="Attic", worst_rssi=-60.0)
    assert fired == []


def test_mesh_degraded_resolution_when_recovered():
    engine = AlertEngine(rules=[
        AlertRule(name="mesh", rule_type="MESH_DEGRADED", cooldown_s=0)
    ])
    engine.evaluate_mesh_checks(unit_count=3, online_count=2, worst_unit="Bedroom", worst_rssi=-50.0)
    fired = engine.evaluate_mesh_checks(unit_count=3, online_count=3, worst_unit="Bedroom", worst_rssi=-50.0)
    assert len(fired) == 1
    assert fired[0].is_resolution is True


# ── MODEM_SIGNAL_DROP ──────────────────────────────────────────────────────────

def test_modem_signal_drop_fires_on_band_downgrade():
    engine = AlertEngine(rules=[
        AlertRule(name="modem", rule_type="MODEM_SIGNAL_DROP", min_samples=20, cooldown_s=0)
    ])
    fired = engine.evaluate_modem_checks(
        network_type="LTE", current_sinr=15.0, prior_sinr=[20.0] * 25, prior_network_type="5G NR NSA",
    )
    assert len(fired) == 1
    assert fired[0].rule_type == "MODEM_SIGNAL_DROP"
    assert "5G" in fired[0].message
    assert fired[0].cta_page == "Hardware"


def test_modem_signal_drop_fires_on_baseline_drop():
    prior = [20.0] * 25
    prior[0] = 5.0
    engine = AlertEngine(rules=[
        AlertRule(name="modem", rule_type="MODEM_SIGNAL_DROP", min_samples=20, cooldown_s=0)
    ])
    fired = engine.evaluate_modem_checks(
        network_type="5G NR NSA", current_sinr=1.0, prior_sinr=prior, prior_network_type="5G NR NSA",
    )
    assert len(fired) == 1


def test_modem_signal_drop_no_fire_when_stable():
    engine = AlertEngine(rules=[
        AlertRule(name="modem", rule_type="MODEM_SIGNAL_DROP", min_samples=20, cooldown_s=0)
    ])
    fired = engine.evaluate_modem_checks(
        network_type="5G NR NSA", current_sinr=20.0,
        prior_sinr=[19.0, 20.0, 21.0, 20.5, 19.5] * 5, prior_network_type="5G NR NSA",
    )
    assert fired == []


# ── GRADE_REGRESSION ────────────────────────────────────────────────────────────

def test_grade_regression_fires_on_decline():
    engine = AlertEngine(rules=[
        AlertRule(name="grade", rule_type="GRADE_REGRESSION", cooldown_s=0)
    ])
    fired = engine.evaluate_grade_check(grade="C", score=70.0, verdict="Degraded", prior_grade="A")
    assert len(fired) == 1
    assert fired[0].rule_type == "GRADE_REGRESSION"
    assert fired[0].cta_page == "Network Grade"


def test_grade_regression_no_fire_on_improvement():
    engine = AlertEngine(rules=[
        AlertRule(name="grade", rule_type="GRADE_REGRESSION", cooldown_s=0)
    ])
    fired = engine.evaluate_grade_check(grade="A", score=95.0, verdict="Excellent", prior_grade="C")
    assert fired == []


def test_grade_regression_no_fire_when_no_prior():
    engine = AlertEngine(rules=[
        AlertRule(name="grade", rule_type="GRADE_REGRESSION", cooldown_s=0)
    ])
    fired = engine.evaluate_grade_check(grade="B", score=85.0, verdict="Good", prior_grade=None)
    assert fired == []


def test_grade_regression_severity_scales_with_drop_size():
    engine = AlertEngine(rules=[
        AlertRule(name="grade", rule_type="GRADE_REGRESSION", cooldown_s=0)
    ])
    fired = engine.evaluate_grade_check(grade="F", score=20.0, verdict="Poor", prior_grade="A")
    assert fired[0].severity == "CRITICAL"


# ── IP_CHURN ────────────────────────────────────────────────────────────────────

def test_ip_churn_fires_per_device():
    engine = AlertEngine(rules=[
        AlertRule(name="churn", rule_type="IP_CHURN", cooldown_s=0)
    ])
    fired = engine.evaluate_ip_churn_checks({"f8:7d:76:00:00:01": 4})
    assert len(fired) == 1
    assert fired[0].rule_type == "IP_CHURN"
    assert fired[0].host == "f8:7d:76:00:00:01"
    assert fired[0].cta_page == "Devices"


def test_ip_churn_no_fire_when_empty():
    engine = AlertEngine(rules=[
        AlertRule(name="churn", rule_type="IP_CHURN", cooldown_s=0)
    ])
    assert engine.evaluate_ip_churn_checks({}) == []


def test_ip_churn_skips_locally_administered_mac():
    """S4: a privacy-randomised MAC (U/L bit set, e.g. iOS/Android private
    Wi-Fi addressing) churning IPs is normal OS behaviour, not a missing
    DHCP reservation -- must not fire. 0x6a & 0x02 == 0x02, the exact MAC
    shape confirmed live in the plan's audit (docs/internal/
    scan-guidance-audit-2026-07-29.md)."""
    engine = AlertEngine(rules=[
        AlertRule(name="churn", rule_type="IP_CHURN", cooldown_s=0)
    ])
    fired = engine.evaluate_ip_churn_checks({"6a:34:64:72:f8:f0": 3})
    assert fired == []


def test_ip_churn_resolution_when_stabilized():
    engine = AlertEngine(rules=[
        AlertRule(name="churn", rule_type="IP_CHURN", cooldown_s=0)
    ])
    engine.evaluate_ip_churn_checks({"f8:7d:76:00:00:01": 4})
    fired = engine.evaluate_ip_churn_checks({})
    assert len(fired) == 1
    assert fired[0].is_resolution is True
