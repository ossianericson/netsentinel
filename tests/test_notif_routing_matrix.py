"""
Phase 6 -- per-rule x per-channel routing matrix (RULE-T7 behavioral test;
RULE-TDD1 does not apply to ui/pages/).

Additive and self-gating: absent notif/rule_routing -> {} -> every channel's
rule_types stays [] ("all rules") -> byte-identical behaviour to before this
card existed. The only way to change routing is to open the collapsed
"Advanced" card and uncheck something.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtCore import QSettings  # noqa: E402


def _clear_routing():
    qs = QSettings("NetSentinel", "NetSentinel")
    qs.remove("notif/rule_routing")
    qs.remove("notif/email_enabled")
    qs.remove("notif/email_host")
    qs.remove("notif/email_to")
    qs.sync()
    return qs


def _make_page():
    from ui.pages.notifications_page import NotificationsPage
    return NotificationsPage()


class TestBackwardCompat:
    def test_routing_matrix_from_json_empty_string_is_backward_compatible(self):
        from modules.notification_router import routing_matrix_from_json
        assert routing_matrix_from_json("") == {}

    def test_fresh_page_has_no_stored_routing_and_every_channel_gets_all_rules(self):
        _clear_routing()
        try:
            page = _make_page()
            from modules.notification_router import ToastChannel
            router = MagicMock()
            page.set_router(router)
            channels = router.set_channels.call_args[0][0]
            toast = next(c for c in channels if isinstance(c, ToastChannel))
            assert toast.rule_types == []
        finally:
            _clear_routing()


class TestSelectingOneRuleForOneChannel:
    def test_email_routed_to_only_new_cve(self):
        qs = _clear_routing()
        try:
            qs.setValue("notif/email_enabled", True)
            qs.setValue("notif/email_host", "smtp.example.com")
            qs.setValue("notif/email_to", "a@b.com")
            page = _make_page()

            # Switch the routing-matrix combo to "Email" and uncheck every
            # rule except New CVE Found.
            idx = page._route_channel_combo.findData("email")
            page._route_channel_combo.setCurrentIndex(idx)
            for rt, chk in page._route_rule_checks.items():
                chk.setChecked(rt == "NEW_CVE")

            router = MagicMock()
            page.set_router(router)

            from modules.notification_router import EmailChannel
            channels = router.set_channels.call_args[0][0]
            em = next(c for c in channels if isinstance(c, EmailChannel))
            assert em.rule_types == ["NEW_CVE"]
            assert em.enabled is True
        finally:
            _clear_routing()

    def test_other_channels_unaffected_by_email_only_routing(self):
        qs = _clear_routing()
        try:
            qs.setValue("notif/toast_enabled", True)
            page = _make_page()

            idx = page._route_channel_combo.findData("email")
            page._route_channel_combo.setCurrentIndex(idx)
            for rt, chk in page._route_rule_checks.items():
                chk.setChecked(rt == "NEW_CVE")

            router = MagicMock()
            page.set_router(router)

            from modules.notification_router import ToastChannel
            channels = router.set_channels.call_args[0][0]
            toast = next(c for c in channels if isinstance(c, ToastChannel))
            assert toast.rule_types == []
            assert toast.enabled is True
        finally:
            _clear_routing()
            qs.remove("notif/toast_enabled")


class TestZeroSelectionDisablesTheChannel:
    def test_unchecking_every_rule_disables_the_channel(self):
        qs = _clear_routing()
        try:
            qs.setValue("notif/email_enabled", True)
            qs.setValue("notif/email_host", "smtp.example.com")
            qs.setValue("notif/email_to", "a@b.com")
            page = _make_page()
            page.show()                  # isVisible() reflects the WHOLE
                                          # ancestor chain up to the top-level
                                          # window, which defaults to unshown
            page._toggle_routing_body()  # expand -- the card starts collapsed

            idx = page._route_channel_combo.findData("email")
            page._route_channel_combo.setCurrentIndex(idx)
            for chk in page._route_rule_checks.values():
                chk.setChecked(False)

            assert page._route_empty_warning.isVisible() is True

            router = MagicMock()
            page.set_router(router)

            from modules.notification_router import EmailChannel
            channels = router.set_channels.call_args[0][0]
            em = next(c for c in channels if isinstance(c, EmailChannel))
            assert em.enabled is False
        finally:
            _clear_routing()

    def test_all_rules_checkbox_reflects_full_selection(self):
        _clear_routing()
        try:
            page = _make_page()
            idx = page._route_channel_combo.findData("toast")
            page._route_channel_combo.setCurrentIndex(idx)
            assert page._chk_route_all.isChecked() is True  # default: all selected

            next(iter(page._route_rule_checks.values())).setChecked(False)
            assert page._chk_route_all.isChecked() is False
        finally:
            _clear_routing()


class TestRoutingSurvivesSaveRestore:
    def test_matrix_persists_across_page_reconstruction(self):
        _clear_routing()
        try:
            page_a = _make_page()
            idx = page_a._route_channel_combo.findData("webhook")
            page_a._route_channel_combo.setCurrentIndex(idx)
            for rt, chk in page_a._route_rule_checks.items():
                chk.setChecked(rt in ("HOST_DOWN", "NEW_CVE"))

            page_b = _make_page()
            idx_b = page_b._route_channel_combo.findData("webhook")
            page_b._route_channel_combo.setCurrentIndex(idx_b)
            selected = {rt for rt, chk in page_b._route_rule_checks.items() if chk.isChecked()}
            assert selected == {"HOST_DOWN", "NEW_CVE"}
        finally:
            _clear_routing()
