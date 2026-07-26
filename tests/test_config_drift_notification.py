"""
Phase 2.2 -- config-drift duplicate balloon.

_on_config_drift_detected() (ui/nav/builder.py) was a second, ungated tray
balloon for the SAME event CONFIG_DRIFT already has a real, gated path for
(ui/scan_wiring.py -> AlertEngine.evaluate_config_drift_checks() ->
_surface_alert_in_app() -> router). Deleting the raw show_notification() call
here removes the duplicate; the status-bar/badge update stays as an
always-on in-app surface.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from ui.nav.builder import _NavBuilderMixin  # noqa: E402


class _FakeTray:
    def __init__(self) -> None:
        self.balloons: list = []

    def is_available(self) -> bool:
        return True

    def show_notification(self, *a, **kw) -> None:
        self.balloons.append((a, kw))


class _Stub(_NavBuilderMixin):
    def __init__(self) -> None:
        self._tray_manager = _FakeTray()
        self._baseline_has_drift = False
        self._refresh_section_badges = MagicMock()
        self._set_status = MagicMock()


def test_config_drift_no_longer_shows_a_raw_tray_balloon():
    stub = _Stub()
    stub._on_config_drift_detected("2 devices added")
    assert stub._tray_manager.balloons == []


def test_config_drift_still_updates_status_and_badges():
    stub = _Stub()
    stub._on_config_drift_detected("2 devices added")
    assert stub._baseline_has_drift is True
    stub._refresh_section_badges.assert_called_once()
    stub._set_status.assert_called_once()
