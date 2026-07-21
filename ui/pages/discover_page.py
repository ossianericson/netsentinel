"""
Feature Guide page — searchable index of every NetSentinel feature.

Gives users a single place to discover what the app can do, understand each
feature in one sentence, and navigate directly to it.  Grouped by theme;
filterable by name, description, group, page label, or synonym tag.
"""
from __future__ import annotations

import datetime
import json

from PyQt6.QtCore import QSettings, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from ui import styles as _s

from ui.pages.discover_data import _FEATURES, _RECOMMENDED_PAGES



_REQUIRES_COLOR_NAME = {
    "Npcap": "AMBER",
    "admin": "RED",
}

_REQUIRES_TOOLTIP = {
    "Npcap": "Requires the Npcap packet-capture driver — install it from npcap.com, "
             "or via the WinGet task offered during setup.",
    "admin": "Requires running NetSentinel as Administrator — right-click the app "
             "and choose 'Run as administrator'.",
    "Npcap + Admin": "Requires both the Npcap packet-capture driver (npcap.com) and "
             "running NetSentinel as Administrator.",
}


# ── Widget ─────────────────────────────────────────────────────────────────────

class FeatureGuidePage(QWidget):
    """Searchable index of every NetSentinel feature."""

    navigate_to = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._visited_pages: set[str] = set()
        self._build_ui()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._load_visited_pages()
        if not self._search.text().strip():
            self._render_features(_FEATURES)

    def _load_visited_pages(self) -> None:
        """Refresh the set of page labels the user has actually visited (S9-4)."""
        qs = QSettings("NetSentinel", "NetSentinel")
        try:
            self._visited_pages = set(json.loads(qs.value("discover/visited_pages", "[]")))
        except Exception:
            self._visited_pages = set()

    def _recommended_features(self) -> list[dict]:
        """Behavioural recommendations — unvisited pages from a fixed priority
        list (S9-4). No persona, no scan dependency: purely "haven't tried this yet"."""
        by_page = {f["page"]: f for f in _FEATURES if f.get("page")}
        return [
            by_page[label] for label in _RECOMMENDED_PAGES
            if label in by_page and label not in self._visited_pages
        ][:3]

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Page header
        hdr = QLabel("Feature Guide")
        hdr.setFixedHeight(32)
        _s.themed_ss(hdr, "QLabel {{ background:{BG_DARK}; font-size:15px; font-weight:bold;"
            " color:{TEXT_PRIMARY}; padding:0 16px; border-bottom:1px solid {BORDER}; }}")
        root.addWidget(hdr)

        # Search bar
        search_row = QHBoxLayout()
        search_row.setContentsMargins(16, 10, 16, 6)
        search_row.setSpacing(8)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search features, synonyms, page names…")
        _s.themed_ss(self._search, "QLineEdit {{ border:1px solid {BORDER}; border-radius:4px;"
            " padding:4px 10px; font-size:12px; background:{BG_CARD}; color:{TEXT_PRIMARY}; }}")
        self._search.textChanged.connect(self._apply_filter)
        search_row.addWidget(self._search)

        sub = QLabel(f"{len(_FEATURES)} features")
        _s.themed_ss(sub, "font-size:11px; color:{TEXT_MUTED}; background:transparent;")
        search_row.addWidget(sub)
        root.addLayout(search_row)

        # Scrollable body
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        _s.themed_ss(scroll, "QScrollArea {{ background:{BG_DARK}; border:none; }}")

        self._body = QWidget()
        _s.themed_ss(self._body, "background:{BG_DARK};")
        self._body_lay = QVBoxLayout(self._body)
        self._body_lay.setContentsMargins(16, 8, 16, 16)
        self._body_lay.setSpacing(4)

        scroll.setWidget(self._body)
        root.addWidget(scroll, 1)

        self._load_visited_pages()
        self._render_features(_FEATURES)

    def _render_features(self, features: list[dict], show_recommended: bool = True) -> None:
        while self._body_lay.count():
            item = self._body_lay.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        if show_recommended:
            recommended = self._recommended_features()
            if recommended:
                rec_lbl = QLabel("RECOMMENDED FOR YOU")
                _s.themed_ss(rec_lbl, "font-size:10px; font-weight:bold; color:{ACCENT};"
                    " background:transparent; letter-spacing:1px;")
                self._body_lay.addWidget(rec_lbl)
                for feat in recommended:
                    self._body_lay.addWidget(self._make_card(feat))

        current_group = None
        for feat in features:
            g = feat["group"]
            if g != current_group:
                current_group = g
                grp_lbl = QLabel(g.upper())
                _s.themed_ss(grp_lbl, "font-size:10px; font-weight:bold; color:{TEXT_SECONDARY};"
                    " background:transparent; letter-spacing:1px; padding-top:10px;")
                self._body_lay.addWidget(grp_lbl)

            card = self._make_card(feat)
            self._body_lay.addWidget(card)

        if not features:
            empty = QLabel("No features match your search.")
            _s.themed_ss(empty, "font-size:12px; color:{TEXT_MUTED}; background:transparent;")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._body_lay.addWidget(empty)

        self._body_lay.addStretch()

    def _make_card(self, feat: dict) -> QFrame:
        card = QFrame()
        _s.themed_ss(card, "QFrame {{ background:{BG_CARD}; border:1px solid {BORDER};"
            " border-radius:{CARD_RADIUS}; }}")
        lay = QHBoxLayout(card)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(10)

        icon_lbl = QLabel(feat["icon"])
        icon_lbl.setFixedWidth(18)
        _s.themed_ss(icon_lbl, "font-size:14px; color:{TEXT_PRIMARY}; background:transparent; border:none;")
        lay.addWidget(icon_lbl)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        text_col.setContentsMargins(0, 0, 0, 0)

        name_row = QHBoxLayout()
        name_row.setSpacing(6)
        name_lbl = QLabel(feat["name"])
        _s.themed_ss(name_lbl, "font-size:12px; font-weight:bold; color:{TEXT_PRIMARY};"
            " background:transparent; border:none;")
        name_row.addWidget(name_lbl)

        if feat.get("requires"):
            req_color = getattr(_s, _REQUIRES_COLOR_NAME.get(feat["requires"], "AMBER"))
            req_lbl = QLabel(feat["requires"])
            req_lbl.setStyleSheet(
                f"font-size:9px; font-weight:bold; color:{req_color};"
                f" background:transparent; border:1px solid {req_color};"
                f" border-radius:3px; padding:0 4px;"
            )
            req_lbl.setToolTip(_s.safe_tooltip(_REQUIRES_TOOLTIP.get(
                feat["requires"], f"Requires: {feat['requires']}"
            )))
            name_row.addWidget(req_lbl)

        badge = feat.get("badge")
        if badge:
            until_str = feat.get("badge_until")
            badge_active = True
            if until_str:
                try:
                    badge_active = datetime.date.today() <= datetime.date.fromisoformat(until_str)
                except ValueError:
                    badge_active = False
            if badge_active:
                badge_color = _s.GREEN if badge == "new" else _s.AMBER
                badge_lbl = QLabel("New" if badge == "new" else "Updated")
                badge_lbl.setStyleSheet(
                    f"font-size:9px; font-weight:bold; color:{_s.WHITE};"
                    f" background:{badge_color}; border-radius:3px; padding:0 5px;"
                )
                name_row.addWidget(badge_lbl)

        if feat.get("page") and feat["page"] in self._visited_pages:
            used_lbl = QLabel("✓ Used")
            _s.themed_ss(used_lbl, "font-size:9px; font-weight:bold; color:{TEXT_MUTED};"
                " background:transparent; border:1px solid {BORDER};"
                " border-radius:3px; padding:0 5px;")
            name_row.addWidget(used_lbl)

        name_row.addStretch()
        text_col.addLayout(name_row)

        desc_lbl = QLabel(feat["desc"])
        desc_lbl.setWordWrap(True)
        _s.themed_ss(desc_lbl, "font-size:11px; color:{TEXT_SECONDARY}; background:transparent; border:none;")
        text_col.addWidget(desc_lbl)
        lay.addLayout(text_col, 1)

        if feat.get("page"):
            btn = QPushButton("Open →")
            btn.setFixedHeight(26)
            btn.setFixedWidth(72)
            _s.themed_ss(btn, "QPushButton {{ background:transparent; border:1px solid {ACCENT};"
                " color:{ACCENT}; border-radius:4px; font-size:11px; }}"
                "QPushButton:hover {{ background:{ACCENT}; color:{WHITE}; }}"
                "QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_PRIMARY}; }}")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            _page = feat["page"]
            btn.clicked.connect(lambda _=False, p=_page: self.navigate_to.emit(p))
            lay.addWidget(btn)

        return card

    def focus_search(self) -> None:
        self._search.clear()
        self._search.setFocus()

    def _apply_filter(self, text: str) -> None:
        q = text.strip().lower()
        if not q:
            self._render_features(_FEATURES)
            return
        filtered = [
            f for f in _FEATURES
            if q in f["name"].lower()
            or q in f["desc"].lower()
            or q in f.get("group", "").lower()
            or q in (f.get("page") or "").lower()
            or any(q in t.lower() for t in f.get("tags", []))
        ]
        self._render_features(filtered, show_recommended=False)
