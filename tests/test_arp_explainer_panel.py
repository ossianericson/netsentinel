"""Regression test for F-31: ui/help.py claims ARP Spoof Watch has an
"Explain This" strip showing a step-by-step ARP spoofing diagram, but
_build_arp_monitor_tab() wired no ExplainerPanel at all.

The "rogue_device" ExplainerPanel content (used on the Devices/M1 tab) is
literally about ARP and ARP spoofing already, and its "See ARP animated
diagram" button routes to Protocol Visualizer -- exactly what the claim
describes. This reuses that existing widget rather than inventing new
content.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QWidget

from ui.tabs_monitors import _MonitorTabsMixin
from ui.widgets.explainer_panel import ExplainerPanel


class _ArpTabHost(_MonitorTabsMixin, QWidget):
    """Minimal Dashboard stand-in exposing only what _build_arp_monitor_tab touches."""

    def __init__(self):
        super().__init__()
        self._arp_worker = None

    def _nav_rail_go_to(self, label: str) -> None:
        pass


def _cleanup(w, qt_app) -> None:
    try:
        w.deleteLater()
    except RuntimeError:
        pass  # non-fatal — already deleted
    if qt_app:
        for _ in range(3):
            qt_app.processEvents()


def test_arp_monitor_tab_has_explainer_panel(qt_app):
    host = _ArpTabHost()
    tab = host._build_arp_monitor_tab()  # keep alive — the panel is its child

    assert hasattr(host, "_arp_explainer"), (
        "ARP Spoof Watch has no ExplainerPanel -- ui/help.py's 'Explain This' "
        "strip claim (F-31) is false"
    )
    assert isinstance(host._arp_explainer, ExplainerPanel)
    _cleanup(tab, qt_app)


def test_arp_explainer_panel_has_arp_content(qt_app):
    host = _ArpTabHost()
    tab = host._build_arp_monitor_tab()  # keep alive — the panel is its child

    # The panel must not be the "no content configured" hidden state.
    assert host._arp_explainer.isHidden() is False
    _cleanup(tab, qt_app)
