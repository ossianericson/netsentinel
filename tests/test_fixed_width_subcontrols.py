"""A pinned width below the widget's own minimum clips its text (RULE-QSS5's family).

Reported live: the Network Logger's Activity-log history bar rendered `2026-09-0⌄` and
`23:5⌄` — the From/To date and time fields with their last characters cut off.

Two things compound at that site, and each is guarded separately below.

**Pinned too narrow.** `setFixedWidth()` overrides `minimumSizeHint()`, so Qt clips
rather than growing. The date editors were pinned at 100 px against a 151 px minimum and
the time editors at 72 px against 116 px. The correct number is font-, theme- **and
locale**-dependent — with no `setDisplayFormat()` the format comes from
`QLocale::system()`, which is `yyyy-MM-dd` on sv-SE, `M/d/yyyy` on en-US and
`dd.MM.yyyy` on de-DE — so it cannot be audited by eye, only measured.

**Unsafe QSS on the spinbox family.** `ui/styles.py` (above `SPINBOX_WIDTH_PLAIN`)
records, from a live investigation, that `padding`/`border`/`border-radius` in a
stylesheet applied to a `QAbstractSpinBox` shifts the text area **into** the button
subcontrol rects — the buttons still paint correctly but stop responding to clicks. That
lesson was written for `QSpinBox` and never reached its `QDateEdit`/`QTimeEdit`/
`QDateTimeEdit` siblings, which is how the Activity-log fields got styled that way.

RULE-QSS5's trap applies to the render test here: a bare pytest `QApplication` has no
application stylesheet, so the clipping does not reproduce unless the real one is applied
first — and it must be restored afterwards, or every later test in the session renders
against it.
"""
from __future__ import annotations

import ast
import pathlib
from unittest.mock import MagicMock

import pytest

try:
    from PyQt6.QtWidgets import QAbstractSpinBox, QApplication
except ImportError:  # pragma: no cover - PyQt6 is present in every supported env
    pytest.skip("PyQt6 not available", allow_module_level=True)

_UI_ROOT = pathlib.Path(__file__).resolve().parent.parent / "ui"

#: Every QAbstractSpinBox subclass the app builds. A rule written for QSpinBox alone
#: does not reach these siblings — which is exactly how the reported bug shipped.
SPINBOX_FAMILY = {
    "QAbstractSpinBox", "QSpinBox", "QDoubleSpinBox",
    "QDateEdit", "QTimeEdit", "QDateTimeEdit",
}

#: QSS properties that are unsafe on the spinbox family; see the module docstring.
UNSAFE_SPINBOX_QSS = ("padding", "border")


@pytest.fixture
def app_stylesheet():
    """Apply the real application stylesheet for the duration of one test."""
    app = QApplication.instance()
    assert app is not None, "conftest owns the session QApplication (RULE-WIN3)"
    from ui import styles as _s

    previous = app.styleSheet()
    app.setStyleSheet(_s.MAIN_STYLE + _s.get_app_qss())
    try:
        yield app
    finally:
        app.setStyleSheet(previous)


@pytest.fixture
def log_hub_page(monkeypatch, app_stylesheet):
    monkeypatch.setattr(
        "ui.pages.log_hub_page.QFileSystemWatcher",
        lambda *a, **kw: MagicMock(),
        raising=False,
    )
    from ui.pages.log_hub_page import LogHubPage

    page = LogHubPage(store=None)
    yield page
    try:
        page.deleteLater()
    except RuntimeError:
        pass  # already destroyed — safe to skip
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


def _ink(widget) -> int:
    """Pixels in *widget*'s render that differ from its most common colour.

    The modal colour is the field's background, so everything else is glyph and chrome.
    Counting ink rather than comparing images makes the measure insensitive to which
    font the platform plugin happens to supply.
    """
    image = widget.grab().toImage()
    counts: dict = {}
    for y in range(image.height()):
        for x in range(image.width()):
            pixel = image.pixel(x, y)
            counts[pixel] = counts.get(pixel, 0) + 1
    if not counts:
        return 0
    background = max(counts, key=counts.__getitem__)
    return sum(n for pixel, n in counts.items() if pixel != background)


def _relayout(root, app) -> None:
    root.grab()
    if app is not None:
        for _ in range(2):
            app.processEvents()


def clipped_spinboxes(root, width: int = 1200, height: int = 800) -> list:
    """Every spinbox-family descendant whose value does not fit the space it has.

    Measured **differentially**: render each field's line edit as laid out, then give
    the field a large `min-width` and render it again. Text is left-aligned, so extra
    room adds only background — unless characters were being cut off, in which case the
    second render contains strictly more ink. That difference is the definition of
    "clipped", and it needs no font metrics at all.

    That independence is the whole point, and it was learned the hard way. The first
    version of this check compared ``fontMetrics().horizontalAdvance(text)`` against the
    line edit's width and **passed while the bug was plainly visible on screen**: under
    pytest's offscreen platform the fallback font's advances differ from the real Segoe
    UI, and even on the real platform the advance under-reports what a QDateTimeEdit's
    sectioned editor needs by ~27px (measured: 56px reported, 83px actually required).
    A guard that green-lights a shipped defect is worse than no guard.

    ``grab()`` forces the layout and polish pass that gives children real geometry,
    without showing a window.
    """
    app = QApplication.instance()
    root.resize(width, height)
    _relayout(root, app)

    offenders = []
    for w in root.findChildren(QAbstractSpinBox):
        line_edit = w.lineEdit()
        if line_edit is None or not line_edit.text():
            continue
        as_laid_out = _ink(line_edit)

        original = w.styleSheet()
        w.setStyleSheet(original + " min-width: 400px;")
        _relayout(root, app)
        with_room = _ink(line_edit)
        w.setStyleSheet(original)
        _relayout(root, app)

        if with_room > as_laid_out:
            offenders.append((type(w).__name__, line_edit.text(),
                              as_laid_out, with_room))
    return offenders


def test_activity_log_range_fields_do_not_cut_off_their_own_values(log_hub_page):
    """The reported bug: From/To rendered as `2026-09-0` and `23:5`, last chars gone.

    Asserted against the real page's real widgets under the real stylesheet, never a
    re-derived copy — both the pinned width and the text have to come from the thing
    that actually shipped, or the test proves nothing about it (RULE-DBG5).
    """
    log_hub_page._history_bar.setVisible(True)   # hidden until the user opens history

    offenders = clipped_spinboxes(log_hub_page)

    assert not offenders, (
        "the Activity-log range fields cut their own values off — each renders more "
        "ink once given room, which means characters are being clipped:\n"
        + "\n".join(
            f"  {cls} showing {text!r}: {as_laid_out} ink as laid out, "
            f"{with_room} with room"
            for cls, text, as_laid_out, with_room in offenders
        )
    )


def _spinbox_bindings(tree: ast.AST) -> dict:
    """Map every name unambiguously bound to a spinbox-family widget to its class.

    "Unambiguously" is load-bearing in both directions.

    A name assigned a spinbox class in one branch and something else in another is
    **dropped**: `ui/widgets/hub_card.py` binds `w` to a QCheckBox, a QSpinBox and a
    QLineEdit across three branches of one `if`, and a flow-insensitive map reported its
    (correct) QCheckBox styling as a spinbox violation.

    A `for _w in (a, b, c):` loop over already-bound spinboxes **is** followed, because
    that is the shape the reported bug was written in — styling four date/time editors
    in one loop body. Without it the guard would sweep the whole tree and miss the only
    site anyone had complained about.
    """
    bound: dict = {}
    ambiguous: set = set()

    def _remember(target, cls) -> None:
        key = ast.unparse(target)
        if key in bound and bound[key] != cls:
            ambiguous.add(key)
        bound[key] = cls

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            fn = node.value.func
            cls = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", None)
            for target in node.targets:
                _remember(target, cls if cls in SPINBOX_FAMILY else None)

    for key in ambiguous:
        bound.pop(key, None)
    resolved = {k: v for k, v in bound.items() if v is not None}

    # Second pass: a loop variable iterating a tuple/list of resolved spinboxes.
    for node in ast.walk(tree):
        if (isinstance(node, ast.For) and isinstance(node.target, ast.Name)
                and isinstance(node.iter, (ast.Tuple, ast.List))):
            members = {resolved.get(ast.unparse(e)) for e in node.iter.elts}
            # Every member must be spinbox-family, but they need not be the same class:
            # the reported site loops over two QDateEdits and two QTimeEdits together.
            if members and None not in members:
                resolved[node.target.id] = "/".join(sorted(members))
    return resolved


def _inline_stylesheet_calls(tree: ast.AST) -> list:
    """Every `X.setStyleSheet("literal")` call, as (receiver, literal, lineno)."""
    found = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "setStyleSheet" and node.args):
            arg = node.args[0]
            text = "".join(
                part.value for part in ast.walk(arg)
                if isinstance(part, ast.Constant) and isinstance(part.value, str)
            )
            found.append((ast.unparse(node.func.value), text, node.lineno))
    return found


def _themed_ss_calls(tree: ast.AST) -> list:
    """Every `themed_ss(widget, "literal")` call, as (receiver, literal, lineno).

    `themed_ss` is this codebase's own re-themable wrapper around `setStyleSheet`, so a
    guard that only looked for `setStyleSheet` would miss most of `ui/` — including the
    site that produced the reported bug.
    """
    found = []
    for node in ast.walk(tree):
        func = node.func if isinstance(node, ast.Call) else None
        name = getattr(func, "attr", None) or getattr(func, "id", None)
        if name == "themed_ss" and len(getattr(node, "args", [])) >= 2:
            text = "".join(
                part.value for part in ast.walk(node.args[1])
                if isinstance(part, ast.Constant) and isinstance(part.value, str)
            )
            found.append((ast.unparse(node.args[0]), text, node.lineno))
    return found


def test_no_inline_qss_applies_padding_or_border_to_a_spinbox_family_widget():
    """The cause, swept statically — the symptom above is only one of its sites.

    `ui/styles.py` documents this as verified-unsafe and offers `style_spinbox()` plus
    the `SPINBOX_WIDTH_*` constants as the supported way to style these. The note was
    written for QSpinBox, so nothing stopped the date/time siblings being styled the
    forbidden way; this closes that gap for the whole family.
    """
    violations = []
    for path in sorted(_UI_ROOT.rglob("*.py")):
        src = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue

        kinds = _spinbox_bindings(tree)
        for receiver, text, lineno in (_inline_stylesheet_calls(tree)
                                       + _themed_ss_calls(tree)):
            cls = kinds.get(receiver)
            if cls is None:
                continue
            bad = [prop for prop in UNSAFE_SPINBOX_QSS if prop in text]
            if bad:
                rel = path.relative_to(_UI_ROOT.parent).as_posix()
                violations.append(f"{rel}:{lineno} {cls} {receiver} sets {bad}")

    assert not violations, (
        "QSS padding/border on a QAbstractSpinBox shifts its text area into the button "
        "subcontrol rects — the buttons paint correctly but stop responding to clicks, "
        "and the value text is drawn under them. Use ui.styles.style_spinbox() and a "
        "SPINBOX_WIDTH_* constant instead:\n  " + "\n  ".join(violations)
    )
