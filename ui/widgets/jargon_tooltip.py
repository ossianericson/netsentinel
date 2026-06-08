"""
JargonTooltip — underlined QLabel that shows a plain-English popup on hover (A4).

Usage::

    from ui.widgets.jargon_tooltip import JargonTooltip

    lbl = JargonTooltip("STP")
    # Looks up "STP" in data/glossary.json automatically.
    # Underlines the term and shows a definition balloon on hover.
    layout.addWidget(lbl)

    # Inline term inside a sentence — use make_jargon_label() for inline placement:
    row = QHBoxLayout()
    row.addWidget(QLabel("This page detects "))
    row.addWidget(JargonTooltip("STP"))
    row.addWidget(QLabel(" problems automatically."))
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QWidget

from ui.styles import ACCENT

# ── Glossary loader ────────────────────────────────────────────────────────────

_GLOSSARY: Optional[dict[str, str]] = None


def _load_glossary() -> dict[str, str]:
    global _GLOSSARY
    if _GLOSSARY is not None:
        return _GLOSSARY
    try:
        _data_dir = Path(__file__).parent.parent.parent / "data"
        with open(_data_dir / "glossary.json", encoding="utf-8") as fh:
            raw = json.load(fh)
        _GLOSSARY = {item["term"]: item["definition"] for item in raw.get("terms", [])}
    except Exception:
        _GLOSSARY = {}
    return _GLOSSARY


def get_definition(term: str) -> str:
    """Return the plain-English definition for *term*, or empty string if unknown."""
    return _load_glossary().get(term, "")


# ── Widget ─────────────────────────────────────────────────────────────────────

class JargonTooltip(QLabel):
    """
    A QLabel that underlines a technical term and shows its plain-English
    definition in a tooltip balloon on hover.

    If the term is not found in glossary.json the label renders normally
    with no underline and no tooltip (graceful degradation).
    """

    def __init__(self, term: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._term = term
        definition = get_definition(term)
        if definition:
            self.setText(
                f'<span style="color:{ACCENT}; text-decoration:underline dotted;">{term}</span>'
            )
            self.setTextFormat(Qt.TextFormat.RichText)
            self.setToolTip(
                f"<b>{term}</b><br><span style='font-size:11px;'>{definition}</span>"
            )
            self.setCursor(Qt.CursorShape.WhatsThisCursor)
        else:
            self.setText(term)
        self.setStyleSheet("background:transparent;")
