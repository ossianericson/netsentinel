"""Tests for modules/metric_store_queries_uptime.py — _UptimeQueriesMixin."""
from __future__ import annotations

import time


# ── Stub ────────────────────────────────────────────────────────────────────


def _make_stub(rows=None):
    """Return a _UptimeQueriesMixin instance with a stubbed _execute_read."""
    from modules.metric_store_queries_uptime import _UptimeQueriesMixin

    _rows = rows if rows is not None else []

    class _Stub(_UptimeQueriesMixin):
        def _execute_read(self, sql, params=()):
            return _rows

    return _Stub()


# ── Import ──────────────────────────────────────────────────────────────────


def test_import():
    from modules import metric_store_queries_uptime  # noqa: F401


def test_class_importable():
    from modules.metric_store_queries_uptime import _UptimeQueriesMixin
    assert _UptimeQueriesMixin is not None


# ── query_all_state_ips ───────────────────────────────────────────────────────


def test_query_all_state_ips_empty_returns_list():
    stub = _make_stub()
    result = stub.query_all_state_ips()
    assert isinstance(result, list)
    assert result == []


def test_query_all_state_ips_returns_strings():
    rows = [{"ip": "192.168.1.1"}, {"ip": "192.168.1.2"}]
    stub = _make_stub(rows)
    result = stub.query_all_state_ips(hours=24.0)
    assert result == ["192.168.1.1", "192.168.1.2"]


# ── query_uptime_pct ──────────────────────────────────────────────────────────


def test_query_uptime_pct_none_on_no_data():
    stub = _make_stub([{"total": 0, "up_count": 0}])
    result = stub.query_uptime_pct("192.168.1.1", hours=24.0)
    assert result is None


def test_query_uptime_pct_none_on_empty():
    stub = _make_stub([])
    result = stub.query_uptime_pct("192.168.1.1", hours=24.0)
    assert result is None


def test_query_uptime_pct_returns_float():
    stub = _make_stub([{"total": 10, "up_count": 9}])
    result = stub.query_uptime_pct("192.168.1.1", hours=24.0)
    assert isinstance(result, float)
    assert result == 90.0


def test_query_uptime_pct_100_when_all_up():
    stub = _make_stub([{"total": 5, "up_count": 5}])
    result = stub.query_uptime_pct("10.0.0.1", hours=1.0)
    assert result == 100.0


# ── query_uptime_table ────────────────────────────────────────────────────────


def test_query_uptime_table_empty_returns_list():
    stub = _make_stub()
    result = stub.query_uptime_table()
    assert isinstance(result, list)


def test_query_uptime_table_default_hours_list():
    stub = _make_stub()
    result = stub.query_uptime_table(hours_list=[24.0, 168.0])
    assert isinstance(result, list)


# ── query_device_state_history ────────────────────────────────────────────────


def test_query_device_state_history_empty_returns_list():
    stub = _make_stub()
    result = stub.query_device_state_history("10.0.0.1", hours=24.0)
    assert isinstance(result, list)


def test_query_device_state_history_maps_to_device_state_points():
    from modules.metric_store_schema import DeviceStatePoint
    now = int(time.time())
    rows = [{
        "ts": now, "ip": "10.0.0.1", "mac": "aa:bb:cc:dd:ee:ff",
        "hostname": "router", "state": "UP", "rtt_ms": 1.5,
    }]
    stub = _make_stub(rows)
    result = stub.query_device_state_history("10.0.0.1", hours=1.0)
    assert len(result) == 1
    assert isinstance(result[0], DeviceStatePoint)
    assert result[0].ip == "10.0.0.1"
    assert result[0].state == "UP"


# ── query_device_events ───────────────────────────────────────────────────────


def test_query_device_events_empty_returns_list():
    stub = _make_stub()
    result = stub.query_device_events(hours=24.0)
    assert isinstance(result, list)


def test_query_device_events_maps_to_device_events():
    from modules.metric_store_schema import DeviceEvent
    now = int(time.time())
    rows = [{
        "ts": now, "ip": "10.0.0.1", "mac": "aa:bb:cc:dd:ee:ff",
        "event_type": "NEW", "detail": "first seen",
    }]
    stub = _make_stub(rows)
    result = stub.query_device_events(hours=24.0)
    assert len(result) == 1
    assert isinstance(result[0], DeviceEvent)
    assert result[0].event_type == "NEW"
