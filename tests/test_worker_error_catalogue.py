"""S5 — the fixed text behind every converted worker-error site, and the sites' references to it.

Two failure modes this guards, both invisible until a user hits the error:

* **Wording drift** — an entry that says nothing, embeds markup, or is too long for a status
  label that does not wrap (17 of the 24 converted labels do not; a long non-wrapping QLabel
  also raises its page's minimum width).
* **A broken reference on the error path.** ``show_worker_error(lbl, e, WE.TYPO)`` sits inside
  an error-signal lambda, so an ``AttributeError`` there fires only when the scan actually
  fails — and then reaches the crash dialog instead of the user's message. The AST check below
  resolves every reference statically.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

#: Visible budget for ``worker_error_text(spec)`` — owner decision 2026-09-17: fit the
#: non-wrapping labels instead of changing their layout.
MAX_VISIBLE_CHARS = 140

#: Specs from outside the catalogue that a site may pass, by the bare name it is imported as.
_EXTERNAL_SPECS = {"SYSLOG_RECEIVER", "SNMP_TRAP_RECEIVER"}
#: Helper name -> index of its spec argument.
_HELPERS = {"show_worker_error": 2, "worker_error_text": 0, "record_worker_error": 0,
            "export_failed": 1, "show_error_dialog": 2}

#: An entry that opts in to ``error_text`` explanations is shown only where text wraps (a toast, a
#: dialog, a wrapping label): the explanation's wording is longer than a status-label budget.
MAX_EXPLAINED_CHARS = 220


def _catalogue():
    from ui import worker_error_catalogue
    return worker_error_catalogue


def test_every_entry_is_complete_and_plain():
    cat = _catalogue()
    assert cat.ALL, "the catalogue is empty"
    for name, spec in cat.ALL.items():
        assert isinstance(spec, cat.WorkerErrorSpec), name
        for field in ("key", "what", "why", "next_step"):
            value = getattr(spec, field)
            assert value.strip(), f"{name}.{field} is empty"
            assert "<" not in value and "{" not in value, f"{name}.{field} carries markup/format text"
        assert not spec.what.endswith("."), f"{name}.what is a fragment: the helper adds the period"
        assert spec.why.endswith(".") and spec.next_step.endswith("."), f"{name}: why/next are sentences"


def test_every_explained_kind_is_one_error_text_can_return():
    """A misspelled kind would never match, silently keeping the fixed text forever."""
    from modules.error_text import KINDS

    unknown = {
        name: sorted(spec.explains - KINDS)
        for name, spec in _catalogue().ALL.items()
        if spec.explains - KINDS
    }
    assert not unknown, f"explains names kinds error_text never returns: {unknown}"
    assert all("unknown" not in spec.explains for spec in _catalogue().ALL.values()), (
        "'unknown' carries no site-specific cause; the entry's own why/next is always better"
    )


def test_the_file_entries_opt_in_to_every_location_kind():
    from ui.error_display import LOCATION_KINDS

    assert _catalogue().FILE_KINDS >= LOCATION_KINDS


def test_every_explained_message_fits_a_wrapping_surface():
    too_long = {}
    for name, spec in _catalogue().ALL.items():
        for kind in spec.explains:
            exp = _explanation_for(kind)
            shown = f"{spec.what}. {exp.why} {exp.next_step}"
            if len(shown) > MAX_EXPLAINED_CHARS:
                too_long[f"{name}/{kind}"] = len(shown)
    assert not too_long, f"over {MAX_EXPLAINED_CHARS} characters: {too_long}"


def _explanation_for(kind):
    """A real exception of ``kind``, classified by the real explain()."""
    import errno

    from modules.error_text import explain

    samples = {
        "path_not_found": FileNotFoundError(errno.ENOENT, "saknas", "x.csv"),
        "invalid_path": OSError(errno.EINVAL, "ogiltig", "a<b>.csv"),
        "permission_denied": PermissionError(errno.EACCES, "nekad", "x.csv"),
        "disk_full": OSError(errno.ENOSPC, "full"),
    }
    exp = explain(samples[kind] if kind in samples else _real_error(kind))
    assert exp.kind == kind, f"no sample for {kind}: add one to _explanation_for"
    return exp


def _real_error(kind):
    """Kinds whose code cannot be set on a hand-built exception: raise the real thing (RULE-DBG5)."""
    import sqlite3
    import tempfile
    from pathlib import Path

    assert kind == "database_busy", f"no sample for {kind}: add one to _explanation_for"
    with tempfile.TemporaryDirectory() as folder:
        path = str(Path(folder) / "busy.db")
        holder = sqlite3.connect(path)
        other = sqlite3.connect(path, timeout=0)
        try:
            holder.execute("CREATE TABLE t (x)")
            holder.commit()
            holder.execute("BEGIN EXCLUSIVE")
            try:
                other.execute("INSERT INTO t VALUES (1)")
            except sqlite3.OperationalError as exc:
                return exc
            raise AssertionError("a second writer was not blocked by an exclusive transaction")
        finally:
            holder.rollback()
            holder.close()
            other.close()


def test_keys_are_unique():
    keys = [spec.key for spec in _catalogue().ALL.values()]
    assert len(keys) == len(set(keys)), sorted(k for k in keys if keys.count(k) > 1)


def test_every_message_fits_a_status_label_that_does_not_wrap():
    pytest.importorskip("PyQt6")
    from ui.error_display import worker_error_text

    too_long = {
        name: len(worker_error_text(spec))
        for name, spec in _catalogue().ALL.items()
        if len(worker_error_text(spec)) > MAX_VISIBLE_CHARS
    }
    assert not too_long, f"over {MAX_VISIBLE_CHARS} visible characters: {too_long}"


def _helper_calls():
    """(path, line, spec node) for every error-display helper call outside the helper itself."""
    for path in sorted((REPO / "ui").rglob("*.py")):
        rel = path.relative_to(REPO).as_posix()
        if rel == "ui/error_display.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None
            if name in _HELPERS and len(node.args) > _HELPERS[name]:
                yield rel, node.lineno, node.args[_HELPERS[name]]


def test_every_site_names_a_spec_that_exists():
    cat = _catalogue()
    unresolved = []
    for rel, line, spec in _helper_calls():
        if isinstance(spec, ast.Attribute) and isinstance(spec.value, ast.Name) and spec.value.id == "WE":
            if spec.attr not in cat.ALL:
                unresolved.append(f"{rel}:{line} WE.{spec.attr}")
        elif not (isinstance(spec, ast.Name) and spec.id in _EXTERNAL_SPECS):
            unresolved.append(f"{rel}:{line} {ast.unparse(spec)}")
    assert not unresolved, "error-path references that would raise when the scan fails:\n" + "\n".join(unresolved)


def test_every_entry_is_used_by_a_site():
    """An unused entry is wording nobody sees — delete it or wire its site."""
    used = {
        spec.attr for _rel, _line, spec in _helper_calls()
        if isinstance(spec, ast.Attribute) and isinstance(spec.value, ast.Name) and spec.value.id == "WE"
    }
    unused = sorted(set(_catalogue().ALL) - used)
    assert not unused, f"catalogue entries no site passes: {unused}"
