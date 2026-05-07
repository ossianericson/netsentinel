"""Command palette — Ctrl+K fuzzy launcher for pages and actions."""

from PyQt6.QtCore import Qt, QEvent, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication, QDialog, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout, QWidget,
)

from ui.styles import ACCENT, BG_CARD, BG_HOVER, BORDER, TEXT_PRIMARY, TEXT_SECONDARY, WHITE


class CommandPalette(QDialog):
    page_requested   = pyqtSignal(str)  # emits page label
    action_requested = pyqtSignal(str)  # emits action key

    def __init__(self, items: list, parent=None):
        """items: list of {'icon': str, 'label': str, 'kind': 'page'|'action'}"""
        super().__init__(parent, Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._all_items = items
        self._build()

    def _build(self):
        self.setMinimumWidth(500)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        wrap = QWidget()
        wrap.setObjectName("paletteWrap")
        wrap.setStyleSheet(
            f"QWidget#paletteWrap {{"
            f"  background:{BG_CARD};"
            f"  border:1px solid {ACCENT};"
            f"  border-radius:8px;"
            f"}}"
        )
        wl = QVBoxLayout(wrap)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.setSpacing(0)

        self._search = QLineEdit()
        self._search.setPlaceholderText("  Go to page or run action…")
        self._search.setFixedHeight(42)
        self._search.setStyleSheet(
            f"QLineEdit {{"
            f"  background:{BG_CARD}; color:{TEXT_PRIMARY};"
            f"  border:none; border-bottom:1px solid {BORDER};"
            f"  padding:0 14px; font-size:14px;"
            f"  border-top-left-radius:8px; border-top-right-radius:8px;"
            f"}}"
        )
        self._search.textChanged.connect(self._filter)
        self._search.installEventFilter(self)
        wl.addWidget(self._search)

        self._list = QListWidget()
        self._list.setFixedHeight(320)
        self._list.setStyleSheet(
            f"QListWidget {{"
            f"  background:{BG_CARD}; border:none; outline:none;"
            f"  border-bottom-left-radius:8px; border-bottom-right-radius:8px;"
            f"}}"
            f"QListWidget::item {{"
            f"  padding:9px 14px; color:{TEXT_PRIMARY}; background:{BG_CARD}; font-size:12px; border:none;"
            f"}}"
            f"QListWidget::item:selected {{"
            f"  background:{ACCENT}; color:{WHITE}; border-radius:0;"
            f"}}"
            f"QListWidget::item:hover:!selected {{ background:{BG_HOVER}; color:{TEXT_PRIMARY}; }}"
        )
        self._list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._list.itemClicked.connect(self._activate)
        wl.addWidget(self._list)

        outer.addWidget(wrap)
        self._populate(self._all_items)

    def _populate(self, items: list):
        self._list.clear()
        for it in items:
            icon  = it.get("icon", "")
            label = it.get("label", "")
            kind  = it.get("kind", "page")
            row   = QListWidgetItem(f"  {icon}  {label}")
            row.setData(Qt.ItemDataRole.UserRole, it)
            if kind == "action":
                from PyQt6.QtGui import QColor
                row.setForeground(QColor(TEXT_SECONDARY))
            self._list.addItem(row)
        if self._list.count():
            self._list.setCurrentRow(0)

    def _filter(self, text: str):
        text = text.strip()
        if not text:
            self._populate(self._all_items)
            return
        matched = [it for it in self._all_items if text.lower() in it["label"].lower()]
        self._populate(matched)

    def _activate(self, item: QListWidgetItem):
        data = item.data(Qt.ItemDataRole.UserRole)
        if data["kind"] == "page":
            self.page_requested.emit(data["label"])
        else:
            self.action_requested.emit(data["label"])
        self.accept()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.MouseButtonPress:
            # Close if the click landed outside our own geometry
            if not self.geometry().contains(event.globalPosition().toPoint()):
                self.reject()
                return False
        if obj is self._search and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Escape:
                self.reject()
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                cur = self._list.currentItem()
                if cur:
                    self._activate(cur)
                return True
            if key == Qt.Key.Key_Down:
                self._list.setCurrentRow(min(self._list.currentRow() + 1, self._list.count() - 1))
                return True
            if key == Qt.Key.Key_Up:
                self._list.setCurrentRow(max(self._list.currentRow() - 1, 0))
                return True
        return False

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.reject()
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            cur = self._list.currentItem()
            if cur:
                self._activate(cur)
        elif key == Qt.Key.Key_Down:
            self._list.setCurrentRow(min(self._list.currentRow() + 1, self._list.count() - 1))
        elif key == Qt.Key.Key_Up:
            self._list.setCurrentRow(max(self._list.currentRow() - 1, 0))
        else:
            super().keyPressEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        self._search.clear()
        if self.parent():
            pw  = self.parent()
            geo = pw.frameGeometry()
            x   = geo.x() + (geo.width() - self.width()) // 2
            y   = geo.y() + geo.height() // 5
            self.move(x, y)
        self.activateWindow()
        self._search.setFocus()
        QApplication.instance().installEventFilter(self)

    def hideEvent(self, event):
        QApplication.instance().removeEventFilter(self)
        super().hideEvent(event)
