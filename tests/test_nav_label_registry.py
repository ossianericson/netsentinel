"""
test_nav_label_registry.py — P1 nav label registry enforcement.

``ui/nav/labels.py`` is the single source of truth for every nav page label and
rail-section name. These gates keep it honest and kill the biggest recurring nav
bug class — a typo'd or renamed label that routes nowhere with no error
(RULE-NAV3 / RULE-NAV-RENAME):

  1. Registry parity — ``set(NavLabel)`` must equal the labels registered in
     ``_build_pro_nav()``; ``set(NavSection)`` must equal the
     ``_nav_begin_section()`` names. Add/remove a page there → add/remove its
     member here.
  2. Literal validation — every string literal handed to a nav router
     (``_nav_rail_go_to`` / ``_nav_set_scan_state`` / ``_nav_deep_link_go_to`` /
     ``navigate_requested.emit`` / ``navigate_to.emit``) must resolve to a
     ``NavLabel`` member or a ``SPECIAL_LABELS`` entry. Caught at test time
     instead of silently no-oping at runtime.
  3. Ratchets — the spec-named routers carry ZERO string literals (fully migrated
     to ``NavLabel``); ``navigate_to.emit`` literals may only decrease from the
     baseline. Migrate a literal → lower the baseline; never raise it
     (RULE-ENFORCE1).
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
UI_DIR = ROOT / "ui"
# S3 root cause: this net used to walk UI_DIR only, so a dead nav label
# referenced from modules/ (every alert deep-link lives in
# modules/alert_engine_routing.py) or workers/ was invisible to it. Widened
# so the whole app, not just ui/, is covered.
LITERAL_SCAN_DIRS = (UI_DIR, ROOT / "modules", ROOT / "workers")
sys.path.insert(0, str(ROOT))

from ui.nav.labels import NavLabel, NavSection, KNOWN_LABELS  # noqa: E402 — needs ROOT on path

# Routers whose first positional arg is a nav label and that are fully migrated
# to NavLabel constants — their string-literal count must stay at zero.
# ``_nav_go_to`` is the thin wrapper that forwards to ``_nav_rail_go_to``.
_GOTO_FUNCS = frozenset(
    {"_nav_rail_go_to", "_nav_go_to", "_nav_set_scan_state", "_nav_deep_link_go_to"}
)

# navigate_to.emit(...) is the same bug class but a larger population still on
# string literals. Ratchet it down; never up. Lower this when you migrate sites.
_NAV_TO_EMIT_BASELINE = 40


def _iter_nav_literal_calls():
    """Yield (rel_path, lineno, router_kind, literal) for every nav-router call
    whose first positional arg is a string constant.

    ``router_kind`` is the function/attribute name: a member of ``_GOTO_FUNCS``,
    or ``"navigate_to"`` / ``"navigate_requested"`` for the signal emits.
    """
    for scan_dir in LITERAL_SCAN_DIRS:
        for path in sorted(scan_dir.rglob("*.py")):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8").lstrip("﻿"))
            except SyntaxError:
                continue  # tolerate a file mid-edit; other gates cover syntax
            rel = str(path.relative_to(ROOT))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not node.args:
                    continue
                a0 = node.args[0]
                if not (isinstance(a0, ast.Constant) and isinstance(a0.value, str)):
                    continue
                fn = node.func
                if isinstance(fn, ast.Attribute) and fn.attr in _GOTO_FUNCS:
                    yield rel, node.lineno, fn.attr, a0.value
                elif (
                    isinstance(fn, ast.Attribute)
                    and fn.attr == "emit"
                    and isinstance(fn.value, ast.Attribute)
                    and fn.value.attr in ("navigate_to", "navigate_requested")
                ):
                    yield rel, node.lineno, fn.value.attr, a0.value


def _build_pro_nav_body() -> str:
    src = (UI_DIR / "nav" / "builder.py").read_text(encoding="utf-8")
    m = re.search(r"(    def _build_pro_nav\(.*?)(?=\n    def |\Z)", src, re.DOTALL)
    assert m, "_build_pro_nav not found in ui/nav/builder.py"
    return m.group(1)


def test_registry_matches_pro_nav_labels():
    """set(NavLabel) must equal the labels registered in _build_pro_nav()."""
    body = _build_pro_nav_body()
    registered = set(re.findall(r'_nav_add_rail_item\(\s*"([^"]+)"', body))
    members = {str(m) for m in NavLabel}
    assert registered == members, (
        "NavLabel is out of sync with _build_pro_nav():\n"
        f"  registered but no NavLabel member: {sorted(registered - members)}\n"
        f"  NavLabel member but not registered: {sorted(members - registered)}\n"
        "Every page registered via _nav_add_rail_item() needs a NavLabel member "
        "and vice-versa (dynamic plugin pages excepted — they carry string labels)."
    )


def test_registry_matches_pro_nav_sections():
    """set(NavSection) must equal the _nav_begin_section() names in _build_pro_nav()."""
    body = _build_pro_nav_body()
    registered = set(re.findall(r'_nav_begin_section\(\s*"([^"]+)"', body))
    members = {str(m) for m in NavSection}
    assert registered == members, (
        "NavSection is out of sync with _build_pro_nav():\n"
        f"  registered but no NavSection member: {sorted(registered - members)}\n"
        f"  NavSection member but not registered: {sorted(members - registered)}"
    )


def test_all_nav_literal_targets_are_known():
    """Every string literal routed through a nav router must be a real target.

    A literal that is neither a NavLabel member nor a SPECIAL_LABELS entry routes
    nowhere at runtime (RULE-NAV3). This is the compile-time typo catcher.
    """
    bad = [
        f"{rel}:{ln}  {kind}({lit!r})"
        for rel, ln, kind, lit in _iter_nav_literal_calls()
        if lit not in KNOWN_LABELS
    ]
    assert not bad, (
        "Nav-router calls target labels that are not NavLabel members "
        "(nor SPECIAL_LABELS) — these routes silently no-op at runtime (RULE-NAV3).\n"
        "Fix the label to a ui.nav.labels.NavLabel member, or register the page in "
        "_build_pro_nav() / add it to SPECIAL_LABELS:\n  " + "\n  ".join(bad)
    )


def test_goto_routers_have_no_string_literals():
    """The fully-migrated routers must carry no string-literal labels (baseline 0).

    Covers _nav_rail_go_to / _nav_set_scan_state / _nav_deep_link_go_to /
    navigate_requested.emit. New code must pass a NavLabel member.
    """
    offenders = [
        f"{rel}:{ln}  {kind}({lit!r})"
        for rel, ln, kind, lit in _iter_nav_literal_calls()
        if kind in _GOTO_FUNCS or kind == "navigate_requested"
    ]
    assert not offenders, (
        "String-literal nav labels reintroduced into fully-migrated routers "
        "(baseline is zero). Pass a ui.nav.labels.NavLabel member instead:\n  "
        + "\n  ".join(offenders)
    )


def test_navigate_to_emit_literal_ratchet():
    """navigate_to.emit(...) string literals may only decrease (RULE-ENFORCE1)."""
    count = sum(
        1 for _rel, _ln, kind, _lit in _iter_nav_literal_calls() if kind == "navigate_to"
    )
    assert count <= _NAV_TO_EMIT_BASELINE, (
        f"navigate_to.emit string-literal count rose to {count} "
        f"(baseline {_NAV_TO_EMIT_BASELINE}).\n"
        "Emit a ui.nav.labels.NavLabel member instead of a bare string. When you "
        "migrate existing sites, lower _NAV_TO_EMIT_BASELINE to match."
    )
    # Keep the baseline honest — ratchet down when fixes drop it well below.
    assert count > _NAV_TO_EMIT_BASELINE - 8, (
        f"navigate_to.emit literal count is {count}, well below baseline "
        f"{_NAV_TO_EMIT_BASELINE}. Lower _NAV_TO_EMIT_BASELINE to {count}."
    )
