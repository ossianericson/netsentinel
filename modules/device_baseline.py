"""
device_baseline.py — what is normal *for this device*.

Phase 3 of the Signal Quality Program. Phase 0's defect 4: a fixed global
threshold applied to devices whose normal is different. `availability_monitor`
classifies anything slower than `DEFAULT_DEGRADED_THRESHOLD` (150 ms) as
DEGRADED, and the reference network's Chromecast averages **194.3 ms** — so it
sat permanently on the boundary and produced **306 state events in 25 days**,
the loudest device on the network. The top five churn sources were a
Chromecast, a laptop, a printer, a PS5 and a streaming stick: every one a
device that legitimately sleeps or varies. None of them were broken.

Two questions are answered here:

  * `degraded_threshold(host)` — how slow is *unusually* slow for this device?
    Replaces the global constant with `mean + 2σ` of the device's own history.
  * `is_expected_down(host, ts)` — is this device normally absent right now?
    An hour-of-week duty cycle: a streaming stick asleep at 03:00 on a Tuesday
    is expected; the same device unreachable at 14:00 is not.

Two invariants shape every default below, both from the program plan's stated
failure mode ("over-suppression is the failure mode to watch"):

  1. **The global default is a floor, never a ceiling.** Learning may only
     raise a device's threshold, never lower it. A fast host that starts
     answering in 40 ms instead of 4 ms must still trip the global rule.
  2. **Unknown is never "expected".** Every predicate returns `None` rather
     than `True` when it lacks evidence, so a fresh install — where no baseline
     exists for anything — stays as loud as it is today rather than silently
     swallowing every first outage.

Architecture rules observed:
  • Pure Python — no PyQt6, no ui/ imports (ARCH RULE 1).
  • MetricStore injected, never constructed (ARCH RULE 2); read-only, and only
    through the existing public `query_device_state_history()`.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence

# Consecutive failed observations before availability_monitor will classify a
# host as DOWN. One missed ping is a missed ping; a device is not offline until
# it has failed to answer twice running.
#
# Kept at 2, and deliberately not tunable per device: it is latency added ahead
# of *every* real outage alert, and it stacks with the alert engine's own edge
# gate. Acceptance criterion 5 gives the whole chain 3 minutes at the shipped
# 60 s interval — see evidence.DEFAULT_MIN_CONSECUTIVE, and the budget assertion
# in tests/test_alert_engine_edge_trigger.py.
DOWN_CONFIRMATION_CYCLES = 2

# Samples required before a learned threshold displaces the global default.
# Matches alert_baseline._MIN_SAMPLES — one convention for "enough data", not two.
MIN_BASELINE_SAMPLES = 30

# Standard deviations above a device's own mean that count as unusual.
_SIGMA = 2.0

# Minimum headroom above the mean, as a fraction of it. A device with near-zero
# RTT variance would otherwise get `mean + 2*0 == mean` — the threshold lands
# exactly on the boundary and reproduces the original defect with different
# arithmetic.
_MIN_HEADROOM_FRACTION = 0.20

# Observations required in an hour-of-week bucket before its duty cycle is
# trusted. One observation is not a pattern, and treating it as one would
# suppress a device's first-ever outage in that hour.
_MIN_BUCKET_SAMPLES = 3

# Fraction of a bucket's observations that must be DOWN for absence to count as
# this device's normal behaviour at that hour.
_EXPECTED_DOWN_FRACTION = 0.7

# How long a computed baseline is reused before recomputation. Baselines move on
# the scale of days; this sits on the 60 s availability cycle, so recomputing
# per call would put a multi-thousand-row query on the monitor thread every
# minute per target.
_DEFAULT_TTL_S = 3600

_DEFAULT_WINDOW_DAYS = 7

# States that mean "the device answered". DEGRADED is reachable — slow is not
# absent, and counting it as downtime would teach the duty cycle that a
# permanently-slow device is permanently asleep.
_REACHABLE_STATES = ("UP", "DEGRADED")


# ── Pure maths — no store, no cache, directly testable ───────────────────────

def derive_degraded_threshold(
    rtts: Sequence[float],
    default_ms: float,
    sigma: float = _SIGMA,
) -> float:
    """Return the DEGRADED threshold for a device with these RTT samples.

    `mean + sigma*stddev`, floored at `default_ms` (invariant 1 above) and at a
    proportional headroom above the mean (so a zero-variance device does not
    land its threshold exactly on its own average). Negative samples are
    dropped: `rtt = -1` means "no reply", not "an extremely fast reply", and
    averaging it in would drag the mean down and *tighten* the threshold on
    exactly the devices that drop packets most.
    """
    usable = [float(r) for r in rtts if r is not None and r >= 0]
    if len(usable) < MIN_BASELINE_SAMPLES:
        return default_ms

    n = len(usable)
    mean = sum(usable) / n
    variance = sum((v - mean) ** 2 for v in usable) / (n - 1) if n > 1 else 0.0
    stddev = variance ** 0.5

    learned = max(
        mean + sigma * stddev,
        mean * (1.0 + _MIN_HEADROOM_FRACTION),
    )
    return max(default_ms, learned)


def hour_of_week(ts: int) -> int:
    """Bucket `ts` into 0..167 (Monday 00:00 = 0).

    Local time deliberately: device sleep schedules follow the user's day, not
    UTC, and a household whose devices go quiet at 23:00 local should learn that
    as one bucket rather than smeared across two.
    """
    lt = time.localtime(ts)
    return lt.tm_wday * 24 + lt.tm_hour


def derive_hour_of_week_downtime(points: Sequence[Any]) -> Dict[int, float]:
    """Return {hour_of_week: fraction_down} for buckets with enough samples.

    Buckets below `_MIN_BUCKET_SAMPLES` are omitted entirely rather than
    reported with a shaky number — the caller distinguishes "normally down" from
    "no idea" by presence, so a thin bucket must be absent, not confident.
    """
    totals: Dict[int, int] = {}
    downs:  Dict[int, int] = {}
    for p in points:
        ts = getattr(p, "ts", None)
        if ts is None:
            continue
        bucket = hour_of_week(int(ts))
        totals[bucket] = totals.get(bucket, 0) + 1
        if getattr(p, "state", None) not in _REACHABLE_STATES:
            downs[bucket] = downs.get(bucket, 0) + 1
    return {
        bucket: downs.get(bucket, 0) / total
        for bucket, total in totals.items()
        if total >= _MIN_BUCKET_SAMPLES
    }


# ── Cached facade over MetricStore ───────────────────────────────────────────

class _HostBaseline:
    __slots__ = ("threshold_ms", "downtime_by_hour", "computed_at")

    def __init__(self, threshold_ms: float, downtime_by_hour: Dict[int, float]):
        self.threshold_ms = threshold_ms
        self.downtime_by_hour = downtime_by_hour
        self.computed_at = time.time()


class DeviceBaselines:
    """Per-device normals, computed on demand and cached for `ttl_s`.

    One instance per app, constructed where the MetricStore already is and
    injected into the consumers (`availability_monitor`, the alert engine's
    expected-down check). Never constructs a MetricStore itself.

    Every method is failure-tolerant by design: a baseline is an optimisation,
    and a database error, a missing table or a `None` store must degrade to the
    global default rather than take the monitoring thread down with it.
    """

    def __init__(
        self,
        store: Optional[Any],
        default_degraded_ms: float = 150.0,
        ttl_s: int = _DEFAULT_TTL_S,
        window_days: int = _DEFAULT_WINDOW_DAYS,
    ) -> None:
        self._store = store
        self._default_ms = float(default_degraded_ms)
        self._ttl_s = int(ttl_s)
        self._window_days = int(window_days)
        self._cache: Dict[str, _HostBaseline] = {}

    # ── Public API ────────────────────────────────────────────────────────────

    def degraded_threshold(self, host: str) -> float:
        """The RTT above which `host` is unusually slow *for itself*."""
        baseline = self._baseline_for(host)
        return baseline.threshold_ms if baseline else self._default_ms

    def is_expected_down(
        self, host: str, ts: Optional[int] = None
    ) -> Optional[bool]:
        """Is `host` normally unreachable at this hour of the week?

        True  — habitually absent now (a sleeping streaming stick at 03:00)
        False — habitually present now, so absence is news
        None  — not enough history to say. **Callers must treat None as "no
                opinion" and not suppress**; see invariant 2 in the module
                docstring.
        """
        baseline = self._baseline_for(host)
        if baseline is None:
            return None
        bucket = hour_of_week(int(ts if ts is not None else time.time()))
        fraction = baseline.downtime_by_hour.get(bucket)
        if fraction is None:
            return None
        return fraction >= _EXPECTED_DOWN_FRACTION

    def invalidate(self, host: Optional[str] = None) -> None:
        """Drop cached baselines — all of them, or just one host's."""
        if host is None:
            self._cache.clear()
        else:
            self._cache.pop(host, None)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _baseline_for(self, host: str) -> Optional[_HostBaseline]:
        cached = self._cache.get(host)
        if cached is not None and (time.time() - cached.computed_at) < self._ttl_s:
            return cached
        baseline = self._compute(host)
        # Cache the miss too. A host with no history is the common case on a
        # fresh install, and re-querying for it every cycle is exactly the I/O
        # the TTL exists to avoid.
        self._cache[host] = baseline
        return baseline

    def _compute(self, host: str) -> _HostBaseline:
        points: List[Any] = []
        if self._store is not None:
            try:
                points = list(
                    self._store.query_device_state_history(
                        host, hours=self._window_days * 24.0
                    )
                    or []
                )
            except Exception:
                points = []  # a baseline is an optimisation; never fatal
        rtts = [
            getattr(p, "rtt_ms", None)
            for p in points
            if getattr(p, "rtt_ms", None) is not None
        ]
        return _HostBaseline(
            threshold_ms=derive_degraded_threshold(rtts, self._default_ms),
            downtime_by_hour=derive_hour_of_week_downtime(points),
        )
