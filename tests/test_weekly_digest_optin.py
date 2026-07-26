"""
Phase 2.1 -- the weekly-digest fresh-install balloon.

Two implementations existed: ui/tabs_logger.py's _maybe_send_weekly_digest()
was gated only on a 7-day timestamp defaulting to 0, so it could fire ~4s
into a fresh install. The correct opt-in one, Dashboard._check_weekly_digest,
was gated correctly but dead -- it imported `Alert` from
modules.notification_router, which does not exist (only AlertFired), so the
dispatch always ImportError'd, silently swallowed. Worse, it wrote
notif/weekly_digest_last_ts BEFORE the doomed dispatch, making the failure
self-suppressing for 6 days.

Fix: delete the ungated duplicate; repair the gated one to deliver directly
via the tray manager (matching the morning-briefing pattern) and move the
last_ts write to after a successful send.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from ui.dashboard import Dashboard  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def test_no_digest_scheduler_for_ungated_implementation():
    src = (ROOT / "ui" / "app_settings.py").read_text(encoding="utf-8")
    assert "_maybe_send_weekly_digest" not in src


def test_maybe_send_weekly_digest_method_removed():
    src = (ROOT / "ui" / "tabs_logger.py").read_text(encoding="utf-8")
    assert "_maybe_send_weekly_digest" not in src


class _FakeTray:
    def __init__(self) -> None:
        self.balloons: list = []

    def is_available(self) -> bool:
        return True

    def show_notification(self, title, message, severity="INFO", on_click=None) -> None:
        self.balloons.append((title, message, severity))


class _Stub:
    _check_weekly_digest = Dashboard._check_weekly_digest

    def __init__(self) -> None:
        self._tray_manager = _FakeTray()

    def _nav_rail_go_to(self, label) -> None:
        pass


def test_gated_digest_returns_early_when_disabled():
    from PyQt6.QtCore import QSettings

    qs = QSettings("NetSentinel", "NetSentinel")
    had = qs.contains("notif/weekly_digest_enabled")
    prior = qs.value("notif/weekly_digest_enabled", False, type=bool)
    qs.setValue("notif/weekly_digest_enabled", False)
    try:
        stub = _Stub()
        stub._check_weekly_digest()
        assert stub._tray_manager.balloons == []
    finally:
        if had:
            qs.setValue("notif/weekly_digest_enabled", prior)
        else:
            qs.remove("notif/weekly_digest_enabled")


def test_check_weekly_digest_never_imports_the_nonexistent_alert_name():
    """Regression guard for the dead-on-arrival `from modules.notification_router
    import Alert` -- Alert has never existed there, only AlertFired."""
    import inspect

    src = inspect.getsource(Dashboard._check_weekly_digest)
    assert "import Alert" not in src
    assert "notification_router import Alert" not in src
