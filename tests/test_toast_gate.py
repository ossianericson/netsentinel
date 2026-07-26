"""
Phase 1 -- the toast gate.

Two long-standing double paths collapse here:
  1. _show_alert_toast() used to be called directly from 17 call sites AND
     reached again via NotificationRouter -> set_toast_callback -> the same
     method, so an enabled ToastChannel produced TWO balloons per alert.
  2. _show_alert_toast() read no setting at all, so notif/toast_enabled
     (default False) never actually gated anything.

Fix: split into _surface_alert_in_app() (always-on status bar + tray badge,
called by every evaluate_*() consumer) and _show_alert_toast() (the desktop
balloon, wired ONCE as NotificationRouter.set_toast_callback in app.py). Each
surface now has exactly one owner and the paths no longer overlap.

RULE-TP4-DASH: never construct a real Dashboard in a pytest-collected test
(its closeEvent() ends in os._exit(0)). Bind the unbound methods onto a
duck-typed stub instead -- same pattern as test_security_scan_dispatch.py.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from ui.dashboard import Dashboard  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _isolate_toast_optin_prompted_key():
    """_surface_alert_in_app() writes notif/toast_optin_prompted as a side
    effect -- save/restore the real value so running this suite never leaves
    the developer's own profile looking like the nudge already fired."""
    from PyQt6.QtCore import QSettings
    qs = QSettings("NetSentinel", "NetSentinel")
    had_key = qs.contains("notif/toast_optin_prompted")
    prior = qs.value("notif/toast_optin_prompted", False, type=bool)
    yield
    if had_key:
        qs.setValue("notif/toast_optin_prompted", prior)
    else:
        qs.remove("notif/toast_optin_prompted")


class _FakeTray:
    def __init__(self) -> None:
        self.balloons: list = []
        self.badge = 0

    def is_available(self) -> bool:
        return True

    def show_notification(self, title, message, severity="INFO", on_click=None) -> None:
        self.balloons.append((title, message, severity))

    def increment_badge(self) -> None:
        self.badge += 1


class _Stub:
    _show_alert_toast = Dashboard._show_alert_toast
    _surface_alert_in_app = Dashboard._surface_alert_in_app
    _maybe_prompt_toast_optin = Dashboard._maybe_prompt_toast_optin

    def __init__(self) -> None:
        self._tray_manager = _FakeTray()
        self._tray_icon = None
        self.status: list = []

    def _set_status(self, msg) -> None:
        self.status.append(msg)

    def _nav_rail_go_to(self, label) -> None:
        pass  # only invoked if the nudge's action button is clicked


def _alert(severity="WARNING", message="test message", is_resolution=False):
    from modules.alert_types import AlertFired
    return AlertFired(
        rule_name="Test Rule", rule_type="RTT_THRESHOLD", host="10.0.0.1",
        message=message, severity=severity, ts=1000, is_resolution=is_resolution,
    )


class TestSurfaceAlertInApp:
    def test_in_app_surface_never_shows_a_balloon(self):
        stub = _Stub()
        stub._surface_alert_in_app(_alert())
        assert stub._tray_manager.balloons == []
        assert len(stub.status) == 1

    def test_updates_badge_for_a_normal_alert(self):
        stub = _Stub()
        stub._surface_alert_in_app(_alert())
        assert stub._tray_manager.badge == 1

    def test_does_not_bump_badge_for_a_resolution(self):
        stub = _Stub()
        stub._surface_alert_in_app(_alert(severity="HEALTHY", is_resolution=True))
        assert stub._tray_manager.badge == 0
        assert stub._tray_manager.balloons == []


class TestRouterGating:
    def test_no_balloon_when_toast_channel_disabled(self):
        from modules.notification_router import NotificationRouter, ToastChannel

        stub = _Stub()
        router = NotificationRouter()
        router.set_channels([ToastChannel(enabled=False)])
        router.set_toast_callback(stub._show_alert_toast)

        stub._surface_alert_in_app(_alert())
        router.dispatch(_alert())

        assert stub._tray_manager.balloons == []
        assert len(stub.status) == 1

    def test_exactly_one_balloon_when_toast_channel_enabled(self):
        """The double-toast regression test -- must be 1, never 2."""
        from modules.notification_router import NotificationRouter, ToastChannel

        stub = _Stub()
        router = NotificationRouter()
        router.set_channels([ToastChannel(enabled=True, min_severity="INFO")])
        router.set_toast_callback(stub._show_alert_toast)

        stub._surface_alert_in_app(_alert())
        router.dispatch(_alert())

        assert len(stub._tray_manager.balloons) == 1


class TestToastCallSiteGuard:
    def test_show_alert_toast_has_exactly_one_call_site(self):
        """Shares its implementation with modules.alert_audit's
        TOAST_CALL_SITES finding via audit_source_tree() -- if this fails, the
        fix is to repoint the extra call site to _surface_alert_in_app()."""
        from modules.alert_audit import audit_source_tree

        findings = audit_source_tree(REPO_ROOT)
        finding = next(f for f in findings if f.code == "TOAST_CALL_SITES")
        assert finding.ok, (
            "_show_alert_toast must have exactly one call site (app.py's "
            "set_toast_callback wiring) plus its own def -- route every "
            "other evaluate_*() consumer through _surface_alert_in_app() "
            f"instead. Detail: {finding.detail}"
        )
