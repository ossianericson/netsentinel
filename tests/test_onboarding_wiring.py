"""
Regression tests for Dashboard._maybe_start_onboarding (ui/dashboard.py).

Bug (live-reported, confirmed via registry inspection on a machine with 2,328
recorded scans and no "ui/onboarding_v2_done" key ever written): the Step-1
coach mark's card anchored to whichever Home-page scan button
_pick_home_scan_btn() resolved. That button's visibility is toggled by
_apply_recurring_layout(), which can flip asynchronously right after the coach
mark captures its target reference -- when that happens, CoachMarkOverlay's
_position() loses its anchor and falls back to the disconnected bottom-right
corner of the window. Because mark_onboarding_done() only fired from the
card's own action-button/dismiss-button click handlers, a card nobody could
see was a card nobody ever dismissed -- so it reappeared on every launch
instead of showing once, ever.

Fix: (1) anchor the card to the header Scan button, a permanent top-bar
element never hidden by Home-page mode state; (2) mark onboarding done as
soon as we decide to show it, not only on interaction.

RULE-TP4-DASH forbids constructing a real Dashboard in-process under pytest,
so these are source-inspection guards on Dashboard._maybe_start_onboarding
(see tests/test_verdict_badge_clickable.py for the established pattern).
"""
from __future__ import annotations

import inspect

import pytest

pytest.importorskip("PyQt6.QtWidgets")


def _onboarding_source():
    from ui.dashboard import Dashboard
    return inspect.getsource(Dashboard._maybe_start_onboarding)


def test_onboarding_card_anchors_to_header_scan_button(qt_app):
    if qt_app is None:
        pytest.skip("No QApplication")
    src = _onboarding_source()
    assert '"card_target"' in src, (
        "Step-1 coach mark must set card_target so the card anchors to a "
        "stable widget instead of falling back to the target used for the "
        "ring (which can go invisible when Home-page mode state flips)"
    )
    # The card_target lambda must resolve _header_scan_btn specifically --
    # a permanent top-bar element, never hidden by recurring/first-run mode.
    assert "_header_scan_btn" in src.split('"card_target"', 1)[1].split("\n")[0], (
        "card_target must resolve _header_scan_btn"
    )


def test_onboarding_marked_done_before_chain_is_shown(qt_app):
    """mark_onboarding_done() must fire once, unconditionally, before the
    CoachMarkChain is constructed -- not only from interaction callbacks
    nested inside the function, which never fire if the card is never
    seen/clicked."""
    if qt_app is None:
        pytest.skip("No QApplication")
    src = _onboarding_source()

    call_idx = src.index("mark_onboarding_done()")
    chain_idx = src.index("CoachMarkChain(")
    assert call_idx < chain_idx, (
        "mark_onboarding_done() must be called before the CoachMarkChain is "
        "constructed, so the flag is set as soon as onboarding is shown -- "
        "not deferred until the user happens to interact with the card"
    )

    # Must appear exactly once — not duplicated inside the nested _step1_done/
    # _step1_skipped interaction callbacks (that was the pre-fix bug shape).
    assert src.count("mark_onboarding_done()") == 1, (
        "mark_onboarding_done() should be called exactly once, unconditionally "
        "-- not re-added inside interaction callbacks"
    )


def test_should_show_onboarding_still_gates_the_call(qt_app):
    """The early-return on should_show_onboarding() must still precede the
    unconditional mark_onboarding_done() call, or every launch would mark
    onboarding done even when it was never shown."""
    if qt_app is None:
        pytest.skip("No QApplication")
    src = _onboarding_source()
    gate_idx = src.index("if not should_show_onboarding():")
    call_idx = src.index("mark_onboarding_done()")
    assert gate_idx < call_idx
