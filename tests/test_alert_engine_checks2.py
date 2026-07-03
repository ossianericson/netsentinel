"""Tests for modules/alert_engine_checks2.py — _AlertChecksMixin2.

Full behavioural coverage (RTT_ANOMALY / IOT_BEHAVIOR / TREND_FORECAST) lives
in tests/test_alert_engine_v6_sprint2.py — this file satisfies RULE-T1's
per-module test-file requirement with the import + smoke checks.
"""


def test_import_mixin():
    from modules.alert_engine_checks2 import _AlertChecksMixin2
    assert _AlertChecksMixin2 is not None


def test_mixin_methods_present():
    from modules.alert_engine_checks2 import _AlertChecksMixin2
    assert hasattr(_AlertChecksMixin2, "evaluate_rtt_anomaly_checks")
    assert hasattr(_AlertChecksMixin2, "evaluate_iot_behavior_checks")
    assert hasattr(_AlertChecksMixin2, "evaluate_trend_checks")


def test_evaluate_rtt_anomaly_checks_no_learner():
    """No baseline learner means no anomaly can be assessed — must not fire or crash."""
    from modules.alert_engine import AlertEngine, AlertRule
    engine = AlertEngine(rules=[
        AlertRule(name="rtt_test", rule_type="RTT_ANOMALY", cooldown_s=0)
    ])
    fired = engine.evaluate_rtt_anomaly_checks({"192.168.1.1": 999.0}, None)
    assert fired == []
