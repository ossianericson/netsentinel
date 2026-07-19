"""
Behavioral regression coverage for ui/widgets/home_session_widgets.py.

FreshnessStrip sits on always-dark NAV_BAR chrome in both themes. Its labels
must use a token that stays readable on that chrome in both themes -- unlike
TEXT_SECONDARY, which swings light-to-dark across themes and measures only
1.93:1 in Arctic Clean (fails WCAG AA). This test reads the widget's actual
rendered stylesheet (not just the abstract token catalogue in
tests/test_contrast.py) so it fails for real before the fix and passes after.
"""
from __future__ import annotations

import re

from tests.test_contrast import contrast_ratio, WCAG_AA

_COLOR_RE = re.compile(r"color:\s*(#[0-9A-Fa-f]{6})")


def _extract_color(stylesheet: str) -> str:
    m = _COLOR_RE.search(stylesheet)
    assert m, f"no color: found in stylesheet {stylesheet!r}"
    return m.group(1)


class TestFreshnessStripContrast:
    def test_scan_and_next_scan_labels_meet_contrast_on_nav_bar(self):
        from ui import styles as _s
        from ui.widgets.home_session_widgets import FreshnessStrip

        original = _s.get_active_theme_name()
        strip = FreshnessStrip()
        try:
            for theme in ("Arctic Clean", "Midnight Pro"):
                _s.apply_theme(theme)
                nav_bar = _s.THEMES[theme]["NAV_BAR"]
                for lbl in (strip._fs_scan_lbl, strip._fs_next_scan_lbl):
                    fg = _extract_color(lbl.styleSheet())
                    ratio = contrast_ratio(fg, nav_bar)
                    assert ratio >= WCAG_AA, (
                        f"[{theme}] {lbl.objectName() or lbl.text()!r}: "
                        f"{fg} on NAV_BAR={nav_bar} -> ratio={ratio:.2f} "
                        f"(need >= {WCAG_AA})"
                    )
        finally:
            strip.deleteLater()
            _s.apply_theme(original)
