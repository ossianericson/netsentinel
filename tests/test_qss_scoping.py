"""
test_qss_scoping.py — RULE-QSS1 enforcement: no bare (selector-less) stylesheets
on container widgets.

MECHANISM (why this matters):
A Qt stylesheet with no selector — setStyleSheet("background:transparent;") —
is interpreted as `* { ... }` and applies to the widget AND EVERY DESCENDANT.
Widget stylesheets always beat the application stylesheet regardless of
specificity, so a bare declaration on a page/frame container silently wipes the
app-QSS styling of every child. The canonical failure: QPushButton#btnScan gets
`background: ACCENT; color: WHITE` from ui/styles.py; a bare
"background:transparent;" on an ancestor wipes the blue background while the
white text survives -> a white-on-white, invisible button (the "Run Speed Test"
bug, July 2026).

CORRECT PATTERN — scope container stylesheets with an objectName selector,
which matches only the container itself and never propagates:

    w.setObjectName("pageContent")
    w.setStyleSheet(f"QWidget#pageContent {{ background: transparent; }}")

Two enforcement tiers:
  Tier 1 (hard fail, zero allowed): a button styled by the global QSS via
    setObjectName("btnScan"/"btnScanHero"/...) placed — traceably within one
    function — under a container carrying a bare stylesheet. These buttons
    become invisible or mis-styled.
  Tier 2 (ratchet): the total number of bare-styled containers in ui/ must
    never increase. Fix sites opportunistically; the baseline only moves down.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).parent.parent
UI_DIR = ROOT / "ui"

LAYOUT_CTORS = {"QVBoxLayout", "QHBoxLayout", "QGridLayout", "QFormLayout", "QStackedLayout"}

# Buttons whose entire visual identity comes from the app-level QSS in
# ui/styles.py (objectName selectors). If a bare ancestor stylesheet wipes
# their background, the text colour survives and the button turns invisible.
GLOBAL_BTN_NAMES = {
    "btnScan", "btnScanHero", "btnExport", "btnDiag", "btnNetRefresh", "btnRouterLink",
}

# Tier 2 ratchet baseline — number of bare-styled containers in ui/**.
# This number may only DECREASE. If your change adds a bare stylesheet to a
# container, scope it with an objectName selector instead (see module
# docstring). When you fix existing sites, lower the baseline accordingly.
BARE_CONTAINER_BASELINE = 174


def _key(node: ast.expr) -> "str | None":
    """Stable key for `x` or `self._x` receivers."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        return f"{node.value.id}.{node.attr}"
    return None


def _literal_text(node: ast.expr) -> "str | None":
    """Literal text of a str constant, or the constant parts of an f-string."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(
            v.value for v in node.values
            if isinstance(v, ast.Constant) and isinstance(v.value, str)
        )
    return None


def _iter_ui_trees():
    for path in sorted(UI_DIR.rglob("*.py")):
        try:
            src = path.read_text(encoding="utf-8")
            # Tolerate a UTF-8 BOM (RULE-ENC3 legacy files)
            yield path, ast.parse(src.lstrip("﻿"))
        except SyntaxError:
            continue


def _scan_function(func: ast.AST):
    """Return (bare_containers, layout_owner, layout_parent, objname_btns,
    styled_widgets, added_widgets) facts for one function body."""
    bare_containers: dict = {}   # widget key -> (line, snippet)
    layout_owner: dict = {}      # layout key -> widget key
    layout_parent: dict = {}     # layout key -> parent layout key
    objname_btns: dict = {}      # widget key -> objectName
    styled: set = set()          # widget keys with own setStyleSheet
    added: list = []             # (layout key, widget key, line)
    containers: set = set()      # widget keys used as layout parents

    for node in ast.walk(func):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            fn = node.value.func
            if isinstance(fn, ast.Name) and fn.id in LAYOUT_CTORS and node.value.args:
                lk = _key(node.targets[0])
                wk = _key(node.value.args[0])
                if lk and wk:
                    layout_owner[lk] = wk
                    containers.add(wk)
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        # bare QxLayout(w) call not captured by an assignment
        if isinstance(fn, ast.Name) and fn.id in LAYOUT_CTORS and node.args:
            wk = _key(node.args[0])
            if wk:
                containers.add(wk)
        # themed_ss(w, template) is the live-theming equivalent of
        # w.setStyleSheet(template) — treat it identically so converted sites
        # stay visible to both tiers instead of vanishing from the scan.
        if isinstance(fn, ast.Name) and fn.id == "themed_ss" and len(node.args) >= 2:
            recv = _key(node.args[0])
            if recv is not None:
                styled.add(recv)
                text = _literal_text(node.args[1])
                if text is not None and "{" not in text and text.strip():
                    bare_containers[recv] = (node.lineno, text.strip()[:60])
            continue
        if not isinstance(fn, ast.Attribute):
            continue
        recv = _key(fn.value)
        if recv is None or not node.args:
            if isinstance(fn, ast.Attribute) and fn.attr == "setStyleSheet" and recv:
                styled.add(recv)
            continue
        if fn.attr == "setStyleSheet":
            styled.add(recv)
            text = _literal_text(node.args[0])
            if text is not None and "{" not in text and text.strip():
                bare_containers[recv] = (node.lineno, text.strip()[:60])
        elif fn.attr == "setObjectName":
            t = _literal_text(node.args[0])
            if t in GLOBAL_BTN_NAMES:
                objname_btns[recv] = t
        elif fn.attr == "addLayout":
            ck = _key(node.args[0])
            if ck:
                layout_parent[ck] = recv
        elif fn.attr == "addWidget":
            wk = _key(node.args[0])
            if wk:
                added.append((recv, wk, node.lineno))
        elif fn.attr == "setLayout":
            lk = _key(node.args[0])
            if lk:
                layout_owner[lk] = recv
                containers.add(recv)
        elif fn.attr == "setWidget":
            wk = _key(node.args[0])
            if wk:
                containers.add(wk)
    return bare_containers, layout_owner, layout_parent, objname_btns, styled, added, containers


def _funcs(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node


def test_no_global_qss_button_under_bare_styled_container():
    """Tier 1: a #btnScan-class button under a bare-styled ancestor is invisible."""
    violations = []
    for path, tree in _iter_ui_trees():
        rel = path.relative_to(ROOT)
        for func in _funcs(tree):
            (bare, layout_owner, layout_parent,
             objname_btns, styled, added, _containers) = _scan_function(func)
            if not bare or not objname_btns:
                continue

            def root_container(lk, depth=0):
                if depth > 12:
                    return None
                if lk in layout_owner:
                    return layout_owner[lk]
                return root_container(layout_parent.get(lk), depth + 1) if lk in layout_parent else None

            for lay_k, wid_k, line in added:
                if wid_k not in objname_btns or wid_k in styled:
                    continue
                container = root_container(lay_k)
                if container and container in bare:
                    c_line, c_text = bare[container]
                    violations.append(
                        f"{rel}:{line}  button {wid_k!r} (#{objname_btns[wid_k]}) sits under "
                        f"container {container!r} which has a bare stylesheet at line "
                        f"{c_line} ({c_text!r})"
                    )
    assert not violations, (
        "RULE-QSS1 violation — global-QSS buttons under bare-styled containers.\n"
        "A selector-less setStyleSheet() on a container acts as `* { ... }` for the whole\n"
        "subtree and overrides the app stylesheet: the button's coloured background is\n"
        "wiped while its white text survives -> invisible button.\n"
        "FIX: scope the container stylesheet with an objectName selector, e.g.\n"
        '    w.setObjectName("myContainer")\n'
        '    w.setStyleSheet(f"QWidget#myContainer {{ background: transparent; }}")\n\n'
        + "\n".join(violations)
    )


def test_bare_styled_container_count_ratchet():
    """Tier 2: total bare-styled containers in ui/** must never increase."""
    seen = set()
    for path, tree in _iter_ui_trees():
        rel = path.relative_to(ROOT)
        for func in _funcs(tree):
            bare, _lo, _lp, _ob, _st, _ad, containers = _scan_function(func)
            for k, (line, _text) in bare.items():
                if k in containers:
                    seen.add((str(rel), line))
    count = len(seen)
    assert count <= BARE_CONTAINER_BASELINE, (
        f"RULE-QSS1 ratchet — bare-styled containers in ui/ rose to {count} "
        f"(baseline {BARE_CONTAINER_BASELINE}).\n"
        "New container stylesheets must be scoped with an objectName selector\n"
        '(w.setObjectName("x"); w.setStyleSheet("QWidget#x { ... }")) — bare\n'
        "declarations propagate to every descendant and clobber app-QSS styling.\n"
        "Never raise the baseline; when you fix existing sites, lower it."
    )
    # Keep the baseline honest — if fixes dropped the count well below the
    # baseline, ratchet it down so regressions can't hide in the slack.
    assert count > BARE_CONTAINER_BASELINE - 10, (
        f"Bare-styled container count is {count}, well below baseline "
        f"{BARE_CONTAINER_BASELINE}. Lower BARE_CONTAINER_BASELINE to {count}."
    )
