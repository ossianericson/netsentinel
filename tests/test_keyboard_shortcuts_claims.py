"""
Regression test for F-19 (claims-audit): fake keyboard shortcuts (Ctrl+R, Ctrl+E, F5,
Ctrl+Shift+M "Matrix mode") were documented in 4 places (ui/help_tab.py, ui/tabs.py,
ui/nav/builder.py, ui/pages/settings_cards.py) but wired to no QShortcut anywhere in
the app -- and the one real binding these lists omitted, Ctrl+S (Inventory page save),
appeared in none of them.

The real QShortcut set lives in ui/dashboard.py's __init__: Ctrl+Q/F/K, Escape, ?,
Ctrl+,, Ctrl+L, Ctrl+Shift+H, Alt+1..5, plus Ctrl+S on ui/pages/inventory_page.py.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parent.parent

_FAKE_TOKENS = ["Ctrl+R", "Ctrl + R", "Ctrl+E", "Ctrl + E",
                "F5", "Ctrl+Shift+M", "Ctrl + Shift + M", "Matrix mode"]

_FILES = [
    ROOT / "ui" / "help_tab.py",
    ROOT / "ui" / "tabs.py",
    ROOT / "ui" / "nav" / "builder.py",
    ROOT / "ui" / "pages" / "settings_cards.py",
]


def test_no_fake_shortcuts_documented_anywhere():
    offenders = []
    for path in _FILES:
        src = path.read_text(encoding="utf-8")
        for token in _FAKE_TOKENS:
            if token in src:
                offenders.append(f"{path.name}: {token!r}")
    assert not offenders, f"Fake shortcut claims still present: {offenders}"


def test_real_ctrl_s_documented_in_help_tab_and_settings():
    help_tab_src = (ROOT / "ui" / "help_tab.py").read_text(encoding="utf-8")
    settings_src = (ROOT / "ui" / "pages" / "settings_cards.py").read_text(encoding="utf-8")
    assert "Ctrl + S" in help_tab_src
    assert "Ctrl + S" in settings_src


def test_dashboard_has_no_qshortcut_for_fake_bindings():
    dashboard_src = (ROOT / "ui" / "dashboard.py").read_text(encoding="utf-8")
    for key in ("Ctrl+R", "Ctrl+E", "F5", "Ctrl+Shift+M"):
        assert f'QKeySequence("{key}")' not in dashboard_src
    assert 'QKeySequence("Ctrl+S")' in (ROOT / "ui" / "pages" / "inventory_page.py").read_text(encoding="utf-8")
