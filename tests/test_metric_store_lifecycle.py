"""
Tests for modules/metric_store_lifecycle.py — _LifecycleMixin.

Full end-to-end coverage (corruption recovery against a real corrupt file,
WAL truncation against a real DB) lives in tests/test_metric_store.py, since
those behaviors are only meaningful through the composed MetricStore class.
This file adds focused unit coverage for the mixin's decision logic in
isolation, per RULE-T1 (every modules/*.py needs its own tests/test_<name>.py).
"""
from __future__ import annotations

from unittest.mock import MagicMock


def test_import():
    from modules.metric_store_lifecycle import _LifecycleMixin
    assert _LifecycleMixin is not None


def _make_stub(backend="sqlite"):
    from modules.metric_store_lifecycle import _LifecycleMixin

    class _Stub(_LifecycleMixin):
        def __init__(self):
            self._backend = backend
            self._db_path = MagicMock()
            self._db_path.__str__.return_value = "test.db"
            self._conn = MagicMock()

    return _Stub()


def test_vacuum_if_needed_runs_above_threshold():
    stub = _make_stub()
    assert stub.vacuum_if_needed(rows_deleted=1000, threshold=500) is True
    stub._conn.execute.assert_called_once_with("VACUUM")


def test_vacuum_if_needed_skips_below_threshold():
    stub = _make_stub()
    assert stub.vacuum_if_needed(rows_deleted=1, threshold=500) is False
    stub._conn.execute.assert_not_called()


def test_vacuum_if_needed_false_on_non_sqlite_backend():
    stub = _make_stub(backend="sqlalchemy")
    assert stub.vacuum_if_needed(rows_deleted=10000, threshold=500) is False


def test_vacuum_if_needed_returns_false_on_execute_error():
    stub = _make_stub()
    stub._conn.execute.side_effect = Exception("database is locked")
    assert stub.vacuum_if_needed(rows_deleted=1000, threshold=500) is False


def test_checkpoint_noop_on_non_sqlite_backend():
    stub = _make_stub(backend="sqlalchemy")
    stub.checkpoint()  # must not raise
    stub._conn.execute.assert_not_called()


def test_checkpoint_noop_when_db_path_is_none():
    stub = _make_stub()
    stub._db_path = None
    stub.checkpoint()  # must not raise
    stub._conn.execute.assert_not_called()


def test_checkpoint_runs_wal_checkpoint_pragma():
    stub = _make_stub()
    stub.checkpoint()
    stub._conn.execute.assert_called_once_with("PRAGMA wal_checkpoint(TRUNCATE)")


def test_checkpoint_swallows_execute_errors():
    stub = _make_stub()
    stub._conn.execute.side_effect = Exception("disk I/O error")
    stub.checkpoint()  # must not raise
