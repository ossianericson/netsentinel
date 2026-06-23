"""
tests/test_nav_scan_badges.py — Sprint B badge state tests.

Verifies that _nav_set_scan_state() correctly maps scan states to
flyout dot colours and rail button badge colours.
"""
from __future__ import annotations

import types
import unittest


def _make_mock_dashboard():
    """Minimal object satisfying _NavBuilderMixin._nav_set_scan_state."""
    from ui.nav.builder import _NavBuilderMixin

    class _MockDash(_NavBuilderMixin):
        def __init__(self):
            self._scan_registry: dict = {}
            self._flyout_dots: dict = {}
            self._nav_flyout = types.SimpleNamespace(
                apply_dot=lambda lbl, col: None,
                set_item_tooltip=lambda lbl, tip: None,
            )

    return _MockDash()


class TestFlyoutDotStateMapping(unittest.TestCase):
    def setUp(self):
        self.dash = _make_mock_dashboard()

    def test_fresh_maps_to_green(self):
        from ui.styles import GREEN
        self.dash._nav_set_scan_state("Port Scan (TCP)", "fresh")
        assert self.dash._flyout_dots["Port Scan (TCP)"] == GREEN

    def test_stale_maps_to_amber(self):
        from ui.styles import AMBER
        self.dash._nav_set_scan_state("CVE Lookup", "stale")
        assert self.dash._flyout_dots["CVE Lookup"] == AMBER

    def test_running_maps_to_accent(self):
        from ui.styles import ACCENT
        self.dash._nav_set_scan_state("Threat Intel", "running")
        assert self.dash._flyout_dots["Threat Intel"] == ACCENT

    def test_error_maps_to_red(self):
        from ui.styles import RED
        self.dash._nav_set_scan_state("Login Test", "error", error="Timeout")
        assert self.dash._flyout_dots["Login Test"] == RED

    def test_never_maps_to_empty_string(self):
        self.dash._nav_set_scan_state("OS Detection", "never")
        assert self.dash._flyout_dots["OS Detection"] == ""

    def test_registry_stores_error_message(self):
        self.dash._nav_set_scan_state("Port Scan (UDP)", "error", error="Admin required")
        assert self.dash._scan_registry["Port Scan (UDP)"]["error"] == "Admin required"

    def test_registry_stores_verdict(self):
        self.dash._nav_set_scan_state("CVE Lookup", "fresh", verdict="3 CVEs found")
        assert self.dash._scan_registry["CVE Lookup"]["verdict"] == "3 CVEs found"

    def test_multiple_labels_independent(self):
        self.dash._nav_set_scan_state("Port Scan (TCP)", "fresh")
        self.dash._nav_set_scan_state("CVE Lookup", "stale")
        from ui.styles import GREEN, AMBER
        assert self.dash._flyout_dots["Port Scan (TCP)"] == GREEN
        assert self.dash._flyout_dots["CVE Lookup"] == AMBER

    def test_state_can_transition(self):
        from ui.styles import ACCENT, GREEN
        self.dash._nav_set_scan_state("Threat Intel", "running")
        assert self.dash._flyout_dots["Threat Intel"] == ACCENT
        self.dash._nav_set_scan_state("Threat Intel", "fresh")
        assert self.dash._flyout_dots["Threat Intel"] == GREEN
