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
