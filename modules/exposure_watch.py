"""
exposure_watch — weekly internet-exposure check with diffing
(V6 Sprint 3.4).

Runs modules.internet_exposure.check_exposure(), snapshots the resulting
per-device exposed-port map via modules.config_baseline
(label="posture_exposure_check"), and diffs against the prior week's
snapshot to surface newly internet-reachable ports.

Architecture rules observed:
  • Pure Python — no PyQt6, no ui/ imports (ARCH RULE 3).
  • MetricStore injected at call time — never instantiated here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

from modules import internet_exposure
from modules.config_baseline import (
    ConfigSnapshot,
    build_snapshot_from_scan,
    diff_snapshots,
    latest_snapshot_with_label,
    store_snapshot,
)
from modules.internet_exposure import ExposureResult
from modules.metric_store import MetricStore

EXPOSURE_LABEL = "posture_exposure_check"


@dataclass
class ExposureWatchReport:
    """Result of one weekly exposure-check run."""
    new_exposed: List[Tuple[str, int]] = field(default_factory=list)   # (ip, port)
    result: ExposureResult = field(default_factory=ExposureResult)


def run_weekly_exposure_check(store: MetricStore) -> ExposureWatchReport:
    """
    Run the internet-exposure check, store a labeled snapshot, and diff
    against the prior week's snapshot to find newly exposed ports.
    """
    result = internet_exposure.check_exposure()

    devices = [{"ip": ip, "open_ports": ports} for ip, ports in result.exposed.items()]
    prior = latest_snapshot_with_label(store, EXPOSURE_LABEL)

    new_snap = build_snapshot_from_scan(devices, label=EXPOSURE_LABEL)
    stored: ConfigSnapshot = store_snapshot(store, new_snap)

    if prior is None:
        return ExposureWatchReport(new_exposed=[], result=result)

    diff = diff_snapshots(prior, stored)
    new_exposed = [
        (ip, port)
        for ip, delta in diff.changed_ports.items()
        for port in delta.get("added", [])
    ]
    return ExposureWatchReport(new_exposed=new_exposed, result=result)
