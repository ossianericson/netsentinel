"""
health_score.py — Lightweight ambient network health score.

Computes a composite health score (0-100) from already-collected monitor data
stored in MetricStore.  No new network traffic is generated.

State thresholds:
  green   — score >= 75  (all good)
  amber   — score >= 45  (some issues)
  red     — score <  45  (active problems)
  unknown — no monitoring data available yet
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class HealthSnapshot:
    """Immutable snapshot of network health at a point in time."""

    score: int                              # 0-100
    state: str                              # "green" | "amber" | "red" | "unknown"
    headline: str                           # one-sentence plain-English status
    sub_text: str                           # secondary detail line
    checked_at: datetime = field(default_factory=datetime.now)
    stable_hours: float = 0.0              # hours since the last detected issue


class HealthScoreCalculator:
    """
    Derives a network health score from MetricStore without any new I/O.

    Called by HealthWorker every 60 seconds.  Safe to call from any thread
    because all underlying MetricStore queries are thread-safe (WAL mode).
    """

    _GREEN = 75
    _AMBER = 45

    def compute(self, store) -> HealthSnapshot:
        """Return a HealthSnapshot by querying MetricStore."""
        if store is None:
            return self._unknown_snapshot()

        try:
            avail_score   = self._availability_score(store)
            latency_score = self._latency_score(store)
            alert_score   = self._alert_score(store)
        except Exception:
            return self._unknown_snapshot()  # non-fatal — store may be empty

        if avail_score is None and latency_score is None and alert_score is None:
            return self._unknown_snapshot()

        # Fill defaults for missing data sources so we can still produce a score
        a  = avail_score   if avail_score   is not None else 80.0
        l  = latency_score if latency_score is not None else 80.0
        al = alert_score   if alert_score   is not None else 100.0

        # Weighted composite: availability most important, then alerts, then latency
        score = int(a * 0.45 + al * 0.35 + l * 0.20)
        score = max(0, min(100, score))

        state = self._score_to_state(score)
        stable = self._stable_hours(store)
        headline, sub_text = self._generate_copy(
            state, store, avail_score, alert_score, stable
        )

        return HealthSnapshot(
            score=score,
            state=state,
            headline=headline,
            sub_text=sub_text,
            stable_hours=stable,
        )

    # ── Score components ──────────────────────────────────────────────────────

    def _availability_score(self, store) -> Optional[float]:
        """Average 24-hour uptime % across monitored hosts (0-100 scale)."""
        try:
            table = store.query_uptime_table(hours_list=[24.0])
        except Exception:
            return None
        if not table:
            return None
        uptimes = [
            row.get("24h", 100.0)
            for row in table
            if row.get("24h") is not None
        ]
        if not uptimes:
            return None
        return sum(uptimes) / len(uptimes)

    def _latency_score(self, store) -> Optional[float]:
        """Score based on average RTT vs expected thresholds (last 1 hour)."""
        try:
            hosts = store.query_all_rtt_hosts(hours=1.0)
        except Exception:
            return None
        if not hosts:
            return None

        scores: list[float] = []
        for host in hosts[:5]:  # cap to keep queries fast
            try:
                points = store.query_rtt_history(host, hours=1.0)
            except Exception:
                continue
            if not points:
                continue
            avg_ms = sum(p.rtt_ms for p in points) / len(points)
            # <50 ms = 100, 50-150 ms = 100->80, 150-300 ms = 80->40, >300 ms = 40->0
            if avg_ms < 50:
                s = 100.0
            elif avg_ms < 150:
                s = 100.0 - (avg_ms - 50.0) / 100.0 * 20.0
            elif avg_ms < 300:
                s = 80.0 - (avg_ms - 150.0) / 150.0 * 40.0
            else:
                s = max(0.0, 40.0 - (avg_ms - 300.0) / 300.0 * 40.0)
            scores.append(s)

        if not scores:
            return None
        return sum(scores) / len(scores)

    def _alert_score(self, store) -> Optional[float]:
        """Score penalised by recent unacknowledged alerts (last 24 h)."""
        try:
            alerts = store.get_recent_alerts(hours=24.0, limit=50)
        except Exception:
            return None
        n = len(alerts)
        if n == 0:
            return 100.0
        # Each alert costs 15 points; floor at 0
        return max(0.0, 100.0 - n * 15.0)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _score_to_state(self, score: int) -> str:
        if score >= self._GREEN:
            return "green"
        if score >= self._AMBER:
            return "amber"
        return "red"

    def _stable_hours(self, store) -> float:
        """Hours elapsed since the most recent alert."""
        try:
            alerts = store.get_recent_alerts(hours=168.0, limit=1)
            if not alerts:
                return 168.0
            last_ts = alerts[0].get("ts") or alerts[0].get("timestamp") or 0
            if last_ts:
                return max(0.0, (time.time() - float(last_ts)) / 3600.0)
        except Exception:
            pass  # non-fatal
        return 0.0

    def _generate_copy(
        self,
        state: str,
        store,
        avail_score: Optional[float],
        alert_score: Optional[float],
        stable: float,
    ) -> tuple[str, str]:
        if state == "green":
            if stable >= 72:
                days = int(stable / 24)
                headline = (
                    f"Everything looks good — your network has been healthy "
                    f"for {days} day{'s' if days != 1 else ''}"
                )
            elif stable >= 2:
                hrs = int(stable)
                headline = (
                    f"Your network has been stable for "
                    f"{hrs} hour{'s' if hrs != 1 else ''}"
                )
            else:
                headline = "All clear — no issues detected right now"
            sub = "All monitored devices and services are responding normally."

        elif state == "amber":
            try:
                n = len(store.get_recent_alerts(hours=24.0, limit=50))
            except Exception:
                n = 0
            if n > 0:
                headline = (
                    f"{n} alert{'s' if n != 1 else ''} in the last 24 hours"
                    " — worth checking"
                )
                sub = "Some issues were flagged. Open alerts to review what needs attention."
            else:
                headline = "Network performance is slightly degraded"
                sub = "Connectivity is OK but response times are higher than usual."

        else:  # red
            if avail_score is not None and avail_score < 70:
                headline = (
                    "Connectivity problems detected — some devices are unreachable"
                )
                sub = "One or more monitored hosts are not responding. Check your connection."
            else:
                headline = "Multiple alerts need attention right now"
                sub = "Open the alerts panel to see what needs to be fixed."

        return headline, sub

    def _unknown_snapshot(self) -> HealthSnapshot:
        return HealthSnapshot(
            score=0,
            state="unknown",
            headline="Monitoring data not available yet",
            sub_text=(
                "Start the Network Logger or run a scan to begin collecting data."
            ),
        )
