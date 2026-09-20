"""Census of how caught failures reach -- or fail to reach -- the user.

Error-surfacing audit S0.1 (`docs/internal/error-surfacing-audit-2026-09-15.md`).

The crash net (`modules/crash_net.py`) records what escapes. This scanner looks
underneath it, at failures that are caught and then go nowhere useful. It measures:

  (a) ``find_raw_exception_ui_sinks``  -- a raw exception or worker error string
      written straight into a user-visible sink (RULE-A2).
  (b) ``find_silent_broad_handlers``   -- a broad ``except`` whose body is only
      ``pass`` or a constant/name fallback: no log line, no signal, no UI write.
  (c) ``find_invalid_toast_kinds``     -- ``ToastManager.show()`` with a kind that
      ``ui/widgets/toast.py`` does not define (it silently renders as a sticky
      info toast).
  (d) ``find_scan_labels_without_error_path`` -- a scan-registry label that code can
      set ``running``/``fresh`` but never ``error``/``not_testable``, so a failed run
      shows as still-running or as the last success.
  ``find_stringified_exception_args`` -- an error-display helper handed ``str(exc)``
      (or any expression of it) inside ``except ... as exc``; it needs the exception.

Everything here is a pointer, not a verdict. Most silent swallows are legitimate,
and `tests/test_error_surfacing_ratchet.py` therefore ratchets (b)-(d): nothing new
may appear, and the baselines only move down. (a) and the stringified-argument guard
are held at zero (S6b).

Known blind spots (all make the scanner UNDER-count, never over-count):
  * (a) recognises a raw value only by how it was bound -- an ``except ... as X``
    name, a parameter of an error slot (``on_error``, ``_on_scan_failed``,
    ``_on_abuse_not_testable``), or a parameter of a lambda connected to an
    error/failure signal. A value laundered through a local or a call first
    (``msg = str(exc); lbl.setText(msg)``) is invisible, and so is a lambda passed as
    a callback keyword (``IoTMonitor(on_error=lambda m: lbl.setText(m))``) or text
    emitted into another file's sink (``.emit(str(exc))``).
  * (a) sinks are widget writes (``setText``, ``showMessage``, the ``ui/`` append
    family, a local or method ``_set_status``), chart text (``set_title``,
    ``Axes.text``), ``QListWidgetItem(...)``, message boxes and toasts — plus, in the
    entry points only, the headless surfaces ``print`` and ``servicemanager.Log*Msg``
    (S10.1). A banner's
    ``.update(text, level)`` is not a sink here -- too many unrelated ``update``
    methods; each such site is pinned by its own behavioural test instead.
  * Log calls are recognised by the receiver's name (``log``, ``_log``, ``logger``,
    ``logging.getLogger(...)``, ``*_log``). A logger bound to an unusual name
    counts as "other".
  * (d) ignores labels passed as variables, and cannot see an error shown through
    some other mechanism (a page-local label). A hit asks "where does this label's
    failure go?" -- read the handler before concluding it goes nowhere.

Usage: ``python tools/check_error_surfacing.py`` prints the full census;
``--worksheet [PATH ...]`` prints the (b) hits as a per-file Markdown triage worksheet
(S7.1) -- function, what the ``try`` attempts, the fallback, the handler's own comment and
shape facts (import / loop / OS branch / nested), with a blank verdict column.
"""
from __future__ import annotations

import argparse
import ast
import io
import re
import sys
import tokenize
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, FrozenSet, Iterator, List, Mapping, Optional, Set

REPO_ROOT = Path(__file__).resolve().parent.parent
PROD_DIRS = ("modules", "ui", "workers")
PROD_ENTRYPOINTS = ("app.py", "cli.py", "svc.py")

CATEGORIES = ("pass", "silent_default", "log_low_only", "other", "log_high", "surfaced", "reraise")
SILENT_CATEGORIES: FrozenSet[str] = frozenset({"pass", "silent_default"})

_LOG_LOW = frozenset({"debug", "info"})
_LOG_HIGH = frozenset({"warning", "warn", "error", "exception", "critical", "fatal"})
_LOGGER_TOKEN = re.compile(r"^(_*log|_*logger|_*logging|getLogger|\w+_log|\w+_logger)$")
_MESSAGE_BOX_METHODS = frozenset({"warning", "critical", "information", "question", "about"})
# Writes the user reads as the message itself. Tooltips and QMessageBox.setDetailedText
# are deliberately absent: that is where raw text belongs (RULE-A1 technical detail).
_RAW_SINK_ATTRS = frozenset({
    "setText", "showMessage", "setPlainText", "appendPlainText", "_set_status", "set_status",
})
_SURFACE_ATTRS = _RAW_SINK_ATTRS | {"_nav_set_scan_state"}
# S6b.4 sink shapes, for (a) only — (b)'s handler classification is unchanged by them.
_CHART_SINK_ATTRS = frozenset({"set_title"})
_AXES_RECEIVER = re.compile(r"(^|\.)_?ax(es)?$")
#: Bare-name calls: a list item's constructor, and a status writer defined as a local function.
_RAW_SINK_NAMES = frozenset({"QListWidgetItem", "_set_status", "set_status"})
#: Text-pane writes. Owner decision S6.4: ``ui/`` only — elsewhere ``append`` is a list's.
_UI_ONLY_SINK_ATTRS = frozenset({"append", "appendHtml", "insertPlainText", "setHtml"})
#: S10.1 — the surfaces a headless run leaves behind. A service writes to the Windows Event
#: Log and a CLI writes to the console; both are read by a person and neither can hold a
#: tooltip, so RULE-A2 applies to them exactly as it does to a label. Scoped to the entry
#: points the way _UI_ONLY_SINK_ATTRS is scoped to ``ui/``: elsewhere a ``print`` is a
#: developer's, not a user's.
_HEADLESS_SINK_ATTRS = frozenset({"LogErrorMsg", "LogWarningMsg", "LogInfoMsg"})
_HEADLESS_SINK_NAMES = frozenset({"print"})
#: Error-display helpers (``ui/error_display.py``) -> index of their ``raw`` argument.
_ERROR_HELPER_RAW_ARG = {
    "show_worker_error": 1, "worker_error_text": 1, "record_worker_error": 1,
    "export_failed": 0, "show_error_dialog": 1,
}
_BROAD_NAMES = frozenset({"Exception", "BaseException"})
_ERROR_SLOT = re.compile(r"^_?on_\w*(error|fail|not_testable)", re.IGNORECASE)
_ERROR_SIGNAL = re.compile(r"(error|fail)", re.IGNORECASE)
_ERROR_STATES = frozenset({"error", "not_testable"})
_PROGRESS_STATES = frozenset({"running", "fresh"})


@dataclass(frozen=True)
class Hit:
    path: str    # repo-relative, forward slashes
    line: int
    detail: str


# ── Source loading ───────────────────────────────────────────────────────────

def _iter_production_files() -> Iterator[Path]:
    for d in PROD_DIRS:
        root = REPO_ROOT / d
        if root.exists():
            yield from sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)
    for name in PROD_ENTRYPOINTS:
        path = REPO_ROOT / name
        if path.exists():
            yield path


@lru_cache(maxsize=1)
def load_production_sources() -> Mapping[str, str]:
    """relpath -> source for every production file. Cached; do not mutate."""
    return {
        p.relative_to(REPO_ROOT).as_posix(): p.read_text(encoding="utf-8")
        for p in _iter_production_files()
    }


@lru_cache(maxsize=4096)
def _parse(path: str, source: str) -> Optional[ast.Module]:
    try:
        return ast.parse(source, filename=path)
    except SyntaxError:
        return None


def _trees(sources: Optional[Mapping[str, str]]) -> Iterator[tuple[str, ast.Module]]:
    src_map = load_production_sources() if sources is None else sources
    for path in sorted(src_map):
        tree = _parse(path, src_map[path])
        if tree is not None:
            yield path, tree


def area_of(path: str) -> str:
    head = path.split("/", 1)[0]
    return head if head in PROD_DIRS else "entrypoints"


def count_by_area(hits: List[Hit]) -> Dict[str, int]:
    return dict(sorted(Counter(area_of(h.path) for h in hits).items()))


# ── Handler classification ───────────────────────────────────────────────────

def is_broad(handler: ast.ExceptHandler) -> bool:
    if handler.type is None:
        return True
    names = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
    for node in names:
        if isinstance(node, ast.Name) and node.id in _BROAD_NAMES:
            return True
        if isinstance(node, ast.Attribute) and node.attr in _BROAD_NAMES:
            return True
    return False


def _log_level(call: ast.Call) -> Optional[str]:
    func = call.func
    if not isinstance(func, ast.Attribute):
        return None
    if func.attr not in _LOG_LOW and func.attr not in _LOG_HIGH:
        return None
    tokens = re.findall(r"[A-Za-z_]\w*", ast.unparse(func.value))
    return func.attr if any(_LOGGER_TOKEN.match(t) for t in tokens) else None


def _is_traceback_print(call: ast.Call) -> bool:
    func = call.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr in {"print_exc", "print_exception"}
        and ast.unparse(func.value).endswith("traceback")
    )


def _is_ui_surface(call: ast.Call) -> bool:
    func = call.func
    if not isinstance(func, ast.Attribute):
        return False
    if func.attr == "emit":
        return True
    receiver = ast.unparse(func.value)
    if receiver.endswith("QMessageBox") and func.attr in _MESSAGE_BOX_METHODS:
        return True
    if "ToastManager" in receiver:
        return True
    return func.attr in _SURFACE_ATTRS


def _is_simple_value(node: Optional[ast.AST]) -> bool:
    if node is None:
        return True
    if isinstance(node, ast.UnaryOp):
        return isinstance(node.operand, ast.Constant)
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return all(_is_simple_value(e) for e in node.elts)
    if isinstance(node, ast.Dict):
        return all(k is None or _is_simple_value(k) for k in node.keys) and all(
            _is_simple_value(v) for v in node.values
        )
    return isinstance(node, (ast.Constant, ast.Name, ast.Attribute))


def _is_constant_fallback(stmt: ast.stmt) -> bool:
    if isinstance(stmt, (ast.Pass, ast.Continue, ast.Break)):
        return True
    if isinstance(stmt, ast.Return):
        return _is_simple_value(stmt.value)
    if isinstance(stmt, (ast.Assign, ast.AnnAssign)):
        return _is_simple_value(stmt.value)
    return isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant)


def classify_handler(handler: ast.ExceptHandler) -> str:
    """One of CATEGORIES. Loudest outcome wins: reraise > surfaced > log_high > log_low."""
    if all(isinstance(s, ast.Pass) for s in handler.body):
        return "pass"
    kinds: Set[str] = set()
    for stmt in handler.body:
        for node in ast.walk(stmt):
            if isinstance(node, ast.Raise):
                kinds.add("reraise")
            elif isinstance(node, ast.Call):
                level = _log_level(node)
                if level is not None:
                    kinds.add("log_low" if level in _LOG_LOW else "log_high")
                elif _is_traceback_print(node):
                    kinds.add("log_high")
                elif _is_ui_surface(node):
                    kinds.add("surfaced")
    for kind, category in (("reraise", "reraise"), ("surfaced", "surfaced"),
                           ("log_high", "log_high"), ("log_low", "log_low_only")):
        if kind in kinds:
            return category
    if all(_is_constant_fallback(s) for s in handler.body):
        return "silent_default"
    return "other"


def census_by_area(sources: Optional[Mapping[str, str]] = None) -> Dict[str, Counter]:
    """area -> Counter of "broad:<category>" / "narrow:<category>" for every handler."""
    result: Dict[str, Counter] = {}
    for path, tree in _trees(sources):
        counter = result.setdefault(area_of(path), Counter())
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                scope = "broad" if is_broad(node) else "narrow"
                counter[f"{scope}:{classify_handler(node)}"] += 1
    return result


def find_silent_broad_handlers(sources: Optional[Mapping[str, str]] = None) -> List[Hit]:
    hits: List[Hit] = []
    for path, tree in _trees(sources):
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and is_broad(node):
                category = classify_handler(node)
                if category in SILENT_CATEGORIES:
                    hits.append(Hit(path, node.lineno, category))
    return sorted(hits, key=lambda h: (h.path, h.line))


# ── S7.1 triage worksheet (--worksheet) ─────────────────────────────────────

_WINDOWS_TEST = re.compile(r"Windows|['\"]win|IS_WIN|['\"]nt['\"]")
_OTHER_OS_TEST = re.compile(r"Darwin|Linux|darwin|linux")
_NEGATING_OPS = (ast.NotEq, ast.IsNot, ast.NotIn)
_ATTEMPT_WIDTH = 72
_VERDICT_KEY = (
    "Verdicts: **(a)** expected → `log.debug(..., exc_info=True)` · **(b)** degrades a result → "
    "the result carries degraded / partial / not_testable · **(c)** disables a feature → "
    "app-health condition."
)


@dataclass(frozen=True)
class WorksheetRow:
    """One silent broad handler plus the facts a triager would otherwise re-read for.

    The verdict -- (a) expected, (b) degrades a result, (c) disables a feature -- is never
    inferred here: it depends on what the caller does with the fallback, which an AST of
    one file cannot see. ``shapes`` are facts, not hints at a verdict.
    """
    path: str
    line: int
    category: str              # "pass" | "silent_default"
    function: str              # qualified enclosing def/class, or "<module>"
    attempt: str               # first statement of the try body
    fallback: str              # the handler body on one line
    comment: str               # comments on the handler's lines -- RULE-LINT2's stated reason
    shapes: tuple[str, ...]    # subset of: import, loop, windows | non-windows, nested


def _comments_by_line(source: str) -> Dict[int, str]:
    return {
        tok.start[0]: tok.string.lstrip("#").strip()
        for tok in tokenize.generate_tokens(io.StringIO(source).readline)
        if tok.type == tokenize.COMMENT
    }


def _qualified_name(node: ast.AST, parents: Dict[ast.AST, ast.AST]) -> str:
    names: List[str] = []
    while node in parents:
        node = parents[node]
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(node.name)
    return ".".join(reversed(names)) or "<module>"


def _attempt(body: List[ast.stmt]) -> str:
    first = ast.unparse(body[0]).splitlines()[0]
    if len(first) > _ATTEMPT_WIDTH:
        first = first[: _ATTEMPT_WIDTH - 1] + "…"
    return f"{first}  (+{len(body) - 1} more)" if len(body) > 1 else first


def _platform_of_branch(if_node: ast.If, child: ast.AST) -> Optional[str]:
    """"windows" / "non-windows" when *child* sits in an OS-specific branch of *if_node*."""
    test = if_node.test
    negated = isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not)
    if isinstance(test, ast.Compare):
        negated = any(isinstance(op, _NEGATING_OPS) for op in test.ops)
    in_body = any(child is stmt for stmt in if_node.body) != negated
    text = ast.unparse(test)
    if _WINDOWS_TEST.search(text):
        return "windows" if in_body else "non-windows"
    if _OTHER_OS_TEST.search(text) and in_body:
        return "non-windows"
    return None  # not an OS test, or the else of a non-Windows test -- look further up


def _shapes(handler: ast.ExceptHandler, try_node: ast.Try | ast.TryStar,
            parents: Dict[ast.AST, ast.AST]) -> tuple[str, ...]:
    shapes: List[str] = []
    if all(isinstance(s, (ast.Import, ast.ImportFrom)) for s in try_node.body):
        shapes.append("import")
    loop = nested = inside_def = False
    platform: Optional[str] = None
    node: ast.AST = try_node
    while node in parents:
        parent = parents[node]
        if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            inside_def = True  # loops and handlers outside the def are not this code's
        elif isinstance(parent, (ast.For, ast.AsyncFor, ast.While)) and not inside_def:
            loop = True
        elif isinstance(parent, ast.ExceptHandler) and not inside_def:
            nested = True
        elif isinstance(parent, ast.If) and platform is None:
            platform = _platform_of_branch(parent, node)
        node = parent
    if loop:
        shapes.append("loop")
    if platform:
        shapes.append(platform)
    if nested:
        shapes.append("nested")
    return tuple(shapes)


def _path_selected(path: str, paths: Optional[List[str]]) -> bool:
    if not paths:
        return True
    for wanted in paths:
        prefix = wanted.replace("\\", "/").rstrip("/")
        if path == prefix or path.startswith(prefix + "/"):
            return True
    return False


def build_worksheet(sources: Optional[Mapping[str, str]] = None,
                    paths: Optional[List[str]] = None) -> List[WorksheetRow]:
    """One row per ``find_silent_broad_handlers`` hit, limited to *paths* (files or dirs)."""
    src_map = load_production_sources() if sources is None else sources
    rows: List[WorksheetRow] = []
    for path, tree in _trees(src_map):
        if not _path_selected(path, paths):
            continue
        parents = _parents(tree)
        comments = _comments_by_line(src_map[path])
        for node in ast.walk(tree):
            if not (isinstance(node, ast.ExceptHandler) and is_broad(node)):
                continue
            category = classify_handler(node)
            if category not in SILENT_CATEGORIES:
                continue
            try_node = parents[node]
            assert isinstance(try_node, (ast.Try, ast.TryStar))
            end = node.end_lineno or node.lineno
            rows.append(WorksheetRow(
                path=path,
                line=node.lineno,
                category=category,
                function=_qualified_name(node, parents),
                attempt=_attempt(try_node.body),
                fallback="; ".join(ast.unparse(s).replace("\n", " ") for s in node.body),
                comment=" / ".join(comments[n] for n in range(node.lineno, end + 1) if n in comments),
                shapes=_shapes(node, try_node, parents),
            ))
    return sorted(rows, key=lambda r: (r.path, r.line))


def _cell(text: str) -> str:
    return text.replace("|", "\\|")


def format_worksheet(rows: List[WorksheetRow]) -> str:
    """Markdown, one table per file; the Verdict column is left blank for the triager."""
    out = [f"# Silent broad handler triage worksheet — {len(rows)} handler(s)", "", _VERDICT_KEY]
    by_file: Dict[str, List[WorksheetRow]] = {}
    for row in rows:
        by_file.setdefault(row.path, []).append(row)
    for path, file_rows in by_file.items():
        out += ["", f"### {path} — {len(file_rows)}", "",
                "| Line | Function | Tries | Fallback | Comment | Shape | Verdict |",
                "|---:|---|---|---|---|---|---|"]
        for r in file_rows:
            cells = [str(r.line), r.function, r.attempt, r.fallback, r.comment,
                     ", ".join(r.shapes), ""]
            out.append("| " + " | ".join(_cell(c) for c in cells) + " |")
    return "\n".join(out)


# ── (a) raw exception text in user-visible sinks ────────────────────────────

def _parents(tree: ast.Module) -> Dict[ast.AST, ast.AST]:
    parents: Dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    return parents


def _arg_names(args: ast.arguments) -> Set[str]:
    return {a.arg for a in (*args.posonlyargs, *args.args, *args.kwonlyargs)} - {"self", "cls"}


def _is_error_signal_lambda(node: ast.Lambda, parents: Dict[ast.AST, ast.AST]) -> bool:
    call = parents.get(node)
    if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)):
        return False
    if call.func.attr != "connect" or not isinstance(call.func.value, ast.Attribute):
        return False
    return bool(_ERROR_SIGNAL.search(call.func.value.attr))


def _raw_names_in_scope(node: ast.AST, parents: Dict[ast.AST, ast.AST]) -> Set[str]:
    names: Set[str] = set()
    current = parents.get(node)
    while current is not None:
        if isinstance(current, ast.ExceptHandler) and current.name:
            names.add(current.name)
        elif isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)) and _ERROR_SLOT.search(current.name):
            names |= _arg_names(current.args)
        elif isinstance(current, ast.Lambda) and _is_error_signal_lambda(current, parents):
            names |= _arg_names(current.args)
        current = parents.get(current)
    return names


def _is_raw_sink_call(call: ast.Call, path: str) -> bool:
    func = call.func
    if isinstance(func, ast.Name):
        if func.id in _HEADLESS_SINK_NAMES:
            return area_of(path) == "entrypoints"
        return func.id in _RAW_SINK_NAMES
    if not isinstance(func, ast.Attribute):
        return False
    receiver = ast.unparse(func.value)
    if receiver.endswith("QMessageBox") and func.attr in _MESSAGE_BOX_METHODS:
        return True
    if "ToastManager" in receiver and func.attr == "show":
        return True
    if func.attr == "text" and _AXES_RECEIVER.search(receiver):
        return True  # matplotlib Axes.text — drawn on the chart
    if func.attr in _UI_ONLY_SINK_ATTRS:
        return area_of(path) == "ui"
    if func.attr in _HEADLESS_SINK_ATTRS:
        return area_of(path) == "entrypoints"
    return func.attr in _RAW_SINK_ATTRS or func.attr in _CHART_SINK_ATTRS


def find_raw_exception_ui_sinks(sources: Optional[Mapping[str, str]] = None) -> List[Hit]:
    hits: List[Hit] = []
    for path, tree in _trees(sources):
        parents: Optional[Dict[ast.AST, ast.AST]] = None
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and _is_raw_sink_call(node, path)):
                continue
            if parents is None:
                parents = _parents(tree)
            raw = _raw_names_in_scope(node, parents)
            if not raw:
                continue
            values = [*node.args, *(k.value for k in node.keywords)]
            if any(n.id in raw for v in values for n in _names_outside_translators(v)):
                hits.append(Hit(path, node.lineno, ast.unparse(node)[:120]))
    return sorted(hits, key=lambda h: (h.path, h.line))


#: Calls whose result never contains their arguments' text: ``worker_error_text(spec, exc)`` shows the
#: spec's wording, or ``explain()``'s for an opted-in kind (``ui/error_display.py``).
#: ``_headless_error(what, exc)`` (``svc.py``) is the same contract for the Event Log.
_TRANSLATORS = frozenset({"worker_error_text", "_headless_error"})


def _names_outside_translators(node: ast.AST) -> Iterator[ast.Name]:
    if isinstance(node, ast.Call):
        func = node.func
        name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None
        if name in _TRANSLATORS:
            return
    if isinstance(node, ast.Name):
        yield node
    for child in ast.iter_child_nodes(node):
        yield from _names_outside_translators(child)


def _except_names_in_scope(node: ast.AST, parents: Dict[ast.AST, ast.AST]) -> Set[str]:
    names: Set[str] = set()
    current = parents.get(node)
    while current is not None:
        if isinstance(current, ast.ExceptHandler) and current.name:
            names.add(current.name)
        current = parents.get(current)
    return names


def find_stringified_exception_args(sources: Optional[Mapping[str, str]] = None) -> List[Hit]:
    """An error-display helper handed ``str(exc)`` (or any expression of it) inside ``except ... as exc``.

    The helper classifies only an exception object (``modules/error_text.explain``); text of one
    silently keeps the entry's fixed why/next and drops the traceback from the log record.
    """
    hits: List[Hit] = []
    for path, tree in _trees(sources):
        parents: Optional[Dict[ast.AST, ast.AST]] = None
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None
            index = _ERROR_HELPER_RAW_ARG.get(name or "")
            if index is None or len(node.args) <= index:
                continue
            if parents is None:
                parents = _parents(tree)
            caught = _except_names_in_scope(node, parents)
            raw = node.args[index]
            if isinstance(raw, ast.Name) or not caught:
                continue
            if any(isinstance(n, ast.Name) and n.id in caught for n in ast.walk(raw)):
                hits.append(Hit(path, node.lineno, ast.unparse(node)[:120]))
    return sorted(hits, key=lambda h: (h.path, h.line))


# ── (c) toast kinds ─────────────────────────────────────────────────────────

def valid_toast_kinds(toast_source: Optional[str] = None) -> FrozenSet[str]:
    """Keys of ``_AUTO_DISMISS_MS`` in ui/widgets/toast.py -- derived, never duplicated."""
    if toast_source is None:
        toast_source = (REPO_ROOT / "ui" / "widgets" / "toast.py").read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(toast_source)):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict) and any(
            isinstance(t, ast.Name) and t.id == "_AUTO_DISMISS_MS" for t in node.targets
        ):
            return frozenset(
                k.value for k in node.value.keys
                if isinstance(k, ast.Constant) and isinstance(k.value, str)
            )
    # Fail closed: an empty set would flag every call, a missing check would flag none.
    raise RuntimeError("_AUTO_DISMISS_MS not found in ui/widgets/toast.py -- update valid_toast_kinds()")


def find_invalid_toast_kinds(
    sources: Optional[Mapping[str, str]] = None, valid: Optional[FrozenSet[str]] = None,
) -> List[Hit]:
    kinds = valid_toast_kinds() if valid is None else valid
    hits: List[Hit] = []
    for path, tree in _trees(sources):
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            if node.func.attr != "show" or "ToastManager" not in ast.unparse(node.func.value):
                continue
            kind: Optional[ast.AST] = node.args[1] if len(node.args) > 1 else next(
                (k.value for k in node.keywords if k.arg == "kind"), None
            )
            if isinstance(kind, ast.Constant) and isinstance(kind.value, str) and kind.value not in kinds:
                hits.append(Hit(path, node.lineno, kind.value))
    return sorted(hits, key=lambda h: (h.path, h.line))


# ── (d) scan-registry error paths ───────────────────────────────────────────

def load_nav_labels(labels_source: Optional[str] = None) -> Dict[str, str]:
    """NavLabel member name -> label string, read from ui/nav/labels.py by AST."""
    if labels_source is None:
        labels_source = (REPO_ROOT / "ui" / "nav" / "labels.py").read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(labels_source)):
        if isinstance(node, ast.ClassDef) and node.name == "NavLabel":
            return {
                stmt.targets[0].id: stmt.value.value
                for stmt in node.body
                if isinstance(stmt, ast.Assign)
                and isinstance(stmt.targets[0], ast.Name)
                and isinstance(stmt.value, ast.Constant)
                and isinstance(stmt.value.value, str)
            }
    raise RuntimeError("class NavLabel not found in ui/nav/labels.py -- update load_nav_labels()")


def _call_arg(call: ast.Call, index: int, keyword: str) -> Optional[ast.AST]:
    if len(call.args) > index:
        return call.args[index]
    return next((k.value for k in call.keywords if k.arg == keyword), None)


def _resolve_label(node: Optional[ast.AST], nav: Mapping[str, str]) -> Optional[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.attr in nav:
        return nav[node.attr]
    return None  # a variable -- cannot be resolved statically


def scan_state_coverage(
    sources: Optional[Mapping[str, str]] = None, nav_labels: Optional[Mapping[str, str]] = None,
) -> Dict[str, Set[str]]:
    nav = load_nav_labels() if nav_labels is None else nav_labels
    coverage: Dict[str, Set[str]] = {}
    for _path, tree in _trees(sources):
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            if node.func.attr != "_nav_set_scan_state":
                continue
            state = _call_arg(node, 1, "state")
            label = _resolve_label(_call_arg(node, 0, "label"), nav)
            if label is None or not (isinstance(state, ast.Constant) and isinstance(state.value, str)):
                continue
            coverage.setdefault(label, set()).add(state.value)
    return coverage


def find_scan_labels_without_error_path(
    sources: Optional[Mapping[str, str]] = None, nav_labels: Optional[Mapping[str, str]] = None,
) -> List[str]:
    return sorted(
        label for label, states in scan_state_coverage(sources, nav_labels).items()
        if states & _PROGRESS_STATES and not states & _ERROR_STATES
    )


# ── CLI ──────────────────────────────────────────────────────────────────────

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--worksheet", nargs="*", metavar="PATH",
        help="print a Markdown triage worksheet of silent broad handlers (b) instead of the "
             "census, limited to the given files or directories",
    )
    args = parser.parse_args(argv)

    # Findings quote real source lines, which contain non-cp1252 characters (the
    # "warning" toasts carry a literal U+26A0). A Windows console defaults to
    # cp1252 and would raise UnicodeEncodeError mid-report.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass  # already UTF-8, or a stream without reconfigure (pytest capture)

    if args.worksheet is not None:
        print(format_worksheet(build_worksheet(paths=args.worksheet)))
        return 0

    print("Broad/narrow except handlers by area:")
    for area, counter in sorted(census_by_area().items()):
        broad = {c: counter[f"broad:{c}"] for c in CATEGORIES}
        narrow = sum(v for k, v in counter.items() if k.startswith("narrow:"))
        print(f"  {area:12} broad={broad} narrow={narrow}")

    silent = find_silent_broad_handlers()
    print(f"\n(b) silent broad handlers: {len(silent)} {count_by_area(silent)}")
    for path, n in Counter(h.path for h in silent).most_common(25):
        print(f"  {n:4}  {path}")

    raw = find_raw_exception_ui_sinks()
    print(f"\n(a) raw exception text in user-visible sinks: {len(raw)}")
    for h in raw:
        print(f"  {h.path}:{h.line}  {h.detail}")

    toasts = find_invalid_toast_kinds()
    print(f"\n(c) invalid toast kinds (valid: {sorted(valid_toast_kinds())}): {len(toasts)}")
    for h in toasts:
        print(f"  {h.path}:{h.line}  kind={h.detail!r}")

    labels = find_scan_labels_without_error_path()
    print(f"\n(d) scan labels set running/fresh with no error/not_testable path: {len(labels)}")
    coverage = scan_state_coverage()
    for label in labels:
        print(f"  {label}: {sorted(coverage[label])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
