"""RULE-QSS5 corollary: a fixed-width spin box must show its widest value in full.

Owner-reported 2026-09-18: Port Scan (TCP)'s rate box rendered "500 p". The shared
``SPINBOX_WIDTH_*`` constants in ``ui/styles.py`` were sized before the global
``QLineEdit { padding: 4px 8px; }`` rule, which also reaches a spin box's internal line
edit, so every box using them lost 8 px of text area on top of the two windows11
``+``/``-`` buttons.

Two halves:
  * an AST sweep of ``ui/`` finds every ``X.setFixedWidth(<...>.SPINBOX_WIDTH_*)`` and
    reads X's literal ``setRange``/``setMaximum``/``setSuffix`` in the same function —
    plus calls to a local helper whose width parameter defaults to such a constant
    (``tabs_logger._spin``). A site whose range is not a literal must be listed in
    ``_DYNAMIC_RANGE_WORST`` with the widest value it can show.
  * ``tests/_spinbox_fit_child.py`` measures each site's widest value against the text
    area the stylesheet actually lays out, on the NATIVE platform (Windows only).
    ``sizeHint()`` cannot stand in: under windows11 it is 158 px whatever the text.
"""
from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pytest

REPO = Path(__file__).resolve().parent.parent
_CHILD = REPO / "tests" / "_spinbox_fit_child.py"
_CONST = re.compile(r"^SPINBOX_WIDTH_[A-Z_]+$")
_MISSING = object()

#: Sites whose range is not a literal at the call site -> (lo, hi, suffix) worst case.
_DYNAMIC_RANGE_WORST: Dict[str, Tuple[int, int, str]] = {
    # Plugin-declared "int" config field; the range comes from the plugin's spec and
    # defaults to max 99999 when the plugin gives none.
    "ui/widgets/hub_card.py": (0, 99999, ""),
}


def _const_name(node: Optional[ast.AST]) -> Optional[str]:
    if isinstance(node, ast.Attribute) and _CONST.match(node.attr):
        return node.attr
    if isinstance(node, ast.Name) and _CONST.match(node.id):
        return node.id
    return None


def _literal(node: Optional[ast.AST]):
    if node is None:
        return _MISSING
    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError, TypeError):
        return _MISSING


def _method_calls(func: ast.AST, method: str) -> List[ast.Call]:
    return [n for n in ast.walk(func)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == method]


def _receiver_calls(func: ast.AST, receiver: str, method: str) -> List[ast.Call]:
    return [c for c in _method_calls(func, method) if ast.unparse(c.func.value) == receiver]


def _direct_sites(path: str, func: ast.AST, sites: list, unresolved: list) -> None:
    for call in _method_calls(func, "setFixedWidth"):
        const = _const_name(call.args[0]) if call.args else None
        if const is None:
            continue
        receiver = ast.unparse(call.func.value)
        lo, hi, suffix = 0, _MISSING, ""
        for c in _receiver_calls(func, receiver, "setRange"):
            if len(c.args) == 2:
                lo, hi = _literal(c.args[0]), _literal(c.args[1])
        for c in _receiver_calls(func, receiver, "setMaximum"):
            hi = _literal(c.args[0]) if c.args else _MISSING
        for c in _receiver_calls(func, receiver, "setSuffix"):
            suffix = _literal(c.args[0]) if c.args else _MISSING
        site = (path, call.lineno, const)
        if isinstance(hi, int) and isinstance(lo, int) and isinstance(suffix, str):
            sites.append((*site, lo, hi, suffix))
        else:
            unresolved.append(site)


def _helper_sites(path: str, tree: ast.Module, sites: list) -> None:
    """A local helper whose width parameter defaults to a SPINBOX_WIDTH_* constant."""
    for func in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
        params = [a.arg for a in func.args.args]
        defaults = dict(zip(params[len(params) - len(func.args.defaults):], func.args.defaults))
        width_params = {p: _const_name(d) for p, d in defaults.items() if _const_name(d)}
        if not width_params:
            continue
        roles: Dict[str, str] = {}
        for c in _method_calls(func, "setRange"):
            if len(c.args) == 2 and all(isinstance(a, ast.Name) for a in c.args):
                roles["lo"], roles["hi"] = c.args[0].id, c.args[1].id
        for c in _method_calls(func, "setSuffix"):
            if c.args and isinstance(c.args[0], ast.Name):
                roles["suffix"] = c.args[0].id
        if "hi" not in roles:
            continue
        for call in [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                     and isinstance(n.func, ast.Name) and n.func.id == func.name]:
            bound = dict(zip(params, call.args))
            bound.update({k.arg: k.value for k in call.keywords if k.arg})
            wp, default_const = next(iter(width_params.items()))
            const = _const_name(bound[wp]) if wp in bound else default_const
            lo = _literal(bound.get(roles.get("lo", ""))) if roles.get("lo") else 0
            hi = _literal(bound.get(roles["hi"]))
            suffix = _literal(bound.get(roles["suffix"])) if roles.get("suffix") in bound else ""
            if const and isinstance(lo, int) and isinstance(hi, int) and isinstance(suffix, str):
                sites.append((path, call.lineno, const, lo, hi, suffix))


def collect_sites() -> Tuple[list, list]:
    """(sites, unresolved): sites are (path, line, const, lo, hi, suffix)."""
    sites: list = []
    unresolved: list = []
    for file in sorted((REPO / "ui").rglob("*.py")):
        path = file.relative_to(REPO).as_posix()
        if path == "ui/styles.py":
            continue
        tree = ast.parse(file.read_text(encoding="utf-8"))
        # Outermost functions only: ast.walk already descends into nested defs.
        for func in [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))]:
            for f in ([func] if isinstance(func, ast.FunctionDef)
                      else [m for m in func.body if isinstance(m, ast.FunctionDef)]):
                _direct_sites(path, f, sites, unresolved)
        _helper_sites(path, tree, sites)
    return sorted(set(sites)), sorted(set(unresolved))


def test_every_fixed_width_spinbox_site_is_resolved() -> None:
    sites, unresolved = collect_sites()
    # A sweep that silently finds nothing would pass the fit test vacuously.
    assert len(sites) >= 20, f"expected >= 20 SPINBOX_WIDTH_* sites, found {len(sites)}"
    assert any(p == "ui/tabs_recon.py" and hi == 5000 and sfx == " pps"
               for p, _l, _c, _lo, hi, sfx in sites), "Port Scan rate box not found"
    assert any(p == "ui/tabs_logger.py" and sfx == " min" for p, *_rest, sfx in sites), \
        "tabs_logger._spin() helper calls not resolved"
    unresolved_paths = {p for p, _line, _c in unresolved}
    assert unresolved_paths == set(_DYNAMIC_RANGE_WORST), (
        "A SPINBOX_WIDTH_* site whose range is not a literal must be listed in "
        f"_DYNAMIC_RANGE_WORST with its widest value. Unresolved: {unresolved}"
    )


#: The child inherits this. CI runs the suite under ``QT_QPA_PLATFORM=offscreen``, whose
#: plugin resolves to the fusion style and measures fonts ~2x wider, so the numbers mean
#: nothing there -- the style guard below is what catches it, and it did, as a CI failure
#: on a tree whose spin boxes were fine. Measuring needs the real plugin, so skip instead.
#: The AST sweep half of this file still runs on every platform and in CI.
_FORCED_PLATFORM = os.environ.get("QT_QPA_PLATFORM", "").strip().lower()
_NATIVE_PLUGIN = _FORCED_PLATFORM in ("", "windows")


@pytest.mark.skipif(sys.platform != "win32", reason="measures windows11 geometry on the native platform")
@pytest.mark.skipif(not _NATIVE_PLUGIN,
                    reason=f"QT_QPA_PLATFORM={_FORCED_PLATFORM!r} is not the native plugin; "
                           "the windows11 geometry this measures does not exist under it")
def test_every_fixed_width_spinbox_shows_its_widest_value(tmp_path: Path) -> None:
    from ui import styles as _s

    sites, unresolved = collect_sites()
    cases = [{"id": f"{p}:{line}", "width": getattr(_s, const), "lo": lo, "hi": hi, "suffix": sfx,
              "const": const} for p, line, const, lo, hi, sfx in sites]
    for p, line, const in unresolved:
        lo, hi, sfx = _DYNAMIC_RANGE_WORST[p]
        cases.append({"id": f"{p}:{line}", "width": getattr(_s, const), "lo": lo, "hi": hi,
                      "suffix": sfx, "const": const})
    case_file = tmp_path / "cases.json"
    case_file.write_text(json.dumps(cases), encoding="utf-8")

    r = subprocess.run([sys.executable, str(_CHILD), str(case_file)], capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=120, cwd=str(REPO))
    lines = [ln for ln in r.stdout.splitlines() if ln.startswith("RESULT:")]
    assert lines, f"child produced no result (exit {r.returncode}):\n{r.stdout}\n{r.stderr}"
    results = json.loads(lines[-1][len("RESULT:"):])
    assert {res["style"] for res in results} == {"windows11"}, \
        f"measured under the wrong style: {sorted({res['style'] for res in results})}"

    by_id = {c["id"]: c for c in cases}
    clipped = [
        f"{res['id']}: {by_id[res['id']]['const']}={by_id[res['id']]['width']} px shows "
        f"{res['avail']} px of {res['text']!r}, which needs {res['need']} px "
        f"(>= {by_id[res['id']]['width'] + res['need'] - res['avail']} px would fit)"
        for res in results if res["avail"] < res["need"]
    ]
    assert not clipped, (
        "Spin box values are cut off — raise the SPINBOX_WIDTH_* constant in ui/styles.py "
        "(or give the site its own wider width):\n  " + "\n  ".join(clipped)
    )
