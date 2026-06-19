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
