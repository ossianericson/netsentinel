"""Tests for modules/alert_engine_checks3.py — _AlertChecksMixin3.

Full behavioural coverage (NEW_OPEN_PORT / NEW_CVE / NEW_EXPOSURE) lives in
tests/test_alert_engine_v6_sprint3.py — this file satisfies RULE-T1's
per-module test-file requirement with the import + smoke checks.
"""


def test_import_mixin():
    from modules.alert_engine_checks3 import _AlertChecksMixin3
    assert _AlertChecksMixin3 is not None


def test_mixin_methods_present():
    from modules.alert_engine_checks3 import _AlertChecksMixin3
    assert hasattr(_AlertChecksMixin3, "evaluate_port_sweep_checks")
    assert hasattr(_AlertChecksMixin3, "evaluate_cve_recheck_checks")
    assert hasattr(_AlertChecksMixin3, "evaluate_exposure_checks")


def test_evaluate_port_sweep_checks_no_new_ports():
    """An empty report must not fire or crash."""
    from modules.alert_engine import AlertEngine, AlertRule
    from modules.port_sweep import PortSweepReport
    engine = AlertEngine(rules=[
        AlertRule(name="sweep", rule_type="NEW_OPEN_PORT", cooldown_s=0)
    ])
    fired = engine.evaluate_port_sweep_checks(PortSweepReport(new_ports=[]))
    assert fired == []
