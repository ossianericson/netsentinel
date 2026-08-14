"""Local/CI gate for import-hygiene issues that ruff's F401/F811/F841
selection (RULE-LINT1) does not catch: CodeQL py/import-and-import-from
(RULE-LINT4), py/cyclic-import, and py/unused-global-variable (RULE-LINT6).
See tools/check_import_lint.py for the detection logic and
BASELINE_IMPORT_AND_IMPORT_FROM / BASELINE_UNUSED_GLOBALS for grandfathered
debt.
"""
from __future__ import annotations

import pytest

from tools.check_import_lint import (
    REPO_ROOT,
    BASELINE_IMPORT_AND_IMPORT_FROM,
    BASELINE_UNUSED_GLOBALS,
    find_cyclic_import_violations,
    find_import_and_import_from_violations,
    find_shadowed_import_violations,
    find_unused_global_violations,
)


def test_no_new_import_and_import_from_violations():
    """No file may newly import a module both as `import X` and `from X import Y`.

    If this fails on a file you are actively changing, fix it the same way as
    the historical CodeQL cleanups: change the plain `import X` into
    `from <parent-package> import <leaf>` so the module string no longer
    collides (see RULE-LINT4). Do not add the new hit to
    BASELINE_IMPORT_AND_IMPORT_FROM -- that list is for pre-existing debt only.
    """
    violations = find_import_and_import_from_violations()
    assert not violations, "New import-and-import-from violations:\n" + "\n".join(
        f"  {v}" for v in violations
    )


def test_baseline_import_and_import_from_entries_are_current():
    """Every BASELINE_IMPORT_AND_IMPORT_FROM entry must still be a real violation.

    Once a baselined file is fixed, remove its entry -- a stale entry hides a
    regression if the same file reintroduces the pattern in a different form.
    """
    stale = []
    for rel_path, module in BASELINE_IMPORT_AND_IMPORT_FROM:
        path = REPO_ROOT / rel_path
        if not path.exists():
            stale.append((rel_path, module, "file no longer exists"))
            continue
        raw = find_import_and_import_from_violations(paths=[path], baseline=frozenset())
        if module not in {v.module for v in raw}:
            stale.append((rel_path, module, "no longer a violation -- remove from baseline"))

    assert not stale, "Stale BASELINE_IMPORT_AND_IMPORT_FROM entries:\n" + "\n".join(
        f"  {rel_path}: {module} -- {reason}" for rel_path, module, reason in stale
    )


def test_no_cyclic_imports():
    """modules/, ui/, and workers/ must not contain a module-level import cycle.

    A cycle here means two or more first-party modules whose top-level
    imports mutually depend on each other (CodeQL py/cyclic-import) -- the
    same class of bug fixed in commit 5cfbe22 (root_cause_correlator <->
    root_cause_correlator_alerts, utils <-> mac_lookup). Break the cycle by
    extracting the shared types/helpers both sides need into a third module,
    or by deferring one side's import into the function that uses it.
    """
    violations = find_cyclic_import_violations()
    assert not violations, "Cyclic first-party imports:\n" + "\n".join(
        f"  {v}" for v in violations
    )


def test_no_new_unused_globals():
    """No modules/, ui/, or workers/ file may add a module-level assignment
    that is never read -- in its own file, or by any other tracked file
    importing it (CodeQL py/unused-global-variable, RULE-LINT6).

    If this fails on a global you just added: either use it, delete it, or
    -- if it's a deliberate forward-declared constant / re-export -- add it
    to that module's `__all__`. Do not add the new hit to
    BASELINE_UNUSED_GLOBALS; that list is for pre-existing debt confirmed
    against this repo's CodeQL alert history, not a place to silence new
    violations.
    """
    violations = find_unused_global_violations()
    assert not violations, "New unused-global-variable violations:\n" + "\n".join(
        f"  {v}" for v in violations
    )


def test_baseline_unused_globals_entries_are_current():
    """Every BASELINE_UNUSED_GLOBALS entry must still be a real violation.

    Once a baselined name is genuinely wired up (or the module deleted),
    remove its entry -- a stale entry hides a regression if the same name
    is reintroduced elsewhere with different (real) dead-code semantics.
    """
    stale = []
    for rel_path, name in BASELINE_UNUSED_GLOBALS:
        path = REPO_ROOT / rel_path
        if not path.exists():
            stale.append((rel_path, name, "file no longer exists"))
            continue
        raw = find_unused_global_violations(candidate_paths=[path], baseline=frozenset())
        if name not in {v.name for v in raw}:
            stale.append((rel_path, name, "no longer a violation -- remove from baseline"))

    assert not stale, "Stale BASELINE_UNUSED_GLOBALS entries:\n" + "\n".join(
        f"  {rel_path}: {name} -- {reason}" for rel_path, name, reason in stale
    )


def test_no_conditionally_shadowed_imports():
    """A name imported inside a branch must not be used outside that branch.

    `import X` anywhere in a function makes X a LOCAL for the whole function,
    so a bare `import logging` inside an `if`/`try` shadows the module-level
    name at every other use site in that function -- which raises
    UnboundLocalError whenever the branch is not taken (CodeQL
    py/uninitialized-local-variable, RULE-LINT7). It shipped silently in
    app.py::main(): the shadowed use sat inside `except Exception: pass`, so
    the log line simply never appeared. Alias the conditional import
    (`import logging as _x_logging`) rather than widening its scope.
    """
    violations = find_shadowed_import_violations()
    assert not violations, "Conditionally shadowed import(s):\n" + "\n".join(
        f"  {v}" for v in violations
    )


# The tree-wide check above passes with zero violations, so on its own it would
# still pass if the detector stopped detecting. These two pin the behaviour.

_SHADOW_CASES = {
    "conditional_import_used_later": (
        "def main():\n"
        "    if not ok():\n"
        "        import logging\n"
        "        logging.getLogger('x').warning('a')\n"
        "    try:\n"
        "        logging.getLogger('x').info('b')\n"
        "    except Exception:\n"
        "        pass\n"
    ),
    "loop_import_used_after": (
        "def main():\n"
        "    for item in items():\n"
        "        import json\n"
        "    return json.dumps({})\n"
    ),
}

_SAFE_CASES = {
    # The optional-dependency guard: the handler closes the fall-through, so
    # code after the try is unreachable unless the import ran (RULE-AH4).
    "guard_returns": (
        "def scan():\n"
        "    try:\n"
        "        from scapy.all import IP\n"
        "    except ImportError:\n"
        "        return None\n"
        "    return IP()\n"
    ),
    "guard_raises": (
        "def engine(url):\n"
        "    try:\n"
        "        from sqlalchemy import create_engine\n"
        "    except ImportError as exc:\n"
        "        raise ImportError('install sqlalchemy') from exc\n"
        "    return create_engine(url)\n"
    ),
    "guard_exits": (
        "def cli():\n"
        "    try:\n"
        "        import click\n"
        "    except ImportError:\n"
        "        sys.exit(1)\n"
        "    return click.echo('hi')\n"
    ),
    # The handler re-binds the name, by import or by fallback definition.
    "handler_reimports": (
        "def toolbar(canvas):\n"
        "    try:\n"
        "        from mpl.qtagg import NavigationToolbar2QT\n"
        "    except ImportError:\n"
        "        from mpl.qt import NavigationToolbar2QT\n"
        "    return NavigationToolbar2QT(canvas)\n"
    ),
    "handler_defines_fallback": (
        "def render(units):\n"
        "    try:\n"
        "        from modules.deco_client import _norm_mac\n"
        "    except ImportError:\n"
        "        def _norm_mac(m):\n"
        "            return m.lower()\n"
        "    return {_norm_mac(u) for u in units}\n"
    ),
    # Unconditional import, and a use confined to the branch that imported it.
    "unconditional": (
        "def main():\n"
        "    import logging\n"
        "    if not ok():\n"
        "        logging.getLogger('x').warning('a')\n"
        "    return logging.getLogger('x')\n"
    ),
    "use_stays_inside_branch": (
        "def main():\n"
        "    if not ok():\n"
        "        import logging\n"
        "        logging.getLogger('x').warning('a')\n"
        "    return 1\n"
    ),
}


@pytest.mark.parametrize("name", sorted(_SHADOW_CASES))
def test_shadowed_import_detector_fires(tmp_path, name):
    """Each shape leaves the name unbound on at least one reachable path."""
    src = tmp_path / f"{name}.py"
    src.write_text(_SHADOW_CASES[name], encoding="utf-8")
    assert find_shadowed_import_violations(paths=[src]), (
        f"detector missed a real shadow ({name}):\n{_SHADOW_CASES[name]}"
    )


@pytest.mark.parametrize("name", sorted(_SAFE_CASES))
def test_shadowed_import_detector_stays_quiet(tmp_path, name):
    """Guard idioms bind the name on every path that can observe it.

    Without these the detector reports 44 sites across this repo — noise that
    would get the whole gate switched off rather than the one real bug fixed.
    """
    src = tmp_path / f"{name}.py"
    src.write_text(_SAFE_CASES[name], encoding="utf-8")
    violations = find_shadowed_import_violations(paths=[src])
    assert not violations, f"false positive on {name}:\n" + "\n".join(
        f"  {v}" for v in violations
    )
