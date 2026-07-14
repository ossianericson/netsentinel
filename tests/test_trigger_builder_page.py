"""
Tests for ui/pages/trigger_builder_page.py -- F-39.

Custom Triggers previously had exactly one caller of evaluate_all() repo-wide
(the manual "Test" button), despite evaluate_all()'s own docstring claiming
"Called by dashboard on each monitoring cycle". This covers:
  - the new self-contained auto-eval QTimer
  - cooldown_s enforcement (declared on TriggerRule but never read before)
  - the message-formatting bug in evaluate_all() that would have raised
    ValueError the first time a real (non-manual-Test) fire ever happened
  - desktop-notification dispatch on fire
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from modules.trigger_expression import TriggerRule  # noqa: E402


@pytest.fixture
def page(tmp_path, monkeypatch):
    monkeypatch.setattr("modules.trigger_expression.get_app_data_dir", lambda: tmp_path)
    from ui.pages.trigger_builder_page import TriggerBuilderPage
    w = TriggerBuilderPage(store=None, parent=None)
    yield w
    try:
        w._auto_eval_timer.stop()
        w.deleteLater()
    except RuntimeError:
        pass  # non-fatal — widget may already be closed
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


def _rule(**kwargs) -> TriggerRule:
    defaults = dict(id="r1", name="Test Rule", expression='rtt["1.1.1.1"] > 10', cooldown_s=300)
    defaults.update(kwargs)
    return TriggerRule(**defaults)


class TestAutoEvalTimer:
    def test_timer_exists_and_running(self, page):
        assert page._auto_eval_timer.isActive()
        assert page._auto_eval_timer.interval() == 60_000

    def test_auto_evaluate_noops_with_no_store(self, page, monkeypatch):
        mock_evaluate_all = MagicMock(return_value=[])
        monkeypatch.setattr(page, "evaluate_all", mock_evaluate_all)
        page._auto_evaluate()
        mock_evaluate_all.assert_not_called()


class TestCooldownEnforcement:
    def test_fires_once_then_respects_cooldown(self, page, monkeypatch):
        page._store = MagicMock()
        page._rules = [_rule(cooldown_s=300)]
        monkeypatch.setattr(
            "ui.pages.trigger_builder_page.evaluate",
            lambda rule, store: (True, 55.0, ""),
        )
        first = page.evaluate_all()
        assert len(first) == 1
        second = page.evaluate_all()
        assert second == []  # still within cooldown

    def test_fires_again_after_cooldown_elapses(self, page, monkeypatch):
        page._store = MagicMock()
        page._rules = [_rule(cooldown_s=10)]
        monkeypatch.setattr(
            "ui.pages.trigger_builder_page.evaluate",
            lambda rule, store: (True, 55.0, ""),
        )
        page._last_fired["r1"] = 0.0  # long ago
        fired = page.evaluate_all()
        assert len(fired) == 1

    def test_disabled_rule_never_fires(self, page, monkeypatch):
        page._store = MagicMock()
        page._rules = [_rule(enabled=False)]
        monkeypatch.setattr(
            "ui.pages.trigger_builder_page.evaluate",
            lambda rule, store: (True, 55.0, ""),
        )
        assert page.evaluate_all() == []


class TestMessageFormatting:
    def test_fired_message_does_not_raise_with_real_value(self, page, monkeypatch):
        """Reproduces the pre-fix bug: f'{lhs:.2f if not math.isnan(lhs) else
        \"no data\"}' is an invalid format spec and raised ValueError on every
        real (non-NaN) fire -- never observed before because evaluate_all()
        had no automatic caller."""
        page._store = MagicMock()
        page._rules = [_rule()]
        monkeypatch.setattr(
            "ui.pages.trigger_builder_page.evaluate",
            lambda rule, store: (True, 55.4321, ""),
        )
        fired = page.evaluate_all()
        assert len(fired) == 1
        assert "55.43" in fired[0].message

    def test_fired_message_handles_nan(self, page, monkeypatch):
        import math
        page._store = MagicMock()
        page._rules = [_rule()]
        monkeypatch.setattr(
            "ui.pages.trigger_builder_page.evaluate",
            lambda rule, store: (True, math.nan, ""),
        )
        fired = page.evaluate_all()
        assert len(fired) == 1
        assert "no data" in fired[0].message


class TestDispatch:
    def test_fired_trigger_shows_toast(self, page, monkeypatch):
        shown = []
        monkeypatch.setattr(
            "ui.widgets.toast.ToastManager.show",
            staticmethod(lambda msg, kind="info", **kw: shown.append((msg, kind))),
        )
        page._store = MagicMock()
        page._rules = [_rule(severity="CRITICAL")]
        monkeypatch.setattr(
            "ui.pages.trigger_builder_page.evaluate",
            lambda rule, store: (True, 55.0, ""),
        )
        page._auto_evaluate()
        assert len(shown) == 1
        assert shown[0][1] == "error"
