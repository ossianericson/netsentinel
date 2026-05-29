"""Tests for HubCard error routing and PluginDevicePage banner pip-install detection.

RULE-T1 compliance for hardware_integration_page UI error paths.
Requires QApplication for widget creation.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from PyQt6.QtWidgets import QApplication


# ── health stubs ──────────────────────────────────────────────────────────────


_FRESH_HEALTH = {
    "success": 0, "errors": 0, "consecutive": 0,
    "last_ok": 0.0, "last_err": "", "disabled": False,
}
_DISABLED_HEALTH = {
    **_FRESH_HEALTH, "consecutive": 10, "disabled": True,
}


@pytest.fixture
def make_card():
    """Factory fixture — creates HubCard objects and ensures deleteLater() cleanup."""
    created = []

    def _factory(health: dict, last_result=None):
        with patch("ui.pages.hardware_integration_page._load_health",
                   return_value=dict(health)):
            from ui.pages.hardware_integration_page import HubCard
            card = HubCard(
                "/fake/plugin.py",
                {"name": "Test", "type": "other", "ip": "192.168.1.1"},
                last_result,
            )
            created.append(card)
            return card

    yield _factory

    app = QApplication.instance()
    for card in created:
        try:
            card.deleteLater()
        except RuntimeError:
            pass
    if app:
        app.processEvents()


# isVisible() returns False for widgets whose parent has never been shown.
# Use isHidden() instead: setVisible(True) → isHidden()=False, regardless of parent.
_vis  = lambda w: not w.isHidden()   # widget was shown (setVisible(True) called)
_hid  = lambda w: w.isHidden()       # widget is explicitly hidden


# ── set_error — pip-install detection ────────────────────────────────────────


def test_set_error_pip_shows_install_button(make_card):
    card = make_card(_FRESH_HEALTH)
    card.set_error(
        "Missing library: tplinkrouterc6u\nRun: pip install tplinkrouterc6u"
    )
    assert _vis(card._btn_install)
    assert "tplinkrouterc6u" in card._btn_install.text()


def test_set_error_raw_pip_message_shows_button(make_card):
    """A message containing 'pip install <pkg>' triggers the install button."""
    card = make_card(_FRESH_HEALTH)
    card.set_error("foo is not installed. pip install foo to continue")
    assert _vis(card._btn_install)
    assert "foo" in card._btn_install.text()


def test_set_error_generic_hides_install_button(make_card):
    card = make_card(_FRESH_HEALTH)
    card.set_error("Connection timeout — device not responding")
    assert _hid(card._btn_install)


def test_set_error_auth_failure_hides_install_button(make_card):
    card = make_card(_FRESH_HEALTH)
    card.set_error("Authentication failed — check your password.")
    assert _hid(card._btn_install)


def test_set_error_dot_turns_red(make_card):
    from ui.styles import RED
    card = make_card(_FRESH_HEALTH)
    card.set_error("Something went wrong")
    assert RED in card._dot.styleSheet()


# ── set_error — metrics label updated ────────────────────────────────────────


def test_set_error_updates_metrics_label(make_card):
    card = make_card(_FRESH_HEALTH)
    card.set_error("Authentication failed — check your password.")
    text = card._metrics_lbl.text()
    assert "Error" in text or "failed" in text.lower()


# ── circuit-breaker state ─────────────────────────────────────────────────────


def test_disabled_card_shows_reenable_button(make_card):
    card = make_card(_DISABLED_HEALTH)
    assert _vis(card._btn_reenable)


def test_disabled_card_refresh_is_disabled(make_card):
    card = make_card(_DISABLED_HEALTH)
    assert not card._btn_refresh.isEnabled()


def test_fresh_card_reenable_hidden(make_card):
    card = make_card(_FRESH_HEALTH)
    assert _hid(card._btn_reenable)


def test_fresh_card_refresh_enabled(make_card):
    card = make_card(_FRESH_HEALTH)
    assert card._btn_refresh.isEnabled()


# ── PluginDevicePage banner pip-install detection ─────────────────────────────


@pytest.fixture
def device_page():
    """Create PluginDevicePage and clean it up after the test."""
    from ui.pages.plugin_device_page import PluginDevicePage
    page = PluginDevicePage(
        plugin_path="/fake/plugin.py",
        label="Test",
        hw_type="other",
        hw_ip="192.168.1.1",
    )
    yield page
    app = QApplication.instance()
    try:
        page.deleteLater()
    except RuntimeError:
        pass
    if app:
        app.processEvents()


def test_plugin_device_page_banner_pip_shows_button(device_page):
    from ui.styles import RED
    device_page._show_banner(
        "DEPS: tplinkrouterc6u not installed. Run: pip install tplinkrouterc6u", RED
    )
    assert _vis(device_page._banner_install_btn)
    assert "tplinkrouterc6u" in device_page._banner_install_btn.text()


def test_plugin_device_page_banner_generic_hides_button(device_page):
    from ui.styles import AMBER
    device_page._show_banner("Cannot reach the device — is it online?", AMBER)
    assert _hid(device_page._banner_install_btn)


def test_plugin_device_page_banner_visible_on_call(device_page):
    from ui.styles import RED
    assert _hid(device_page._banner_frame)
    device_page._show_banner("Some error", RED)
    assert _vis(device_page._banner_frame)
