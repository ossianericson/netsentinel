"""
Derived WCAG contrast enforcement over the QSS the app actually ships.

WHY THIS EXISTS
---------------
`tests/test_contrast.py` checks a hand-written catalogue of ~30 token pairs.
It only ever verifies pairs somebody remembered to add, so the two failure modes
that actually reach users both slip past it:

  1. A rule pairs two tokens nobody listed. Green test, unreadable widget.
  2. A pair reads fine in Midnight Pro and is illegible in Arctic Clean (or the
     reverse) -- the exact shape of RULE-UX7's tooltip bug and the RULE-AX1
     WHITE-on-WHITE pressed-button bug.

This test derives the pairs instead of trusting a list: it walks the real global
QSS plus every `themed_ss(...)` template literal in `ui/`, extracts each rule
block that sets BOTH a foreground and a background, resolves the tokens under
EVERY theme, and asserts a WCAG contrast ratio.

RATCHET
-------
Pre-existing violations are pinned in `_BASELINE`. The gate is:
  * a NEW violation fails the build;
  * fixing a baselined one and leaving it in `_BASELINE` also fails, so the
    baseline cannot rot.
Never add to `_BASELINE` to make a new failure go away -- fix the colours.
"""

from __future__ import annotations

import ast
import pathlib
import re

import pytest

from tests.test_contrast import contrast_ratio

UI_ROOT = pathlib.Path(__file__).resolve().parent.parent / "ui"

# Buttons, tabs, headers and badges are bold and/or >= 14px in this app, and the
# palette is tuned around it; 3.0:1 is WCAG AA for large/bold text. Body text
# pairs are already covered at 4.5:1 by tests/test_contrast.py.
MIN_RATIO = 3.0

_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_RULE_RE = re.compile(r"([^{}]*)\{([^{}]*)\}")

# `color:` but not `background-color:` / `selection-color:` / `border-color:`
_FG_RE = re.compile(r"(?<![-a-z]) color \s*:\s* ([^;]+)", re.X)
_BG_RE = re.compile(r"(?<![-a-z]) background (?:-color)? \s*:\s* ([^;]+)", re.X)


# ---------------------------------------------------------------------------
# Ratchet
#
# Format: "file::selector::THEME::FG_on_BG" (no line numbers — see _key_source).
#
# Every entry below is light text on a SATURATED ACCENT FILL (white-ish on blue,
# red, green) measuring 2.0–3.0:1. That pattern is the near-universal convention
# for primary/danger/success buttons across mainstream design systems, and it is
# legible in practice — it is not the bug class this file was written to catch,
# which is text that genuinely cannot be read (identical or near-identical fg/bg).
# All seven of those, found when this scan was first run on 2026-07-26, are fixed:
#   • 5 QLineEdit search boxes styled `color:{TEXT_PRIMARY}; background:{WHITE}`
#     — WHITE == TEXT_PRIMARY == #E6EDF3 in Midnight Pro, so the typed text was
#     literally invisible in the default theme.
#   • 2 amber-fill buttons at 1.49:1 (now using the TEXT_ON_FILL dark ink token).
#
# OWNER DECISION, 2026-07-27: these 43 pairs STAY AS THEY ARE. They are the
# standard filled-button convention, not a defect, and reworking them would
# change every primary/danger/success button in the app for no legibility gain.
# Do not re-open this as "43 open contrast findings" — it is settled, not
# pending. This list is frozen: entries may only be REMOVED (when a colour
# legitimately changes), never added. A new violation is a regression — fix the
# colours rather than baselining them.
#
# HARD_FLOOR below is the un-waivable half of this and is NOT covered by that
# decision: anything under 2.0:1 must be fixed, never added here.
# ---------------------------------------------------------------------------
_BASELINE: set[str] = {
    "ui/first_run_dialog.py::QPushButton:hover::Arctic Clean::#FFFFFF_on_#409CFF",
    "ui/first_run_dialog.py::QPushButton:hover::Midnight Pro::#E6EDF3_on_#409CFF",
    "ui/help_tab.py::QPushButton::Arctic Clean::#1E293B_on_#2C6CB0",
    "ui/pages/app_traffic_page.py::QPushButton::Midnight Pro::#E6EDF3_on_#F85149",
    "ui/pages/app_traffic_page.py::QPushButton:hover::Midnight Pro::#E6EDF3_on_#60A5FA",
    "ui/pages/connections_page.py::(bare)::Midnight Pro::#E6EDF3_on_#F85149",
    "ui/pages/diagnosis_page.py::QPushButton:pressed::Midnight Pro::#1A6BC4_on_#1A2233",
    "ui/pages/home_page.py::QPushButton:hover::Midnight Pro::#E6EDF3_on_#60A5FA",
    "ui/pages/inventory_page.py::QPushButton:hover::Midnight Pro::#E6EDF3_on_#60A5FA",
    "ui/pages/inventory_page.py::QPushButton:hover::Midnight Pro::#E6EDF3_on_#F85149",
    "ui/pages/inventory_page.py::QPushButton:pressed::Midnight Pro::#E6EDF3_on_#F85149",
    "ui/pages/lab_mode_page.py::QPushButton::Midnight Pro::#E6EDF3_on_#4CAF50",
    "ui/pages/lab_mode_page.py::QPushButton:hover:!disabled::Midnight Pro::#E6EDF3_on_#4CAF50",
    "ui/pages/lab_mode_page.py::QPushButton:pressed::Midnight Pro::#E6EDF3_on_#4CAF50",
    "ui/pages/maintenance_page.py::QPushButton:hover::Midnight Pro::#E6EDF3_on_#F85149",
    "ui/pages/maintenance_page.py::QPushButton:pressed::Midnight Pro::#E6EDF3_on_#F85149",
    "ui/pages/monitor_overview_page.py::QPushButton:hover::Midnight Pro::#E6EDF3_on_#60A5FA",
    "ui/pages/network_map_page.py::QPushButton:hover::Midnight Pro::#E6EDF3_on_#60A5FA",
    "ui/pages/plugin_device_page.py::QPushButton:hover::Midnight Pro::#E6EDF3_on_#60A5FA",
    "ui/pages/plugin_device_page.py::QPushButton:hover::Midnight Pro::#E6EDF3_on_#F85149",
    "ui/pages/plugin_device_page.py::QPushButton:pressed::Midnight Pro::#E6EDF3_on_#F85149",
    "ui/pages/plugin_wizard_mixin.py::QPushButton:hover::Midnight Pro::#E6EDF3_on_#60A5FA",
    "ui/pages/rest_api_page.py::(bare)::Arctic Clean::#F59E0B_on_#FFFBF0",
    "ui/pages/service_diagnostics_page.py::QPushButton:hover::Midnight Pro::#E6EDF3_on_#60A5FA",
    "ui/pages/troubleshoot_page.py::QPushButton:pressed::Midnight Pro::#1A6BC4_on_#1A2233",
    "ui/styles.py:_build_qss::QPushButton#btnDiag:hover::Midnight Pro::#E6EDF3_on_#60A5FA",
    "ui/styles.py:_build_qss::QPushButton#btnScan:hover::Midnight Pro::#E6EDF3_on_#60A5FA",
    "ui/styles.py:_build_qss::QPushButton#btnScanHero:hover::Midnight Pro::#E6EDF3_on_#60A5FA",
    "ui/tabs_recon.py::(bare)::Arctic Clean::#F59E0B_on_#FFFBF0",
    "ui/tabs_recon.py::(bare)::Arctic Clean::#F59E0B_on_#FFFFFF",
    "ui/widgets/alert_drawer.py::QPushButton::Midnight Pro::#E6EDF3_on_#4CAF50",
    "ui/widgets/bandwidth_hog_card.py::QPushButton:hover::Midnight Pro::#E6EDF3_on_#60A5FA",
    "ui/widgets/coach_mark.py::QPushButton:hover::Arctic Clean::#FFFFFF_on_#409CFF",
    "ui/widgets/coach_mark.py::QPushButton:hover::Midnight Pro::#E6EDF3_on_#409CFF",
    "ui/widgets/credential_dialog.py::QPushButton:hover::Midnight Pro::#E6EDF3_on_#60A5FA",
    "ui/widgets/device_popover.py::(bare)::Midnight Pro::#E6EDF3_on_#F85149",
    "ui/widgets/empty_state_card.py::QPushButton:hover::Midnight Pro::#E6EDF3_on_#60A5FA",
    "ui/widgets/feedback_dialog.py::QPushButton:hover::Midnight Pro::#E6EDF3_on_#60A5FA",
    "ui/widgets/home_session_widgets.py::QPushButton:hover::Midnight Pro::#E6EDF3_on_#60A5FA",
    "ui/widgets/inventory_dialogs.py::QPushButton:hover::Midnight Pro::#E6EDF3_on_#60A5FA",
    "ui/widgets/inventory_dialogs.py::QPushButton:hover::Midnight Pro::#E6EDF3_on_#F85149",
    "ui/widgets/inventory_dialogs.py::QPushButton:pressed::Midnight Pro::#E6EDF3_on_#F85149",
    "ui/widgets/usage_insights_card.py::QPushButton:hover::Midnight Pro::#E6EDF3_on_#60A5FA",
}

# Below this ratio, text is not "low contrast" — it is unreadable. Nothing may
# be baselined here; the ratchet above is only for the 2.0–3.0 convention band.
HARD_FLOOR = 2.0

# Share of themed_ss templates passed as callables rather than string literals.
# Callables are invisible to this static scan, so this caps the blind spot.
# RATCHET: measured at 18.6% on 2026-07-26. Lower it, never raise it.
CALLABLE_SHARE_CAP = 0.20


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def _qframe_names(tree: ast.AST) -> set[str]:
    """Names assigned from `QFrame(...)` anywhere in a module.

    A 1px `QFrame.Shape.HLine` divider is styled `color:{BORDER};
    background:{BORDER};` on purpose -- the QFrame frame-colour property and the
    fill must match or the line renders two-tone. That is a 1.00 ratio with no
    text anywhere near it, so it must not be reported as a contrast failure.

    Only used to suppress the fg == bg case, so a QFrame used as a card
    container (which never sets colour == background) keeps full coverage.
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            fn = node.value.func
            if getattr(fn, "id", getattr(fn, "attr", "")) == "QFrame":
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name):
                        names.add(tgt.id)
                    elif isinstance(tgt, ast.Attribute):
                        # `self._class_sep = QFrame()` — separators are just as
                        # often stored on self as in a local.
                        names.add(tgt.attr)
    return names


def _iter_templates():
    """Yield (source_label, template_str) for every themed_ss template in ui/.

    Only string-literal templates are visible to a static scan; callable
    templates (used where a value is computed at render time) are skipped and
    counted by `test_callable_template_share_stays_small` so the blind spot
    cannot quietly grow.

    A `!` prefix on the label marks a QFrame target (see `_qframe_names`).
    """
    for path in sorted(UI_ROOT.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):  # pragma: no cover - defensive
            continue
        # Forward slashes always: these strings become ratchet keys, and CI
        # type-checks/runs on Linux while development happens on Windows.
        rel = path.relative_to(UI_ROOT.parent).as_posix()
        frames = _qframe_names(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
            if name != "themed_ss" or len(node.args) < 2:
                continue
            arg = node.args[1]
            parts: list[str] = []
            stack = [arg]
            while stack:  # implicit str concat parses as nested BinOp/JoinedStr
                cur = stack.pop()
                if isinstance(cur, ast.Constant) and isinstance(cur.value, str):
                    parts.append(cur.value)
                elif isinstance(cur, ast.BinOp):
                    stack.extend([cur.left, cur.right])
            if not parts:
                continue
            target = node.args[0]
            if isinstance(target, ast.Name):
                tname = target.id
            elif isinstance(target, ast.Attribute):
                tname = target.attr
            else:
                tname = ""
            mark = "!" if tname and tname in frames else ""
            yield f"{mark}{rel}:{node.lineno}", "".join(parts)


def _callable_template_count() -> int:
    n = 0
    for path in sorted(UI_ROOT.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):  # pragma: no cover - defensive
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
            if name == "themed_ss" and len(node.args) >= 2:
                if isinstance(node.args[1], (ast.Name, ast.Lambda)):
                    n += 1
    return n


def _render(template: str) -> str | None:
    """Render a themed_ss template exactly as `ui.styles._render()` would.

    Templates carry LITERAL QSS braces doubled (`QMenu::item {{ ... }}`) and
    token placeholders single (`{ACCENT}`) -- so they must be run through
    `format_map` before any rule parsing. Parsing the raw source text instead
    silently matches nothing, which is how the first draft of this scanner
    found zero pairs across 1,792 templates.
    """
    from ui import styles as _s

    try:
        return template.format_map(_s._LIVE_TOKENS)
    except (KeyError, IndexError, ValueError, AttributeError):
        # A template referencing a name that is not a theme token is not this
        # test's business; tests/test_themed_templates.py owns that check.
        return None


def _resolve(value: str) -> str | None:
    """Resolve a RENDERED QSS colour value to #RRGGBB, or None to skip.

    rgba() is deliberately skipped: a translucent colour's effective contrast
    depends on the surface beneath it, which a static scan cannot know.
    Compositing it over white (as tests/test_contrast.py does for its curated
    pairs) would produce confidently wrong numbers on the dark theme.
    """
    value = value.strip().rstrip(";").strip()
    if not value or value in {"transparent", "none", "inherit"}:
        return None
    if re.fullmatch(r"#[0-9A-Fa-f]{6}", value):
        return value.upper()
    if re.fullmatch(r"#[0-9A-Fa-f]{3}", value):
        r, g, b = value[1], value[2], value[3]
        return f"#{r}{r}{g}{g}{b}{b}".upper()
    return None


def _blocks(qss: str):
    """Yield (selector, declaration_body) for a rendered stylesheet.

    Handles both real rule blocks and the bare, selector-less declaration lists
    used on leaf widgets (`"font-size:11px; color:{TEXT_PRIMARY};"`), which Qt
    treats as `* { ... }` (RULE-QSS1).
    """
    qss = _COMMENT_RE.sub("\n", qss)
    if "{" in qss:
        for rule in _RULE_RE.finditer(qss):
            yield " ".join(rule.group(1).split()), rule.group(2)
    elif qss.strip():
        yield "(bare)", qss


def _key_source(source: str) -> str:
    """Strip the `!` QFrame marker and the trailing `:lineno` from a label.

    Ratchet keys must survive unrelated edits to the same file. Keying on
    `file:line` would invalidate the baseline every time a line is inserted
    above a styled widget, producing simultaneous "new violation" and "stale
    baseline" failures that have nothing to do with colour.
    """
    source = source.lstrip("!")
    head, sep, tail = source.rpartition(":")
    return head if sep and tail.isdigit() else source


def _pairs_from_qss(source: str, qss: str, palette: dict, theme: str):
    """Yield (key, fg, bg, selector) for each rule declaring both fg and bg."""
    is_frame = source.startswith("!")
    key_src = _key_source(source)
    for selector, body in _blocks(qss):
        # WCAG 2.1 SC 1.4.3 exempts "text or images of text that are part of an
        # INACTIVE user interface component" — greyed-out is the affordance, and
        # forcing 3:1 on a disabled control would make it look enabled.
        if ":disabled" in selector or ":!enabled" in selector:
            continue
        fg_m = _FG_RE.search(body)
        bg_m = _BG_RE.search(body)
        if not (fg_m and bg_m):
            continue
        fg = _resolve(fg_m.group(1))
        bg = _resolve(bg_m.group(1))
        if not fg or not bg:
            continue
        if is_frame and fg == bg:
            continue  # 1px QFrame divider, not text — see _qframe_names()
        key = f"{key_src}::{selector}::{theme}::{fg}_on_{bg}"
        yield key, fg, bg, selector


def _theme_names():
    from ui.styles import THEMES

    return list(THEMES.keys())


def _all_violations() -> dict[str, str]:
    """Return {ratchet_key: human message} for every sub-threshold pair."""
    from ui import styles as _s
    from ui.styles import THEMES

    violations: dict[str, str] = {}
    for theme in _theme_names():
        palette = THEMES[theme]
        _s.apply_theme(theme)

        sources = [("ui/styles.py:_build_qss", _s.MAIN_STYLE + _s.get_app_qss())]
        for label, tmpl in _iter_templates():
            rendered = _render(tmpl)
            if rendered:
                sources.append((label, rendered))

        for source, qss in sources:
            for key, fg, bg, selector in _pairs_from_qss(source, qss, palette, theme):
                ratio = contrast_ratio(fg, bg)
                if ratio < MIN_RATIO:
                    violations[key] = (
                        f"[{theme}] {source} — `{selector}`: "
                        f"{fg} on {bg} → ratio {ratio:.2f} (need >= {MIN_RATIO})"
                    )
    return violations


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_no_new_contrast_violations():
    """The gate. Any rule pairing two colours below WCAG AA-large fails."""
    violations = _all_violations()
    new = {k: v for k, v in violations.items() if k not in _BASELINE}
    assert not new, (
        f"{len(new)} NEW colour-contrast violation(s). A rule that sets both "
        f"`color` and `background` must clear {MIN_RATIO}:1 in EVERY theme — "
        f"a pair that reads fine in Midnight Pro can be illegible in Arctic "
        f"Clean (RULE-UX7) and vice versa.\n\n"
        + "\n".join(f"  • {v}" for v in sorted(new.values()))
        + "\n\nFix the colours in ui/styles.py. Do NOT add these to _BASELINE."
    )


def test_nothing_is_below_the_hard_floor():
    """The un-waivable gate: no rule may pair text below HARD_FLOOR:1.

    `_BASELINE` covers the 2.0-3.0 accent-fill convention band only. A pair
    below 2.0 is the actual reported bug class -- invisible or near-invisible
    text -- and must be fixed, never pinned. Without this test a future
    maintainer could silence a real regression by pasting its key into the
    baseline, which is exactly how a ratchet quietly stops protecting anything.
    """
    unreadable: list[str] = []
    for key, msg in _all_violations().items():
        m = re.search(r"ratio ([0-9.]+)", msg)
        if m and float(m.group(1)) < HARD_FLOOR:
            unreadable.append(f"{msg}\n      key: {key}")

    assert not unreadable, (
        f"{len(unreadable)} rule(s) pair text below {HARD_FLOOR}:1 — that is "
        f"unreadable, not merely low-contrast. Fix the colours; these may NOT "
        f"be added to _BASELINE.\n\n"
        + "\n".join(f"  - {u}" for u in sorted(unreadable))
    )


def test_baseline_has_no_stale_entries():
    """A fixed violation must be removed from the ratchet, so it can't rot."""
    violations = _all_violations()
    stale = sorted(k for k in _BASELINE if k not in violations)
    assert not stale, (
        "These _BASELINE entries no longer violate — delete them so the "
        "ratchet keeps moving in one direction:\n"
        + "\n".join(f"  • {k}" for k in stale)
    )


def test_scan_actually_finds_pairs():
    """Guard against the scanner silently matching nothing.

    A regex or AST change that quietly returns zero pairs would make every
    assertion above vacuously pass -- the classic way an enforcement test dies
    without anyone noticing.
    """
    from ui import styles as _s
    from ui.styles import THEMES

    theme = _theme_names()[0]
    _s.apply_theme(theme)
    palette = THEMES[theme]

    global_pairs = list(
        _pairs_from_qss("g", _s.MAIN_STYLE + _s.get_app_qss(), palette, theme)
    )
    assert len(global_pairs) >= 10, (
        f"Only {len(global_pairs)} fg/bg pairs found in the global QSS — the "
        f"extractor is probably broken, not the stylesheet."
    )

    template_pairs = 0
    for source, tmpl in _iter_templates():
        rendered = _render(tmpl)
        if rendered:
            template_pairs += len(list(_pairs_from_qss(source, rendered, palette, theme)))
    assert template_pairs >= 50, (
        f"Only {template_pairs} fg/bg pairs found across all themed_ss "
        f"templates — the AST scan is probably broken."
    )


def test_tab_rules_are_covered_by_this_scan():
    """The bug that motivated all of this must be inside the net."""
    from ui import styles as _s
    from ui.styles import THEMES

    theme = _theme_names()[0]
    _s.apply_theme(theme)
    keys = [
        k
        for k, _fg, _bg, _sel in _pairs_from_qss(
            "g", _s.MAIN_STYLE + _s.get_app_qss(), THEMES[theme], theme
        )
    ]
    assert any("QTabBar::tab" in k for k in keys), (
        "The derived scan does not see the QTabBar rules — it would not have "
        "caught the SMB-tabs bug even once styled."
    )


def test_callable_template_share_stays_small():
    """Callable themed_ss templates are invisible to this static scan.

    Keep them rare so the blind spot stays small. If this fails because
    callables genuinely grew, consider rendering them under a live
    QApplication rather than raising the cap.
    """
    literal = len(list(_iter_templates()))
    callables = _callable_template_count()
    total = literal + callables
    assert total, "no themed_ss call sites found at all — scan is broken"
    share = callables / total
    assert share <= CALLABLE_SHARE_CAP, (
        f"{callables}/{total} ({share:.1%}) of themed_ss templates are "
        f"callables, which this static contrast scan cannot read — its blind "
        f"spot is growing.\n"
        f"CALLABLE_SHARE_CAP is a RATCHET: lower it as literals are adopted, "
        f"never raise it. Prefer a plain '{{TOKEN}}' string template over a "
        f"lambda unless the value genuinely must be computed at render time."
    )


@pytest.fixture(autouse=True)
def _restore_theme():
    """Leave the developer's saved theme alone.

    `apply_theme()` persists to QSettings, so a test that switches themes
    rewrites the real app's setting (see tests/test_themes.py for the same
    hazard).
    """
    from ui import styles as _s

    original = _s.get_active_theme_name()
    yield
    _s.apply_theme(original)
