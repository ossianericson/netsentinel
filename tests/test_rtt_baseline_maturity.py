"""RTT_ANOMALY's maturity gate was unreachable by construction.

`BaselineLearner._refresh_host_baselines()` queried exactly
`_BASELINE_DAYS * 24` hours of history, then computed

    days_covered = (now - oldest_ts) / 86400

where `oldest_ts` is the oldest row *inside that same window*. So
`days_covered` could never reach `_BASELINE_DAYS`, while `Baseline.is_mature`
requires `days_covered >= _BASELINE_DAYS` — the gate was a tautology against
itself. Measured on the live database: 6.9876 days on the richest host and
0 of 3 hosts mature, against 29.86 days of real history for that host.

The window and the maturity threshold answer two different questions:
  • how much history should the mean/sigma be computed from? (recency — 7 days)
  • how long have we been watching this host?      (confidence — all of it)

Conflating them is what made the rule dead. The fix separates them: the
statistics still come from the 7-day window, `days_covered` comes from the
host's first-ever sample.
"""
from __future__ import annotations

import time

import pytest

from modules.alert_baseline import BaselineLearner, _BASELINE_DAYS, _MIN_SAMPLES


@pytest.fixture()
def store(tmp_path):
    from modules.metric_store import MetricStore
    s = MetricStore(db_path=tmp_path / "test.db")
    yield s
    s.close()


def _seed(store, host: str, *, days: int, per_day: int = 12, rtt: float = 20.0):
    """Write `per_day` samples a day for `days` days, ending now."""
    now = int(time.time())
    rows = []
    for d in range(days):
        for i in range(per_day):
            ts = now - d * 86400 - i * 3600
            rows.append({"host": host, "rtt_ms": rtt, "loss_pct": 0.0, "ts": ts})
    store.record_availability_cycle(rows, [])


def test_first_seen_per_host_spans_the_whole_history(store):
    """The MetricStore primitive the fix needs — one grouped scan, not N queries."""
    _seed(store, "10.0.0.1", days=20)
    _seed(store, "10.0.0.2", days=2)
    first = store.query_rtt_first_seen_by_host()
    now = time.time()
    assert (now - first["10.0.0.1"]) / 86400 > 18
    assert (now - first["10.0.0.2"]) / 86400 < 3


def test_a_host_with_a_month_of_history_is_mature(store):
    """The case that measured 6.9876 days on the live DB against 29.86 real."""
    _seed(store, "192.168.68.1", days=30)
    learner = BaselineLearner()
    learner.refresh(store)
    bl = learner.get_host_baseline("192.168.68.1")
    assert bl is not None and bl.rtt_ms is not None
    assert bl.rtt_ms.sample_count >= _MIN_SAMPLES
    assert bl.rtt_ms.days_covered >= _BASELINE_DAYS, (
        f"days_covered={bl.rtt_ms.days_covered:.4f} — the maturity gate is "
        f"still measuring the query window, not the history"
    )
    assert bl.is_mature is True
    assert learner.is_mature() is True


def test_a_young_host_is_still_not_mature(store):
    """The gate must keep gating — this is the case it exists for."""
    _seed(store, "192.168.68.99", days=3)
    learner = BaselineLearner()
    learner.refresh(store)
    bl = learner.get_host_baseline("192.168.68.99")
    assert bl is not None
    assert bl.rtt_ms is None or bl.rtt_ms.days_covered < _BASELINE_DAYS
    assert bl.is_mature is False


def test_statistics_still_come_from_the_recent_window_only(store):
    """Widening the maturity lookback must NOT widen what the mean learns from.

    A host that was slow a month ago and is fast now must not carry the old
    mean forward — that would raise its threshold and desensitise the rule,
    which is the opposite of the program's intent.
    """
    now = int(time.time())
    rows = []
    # Ancient, very slow samples — well outside the 7-day statistics window.
    for i in range(200):
        rows.append({"host": "h", "rtt_ms": 900.0, "loss_pct": 0.0,
                     "ts": now - 25 * 86400 - i * 60})
    # Recent, fast samples.
    for i in range(200):
        rows.append({"host": "h", "rtt_ms": 10.0, "loss_pct": 0.0,
                     "ts": now - i * 600})
    store.record_availability_cycle(rows, [])

    learner = BaselineLearner()
    learner.refresh(store)
    bl = learner.get_host_baseline("h")
    assert bl is not None and bl.rtt_ms is not None
    assert bl.rtt_ms.mean < 50.0, (
        f"mean={bl.rtt_ms.mean:.1f} — 25-day-old samples leaked into the "
        f"statistics window"
    )
    # ...while maturity still sees the full span.
    assert bl.rtt_ms.days_covered >= _BASELINE_DAYS
    assert bl.is_mature is True


def test_no_history_leaves_no_baseline(store):
    learner = BaselineLearner()
    learner.refresh(store)
    assert learner.get_host_baseline("nobody") is None
    assert learner.is_mature() is False
