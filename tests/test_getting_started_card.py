"""
Tests for GettingStartedCard (H2+H3 sprint changes):
- Step order: scan → hw_deco → hw_zte → grade → arp → logger
- _checklist_states includes 'logger' key
- notify_hw_detected changes dot to amber for correct step
- refresh_checklist marks all 6 steps
"""
import pytest
import sys

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)


# ── Step order ────────────────────────────────────────────────────────────────

def test_step_order_scan_first():
    from ui.widgets.home_session_widgets import GettingStartedCard
    card = GettingStartedCard()
    keys = list(card._setup_check_lbls.keys())
    assert keys[0] == "scan", f"First step must be 'scan', got {keys[0]}"
    try:
        card.deleteLater()
    except RuntimeError:
        pass
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


def test_step_order_logger_last():
    from ui.widgets.home_session_widgets import GettingStartedCard
    card = GettingStartedCard()
    keys = list(card._setup_check_lbls.keys())
    assert keys[-1] == "logger", f"Last step must be 'logger', got {keys[-1]}"
    try:
        card.deleteLater()
    except RuntimeError:
        pass
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


def test_step_order_hw_after_scan():
    from ui.widgets.home_session_widgets import GettingStartedCard
    card = GettingStartedCard()
    keys = list(card._setup_check_lbls.keys())
    assert "hw_deco" in keys and "hw_zte" in keys
    assert keys.index("scan") < keys.index("hw_deco")
    assert keys.index("scan") < keys.index("hw_zte")
    try:
        card.deleteLater()
    except RuntimeError:
        pass
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


# ── _checklist_states ─────────────────────────────────────────────────────────

def test_checklist_states_includes_logger():
    from ui.widgets.home_session_widgets import GettingStartedCard
    card = GettingStartedCard()
    states = card._checklist_states(device_count=0)
    assert "logger" in states, "_checklist_states must include 'logger' key"
    assert isinstance(states["logger"], bool)
    try:
        card.deleteLater()
    except RuntimeError:
        pass
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


def test_checklist_states_all_keys():
    from ui.widgets.home_session_widgets import GettingStartedCard
    card = GettingStartedCard()
    states = card._checklist_states(device_count=0)
    expected = {"scan", "hw_deco", "hw_zte", "grade", "arp", "logger"}
    assert set(states.keys()) == expected
    try:
        card.deleteLater()
    except RuntimeError:
        pass
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


# ── notify_hw_detected ────────────────────────────────────────────────────────

def test_notify_hw_detected_modem_changes_zte_dot():
    from ui.widgets.home_session_widgets import GettingStartedCard
    card = GettingStartedCard()
    card.notify_hw_detected("modem")
    chk = card._setup_check_lbls.get("hw_zte")
    assert chk is not None
    assert chk.text() == "◉", f"Expected amber dot '◉', got '{chk.text()}'"
    try:
        card.deleteLater()
    except RuntimeError:
        pass
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


def test_notify_hw_detected_router_changes_deco_dot():
    from ui.widgets.home_session_widgets import GettingStartedCard
    card = GettingStartedCard()
    card.notify_hw_detected("router")
    chk = card._setup_check_lbls.get("hw_deco")
    assert chk is not None
    assert chk.text() == "◉", f"Expected amber dot '◉', got '{chk.text()}'"
    try:
        card.deleteLater()
    except RuntimeError:
        pass
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


def test_notify_hw_detected_unknown_type_no_crash():
    from ui.widgets.home_session_widgets import GettingStartedCard
    card = GettingStartedCard()
    card.notify_hw_detected("unknown_type")  # must not raise
    try:
        card.deleteLater()
    except RuntimeError:
        pass
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


# ── FreshnessStrip pills ──────────────────────────────────────────────────────

def test_freshness_strip_pills_have_navigate_to_signal():
    from ui.widgets.home_session_widgets import FreshnessStrip
    strip = FreshnessStrip()
    assert hasattr(strip, "navigate_to"), "FreshnessStrip must have navigate_to signal"
    try:
        strip.deleteLater()
    except RuntimeError:
        pass
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


def test_freshness_strip_pills_are_buttons():
    from PyQt6.QtWidgets import QPushButton
    from ui.widgets.home_session_widgets import FreshnessStrip
    strip = FreshnessStrip()
    assert isinstance(strip._fs_pill_arp, QPushButton)
    assert isinstance(strip._fs_pill_log, QPushButton)
    try:
        strip.deleteLater()
    except RuntimeError:
        pass
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()
