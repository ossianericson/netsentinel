"""
Static scan: every literal-string themed_ss() template must reference only
real ui/styles.py theme tokens.

Background
----------
themed_ss(widget, template) accepts either a plain str with ``{TOKEN}``
placeholders or a zero-arg callable. For the str form, a typo in a token name
(e.g. ``{ACCET}``) would previously only surface as a ``KeyError`` the first
time that widget's theme got re-applied at runtime — often minutes after the
file was written, and only if a manual theme switch happened to be tested.

This test finds every ``themed_ss(...)`` call site whose second argument is a
string constant, extracts its format fields with ``string.Formatter().parse()``
(the same parser ``str.format_map()`` uses internally), and asserts each field
name is a real key in one of ui/styles.py's theme dicts — derived the same way
test_style_imports.py's ``_DYNAMIC_CONSTANTS`` is. Callable-form templates are
skipped: they're plain Python, already covered by normal NameError/AttributeError
at call time and by test_style_imports.py's bare-Name AST check.
"""

from __future__ import annotations

import ast
import re
import string
from pathlib import Path

ROOT = Path(__file__).parent.parent
_UI_ROOT = ROOT / "ui"
_STYLES_PATH = _UI_ROOT / "styles.py"

_styles_src = _STYLES_PATH.read_text(encoding="utf-8")

# Same derivation as test_style_imports.py's _DYNAMIC_CONSTANTS / this repo's
# test_frozen_token_ratchet.py — keys of either theme dict in ui/styles.py.
_DYNAMIC_CONSTANTS: frozenset[str] = frozenset(
    re.findall(r'"([A-Z][A-Z0-9_]{2,})":', _styles_src)
)


def _literal_str(node: ast.expr) -> "str | None":
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _themed_ss_calls(tree: ast.Module):
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if isinstance(fn, ast.Name) and fn.id == "themed_ss" and len(node.args) >= 2:
            yield node


def _ui_files() -> list[Path]:
    return sorted(p for p in _UI_ROOT.rglob("*.py") if p.name != "styles.py")


def test_themed_ss_string_templates_reference_real_tokens():
    offenders = []
    for path in _ui_files():
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        rel = path.relative_to(ROOT).as_posix()
        for call in _themed_ss_calls(tree):
            text = _literal_str(call.args[1])
            if text is None:
                continue  # callable-form template — nothing to statically check

            try:
                fields = [
                    name for _, name, _, _ in string.Formatter().parse(text)
                    if name  # skip literal-only trailing segment (name is None)
                ]
            except ValueError as exc:
                offenders.append(
                    f"{rel}:{call.lineno}: malformed themed_ss() template ({exc})"
                )
                continue

            for name in fields:
                # format_map only looks up the part before '.'/'[' — a themed_ss
                # template never needs attribute/index access on a token, but
                # validate against exactly what str.format_map would resolve.
                base = name.split(".")[0].split("[")[0]
                if base and base not in _DYNAMIC_CONSTANTS:
                    offenders.append(
                        f"{rel}:{call.lineno}: themed_ss() template references "
                        f"unknown token {{{name}}} — must be a key in one of "
                        "ui/styles.py's theme dicts"
                    )

    assert not offenders, (
        "themed_ss() templates referencing unknown style tokens:\n"
        + "\n".join(f"  {o}" for o in offenders)
    )
