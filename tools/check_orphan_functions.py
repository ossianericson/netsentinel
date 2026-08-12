"""Find production functions/methods that only tests reference (RULE-DBG5 sweep).

The v2.2.4 passive-observation fix shipped completely inert: it preferred a MAC
over an IP, the MAC came from `passive_observer.enrich_mac()`, and that helper
had **zero callers outside its test file**. 100% of traffic took the fallback --
the very bug the fix was written to close -- with no exception, no log line and
a green test suite, because the regression test hand-supplied the MAC that
production never produced.

This scanner generalises that check: a definition that exists in `modules/`,
`ui/` or `workers/`, is exercised by tests, and is referenced by no other
production code is either dead wiring (dangerous) or unused clutter (harmless).
It cannot tell those apart -- a human must -- so findings are baselined once
triaged and the ratchet only forbids NEW ones.

Detection is name-based rather than call-graph based, deliberately: it catches
`self.foo()`, `obj.foo()`, `mod.foo()` and bare `foo()` alike without needing
type inference. The cost is that a name defined in more than one place is
ambiguous, so those are skipped (conservative -- misses, never false-alarms).

Known blind spot, shared with CodeQL and `tools/check_import_lint.py`: a
reference made only through a string literal (`getattr(obj, "foo")`,
`monkeypatch.setattr("mod.foo", ...)`) is invisible here. Grep for the literal
name before concluding a hit is real.
"""
from __future__ import annotations

import ast
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
PROD_DIRS = ("modules", "ui", "workers")
# Wired from these, so they count as production references, not definitions.
PROD_ENTRYPOINTS = ("app.py", "cli.py", "svc.py")
TEST_DIR = "tests"

# Called by a framework, never by name from our own code. Not orphans.
FRAMEWORK_CALLBACKS: Set[str] = {
    # QWidget/QObject event handlers
    "showEvent", "hideEvent", "closeEvent", "paintEvent", "resizeEvent",
    "moveEvent", "changeEvent", "enterEvent", "leaveEvent", "focusInEvent",
    "focusOutEvent", "keyPressEvent", "keyReleaseEvent", "mousePressEvent",
    "mouseReleaseEvent", "mouseMoveEvent", "mouseDoubleClickEvent",
    "wheelEvent", "contextMenuEvent", "dragEnterEvent", "dragMoveEvent",
    "dragLeaveEvent", "dropEvent", "eventFilter", "event", "nativeEvent",
    "timerEvent", "actionEvent", "inputMethodEvent",
    # QWidget/model overrides Qt calls internally
    "sizeHint", "minimumSizeHint", "heightForWidth", "hasHeightForWidth",
    "paint", "data", "rowCount", "columnCount", "headerData", "flags",
    "setData", "index", "parent", "run", "start", "stop",
    # QThread / QRunnable
    "quit", "exec",
    # dunder-adjacent protocol methods
    "setUp", "tearDown",
}

# ast.NodeVisitor dispatches `visit_<NodeType>` by name construction, so these
# are called by the framework and never appear as a literal reference.
FRAMEWORK_CALLBACK_PREFIXES: Tuple[str, ...] = ("visit_", "generic_visit")


def _iter_py(rel_dir: str):
    root = REPO_ROOT / rel_dir
    if not root.exists():
        return
    yield from sorted(root.rglob("*.py"))


def _collect_definitions() -> Dict[str, List[Tuple[str, int]]]:
    """name -> [(relpath, lineno), ...] for every def in the production tree."""
    defs: Dict[str, List[Tuple[str, int]]] = {}
    for d in PROD_DIRS:
        for path in _iter_py(d):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            rel = path.relative_to(REPO_ROOT).as_posix()
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                name = node.name
                if name.startswith("__") and name.endswith("__"):
                    continue
                if name in FRAMEWORK_CALLBACKS:
                    continue
                if name.startswith(FRAMEWORK_CALLBACK_PREFIXES):
                    continue
                defs.setdefault(name, []).append((rel, node.lineno))
    return defs


def _read_sources(rel_dirs, extra_files=()) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    for d in rel_dirs:
        for path in _iter_py(d):
            try:
                out.append((path.relative_to(REPO_ROOT).as_posix(),
                            path.read_text(encoding="utf-8")))
            except UnicodeDecodeError:
                continue
    for fname in extra_files:
        p = REPO_ROOT / fname
        if p.exists():
            out.append((fname, p.read_text(encoding="utf-8")))
    return out


_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _identifier_counts(sources: List[Tuple[str, str]]) -> Dict[str, Counter]:
    """relpath -> Counter of every identifier token in that file.

    Tokenising each file ONCE and counting lookups is what keeps this usable:
    the naive "regex each name against each file" shape is O(names x files)
    full scans -- ~1,900 names against ~400 files here -- and takes minutes.
    """
    return {rel: Counter(_IDENT_RE.findall(text)) for rel, text in sources}


def find_test_only_definitions() -> List[Tuple[str, str, int, int]]:
    """Return (name, relpath, lineno, test_refs), sorted by test_refs desc.

    A hit means: defined exactly once in production, referenced nowhere in
    production outside its own definition line, and referenced at least once
    from tests/.
    """
    defs = _collect_definitions()
    prod_counts = _identifier_counts(_read_sources(PROD_DIRS, PROD_ENTRYPOINTS))
    test_counts = _identifier_counts(_read_sources((TEST_DIR,)))

    prod_total: Counter = Counter()
    for counts in prod_counts.values():
        prod_total.update(counts)
    test_total: Counter = Counter()
    for counts in test_counts.values():
        test_total.update(counts)

    hits: List[Tuple[str, str, int, int]] = []
    for name, locations in defs.items():
        if len(locations) != 1:
            continue  # ambiguous name — conservative skip
        def_file, def_line = locations[0]

        # Discount the definition's own `def <name>` token.
        prod_refs = prod_total.get(name, 0) - 1
        if prod_refs > 0:
            continue

        test_refs = test_total.get(name, 0)
        if test_refs > 0:
            hits.append((name, def_file, def_line, test_refs))

    hits.sort(key=lambda h: (-h[3], h[1], h[0]))
    return hits


def main() -> int:
    hits = find_test_only_definitions()
    print(f"Production definitions referenced only by tests: {len(hits)}")
    for name, rel, line, refs in hits:
        print(f"  {name:44s} {rel}:{line}  test-refs={refs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
