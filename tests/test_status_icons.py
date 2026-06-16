"""Tests for colour-blind accessible status icons (UX Sprint 10, S10-2).

Validates that STATUS_ICON_* constants exist in ui.styles and that the key
status-display modules import and use them rather than using colour alone.
"""
from __future__ import annotations

import ast
from pathlib import Path

# ── Constants presence ────────────────────────────────────────────────────────

def test_status_icons_exported_from_styles():
    from ui.styles import STATUS_ICON_CRIT, STATUS_ICON_OK, STATUS_ICON_UNKNOWN, STATUS_ICON_WARN  # noqa: F401
    assert STATUS_ICON_OK      == "✓"
    assert STATUS_ICON_WARN    == "⚠"
    assert STATUS_ICON_CRIT    == "✗"
    assert STATUS_ICON_UNKNOWN == "○"


def test_status_icons_are_distinct():
    from ui.styles import STATUS_ICON_CRIT, STATUS_ICON_OK, STATUS_ICON_UNKNOWN, STATUS_ICON_WARN
    icons = [STATUS_ICON_OK, STATUS_ICON_WARN, STATUS_ICON_CRIT, STATUS_ICON_UNKNOWN]
    assert len(set(icons)) == 4, "All four status icons must be distinct characters"


# ── Static import checks ──────────────────────────────────────────────────────

def _imports_in(path: Path) -> set[str]:
    """Return the set of names imported from ui.styles in a source file."""
    src = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "ui.styles":
            names.update(a.name for a in node.names)
    return names


def test_service_page_imports_status_icons():
    path = Path("ui/pages/service_page.py")
    imports = _imports_in(path)
    assert "STATUS_ICON_OK" in imports, "service_page.py must import STATUS_ICON_OK"
    assert "STATUS_ICON_CRIT" in imports, "service_page.py must import STATUS_ICON_CRIT"


def test_uptime_page_imports_status_icons():
    path = Path("ui/pages/uptime_page.py")
    imports = _imports_in(path)
    assert "STATUS_ICON_OK" in imports, "uptime_page.py must import STATUS_ICON_OK"
    assert "STATUS_ICON_WARN" in imports, "uptime_page.py must import STATUS_ICON_WARN"
    assert "STATUS_ICON_CRIT" in imports, "uptime_page.py must import STATUS_ICON_CRIT"
    assert "STATUS_ICON_UNKNOWN" in imports, "uptime_page.py must import STATUS_ICON_UNKNOWN"


def test_monitor_state_imports_status_icons():
    path = Path("ui/monitor_state.py")
    imports = _imports_in(path)
    assert "STATUS_ICON_OK" in imports, "monitor_state.py must import STATUS_ICON_OK"
    assert "STATUS_ICON_WARN" in imports, "monitor_state.py must import STATUS_ICON_WARN"
    assert "STATUS_ICON_CRIT" in imports, "monitor_state.py must import STATUS_ICON_CRIT"


# ── icon_for_level helper ─────────────────────────────────────────────────────

def test_icon_for_level_maps_clean_to_ok():
    from ui.monitor_state import _icon_for_level
    from ui.styles import STATUS_ICON_OK
    assert _icon_for_level("CLEAN") == STATUS_ICON_OK
    assert _icon_for_level("LOW") == STATUS_ICON_OK


def test_icon_for_level_maps_warning_to_warn():
    from ui.monitor_state import _icon_for_level
    from ui.styles import STATUS_ICON_WARN
    assert _icon_for_level("WARNING") == STATUS_ICON_WARN
    assert _icon_for_level("MEDIUM") == STATUS_ICON_WARN


def test_icon_for_level_maps_high_to_crit():
    from ui.monitor_state import _icon_for_level
    from ui.styles import STATUS_ICON_CRIT
    assert _icon_for_level("HIGH") == STATUS_ICON_CRIT
    assert _icon_for_level("STORM") == STATUS_ICON_CRIT


def test_icon_for_level_unknown_returns_circle():
    from ui.monitor_state import _icon_for_level
    assert _icon_for_level("UNKNOWN") == "○"
    assert _icon_for_level("") == "○"
