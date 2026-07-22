"""
Test for F-73 -- Device Risk Score claims a row click reveals contributing
findings; no click handler existed.

_run_risk_scorer() already computes the full RiskAssessment.findings list per
device (title/impact/remediation/score_contribution -- modules/risk_scorer.py)
but the table only ever rendered findings[0] as a static "Primary Finding"
column. This covers wiring a cellClicked handler that surfaces every finding
for the clicked row's device, matching ui/help.py's existing claim.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from modules.risk_scorer import RiskAssessment, RiskFinding  # noqa: E402
from ui.tabs_helpers import _table  # noqa: E402
from ui.tabs_recon import _ReconTabsMixin  # noqa: E402


class _FakeHost(_ReconTabsMixin):
    """Minimal stand-in exposing only what _run_risk_scorer/_on_risk_cell_clicked touch."""

    def __init__(self) -> None:
        self._m1_result = {"devices": []}
        self._cred_access_hosts = None
        self._risk_status = MagicMock()
        # RULE-SS1: _run_risk_scorer now records its scan state on the nav registry
        self._nav_set_scan_state = MagicMock()
        self._recon_risk_table = _table(
            ["IP", "Device Type", "Score", "Severity", "Primary Finding", "Remediation"]
        )


_ASSESSMENTS = [
    RiskAssessment(
        ip="10.0.0.5", mac="aa:bb:cc:dd:ee:01", hostname="nas1", vendor="Synology",
        device_type="NAS", os_family="Linux", total_score=82, severity="HIGH",
        findings=[
            RiskFinding(title="Telnet open (port 23)", score_contribution=40,
                        impact="Cleartext remote admin access", remediation="Disable Telnet"),
            RiskFinding(title="Outdated firmware", score_contribution=25,
                        impact="Known CVEs unpatched", remediation="Update firmware"),
            RiskFinding(title="Default credentials accepted", score_contribution=17,
                        impact="Trivial takeover", remediation="Change the password"),
        ],
        plain_summary="High risk device", top_remediation="Disable Telnet",
    ),
]


def _click_row_zero(monkeypatch) -> str:
    """Populate the risk table via the real scorer call, click row 0, and
    return the text passed to QMessageBox.information (or "" if none shown)."""
    monkeypatch.setattr("modules.risk_scorer.score_devices", lambda *a, **kw: _ASSESSMENTS)
    host = _FakeHost()
    host._run_risk_scorer()

    with patch("PyQt6.QtWidgets.QMessageBox.information") as mock_info:
        host._on_risk_cell_clicked(0, 0)
        if not mock_info.called:
            return ""
        args, _kwargs = mock_info.call_args
        return args[-1] if args else ""


class TestRiskScoreRowClickShowsAllFindings:
    def test_click_reveals_every_contributing_finding_not_just_primary(self, monkeypatch):
        text = _click_row_zero(monkeypatch)
        assert text, "clicking a Device Risk Score row must show the contributing findings"
        assert "Telnet open (port 23)" in text
        assert "Outdated firmware" in text
        assert "Default credentials accepted" in text

    def test_click_shows_remediation_for_each_finding(self, monkeypatch):
        text = _click_row_zero(monkeypatch)
        assert "Disable Telnet" in text
        assert "Update firmware" in text
        assert "Change the password" in text


# Live-walk regression (Sprint 5a RULE-T6): a not_testable device whose only
# finding is the noise "Vendor risk (UNKNOWN)" placeholder — see
# tests/test_risk_scorer.py::test_not_testable_with_only_unknown_vendor_finding_...
_INSUFFICIENT_DATA_ASSESSMENT = RiskAssessment(
    ip="10.0.0.9", mac="", hostname="", vendor="Acme Corp",
    device_type="", os_family="", total_score=3, severity="INFO",
    findings=[RiskFinding(
        title="Vendor risk (UNKNOWN): Acme Corp", score_contribution=3,
        impact="Vendor flagged in OUI risk database.",
        remediation="Review known issues for this vendor and apply recommended network segmentation.",
    )],
    plain_summary=(
        "10.0.0.9 — Insufficient data — Port Scan could not reach this device, "
        "so this is not a confirmed clean result."
    ),
    top_remediation="Re-run the scan from a network path that can reach this device.",
    not_testable_inputs=["Port Scan"],
    insufficient_data=True,
)


class TestRiskScoreTableShowsInsufficientData:
    def test_primary_finding_column_shows_coverage_gap_not_vendor_noise(self, monkeypatch):
        monkeypatch.setattr(
            "modules.risk_scorer.score_devices", lambda *a, **kw: [_INSUFFICIENT_DATA_ASSESSMENT]
        )
        host = _FakeHost()
        host._run_risk_scorer()
        primary_finding_item = host._recon_risk_table.item(0, 4)
        assert "Could not test" in primary_finding_item.text()
        assert "Vendor risk" not in primary_finding_item.text()

    def test_row_click_shows_dialog_even_with_only_noise_finding(self, monkeypatch):
        monkeypatch.setattr(
            "modules.risk_scorer.score_devices", lambda *a, **kw: [_INSUFFICIENT_DATA_ASSESSMENT]
        )
        host = _FakeHost()
        host._run_risk_scorer()
        with patch("PyQt6.QtWidgets.QMessageBox.information") as mock_info:
            host._on_risk_cell_clicked(0, 0)
            assert mock_info.called, "clicking an insufficient-data row must not silently no-op"
            args, _kwargs = mock_info.call_args
            text = args[-1] if args else ""
            assert "Insufficient data" in text
