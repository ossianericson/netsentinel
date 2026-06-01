"""
S10-1 — Hardcoded hex-colour inventory (prereq for the purge sprint).

Scans ui/ and modules/ for raw hex colour strings (#RRGGBB / #RGB) that appear
outside the canonical sources (ui/styles.py and modules/colours.py).

These are RULE-AH3 violations:
  • ui/**/*.py colours  →  must use tokens from ui/styles.py
  • modules/**/*.py colours  →  must use tokens from modules/colours.py

This test establishes a per-file budget at the current violation count so:
  1. No new violations can be introduced without raising the budget.
  2. Each purge sprint lowers the budgets toward zero.

To update a budget after a purge:
  • Lower the number in _UI_BUDGETS or _MODULE_BUDGETS.
  • Never raise a budget — add the token to ui/styles.py or modules/colours.py instead.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent

# ── Pattern ───────────────────────────────────────────────────────────────────
# Match 3- or 6-digit hex colour literals: #FFF  #FFFFFF
# Exclude 7+ char runs (e.g. git SHAs) by bounding after 3 or 6 hex digits
_HEX_RE = re.compile(r'#[0-9A-Fa-f]{6}\b|#[0-9A-Fa-f]{3}\b')

# ── Budgets (current violation counts — ratchet these down during the purge) ──

_UI_BUDGETS: dict[str, int] = {
    # Canonical source — always exempt
    "ui/styles.py": 9999,

    # Sprint 12: all previously-budgeted UI files purged to 0.
    # Budgets lowered from Sprint 10-1 baseline → 0 (ratchet locked).
    "ui/widgets/protocol_canvas.py": 0,    # was 16
    "ui/pages/settings_cards.py": 0,       # was 16
    "ui/pages/threat_intel_page.py": 0,
    "ui/first_run_dialog.py": 0,           # was 18
    "ui/pages/home_page.py": 0,
    "ui/pages/dns_zone_page.py": 0,
    "ui/pages/ookla_cli_banner.py": 0,     # was 12
    "ui/pages/baseline_page.py": 0,        # was 11
    "ui/widgets/coach_mark.py": 0,         # was 10
    "ui/pages/inventory_page.py": 0,       # was 8
    "ui/widgets/overview_tile.py": 0,      # was 8
    "ui/dashboard.py": 0,                  # was 7
    "ui/pages/reports_page.py": 0,         # was 7
    "ui/pages/dhcp_lease_page.py": 0,
    "ui/pages/cve_page.py": 0,             # was 6
    "ui/pages/geo_map_page.py": 0,         # was 6
    "ui/pages/ip_calculator_page.py": 0,   # was 6
    "ui/pages/log_source_panel.py": 0,     # was 6
    "ui/pages/notif_channel_panels.py": 0, # was 6
    "ui/pages/notif_alert_history.py": 0,  # Sprint 17 new file
    "ui/pages/diagnosis_page.py": 0,
    "ui/pages/trigger_builder_page.py": 0, # was 5
    "ui/pages/protocol_viz_page.py": 0,    # was 5
    "ui/pages/log_hub_page.py": 0,         # was 5
    "ui/nav/rail.py": 0,                   # was 5
    "ui/tabs.py": 0,                        # was 5
    "ui/tabs_scan.py": 0,                  # was 4
    "ui/pages/automation_page.py": 0,      # was 4
    "ui/pages/lab_mode_page.py": 0,        # was 4
    "ui/pages/overview_page.py": 0,        # was 4
    "ui/pages/rest_api_page.py": 0,        # was 4
    "ui/pages/speed_test_page.py": 0,      # was 4
    "ui/pages/wifi_heatmap_page.py": 0,    # was 4
    "ui/live_graph.py": 0,                 # was 4
    "ui/pages/history_page.py": 0,         # was 3
    "ui/pages/home_automation_page.py": 0, # was 3
    "ui/pages/syslog_page.py": 0,          # was 3
    "ui/widgets/home_widgets.py": 0,       # was 3
    "ui/widgets/home_session_widgets.py": 0,  # Sprint 17 new file
    "ui/widgets/hub_card.py": 0,           # was 3
    "ui/npcap_banner.py": 0,               # was 2
    "ui/pages/cert_page.py": 0,            # was 2
    "ui/pages/connections_page.py": 0,     # was 2
    "ui/pages/discover_page.py": 0,        # was 2
    "ui/pages/live_bandwidth_page.py": 0,  # was 2
    "ui/pages/plugin_device_page.py": 0,   # was 2
    "ui/pages/security_overview_page.py": 0, # was 2
    "ui/pages/service_page.py": 0,         # was 2
    "ui/pages/uptime_page.py": 0,          # was 2
    "ui/system_tray.py": 0,                # was 2
    "ui/tabs_helpers.py": 0,               # was 2
    "ui/pages/hardware_browse_mixin.py": 0, # was 1
    "ui/pages/mqtt_page.py": 0,            # was 1
    "ui/pages/settings_page.py": 0,        # was 1
    "ui/pages/snmp_trap_page.py": 0,       # was 1
    "ui/pages/timeline_page.py": 0,        # was 1
    "ui/widgets/density_toggle.py": 0,     # was 1
    "ui/widgets/explainer_panel.py": 0,    # was 1
    "ui/widgets/page_header.py": 0,        # was 1
    "ui/widgets/pulsing_dot.py": 0,        # was 1
}

_MODULE_BUDGETS: dict[str, int] = {
    # Canonical source — always exempt
    "modules/colours.py": 9999,

    # HTML/CSS report generators — violations should migrate to modules/colours.py
    # Lower these numbers as each purge PR lands.
    "modules/digest_builder.py": 34,
    "modules/report_scheduler.py": 30,
    "modules/web_dashboard.py": 21,
    "modules/report_html.py": 22,
    "modules/net_doc_generator.py": 13,
    "modules/report_exporter.py": 0,
    "modules/report_isp.py": 4,   # inherited from report_exporter.py split (S20-5)
    "modules/network_benchmark.py": 1,
}

_DEFAULT_BUDGET = 0  # any file not listed must have zero violations


def _count_hex_in_file(path: Path) -> int:
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0
    # Strip comments to avoid false positives in docstrings / line comments
    # Keep only non-comment lines for the count
    lines = source.splitlines()
    total = 0
    for line in lines:
        # Strip inline comment portion
        code = line.split("#")[0] if "#" not in line[:line.find("#")+1].replace("#", "", 1) else line
        # Simpler: count occurrences of _HEX_RE anywhere on the line
        total += len(_HEX_RE.findall(line))
    return total


def _count_hex(path: Path) -> int:
    """Count hex colour literals in a Python source file."""
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0
    return len(_HEX_RE.findall(source))


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_ui_hardcoded_hex_within_budget():
    """No UI file may exceed its per-file hex colour budget."""
    offenders = []
    for path in sorted((ROOT / "ui").rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        budget = _UI_BUDGETS.get(rel, _DEFAULT_BUDGET)
        count = _count_hex(path)
        if count > budget:
            offenders.append((rel, count, budget))

    assert not offenders, (
        "Hardcoded hex colours exceed budget — add tokens to ui/styles.py:\n"
        + "\n".join(f"  {f}: {c} (budget {b})" for f, c, b in offenders)
    )


def test_modules_hardcoded_hex_within_budget():
    """No module file may exceed its per-file hex colour budget."""
    offenders = []
    for path in sorted((ROOT / "modules").rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        budget = _MODULE_BUDGETS.get(rel, _DEFAULT_BUDGET)
        count = _count_hex(path)
        if count > budget:
            offenders.append((rel, count, budget))

    assert not offenders, (
        "Hardcoded hex colours exceed budget — add tokens to modules/colours.py:\n"
        + "\n".join(f"  {f}: {c} (budget {b})" for f, c, b in offenders)
    )


def test_inventory_totals_documented():
    """Verify the budget tables are complete — every file with violations is listed."""
    ui_unlisted = []
    for path in sorted((ROOT / "ui").rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if rel in _UI_BUDGETS:
            continue
        count = _count_hex(path)
        if count > 0:
            ui_unlisted.append((rel, count))

    module_unlisted = []
    for path in sorted((ROOT / "modules").rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if rel in _MODULE_BUDGETS:
            continue
        count = _count_hex(path)
        if count > 0:
            module_unlisted.append((rel, count))

    all_unlisted = ui_unlisted + module_unlisted
    assert not all_unlisted, (
        "New hardcoded-hex violations found in files not in the budget table.\n"
        "Add to _UI_BUDGETS or _MODULE_BUDGETS with count=0 or fix the violation:\n"
        + "\n".join(f"  {f}: {c}" for f, c in all_unlisted)
    )
