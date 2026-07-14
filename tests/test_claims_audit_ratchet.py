"""
Ratchet test -- the machine-checked driver for docs/internal/claims-audit.md.

Background
----------
The claims audit (docs/internal/claims-audit.md) found ~89 places where the UI, docs, or
help text assert a behaviour the code does not actually deliver -- a column that's always
blank, a status dot pinned to a constant, a documented cross-feature link that was never
wired. Prose rots silently: nothing stops the doc from drifting out of sync with the code
it describes, in either direction (a "fixed" finding never gets removed from the doc, or a
regression reintroduces a defect the doc already covers).

This test is the ratchet, mirroring tests/test_frozen_token_ratchet.py exactly:
  * ``_OPEN_FINDINGS`` is the master ledger -- every key is an OPEN finding ID from the doc.
    Fixing a finding means DELETING its entry here (and its block in the doc) in the same
    commit. This dict may only ever SHRINK.
  * Six structural-invariant checks re-derive specific violation classes LIVE from the
    actual code (not from the doc's prose) and assert the live result matches a small
    per-check baseline. Each fails in both directions: a NEW violation the doc doesn't know
    about fails CI; a violation that silently disappears (fixed without updating the
    baseline+doc) also fails CI, forcing the fix commit to also close out the doc entry.

Structural checks are not exhaustive re-verification of all 89 findings -- most findings
(a wrong help-text sentence, a missing UI element) have no generic AST signature and would
just be re-encoding today's prose as a brittle string test. The six checks below instead
target the finding *shapes* that recur across this audit and are cheap to re-derive
structurally: hand-copied list drift (D), a hardcoded literal masquerading as live registry
state (B), a dispatch table missing entries (E/C), a UI attribute read that doesn't exist
on the dataclass it's reading (A), a declared dataclass field with zero producers (A), and
a duplicate documentation source (D). New findings of these six shapes should extend the
relevant check's baseline (or, if unrelated to all six, only ``_OPEN_FINDINGS`` needs the
new ID -- there is no seventh generic checker to force onto every future violation).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
DOC_PATH = ROOT / "docs" / "internal" / "claims-audit.md"


# ── Master ledger ──────────────────────────────────────────────────────────────
# Each key is an OPEN finding in docs/internal/claims-audit.md.
# Fix the finding -> DELETE the entry (and its block in the doc) in the same commit.
# This dict may only ever SHRINK.
#
# All 89 findings are closed as of the 2026-07 documentation-sync pass. Missing
# high-value functionality uncovered along the way lives in BACKLOG.md instead.
_OPEN_FINDINGS: dict[str, str] = {}


def test_open_findings_match_audit_doc():
    """Every F-nn in _OPEN_FINDINGS must have a block in claims-audit.md, and vice versa.

    Keeps the ledger and the doc from drifting apart in either direction -- delete a
    finding from one without the other and this fails.
    """
    doc = DOC_PATH.read_text(encoding="utf-8")
    doc_ids = set(re.findall(r"\*\*(F-\d+)\s+—", doc))
    ledger_ids = set(_OPEN_FINDINGS.keys())

    missing_from_doc = sorted(ledger_ids - doc_ids)
    missing_from_ledger = sorted(doc_ids - ledger_ids)

    assert not missing_from_doc, (
        f"_OPEN_FINDINGS has IDs with no block in {DOC_PATH.name}: {missing_from_doc} -- "
        "either add the block or remove the ledger entry"
    )
    assert not missing_from_ledger, (
        f"{DOC_PATH.name} has finding blocks not tracked in _OPEN_FINDINGS: {missing_from_ledger} -- "
        "add them to the ledger (or, if fixed, delete the doc block too)"
    )


# ── Check 1: hand-copied rollup lists vs. _AUDIT_SCAN_LABELS (F-04, class D) ────

def _extract_str_list_literal(path: Path, var_name: str) -> list[str] | None:
    """Find the first `var_name = [...]` assignment (module- or function-local) via AST
    and return its string elements. Returns None if not found."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == var_name for t in node.targets):
            continue
        if isinstance(node.value, ast.List):
            return [
                elt.value for elt in node.value.elts
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
            ]
    return None


# Per-list baseline of labels present in _AUDIT_SCAN_LABELS but missing from the
# hand-copied rollup. F-04 closed: both lists now include "Port Scan (UDP)".
_ROLLUP_MISSING_BASELINE: dict[str, frozenset[str]] = {
    "ui/pages/home_data_mixin.py::_SEC_LABELS": frozenset(),
    "ui/widgets/overview_tile.py::_SEC": frozenset(),
}


def test_rollup_lists_match_audit_labels():
    from ui.pages.security_overview_page import _AUDIT_SCAN_LABELS

    audit = {str(lbl) for lbl in _AUDIT_SCAN_LABELS}

    sec_labels = _extract_str_list_literal(ROOT / "ui" / "pages" / "home_data_mixin.py", "_SEC_LABELS")
    sec = _extract_str_list_literal(ROOT / "ui" / "widgets" / "overview_tile.py", "_SEC")
    assert sec_labels is not None, "_SEC_LABELS list literal not found in home_data_mixin.py -- did it get renamed?"
    assert sec is not None, "_SEC list literal not found in overview_tile.py -- did it get renamed?"

    live = {
        "ui/pages/home_data_mixin.py::_SEC_LABELS": frozenset(audit - set(sec_labels)),
        "ui/widgets/overview_tile.py::_SEC": frozenset(audit - set(sec)),
    }

    offenders = []
    for key, baseline in _ROLLUP_MISSING_BASELINE.items():
        if live[key] != baseline:
            offenders.append(f"{key}: live missing={sorted(live[key])}, baseline={sorted(baseline)}")
    assert not offenders, (
        "Rollup list drift changed vs. the F-04 baseline:\n" + "\n".join(offenders) +
        "\n\nIf a list now derives from _AUDIT_SCAN_LABELS (or was hand-updated to include "
        "the missing label), lower its baseline entry above and delete F-04 from _OPEN_FINDINGS "
        "+ its block in claims-audit.md. If a NEW label went missing, that's a regression -- fix "
        "the list, don't raise the baseline."
    )


# ── Check 2: hardcoded literal masquerading as registry state (F-01, class B/C) ─

_HARDCODED_STATE_BASELINE: frozenset[str] = frozenset()


def _find_hardcoded_state_reg_keys(path: Path, class_name: str, method_name: str) -> set[str]:
    """Walk `class_name.method_name`'s `if reg_key == "X": ... elif reg_key == "Y": ...`
    dispatch chain. For each branch, flag reg_key literals whose `state` variable is
    assigned directly from a string Constant (hardcoded) rather than derived from a
    registry lookup (a Subscript/Call/Attribute expression)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    offenders: set[str] = set()

    def _find_method(node: ast.AST) -> ast.FunctionDef | None:
        for n in ast.walk(node):
            if isinstance(n, ast.ClassDef) and n.name == class_name:
                for item in n.body:
                    if isinstance(item, ast.FunctionDef) and item.name == method_name:
                        return item
        return None

    method = _find_method(tree)
    if method is None:
        return offenders

    for stmt in ast.walk(method):
        if not isinstance(stmt, ast.If):
            continue
        cmp = stmt.test
        if not (isinstance(cmp, ast.Compare) and len(cmp.ops) == 1 and isinstance(cmp.ops[0], ast.Eq)):
            continue
        left, right = cmp.left, cmp.comparators[0]
        # Match `reg_key == "literal"` in either operand order.
        reg_key_literal = None
        if isinstance(left, ast.Name) and left.id == "reg_key" and isinstance(right, ast.Constant):
            reg_key_literal = right.value
        elif isinstance(right, ast.Name) and right.id == "reg_key" and isinstance(left, ast.Constant):
            reg_key_literal = left.value
        if reg_key_literal is None:
            continue

        for body_stmt in stmt.body:
            if not isinstance(body_stmt, ast.Assign):
                continue
            targets = body_stmt.targets
            if not (len(targets) == 1 and isinstance(targets[0], ast.Tuple)):
                continue
            names = [t.id for t in targets[0].elts if isinstance(t, ast.Name)]
            if "state" not in names:
                continue
            value = body_stmt.value
            if not isinstance(value, ast.Tuple):
                continue
            state_idx = names.index("state")
            state_rhs = value.elts[state_idx]
            if isinstance(state_rhs, ast.Constant) and isinstance(state_rhs.value, str):
                offenders.add(str(reg_key_literal))

    return offenders


def test_every_displayed_scan_row_has_a_producer():
    live = _find_hardcoded_state_reg_keys(
        ROOT / "ui" / "widgets" / "overview_tile.py", "_ScanStatusTile", "refresh",
    )
    assert live == _HARDCODED_STATE_BASELINE, (
        f"_ScanStatusTile.refresh()'s reg_key dispatch has hardcoded-literal state branches "
        f"{sorted(live)}, baseline expects {sorted(_HARDCODED_STATE_BASELINE)} -- "
        "a row whose state is a bare string literal ignores the scan registry entirely "
        "(F-01's exact defect shape). If '_logger' now reads from the registry like every "
        "other row, empty the baseline and delete F-01. If a NEW row was added this way, "
        "that's a regression -- read the registry instead of hardcoding."
    )


# ── Check 3: security panel tools missing from the audit dispatcher (F-02) ──────

_UNDISPATCHED_TOOLS_BASELINE: frozenset[str] = frozenset()


def _find_dispatched_labels(path: Path, method_name: str) -> set[str]:
    """Walk `method_name`'s `if label == L.XXX:` / `elif label == L.YYY:` chain and
    return the set of NavLabel attribute names it dispatches (e.g. {"PORT_SCAN_TCP"})."""
    from ui.nav.labels import NavLabel as L

    tree = ast.parse(path.read_text(encoding="utf-8"))
    dispatched_attrs: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == method_name:
            for stmt in ast.walk(node):
                if not isinstance(stmt, ast.Compare):
                    continue
                if not (len(stmt.ops) == 1 and isinstance(stmt.ops[0], ast.Eq)):
                    continue
                for side in (stmt.left, stmt.comparators[0]):
                    if (
                        isinstance(side, ast.Attribute)
                        and isinstance(side.value, ast.Name)
                        and side.value.id == "L"
                    ):
                        dispatched_attrs.add(side.attr)
    return {str(getattr(L, attr).value) for attr in dispatched_attrs if hasattr(L, attr)}


def test_security_panel_tools_are_all_dispatched():
    from ui.widgets.overview_tile import _SecurityScanPanel

    all_tools = {nav_lbl for (nav_lbl, *_rest) in _SecurityScanPanel._TOOLS}
    dispatched = _find_dispatched_labels(ROOT / "ui" / "dashboard.py", "_advance_security_audit")
    live_undispatched = frozenset(all_tools - dispatched)

    assert live_undispatched == _UNDISPATCHED_TOOLS_BASELINE, (
        f"_advance_security_audit() dispatch coverage of _SecurityScanPanel._TOOLS changed: "
        f"live undispatched={sorted(live_undispatched)}, baseline={sorted(_UNDISPATCHED_TOOLS_BASELINE)} -- "
        "clicking 'Run Selected' silently skips any tool in this set (F-02's exact defect "
        "shape). If dispatch branches were added, shrink the baseline and correspondingly "
        "shrink _OPEN_FINDINGS['F-02']'s scope (delete it once undispatched is empty). If a "
        "NEW tool was added to _TOOLS without a dispatch branch, that's a regression."
    )


# ── Check 4: UI reads an attribute that doesn't exist on the dataclass it's given (F-03) ─

# Registry of known (dataclass module, dataclass name, consuming file, consuming function,
# loop variable) tuples worth checking. Add an entry whenever a new "for x in res.items:"
# loop over a known dataclass is added to a scan_enrichment-style handler.
_DATACLASS_READ_SITES: list[tuple[str, str, str, str, str]] = [
    ("modules.smb_enumerator", "SMBUser", "ui/scan_enrichment.py", "_on_smb_result", "u"),
    ("modules.credentialed_scan_helpers", "UserEntry", "ui/scan_enrichment.py", "_on_cred_result", "u"),
]

# baseline: {(file, function, loop_var): frozenset of attribute names read that do NOT
# exist on the mapped dataclass}. Empty frozenset = clean.
_BAD_ATTR_READ_BASELINE: dict[tuple[str, str, str], frozenset[str]] = {
    ("ui/scan_enrichment.py", "_on_smb_result", "u"): frozenset(),
    ("ui/scan_enrichment.py", "_on_cred_result", "u"): frozenset(),
}


def _dataclass_field_names(module_name: str, class_name: str) -> set[str]:
    import dataclasses
    import importlib

    mod = importlib.import_module(module_name)
    cls = getattr(mod, class_name)
    return {f.name for f in dataclasses.fields(cls)}


def _attrs_read_on_loop_var(path: Path, func_name: str, loop_var: str) -> set[str]:
    """Within `func_name`, find `for <loop_var> in ...:` loops and collect every
    `<loop_var>.<attr>` read inside the loop body."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    attrs: set[str] = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.FunctionDef) and node.name == func_name):
            continue
        for sub in ast.walk(node):
            if not (isinstance(sub, ast.For) and isinstance(sub.target, ast.Name) and sub.target.id == loop_var):
                continue
            for inner in ast.walk(sub):
                if (
                    isinstance(inner, ast.Attribute)
                    and isinstance(inner.value, ast.Name)
                    and inner.value.id == loop_var
                ):
                    attrs.add(inner.attr)
    return attrs


def test_ui_reads_only_existing_dataclass_fields():
    offenders = []
    for module_name, class_name, rel_path, func_name, loop_var in _DATACLASS_READ_SITES:
        fields = _dataclass_field_names(module_name, class_name)
        read_attrs = _attrs_read_on_loop_var(ROOT / rel_path, func_name, loop_var)
        bad = frozenset(read_attrs - fields)
        key = (rel_path, func_name, loop_var)
        baseline = _BAD_ATTR_READ_BASELINE.get(key, frozenset())
        if bad != baseline:
            offenders.append(
                f"{rel_path}:{func_name} reads {loop_var}.<attr> not on {class_name}: "
                f"live={sorted(bad)}, baseline={sorted(baseline)}"
            )
    assert not offenders, (
        "UI code reads dataclass attributes that don't exist (F-03's exact defect shape -- "
        "a live AttributeError waiting for the right scan result):\n" + "\n".join(offenders) +
        "\n\nIf a bad read was fixed, shrink its baseline entry and delete F-03 once all "
        "entries are clean. If a NEW bad read appeared, that's a regression -- fix the read "
        "or add the missing field to the dataclass."
    )


# ── Check 5: declared dataclass field with zero producers anywhere (F-06, class A) ──

# Registry of (module, class, field) that the UI renders but nothing assigns. A field is
# "produced" if `.field = ` (or `field=value` in a constructor call) appears anywhere in
# modules/, ui/, or workers/ outside the dataclass's own definition file.
_PRODUCERLESS_FIELD_BASELINE: dict[tuple[str, str, str], bool] = {
    ("modules.geo_locator", "GeoResult", "asn"): True,       # True = confirmed producer-less
    ("modules.geo_locator", "GeoResult", "org"): True,
    ("modules.credentialed_scan_helpers", "PatchInfo", "last_update"): True,
    ("modules.smb_enumerator", "SMBEnumResult", "sessions"): True,
    ("modules.smb_enumerator", "SMBEnumResult", "is_domain_controller"): True,
}

_SEARCH_ROOTS = ("modules", "ui", "workers")


def _has_producer(field: str, defining_file: Path) -> bool:
    """Grep-based: does any assignment to `.field = ` or `field=...` (constructor kwarg)
    exist anywhere in modules/ui/workers, outside the dataclass's own definition file?"""
    assign_pat = re.compile(rf"\.{re.escape(field)}\s*=(?!=)")
    kwarg_pat = re.compile(rf"(?<![.\w]){re.escape(field)}\s*=(?!=)")
    for root_name in _SEARCH_ROOTS:
        root = ROOT / root_name
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if path.resolve() == defining_file.resolve():
                continue
            try:
                src = path.read_text(encoding="utf-8")
            except OSError:
                continue
            if assign_pat.search(src) or (kwarg_pat.search(src) and f"{field}:" not in src.split(f"{field}=")[0][-40:]):
                # kwarg_pat alone is noisy (matches unrelated same-named params); only trust
                # it combined with a nearby class-construction-shaped context is out of scope
                # for this lightweight check, so real signal comes from assign_pat primarily.
                if assign_pat.search(src):
                    return True
    return False


def test_declared_dataclass_fields_have_a_producer():
    import importlib

    offenders = []
    for (module_name, class_name, field), expected_producerless in _PRODUCERLESS_FIELD_BASELINE.items():
        mod = importlib.import_module(module_name)
        defining_file = Path(mod.__file__)
        live_producerless = not _has_producer(field, defining_file)
        if live_producerless != expected_producerless:
            offenders.append(
                f"{module_name}.{class_name}.{field}: live producerless={live_producerless}, "
                f"baseline expects={expected_producerless}"
            )
    assert not offenders, (
        "Producer-less dataclass field status changed vs. baseline (F-06/F-56/F-78's defect "
        "shape -- a field the UI renders that no scan/parser ever assigns):\n"
        + "\n".join(offenders) +
        "\n\nIf a field now has a real producer, flip its baseline entry to False and delete "
        "the corresponding finding once all its fields are fixed. If a field that used to "
        "have a producer lost it, that's a regression."
    )


# ── Check 6: duplicate _PAGE_HELP source (F-07, class D) ────────────────────────

_PAGE_HELP_DEFINITION_COUNT_BASELINE = 1  # ui/help.py (live); dead ui/pages/help_content.py deleted (F-07)


def _files_defining_page_help() -> list[str]:
    pattern = re.compile(r"^_PAGE_HELP\s*[:=]", re.MULTILINE)
    hits = []
    for path in (ROOT / "ui").rglob("*.py"):
        try:
            src = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if pattern.search(src):
            hits.append(path.relative_to(ROOT).as_posix())
    return sorted(hits)


def test_no_duplicate_page_help_source():
    live_files = _files_defining_page_help()
    assert len(live_files) == _PAGE_HELP_DEFINITION_COUNT_BASELINE, (
        f"Found {len(live_files)} file(s) defining a module-level _PAGE_HELP: {live_files}, "
        f"baseline expects {_PAGE_HELP_DEFINITION_COUNT_BASELINE} -- "
        "a second _PAGE_HELP source is dead-code drift risk: whichever page/test "
        "imports the wrong one silently checks against stale content. Consolidate to "
        "one source (ui/help.py) before raising this baseline again."
    )
