"""
Tests for modules/metric_store_writes_batch.py (_BatchWritesMixin) -- Phase B1.

Written test-first (RULE-TDD1): these must fail (module/mixin does not exist yet)
before any implementation code is written. Covers the two new public batch
methods (record_app_traffic_samples, record_availability_cycle) added to cut the
per-row-commit write paths flagged by the July 2026 data-wiring audit (F2, F5).

record_availability_cycle spans TWO tables (rtt_sample + device_state) in a
single transaction -- the crash-mid-batch tests below prove real cross-table
atomicity: a bad row in state_rows rolls back the already-applied rtt_rows from
the same cycle too, so the two tables can never end up out of sync for one call.
"""
import sqlite3

import pytest

from modules.metric_store import MetricStore


@pytest.fixture()
def store(tmp_path):
    s = MetricStore(db_path=tmp_path / "batch.db")
    yield s
    s.close()


def _count_commits(conn: sqlite3.Connection, fn) -> int:
    """Run fn() and return how many real SQLite COMMITs it issued.

    sqlite3.Connection.commit is a read-only C slot (can't be patched with
    unittest.mock), so trace the actual statements sent to SQLite instead --
    set_trace_callback observes the literal "COMMIT" python's sqlite3 module
    sends on conn.commit(), which is what "one transaction" really means here.
    """
    events = []
    conn.set_trace_callback(lambda sql: events.append(sql))
    try:
        fn()
    finally:
        conn.set_trace_callback(None)
    return sum(1 for e in events if e.strip().upper() == "COMMIT")


def _traffic_sample(i, mac="aa:bb:cc:dd:ee:01"):
    return {
        "mac": mac, "label": f"dev-{i}", "category": "Streaming", "app": "",
        "bytes_total": 1000 + i, "window_s": 10.0, "cdn": None,
    }


def _rtt_row(host, rtt_ms=12.5, ts=1_700_000_000):
    return {"host": host, "rtt_ms": rtt_ms, "loss_pct": 0.0, "jitter_ms": -1.0, "ts": ts}


def _state_row(ip, state="UP", mac=None, hostname=None, rtt_ms=12.5, ts=1_700_000_000):
    return {"ip": ip, "mac": mac, "hostname": hostname, "state": state, "rtt_ms": rtt_ms, "ts": ts}


# ── record_app_traffic_samples ────────────────────────────────────────────────

class TestRecordAppTrafficSamples:
    def test_zero_rows_is_noop(self, store):
        store.record_app_traffic_samples([])
        rows = store._execute_read("SELECT * FROM app_traffic_sample")
        assert len(rows) == 0

    def test_one_row(self, store):
        store.record_app_traffic_samples([_traffic_sample(0)])
        rows = store._execute_read(
            "SELECT mac, label, category, bytes_total FROM app_traffic_sample"
        )
        assert len(rows) == 1
        assert rows[0]["mac"] == "aa:bb:cc:dd:ee:01"
        assert rows[0]["bytes_total"] == 1000

    def test_n_rows_equivalent_to_n_single_calls(self, tmp_path):
        samples = [_traffic_sample(i) for i in range(12)]

        batched = MetricStore(db_path=tmp_path / "batched.db")
        single = MetricStore(db_path=tmp_path / "single.db")
        try:
            batched.record_app_traffic_samples(samples)
            for s in samples:
                single.record_app_traffic_sample(**s)

            cols = "mac, label, category, app, cdn, bytes_total, window_s"
            got = sorted(
                tuple(r) for r in
                batched._execute_read(f"SELECT {cols} FROM app_traffic_sample")
            )
            want = sorted(
                tuple(r) for r in
                single._execute_read(f"SELECT {cols} FROM app_traffic_sample")
            )
            assert got == want
            assert len(got) == 12
        finally:
            batched.close()
            single.close()

    def test_one_commit_regardless_of_row_count(self, store):
        samples = [_traffic_sample(i) for i in range(9)]
        n = _count_commits(store._conn, lambda: store.record_app_traffic_samples(samples))
        assert n == 1

    def test_crash_mid_batch_rolls_back_and_store_stays_usable(self, store):
        # app_traffic_sample.mac is NOT NULL -- a None mid-batch trips an
        # IntegrityError inside executemany, after row 0 already applied.
        bad = [_traffic_sample(0), {**_traffic_sample(1), "mac": None}, _traffic_sample(2)]
        with pytest.raises(sqlite3.IntegrityError):
            store.record_app_traffic_samples(bad)

        rows = store._execute_read("SELECT * FROM app_traffic_sample")
        assert len(rows) == 0  # all-or-nothing: row 0 must not have survived

        # connection must not be left wedged mid-transaction
        store.record_app_traffic_sample(**_traffic_sample(9))
        rows = store._execute_read("SELECT * FROM app_traffic_sample")
        assert len(rows) == 1


# ── record_availability_cycle ─────────────────────────────────────────────────

class TestRecordAvailabilityCycle:
    def test_zero_rows_is_noop(self, store):
        store.record_availability_cycle([], [])
        assert store._execute_read("SELECT * FROM rtt_sample") == []
        assert store._execute_read("SELECT * FROM device_state") == []

    def test_one_row_each_table(self, store):
        store.record_availability_cycle(
            [_rtt_row("192.168.1.1")], [_state_row("192.168.1.1", mac="aa:bb:cc:00:00:01")]
        )
        rtt = store._execute_read("SELECT host, rtt_ms FROM rtt_sample")
        state = store._execute_read("SELECT ip, mac, state FROM device_state")
        assert len(rtt) == 1 and rtt[0]["host"] == "192.168.1.1"
        assert len(state) == 1 and state[0]["state"] == "UP"

    def test_rtt_rows_without_matching_state_rows(self, store):
        # asymmetric batch: e.g. a cycle where every target got an rtt_sample
        # but no state actually changed shape (targets list mismatch is not
        # possible in practice, but the API must tolerate uneven lists).
        store.record_availability_cycle([_rtt_row("10.0.0.1"), _rtt_row("10.0.0.2")], [])
        assert len(store._execute_read("SELECT * FROM rtt_sample")) == 2
        assert store._execute_read("SELECT * FROM device_state") == []

    def test_n_rows_equivalent_to_n_single_calls(self, tmp_path):
        rtt_rows = [_rtt_row(f"10.0.0.{i}", rtt_ms=10.0 + i) for i in range(5)]
        state_rows = [
            _state_row(f"10.0.0.{i}", mac=f"aa:bb:cc:00:00:{i:02x}", rtt_ms=10.0 + i)
            for i in range(5)
        ]

        batched = MetricStore(db_path=tmp_path / "batched.db")
        single = MetricStore(db_path=tmp_path / "single.db")
        try:
            batched.record_availability_cycle(rtt_rows, state_rows)
            for r in rtt_rows:
                single.record_rtt(r["host"], r["rtt_ms"], r["loss_pct"], r["jitter_ms"], ts=r["ts"])
            for s in state_rows:
                single.record_device_state(
                    ip=s["ip"], mac=s["mac"], hostname=s["hostname"],
                    state=s["state"], rtt_ms=s["rtt_ms"], ts=s["ts"],
                )

            rtt_cols = "ts, host, rtt_ms, loss_pct, jitter_ms"
            state_cols = "ts, ip, mac, hostname, state, rtt_ms"
            assert sorted(tuple(r) for r in batched._execute_read(f"SELECT {rtt_cols} FROM rtt_sample")) == \
                sorted(tuple(r) for r in single._execute_read(f"SELECT {rtt_cols} FROM rtt_sample"))
            assert sorted(tuple(r) for r in batched._execute_read(f"SELECT {state_cols} FROM device_state")) == \
                sorted(tuple(r) for r in single._execute_read(f"SELECT {state_cols} FROM device_state"))
        finally:
            batched.close()
            single.close()

    def test_one_commit_for_both_tables_combined(self, store):
        rtt_rows = [_rtt_row(f"10.0.0.{i}") for i in range(5)]
        state_rows = [_state_row(f"10.0.0.{i}") for i in range(5)]
        n = _count_commits(
            store._conn, lambda: store.record_availability_cycle(rtt_rows, state_rows)
        )
        assert n == 1  # ONE transaction covers both tables, not two

    def test_crash_in_state_rows_rolls_back_already_applied_rtt_rows(self, store):
        # device_state.ip is NOT NULL -- None trips a SQLite IntegrityError
        # while writing state_rows (unlike `state`, `ip` has no Python-side
        # transform, so the bad value survives to reach SQL), which must roll
        # back the rtt_rows batch already executemany'd earlier in the SAME
        # transaction.
        rtt_rows = [_rtt_row("10.0.0.1"), _rtt_row("10.0.0.2")]
        state_rows = [_state_row("10.0.0.1"), {**_state_row("10.0.0.2"), "ip": None}]

        with pytest.raises(sqlite3.IntegrityError):
            store.record_availability_cycle(rtt_rows, state_rows)

        # cross-table atomicity: rtt_sample must NOT have the rows either
        assert store._execute_read("SELECT * FROM rtt_sample") == []
        assert store._execute_read("SELECT * FROM device_state") == []

        # store must still be usable afterward
        store.record_availability_cycle([_rtt_row("10.0.0.3")], [_state_row("10.0.0.3")])
        assert len(store._execute_read("SELECT * FROM rtt_sample")) == 1
        assert len(store._execute_read("SELECT * FROM device_state")) == 1
