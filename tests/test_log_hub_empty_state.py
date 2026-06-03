"""
Tests for LogHubPage empty state changes (H3-F2):
- start_logger_requested signal exists
- content stack exists with 2 pages
- EmptyStateCard CTA button is present on page 0
"""
import pytest
import sys
from unittest.mock import MagicMock

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)


@pytest.fixture
def log_hub_page(monkeypatch):
    from PyQt6.QtWidgets import QStackedWidget
    monkeypatch.setattr(
        "ui.pages.log_hub_page.QFileSystemWatcher",
        lambda *a, **kw: MagicMock(),
        raising=False,
    )
    from ui.pages.log_hub_page import LogHubPage
    page = LogHubPage(store=None)
    yield page
    try:
        page.deleteLater()
    except RuntimeError:
        pass
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


def test_start_logger_requested_signal_exists(log_hub_page):
    assert hasattr(log_hub_page, "start_logger_requested"), (
        "LogHubPage must have start_logger_requested signal"
    )


def test_content_stack_exists(log_hub_page):
    assert hasattr(log_hub_page, "_content_stack"), (
        "LogHubPage must have _content_stack QStackedWidget"
    )


def test_content_stack_has_two_pages(log_hub_page):
    stack = log_hub_page._content_stack
    assert stack.count() == 2, f"content_stack must have 2 pages, got {stack.count()}"


def test_empty_state_page_zero_has_cta(log_hub_page):
    """Page 0 should be the EmptyStateCard with a button."""
    from PyQt6.QtWidgets import QPushButton
    stack = log_hub_page._content_stack
    page0 = stack.widget(0)
    # Find any QPushButton in the empty state card
    buttons = page0.findChildren(QPushButton)
    assert buttons, "Empty state (page 0) must have at least one CTA button"
