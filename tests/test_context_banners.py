"""Tests for ui.context_banners and PageHeaderBar.show_first_visit_banner (Sprint 7, S7-1)."""
import pytest

try:
    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QApplication, QPushButton
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

pytestmark = pytest.mark.skipif(not _HAS_QT, reason="PyQt6 not available")


def _fresh(key: str):
    qs = QSettings("NetSentinel", "NetSentinel")
    qs.remove(f"banner/{key}_seen")
    return qs


def _cleanup(widget):
    app = QApplication.instance()
    try:
        widget.deleteLater()
    except RuntimeError:
        pass  # already destroyed — safe to skip
    if app:
        for _ in range(3):
            app.processEvents()


# ── ui.context_banners helpers ──────────────────────────────────────────────

class TestContextBannerSettings:
    def setup_method(self):    _fresh("test_page")
    def teardown_method(self): _fresh("test_page")

    def test_should_show_true_on_fresh_install(self):
        from ui.context_banners import should_show_banner
        assert should_show_banner("test_page") is True

    def test_should_show_false_after_marked_seen(self):
        from ui.context_banners import mark_banner_seen, should_show_banner
        mark_banner_seen("test_page")
        assert should_show_banner("test_page") is False

    def test_mark_seen_sets_settings_key(self):
        from ui.context_banners import mark_banner_seen
        mark_banner_seen("test_page")
        qs = QSettings("NetSentinel", "NetSentinel")
        assert qs.value("banner/test_page_seen", False, type=bool) is True

    def test_each_page_key_tracked_independently(self):
        from ui.context_banners import mark_banner_seen, should_show_banner
        _fresh("other_page")
        mark_banner_seen("test_page")
        assert should_show_banner("test_page") is False
        assert should_show_banner("other_page") is True
        _fresh("other_page")


# ── PageHeaderBar.show_first_visit_banner ───────────────────────────────────

@pytest.fixture
def header():
    from ui.widgets.page_header import PageHeaderBar
    QApplication.instance()
    hdr = PageHeaderBar("Test Page")
    yield hdr
    _cleanup(hdr)


class TestPageHeaderBanner:
    def setup_method(self):    _fresh("hdr_test")
    def teardown_method(self): _fresh("hdr_test")

    def test_banner_hidden_by_default(self, header):
        assert header._banner_row.isVisibleTo(header) is False

    def test_banner_shown_on_first_visit(self, header):
        header.show_first_visit_banner("hdr_test", "Explanatory text.")
        assert header._banner_row.isVisibleTo(header) is True
        assert "Explanatory text." in header._banner_lbl.text()

    def test_banner_increases_header_height(self, header):
        base = header.height()
        header.show_first_visit_banner("hdr_test", "Explanatory text.")
        assert header.height() > base

    def test_dismiss_hides_banner_and_marks_seen(self, header):
        from ui.context_banners import should_show_banner
        header.show_first_visit_banner("hdr_test", "Explanatory text.")
        dismiss_btn = header._banner_dismiss_btn
        dismiss_btn.click()
        assert header._banner_row.isVisibleTo(header) is False
        assert should_show_banner("hdr_test") is False

    def test_dismiss_restores_base_height(self, header):
        base = header.height()
        header.show_first_visit_banner("hdr_test", "Explanatory text.")
        header._banner_dismiss_btn.click()
        assert header.height() == base

    def test_not_shown_again_on_new_header_after_dismiss(self):
        from ui.context_banners import mark_banner_seen
        from ui.widgets.page_header import PageHeaderBar
        mark_banner_seen("hdr_test")
        hdr2 = PageHeaderBar("Test Page 2")
        hdr2.show_first_visit_banner("hdr_test", "Explanatory text.")
        assert hdr2._banner_row.isVisibleTo(hdr2) is False
        _cleanup(hdr2)

    def test_dismiss_button_is_a_qpushbutton(self, header):
        header.show_first_visit_banner("hdr_test", "Explanatory text.")
        assert isinstance(header._banner_dismiss_btn, QPushButton)
