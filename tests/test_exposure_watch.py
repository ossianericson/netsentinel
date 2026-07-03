"""Tests for modules/exposure_watch.py (V6 Sprint 3.4 — weekly exposure check)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from modules.config_baseline import build_snapshot_from_scan
from modules.internet_exposure import ExposureResult


def test_import():
    from modules.exposure_watch import run_weekly_exposure_check, ExposureWatchReport
    assert run_weekly_exposure_check is not None
    assert ExposureWatchReport is not None


def test_first_run_stores_snapshot_with_no_diff():
    from modules.exposure_watch import run_weekly_exposure_check

    store = MagicMock()
    store.list_snapshots.return_value = []
    store.store_snapshot.return_value = 1

    result = ExposureResult(wan_ip="1.2.3.4", exposed={"192.168.1.40": [80]})
    with patch("modules.exposure_watch.internet_exposure.check_exposure", return_value=result):
        report = run_weekly_exposure_check(store)

    assert report.new_exposed == []
    assert report.result.wan_ip == "1.2.3.4"


def test_second_run_detects_newly_exposed_port():
    from modules.exposure_watch import run_weekly_exposure_check

    store = MagicMock()
    prior_snap = build_snapshot_from_scan(
        [{"ip": "192.168.1.40", "open_ports": [80]}], label="posture_exposure_check",
    )
    prior_snap.id = 1
    prior_snap.ts = 1000
    prior_row = {"id": 1, "ts": 1000, "label": "posture_exposure_check", "data_json": prior_snap.to_json()}
    store.list_snapshots.return_value = [prior_row]
    store.store_snapshot.return_value = 2

    result = ExposureResult(wan_ip="1.2.3.4", exposed={"192.168.1.40": [80, 445]})
    with patch("modules.exposure_watch.internet_exposure.check_exposure", return_value=result):
        report = run_weekly_exposure_check(store)

    assert report.new_exposed == [("192.168.1.40", 445)]
