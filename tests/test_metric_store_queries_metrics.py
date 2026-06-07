"""Tests for modules/metric_store_queries_metrics.py — _MetricsQueriesMixin."""
from __future__ import annotations

import time


# ── Stub ────────────────────────────────────────────────────────────────────


def _make_stub(rows=None):
    """Return a _MetricsQueriesMixin instance with a stubbed _execute_read."""
    from modules.metric_store_queries_metrics import _MetricsQueriesMixin

    _rows = rows if rows is not None else []

    class _Stub(_MetricsQueriesMixin):
        def _execute_read(self, sql, params=()):
            return _rows

    return _Stub()


# ── Import ──────────────────────────────────────────────────────────────────


def test_import():
    from modules import metric_store_queries_metrics  # noqa: F401


def test_class_importable():
    from modules.metric_store_queries_metrics import _MetricsQueriesMixin
    assert _MetricsQueriesMixin is not None


# ── RTT ──────────────────────────────────────────────────────────────────────


def test_query_rtt_history_empty_returns_list():
    stub = _make_stub()
    result = stub.query_rtt_history("8.8.8.8", hours=1.0)
    assert isinstance(result, list)
    assert result == []


def test_query_rtt_history_maps_to_rtt_points():
    from modules.metric_store_schema import RttPoint
    now = int(time.time())
    rows = [{"ts": now, "host": "8.8.8.8", "rtt_ms": 12.5, "loss_pct": 0.0, "jitter_ms": 1.1}]
    stub = _make_stub(rows)
    result = stub.query_rtt_history("8.8.8.8", hours=24.0)
    assert len(result) == 1
    assert isinstance(result[0], RttPoint)
    assert result[0].host == "8.8.8.8"
    assert result[0].rtt_ms == 12.5


def test_query_all_rtt_hosts_returns_list_of_strings():
    rows = [{"host": "8.8.8.8"}, {"host": "1.1.1.1"}]
    stub = _make_stub(rows)
    result = stub.query_all_rtt_hosts(hours=24.0)
    assert isinstance(result, list)
    assert "8.8.8.8" in result
    assert "1.1.1.1" in result


# ── Speed test ────────────────────────────────────────────────────────────────


def test_query_speed_test_history_empty_returns_list():
    stub = _make_stub()
    result = stub.query_speed_test_history()
    assert isinstance(result, list)


def test_query_speed_test_history_maps_to_speed_test_points():
    from modules.metric_store_schema import SpeedTestPoint
    now = int(time.time())
    rows = [{
        "ts": now, "download_mbps": 200.0, "upload_mbps": 50.0, "ping_ms": 10.0,
        "server_name": "Test", "server_city": "NYC", "server_country": "US",
        "network_type": "5G", "signal_bars": 4, "nr5g_rsrp": -80.0, "nr5g_sinr": 15.0,
        "nr5g_band": "n78", "lte_rsrp": -90.0, "lte_band": "B3",
        "cell_id": "123", "enb_id": "456", "mcc": "310", "mnc": "260",
        "wan_ip": "1.2.3.4", "nr5g_rsrq": -10.0, "nr5g_pci": "1", "nr5g_arfcn": "2",
        "lte_snr": 5.0, "lte_rsrq": -8.0, "lte_pci": "3", "lte_earfcn": "4",
    }]
    stub = _make_stub(rows)
    result = stub.query_speed_test_history(hours=24.0)
    assert len(result) == 1
    assert isinstance(result[0], SpeedTestPoint)
    assert result[0].download_mbps == 200.0


# ── CVE ──────────────────────────────────────────────────────────────────────


def test_list_cve_lifecycles_empty_returns_list():
    stub = _make_stub()
    result = stub.list_cve_lifecycles()
    assert isinstance(result, list)


def test_list_cve_lifecycles_returns_dicts():
    rows = [
        {"id": 1, "cve_id": "CVE-2024-1234", "service": "ssh", "host": "10.0.0.1",
         "state": "open", "owner": None, "notes": None, "cvss_score": 9.8,
         "severity": "Critical", "description": "desc", "opened_ts": 0, "updated_ts": 0}
    ]
    stub = _make_stub(rows)
    result = stub.list_cve_lifecycles()
    assert len(result) == 1
    assert isinstance(result[0], dict)
    assert result[0]["cve_id"] == "CVE-2024-1234"


# ── Alerts ────────────────────────────────────────────────────────────────────


def test_get_unacked_alerts_empty_returns_list():
    stub = _make_stub()
    result = stub.get_unacked_alerts()
    assert isinstance(result, list)


def test_get_recent_alerts_empty_returns_list():
    stub = _make_stub()
    result = stub.get_recent_alerts(hours=24.0)
    assert isinstance(result, list)


def test_get_last_event_time_none_on_empty():
    stub = _make_stub([{"t": None}])
    result = stub.get_last_event_time("rogue_device")
    assert result is None


def test_get_last_event_time_returns_float():
    now = int(time.time())
    stub = _make_stub([{"t": now}])
    result = stub.get_last_event_time("rogue_device")
    assert isinstance(result, float)
    assert result == float(now)


# ── Modem / mesh ──────────────────────────────────────────────────────────────


def test_query_modem_signal_log_empty_returns_list():
    stub = _make_stub()
    result = stub.query_modem_signal_log()
    assert isinstance(result, list)


def test_query_mesh_signal_log_empty_returns_list():
    stub = _make_stub()
    result = stub.query_mesh_signal_log()
    assert isinstance(result, list)


# ── Plugin log ────────────────────────────────────────────────────────────────


def test_query_plugin_log_empty_returns_list():
    stub = _make_stub()
    result = stub.query_plugin_log()
    assert isinstance(result, list)
