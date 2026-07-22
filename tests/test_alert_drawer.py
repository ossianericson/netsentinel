"""Tests for ui.widgets.alert_drawer — contextual learn-more link wiring (Sprint 7, S7-3)."""
import time

import pytest

try:
    from PyQt6.QtWidgets import QApplication
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

pytestmark = pytest.mark.skipif(not _HAS_QT, reason="PyQt6 not available")


def _cleanup(widget):
    app = QApplication.instance()
    try:
        widget.deleteLater()
    except RuntimeError:
        pass  # already destroyed — safe to skip
    if app:
        for _ in range(3):
            app.processEvents()


@pytest.fixture
def drawer():
    from ui.widgets.alert_drawer import AlertDrawer
    QApplication.instance()
    d = AlertDrawer()
    yield d
    _cleanup(d)


def _alert(rule_name: str, message: str) -> dict:
    return {
        "id": 1,
        "severity": "WARNING",
        "rule_name": rule_name,
        "host": "192.168.1.10",
        "ts": int(time.time()),
        "message": message,
    }


class TestActionRowNoClipping:
    """Regression test for the action-row text-clipping bug: the drawer is a fixed
    320px frame, and up to 5 action buttons (Acknowledge, Snooze 1h, Network Logger,
    Fix this/Go to page, Troubleshoot) need to render — their combined width does
    not fit one row, so each button's rendered width must match its sizeHint (i.e.
    the layout wraps to multiple rows instead of clipping button text).
    """

    def _open_and_layout(self, drawer, alert):
        drawer.open(alert)
        drawer.setMaximumWidth(drawer.OPEN_WIDTH)
        drawer.resize(drawer.OPEN_WIDTH, 700)
        drawer.show()
        QApplication.instance().processEvents()

    def _assert_no_button_clipped(self, drawer):
        for btn in (
            drawer._ack_btn, drawer._snooze_btn, drawer._log_btn,
            drawer._fix_btn, drawer._go_btn, drawer._troubleshoot_btn,
        ):
            if not btn.isVisible():
                continue
            assert btn.width() >= btn.sizeHint().width(), (
                f"{btn.text()!r} rendered at width={btn.width()} but needs "
                f"{btn.sizeHint().width()} — text is being clipped"
            )

    def test_fix_button_variant_not_clipped(self, drawer):
        # PORT_SCAN has both a mapped page and fix text -> Fix this button shown
        self._open_and_layout(drawer, _alert("PORT_SCAN", "Unexpected open port"))
        assert drawer._fix_btn.isVisible()
        assert not drawer._go_btn.isVisible()
        self._assert_no_button_clipped(drawer)

    def test_go_to_page_variant_not_clipped(self, drawer):
        # RATE_SPIKE maps to a page but has no fix text -> Go to page button shown
        self._open_and_layout(drawer, _alert("RATE_SPIKE", "Bandwidth spike detected"))
        assert drawer._go_btn.isVisible()
        assert not drawer._fix_btn.isVisible()
        self._assert_no_button_clipped(drawer)

    def test_no_page_variant_not_clipped(self, drawer):
        # Unmapped rule -> neither Fix this nor Go to page shown
        self._open_and_layout(drawer, _alert("SOME_UNMAPPED_RULE", "Unrecognised alert"))
        assert not drawer._fix_btn.isVisible()
        assert not drawer._go_btn.isVisible()
        self._assert_no_button_clipped(drawer)


class TestLearnMoreWiring:
    def test_known_term_in_rule_name_shows_link(self, drawer):
        drawer.open(_alert("ARP_SPOOF", "Possible ARP spoofing detected on 192.168.1.10"))
        assert drawer._learn_more_link is not None
        assert "ARP" in drawer._learn_more_link.text()

    def test_unknown_term_shows_no_link(self, drawer):
        drawer.open(_alert("BANDWIDTH_SPIKE", "Unusual bandwidth detected on eth0"))
        assert drawer._learn_more_link is None

    def test_switching_alerts_clears_previous_link(self, drawer):
        drawer.open(_alert("ARP_SPOOF", "Possible ARP spoofing detected"))
        assert drawer._learn_more_link is not None
        drawer.open(_alert("BANDWIDTH_SPIKE", "Unusual bandwidth detected"))
        assert drawer._learn_more_link is None

    def test_term_found_in_message_when_not_in_rule_name(self, drawer):
        drawer.open(_alert("SECURITY_FINDING", "A known CVE was found on this device"))
        assert drawer._learn_more_link is not None
        assert "CVE" in drawer._learn_more_link.text()
