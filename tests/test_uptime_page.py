"""
Tests for Uptime/SLA page — MetricStore.query_uptime_table() and
MetricStore.query_all_state_ips() (T2#13).
"""

from __future__ import annotations

import time

import pytest

from modules.metric_store import MetricStore


@pytest.fixture
def store(tmp_path):
    s = MetricStore(db_path=tmp_path / "test.db")
    yield s
    s.close()


def _write_states(store, ip, states, base_ts=None, interval=60):
    """Write a sequence of device_state rows for an IP."""
    ts = base_ts or int(time.time()) - len(states) * interval
    for state in states:
        store.record_device_state(ip, None, None, state, None, ts=ts)
        ts += interval


# ── query_all_state_ips ───────────────────────────────────────────────────────

class TestQueryAllStateIps:
    def test_empty_returns_empty(self, store):
        assert store.query_all_state_ips() == []

    def test_returns_known_ip(self, store):
        _write_states(store, "10.0.0.1", ["UP"])
        ips = store.query_all_state_ips()
        assert "10.0.0.1" in ips

    def test_multiple_ips(self, store):
        _write_states(store, "10.0.0.1", ["UP"])
        _write_states(store, "10.0.0.2", ["DOWN"])
        ips = set(store.query_all_state_ips())
        assert {"10.0.0.1", "10.0.0.2"} == ips

    def test_deduplicates_same_ip(self, store):
        _write_states(store, "10.0.0.1", ["UP", "DOWN", "UP"])
        ips = store.query_all_state_ips()
        assert ips.count("10.0.0.1") == 1

    def test_window_excludes_old_records(self, store):
        old_ts = int(time.time()) - 800 * 3600  # ~33 days ago
        store.record_device_state("old.host", None, None, "UP", None, ts=old_ts)
        # query_all_state_ips uses 720h (30d) window by default
        ips = store.query_all_state_ips(hours=720.0)
        assert "old.host" not in ips


# ── query_uptime_table ────────────────────────────────────────────────────────

class TestQueryUptimeTable:
    def test_empty_returns_empty(self, store):
        assert store.query_uptime_table() == []

    def test_single_ip_all_up(self, store):
        _write_states(store, "10.0.0.1", ["UP"] * 10)
        rows = store.query_uptime_table()
        assert len(rows) == 1
        assert rows[0]["ip"] == "10.0.0.1"
        assert rows[0]["24.0"] == 100.0

    def test_single_ip_all_down(self, store):
        _write_states(store, "10.0.0.1", ["DOWN"] * 10)
        rows = store.query_uptime_table()
        assert rows[0]["24.0"] == 0.0

    def test_50_percent_up(self, store):
        _write_states(store, "10.0.0.1", ["UP", "DOWN"] * 5)
        rows = store.query_uptime_table()
        assert rows[0]["24.0"] == 50.0

    def test_multiple_ips(self, store):
        _write_states(store, "10.0.0.1", ["UP"] * 5)
        _write_states(store, "10.0.0.2", ["DOWN"] * 5)
        rows = store.query_uptime_table()
        assert len(rows) == 2
        ips = {r["ip"] for r in rows}
        assert ips == {"10.0.0.1", "10.0.0.2"}

    def test_hostname_included(self, store):
        now = int(time.time())
        store.record_device_state("10.0.0.1", None, "myrouter", "UP", None, ts=now)
        rows = store.query_uptime_table()
        assert rows[0]["hostname"] == "myrouter"

    def test_hostname_is_none_when_not_recorded(self, store):
        _write_states(store, "10.0.0.1", ["UP"])
        rows = store.query_uptime_table()
        assert rows[0]["hostname"] is None

    def test_keys_include_all_windows(self, store):
        _write_states(store, "10.0.0.1", ["UP"])
        rows = store.query_uptime_table()
        assert "24.0"  in rows[0]
        assert "168.0" in rows[0]
        assert "720.0" in rows[0]

    def test_custom_hours_list(self, store):
        _write_states(store, "10.0.0.1", ["UP"])
        rows = store.query_uptime_table(hours_list=[6.0, 12.0])
        assert "6.0"  in rows[0]
        assert "12.0" in rows[0]
        assert "24.0" not in rows[0]

    def test_uptime_for_7d_window(self, store):
        now = int(time.time())
        # 5 UP samples within 7 days, 5 DOWN samples
        for i in range(5):
            store.record_device_state(
                "10.0.0.1", None, None, "UP", None, ts=now - (7 * 86400 - i * 3600)
            )
            store.record_device_state(
                "10.0.0.1", None, None, "DOWN", None, ts=now - (7 * 86400 - i * 3600 - 1800)
            )
        rows = store.query_uptime_table()
        # 7d uptime should be 50%
        assert rows[0]["168.0"] == 50.0

    def test_no_data_in_window_returns_100(self, store):
        # Write data too old to be in any window
        old_ts = int(time.time()) - 800 * 3600
        store.record_device_state("10.0.0.1", None, None, "DOWN", None, ts=old_ts)
        # IP won't even appear in query_all_state_ips (30d window)
        rows = store.query_uptime_table()
        assert rows == []

    def test_returns_ip_field(self, store):
        _write_states(store, "192.168.1.1", ["UP"] * 3)
        rows = store.query_uptime_table()
        assert rows[0]["ip"] == "192.168.1.1"
