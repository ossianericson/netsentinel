"""
objective_badge.py — Compact exam-objective badge widget for Lab Mode and Protocol Viz.

Shows a pill-style badge (e.g. "N+" or "CCNA") that reveals full exam objectives in a
rich tooltip on hover.  Data comes from data/curriculum_map.json.

Usage:
    badges = ObjectiveBadge.for_scenario("Find the Rogue Device", parent=self)
    for badge in badges:
        hbox.addWidget(badge)
"""
from __future__ import annotations

from typing import List

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QWidget

from modules.curriculum_map import entry_for
from ui import styles as _s


# ── Badge labels per certification ────────────────────────────────────────────

_CERT_LABELS = {
    "Network+": "N+",
    "CCNA":     "CCNA",
    "Security+":"Sec+",
}

_CERT_COLORS = {
    "N+":   ("CERT_NETPLUS_BG", "WHITE"),   # CompTIA red
    "CCNA": ("CERT_CISCO_BG",   "NAV_BAR"), # Cisco teal on dark bg
    "Sec+": ("CERT_SEC_BG",     "WHITE"),   # CompTIA purple
}


# ── Widget ────────────────────────────────────────────────────────────────────

class ObjectiveBadge(QLabel):
    """
    Compact pill badge showing an exam certification abbreviation.

    Hover tooltip lists the full exam objectives from curriculum_map.json.
    """

    def __init__(self, cert_label: str, objectives: list[str],
                 study_note: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cert_label = cert_label
        bg_name, fg_name = _CERT_COLORS.get(cert_label, ("ACCENT", "WHITE"))

        self.setText(cert_label)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedHeight(18)
        self.setContentsMargins(6, 0, 6, 0)
        _s.themed_ss(self, lambda bn=bg_name, fn=fg_name: (
            f"QLabel {{ background:{getattr(_s, bn)}; color:{getattr(_s, fn)}; border-radius:9px;"
            f" font-size:9px; font-weight:bold; padding:0 6px; border:none; }}"
        ))

        tip_lines = [f"<b>{cert_label} exam objectives:</b>"]
        for obj in objectives:
            tip_lines.append(f"&nbsp;&nbsp;• {obj}")
        if study_note:
            tip_lines.append(f"<br><i>{study_note}</i>")
        # Not routed through safe_tooltip() — tip_lines is already hand-built rich
        # text (<b>/<br>/<i> tags, &nbsp; entities); safe_tooltip() HTML-escapes
        # its input, which would literal-ize that markup. Wrap with the same
        # fixed light foreground color it applies, without escaping the content.
        self.setToolTip(f"<span style='color:{_s.WHITE};'>" + "<br>".join(tip_lines) + "</span>")
        self.setCursor(Qt.CursorShape.WhatsThisCursor)

    # ── Factory helpers ───────────────────────────────────────────────────────

    @classmethod
    def for_scenario(cls, scenario_name: str, parent: QWidget | None = None) -> List["ObjectiveBadge"]:
        """Return one badge per certification for the given lab scenario name."""
        entry = entry_for("lab_scenarios", scenario_name)
        return cls._from_entry(entry, parent)

    @classmethod
    def for_protocol(cls, protocol_key: str, parent: QWidget | None = None) -> List["ObjectiveBadge"]:
        """Return one badge per certification for the given protocol visualizer key (e.g. 'ARP')."""
        entry = entry_for("protocol_viz", protocol_key)
        return cls._from_entry(entry, parent)

    @classmethod
    def for_page(cls, page_label: str, parent: QWidget | None = None) -> List["ObjectiveBadge"]:
        """Return one badge per certification for the given nav page label."""
        entry = entry_for("pages", page_label)
        return cls._from_entry(entry, parent)

    @classmethod
    def _from_entry(cls, entry: dict, parent: QWidget | None) -> List["ObjectiveBadge"]:
        certs       = entry.get("certifications", [])
        objectives  = entry.get("objectives", [])
        study_note  = entry.get("study_note", "")
        badges = []
        for cert in certs:
            label = _CERT_LABELS.get(cert, cert)
            badges.append(cls(label, objectives, study_note, parent))
        return badges
