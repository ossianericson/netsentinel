"""
tests/test_nav_admin_indicator.py — elevation-aware admin indicator in the nav.

`admin_required` nav entries used to render a static red "admin" pill in the flyout
unconditionally — including for a user who IS elevated, where it says nothing at
all. The pill is a warning ("you cannot run this as you are"), so it must track
`Dashboard._admin`, and the rail button carries a matching amber left-dot so the
state is visible before the flyout is even opened.

Both directions are asserted in every case: an indicator that is always-on and one
that is always-off are equally wrong, and only checking one branch cannot tell them
apart.
"""
from __future__ import annotations

import types
import unittest


def _make_nav_host(admin: bool, tmp_ini):
    """Minimal object satisfying _NavBuilderMixin._nav_rail_toggle."""
    from ui.nav.builder import _NavBuilderMixin
    from ui.nav.rail import _NavEntry

    captured: dict = {}

    class _Host(_NavBuilderMixin):
        def __init__(self):
            self._admin = admin
            self._nav_open_section = ""
            self._nav_pinned_labels: list = []
            self._nav_current_page_label = ""
            self._flyout_dots: dict = {}
            self._nav_rail_buttons: dict = {}
            self._nav_sections = [{
                "name": "Security Audit",
                "icon": "shield",
                "entries": [
                    _NavEntry(label="Port Scan (TCP)", page=None, admin_required=True,
                              audit_item=True),
                    _NavEntry(label="802.11 Monitor", page=None, npcap_required=True,
                              audit_item=True),
                    _NavEntry(label="Security Overview", page=None, audit_item=True),
                ],
            }]
            self._nav_flyout = types.SimpleNamespace(
                maximumWidth=lambda: 0,
                load_section=lambda **kw: captured.update(kw),
                apply_dot=lambda lbl, col: None,
                open=lambda: None,
                is_pinned=False,
            )

        # Never let a test write the developer's real NetSentinel.ini
        def _settings_path(self):
            return tmp_ini

        def _on_rail_pin_toggle(self, *a):
            pass

        def _on_rail_pin_move(self, *a):
            pass

        # Mirrors _NavBuilderMixin._nav_rail_go_to's signature exactly — a
        # bare *a stub cannot accept the keyword arguments the base method
        # does (CodeQL py/inheritance/signature-mismatch).
        def _nav_rail_go_to(self, label: str, _push_history: bool = False) -> None:
            pass

    return _Host(), captured


def _badges(captured):
    """{label: badge string} from the entries tuple _nav_rail_toggle built."""
    return {label: badge for label, _pinned, _dim, badge in captured["entries"]}


class TestFlyoutAdminPill(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        self._tmp = tempfile.TemporaryDirectory()
        self._ini = Path(self._tmp.name) / "NetSentinel.ini"

    def tearDown(self):
        self._tmp.cleanup()

    def test_non_admin_user_sees_the_admin_pill(self):
        host, captured = _make_nav_host(admin=False, tmp_ini=self._ini)
        host._nav_rail_toggle("Security Audit")
        assert _badges(captured)["Port Scan (TCP)"] == "admin"

    def test_elevated_user_sees_no_admin_pill(self):
        host, captured = _make_nav_host(admin=True, tmp_ini=self._ini)
        host._nav_rail_toggle("Security Audit")
        assert _badges(captured)["Port Scan (TCP)"] == "", (
            "the 'admin' pill still shows for an elevated process — it is a warning "
            "that the tool cannot run, so it is pure noise once the user IS admin"
        )

    def test_npcap_pill_is_unaffected_by_elevation(self):
        """Npcap is a driver dependency, not a privilege — admin does not supply it."""
        for admin in (True, False):
            host, captured = _make_nav_host(admin=admin, tmp_ini=self._ini)
            host._nav_rail_toggle("Security Audit")
            assert _badges(captured)["802.11 Monitor"] == "Npcap", (
                f"Npcap badge changed with _admin={admin}; elevation does not install Npcap"
            )

    def test_plain_audit_entry_never_gets_a_badge(self):
        for admin in (True, False):
            host, captured = _make_nav_host(admin=admin, tmp_ini=self._ini)
            host._nav_rail_toggle("Security Audit")
            assert _badges(captured)["Security Overview"] == ""

    def test_entries_stay_dimmed_when_elevated(self):
        """Suppressing the pill must not also drop the audit_item dim flag —
        that flag marks the whole section as elevated-privilege tooling."""
        host, captured = _make_nav_host(admin=True, tmp_ini=self._ini)
        host._nav_rail_toggle("Security Audit")
        dims = {label: dim for label, _pinned, dim, _badge in captured["entries"]}
        assert dims["Port Scan (TCP)"] is True


class TestSecurityAuditRailDot(unittest.TestCase):
    """The rail-level counterpart: visible without opening the flyout."""

    def _host(self, admin: bool):
        from ui.monitor_state import _MonitorStateMixin

        class _Btn:
            def __init__(self):
                self.left_dot = "<unset>"
                self.badge = "<unset>"
                self.tip = ""

            def set_left_dot(self, color):
                self.left_dot = color

            def set_badge(self, value):
                self.badge = value

            def setToolTip(self, tip):
                self.tip = tip

        class _Host(_MonitorStateMixin):
            def __init__(self):
                self._admin = admin
                self._store = None
                self._nav_rail_buttons = {
                    "Monitor": _Btn(), "Analysis": _Btn(), "Security Audit": _Btn(),
                }

        return _Host()

    def test_non_admin_shows_amber_dot_and_explains_why(self):
        from ui.styles import AMBER
        host = self._host(admin=False)
        host._refresh_section_badges(arp=False, dhcp=False, storm=False, logger=False)
        btn = host._nav_rail_buttons["Security Audit"]
        assert btn.left_dot == AMBER
        assert "not running as Administrator" in btn.tip, (
            f"rail dot has no explanation in its tooltip: {btn.tip!r}"
        )

    def test_elevated_shows_no_dot_and_no_note(self):
        host = self._host(admin=True)
        host._refresh_section_badges(arp=False, dhcp=False, storm=False, logger=False)
        btn = host._nav_rail_buttons["Security Audit"]
        assert btn.left_dot == "", "amber dot still shown to an elevated user"
        assert "Administrator" not in btn.tip

    def test_alert_count_pill_survives_the_dot(self):
        """The numeric alert pill and the elevation dot are separate paint slots —
        adding the dot must not displace the badge (or vice versa)."""
        from ui.styles import AMBER

        class _Store:
            def get_unacked_alerts(self, rule_types=None):
                return [object(), object(), object()]

        host = self._host(admin=False)
        host._store = _Store()
        host._refresh_section_badges(arp=False, dhcp=False, storm=False, logger=False)
        btn = host._nav_rail_buttons["Security Audit"]
        assert btn.badge == 3
        assert btn.left_dot == AMBER
        assert "3 unacknowledged alert(s)" in btn.tip
        assert "not running as Administrator" in btn.tip


if __name__ == "__main__":
    unittest.main()
