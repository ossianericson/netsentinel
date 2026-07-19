"""test_widget_visibility_order.py — enforcement guard for RULE-WIN7.

MECHANISM (why this matters):
A freshly-constructed Qt widget with no ``parent=`` argument has no parent
until it is inserted into a layout (``addWidget``/``insertWidget``) or given
an explicit parent. Until that happens, Qt treats it as an independent
top-level window. Calling ``.setVisible(True)`` (or ``.setVisible(<expr>)``
where the expression can be truthy) on such a widget BEFORE it is added to
its layout makes that still-parentless widget flash on screen with full
native OS chrome (title bar + min/max/close) for a fraction of a second —
this shipped in v2.1.22 (commit e83eb86, "Fix startup native-frame flash
from parentless setVisible() calls": ``ui/tabs_scan.py``, the old
``ui/pages/home_page.py``, ``ui/pages/log_source_panel.py``). That fix
covered only the three sites found by manual audit at the time; it did not
add a structural guard, so the same pattern reappeared independently in
``ui/widgets/hub_card.py`` (the Configure button, shown for any plugin with
a ``CONFIG_SCHEMA`` — flashes every startup once such a plugin is
configured) and ``ui/pages/rest_api_page.py`` (the external-access warning
label, flashes on startup once "Allow external access" has ever been
checked) — both fixed in the same commit that added this test.

A fourth instance shipped in ``ui/pages/home_page.py``'s ``protovizNudgeCard``
(the Protocol Visualizer education nudge on Home) — the AST guard below did
**not** catch it because the parentless ``QFrame`` is constructed and made
visible inside ``_build_protoviz_nudge_card()``, but ``addWidget()`` happens
in the *caller* (``_setup_ui()``) on a different reference
(``self._protoviz_nudge_card`` vs. the local ``bar``) — this guard only
tracks a single function's own scope (see the module docstring above), so a
widget returned from a helper and added to its layout by the caller is
structurally invisible to it. Found via a live ``python app.py
--trace-windows`` repro, not by this test. Fixed by deferring the
``setVisible(should_show_banner(...))`` call from inside the builder to
right after ``lay.addWidget()`` in ``_setup_ui()``. This is a known blind
spot of the heuristic below, not something the guard can be trivially
extended to catch — a real fix would need cross-function data flow analysis.

CORRECT PATTERN — call setVisible() only after addWidget():

    self._btn_configure = QPushButton("...")
    ...
    hdr_lay.addWidget(self._btn_configure)
    self._btn_configure.setVisible(bool(self._config_schema))   # after addWidget

``setVisible(False)`` before ``addWidget`` is harmless (the widget never
shows) and is not flagged — only a non-``False``-literal argument (a
dynamic expression or a literal ``True``) is a real risk, since that is the
case that can actually paint a visible top-level window.

This is a heuristic AST guard, not a full data-flow analysis. It only
tracks locally-constructed widgets with no `parent=` kwarg and no
positional args beyond string/number literals (covers the common
`QPushButton("label")`, `QLabel()`, `QFrame()` cases), and does not descend
into nested `def`/`lambda` bodies when scanning a function's own statements
(those run later, asynchronously, e.g. a `clicked.connect` callback — not
part of the synchronous construction sequence).
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).parent.parent
UI_DIR = ROOT / "ui"

_WIDGET_CTORS = {
    "QPushButton", "QLabel", "QFrame", "QWidget", "QCheckBox", "QToolButton",
    "QRadioButton", "QGroupBox",
}


def _ref_key(node: ast.AST) -> str | None:
    """Stable string key for a local variable or a `self.<attr>` reference."""
    if isinstance(node, ast.Name):
        return node.id
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "self"
    ):
        return f"self.{node.attr}"
    return None


def _is_unparented_ctor(call: ast.Call) -> bool:
    func = call.func
    name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
    if name not in _WIDGET_CTORS:
        return False
    if any(kw.arg == "parent" for kw in call.keywords):
        return False
    # A positional arg is only a possible *parent* if it is a variable reference
    # (a Name like `tab_bar` or an Attribute like `self._hdr`). Literal text —
    # a plain string, an f-string (ast.JoinedStr), a `"a" + b` concat, or a
    # number — is a label/content argument, never a parent, so a ctor with only
    # those args is still unparented. Missing the f-string case is exactly what
    # let the rest_api_page.py `_lbl_other_devices` flash slip through the first
    # time this guard ran.
    for a in call.args:
        if isinstance(a, (ast.Name, ast.Attribute, ast.Call)):
            return False
    return True


def _iter_own_scope(node: ast.AST):
    """Descendants of node, not descending into nested function/lambda bodies —
    those execute later (event callbacks), not as part of this scope's
    synchronous construction sequence."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        yield child
        yield from _iter_own_scope(child)


def _collect_violations(tree: ast.AST, path: Path) -> list[str]:
    violations = []
    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        constructed: dict[str, int] = {}
        for node in _iter_own_scope(func):
            if (
                isinstance(node, ast.Assign)
                and isinstance(node.value, ast.Call)
                and _is_unparented_ctor(node.value)
            ):
                for t in node.targets:
                    key = _ref_key(t)
                    if key:
                        constructed.setdefault(key, node.lineno)

        if not constructed:
            continue

        first_setvisible_truthy: dict[str, int] = {}
        first_addwidget: dict[str, int] = {}

        for node in _iter_own_scope(func):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            attr = node.func.attr
            if attr == "setVisible":
                key = _ref_key(node.func.value)
                if key in constructed:
                    arg = node.args[0] if node.args else None
                    is_hard_false = isinstance(arg, ast.Constant) and arg.value is False
                    if not is_hard_false:
                        first_setvisible_truthy.setdefault(key, node.lineno)
            elif attr in ("addWidget", "insertWidget"):
                for a in node.args:
                    akey = _ref_key(a)
                    if akey in constructed:
                        first_addwidget.setdefault(akey, node.lineno)

        for var, sv_line in first_setvisible_truthy.items():
            aw_line = first_addwidget.get(var)
            if aw_line is not None and sv_line < aw_line:
                rel = path.relative_to(ROOT)
                violations.append(
                    f"{rel}:{sv_line}: {var}.setVisible(...) is called before "
                    f"{var} is added to its layout at line {aw_line}. Qt treats a "
                    "still-parentless widget as an independent top-level window "
                    "and gives it full native chrome — this flashes on screen "
                    "(RULE-WIN7). Move the addWidget() call before setVisible()."
                )
    return violations


def test_no_setvisible_before_addwidget():
    offenders: list[str] = []
    for path in sorted(UI_DIR.rglob("*.py")):
        src = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(src, filename=str(path))
        except SyntaxError:
            continue
        offenders.extend(_collect_violations(tree, path))
    assert not offenders, "\n".join(offenders)
