"""
Regression test for F-49: the "See {protocol} animated diagram" button in
ExplainerPanel emitted only a bare page-navigation signal with no protocol
argument -- every wiring site routed through the generic
_nav_rail_go_to(label), which has no pre-select parameter, so Protocol
Visualizer always opened on whatever protocol was last selected instead of
the one the button named.

ProtocolVizPage.select_protocol(key) already existed as a public API
(ui/pages/protocol_viz_page.py) and app.py already had the exact wiring
pattern for LabModePage.explore_protocol -- this fix reuses both instead
of inventing anything new.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtWidgets import QPushButton

from ui.widgets.explainer_panel import ExplainerPanel

ROOT = Path(__file__).parent.parent


@pytest.fixture
def panel(qt_app):
    p = ExplainerPanel("stp_rogue")  # protocol key = "STP"
    yield p
    try:
        p.deleteLater()
    except RuntimeError:
        pass  # already gone
    if qt_app:
        for _ in range(3):
            qt_app.processEvents()


def _find_diagram_button(widget) -> QPushButton:
    for btn in widget.findChildren(QPushButton):
        if btn.text().startswith("▶") and "animated diagram" in btn.text():
            return btn
    raise AssertionError("could not find the 'See ... animated diagram' button")


def test_see_diagram_click_emits_navigate_and_protocol(panel):
    nav_calls = []
    proto_calls = []
    panel.navigate_to.connect(nav_calls.append)
    panel.explore_protocol.connect(proto_calls.append)

    btn = _find_diagram_button(panel)
    btn.click()

    assert nav_calls == ["Protocol Visualizer"]
    assert proto_calls == ["STP"]


def test_app_wires_all_four_explainer_panels_to_explore_protocol():
    """Static guard: every ExplainerPanel instance created in tabs_scan.py
    must have its explore_protocol signal connected in app.py, or the
    pre-select silently no-ops for that page (same class of bug as F-49
    itself -- a wiring site missed)."""
    tabs_scan_src = (ROOT / "ui" / "tabs_scan.py").read_text(encoding="utf-8")
    app_src = (ROOT / "app.py").read_text(encoding="utf-8")

    explainer_attrs = sorted(set(
        line.split("self.", 1)[1].split(" ", 1)[0].split("=")[0].strip()
        for line in tabs_scan_src.splitlines()
        if "= ExplainerPanel(" in line
    ))
    assert explainer_attrs, "expected at least one ExplainerPanel(...) construction"

    for attr in explainer_attrs:
        assert f"window.{attr}" in app_src, (
            f"window.{attr}.explore_protocol is never connected in app.py"
        )
    assert "explore_protocol.connect(_on_explore_protocol)" in app_src
