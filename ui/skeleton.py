"""
Skeleton loading state widget — animated placeholder for async data loading.

Usage:
    skeleton = SkeletonRow(rows=5)
    layout.addWidget(skeleton)
    # ... worker fires and loads data ...
    layout.removeWidget(skeleton)
    skeleton.deleteLater()
"""
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QFrame, QVBoxLayout, QWidget

from ui.styles import BORDER, BORDER_LITE


class SkeletonRow(QWidget):
    """
    Animated skeleton loading widget showing N shimmer rows.
    
    Each row is a fixed-height gray QFrame that pulses between BORDER and BORDER_LITE
    every 600ms, creating a shimmer effect while async workers load data.
    """

    def __init__(self, rows: int = 5, row_height: int = 16, parent=None):
        super().__init__(parent)
        self.setObjectName("skeletonRow")
        
        self._row_height = row_height
        self._frames = []
        self._state = False  # False = BORDER, True = BORDER_LITE
        
        # Build the layout with N animated frames
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        
        for _ in range(rows):
            frame = QFrame()
            frame.setFixedHeight(row_height)
            frame.setStyleSheet(f"background:{BORDER};border:none;")
            layout.addWidget(frame)
            self._frames.append(frame)
        
        # Animation timer: toggle every 600ms
        self._timer = QTimer(self)
        self._timer.setInterval(600)
        self._timer.timeout.connect(self._animate)
        self._timer.start()
    
    def _animate(self):
        """Toggle all frames between BORDER and BORDER_LITE."""
        self._state = not self._state
        color = BORDER_LITE if self._state else BORDER
        for frame in self._frames:
            frame.setStyleSheet(f"background:{color};border:none;")
    
    def cleanup(self):
        """Explicitly stop the timer (called before deleteLater)."""
        self._timer.stop()
