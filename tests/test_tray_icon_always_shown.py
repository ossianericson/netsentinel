"""
tests/test_tray_icon_always_shown.py — Phase 5.5 guard (RULE-WIN10 / plan 5.5).

show_tray_icon() (ui/system_tray.py) must be called from exactly two places:
  1. AppHeaderMixin.showEvent() (ui/header.py) — the normal-launch path.
  2. app.py's main(), on a parented QTimer scheduled after every _splash_msg()
     pump — the only path a tray-only (_start_minimised) launch has, since
     that launch never calls window.show() and showEvent() never fires.

A tray-only launch with neither call site wired is a running process with
zero UI affordance: no window (by design) AND no tray icon (the bug this
guards). AST-based because no runtime test can force "the window is never
shown" and still observe whether the tray icon appeared — the invariant is
structural (which code paths exist), not a value to compute at runtime.
"""
from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

_SCAN_ROOTS = [
    REPO / "app.py",
    *sorted((REPO / "ui").rglob("*.py")),
    *sorted((REPO / "workers").rglob("*.py")),
    *sorted((REPO / "modules").rglob("*.py")),
]


def _find_show_tray_icon_calls(path: Path) -> list[int]:
    """Line numbers of every `<expr>.show_tray_icon(...)` call in *path*."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    lines = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "show_tray_icon"
        ):
            lines.append(node.lineno)
    return lines


def test_show_tray_icon_call_sites_are_exactly_showevent_and_main():
    found: dict[str, list[int]] = {}
    for path in _SCAN_ROOTS:
        lines = _find_show_tray_icon_calls(path)
        if lines:
            found[str(path.relative_to(REPO)).replace("\\", "/")] = lines

    # The definition site itself (ui/system_tray.py) must never call itself.
    assert "ui/system_tray.py" not in found

    assert set(found) == {"app.py", "ui/header.py"}, (
        f"show_tray_icon() call sites drifted from the two expected — found: {found}. "
        "A tray-only launch never calls window.show(), so showEvent() (ui/header.py) "
        "never fires; app.py's QTimer-scheduled call is the ONLY thing that shows "
        "the tray icon on that path. Removing or relocating either call site risks "
        "a running process with zero UI affordance."
    )
    assert len(found["app.py"]) == 1
    assert len(found["ui/header.py"]) == 1


def test_header_call_site_is_inside_showevent():
    src = (REPO / "ui" / "header.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    show_event_fn = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "showEvent"
    )
    calls_in_show_event = [
        node.func.attr
        for node in ast.walk(show_event_fn)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]
    assert "show_tray_icon" in calls_in_show_event


def test_app_py_call_site_is_after_the_last_splash_msg_call():
    """Source-order guard: placing the QTimer.start(0) call before the last
    _splash_msg() pump reintroduces the exact bug docs/spikes/
    startup-com-reentrancy.md's "Fix attempt 1" hit — a 0ms timer fired
    prematurely by the very pump it was meant to run after."""
    src = (REPO / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    main_fn = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "main"
    )
    start, end = main_fn.lineno, main_fn.end_lineno
    body_lines = src.splitlines()[start - 1:end]
    body = "\n".join(body_lines)

    last_splash_msg_pos = body.rfind("_splash_msg(")
    show_tray_icon_pos = body.find("show_tray_icon(")
    assert last_splash_msg_pos != -1, "expected _splash_msg( calls inside main()"
    assert show_tray_icon_pos != -1, "expected a show_tray_icon( call inside main()"
    assert last_splash_msg_pos < show_tray_icon_pos, (
        "the tray-icon QTimer must be scheduled AFTER the last _splash_msg() "
        "pump in main() — scheduling it earlier lets a later processEvents() "
        "call fire the 0ms timer prematurely, the exact mechanism RULE-WIN10's "
        "'Fix attempt 1' history documents as ineffective."
    )
