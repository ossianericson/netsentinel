"""
RULE-LINT3 enforcement: no class may define the same method name twice.
CodeQL rule: py/multiple-definition
"""
import ast
from pathlib import Path

_ROOT = Path(__file__).parent.parent
_SCAN_DIRS = [_ROOT / "ui", _ROOT / "modules", _ROOT / "workers"]
_EXCLUDE_DIRS = {".venv", "build", "__pycache__", ".git", "dist"}


def _iter_py_files():
    for base in _SCAN_DIRS:
        for path in sorted(base.rglob("*.py")):
            if any(p in _EXCLUDE_DIRS for p in path.parts):
                continue
            yield path


def test_no_duplicate_method_names_in_class():
    """No class body may define the same method name more than once."""
    offenders = []
    for path in _iter_py_files():
        try:
            src = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                seen: set[str] = set()
                dups: set[str] = set()
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if item.name in seen:
                            dups.add(item.name)
                        seen.add(item.name)
                if dups:
                    rel = path.relative_to(_ROOT)
                    offenders.append(
                        f"{rel}: class {node.name} — duplicate methods: {sorted(dups)}"
                    )
    assert not offenders, (
        "Duplicate method definitions in class (RULE-LINT3 — remove the redundant copy):\n"
        + "\n".join(offenders)
    )
