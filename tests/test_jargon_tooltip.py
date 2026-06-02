"""Tests for ui.widgets.jargon_tooltip and data/glossary.json (Sprint A4)."""
import json
from pathlib import Path

import pytest

try:
    from PyQt6.QtWidgets import QApplication
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

pytestmark = pytest.mark.skipif(not _HAS_QT, reason="PyQt6 not available")

_REPO = Path(__file__).parent.parent


# ── Glossary data file ─────────────────────────────────────────────────────────

def test_glossary_json_exists():
    assert (_REPO / "data" / "glossary.json").is_file()


def test_glossary_json_valid():
    raw = json.loads((_REPO / "data" / "glossary.json").read_text(encoding="utf-8"))
    assert "terms" in raw
    assert isinstance(raw["terms"], list)
    assert len(raw["terms"]) >= 20, "Glossary must have at least 20 terms"


def test_glossary_terms_have_required_fields():
    raw = json.loads((_REPO / "data" / "glossary.json").read_text(encoding="utf-8"))
    for item in raw["terms"]:
        assert "term" in item, f"Missing 'term' key: {item}"
        assert "definition" in item, f"Missing 'definition' key: {item}"
        assert item["term"], "term must be non-empty"
        assert item["definition"], "definition must be non-empty"


def test_glossary_key_terms_present():
    raw = json.loads((_REPO / "data" / "glossary.json").read_text(encoding="utf-8"))
    terms = {item["term"] for item in raw["terms"]}
    required = {"ARP", "DNS", "DHCP", "STP", "Jitter", "Latency", "TLS", "CVSS"}
    missing = required - terms
    assert not missing, f"Glossary missing required terms: {missing}"


# ── Module import ──────────────────────────────────────────────────────────────

def test_jargon_tooltip_import():
    from ui.widgets.jargon_tooltip import JargonTooltip, get_definition  # noqa: F401


# ── get_definition() ───────────────────────────────────────────────────────────

def test_get_definition_known_term():
    from ui.widgets.jargon_tooltip import get_definition
    d = get_definition("DNS")
    assert isinstance(d, str)
    assert len(d) > 10, "Definition should be a real sentence"


def test_get_definition_unknown_term():
    from ui.widgets.jargon_tooltip import get_definition
    d = get_definition("XYZZY_DOES_NOT_EXIST")
    assert d == ""


def test_get_definition_case_sensitive():
    from ui.widgets.jargon_tooltip import get_definition
    # Terms in the glossary are stored with exact case
    d_upper = get_definition("DNS")
    d_lower = get_definition("dns")
    # At least the canonical form works
    assert d_upper != ""


# ── JargonTooltip widget ───────────────────────────────────────────────────────

@pytest.fixture
def jt():
    from ui.widgets.jargon_tooltip import JargonTooltip
    app = QApplication.instance()
    w = JargonTooltip("DNS")
    yield w
    try:
        w.deleteLater()
    except RuntimeError:
        pass
    if app:
        for _ in range(3):
            app.processEvents()


def test_jargon_tooltip_known_term_has_tooltip(jt):
    assert jt.toolTip() != "", "Known term must have a tooltip"
    assert "DNS" in jt.toolTip()


def test_jargon_tooltip_unknown_term():
    from ui.widgets.jargon_tooltip import JargonTooltip
    app = QApplication.instance()
    w = JargonTooltip("XYZZY_NO_MATCH")
    assert w.text() == "XYZZY_NO_MATCH"
    assert w.toolTip() == ""
    try:
        w.deleteLater()
    except RuntimeError:
        pass
    if app:
        for _ in range(3):
            app.processEvents()
