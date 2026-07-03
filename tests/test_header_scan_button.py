"""test_header_scan_button.py — regression guard for the top-bar Scan CTA.

The header's "▶ Scan" button is the one PRIMARY action in the app chrome. It
shipped sharing ``_icon_btn_qss`` (transparent at rest, solid ACCENT only on
:hover), a style meant for the secondary icon buttons (gear, time picker), so
it looked like a faint outline until hovered. It must read as a solid primary
button at rest instead — a dedicated ``_scan_btn_qss`` with a solid ``{ACCENT}``
background in the base ``QToolButton`` rule.

Source-level check: building the real button requires a full Dashboard, so this
asserts on the header module source instead.
"""
from __future__ import annotations

import re
from pathlib import Path

HEADER = Path(__file__).parent.parent / "ui" / "header.py"


def _read() -> str:
    return HEADER.read_text(encoding="utf-8-sig")


def test_scan_button_does_not_use_ghost_icon_style():
    src = _read()
    m = re.search(r"self\._header_scan_btn\.setStyleSheet\((\w+)\)", src)
    assert m, "could not find _header_scan_btn.setStyleSheet(...) in header.py"
    assert m.group(1) != "_icon_btn_qss", (
        "header Scan button uses the transparent-at-rest icon style; it must use "
        "a dedicated solid primary style (see test docstring)."
    )


def test_scan_button_has_solid_accent_at_rest():
    src = _read()
    # Grab the _scan_btn_qss assignment (the f-string tuple) and confirm its base
    # QToolButton rule sets a solid ACCENT background before any :hover pseudo.
    m = re.search(r"_scan_btn_qss\s*=\s*\((.*?)\)\n", src, re.S)
    assert m, "expected a _scan_btn_qss definition in header.py"
    body = m.group(1)
    base = body.split(":hover")[0]
    assert "background:{ACCENT}" in base, (
        "base QToolButton rule must set a solid {ACCENT} background at rest"
    )


def test_secondary_header_controls_avoid_light_hex_border_on_dark_bar():
    # Regression: the gear + time-picker drew their rest border with
    # SIDEBAR_SECTION_BG, a near-WHITE light-theme value, producing a harsh white
    # box on the dark header bar in Arctic. Their border must be a faint
    # WHITE-alpha hairline that blends on the dark bar in both themes.
    src = _read()
    for name in ("_icon_btn_qss", "_time_combo_qss"):
        m = re.search(rf"{name}\s*=\s*\((.*?)\)\n", src, re.S)
        assert m, f"expected {name} in header.py"
        base = m.group(1).split(":hover")[0]
        assert "border:1px solid {SIDEBAR_SECTION_BG}" not in base, (
            f"{name} uses a light-theme hex border on the dark header bar"
        )
        assert "alpha(WHITE" in base, (
            f"{name} rest border must be a faint alpha(WHITE, ...) hairline"
        )
