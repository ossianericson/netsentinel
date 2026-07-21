"""
Sprint 5b (A) -- CVE Lookup batch-level not_testable aggregation.

_on_cve_result() (ui/scan_wiring.py) fires once per completed service-version
lookup and always sets "fresh" live, since the last call wins that is only a
transient progress indicator. The definitive verdict can only be known once
every service version has reported back -- _on_cve_finished() (ui/tabs_recon.py)
-- mirroring OS Detection's "all guesses not_testable" aggregation from
Sprint 5a, adapted to CVE Lookup's incremental per-item worker design.
"""
from __future__ import annotations

import types
import unittest
from unittest.mock import MagicMock


class _FakeCVELookupResult:
    def __init__(self, not_testable=False, not_testable_reason=""):
        self.cves = []
        self.not_testable = not_testable
        self.not_testable_reason = not_testable_reason


def _make_stub():
    from PyQt6.QtWidgets import QLabel, QStackedWidget, QTableWidget

    from ui.nav.builder import _NavBuilderMixin
    from ui.scan_wiring import ScanResultMixin
    from ui.tabs_recon import _ReconTabsMixin

    states: list = []

    class _Stub(ScanResultMixin, _ReconTabsMixin, _NavBuilderMixin):
        def __init__(self):
            self._scan_registry: dict = {}
            self._flyout_dots: dict = {}
            self._nav_flyout = types.SimpleNamespace(
                apply_dot=lambda l, c: None,
                set_item_tooltip=lambda l, t: None,
            )
            self._cve_stack = QStackedWidget()
            self._cve_stack.addWidget(QLabel("empty"))
            self._cve_stack.addWidget(QLabel("table"))
            self._recon_cve_table = QTableWidget(0, 6)
            self._cve_batch_results: list = []
            self._risk_status = MagicMock()
            self._m1_result = None

        def _nav_set_scan_state(self, label, state, ts=None, error=None, verdict=None):
            states.append((label, state))
            super()._nav_set_scan_state(label, state, ts=ts, error=error, verdict=verdict)

    return _Stub(), states


class TestCveNotTestableAggregation(unittest.TestCase):
    def test_all_not_testable_results_set_not_testable_state(self):
        stub, states = _make_stub()
        try:
            stub._on_cve_result("OpenSSH 8.9", _FakeCVELookupResult(
                not_testable=True, not_testable_reason="NVD API unreachable",
            ))
            stub._on_cve_result("Apache 2.4", _FakeCVELookupResult(
                not_testable=True, not_testable_reason="NVD API unreachable",
            ))
            stub._on_cve_finished()

            assert states[-1] == ("CVE Lookup", "not_testable"), (
                f"Expected final state ('CVE Lookup', 'not_testable'), got {states}"
            )
        finally:
            stub._cve_stack.deleteLater()
            stub._recon_cve_table.deleteLater()

    def test_partial_not_testable_stays_fresh(self):
        """One real result among the batch means the scan was still
        informative overall -- must not be masked as not_testable."""
        stub, states = _make_stub()
        try:
            stub._on_cve_result("OpenSSH 8.9", _FakeCVELookupResult(not_testable=True))
            stub._on_cve_result("Apache 2.4", _FakeCVELookupResult(not_testable=False))
            stub._on_cve_finished()

            assert states[-1] == ("CVE Lookup", "fresh"), (
                f"Expected final state ('CVE Lookup', 'fresh'), got {states}"
            )
        finally:
            stub._cve_stack.deleteLater()
            stub._recon_cve_table.deleteLater()

    def test_no_results_at_all_does_not_crash_and_stays_fresh(self):
        stub, states = _make_stub()
        try:
            stub._on_cve_finished()
            assert not any(st == "not_testable" for _lbl, st in states)
        finally:
            stub._cve_stack.deleteLater()
            stub._recon_cve_table.deleteLater()
