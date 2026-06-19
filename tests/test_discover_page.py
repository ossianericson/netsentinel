"""Tests for ui.pages.discover_page — Sprint 9, S9-4 'Recommended for you' + Used badge."""
import json

import pytest

try:
    from PyQt6.QtWidgets import QApplication, QLabel
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

pytestmark = pytest.mark.skipif(not _HAS_QT, reason="PyQt6 not available")


def _cleanup(*widgets):
    app = QApplication.instance()
    for w in widgets:
        try:
            w.deleteLater()
        except RuntimeError:
            pass  # already destroyed — safe to skip
    if app:
        for _ in range(3):
            app.processEvents()


class _FakeQSettings:
    _shared: dict = {}

    def __init__(self, *a, **kw):
        pass

    def value(self, key, default=None, type=None):
        return self._shared.get(key, default)

    def setValue(self, key, value):
        self._shared[key] = value


@pytest.fixture
def fresh_settings(monkeypatch):
    _FakeQSettings._shared = {}
    monkeypatch.setattr("ui.pages.discover_page.QSettings", _FakeQSettings)
    yield _FakeQSettings


def _make_page(fresh_settings):
    from ui.pages.discover_page import FeatureGuidePage
    page = FeatureGuidePage()
    return page


class TestRecommendedForYou:
    def test_recommended_section_shown_when_nothing_visited(self, fresh_settings):
        page = _make_page(fresh_settings)
        assert page._recommended_features(), "should recommend at least one page"
        _cleanup(page)

    def test_recommended_features_are_unvisited(self, fresh_settings):
        from ui.pages.discover_data import _RECOMMENDED_PAGES
        fresh_settings._shared["discover/visited_pages"] = json.dumps(
            [_RECOMMENDED_PAGES[0]]
        )
        page = _make_page(fresh_settings)
        page._load_visited_pages()
        recommended_pages = [f["page"] for f in page._recommended_features()]
        assert _RECOMMENDED_PAGES[0] not in recommended_pages
        _cleanup(page)

    def test_no_recommendations_when_all_visited(self, fresh_settings):
        from ui.pages.discover_data import _RECOMMENDED_PAGES
        fresh_settings._shared["discover/visited_pages"] = json.dumps(_RECOMMENDED_PAGES)
        page = _make_page(fresh_settings)
        page._load_visited_pages()
        assert page._recommended_features() == []
        _cleanup(page)


class TestUsedBadge:
    def test_used_badge_appears_for_visited_page(self, fresh_settings):
        fresh_settings._shared["discover/visited_pages"] = json.dumps(["Devices"])
        page = _make_page(fresh_settings)
        page._load_visited_pages()
        from ui.pages.discover_data import _FEATURES
        feat = next(f for f in _FEATURES if f.get("page") == "Devices")
        card = page._make_card(feat)
        labels = [c for c in card.findChildren(QLabel) if c.text() == "✓ Used"]
        assert len(labels) == 1
        _cleanup(page)

    def test_no_used_badge_for_unvisited_page(self, fresh_settings):
        page = _make_page(fresh_settings)
        page._load_visited_pages()
        from ui.pages.discover_data import _FEATURES
        feat = next(f for f in _FEATURES if f.get("page") == "Devices")
        card = page._make_card(feat)
        labels = [c for c in card.findChildren(QLabel) if c.text() == "✓ Used"]
        assert len(labels) == 0
        _cleanup(page)


class TestSearchHidesRecommendations:
    def test_search_query_renders_without_recommended_header(self, fresh_settings):
        page = _make_page(fresh_settings)
        page._search.setText("devices")
        # deleteLater() only schedules destruction — force it through so stale
        # widgets removed from the layout are gone before we inspect children.
        app = QApplication.instance()
        from PyQt6.QtCore import QCoreApplication, QEvent
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
        for _ in range(3):
            app.processEvents()
        labels = [c.text() for c in page._body.findChildren(QLabel)]
        assert "RECOMMENDED FOR YOU" not in labels
        _cleanup(page)
