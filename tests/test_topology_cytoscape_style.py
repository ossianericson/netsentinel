"""Tests for modules/topology_cytoscape_style.py — Cytoscape.js stylesheet builder."""
import re
from pathlib import Path

from modules.topology_cytoscape_style import _build_style


def test_import():
    assert callable(_build_style)


def test_build_style_returns_list():
    result = _build_style()
    assert isinstance(result, list)
    assert len(result) > 0


def test_build_style_entries_are_dicts():
    for entry in _build_style():
        assert isinstance(entry, dict)
        assert "selector" in entry
        assert "style" in entry


def test_build_style_no_raw_hex():
    """Stylesheet must use named constants — no raw hex literals in source."""
    src = (Path(__file__).parent.parent / "modules" / "topology_cytoscape_style.py").read_text(encoding="utf-8")
    hex_re = re.compile(r'#[0-9A-Fa-f]{6}\b|#[0-9A-Fa-f]{3}\b')
    matches = hex_re.findall(src)
    assert matches == [], f"Raw hex literals found: {matches}"


def test_build_style_base_node_present():
    styles = _build_style()
    selectors = [s["selector"] for s in styles]
    assert "node" in selectors
    assert "edge" in selectors
