"""Tests for modules/cve_recheck.py (V6 Sprint 3.2 — scheduled CVE re-check)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from modules.cve_lookup import CVELookupResult, CVEResult


def _tracked_row(host, service, cve_id, severity="HIGH", cvss=7.5):
    return {
        "id": 1, "cve_id": cve_id, "service": service, "host": host, "state": "Open",
        "owner": "", "notes": "", "cvss_score": cvss, "severity": severity,
        "description": "desc", "opened_ts": 0, "updated_ts": 0,
    }


def test_import():
    from modules.cve_recheck import run_cve_recheck, CveRecheckReport
    assert run_cve_recheck is not None
    assert CveRecheckReport is not None


def test_no_new_cve_when_lookup_matches_existing():
    from modules.cve_recheck import run_cve_recheck

    store = MagicMock()
    store.list_cve_lifecycles.return_value = [
        _tracked_row("192.168.1.10", "OpenSSH 8.9p1", "CVE-2023-1111"),
    ]
    lookup_result = CVELookupResult(
        keyword="OpenSSH 8.9p1",
        cves=[CVEResult(cve_id="CVE-2023-1111", description="d", cvss_score=7.5,
                         severity="HIGH", published="2023-01-01")],
    )
    with patch("modules.cve_recheck.cve_lookup.lookup", return_value=lookup_result):
        report = run_cve_recheck(store)

    assert report.new_cves == []
    store.upsert_cve_lifecycle.assert_not_called()


def test_new_cve_detected_and_persisted():
    from modules.cve_recheck import run_cve_recheck

    store = MagicMock()
    store.list_cve_lifecycles.return_value = [
        _tracked_row("192.168.1.10", "OpenSSH 8.9p1", "CVE-2023-1111"),
    ]
    lookup_result = CVELookupResult(
        keyword="OpenSSH 8.9p1",
        cves=[
            CVEResult(cve_id="CVE-2023-1111", description="d", cvss_score=7.5,
                       severity="HIGH", published="2023-01-01"),
            CVEResult(cve_id="CVE-2024-9999", description="new one", cvss_score=9.8,
                       severity="CRITICAL", published="2024-06-01"),
        ],
    )
    with patch("modules.cve_recheck.cve_lookup.lookup", return_value=lookup_result):
        report = run_cve_recheck(store)

    assert len(report.new_cves) == 1
    host, service, cve = report.new_cves[0]
    assert host == "192.168.1.10"
    assert service == "OpenSSH 8.9p1"
    assert cve.cve_id == "CVE-2024-9999"
    store.upsert_cve_lifecycle.assert_called_once()
    kwargs = store.upsert_cve_lifecycle.call_args.kwargs
    assert kwargs["cve_id"] == "CVE-2024-9999"
    assert kwargs["host"] == "192.168.1.10"


def test_no_tracked_services_means_no_lookups():
    from modules.cve_recheck import run_cve_recheck

    store = MagicMock()
    store.list_cve_lifecycles.return_value = []
    with patch("modules.cve_recheck.cve_lookup.lookup") as mock_lookup:
        report = run_cve_recheck(store)

    mock_lookup.assert_not_called()
    assert report.new_cves == []
