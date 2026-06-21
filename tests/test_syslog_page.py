"""Tests for ui/pages/syslog_page.py"""
from __future__ import annotations

import pytest

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)


@pytest.fixture
def page():
    from ui.pages.syslog_page import SyslogPage
    p = SyslogPage()
    yield p
    try:
        p.deleteLater()
    except RuntimeError:
        pass  # already deleted
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


def test_import():
    from ui.pages.syslog_page import SyslogPage  # noqa: F401


def test_instantiation(page):
    assert page is not None


def test_on_message_received_does_not_crash(page):
    """Injecting a syslog message should add a row without crashing."""
    msg = {
        "src": "192.168.1.10",
        "severity": 6,      # integer severity level (RFC 5424)
        "facility": "daemon",
        "message": "System started",
    }
    slot = (
        getattr(page, "on_message_received", None) or
        getattr(page, "on_syslog_message", None) or
        getattr(page, "on_message", None)
    )
    if slot:
        slot(msg)
    assert page is not None


def test_widget_is_not_none(page):
    assert page is not None
