"""Tests for ui/pages/automation_page.py's RuleEditorDialog (F-37)."""
from __future__ import annotations

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from modules.automation_hooks import AutomationRule  # noqa: E402


def _cleanup(w):
    app = QApplication.instance()
    try:
        w.deleteLater()
    except RuntimeError:
        pass  # non-fatal — already deleted
    if app:
        for _ in range(3):
            app.processEvents()


def test_webhook_field_prefilled_from_existing_rule():
    from ui.pages.automation_page import RuleEditorDialog
    rule = AutomationRule(name="Existing", webhook_url="https://hooks.slack.com/services/x")
    dlg = RuleEditorDialog(rule=rule)
    assert dlg._webhook_url.text() == "https://hooks.slack.com/services/x"
    _cleanup(dlg)


def test_commit_saves_webhook_url_into_rule():
    from ui.pages.automation_page import RuleEditorDialog
    dlg = RuleEditorDialog(rule=None)
    dlg._name.setText("New Rule")
    dlg._webhook_url.setText("https://discord.com/api/webhooks/1/abc")
    dlg._commit()
    assert dlg.get_rule().webhook_url == "https://discord.com/api/webhooks/1/abc"
    _cleanup(dlg)
