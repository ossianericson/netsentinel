"""
test_nav_completeness.py

RULE-NAV1/NAV2 compliance tests (S11-4 parity gates added in Sprint 3).

There is one nav builder: _build_pro_nav(). New pages are registered there via
_nav_add_rail_item() — that is the only registration needed. _build_tabs() /
_nav_add_page() is legacy dead code for the old flat nav and must not be used
for new pages.

S11-4 gates (added Sprint 3):
  - test_all_nav_labels_have_page_help: every static nav label has a _PAGE_HELP entry
  - test_features_page_refs_are_valid_nav_labels: every _FEATURES "page" is a valid
    nav label or None
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
SRC  = (ROOT / "ui" / "dashboard.py").read_text(encoding="utf-8")
# _build_pro_nav was extracted to nav/builder.py (Sprint 19); include it for nav tests
_NAV_BUILDER_SRC = (ROOT / "ui" / "nav" / "builder.py").read_text(encoding="utf-8")
_COMBINED_SRC = SRC + "\n" + _NAV_BUILDER_SRC

sys.path.insert(0, str(ROOT))
from ui.nav.labels import NavLabel as L, NavSection as S  # noqa: E402 — needs ROOT on path


def _static_nav_labels() -> list[str]:
    """Return the ordered list of static string labels from _build_pro_nav()."""
    body = _method_body("_build_pro_nav")
    return re.findall(r'_nav_add_rail_item\(\s*"([^"]+)"', body)


def _method_body(method_name: str) -> str:
    """Return the full source of a method (up to the next same-indent def).

    Searches dashboard.py first; falls back to nav/builder.py so that
    _build_pro_nav (Sprint 19 extraction) is still found.
    """
    pattern = rf"(    def {re.escape(method_name)}\(.*?)(?=\n    def |\Z)"
    m = re.search(pattern, _COMBINED_SRC, re.DOTALL)
    assert m, f"Method {method_name!r} not found in ui/dashboard.py or ui/nav/builder.py"
    return m.group(1)


def test_no_duplicate_labels_in_pro_nav():
    """
    RULE-NAV1: _build_pro_nav() must not register the same label twice.
    Two entries for the same label would show a duplicate sidebar item.
    """
    body   = _method_body("_build_pro_nav")
    labels = re.findall(r'_nav_add_rail_item\(\s*"([^"]+)"', body)
    seen:  set[str]  = set()
    dupes: list[str] = []
    for lbl in labels:
        if lbl in seen:
            dupes.append(lbl)
        seen.add(lbl)
    assert not dupes, (
        f"_build_pro_nav() contains duplicate nav labels: {dupes}\n"
        "Each page must appear only once."
    )


def test_build_home_and_standard_nav_do_not_exist():
    """
    RULE-NAV2: _build_home_nav() and _build_standard_nav() must not exist.
    There is one nav mode. Recreating these methods causes the multi-mode bug
    where items added to one builder are invisible in the actual running app.
    """
    for dead_method in ("_build_home_nav", "_build_standard_nav"):
        assert f"def {dead_method}" not in SRC, (
            f"{dead_method}() was recreated in ui/dashboard.py.\n"
            "There is only one nav builder: _build_pro_nav(). "
            "Delete the dead method and add any pages to _build_pro_nav() instead."
        )


# ── S11-4 parity gates ────────────────────────────────────────────────────────

def test_all_nav_labels_have_page_help():
    """S11-4-1: Every static nav label has a non-empty _PAGE_HELP entry (RULE-D1)."""
    sys.path.insert(0, str(ROOT))
    from ui.help import _PAGE_HELP  # no Qt deps — pure data module

    missing = [lbl for lbl in _static_nav_labels() if lbl not in _PAGE_HELP]
    assert not missing, (
        f"Nav labels missing _PAGE_HELP entries: {missing}\n"
        'Add them to ui/help.py using the {"what": ..., "hidden": [...]} format.'
    )


def test_features_page_refs_are_valid_nav_labels():
    """S11-4-2: Every _FEATURES 'page' value is a valid nav label or None (RULE-D2).

    Reads from discover_data.py (the canonical data source) and also scans
    discover_page.py as a safety net.  The original test read only discover_page.py
    which only had 3 'page' entries — the bulk of the data lives in discover_data.py.
    """
    # Primary data source
    DISCOVER_DATA_SRC = (ROOT / "ui" / "pages" / "discover_data.py").read_text(encoding="utf-8")
    # Also check the page module itself as a safety net
    DISCOVER_PAGE_SRC = (ROOT / "ui" / "pages" / "discover_page.py").read_text(encoding="utf-8")
    nav_labels = set(_static_nav_labels())

    combined = DISCOVER_DATA_SRC + "\n" + DISCOVER_PAGE_SRC
    # Capture the full quoted label or the bare keyword None
    page_refs_raw = re.findall(r'"page"\s*:\s*("(?:[^"]+)"|None)', combined)

    stale = [
        ref.strip('"')
        for ref in page_refs_raw
        if ref != "None" and ref.strip('"') not in nav_labels
    ]
    assert not stale, (
        f"_FEATURES entries reference non-existent nav labels: {stale}\n"
        "Fix the 'page' field to match an exact _nav_add_rail_item() label, or set to None."
    )


# ── Section placement gate ────────────────────────────────────────────────────

#: Expected section for specific pages (subset — only pages where placement is
#: non-obvious or was previously wrong).  Labels not in this dict are not checked.
_EXPECTED_SECTIONS: dict[str, str] = {
    # Monitor section
    L.MONITOR_STATUS:       S.MONITOR,
    L.NETWORK_LOGGER:       S.MONITOR,
    L.NETWORK_TIMELINE:     S.MONITOR,
    L.LIVE_BANDWIDTH:       S.MONITOR,
    L.APP_TRAFFIC:          S.MONITOR,
    L.ACTIVE_CONNECTIONS:   S.MONITOR,
    L.AVAILABILITY_HISTORY: S.MONITOR,
    L.INVENTORY_CHANGES:    S.MONITOR,
    L.BANDWIDTH_USAGE:      S.MONITOR,
    L.SERVICE_HEARTBEAT:    S.MONITOR,
    L.IPV6_DEVICES:         S.MONITOR,
    L.UPTIME_SLA:           S.MONITOR,
    L.SYSLOG_VIEWER:        S.MONITOR,
    L.SNMP_TRAP_RECEIVER:   S.MONITOR,
    # Discover section
    L.DEVICES:              S.DISCOVER,
    L.NETWORK_MAP:          S.DISCOVER,
    L.WIFI_NETWORKS:        S.DISCOVER,
    L.WIFI_HEATMAP:         S.DISCOVER,
    L.DHCP_LEASES:          S.DISCOVER,
    L.DNS_ZONE_MAP:         S.DISCOVER,
    L.HOME_AUTOMATION:      S.DISCOVER,
    # Analysis section
    L.ROOT_CAUSE_CORRELATOR: S.ANALYSIS,
    L.TREND_FORECASTS:       S.ANALYSIS,
    L.SERVICE_DIAGNOSTICS:   S.ANALYSIS,
    L.GEOLOCATION_MAP:       S.ANALYSIS,
    # Security Audit section
    L.SECURITY_OVERVIEW:    S.SECURITY_AUDIT,
    L.PORT_SCAN_TCP:        S.SECURITY_AUDIT,
    # Education section
    L.PROTOCOL_VISUALIZER:  S.EDUCATION,
    L.LAB_MODE:             S.EDUCATION,
    L.FEATURE_GUIDE:        S.EDUCATION,
}


def test_nav_section_placement():
    """Pages in _EXPECTED_SECTIONS must be registered under the correct rail section."""
    body = _method_body("_build_pro_nav")

    # Build {label: section} from the nav builder source
    actual_sections: dict[str, str] = {}
    current_section = ""
    for line in body.splitlines():
        sec_m = re.search(r'_nav_begin_section\(\s*"([^"]+)"', line)
        if sec_m:
            current_section = sec_m.group(1)
            continue
        lbl_m = re.search(r'_nav_add_rail_item\(\s*"([^"]+)"', line)
        if lbl_m:
            actual_sections[lbl_m.group(1)] = current_section

    wrong = []
    for label, expected_sec in _EXPECTED_SECTIONS.items():
        actual_sec = actual_sections.get(label)
        if actual_sec is None:
            wrong.append(f"  {label!r}: not found in _build_pro_nav()")
        elif actual_sec != expected_sec:
            wrong.append(f"  {label!r}: in {actual_sec!r}, expected {expected_sec!r}")
    assert not wrong, (
        "Nav section placement errors:\n" + "\n".join(wrong) + "\n"
        "Fix: move the _nav_add_rail_item() call to the correct _nav_begin_section() block."
    )


def test_legacy_nav_add_page_labels_all_in_pro_nav():
    """Any legacy _nav_add_page() call must also have an entry in _build_pro_nav().

    _nav_add_page() is dead code from the old flat nav and silently fails at runtime.
    Pages registered *only* via _nav_add_page() are unreachable.  This gate ensures
    that every such label is also registered via the live path: _nav_add_rail_item().

    Labels that appear in _LEGACY_RENAMES have been renamed — they resolve to a current
    label and are not flagged as orphaned.
    """
    # Old nav label → current _build_pro_nav() label (pages that were simply renamed)
    _LEGACY_RENAMES: dict[str, str] = {
        "DNS & Outages":         "DNS & Stability",
        "Devices on Network":    "Devices",
        "Auto Reports":          "Scheduled Scans",
        "Threat Intelligence":   "Threat Intel",
        "TLS & exposure":        "TLS & Exposure",
        "Known CVEs":            "CVE Tracker",
        "Login Test (SSH/SMB)":  "Login Test",
    }

    TABS_SRC = (ROOT / "ui" / "tabs.py").read_text(encoding="utf-8")
    # _nav_add_page(icon, label, widget) — capture the SECOND quoted string (label)
    legacy_labels = re.findall(r'_nav_add_page\(\s*"[^"]*"\s*,\s*"([^"]+)"', TABS_SRC)
    if not legacy_labels:
        return  # no legacy calls — nothing to check

    pro_nav_labels = set(_static_nav_labels())
    orphaned = [
        lbl for lbl in legacy_labels
        if lbl not in pro_nav_labels
        and _LEGACY_RENAMES.get(lbl) not in pro_nav_labels
    ]
    assert not orphaned, (
        f"Pages registered ONLY via dead _nav_add_page() — unreachable at runtime: {orphaned}\n"
        "Add each to _build_pro_nav() via _nav_add_rail_item() under the correct section,\n"
        "or add to _LEGACY_RENAMES if the page was renamed."
    )
