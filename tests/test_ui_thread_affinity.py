"""RULE-WIN27 — a plain ``threading`` target in ``ui/`` may touch Qt only by emitting a signal.

An AST pointer, not a proof. For every ``threading.Thread(target=...)`` / ``threading.Timer(n, fn)``
in ``ui/``, the target — a lambda, a function nested in the same function, or a method of the same
class — is walked *including the lambdas it hands on* (``progress_cb=lambda m: ...``), because a
callback given to a ``modules/`` function runs on the thread that calls it. Methods of the same
class that the target calls are followed one level.

A violation is a widget-mutating call on something reached through ``self`` (``self._lbl.setText``,
``self.show()``), or a call to a ``self`` method whose name says it writes widgets
(``_populate_*``, ``_set_status``, ``_render*``). Known blind spots (the guard under-counts, never
over-counts): a widget reached through a local alias (``lbl = self._lbl``), a helper defined in a
different class or file, and a target that is not resolvable by name.
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent

# Unambiguous Qt widget/item mutators. ``append``/``update``/``clear`` are left out on purpose: a
# list or dict owned by ``self`` has the same method names and is safe to touch from a thread.
_WIDGET_MUTATORS = frozenset({
    "setText", "setPlainText", "setHtml", "appendPlainText", "appendHtml", "insertPlainText",
    "setItem", "setCellWidget", "insertRow", "removeRow", "setRowCount", "setColumnCount",
    "clearContents", "addItem", "addItems", "insertItem", "takeItem", "setCurrentIndex",
    "setCurrentWidget", "setValue", "setRange", "setVisible", "show", "hide", "setEnabled",
    "setToolTip", "setStyleSheet", "setPixmap", "scrollToBottom", "repaint", "adjustSize",
    "setChecked", "setTitle", "setWindowTitle", "setForeground", "setBackground", "draw_idle",
})
_WIDGET_METHOD_PREFIXES = ("_populate_", "_set_status", "_render")


def _rooted_at_self(node: ast.AST) -> bool:
    while isinstance(node, ast.Attribute):
        node = node.value
    return isinstance(node, ast.Name) and node.id == "self"


def _thread_target(call: ast.Call) -> Optional[ast.AST]:
    """The callable a ``threading.Thread``/``Timer`` call will run, or None."""
    func = call.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
    if name == "Thread":
        for kw in call.keywords:
            if kw.arg == "target":
                return kw.value
        return call.args[1] if len(call.args) > 1 else None
    if name == "Timer":
        for kw in call.keywords:
            if kw.arg == "function":
                return kw.value
        return call.args[1] if len(call.args) > 1 else None
    return None


def _violations_in(body: ast.AST, methods: Dict[str, ast.FunctionDef], depth: int = 0) -> Iterator[Tuple[int, str]]:
    for node in ast.walk(body):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        attr = node.func.attr
        receiver = node.func.value
        if attr in _WIDGET_MUTATORS and _rooted_at_self(receiver):
            yield node.lineno, f"{ast.unparse(node.func)}()"
        elif isinstance(receiver, ast.Name) and receiver.id == "self":
            if attr.startswith(_WIDGET_METHOD_PREFIXES):
                yield node.lineno, f"self.{attr}()"
            elif depth == 0 and attr in methods:
                for _, what in _violations_in(methods[attr], methods, depth + 1):
                    yield node.lineno, f"self.{attr}() -> {what}"


def _resolve(target: ast.AST, enclosing: ast.AST, methods: Dict[str, ast.FunctionDef]) -> Optional[ast.AST]:
    if isinstance(target, ast.Lambda):
        return target
    if isinstance(target, ast.Name):
        for node in ast.walk(enclosing):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == target.id:
                return node
        return None
    if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self":
        return methods.get(target.attr)
    return None


def find_thread_affinity_violations(source: str, path: str = "<src>") -> List[str]:
    tree = ast.parse(source)
    found: List[str] = []

    def _scan(scope: ast.AST, methods: Dict[str, ast.FunctionDef]) -> None:
        for node in ast.iter_child_nodes(scope):
            if isinstance(node, ast.ClassDef):
                _scan(node, {n.name: n for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))})
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for call in ast.walk(node):
                    if not isinstance(call, ast.Call):
                        continue
                    target = _thread_target(call)
                    body = _resolve(target, node, methods) if target is not None else None
                    if body is None:
                        continue
                    for lineno, what in _violations_in(body, methods):
                        found.append(f"{path}:{lineno}: {what} runs on the thread started at line {call.lineno}")
            else:
                _scan(node, methods)

    _scan(tree, {})
    return sorted(set(found))


def _ui_files() -> List[Path]:
    return sorted((REPO_ROOT / "ui").rglob("*.py"))


# ── The guard on the real tree ────────────────────────────────────────────────

def test_no_ui_thread_target_touches_a_widget():
    violations: List[str] = []
    for path in _ui_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        violations += find_thread_affinity_violations(path.read_text(encoding="utf-8"), rel)
    assert not violations, (
        "RULE-WIN27: a threading target in ui/ writes a widget. Emit a signal from the thread and "
        "do the write in a GUI-thread slot; a callback passed to a modules/ function runs on the "
        "thread that calls it.\n  " + "\n  ".join(violations)
    )


# ── The guard itself (the shapes it must and must not flag) ──────────────────

_WRONG = '''
import threading
class P:
    def _populate_table(self, rows):
        self._table.setRowCount(0)
    def _go(self):
        def _do():
            rows = learn(progress_cb=lambda m: self._status.setText(m))
            self._populate_table(rows)
        threading.Thread(target=_do, daemon=True).start()
'''

_RIGHT = '''
import threading
class P:
    def _announce(self, v):
        self._ready.emit(v)
    def _go(self):
        def _do():
            rows = learn(progress_cb=lambda m: self._progress.emit(1, m))
            self._results.append(rows)
            self._announce(rows)
        threading.Thread(target=_do, daemon=True).start()
        threading.Timer(5.0, lambda: self._done.emit("")).start()
'''


def test_guard_flags_a_lambda_callback_and_a_populate_call():
    found = find_thread_affinity_violations(_WRONG)
    assert any("self._status.setText()" in v for v in found), found
    assert any("self._populate_table()" in v for v in found), found


def test_guard_follows_a_same_class_method_one_level():
    src = '''
import threading
class P:
    def _paint(self):
        self._label.setText("x")
    def _go(self):
        threading.Thread(target=self._paint).start()
    def _go2(self):
        def _do():
            self._paint()
        threading.Thread(target=_do).start()
'''
    found = find_thread_affinity_violations(src)
    assert len(found) == 2, found


def test_guard_accepts_signal_emission_and_plain_containers():
    assert find_thread_affinity_violations(_RIGHT) == []


def test_guard_flags_a_timer_lambda_that_writes_a_widget():
    src = '''
import threading
class P:
    def _go(self):
        threading.Timer(5.0, lambda: self._lbl.setText("")).start()
'''
    assert len(find_thread_affinity_violations(src)) == 1
