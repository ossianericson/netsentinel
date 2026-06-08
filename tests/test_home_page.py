"""
Tests for ui/pages/home_page.py

Covers:
  • HomePage and StandardWelcomePage import cleanly
  • HomePage(store=None) constructs without error
  • on_grade() updates the grade circle text
  • on_speed_result() updates the speed card
  • on_cycle_done() updates devices and stability cards
  • on_alert() adds rows to the alert strip and caps at 3
  • _preload_from_store() populates cards when store has data
  • _preload_from_store() is a no-op when store is None
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)


# ---------------------------------------------------------------------------
# RULE-WIN4 compliance: keep created pages alive until deleteLater() runs.
# Python GC destroys C++ objects immediately on scope-exit, but HomePage
# starts a 0ms QTimer in __init__.  Storing every page here prevents
# premature destruction; the autouse fixture below drains the list via
# deleteLater() + 3× processEvents() after every test.
# ---------------------------------------------------------------------------
_created_pages: list = []


@pytest.fixture(autouse=True)
def _cleanup_home_pages():
    yield
    app = QApplication.instance()
    # Schedule Qt-side deletion while we still hold Python references
    for page in _created_pages:
        try:
            page.deleteLater()
        except RuntimeError:
            pass  # already destroyed — safe to skip
    # processEvents() runs Qt's deferred deletions while references are still held;
    # the C++ objects are gone after this but the Python wrappers are still alive.
    if app:
        for _ in range(3):
            app.processEvents()
    # Now release Python references — C++ objects already deleted by Qt above
    _created_pages.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_page(store=None):
    from ui.pages.home_page import HomePage
    page = HomePage(store=store)
    _created_pages.append(page)
    return page


def _make_alert(severity: str = "WARNING", message: str = "Test alert"):
    return SimpleNamespace(severity=severity, message=message)


def _make_speed_result(dl: float = 100.0, ul: float = 50.0, ping: float = 10.0):
    return SimpleNamespace(
        download_mbps=dl,
        upload_mbps=ul,
        ping_ms=ping,
        server_name="Test",
        server_city="City",
        server_country="XX",
        backend="test",
    )


# ---------------------------------------------------------------------------
# Import / instantiation
# ---------------------------------------------------------------------------

class TestImport:
    def test_home_page_imports(self):
        from ui.pages.home_page import HomePage  # noqa: F401
        assert HomePage is not None

    def test_standard_welcome_page_imports(self):
        from ui.pages.home_page import StandardWelcomePage  # noqa: F401
        assert StandardWelcomePage is not None


class TestConstruction:
    def test_constructs_with_no_store(self):
        page = _make_page()
        assert page is not None

    def test_constructs_with_mock_store(self):
        store = MagicMock()
        store.query_speed_test_history.return_value = []
        store.get_known_devices.return_value = {}
        page = _make_page(store=store)
        assert page is not None

    def test_alert_count_zero_on_init(self):
        page = _make_page()
        assert page._alert_count == 0


# ---------------------------------------------------------------------------
# on_grade()
# ---------------------------------------------------------------------------

class TestOnGrade:
    def test_grade_a_sets_text(self):
        page = _make_page()
        page.on_grade("A", 95.0)
        assert page._grade_circle.text() == "A"

    def test_grade_b_sets_text(self):
        page = _make_page()
        page.on_grade("B", 82.0)
        assert page._grade_circle.text() == "B"

    def test_grade_f_sets_text(self):
        page = _make_page()
        page.on_grade("F", 30.0)
        assert page._grade_circle.text() == "F"


# ---------------------------------------------------------------------------
# on_speed_result()
# ---------------------------------------------------------------------------

class TestOnSpeedResult:
    def test_speed_card_updated(self):
        page = _make_page()
        result = _make_speed_result(dl=200.0, ul=80.0)
        page.on_speed_result(result)
        assert "200" in page._speed_card._val_lbl.text()

    def test_upload_shown_in_sub(self):
        page = _make_page()
        result = _make_speed_result(dl=100.0, ul=45.0)
        page.on_speed_result(result)
        assert "45" in page._speed_card._sub_lbl.text()


# ---------------------------------------------------------------------------
# on_cycle_done()
# ---------------------------------------------------------------------------

class TestOnCycleDone:
    def test_devices_card_shows_count(self):
        page = _make_page()
        devices = [{"ip": "192.168.1.1", "risk_level": "LOW"}] * 5
        page.on_cycle_done({"devices": devices, "rtts": {}})
        assert page._devices_card._val_lbl.text() == "5"

    def test_stability_card_set_when_rtts_present(self):
        page = _make_page()
        page.on_cycle_done({"devices": [], "rtts": {"1.1.1.1": 20.0}})
        # Value should contain "ms"
        assert "ms" in page._stability_card._val_lbl.text()

    def test_zero_devices_shows_zero_state(self):
        page = _make_page()
        page.on_cycle_done({"devices": [], "rtts": {}})
        assert page._devices_card._val_lbl.text() == "0"

    def test_results_strip_hidden_before_first_scan(self):
        page = _make_page()
        assert page._results_strip.isHidden()

    def test_results_strip_shown_after_first_scan(self):
        page = _make_page()
        devices = [{"ip": "192.168.1.1", "risk_level": "LOW"}]
        page.on_cycle_done({"devices": devices, "rtts": {}})
        assert not page._results_strip.isHidden()

    def test_results_strip_device_count_text(self):
        page = _make_page()
        devices = [{"ip": f"192.168.1.{i}", "risk_level": "LOW"} for i in range(7)]
        page.on_cycle_done({"devices": devices, "rtts": {}})
        assert "7" in page._res_devices_lbl.text()

    def test_results_strip_security_green_when_no_at_risk(self):
        from ui.styles import GREEN
        page = _make_page()
        devices = [{"ip": "192.168.1.1", "risk_level": "LOW"}]
        page.on_cycle_done({"devices": devices, "rtts": {}})
        assert GREEN in page._res_security_dot.styleSheet()

    def test_results_strip_security_red_when_at_risk(self):
        from ui.styles import RED
        page = _make_page()
        devices = [{"ip": "192.168.1.1", "risk_level": "HIGH"}]
        page.on_cycle_done({"devices": devices, "rtts": {}})
        assert RED in page._res_security_dot.styleSheet()

    def test_results_strip_connection_rtt_shown(self):
        page = _make_page()
        devices = [{"ip": "192.168.1.1", "risk_level": "LOW"}]
        page.on_cycle_done({"devices": devices, "rtts": {"8.8.8.8": 35.0}})
        assert "ms" in page._res_conn_lbl.text()


# ---------------------------------------------------------------------------
# on_alert()
# ---------------------------------------------------------------------------

class TestOnAlert:
    def test_first_alert_hides_no_alerts_label(self):
        page = _make_page()
        assert not page._no_alerts_lbl.isHidden()
        page.on_alert(_make_alert())
        assert page._no_alerts_lbl.isHidden()

    def test_alert_count_increments(self):
        page = _make_page()
        page.on_alert(_make_alert())
        assert page._alert_count == 1

    def test_alert_capped_at_three(self):
        page = _make_page()
        for i in range(5):
            page.on_alert(_make_alert(message=f"Alert {i}"))
        assert page._alert_count == 3


# ---------------------------------------------------------------------------
# _preload_from_store()
# ---------------------------------------------------------------------------

class TestPreloadFromStore:
    def test_no_op_when_store_is_none(self):
        """Must not raise when store is None."""
        page = _make_page(store=None)
        page._preload_from_store()  # explicit call — no error expected

    def test_speed_card_populated_from_store(self):
        from modules.metric_store import SpeedTestPoint
        row = SpeedTestPoint(
            ts=1_700_000_000, download_mbps=300.0, upload_mbps=120.0,
            ping_ms=5.0, server_name="Test", server_city="City", server_country="XX",
        )
        store = MagicMock()
        store.query_speed_test_history.return_value = [row]
        store.get_known_devices.return_value = {}
        page = _make_page(store=store)
        page._preload_from_store()
        assert "300" in page._speed_card._val_lbl.text()

    def test_devices_card_populated_from_store(self):
        store = MagicMock()
        store.query_speed_test_history.return_value = []
        # Return 7 mock devices
        store.get_known_devices.return_value = {
            f"aa:bb:cc:dd:ee:{i:02x}": MagicMock() for i in range(7)
        }
        page = _make_page(store=store)
        page._preload_from_store()
        assert page._devices_card._val_lbl.text() == "7"

    def test_store_exception_does_not_propagate(self):
        store = MagicMock()
        store.query_speed_test_history.side_effect = RuntimeError("DB gone")
        store.get_known_devices.side_effect = RuntimeError("DB gone")
        page = _make_page(store=store)
        page._preload_from_store()  # must not raise


# ---------------------------------------------------------------------------
# MiniCard layout — RULE UX5 regression
# ---------------------------------------------------------------------------

class TestMiniCardLayout:
    """Regression: cards must not use setFixedHeight (clips text)."""

    def test_speed_card_has_no_fixed_height(self):
        """setFixedHeight clamps both min and max — causes text overflow."""
        page = _make_page()
        card = page._speed_card
        # A fixed height sets minimumHeight == maximumHeight == that value.
        # After the UX5 fix we use setMinimumHeight, so maximumHeight stays
        # at QWIDGETSIZE_MAX (16777215).
        assert card.maximumHeight() > 500, (
            "_MiniCard must not use setFixedHeight — use setMinimumHeight instead"
        )

    def test_stability_card_has_no_fixed_height(self):
        page = _make_page()
        card = page._stability_card
        assert card.maximumHeight() > 500, (
            "_MiniCard must not use setFixedHeight — use setMinimumHeight instead"
        )

    def test_devices_card_has_no_fixed_height(self):
        page = _make_page()
        card = page._devices_card
        assert card.maximumHeight() > 500, (
            "_MiniCard must not use setFixedHeight — use setMinimumHeight instead"
        )

    def test_speed_card_grows_with_long_value(self):
        """Card minimum height must accommodate a long value label."""
        page = _make_page()
        page.on_speed_result(_make_speed_result(dl=9999.9, ul=9999.9))
        assert page._speed_card.minimumHeight() >= 100
