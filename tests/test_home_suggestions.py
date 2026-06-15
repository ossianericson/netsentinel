"""
Tests for Sprint H4: suggestion persistence, snooze expiry, fallback entry,
and live challenge banner wiring.
"""
from __future__ import annotations

import datetime

import pytest

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)


# ---------------------------------------------------------------------------
# Pure-logic helpers (no Qt widgets needed)
# ---------------------------------------------------------------------------

class TestSuggestionSuppression:
    """Unit tests for _suggestion_is_suppressed() pure logic."""

    def _mixin(self):
        from ui.pages.home_suggestions import _HomeSuggestionsMixin
        return _HomeSuggestionsMixin

    def _qs_with(self, prefix: str, key: str, ts: datetime.datetime):
        """Build a mock QSettings-like object."""
        from unittest.mock import MagicMock
        qs = MagicMock()
        mapping = {f"{prefix}{key}": ts.isoformat()}
        qs.value = lambda k, default="": mapping.get(k, default)
        return qs

    def test_not_suppressed_when_no_key(self):
        from unittest.mock import MagicMock
        mixin = self._mixin()
        qs = MagicMock()
        qs.value = lambda k, default="": ""
        now = datetime.datetime.now()
        assert not mixin._suggestion_is_suppressed(qs, now, "test_key")

    def test_suppressed_when_acted_within_7_days(self):
        mixin = self._mixin()
        now = datetime.datetime.now()
        ts_3_days_ago = now - datetime.timedelta(days=3)
        qs = self._qs_with("suggestion_acted/", "test_key", ts_3_days_ago)
        assert mixin._suggestion_is_suppressed(qs, now, "test_key")

    def test_not_suppressed_when_acted_over_7_days_ago(self):
        mixin = self._mixin()
        now = datetime.datetime.now()
        ts_8_days_ago = now - datetime.timedelta(days=8)
        qs = self._qs_with("suggestion_acted/", "test_key", ts_8_days_ago)
        assert not mixin._suggestion_is_suppressed(qs, now, "test_key")

    def test_suppressed_when_snoozed_within_7_days(self):
        mixin = self._mixin()
        now = datetime.datetime.now()
        ts_1_day_ago = now - datetime.timedelta(days=1)
        qs = self._qs_with("suggestion_snoozed/", "test_key", ts_1_day_ago)
        assert mixin._suggestion_is_suppressed(qs, now, "test_key")

    def test_not_suppressed_when_snoozed_over_7_days_ago(self):
        mixin = self._mixin()
        now = datetime.datetime.now()
        ts_10_days_ago = now - datetime.timedelta(days=10)
        qs = self._qs_with("suggestion_snoozed/", "test_key", ts_10_days_ago)
        assert not mixin._suggestion_is_suppressed(qs, now, "test_key")

    def test_suggestions_without_action_key_never_suppressed(self):
        from unittest.mock import MagicMock
        mixin = self._mixin()
        qs = MagicMock()
        qs.value = lambda k, default="": "2020-01-01"  # old date for any key
        now = datetime.datetime.now()
        # action_key=None means no suppression logic applies
        assert not mixin._suggestion_is_suppressed(qs, now, "")


# ---------------------------------------------------------------------------
# Widget-level tests
# ---------------------------------------------------------------------------

@pytest.fixture
def home_page(qt_app, monkeypatch):
    from unittest.mock import patch
    # Patch QSettings to avoid real registry writes during tests
    monkeypatch.setattr(
        "ui.pages.home_suggestions.QSettings",
        lambda *a, **kw: _FakeQSettings(),
    )
    monkeypatch.setattr(
        "ui.pages.home_data_mixin.QSettings",
        lambda *a, **kw: _FakeQSettings(),
    )
    with patch("ui.pages.home_page.QSettings", lambda *a, **kw: _FakeQSettings()):
        from ui.pages.home_page import HomePage
        page = HomePage(store=None)
    yield page
    try:
        page.deleteLater()
    except RuntimeError:
        pass  # already destroyed — safe to skip
    app = QApplication.instance()
    if app:
        try:
            from PyQt6.QtCore import QCoreApplication, QEvent
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
        except Exception:
            pass  # non-fatal — best-effort cleanup
        for _ in range(3):
            app.processEvents()


class _FakeQSettings:
    """Lightweight in-memory QSettings substitute for tests."""
    _store: dict = {}

    def __init__(self, *a, **kw):
        self._data: dict = {}

    def value(self, key, default=None, type=None):
        v = self._data.get(key, default)
        if type is bool and isinstance(v, str):
            return v.lower() in ("true", "1", "yes")
        return v

    def setValue(self, key, value):
        self._data[key] = value


class TestSuggestionsWidgetFiltering:
    """Verify set_suggestions hides suggestions acted on within 7 days."""

    def test_set_suggestions_shows_non_suppressed(self, home_page):
        suggestions = [
            {"action_key": "new_key", "text": "Do something", "action_label": "Go →", "target": "Dashboard", "priority": "low"},
        ]
        home_page.set_suggestions(suggestions)
        # Use isHidden() — isVisible() requires the full parent chain to be shown
        assert not home_page._suggestions_card.isHidden()

    def test_set_suggestions_empty_hides_card(self, home_page):
        home_page.set_suggestions([])
        assert home_page._suggestions_card.isHidden()

    def test_set_suggestions_without_action_key_always_shows(self, home_page):
        suggestions = [
            {"text": "No key suggestion", "action_label": "Go →", "target": "Dashboard", "priority": "low"},
        ]
        home_page.set_suggestions(suggestions)
        assert not home_page._suggestions_card.isHidden()


class TestLiveChallengeBanner:
    """Verify the live challenge banner appears and is dismissible."""

    def test_banner_hidden_by_default(self, home_page):
        assert home_page._live_challenge_banner.isHidden()

    def test_on_live_challenge_shows_banner(self, home_page):
        from unittest.mock import MagicMock
        scenario = MagicMock()
        scenario.title = "Connectivity Drop"
        home_page.on_live_challenge(scenario)
        assert not home_page._live_challenge_banner.isHidden()

    def test_on_live_challenge_sets_text(self, home_page):
        from unittest.mock import MagicMock
        scenario = MagicMock()
        scenario.title = "Gateway Unreachable"
        home_page.on_live_challenge(scenario)
        assert "gateway unreachable" in home_page._lc_text.text().lower()

    def test_on_live_challenge_none_scenario(self, home_page):
        # Should not raise even with None scenario
        home_page.on_live_challenge(None)
        assert not home_page._live_challenge_banner.isHidden()


class TestFallbackSuggestion:
    """Verify _compute_suggestions always provides ≥1 suggestion after scan."""

    def test_fallback_suggestion_added_when_empty(self, monkeypatch):
        from unittest.mock import MagicMock
        monkeypatch.setattr(
            "ui.tabs_logger.QSettings",
            lambda *a, **kw: _FakeQSettings(),
            raising=False,
        )
        # Import just the compute logic (no full Dashboard)
        from ui.tabs_logger import _LoggerTabMixin

        class _Stub(_LoggerTabMixin):
            _home_page = MagicMock()
            _m1_result = None
            _last_benchmark_result = None
            _store = None
            _logger_worker = None

        stub = _Stub()
        stub._compute_suggestions()
        calls = stub._home_page.set_suggestions.call_args_list
        assert calls, "set_suggestions should have been called"
        suggestions = calls[0][0][0]
        assert len(suggestions) >= 1, "Fallback suggestion must appear when all conditions are green"
        keys = [s.get("action_key") for s in suggestions]
        assert "start_logger_fallback" in keys or "start_logger" in keys
