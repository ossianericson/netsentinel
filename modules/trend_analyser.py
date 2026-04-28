"""
trend_analyser — predictive trend engine for NetSentinel.

Uses ordinary least-squares linear regression (no external dependencies —
pure stdlib math) to extrapolate stored time-series data and produce
plain-English forecasts like:

    "At current growth rate, RTT for 8.8.8.8 will exceed 100 ms in ~3 days."
    "Packet loss on 192.168.1.1 is trending to 10% threshold in ~12 h."

Data sources
------------
    rtt_sample     — RTT (ms), packet-loss (%), jitter (ms) per host
    device_state   — up/down events per IP (availability trend)

All analysis is done against the MetricStore time-series tables.

Architecture rules
------------------
    • Pure Python — no PyQt6, no ui/ imports (ARCH RULE 3).
    • No third-party packages — only stdlib math + MetricStore.
    • MetricStore injected at call time — never instantiated here.
    • All timestamps handled as Unix integer seconds internally.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ── Regression core ───────────────────────────────────────────────────────────

def _linreg(xs: List[float], ys: List[float]) -> Tuple[float, float, float]:
    """
    Ordinary least-squares linear regression y = slope*x + intercept.

    Returns (slope, intercept, r_squared).
    Returns (0, mean(ys), 0) when regression is degenerate (< 2 points,
    or zero variance in x).
    """
    n = len(xs)
    if n < 2:
        mean_y = ys[0] if ys else 0.0
        return 0.0, mean_y, 0.0

    mean_x = sum(xs) / n
    mean_y = sum(ys) / n

    ss_xx = sum((x - mean_x) ** 2 for x in xs)
    ss_xy = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(n))

    if ss_xx == 0:
        return 0.0, mean_y, 0.0

    slope     = ss_xy / ss_xx
    intercept = mean_y - slope * mean_x

    ss_yy = sum((y - mean_y) ** 2 for y in ys)
    r_squared = (ss_xy ** 2 / (ss_xx * ss_yy)) if ss_yy > 0 else 1.0

    return slope, intercept, r_squared


def _project_hours_to_threshold(
    slope: float,
    intercept: float,
    current_x: float,
    threshold: float,
) -> Optional[float]:
    """
    Given y = slope*x + intercept (x in seconds), return the number of
    *hours from now* at which y will reach `threshold`.

    Returns None if:
      - slope is effectively flat (|slope| < 1e-12)
      - crossing is in the past
      - crossing is more than 30 days away (not actionable)
    """
    if abs(slope) < 1e-12:
        return None
    x_cross = (threshold - intercept) / slope
    delta_s = x_cross - current_x
    if delta_s <= 0:
        return None
    hours = delta_s / 3600.0
    if hours > 30 * 24:
        return None
    return hours


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class TrendResult:
    """
    Trend analysis result for one metric on one host.

    Attributes
    ----------
    host            : target IP or hostname
    metric          : "rtt_ms" | "loss_pct" | "jitter_ms"
    window_hours    : analysis window (e.g. 24, 168)
    sample_count    : number of data points used
    current_value   : latest observed value (most recent sample)
    mean_value      : mean over the window
    slope_per_hour  : rate of change per hour (positive = rising)
    r_squared       : fit quality (0–1; < 0.5 = noisy / no clear trend)
    threshold       : the alert threshold being tracked
    eta_hours       : hours until threshold is reached (None = won't / unknown)
    direction       : "RISING" | "FALLING" | "STABLE"
    severity        : "CRITICAL" | "WARNING" | "INFO" | "CLEAN"
    summary         : plain-English one-liner
    """
    host:           str
    metric:         str
    window_hours:   float
    sample_count:   int
    current_value:  float
    mean_value:     float
    slope_per_hour: float
    r_squared:      float
    threshold:      float
    eta_hours:      Optional[float]
    direction:      str
    severity:       str
    summary:        str


@dataclass
class TrendReport:
    """Collection of TrendResult objects for a full analysis run."""
    ts:      int                       # Unix timestamp when report was generated
    results: List[TrendResult]         = field(default_factory=list)

    @property
    def critical(self) -> List[TrendResult]:
        return [r for r in self.results if r.severity == "CRITICAL"]

    @property
    def warnings(self) -> List[TrendResult]:
        return [r for r in self.results if r.severity == "WARNING"]

    @property
    def has_alerts(self) -> bool:
        return bool(self.critical or self.warnings)


# ── Default thresholds ────────────────────────────────────────────────────────

DEFAULT_THRESHOLDS: Dict[str, float] = {
    "rtt_ms":     100.0,   # ms — alert when RTT is projected to exceed 100 ms
    "loss_pct":   5.0,     # % — alert when packet loss projected to exceed 5%
    "jitter_ms":  30.0,    # ms — alert when jitter projected to exceed 30 ms
}


def _direction(slope_per_hour: float) -> str:
    if slope_per_hour > 0.01:
        return "RISING"
    if slope_per_hour < -0.01:
        return "FALLING"
    return "STABLE"


def _eta_description(eta_hours: Optional[float]) -> str:
    if eta_hours is None:
        return "no crossing projected"
    if eta_hours < 1:
        return f"in ~{int(eta_hours * 60)} min"
    if eta_hours < 48:
        return f"in ~{eta_hours:.1f} h"
    return f"in ~{eta_hours / 24:.1f} days"


def _severity_from_eta(eta_hours: Optional[float], current_above_threshold: bool) -> str:
    if current_above_threshold:
        return "CRITICAL"
    if eta_hours is None:
        return "CLEAN"
    if eta_hours < 6:
        return "CRITICAL"
    if eta_hours < 48:
        return "WARNING"
    return "INFO"


def _build_summary(
    host: str,
    metric: str,
    direction: str,
    current_value: float,
    threshold: float,
    eta_hours: Optional[float],
    r_squared: float,
    severity: str,
) -> str:
    unit = {"rtt_ms": "ms", "loss_pct": "%", "jitter_ms": "ms"}.get(metric, "")
    metric_label = {"rtt_ms": "RTT", "loss_pct": "packet loss", "jitter_ms": "jitter"}.get(metric, metric)

    if severity == "CLEAN":
        return f"{host} — {metric_label} stable at {current_value:.1f}{unit} (threshold {threshold:.0f}{unit})"

    eta_str = _eta_description(eta_hours)
    conf = "high confidence" if r_squared >= 0.7 else "low confidence"

    if current_value >= threshold:
        return (
            f"{host} — {metric_label} is {current_value:.1f}{unit}, "
            f"already above threshold ({threshold:.0f}{unit})"
        )

    return (
        f"{host} — {metric_label} {direction.lower()} at {current_value:.1f}{unit}; "
        f"projected to reach {threshold:.0f}{unit} {eta_str} ({conf}, R²={r_squared:.2f})"
    )


# ── Analysis functions ────────────────────────────────────────────────────────

def analyse_host_rtt(
    store,
    host: str,
    window_hours: float = 24.0,
    thresholds: Optional[Dict[str, float]] = None,
) -> List[TrendResult]:
    """
    Run linear regression on RTT, loss_pct, and jitter_ms for one host.

    Parameters
    ----------
    store           : MetricStore instance
    host            : target hostname or IP
    window_hours    : how many hours of history to use for regression
    thresholds      : override default thresholds per metric

    Returns a list of up to 3 TrendResult objects (one per metric).
    Returns empty list if fewer than 3 samples available.
    """
    thr = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    points = store.query_rtt_history(host, hours=window_hours)
    results: List[TrendResult] = []

    if len(points) < 3:
        return results

    now = time.time()
    # Normalise x to hours-ago so slope is in units/hour and intercept is human-readable
    xs = [(p.ts - now) / 3600.0 for p in points]   # negative values = past

    for metric, getter in [
        ("rtt_ms",   lambda p: p.rtt_ms   if p.rtt_ms   >= 0 else None),
        ("loss_pct", lambda p: p.loss_pct),
        ("jitter_ms", lambda p: p.jitter_ms if p.jitter_ms >= 0 else None),
    ]:
        threshold = thr.get(metric, 100.0)
        pairs = [(xs[i], getter(points[i])) for i in range(len(points))
                 if getter(points[i]) is not None]
        if len(pairs) < 3:
            continue
        px, py = zip(*pairs)
        slope, intercept, r_sq = _linreg(list(px), list(py))
        current_value = py[-1]
        mean_value    = sum(py) / len(py)
        slope_per_h   = slope   # already per hour

        # Project from now (x=0) forward
        eta_hours = _project_hours_to_threshold(slope, intercept, 0.0, threshold)
        direction = _direction(slope_per_h)
        severity  = _severity_from_eta(eta_hours, current_value >= threshold)
        summary   = _build_summary(host, metric, direction, current_value,
                                   threshold, eta_hours, r_sq, severity)

        results.append(TrendResult(
            host=host,
            metric=metric,
            window_hours=window_hours,
            sample_count=len(pairs),
            current_value=round(current_value, 2),
            mean_value=round(mean_value, 2),
            slope_per_hour=round(slope_per_h, 4),
            r_squared=round(r_sq, 4),
            threshold=threshold,
            eta_hours=round(eta_hours, 2) if eta_hours is not None else None,
            direction=direction,
            severity=severity,
            summary=summary,
        ))

    return results


def run_full_trend_report(
    store,
    window_hours: float = 24.0,
    thresholds: Optional[Dict[str, float]] = None,
    max_hosts: int = 50,
) -> TrendReport:
    """
    Run trend analysis for every host that has RTT data in the window.

    Parameters
    ----------
    store           : MetricStore instance
    window_hours    : analysis window; default 24 h (enough for short-term ETA)
    thresholds      : per-metric threshold overrides
    max_hosts       : cap to avoid runaway analysis on very large networks

    Returns a TrendReport with all TrendResult objects, sorted by severity
    (CRITICAL first), then by ETA (soonest first).
    """
    hosts = store.query_all_rtt_hosts(hours=window_hours)[:max_hosts]
    all_results: List[TrendResult] = []
    for host in hosts:
        all_results.extend(analyse_host_rtt(store, host, window_hours, thresholds))

    _sev_order = {"CRITICAL": 0, "WARNING": 1, "INFO": 2, "CLEAN": 3}

    def _sort_key(r: TrendResult):
        sev = _sev_order.get(r.severity, 4)
        eta = r.eta_hours if r.eta_hours is not None else 999_999
        return (sev, eta)

    all_results.sort(key=_sort_key)
    return TrendReport(ts=int(time.time()), results=all_results)
