"""
Regression tests for two doc-only claims-audit fixes to ui/help.py's live
_PAGE_HELP copy (F-61, F-70) -- each corrects a sentence that described
behaviour the app doesn't actually have.
"""
from __future__ import annotations

from ui.help import _PAGE_HELP


class TestF70ScheduledScansPortScanClaim:
    """modules/scheduler.py's _run_scan() only ever calls
    modules.rogue_device.scan() -- device discovery, never a port scan."""

    def test_help_no_longer_claims_port_scans(self):
        text = _PAGE_HELP["Scheduled Scans"]["what"]
        assert "port scan" not in text.lower()

    def test_help_states_the_real_behavior(self):
        text = _PAGE_HELP["Scheduled Scans"]["what"]
        assert "discovery" in text.lower()


class TestF61NetworkMapClickBehavior:
    """ui/tabs_monitors.py opens a _DeviceDrawer overlay on the Network Map
    page itself -- clicking a node never navigates to the Devices page."""

    def test_help_no_longer_claims_navigation_to_devices_page(self):
        text = " ".join(_PAGE_HELP["Network Map"].get("hidden", []))
        assert "jump to that device's row in the Devices page" not in text

    def test_help_describes_the_real_drawer_behavior(self):
        text = " ".join(_PAGE_HELP["Network Map"].get("hidden", []))
        assert "drawer" in text.lower() or "on this page" in text.lower()
