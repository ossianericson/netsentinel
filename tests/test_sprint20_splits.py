"""
Sprint 20 split tests — import + smoke tests for all 7 new modules.

RULE-T1: every new module/ file needs at least one import and one behavioural test.
"""


# ── S20-1: metric_store_queries._default_db_path ──────────────────────────────

def test_import_default_db_path():
    from modules.metric_store_queries import _default_db_path
    assert callable(_default_db_path)


def test_default_db_path_returns_path():
    from pathlib import Path
    from modules.metric_store_queries import _default_db_path
    result = _default_db_path()
    assert isinstance(result, Path)
    assert result.suffix == ".db"


# ── S20-2: credentialed_scan_helpers ─────────────────────────────────────────

def test_import_credentialed_scan_helpers():
    import modules.credentialed_scan_helpers as h
    assert hasattr(h, "CredScanResult")
    assert hasattr(h, "_parse_linux")
    assert hasattr(h, "_parse_windows")
    assert hasattr(h, "_LINUX_CMDS")
    assert hasattr(h, "_WINDOWS_CMDS")


def test_credentialed_scan_helpers_dataclasses():
    from modules.credentialed_scan_helpers import (
        CredScanResult,
    )
    r = CredScanResult(host="192.168.1.1")
    assert r.host == "192.168.1.1"
    assert r.os_type == ""
    assert r.software == []


def test_parse_linux_empty():
    from modules.credentialed_scan_helpers import _parse_linux
    result = _parse_linux({})
    assert result.os_type == "linux"
    assert result.software == []


def test_cred_scan_re_exports():
    """Backwards compat: re-exports from credentialed_scan still work."""
    from modules.credentialed_scan import (
        CredScanResult,
    )
    assert CredScanResult is not None


# ── S20-3: notification_channels ─────────────────────────────────────────────

def test_import_notification_channels():
    import modules.notification_channels as nc
    assert hasattr(nc, "_build_payload")
    assert hasattr(nc, "_deliver_webhook")
    assert hasattr(nc, "_deliver_email")
    assert hasattr(nc, "_deliver_pushover")
    assert hasattr(nc, "_deliver_ntfy")
    assert hasattr(nc, "_deliver_telegram")


def test_build_payload_shape():
    from modules.alert_engine import AlertFired
    from modules.notification_channels import _build_payload
    alert = AlertFired(
        rule_name="Test", rule_type="HOST_DOWN",
        host="1.2.3.4", message="down", severity="CRITICAL", ts=1000,
    )
    p = _build_payload(alert)
    assert p["rule_name"] == "Test"
    assert p["severity"] == "CRITICAL"
    assert p["host"] == "1.2.3.4"


# ── S20-4: alert_suppressor ───────────────────────────────────────────────────

def test_import_alert_suppressor():
    import modules.alert_suppressor as sup
    assert hasattr(sup, "EscalationPolicy")
    assert hasattr(sup, "_default_rules")
    assert hasattr(sup, "rule_settings_key")


def test_escalation_policy_defaults():
    from modules.alert_suppressor import EscalationPolicy
    ep = EscalationPolicy(rule_name="High RTT")
    assert ep.wait_minutes == 15
    assert ep.enabled is True


def test_default_rules_count():
    from modules.alert_suppressor import _default_rules
    rules = _default_rules()
    assert len(rules) == 18  # V6 Sprint 1: +5; V6 Sprint 2: +3 (RTT Anomaly, IoT Behavior Anomaly, Trend Forecast)
    assert all(not r.enabled for r in rules)


def test_rule_settings_key():
    from modules.alert_suppressor import rule_settings_key
    key = rule_settings_key("High RTT")
    assert key == "alert_rules/high_rtt/enabled"


def test_alert_engine_re_exports():
    """Backwards compat: EscalationPolicy and rule_settings_key importable from alert_engine."""
    from modules.alert_engine import EscalationPolicy, rule_settings_key
    assert EscalationPolicy is not None
    assert callable(rule_settings_key)


# ── S20-5: report_isp ────────────────────────────────────────────────────────

def test_import_report_isp():
    import modules.report_isp as ri
    assert hasattr(ri, "generate_isp_report")
    assert hasattr(ri, "save_isp_report")
    assert hasattr(ri, "_ISP_CSS")


def test_generate_isp_report_no_data():
    from modules.report_isp import generate_isp_report
    html = generate_isp_report()
    assert "NetSentinel" in html
    assert "ISP Accountability Report" in html
    assert "<!DOCTYPE html>" in html


def test_report_exporter_re_exports():
    """Backwards compat: generate_isp_report importable from report_exporter."""
    from modules.report_exporter import generate_isp_report, save_isp_report
    assert callable(generate_isp_report)
    assert callable(save_isp_report)


# ── S20-6: network_log_writer ─────────────────────────────────────────────────

def test_import_network_log_writer():
    import modules.network_log_writer as nlw
    assert hasattr(nlw, "LogEntry")
    assert hasattr(nlw, "LogSummary")
    assert hasattr(nlw, "OutageSummary")
    assert hasattr(nlw, "AnalysisFinding")
    assert hasattr(nlw, "_compute_summary")
    assert hasattr(nlw, "analyse_log")
    assert hasattr(nlw, "load_log_file")
    assert hasattr(nlw, "list_log_files")


def test_compute_summary_empty():
    from modules.network_log_writer import _compute_summary
    s = _compute_summary([], "/tmp/test.csv")
    assert s.total_pings == 0
    assert s.uptime_pct == 100.0


def test_analyse_log_clean():
    from modules.network_log_writer import LogEntry, LogSummary, analyse_log
    entry = LogEntry(timestamp="2026-01-01T00:00:00", host="8.8.8.8",
                     rtt_ms=12.0, status="OK")
    summary = LogSummary(entries=[entry], total_pings=1)
    findings = analyse_log(summary)
    assert len(findings) >= 1
    assert findings[-1].severity == "INFO"


def test_network_logger_re_exports():
    """Backwards compat: LogEntry importable from network_logger."""
    from modules.network_logger import LogEntry, analyse_log
    assert LogEntry is not None
    assert callable(analyse_log)


# ── S20-7: speed_tester_backends ─────────────────────────────────────────────

def test_import_speed_tester_backends():
    import modules.speed_tester_backends as stb
    assert hasattr(stb, "SpeedServer")
    assert hasattr(stb, "SpeedTestResult")
    assert hasattr(stb, "_find_ookla_cli")
    assert hasattr(stb, "_run_ookla_cli")
    assert hasattr(stb, "_run_speedtest_cli")
    assert hasattr(stb, "_run_python_test")
    # Server discovery moved to speed_tester_servers (S20-7b split)
    import modules.speed_tester_servers as sts
    assert hasattr(sts, "_fetch_servers_python")


def test_speed_server_dataclass():
    from modules.speed_tester_backends import SpeedServer
    s = SpeedServer(id="1", name="Test ISP", city="London",
                    country="GB", host="test.example.com:8080", latency_ms=12.5)
    assert s.latency_ms == 12.5


def test_speed_test_result_dataclass():
    from modules.speed_tester_backends import SpeedTestResult
    r = SpeedTestResult(
        download_mbps=100.0, upload_mbps=50.0, ping_ms=12.0,
        server_name="Test", server_city="London", server_country="GB",
        backend="Pure-Python",
    )
    assert r.download_mbps == 100.0
    assert r.backend == "Pure-Python"
    assert r.timestamp != ""


def test_find_ookla_cli_returns_none_or_path():
    from modules.speed_tester_backends import _find_ookla_cli
    result = _find_ookla_cli()
    assert result is None or result.is_file()


def test_speed_tester_re_exports():
    """Backwards compat: SpeedServer, SpeedTestResult importable from speed_tester."""
    from modules.speed_tester import SpeedServer, speed_to_fraction
    assert SpeedServer is not None
    assert callable(speed_to_fraction)


def test_speed_to_fraction():
    from modules.speed_tester import speed_to_fraction
    assert speed_to_fraction(0) == 0.0
    assert 0.0 < speed_to_fraction(100) < 1.0
    assert speed_to_fraction(1000) <= 1.0
