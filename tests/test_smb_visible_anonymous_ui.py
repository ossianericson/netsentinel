"""
Regression test for F-88 (claims-audit/BACKLOG): help text claimed shares are flagged
specifically when "visible without a password," but the shares table's HIGH/-- column
fired on any non-hidden DISK share regardless of whether the scan authenticated
anonymously or with credentials -- disagreeing with the (also-fixed) risk_flags banner.

Fix: SMBShare.visible_anonymous (modules/smb_enumerator.py) tracks whether a share was
seen via a no-credentials/null session; _on_smb_result (ui/scan_enrichment.py) now
requires it before marking a row HIGH.
"""
from __future__ import annotations

import types

import pytest

try:
    from PyQt6.QtWidgets import QLabel, QTableWidget
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

pytestmark = pytest.mark.skipif(not _HAS_QT, reason="PyQt6 not available")


def _call_on_smb_result(result):
    from ui.scan_enrichment import ScanEnrichmentMixin

    obj = types.SimpleNamespace(
        _smb_verdict=QLabel(),
        _smb_status=QLabel(),
        _recon_smb_shares_table=QTableWidget(0, 4),
        _recon_smb_users_table=QTableWidget(0, 4),
    )
    ScanEnrichmentMixin._on_smb_result(obj, result)
    return obj


def test_high_risk_only_for_anonymously_visible_disk_share():
    from modules.smb_enumerator import SMBEnumResult, SMBShare

    result = SMBEnumResult(
        host="10.0.0.5",
        shares=[
            SMBShare(name="Public", share_type="DISK", visible_anonymous=True),
            SMBShare(name="Private", share_type="DISK", visible_anonymous=False),
        ],
        tier=2,
    )
    obj = _call_on_smb_result(result)

    assert obj._recon_smb_shares_table.rowCount() == 2
    risk_col = 3
    assert obj._recon_smb_shares_table.item(0, risk_col).text() == "HIGH"
    assert obj._recon_smb_shares_table.item(1, risk_col).text() == "—"


def test_no_high_risk_row_when_nothing_anonymously_visible():
    from modules.smb_enumerator import SMBEnumResult, SMBShare

    result = SMBEnumResult(
        host="10.0.0.5",
        shares=[SMBShare(name="Private", share_type="DISK", visible_anonymous=False)],
        tier=2,
    )
    obj = _call_on_smb_result(result)

    risk_col = 3
    assert obj._recon_smb_shares_table.item(0, risk_col).text() == "—"
