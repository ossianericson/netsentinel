"""
Regression test for critical-UX Phase 1.1/1.4: the two "View all alerts"
buttons on the Home page (Action Needed card + Recent Alerts section) both
emit navigate_to.emit("Notifications"), routed through the shared
_on_overview_navigate() slot (ui/nav/builder.py) -- also used by
overview_page.py and diagnosis_page.py, neither of which ever emits that
string. Before the fix this landed on Notifications tab 0 ("Configure")
via a bare _nav_rail_go_to call; it must instead land on tab 1 ("History")
with the unacked-only filter checked, via the same two-step sequence the
command-palette "View Alert History" action already uses.

RULE-T3: must fail before the fix (a bare _nav_rail_go_to("Notifications")
call, no switch_to_history_tab).
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

try:
    from ui.nav.builder import _NavBuilderMixin
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)


class _Stub(_NavBuilderMixin):
    def __init__(self):
        self.nav_calls: list = []
        self._notifications_page = MagicMock()

    def _nav_rail_go_to(self, label, _push_history=False):
        self.nav_calls.append(label)


def test_notifications_routes_through_two_step_history_sequence():
    stub = _Stub()
    stub._on_overview_navigate("Notifications")

    assert stub.nav_calls == ["Notifications"]
    stub._notifications_page.switch_to_history_tab.assert_called_once_with(unacked_only=True)


def test_other_labels_still_use_plain_nav_rail_go_to():
    """Regression guard: the special-case must be scoped to exactly
    "Notifications" -- every other label keeps the original one-step routing."""
    stub = _Stub()
    stub._on_overview_navigate("Devices")

    assert stub.nav_calls == ["Devices"]
    stub._notifications_page.switch_to_history_tab.assert_not_called()


def test_diagnose_network_still_routes_to_whats_wrong():
    """Pre-existing special case must be untouched by the new one."""
    from ui.nav.labels import NavLabel as L

    stub = _Stub()
    stub._on_overview_navigate("Diagnose Network")

    assert stub.nav_calls == [L.WHATS_WRONG]
    stub._notifications_page.switch_to_history_tab.assert_not_called()
