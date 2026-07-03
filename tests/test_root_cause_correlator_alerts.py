"""Tests for modules/root_cause_correlator_alerts.py (RULE-AH1 split of
root_cause_correlator.py — see tests/test_root_cause_correlator.py for the
full behavioral coverage via correlate(recent_alerts=...))."""


def test_import():
    from modules.root_cause_correlator_alerts import correlate_recent_alerts
    assert correlate_recent_alerts


def test_empty_alerts_no_findings():
    from modules.root_cause_correlator_alerts import correlate_recent_alerts
    findings = []
    correlate_recent_alerts([], findings)
    assert findings == []


def test_modem_alert_appends_one_finding():
    from modules.root_cause_correlator_alerts import correlate_recent_alerts
    findings = []
    alerts = [{"rule_name": "Modem Signal Drop", "host": "modem", "message": "dropped", "ts": 1700000000}]
    correlate_recent_alerts(alerts, findings)
    assert len(findings) == 1
    assert findings[0].verify_step
