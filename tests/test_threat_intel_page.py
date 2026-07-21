"""
Sprint 5b (B) -- ThreatIntelPage feed-refresh not_testable signal.

_on_db_ready() previously always emitted scan_complete regardless of outcome,
so "every OSINT feed failed to download and none had a cached fallback" (an
unreachable-network coverage gap) read identically to "feeds downloaded fine,
0 indicators today" -- the same false-clean-result pattern fixed elsewhere in
Sprint 5b, applied here without needing to touch modules/threat_intel.py at
all: _fetch_one_feed() already falls back to a stale local cache file on
download failure, so an EMPTY combined list from a live refresh specifically
means every feed failed AND none had ANY cached data -- a near-impossible
outcome for genuinely reachable public OSINT blocklists (which always carry
entries), not a plausible "0 threats found today" result.
"""
from __future__ import annotations

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication  # noqa: E402


def _make_page():
    from ui.pages.threat_intel_page import ThreatIntelPage
    app = QApplication.instance() or QApplication([])
    return ThreatIntelPage(parent=None), app


def _cleanup(page, app):
    page.deleteLater()
    for _ in range(3):
        app.processEvents()


class TestThreatIntelNotTestableSignal:
    def test_zero_entries_from_live_refresh_emits_not_testable(self):
        from modules.threat_intel import ThreatIntelDB
        page, app = _make_page()
        try:
            not_testable_msgs: list = []
            complete_count = [0]
            page.scan_not_testable.connect(lambda msg: not_testable_msgs.append(msg))
            page.scan_complete.connect(lambda: complete_count.__setitem__(0, complete_count[0] + 1))

            empty_db = ThreatIntelDB.from_entries([])
            page._on_db_ready(empty_db, from_cache=False)

            assert len(not_testable_msgs) == 1
            assert not_testable_msgs[0] != ""
            assert complete_count[0] == 0
        finally:
            _cleanup(page, app)

    def test_zero_entries_from_cache_load_does_not_emit_not_testable(self):
        """Loading an empty LOCAL cache (e.g. fresh install, never fetched) is
        a deliberate, expected action -- not a network coverage gap."""
        from modules.threat_intel import ThreatIntelDB
        page, app = _make_page()
        try:
            not_testable_msgs: list = []
            page.scan_not_testable.connect(lambda msg: not_testable_msgs.append(msg))

            empty_db = ThreatIntelDB.from_entries([])
            page._on_db_ready(empty_db, from_cache=True)

            assert not_testable_msgs == []
        finally:
            _cleanup(page, app)

    def test_nonzero_entries_emits_scan_complete_not_not_testable(self):
        from modules.threat_intel import ThreatEntry, ThreatIntelDB
        page, app = _make_page()
        try:
            not_testable_msgs: list = []
            complete_count = [0]
            page.scan_not_testable.connect(lambda msg: not_testable_msgs.append(msg))
            page.scan_complete.connect(lambda: complete_count.__setitem__(0, complete_count[0] + 1))

            db = ThreatIntelDB.from_entries([
                ThreatEntry(indicator="1.2.3.4", itype="ip", categories=["botnet_c2"],
                            source="test", confidence=80, last_seen=""),
            ])
            page._on_db_ready(db, from_cache=False)

            assert not_testable_msgs == []
            assert complete_count[0] == 1
        finally:
            _cleanup(page, app)


class TestAbuseNotTestableHandler:
    def test_on_abuse_not_testable_shows_could_not_test_not_private_ip_text(self):
        """Sprint 5b (B): an unreachable AbuseIPDB API must render as a
        distinguishable 'could not test' message, not the private/no-data
        wording used for a genuinely private IP or missing API key."""
        page, app = _make_page()
        try:
            page._lookup_btn.setEnabled(False)
            page._lookup_btn.setText("Checking…")
            page._lookup_result.setText("1.2.3.4: not in local blocklist.")

            page._on_abuse_not_testable("timed out")

            text = page._lookup_result.text()
            assert "Could not test" in text
            assert "timed out" in text
            assert "private" not in text.lower()
            assert page._lookup_btn.isEnabled() is True
        finally:
            _cleanup(page, app)


class TestThreatIntelScanStartedSignal:
    def test_run_refresh_emits_scan_started(self, monkeypatch):
        """Sprint 5b (B): _run_refresh() previously set zero nav state at all
        (RULE-SS1 gap) -- the Scan Status card 'running' row depends on this.

        _run_refresh() defers the actual worker start via a zero-delay
        QTimer (RULE-WIN5) so WM_LBUTTONUP can return to Windows first. The
        autouse _flush_qt_events fixture calls processEvents() during test
        teardown, which would fire that deferred timer AFTER this test
        returns and spin up a real network-touching QThread -- neutered here
        by stubbing _start_refresh_worker to a no-op before triggering it."""
        page, app = _make_page()
        try:
            monkeypatch.setattr(page, "_start_refresh_worker", lambda: None)
            started_count = [0]
            page.scan_started.connect(lambda: started_count.__setitem__(0, started_count[0] + 1))
            page._run_refresh()
            assert started_count[0] == 1
        finally:
            _cleanup(page, app)
