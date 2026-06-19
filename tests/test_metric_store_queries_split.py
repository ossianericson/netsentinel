"""
Tests for metric_store_queries_uptime.py and metric_store_queries_metrics.py.

Verifies the E3 sprint split: all methods from the original
metric_store_queries.py are accessible through MetricStoreQueryMixin
after extraction into two sub-mixins.
"""
from unittest.mock import MagicMock


def _make_mixin():
    """Create a MetricStoreQueryMixin with a mock _execute_read/_execute_write."""
    from modules.metric_store_queries import MetricStoreQueryMixin

    class _Stub(MetricStoreQueryMixin):
        def __init__(self):
            self._retain_days = 30
            self._db_path = MagicMock()
            self._db_path.stat.return_value.st_size = 1024

        def _execute_read(self, sql, params=()):
            return []

        def _execute_write(self, sql, params=()):
            pass

    return _Stub()


# ── Uptime sub-mixin imports ──────────────────────────────────────────────────

def test_uptime_mixin_import():
    from modules.metric_store_queries_uptime import _UptimeQueriesMixin
    assert _UptimeQueriesMixin is not None


def test_uptime_mixin_methods():
    from modules.metric_store_queries_uptime import _UptimeQueriesMixin
    expected = {
        "query_all_state_ips",
        "query_uptime_table",
        "query_device_state_history",
        "query_uptime_pct",
        "query_device_events",
    }
    actual = {m for m in dir(_UptimeQueriesMixin) if not m.startswith("_")}
    assert expected <= actual


# ── Metrics sub-mixin imports ─────────────────────────────────────────────────

def test_metrics_mixin_import():
    from modules.metric_store_queries_metrics import _MetricsQueriesMixin
    assert _MetricsQueriesMixin is not None


def test_metrics_mixin_methods():
    from modules.metric_store_queries_metrics import _MetricsQueriesMixin
    expected = {
        "query_rtt_history",
        "query_all_rtt_hosts",
        "query_speed_test_history",
        "list_cve_lifecycles",
        "get_unacked_alerts",
        "get_recent_alerts",
        "get_last_event_time",
        "query_modem_signal_log",
        "query_mesh_signal_log",
        "query_plugin_log",
    }
    actual = {m for m in dir(_MetricsQueriesMixin) if not m.startswith("_")}
    assert expected <= actual


# ── MetricStoreQueryMixin composition ────────────────────────────────────────

def test_query_mixin_has_all_methods():
    from modules.metric_store_queries import MetricStoreQueryMixin
    expected = {
        # From uptime mixin
        "query_all_state_ips", "query_uptime_table",
        "query_device_state_history", "query_uptime_pct", "query_device_events",
        # From metrics mixin
        "query_rtt_history", "query_all_rtt_hosts", "query_speed_test_history",
        "list_cve_lifecycles", "get_unacked_alerts", "get_recent_alerts",
        "get_last_event_time", "query_modem_signal_log", "query_mesh_signal_log",
        "query_plugin_log",
        # Retained in main mixin
        "query_cert_status", "query_cert_history",
        "query_service_status", "query_service_history", "query_all_service_targets",
        "get_known_devices", "query_ha_detected", "query_ha_devices",
        "load_snapshot", "list_snapshots", "query_last_grade",
        "prune_old_data", "get_db_size_bytes", "get_row_counts",
    }
    actual = {m for m in dir(MetricStoreQueryMixin) if not m.startswith("_")}
    missing = expected - actual
    assert not missing, f"Methods missing from MetricStoreQueryMixin: {missing}"


# ── Behavioural tests (stub implementation) ───────────────────────────────────

def test_query_all_state_ips_returns_list():
    stub = _make_mixin()
    result = stub.query_all_state_ips(hours=1.0)
    assert isinstance(result, list)


def test_query_uptime_table_returns_list():
    stub = _make_mixin()
    result = stub.query_uptime_table(hours_list=[24.0])
    assert isinstance(result, list)


def test_query_rtt_history_returns_list():
    stub = _make_mixin()
    result = stub.query_rtt_history(host="8.8.8.8", hours=1.0)
    assert isinstance(result, list)


def test_query_speed_test_history_returns_list():
    stub = _make_mixin()
    result = stub.query_speed_test_history(hours=24.0)
    assert isinstance(result, list)


def test_get_recent_alerts_returns_list():
    stub = _make_mixin()
    result = stub.get_recent_alerts(hours=1.0)
    assert isinstance(result, list)


def test_prune_old_data_returns_int():
    stub = _make_mixin()
    result = stub.prune_old_data(retain_days=30)
    assert isinstance(result, int)


def test_get_row_counts_returns_dict():
    stub = _make_mixin()
    result = stub.get_row_counts()
    assert isinstance(result, dict)


def test_query_uptime_pct_none_on_empty():
    stub = _make_mixin()
    result = stub.query_uptime_pct("192.168.1.1", hours=1.0)
    assert result is None
