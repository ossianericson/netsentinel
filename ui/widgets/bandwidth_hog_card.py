"""
ui/widgets/bandwidth_hog_card.py — "Who's hogging bandwidth?" home page card (S5-4).

Receives top-host snapshots via on_bandwidth_update(payload) from
AppTrafficPage.top_host_changed. Shows an empty-state CTA until App Traffic
monitoring has been started at least once — this card never starts packet
capture itself (RULE 4: capture only runs in a worker the user explicitly
started).
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from ui import styles as _s


def _fmt_bytes(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f} MB"
    if n >= 1_000:
        return f"{n / 1_000:.1f} KB"
    return f"{n} B"


class BandwidthHogCard(QWidget):
    """Full-width home page card answering "who is using my bandwidth right now?"."""

    navigate_to = pyqtSignal(str)   # emitted when CTA is clicked

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._has_data = False
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setObjectName("bandwidthHogCard")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._frame = QFrame()
        self._frame.setObjectName("bandwidthHogFrame")
        _s.themed_ss(self._frame, "QFrame#bandwidthHogFrame {{ background:{BG_CARD};"
            " border:1px solid {BORDER}; border-radius:6px; }}")
        frame_lay = QHBoxLayout(self._frame)
        frame_lay.setContentsMargins(14, 10, 14, 10)
        frame_lay.setSpacing(12)

        self._icon_lbl = QLabel("◆")
        self._icon_lbl.setFixedWidth(28)
        self._icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _s.themed_ss(self._icon_lbl, "font-size:18px; font-weight:bold; color:{TEXT_MUTED};"
            " background:transparent; border:none;")

        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        self._headline_lbl = QLabel("Who's using my bandwidth right now?")
        _s.themed_ss(self._headline_lbl, "font-size:12px; font-weight:bold; color:{TEXT_PRIMARY};"
            " background:transparent; border:none;")
        self._headline_lbl.setWordWrap(True)

        self._sub_lbl = QLabel(
            "Start App Traffic monitoring to see a live answer here."
        )
        _s.themed_ss(self._sub_lbl, "font-size:11px; color:{TEXT_SECONDARY}; background:transparent; border:none;")
        self._sub_lbl.setWordWrap(True)

        text_col.addWidget(self._headline_lbl)
        text_col.addWidget(self._sub_lbl)

        self._cta_btn = QPushButton("Open App Traffic →")
        self._cta_btn.setFixedHeight(28)
        self._cta_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cta_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        _s.themed_ss(self._cta_btn, "QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
            " border-radius:4px; font-size:11px; padding:0 12px; }}"
            "QPushButton:hover {{ background:{ACCENT_LITE}; color:{WHITE}; }}"
            "QPushButton:pressed {{ background:{ACCENT_DARK}; color:{WHITE}; }}")
        self._cta_btn.clicked.connect(lambda: self.navigate_to.emit("App Traffic"))

        frame_lay.addWidget(self._icon_lbl)
        frame_lay.addLayout(text_col, 1)
        frame_lay.addWidget(self._cta_btn)

        outer.addWidget(self._frame)

    def on_bandwidth_update(self, payload: dict) -> None:
        """Called whenever AppTrafficPage emits a new top-host snapshot."""
        self._has_data = True
        label = payload.get("label", "A device")
        pct = float(payload.get("share_pct", 0.0))
        bytes_total = int(payload.get("bytes_total", 0))
        window_s = float(payload.get("window_s", 10.0))

        _s.themed_ss(self._icon_lbl, "font-size:18px; font-weight:bold; color:{ACCENT};"
            " background:transparent; border:none;")
        self._headline_lbl.setText(
            f"Right now: {label} is using {pct:.0f}% of your bandwidth"
        )
        self._sub_lbl.setText(
            f"{_fmt_bytes(bytes_total)} in the last {window_s:.0f} s"
        )
        self._cta_btn.setText("View Details →")
