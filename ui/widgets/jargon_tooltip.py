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

    # Contextual "learn more" inline link (S7-3) — click expands a multi-paragraph
    # popover (definition + "what to look for" detail) instead of a hover tooltip.
    # Only add it where find_known_term() actually finds a glossary term:
    from ui.widgets.jargon_tooltip import LearnMoreLink, find_known_term
    term = find_known_term(alert_message)
    if term:
        row.addWidget(LearnMoreLink(term))
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtWidgets import QApplication, QFrame, QLabel, QVBoxLayout, QWidget

from ui import styles as _s

# ── Glossary loader ────────────────────────────────────────────────────────────

_GLOSSARY: Optional[dict[str, str]] = None
_GLOSSARY_DETAIL: Optional[dict[str, str]] = None


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


def _load_glossary_detail() -> dict[str, str]:
    global _GLOSSARY_DETAIL
    if _GLOSSARY_DETAIL is not None:
        return _GLOSSARY_DETAIL
    try:
        _data_dir = Path(__file__).parent.parent.parent / "data"
        with open(_data_dir / "glossary.json", encoding="utf-8") as fh:
            raw = json.load(fh)
        _GLOSSARY_DETAIL = {
            item["term"]: item["detail"] for item in raw.get("terms", []) if item.get("detail")
        }
    except Exception:
        _GLOSSARY_DETAIL = {}
    return _GLOSSARY_DETAIL


def get_definition(term: str) -> str:
    """Return the plain-English definition for *term*, or empty string if unknown."""
    return _load_glossary().get(term, "")


def get_detail(term: str) -> str:
    """Return the second-paragraph 'what to look for' detail for *term*, or "" if none (S7-3)."""
    return _load_glossary_detail().get(term, "")


def find_known_term(text: str) -> str:
    """Return the first glossary term that appears as a whole word in *text*, or "" (S7-3).

    Longer terms are checked first so e.g. "MAC Address" wins over a bare "MAC" if both
    were ever defined. Underscores count as separators (not word characters) so rule
    names like "ARP_SPOOF" or "RTT_THRESHOLD" still match their bare term.
    """
    terms = sorted(_load_glossary().keys(), key=len, reverse=True)
    for term in terms:
        pattern = rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])"
        if re.search(pattern, text, re.IGNORECASE):
            return term
    return ""


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
                f'<span style="color:{_s.ACCENT}; text-decoration:underline dotted;">{term}</span>'
            )
            self.setTextFormat(Qt.TextFormat.RichText)
            # Not routed through safe_tooltip() — this string is already hand-built
            # rich text (<b>/<span> tags); safe_tooltip() HTML-escapes its input,
            # which would literal-ize those tags. Wrap with the same fixed light
            # foreground color it applies, without escaping the inner markup.
            self.setToolTip(
                f"<span style='color:{_s.WHITE};'>"
                f"<b>{term}</b><br><span style='font-size:11px;'>{definition}</span>"
                f"</span>"
            )
            self.setCursor(Qt.CursorShape.WhatsThisCursor)
        else:
            self.setText(term)
        self.setStyleSheet("background:transparent;")


# ── Contextual "learn more" inline link (S7-3) ──────────────────────────────────

class _LearnMorePopover(QFrame):
    """Floating panel showing a glossary term's full (possibly multi-paragraph)
    explanation — the definition plus an optional 'what to look for' detail paragraph.
    """

    def __init__(self, term: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setFixedWidth(280)
        _s.themed_ss(self, "QFrame {{ background:{BG_CARD}; border:1px solid {BORDER}; border-radius:4px; }}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 12)
        lay.setSpacing(6)

        title = QLabel(term)
        title.setWordWrap(True)
        _s.themed_ss(title, "font-size:12px; font-weight:bold; color:{TEXT_PRIMARY};"
            " background:transparent; border:none;")
        lay.addWidget(title)

        defn = QLabel(get_definition(term) or "No definition available.")
        defn.setWordWrap(True)
        _s.themed_ss(defn, "font-size:11px; color:{TEXT_PRIMARY}; background:transparent; border:none;")
        lay.addWidget(defn)

        detail = get_detail(term)
        if detail:
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setFixedHeight(1)
            _s.themed_ss(sep, "color:{BORDER}; background:{BORDER};")
            lay.addWidget(sep)
            detail_lbl = QLabel(detail)
            detail_lbl.setWordWrap(True)
            _s.themed_ss(detail_lbl, "font-size:11px; color:{TEXT_SECONDARY}; background:transparent; border:none;")
            lay.addWidget(detail_lbl)

    def show_at(self, global_pos: QPoint) -> None:
        self.adjustSize()
        x, y = global_pos.x(), global_pos.y() + 4

        screen = QApplication.screenAt(global_pos) or QApplication.primaryScreen()
        if screen:
            avail = screen.availableGeometry()
            x = max(avail.left() + 4, min(x, avail.right() - self.width() - 4))
            y = max(avail.top() + 4, min(y, avail.bottom() - self.height() - 4))

        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.move(x, y)
        self.show()
        self.raise_()


class LearnMoreLink(QLabel):
    """Small inline clickable link — 'ⓘ what is "X"? →' — that opens a multi-paragraph
    glossary popover for *term* on click (S7-3).

    Use alongside ``find_known_term()`` to surface this only where a real glossary
    term was detected in scan-result or alert text — never invent a term to link to.
    """

    def __init__(self, term: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._term = term
        self._popover: "_LearnMorePopover | None" = None
        self.setText(f'<span style="color:{_s.ACCENT};">ⓘ what is "{term}"? →</span>')
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("background:transparent; font-size:10px;")
        self.setMinimumHeight(20)

    def mousePressEvent(self, event) -> None:
        if self._popover is None:
            self._popover = _LearnMorePopover(self._term)
        global_pos = self.mapToGlobal(QPoint(0, self.height()))
        self._popover.show_at(global_pos)
        super().mousePressEvent(event)
