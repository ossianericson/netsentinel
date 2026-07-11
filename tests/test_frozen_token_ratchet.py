"""
Ratchet test -- the long-tail driver for the Instant Theme Switching migration.

Background
----------
~125 of 144 ui/ files destructure ``from ui.styles import ACCENT, ...`` --
those names are copied at import time. ``apply_theme()``/``apply_accent_override()``
mutate ``ui.styles`` module globals in place, but every already-imported bare
name in a consumer file stays frozen at whatever value it had when that file
was first imported. Converting a site to a live read (``from ui import styles
as _s; _s.TOKEN``) or a ``themed_ss()`` template makes it immune; until then
it is a frozen site that will show the pre-switch colour after a live theme
change.

This test locks in the CURRENT per-file frozen-site count so that:
  * no new frozen site can be added without failing CI ("convert, never
    raise the baseline"),
  * a conversion commit that lowers a file's count must also lower its
    baseline entry here in the same commit ("lower the stale baseline"),
  * a brand-new ui/ file defaults to a baseline of 0 -- new UI must be born
    live, never with fresh frozen sites.

A "frozen site" = a bare ``ast.Name`` node whose id is a key in either theme
dict in ``ui/styles.py``, outside of an import statement. This is AST-based
(not a source regex) so multi-line f-strings count every field correctly.
Converted forms are invisible to it by construction:
  * a ``themed_ss(w, "...{TOKEN}...")`` template is a *string*, not a Name
    node -- it has no bare-Name reference to count;
  * ``_s.TOKEN`` is an ``ast.Attribute`` node (attribute of the ``_s`` Name),
    never a bare ``ast.Name`` matching a theme-dict key.
Theme-INdependent constants (``CHART_DOWN``/``CHART_UP``, ``TEAL``,
``ACCENT_PURPLE``, ``MAP_LAND_*``, ``RADAR_*`` -- module assignments, not
theme-dict keys) are never counted since they are never dict keys.

Reuses the exact ``_DYNAMIC_CONSTANTS`` derivation and ``_bare_name_uses``
machinery from test_style_imports.py so both tests agree on what counts as a
dynamic style token.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
_UI_ROOT = ROOT / "ui"
_STYLES_PATH = _UI_ROOT / "styles.py"

_styles_src = _STYLES_PATH.read_text(encoding="utf-8")

# Extract keys from the theme dicts in styles.py -- the names injected into
# module globals via globals().update() at import time and on every
# apply_theme()/apply_accent_override() call. Same derivation as
# test_style_imports.py's _DYNAMIC_CONSTANTS.
_DYNAMIC_CONSTANTS: frozenset[str] = frozenset(
    re.findall(r'"([A-Z][A-Z0-9_]{2,})":', _styles_src)
)

assert len(_DYNAMIC_CONSTANTS) >= 30, (
    f"Only {len(_DYNAMIC_CONSTANTS)} dynamic constants found -- "
    "regex may have broken; check ui/styles.py theme dict format"
)


def _collect_import_lines(tree: ast.Module) -> set[int]:
    """Return the set of line numbers occupied by import statements."""
    lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for ln in range(node.lineno, node.end_lineno + 1):
                lines.add(ln)
    return lines


def _bare_name_uses(tree: ast.Module, import_lines: set[int]) -> dict[str, list[int]]:
    """Return mapping of dynamic-constant-name -> [line numbers] where the
    name appears as a bare Name node outside of import statements."""
    uses: dict[str, list[int]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Name):
            continue
        if node.id not in _DYNAMIC_CONSTANTS:
            continue
        if node.lineno in import_lines:
            continue
        uses.setdefault(node.id, []).append(node.lineno)
    return uses


def _frozen_count(path: Path) -> int:
    """Number of frozen bare-Name style-token sites in this file."""
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return 0
    import_lines = _collect_import_lines(tree)
    uses = _bare_name_uses(tree, import_lines)
    return sum(len(lines) for lines in uses.values())


def _ui_files() -> list[Path]:
    return sorted(p for p in _UI_ROOT.rglob("*.py") if p.name != "styles.py")


# Per-file baseline: {repo-relative path -> frozen-site count}.
# Every entry must equal the file's ACTUAL current count -- this is a
# ratchet, not a todo list. Unlisted files default to 0 (new UI files must
# be born live: _s.TOKEN reads and themed_ss() templates only).
#
# Regenerate with: python tests/test_frozen_token_ratchet.py
_BASELINE: dict[str, int] = {
    "ui/command_palette.py": 17,
    "ui/dashboard.py": 26,
    "ui/empty_state.py": 3,
    "ui/first_run_dialog.py": 15,
    "ui/header.py": 57,
    "ui/help_tab.py": 85,
    "ui/live_graph.py": 17,
    "ui/monitor_state.py": 64,
    "ui/nav/builder.py": 29,
    "ui/nav/lazy_page.py": 2,
    "ui/nav/rail.py": 19,
    "ui/npcap_banner.py": 8,
    "ui/pages/app_traffic_page.py": 61,
    "ui/pages/automation_page.py": 60,
    "ui/pages/baseline_page.py": 82,
    "ui/pages/cert_page.py": 43,
    "ui/pages/connections_page.py": 115,
    "ui/pages/cve_page.py": 82,
    "ui/pages/dhcp_lease_page.py": 26,
    "ui/pages/diagnosis_page.py": 157,
    "ui/pages/discover_page.py": 31,
    "ui/pages/dns_zone_page.py": 38,
    "ui/pages/geo_map_page.py": 80,
    "ui/pages/hardware_browse_mixin.py": 27,
    "ui/pages/hardware_integration_page.py": 21,
    "ui/pages/history_page.py": 63,
    "ui/pages/home_automation_page.py": 107,
    "ui/pages/home_data_mixin.py": 126,
    "ui/pages/home_page.py": 187,
    "ui/pages/home_suggestions.py": 8,
    "ui/pages/inventory_page.py": 221,
    "ui/pages/ip_calculator_page.py": 60,
    "ui/pages/lab_mode_page.py": 120,
    "ui/pages/live_bandwidth_page.py": 41,
    "ui/pages/log_hub_page.py": 64,
    "ui/pages/log_source_panel.py": 116,
    "ui/pages/maintenance_page.py": 72,
    "ui/pages/monitor_overview_page.py": 75,
    "ui/pages/mqtt_page.py": 48,
    "ui/pages/network_doc_page.py": 30,
    "ui/pages/network_map_page.py": 49,
    "ui/pages/notif_alert_history.py": 110,
    "ui/pages/notif_channel_panels.py": 72,
    "ui/pages/notif_dep_card.py": 32,
    "ui/pages/notif_extra_channels.py": 71,
    "ui/pages/notifications_page.py": 9,
    "ui/pages/ookla_cli_banner.py": 13,
    "ui/pages/overview_page.py": 98,
    "ui/pages/plugin_device_page.py": 88,
    "ui/pages/plugin_guide.py": 4,
    "ui/pages/plugin_wizard_mixin.py": 21,
    "ui/pages/protocol_viz_page.py": 54,
    "ui/pages/reports_page.py": 57,
    "ui/pages/rest_api_page.py": 49,
    "ui/pages/security_overview_page.py": 70,
    "ui/pages/service_diagnostics_page.py": 73,
    "ui/pages/service_page.py": 59,
    "ui/pages/settings_cards.py": 158,
    "ui/pages/settings_page.py": 32,
    "ui/pages/snmp_trap_page.py": 24,
    "ui/pages/speed_test_page.py": 127,
    "ui/pages/syslog_page.py": 50,
    "ui/pages/threat_intel_page.py": 74,
    "ui/pages/timeline_page.py": 35,
    "ui/pages/trend_page.py": 66,
    "ui/pages/trigger_builder_page.py": 49,
    "ui/pages/troubleshoot_page.py": 28,
    "ui/pages/uptime_page.py": 40,
    "ui/pages/wifi_heatmap_page.py": 40,
    "ui/pages/wifi_monitor_page.py": 13,
    "ui/scan_enrichment.py": 49,
    "ui/scan_wiring.py": 65,
    "ui/skeleton.py": 3,
    "ui/system_tray.py": 11,
    "ui/table_utils.py": 5,
    "ui/tabs.py": 55,
    "ui/tabs_analysis.py": 70,
    "ui/tabs_analysis_isp.py": 17,
    "ui/tabs_diag.py": 7,
    "ui/tabs_diag_extra.py": 24,
    "ui/tabs_help.py": 13,
    "ui/tabs_helpers.py": 2,
    "ui/tabs_logger.py": 50,
    "ui/tabs_monitors.py": 19,
    "ui/tabs_network.py": 28,
    "ui/tabs_recon.py": 86,
    "ui/tabs_scan.py": 59,
    "ui/theme.py": 4,
    "ui/topology_widget.py": 82,
    "ui/widgets/alert_drawer.py": 83,
    "ui/widgets/bandwidth_hog_card.py": 12,
    "ui/widgets/coach_mark.py": 7,
    "ui/widgets/column_visibility_toggle.py": 8,
    "ui/widgets/context_menu.py": 6,
    "ui/widgets/credential_dialog.py": 40,
    "ui/widgets/density_toggle.py": 8,
    "ui/widgets/device_detail_pane.py": 68,
    "ui/widgets/device_detail_panels.py": 48,
    "ui/widgets/device_popover.py": 18,
    "ui/widgets/diagnostic_card_widget.py": 16,
    "ui/widgets/empty_state_card.py": 14,
    "ui/widgets/explainer_panel.py": 18,
    "ui/widgets/feedback_dialog.py": 24,
    "ui/widgets/health_status_card.py": 36,
    "ui/widgets/home_session_widgets.py": 99,
    "ui/widgets/home_widgets.py": 30,
    "ui/widgets/hub_card.py": 145,
    "ui/widgets/hub_helpers.py": 10,
    "ui/widgets/inventory_dialogs.py": 81,
    "ui/widgets/jargon_tooltip.py": 9,
    "ui/widgets/kpi_bar.py": 23,
    "ui/widgets/modem_signal_panel.py": 18,
    "ui/widgets/objective_badge.py": 5,
    "ui/widgets/overview_tile.py": 206,
    "ui/widgets/overview_tile_monitor.py": 79,
    "ui/widgets/page_header.py": 30,
    "ui/widgets/quick_check_window.py": 15,
    "ui/widgets/scan_radar_widget.py": 5,
    "ui/widgets/scan_summary_sheet.py": 31,
    "ui/widgets/signal_bar.py": 5,
    "ui/widgets/skeleton.py": 2,
    "ui/widgets/toast.py": 17,
    "ui/widgets/usage_insights_card.py": 17,
    "ui/widgets/weekly_report_card.py": 11,
}


def test_frozen_token_count_matches_baseline():
    offenders = []
    for path in _ui_files():
        rel = path.relative_to(ROOT).as_posix()
        n = _frozen_count(path)
        baseline = _BASELINE.get(rel, 0)
        if n > baseline:
            offenders.append(
                f"{rel}: {n} frozen token site(s), baseline {baseline} -- "
                "convert, never raise the baseline"
            )
        elif n < baseline:
            offenders.append(
                f"{rel}: {n} frozen token site(s), baseline says {baseline} -- "
                "lower the stale baseline in this commit"
            )

    assert not offenders, (
        "Frozen style-token ratchet drifted from the per-file baseline in "
        "test_frozen_token_ratchet.py:\n"
        + "\n".join(f"  {o}" for o in offenders)
        + "\n\nConvert each site to a live read (`from ui import styles as _s; "
        "_s.TOKEN`) or register with `themed_ss()` per the conversion recipe "
        "in the Instant Theme Switching plan, then update the baseline entry "
        "in the same commit. Regenerate all baselines with: "
        "python tests/test_frozen_token_ratchet.py"
    )


if __name__ == "__main__":
    # Regenerate the baseline dict -- paste the printed block back into
    # _BASELINE above after any conversion commit.
    counts: dict[str, int] = {}
    for path in _ui_files():
        n = _frozen_count(path)
        if n:
            counts[path.relative_to(ROOT).as_posix()] = n
    print("_BASELINE: dict[str, int] = {")
    for rel, n in sorted(counts.items()):
        print(f'    "{rel}": {n},')
    print("}")
