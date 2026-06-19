"""EmptyStateOverlay — zero-boilerplate empty-table placeholder.

Usage:
    EmptyStateOverlay(table, icon="◎", title="No devices found",
                      subtitle="Click Scan to begin")

The overlay positions itself over the table viewport and shows/hides
automatically as rows are added or removed.  No layout restructuring needed.
"""

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ui.styles import BORDER, TEXT_MUTED, TEXT_SECONDARY


class EmptyStateOverlay(QWidget):
    def __init__(self, table, icon: str = "◎", title: str = "No data",
                 subtitle: str = "", parent=None):
        super().__init__(table.viewport())
        self._table = table

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._icon_lbl = QLabel(icon)
        self._icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon_lbl.setStyleSheet(
            f"color:{BORDER}; font-size:40px; background:transparent; border:none;"
        )

        self._title_lbl = QLabel(title)
        self._title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title_lbl.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:13px; font-weight:600;"
            "background:transparent; border:none;"
        )

        lay.addWidget(self._icon_lbl)
        lay.addWidget(self._title_lbl)

        if subtitle:
            sub = QLabel(subtitle)
            sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sub.setStyleSheet(
                f"color:{TEXT_MUTED}; font-size:11px;"
                "background:transparent; border:none;"
            )
            lay.addWidget(sub)

        # Watch viewport resize so overlay always fills it
        table.viewport().installEventFilter(self)

        # Watch model changes
        model = table.model()
        if model:
            model.rowsInserted.connect(self._refresh)
            model.rowsRemoved.connect(self._refresh)
            model.modelReset.connect(self._refresh)

        self._refresh()

    def eventFilter(self, obj, event):
        if obj is self._table.viewport() and event.type() == QEvent.Type.Resize:
            self.resize(obj.size())
        return False

    def _refresh(self):
        empty = self._table.rowCount() == 0
        self.setVisible(empty)
        if empty:
            self.resize(self._table.viewport().size())
            self.raise_()
