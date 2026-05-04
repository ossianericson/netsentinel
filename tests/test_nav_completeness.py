"""
test_nav_completeness.py

RULE-NAV1 compliance test.

Every page registered in _build_tabs() via _nav_add_page() must be reachable
via _nav_ref() in at least one of the three mode nav builders:
  _build_home_nav / _build_standard_nav / _build_pro_nav

How this works
--------------
1. Extract the body of _build_tabs() and find every _nav_add_page("icon", "label", WIDGET).
2. Normalise WIDGET: local variables used in _build_tabs (m1→self._m1_tab, etc.)
   are resolved to their self._ attribute names using the known mapping below.
3. Extract the bodies of the three mode nav builders and find every
   _nav_ref("icon", "label", WIDGET) call.
4. Assert that every widget from step 1 appears in at least one of the three
   mode nav builder sets.

If this test fails it means a page was registered in _build_tabs() (so it exists
in the QStackedWidget) but is not reachable from the sidebar in any user-facing
mode.  Fix: add it to _build_standard_nav() and/or _build_pro_nav().
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
SRC  = (ROOT / "ui" / "dashboard.py").read_text(encoding="utf-8")

# ── Local variable → self attribute mapping for _build_tabs() ─────────────────
# These local vars are created early in _build_tabs() and assigned to
# self._ attributes later in the same method.  _nav_add_page() calls in
# _build_tabs() use the local names; mode builders use the self._ names.
_LOCAL_TO_SELF = {
    "m1":  "self._m1_tab",
    "m2":  "self._m2_tab",
    "m3":  "self._m3_tab",
    "m4":  "self._m4_tab",
    "m5":  "self._m5_tab",
    "net": "self._net_tab",
    "dia": "self._dia_tab",
    "log": "self._log_tab",
}

# Pages that are intentionally absent from mode nav builders because they are
# only accessible via dedicated buttons/links (never the sidebar directly).
# Keep this set as small as possible — every entry is a discoverability gap.
_INTENTIONALLY_UNLISTED: set[str] = set()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _method_body(method_name: str) -> str:
    """Return the full source of a method (up to the next same-indent def)."""
    pattern = rf"(    def {re.escape(method_name)}\(.*?)(?=\n    def |\Z)"
    m = re.search(pattern, SRC, re.DOTALL)
    assert m, f"Method {method_name!r} not found in ui/dashboard.py"
    return m.group(1)


def _extract_widgets(body: str, call_name: str) -> set[str]:
    """
    Extract the last positional argument from every call_name(...) call.
    Handles both self._attr forms and local variable names (resolved via
    _LOCAL_TO_SELF).  Skips non-self-attribute arguments.
    """
    found: set[str] = set()
    # Match single-line calls only (all _nav_add_page/_nav_ref calls are single-line).
    pattern = rf"{re.escape(call_name)}\(([^)]+)\)"
    for m in re.finditer(pattern, body):
        args_str = m.group(1)
        # Split by comma — last token is the widget argument
        parts = [p.strip() for p in args_str.split(",")]
        last = parts[-1] if parts else ""
        last = last.strip("() ")
        resolved = _LOCAL_TO_SELF.get(last, last)
        if resolved.startswith("self._"):
            found.add(resolved)
    return found


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_all_nav_pages_accessible_in_mode_builders():
    """
    RULE-NAV1: every page registered in _build_tabs() must be reachable
    via _nav_ref() in at least one of the three mode nav builders.
    """
    build_tabs   = _method_body("_build_tabs")
    registered   = _extract_widgets(build_tabs, "_nav_add_page")

    home_nav     = _method_body("_build_home_nav")
    standard_nav = _method_body("_build_standard_nav")
    pro_nav      = _method_body("_build_pro_nav")

    accessible = (
        _extract_widgets(home_nav,     "_nav_ref") |
        _extract_widgets(standard_nav, "_nav_ref") |
        _extract_widgets(pro_nav,      "_nav_ref")
    )

    missing = registered - accessible - _INTENTIONALLY_UNLISTED

    assert not missing, (
        f"\nRULE-NAV1 violation — {len(missing)} page(s) are registered in "
        f"_build_tabs() but not reachable from any mode nav builder:\n\n"
        + "\n".join(f"  {w}" for w in sorted(missing))
        + "\n\nFor each missing page, add it to _build_standard_nav() (and "
        "_build_pro_nav() if appropriate) using self._nav_ref(icon, label, WIDGET).\n"
        "If a page is intentionally nav-unlisted, add it to "
        "_INTENTIONALLY_UNLISTED in this test file with a comment explaining why."
    )


def test_no_duplicate_labels_in_mode_builders():
    """
    Each of the three mode builders should not register the same label twice
    within itself — that would create two sidebar entries for the same page.
    """
    for builder in ("_build_home_nav", "_build_standard_nav", "_build_pro_nav"):
        body   = _method_body(builder)
        labels = re.findall(r'_nav_ref\([^,]+,\s*"([^"]+)"', body)
        seen: set[str] = set()
        dupes: list[str] = []
        for lbl in labels:
            if lbl in seen:
                dupes.append(lbl)
            seen.add(lbl)
        assert not dupes, (
            f"{builder}() contains duplicate nav labels: {dupes}\n"
            "Each page should appear only once in a mode nav builder."
        )


def test_home_nav_stays_minimal():
    """
    Home mode is intentionally a simplified 5-6 item nav.
    If it grows beyond 10 nav_ref entries the simplification promise is broken.
    """
    body  = _method_body("_build_home_nav")
    count = len(re.findall(r"_nav_ref\(", body))
    assert count <= 10, (
        f"_build_home_nav() has {count} _nav_ref entries — expected ≤ 10.\n"
        "Home mode is meant to be a minimal nav for new users.  Move additional "
        "pages to _build_standard_nav() instead."
    )
