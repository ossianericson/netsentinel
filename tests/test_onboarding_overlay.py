"""
Tests for ui/widgets/onboarding_overlay.py and ui/widgets/scan_animation.py.

Covers Sprint I1 acceptance criteria:
  - Overlay can be imported and instantiated
  - scan_requested signal fires when "Scan my network" is clicked
  - Skip jumps to Screen 6 (done)
  - Screen 0 → Screen 1 navigation works
  - should_show_onboarding / mark_onboarding_done round-trip
"""
import pytest

try:
    from PyQt6.QtWidgets import QApplication, QWidget
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)


# ── Import tests ──────────────────────────────────────────────────────────────

def test_scan_animation_import():
    from ui.widgets.scan_animation import ScanAnimationWidget
    assert ScanAnimationWidget is not None


def test_onboarding_overlay_import():
    from ui.widgets.onboarding_overlay import OnboardingOverlay
    assert OnboardingOverlay is not None


def test_onboarding_shim_import():
    from ui.onboarding import should_show_onboarding, mark_onboarding_done
    assert callable(should_show_onboarding)
    assert callable(mark_onboarding_done)


# ── Behaviour tests ───────────────────────────────────────────────────────────

@pytest.fixture
def root_widget():
    app = QApplication.instance()
    w = QWidget()
    w.resize(1024, 768)
    yield w
    try:
        w.deleteLater()
    except RuntimeError:
        pass
    if app:
        for _ in range(3):
            app.processEvents()


def test_overlay_instantiates(root_widget):
    from ui.widgets.onboarding_overlay import OnboardingOverlay
    overlay = OnboardingOverlay(root_widget)
    assert overlay is not None
    assert overlay.parent() is root_widget
    try:
        overlay.deleteLater()
    except RuntimeError:
        pass
    QApplication.instance().processEvents()


def test_overlay_starts_on_screen_0(root_widget):
    from ui.widgets.onboarding_overlay import OnboardingOverlay
    overlay = OnboardingOverlay(root_widget)
    assert overlay._stack.currentIndex() == 0
    try:
        overlay.deleteLater()
    except RuntimeError:
        pass
    QApplication.instance().processEvents()


def test_overlay_navigate_to_screen_1(root_widget):
    from ui.widgets.onboarding_overlay import OnboardingOverlay
    overlay = OnboardingOverlay(root_widget)
    overlay._go_to_screen(1)
    assert overlay._stack.currentIndex() == 1
    try:
        overlay.deleteLater()
    except RuntimeError:
        pass
    QApplication.instance().processEvents()


def test_scan_requested_signal(root_widget):
    from ui.widgets.onboarding_overlay import OnboardingOverlay
    overlay = OnboardingOverlay(root_widget)
    overlay._go_to_screen(1)

    fired = []
    overlay.scan_requested.connect(lambda: fired.append(True))
    overlay._on_scan_clicked()

    assert fired == [True], "scan_requested should have been emitted once"
    # After clicking, overlay advances to Screen 2
    assert overlay._stack.currentIndex() == 2

    try:
        overlay.deleteLater()
    except RuntimeError:
        pass
    QApplication.instance().processEvents()


def test_skip_goes_to_screen_6(root_widget):
    from ui.widgets.onboarding_overlay import OnboardingOverlay
    overlay = OnboardingOverlay(root_widget)
    overlay._do_skip()
    assert overlay._stack.currentIndex() == 6
    try:
        overlay.deleteLater()
    except RuntimeError:
        pass
    QApplication.instance().processEvents()


def test_should_show_onboarding_after_mark_done(root_widget):
    from PyQt6.QtCore import QSettings
    from ui.onboarding import should_show_onboarding, mark_onboarding_done

    qs = QSettings("NetSentinel", "NetSentinel")
    original = qs.value("ui/onboarding_v2_done", None)

    try:
        qs.setValue("ui/onboarding_v2_done", False)
        assert should_show_onboarding() is True

        mark_onboarding_done()
        assert should_show_onboarding() is False
    finally:
        if original is None:
            qs.remove("ui/onboarding_v2_done")
        else:
            qs.setValue("ui/onboarding_v2_done", original)


def test_scan_animation_rings_instantiates(root_widget):
    from ui.widgets.scan_animation import ScanAnimationWidget
    w = ScanAnimationWidget(mode="rings", parent=root_widget)
    assert w is not None
    w.stop()
    try:
        w.deleteLater()
    except RuntimeError:
        pass
    QApplication.instance().processEvents()


def test_scan_animation_radar_instantiates(root_widget):
    from ui.widgets.scan_animation import ScanAnimationWidget
    w = ScanAnimationWidget(mode="radar", parent=root_widget)
    assert w is not None
    w.stop()
    try:
        w.deleteLater()
    except RuntimeError:
        pass
    QApplication.instance().processEvents()
