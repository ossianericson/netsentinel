"""Empty state quality audit (UX Sprint 10, S10-4).

Every page that requires scan data must use the EmptyStateCard pattern
(RULE-UX5): a QStackedWidget with page 0 = empty state + CTA button,
page 1 = content. Plain "No data yet" labels with no CTA are a dead end.

This test:
  1. Checks that the known set of pages using the scan_requested pattern
     still have that signal defined.
  2. Verifies no page introduced a new bare dead-end empty-state label
     outside an EmptyStateCard context.
"""
from __future__ import annotations

import ast
from pathlib import Path

_PAGES_DIR = Path("ui/pages")


def _ast_parse(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return None


def _has_signal(tree: ast.Module, signal_name: str) -> bool:
    """Return True if the file assigns `signal_name = pyqtSignal(...)`."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == signal_name:
                    return True
    return False


# Pages that expose scan_requested per RULE-UX5
_SCAN_REQUESTED_PAGES = [
    "uptime_page.py",
    "cert_page.py",
    "cve_page.py",
    "connections_page.py",
    "app_traffic_page.py",
    "threat_intel_page.py",
    "history_page.py",
    "baseline_page.py",
    "trend_page.py",
    "network_doc_page.py",
    "geo_map_page.py",
    "security_overview_page.py",
]


def test_scan_requested_signal_present_in_required_pages():
    missing = []
    for fname in _SCAN_REQUESTED_PAGES:
        path = _PAGES_DIR / fname
        if not path.exists():
            missing.append(f"{fname} (file missing)")
            continue
        tree = _ast_parse(path)
        if tree is None:
            missing.append(f"{fname} (parse error)")
            continue
        if not _has_signal(tree, "scan_requested"):
            missing.append(fname)
    assert not missing, (
        f"These pages must define scan_requested = pyqtSignal() (RULE-UX5): {missing}"
    )


# Known plain-text dead-end patterns allowed (niche in-card timestamps, etc.)
_ALLOWED_DEAD_ENDS = {
    "plugin_device_page.py":    "timestamp row inside full plugin page — not a page-level empty state",
    "monitor_overview_page.py": "aggregated monitor view; individual tiles show their own empty states",
}

_DEAD_END_PATTERNS = [
    '"No data yet"',
    "'No data yet'",
]


def test_no_new_dead_end_empty_states():
    offenders = []
    for path in sorted(_PAGES_DIR.glob("*.py")):
        src = path.read_text(encoding="utf-8")
        for pat in _DEAD_END_PATTERNS:
            if pat not in src:
                continue
            fname = path.name
            if fname in _ALLOWED_DEAD_ENDS:
                break
            # Check: is there an EmptyStateCard or scan_requested nearby?
            if "EmptyStateCard" not in src and "scan_requested" not in src:
                offenders.append(
                    f"{fname}: contains {pat!r} without EmptyStateCard or scan_requested"
                )
            break
    assert not offenders, (
        "Dead-end empty states found (no CTA for the user):\n"
        + "\n".join(offenders)
        + "\nFix: use EmptyStateCard with a CTA button, or add to _ALLOWED_DEAD_ENDS with a reason."
    )
