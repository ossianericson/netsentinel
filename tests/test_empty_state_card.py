"""Tests for ui.widgets.empty_state_card (Sprint A2)."""
import pytest

try:
    from PyQt6.QtWidgets import QApplication, QLabel, QPushButton
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

pytestmark = pytest.mark.skipif(not _HAS_QT, reason="PyQt6 not available")


# ── Import test ────────────────────────────────────────────────────────────────

def test_import():
    from ui.widgets.empty_state_card import EmptyStateCard  # noqa: F401


# ── Construction ───────────────────────────────────────────────────────────────

@pytest.fixture
def card():
    from ui.widgets.empty_state_card import EmptyStateCard
    app = QApplication.instance()
    w = EmptyStateCard(
        icon="◆",
        title="Test Page",
        what_it_shows="Shows every device on your network.",
        why_it_matters="You can't secure what you don't know about.",
        btn_label="Run Scan",
    )
    yield w
    try:
        w.deleteLater()
    except RuntimeError:
        pass  # skip test if PyQt6 unavailable
    if app:
        for _ in range(3):
            app.processEvents()


def test_card_has_correct_signals(card):
    from ui.widgets.empty_state_card import EmptyStateCard
    assert hasattr(EmptyStateCard, "clicked")


def test_card_button_emits_clicked(card):
    clicked_count = []
    card.clicked.connect(lambda: clicked_count.append(1))

    # Find the QPushButton child and click it
    btn = card.findChild(QPushButton)
    assert btn is not None, "EmptyStateCard must contain a QPushButton"
    btn.click()
    assert clicked_count == [1], "Clicking the CTA button must emit clicked"


def test_card_shows_correct_title(card):
    labels = card.findChildren(QLabel)
    texts = [lbl.text() for lbl in labels]
    assert any("Test Page" in t for t in texts), "Card must display the title"


def test_card_shows_what_it_shows(card):
    labels = card.findChildren(QLabel)
    texts = [lbl.text() for lbl in labels]
    assert any("Shows every device" in t for t in texts)


def test_card_shows_why_it_matters(card):
    labels = card.findChildren(QLabel)
    texts = [lbl.text() for lbl in labels]
    assert any("secure what you don't know" in t for t in texts)


def test_card_btn_label(card):
    btn = card.findChild(QPushButton)
    assert btn is not None
    assert btn.text() == "Run Scan"


# ── Connected signal passthrough ───────────────────────────────────────────────

def test_card_clicked_connects_to_external_slot():
    from ui.widgets.empty_state_card import EmptyStateCard
    app = QApplication.instance()
    received = []
    w = EmptyStateCard("◆", "T", "W", "Y", "Go")
    w.clicked.connect(lambda: received.append(True))
    btn = w.findChild(QPushButton)
    if btn:
        btn.click()
    assert received == [True]
    try:
        w.deleteLater()
    except RuntimeError:
        pass  # skip test if PyQt6 unavailable
    if app:
        for _ in range(3):
            app.processEvents()
