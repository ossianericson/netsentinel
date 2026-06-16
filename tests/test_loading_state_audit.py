"""Loading state consistency audit (UX Sprint 10, S10-5).

Every page that loads data asynchronously must avoid showing a blank white
card while data loads. The approved patterns are:
  1. Skeleton rows via ``insert_skeleton_rows`` / ``clear_skeleton_rows``
  2. EmptyStateCard shown until the first result arrives (QStackedWidget page 0)
  3. MetricStore cache loaded synchronously in __init__ (no async gap)

This test validates the skeleton module API contract and checks that pages
using skeleton rows still call the correct helpers.
"""
from __future__ import annotations

from pathlib import Path

# ── Skeleton API contract ─────────────────────────────────────────────────────

def test_skeleton_module_exports():
    from ui.widgets.skeleton import (  # noqa: F401
        _SKELETON_TAG, clear_skeleton_rows, insert_skeleton_rows,
    )


def test_skeleton_tag_is_unique_string():
    from ui.widgets.skeleton import _SKELETON_TAG
    assert isinstance(_SKELETON_TAG, str) and len(_SKELETON_TAG) > 0


# ── Pages that currently use skeleton rows ────────────────────────────────────

_SKELETON_PAGES = {
    "inventory_page.py":  "insert_skeleton_rows",
    "service_page.py":    "insert_skeleton_rows",
    "threat_intel_page.py": "insert_skeleton_rows",
}

# Split-pattern: notifications insert in notifications_page.py, clear is in notif_alert_history.py mixin
_SKELETON_SPLIT: list[tuple[str, str]] = [
    ("notifications_page.py", "insert_skeleton_rows"),
    ("notif_alert_history.py", "clear_skeleton_rows"),
]


def test_skeleton_pages_still_call_insert():
    offenders = []
    for fname, fn_name in _SKELETON_PAGES.items():
        path = Path("ui/pages") / fname
        if not path.exists():
            continue
        src = path.read_text(encoding="utf-8")
        if fn_name not in src:
            offenders.append(f"{fname}: missing call to {fn_name}")
    assert not offenders, (
        "These pages must call insert_skeleton_rows before async fetch:\n"
        + "\n".join(offenders)
    )


def test_skeleton_pages_also_call_clear():
    offenders = []
    for fname in _SKELETON_PAGES:
        path = Path("ui/pages") / fname
        if not path.exists():
            continue
        src = path.read_text(encoding="utf-8")
        if "clear_skeleton_rows" not in src:
            offenders.append(f"{fname}: missing call to clear_skeleton_rows")
    assert not offenders, (
        "Pages that insert skeleton rows must also call clear_skeleton_rows:\n"
        + "\n".join(offenders)
    )


def test_split_skeleton_pattern_intact():
    """The notifications insert/clear split-mixin pattern must stay intact."""
    for fname, fn_name in _SKELETON_SPLIT:
        path = Path("ui/pages") / fname
        if not path.exists():
            continue
        src = path.read_text(encoding="utf-8")
        assert fn_name in src, (
            f"{fname} must contain {fn_name} (split skeleton pattern)"
        )


# ── No new blank-state table.clear() without skeleton cover ──────────────────

# Pages allowed to call table.clear() without a prior skeleton
# (they use cache or EmptyStateCard instead)
_ALLOWED_CLEAR_WITHOUT_SKELETON: set[str] = {
    "history_page.py",        # populated from MetricStore cache immediately
    "baseline_page.py",       # small table, fast synchronous clear-and-fill
    "cert_page.py",           # EmptyStateCard covers the empty case
    "dns_zone_page.py",       # EmptyStateCard covers the empty case
    "uptime_page.py",         # EmptyStateCard covers the empty case
    "cve_page.py",            # EmptyStateCard covers the empty case
    "connections_page.py",    # EmptyStateCard covers the empty case
    "live_bandwidth_page.py", # EmptyStateCard covers the empty case
    "trend_page.py",          # EmptyStateCard covers the empty case
    "geo_map_page.py",        # EmptyStateCard covers the empty case
    "timeline_page.py",       # EmptyStateCard covers the empty case
    "snmp_trap_page.py",      # EmptyStateCard covers the empty case
    "log_hub_page.py",        # live log view, data appended not cleared
    "home_automation_page.py", # fast local-device scan
    "wifi_monitor_page.py",   # live capture stream
    "syslog_page.py",         # live stream, no async gap
    "maintenance_page.py",    # small config table
    "overview_page.py",       # no QTableWidget
    "network_doc_page.py",    # EmptyStateCard covers the empty case
    "app_traffic_page.py",    # EmptyStateCard covers the empty case
    "dhcp_lease_page.py",     # small table, fast fill
    "ip_calculator_page.py",  # synchronous calculation
    "protocol_viz_page.py",   # no table loading
    "lab_mode_page.py",       # EmptyStateCard covers the empty case
    "troubleshoot_page.py",   # tile grid, no table
    "trigger_builder_page.py", # settings page
    "automation_page.py",     # settings page
    "diagnosis_page.py",      # scan-results flow
    "network_map_page.py",    # EmptyStateCard covers the empty case
    "service_diagnostics_page.py",  # EmptyStateCard covers the empty case
    "security_overview_page.py",    # EmptyStateCard covers the empty case
}


def test_no_new_table_clear_without_skeleton_or_allowlist():
    offenders = []
    pages_dir = Path("ui/pages")
    for path in sorted(pages_dir.glob("*.py")):
        fname = path.name
        if fname in _SKELETON_PAGES or fname in _ALLOWED_CLEAR_WITHOUT_SKELETON:
            continue
        src = path.read_text(encoding="utf-8")
        if "table.clear()" in src or "_table.clear()" in src:
            if "insert_skeleton_rows" not in src and "EmptyStateCard" not in src:
                offenders.append(fname)
    assert not offenders, (
        "New pages call table.clear() without skeleton rows or EmptyStateCard:\n"
        + "\n".join(offenders)
        + "\nAdd insert_skeleton_rows before the async fetch, or add to _ALLOWED_CLEAR_WITHOUT_SKELETON."
    )
