"""
RULE-UX6 structural enforcer — every text-bearing widget class the app actually
instantiates must have a rule in the global QSS.

WHY THIS EXISTS
---------------
`tests/test_contrast.py` is a hand-maintained catalogue of token pairs. It is
structurally blind to the most common colour bug in this codebase: a widget
class with *no rule at all*. When nothing styles a class there is no token pair
for anyone to add to the catalogue, so the catalogue stays green while the
widget renders from Qt's NATIVE palette — which is not theme-aware and produces
the recurring "unreadable text / wrong colours" reports.

That is exactly how unreadable dark-on-dark tabs shipped on Security Audit →
Windows Shares (SMB) and Login Test: `ui/styles.py` styled 20 widget classes and
had no `QTabBar` rule anywhere, while `ui/tabs_recon.py` created two QTabWidgets
with no inline stylesheet of their own.

THE TRAP THIS CATCHES
---------------------
Qt QSS type selectors match a class **and its subclasses**, but never its
siblings or its parent. Four real gaps found in the 2026-07-26 audit, every one
invisible to a reader skimming the QSS:

    QPlainTextEdit   sibling of QTextEdit   (both QAbstractScrollArea)
    QDoubleSpinBox   sibling of QSpinBox    (both QAbstractSpinBox)
    QDateTimeEdit    sibling of QSpinBox    (both QAbstractSpinBox)
    QToolButton      sibling of QPushButton (both QAbstractButton)

"There is already a rule for the similar-looking class" is not coverage.

HOW TO FIX A FAILURE
--------------------
Either add a rule for the class to `_build_qss()` / `get_app_qss()` in
`ui/styles.py` (preferred — makes it correct by default everywhere), or add an
entry to `_EXEMPT` below with a real reason. Do not add an exemption merely
because every current call site happens to style itself inline: the next call
site will not.
"""

from __future__ import annotations

import ast
import pathlib
import re

import pytest

UI_ROOT = pathlib.Path(__file__).resolve().parent.parent / "ui"


# ---------------------------------------------------------------------------
# Widget classes that MUST have global QSS coverage
#
# Curated rather than derived: layout classes, non-widget QObjects, and pure
# container widgets that never paint text do not need colour rules. A class
# belongs here when it renders text or a style-painted subcontrol whose colours
# come from the palette when unstyled.
# ---------------------------------------------------------------------------
_STYLING_CRITICAL: frozenset[str] = frozenset({
    # text entry
    "QLineEdit", "QTextEdit", "QPlainTextEdit",
    # numeric / date entry (QAbstractSpinBox family — all siblings)
    "QSpinBox", "QDoubleSpinBox", "QDateEdit", "QTimeEdit", "QDateTimeEdit",
    # buttons (QAbstractButton family — all siblings)
    "QPushButton", "QToolButton", "QCheckBox", "QRadioButton",
    # item views
    "QListWidget", "QTreeWidget", "QTableWidget", "QComboBox",
    # containers that paint their own chrome
    "QGroupBox", "QTabWidget", "QTabBar", "QProgressBar",
    # popups / chrome
    "QMenu", "QMenuBar", "QToolTip", "QScrollBar", "QHeaderView",
})

# Class -> reason. Every entry is a permanent hole in this net; keep it short.
# Empty is the goal state — prefer a real rule in ui/styles.py over an entry here.
_EXEMPT: dict[str, str] = {}

# ---------------------------------------------------------------------------
# Style-painted SUBCONTROLS (RULE-QSS4)
# ---------------------------------------------------------------------------
# A rule on the CLASS does not reach its subcontrols: `QMenu { background: ... }`
# styles the popup frame and says nothing about `QMenu::separator`. An unstyled
# subcontrol is painted from the native palette, which does not track the theme.
#
# This is one level below what _STYLING_CRITICAL can see, and that blind spot is
# structural, not incidental: `QMenu` passes the class-level test today because
# get_app_qss() defines `QMenu`, while 19 files called addSeparator() against a
# separator nobody had styled. Same shape as the QTabBar::tab bug that shipped
# unreadable SMB tabs.
#
# subcontrol -> owning class. The subcontrol is required whenever the owning
# class is instantiated in ui/ — same "no usage, nothing to protect" logic the
# class-level test uses, so this list never demands rules for unused widgets.
_STYLING_CRITICAL_SUBCONTROLS: dict[str, str] = {
    "QMenu::item":               "QMenu",
    "QMenu::separator":          "QMenu",
    "QTabBar::tab":              "QTabBar",
    "QTabWidget::pane":          "QTabWidget",
    "QHeaderView::section":      "QHeaderView",
    "QProgressBar::chunk":       "QProgressBar",
    "QCheckBox::indicator":      "QCheckBox",
    "QComboBox::drop-down":      "QComboBox",
    "QGroupBox::title":          "QGroupBox",
    "QScrollBar::handle":        "QScrollBar",
    "QSplitter::handle":         "QSplitter",
}


# ---------------------------------------------------------------------------
# Source scanning
# ---------------------------------------------------------------------------

def _instantiated_widget_classes() -> dict[str, set[str]]:
    """Return {ClassName: {file, ...}} for every `QFoo(...)` call in ui/.

    Also resolves `from PyQt6.QtWidgets import QTabWidget as _TW` aliases, since
    `ui/tabs_recon.py` — the file that carried the original bug — creates both
    of its unstyled tab widgets through exactly that alias.
    """
    found: dict[str, set[str]] = {}
    for path in sorted(UI_ROOT.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):  # pragma: no cover - defensive
            continue

        aliases: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("PyQt6"):
                for a in node.names:
                    if a.asname and a.name.startswith("Q"):
                        aliases[a.asname] = a.name

        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                name = aliases.get(node.func.id, node.func.id)
                if name.startswith("Q"):
                    found.setdefault(name, set()).add(
                        str(path.relative_to(UI_ROOT.parent))
                    )
    return found


_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)


def _global_qss() -> str:
    """The full application-level QSS, comments stripped."""
    from ui import styles as _s

    return _COMMENT_RE.sub("\n", _s.MAIN_STYLE + _s.get_app_qss())


# Qt base classes for the styling-critical set. A QSS type selector matches the
# named class AND its subclasses, so a rule on a base counts as coverage for
# everything beneath it -- but NEVER for a sibling. Modelling the chain here is
# what lets this test tell "QDateEdit is covered by the QDateTimeEdit rule"
# (true) apart from "QPlainTextEdit is covered by the QTextEdit rule" (false,
# and the bug this file exists to catch).
_BASES: dict[str, tuple[str, ...]] = {
    "QDateEdit":      ("QDateTimeEdit", "QAbstractSpinBox"),
    "QTimeEdit":      ("QDateTimeEdit", "QAbstractSpinBox"),
    "QDateTimeEdit":  ("QAbstractSpinBox",),
    "QSpinBox":       ("QAbstractSpinBox",),
    "QDoubleSpinBox": ("QAbstractSpinBox",),
    "QPushButton":    ("QAbstractButton",),
    "QToolButton":    ("QAbstractButton",),
    "QCheckBox":      ("QAbstractButton",),
    "QRadioButton":   ("QAbstractButton",),
    "QTextEdit":      ("QAbstractScrollArea",),
    "QPlainTextEdit": ("QAbstractScrollArea",),
    "QListWidget":    ("QListView", "QAbstractItemView"),
    "QTreeWidget":    ("QTreeView", "QAbstractItemView"),
    "QTableWidget":   ("QTableView", "QAbstractItemView"),
}
# Deliberately absent: any mapping to QWidget. Every widget derives from it, so
# listing it would make the global QWidget rule satisfy this test universally
# and silently disable the whole check.


def _has_type_selector(qss: str, cls: str) -> bool:
    """True when `cls` appears as an UNQUALIFIED type selector in some rule.

    Matches `QFoo`, `QFoo:hover`, `QFoo::item`, and `QFoo` inside a descendant
    selector, but NOT the substring hit `QFooBar` and NOT `QFoo#someName`.

    The ID exclusion matters: `QListWidget#sideNav { ... }` styles exactly one
    widget in the whole app. Counting it as coverage for QListWidget would mean
    every other list in the app could render from the native palette while this
    test stayed green — the same false-confidence failure that let the SMB tabs
    ship. General coverage requires a general selector.
    """
    for block in re.finditer(r"([^{}]*)\{[^{}]*\}", qss):
        selectors = block.group(1)
        if re.search(
            rf"(?<![A-Za-z0-9_#]){re.escape(cls)}(?![A-Za-z0-9_#])", selectors
        ):
            return True
    return False


def _selector_covers(qss: str, cls: str) -> bool:
    """True when `cls` is styled directly or through one of its Qt base classes.

    `QWidget` is deliberately NOT treated as universal coverage: the global
    `QWidget` rule sets a background and text colour, but style-painted
    subcontrols (`QTabBar::tab`, spinbox steppers, scrollbar handles) never see
    it -- which is precisely why the SMB tabs rendered from the native palette
    despite that rule existing.
    """
    if _has_type_selector(qss, cls):
        return True
    return any(_has_type_selector(qss, base) for base in _BASES.get(cls, ()))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_every_instantiated_styling_critical_class_has_global_qss():
    """The core invariant. A class the app builds but never styles is a bug."""
    used = _instantiated_widget_classes()
    qss = _global_qss()

    uncovered: list[str] = []
    for cls in sorted(_STYLING_CRITICAL):
        if cls not in used:
            continue  # not used anywhere — nothing to protect
        if cls in _EXEMPT:
            continue
        if not _selector_covers(qss, cls):
            files = sorted(used[cls])
            shown = ", ".join(files[:4]) + (" ..." if len(files) > 4 else "")
            uncovered.append(f"  {cls}  ({len(files)} file(s): {shown})")

    assert not uncovered, (
        "These widget classes are instantiated in ui/ but have NO rule in the "
        "global QSS, so they render from Qt's native palette and will be wrong "
        "in at least one theme:\n"
        + "\n".join(uncovered)
        + "\n\nAdd a rule to _build_qss() in ui/styles.py (preferred), or add an "
          "entry to _EXEMPT in this file with a real reason. Remember Qt type "
          "selectors do NOT match siblings: a QTextEdit rule never reaches "
          "QPlainTextEdit."
    )


def test_exempt_entries_are_still_used():
    """Prune the exemption list when a class stops being used.

    An exemption for a class nobody instantiates is dead weight that makes the
    net look leakier than it is.
    """
    used = _instantiated_widget_classes()
    stale = sorted(c for c in _EXEMPT if c not in used)
    assert not stale, (
        f"These _EXEMPT entries are no longer instantiated anywhere in ui/ "
        f"and should be deleted: {stale}"
    )


def test_qabstractspinbox_family_is_covered_together():
    """Regression pin for the sibling trap.

    QDateEdit/QTimeEdit derive from QDateTimeEdit, which is a SIBLING of
    QSpinBox — styling QSpinBox alone leaves all three unstyled.
    """
    qss = _global_qss()
    for cls in ("QSpinBox", "QDoubleSpinBox", "QDateTimeEdit"):
        assert _selector_covers(qss, cls), (
            f"{cls} has no global QSS rule. The QAbstractSpinBox family are "
            f"siblings — each must be named explicitly (or use "
            f"QAbstractSpinBox), a QSpinBox selector does not reach them."
        )


def test_qplaintextedit_is_covered():
    """Regression pin: QPlainTextEdit is not a QTextEdit subclass."""
    assert _selector_covers(_global_qss(), "QPlainTextEdit"), (
        "QPlainTextEdit has no global QSS rule. It is a SIBLING of QTextEdit "
        "(both derive from QAbstractScrollArea), so the QTextEdit selector "
        "does not reach it."
    )


def test_completer_popup_is_covered_globally_not_at_the_call_site():
    """Regression pin for a double-free found by bisect on 2026-07-26.

    A QCompleter's completion popup is a standalone QListView, so it needs a
    global rule. It must NOT be styled by calling `completer.popup()` at the
    call site: that constructs the popup eagerly, and the resulting top-level
    widget gets deleted by BOTH QCompleter and conftest's _flush_qt_events
    teardown sweep — aborting the whole suite thousands of tests later.
    """
    assert _has_type_selector(_global_qss(), "QListView"), (
        "No global QListView rule — a QCompleter popup would render from Qt's "
        "native palette."
    )

    offenders = [
        f"{p.relative_to(UI_ROOT.parent).as_posix()}:{i}"
        for p in UI_ROOT.rglob("*.py")
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if ".popup()" in line and "themed_ss" in line
    ]
    assert not offenders, (
        "Do not style a QCompleter popup via `.popup()` — it materialises a "
        "top-level widget that is then double-deleted (abort in the "
        "DeferredDelete drain). Rely on the global QListView rule instead.\n"
        + "\n".join(f"  {o}" for o in offenders)
    )


@pytest.mark.parametrize("cls", ["QTabWidget", "QTabBar"])
def test_tab_classes_are_covered(cls: str):
    """Regression pin for the reported SMB-tabs bug."""
    assert _selector_covers(_global_qss(), cls), (
        f"{cls} has no global QSS rule — this is the bug that shipped "
        f"unreadable tabs on Security Audit → Windows Shares (SMB)."
    )


def test_every_used_style_painted_subcontrol_has_global_qss():
    """RULE-QSS4: the class-level net above is blind one level down.

    A `QMenu` rule does not reach `QMenu::separator`; Qt paints an unstyled
    subcontrol from the native palette instead of inheriting the parent rule.
    """
    used = _instantiated_widget_classes()
    qss = _global_qss()

    uncovered: list[str] = []
    for sub, owner in sorted(_STYLING_CRITICAL_SUBCONTROLS.items()):
        if owner not in used:
            continue  # owning class never instantiated — nothing to protect
        if not _has_type_selector(qss, sub):
            n = len(used[owner])
            uncovered.append(f"  {sub}  ({owner} built in {n} file(s))")

    assert not uncovered, (
        "These style-painted subcontrols have NO rule in the global QSS, so Qt "
        "paints them from the native palette and they will be wrong in at least "
        "one theme:\n"
        + "\n".join(uncovered)
        + "\n\nA rule on the owning CLASS does not cover its subcontrols — add "
          "the subcontrol rule explicitly in _build_qss()/get_app_qss() in "
          "ui/styles.py. Inline per-site sheets still override the global rule, "
          "so a global default never removes a deliberate local deviation."
    )


def test_menu_separator_is_covered_globally():
    """Regression pin: 19 files call addSeparator(), only 4 ever styled it.

    Kept separate from the parametrised net above so the failure message names
    the specific defect rather than a generic subcontrol miss.
    """
    assert _has_type_selector(_global_qss(), "QMenu::separator"), (
        "No global QMenu::separator rule. Menus that call addSeparator() render "
        "the divider from Qt's native palette in both themes — the same defect "
        "class as the unstyled QTabBar::tab that shipped the SMB tabs bug."
    )
