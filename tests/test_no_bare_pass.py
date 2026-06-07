"""
RULE-LINT2 enforcement: every bare `pass` in an except block must have an inline comment.
CodeQL rule: py/empty-except
"""
import ast
from pathlib import Path

_ROOT = Path(__file__).parent.parent
_EXCLUDE_DIRS = {"build", "__pycache__", ".git", ".mypy_cache", "dist"}


def _iter_py_files():
    for path in sorted(_ROOT.rglob("*.py")):
        # Exclude any virtualenv directory (named .venv, .venv311, venv, etc.)
        parts_set = set(path.parts)
        if any(p in _EXCLUDE_DIRS for p in parts_set):
            continue
        if any(p.startswith(".venv") or p == "venv" or p.startswith("venv") for p in parts_set):
            continue
        yield path


def test_no_uncommented_bare_pass_in_except():
    """Every bare 'pass' in an except block must have a comment explaining why."""
    offenders = []
    for path in _iter_py_files():
        try:
            src = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines = src.splitlines()
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                body = node.body
                if len(body) == 1 and isinstance(body[0], ast.Pass):
                    pass_lineno = body[0].lineno
                    line_text = lines[pass_lineno - 1] if pass_lineno <= len(lines) else ""
                    if "#" not in line_text:
                        rel = path.relative_to(_ROOT)
                        offenders.append(f"{rel}:{pass_lineno}")
    assert not offenders, (
        "Bare 'pass' in except block without explanatory comment "
        "(add  pass  # reason  to satisfy RULE-LINT2):\n"
        + "\n".join(offenders[:30])
    )
