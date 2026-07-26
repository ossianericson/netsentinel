"""
Tests for ui/pages/notifications_page.py

Covers:
  • NotificationsPage instantiates without errors (catches the _rule_checkboxes
    AttributeError regression that crashed the app on first launch)
  • All expected alert-rule checkboxes are present and unchecked by default
  • _ALERT_RULE_DEFS names match the default rules in alert_engine._default_rules()
  • set_alert_engine() wires the engine; _apply_to_engine() propagates checkbox state
  • set_router() stores the router reference
  • _save() / _restore() round-trip persists rule enabled states
  • Enabling a rule checkbox updates the live AlertEngine immediately
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytest.importorskip("PyQt6.QtWidgets")

# Use the session-scoped app from conftest; fall back for standalone runs.


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_page():
    from ui.pages.notifications_page import NotificationsPage
    return NotificationsPage()


def _default_rule_names():
    from modules.alert_engine import _default_rules
    return [r.name for r in _default_rules()]


# ---------------------------------------------------------------------------
# Instantiation
# ---------------------------------------------------------------------------

class TestInstantiation:
    def test_page_constructs_without_error(self):
        """Regression: _rule_checkboxes must exist before _build_alert_rules_card runs."""
        page = _make_page()
        assert page is not None

    def test_rule_checkboxes_dict_populated(self):
        page = _make_page()
        assert isinstance(page._rule_checkboxes, dict)
        assert len(page._rule_checkboxes) > 0

    def test_alert_engine_attr_initialised(self):
        page = _make_page()
        assert hasattr(page, "_alert_engine")
        assert page._alert_engine is None


# ---------------------------------------------------------------------------
# Alert rule checkboxes
# ---------------------------------------------------------------------------

class TestAlertRuleCheckboxes:
    def test_all_default_rules_have_checkboxes(self):
        page = _make_page()
        for name in _default_rule_names():
            assert name in page._rule_checkboxes, (
                f"Expected checkbox for rule {name!r} but it is missing"
            )

    def test_all_checkboxes_unchecked_by_default(self):
        """All rules must default to unchecked (opt-in only)."""
        # Clear any saved rule states so a fresh page starts with all off.
        from PyQt6.QtCore import QSettings
        from modules.alert_engine import rule_settings_key
        qs = QSettings("NetSentinel", "NetSentinel")
        for name in _default_rule_names():
            qs.remove(rule_settings_key(name))
        qs.sync()
        page = _make_page()
        for name, chk in page._rule_checkboxes.items():
            assert not chk.isChecked(), (
                f"Rule {name!r} checkbox must default to unchecked"
            )

    def test_defs_match_default_rules(self):
        """_ALERT_RULE_DEFS names must be a superset of _default_rules() names."""
        from ui.pages.notifications_page import _ALERT_RULE_DEFS
        def_names = {entry[0] for entry in _ALERT_RULE_DEFS}
        for name in _default_rule_names():
            assert name in def_names, (
                f"Rule {name!r} in _default_rules() has no entry in _ALERT_RULE_DEFS"
            )


# ---------------------------------------------------------------------------
# AlertEngine wiring
# ---------------------------------------------------------------------------

class TestAlertEngineWiring:
    def _make_engine(self):
        from modules.alert_engine import AlertEngine, _default_rules
        eng = AlertEngine(store=None, rules=_default_rules())
        return eng

    def test_set_alert_engine_stores_reference(self):
        page = _make_page()
        eng = self._make_engine()
        page.set_alert_engine(eng)
        assert page._alert_engine is eng

    def test_apply_to_engine_propagates_disabled(self):
        """With all checkboxes unchecked, all rules remain disabled in the engine."""
        page = _make_page()
        eng = self._make_engine()
        page.set_alert_engine(eng)
        for rule in eng.get_rules():
            assert rule.enabled is False, (
                f"Rule {rule.name!r} should be disabled after set_alert_engine with unchecked boxes"
            )

    def test_checking_checkbox_enables_rule_in_engine(self):
        """Checking a checkbox immediately enables that rule in the live engine."""
        page = _make_page()
        eng = self._make_engine()
        page.set_alert_engine(eng)

        target = "Host Down"
        chk = page._rule_checkboxes[target]
        chk.setChecked(True)  # triggers _save → _apply_to_engine

        matching = [r for r in eng.get_rules() if r.name == target]
        assert matching, f"Rule {target!r} not found in engine"
        assert matching[0].enabled is True

    def test_unchecking_checkbox_disables_rule_in_engine(self):
        page = _make_page()
        eng = self._make_engine()
        page.set_alert_engine(eng)

        target = "New Device"
        chk = page._rule_checkboxes[target]
        chk.setChecked(True)
        chk.setChecked(False)

        matching = [r for r in eng.get_rules() if r.name == target]
        assert matching[0].enabled is False


# ---------------------------------------------------------------------------
# Escalation policy wiring (F-21)
# ---------------------------------------------------------------------------

class TestEscalationWiring:
    """AlertEngine.set_escalation_policies()/check_escalations() previously had
    zero callers — _apply_to_engine() must build real EscalationPolicy objects
    from the Escalation card's controls."""

    def setup_method(self, _method) -> None:
        # QSettings persists to the real OS store across process runs (not
        # just within this test session) — start every test from a clean slate.
        from PyQt6.QtCore import QSettings
        qs = QSettings("NetSentinel", "NetSentinel")
        for key in ("notif/escalation_enabled", "notif/escalation_wait",
                    "notif/escalation_channel", "notif/escalation_rules"):
            qs.remove(key)
        qs.sync()

    def _make_engine(self):
        from modules.alert_engine import AlertEngine, _default_rules
        return AlertEngine(store=None, rules=_default_rules())

    def test_disabled_by_default_produces_no_enabled_policies(self):
        page = _make_page()
        eng = self._make_engine()
        page.set_alert_engine(eng)
        assert all(not p.enabled for p in eng.get_escalation_policies())

    def test_explicit_rule_list_builds_matching_policies(self):
        page = _make_page()
        eng = self._make_engine()
        page.set_alert_engine(eng)

        page._chk_escalation.setChecked(True)
        page._spin_escalation_wait.setValue(30)
        page._combo_escalation_channel.setCurrentText("Webhook")
        page._txt_escalation_rules.setText("Host Down, High RTT")
        page._save()

        policies = {p.rule_name: p for p in eng.get_escalation_policies()}
        assert set(policies) == {"Host Down", "High RTT"}
        for p in policies.values():
            assert p.enabled is True
            assert p.wait_minutes == 30
            assert p.notify_channels == ["Webhook"]

    def test_blank_rules_field_means_all_currently_enabled_rules(self):
        page = _make_page()
        eng = self._make_engine()
        page.set_alert_engine(eng)

        page._rule_checkboxes["Host Down"].setChecked(True)
        page._chk_escalation.setChecked(True)
        page._txt_escalation_rules.setText("")
        page._save()

        policy_names = {p.rule_name for p in eng.get_escalation_policies()}
        assert "Host Down" in policy_names
        assert "New Device" not in policy_names  # never enabled in this test

    def test_case_insensitive_rule_names_canonicalise(self):
        """Phase 7.6 -- alert_engine.py:212 compares case-sensitively, so free
        text like 'host down' previously silently escalated nothing."""
        page = _make_page()
        eng = self._make_engine()
        page.set_alert_engine(eng)

        page._chk_escalation.setChecked(True)
        page._txt_escalation_rules.setText("host down, HIGH rtt")
        page._save()

        policy_names = {p.rule_name for p in eng.get_escalation_policies()}
        assert policy_names == {"Host Down", "High RTT"}

    def test_unknown_rule_name_produces_no_policy_and_shows_warning(self):
        page = _make_page()
        eng = self._make_engine()
        page.set_alert_engine(eng)
        page.show()  # isVisible() reflects the whole ancestor chain, and the
                     # escalation card body starts collapsed
        page._toggle_escalation_body()

        page._chk_escalation.setChecked(True)
        page._txt_escalation_rules.setText("Nope")
        page._save()

        assert eng.get_escalation_policies() == []
        assert hasattr(page, "_escalation_rules_warning")
        assert page._escalation_rules_warning.isVisible() is True
        assert "Nope" in page._escalation_rules_warning.text()

    def test_warning_clears_once_all_names_are_valid(self):
        page = _make_page()
        eng = self._make_engine()
        page.set_alert_engine(eng)
        page.show()
        page._toggle_escalation_body()

        page._chk_escalation.setChecked(True)
        page._txt_escalation_rules.setText("Nope")
        page._save()
        assert page._escalation_rules_warning.isVisible() is True

        page._txt_escalation_rules.setText("Host Down")
        page._save()
        assert page._escalation_rules_warning.isVisible() is False


# ---------------------------------------------------------------------------
# Router injection
# ---------------------------------------------------------------------------

class TestRouterInjection:
    def test_set_router_stores_reference(self):
        page = _make_page()
        mock_router = MagicMock()
        mock_router.set_channels = MagicMock()
        page.set_router(mock_router)
        assert page._router is mock_router

    def test_set_router_calls_apply_to_router(self):
        page = _make_page()
        mock_router = MagicMock()
        mock_router.set_channels = MagicMock()
        page.set_router(mock_router)
        mock_router.set_channels.assert_called()


# ---------------------------------------------------------------------------
# Settings persistence round-trip
# ---------------------------------------------------------------------------

class TestSettingsPersistence:
    def test_rule_state_survives_save_restore(self):
        """Enable two rules, save, create a fresh page, restore — states match."""
        from PyQt6.QtCore import QSettings
        from modules.alert_engine import rule_settings_key

        # Clear state first to avoid interference from other tests.
        qs = QSettings("NetSentinel", "NetSentinel")
        for name in _default_rule_names():
            qs.remove(rule_settings_key(name))
        qs.sync()

        # Set two rules via checkboxes then call _save() explicitly.
        page_a = _make_page()
        page_a._rule_checkboxes["Host Down"].setChecked(True)
        page_a._rule_checkboxes["New Device"].setChecked(True)
        page_a._save()  # explicit call after both boxes are set

        # Fresh page should restore the saved state.
        page_b = _make_page()
        assert page_b._rule_checkboxes["Host Down"].isChecked()
        assert page_b._rule_checkboxes["New Device"].isChecked()
        assert not page_b._rule_checkboxes["High RTT"].isChecked()

        # Clean up.
        for name in ("Host Down", "New Device"):
            qs.setValue(rule_settings_key(name), False)
        qs.sync()

    def test_sensitivity_survives_save_restore(self):
        """V6 Sprint 5.4 — global sensitivity combo persists across reload."""
        from PyQt6.QtCore import QSettings

        qs = QSettings("NetSentinel", "NetSentinel")
        qs.remove("alerts/sensitivity")
        qs.sync()

        page_a = _make_page()
        idx = page_a._combo_sensitivity.findData("aggressive")
        page_a._combo_sensitivity.setCurrentIndex(idx)
        page_a._save()

        page_b = _make_page()
        assert page_b._combo_sensitivity.currentData() == "aggressive"

        qs.remove("alerts/sensitivity")
        qs.sync()


class TestSensitivityAppliesImmediately:
    """Phase 7.7 -- apply_sensitivity() mutates AlertRule objects in place and
    is NOT idempotent (calling it twice compounds: 200 -> 140 -> 98). The
    'requires a restart' hint existed because _apply_to_engine() used to
    re-scale the ALREADY-SCALED live rule objects on every save. Fixed by
    rebuilding from _default_rules() every time, matching app.py's own
    startup bootstrap sequence."""

    def _make_engine(self):
        from modules.alert_engine import AlertEngine, _default_rules
        return AlertEngine(store=None, rules=_default_rules())

    def test_sensitivity_change_rescales_live_engine_thresholds(self):
        page = _make_page()
        eng = self._make_engine()
        page.set_alert_engine(eng)

        idx = page._combo_sensitivity.findData("aggressive")
        page._combo_sensitivity.setCurrentIndex(idx)
        page._save()

        rule = next(r for r in eng.get_rules() if r.name == "High RTT")
        assert rule.threshold_ms == 140.0

    def test_repeated_saves_do_not_compound_the_scale(self):
        page = _make_page()
        eng = self._make_engine()
        page.set_alert_engine(eng)

        idx = page._combo_sensitivity.findData("aggressive")
        page._combo_sensitivity.setCurrentIndex(idx)
        page._save()
        page._save()
        page._save()

        rule = next(r for r in eng.get_rules() if r.name == "High RTT")
        assert rule.threshold_ms == 140.0

    def test_cooldown_state_survives_a_settings_change(self):
        """_last_fired is keyed by 'rule_name::host' strings, so replacing
        rule objects wholesale must not let a just-fired alert re-fire
        immediately after a sensitivity change."""
        from modules.alert_engine import AlertRule

        page = _make_page()
        eng = self._make_engine()
        page.set_alert_engine(eng)
        page._rule_checkboxes["Host Down"].setChecked(True)
        page._save()

        now = 1_000_000
        rule = next(r for r in eng.get_rules() if r.name == "Host Down")
        fired = eng._eval_rule_for_host(
            rule, "10.0.0.1", {"10.0.0.1": "DOWN"}, {}, now,
        )
        assert fired is not None  # first firing populates _last_fired

        idx = page._combo_sensitivity.findData("conservative")
        page._combo_sensitivity.setCurrentIndex(idx)
        page._save()

        rule2 = next(r for r in eng.get_rules() if r.name == "Host Down")
        assert isinstance(rule2, AlertRule)
        refired = eng._eval_rule_for_host(
            rule2, "10.0.0.1", {"10.0.0.1": "DOWN"}, {}, now + 1,
        )
        assert refired is None  # still within cooldown -- must not double-fire

    def test_sensitivity_hint_no_longer_claims_a_restart_is_needed(self):
        page = _make_page()
        text = page._sens_hint_lbl.text().lower()
        assert "restart" not in text
        assert "immediately" in text


# ---------------------------------------------------------------------------
# Service Down escalation sub-toggle (Sprint 1)
# ---------------------------------------------------------------------------

class TestServiceEscalationToggle:
    def test_checkbox_exists_and_defaults_checked(self):
        """'Diagnose why' defaults to True once SERVICE_DOWN is enabled (opt-out, not opt-in)."""
        from PyQt6.QtCore import QSettings
        qs = QSettings("NetSentinel", "NetSentinel")
        qs.remove("notif/service_escalation_enabled")
        qs.sync()

        page = _make_page()
        assert hasattr(page, "_chk_service_escalation")
        assert page._chk_service_escalation.isChecked() is True

    def test_disabling_toggle_persists_across_reload(self):
        from PyQt6.QtCore import QSettings
        qs = QSettings("NetSentinel", "NetSentinel")

        page_a = _make_page()
        page_a._chk_service_escalation.setChecked(False)
        page_a._save()

        page_b = _make_page()
        assert page_b._chk_service_escalation.isChecked() is False

        # Clean up.
        qs.setValue("notif/service_escalation_enabled", True)
        qs.sync()


# ---------------------------------------------------------------------------
# Alert History — "Unacknowledged only" filter (critical-UX Phase 1.1)
# ---------------------------------------------------------------------------

class _FakeStore:
    def __init__(self, unacked=None, recent=None, history=None):
        self._unacked = unacked or []
        self._recent = recent or []
        self._history = history
        self.get_alert_history_calls: list = []

    def get_unacked_alerts(self, *a, **kw):
        return self._unacked

    def get_recent_alerts(self, hours=24.0, limit=200):
        return self._recent

    def get_alert_history(self, hours=24.0, limit=500, unacked_only=False):
        self.get_alert_history_calls.append((hours, limit, unacked_only))
        if unacked_only:
            return self._history if self._history is not None else self._unacked
        return self._recent


class TestAlertHistoryUnackedFilter:
    def test_checkbox_exists(self):
        page = _make_page()
        assert hasattr(page, "_chk_unacked_only")

    def test_checkbox_defaults_checked_when_unacked_alerts_exist(self):
        page = _make_page()
        page.set_store(_FakeStore(unacked=[{"id": 1}]))
        page.show()
        page._refresh_alert_history()
        assert page._chk_unacked_only.isChecked() is True

    def test_checkbox_defaults_unchecked_when_no_unacked_alerts(self):
        page = _make_page()
        page.set_store(_FakeStore(unacked=[]))
        page.show()
        page._refresh_alert_history()
        assert page._chk_unacked_only.isChecked() is False

    def test_checked_state_calls_get_alert_history_unacked_only(self):
        page = _make_page()
        store = _FakeStore(unacked=[{"id": 1, "ts": 0, "severity": "INFO", "host": "h"}])
        page.set_store(store)
        page.show()
        page._chk_unacked_only.setChecked(True)
        page._refresh_alert_history()
        assert store.get_alert_history_calls
        assert store.get_alert_history_calls[-1][2] is True

    def test_unchecked_state_does_not_use_unacked_only(self):
        """No unacked alerts -> the auto-default logic has nothing to force
        checked, so an explicit uncheck (or the natural default) sticks."""
        page = _make_page()
        store = _FakeStore(unacked=[])
        page.set_store(store)
        page.show()
        page._chk_unacked_only.setChecked(False)
        page._refresh_alert_history()
        assert not store.get_alert_history_calls

    def test_user_can_uncheck_despite_unacked_alerts_existing(self):
        """The auto-default only applies once (first refresh) -- after that,
        an explicit user uncheck must stick even though unacked alerts still
        exist, or the checkbox would be un-uncheckable."""
        page = _make_page()
        store = _FakeStore(unacked=[{"id": 1, "ts": 0, "severity": "INFO", "host": "h"}])
        page.set_store(store)
        page.show()
        page._refresh_alert_history()  # applies the auto-default -> checked
        assert page._chk_unacked_only.isChecked() is True
        calls_before = len(store.get_alert_history_calls)
        page._chk_unacked_only.setChecked(False)
        page._refresh_alert_history()
        assert page._chk_unacked_only.isChecked() is False
        assert len(store.get_alert_history_calls) == calls_before

    def test_window_combo_disabled_while_unacked_filter_active(self):
        page = _make_page()
        page.set_store(_FakeStore(unacked=[{"id": 1, "ts": 0, "severity": "INFO", "host": "h"}]))
        page.show()
        page._chk_unacked_only.setChecked(True)
        page._refresh_alert_history()
        assert page._hist_time_combo.isEnabled() is False

    def test_window_combo_enabled_when_filter_off(self):
        page = _make_page()
        page.set_store(_FakeStore(unacked=[]))
        page.show()
        page._chk_unacked_only.setChecked(False)
        page._refresh_alert_history()
        assert page._hist_time_combo.isEnabled() is True


class TestSwitchToHistoryTabUnacked:
    def test_default_call_keeps_old_behaviour(self):
        page = _make_page()
        page.switch_to_history_tab()
        assert page._notif_tabs.currentIndex() == 1

    def test_unacked_only_true_checks_the_filter(self):
        page = _make_page()
        page.set_store(_FakeStore(unacked=[]))
        page.switch_to_history_tab(unacked_only=True)
        assert page._notif_tabs.currentIndex() == 1
        assert page._chk_unacked_only.isChecked() is True


class TestChannelTestButtons:
    """Phase 3.1 -- defect 8, a live crash. All five 'Send Test' buttons
    imported _deliver_* from modules.notification_router, where those names
    do not exist (they live in modules.notification_channels). No try/except
    guarded the import, so it escaped into the global exception hook as an
    'unhandled error' dialog on every click."""

    def _rig(self, page, monkeypatch):
        calls = []
        monkeypatch.setattr(page, "_run_test", lambda key, fn, ch, alert: calls.append((key, fn, ch, alert)))
        return calls

    def test_email_test_button_does_not_raise(self, monkeypatch):
        page = _make_page()
        calls = self._rig(page, monkeypatch)
        page._email_host.setText("smtp.example.com")
        page._email_to.setText("a@b.com")
        page._test_email()
        assert calls and calls[0][0] == "email"

    def test_webhook_test_button_does_not_raise(self, monkeypatch):
        page = _make_page()
        calls = self._rig(page, monkeypatch)
        page._webhook_url.setText("https://example.com/hook")
        page._test_webhook()
        assert calls and calls[0][0] == "webhook"

    def test_pushover_test_button_does_not_raise(self, monkeypatch):
        page = _make_page()
        calls = self._rig(page, monkeypatch)
        page._test_pushover()
        assert calls and calls[0][0] == "pushover"

    def test_ntfy_test_button_does_not_raise(self, monkeypatch):
        page = _make_page()
        calls = self._rig(page, monkeypatch)
        page._test_ntfy()
        assert calls and calls[0][0] == "ntfy"

    def test_telegram_test_button_does_not_raise(self, monkeypatch):
        page = _make_page()
        calls = self._rig(page, monkeypatch)
        page._test_telegram()
        assert calls and calls[0][0] == "telegram"


class TestSetGlobalHoursSync:
    def test_updates_combo_display(self):
        page = _make_page()
        page.set_store(_FakeStore())
        page.set_global_hours(6.0)
        assert page._hist_time_combo.currentText() == "6h"

    def test_skips_override_while_unacked_filter_active(self):
        page = _make_page()
        page.set_store(_FakeStore(unacked=[{"id": 1, "ts": 0, "severity": "INFO", "host": "h"}]))
        page.show()
        page._chk_unacked_only.setChecked(True)
        page._refresh_alert_history()
        before = page._hist_hours
        page.set_global_hours(1.0)
        assert page._hist_hours == before
