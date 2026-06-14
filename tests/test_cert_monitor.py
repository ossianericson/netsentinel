"""
Tests for CertMonitor and cert-related MetricStore + AlertEngine extensions.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from modules.cert_monitor import CertMonitor, CertTarget
from modules.metric_store import MetricStore
from modules.tls_checker import CertInfo


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def store(tmp_path):
    s = MetricStore(db_path=tmp_path / "test.db")
    yield s
    s.close()


def _make_cert(host="example.com", port=443, days=90, expired=False,
               self_signed=False, error=""):
    info = CertInfo(host=host, port=port)
    info.days_remaining = days
    info.is_expired = expired
    info.is_self_signed = self_signed
    info.subject = f"CN={host}"
    info.issuer = "CN=Let's Encrypt" if not self_signed else f"CN={host}"
    info.not_after = "Jan  1 00:00:00 2030 GMT"
    info.error = error
    if error:
        info.verdict = f"Error: {error}"
    elif expired:
        info.verdict = f"EXPIRED cert on {host}:{port}"
    elif days < 14:
        info.verdict = f"Expiring soon: {days} days"
    else:
        info.verdict = f"Valid cert: {days} days remaining"
    return info


# ── MetricStore cert_check table ──────────────────────────────────────────────

class TestMetricStoreCert:
    def test_record_and_query_cert_check(self, store):
        store.record_cert_check("example.com", 443, days_remaining=90,
                                subject="CN=example.com", issuer="CN=Let's Encrypt",
                                not_after="Jan  1 00:00:00 2030 GMT")
        rows = store.query_cert_status()
        assert len(rows) == 1
        r = rows[0]
        assert r.host == "example.com"
        assert r.port == 443
        assert r.days_remaining == 90
        assert r.subject == "CN=example.com"
        assert not r.is_expired

    def test_query_cert_status_returns_latest_per_host_port(self, store):
        now = int(time.time())
        store.record_cert_check("example.com", 443, days_remaining=60, ts=now - 100)
        store.record_cert_check("example.com", 443, days_remaining=59, ts=now)
        rows = store.query_cert_status()
        assert len(rows) == 1
        assert rows[0].days_remaining == 59

    def test_query_cert_status_multiple_hosts(self, store):
        store.record_cert_check("alpha.com", 443, days_remaining=100)
        store.record_cert_check("beta.com", 443, days_remaining=5)
        store.record_cert_check("beta.com", 8443, days_remaining=200)
        rows = store.query_cert_status()
        assert len(rows) == 3
        hosts = {(r.host, r.port) for r in rows}
        assert ("alpha.com", 443) in hosts
        assert ("beta.com", 443) in hosts
        assert ("beta.com", 8443) in hosts

    def test_query_cert_status_empty(self, store):
        assert store.query_cert_status() == []

    def test_query_cert_history_ordered_asc(self, store):
        now = int(time.time())
        store.record_cert_check("example.com", 443, days_remaining=91, ts=now - 200)
        store.record_cert_check("example.com", 443, days_remaining=90, ts=now - 100)
        store.record_cert_check("example.com", 443, days_remaining=89, ts=now)
        rows = store.query_cert_history("example.com", 443)
        assert len(rows) == 3
        assert rows[0].days_remaining == 91
        assert rows[-1].days_remaining == 89

    def test_query_cert_history_filters_by_host_port(self, store):
        store.record_cert_check("alpha.com", 443, days_remaining=80)
        store.record_cert_check("beta.com", 443, days_remaining=70)
        rows = store.query_cert_history("alpha.com", 443)
        assert all(r.host == "alpha.com" for r in rows)

    def test_record_expired_cert(self, store):
        store.record_cert_check("bad.com", 443, days_remaining=-5, is_expired=True)
        rows = store.query_cert_status()
        assert rows[0].is_expired is True
        assert rows[0].days_remaining == -5

    def test_record_self_signed_cert(self, store):
        store.record_cert_check("internal.com", 443, is_self_signed=True, days_remaining=365)
        rows = store.query_cert_status()
        assert rows[0].is_self_signed is True

    def test_record_cert_with_error(self, store):
        store.record_cert_check("unreachable.com", 443, error="Connection refused")
        rows = store.query_cert_status()
        assert rows[0].error == "Connection refused"
        assert rows[0].days_remaining is None

    def test_prune_removes_cert_check_rows(self, store):
        old_ts = int(time.time()) - 40 * 86400
        store.record_cert_check("old.com", 443, days_remaining=300, ts=old_ts)
        store.record_cert_check("new.com", 443, days_remaining=100)
        store.prune_old_data(retain_days=30)
        rows = store.query_cert_status(hours=24 * 60)
        hosts = {r.host for r in rows}
        assert "old.com" not in hosts
        assert any(h == "new.com" for h in hosts)

    def test_get_row_counts_includes_cert_check(self, store):
        store.record_cert_check("example.com", 443, days_remaining=90)
        counts = store.get_row_counts()
        assert "cert_check" in counts
        assert counts["cert_check"] == 1

    def test_schema_version_is_2(self, store):
        rows = store._execute_read("SELECT value FROM meta WHERE key='schema_version'", ())
        assert rows[0]["value"] == "15"


# ── CertMonitor ───────────────────────────────────────────────────────────────

class TestCertMonitor:
    def test_run_check_records_to_store(self, store):
        target = CertTarget(host="example.com", ports=[443])
        monitor = CertMonitor(store=store, targets=[target])
        mock_info = _make_cert("example.com", 443, days=90)

        with patch("modules.cert_monitor.check_host_certs", return_value=[mock_info]):
            results = monitor.run_check()

        assert len(results) == 1
        rows = store.query_cert_status()
        assert len(rows) == 1
        assert rows[0].host == "example.com"
        assert rows[0].days_remaining == 90

    def test_run_check_multiple_targets(self, store):
        targets = [
            CertTarget("alpha.com", [443]),
            CertTarget("beta.com", [443, 8443]),
        ]
        monitor = CertMonitor(store=store, targets=targets)

        def _mock_check(host, ports):
            return [_make_cert(host, p) for p in ports]

        with patch("modules.cert_monitor.check_host_certs", side_effect=_mock_check):
            results = monitor.run_check()

        assert len(results) == 3
        rows = store.query_cert_status()
        assert len(rows) == 3

    def test_run_check_calls_on_result_callback(self, store):
        target = CertTarget(host="example.com", ports=[443])
        callback = MagicMock()
        monitor = CertMonitor(store=store, targets=[target], on_result=callback)
        mock_info = _make_cert("example.com", 443)

        with patch("modules.cert_monitor.check_host_certs", return_value=[mock_info]):
            monitor.run_check()

        callback.assert_called_once()
        args = callback.call_args[0][0]
        assert len(args) == 1

    def test_run_check_handles_exception_per_target(self, store):
        target = CertTarget(host="fail.com", ports=[443])
        monitor = CertMonitor(store=store, targets=[target])

        with patch("modules.cert_monitor.check_host_certs", side_effect=OSError("timeout")):
            results = monitor.run_check()

        # Error CertInfo should still be produced
        assert len(results) == 1
        assert results[0].error == "timeout"

    def test_run_check_error_recorded_to_store(self, store):
        target = CertTarget(host="fail.com", ports=[443])
        monitor = CertMonitor(store=store, targets=[target])

        with patch("modules.cert_monitor.check_host_certs", side_effect=OSError("refused")):
            monitor.run_check()

        rows = store.query_cert_status()
        assert len(rows) == 1
        assert rows[0].error == "refused"

    def test_set_targets_replaces_list(self, store):
        monitor = CertMonitor(store=store, targets=[CertTarget("old.com")])
        monitor.set_targets([CertTarget("new.com")])
        assert monitor.get_targets()[0].host == "new.com"

    def test_run_check_no_targets_returns_empty(self, store):
        monitor = CertMonitor(store=store, targets=[])
        results = monitor.run_check()
        assert results == []

    def test_expired_cert_stored_correctly(self, store):
        target = CertTarget(host="expired.com", ports=[443])
        monitor = CertMonitor(store=store, targets=[target])
        mock_info = _make_cert("expired.com", 443, days=-10, expired=True)

        with patch("modules.cert_monitor.check_host_certs", return_value=[mock_info]):
            monitor.run_check()

        rows = store.query_cert_status()
        assert rows[0].is_expired is True
        assert rows[0].days_remaining == -10


# ── AlertEngine cert rules ────────────────────────────────────────────────────

class TestAlertEngineCert:
    def setup_method(self):
        from modules.alert_engine import AlertEngine, AlertRule
        self.AlertEngine = AlertEngine
        self.AlertRule = AlertRule

    def test_cert_expiry_fires_when_below_threshold(self, store):
        from modules.alert_engine import AlertRule, AlertEngine
        rule = AlertRule(
            name="Cert Expiring",
            rule_type="CERT_EXPIRY",
            threshold_days=30,
            cooldown_s=0,
        )
        engine = AlertEngine(store=store, rules=[rule])
        results = [_make_cert("example.com", 443, days=10)]
        fired = engine.evaluate_cert_checks(results)
        assert len(fired) == 1
        assert fired[0].rule_type == "CERT_EXPIRY"
        assert "10 day" in fired[0].message

    def test_cert_expiry_does_not_fire_when_above_threshold(self, store):
        from modules.alert_engine import AlertRule, AlertEngine
        rule = AlertRule(
            name="Cert Expiring",
            rule_type="CERT_EXPIRY",
            threshold_days=30,
            cooldown_s=0,
        )
        engine = AlertEngine(store=store, rules=[rule])
        results = [_make_cert("example.com", 443, days=60)]
        fired = engine.evaluate_cert_checks(results)
        assert fired == []

    def test_cert_expired_fires_on_expired_cert(self, store):
        from modules.alert_engine import AlertRule, AlertEngine
        rule = AlertRule(name="Cert Expired", rule_type="CERT_EXPIRED", cooldown_s=0)
        engine = AlertEngine(store=store, rules=[rule])
        results = [_make_cert("example.com", 443, days=-5, expired=True)]
        fired = engine.evaluate_cert_checks(results)
        assert len(fired) == 1
        assert fired[0].severity == "CRITICAL"

    def test_cert_expired_does_not_fire_for_valid_cert(self, store):
        from modules.alert_engine import AlertRule, AlertEngine
        rule = AlertRule(name="Cert Expired", rule_type="CERT_EXPIRED", cooldown_s=0)
        engine = AlertEngine(store=store, rules=[rule])
        results = [_make_cert("example.com", 443, days=90)]
        fired = engine.evaluate_cert_checks(results)
        assert fired == []

    def test_cert_rule_skips_unreachable_hosts(self, store):
        from modules.alert_engine import AlertRule, AlertEngine
        rule = AlertRule(
            name="Cert Expiring",
            rule_type="CERT_EXPIRY",
            threshold_days=30,
            cooldown_s=0,
        )
        engine = AlertEngine(store=store, rules=[rule])
        results = [_make_cert("down.com", 443, error="Connection refused")]
        fired = engine.evaluate_cert_checks(results)
        assert fired == []

    def test_cert_rule_cooldown_suppresses_repeat(self, store):
        from modules.alert_engine import AlertRule, AlertEngine
        rule = AlertRule(
            name="Cert Expiring",
            rule_type="CERT_EXPIRY",
            threshold_days=30,
            cooldown_s=9999,
        )
        engine = AlertEngine(store=store, rules=[rule])
        results = [_make_cert("example.com", 443, days=10)]
        fired1 = engine.evaluate_cert_checks(results)
        fired2 = engine.evaluate_cert_checks(results)
        assert len(fired1) == 1
        assert len(fired2) == 0

    def test_cert_rule_host_filter(self, store):
        from modules.alert_engine import AlertRule, AlertEngine
        rule = AlertRule(
            name="Cert Watch",
            rule_type="CERT_EXPIRY",
            host="alpha.com",
            threshold_days=30,
            cooldown_s=0,
        )
        engine = AlertEngine(store=store, rules=[rule])
        results = [
            _make_cert("alpha.com", 443, days=10),
            _make_cert("beta.com", 443, days=10),
        ]
        fired = engine.evaluate_cert_checks(results)
        assert len(fired) == 1
        assert fired[0].host in ("alpha.com", "alpha.com:443")

    def test_default_rules_include_cert_rules(self):
        from modules.alert_engine import AlertEngine
        engine = AlertEngine()
        types = {r.rule_type for r in engine.get_rules()}
        assert "CERT_EXPIRY" in types
        assert "CERT_EXPIRED" in types

    def test_cert_rule_with_dict_input(self, store):
        """evaluate_cert_checks must accept dicts as well as CertInfo objects."""
        from modules.alert_engine import AlertRule, AlertEngine
        rule = AlertRule(
            name="Cert Expiring",
            rule_type="CERT_EXPIRY",
            threshold_days=30,
            cooldown_s=0,
        )
        engine = AlertEngine(store=store, rules=[rule])
        results = [{"host": "example.com", "port": 443, "days_remaining": 5,
                    "is_expired": False, "error": None}]
        fired = engine.evaluate_cert_checks(results)
        assert len(fired) == 1

    def test_cert_expiry_exactly_at_threshold_does_not_fire(self, store):
        from modules.alert_engine import AlertRule, AlertEngine
        rule = AlertRule(
            name="Cert Expiring",
            rule_type="CERT_EXPIRY",
            threshold_days=30,
            cooldown_s=0,
        )
        engine = AlertEngine(store=store, rules=[rule])
        results = [_make_cert("example.com", 443, days=30)]
        fired = engine.evaluate_cert_checks(results)
        assert fired == []  # strictly less-than threshold
