"""
Regression test — the global QSS must style QTabBar in both themes.

Bug (reported 2026-07-26): Security Audit -> Windows Shares (SMB) rendered its
"Shares" / "Users" inner tabs as unreadable dark-on-dark in Midnight Pro.

Root cause: `ui/styles.py` defined no QTabBar/QTabWidget rule anywhere -- neither
in `_build_qss()` nor in `get_app_qss()`. Any QTabWidget created without its own
inline stylesheet therefore fell through to Qt's *native palette*, which is not
theme-aware. The global `QWidget { background-color: ... }` base rule does not
rescue it: `QTabBar::tab` is a subcontrol painted by the style, not the widget
background, so it never sees that declaration.

Two tab widgets in the app had zero styling, both in `ui/tabs_recon.py`
(Login Test at ~L804, Windows Shares/SMB at ~L992), plus a half-styled third in
`ui/widgets/device_detail_pane.py` that set `color:` with no tab background.

The fix is in the global QSS rather than per-site, so any future QTabWidget is
correct by default. `tests/test_qss_widget_coverage.py` is the general enforcer
for this whole bug class; this file is the specific regression pin.
"""

from __future__ import annotations

import re

import pytest


def _global_qss(theme_name: str) -> str:
    """Return the full application-level QSS as applied for `theme_name`."""
    from ui import styles as _s

    _s.apply_theme(theme_name)
    return _s.MAIN_STYLE + _s.get_app_qss()


def _theme_names():
    from ui.styles import THEMES

    return list(THEMES.keys())


_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)


def _rule_body(qss: str, selector: str) -> str:
    """Return the declaration block for `selector`, or "" when absent.

    Matches the selector as a whole comma-separated entry in a selector list so
    `QTabBar::tab` does not accidentally match `QTabBar::tab:selected`.

    Comments are stripped first: prose between two rules is not brace-delimited,
    so a `/* ... */` block containing a comma would otherwise be swallowed into
    the following rule's selector list.
    """
    qss = _COMMENT_RE.sub("\n", qss)
    pattern = re.compile(
        r"(?:^|[},])\s*([^{}]*?)\{([^{}]*)\}",
        re.MULTILINE,
    )
    for match in pattern.finditer(qss):
        selectors = [s.strip() for s in match.group(1).split(",")]
        if selector in selectors:
            return match.group(2)
    return ""


@pytest.mark.parametrize("theme_name", _theme_names())
@pytest.mark.parametrize(
    "selector",
    ["QTabBar::tab", "QTabBar::tab:selected"],
)
def test_tab_selector_sets_both_background_and_color(theme_name: str, selector: str):
    """Every tab state must declare BOTH background and color.

    Declaring only one leaves the other to Qt's native palette -- exactly the
    half-styled shape that shipped the unreadable SMB tabs (RULE-UX6 is the
    same invariant for `item:selected`).
    """
    qss = _global_qss(theme_name)
    body = _rule_body(qss, selector)

    assert body, (
        f"[{theme_name}] The global QSS defines no `{selector}` rule.\n"
        f"An unstyled QTabWidget falls back to Qt's native palette, which is "
        f"not theme-aware -- this is the SMB-tabs bug. Add the rule to "
        f"`_build_qss()` in ui/styles.py."
    )
    assert re.search(r"\bbackground(-color)?\s*:", body), (
        f"[{theme_name}] `{selector}` sets no background; the tab background "
        f"falls back to the native palette."
    )
    assert re.search(r"(?<!-)\bcolor\s*:", body), (
        f"[{theme_name}] `{selector}` sets no text colour; the tab label "
        f"falls back to the native palette."
    )


@pytest.mark.parametrize("theme_name", _theme_names())
def test_tab_pane_is_styled(theme_name: str):
    """The pane behind the tab content must not fall back to the palette."""
    qss = _global_qss(theme_name)
    body = _rule_body(qss, "QTabWidget::pane")
    assert body and re.search(r"\bbackground(-color)?\s*:", body), (
        f"[{theme_name}] `QTabWidget::pane` must declare a background so the "
        f"area behind tab content is theme-aware."
    )


@pytest.mark.parametrize("theme_name", _theme_names())
def test_selected_and_unselected_tabs_are_visually_distinct(theme_name: str):
    """A selected tab must differ from an unselected one by more than nothing.

    The reported bug was partly "I can't tell which tab is active". Assert the
    selected rule actually changes something beyond re-stating the base.
    """
    qss = _global_qss(theme_name)
    base = _rule_body(qss, "QTabBar::tab").strip()
    selected = _rule_body(qss, "QTabBar::tab:selected").strip()
    assert base and selected and base != selected, (
        f"[{theme_name}] `QTabBar::tab:selected` is identical to the base tab "
        f"rule -- the active tab would be indistinguishable."
    )
