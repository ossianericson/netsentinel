"""
Regression tests for three doc-only claims-audit fixes outside ui/help.py
(F-12, F-17, F-77) -- README.md and ui/pages/discover_data.py claims that
described behaviour the app doesn't actually have.
"""
from __future__ import annotations

from pathlib import Path

from ui.pages.discover_data import _FEATURES

ROOT = Path(__file__).parent.parent


class TestF12IspReportReadmeClaim:
    """modules/report_isp.py's real caller (ui/tabs_analysis_isp.py) never
    constructs an mtr_result -- every real export falls into the plain
    single-pass traceroute branch that hardcodes '--' for Packet Loss and
    Last RTT. There is no repeated-pass MTR-style loss/RTT aggregator
    anywhere in the codebase."""

    def test_readme_no_longer_claims_mtr_or_packet_loss(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        bullet = next(
            l for l in text.splitlines()
            if l.strip().startswith("- **ISP Accountability Report**")
        )
        assert "MTR" not in bullet
        assert "packet-loss" not in bullet

    def test_readme_states_traceroute(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        bullet = next(
            l for l in text.splitlines()
            if l.strip().startswith("- **ISP Accountability Report**")
        )
        assert "traceroute" in bullet.lower()


class TestF17FeatureGuideNewInVersion:
    """The 'New in this version' group's two entries referenced '...v1.9.97'
    while the app ships v2.1.30 -- dozens of releases had shipped since
    with no update to this group."""

    def _new_in_version_entries(self):
        return [f for f in _FEATURES if f["group"] == "New in this version"]

    def test_entries_no_longer_reference_stale_version(self):
        entries = self._new_in_version_entries()
        assert entries, "expected at least one 'New in this version' entry"
        for f in entries:
            assert "v1.9.97" not in f["desc"]

    def test_entries_reference_current_era_versions(self):
        entries = self._new_in_version_entries()
        assert any("v2.1." in f["desc"] for f in entries)


class TestF77HardwarePluginRefreshInterval:
    """workers/plugin_polling_worker.py's _INTERVALS dict is
    {"modem": 30, "router": 60, "ap": 60, "switch": 300} -- refresh cadence
    varies by device type, never a flat 5 minutes."""

    def _hardware_hub_entry(self):
        return next(f for f in _FEATURES if f["name"] == "Hardware Hub")

    def test_no_longer_claims_flat_five_minutes(self):
        desc = self._hardware_hub_entry()["desc"]
        assert "every 5 minutes" not in desc

    def test_states_the_real_variable_range(self):
        desc = self._hardware_hub_entry()["desc"]
        assert "30" in desc and "300" in desc
