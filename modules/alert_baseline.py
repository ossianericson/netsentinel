"""
alert_baseline — 7-day rolling baseline for anomaly-aware alerting (S4-2).

After 7 days of monitoring data the baseline is considered "mature".  Rule
evaluations can then use personal baselines rather than fixed absolute
thresholds, reducing false positives on networks that naturally have higher
latency or lower speeds.

Metrics tracked
---------------
  rtt_ms        — per-host average RTT over 7 days (from rtt_sample table)
  loss_pct      — per-host packet-loss percentage over 7 days
  download_mbps — download speed baseline from speed-test history
  upload_mbps   — upload speed baseline from speed-test history

Architecture rules
------------------
  • Pure Python — no PyQt6, no ui/ imports (ARCH RULE 3).
  • MetricStore injected at call time — never instantiated here.
  • No third-party packages — only stdlib math.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:
    from modules.metric_store import MetricStore

# ── Days required before baseline is considered mature ───────────────────────
_BASELINE_DAYS = 7
_MIN_SAMPLES = 30           # minimum samples required for a metric to be valid


# ── Data types ────────────────────────────────────────────────────────────────

@dataclass
class BaselineMetric:
    """Statistics for a single metric."""
    mean:         float
    stddev:       float
    sample_count: int
    days_covered: float     # how many days of data back-fill this metric

    @property
    def is_valid(self) -> bool:
        """True if there are enough samples to trust this baseline."""
        return self.sample_count >= _MIN_SAMPLES

    def anomaly_threshold(self, sigma: float = 2.0) -> float:
        """Return mean + sigma * stddev as the upper anomaly boundary."""
        return self.mean + sigma * self.stddev

    def low_threshold(self, sigma: float = 2.0) -> float:
        """Return mean - sigma * stddev as the lower anomaly boundary (e.g. speed drops)."""
        return max(0.0, self.mean - sigma * self.stddev)


@dataclass
class Baseline:
    """Complete baseline snapshot for one host or the network overall."""
    host:          Optional[str]                         # None = network-wide
    rtt_ms:        Optional[BaselineMetric]   = None
    loss_pct:      Optional[BaselineMetric]   = None
    download_mbps: Optional[BaselineMetric]   = None
    upload_mbps:   Optional[BaselineMetric]   = None
    computed_at:   int                        = field(default_factory=lambda: int(time.time()))

    @property
    def is_mature(self) -> bool:
        """True when at least one metric has 7+ days of valid data."""
        for m in (self.rtt_ms, self.loss_pct, self.download_mbps, self.upload_mbps):
            if m and m.is_valid and m.days_covered >= _BASELINE_DAYS:
                return True
        return False


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mean_stddev(values: List[float]) -> tuple[float, float]:
    """Return (mean, sample stddev) for a non-empty list.  Returns (0, 0) for < 2 items."""
    n = len(values)
    if n == 0:
        return 0.0, 0.0
    mean = sum(values) / n
    if n < 2:
        return mean, 0.0
    variance = sum((v - mean) ** 2 for v in values) / (n - 1)
    return mean, math.sqrt(variance)


def modem_sinr_dropped(
    current_sinr: Optional[float],
    prior_sinr: List[float],
    min_samples: int = 20,
    sigma: float = 2.0,
) -> bool:
    """True if `current_sinr` is more than `sigma` std-devs below the mean of
    `prior_sinr` — reuses the mean+2sigma baseline math (MODEM_SIGNAL_DROP,
    V6 Sprint 1) rather than a fixed absolute threshold."""
    if current_sinr is None or len(prior_sinr) < min_samples:
        return False
    mean, std = _mean_stddev(prior_sinr)
    if std <= 0:
        return False
    metric = BaselineMetric(
        mean=mean, stddev=std, sample_count=len(prior_sinr), days_covered=_BASELINE_DAYS,
    )
    return current_sinr < metric.low_threshold(sigma)


# ── Core learner ──────────────────────────────────────────────────────────────

class BaselineLearner:
    """
    Computes and caches rolling 7-day baselines from MetricStore.

    Usage
    -----
    learner = BaselineLearner()
    learner.refresh(store)           # call periodically (e.g. hourly)

    host_bl = learner.get_host_baseline("8.8.8.8")
    if host_bl and host_bl.is_mature and host_bl.rtt_ms:
        threshold = host_bl.rtt_ms.anomaly_threshold(sigma=2.0)
    """

    def __init__(self) -> None:
        # host → Baseline
        self._host_baselines: Dict[str, Baseline] = {}
        # network-wide (speed test, device count)
        self._network_baseline: Optional[Baseline] = None
        self._last_refresh: float = 0.0

    # ── Public API ────────────────────────────────────────────────────────────

    def get_host_baseline(self, host: str) -> Optional[Baseline]:
        """Return cached baseline for *host*, or None if not yet computed."""
        return self._host_baselines.get(host)

    def get_network_baseline(self) -> Optional[Baseline]:
        """Return cached network-wide baseline (speed, etc.), or None."""
        return self._network_baseline

    def is_mature(self) -> bool:
        """True when at least one baseline is computed and mature."""
        if self._network_baseline and self._network_baseline.is_mature:
            return True
        return any(b.is_mature for b in self._host_baselines.values())

    def refresh(self, store: MetricStore) -> None:
        """Recompute baselines from MetricStore.  Call periodically (not on every cycle)."""
        now = time.time()
        self._refresh_host_baselines(store, now)
        self._refresh_network_baseline(store, now)
        self._last_refresh = now

    # ── Internal ──────────────────────────────────────────────────────────────

    def _refresh_host_baselines(self, store, now: float) -> None:
        """Per-host RTT and loss baselines from rtt_sample."""
        hosts = store.query_all_rtt_hosts(hours=_BASELINE_DAYS * 24.0)
        for host in hosts:
            points = store.query_rtt_history(host, hours=_BASELINE_DAYS * 24.0)
            if not points:
                continue

            rtts  = [p.rtt_ms  for p in points if p.rtt_ms >= 0]
            losses = [p.loss_pct for p in points if p.loss_pct is not None]

            if rtts:
                mean, std = _mean_stddev(rtts)
                oldest_ts = min(p.ts for p in points)
                days = (now - oldest_ts) / 86400.0
                rtt_metric = BaselineMetric(
                    mean=mean, stddev=std,
                    sample_count=len(rtts), days_covered=days,
                )
            else:
                rtt_metric = None

            if losses:
                mean, std = _mean_stddev(losses)
                oldest_ts = min(p.ts for p in points)
                days = (now - oldest_ts) / 86400.0
                loss_metric = BaselineMetric(
                    mean=mean, stddev=std,
                    sample_count=len(losses), days_covered=days,
                )
            else:
                loss_metric = None

            self._host_baselines[host] = Baseline(
                host=host,
                rtt_ms=rtt_metric,
                loss_pct=loss_metric,
            )

    def _refresh_network_baseline(self, store, now: float) -> None:
        """Network-wide speed baseline from speed-test history."""
        points = store.query_speed_test_history(hours=_BASELINE_DAYS * 24.0)
        if not points:
            self._network_baseline = Baseline(host=None)
            return

        downloads = [p.download_mbps for p in points if p.download_mbps and p.download_mbps > 0]
        uploads   = [p.upload_mbps   for p in points if p.upload_mbps   and p.upload_mbps   > 0]

        oldest_ts = min(p.ts for p in points)
        days = (now - oldest_ts) / 86400.0

        dl_metric: Optional[BaselineMetric] = None
        ul_metric: Optional[BaselineMetric] = None

        if downloads:
            mean, std = _mean_stddev(downloads)
            dl_metric = BaselineMetric(
                mean=mean, stddev=std,
                sample_count=len(downloads), days_covered=days,
            )
        if uploads:
            mean, std = _mean_stddev(uploads)
            ul_metric = BaselineMetric(
                mean=mean, stddev=std,
                sample_count=len(uploads), days_covered=days,
            )

        self._network_baseline = Baseline(
            host=None,
            download_mbps=dl_metric,
            upload_mbps=ul_metric,
        )
