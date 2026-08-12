"""
Acceptance criterion 7 — "a fresh install surfaces the curated default set and
nothing else".

Every alert rule has shipped `enabled=False` since the app gained an alert
engine, which is why Phase 0 could measure the engine as "nearly silent" while
the *event* stream carried 147 claims/day. The rules the user calls real —
the modem stopping, a mesh node dropping, the gateway going — were off by
default and stayed off.

The lever is the QSettings fallback, not `_default_rules()`'s own `enabled`
field: an absent key now falls back to `default_enabled(name)` instead of a
hardcoded False, so a fresh install gets the curated set while anyone who has
ever pressed Save on the Notifications page keeps exactly what they chose.
"""
from __future__ import annotations

from modules.alert_suppressor import (
    DEFAULT_ENABLED_RULES,
    _default_rules,
    default_enabled,
    rule_settings_key,
)


class TestTheCuratedSet:
    def test_every_curated_name_is_a_real_rule(self):
        """A typo here silently disables the whole set — the name would never
        match a rule, so nothing would turn on and nothing would complain."""
        known = {r.name for r in _default_rules()}
        assert DEFAULT_ENABLED_RULES <= known, (
            f"not real rules: {sorted(DEFAULT_ENABLED_RULES - known)}"
        )

    def test_the_four_phase_4_signals_are_on_by_default(self):
        """The entire point of the program: the signals the user calls real
        were built in Phase 4 and would otherwise ship switched off."""
        for name in ("Infrastructure Unreachable", "Mesh Degraded",
                     "Modem Signal Drop", "DNS Latency"):
            assert name in DEFAULT_ENABLED_RULES

    def test_host_down_is_on_by_default(self):
        assert "Host Down" in DEFAULT_ENABLED_RULES

    def test_the_level_triggered_noise_rules_stay_off(self):
        """Measured over 23.7 days on the reference network, through the v2 tier
        gate. These are level-triggered against fixed thresholds — the defect
        class the whole program exists to stop — so they stay opt-in.

        "Jitter High" belongs here for the same reason despite being revived in
        Phase 4: its threshold is a fixed 20 ms, which is precisely the
        objection that dropped "High RTT"."""
        for name in ("High RTT", "Host Degraded", "Packet Loss", "Jitter High"):
            assert name not in DEFAULT_ENABLED_RULES, (
                f"{name} is level-triggered or unmeasured; it must stay opt-in"
            )

    def test_rtt_anomaly_is_on_by_default(self):
        """v2.2.6. It was grouped with the fixed-threshold rules above, which
        misfiled it: RTT_ANOMALY learns a per-host mean+2sigma baseline rather
        than comparing against a constant, so it does not carry the defect that
        keeps the others off. Measured at 0.15 claims/day over 28.8 days through
        the v2 tier gate — quieter than MODEM_SIGNAL_DROP, which already ships
        on — and Phase 6 gave it an absolute floor so a host with a very low
        baseline cannot alert on a harmless few-millisecond excursion."""
        assert "RTT Anomaly" in DEFAULT_ENABLED_RULES

    def test_default_enabled_matches_the_set(self):
        for r in _default_rules():
            assert default_enabled(r.name) is (r.name in DEFAULT_ENABLED_RULES)

    def test_an_unknown_rule_name_defaults_off(self):
        """A user-authored rule the app has never seen must not be switched on
        by a lookup miss."""
        assert default_enabled("Some Rule Nobody Curated") is False

    def test_default_rules_still_ship_disabled_on_the_dataclass(self):
        """The lever is deliberately the QSettings fallback, not the dataclass:
        AlertEngine() is constructed headlessly by tests and tools/alert_replay,
        and flipping `enabled` here would change what those measure."""
        assert all(r.enabled is False for r in _default_rules())


class TestReadersUseTheDefault:
    """All three readers of the enable key must share one default, or the app,
    the audit and the Notifications page disagree about what is on."""

    def _reader_sources(self):
        import pathlib
        root = pathlib.Path(__file__).resolve().parent.parent
        return {
            "app.py": (root / "app.py").read_text(encoding="utf-8"),
            "notifications_page.py": (
                root / "ui" / "pages" / "notifications_page.py"
            ).read_text(encoding="utf-8"),
            "alert_audit.py": (
                root / "modules" / "alert_audit.py"
            ).read_text(encoding="utf-8"),
        }

    def test_no_reader_hardcodes_false_for_a_rule_key(self):
        offenders = []
        for name, src in self._reader_sources().items():
            for line in src.splitlines():
                if "_rk(" in line or "_rule_key(" in line or "rule_settings_key(" in line:
                    if "False" in line and "default_enabled" not in line:
                        offenders.append(f"{name}: {line.strip()}")
        assert not offenders, (
            "these readers still hardcode False as a rule's default, so the "
            "curated set will not reach them:\n  " + "\n  ".join(offenders)
        )

    def test_every_reader_imports_default_enabled(self):
        for name, src in self._reader_sources().items():
            assert "default_enabled" in src, f"{name} never consults the default"


class TestRuleSettingsKey:
    def test_key_shape_is_unchanged(self):
        """Existing installs' keys must keep resolving — a changed shape would
        silently reset every user's choices to the curated set."""
        assert rule_settings_key("Host Down") == "alert_rules/host_down/enabled"
        assert (
            rule_settings_key("Infrastructure Unreachable")
            == "alert_rules/infrastructure_unreachable/enabled"
        )


class TestAuditAcceptsTheDefaults:
    """`python app.py --audit` must pass on a fresh install. RULES_OPT_IN
    compares each enabled rule against its stored key, and DELIVERABILITY wants
    a channel that would accept it — both would fail for every curated rule if
    they still assumed 'enabled' implies 'the user wrote a key'."""

    def _audit(self, settings, channels=()):
        from modules.alert_audit import audit_alert_config
        rules = _default_rules()
        for r in rules:
            r.enabled = settings.get(rule_settings_key(r.name), default_enabled(r.name))
        return audit_alert_config(
            rules=rules,
            settings_get=lambda k, d=None: settings.get(k, d),
            channels=list(channels),
            escalation_policies=[],
        )

    def _finding(self, findings, code):
        return next(f for f in findings if f.code == code)

    def test_rules_opt_in_passes_on_a_fresh_install(self):
        findings = self._audit({})
        f = self._finding(findings, "RULES_OPT_IN")
        assert f.ok is True, f.detail

    def test_rules_opt_in_still_catches_a_genuine_mismatch(self):
        """The check must not become vacuous: a rule enabled in code while the
        user explicitly turned it off is still a real inconsistency."""
        from modules.alert_audit import audit_alert_config
        rules = _default_rules()
        for r in rules:
            r.enabled = r.name == "Host Down"
        findings = audit_alert_config(
            rules=rules,
            settings_get=lambda k, d=None: (
                False if k == rule_settings_key("Host Down") else d
            ),
            channels=[],
            escalation_policies=[],
        )
        f = next(x for x in findings if x.code == "RULES_OPT_IN")
        assert f.ok is False
        assert "Host Down" in f.detail

    def test_deliverability_passes_with_no_external_channel(self):
        """In-app surfacing is a real delivery path — _surface_alert_in_app()
        is always on and never gated — so a curated rule with no configured
        channel is reachable, not undeliverable."""
        f = self._finding(self._audit({}), "DELIVERABILITY")
        assert f.ok is True, f.detail

    def test_deliverability_names_the_in_app_only_rules(self):
        """It must stay informative, not just green: the user should be able to
        see which rules will never leave the app."""
        f = self._finding(self._audit({}), "DELIVERABILITY")
        assert "in-app" in f.detail.lower()
        assert "Host Down" in f.detail

    def test_deliverability_says_nothing_extra_when_a_channel_covers_everything(self):
        from modules.notification_router import ToastChannel
        f = self._finding(
            self._audit({}, channels=[ToastChannel(enabled=True, min_severity="INFO")]),
            "DELIVERABILITY",
        )
        assert f.ok is True
        assert "in-app" not in f.detail.lower()


class TestToastStaysOptIn:
    def test_the_curated_set_does_not_turn_desktop_notifications_on(self):
        """Deliberate: notif/toast_enabled default False is a tested decision
        (tests/test_first_run_notif_optin.py), and the curated rules surface
        in-app regardless. Enabling rules must not silently start showing OS
        balloons to an existing install that never asked for them."""
        import pathlib
        root = pathlib.Path(__file__).resolve().parent.parent
        for rel in ("modules/alert_audit.py", "ui/pages/notifications_page.py",
                    "ui/dashboard.py"):
            src = (root / rel).read_text(encoding="utf-8")
            for line in src.splitlines():
                if "notif/toast_enabled" in line and "setValue" not in line:
                    assert "True" not in line, (
                        f"{rel} now defaults desktop toasts ON: {line.strip()}"
                    )
