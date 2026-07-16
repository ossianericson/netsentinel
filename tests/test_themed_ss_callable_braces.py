"""test_themed_ss_callable_braces.py — guard against unbalanced QSS braces in
themed_ss() callable templates.

MECHANISM (why this matters):
``ui.styles.themed_ss(widget, template)`` renders its template two different ways
depending on the argument type (see ``_render()`` in ui/styles.py):

  * a plain string goes through ``template.format_map(_LIVE_TOKENS)`` — Python's
    ``str.format`` collapses ``{{``/``}}`` to a literal ``{``/``}`` as part of
    that call, so writing a selector block like ``"QFrame {{ ... }}"`` is
    correct: it needs doubling because format_map collapses it exactly once.

  * a callable (almost always a lambda, used so the QSS re-evaluates live theme
    tokens on every theme/accent change) is invoked directly — ``template()`` —
    and its return value is used AS-IS, with NO subsequent format_map pass.
    Since the callable's body is itself an f-string, Python ALREADY collapses
    ``{{``/``}}`` to ``{``/``}`` once, at f-string-evaluation time. Doubling the
    braces inside a callable's f-string is therefore wrong: it survives as a
    literal ``{{``/``}}`` in the final QSS handed to Qt.

This exact mistake shipped in ``ui/pages/home_data_mixin.py`` (the Home page's
"pending alerts" strip): a lambda's QSS was written across two concatenated
string literals, one f-prefixed and one not —

    lambda: (
        f"QLabel {{ font-size:11px; color:{_s.TEXT_PRIMARY};"
        " background:transparent; border:none; }}"   # <- no f-prefix
    )

The first line's ``f"..."`` collapses its own ``{{`` to ``{`` correctly. The
second line has no ``f`` prefix, so Python does not touch its ``}}`` at all —
it survives as two literal closing braces. The lambda's return value ends up
``"QLabel { font-size:11px; color:#1A1A2E; background:transparent; border:none; }}"``
— one open brace, two close braces — which Qt's CSS parser cannot parse,
producing ``Could not parse stylesheet of object QLabel(0x...)`` on every
startup (the pending-alerts strip renders unconditionally while restoring the
last scan). Non-fatal (the label falls back to unstyled), but real: it was
silently dropping the row's styling.

DETECTION: by the time the AST exists, any f-string-derived text has already
had its own ``{{``/``}}`` collapsed to ``{``/``}``. If a ``{{`` or ``}}``
substring survives literally inside a ``JoinedStr`` Constant piece that is the
body of a ``themed_ss(widget, <lambda>)`` call, that piece did NOT go through
f-string collapsing — the only way that happens is a non-f-prefixed literal
implicitly concatenated into an otherwise-f-string expression. That is always
a bug for the callable-template case (unlike the plain-string-template case,
where deliberate double-escaping is legitimate — see
``ui/pages/speed_test_page.py``'s ``f"QFrame {{{{ {_hdr_style} }}}}"``, which
intentionally survives ONE collapse pass so ``_render()``'s later
``format_map()`` can do the second).
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).parent.parent
UI_DIR = ROOT / "ui"


def _find_offending_callable_templates() -> list[str]:
    offenders: list[str] = []
    for path in sorted(UI_DIR.rglob("*.py")):
        try:
            src = path.read_text(encoding="utf-8-sig")
            tree = ast.parse(src, filename=str(path))
        except Exception:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else (
                fn.id if isinstance(fn, ast.Name) else None
            )
            if name != "themed_ss" or len(node.args) < 2:
                continue
            tmpl = node.args[1]
            if not isinstance(tmpl, ast.Lambda):
                continue
            for sub in ast.walk(tmpl.body):
                if not isinstance(sub, ast.JoinedStr):
                    continue
                for v in sub.values:
                    if isinstance(v, ast.Constant) and isinstance(v.value, str):
                        if "{{" in v.value or "}}" in v.value:
                            rel = path.relative_to(ROOT).as_posix()
                            offenders.append(
                                f"{rel}:{node.lineno}  fragment={v.value!r}"
                            )
    return offenders


def test_no_unbalanced_braces_in_themed_ss_callables():
    offenders = _find_offending_callable_templates()
    assert not offenders, (
        "themed_ss(widget, <lambda>) callable template(s) contain a literal "
        "'{{' or '}}' that survived f-string evaluation — this means part of "
        "the template was NOT f-string-prefixed, so Qt receives unbalanced "
        "braces and drops the whole stylesheet ('Could not parse stylesheet'). "
        "Callables are rendered once via direct call (no format_map pass), so "
        "every concatenated literal in the lambda body must carry the 'f' "
        "prefix. Offenders:\n  " + "\n  ".join(offenders)
    )
