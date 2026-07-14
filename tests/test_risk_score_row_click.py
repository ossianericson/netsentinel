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
