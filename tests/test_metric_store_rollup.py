"""Tests for modules/metric_store_rollup.py — _RollupMixin (Stability Sprint 2 / G4).

daily_rollup survives raw-row pruning so long-term trend charts have data
beyond the 30-day rtt_sample retention window.
"""
import time

import pytest

from modules.metric_store import MetricStore


@pytest.fixture
def store(tmp_path):
    s = MetricStore(db_path=tmp_path / "test.db")
    yield s
    s.close()


def test_import():
    from modules import metric_store_rollup  # noqa: F401


def test_record_daily_rollup_round_trip(store):
    store.record_daily_rollup("2026-01-01", "rtt_ms", "host1", 1.0, 5.0, 10.0, 3)
    rows = store.query_daily_rollup("rtt_ms", host="host1")
    assert len(rows) == 1
    assert rows[0].day == "2026-01-01"
    assert rows[0].min == 1.0
    assert rows[0].avg == 5.0
    assert rows[0].max == 10.0
    assert rows[0].n == 3


def test_record_daily_rollup_upsert_merges_weighted_average(store):
    """Two partial rollups for the same (day, metric, host) must merge into a
    single row with a correctly weighted average, not silently overwrite."""
    store.record_daily_rollup("2026-01-01", "rtt_ms", "host1", 10.0, 10.0, 10.0, 1)
    store.record_daily_rollup("2026-01-01", "rtt_ms", "host1", 20.0, 20.0, 20.0, 1)
    rows = store.query_daily_rollup("rtt_ms", host="host1")
    assert len(rows) == 1
    assert rows[0].min == 10.0
    assert rows[0].max == 20.0
    assert rows[0].avg == 15.0
    assert rows[0].n == 2


def test_query_daily_rollup_filters_by_metric(store):
    store.record_daily_rollup("2026-01-01", "rtt_ms", "host1", 1.0, 5.0, 10.0, 3)
    store.record_daily_rollup("2026-01-01", "loss_pct", "host1", 0.0, 1.0, 2.0, 3)
    rtt_rows = store.query_daily_rollup("rtt_ms", host="host1")
    loss_rows = store.query_daily_rollup("loss_pct", host="host1")
    assert len(rtt_rows) == 1
    assert len(loss_rows) == 1
    assert rtt_rows[0].metric == "rtt_ms"
    assert loss_rows[0].metric == "loss_pct"


def test_query_daily_rollup_without_host_returns_all_hosts(store):
    store.record_daily_rollup("2026-01-01", "rtt_ms", "host1", 1.0, 5.0, 10.0, 3)
    store.record_daily_rollup("2026-01-01", "rtt_ms", "host2", 2.0, 6.0, 11.0, 3)
    rows = store.query_daily_rollup("rtt_ms")
    assert len(rows) == 2


def test_query_daily_rollup_empty_returns_empty_list(store):
    assert store.query_daily_rollup("rtt_ms") == []


def test_rollup_rtt_samples_aggregates_by_day_and_host(store):
    old_ts = int(time.time()) - 40 * 86400
    store.record_rtt("host1", 10.0, ts=old_ts)
    store.record_rtt("host1", 20.0, ts=old_ts + 60)
    cutoff = int(time.time()) - 30 * 86400
    n = store.rollup_rtt_samples_before(cutoff)
    assert n >= 1
    rows = store.query_daily_rollup("rtt_ms", host="host1")
    assert len(rows) == 1
    assert rows[0].n == 2
    assert rows[0].avg == 15.0


def test_query_rollup_hosts_returns_hosts_with_no_recent_raw_data(store):
    """A host whose rtt_sample rows have all aged past the 30-day raw
    retention window must still be discoverable from daily_rollup — history
    page host discovery must not depend on query_all_rtt_hosts() alone."""
    store.record_daily_rollup("2026-01-01", "rtt_ms", "host1", 1.0, 5.0, 10.0, 3)
    assert store.query_rollup_hosts("rtt_ms") == ["host1"]


def test_query_rollup_hosts_empty_when_no_rollups(store):
    assert store.query_rollup_hosts("rtt_ms") == []


def test_rollup_rtt_samples_ignores_unreachable_sentinel(store):
    """rtt_ms == -1.0 means unreachable — must not pollute the min/avg/max."""
    old_ts = int(time.time()) - 40 * 86400
    store.record_rtt("host1", 10.0, ts=old_ts)
    store.record_rtt("host1", -1.0, ts=old_ts + 60)
    cutoff = int(time.time()) - 30 * 86400
    store.rollup_rtt_samples_before(cutoff)
    rows = store.query_daily_rollup("rtt_ms", host="host1")
    assert len(rows) == 1
    assert rows[0].n == 1
    assert rows[0].avg == 10.0
