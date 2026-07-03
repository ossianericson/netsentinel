"""
metric_store_lifecycle.py — _LifecycleMixin: WAL checkpoint/growth-guard and
startup corruption recovery for MetricStore.

Extracted from modules/metric_store.py (Stability Sprint 1 split, RULE-AH1)
to keep that file within its LOC budget after G7/G8 additions.
MetricStore mixes this in alongside MetricStoreQueryMixin/_DeviceWritesMixin;
all methods here assume self._backend, self._db_path, self._local, self._conn
(the connection property defined on MetricStore itself).
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path


class _LifecycleMixin:
    """WAL checkpoint and corruption-recovery behavior for MetricStore."""

    # ── S6-1: WAL growth guard ────────────────────────────────────────────────

    def _checkpoint_wal_if_needed(self, threshold_bytes: int = 50 * 1024 * 1024) -> None:
        """Run PRAGMA wal_checkpoint(TRUNCATE) if the WAL file exceeds 50 MB."""
        if self._db_path is None:
            return
        wal_path = self._db_path.with_suffix(".db-wal")
        if not wal_path.exists():
            wal_path = Path(str(self._db_path) + "-wal")
        try:
            if wal_path.exists() and wal_path.stat().st_size > threshold_bytes:
                conn = sqlite3.connect(str(self._db_path), check_same_thread=False, timeout=10)
                conn.execute("PRAGMA busy_timeout = 5000")
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                conn.close()
        except Exception:
            pass  # non-fatal

    def checkpoint(self) -> None:
        """G7: force a WAL checkpoint so all pending writes are flushed to the
        main DB file. Call before process exit — dashboard.py's shutdown path
        uses os._exit(0) (a documented QThread-destructor workaround) which
        bypasses Python's normal connection-close/atexit path entirely, so the
        WAL would otherwise never be truncated. wal_checkpoint is a whole-
        database operation, so any open connection can perform it — it is not
        limited to flushing only the calling thread's own writes."""
        if self._backend != "sqlite" or self._db_path is None or str(self._db_path) == ":memory:":
            return
        try:
            self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except Exception:
            pass  # non-fatal — best-effort flush before hard exit

    def vacuum_if_needed(self, rows_deleted: int, threshold: int = 500) -> bool:
        """Run a real VACUUM only when enough rows were just deleted to make
        rewriting the whole file worthwhile (VACUUM is O(db size), not O(rows
        deleted)). Returns True if VACUUM ran. sqlite backend only — the
        previous `PRAGMA VACUUM` call (invalid SQL) was a silent no-op (G2)."""
        if self._backend != "sqlite" or rows_deleted < threshold:
            return False
        try:
            self._conn.execute("VACUUM")
        except Exception:
            import logging
            logging.getLogger(__name__).warning("VACUUM failed", exc_info=True)
            return False
        return True

    # ── G8: startup corruption recovery ───────────────────────────────────────

    def _recover_from_corruption(self, exc: sqlite3.DatabaseError) -> None:
        """G8: the on-disk file failed to open as a valid SQLite database
        (e.g. truncated by a crash, disk corruption). Rather than crashing
        the whole app on startup, back up the bad file and start fresh —
        losing history is far better than the app never launching again."""
        import logging
        logging.getLogger(__name__).error(
            "MetricStore: %s is not a valid database (%s) — "
            "backing it up and starting a fresh database.",
            self._db_path, exc,
        )
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass  # connection is already broken; nothing to clean up
            self._local.conn = None

        original_path = self._db_path
        # Any WAL/SHM sidecars belong to the corrupt file and are useless once
        # it's moved aside — drop them so a stale one can't reattach to the
        # fresh database created at the same path.
        for suffix in ("-wal", "-shm"):
            sidecar = Path(str(original_path) + suffix)
            try:
                sidecar.unlink(missing_ok=True)
            except OSError:
                pass  # non-fatal — stale sidecar left behind

        backup_path = original_path.with_name(f"{original_path.name}.corrupt-{int(time.time())}")
        try:
            original_path.rename(backup_path)
            self.corruption_backup_path = backup_path
        except OSError:
            # Couldn't even rename (permissions, file lock) — fall back to a
            # sibling path so the app can still start rather than crashing.
            self._db_path = original_path.with_name(f"{original_path.stem}.recovered.db")

        self.recovered_from_corruption = True
        self._init_schema()  # retry against the now-fresh path
