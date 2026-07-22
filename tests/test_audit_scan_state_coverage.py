"""RULE-SS1 enforcement — every Security Audit page must record its scan state.

RULE-SS1 requires every Security Audit result handler to call
`_nav_set_scan_state`, because the Scan Status card, the flyout dot badges and
the Security Audit rail badge all read from `_scan_registry`. Until this test
existed the rule's own text said:

    "No automated test enforces that every audit handler calls this — rely on
     code review and the fact that a missing call produces a visibly wrong
     'Never run' in the UI."

Relying on that let four pages ship with no registry wiring at all (Cloud
Metadata Probe, Private Endpoint Check, Recon Plugins, Device Risk Score), so a
genuine HIGH/FAIL finding never propagated to the rail badge — the badge could
read clean while a HIGH finding sat on the page. This test closes the class
(RULE-ENFORCE1: prefer tool enforcement over discipline).

Conservative by design: a label passed as a *variable* cannot be resolved
statically and therefore counts as covering nothing. If that ever produces a
false failure, wire the page with an explicit `L.<LABEL>` constant rather than
weakening this guard.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

try:
    from ui.nav.labels import NavLabel
except ImportError:  # pragma: no cover - PyQt6 always present in CI
    pytest.skip("ui.nav.labels not importable", allow_module_level=True)


# Audit pages that legitimately never record a scan state, each with the reason
# it cannot. Adding an entry here is a deliberate, reviewable act — do not add
# one to silence a genuine wiring gap.
EXEMPT: dict[str, str] = {
    "Security Overview":
        "the aggregate dashboard that DISPLAYS other pages' states; it runs no "
        "scan of its own",
    "CVE Tracker":
        "a passive view over stored per-device CVE history (schema v20) — it has "
        "no worker and never 'runs', so it can never be fresh/stale",
    "DHCP Rogue Monitor":
        "a continuous monitor, not a one-shot scan; it drives its dot through "
        "_set_flyout_dot (monitor_state.py / app.py) instead of the scan registry",
}


def _audit_labels() -> set[str]:
    """Labels registered with audit_item=True in _build_pro_nav()."""
    tree = ast.parse((ROOT / "ui" / "nav" / "builder.py").read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "_nav_add_rail_item"):
            continue
        is_audit = any(
            kw.arg == "audit_item" and getattr(kw.value, "value", False) is True
            for kw in node.keywords
        )
        if is_audit and node.args and isinstance(node.args[0], ast.Constant):
            found.add(node.args[0].value)
    return found


def _labels_with_scan_state() -> set[str]:
    """Every label statically passed as the first arg to _nav_set_scan_state."""
    files = list((ROOT / "ui").rglob("*.py"))
    files.append(ROOT / "app.py")
    files.extend((ROOT / "workers").rglob("*.py"))

    found: set[str] = set()
    for path in files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "_nav_set_scan_state"
                    and node.args):
                continue
            arg = node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                found.add(arg.value)
            elif isinstance(arg, ast.Attribute):
                member = getattr(NavLabel, arg.attr, None)
                if member is not None:
                    found.add(str(member.value))
    return found


def test_every_audit_page_records_its_scan_state():
    missing = _audit_labels() - _labels_with_scan_state() - set(EXEMPT)
    assert not missing, (
        "RULE-SS1: these Security Audit pages never call _nav_set_scan_state, so "
        "their flyout dot stays dark ('Never run') and a real HIGH/FAIL finding "
        "never reaches the Security Audit rail badge:\n"
        + "".join(f"  - {label}\n" for label in sorted(missing))
        + "\nWire all three slots on each page:\n"
          "    start:  self._nav_set_scan_state(L.<LABEL>, 'running')\n"
          "    result: self._nav_set_scan_state(L.<LABEL>, 'fresh', ts=time.time(), verdict=...)\n"
          "    error:  self._nav_set_scan_state(L.<LABEL>, 'error', error=msg)\n"
          "If the probe was structurally blocked, use 'not_testable' rather than "
          "'fresh' so the grade says 'Insufficient data' instead of a false clean.\n"
          "If a page genuinely cannot record state, add it to EXEMPT in this file "
          "with the reason."
    )


def test_exempt_entries_are_still_real_audit_pages():
    """Keep EXEMPT honest — a stale entry would silently widen the hole."""
    stale = set(EXEMPT) - _audit_labels()
    assert not stale, (
        "These EXEMPT entries are no longer registered with audit_item=True; "
        f"remove them from EXEMPT: {sorted(stale)}"
    )


def test_exempt_reasons_are_documented():
    for label, reason in EXEMPT.items():
        assert reason and len(reason) > 20, (
            f"EXEMPT['{label}'] needs a real explanation of why it cannot "
            "record a scan state"
        )


def test_audit_label_strings_match_the_navlabel_enum():
    """A label typo yields a silent 'Never run' row — catch drift early."""
    known = {str(m.value) for m in NavLabel}
    unknown = {lbl for lbl in _audit_labels() if lbl not in known}
    assert not unknown, (
        "Audit page labels not present in the NavLabel enum (typo or missing "
        f"enum member): {sorted(unknown)}"
    )


def test_no_audit_label_uses_regex_unsafe_drift():
    """Guard against label/enum mismatch by normalised comparison."""
    def norm(s: str) -> str:
        return re.sub(r"[^A-Z0-9]", "", s.upper())

    enum_norms = {norm(str(m.value)) for m in NavLabel}
    for label in _audit_labels():
        assert norm(label) in enum_norms, f"{label!r} has no NavLabel counterpart"
