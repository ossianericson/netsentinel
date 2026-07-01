"""Tests for modules/alert_engine_checks.py — _AlertChecksMixin."""


# ── Import tests ──────────────────────────────────────────────────────────────

def test_import_mixin():
    from modules.alert_engine_checks import _AlertChecksMixin
    assert _AlertChecksMixin is not None


def test_mixin_methods_present():
    from modules.alert_engine_checks import _AlertChecksMixin
    assert hasattr(_AlertChecksMixin, "evaluate_cert_checks")
    assert hasattr(_AlertChecksMixin, "evaluate_service_checks")


# ── Behavioural tests via AlertEngine ────────────────────────────────────────

def test_evaluate_cert_checks_no_results():
    """evaluate_cert_checks returns empty list when given no cert results."""
    from modules.alert_engine import AlertEngine, AlertRule
    engine = AlertEngine(rules=[
        AlertRule(name="cert_test", rule_type="CERT_EXPIRY", threshold_days=30)
    ])
    fired = engine.evaluate_cert_checks([])
    assert fired == []


def test_evaluate_cert_checks_fires_expiry():
    """evaluate_cert_checks fires when days_remaining < threshold_days."""
    from modules.alert_engine import AlertEngine, AlertRule
    engine = AlertEngine(rules=[
        AlertRule(name="cert_test", rule_type="CERT_EXPIRY", threshold_days=30, cooldown_s=0)
    ])
    results = [{"host": "example.com", "port": 443, "days_remaining": 5, "is_expired": False, "error": None}]
    fired = engine.evaluate_cert_checks(results)
    assert len(fired) == 1
    assert fired[0].rule_type == "CERT_EXPIRY"
    assert fired[0].host == "example.com:443"


def test_evaluate_cert_checks_no_fire_when_ok():
    """evaluate_cert_checks does not fire when cert is healthy."""
    from modules.alert_engine import AlertEngine, AlertRule
    engine = AlertEngine(rules=[
        AlertRule(name="cert_test", rule_type="CERT_EXPIRY", threshold_days=30, cooldown_s=0)
    ])
    results = [{"host": "example.com", "port": 443, "days_remaining": 60, "is_expired": False, "error": None}]
    fired = engine.evaluate_cert_checks(results)
    assert fired == []


def test_evaluate_cert_checks_expired():
    """evaluate_cert_checks fires CERT_EXPIRED when is_expired=True."""
    from modules.alert_engine import AlertEngine, AlertRule
    engine = AlertEngine(rules=[
        AlertRule(name="cert_expired", rule_type="CERT_EXPIRED", cooldown_s=0)
    ])
    results = [{"host": "old.example.com", "port": 443, "days_remaining": 0, "is_expired": True, "error": None}]
    fired = engine.evaluate_cert_checks(results)
    assert len(fired) == 1
    assert fired[0].severity == "CRITICAL"


def test_evaluate_service_checks_no_results():
    """evaluate_service_checks returns empty list when given no results."""
    from modules.alert_engine import AlertEngine, AlertRule
    engine = AlertEngine(rules=[
        AlertRule(name="svc_test", rule_type="SERVICE_DOWN")
    ])
    fired = engine.evaluate_service_checks([])
    assert fired == []


def test_evaluate_service_checks_fires_down():
    """evaluate_service_checks fires when up=False."""
    from modules.alert_engine import AlertEngine, AlertRule
    engine = AlertEngine(rules=[
        AlertRule(name="svc_test", rule_type="SERVICE_DOWN", cooldown_s=0)
    ])
    results = [{"host": "192.168.1.1", "port": 80, "up": False, "label": "Web server", "error": None}]
    fired = engine.evaluate_service_checks(results)
    assert len(fired) == 1
    assert fired[0].rule_type == "SERVICE_DOWN"
    assert fired[0].severity == "CRITICAL"


def test_evaluate_service_checks_resolution():
    """evaluate_service_checks emits a HEALTHY resolution when service recovers."""
    from modules.alert_engine import AlertEngine, AlertRule
    engine = AlertEngine(rules=[
        AlertRule(name="svc_test", rule_type="SERVICE_DOWN", cooldown_s=0)
    ])
    # Mark service as previously down
    engine._service_down_since["192.168.1.1:80"] = 1000

    results = [{"host": "192.168.1.1", "port": 80, "up": True, "label": "Web server", "error": None}]
    fired = engine.evaluate_service_checks(results)
    assert len(fired) == 1
    assert fired[0].is_resolution is True
    assert fired[0].severity == "HEALTHY"


def test_cert_checks_skips_on_error():
    """evaluate_cert_checks skips entries with error set."""
    from modules.alert_engine import AlertEngine, AlertRule
    engine = AlertEngine(rules=[
        AlertRule(name="cert_test", rule_type="CERT_EXPIRY", threshold_days=30, cooldown_s=0)
    ])
    results = [{"host": "down.example.com", "port": 443, "days_remaining": 5, "is_expired": False, "error": "timeout"}]
    fired = engine.evaluate_cert_checks(results)
    assert fired == []


# ── evaluate_baseline_metrics (Sprint 3 — BASELINE_DROP) ─────────────────────

def test_mixin_has_evaluate_baseline_metrics():
    from modules.alert_engine_checks import _AlertChecksMixin
    assert hasattr(_AlertChecksMixin, "evaluate_baseline_metrics")


def test_evaluate_baseline_metrics_no_drop():
    """A current speed close to typical does not fire."""
    from modules.alert_engine import AlertEngine, AlertRule
    engine = AlertEngine(rules=[
        AlertRule(name="speed_test", rule_type="BASELINE_DROP", cooldown_s=0)
    ])
    fired = engine.evaluate_baseline_metrics(730.0, [740.0, 735.0, 742.0, 745.0])
    assert fired == []


def test_evaluate_baseline_metrics_fires_on_severe_drop():
    """A >50% drop vs. the rolling median fires — the 740->94 Mbps incident case."""
    from modules.alert_engine import AlertEngine, AlertRule
    engine = AlertEngine(rules=[
        AlertRule(name="speed_test", rule_type="BASELINE_DROP", cooldown_s=0)
    ])
    fired = engine.evaluate_baseline_metrics(94.0, [740.0, 735.0, 742.0, 745.0])
    assert len(fired) == 1
    assert fired[0].rule_type == "BASELINE_DROP"
    assert fired[0].severity == "CRITICAL"
    assert "94" in fired[0].message
    assert fired[0].cta_page == "Speed Test"


def test_evaluate_baseline_metrics_respects_min_samples():
    """Fewer than min_samples prior tests → no false positive."""
    from modules.alert_engine import AlertEngine, AlertRule
    engine = AlertEngine(rules=[
        AlertRule(name="speed_test", rule_type="BASELINE_DROP", min_samples=4, cooldown_s=0)
    ])
    fired = engine.evaluate_baseline_metrics(94.0, [740.0, 735.0])
    assert fired == []


def test_evaluate_baseline_metrics_respects_cooldown():
    """Repeated drops within cooldown fire at most once."""
    from modules.alert_engine import AlertEngine, AlertRule
    engine = AlertEngine(rules=[
        AlertRule(name="speed_test", rule_type="BASELINE_DROP", cooldown_s=3600)
    ])
    prior = [740.0, 735.0, 742.0, 745.0]
    first = engine.evaluate_baseline_metrics(94.0, prior)
    second = engine.evaluate_baseline_metrics(90.0, prior)
    assert len(first) == 1
    assert second == []


def test_evaluate_baseline_metrics_disabled_rule_does_not_fire():
    from modules.alert_engine import AlertEngine, AlertRule
    engine = AlertEngine(rules=[
        AlertRule(name="speed_test", rule_type="BASELINE_DROP", cooldown_s=0, enabled=False)
    ])
    fired = engine.evaluate_baseline_metrics(94.0, [740.0, 735.0, 742.0, 745.0])
    assert fired == []
