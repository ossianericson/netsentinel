"""
Tests for modules/scan_guidance_audit.py — the --audit scan-guidance diagnostic.

CTA_LABELS_RESOLVE and CTA_TABLE_PARITY are pure-function checks against
injected data, so they get synthetic RED/GREEN unit coverage directly.
AUDIT_STATE_WIRED / AUDIT_CARD_PARITY / GUIDANCE_FITS / GRADE_INPUTS_GATED
take injected data too but their real producers are AST-derived, so each
also gets a synthetic-fixture test proving the checker logic AND a real-tree
test documenting today's known state. AUDIT_QUEUE_TERMINATES is pure
AST-over-source and gets a synthetic tmp_path fixture plus a real-tree test.

Every "real tree" test here is expected to FAIL until the Phase-3 fix named
in its docstring lands — mirroring alert_audit.py::audit_source_tree()'s
established convention for this codebase.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _finding(findings, code):
    return next(f for f in findings if f.code == code)


# ── audit_cta_labels_resolve ──────────────────────────────────────────────────

class TestCtaLabelsResolve:
    def test_fails_when_a_target_is_not_a_known_label(self):
        from modules.scan_guidance_audit import audit_cta_labels_resolve

        findings = audit_cta_labels_resolve(
            rule_cta={"HOST_DOWN": "Inventory"},
            known_labels=frozenset({"Inventory Changes", "Devices"}),
        )
        f = _finding(findings, "CTA_LABELS_RESOLVE")
        assert f.ok is False
        assert "HOST_DOWN" in f.detail

    def test_passes_when_every_target_is_known(self):
        from modules.scan_guidance_audit import audit_cta_labels_resolve

        findings = audit_cta_labels_resolve(
            rule_cta={"HOST_DOWN": "Inventory Changes"},
            known_labels=frozenset({"Inventory Changes", "Devices"}),
        )
        assert _finding(findings, "CTA_LABELS_RESOLVE").ok is True

    def test_real_rule_cta_table_resolves_after_phase_3_2(self):
        """S3: HOST_DOWN/HOST_DEGRADED/DEVICE_GONE used to target the dead
        label 'Inventory' and CERT_EXPIRY/CERT_EXPIRED the dead label
        'TLS & Cert Monitor'. Fixed in Phase 3.2 — RULE_CTA's values are now
        ui.nav.labels.NavLabel members."""
        from modules.alert_engine_routing import RULE_CTA
        from modules.scan_guidance_audit import audit_cta_labels_resolve
        from ui.nav.labels import KNOWN_LABELS

        findings = audit_cta_labels_resolve(RULE_CTA, KNOWN_LABELS)
        assert _finding(findings, "CTA_LABELS_RESOLVE").ok is True


# ── audit_cta_table_parity ────────────────────────────────────────────────────

class _FakeRule:
    def __init__(self, name, rule_type):
        self.name = name
        self.rule_type = rule_type


class TestCtaTableParity:
    def test_passes_when_tables_agree(self):
        from modules.scan_guidance_audit import audit_cta_table_parity

        findings = audit_cta_table_parity(
            rule_cta={"HOST_DOWN": "Inventory Changes"},
            rule_name_cta={"host down": "Inventory Changes"},
            rules=[_FakeRule("Host Down", "HOST_DOWN")],
        )
        assert _finding(findings, "CTA_TABLE_PARITY").ok is True

    def test_fails_when_tables_disagree(self):
        from modules.scan_guidance_audit import audit_cta_table_parity

        findings = audit_cta_table_parity(
            rule_cta={"HOST_DOWN": "Inventory"},
            rule_name_cta={"host down": "Inventory Changes"},
            rules=[_FakeRule("Host Down", "HOST_DOWN")],
        )
        f = _finding(findings, "CTA_TABLE_PARITY")
        assert f.ok is False
        assert "HOST_DOWN" in f.detail

    def test_passes_when_only_one_table_has_an_opinion(self):
        """A rule_type absent from one table is not a disagreement — it's
        just uncovered by that table."""
        from modules.scan_guidance_audit import audit_cta_table_parity

        findings = audit_cta_table_parity(
            rule_cta={"HOST_DOWN": "Inventory"},
            rule_name_cta={},
            rules=[_FakeRule("Host Down", "HOST_DOWN")],
        )
        assert _finding(findings, "CTA_TABLE_PARITY").ok is True

    def test_real_tables_agree_after_phase_3_2(self):
        """S3: RULE_CTA used to say 'Inventory' (dead) while
        notif_alert_history's table said 'Inventory Changes' (real) for the
        same rule — same shape for CERT_EXPIRY/CERT_EXPIRED and NEW_CVE (the
        6th disagreement the harness itself surfaced, beyond the plan's
        original 5). Fixed in Phase 3.2."""
        from modules.alert_engine_routing import RULE_CTA
        from modules.alert_suppressor import _default_rules
        from modules.scan_guidance_audit import audit_cta_table_parity, _extract_dict_literal

        rule_name_cta = _extract_dict_literal(
            REPO_ROOT / "ui" / "pages" / "notif_alert_history.py", "_RULE_NAME_CTA",
        )
        findings = audit_cta_table_parity(RULE_CTA, rule_name_cta, _default_rules())
        assert _finding(findings, "CTA_TABLE_PARITY").ok is True


# ── audit_scan_state_wired / audit_card_parity (synthetic) ───────────────────

class TestScanStateWiredSynthetic:
    def test_fails_when_a_registered_label_has_no_producer(self):
        from modules.scan_guidance_audit import audit_scan_state_wired

        findings = audit_scan_state_wired(
            registered_audit_labels=["Threat Intel", "Port Scan (TCP)"],
            producer_label_values={"Port Scan (TCP)"},
        )
        f = _finding(findings, "AUDIT_STATE_WIRED")
        assert f.ok is False
        assert "Threat Intel" in f.detail

    def test_passes_when_every_registered_label_has_a_producer(self):
        from modules.scan_guidance_audit import audit_scan_state_wired

        findings = audit_scan_state_wired(
            registered_audit_labels=["Port Scan (TCP)"],
            producer_label_values={"Port Scan (TCP)"},
        )
        assert _finding(findings, "AUDIT_STATE_WIRED").ok is True

    def test_exempt_labels_are_never_flagged(self):
        from modules.scan_guidance_audit import audit_scan_state_wired

        findings = audit_scan_state_wired(
            registered_audit_labels=["Security Overview"],
            producer_label_values=set(),
        )
        assert _finding(findings, "AUDIT_STATE_WIRED").ok is True


class TestCardParitySynthetic:
    def test_fails_when_a_wired_page_has_no_card_row(self):
        from modules.scan_guidance_audit import audit_card_parity

        findings = audit_card_parity(
            registered_audit_labels=["Device Risk Score"],
            producer_label_values={"Device Risk Score"},
            card_labels=set(),
        )
        f = _finding(findings, "AUDIT_CARD_PARITY")
        assert f.ok is False
        assert "Device Risk Score" in f.detail

    def test_fails_when_a_card_row_is_not_a_registered_page(self):
        from modules.scan_guidance_audit import audit_card_parity

        findings = audit_card_parity(
            registered_audit_labels=[],
            producer_label_values=set(),
            card_labels={"Threat Intel"},
        )
        f = _finding(findings, "AUDIT_CARD_PARITY")
        assert f.ok is False
        assert "Threat Intel" in f.detail

    def test_passes_when_card_matches_wired_pages_exactly(self):
        from modules.scan_guidance_audit import audit_card_parity

        findings = audit_card_parity(
            registered_audit_labels=["Device Risk Score"],
            producer_label_values={"Device Risk Score"},
            card_labels={"Device Risk Score"},
        )
        assert _finding(findings, "AUDIT_CARD_PARITY").ok is True


# ── real-tree integration: S1 / S6 ────────────────────────────────────────────

class TestScanStateWiredRealTree:
    def test_every_registered_audit_page_reports_scan_state_after_phase_3_6(self):
        """S1/S6: Threat Intel, CVE Tracker, and DHCP Rogue Monitor were the
        three registered audit pages that never called _nav_set_scan_state
        anywhere. Fixed in Phase 3.1 (Threat Intel) and Phase 3.6 (CVE
        Tracker's new data_refreshed signal; DHCP Rogue Monitor's worker
        result/error now call _nav_set_scan_state instead of the older,
        registry-blind _set_flyout_dot)."""
        from modules.scan_guidance_audit import (
            _registered_audit_labels, _scan_state_producer_label_names_as_values,
            audit_scan_state_wired,
        )

        registered = _registered_audit_labels(REPO_ROOT)
        producers = _scan_state_producer_label_names_as_values(REPO_ROOT)
        findings = audit_scan_state_wired(registered, producers)
        assert _finding(findings, "AUDIT_STATE_WIRED").ok is True


class TestCardParityRealTree:
    def test_card_matches_wired_pages_after_phase_3_6(self):
        """S6: Device Risk Score, Windows Shares (SMB), Recon Plugins,
        Private Endpoint Check, Cloud Metadata Probe, CVE Tracker and DHCP
        Rogue Monitor all report scan state but were absent from
        _AUDIT_SCAN_LABELS. Fixed in Phase 3.6 by reconciling the card."""
        from modules.scan_guidance_audit import (
            _registered_audit_labels, _scan_state_producer_label_names_as_values,
            _card_labels, audit_card_parity,
        )

        registered = _registered_audit_labels(REPO_ROOT)
        producers = _scan_state_producer_label_names_as_values(REPO_ROOT)
        card_labels = _card_labels(REPO_ROOT)
        findings = audit_card_parity(registered, producers, card_labels)
        assert _finding(findings, "AUDIT_CARD_PARITY").ok is True


# ── audit_queue_terminates (synthetic + real) ─────────────────────────────────

_SYNTHETIC_DASHBOARD_STALLED = '''
class Dashboard:
    def _advance_security_audit(self):
        if not self._pending_security_tools:
            return
        label = self._pending_security_tools.pop(0)
        if label == L.PORT_SCAN_TCP:
            self._start_syn_scan()
        elif label == L.SOME_UNWIRED_TOOL:
            self._some_page._run_refresh()
        else:
            self._advance_security_audit()
'''

_SYNTHETIC_DASHBOARD_CLEAN = '''
class Dashboard:
    def _advance_security_audit(self):
        if not self._pending_security_tools:
            return
        label = self._pending_security_tools.pop(0)
        if label == L.PORT_SCAN_TCP:
            self._start_syn_scan()
        elif label == L.DEVICE_RISK_SCORE:
            self._run_risk_scorer()
            self._advance_security_audit()
        else:
            self._advance_security_audit()
'''


class TestQueueTerminatesSynthetic:
    def test_flags_a_branch_that_never_advances(self, tmp_path):
        from modules.scan_guidance_audit import audit_queue_terminates

        (tmp_path / "ui").mkdir()
        (tmp_path / "ui" / "dashboard.py").write_text(_SYNTHETIC_DASHBOARD_STALLED, encoding="utf-8")
        findings = audit_queue_terminates(tmp_path)
        f = _finding(findings, "AUDIT_QUEUE_TERMINATES")
        assert f.ok is False
        assert "SOME_UNWIRED_TOOL" in f.detail
        assert "PORT_SCAN_TCP" not in f.detail  # allow-listed elsewhere

    def test_passes_when_every_branch_advances_or_is_allow_listed(self, tmp_path):
        from modules.scan_guidance_audit import audit_queue_terminates

        (tmp_path / "ui").mkdir()
        (tmp_path / "ui" / "dashboard.py").write_text(_SYNTHETIC_DASHBOARD_CLEAN, encoding="utf-8")
        findings = audit_queue_terminates(tmp_path)
        assert _finding(findings, "AUDIT_QUEUE_TERMINATES").ok is True


class TestQueueTerminatesRealTree:
    def test_every_branch_advances_after_phase_3_1(self):
        """S1: the Threat Intel branch used to fire _run_refresh() and
        return, with no branch nor any allow-listed downstream handler
        advancing the queue. Fixed in Phase 3.1 — the dashboard's new
        _on_threat_intel_scan_complete/_error/_not_testable handlers now
        advance it, added to _QUEUE_ADVANCING_ELSEWHERE."""
        from modules.scan_guidance_audit import audit_queue_terminates

        findings = audit_queue_terminates(REPO_ROOT)
        f = _finding(findings, "AUDIT_QUEUE_TERMINATES")
        assert f.ok is True


# ── audit_guidance_render_paths ───────────────────────────────────────────────

class TestGuidanceFitsRealTree:
    def test_home_action_card_no_longer_truncates_after_phase_3_3(self):
        """S5: home_data_mixin.py's set_pending_alert_rows() used to slice to
        msg[:50] — live messages run 116-181 chars and append_action() puts
        the -> steps at the end, so they never reached the screen. Fixed in
        Phase 3.3 by dropping the slice and word-wrapping the label instead."""
        from modules.scan_guidance_audit import audit_guidance_render_paths

        findings = audit_guidance_render_paths(REPO_ROOT)
        assert _finding(findings, "GUIDANCE_FITS").ok is True


class TestGuidanceFitsSynthetic:
    def test_passes_when_no_short_slice_exists(self, tmp_path):
        from modules.scan_guidance_audit import audit_guidance_render_paths, _GUIDANCE_RENDER_SITES

        (tmp_path / "ui" / "pages").mkdir(parents=True)
        rel, method_name, _name_substring, _min_safe = _GUIDANCE_RENDER_SITES[0]
        (tmp_path / rel).write_text(
            f"class X:\n    def {method_name}(self, alerts):\n        label_text = f'{{rule}} - {{msg}}'\n",
            encoding="utf-8",
        )
        findings = audit_guidance_render_paths(tmp_path)
        assert _finding(findings, "GUIDANCE_FITS").ok is True

    def test_ignores_a_short_slice_on_an_unrelated_variable(self, tmp_path):
        """alerts[:5] limits row COUNT, not message length — must not be
        flagged as a truncation-before-action-steps defect (S5)."""
        from modules.scan_guidance_audit import audit_guidance_render_paths, _GUIDANCE_RENDER_SITES

        (tmp_path / "ui" / "pages").mkdir(parents=True)
        rel, method_name, _name_substring, _min_safe = _GUIDANCE_RENDER_SITES[0]
        (tmp_path / rel).write_text(
            f"class X:\n    def {method_name}(self, alerts):\n        alerts = alerts[:5]\n",
            encoding="utf-8",
        )
        findings = audit_guidance_render_paths(tmp_path)
        assert _finding(findings, "GUIDANCE_FITS").ok is True


# ── audit_grade_gating ────────────────────────────────────────────────────────

_SYNTHETIC_GRADE_GATED = '''
class Page:
    def _update_security_grade(self):
        dims = []
        if self._port_scan_done:
            dims.append(len(self._port_findings))
        if self._store is not None:
            dims.append(len(self._cve_entries))
            dims.append(len(self._tls_issues))
'''

_SYNTHETIC_GRADE_CLEAN = '''
class Page:
    def _update_security_grade(self):
        dims = []
        if self._port_scan_done:
            dims.append(len(self._port_findings))
        if self._store is not None and self._cve_scan_done:
            dims.append(len(self._cve_entries))
'''


class TestGradeGatingSynthetic:
    def test_flags_a_store_presence_only_gated_append(self, tmp_path):
        from modules.scan_guidance_audit import audit_grade_gating

        (tmp_path / "ui" / "pages").mkdir(parents=True)
        (tmp_path / "ui" / "pages" / "security_overview_page.py").write_text(
            _SYNTHETIC_GRADE_GATED, encoding="utf-8",
        )
        findings = audit_grade_gating(tmp_path)
        f = _finding(findings, "GRADE_INPUTS_GATED")
        assert f.ok is False

    def test_passes_when_store_presence_is_combined_with_a_scan_done_flag(self, tmp_path):
        from modules.scan_guidance_audit import audit_grade_gating

        (tmp_path / "ui" / "pages").mkdir(parents=True)
        (tmp_path / "ui" / "pages" / "security_overview_page.py").write_text(
            _SYNTHETIC_GRADE_CLEAN, encoding="utf-8",
        )
        findings = audit_grade_gating(tmp_path)
        assert _finding(findings, "GRADE_INPUTS_GATED").ok is True


class TestGradeGatingRealTree:
    def test_cve_and_tls_dims_are_gated_on_scan_completion_after_phase_3_7(self):
        """S7: confirmed live in Phase 2 (docs/internal/
        scan-guidance-audit-2026-07-29.md) — a profile with only Port Scan
        (TCP) ever run still had cve_lifecycle/cert_check data counted as
        checked-clean dimensions. Fixed by gating both on the same scan
        registry the Scan Status card itself reads, matching the
        port/cred dimensions' existing *_scan_done pattern."""
        from modules.scan_guidance_audit import audit_grade_gating

        findings = audit_grade_gating(REPO_ROOT)
        assert _finding(findings, "GRADE_INPUTS_GATED").ok is True


# ── audit_identity_churn ─────────────────────────────────────────────────────

def _make_identity_db(tmp_path, events, n_devices=1, base_ts="2026-01-01 00:00:00"):
    """A synthetic NetSentinel.db with `n_devices` known_device rows and
    `events` (list of (old_value, new_value, ts) class_changed rows)."""
    import sqlite3

    from modules.metric_store_schema import _DDL

    path = tmp_path / "NetSentinel.db"
    conn = sqlite3.connect(path)
    conn.executescript(_DDL)
    for i in range(n_devices):
        conn.execute(
            "INSERT INTO known_device (mac, ip, first_seen, last_seen) "
            "VALUES (?, ?, ?, ?)",
            (f"aa:bb:cc:00:00:{i:02x}", f"192.168.1.{i}", 1_780_000_000, 1_780_000_000),
        )
    for old, new, ts in events:
        conn.execute(
            "INSERT INTO device_events (mac, event_type, old_value, new_value, ts) "
            "VALUES ('aa:bb:cc:00:00:00', 'class_changed', ?, ?, ?)",
            (old, new, ts),
        )
    conn.commit()
    conn.close()
    return path


class TestIdentityChurn:
    def test_passes_with_no_database_at_all(self, tmp_path):
        from modules.scan_guidance_audit import audit_identity_churn

        findings = audit_identity_churn(db_path=tmp_path / "nope.db")
        f = _finding(findings, "IDENTITY_CHURN")
        assert f.ok is True
        assert "No database" in f.detail

    def test_passes_with_a_database_but_no_device_events(self, tmp_path):
        from modules.scan_guidance_audit import audit_identity_churn

        db_path = _make_identity_db(tmp_path, events=[], n_devices=1)
        f = _finding(audit_identity_churn(db_path=db_path), "IDENTITY_CHURN")
        assert f.ok is True

    def test_passes_when_churn_and_noop_share_are_both_clean(self, tmp_path):
        from modules.scan_guidance_audit import audit_identity_churn

        db_path = _make_identity_db(tmp_path, events=[
            ("", "Print Server", "2026-01-01 00:00:00"),
        ], n_devices=10)
        f = _finding(audit_identity_churn(db_path=db_path), "IDENTITY_CHURN")
        assert f.ok is True

    def test_fails_on_any_noop_row_in_the_window(self, tmp_path):
        """Phase 1's record_device_change_event() guard should make this
        structurally impossible -- a nonzero share here means a new writer
        somewhere is bypassing it."""
        from modules.scan_guidance_audit import audit_identity_churn

        db_path = _make_identity_db(tmp_path, events=[
            ("Router", "Router", "2026-01-01 00:00:00"),
        ], n_devices=10)
        f = _finding(audit_identity_churn(db_path=db_path), "IDENTITY_CHURN")
        assert f.ok is False
        assert "no-op" in f.detail

    def test_fails_when_per_device_day_ceiling_is_exceeded(self, tmp_path):
        from modules.scan_guidance_audit import (
            IDENTITY_CHURN_MAX_PER_DEVICE_DAY, IDENTITY_CHURN_WINDOW_DAYS,
            audit_identity_churn,
        )

        # 1 device, enough real (non-noop) class_changed events in the window
        # to push per-device-day comfortably over the ceiling.
        n_events = int(IDENTITY_CHURN_MAX_PER_DEVICE_DAY * IDENTITY_CHURN_WINDOW_DAYS) + 5
        events = [
            (f"Type{i}", f"Type{i + 1}", "2026-01-01 00:00:00")
            for i in range(n_events)
        ]
        db_path = _make_identity_db(tmp_path, events=events, n_devices=1)
        f = _finding(audit_identity_churn(db_path=db_path), "IDENTITY_CHURN")
        assert f.ok is False
        assert "device-day" in f.detail

    def test_window_excludes_events_older_than_the_trailing_period(self, tmp_path):
        """A device that churned badly a month ago but is clean now must not
        keep failing the gate forever -- device_events is never pruned."""
        from modules.scan_guidance_audit import audit_identity_churn

        old_noop_events = [
            ("Router", "Router", "2025-11-01 00:00:00") for _ in range(50)
        ]
        recent_clean_event = [("", "Router", "2026-01-01 00:00:00")]
        db_path = _make_identity_db(
            tmp_path, events=old_noop_events + recent_clean_event, n_devices=10,
        )
        f = _finding(audit_identity_churn(db_path=db_path), "IDENTITY_CHURN")
        assert f.ok is True

    def test_included_in_run_all(self):
        from modules.scan_guidance_audit import run_all

        findings = run_all(REPO_ROOT)
        f = _finding(findings, "IDENTITY_CHURN")
        # This is the real installed/dev database (or none) -- just confirm
        # the check ran and produced a real verdict, not that it passes.
        assert f.ok in (True, False)


# ── run_all / CLI wiring ───────────────────────────────────────────────────────

def test_run_all_returns_all_eight_codes():
    from modules.scan_guidance_audit import run_all

    findings = run_all(REPO_ROOT)
    codes = {f.code for f in findings}
    assert codes == {
        "CTA_LABELS_RESOLVE", "CTA_TABLE_PARITY", "AUDIT_STATE_WIRED",
        "AUDIT_CARD_PARITY", "AUDIT_QUEUE_TERMINATES", "GUIDANCE_FITS",
        "GRADE_INPUTS_GATED", "IDENTITY_CHURN",
    }


def test_app_exposes_audit_flag():
    """AST-scan app.py for the '--audit' literal (RULE-T4 companion,
    mirroring test_alert_audit.py::test_app_exposes_audit_alerts_flag)."""
    import ast

    tree = ast.parse(REPO_ROOT.joinpath("app.py").read_text(encoding="utf-8"))
    found = any(
        isinstance(node, ast.Constant) and node.value == "--audit"
        for node in ast.walk(tree)
    )
    assert found, "app.py must reference the literal '--audit'"
