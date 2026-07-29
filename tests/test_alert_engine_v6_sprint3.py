"""
Tests for the V6 Sprint 3 alert rule types — NEW_OPEN_PORT, NEW_CVE,
NEW_EXPOSURE — added to modules/alert_engine_checks3.py (_AlertChecksMixin3).

See BACKLOG-V6.md Sprint 3 for the acceptance criteria these encode.
"""
from modules.alert_engine import AlertEngine, AlertRule
from modules.cve_lookup import CVEResult
from modules.cve_recheck import CveRecheckReport
from modules.exposure_watch import ExposureWatchReport
from modules.port_sweep import PortSweepReport


# ── NEW_OPEN_PORT ────────────────────────────────────────────────────────────

def test_new_open_port_fires_one_alert_per_port():
    engine = AlertEngine(rules=[
        AlertRule(name="sweep", rule_type="NEW_OPEN_PORT", cooldown_s=0)
    ])
    report = PortSweepReport(new_ports=[("192.168.1.40", 23), ("192.168.1.40", 3389)])
    fired = engine.evaluate_port_sweep_checks(report)
    assert len(fired) == 2
    assert all(a.rule_type == "NEW_OPEN_PORT" for a in fired)
    assert all(a.host == "192.168.1.40" for a in fired)
    assert "23" in fired[0].message
    assert fired[0].cta_page == "Devices"


def test_new_open_port_respects_host_filter():
    engine = AlertEngine(rules=[
        AlertRule(name="sweep", rule_type="NEW_OPEN_PORT", host="192.168.1.99", cooldown_s=0)
    ])
    report = PortSweepReport(new_ports=[("192.168.1.40", 23)])
    fired = engine.evaluate_port_sweep_checks(report)
    assert fired == []


def test_new_open_port_disabled_rule_does_not_fire():
    engine = AlertEngine(rules=[
        AlertRule(name="sweep", rule_type="NEW_OPEN_PORT", cooldown_s=0, enabled=False)
    ])
    report = PortSweepReport(new_ports=[("192.168.1.40", 23)])
    fired = engine.evaluate_port_sweep_checks(report)
    assert fired == []


def test_new_open_port_cooldown_suppresses_repeat():
    engine = AlertEngine(rules=[
        AlertRule(name="sweep", rule_type="NEW_OPEN_PORT", cooldown_s=300)
    ])
    report = PortSweepReport(new_ports=[("192.168.1.40", 23)])
    first = engine.evaluate_port_sweep_checks(report)
    second = engine.evaluate_port_sweep_checks(report)
    assert len(first) == 1
    assert len(second) == 0


# ── NEW_CVE ──────────────────────────────────────────────────────────────────

def test_new_cve_fires_with_severity_from_finding():
    engine = AlertEngine(rules=[
        AlertRule(name="cve", rule_type="NEW_CVE", cooldown_s=0)
    ])
    cve = CVEResult(cve_id="CVE-2024-9999", description="RCE in service",
                     cvss_score=9.8, severity="CRITICAL", published="2024-06-01")
    report = CveRecheckReport(new_cves=[("192.168.1.10", "OpenSSH 8.9p1", cve)])
    fired = engine.evaluate_cve_recheck_checks(report)
    assert len(fired) == 1
    assert fired[0].rule_type == "NEW_CVE"
    assert fired[0].host == "192.168.1.10"
    assert fired[0].severity == "CRITICAL"
    assert "CVE-2024-9999" in fired[0].message
    # S3 fix: NEW_CVE used to point at "CVE Lookup" (the on-demand scan
    # page); the alert is about an already-tracked pair gaining a CVE, so
    # "CVE Tracker" (the lifecycle page) is the real destination.
    assert fired[0].cta_page == "CVE Tracker"


def test_new_cve_empty_report_does_not_fire():
    engine = AlertEngine(rules=[
        AlertRule(name="cve", rule_type="NEW_CVE", cooldown_s=0)
    ])
    fired = engine.evaluate_cve_recheck_checks(CveRecheckReport(new_cves=[]))
    assert fired == []


# ── NEW_EXPOSURE ─────────────────────────────────────────────────────────────

def test_new_exposure_fires_one_alert_per_port():
    engine = AlertEngine(rules=[
        AlertRule(name="exposure", rule_type="NEW_EXPOSURE", cooldown_s=0)
    ])
    report = ExposureWatchReport(new_exposed=[("192.168.1.20", 445)])
    fired = engine.evaluate_exposure_checks(report)
    assert len(fired) == 1
    assert fired[0].rule_type == "NEW_EXPOSURE"
    assert fired[0].host == "192.168.1.20"
    assert fired[0].cta_page == "Exposed to Internet"
    assert "445" in fired[0].message


def test_new_exposure_empty_report_does_not_fire():
    engine = AlertEngine(rules=[
        AlertRule(name="exposure", rule_type="NEW_EXPOSURE", cooldown_s=0)
    ])
    fired = engine.evaluate_exposure_checks(ExposureWatchReport(new_exposed=[]))
    assert fired == []
