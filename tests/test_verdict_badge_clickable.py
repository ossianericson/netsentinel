"""
Regression test for a live-discovered gap alongside critical-UX Phase 1: the
header's "network status" badge (ui/header.py::_verdict_badge) shows text
like "Action required" (risk_to_label() for HIGH/CRITICAL) but was a plain
QLabel with no click handler -- and the detailed VerdictPanel that would
explain what's wrong is built but never shown in the live UI
(dashboard.py: "_verdict_area ... kept alive for exports; not shown"). A user
had no way to discover what the required action actually was.

Fix: _verdict_badge becomes a _ClickLabel (the same widget class the footer
pulse segments already use) routed to the "What's Wrong?" diagnosis page --
the same destination the footer's own connection-status pulse uses for an
analogous "something's off" signal.

RULE-T3: must fail before the fix (_verdict_badge is a bare QLabel; the
click handler doesn't exist).
"""
from __future__ import annotations

import ast
import inspect

import pytest

pytest.importorskip("PyQt6.QtWidgets")


def test_verdict_badge_constructed_as_click_label():
    """Source-scan guard: header.py's own construction code must instantiate
    _verdict_badge via _ClickLabel(...), not a bare QLabel() -- unit-testing
    the widget construction itself would require the full native-chrome
    header build (AppHeaderMixin), which needs a real Dashboard."""
    from ui import header
    src = inspect.getsource(header)
    tree = ast.parse(src)
    found = False
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Attribute)
            and node.targets[0].attr == "_verdict_badge"
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
        ):
            found = True
            assert node.value.func.id == "_ClickLabel", (
                "_verdict_badge must be constructed as _ClickLabel(...), "
                f"found {node.value.func.id}(...) instead"
            )
    assert found, "_verdict_badge assignment not found in ui/header.py"


def test_verdict_badge_clicked_is_connected():
    from ui import header
    src = inspect.getsource(header)
    assert "_verdict_badge.clicked.connect(" in src


def test_monitor_state_mixin_has_verdict_badge_click_handler():
    from ui.monitor_state import _MonitorStateMixin
    assert hasattr(_MonitorStateMixin, "_on_verdict_badge_clicked")


def test_verdict_badge_click_routes_to_whats_wrong_with_no_specific_cause():
    """Fallback: diagnostics-only escalation (gateway ping fail, DNS leak)
    has no dedicated results page of its own -- What's Wrong? is correct
    there, since it's literally what produces _diag_result."""
    from ui.monitor_state import _MonitorStateMixin
    from ui.nav.labels import NavLabel as L

    class _Stub(_MonitorStateMixin):
        def __init__(self):
            self.nav_calls = []

        def _nav_rail_go_to(self, label, _push_history=False):
            self.nav_calls.append(label)

    stub = _Stub()
    stub._on_verdict_badge_clicked()

    assert stub.nav_calls == [L.WHATS_WRONG]


def test_verdict_badge_click_routes_to_specific_cause_page():
    """When _update_overall_verdict() identified which scan actually raised
    the severity, the badge must route there -- not a generic diagnosis
    entry point that doesn't even show the existing finding."""
    from ui.monitor_state import _MonitorStateMixin
    from ui.nav.labels import NavLabel as L

    class _Stub(_MonitorStateMixin):
        def __init__(self):
            self.nav_calls = []
            self._verdict_cause_page = L.DEVICES

        def _nav_rail_go_to(self, label, _push_history=False):
            self.nav_calls.append(label)

    stub = _Stub()
    stub._on_verdict_badge_clicked()

    assert stub.nav_calls == [L.DEVICES]


# ── _header_nc_client_widgets — native chrome click-swallow guard ───────────

def test_verdict_badge_registered_as_nc_client_widget():
    """Regression: under native window chrome (RULE-WIN9/native_chrome.py),
    any header widget NOT listed in _header_nc_client_widgets becomes
    HTCAPTION -- the OS treats clicks on it as dragging the window, and
    Qt's mousePressEvent never fires. Making _verdict_badge a _ClickLabel
    was not enough on its own; it must also be added to this list or the
    click is silently swallowed."""
    from ui import header
    src = inspect.getsource(header)
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Attribute)
            and node.targets[0].attr == "_header_nc_client_widgets"
        ):
            names = [
                elt.attr if isinstance(elt, ast.Attribute) else getattr(elt, "id", None)
                for elt in node.value.elts
            ]
            assert "_verdict_badge" in names, (
                "_verdict_badge is missing from _header_nc_client_widgets -- "
                "clicks on it will be swallowed as window-drag under native chrome"
            )
            return
    pytest.fail("_header_nc_client_widgets assignment not found in ui/header.py")


# ── Per-source verdict cause tracking ────────────────────────────────────────

from ui.monitor_state import _MonitorStateMixin  # noqa: E402


class _VerdictCauseHost(_MonitorStateMixin):
    """Minimal stand-in exposing only what _update_overall_verdict touches."""

    def __init__(self):
        from unittest.mock import MagicMock
        self._m1_result = None
        self._m2_result = None
        self._m3_result = None
        self._m4_result = None
        self._m5_result = None
        self._diag_result = None
        self._verdict = MagicMock()
        self._verdict_badge = MagicMock()


class TestVerdictCauseTracking:
    def test_high_risk_devices_points_at_devices_page(self):
        from ui.nav.labels import NavLabel as L
        host = _VerdictCauseHost()
        host._m1_result = {"plain_verdict": "2 high-risk devices", "high_risk_count": 2}
        host._update_overall_verdict()
        assert host._verdict_cause_page == L.DEVICES

    def test_rogue_bridge_points_at_rogue_bridge_page(self):
        from ui.nav.labels import NavLabel as L
        host = _VerdictCauseHost()
        host._m2_result = {"plain_verdict": "rogue root bridge claim", "rogue_count": 1}
        host._update_overall_verdict()
        assert host._verdict_cause_page == L.ROGUE_BRIDGE_STP

    def test_broadcast_storm_points_at_broadcast_storm_page(self):
        from ui.nav.labels import NavLabel as L
        host = _VerdictCauseHost()
        host._m3_result = {"plain_verdict": "storm", "storm_level": "STORM"}
        host._update_overall_verdict()
        assert host._verdict_cause_page == L.BROADCAST_STORM

    def test_rogue_wifi_points_at_wifi_networks_page(self):
        from ui.nav.labels import NavLabel as L
        host = _VerdictCauseHost()
        host._m4_result = {"plain_verdict": "rogue SSID", "rogue_count": 1}
        host._update_overall_verdict()
        assert host._verdict_cause_page == L.WIFI_NETWORKS

    def test_stp_reconvergence_points_at_dns_stability_page(self):
        from ui.nav.labels import NavLabel as L
        host = _VerdictCauseHost()
        host._m5_result = {"plain_verdict": "outages", "stp_signatures": [{"target": "x"}]}
        host._update_overall_verdict()
        assert host._verdict_cause_page == L.DNS_STABILITY

    def test_diagnostics_only_has_no_specific_cause_page(self):
        from unittest.mock import MagicMock
        host = _VerdictCauseHost()
        host._diag_result = MagicMock(
            plain_verdict="gateway unreachable",
            ping_results=[MagicMock(host="Gateway", status="FAIL")],
            dns_leak=None,
        )
        host._update_overall_verdict()
        assert getattr(host, "_verdict_cause_page", None) is None

    def test_clean_state_has_no_cause_page(self):
        host = _VerdictCauseHost()
        host._update_overall_verdict()
        assert getattr(host, "_verdict_cause_page", None) is None
