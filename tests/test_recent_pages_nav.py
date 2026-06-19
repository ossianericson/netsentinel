"""Tests for the 'Recently visited' rail shortcut (Sprint 7, S7-4).

Uses a lightweight harness that mixes in _NavBuilderMixin with the minimum
rail-layout scaffolding (search button, Ctrl+K chip, stretch, Settings button)
instead of constructing the full Dashboard, which has heavy startup dependencies.
"""
from unittest.mock import MagicMock

import pytest

try:
    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QApplication, QLabel, QPushButton, QVBoxLayout, QWidget
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

pytestmark = pytest.mark.skipif(not _HAS_QT, reason="PyQt6 not available")


def _fresh_settings():
    qs = QSettings("NetSentinel", "NetSentinel")
    qs.remove("nav/recent_pages")
    qs.remove("discover/visited_pages")
    qs.remove("nav/pin_hint_shown")
    return qs


def _cleanup(widget):
    app = QApplication.instance()
    try:
        widget.deleteLater()
    except RuntimeError:
        pass  # already destroyed — safe to skip
    if app:
        for _ in range(3):
            app.processEvents()


def _rail_widget_names(rail_lay) -> list:
    names = []
    for i in range(rail_lay.count()):
        item = rail_lay.itemAt(i)
        names.append(item.widget().objectName() if item.widget() else "SPACER")
    return names


@pytest.fixture
def harness():
    from ui.nav.builder import _NavBuilderMixin

    class _Harness(QWidget, _NavBuilderMixin):
        def __init__(self):
            super().__init__()
            self._nav_rail_lay = QVBoxLayout()
            search = QPushButton()
            search.setObjectName("search")
            chip = QLabel("Ctrl+K")
            chip.setObjectName("chip")
            self._nav_rail_lay.addWidget(search)
            self._nav_rail_lay.addWidget(chip)
            self._nav_rail_lay.addStretch()
            self._rail_settings_btn = QPushButton()
            self._rail_settings_btn.setObjectName("settings")
            self._nav_rail_lay.addWidget(self._rail_settings_btn)

            self._nav_rail_buttons = {}
            self._nav_sections = []
            self._nav_pinned_labels = []
            self._nav_label_to_widget = {}
            self._nav_page_to_section = {}
            self._nav_current_page_label = ""
            self._nav_open_section = ""
            self._nav_flyout = MagicMock()
            self._nav_flyout.maximumWidth.return_value = 0
            self._nav_flyout.is_pinned = False
            self.status_calls = []

            self._nav_finalize_rail()

        def _set_status(self, text):
            self.status_calls.append(text)

    QApplication.instance()
    h = _Harness()
    yield h
    _cleanup(h)


class TestRecentRailPlacement:
    def setup_method(self):    _fresh_settings()
    def teardown_method(self): _fresh_settings()

    def test_recent_button_created_on_finalize(self, harness):
        assert hasattr(harness, "_recent_rail_btn")

    def test_recent_button_sits_between_search_and_spacer(self, harness):
        names = _rail_widget_names(harness._nav_rail_lay)
        recent_idx = next(
            i for i in range(harness._nav_rail_lay.count())
            if harness._nav_rail_lay.itemAt(i).widget() is harness._recent_rail_btn
        )
        assert names.index("search") < recent_idx < names.index("SPACER")

    def test_sections_inserted_between_recent_and_spacer_not_after_settings(self, harness):
        harness._nav_sections = [{"name": "Getting Started", "icon": "grid", "entries": []}]
        harness._nav_finalize_rail()
        names = _rail_widget_names(harness._nav_rail_lay)
        recent_idx = next(
            i for i in range(harness._nav_rail_lay.count())
            if harness._nav_rail_lay.itemAt(i).widget() is harness._recent_rail_btn
        )
        spacer_idx = names.index("SPACER")
        settings_idx = names.index("settings")
        section_idx = next(
            i for i in range(harness._nav_rail_lay.count())
            if harness._nav_rail_lay.itemAt(i).widget() is harness._nav_rail_buttons["Getting Started"]
        )
        # search < recent < section(s) < SPACER < settings — no gap, nothing after Settings
        assert recent_idx < section_idx < spacer_idx < settings_idx

    def test_no_duplicate_buttons_after_repeated_finalize(self, harness):
        harness._nav_sections = [{"name": "Getting Started", "icon": "grid", "entries": []}]
        harness._nav_finalize_rail()
        harness._nav_finalize_rail()
        harness._nav_finalize_rail()
        names = _rail_widget_names(harness._nav_rail_lay)
        assert names.count("SPACER") == 1
        assert names.count("search") == 1
        assert names.count("settings") == 1
        # search, recent, 1 section button, SPACER, settings — no leftover duplicates
        # from earlier finalize() calls
        assert harness._nav_rail_lay.count() == 5


class TestTrackPageVisitMRU:
    def setup_method(self):    _fresh_settings()
    def teardown_method(self): _fresh_settings()

    def test_get_recent_pages_empty_initially(self, harness):
        assert harness._get_recent_pages() == []

    def test_track_page_visit_updates_recent_pages(self, harness):
        harness._nav_label_to_widget = {"Home": QWidget()}
        harness._track_page_visit("Home")
        assert harness._get_recent_pages() == ["Home"]

    def test_mru_order_most_recent_first(self, harness):
        harness._nav_label_to_widget = {l: QWidget() for l in ["A", "B", "C", "D"]}
        for label in ["A", "B", "C", "D"]:
            harness._track_page_visit(label)
        assert harness._get_recent_pages() == ["D", "C", "B"]

    def test_revisit_moves_label_to_front_without_duplicate(self, harness):
        harness._nav_label_to_widget = {l: QWidget() for l in ["A", "B", "C"]}
        for label in ["A", "B", "C"]:
            harness._track_page_visit(label)
        harness._track_page_visit("A")
        assert harness._get_recent_pages() == ["A", "C", "B"]

    def test_get_recent_pages_filters_unknown_labels(self, harness):
        harness._nav_label_to_widget = {"Home": QWidget()}
        harness._track_page_visit("Home")
        harness._track_page_visit("StalePageNoLongerRegistered")
        assert harness._get_recent_pages() == ["Home"]


class TestToggleRecentFlyout:
    def setup_method(self):    _fresh_settings()
    def teardown_method(self): _fresh_settings()

    def test_no_history_shows_status_hint_and_does_not_open(self, harness):
        harness._toggle_recent_pages_flyout()
        harness._nav_flyout.open.assert_not_called()
        assert harness.status_calls == ["No recently visited pages yet"]

    def test_with_history_opens_flyout_with_recent_title(self, harness):
        harness._nav_label_to_widget = {"Home": QWidget()}
        harness._track_page_visit("Home")
        harness._toggle_recent_pages_flyout()
        harness._nav_flyout.load_section.assert_called_once()
        _, kwargs = harness._nav_flyout.load_section.call_args
        assert kwargs["title"] == "Recent"
        assert kwargs["entries"] == [("Home", False, False, "")]
        harness._nav_flyout.open.assert_called_once()

    def test_opening_checks_recent_button_and_unchecks_sections(self, harness):
        harness._nav_label_to_widget = {"Home": QWidget()}
        harness._track_page_visit("Home")
        sec_btn = QPushButton()
        sec_btn.setCheckable(True)
        sec_btn.setChecked(True)
        harness._nav_rail_buttons["Getting Started"] = sec_btn
        harness._toggle_recent_pages_flyout()
        assert harness._recent_rail_btn.isChecked() is True
        assert sec_btn.isChecked() is False

    def test_second_click_closes_when_open_and_not_pinned(self, harness):
        harness._nav_label_to_widget = {"Home": QWidget()}
        harness._track_page_visit("Home")
        harness._nav_flyout.maximumWidth.return_value = 0
        harness._toggle_recent_pages_flyout()
        harness._nav_flyout.maximumWidth.return_value = 280
        harness._toggle_recent_pages_flyout()
        harness._nav_flyout.close_panel.assert_called_once()
        assert harness._recent_rail_btn.isChecked() is False

    def test_does_not_close_when_flyout_is_pinned(self, harness):
        harness._nav_label_to_widget = {"Home": QWidget()}
        harness._track_page_visit("Home")
        harness._nav_flyout.maximumWidth.return_value = 0
        harness._toggle_recent_pages_flyout()
        harness._nav_flyout.maximumWidth.return_value = 280
        harness._nav_flyout.is_pinned = True
        harness._toggle_recent_pages_flyout()
        harness._nav_flyout.close_panel.assert_not_called()
