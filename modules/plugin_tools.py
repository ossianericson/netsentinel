"""
NetSentinel Plugin Validator CLI — P3-1 (validator) + P4-3 (import advisory)

Usage:
    python -m modules.plugin_tools validate path/to/plugin.py
    python -m modules.plugin_tools validate path/to/plugin.py --live

Checks:
  [error]   Valid Python syntax
  [error]   Required constants: HARDWARE_NAME, HARDWARE_TYPE
  [error]   Required functions: get_info(), get_status()
  [error]   get_info / get_status take no required positional args
  [warning] PYPI_PACKAGE declared when external imports detected
  [warning] No HARDWARE_IP constant
  [warning] Top-level network calls at module scope
  [info]    CREDENTIAL_LABEL recommended
  [info]    Imports outside default safe list (P4-3 advisory)
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

# P4-3: Safe import baseline — plugin may override with SAFE_IMPORTS = [...]
_DEFAULT_SAFE_IMPORTS: set[str] = {
    "json", "sys", "os", "re", "time", "datetime", "pathlib", "hashlib",
    "socket", "ssl", "typing", "collections", "itertools", "functools",
    "requests", "keyring", "urllib", "http", "logging", "traceback",
    "abc", "copy", "enum", "struct", "math", "base64", "binascii",
    "xml", "html", "string", "io", "contextlib", "threading", "queue",
}

# Top-level calls that suggest network I/O at import time (advisory only)
_NETWORK_CALL_NAMES: frozenset[str] = frozenset({
    "socket", "connect", "urllib", "requests", "httpx", "aiohttp",
})

# Standard-library-ish set used when deciding whether to warn about PYPI_PACKAGE
_STDLIB_NAMES: frozenset[str] = frozenset({
    "json", "sys", "os", "re", "time", "datetime", "pathlib", "hashlib",
    "socket", "ssl", "typing", "collections", "itertools", "functools",
    "logging", "traceback", "abc", "copy", "enum", "struct", "math",
    "base64", "binascii", "io", "contextlib", "threading", "queue",
    "xml", "html", "string", "urllib", "http", "modules", "keyring",
})


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class ValidationIssue:
    level:   str    # "error" | "warning" | "info"
    message: str


@dataclass
class ValidationResult:
    path:   str
    ok:     bool
    meta:   dict                         = field(default_factory=dict)
    issues: List[ValidationIssue]        = field(default_factory=list)

    @property
    def errors(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.level == "warning"]

    def pretty(self) -> str:
        marker_map = {"error": "✗", "warning": "⚠", "info": "·"}
        lines = [f"{'✓' if self.ok else '✗'}  {self.path}"]
        for issue in self.issues:
            m = marker_map.get(issue.level, "·")
            lines.append(f"  {m}  [{issue.level.upper()}] {issue.message}")
        if self.ok and not self.issues:
            lines.append("  ·  All checks passed.")
        return "\n".join(lines)


def _issue(level: str, msg: str) -> ValidationIssue:
    return ValidationIssue(level=level, message=msg)


# ── Core validator ────────────────────────────────────────────────────────────

def validate_plugin(path: str, *, live: bool = False) -> ValidationResult:
    """Validate a hardware plugin file.

    Args:
        path: Absolute or relative path to the .py plugin file.
        live: If True, attempt to import and call get_info() after static checks.

    Returns:
        ValidationResult.  .ok is True only when there are no error-level issues.
    """
    issues: List[ValidationIssue] = []
    meta:   dict = {}

    # ── File exists ───────────────────────────────────────────────────────────
    p = Path(path)
    if not p.exists():
        return ValidationResult(
            path=path, ok=False,
            issues=[_issue("error", f"File not found: {path}")],
        )

    # ── Syntax ────────────────────────────────────────────────────────────────
    try:
        source = p.read_text(encoding="utf-8", errors="replace")
        tree   = ast.parse(source, filename=path)
    except SyntaxError as exc:
        return ValidationResult(
            path=path, ok=False,
            issues=[_issue("error", f"Syntax error at line {exc.lineno}: {exc.msg}")],
        )
    except Exception as exc:
        return ValidationResult(
            path=path, ok=False,
            issues=[_issue("error", f"Cannot parse file: {exc}")],
        )

    # ── AST walk ──────────────────────────────────────────────────────────────
    top_assigns:    dict[str, object] = {}
    func_defs:      set[str]          = set()
    import_names:   set[str]          = set()
    top_level_call  = False

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    if isinstance(node.value, ast.Constant):
                        top_assigns[target.id] = node.value.value
                    elif isinstance(node.value, ast.List):
                        elts = [
                            e.value for e in node.value.elts
                            if isinstance(e, ast.Constant)
                            and isinstance(e.value, str)
                        ]
                        top_assigns[target.id] = elts
                    elif isinstance(node.value, ast.Dict):
                        # Shallow-parse dict literals (used for CONFIG_SCHEMA)
                        d: dict = {}
                        for k, v in zip(node.value.keys, node.value.values):
                            if isinstance(k, ast.Constant) and isinstance(v, ast.Constant):
                                d[k.value] = v.value
                            elif isinstance(k, ast.Constant) and isinstance(v, ast.Dict):
                                inner: dict = {}
                                for ik, iv in zip(v.keys, v.values):
                                    if isinstance(ik, ast.Constant) and isinstance(iv, ast.Constant):
                                        inner[ik.value] = iv.value
                                d[k.value] = inner
                        top_assigns[target.id] = d
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_defs.add(node.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                import_names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                import_names.add(node.module.split(".")[0])
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call_str = (
                ast.unparse(node.value) if hasattr(ast, "unparse") else ""
            )
            if any(n in call_str for n in _NETWORK_CALL_NAMES):
                top_level_call = True

    # ── Required constants ────────────────────────────────────────────────────
    for name in ("HARDWARE_NAME", "HARDWARE_TYPE"):
        if name not in top_assigns:
            issues.append(_issue("error", f"Missing required constant: {name}"))

    # ── Required functions ────────────────────────────────────────────────────
    for fn in ("get_info", "get_status"):
        if fn not in func_defs:
            issues.append(_issue("error", f"Missing required function: {fn}()"))

    # ── Function signatures — no required positional args ─────────────────────
    for node in ast.iter_child_nodes(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in ("get_info", "get_status")
        ):
            n_required = len(node.args.args) - len(node.args.defaults)
            if n_required > 0:
                issues.append(_issue(
                    "error",
                    f"{node.name}() must take no required positional arguments "
                    f"(found {n_required}).  Use **kwargs for optional config.",
                ))

    # ── PYPI_PACKAGE advisory ─────────────────────────────────────────────────
    if "PYPI_PACKAGE" not in top_assigns:
        external = import_names - _STDLIB_NAMES
        if external:
            issues.append(_issue(
                "warning",
                f"No PYPI_PACKAGE declared, but external imports detected: "
                f"{', '.join(sorted(external))}.  "
                "Add PYPI_PACKAGE = \"<pkg>\" so users can auto-install deps.",
            ))

    # ── HARDWARE_IP advisory ──────────────────────────────────────────────────
    if "HARDWARE_IP" not in top_assigns:
        issues.append(_issue(
            "warning",
            "No HARDWARE_IP constant.  Add HARDWARE_IP = \"192.168.1.1\" so the "
            "app can pre-fill the credential dialog.",
        ))

    # ── Top-level network call advisory ───────────────────────────────────────
    if top_level_call:
        issues.append(_issue(
            "warning",
            "Possible network call at module top level.  "
            "Network calls must be inside functions — top-level calls block "
            "plugin loading when the device is offline.",
        ))

    # ── CREDENTIAL_LABEL info ─────────────────────────────────────────────────
    if "CREDENTIAL_LABEL" not in top_assigns:
        issues.append(_issue(
            "info",
            "No CREDENTIAL_LABEL constant; the app defaults to 'Password'.  "
            "Add CREDENTIAL_LABEL = \"Password\" (or 'PIN', 'Token') to be explicit.",
        ))

    # ── P4-3: Restricted import advisory ─────────────────────────────────────
    safe_raw = top_assigns.get("SAFE_IMPORTS")
    allowed_prefixes: set[str]
    if isinstance(safe_raw, list):
        allowed_prefixes = {s.rstrip(".*") for s in safe_raw}
    else:
        allowed_prefixes = {s.rstrip(".*") for s in _DEFAULT_SAFE_IMPORTS}

    suspicious = {
        name for name in import_names
        if not any(
            name == pfx or name.startswith(pfx + ".")
            for pfx in allowed_prefixes
        )
    }
    if suspicious:
        issues.append(_issue(
            "info",
            f"Imports outside safe list: {', '.join(sorted(suspicious))}.  "
            "Add SAFE_IMPORTS = [...] to acknowledge these imports.",
        ))

    # ── Build meta dict ───────────────────────────────────────────────────────
    raw_schema = top_assigns.get("CONFIG_SCHEMA")
    meta = {
        "name":             str(top_assigns.get("HARDWARE_NAME", p.stem)),
        "type":             str(top_assigns.get("HARDWARE_TYPE", "unknown")),
        "ip":               str(top_assigns.get("HARDWARE_IP", "")),
        "description":      str(top_assigns.get("DESCRIPTION", "")),
        "credential_label": str(top_assigns.get("CREDENTIAL_LABEL", "Password")),
        "pypi_package":     str(top_assigns.get("PYPI_PACKAGE", "")),
        "author":           str(top_assigns.get("AUTHOR", "")),
        "config_schema":    raw_schema if isinstance(raw_schema, dict) else {},
    }
    try:
        meta["sha256"] = hashlib.sha256(p.read_bytes()).hexdigest()
    except Exception:
        meta["sha256"] = ""

    # ── Live test (optional) ──────────────────────────────────────────────────
    if live and not any(i.level == "error" for i in issues):
        pypi_pkg = meta.get("pypi_package", "")
        if pypi_pkg:
            mname = pypi_pkg.replace("-", "_")
            if importlib.util.find_spec(mname) is None:
                issues.append(_issue(
                    "error",
                    f"PYPI_PACKAGE '{pypi_pkg}' not installed.  "
                    f"Run: pip install {pypi_pkg}",
                ))
        else:
            try:
                spec = importlib.util.spec_from_file_location(
                    f"_ns_validate_{p.stem}", str(p)
                )
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)  # type: ignore[union-attr]
                    get_info = getattr(mod, "get_info", None)
                    if callable(get_info):
                        info_result = get_info()
                        issues.append(_issue(
                            "info",
                            f"get_info() returned keys: {list(info_result.keys())}",
                        ))
            except Exception as exc:
                issues.append(_issue("warning", f"Live import error: {exc}"))

    ok = not any(i.level == "error" for i in issues)
    return ValidationResult(path=path, ok=ok, meta=meta, issues=issues)


# ── Signature verification (P4-2) ─────────────────────────────────────────────

def _load_hash_db() -> dict[str, str]:
    """Load data/plugin_hashes.json, returning {} if absent."""
    try:
        import json
        hash_file = Path(__file__).parent.parent / "data" / "plugin_hashes.json"
        if hash_file.exists():
            return json.loads(hash_file.read_text(encoding="utf-8"))
    except Exception:
        pass  # hash file absent or corrupted — treat all plugins as unsigned
    return {}


def _file_hash(path: "str | Path") -> str:
    """SHA-256 of a file's content normalised to LF line endings.

    Normalising before hashing makes the digest identical on Windows (CRLF),
    Linux, and macOS (LF) after git checkout, regardless of the host platform
    or .gitattributes autocrlf settings.
    """
    raw = Path(path).read_bytes()
    normalised = raw.replace(b"\r\n", b"\n")
    return hashlib.sha256(normalised).hexdigest()


def verify_signature(path: str) -> tuple[bool, str]:
    """Check a plugin file against data/plugin_hashes.json.

    Returns (is_verified, status_message):
      (True,  "Verified")                         — hash matches
      (False, "Not in hash list")                 — user-added plugin (not signed)
      (False, "HASH MISMATCH — possible tampering") — signed but hash differs
    """
    db = _load_hash_db()
    recorded = db.get(Path(path).name)
    if recorded is None:
        return False, "Not in hash list"
    try:
        actual = _file_hash(path)
    except Exception:
        return False, "Cannot read file"
    if actual == recorded:
        return True, "Verified"
    return False, "HASH MISMATCH — possible tampering"


# ── CLI entry point ────────────────────────────────────────────────────────────

def _cli_validate(args: list[str]) -> int:
    if not args:
        print("Usage: python -m modules.plugin_tools validate <plugin.py> [--live]")
        return 1

    live  = "--live" in args
    paths = [a for a in args if not a.startswith("--")]

    all_ok = True
    for path in paths:
        result = validate_plugin(path, live=live)
        print(result.pretty())

        signed, sig_msg = verify_signature(path)
        if signed:
            print(f"  ✓  Signature: {sig_msg}")
        elif "MISMATCH" in sig_msg:
            print(f"  ✗  Signature: {sig_msg}")
        else:
            print(f"  ·  Signature: {sig_msg}")
        print()
        if not result.ok:
            all_ok = False

    return 0 if all_ok else 1


if __name__ == "__main__":
    argv = sys.argv[1:]
    if not argv or argv[0] not in ("validate",):
        print("NetSentinel Plugin Tools")
        print("Commands:")
        print("  validate <plugin.py> [--live]   Static-analyse a plugin file")
        sys.exit(0)

    cmd, *rest = argv
    if cmd == "validate":
        sys.exit(_cli_validate(rest))
