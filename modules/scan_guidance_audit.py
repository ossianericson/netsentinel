"""
scan_guidance_audit.py — pure-Python self-test for scan-guidance wiring.

Sibling to modules/alert_audit.py, same shape: pure Python (ARCH RULE 3),
returns AuditFinding(code, ok, detail), nothing here raises on a failed
invariant — a FAIL is a normal, expected result until the phase that fixes
the underlying defect lands.

Three families of check:
  - Data-driven (CTA_LABELS_RESOLVE, CTA_TABLE_PARITY): take already-loaded
    Python data as plain arguments, so they are synthetically unit-testable
    with no filesystem/import dependency of their own.
  - Source-tree (AUDIT_STATE_WIRED, AUDIT_CARD_PARITY, AUDIT_QUEUE_TERMINATES,
    GUIDANCE_FITS, GRADE_INPUTS_GATED): AST-only inspection of the real repo
    tree, mirroring alert_audit.py::audit_source_tree()'s style — no import
    of the (PyQt-laden) ui/ files being inspected, so this module stays
    PyQt-free even though it reports on ui/ wiring.
  - Live-database (IDENTITY_CHURN): reads a real NetSentinel.db when one is
    present. Unlike the other two families this can genuinely have nothing to
    check — a fresh install or a CI sandbox has no database yet — and that is
    a PASS, not a violation; see audit_identity_churn()'s own docstring.

Driven by ``python app.py --audit`` (app.py's CLI entry point, alongside the
existing --audit-alerts) and exercised directly by
tests/test_scan_guidance_audit.py.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import AbstractSet, Dict, List, Optional

from modules.alert_audit import AuditFinding

__all__ = [
    "AuditFinding",
    "audit_cta_labels_resolve",
    "audit_cta_table_parity",
    "audit_scan_state_wired",
    "audit_card_parity",
    "audit_queue_terminates",
    "audit_guidance_render_paths",
    "audit_grade_gating",
    "audit_identity_churn",
    "run_all",
]


# ── S3: CTA routing table sanity ───────────────────────────────────────────────

def audit_cta_labels_resolve(
    rule_cta: Dict[str, str], known_labels: AbstractSet[str],
) -> List[AuditFinding]:
    """Every modules.alert_engine_routing.RULE_CTA value must be a real nav
    target — a dead label silently no-ops the 'Fix this' button on every
    alert of that rule_type (RULE-NAV3)."""
    bad = sorted(
        f"{rule_type} -> {page!r}"
        for rule_type, page in rule_cta.items()
        if page not in known_labels
    )
    return [AuditFinding(
        "CTA_LABELS_RESOLVE", not bad,
        "Every RULE_CTA target is a known nav label" if not bad
        else f"RULE_CTA targets that resolve to no real page: {', '.join(bad)}",
    )]


def _cta_page_for_rule_name(rule_name: str, table: Dict[str, str]) -> Optional[str]:
    """Mirrors ui.pages.notif_alert_history._cta_page_for_rule()'s substring
    match — duplicated here (rather than imported) so this module never has
    to import that PyQt-laden file just to read its lookup table."""
    lower = rule_name.lower()
    for pattern, page in table.items():
        if pattern in lower:
            return page
    return None


def audit_cta_table_parity(
    rule_cta: Dict[str, str], rule_name_cta: Dict[str, str], rules: list,
) -> List[AuditFinding]:
    """RULE_CTA (keyed by rule_type) and notif_alert_history's _RULE_NAME_CTA
    (keyed by rule-name substring) are two independent tables with no parity
    check between them (S3). Flag every rule where both tables have an
    opinion and disagree. ``rules`` is a list of AlertRule-like objects
    exposing .name and .rule_type."""
    mismatches = []
    for rule in rules:
        history_target = _cta_page_for_rule_name(rule.name, rule_name_cta)
        routing_target = rule_cta.get(rule.rule_type)
        if history_target and routing_target and history_target != routing_target:
            mismatches.append(
                f"{rule.rule_type} ({rule.name!r}): RULE_CTA={routing_target!r} "
                f"vs notif_alert_history={history_target!r}"
            )
    return [AuditFinding(
        "CTA_TABLE_PARITY", not mismatches,
        "RULE_CTA and notif_alert_history's CTA table agree on every overlapping rule"
        if not mismatches
        else "Disagreeing CTA targets: " + "; ".join(mismatches),
    )]


# ── Shared source-tree helpers ─────────────────────────────────────────────────

def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _parse(path: Path) -> Optional[ast.Module]:
    src = _read(path)
    if not src:
        return None
    try:
        return ast.parse(src, filename=str(path))
    except SyntaxError:
        return None


def _extract_dict_literal(path: Path, var_name: str) -> Dict[str, str]:
    """AST-only extraction of a module-level ``var_name = {...}`` string dict
    — handles both a plain assignment and an annotated one
    (``var_name: dict[str, str] = {...}``, which is a separate ast.AnnAssign
    node, not ast.Assign)."""
    tree = _parse(path)
    if tree is None:
        return {}
    for node in ast.walk(tree):
        target_matches = (
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == var_name for t in node.targets)
        ) or (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name) and node.target.id == var_name
        )
        if target_matches and node.value is not None:  # type: ignore[attr-defined]
            try:
                value = ast.literal_eval(node.value)  # type: ignore[attr-defined]
            except (ValueError, SyntaxError):
                return {}
            return value if isinstance(value, dict) else {}
    return {}


def _build_pro_nav_body(repo_root: Path) -> str:
    src = _read(repo_root / "ui" / "nav" / "builder.py")
    m = re.search(r"(    def _build_pro_nav\(.*?)(?=\n    def |\Z)", src, re.DOTALL)
    return m.group(1) if m else ""


def _registered_audit_labels(repo_root: Path) -> List[str]:
    body = _build_pro_nav_body(repo_root)
    return re.findall(r'_nav_add_rail_item\(\s*"([^"]+)"[^\n]*audit_item=True', body)


class _ScanStateVisitor(ast.NodeVisitor):
    """Collects the label passed to every ``self._nav_set_scan_state(...)``
    call. RULE-NAV1 already ratchets this router to zero string literals, so
    every real call site passes a NavLabel attribute (``L.X``)."""

    def __init__(self) -> None:
        self.label_attrs: List[str] = []  # NavLabel member NAMEs, e.g. "TLS_EXPOSURE"

    def visit_Call(self, node: ast.Call) -> None:
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "_nav_set_scan_state"
            and node.args
            and isinstance(node.args[0], ast.Attribute)
        ):
            self.label_attrs.append(node.args[0].attr)
        self.generic_visit(node)


def _scan_state_producer_label_names(repo_root: Path) -> AbstractSet[str]:
    visitor = _ScanStateVisitor()
    for path in sorted((repo_root / "ui").rglob("*.py")):
        tree = _parse(path)
        if tree is not None:
            visitor.visit(tree)
    return set(visitor.label_attrs)


def _card_labels(repo_root: Path) -> AbstractSet[str]:
    src = _read(repo_root / "ui" / "pages" / "security_overview_page.py")
    m = re.search(r"_AUDIT_SCAN_LABELS[^=]*=\s*\((.*?)\n\)", src, re.DOTALL)
    if not m:
        return set()
    try:
        from ui.nav.labels import NavLabel
    except ImportError:
        return set()
    name_to_value = {member.name: str(member) for member in NavLabel}
    names = re.findall(r"L\.([A-Z_0-9]+)", m.group(1))
    return {name_to_value[n] for n in names if n in name_to_value}


# Registered audit_item=True pages that are containers/aggregators, not scans
# in their own right — never expected to call _nav_set_scan_state themselves.
_SCAN_STATE_EXEMPT_LABELS: AbstractSet[str] = frozenset({"Security Overview"})


# ── S1 / S6: Security-audit scan-state wiring ──────────────────────────────────

def audit_scan_state_wired(
    registered_audit_labels: List[str],
    producer_label_values: AbstractSet[str],
    exempt: AbstractSet[str] = _SCAN_STATE_EXEMPT_LABELS,
) -> List[AuditFinding]:
    """Every audit_item=True nav page must have at least one
    _nav_set_scan_state producer, or its Scan Status row reads 'Never run'
    forever even after a real scan completes (RULE-SS1)."""
    missing = sorted(
        label for label in registered_audit_labels
        if label not in exempt and label not in producer_label_values
    )
    return [AuditFinding(
        "AUDIT_STATE_WIRED", not missing,
        "Every audit_item=True page has a _nav_set_scan_state producer" if not missing
        else f"Registered as an audit page but never reports scan state (RULE-SS1): {', '.join(missing)}",
    )]


def audit_card_parity(
    registered_audit_labels: List[str],
    producer_label_values: AbstractSet[str],
    card_labels: AbstractSet[str],
    exempt: AbstractSet[str] = _SCAN_STATE_EXEMPT_LABELS,
) -> List[AuditFinding]:
    """_AUDIT_SCAN_LABELS (the Scan Status card's rows) must (a) only name
    registered audit pages and (b) include every audit page that actually
    reports scan state — otherwise a real, wired scan never gets a row (S6)."""
    registered_set = set(registered_audit_labels)
    not_registered = sorted(card_labels - registered_set)
    wired_but_no_row = sorted(
        label for label in registered_audit_labels
        if label not in exempt
        and label in producer_label_values
        and label not in card_labels
    )
    problems = []
    if not_registered:
        problems.append(f"Scan Status card rows not registered as audit pages: {', '.join(not_registered)}")
    if wired_but_no_row:
        problems.append(
            "Audit pages that report scan state but have no Scan Status card row: "
            + ", ".join(wired_but_no_row)
        )
    return [AuditFinding(
        "AUDIT_CARD_PARITY", not problems,
        "Scan Status card rows exactly match state-reporting audit pages" if not problems
        else "; ".join(problems),
    )]


# ── S1: security-audit queue termination ────────────────────────────────────────

# Branches that dispatch an async worker and advance the queue from a
# *different* file's completion handler, rather than inline in the branch
# itself — verified by code review at the cited location. Same convention as
# alert_audit.py's ALLOWED_TRAY_FUNCTIONS: a manually-audited allow-list, not
# something an AST walk alone could infer across file boundaries.
_QUEUE_ADVANCING_ELSEWHERE: Dict[str, str] = {
    "PORT_SCAN_TCP":       "scan_wiring.py::_on_syn_result() calls _advance_security_audit()",
    "EXPOSED_TO_INTERNET": "scan_wiring.py::_on_exposure_result() calls _advance_security_audit()",
    "CVE_LOOKUP":          "tabs_recon.py::_start_cve_lookup() advances on both its paths",
    "TLS_EXPOSURE":        "dashboard.py::_on_tls_check_done() advances via the _awaiting_tls_check flag",
    "THREAT_INTEL":        "dashboard.py::_on_threat_intel_scan_complete/_error/_not_testable() "
                            "advance via the _awaiting_threat_intel flag",
}


def _is_label_equality_test(test: ast.expr) -> bool:
    return (
        isinstance(test, ast.Compare)
        and isinstance(test.left, ast.Name) and test.left.id == "label"
        and len(test.ops) == 1 and isinstance(test.ops[0], ast.Eq)
        and len(test.comparators) == 1 and isinstance(test.comparators[0], ast.Attribute)
    )


def _calls_advance_somewhere(body: list) -> bool:
    for stmt in body:
        for node in ast.walk(stmt):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "_advance_security_audit"
            ):
                return True
    return False


def _find_stalled_labels(
    func: ast.FunctionDef, advancing_elsewhere: Dict[str, str] = _QUEUE_ADVANCING_ELSEWHERE,
) -> List[str]:
    stalled = []
    for node in ast.walk(func):
        if not (isinstance(node, ast.If) and _is_label_equality_test(node.test)):
            continue
        label_name = node.test.comparators[0].attr  # type: ignore[attr-defined]
        if label_name in advancing_elsewhere:
            continue
        if _calls_advance_somewhere(node.body):
            continue
        stalled.append(label_name)
    return sorted(set(stalled))


def audit_queue_terminates(repo_root: Path) -> List[AuditFinding]:
    """Every ``elif label == L.X:`` branch inside
    Dashboard._advance_security_audit must eventually call
    _advance_security_audit() again, or the queue silently stalls on that
    tool (S1 — exactly how Threat Intel currently stalls the Overview 'Run'
    button after just one tool)."""
    tree = _parse(repo_root / "ui" / "dashboard.py")
    if tree is None:
        return [AuditFinding("AUDIT_QUEUE_TERMINATES", False, "ui/dashboard.py could not be parsed")]

    func = next(
        (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_advance_security_audit"),
        None,
    )
    if func is None:
        return [AuditFinding("AUDIT_QUEUE_TERMINATES", False, "_advance_security_audit not found in ui/dashboard.py")]

    stalled = _find_stalled_labels(func)
    return [AuditFinding(
        "AUDIT_QUEUE_TERMINATES", not stalled,
        "Every dispatch branch in _advance_security_audit reaches an advance call" if not stalled
        else f"Branches that dispatch a tool and never advance the queue: {', '.join(stalled)}",
    )]


# ── S5: guidance-render-path budget ──────────────────────────────────────────────

# (relative path, method name, sliced-variable-name substring, minimum safe
# slice bound) — a slice shorter than this, applied to a message-like
# variable inside the named method, can cut a message before its
# ACTION_STEPS suffix ever reaches the screen. The variable-name filter keeps
# this from flagging unrelated short slices in the same method (e.g.
# `alerts[:5]`, which limits row COUNT, not message length). Add a render
# surface here as it's found to truncate; remove it once its fix stops
# blind-slicing.
_GUIDANCE_RENDER_SITES: List[tuple] = [
    ("ui/pages/home_data_mixin.py", "set_pending_alert_rows", "msg", 100),
]


def _find_short_slices(func: ast.FunctionDef, name_substring: str, min_safe: int) -> List[int]:
    lines = []
    for node in ast.walk(func):
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name) and name_substring in node.value.id
            and isinstance(node.slice, ast.Slice)
            and node.slice.lower is None
            and isinstance(node.slice.upper, ast.Constant)
            and isinstance(node.slice.upper.value, int)
            and node.slice.upper.value < min_safe
        ):
            lines.append(node.lineno)
    return lines


def audit_guidance_render_paths(repo_root: Path) -> List[AuditFinding]:
    """No alert-render path may blind-truncate a message short enough to cut
    off its ACTION_STEPS suffix (S5). Live message lengths run 116-181 chars;
    append_action() appends the action steps at the END of the message, so a
    render path that slices to a small fixed bound structurally can't show
    them."""
    offenders = []
    for rel, method_name, name_substring, min_safe in _GUIDANCE_RENDER_SITES:
        tree = _parse(repo_root / rel)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == method_name:
                for lineno in _find_short_slices(node, name_substring, min_safe):
                    offenders.append(f"{rel}:{lineno} slices below {min_safe} chars inside {method_name}()")
    return [AuditFinding(
        "GUIDANCE_FITS", not offenders,
        "No alert render path truncates a message below its action-step budget" if not offenders
        else "Render paths that can cut a message before its action steps: " + "; ".join(offenders),
    )]


# ── S7: grade-dimension gating ────────────────────────────────────────────────

def _is_store_presence_test(test: ast.expr) -> bool:
    return (
        isinstance(test, ast.Compare)
        and isinstance(test.left, ast.Attribute) and test.left.attr == "_store"
        and len(test.ops) == 1 and isinstance(test.ops[0], ast.IsNot)
        and len(test.comparators) == 1
        and isinstance(test.comparators[0], ast.Constant) and test.comparators[0].value is None
    )


def _find_store_gated_dims_appends(func: ast.FunctionDef) -> List[int]:
    lines = []
    for node in ast.walk(func):
        if isinstance(node, ast.If) and _is_store_presence_test(node.test):
            for inner in ast.walk(node):
                if (
                    isinstance(inner, ast.Call)
                    and isinstance(inner.func, ast.Attribute) and inner.func.attr == "append"
                    and isinstance(inner.func.value, ast.Name) and inner.func.value.id == "dims"
                ):
                    lines.append(inner.lineno)
    return lines


def audit_grade_gating(repo_root: Path) -> List[AuditFinding]:
    """No Security Overview grade dimension may be counted on store-presence
    alone (``if self._store is not None:``) — that's data persistence, not
    proof the scan that produces it ever ran (S7). Sibling dimensions already
    gate on a *_scan_done flag; store-presence dimensions should too."""
    tree = _parse(repo_root / "ui" / "pages" / "security_overview_page.py")
    offenders: List[str] = []
    if tree is not None:
        func = next(
            (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_update_security_grade"),
            None,
        )
        if func is not None:
            offenders = [
                f"ui/pages/security_overview_page.py:{ln} appends a grade dimension gated only on "
                "`self._store is not None`"
                for ln in _find_store_gated_dims_appends(func)
            ]
    return [AuditFinding(
        "GRADE_INPUTS_GATED", not offenders,
        "No grade dimension is counted on store-presence alone" if not offenders
        else "Store-presence-gated (not scan-completion-gated) dimensions: " + "; ".join(offenders),
    )]


# ── S8: Device Identity Program — classification churn regression gate ─────

# Acceptance criteria from the Device Identity & Classification Program plan,
# measured against docs/spikes/device-identity-baseline.md's baseline (47.5%
# no-op share, 7.08 class_changed/device-day): criterion 1 (no-op share -> 0)
# and criterion 2 (per-device-day <= 0.5). A trailing window, not full
# history: device_events is an append-only audit log nothing ever prunes, so
# the pre-fix churn baked into old rows would keep this permanently failing
# if it were measured over all time. 7 days matches the plan's own "after a
# normal week of use" framing for these criteria.
IDENTITY_CHURN_WINDOW_DAYS = 7.0
IDENTITY_CHURN_MAX_PER_DEVICE_DAY = 0.5
IDENTITY_CHURN_MAX_NOOP_SHARE = 0.0


def audit_identity_churn(db_path: Optional[Path] = None) -> List[AuditFinding]:
    """class_changed churn must not regress past the Device Identity
    Program's acceptance thresholds: 0% pure no-op writes (old_value ==
    new_value -- the record_device_change_event() guard from that program's
    Phase 1) and <= 0.5 class_changed events per device-day, both measured
    over the trailing IDENTITY_CHURN_WINDOW_DAYS days.

    The no-op check is bounded below by
    metric_store_schema.IDENTITY_NOOP_GUARD_META_KEY, a meta-table timestamp
    re-stamped every time a build carrying the no-op guard opens the database.
    Without this, every existing install shows a hard FAIL for a full
    IDENTITY_CHURN_WINDOW_DAYS after upgrading -- the trailing window still
    holds pre-guard no-op rows nothing will ever rewrite, indistinguishable
    from a genuine regression. A guard-bounded no-op window turns that into a
    check that fails on the first *post-guard* no-op instead.

    The marker advances rather than being written once (RULE-DBG6), because a
    single database is routinely shared by more than one build -- the Store
    package auto-starting at login while a newer build is tested, a downgrade,
    a portable copy beside an installed one. A write-once marker cannot see an
    OLDER, unguarded build writing violating rows AFTER it was stamped, and
    reports them as a live regression against code that cannot produce them
    (observed on the reference install: 10 no-op rows written by a pre-v2.2.4
    Store package the morning after a v2.2.5 build stamped the marker). An
    advancing marker scopes the no-op check to the guarded build currently in
    charge -- the only span it can honestly attribute. That deliberately
    narrows this live check to the current session; the durable regression gate
    is tests/test_identity_churn_ratchet.py, which drives the real arbitrate()
    and the real write choke point and does not depend on any install's state.

    The per-device-day churn check is intentionally left on its own full
    IDENTITY_CHURN_WINDOW_DAYS window -- only the no-op check moves. An absent
    marker (a database never opened by a guarded build, or the "no history
    yet" early-return above) falls back to the full window, which is the
    original, stricter behaviour -- never a false PASS.

    PASSes with an explanatory detail when there is nothing to measure yet --
    no database at all, or a database with no device_events history -- since
    this is a live-database regression gate, not a structural correctness
    check the way its sibling audits are. Every SQL string here is a literal
    with no interpolated identifiers, so it carries no injection surface
    despite not going through MetricStore's public API (this module is
    intentionally DB-independent of MetricStore, mirroring alert_audit.py).
    """
    import datetime
    import sqlite3

    from modules.metric_store_schema import IDENTITY_NOOP_GUARD_META_KEY

    if db_path is None:
        from modules.utils import get_app_data_dir
        db_path = get_app_data_dir() / "NetSentinel.db"
    if not db_path.exists():
        return [AuditFinding(
            "IDENTITY_CHURN", True,
            f"No database at {db_path} — check skipped (nothing to measure yet)",
        )]

    uri = "file:" + str(db_path).replace("\\", "/") + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        bounds = conn.execute("SELECT MIN(ts), MAX(ts) FROM device_events").fetchone()
        lo, hi = (bounds[0], bounds[1]) if bounds else (None, None)
        if lo is None or hi is None:
            return [AuditFinding(
                "IDENTITY_CHURN", True,
                "No device_events history yet — check skipped",
            )]
        hi_dt = datetime.datetime.strptime(hi, "%Y-%m-%d %H:%M:%S")
        since = (hi_dt - datetime.timedelta(days=IDENTITY_CHURN_WINDOW_DAYS)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        guard_row = conn.execute(
            "SELECT value FROM meta WHERE key = ?", (IDENTITY_NOOP_GUARD_META_KEY,)
        ).fetchone()
        guard_since = guard_row[0] if guard_row else None
        noop_since = max(since, guard_since) if guard_since else since

        total = conn.execute(
            "SELECT COUNT(*) FROM device_events WHERE event_type='class_changed' AND ts >= ?",
            (since,),
        ).fetchone()[0]
        noop_total = conn.execute(
            "SELECT COUNT(*) FROM device_events WHERE event_type='class_changed' AND ts >= ?",
            (noop_since,),
        ).fetchone()[0]
        noop = conn.execute(
            "SELECT COUNT(*) FROM device_events WHERE event_type='class_changed' "
            "AND ts >= ? AND old_value = new_value",
            (noop_since,),
        ).fetchone()[0]
        n_devices = conn.execute("SELECT COUNT(*) FROM known_device").fetchone()[0]
    finally:
        conn.close()

    noop_share = (noop / noop_total) if noop_total else 0.0
    per_device_day = (
        total / IDENTITY_CHURN_WINDOW_DAYS / n_devices if n_devices else 0.0
    )

    problems = []
    if noop_share > IDENTITY_CHURN_MAX_NOOP_SHARE:
        window_desc = (
            f"since the no-op guard was recorded active ({noop_since})"
            if noop_since != since
            else f"in the last {IDENTITY_CHURN_WINDOW_DAYS:.0f} days"
        )
        problems.append(
            f"{noop}/{noop_total} class_changed rows ({noop_share:.1%}) are pure "
            f"no-ops (old_value == new_value) {window_desc} — the "
            "record_device_change_event() no-op guard should make this 0"
        )
    if per_device_day > IDENTITY_CHURN_MAX_PER_DEVICE_DAY:
        problems.append(
            f"class_changed churn is {per_device_day:.2f}/device-day over the "
            f"last {IDENTITY_CHURN_WINDOW_DAYS:.0f} days, above the "
            f"{IDENTITY_CHURN_MAX_PER_DEVICE_DAY} ceiling"
        )
    return [AuditFinding(
        "IDENTITY_CHURN", not problems,
        "class_changed churn within the Device Identity Program's thresholds"
        if not problems else "; ".join(problems),
    )]


# ── CLI entry point ────────────────────────────────────────────────────────────

def run_all(repo_root: Path) -> List[AuditFinding]:
    """Every scan-guidance invariant, using the real repo tree and real
    lookup tables — what ``python app.py --audit`` runs."""
    from modules.alert_engine_routing import RULE_CTA
    from modules.alert_suppressor import _default_rules
    from ui.nav.labels import KNOWN_LABELS

    rule_name_cta = _extract_dict_literal(
        repo_root / "ui" / "pages" / "notif_alert_history.py", "_RULE_NAME_CTA",
    )
    registered = _registered_audit_labels(repo_root)
    producers = _scan_state_producer_label_names_as_values(repo_root)
    card_labels = _card_labels(repo_root)

    findings: List[AuditFinding] = []
    findings += audit_cta_labels_resolve(RULE_CTA, KNOWN_LABELS)
    findings += audit_cta_table_parity(RULE_CTA, rule_name_cta, _default_rules())
    findings += audit_scan_state_wired(registered, producers)
    findings += audit_card_parity(registered, producers, card_labels)
    findings += audit_queue_terminates(repo_root)
    findings += audit_guidance_render_paths(repo_root)
    findings += audit_grade_gating(repo_root)
    findings += audit_identity_churn()
    return findings


def _scan_state_producer_label_names_as_values(repo_root: Path) -> AbstractSet[str]:
    """Resolve the NavLabel member NAMEs collected by _ScanStateVisitor to
    their label VALUEs, so callers can compare directly against registered
    label strings (both are plain str; NavLabel members ARE str instances,
    but the AST only ever sees the bare attribute name, e.g. "TLS_EXPOSURE")."""
    from ui.nav.labels import NavLabel

    name_to_value = {member.name: str(member) for member in NavLabel}
    names = _scan_state_producer_label_names(repo_root)
    return {name_to_value[n] for n in names if n in name_to_value}
