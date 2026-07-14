"""
Regression tests for four claims-audit doc-only fixes (F-27, F-29, F-36,
F-55) -- each corrects a sentence that described behaviour the app doesn't
actually have.
"""
from __future__ import annotations

from pathlib import Path

from ui.help import _PAGE_HELP

ROOT = Path(__file__).parent.parent


def _what_text(page: str) -> str:
    return _PAGE_HELP[page]["what"]


def _hidden_text(page: str) -> str:
    return " ".join(_PAGE_HELP[page].get("hidden", []))


class TestF27BandwidthUsageClickClaim:
    """ui/tabs_monitors.py's _build_bandwidth_tab() wires no click handler on
    the table at all -- BandwidthWorker has no protocol classification of
    its own. The real per-protocol breakdown lives on the separate
    'App Traffic' page."""

    def test_help_no_longer_claims_click_row_breakdown(self):
        text = _hidden_text("Bandwidth Usage")
        assert "Click a row to see the breakdown of protocols" not in text

    def test_help_points_to_app_traffic(self):
        text = _hidden_text("Bandwidth Usage")
        assert "App Traffic" in text


class TestF29NetworkTimelineExpandClaim:
    """ui/pages/timeline_page.py's _Ev dataclass has no ip/mac fields at
    all, and clicking a row with a mapped source navigates away rather than
    expanding in place."""

    def test_help_no_longer_claims_mac_address(self):
        text = _hidden_text("Network Timeline")
        assert "MAC address" not in text

    def test_help_describes_the_real_navigate_behaviour(self):
        text = _hidden_text("Network Timeline")
        assert "navigates" in text.lower()


class TestF36RootCauseCorrelatorGroupingClaim:
    """modules/root_cause_correlator.py and ui/tabs_analysis.py only sort
    findings by severity -- category is a unique free-form string per
    finding (e.g. 'Rogue Network Bridge'), never one of a 3-way taxonomy."""

    def test_help_no_longer_claims_category_grouping(self):
        text = _hidden_text("Root Cause Correlator")
        assert "grouped by category" not in text.lower()

    def test_help_describes_flat_severity_sort(self):
        text = _hidden_text("Root Cause Correlator")
        assert "severity" in text.lower()


class TestF55MeshProviderClaim:
    """ui/scan_enrichment.py's _apply_mesh_enrichment() does merge generic
    Hardware Hub plugin data (Asus ZenWiFi, Netgear Orbi both ship real
    plugins) into the same Devices-table columns Deco uses -- but no plugin
    exists for Eero or Google Nest, so naming them is false."""

    def test_discover_data_no_longer_names_unsupported_vendors(self):
        text = (ROOT / "ui" / "pages" / "discover_data.py").read_text(encoding="utf-8")
        assert "Eero" not in text
        assert "Google Nest" not in text

    def test_discover_data_keeps_real_vendor_examples(self):
        text = (ROOT / "ui" / "pages" / "discover_data.py").read_text(encoding="utf-8")
        assert "Asus ZenWiFi" in text
        assert "Netgear Orbi" in text


class TestF60DevicesOfflineVendorClaim:
    """modules/mac_lookup.py's tier-4 fallback unconditionally called
    api.macvendors.com when local tables missed. Now allow_online=False (a
    real Settings toggle, privacy/mac_vendor_online_lookup) can suppress it
    -- the help text must disclose the fallback and point at the setting."""

    def test_help_no_longer_claims_unconditional_no_internet_call(self):
        text = _hidden_text("Devices")
        assert "no internet call needed" not in text.lower()

    def test_help_mentions_the_opt_out_setting(self):
        text = _hidden_text("Devices")
        assert "Settings" in text
