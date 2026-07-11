"""
Tests for the themed_ss() live-QSS registry in ui/styles.py (Instant Theme
Switching, Phase 2).

Covers:
  • str template applies immediately and re-applies on apply_theme()
  • callable template applies immediately and re-applies on apply_theme()
  • re-registering a widget replaces its template
  • a widget deleted (deleteLater + processEvents) before the next apply_theme
    is evicted from the registry instead of raising
  • an unknown token in a template raises KeyError naming the token
  • RULE-T7: a real (non-mock) widget's styleSheet() reflects the active
    theme's value after apply_theme(), in both switch directions
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication, QLabel, QPushButton  # noqa: E402

import ui.styles as _styles  # noqa: E402


def _drain(widget) -> None:
    """RULE-WIN4: deleteLater() + drain the event loop so the C++ object is
    actually destroyed before the test ends."""
    try:
        widget.deleteLater()
    except RuntimeError:
        pass  # already destroyed — safe to skip
    app = QApplication.instance()
    if app:
        try:
            from PyQt6.QtCore import QCoreApplication, QEvent
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
        except Exception:
            pass  # best-effort — processEvents() below still runs
        for _ in range(3):
            app.processEvents()


class TestThemedSS:
    def teardown_method(self):
        # Always leave the module's active theme exactly as pytest found it,
        # even if a test raises before its own restore runs.
        _styles.apply_theme(_styles._ACTIVE_THEME)

    def test_str_template_applies_immediately(self):
        w = QLabel()
        try:
            _styles.themed_ss(w, "background:{ACCENT};")
            assert _styles.ACCENT in w.styleSheet()
        finally:
            _drain(w)

    def test_str_template_reapplies_on_theme_switch(self):
        original = _styles._ACTIVE_THEME
        target = "Midnight Pro" if original != "Midnight Pro" else "Arctic Clean"
        w = QLabel()
        try:
            _styles.themed_ss(w, "background:{ACCENT};")
            with patch("ui.styles.get_accent_override", return_value=None):
                _styles.apply_theme(target)
            assert _styles.THEMES[target]["ACCENT"] in w.styleSheet()
        finally:
            _drain(w)
            _styles.apply_theme(original)

    def test_callable_template_applies_and_reapplies(self):
        original = _styles._ACTIVE_THEME
        target = "Midnight Pro" if original != "Midnight Pro" else "Arctic Clean"
        w = QLabel()

        def _tpl():
            return f"color:{_styles.ACCENT};"

        try:
            _styles.themed_ss(w, _tpl)
            assert _styles.ACCENT in w.styleSheet()
            with patch("ui.styles.get_accent_override", return_value=None):
                _styles.apply_theme(target)
            assert _styles.THEMES[target]["ACCENT"] in w.styleSheet()
        finally:
            _drain(w)
            _styles.apply_theme(original)

    def test_reregistering_widget_replaces_template(self):
        w = QLabel()
        try:
            _styles.themed_ss(w, "background:{ACCENT};")
            assert _styles._THEMED_REGISTRY[w] == "background:{ACCENT};"

            _styles.themed_ss(w, "background:{RED};")
            assert _styles._THEMED_REGISTRY[w] == "background:{RED};"
            assert _styles.RED in w.styleSheet()
        finally:
            _drain(w)

    def test_deleted_widget_is_evicted_not_raised(self):
        original = _styles._ACTIVE_THEME
        target = "Midnight Pro" if original != "Midnight Pro" else "Arctic Clean"
        w = QLabel()
        _styles.themed_ss(w, "background:{ACCENT};")
        assert w in _styles._THEMED_REGISTRY
        before = len(_styles._THEMED_REGISTRY)

        _drain(w)  # C++ object destroyed; the Python wrapper (and dict entry) survives

        try:
            _styles.apply_theme(target)  # must not raise
        finally:
            _styles.apply_theme(original)

        assert len(_styles._THEMED_REGISTRY) < before
        assert w not in _styles._THEMED_REGISTRY

    def test_unknown_token_raises_keyerror_naming_token(self):
        w = QLabel()
        try:
            with pytest.raises(KeyError, match="NOT_A_REAL_TOKEN"):
                _styles.themed_ss(w, "background:{NOT_A_REAL_TOKEN};")
            # Bad template raises before registration — the widget's
            # stylesheet and the registry are both left untouched.
            assert w not in _styles._THEMED_REGISTRY
        finally:
            _drain(w)

    def test_widget_stylesheet_reflects_theme_both_directions(self):
        """RULE-T7 behavioral test: a real (non-mock) widget's rendered
        stylesheet tracks the live theme across a switch and a switch-back."""
        original = _styles._ACTIVE_THEME
        w = QPushButton()
        try:
            _styles.themed_ss(w, "QPushButton{{background:{BG_CARD};color:{TEXT_PRIMARY};}}")
            with patch("ui.styles.get_accent_override", return_value=None):
                _styles.apply_theme("Arctic Clean")
                assert _styles.THEMES["Arctic Clean"]["BG_CARD"] in w.styleSheet()

                _styles.apply_theme("Midnight Pro")
                assert _styles.THEMES["Midnight Pro"]["BG_CARD"] in w.styleSheet()
                assert _styles.THEMES["Arctic Clean"]["BG_CARD"] not in w.styleSheet()

                _styles.apply_theme("Arctic Clean")
                assert _styles.THEMES["Arctic Clean"]["BG_CARD"] in w.styleSheet()
        finally:
            _drain(w)
            _styles.apply_theme(original)
