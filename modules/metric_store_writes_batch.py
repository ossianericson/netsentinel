"""
metric_store_writes_batch.py -- _BatchWritesMixin (Phase B1, data-wiring audit).

Every existing MetricStore write method opens its own transaction (F1: one
commit per _execute_write() call). Two production write paths call one of
those methods in a tight loop on every scan/monitor cycle:

  * ui/tabs.py::_on_app_traffic_sample -- one commit per (mac, category) flow,
    on the GUI thread, every ~10s (F2).
  * modules/availability_monitor.py::run_cycle -- 2 commits per target per
    60s cycle (F5).

The methods here batch each of those bursts into ONE transaction. They are
internal to the metric_store family (RULE: raw SQL / _execute_write* calls
never happen outside modules/metric_store*.py) -- callers use these public
methods instead, mirroring the existing single-row methods so call sites are
1-line swaps (record_rtt/record_device_state/record_app_traffic_sample).

Primitives
----------
_execute_write_many(sql, params_seq)
    One INSERT/UPDATE statement, many rows, one transaction. Used where a
    batch only ever touches one table.
_execute_writes_many(statements)
    Multiple (sql, params_seq) pairs, ALL in one transaction. Used by
    record_availability_cycle, which must write rtt_sample and device_state
    atomically -- a failure partway through state_rows rolls back the
    rtt_rows already applied in the same cycle, so the two tables can never
    end up out of sync for one call.

Both primitives are all-or-nothing: on the sqlite backend, an exception
during executemany() triggers an explicit rollback() (the connection's
implicit transaction would otherwise stay open, uncommitted, and pollute the
next unrelated write) before re-raising. On the sqlalchemy backend,
Engine.begin() already rolls back on exception.
"""
import time
from typing import Dict, List, Optional, Sequence, Tuple


class _BatchWritesMixin:
    """Batched multi-row write methods. Requires self._execute_write_many /
    self._execute_writes_many primitives defined in this same mixin, and
    self._conn / self._write_lock / self._backend from the host class."""

    # ── Primitives ────────────────────────────────────────────────────────────

    def _execute_write_many(self, sql: str, params_seq: Sequence[tuple]) -> None:
        """Execute one INSERT/UPDATE statement across many rows, one transaction."""
        if not params_seq:
            return
        if self._backend == "sqlalchemy":
            from sqlalchemy import text
            with self._write_lock:
                with self._sa_engine.begin() as conn:
                    conn.execute(text(sql), [dict(enumerate(p)) for p in params_seq])
        else:
            with self._write_lock:
                try:
                    self._conn.executemany(sql, params_seq)
                    self._conn.commit()
                except Exception:
                    self._conn.rollback()
                    raise

    def _execute_writes_many(self, statements: List[Tuple[str, Sequence[tuple]]]) -> None:
        """Execute multiple (sql, params_seq) batches inside a SINGLE transaction."""
        statements = [(sql, rows) for sql, rows in statements if rows]
        if not statements:
            return
        if self._backend == "sqlalchemy":
            from sqlalchemy import text
            with self._write_lock:
                with self._sa_engine.begin() as conn:
                    for sql, rows in statements:
                        conn.execute(text(sql), [dict(enumerate(p)) for p in rows])
        else:
            with self._write_lock:
                try:
                    for sql, rows in statements:
                        self._conn.executemany(sql, rows)
                    self._conn.commit()
                except Exception:
                    self._conn.rollback()
                    raise

    # ── Write: app traffic samples, batched (F2) ──────────────────────────────

    def record_app_traffic_samples(self, samples: List[Dict]) -> None:
        """Batch version of record_app_traffic_sample() -- one commit for the
        whole list instead of one commit per sample."""
        if not samples:
            return
        now = int(time.time())
        rows = [
            (
                s.get("ts") or now, s["mac"], s.get("label", ""), s["category"],
                s.get("app", ""), s.get("cdn"), s.get("bytes_total", 0),
                s.get("window_s", 10.0),
            )
            for s in samples
        ]
        self._execute_write_many(
            "INSERT INTO app_traffic_sample "
            "(ts, mac, label, category, app, cdn, bytes_total, window_s) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )

    # ── Write: alert acknowledgement, batched ─────────────────────────────────

    def acknowledge_alerts(
        self,
        alert_ids: Sequence[int],
        acked_by: str = "user",
        comment: str = "",
        ts: Optional[int] = None,
    ) -> None:
        """Batch version of acknowledge_alert() -- one transaction for a whole
        selection instead of one commit per id.

        Exists because the Alert History table collapses alerts by
        (rule_name, host) into "×N" rows: acknowledging one visible row has to
        clear every member of its group, or the group's remaining members
        reappear on the next refresh. Same reason the Home action card's
        "Acknowledge all" needs it -- that button can clear a backlog of
        hundreds in one click.

        An empty/None-only id list is a no-op, so callers can pass a selection
        straight through without a guard.
        """
        ids = [int(a) for a in alert_ids if a is not None]
        if not ids:
            return
        now = ts or int(time.time())
        self._execute_write_many(
            "UPDATE alert_fired SET acked_ts=?, acked_by=?, acked_comment=? WHERE id=?",
            [(now, acked_by or "user", comment or None, aid) for aid in ids],
        )

    def unacknowledge_alerts(self, alert_ids: Sequence[int]) -> None:
        """Undo acknowledge_alerts() -- put the alerts back in the unacked queue.

        Backs the Home action card's "Acknowledge all" undo toast: that button
        can clear a backlog of hundreds in one click, so the action has to be
        reversible. Clears acked_by/acked_comment too, so an undone ack leaves
        no partial ownership record behind.
        """
        ids = [int(a) for a in alert_ids if a is not None]
        if not ids:
            return
        self._execute_write_many(
            "UPDATE alert_fired SET acked_ts=NULL, acked_by=NULL, acked_comment=NULL "
            "WHERE id=?",
            [(aid,) for aid in ids],
        )

    # ── Write: availability cycle, batched (F5) ───────────────────────────────

    def record_availability_cycle(
        self, rtt_rows: List[Dict], state_rows: List[Dict]
    ) -> None:
        """Batch version of one cycle's record_rtt() + record_device_state()
        calls -- ONE transaction covers both tables, so a cycle's rtt/state
        writes are never partially applied relative to each other.

        rtt_rows:   [{"host", "rtt_ms", "loss_pct"=0.0, "jitter_ms"=-1.0, "ts"=None}, ...]
        state_rows: [{"ip", "mac"=None, "hostname"=None, "state", "rtt_ms"=None, "ts"=None}, ...]

        record_device_event() (state *transitions*) stays a separate,
        per-transition call -- it is rare and event ordering matters, so it is
        not part of this batch (see availability_monitor.py::run_cycle).
        """
        now = int(time.time())
        rtt_params = [
            (
                r.get("ts") or now, r["host"], r["rtt_ms"],
                r.get("loss_pct", 0.0), r.get("jitter_ms", -1.0),
            )
            for r in rtt_rows
        ]
        state_params = [
            (
                s.get("ts") or now, s["ip"], s.get("mac"), s.get("hostname"),
                s["state"].upper(), s.get("rtt_ms"),
            )
            for s in state_rows
        ]
        self._execute_writes_many([
            (
                "INSERT INTO rtt_sample(ts, host, rtt_ms, loss_pct, jitter_ms) "
                "VALUES(?, ?, ?, ?, ?)",
                rtt_params,
            ),
            (
                "INSERT INTO device_state(ts, ip, mac, hostname, state, rtt_ms) "
                "VALUES(?, ?, ?, ?, ?, ?)",
                state_params,
            ),
        ])
