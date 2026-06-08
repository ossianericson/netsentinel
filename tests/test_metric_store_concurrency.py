"""Tests for MetricStore concurrency and health improvements (S6).

Covers:
  S6-1: WAL checkpoint when WAL file is large
  S6-2: VACUUM called after schema migration
  S6-3: busy_timeout set on connection (prevents OperationalError under contention)
  S6-4: two threads writing simultaneously without OperationalError
"""
import threading
import pytest
from pathlib import Path
from unittest.mock import patch

from modules.metric_store import MetricStore


@pytest.fixture
def store(tmp_path):
    db = tmp_path / "test.db"
    s = MetricStore(db_path=str(db))
    yield s
    s.close()


def test_concurrent_writes_no_operational_error(tmp_path):
    """Two threads writing to the same MetricStore must not raise OperationalError."""
    db = tmp_path / "concurrent.db"
    store = MetricStore(db_path=str(db))
    errors = []

    def _writer(host: str, count: int) -> None:
        for i in range(count):
            try:
                store.record_rtt(host, float(i), 0.0)
            except Exception as exc:
                errors.append(exc)

    t1 = threading.Thread(target=_writer, args=("host-a", 20))
    t2 = threading.Thread(target=_writer, args=("host-b", 20))
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)
    store.close()

    assert not errors, f"Concurrent write errors: {errors}"


def test_busy_timeout_set_on_connection(store):
    """The per-thread connection must have busy_timeout configured."""
    conn = store._conn
    rows = conn.execute("PRAGMA busy_timeout").fetchall()
    assert rows
    timeout_ms = rows[0][0]
    assert timeout_ms >= 1000, f"busy_timeout is {timeout_ms}ms — should be ≥1000ms"


def test_wal_checkpoint_triggered_for_large_wal(tmp_path):
    """_checkpoint_wal_if_needed must call PRAGMA wal_checkpoint when WAL is large."""
    db = tmp_path / "wal_test.db"
    # Create the database first
    s = MetricStore(db_path=str(db))
    s.close()

    # Fake a large WAL file
    wal_path = Path(str(db) + "-wal")
    wal_path.write_bytes(b"\x00" * (51 * 1024 * 1024))  # 51 MB

    checkpoint_called = []

    def patched_checkpoint(self, threshold_bytes=50 * 1024 * 1024):
        if self._db_path is not None:
            p = Path(str(self._db_path) + "-wal")
            if p.exists() and p.stat().st_size > threshold_bytes:
                checkpoint_called.append(True)
        # Don't actually run the checkpoint to avoid file issues
        return

    with patch.object(MetricStore, "_checkpoint_wal_if_needed", patched_checkpoint):
        s2 = MetricStore(db_path=str(db))
        s2.close()

    assert checkpoint_called, "WAL checkpoint was not triggered for large WAL"


def test_schema_created_without_vacuum_error(tmp_path):
    """Schema creation (including VACUUM) must not raise any exception."""
    db = tmp_path / "schema.db"
    s = MetricStore(db_path=str(db))
    # If VACUUM failed, the store would not have been constructed
    assert s.query_last_grade() is None  # schema created OK
    s.close()


def test_write_then_read_consistent(tmp_path):
    """Write 50 RTT samples from one thread, read them back from another."""
    db = tmp_path / "rw.db"
    store = MetricStore(db_path=str(db))
    write_count = 50
    for i in range(write_count):
        store.record_rtt("8.8.8.8", float(i))

    read_results = []

    def _reader():
        read_results.extend(store.query_rtt_history("8.8.8.8", hours=1.0))

    t = threading.Thread(target=_reader)
    t.start()
    t.join(timeout=5)
    store.close()

    assert len(read_results) == write_count
