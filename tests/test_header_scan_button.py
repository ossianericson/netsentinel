"""test_header_scan_button.py — regression guard for the top-bar Scan CTA.

The header's "▶ Scan" button uses a dedicated ``_scan_btn_qss`` (not the shared
``_icon_btn_qss``) so it can be tuned independently of the other ghost chrome
buttons (gear, time picker). At rest it matches those neighbours — transparent
background with a faint WHITE-alpha hairline border — and fills solid
``{ACCENT}`` only on ``:hover``/``:pressed``. A prior session pinned it solid at
rest as a workaround for an unrelated colour bug; that was reverted so the
button once again matches its neighbours' at-rest look.

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
    # After the live-theme conversion the button registers a live template via
    # themed_ss(widget, <callable>) instead of setStyleSheet(<str>).
    m = re.search(r"themed_ss\(\s*self\._header_scan_btn,\s*(\w+)\)", src)
    assert m, "could not find themed_ss(self._header_scan_btn, ...) in header.py"
    assert m.group(1) != "_icon_btn_qss", (
        "header Scan button uses the transparent-at-rest icon style; it must use "
        "a dedicated solid primary style (see test docstring)."
    )


def test_scan_button_matches_ghost_chrome_at_rest():
    src = _read()
    # Grab the _scan_btn_qss callable body (the f-string tuple) and confirm its
    # base QToolButton rule is transparent at rest — matching the gear/time-picker
    # ghost buttons — and only fills solid ACCENT on :hover.
    m = re.search(r"def _scan_btn_qss\(\):\s*return \((.*?)\)\n", src, re.S)
    assert m, "expected a _scan_btn_qss definition in header.py"
    body = m.group(1)
    base = body.split(":hover")[0]
    assert "background:transparent" in base, (
        "base QToolButton rule must be transparent at rest, matching the "
        "ghost chrome buttons beside it"
    )
    assert "alpha(_s.WHITE" in base, (
        "rest border must be a faint alpha(WHITE, ...) hairline like its neighbours"
    )
    hover = body.split(":hover", 1)[1]
    assert "background:{_s.ACCENT}" in hover, (
        "hover rule must fill solid {ACCENT} background"
    )


def test_secondary_header_controls_avoid_light_hex_border_on_dark_bar():
    # Regression: the gear + time-picker drew their rest border with
    # SIDEBAR_SECTION_BG, a near-WHITE light-theme value, producing a harsh white
    # box on the dark header bar in Arctic. Their border must be a faint
    # WHITE-alpha hairline that blends on the dark bar in both themes.
    src = _read()
    for name in ("_icon_btn_qss", "_time_combo_qss"):
        m = re.search(rf"def {name}\(\):\s*return \((.*?)\)\n", src, re.S)
        assert m, f"expected {name} in header.py"
        base = m.group(1).split(":hover")[0]
        assert "border:1px solid {_s.SIDEBAR_SECTION_BG}" not in base, (
            f"{name} uses a light-theme hex border on the dark header bar"
        )
        assert "alpha(_s.WHITE" in base, (
            f"{name} rest border must be a faint alpha(WHITE, ...) hairline"
        )
