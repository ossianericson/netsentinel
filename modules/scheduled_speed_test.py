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
from typing import List

from modules.metric_store import MetricStore
from modules import speed_tester


@dataclass
class ScheduledSpeedTestResult:
    download_mbps: float
    upload_mbps: float
    ping_ms: float
    prior_downloads: List[float]


def run_scheduled_speed_test(store: MetricStore) -> ScheduledSpeedTestResult:
    """
    Run one speed test, persist it via MetricStore, and return the result
    plus prior download-speed history (for BASELINE_DROP evaluation).

    Prior history is queried *before* the new result is persisted, so it
    never includes the test this call is about to record.
    """
    prior_downloads = [
        p.download_mbps for p in store.query_speed_test_history(hours=1440.0, limit=400)
    ]

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
    )
