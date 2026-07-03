"""
Daily rollup mixin for MetricStore (Stability Sprint 2 / G4).

daily_rollup stores per-day min/avg/max/n aggregates that survive raw-row
pruning, so long-term trend charts have data beyond the 30-day rtt_sample
retention window. Population happens inside prune_old_data() — see
metric_store_queries.py — immediately before the raw rows it summarizes are
deleted, so nothing is ever lost between "still raw" and "rolled up".

Mixed into MetricStore; requires self._execute_write/_execute_write_counted/
_execute_read from the host class.
"""
from typing import List, Optional

from modules.metric_store_schema import RollupPoint


class _RollupMixin:
    """Daily rollup write/read methods. See module docstring."""

    def record_daily_rollup(
        self,
        day: str,
        metric: str,
        host: str,
        min_v: float,
        avg_v: float,
        max_v: float,
        n: int,
    ) -> None:
        """Insert or merge a daily rollup row. On conflict, merges the new
        partial aggregate into the existing one with a correctly weighted
        average — callers may roll up the same (day, metric, host) more than
        once (e.g. a day's raw rows aging past the retention cutoff in more
        than one prune pass)."""
        self._execute_write(
            "INSERT INTO daily_rollup (day, metric, host, min, avg, max, n) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(day, metric, host) DO UPDATE SET "
            "  min = MIN(daily_rollup.min, excluded.min), "
            "  max = MAX(daily_rollup.max, excluded.max), "
            "  avg = (daily_rollup.avg * daily_rollup.n + excluded.avg * excluded.n) "
            "        * 1.0 / (daily_rollup.n + excluded.n), "
            "  n   = daily_rollup.n + excluded.n",
            (day, metric, host, min_v, avg_v, max_v, n),
        )

    def query_daily_rollup(
        self, metric: str, host: Optional[str] = None,
    ) -> List[RollupPoint]:
        """Return daily rollup rows for `metric`, oldest first. Filters by
        `host` when given, otherwise returns all hosts."""
        if host:
            rows = self._execute_read(
                "SELECT day, metric, host, min, avg, max, n FROM daily_rollup "
                "WHERE metric = ? AND host = ? ORDER BY day ASC",
                (metric, host),
            )
        else:
            rows = self._execute_read(
                "SELECT day, metric, host, min, avg, max, n FROM daily_rollup "
                "WHERE metric = ? ORDER BY day ASC, host ASC",
                (metric,),
            )
        return [
            RollupPoint(
                day=r["day"], metric=r["metric"], host=r["host"],
                min=r["min"], avg=r["avg"], max=r["max"], n=r["n"],
            )
            for r in rows
        ]

    def query_rollup_hosts(self, metric: str) -> List[str]:
        """Return distinct hosts with a daily_rollup row for `metric`. Used
        for long-term-view host discovery — query_all_rtt_hosts() alone
        misses hosts whose raw rtt_sample rows have all aged past the 30-day
        retention window, even though their rollup history still exists."""
        rows = self._execute_read(
            "SELECT DISTINCT host FROM daily_rollup WHERE metric = ? ORDER BY host",
            (metric,),
        )
        return [r["host"] for r in rows]

    def rollup_rtt_samples_before(self, cutoff_ts: int) -> int:
        """Aggregate rtt_sample rows older than `cutoff_ts` into daily_rollup
        (one row per UTC day/host, per metric: rtt_ms, loss_pct, jitter_ms),
        then return the number of source rows aggregated. Does NOT delete the
        source rows — callers (prune_old_data()) delete them separately with
        the same cutoff immediately after. rtt_ms == -1.0 (unreachable
        sentinel) is excluded from the rtt_ms rollup."""
        total = 0
        for metric, extra_where in (
            ("rtt_ms", "AND rtt_ms >= 0"),
            ("loss_pct", ""),
            ("jitter_ms", "AND jitter_ms >= 0"),
        ):
            rows = self._execute_read(
                f"SELECT strftime('%Y-%m-%d', ts, 'unixepoch') AS day, host, "
                f"MIN({metric}) AS min_v, AVG({metric}) AS avg_v, "
                f"MAX({metric}) AS max_v, COUNT(*) AS n "
                f"FROM rtt_sample WHERE ts < ? {extra_where} "
                f"GROUP BY day, host",
                (cutoff_ts,),
            )
            for r in rows:
                self.record_daily_rollup(
                    r["day"], metric, r["host"],
                    r["min_v"], r["avg_v"], r["max_v"], r["n"],
                )
                total += r["n"]
        return total
