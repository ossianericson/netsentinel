"""
modules/scheduled_speed_test.py — probe callable for ProactiveProbeWorker
(Sprint 3) that runs a background speed test, persists it, and returns the
context evaluate_baseline_metrics() needs to check for a BASELINE_DROP.

Architecture rules
-------------------
  • Pure Python — no PyQt6, no ui/ imports (ARCH RULE 3).
  • Delegates to modules.speed_tester.run_test() — the existing 3-tier
    backend cascade (RULE 24). Never reimplement it here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from modules.metric_store import MetricStore
from modules import speed_tester


@dataclass
class ScheduledSpeedTestResult:
    download_mbps: float
    upload_mbps: float
    ping_ms: float
    prior_downloads: List[float]
    current_sinr: Optional[float] = None
    prior_sinr: List[float] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.prior_sinr is None:
            self.prior_sinr = []


def run_scheduled_speed_test(store: MetricStore) -> ScheduledSpeedTestResult:
    """
    Run one speed test, persist it via MetricStore, and return the result
    plus prior download-speed history (for BASELINE_DROP evaluation).

    Prior history is queried *before* the new result is persisted, so it
    never includes the test this call is about to record.

    V6 Sprint 5.2 — also reads the most recent modem_signal_log entries
    (populated independently by the always-on modem monitor, if a 5G modem
    plugin is configured) so evaluate_baseline_metrics() can tell a radio
    problem apart from an ISP problem. Absent any modem plugin, this is
    simply an empty list and current_sinr stays None — no behavior change.
    """
    prior_downloads = [
        p.download_mbps for p in store.query_speed_test_history(hours=1440.0, limit=400)
    ]

    modem_points = store.query_modem_signal_log(hours=1440.0, limit=200)
    current_sinr = modem_points[0].nr5g_sinr if modem_points else None
    prior_sinr = [p.nr5g_sinr for p in modem_points[1:] if p.nr5g_sinr is not None]

    result = speed_tester.run_test()

    store.record_speed_test(
        download_mbps=result.download_mbps,
        upload_mbps=result.upload_mbps,
        ping_ms=result.ping_ms,
        server_name=result.server_name,
        server_city=result.server_city,
        server_country=result.server_country,
    )

    return ScheduledSpeedTestResult(
        download_mbps=result.download_mbps,
        upload_mbps=result.upload_mbps,
        ping_ms=result.ping_ms,
        prior_downloads=prior_downloads,
        current_sinr=current_sinr,
        prior_sinr=prior_sinr,
    )
