"""
Matrix Rain — green falling-character overlay for NetSentinel.

Triggered by:
  - Ctrl+Shift+M keyboard shortcut in the main window
  - --matrix CLI flag (app.py passes this to MainWindow)

Dismissed by:
  - Pressing Escape
  - Clicking anywhere on the overlay
  - Calling .stop() programmatically

Characters: mix of katakana (ｦ-ﾟ) and ASCII digits/punctuation.
Runs at ~20 fps using a QTimer.  Transparent background so it sits on
top of the main window contents without replacing them.
"""

from __future__ import annotations

import random
from typing import List

from PyQt6.QtCore import Qt, QTimer, QRect, QRectF
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QKeyEvent, QMouseEvent
from PyQt6.QtWidgets import QWidget


# ── Character pool ────────────────────────────────────────────────────────────

_KATAKANA  = [chr(c) for c in range(0xFF66, 0xFF9F)]   # ｦ–ﾟ (half-width katakana)
_ASCII     = list("0123456789ABCDEF!@#$%^&*<>?/|\\")
_CHARS     = _KATAKANA * 3 + _ASCII                    # katakana-heavy mix


# ── Column state ─────────────────────────────────────────────────────────────

class _Column:
    """Represents one vertical column of falling characters."""

    def __init__(self, x: int, height: int, char_h: int):
        self.x       = x
        self.char_h  = char_h
        self.max_rows = height // char_h + 2
        self.head    = random.randint(-self.max_rows, 0)   # row of the bright head
        self.speed   = random.randint(1, 3)               # rows per tick
        self.chars: List[str] = [
            random.choice(_CHARS) for _ in range(self.max_rows)
        ]
        self.length  = random.randint(8, 28)              # visible trail length

    def tick(self):
        self.head += self.speed
        if self.head - self.length > self.max_rows:
            self.head   = random.randint(-self.max_rows // 2, -2)
            self.speed  = random.randint(1, 3)
            self.length = random.randint(8, 28)
            # Scramble a few characters
            for i in random.sample(range(self.max_rows), min(4, self.max_rows)):
                self.chars[i] = random.choice(_CHARS)

    def visible_rows(self):
        """Yield (row_index, alpha_factor 0–1, is_head) for visible rows."""
        for row in range(max(0, self.head - self.length), self.head + 1):
            if 0 <= row < self.max_rows:
                dist_from_head = self.head - row
                # alpha falls off linearly from head to tail
                alpha = max(0.0, 1.0 - dist_from_head / max(self.length, 1))
                is_head = (row == self.head)
                yield row, alpha, is_head


# ── Widget ────────────────────────────────────────────────────────────────────

class MatrixRainWidget(QWidget):
    """
    Full-overlay matrix rain.  Parent it to the main window and call show().
    It resizes itself to match the parent whenever the parent resizes.
    """

    CHAR_W = 14
    CHAR_H = 18
    FPS    = 20

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)

        self._font = QFont("Courier New", 11, QFont.Weight.Bold)
        self._columns: List[_Column] = []

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

        self._resize_to_parent()
        self.hide()  # stay hidden until explicitly started via toggle() / Ctrl+Shift+M

    # ── Public ────────────────────────────────────────────────────────────────

    def start(self):
        self._resize_to_parent()
        self._build_columns()
        self.show()
        self.raise_()
        self._timer.start(1000 // self.FPS)

    def stop(self):
        self._timer.stop()
        self.hide()

    def toggle(self):
        if self._timer.isActive():
            self.stop()
        else:
            self.start()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _resize_to_parent(self):
        if self.parent():
            self.setGeometry(self.parent().rect())  # type: ignore[union-attr]

    def _build_columns(self):
        w = self.width()
        h = self.height()
        n_cols = max(1, w // self.CHAR_W)
        self._columns = [
            _Column(x=i * self.CHAR_W, height=h, char_h=self.CHAR_H)
            for i in range(n_cols)
        ]

    def _tick(self):
        for col in self._columns:
            col.tick()
        self.update()

    # ── Events ────────────────────────────────────────────────────────────────

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._build_columns()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape:
            self.stop()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        self.stop()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setFont(self._font)

        # Semi-transparent black background — gives the "fade" trail effect
        painter.fillRect(self.rect(), QColor(0, 0, 0, 160))

        for col in self._columns:
            char_x = col.x
            for row, alpha, is_head in col.visible_rows():
                char_y = row * self.CHAR_H
                ch = col.chars[row % len(col.chars)]

                if is_head:
                    # Bright white/cyan head character
                    color = QColor(200, 255, 220, 255)
                else:
                    # Green trail — brighter = closer to head
                    green = int(80 + 175 * alpha)
                    color = QColor(0, green, int(40 * alpha), int(220 * alpha))

                painter.setPen(QPen(color))
                painter.drawText(
                    QRect(char_x, char_y, self.CHAR_W, self.CHAR_H),
                    Qt.AlignmentFlag.AlignCenter,
                    ch,
                )

        painter.end()
