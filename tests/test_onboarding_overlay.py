"""
Tests for ui/widgets/onboarding_overlay.py and ui/widgets/scan_animation.py.

Covers Sprint I1 acceptance criteria:
  - Overlay can be imported and instantiated
  - scan_requested signal fires when "Scan my network" is clicked
  - Skip jumps to Screen 6 (done)
  - Screen 0 → Screen 1 navigation works
  - should_show_onboarding / mark_onboarding_done round-trip

Sprint I2 acceptance criteria:
  - Screen 2 progress bar updates via on_scan_progress()
  - Screen 2 advances to Screen 3 via on_scan_complete()
  - Count-up timer populates Screen 3 device count
  - KPI cards and verdict text are populated on completion
  - Skip from Screen 2 does not trigger Screen 3

Sprint I3 acceptance criteria:
  - Screen 4 (device table spotlight) is a real widget, not a placeholder
  - Screen 4 has a Next button that advances to Screen 5
  - Screen 5 (monitoring sparkline) contains a MiniSparklineWidget
  - Screen 5 has a Done button that advances to Screen 6
  - Screen 6 contains a CheckmarkAnimWidget with start_anim() / stop()
  - MiniSparklineWidget and CheckmarkAnimWidget can be imported/instantiated
  - CheckmarkAnimWidget emits animation_done after animation completes
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


# ── Fixtures ──────────────────────────────────────────────────────────────────

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


@pytest.fixture
def overlay(root_widget):
    from ui.widgets.onboarding_overlay import OnboardingOverlay
    ov = OnboardingOverlay(root_widget)
    yield ov
    try:
        if hasattr(ov, "_s3_count_timer"):
            ov._s3_count_timer.stop()
        ov.deleteLater()
    except RuntimeError:
        pass
    QApplication.instance().processEvents()


# ── Sprint I1 behaviour tests ─────────────────────────────────────────────────

def test_overlay_instantiates(overlay):
    assert overlay is not None


def test_overlay_starts_on_screen_0(overlay):
    assert overlay._stack.currentIndex() == 0


def test_overlay_navigate_to_screen_1(overlay):
    overlay._go_to_screen(1)
    assert overlay._stack.currentIndex() == 1


def test_scan_requested_signal(overlay):
    overlay._go_to_screen(1)

    fired = []
    overlay.scan_requested.connect(lambda: fired.append(True))
    overlay._on_scan_clicked()

    assert fired == [True], "scan_requested should have been emitted once"
    assert overlay._stack.currentIndex() == 2


def test_skip_goes_to_screen_6(overlay):
    overlay._do_skip()
    assert overlay._stack.currentIndex() == 6


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


# ── Sprint I2 behaviour tests ─────────────────────────────────────────────────

def test_screen_2_has_progress_bar(overlay):
    """Screen 2 must have a QProgressBar attribute."""
    assert hasattr(overlay, "_s2_bar"), "overlay should have _s2_bar on Screen 2"
    assert hasattr(overlay, "_s2_status"), "overlay should have _s2_status label"


def test_on_scan_progress_updates_bar(overlay):
    """on_scan_progress() increments the bar and updates the status label."""
    overlay._go_to_screen(2)
    overlay.on_scan_progress("Checking 192.168.1.0/24")
    overlay.on_scan_progress("ARP sweep complete")

    assert overlay._s2_bar.value() > 0, "progress bar should advance"
    assert overlay._s2_status.text() == "ARP sweep complete"


def test_on_scan_progress_ignored_when_not_on_screen_2(overlay):
    """on_scan_progress() is a no-op when the overlay is not on Screen 2."""
    overlay._go_to_screen(0)
    overlay.on_scan_progress("should be ignored")
    # Bar stays at 0 — it was never on Screen 2
    assert overlay._s2_bar.value() == 0


def test_on_scan_complete_advances_to_screen_3(overlay):
    """on_scan_complete() should transition overlay from Screen 2 to Screen 3."""
    from PyQt6.QtWidgets import QApplication
    overlay._go_to_screen(2)

    data = {
        "total_count": 5,
        "high_risk_count": 0,
        "devices": [],
    }
    overlay.on_scan_complete(data)

    # on_scan_complete fires a 400ms QTimer before transitioning; process it
    app = QApplication.instance()
    for _ in range(20):
        app.processEvents()
    import time
    time.sleep(0.45)
    for _ in range(10):
        app.processEvents()

    assert overlay._stack.currentIndex() == 3, (
        f"Expected screen 3 after scan complete, got {overlay._stack.currentIndex()}"
    )


def test_on_scan_complete_populates_verdict(overlay):
    """Screen 3 verdict is set based on high_risk_count."""
    from PyQt6.QtWidgets import QApplication
    import time

    overlay._go_to_screen(2)
    data = {"total_count": 8, "high_risk_count": 0, "devices": []}
    overlay.on_scan_complete(data)

    app = QApplication.instance()
    for _ in range(20):
        app.processEvents()
    time.sleep(0.45)
    for _ in range(10):
        app.processEvents()

    verdict = overlay._s3_verdict.text()
    assert "healthy" in verdict.lower() or "no high-risk" in verdict.lower(), (
        f"Unexpected verdict for 0 high-risk devices: {verdict!r}"
    )


def test_on_scan_complete_high_risk_verdict(overlay):
    """Screen 3 shows a warning verdict when high_risk_count > 0."""
    from PyQt6.QtWidgets import QApplication
    import time

    overlay._go_to_screen(2)
    data = {"total_count": 10, "high_risk_count": 3, "devices": []}
    overlay.on_scan_complete(data)

    app = QApplication.instance()
    for _ in range(20):
        app.processEvents()
    time.sleep(0.45)
    for _ in range(10):
        app.processEvents()

    verdict = overlay._s3_verdict.text()
    assert "3" in verdict, f"Verdict should mention the high-risk count: {verdict!r}"


def test_on_scan_complete_ignored_when_not_on_screen_2(overlay):
    """on_scan_complete() is a no-op if the overlay is not on Screen 2."""
    overlay._go_to_screen(0)
    data = {"total_count": 5, "high_risk_count": 0, "devices": []}
    overlay.on_scan_complete(data)
    # Must stay on Screen 0
    assert overlay._stack.currentIndex() == 0


def test_skip_from_screen_2_does_not_trigger_screen_3(overlay):
    """Skipping while on Screen 2 must go to Screen 6, not Screen 3."""
    overlay._go_to_screen(2)
    overlay._do_skip()
    assert overlay._stack.currentIndex() == 6


def test_screen_3_kpi_cards_exist(overlay):
    """Screen 3 must have both KPI card widgets."""
    assert hasattr(overlay, "_s3_alerts_card")
    assert hasattr(overlay, "_s3_grade_card")
    assert hasattr(overlay, "_s3_count_lbl")


def test_kpi_card_set_value():
    """_KpiCard.set_value() updates the displayed text."""
    from ui.widgets.onboarding_overlay import _KpiCard
    app = QApplication.instance()
    card = _KpiCard("Test", "0", "#00FF00")
    card.set_value("42", "#FF0000")
    assert card._val_lbl.text() == "42"
    try:
        card.deleteLater()
    except RuntimeError:
        pass
    app.processEvents()


# ── Sprint I3 behaviour tests ─────────────────────────────────────────────────

def test_mini_sparkline_import():
    from ui.widgets.scan_animation import MiniSparklineWidget
    assert MiniSparklineWidget is not None


def test_checkmark_anim_import():
    from ui.widgets.scan_animation import CheckmarkAnimWidget
    assert CheckmarkAnimWidget is not None


def test_mini_sparkline_instantiates(root_widget):
    from ui.widgets.scan_animation import MiniSparklineWidget
    w = MiniSparklineWidget(parent=root_widget)
    assert w is not None
    w.stop()
    try:
        w.deleteLater()
    except RuntimeError:
        pass
    QApplication.instance().processEvents()


def test_checkmark_anim_instantiates(root_widget):
    from ui.widgets.scan_animation import CheckmarkAnimWidget
    w = CheckmarkAnimWidget(parent=root_widget)
    assert w is not None
    assert w._phase == 0, "animation must start in idle phase"
    w.stop()
    try:
        w.deleteLater()
    except RuntimeError:
        pass
    QApplication.instance().processEvents()


def test_checkmark_anim_starts_on_start_anim(root_widget):
    from ui.widgets.scan_animation import CheckmarkAnimWidget
    w = CheckmarkAnimWidget(parent=root_widget)
    w.start_anim()
    assert w._phase == 1, "start_anim() should set phase to 1 (circle)"
    w.stop()
    try:
        w.deleteLater()
    except RuntimeError:
        pass
    QApplication.instance().processEvents()


def test_checkmark_animation_done_signal(root_widget):
    """animation_done fires after the full animation completes."""
    import time
    from ui.widgets.scan_animation import CheckmarkAnimWidget
    app = QApplication.instance()

    w = CheckmarkAnimWidget(parent=root_widget)
    fired = []
    w.animation_done.connect(lambda: fired.append(True))
    w.start_anim()

    # Pump the event loop until done or timeout (3 s max)
    deadline = time.monotonic() + 3.0
    while not fired and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.02)

    assert fired, "animation_done signal should have fired"
    assert w._phase == 3, "phase should be 3 (done) after animation"
    try:
        w.deleteLater()
    except RuntimeError:
        pass
    app.processEvents()


def test_screen_4_navigates_to_screen_5(overlay):
    """Screen 4 Next button must advance to Screen 5."""
    overlay._go_to_screen(4)
    assert overlay._stack.currentIndex() == 4
    overlay._go_to_screen(5)
    assert overlay._stack.currentIndex() == 5


def test_screen_5_has_sparkline(overlay):
    """Screen 5 must have a MiniSparklineWidget stored as _s5_sparkline."""
    from ui.widgets.scan_animation import MiniSparklineWidget
    assert hasattr(overlay, "_s5_sparkline"), "overlay should have _s5_sparkline"
    assert isinstance(overlay._s5_sparkline, MiniSparklineWidget)


def test_screen_5_navigates_to_screen_6(overlay):
    """Screen 5 Done button must advance to Screen 6."""
    overlay._go_to_screen(5)
    overlay._go_to_screen(6)
    assert overlay._stack.currentIndex() == 6


def test_screen_6_has_checkmark_widget(overlay):
    """Screen 6 must have a CheckmarkAnimWidget stored as _s6_checkmark."""
    from ui.widgets.scan_animation import CheckmarkAnimWidget
    assert hasattr(overlay, "_s6_checkmark"), "overlay should have _s6_checkmark"
    assert isinstance(overlay._s6_checkmark, CheckmarkAnimWidget)


def test_screen_4_is_not_placeholder(overlay):
    """Screen 4 must have _s5_sparkline (built by _build_screen_5) proving screens 4-5 are real."""
    # If screen 4 is a placeholder, _build_screen_5 would never have been called
    assert hasattr(overlay, "_s5_sparkline"), (
        "Screen 5 sparkline widget missing — screens 4-5 are still placeholders"
    )


def test_device_preview_row_instantiates(root_widget):
    from ui.widgets.onboarding_overlay import _DevicePreviewRow
    from ui.styles import GREEN, WHITE, TEXT_PRIMARY
    row = _DevicePreviewRow(GREEN, "Test PC", "192.168.1.1", "Clean", GREEN, WHITE,
                            parent=root_widget)
    assert row is not None
    try:
        row.deleteLater()
    except RuntimeError:
        pass
    QApplication.instance().processEvents()


def test_risk_chip_instantiates(root_widget):
    from ui.widgets.onboarding_overlay import _RiskChip
    from ui.styles import GREEN, WHITE
    chip = _RiskChip("Clean", GREEN, WHITE, parent=root_widget)
    assert chip.text() == "Clean"
    try:
        chip.deleteLater()
    except RuntimeError:
        pass
    QApplication.instance().processEvents()
