"""
tests/test_home_ack_button_glyph.py — the Home action card's per-alert ✓ button
must actually render its glyph.

Mechanism. The global stylesheet declares `QPushButton { padding: 5px 14px; }`
(ui/styles.py::MAIN_STYLE). An inline setStyleSheet() merges with that rule
rather than replacing it, so any property the inline sheet does not name is
still inherited. `ack_btn` is `setFixedSize(22, 18)` and its inline sheet names
background/color/border/border-radius/font-size but NOT padding — so 14 px of
left padding plus 14 px of right padding are applied inside a 22 px-wide
button. The label rect computes to zero width and Qt elides the text away
entirely, leaving a bordered empty box. sizeHint() is 40×26 against the forced
22×18, which is the tell.

This shipped: the button is styled transparent and borderless-ish, so the glyph
is its only affordance — the user reported it as "the box on the right", not as
an acknowledge button. Same failure shape as the RULE-ENC1 class-2 dismiss
buttons, but from padding inheritance rather than encoding.

RULE-T3: fails before the fix (the rendered button is a uniform empty box).
"""
from __future__ import annotations

import pytest

try:
    from PyQt6.QtWidgets import QApplication, QPushButton
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)


_created_pages: list = []


def _apply_app_stylesheet() -> None:
    from ui.styles import MAIN_STYLE, get_app_qss, _suspend_repaints
    app = QApplication.instance()
    if app is not None:
        with _suspend_repaints():          # RULE-STARTUP2
            app.setStyleSheet(MAIN_STYLE + get_app_qss())


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    app = QApplication.instance()
    if app is not None:
        # Leave the session QApplication as we found it — a stylesheet left
        # applied changes rendering for every later test in the run.
        from ui.styles import _suspend_repaints
        with _suspend_repaints():
            app.setStyleSheet("")
    for page in _created_pages:
        try:
            page.deleteLater()
        except RuntimeError:
            pass  # already destroyed — safe to skip
    if app:
        try:
            from PyQt6.QtCore import QCoreApplication, QEvent
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
        except Exception:
            pass  # non-fatal
        for _ in range(3):
            app.processEvents()
    _created_pages.clear()


@pytest.fixture()
def store(tmp_path):
    from modules.metric_store import MetricStore
    s = MetricStore(db_path=tmp_path / "test.db")
    yield s
    s.close()


def _ack_button(store):
    from ui.pages.home_page import HomePage
    # The bug only exists under the real app stylesheet — that is where
    # `QPushButton { padding: 5px 14px; }` lives. A bare pytest QApplication
    # has no stylesheet, so without this the button renders fine and the test
    # is measuring nothing.
    _apply_app_stylesheet()
    store.record_alert_fired("Device Gone", "10.0.0.1", "WARNING", "gone")
    page = HomePage(store=store)
    _created_pages.append(page)
    page.resize(900, 200)
    page.set_pending_alert_rows(store.get_unacked_alerts())
    page.show()
    QApplication.instance().processEvents()
    row = page._ac_alert_rows_lay.itemAt(0).widget()
    return next(b for b in row.findChildren(QPushButton) if b.text() == "✓")


def _distinct_interior_colours(widget, inset: int = 4) -> int:
    """Colours inside the button's border box.

    Insetting past the 1px border + 3px radius matters: the border alone
    already makes the full grab multi-coloured, so a whole-widget sample
    passes even when the glyph is completely missing.
    """
    img = widget.grab().toImage()
    seen = set()
    for y in range(inset, img.height() - inset):
        for x in range(inset, img.width() - inset):
            seen.add(img.pixel(x, y))
    return len(seen)


def test_ack_button_label_is_not_elided_away_by_inherited_padding(store):
    """The horizontal padding actually in force must leave room for the glyph."""
    btn = _ack_button(store)
    from PyQt6.QtGui import QFontMetrics

    needed = QFontMetrics(btn.font()).horizontalAdvance(btn.text())
    # Border (1px each side) is the only other horizontal consumer once the
    # inline sheet pins padding; the global 5px 14px rule would leave -8px.
    available = btn.width() - 2 * 1 - _horizontal_padding(btn)
    assert available >= needed, (
        f"the ✓ needs {needed}px but only {available}px of label width is "
        f"available in a {btn.width()}px button — the inline stylesheet must "
        f"declare its own padding, or the global "
        f"'QPushButton {{ padding: 5px 14px; }}' rule is inherited and elides it"
    )


def _horizontal_padding(btn) -> int:
    """Left+right padding actually in force for this button."""
    import re
    sheet = btn.styleSheet()
    m = re.search(r"padding\s*:\s*([^;}]+)", sheet)
    if not m:
        return 28  # inherited from MAIN_STYLE's QPushButton { padding: 5px 14px; }
    parts = m.group(1).split()
    px = [int(re.sub(r"[^0-9-]", "", p) or 0) for p in parts]
    if len(px) == 1:
        return px[0] * 2
    if len(px) in (2, 3):
        return px[1] * 2
    return px[1] + px[3]


def test_ack_button_actually_paints_its_glyph(store):
    """End-to-end render: count pixels inside the border that differ from the
    button's own background.

    Measured on this button: 0 ink pixels as shipped (identical to setText("")
    — the glyph never paints at all), 11 once padding is pinned. A plain
    "is it multi-coloured?" or with/without-text differential check does NOT
    discriminate here — the border supplies colours either way, and a second
    grab can differ for reasons unrelated to the label.
    """
    btn = _ack_button(store)
    ink = _ink_pixels(btn)
    assert ink > 0, (
        "the ✓ acknowledge button painted zero pixels of label — it renders as "
        "a bordered empty box. The glyph is its only affordance, so this is an "
        "unlabelled control"
    )


def _ink_pixels(widget, inset: int = 3) -> int:
    """Interior pixels differing from the modal (background) colour."""
    import collections
    img = widget.grab().toImage()
    px = [
        img.pixel(x, y)
        for y in range(inset, img.height() - inset)
        for x in range(inset, img.width() - inset)
    ]
    if not px:
        return 0
    background = collections.Counter(px).most_common(1)[0][0]
    return sum(1 for p in px if p != background)
