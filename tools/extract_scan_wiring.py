"""
extract_scan_wiring.py — Sprint 4 S1-2 helper script.

Extracts all _on_*_result methods from Dashboard in ui/dashboard.py
into a ScanResultMixin class in ui/scan_wiring.py, then removes them
from dashboard.py and adds the mixin to Dashboard's base classes.

Run from the repo root:
    python tools/extract_scan_wiring.py
"""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
DASHBOARD_PY = ROOT / "ui" / "dashboard.py"
SCAN_WIRING_PY = ROOT / "ui" / "scan_wiring.py"

# The methods to extract (must be exact names)
TARGET_METHODS = {
    "_on_port_scan_result",
    "_on_ipv6_result",
    "_on_cloud_local_result",
    "_on_cloud_network_result",
    "_on_snmp_result",
    "_on_syn_result",
    "_on_udp_result",
    "_on_os_result",
    "_on_cve_result",
    "_on_exposure_result",
    "_on_m1_result",
    "_on_mesh_result",
    "_on_hardware_plugin_result",
    "_on_m2_result",
    "_on_m3_result",
    "_on_m4_result",
    "_on_m5_result",
    "_on_diag_result",
    "_on_cred_result",
    "_on_discovery_result",
    "_on_smb_result",
    "_on_plugin_result",
    "_on_pe_result",
}


def find_method_ranges(source_lines: list[str]) -> dict[str, tuple[int, int]]:
    """Return {method_name: (start_line, end_line)} using AST node positions."""
    source = "\n".join(source_lines)
    tree = ast.parse(source)

    # Find Dashboard class
    dashboard_node = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "Dashboard":
            dashboard_node = node
            break

    if dashboard_node is None:
        raise RuntimeError("Dashboard class not found")

    # Find all target methods and their line ranges
    methods: list[tuple[str, int, int]] = []
    for node in ast.walk(dashboard_node):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in TARGET_METHODS:
                methods.append((node.name, node.lineno, node.end_lineno))

    return {name: (start, end) for name, start, end in methods}


def extract_method_source(source_lines: list[str], start: int, end: int) -> list[str]:
    """Extract lines start..end (1-based, inclusive) and dedent by 4 spaces."""
    lines = source_lines[start - 1:end]
    # Remove one level of indentation (4 spaces) — methods are at class body level
    result = []
    for line in lines:
        if line.startswith("    "):
            result.append(line[4:])
        else:
            result.append(line)
    return result


def build_scan_wiring_module(
    method_blocks: list[tuple[str, list[str]]]
) -> str:
    parts = [
        '"""',
        "scan_wiring.py — ScanResultMixin for Dashboard scan result handlers.",
        "",
        "Extracted from ui/dashboard.py (Sprint 4, S1-2).",
        "Dashboard inherits ScanResultMixin to receive these methods.",
        '"""',
        "from __future__ import annotations",
        "",
        "from typing import TYPE_CHECKING",
        "",
        "if TYPE_CHECKING:",
        "    from ui.dashboard import Dashboard",
        "",
        "",
        "class ScanResultMixin:",
        '    """Mixin providing all _on_*_result scan wiring methods for Dashboard."""',
        "",
    ]
    for name, lines in method_blocks:
        for line in lines:
            parts.append("    " + line if line.strip() else line)
        parts.append("")
    return "\n".join(parts)


def remove_methods_from_dashboard(
    source_lines: list[str],
    ranges_to_remove: list[tuple[int, int]],
) -> list[str]:
    """Remove the given line ranges (1-based, inclusive) from source_lines.

    Ranges must be sorted by start line. Each method block is replaced by a
    single blank line so that nearby comments/decorators don't merge.
    """
    # Build a set of lines to drop
    drop = set()
    for start, end in ranges_to_remove:
        for ln in range(start, end + 1):
            drop.add(ln)

    # Also drop @pyqtSlot decorators immediately before each target method
    # and any blank lines between decorator and method that are within drop range
    result = []
    i = 0
    n = len(source_lines)
    while i < n:
        lineno = i + 1  # 1-based
        if lineno in drop:
            # Skip this line; insert a single blank placeholder at the start of each block
            i += 1
            continue
        result.append(source_lines[i])
        i += 1
    return result


def patch_dashboard_inheritance(lines: list[str]) -> list[str]:
    """Add ScanResultMixin to Dashboard base classes and import it."""
    result = []
    import_inserted = False
    for line in lines:
        # Insert import after the last existing 'from ui.' import in the file
        # (simple heuristic: add just before 'class Dashboard')
        if not import_inserted and line.startswith("class Dashboard("):
            result.append("from ui.scan_wiring import ScanResultMixin\n")
            result.append("\n")
            import_inserted = True
        # Patch the class definition
        if line.startswith("class Dashboard(QMainWindow):"):
            line = line.replace(
                "class Dashboard(QMainWindow):",
                "class Dashboard(ScanResultMixin, QMainWindow):",
            )
        result.append(line)
    return result


def main() -> None:
    print(f"Reading {DASHBOARD_PY} ...")
    source_text = DASHBOARD_PY.read_text(encoding="utf-8-sig")
    source_lines = source_text.splitlines(keepends=False)
    print(f"  {len(source_lines)} lines")

    print("Parsing AST to find method ranges ...")
    ranges = find_method_ranges(source_lines)
    if not ranges:
        print("ERROR: No target methods found — check method names.")
        sys.exit(1)

    print(f"  Found {len(ranges)} methods:")
    sorted_ranges = sorted(ranges.items(), key=lambda kv: kv[1][0])
    for name, (s, e) in sorted_ranges:
        print(f"    {name}: lines {s}–{e} ({e - s + 1} lines)")

    # Build scan_wiring.py content
    method_blocks = []
    for name, (start, end) in sorted_ranges:
        method_lines = extract_method_source(source_lines, start, end)
        method_blocks.append((name, method_lines))

    wiring_content = build_scan_wiring_module(method_blocks)
    SCAN_WIRING_PY.write_text(wiring_content, encoding="utf-8")
    print(f"\nWrote {SCAN_WIRING_PY} ({len(wiring_content.splitlines())} lines)")

    # Remove methods from dashboard.py
    removal_ranges = [r for _, r in sorted_ranges]
    patched = remove_methods_from_dashboard(source_lines, removal_ranges)

    # Patch inheritance
    patched = patch_dashboard_inheritance(patched)

    new_source = "\n".join(patched) + "\n"
    DASHBOARD_PY.write_text(new_source, encoding="utf-8")
    new_count = len(patched)
    original_count = len(source_lines)
    print(f"\nUpdated {DASHBOARD_PY}")
    print(f"  {original_count} → {new_count} lines (−{original_count - new_count})")
    print("\nDone.")


if __name__ == "__main__":
    main()
