"""
Phase B0 baseline / Phase B1 write-batching — MetricStore write profile.

benchmark-marked (skipped in the default suite; run with `pytest -m benchmark`).
This is not a pass/fail gate — it captures the commit-count numbers the July
2026 data-wiring audit is measured against. It asserts only that the profiler
is still wired up (each path records writes and the primitive patch/unpatch is
clean) plus the specific commit-count contract each phase promises, so a
silently-broken profiler or a regressed batch call fails loudly instead of
reporting a stale number.

Reference numbers on 2026-07-17 (python 3.11, one machine) — re-run both sides
with this test, never compare against a number pasted from another machine:
    path                                pre-B1      post-B1
    (a) scan cycle, 25 devices          125 commits 125 commits (no-txn invariant, untouched)
    (b) availability, 5 targets x 10    102 commits  12 commits (10 cycles x 1 batched
                                                                  rtt+state commit, +2 for
                                                                  the stubbed DOWN/recover
                                                                  device_event flip)
    (c) app traffic, 25 flows            25 commits   1 commit  (one record_app_traffic_samples()
                                                                  call replaces the per-sample loop)
"""
import pytest

from modules.metric_store import MetricStore
from tools.write_profile import (
    profile_app_traffic,
    profile_availability,
    profile_scan_cycle,
)


@pytest.mark.benchmark
def test_scan_cycle_baseline(tmp_path, capsys):
    store = MetricStore(db_path=tmp_path / "scan.db")
    try:
        prof = profile_scan_cycle(store, n_devices=25)
    finally:
        store.close()
    prof.report("(a) scan cycle - 25 devices")
    rows, commits, _ = prof.totals()
    # 25 devices, all new: known_device insert+update, ip_history, device_event
    # (JOINED) and device_events (audit) each fire per device.
    # Untouched by B1: process_scan is intentionally NOT wrapped in a
    # transaction (metric_store.py docstring) -- still one commit per row.
    assert commits > 0
    assert rows >= 25
    assert ("INSERT", "known_device") in prof.stats
    assert commits == 125


@pytest.mark.benchmark
def test_availability_baseline(tmp_path, capsys):
    store = MetricStore(db_path=tmp_path / "avail.db")
    try:
        prof = profile_availability(store, n_targets=5, rounds=10)
    finally:
        store.close()
    prof.report("(b) availability - 5 targets x 10 cycles")
    rows, commits, _ = prof.totals()
    # F5, post-B1: run_cycle() batches all 5 targets' rtt_sample + device_state
    # rows into ONE record_availability_cycle() transaction per cycle -- 10
    # cycles = 10 commits, plus 2 device_event commits for the stubbed
    # DOWN/recover flip on host 0 (record_device_event stays per-transition).
    assert rows == 102
    assert commits == 12
    assert prof.stats[("INSERT", "rtt_sample")][0] == 50    # rows
    assert prof.stats[("INSERT", "rtt_sample")][1] == 10    # 1 commit/cycle x 10 cycles
    assert prof.stats[("INSERT", "device_state")][0] == 50  # rows
    assert prof.stats[("INSERT", "device_state")][1] == 0   # commit credited to rtt_sample's bucket
    assert prof.stats[("INSERT", "device_event")][1] == 2


@pytest.mark.benchmark
def test_app_traffic_baseline(tmp_path, capsys):
    store = MetricStore(db_path=tmp_path / "traffic.db")
    try:
        prof = profile_app_traffic(store, n_flows=25)
    finally:
        store.close()
    prof.report("(c) app traffic snapshot - 25 flows")
    rows, commits, _ = prof.totals()
    # F2, post-B1: one record_app_traffic_samples() call replaces the
    # per-sample loop -- 25 rows, 1 commit (was 1 commit per flow).
    assert rows == 25
    assert commits == 1
    assert prof.stats[("INSERT", "app_traffic_sample")][0] == 25
    assert prof.stats[("INSERT", "app_traffic_sample")][1] == 1


@pytest.mark.benchmark
def test_profiler_restores_primitives(tmp_path):
    """The patch must be fully reverted after each scenario — a leaked wrapper
    would corrupt every later test's MetricStore. Verify the primitive is the
    original bound function again once profiling ends."""
    before = MetricStore._execute_write
    store = MetricStore(db_path=tmp_path / "restore.db")
    try:
        profile_app_traffic(store, n_flows=3)
    finally:
        store.close()
    assert MetricStore._execute_write is before
