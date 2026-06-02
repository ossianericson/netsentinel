"""
Tests for ui/pages/diagnosis_page.py

Verifies:
- scan_requested signal exists (RULE-UX5 / Sprint E2)
- _REMEDIATION dict has no CLI command references (Sprint A3)
- navigate_to and diagnosis_saved signals exist
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── Import guard ──────────────────────────────────────────────────────────────

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)


# ── Module-level import ───────────────────────────────────────────────────────

from ui.pages.diagnosis_page import _REMEDIATION


class TestRemediationNoCLI:
    """A3: No CLI command references in _REMEDIATION steps."""

    _BAD_PHRASES = [
        "Command Prompt",
        "nslookup",
        "ping -t",
        "ping -c",
        "ipconfig",
        "ifconfig",
        "speedtest.net",
        "Network Adapter settings",
        "IPv4 Properties",
    ]

    def test_no_cli_in_dns_resolution_failure(self):
        steps = _REMEDIATION.get("DNS Resolution Failure", [])
        assert steps, "DNS Resolution Failure must have remediation steps"
        combined = " ".join(steps)
        for phrase in self._BAD_PHRASES:
            assert phrase not in combined, (
                f"CLI reference '{phrase}' found in DNS Resolution Failure steps"
            )

    def test_no_cli_in_chronic_connectivity_loss(self):
        steps = _REMEDIATION.get("Chronic Connectivity Loss", [])
        assert steps, "Chronic Connectivity Loss must have remediation steps"
        combined = " ".join(steps)
        for phrase in self._BAD_PHRASES:
            assert phrase not in combined, (
                f"CLI reference '{phrase}' found in Chronic Connectivity Loss steps"
            )

    def test_no_cli_in_router_unreachable(self):
        steps = _REMEDIATION.get("Local Network / Router Unreachable", [])
        assert steps, "Local Network / Router Unreachable must have remediation steps"
        combined = " ".join(steps)
        for phrase in self._BAD_PHRASES:
            assert phrase not in combined, (
                f"CLI reference '{phrase}' found in Router Unreachable steps"
            )

    def test_all_remediation_categories_have_steps(self):
        for category, steps in _REMEDIATION.items():
            assert steps, f"Category '{category}' has empty remediation steps"


class TestDiagnosisPageSignals:
    """E2: scan_requested signal must exist on DiagnosisPage."""

    def test_scan_requested_signal_exists(self, qt_app):
        from ui.pages.diagnosis_page import DiagnosisPage
        page = DiagnosisPage()
        assert hasattr(page, "scan_requested"), "DiagnosisPage missing scan_requested signal"
        try:
            page.deleteLater()
        except RuntimeError:
            pass
        qt_app.processEvents()

    def test_navigate_to_signal_exists(self, qt_app):
        from ui.pages.diagnosis_page import DiagnosisPage
        page = DiagnosisPage()
        assert hasattr(page, "navigate_to")
        try:
            page.deleteLater()
        except RuntimeError:
            pass
        qt_app.processEvents()

    def test_diagnosis_saved_signal_exists(self, qt_app):
        from ui.pages.diagnosis_page import DiagnosisPage
        page = DiagnosisPage()
        assert hasattr(page, "diagnosis_saved")
        try:
            page.deleteLater()
        except RuntimeError:
            pass
        qt_app.processEvents()
