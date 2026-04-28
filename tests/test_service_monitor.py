"""
Tests for ServiceMonitor, MetricStore service_check table, and
AlertEngine SERVICE_DOWN rule (T2#7).
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from modules.metric_store import MetricStore, ServiceCheckPoint
from modules.service_monitor import ServiceMonitor, ServiceTarget, check_tcp


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def store(tmp_path):
    s = MetricStore(db_path=tmp_path / "test.db")
    yield s
    s.close()


# ── check_tcp unit tests ──────────────────────────────────────────────────────

class TestCheckTcp:
    def test_returns_up_true_rtt_on_success(self):
        with patch("modules.service_monitor.socket.create_connection") as mock_conn:
            mock_conn.return_value.__enter__ = lambda s: s
            mock_conn.return_value.__exit__ = MagicMock(return_value=False)
            up, rtt, error = check_tcp("example.com", 80)
        assert up is True
        assert rtt is not None
        assert rtt >= 0
        assert error == ""

    def test_returns_down_on_connection_refused(self):
        with patch("modules.service_monitor.socket.create_connection",
                   side_effect=ConnectionRefusedError("refused")):
            up, rtt, error = check_tcp("localhost", 9)
        assert up is False
        assert rtt is None
        assert "refused" in error

    def test_returns_down_on_timeout(self):
        with patch("modules.service_monitor.socket.create_connection",
                   side_effect=TimeoutError("timed out")):
            up, rtt, error = check_tcp("10.0.0.254", 80, timeout=0.01)
        assert up is False
        assert rtt is None

    def test_returns_down_on_oserror(self):
        with patch("modules.service_monitor.socket.create_connection",
                   side_effect=OSError("network unreachable")):
            up, rtt, error = check_tcp("10.0.0.254", 443)
        assert up is False


# ── ServiceTarget defaults ────────────────────────────────────────────────────

class TestServiceTarget:
    def test_label_auto_generated_when_empty(self):
        t = ServiceTarget(host="192.168.1.1", port=80)
        assert t.label == "192.168.1.1:80"

    def test_explicit_label_preserved(self):
        t = ServiceTarget(host="192.168.1.1", port=80, label="Router HTTP")
        assert t.label == "Router HTTP"

    def test_default_timeout_is_3(self):
        t = ServiceTarget(host="x", port=22)
        assert t.timeout == 3.0


# ── MetricStore service_check table ──────────────────────────────────────────

class TestMetricStoreServiceCheck:
    def test_record_and_query_service_check(self, store):
        store.record_service_check("192.168.1.1", 80, up=True, rtt_ms=5.2, label="HTTP")
        rows = store.query_service_status()
        assert len(rows) == 1
        r = rows[0]
        assert r.host == "192.168.1.1"
        assert r.port == 80
        assert r.up is True
        assert r.rtt_ms == pytest.approx(5.2)
        assert r.label == "HTTP"

    def test_query_service_status_returns_latest_per_host_port(self, store):
        now = int(time.time())
        store.record_service_check("host", 80, up=True,  rtt_ms=10.0, ts=now - 100)
        store.record_service_check("host", 80, up=False, rtt_ms=None, ts=now)
        rows = store.query_service_status()
        assert len(rows) == 1
        assert rows[0].up is False

    def test_query_service_status_multiple_services(self, store):
        store.record_service_check("alpha", 80,  up=True,  rtt_ms=5.0)
        store.record_service_check("alpha", 443, up=True,  rtt_ms=8.0)
        store.record_service_check("beta",  22,  up=False, rtt_ms=None)
        rows = store.query_service_status()
        assert len(rows) == 3

    def test_query_service_status_empty(self, store):
        assert store.query_service_status() == []

    def test_query_service_history_ordered_asc(self, store):
        now = int(time.time())
        store.record_service_check("host", 80, up=True, rtt_ms=10.0, ts=now - 200)
        store.record_service_check("host", 80, up=True, rtt_ms=9.0,  ts=now - 100)
        store.record_service_check("host", 80, up=True, rtt_ms=8.0,  ts=now)
        rows = store.query_service_history("host", 80)
        assert rows[0].rtt_ms == pytest.approx(10.0)
        assert rows[-1].rtt_ms == pytest.approx(8.0)

    def test_query_service_history_filters_port(self, store):
        store.record_service_check("host", 80,  up=True, rtt_ms=5.0)
        store.record_service_check("host", 443, up=True, rtt_ms=6.0)
        rows = store.query_service_history("host", 80)
        assert all(r.port == 80 for r in rows)

    def test_record_down_service_no_rtt(self, store):
        store.record_service_check("host", 9999, up=False, rtt_ms=None,
                                   error="Connection refused")
        rows = store.query_service_status()
        assert rows[0].up is False
        assert rows[0].rtt_ms is None
        assert rows[0].error == "Connection refused"

    def test_query_all_service_targets(self, store):
        store.record_service_check("alpha", 80,  up=True, label="HTTP")
        store.record_service_check("alpha", 443, up=True, label="HTTPS")
        store.record_service_check("beta",  22,  up=True, label="SSH")
        targets = store.query_all_service_targets()
        assert len(targets) == 3

    def test_prune_removes_service_check_rows(self, store):
        old_ts = int(time.time()) - 40 * 86400
        store.record_service_check("old.host", 80, up=True, ts=old_ts)
        store.record_service_check("new.host", 80, up=True)
        store.prune_old_data(retain_days=30)
        rows = store.query_service_status(hours=24 * 60)
        hosts = {r.host for r in rows}
        assert "old.host" not in hosts
        assert "new.host" in hosts

    def test_get_row_counts_includes_service_check(self, store):
        store.record_service_check("host", 80, up=True)
        counts = store.get_row_counts()
        assert "service_check" in counts
        assert counts["service_check"] == 1

    def test_schema_version_is_3(self, store):
        rows = store._execute_read("SELECT value FROM meta WHERE key='schema_version'", ())
        assert rows[0]["value"] == "7"


# ── ServiceMonitor ────────────────────────────────────────────────────────────

class TestServiceMonitor:
    def test_run_check_records_to_store(self, store):
        target = ServiceTarget("example.com", 80, label="HTTP")
        monitor = ServiceMonitor(store=store, targets=[target])

        with patch("modules.service_monitor.check_tcp", return_value=(True, 5.0, "")):
            results = monitor.run_check()

        assert len(results) == 1
        assert results[0].up is True
        rows = store.query_service_status()
        assert len(rows) == 1
        assert rows[0].host == "example.com"

    def test_run_check_multiple_targets(self, store):
        targets = [
            ServiceTarget("alpha.com", 80),
            ServiceTarget("beta.com", 443),
        ]
        monitor = ServiceMonitor(store=store, targets=targets)

        with patch("modules.service_monitor.check_tcp", return_value=(True, 3.0, "")):
            results = monitor.run_check()

        assert len(results) == 2
        assert len(store.query_service_status()) == 2

    def test_run_check_down_service(self, store):
        target = ServiceTarget("bad.host", 9999)
        monitor = ServiceMonitor(store=store, targets=[target])

        with patch("modules.service_monitor.check_tcp",
                   return_value=(False, None, "Connection refused")):
            results = monitor.run_check()

        assert results[0].up is False
        assert results[0].rtt_ms is None
        rows = store.query_service_status()
        assert rows[0].up is False

    def test_run_check_calls_on_result(self, store):
        callback = MagicMock()
        monitor = ServiceMonitor(store=store,
                                 targets=[ServiceTarget("x", 80)],
                                 on_result=callback)
        with patch("modules.service_monitor.check_tcp", return_value=(True, 1.0, "")):
            monitor.run_check()
        callback.assert_called_once()

    def test_run_check_no_targets(self, store):
        monitor = ServiceMonitor(store=store, targets=[])
        results = monitor.run_check()
        assert results == []

    def test_set_targets(self, store):
        monitor = ServiceMonitor(store=store, targets=[ServiceTarget("old", 80)])
        monitor.set_targets([ServiceTarget("new", 443)])
        assert monitor.get_targets()[0].host == "new"

    def test_label_passed_to_store(self, store):
        target = ServiceTarget("host", 80, label="My Service")
        monitor = ServiceMonitor(store=store, targets=[target])
        with patch("modules.service_monitor.check_tcp", return_value=(True, 2.0, "")):
            monitor.run_check()
        rows = store.query_service_status()
        assert rows[0].label == "My Service"


# ── AlertEngine SERVICE_DOWN rule ─────────────────────────────────────────────

class TestAlertEngineServiceDown:
    def test_fires_when_service_is_down(self, store):
        from modules.alert_engine import AlertEngine, AlertRule
        rule = AlertRule(name="Svc Down", rule_type="SERVICE_DOWN", cooldown_s=0)
        engine = AlertEngine(store=store, rules=[rule])
        results = [{"host": "192.168.1.1", "port": 80, "up": False,
                    "label": "HTTP", "error": "refused"}]
        fired = engine.evaluate_service_checks(results)
        assert len(fired) == 1
        assert fired[0].rule_type == "SERVICE_DOWN"
        assert "HTTP" in fired[0].message

    def test_does_not_fire_when_service_is_up(self, store):
        from modules.alert_engine import AlertEngine, AlertRule
        rule = AlertRule(name="Svc Down", rule_type="SERVICE_DOWN", cooldown_s=0)
        engine = AlertEngine(store=store, rules=[rule])
        results = [{"host": "192.168.1.1", "port": 80, "up": True,
                    "label": "HTTP", "error": ""}]
        fired = engine.evaluate_service_checks(results)
        assert fired == []

    def test_cooldown_suppresses_repeat(self, store):
        from modules.alert_engine import AlertEngine, AlertRule
        rule = AlertRule(name="Svc Down", rule_type="SERVICE_DOWN", cooldown_s=9999)
        engine = AlertEngine(store=store, rules=[rule])
        results = [{"host": "host", "port": 80, "up": False, "label": "x", "error": ""}]
        fired1 = engine.evaluate_service_checks(results)
        fired2 = engine.evaluate_service_checks(results)
        assert len(fired1) == 1
        assert len(fired2) == 0

    def test_host_filter(self, store):
        from modules.alert_engine import AlertEngine, AlertRule
        rule = AlertRule(name="Svc Down", rule_type="SERVICE_DOWN",
                         host="watched:80", cooldown_s=0)
        engine = AlertEngine(store=store, rules=[rule])
        results = [
            {"host": "watched", "port": 80, "up": False, "label": "W", "error": ""},
            {"host": "other",   "port": 80, "up": False, "label": "O", "error": ""},
        ]
        fired = engine.evaluate_service_checks(results)
        assert len(fired) == 1
        assert "watched" in fired[0].host

    def test_default_rules_include_service_down(self):
        from modules.alert_engine import AlertEngine
        engine = AlertEngine()
        types = {r.rule_type for r in engine.get_rules()}
        assert "SERVICE_DOWN" in types

    def test_multiple_down_services_all_fire(self, store):
        from modules.alert_engine import AlertEngine, AlertRule
        rule = AlertRule(name="Svc Down", rule_type="SERVICE_DOWN", cooldown_s=0)
        engine = AlertEngine(store=store, rules=[rule])
        results = [
            {"host": "a", "port": 80,  "up": False, "label": "HTTP",  "error": ""},
            {"host": "b", "port": 443, "up": False, "label": "HTTPS", "error": ""},
        ]
        fired = engine.evaluate_service_checks(results)
        assert len(fired) == 2

    def test_service_down_severity_is_critical(self, store):
        from modules.alert_engine import AlertEngine, AlertRule
        rule = AlertRule(name="Svc Down", rule_type="SERVICE_DOWN", cooldown_s=0)
        engine = AlertEngine(store=store, rules=[rule])
        results = [{"host": "host", "port": 80, "up": False, "label": "x", "error": ""}]
        fired = engine.evaluate_service_checks(results)
        assert fired[0].severity == "CRITICAL"
