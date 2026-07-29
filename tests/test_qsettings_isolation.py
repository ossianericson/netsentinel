"""The suite must not leave the developer's real `ui/theme` clobbered.

`ui/styles.py::apply_theme()` ends by calling `set_active_theme_name()`, which
persists "ui/theme" to the real QSettings store. `test_charts_theme_switch.py`
and `test_badge_medallion.py` drive the REAL `apply_theme("Arctic Clean")`, so a
full suite run rewrote the developer's own saved theme — verified live
2026-07-22: `Midnight Pro` before a run, `Arctic Clean` after. Those files
restore the prior value at the end, but only if they run to completion; a
mid-file failure left the developer stuck on the wrong theme.

**Why the store is not simply sandboxed** (both verified experimentally, so the
next person does not retry them):

* `QSettings.setDefaultFormat(IniFormat)` does NOT affect
  `QSettings(organization, application)` — that constructor hard-selects
  `NativeFormat`. `defaultFormat()` reports IniFormat while the instance's
  `format()` is still NativeFormat.
* `QSettings.setPath(NativeFormat, UserScope, ...)` has no effect on Windows,
  where NativeFormat is the registry. A redirect attempt wrote straight through
  to the real key.

So the safety net is `conftest.py::_preserve_real_theme`, a session-scoped
autouse fixture whose finalizer runs even when tests fail. This module guards
that the net still exists.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

CONFTEST = Path(__file__).resolve().parent / "conftest.py"


def _conftest_functions() -> dict[str, ast.FunctionDef]:
    tree = ast.parse(CONFTEST.read_text(encoding="utf-8"))
    return {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def test_conftest_defines_the_theme_preserving_fixture():
    funcs = _conftest_functions()
    assert "_preserve_real_theme" in funcs, (
        "conftest.py must define the _preserve_real_theme fixture. Without it a "
        "full test run permanently rewrites the developer's ui/theme to "
        "'Arctic Clean', because apply_theme() persists to the real QSettings "
        "and the theme tests drive the real apply_theme()."
    )


def test_theme_fixture_is_session_scoped_and_autouse():
    fn = _conftest_functions()["_preserve_real_theme"]
    decorators = [ast.unparse(d) for d in fn.decorator_list]
    joined = " ".join(decorators)

    assert "autouse=True" in joined, (
        "_preserve_real_theme must be autouse — an opt-in fixture protects "
        "nothing, since the offending theme tests do not request it."
    )
    assert 'scope="session"' in joined or "scope='session'" in joined, (
        "_preserve_real_theme must be session-scoped so it brackets the whole "
        "run, including the theme tests."
    )


def test_theme_fixture_restores_in_a_finally_block():
    """The restore must survive a red suite — that is the entire point."""
    fn = _conftest_functions()["_preserve_real_theme"]
    has_try_finally = any(
        isinstance(node, ast.Try) and node.finalbody for node in ast.walk(fn)
    )
    assert has_try_finally, (
        "_preserve_real_theme must restore inside a finally block; the original "
        "bug was precisely that the theme tests' own restore was skipped when a "
        "test failed part-way through."
    )


def test_theme_fixture_handles_a_previously_unset_key():
    """A dev with no saved theme must not gain a spurious one."""
    src = ast.unparse(_conftest_functions()["_preserve_real_theme"])
    assert "remove" in src and "None" in src, (
        "_preserve_real_theme must remove ui/theme when it was unset before the "
        "run, rather than writing back the literal None."
    )


@pytest.mark.parametrize("module_name", [
    "test_charts_theme_switch",
    "test_badge_medallion",
])
def test_known_real_apply_theme_callers_are_still_the_known_set(module_name):
    """If a new file starts driving the real apply_theme, surface it here.

    Not a failure condition on its own — these two are expected. It documents
    the blast radius so the next person knows where to look.
    """
    path = Path(__file__).resolve().parent / f"{module_name}.py"
    assert path.exists(), (
        f"{module_name}.py no longer exists — update this guard and the "
        "_preserve_real_theme docstring if the theme tests were reorganised."
    )


def test_conftest_defines_the_window_settings_preserving_fixture():
    funcs = _conftest_functions()
    assert "_preserve_real_window_settings" in funcs, (
        "conftest.py must define the _preserve_real_window_settings fixture. "
        "Without it, tests/_lazy_pages_child.py, tests/_startup_minimised_child.py "
        "and tests/_theme_switch_deferred_child.py each construct a real, "
        "never-shown Dashboard whose dash.close() unconditionally writes the "
        "developer's real on-disk NetSentinel.ini with a degenerate geometry "
        "(confirmed live via an MD5 hash of the file before/after a run)."
    )


def test_window_settings_fixture_is_session_scoped_and_autouse():
    fn = _conftest_functions()["_preserve_real_window_settings"]
    decorators = [ast.unparse(d) for d in fn.decorator_list]
    joined = " ".join(decorators)

    assert "autouse=True" in joined, (
        "_preserve_real_window_settings must be autouse — an opt-in fixture "
        "protects nothing, since the offending subprocess-child tests do not "
        "request it."
    )
    assert 'scope="session"' in joined or "scope='session'" in joined, (
        "_preserve_real_window_settings must be session-scoped so it brackets "
        "the whole run."
    )


def test_window_settings_fixture_restores_in_a_finally_block():
    """The restore must survive a red suite — that is the entire point."""
    fn = _conftest_functions()["_preserve_real_window_settings"]
    has_try_finally = any(
        isinstance(node, ast.Try) and node.finalbody for node in ast.walk(fn)
    )
    assert has_try_finally, (
        "_preserve_real_window_settings must restore inside a finally block; "
        "a subprocess child that crashes mid-test must not leave the "
        "developer's real NetSentinel.ini clobbered."
    )


@pytest.mark.parametrize("module_name", [
    "_lazy_pages_child",
    "_startup_minimised_child",
    "_theme_switch_deferred_child",
])
def test_known_dashboard_subprocess_children_redirect_settings_path(module_name):
    """Every subprocess child that constructs a real Dashboard must redirect
    ui.app_settings.settings_path before doing so — the session fixture above
    is the backstop, not a substitute for not corrupting the file in the
    first place transiently mid-run (other tests may read it in between).
    """
    path = Path(__file__).resolve().parent / f"{module_name}.py"
    assert path.exists(), (
        f"{module_name}.py no longer exists — update this guard if the "
        "subprocess-child tests were reorganised."
    )
    src = path.read_text(encoding="utf-8")
    assert "_app_settings.settings_path = " in src, (
        f"{module_name}.py constructs a real Dashboard and calls dash.close(), "
        "which runs the real closeEvent()/save_settings() -- it must redirect "
        "ui.app_settings.settings_path to an isolated temp file before "
        "constructing any Dashboard, or every test-suite run silently "
        "overwrites the developer's real window geometry."
    )
