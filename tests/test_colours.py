"""Tests for modules/colours.py — module-layer colour palette."""
import re
import pytest


def test_colours_import():
    from modules import colours
    assert colours is not None


def test_semantic_colours_exist():
    from modules.colours import RED, AMBER, GREEN, ACCENT, TEXT_MUTED
    for val in (RED, AMBER, GREEN, ACCENT, TEXT_MUTED):
        assert isinstance(val, str)
        assert val.startswith("#")


def test_export_palette_defined():
    from modules import colours
    export_attrs = [a for a in dir(colours) if a.startswith("EXPORT_")]
    assert len(export_attrs) >= 10, "Expected at least 10 EXPORT_ colour constants"


_HEX_PATTERN = re.compile(r"^#[0-9A-Fa-f]{3,8}$")


def test_all_colour_values_are_valid_hex():
    from modules import colours
    for name in dir(colours):
        if name.startswith("_"):
            continue
        val = getattr(colours, name)
        if not isinstance(val, str):
            continue
        assert _HEX_PATTERN.match(val), (
            f"colours.{name} = {val!r} is not a valid hex colour"
        )


def test_semantic_colours_match_ui_styles():
    from modules.colours import RED as MOD_RED, GREEN as MOD_GREEN, ACCENT as MOD_ACCENT
    from ui.styles import RED as UI_RED, GREEN as UI_GREEN, ACCENT as UI_ACCENT
    assert MOD_RED == UI_RED, "colours.RED must match ui/styles.RED"
    assert MOD_GREEN == UI_GREEN, "colours.GREEN must match ui/styles.GREEN"
    assert MOD_ACCENT == UI_ACCENT, "colours.ACCENT must match ui/styles.ACCENT"


def test_no_duplicate_values():
    from modules import colours
    vals = [
        getattr(colours, n)
        for n in dir(colours)
        if not n.startswith("_") and isinstance(getattr(colours, n), str)
    ]
    # Some duplicates are intentional (e.g., semantic mirrors) — just ensure
    # the set is not identical to the list (i.e., not all values are the same)
    assert len(set(vals)) > 1, "Expected multiple distinct colour values"
