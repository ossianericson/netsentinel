"""
Regression coverage for the QSpinBox up/down stepper glyph visibility bug.

Root cause history (found via live rendering, not just contrast math):
1. No ::up-arrow/::down-arrow QSS rule existed at all -> Qt fell back to a
   QPalette-default near-black glyph (ButtonText role is #000000 by
   default), invisible against the dark INPUT_BTN_BG.
2. A CSS border-triangle on ::up-arrow/::down-arrow (the standard web-CSS
   trick) does NOT render in Qt's QSS engine -- confirmed by an isolated
   rendering test: Qt's QSS border painter draws each edge as an
   independent rectangle and does not miter corners into a point.
3. Declaring ANY ::up-button/::down-button subcontrol rule (even just a
   background colour) disables Qt's native palette-based primitive drawing
   for the whole control -- the glyph then renders nothing at all, arrow or
   +/-, regardless of buttonSymbols or qproperty-buttonSymbols in QSS.

The working fix: style only the base QSpinBox box via QSS (not subcontrol
rules, so native rendering stays active) and set QPalette ButtonText/Button
roles in Python via ui.styles.style_spinbox(), which the native primitive
draw respects. Confirmed visually (isolated QWidget screenshot) before this
test was finalised.

4. A second, separate bug found later: declaring `border`, `border-radius`,
   or `padding` (even just one of the three, even `border: none`) in a
   QSpinBox's QSS desyncs Qt's internal QLineEdit child from where the
   native +/- buttons are drawn under the real "windows11" style -- the
   LineEdit's actual widget geometry extends into the button area, so a
   live click on a visually-correct "+"/"-" glyph is delivered to the
   LineEdit (moves the text cursor) instead of the spinbox's button
   handler. The button LOOKS right and PAINTS right but does not respond
   to clicks. QTest.mouseClick() cannot catch this -- it posts synthetic
   events directly to the named widget, bypassing the geometry-based
   child dispatch a real click goes through; QWidget.childAt(<button
   center>) is the reliable check. Confirmed via live click-through
   testing on the real windows11 style (offscreen/CI probing silently
   falls back to "Fusion", a different style, and does not reproduce it).
   Fix: QSpinBox QSS must be limited to background-color/color/font-size
   only; use lineEdit().setTextMargins() (done centrally in
   style_spinbox()) for a left text inset instead of QSS padding.
"""
from __future__ import annotations

from tests.test_contrast import contrast_ratio, WCAG_AA_LARGE


def test_style_spinbox_sets_visible_button_text_in_both_themes():
    from PyQt6.QtGui import QPalette
    from PyQt6.QtWidgets import QSpinBox
    from ui import styles as _s

    original = _s.get_active_theme_name()
    spin = QSpinBox()
    try:
        _s.style_spinbox(spin)
        for theme in ("Arctic Clean", "Midnight Pro"):
            _s.apply_theme(theme)
            fg = spin.palette().color(QPalette.ColorRole.ButtonText).name()
            bg = spin.palette().color(QPalette.ColorRole.Button).name()
            ratio = contrast_ratio(fg, bg)
            assert ratio >= WCAG_AA_LARGE, (
                f"[{theme}] QSpinBox stepper glyph {fg} on button bg {bg} "
                f"-> ratio={ratio:.2f} (need >= {WCAG_AA_LARGE} for "
                f"UI-component contrast)"
            )
            # Also assert it isn't the un-styled default (#000000 ButtonText,
            # the actual bug this guards against).
            assert fg != "#000000", f"[{theme}] ButtonText fell back to the OS default"
    finally:
        spin.deleteLater()
        _s.apply_theme(original)


def test_style_spinbox_reapplies_live_on_theme_switch():
    """A spinbox styled before a theme switch must pick up the new theme's
    colours after apply_theme() -- mirrors themed_ss's live-reapply guarantee."""
    from PyQt6.QtGui import QPalette
    from PyQt6.QtWidgets import QSpinBox
    from ui import styles as _s

    original = _s.get_active_theme_name()
    spin = QSpinBox()
    try:
        _s.apply_theme("Arctic Clean")
        _s.style_spinbox(spin)
        arctic_fg = spin.palette().color(QPalette.ColorRole.ButtonText).name()

        _s.apply_theme("Midnight Pro")
        midnight_fg = spin.palette().color(QPalette.ColorRole.ButtonText).name()

        assert midnight_fg != arctic_fg, (
            "QSpinBox palette did not re-theme on apply_theme() -- "
            "_reapply_spinbox_palettes() may not be wired into apply_theme()"
        )
    finally:
        spin.deleteLater()
        _s.apply_theme(original)


def test_up_down_button_qss_no_longer_declared():
    """Guard against re-introducing ::up-button/::down-button subcontrol
    rules -- declaring them disables native palette-based glyph drawing
    entirely (confirmed by isolated rendering test), which is how this bug
    shipped in the first place."""
    from ui import styles as _s
    assert "QSpinBox::up-button" not in _s.MAIN_STYLE
    assert "QSpinBox::down-button" not in _s.MAIN_STYLE
    assert "QSpinBox::up-arrow" not in _s.MAIN_STYLE
    assert "QSpinBox::down-arrow" not in _s.MAIN_STYLE


def test_network_logger_spinboxes_call_style_spinbox():
    """Source guard: the shared _spin() factory (Ping RTT / 5G Modem / Mesh
    router interval spinboxes) and log_source_panel's spinbox must call
    style_spinbox() -- a missing call silently reintroduces the invisible
    stepper bug for that specific control."""
    from pathlib import Path
    root = Path(__file__).parent.parent
    for rel in ("ui/tabs_logger.py", "ui/pages/log_source_panel.py"):
        src = (root / rel).read_text(encoding="utf-8")
        assert "_s.style_spinbox(" in src, f"{rel} does not call _s.style_spinbox()"


def test_style_spinbox_uses_plus_minus_symbols():
    """style_spinbox() must set PlusMinus centrally so every caller gets the
    clearer +/- glyph automatically (user preference over up/down arrows)."""
    from PyQt6.QtWidgets import QSpinBox, QAbstractSpinBox
    from ui import styles as _s

    spin = QSpinBox()
    try:
        _s.style_spinbox(spin)
        assert spin.buttonSymbols() == QAbstractSpinBox.ButtonSymbols.PlusMinus
    finally:
        spin.deleteLater()


def test_logger_spinboxes_use_clipping_safe_width_constants():
    """Regression: at the old width=72 (suffix spinboxes) / width=64 (plain
    spinbox), the native +/- stepper-button column overlapped the value text
    under the real "windows11" Qt style -- confirmed via live pixel
    rendering, not just geometry math (QSS padding does not reserve space
    that scales with the native button column the way the old
    `padding: ...22px...` convention assumed). ui.styles.SPINBOX_WIDTH_* are
    the minimum widths confirmed clean by that live-rendering check --
    guard against a future edit silently shrinking a call site back down."""
    from pathlib import Path
    from ui import styles as _s

    root = Path(__file__).parent.parent
    src_logger = (root / "ui" / "tabs_logger.py").read_text(encoding="utf-8")
    assert "_s.SPINBOX_WIDTH_WITH_SUFFIX" in src_logger, (
        "ui/tabs_logger.py's _spin() factory must default to "
        "_s.SPINBOX_WIDTH_WITH_SUFFIX, not a narrower hardcoded width"
    )
    assert "72)" not in src_logger.split("_log_interval")[1].split("\n")[0], (
        "Ping RTT interval spinbox must not override the width back down to 72"
    )

    src_panel = (root / "ui" / "pages" / "log_source_panel.py").read_text(encoding="utf-8")
    assert "_s.SPINBOX_WIDTH_PLAIN" in src_panel, (
        "log_source_panel.py's STP/Storm spinbox must use "
        "_s.SPINBOX_WIDTH_PLAIN, not a narrower hardcoded width"
    )

    assert _s.SPINBOX_WIDTH_WITH_SUFFIX >= 100
    assert _s.SPINBOX_WIDTH_PLAIN >= 72


def _find_spinbox_violations(path):
    """AST-based scan: for every function, find QSpinBox()-assigned locals/
    attributes and flag (a) any themed_ss()/setStyleSheet() call on that
    widget whose literal QSS string mentions "border" or "padding" -- the
    click-breaking bug described in this file's module docstring point 4 --
    and (b) any such widget with no matching style_spinbox() call at all.
    Deliberately AST-based, not regex: a regex anchored on a literal
    "QSpinBox {" selector text misses both the doubled-brace `{{ }}`
    themed_ss template form and the selector-less "bare declaration" form
    (RULE-QSS1) that most call sites in this codebase actually use."""
    import ast

    src = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError:
        return []

    def name_of(node):
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            base = name_of(node.value)
            return f"{base}.{node.attr}" if base else None
        return None

    def is_spinbox_call(node):
        return (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "QSpinBox")

    def contains_forbidden(s):
        low = s.lower()
        return ("border" in low) or ("padding" in low)

    def literal_str(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.JoinedStr):
            return "".join(
                v.value for v in node.values
                if isinstance(v, ast.Constant) and isinstance(v.value, str)
            )
        return None

    violations = []
    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        spin_vars, styled = set(), set()
        for node in ast.walk(func):
            if isinstance(node, ast.Assign) and is_spinbox_call(node.value):
                for t in node.targets:
                    n = name_of(t)
                    if n:
                        spin_vars.add(n)
            if isinstance(node, ast.Call):
                fn = node.func
                fname = fn.attr if isinstance(fn, ast.Attribute) else (
                    fn.id if isinstance(fn, ast.Name) else None)
                if fname == "style_spinbox" and node.args:
                    n = name_of(node.args[0])
                    if n:
                        styled.add(n)
                if fname == "themed_ss" and len(node.args) >= 2:
                    target = name_of(node.args[0])
                    s = literal_str(node.args[1])
                    if target in spin_vars and s and contains_forbidden(s):
                        violations.append((path, func.name, target, "themed_ss QSS has border/padding"))
                if fname == "setStyleSheet" and isinstance(fn, ast.Attribute):
                    target = name_of(fn.value)
                    if node.args:
                        s = literal_str(node.args[0])
                        if target in spin_vars and s and contains_forbidden(s):
                            violations.append((path, func.name, target, "setStyleSheet QSS has border/padding"))
        for v in spin_vars - styled:
            violations.append((path, func.name, v, "never calls style_spinbox()"))
    return violations


def test_no_qspinbox_site_in_ui_has_click_breaking_qss_or_missing_style_spinbox():
    """App-wide guard for the click-breaking bug (module docstring point 4):
    every QSpinBox() constructed anywhere under ui/ must call style_spinbox()
    and must never be styled with border/border-radius/padding QSS. Verified
    against a deliberately-broken sample file to confirm the checker actually
    catches violations (not just trivially passing on a clean tree)."""
    from pathlib import Path

    root = Path(__file__).parent.parent
    violations = []
    for f in (root / "ui").rglob("*.py"):
        violations.extend(_find_spinbox_violations(f))

    assert not violations, (
        "QSpinBox click-safety violations found (see ui/styles.py "
        "style_spinbox() docstring for the fix):\n" +
        "\n".join(f"  {p.relative_to(root)}::{fn} ({var}): {why}" for p, fn, var, why in violations)
    )
