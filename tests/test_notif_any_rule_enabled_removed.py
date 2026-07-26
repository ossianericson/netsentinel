"""
Phase 3.5 -- delete the write-only notif/any_rule_enabled key.

Nothing ever read it (Phase 3.4 now derives the same truth from the real
per-rule keys directly), so it was pure write-only noise in QSettings.
"""
from __future__ import annotations

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtCore import QSettings  # noqa: E402

from ui.pages.notifications_page import NotificationsPage  # noqa: E402


def test_save_never_writes_any_rule_enabled_key():
    qs = QSettings("NetSentinel", "NetSentinel")
    qs.remove("notif/any_rule_enabled")
    qs.sync()

    page = NotificationsPage()
    page._rule_checkboxes["Host Down"].setChecked(True)
    page._save()

    assert not qs.contains("notif/any_rule_enabled")
