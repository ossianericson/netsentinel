"""Command palette — Ctrl+K fuzzy launcher for pages and actions."""

from PyQt6.QtCore import Qt, QEvent, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QApplication, QDialog, QLineEdit, QListWidget, QListWidgetItem, QStyle,
    QStyledItemDelegate, QVBoxLayout, QWidget,
)

from ui.styles import ACCENT, BG_CARD, BG_HOVER, BORDER, TEXT_PRIMARY, TEXT_SECONDARY, WHITE


class _ShortcutDelegate(QStyledItemDelegate):
    """Draws keyboard shortcut text right-aligned on palette items that have one."""

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        shortcut = index.data(Qt.ItemDataRole.UserRole + 1)
        if shortcut:
            painter.save()
            is_selected = bool(option.state & QStyle.StateFlag.State_Selected)
            painter.setPen(QColor(WHITE if is_selected else TEXT_SECONDARY))
            f = QFont()
            f.setPointSize(9)
            painter.setFont(f)
            painter.drawText(
                option.rect.adjusted(0, 0, -14, 0),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                shortcut,
            )
            painter.restore()


class CommandPalette(QDialog):
    page_requested   = pyqtSignal(str)   # emits page label
    action_requested = pyqtSignal(str)   # emits action key or "__device__IP" or "__alert__ID"

    def __init__(self, items: list, parent=None):
        """items: list of {'icon': str, 'label': str, 'kind': 'page'|'action'}"""
        super().__init__(parent, Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowModality(Qt.WindowModality.NonModal)
        self._all_items = items
        self._data_items: list[dict] = []  # pre-loaded device + alert items
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
        self._search.setPlaceholderText("  Search pages, devices, actions… (Ctrl+K)")
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
        self._list.setItemDelegate(_ShortcutDelegate(self._list))
        self._list.itemClicked.connect(self._activate)
        wl.addWidget(self._list)

        outer.addWidget(wrap)
        self._populate(self._all_items)

    def _populate(self, items: list, show_tip: bool = False):
        self._list.clear()
        first_selectable = None
        for it in items:
            icon  = it.get("icon", "")
            label = it.get("label", "")
            kind  = it.get("kind", "page")
            if kind == "separator":
                row = QListWidgetItem(f"  {label.upper()}")
                row.setFlags(Qt.ItemFlag.NoItemFlags)
                row.setForeground(QColor(TEXT_SECONDARY))
                f = QFont()
                f.setPointSize(8)
                f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.2)
                row.setFont(f)
            else:
                row = QListWidgetItem(f"  {icon}  {label}")
                row.setData(Qt.ItemDataRole.UserRole, it)
                shortcut = it.get("shortcut", "")
                if shortcut:
                    row.setData(Qt.ItemDataRole.UserRole + 1, shortcut)
                if kind in ("action", "recent"):
                    row.setForeground(QColor(TEXT_SECONDARY))
                if first_selectable is None:
                    first_selectable = self._list.count()
            self._list.addItem(row)
        if show_tip:
            _tip = QListWidgetItem("  💡  Tip: type an IP address to find a device")
            _tip.setFlags(Qt.ItemFlag.NoItemFlags)
            _f = QFont()
            _f.setPointSize(9)
            _f.setItalic(True)
            _tip.setFont(_f)
            _tip.setForeground(QColor(TEXT_SECONDARY))
            self._list.addItem(_tip)
        if first_selectable is not None:
            self._list.setCurrentRow(first_selectable)

    def load_recent_data(self, store) -> None:
        """Pre-load known devices + recent alerts from MetricStore."""
        self._data_items = []
        if store is None:
            return
        try:
            import time as _t
            devices = list(store.get_known_devices().values())[:10]
            for d in devices:
                ip = d.ip or ""
                mac = d.mac or ""
                vendor = d.vendor or ""
                name = d.custom_name or d.hostname or ""
                label = f"Device — {ip}" + (f" · {name}" if name else "") + (f" · {vendor}" if vendor else "")
                self._data_items.append({
                    "icon": "💻", "label": label, "kind": "device",
                    "ip": ip, "mac": mac, "search": f"{ip} {mac} {vendor} {name}".lower(),
                })
            alerts = store.get_recent_alerts(hours=72)[:5]
            for a in alerts:
                ts = a.get("ts", 0)
                ago_s = _t.time() - ts
                if ago_s < 3600:
                    ago = f"{int(ago_s // 60)}m ago"
                elif ago_s < 86400:
                    ago = f"{int(ago_s // 3600)}h ago"
                else:
                    ago = f"{int(ago_s // 86400)}d ago"
                rule = a.get("rule_name", a.get("rule", "Alert"))
                host = a.get("host", "")
                label = f"Alert — {rule}" + (f" · {host}" if host else "") + f" · {ago}"
                self._data_items.append({
                    "icon": "⚠", "label": label, "kind": "alert",
                    "alert": a, "search": f"{rule} {host}".lower(),
                })
        except Exception:
            pass

        if self._data_items:
            all_with_data = list(self._all_items) + [
                {"kind": "separator", "label": "Recent data"},
            ] + self._data_items
        else:
            all_with_data = self._all_items
        self._combined_items = all_with_data

    def _filter(self, text: str):
        text = text.strip()
        source = getattr(self, "_combined_items", self._all_items)
        if not text:
            self._populate(source, show_tip=True)
            return
        q = text.lower()
        matched = []
        for it in source:
            if it.get("kind") == "separator":
                continue
            search_in = it.get("search") or it["label"].lower()
            if q in search_in or q in it["label"].lower():
                matched.append(it)
        self._populate(matched)

    def _activate(self, item: QListWidgetItem):
        data = item.data(Qt.ItemDataRole.UserRole)
        if data is None:
            return
        kind = data.get("kind", "page")
        if kind == "page":
            self.page_requested.emit(data.get("real_label") or data["label"])
        elif kind == "device":
            self.action_requested.emit(f"__device__{data.get('ip') or data.get('mac', '')}")
        elif kind == "alert":
            import json as _json
            self.action_requested.emit(f"__alert__{_json.dumps(data.get('alert', {}))}")
        elif kind == "recent":
            self.action_requested.emit(f"__recent__{data.get('id', data['label'])}")
        else:
            self.action_requested.emit(data["label"])
        self.accept()

    def showEvent(self, event):
        super().showEvent(event)
        QApplication.instance().installEventFilter(self)
        self._search.setFocus()

    def hideEvent(self, event):
        QApplication.instance().removeEventFilter(self)
        super().hideEvent(event)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.MouseButtonPress:
            # Close if the click landed outside our own geometry.
            # This handles both the app-level filter (installed in showEvent for
            # non-modal show()) and the search-box filter (legacy).
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
        self._populate(getattr(self, "_combined_items", self._all_items), show_tip=True)
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
