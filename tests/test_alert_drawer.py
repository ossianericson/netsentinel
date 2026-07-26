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


def _alert(rule_name: str, message: str, rule_type: str = "") -> dict:
    return {
        "id": 1,
        "severity": "WARNING",
        "rule_name": rule_name,
        "rule_type": rule_type,
        "host": "192.168.1.10",
        "ts": int(time.time()),
        "message": message,
    }


class TestRemediationTextUsesCanonicalModule:
    """Phase 7.3 -- _RULE_FIX / _rule_to_fix moved to modules/alert_remediation.py
    (remediation_for). The drawer must pass rule_type from the alert row, not
    just rule_name -- a row written after schema v19 always carries rule_type,
    so this is the primary lookup key; rule_name substring matching is only the
    legacy fallback for pre-v19 rows."""

    def test_fix_label_uses_canonical_rule_type_over_legacy_name(self, drawer):
        from modules.alert_remediation import REMEDIATION
        drawer.show()
        drawer.open(_alert("Some Made Up Display Name", "msg", rule_type="HOST_DOWN"))
        assert drawer._fix_lbl.text() == REMEDIATION["HOST_DOWN"]
        assert drawer._fix_lbl.isVisible() is True
        assert drawer._no_fix_lbl.isVisible() is False

    def test_fix_label_falls_back_to_legacy_rule_name_match(self, drawer):
        """A pre-schema-v19 row has rule_type='' but a rule_name substring
        match still resolves via the legacy table."""
        drawer.show()
        drawer.open(_alert("ARP Spoof Detected", "msg", rule_type=""))
        assert drawer._fix_lbl.text() != ""
        assert drawer._fix_lbl.isVisible() is True

    def test_no_fix_label_shown_when_nothing_matches(self, drawer):
        drawer.show()
        drawer.open(_alert("Totally Unknown Alert", "msg", rule_type=""))
        assert drawer._fix_lbl.isVisible() is False
        assert drawer._no_fix_lbl.isVisible() is True

    def test_legacy_rule_fix_table_removed_from_the_drawer(self):
        """_RULE_FIX/_rule_to_fix moved to modules/alert_remediation.py."""
        from ui.widgets import alert_drawer as ad
        assert not hasattr(ad, "_RULE_FIX")
        assert not hasattr(ad, "_rule_to_fix")

    def test_live_per_alert_remediation_overrides_the_table(self, drawer):
        """AlertFired.remediation (e.g. IOT_BEHAVIOR's signal-specific text)
        takes priority when present in the alert dict -- not persisted, so
        history rows loaded from the DB simply never carry this key and fall
        back to the table as before."""
        drawer.show()
        alert = _alert("IoT Behavior Anomaly", "msg", rule_type="IOT_BEHAVIOR")
        alert["remediation"] = "Block device's internet access temporarily."
        drawer.open(alert)
        assert drawer._fix_lbl.text() == "Block device's internet access temporarily."

    def test_empty_live_remediation_falls_back_to_the_table(self, drawer):
        from modules.alert_remediation import REMEDIATION
        drawer.show()
        alert = _alert("Host Down", "msg", rule_type="HOST_DOWN")
        alert["remediation"] = ""
        drawer.open(alert)
        assert drawer._fix_lbl.text() == REMEDIATION["HOST_DOWN"]


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
