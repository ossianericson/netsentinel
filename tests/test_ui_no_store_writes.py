"""Architectural invariant (ARCH RULE 1, item #21): the UI layer never writes to
MetricStore directly.

The UI reads MetricStore for display but must route every WRITE through a
module-layer boundary (modules/scan_persistence.py, device_admin.py, cve_admin.py,
network_segments.py). Direct writes from ui/ are how the device_ip_history
double-count bug (scan_wiring calling record_ip_observation twice) happened — the
mediation layer is where the single-writer invariants live.

Mechanism of this guard:
  * Derive the MetricStore WRITE-method name set at test time from the
    modules/metric_store*.py family (every def whose name starts with a mutating
    verb: record_/save_/insert_/upsert_/update_/set_/delete_/clear_/store_/prune_/mark_).
  * AST-walk ui/**/*.py and fail on any ATTRIBUTE call `something.<write>(...)`
    whose method name is in that set (e.g. `self._store.record_rtt(...)`).

Why attribute-only: the mediated path calls the helpers as bare functions
(`from modules.scan_persistence import record_rtt; record_rtt(store, ...)`), which
are ast.Name calls — not attribute access — so they never trip this guard. Reads
use get_/query_ names, which aren't in the set. Comments can't parse as a Call
node, so the app_traffic_page.py doc-comment is not a false positive.

Zero tolerance: no baseline. This item is being closed fully.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI_ROOT = ROOT / "ui"
MODULES_ROOT = ROOT / "modules"

_WRITE_PREFIXES = (
    "record_", "save_", "insert_", "upsert_", "update_",
    "set_", "delete_", "clear_", "store_", "prune_", "mark_",
)


def _metric_store_write_methods() -> set[str]:
    names: set[str] = set()
    for path in MODULES_ROOT.glob("metric_store*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, SyntaxError, OSError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith(_WRITE_PREFIXES):
                    names.add(node.name)
    return names


def _offending_calls(tree: ast.AST, write_methods: set[str]):
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in write_methods:
                hits.append((node.func.attr, node.lineno))
    return hits


def test_ui_never_writes_metric_store_directly():
    write_methods = _metric_store_write_methods()
    # Sanity: the derivation actually found the write surface.
    assert "record_rtt" in write_methods and "upsert_known_device" in write_methods, (
        "write-method derivation failed — check modules/metric_store*.py naming"
    )

    offenders = []
    for path in UI_ROOT.rglob("*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, SyntaxError, OSError):
            continue
        for method, lineno in _offending_calls(tree, write_methods):
            offenders.append(f"{path.relative_to(ROOT)}:{lineno} -> .{method}()")

    assert not offenders, (
        "ui/ writes to MetricStore directly (ARCH RULE 1 layer violation, #21).\n"
        "Route the write through a module-layer helper (imported as a bare function):\n"
        "  device/HA/classification -> modules/device_admin.py\n"
        "  CVE lifecycle            -> modules/cve_admin.py\n"
        "  segments                 -> modules/network_segments.py\n"
        "  scan-result persistence  -> modules/scan_persistence.py\n"
        + "\n".join(f"  {o}" for o in sorted(offenders))
    )
