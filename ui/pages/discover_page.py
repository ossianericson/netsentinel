"""
Feature Guide page — searchable index of every NetSentinel feature.

Gives users a single place to discover what the app can do, understand each
feature in one sentence, and navigate directly to it.  Grouped by theme;
filterable by name, description, group, page label, or synonym tag.
"""
from __future__ import annotations

import datetime

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from ui.styles import (
    ACCENT, AMBER, BG_CARD, BG_DARK,
    BG_HOVER, BORDER, CARD_RADIUS, CRITICAL,
    GREEN, RED, TEXT_MUTED, TEXT_PRIMARY,
    TEXT_SECONDARY, WHITE,
)

from ui.pages.discover_data import _FEATURES, _GROUPS_ORDER  # noqa: F401



_REQUIRES_COLOR = {
    "Npcap": AMBER,
    "admin": RED,
}


# ── Widget ─────────────────────────────────────────────────────────────────────

class FeatureGuidePage(QWidget):
    """Searchable index of every NetSentinel feature."""

    navigate_to = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Page header
        hdr = QLabel("Feature Guide")
        hdr.setFixedHeight(32)
        hdr.setStyleSheet(
            f"QLabel {{ background:{BG_DARK}; font-size:15px; font-weight:bold;"
            f" color:{TEXT_PRIMARY}; padding:0 16px; border-bottom:1px solid {BORDER}; }}"
        )
        root.addWidget(hdr)

        # Search bar
        search_row = QHBoxLayout()
        search_row.setContentsMargins(16, 10, 16, 6)
        search_row.setSpacing(8)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search features, synonyms, page names…")
        self._search.setStyleSheet(
            f"QLineEdit {{ border:1px solid {BORDER}; border-radius:4px;"
            f" padding:4px 10px; font-size:12px; background:{BG_CARD}; color:{TEXT_PRIMARY}; }}"
        )
        self._search.textChanged.connect(self._apply_filter)
        search_row.addWidget(self._search)

        sub = QLabel(f"{len(_FEATURES)} features")
        sub.setStyleSheet(f"font-size:11px; color:{TEXT_MUTED}; background:transparent;")
        search_row.addWidget(sub)
        root.addLayout(search_row)

        # Scrollable body
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(f"QScrollArea {{ background:{BG_DARK}; border:none; }}")

        self._body = QWidget()
        self._body.setStyleSheet(f"background:{BG_DARK};")
        self._body_lay = QVBoxLayout(self._body)
        self._body_lay.setContentsMargins(16, 8, 16, 16)
        self._body_lay.setSpacing(4)

        scroll.setWidget(self._body)
        root.addWidget(scroll, 1)

        self._render_features(_FEATURES)

    def _render_features(self, features: list[dict]) -> None:
        while self._body_lay.count():
            item = self._body_lay.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        current_group = None
        for feat in features:
            g = feat["group"]
            if g != current_group:
                current_group = g
                grp_lbl = QLabel(g.upper())
                grp_lbl.setStyleSheet(
                    f"font-size:10px; font-weight:bold; color:{TEXT_SECONDARY};"
                    f" background:transparent; letter-spacing:1px; padding-top:10px;"
                )
                self._body_lay.addWidget(grp_lbl)

            card = self._make_card(feat)
            self._body_lay.addWidget(card)

        if not features:
            empty = QLabel("No features match your search.")
            empty.setStyleSheet(f"font-size:12px; color:{TEXT_MUTED}; background:transparent;")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._body_lay.addWidget(empty)

        self._body_lay.addStretch()

    def _make_card(self, feat: dict) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER};"
            f" border-radius:{CARD_RADIUS}; }}"
        )
        lay = QHBoxLayout(card)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(10)

        icon_lbl = QLabel(feat["icon"])
        icon_lbl.setFixedWidth(18)
        icon_lbl.setStyleSheet(
            f"font-size:14px; color:{TEXT_PRIMARY}; background:transparent; border:none;"
        )
        lay.addWidget(icon_lbl)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        text_col.setContentsMargins(0, 0, 0, 0)

        name_row = QHBoxLayout()
        name_row.setSpacing(6)
        name_lbl = QLabel(feat["name"])
        name_lbl.setStyleSheet(
            f"font-size:12px; font-weight:bold; color:{TEXT_PRIMARY};"
            " background:transparent; border:none;"
        )
        name_row.addWidget(name_lbl)

        if feat.get("requires"):
            req_color = _REQUIRES_COLOR.get(feat["requires"], AMBER)
            req_lbl = QLabel(feat["requires"])
            req_lbl.setStyleSheet(
                f"font-size:9px; font-weight:bold; color:{req_color};"
                f" background:transparent; border:1px solid {req_color};"
                f" border-radius:3px; padding:0 4px;"
            )
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
                badge_color = GREEN if badge == "new" else AMBER
                badge_lbl = QLabel("New" if badge == "new" else "Updated")
                badge_lbl.setStyleSheet(
                    f"font-size:9px; font-weight:bold; color:{WHITE};"
                    f" background:{badge_color}; border-radius:3px; padding:0 5px;"
                )
                name_row.addWidget(badge_lbl)

        name_row.addStretch()
        text_col.addLayout(name_row)

        desc_lbl = QLabel(feat["desc"])
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent; border:none;"
        )
        text_col.addWidget(desc_lbl)
        lay.addLayout(text_col, 1)

        if feat.get("page"):
            btn = QPushButton("Open →")
            btn.setFixedHeight(26)
            btn.setFixedWidth(72)
            btn.setStyleSheet(
                f"QPushButton {{ background:transparent; border:1px solid {ACCENT};"
                f" color:{ACCENT}; border-radius:4px; font-size:11px; }}"
                f"QPushButton:hover {{ background:{ACCENT}; color:{WHITE}; }}"
                f"QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_PRIMARY}; }}"
            )
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
        self._render_features(filtered)
