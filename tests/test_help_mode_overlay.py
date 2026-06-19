"""Tests for ui.widgets.help_mode_overlay (Sprint 9, S9-5)."""
import pytest

try:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication, QLabel, QPushButton, QVBoxLayout, QWidget
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

pytestmark = pytest.mark.skipif(not _HAS_QT, reason="PyQt6 not available")


def _cleanup(*widgets):
    app = QApplication.instance()
    for w in widgets:
        try:
            w.deleteLater()
        except RuntimeError:
            pass  # already destroyed — safe to skip
    if app:
        for _ in range(3):
            app.processEvents()


@pytest.fixture
def page():
    QApplication.instance()
    w = QWidget()
    w.resize(300, 200)
    lay = QVBoxLayout(w)
    btn = QPushButton("Run", w)
    btn.setToolTip("Runs the scan.\nSecond line should be ignored.")
    lay.addWidget(btn)
    lbl = QLabel("No tooltip here", w)
    lay.addWidget(lbl)
    hidden_btn = QPushButton("Hidden", w)
    hidden_btn.setToolTip("Should never appear")
    hidden_btn.setVisible(False)
    lay.addWidget(hidden_btn)
    w.show()
    yield w
    _cleanup(w)


class TestHelpModeOverlay:
    def test_import(self):
        from ui.widgets.help_mode_overlay import HelpModeOverlay  # noqa: F401

    def test_creates_one_label_per_tooltip_widget(self, page):
        from ui.widgets.help_mode_overlay import HelpModeOverlay
        overlay = HelpModeOverlay(page)
        assert len(overlay._labels) == 1
        assert overlay._labels[0].text() == "Runs the scan."
        _cleanup(overlay)

    def test_skips_hidden_widgets(self, page):
        from ui.widgets.help_mode_overlay import HelpModeOverlay
        overlay = HelpModeOverlay(page)
        texts = [lbl.text() for lbl in overlay._labels]
        assert "Should never appear" not in texts
        _cleanup(overlay)

    def test_escape_closes_overlay(self, page):
        from ui.widgets.help_mode_overlay import HelpModeOverlay
        from PyQt6.QtGui import QKeyEvent
        from PyQt6.QtCore import QEvent
        overlay = HelpModeOverlay(page)
        closed = []
        overlay.closed.connect(lambda: closed.append(True))
        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
        overlay.keyPressEvent(event)
        assert closed == [True]

    def test_click_closes_overlay(self, page):
        from ui.widgets.help_mode_overlay import HelpModeOverlay
        from PyQt6.QtGui import QMouseEvent
        from PyQt6.QtCore import QEvent, QPointF
        overlay = HelpModeOverlay(page)
        closed = []
        overlay.closed.connect(lambda: closed.append(True))
        event = QMouseEvent(
            QEvent.Type.MouseButtonPress, QPointF(5, 5), Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
        )
        overlay.mousePressEvent(event)
        assert closed == [True]
