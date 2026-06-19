"""
Tests for GettingStartedCard (H2+H3 sprint changes):
- Step order: scan → hw_setup → grade → arp → logger
- _checklist_states includes 'logger' key
- notify_hw_detected changes dot to amber for hw_setup step
- refresh_checklist marks all 5 steps
"""
import pytest

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)


# ---------------------------------------------------------------------------
# RULE-WIN4: keep created widgets alive until deleteLater() runs.
# Storing every widget here prevents premature C++ destruction; the autouse
# fixture below drains the list via sendPostedEvents(DeferredDelete) +
# 3× processEvents() after every test.
# ---------------------------------------------------------------------------
_created_widgets: list = []


@pytest.fixture(autouse=True)
def _cleanup_widgets():
    yield
    app = QApplication.instance()
    for w in _created_widgets:
        try:
            w.deleteLater()
        except RuntimeError:
            pass  # already destroyed — safe to skip
    # processEvents() alone does NOT process DeferredDelete in Qt6; call
    # sendPostedEvents(DeferredDelete) explicitly so widgets are actually freed.
    if app:
        try:
            from PyQt6.QtCore import QCoreApplication, QEvent
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
        except Exception:
            pass  # non-fatal — best-effort cleanup
        for _ in range(3):
            app.processEvents()
    # Now release Python references — C++ objects already deleted by Qt above
    _created_widgets.clear()


# ── Step order ────────────────────────────────────────────────────────────────

def test_step_order_scan_first():
    from ui.widgets.home_session_widgets import GettingStartedCard
    card = GettingStartedCard()
    _created_widgets.append(card)
    keys = list(card._setup_check_lbls.keys())
    assert keys[0] == "scan", f"First step must be 'scan', got {keys[0]}"


def test_step_order_logger_last():
    from ui.widgets.home_session_widgets import GettingStartedCard
    card = GettingStartedCard()
    _created_widgets.append(card)
    keys = list(card._setup_check_lbls.keys())
    assert keys[-1] == "logger", f"Last step must be 'logger', got {keys[-1]}"


def test_step_order_hw_after_scan():
    from ui.widgets.home_session_widgets import GettingStartedCard
    card = GettingStartedCard()
    _created_widgets.append(card)
    keys = list(card._setup_check_lbls.keys())
    assert "hw_setup" in keys
    assert keys.index("scan") < keys.index("hw_setup")


# ── _checklist_states ─────────────────────────────────────────────────────────

def test_checklist_states_includes_logger():
    from ui.widgets.home_session_widgets import GettingStartedCard
    card = GettingStartedCard()
    _created_widgets.append(card)
    states = card._checklist_states(device_count=0)
    assert "logger" in states, "_checklist_states must include 'logger' key"
    assert isinstance(states["logger"], bool)


def test_checklist_states_all_keys():
    from ui.widgets.home_session_widgets import GettingStartedCard
    card = GettingStartedCard()
    _created_widgets.append(card)
    states = card._checklist_states(device_count=0)
    expected = {"scan", "hw_setup", "grade", "arp", "logger", "npcap"}
    assert set(states.keys()) == expected


# ── notify_hw_detected ────────────────────────────────────────────────────────

def test_notify_hw_detected_modem_changes_hw_setup_dot():
    from ui.widgets.home_session_widgets import GettingStartedCard
    card = GettingStartedCard()
    _created_widgets.append(card)
    # Force hw_setup=False so notify_hw_detected reaches the amber-dot path regardless of
    # whether the developer's machine has real hardware/instances in QSettings.
    _empty = {"scan": False, "hw_setup": False, "grade": False, "arp": False, "logger": False}
    card._checklist_states = lambda **kw: _empty
    card.notify_hw_detected("modem")
    chk = card._setup_check_lbls.get("hw_setup")
    assert chk is not None
    assert chk.text() == "◉", f"Expected amber dot '◉', got '{chk.text()}'"


def test_notify_hw_detected_router_changes_hw_setup_dot():
    from ui.widgets.home_session_widgets import GettingStartedCard
    card = GettingStartedCard()
    _created_widgets.append(card)
    _empty = {"scan": False, "hw_setup": False, "grade": False, "arp": False, "logger": False}
    card._checklist_states = lambda **kw: _empty
    card.notify_hw_detected("router")
    chk = card._setup_check_lbls.get("hw_setup")
    assert chk is not None
    assert chk.text() == "◉", f"Expected amber dot '◉', got '{chk.text()}'"


def test_notify_hw_detected_unknown_type_no_crash():
    from ui.widgets.home_session_widgets import GettingStartedCard
    card = GettingStartedCard()
    _created_widgets.append(card)
    card.notify_hw_detected("unknown_type")  # must not raise


# ── FreshnessStrip pills ──────────────────────────────────────────────────────

def test_freshness_strip_pills_have_navigate_to_signal():
    from ui.widgets.home_session_widgets import FreshnessStrip
    strip = FreshnessStrip()
    _created_widgets.append(strip)
    assert hasattr(strip, "navigate_to"), "FreshnessStrip must have navigate_to signal"


def test_freshness_strip_pills_are_buttons():
    from PyQt6.QtWidgets import QPushButton
    from ui.widgets.home_session_widgets import FreshnessStrip
    strip = FreshnessStrip()
    _created_widgets.append(strip)
    assert isinstance(strip._fs_pill_arp, QPushButton)
    assert isinstance(strip._fs_pill_log, QPushButton)


# ── Sprint H8 additions ───────────────────────────────────────────────────────

def test_getting_started_card_has_completion_done_signal():
    """completion_done signal must be declared on GettingStartedCard."""
    from ui.widgets.home_session_widgets import GettingStartedCard
    card = GettingStartedCard()
    _created_widgets.append(card)
    assert hasattr(card, "completion_done"), "completion_done signal must exist"


def test_getting_started_card_completion_done_is_connectable():
    """completion_done signal must be connectable without error."""
    from ui.widgets.home_session_widgets import GettingStartedCard
    card = GettingStartedCard()
    _created_widgets.append(card)
    received = []
    card.completion_done.connect(lambda: received.append(True))
    card.completion_done.emit()
    assert received == [True], "completion_done signal must be emittable"


def test_freshness_strip_has_update_logger_tooltip():
    """FreshnessStrip must have update_logger_tooltip method."""
    from ui.widgets.home_session_widgets import FreshnessStrip
    strip = FreshnessStrip()
    _created_widgets.append(strip)
    assert hasattr(strip, "update_logger_tooltip"), "update_logger_tooltip method must exist"
    strip.update_logger_tooltip("5 min ago", "14:47", "23 ms")  # must not raise


def test_freshness_strip_update_logger_tooltip_when_active():
    """update_logger_tooltip must set tooltip text when logger pill is active."""
    from ui.widgets.home_session_widgets import FreshnessStrip
    strip = FreshnessStrip()
    _created_widgets.append(strip)
    strip.update_freshness(logger=True)
    strip.update_logger_tooltip(since_str="10 min ago", rtt_str="22 ms")
    tip = strip._fs_pill_log.toolTip()
    assert "10 min ago" in tip, f"Expected 'since' text in tooltip, got: {tip!r}"


def test_freshness_strip_update_logger_tooltip_noop_when_inactive():
    """update_logger_tooltip must not change tooltip when logger is off."""
    from ui.widgets.home_session_widgets import FreshnessStrip
    strip = FreshnessStrip()
    _created_widgets.append(strip)
    strip.update_freshness(logger=False)
    original_tip = strip._fs_pill_log.toolTip()
    strip.update_logger_tooltip(since_str="10 min ago")
    assert strip._fs_pill_log.toolTip() == original_tip
