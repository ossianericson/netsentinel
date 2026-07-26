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


class TestIotBehaviorRemediationCarried:
    """Phase 7.4 -- IoTAlert.remediation was computed by modules/iot_baseline.py
    with rich, signal-specific text, then silently dropped when wrapped as an
    AlertFired. AlertFired.remediation now carries it through so the drawer
    can prefer this over the generic IOT_BEHAVIOR table entry."""

    def _engine_with_iot_rule(self):
        from modules.alert_engine import AlertEngine, AlertRule
        return AlertEngine(store=None, rules=[
            AlertRule(name="IoT Behavior Anomaly", rule_type="IOT_BEHAVIOR",
                      cooldown_s=0, enabled=True)
        ])

    def test_remediation_field_carried_onto_alert_fired(self):
        from modules.iot_baseline import IoTAlert
        eng = self._engine_with_iot_rule()
        signal = IoTAlert(
            mac="aa:bb:cc:dd:ee:ff", ip="192.168.1.50",
            device_label="Nest Hub [192.168.1.50]", alert_type="NEW_DEST",
            severity="HIGH", detail="contacted a new destination",
            remediation="Block device's internet access temporarily and inspect traffic.",
        )
        fired = eng.evaluate_iot_behavior_checks([signal])
        assert len(fired) == 1
        assert fired[0].remediation == (
            "Block device's internet access temporarily and inspect traffic."
        )

    def test_empty_remediation_on_signal_yields_empty_string(self):
        from modules.iot_baseline import IoTAlert
        eng = self._engine_with_iot_rule()
        signal = IoTAlert(
            mac="aa:bb:cc:dd:ee:ff", ip="192.168.1.50",
            device_label="Nest Hub [192.168.1.50]", alert_type="NEW_DEST",
            severity="HIGH", detail="contacted a new destination",
            remediation="",
        )
        fired = eng.evaluate_iot_behavior_checks([signal])
        assert fired[0].remediation == ""


def test_evaluate_rtt_anomaly_checks_no_learner():
    """No baseline learner means no anomaly can be assessed — must not fire or crash."""
    from modules.alert_engine import AlertEngine, AlertRule
    engine = AlertEngine(rules=[
        AlertRule(name="rtt_test", rule_type="RTT_ANOMALY", cooldown_s=0)
    ])
    fired = engine.evaluate_rtt_anomaly_checks({"192.168.1.1": 999.0}, None)
    assert fired == []
