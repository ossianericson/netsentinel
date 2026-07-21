"""Behavioural tests -- ui.widgets.environment_banner.EnvironmentBanner (RULE-T7)."""
import pytest

try:
    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QApplication
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

pytestmark = pytest.mark.skipif(not _HAS_QT, reason="PyQt6 not available")

from modules.network_environment import NetworkEnvironment

_FP = "vpn:GlobalProtect:"


def _fresh():
    QSettings("NetSentinel", "NetSentinel").remove(f"banner/{_FP}_seen")


def _vpn_env() -> NetworkEnvironment:
    return NetworkEnvironment(
        kind="vpn", confidence="high", title="VPN detected: GlobalProtect",
        reasons=["Active VPN adapter detected: GlobalProtect"],
        effects=["Device names may be missing."],
        vpn_adapter="GlobalProtect", domain="", prefix_len=16, subnet_hosts=65534,
    )


@pytest.fixture
def banner():
    from ui.widgets.environment_banner import EnvironmentBanner
    QApplication.instance()
    b = EnvironmentBanner()
    yield b
    app = QApplication.instance()
    try:
        b.deleteLater()
    except RuntimeError:
        pass  # already destroyed -- safe to skip
    if app:
        for _ in range(3):
            app.processEvents()


class TestEnvironmentBanner:
    def setup_method(self):    _fresh()
    def teardown_method(self): _fresh()

    def test_hidden_by_default(self, banner):
        assert banner.isVisible() is False

    def test_hidden_on_home_environment(self, banner):
        banner.set_environment(NetworkEnvironment(kind="home"))
        assert banner.isVisible() is False

    def test_hidden_on_none(self, banner):
        banner.set_environment(None)
        assert banner.isVisible() is False

    def test_visible_with_title_on_vpn_environment(self, banner):
        banner.set_environment(_vpn_env())
        assert banner.isVisible() is True
        assert "GlobalProtect" in banner._title_lbl.text()

    def test_details_hidden_until_info_clicked(self, banner):
        banner.set_environment(_vpn_env())
        assert banner._details_lbl.isVisible() is False
        banner._info_btn.click()
        assert banner._details_lbl.isVisible() is True
        assert "Active VPN adapter detected" in banner._details_lbl.text()

    def test_dismiss_hides_banner_and_marks_seen(self, banner):
        from ui.context_banners import should_show_banner
        banner.set_environment(_vpn_env())
        banner._dismiss_btn.click()
        assert banner.isVisible() is False
        assert should_show_banner(_FP) is False

    def test_dismissed_fingerprint_stays_hidden_on_next_set(self, banner):
        from ui.context_banners import mark_banner_seen
        mark_banner_seen(_FP)
        banner.set_environment(_vpn_env())
        assert banner.isVisible() is False

    def test_different_fingerprint_is_not_suppressed_by_prior_dismissal(self, banner):
        from ui.context_banners import mark_banner_seen
        mark_banner_seen(_FP)
        other = NetworkEnvironment(
            kind="corporate", confidence="high", title="Corporate network detected (CONTOSO)",
            reasons=["Windows domain membership detected: CONTOSO"], effects=[],
            vpn_adapter="", domain="CONTOSO", prefix_len=24, subnet_hosts=254,
        )
        banner.set_environment(other)
        assert banner.isVisible() is True
        QSettings("NetSentinel", "NetSentinel").remove(f"banner/{other.fingerprint()}_seen")
