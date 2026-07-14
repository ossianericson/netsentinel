"""
Regression tests for four doc-only claims-audit fixes to ui/help.py's live
_PAGE_HELP copy (F-33, F-34, F-86, F-87) -- each corrects a sentence that
described behaviour the app doesn't actually have.
"""
from __future__ import annotations

from ui.help import _PAGE_HELP


def _hidden_text(page: str) -> str:
    return " ".join(_PAGE_HELP[page].get("hidden", []))


class TestF33BroadcastStormLevelNames:
    """storm_analyser.py's StormResult.storm_level is CLEAN/WARNING/STORM
    (UNKNOWN before any scan runs) -- never SAFE or CRITICAL."""

    def test_help_no_longer_claims_safe_or_critical(self):
        text = _hidden_text("Broadcast Storm")
        assert "SAFE" not in text
        assert "CRITICAL" not in text

    def test_help_names_the_real_levels(self):
        text = _hidden_text("Broadcast Storm")
        assert "CLEAN" in text
        assert "WARNING" in text
        assert "STORM" in text


class TestF34IoTBaselineDuration:
    """ui/tabs_analysis.py's learn-duration spinbox range is (30, 600) seconds
    (10 minutes max, default 60s) -- a 24-hour baseline is not achievable."""

    def test_help_no_longer_claims_24_hours(self):
        text = _hidden_text("IoT Behaviour")
        assert "24 hour" not in text and "24-hour" not in text

    def test_help_states_the_real_range(self):
        text = _hidden_text("IoT Behaviour")
        assert "10 minutes" in text or "600" in text


class TestF86ScheduledScansMechanism:
    """workers/scan_worker.py's SchedulerWorker is an in-process QThread;
    svc.py's real Windows service only covers the Network Logger."""

    def test_help_no_longer_claims_a_background_service(self):
        text = _hidden_text("Scheduled Scans")
        assert "background service" not in text

    def test_help_clarifies_app_must_stay_running(self):
        text = _hidden_text("Scheduled Scans")
        assert "stay running" in text or "not a separate Windows service" in text


class TestF87MqttBrokerConfigLocation:
    """ui/pages/mqtt_page.py has its own Broker Configuration card;
    ui/pages/settings_cards.py has zero MQTT fields."""

    def test_help_no_longer_points_to_settings(self):
        text = _hidden_text("MQTT / Home Assistant")
        assert "in Settings" not in text

    def test_help_points_to_the_mqtt_page_itself(self):
        text = _hidden_text("MQTT / Home Assistant")
        assert "this page" in text or "Broker Configuration card" in text
