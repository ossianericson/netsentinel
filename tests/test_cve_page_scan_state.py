"""
tests/test_cve_page_scan_state.py — RULE-T7 behavioural coverage for CvePage's
data_refreshed signal (S6).

CVE Tracker was one of three registered Security Audit pages that never
called _nav_set_scan_state anywhere, so its Scan Status row read "Never run"
forever even with tracked CVEs on screen. The fix adds a data_refreshed
signal emitted at the end of _refresh(), wired in ui/tabs.py to
_nav_set_scan_state(L.CVE_TRACKER, "fresh", ...).
"""
from __future__ import annotations

import pytest

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)


class _FakeStore:
    def __init__(self, rows: list):
        self._rows = rows

    def list_cve_lifecycles(self, state_filter=None):
        if state_filter is None:
            return list(self._rows)
        return [r for r in self._rows if r["state"] == state_filter]

    def get_known_devices(self):
        return {}


@pytest.fixture(autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _row(cve_id: str, state: str = "Open") -> dict:
    return {
        "id": 1, "cve_id": cve_id, "host": "192.168.1.10", "service": "OpenSSH",
        "severity": "HIGH", "state": state, "opened_ts": 0, "cvss_score": 7.5,
        "description": "", "owner": "", "notes": "",
    }


def test_data_refreshed_emits_the_tracked_count_on_construction():
    from ui.pages.cve_page import CvePage

    store = _FakeStore([_row("CVE-2024-1"), _row("CVE-2024-2")])
    received = []
    page = CvePage(store, parent=None)
    page.data_refreshed.connect(received.append)

    page._refresh()

    assert received == [2]
    page.deleteLater()


def test_data_refreshed_emits_zero_for_an_empty_tracker():
    from ui.pages.cve_page import CvePage

    store = _FakeStore([])
    received = []
    page = CvePage(store, parent=None)
    page.data_refreshed.connect(received.append)

    page._refresh()

    assert received == [0]
    page.deleteLater()
