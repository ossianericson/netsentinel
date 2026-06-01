"""Architectural invariant: no modules/ file may exceed RULE-AH1 (600 LOC).

When this test fails, do NOT fix it by trimming comments, collapsing
whitespace, or inlining helpers. Instead split the module at its natural
seam into two files under modules/ and update the hiddenimports in
NetSentinel.spec (RULE-B1).

Known-oversize entries are technical debt tracked here. Add a note
describing the natural split point. Remove the entry once the split lands.
"""
from __future__ import annotations

from pathlib import Path

MODULES_ROOT = Path(__file__).resolve().parents[1] / "modules"

DEFAULT_BUDGET = 600

# Files that currently exceed the default budget.
# Each entry documents WHY and WHAT the split should be.
# Budgets are set to current actuals + a small margin; tighten as splits land.
KNOWN_LARGE_MODULES: dict[str, int] = {
    # Write methods + connection management + S6 health improvements.
    # Schema/DDL/dataclasses → metric_store_schema.py (S2-1).
    # Read/query methods → metric_store_queries.py via MetricStoreQueryMixin (S2-1).
    # Slightly over 600; trim record_speed_test args or split HA methods to hit 600.
    "metric_store.py": 650,  # actual 623 + margin (was 1700; tightened S2-1)
    # Public API: save_report, save_json/csv/nmap_xml, ISP report, card, lab HTML.
    # HTML helpers → report_html.py (S2-2); PDF layout → report_pdf.py (S2-2).
    # Further split target: extract generate_isp_report → report_isp.py.
    "report_exporter.py": 750,  # actual 716 + margin (was 1300; tightened S2-2)
    # Three-tier speed test cascade (Ookla CLI + speedtest-cli + pure-Python).
    # Natural split: each backend → speed_tester_ookla.py,
    # speed_tester_lib.py, speed_tester_http.py.
    "speed_tester.py": 760,
    # Background ping logger + CSV rotation + file management.
    # Natural split: CSV writer → network_log_writer.py.
    "network_logger.py": 740,
    # AlertEngine rule evaluation + suppression + digest pipeline.
    # Natural split: suppression logic → alert_suppressor.py.
    "alert_engine.py": 700,
    # Multi-channel notification dispatch (Email/Webhook/Pushover/Ntfy/Telegram).
    # Natural split: per-channel classes → notification_channels.py.
    "notification_router.py": 680,
    # SSH/SMB/FTP/Telnet credentialed scan logic.
    # Natural split: per-protocol probers → credentialed_scan_ssh.py etc.
    "credentialed_scan.py": 670,
}


UI_ROOT = Path(__file__).resolve().parents[1] / "ui"

# S1/S13 split target: dashboard.py → 3,000 lines after ui/tabs/ package,
# ui/help.py (_build_help_tab), ui/header.py, and ui/app_settings.py are
# extracted.  Budget is set to current actual + 200; tighten after each split.
KNOWN_LARGE_UI_FILES: dict[str, int] = {
    # Main window shell + 9-section nav builder + tab builder family +
    # help panel + tray icon.  Natural split plan (S1/S13):
    #   ui/tabs/ package    — _build_tabs, _build_m1_tab, _build_logger_tab etc.
    #   ui/help.py          — _build_help_tab(), _section/_entry (S13-2)
    #   ui/header.py        — _build_header(), frameless-window logic (S13-3)
    #   ui/app_settings.py  — _restore_settings, _save_settings (S13-4)
    # Target after all splits: ≤3,000 lines.
    # Tighten after S13-1: 7,200; S13-2: 6,500; S13-3: 6,000; S13-4: 5,700
    # Sprint 18: _AnalysisTabsMixin + ScanEnrichmentMixin wired; recon tabs → tabs_recon.py;
    # mesh methods → scan_enrichment.py.  6,472 → 4,092 lines.
    # Next target: ≤3,000 lines (remaining: nav helpers, verdict/badge methods, misc handlers).
    "dashboard.py": 4292,  # actual 4,092 + 200 margin (Sprint 18)

    # TabBuilderMixin shell: _build_tabs() page factory + sidebar assembly only.
    # Sprint 8: sub-mixins extracted to tabs_scan.py, tabs_network.py, tabs_diag.py.
    # tabs.py now 949 lines — tighten further as _build_tabs() is decomposed.
    "tabs.py": 1149,  # actual 949 + 200 margin (Sprint 8 sub-mixin extraction)

    # _DiagTabsMixin — diagnostics tab only; MTR/tools inherited from _DiagExtraTabsMixin,
    # logger inherited from _LoggerTabMixin. Sprint 16: inheritance wired, duplicates removed.
    "tabs_diag.py": 333,  # actual 133 + 200 margin (Sprint 16 duplicate removal)

    # _LoggerTabMixin — network logger tab builder + handlers + retention helpers.
    # Extracted from tabs_diag.py (Sprint 15).
    "tabs_logger.py": 972,  # actual 772 + 200 margin (Sprint 15 new file; tightened Sprint 16)

    # Help panel: _PAGE_HELP dict only (build_help_tab extracted to help_tab.py, Sprint 17).
    "help.py": 684,   # actual 484 + 200 margin (Sprint 17)

    # build_help_tab() + _page_header() + _section/_entry/_subsection helpers.
    # Extracted from help.py (Sprint 17).
    "help_tab.py": 857,  # actual 657 + 200 margin (Sprint 17 new file)

    # AppHeaderMixin: header bar + frameless-window + update-check methods.
    "header.py": 700,  # actual 659 + margin (S13-3 extraction)

    # Hub card widget (HubCard, _ModemDetailPanel, _RouterDetailPanel, PipInstallDialog).
    # Helpers extracted to ui/widgets/hub_helpers.py (Sprint 6, S15-2).  Next target: ≤900.
    "widgets/hub_card.py": 1870,  # actual 1,665 + margin (Sprint 6 S15-2 split)

    # Pure data-persistence and utility helpers extracted from hub_card.py (Sprint 6, S15-2).
    "widgets/hub_helpers.py": 620,  # actual 577 + margin

    # All Overview tile classes (_BaseTile subclasses) + _TILE_CLASSES/_DEFAULT_ORDER.
    # Single concern, appropriate size for now.  Watch for growth.
    "widgets/overview_tile.py": 1950,  # actual 1,867 + margin (Sprint 4 new file; S15-1)

    # ScanResultMixin — all _on_*_result handlers (extracted from dashboard.py).
    # Sprint 18: ScanEnrichmentMixin inherited; 12 duplicate methods removed.
    # If new scan types are added, split by domain: security_wiring.py, monitor_wiring.py.
    "scan_wiring.py": 876,  # actual 676 + margin (Sprint 18 duplicate removal)

    # Notification channel config panels.  Sprint 17: duplicates removed, log panel
    # extracted to notif_alert_history.py; notif_extra_channels.py now fully wired.
    "pages/notifications_page.py": 500,  # actual 300 + 200 margin

    # _NotifChannelsMixin — keychain helpers + alert-rules + toast/webhook/email + test helpers.
    # Sprint 17: pushover/ntfy/telegram/escalation/digest removed (were duplicates);
    # log card + history methods extracted to notif_alert_history.py.
    "pages/notif_channel_panels.py": 814,  # actual 614 + 200 margin (Sprint 17)

    # _NotifAlertHistoryMixin — alert history table + delivery/retry log + bulk actions.
    # Extracted from notif_channel_panels.py (Sprint 17).
    "pages/notif_alert_history.py": 961,  # actual 761 + 200 margin (Sprint 17 new file)

    # Log Hub unified chronological monitor.  Split delivered S14-3b:
    # _LogSourcePanelMixin + shared constants/helpers → log_source_panel.py.
    # log_hub_page.py is now 892 lines.
    "pages/log_hub_page.py": 1092,  # actual 892 + 200 margin (S14-3b delivered)

    # _LogSourcePanelMixin — panel builders + source management for LogHubPage.
    # Single concern; watch for growth.
    "pages/log_source_panel.py": 1137,  # actual 937 + 200 margin (S14-3b new file)

    # Settings page with per-section panels.  Split delivered S14-3c:
    # _SettingsCardsMixin + workers + helpers → settings_cards.py.
    # settings_page.py is now 282 lines (shell only).
    "pages/settings_page.py": 482,  # actual 282 + 200 margin (S14-3c delivered)

    # _SettingsCardsMixin — all card builder methods + workers.
    # Still large; next split: extract per-section QWidget subclasses.
    "pages/settings_cards.py": 1533,  # actual 1,333 + 200 margin (S14-3c new file)

    # Hardware integration page — plugin hub shell + worker management.
    # S14-2 complete: plugin_guide.py + credential_dialog.py + plugin_wizard_mixin.py +
    #   hardware_browse_mixin.py all extracted; 1,786 → 741 lines.
    "pages/hardware_integration_page.py": 941,   # actual 741 + 200 margin (S14-2 complete)
    # New files from S14-2 extractions:
    "pages/plugin_wizard_mixin.py": 460,         # actual 260 + 200 margin
    "pages/hardware_browse_mixin.py": 701,       # actual 501 + 200 margin
    "widgets/credential_dialog.py": 490,         # actual 290 + 200 margin

    # Speed test page shell — modem signal panel extracted to ui/widgets/modem_signal_panel.py
    # in Sprint 13. If still large, extract history table → speed_test_history.py.
    "pages/speed_test_page.py": 1723,  # actual 1,523 + 200 margin

    # Feature guide shell — card widget + data list still in page.
    # Sprint 13 extracted pure _FEATURES data to discover_data.py.
    "pages/discover_page.py": 429,  # actual 229 + 200 margin (Sprint 13 extraction)

    # Pure data file: _FEATURES list + _GROUPS_ORDER for Feature Guide page.
    # 1,142 lines is expected for a 24-entry feature descriptor list with full docstrings.
    # If grows past 1,400, split by group into discover_data_security.py etc.
    "pages/discover_data.py": 1342,  # actual 1,142 + 200 margin (Sprint 13 new file)

    # Landing page — layout only; all data handlers extracted to home_data_mixin.py (Sprint 15).
    # Sprint 15: _MiniCard, _AlertRow → home_widgets.py; all handlers → home_data_mixin.py;
    #   home_page.py 2,238 → 1,128 lines. Target ≤1,200 achieved.
    "pages/home_page.py": 1328,  # actual 1,128 + 200 margin (Sprint 15)

    # _HomeDataMixin — all data handlers + public slots for HomePage (Sprint 15).
    # Natural split if needed: split update vs. scan result methods.
    "pages/home_data_mixin.py": 1107,  # actual 907 + 200 margin (Sprint 15 new file)

    # home_widgets.py — core animated widgets + grade helpers + _MiniCard/_AlertRow.
    # Sprint 17: FreshnessStrip/GettingStartedCard/_GradeBreakdownDialog/Welcome pages
    #   extracted to home_session_widgets.py; 1,316 → 524 lines.
    "widgets/home_widgets.py": 724,  # actual 524 + 200 margin (Sprint 17)

    # home_session_widgets.py — FreshnessStrip, GettingStartedCard, _GradeBreakdownDialog,
    #   StandardWelcomePage, ProWelcomePage. Extracted from home_widgets.py (Sprint 17).
    "widgets/home_session_widgets.py": 1013,  # actual 813 + 200 margin (Sprint 17 new file)

    # ── Sprint 13 new files ────────────────────────────────────────────────────
    # _PAGE_HELP dict — all page help strings for the tip bar.
    "pages/help_content.py": 688,  # actual 488 + 200 margin (Sprint 13 new file)

    # _HomeSuggestionsMixin — 'What to do next' strip logic.
    "pages/home_suggestions.py": 283,  # actual 83 + 200 margin (Sprint 13 new file)

    # _NotifExtraChannelsMixin — Pushover/Ntfy/Telegram/Escalation/WeeklyDigest builders.
    "pages/notif_extra_channels.py": 595,  # actual 395 + 200 margin (Sprint 13 new file)

    # _SettingsAppearanceMixin — appearance + display card builders.
    "pages/settings_appearance.py": 406,  # actual 206 + 200 margin (Sprint 13 new file)

    # ScanEnrichmentMixin — mesh + hardware plugin enrichment handlers + M1 table helpers.
    # Sprint 18: _apply_mesh_enrichment + _m1_* + _filter_m1_by_nl moved here from dashboard.py.
    # If grows past 1,500, split: mesh_enrichment.py (apply + m1 helpers), plugin_enrichment.py.
    "scan_enrichment.py": 1429,  # actual 1,229 + 200 margin (Sprint 18)

    # _AnalysisTabsMixin — IPv6/Cloud/Correlator/IoT/Benchmark tab builders.
    # Sprint 18: wired into TabBuilderMixin; duplicates removed from dashboard.py.
    # Natural split: extract IoT + Benchmark tabs → tabs_analysis_extra.py if > 1,000.
    "tabs_analysis.py": 1047,  # actual 847 + 200 margin (Sprint 13 new file)

    # _ReconTabsMixin — security-audit recon tab builders (SYN/UDP/OS/Risk/CVE/Exposure/
    # Cred/Discovery/SMB/Plugin/PE).  Extracted from dashboard.py (Sprint 18).
    # If grows past 1,300, split into tabs_recon_network.py + tabs_recon_access.py.
    "tabs_recon.py": 1185,  # actual 985 + 200 margin (Sprint 18 new file)

    # _DiagExtraTabsMixin — MTR tab + advanced tools tab + handlers.
    # Logger methods removed (Sprint 16) — now inherits into _DiagTabsMixin cleanly.
    "tabs_diag_extra.py": 546,  # actual 346 + 200 margin (Sprint 16 logger dead-code removal)

    # _DeviceLabelDialog, _DeviceDrawer, _ScanCompareDialog — InventoryPage helper dialogs.
    "widgets/device_detail_pane.py": 580,  # actual 380 + 200 margin (Sprint 13 new file)

    # _ModemDetailPanel, _RouterDetailPanel — hardware detail panels.
    "widgets/device_detail_panels.py": 736,  # actual 536 + 200 margin (Sprint 13 new file)

    # _KpiBarMixin — four KPI tiles for the Devices page.
    "widgets/kpi_bar.py": 341,  # actual 141 + 200 margin (Sprint 13 new file)

    # _ModemSignalPanelMixin — modem signal panel builder/updater for SpeedTestPage.
    "widgets/modem_signal_panel.py": 422,  # actual 222 + 200 margin (Sprint 13 new file)

    # Monitoring-domain tiles: LiveBandwidth, DnsStability, ModemSignal, TopTalkers, etc.
    # If grows past 1,100, split by tile domain: overview_tile_network.py etc.
    "widgets/overview_tile_monitor.py": 1007,  # actual 807 + 200 margin (Sprint 13 new file)
}

UI_DEFAULT_BUDGET = 1000  # stricter than modules for new UI files


def _line_count(path: Path) -> int:
    return sum(1 for _ in path.read_text(encoding="utf-8", errors="replace").splitlines())


def test_no_module_exceeds_loc_budget():
    """No file in modules/ may grow past its LOC budget (RULE-AH1: 600 lines).

    Offenders are listed with their actual line count and budget so the
    next split is easy to target.
    """
    offenders = []
    for path in sorted(MODULES_ROOT.glob("*.py")):
        name = path.name
        budget = KNOWN_LARGE_MODULES.get(name, DEFAULT_BUDGET)
        n = _line_count(path)
        if n > budget:
            offenders.append((name, n, budget))

    assert not offenders, (
        "Modules exceeding LOC budget (file, actual, budget):\n"
        + "\n".join(f"  {name}: {actual} lines (budget {budget})" for name, actual, budget in offenders)
        + "\n\nDo NOT fix by trimming cosmetically. Split at the natural seam "
        "described in KNOWN_LARGE_MODULES, then update hiddenimports in "
        "NetSentinel.spec (RULE-B1)."
    )


def test_known_large_modules_budgets_are_current():
    """Budgets in KNOWN_LARGE_MODULES must be >= actual line count.

    If a file shrank below its exception budget after a split, remove or
    tighten its entry so the exception list doesn't hide future growth.
    """
    stale = []
    for name, budget in KNOWN_LARGE_MODULES.items():
        path = MODULES_ROOT / name
        if not path.exists():
            stale.append((name, "file no longer exists — remove from KNOWN_LARGE_MODULES"))
            continue
        n = _line_count(path)
        if n <= DEFAULT_BUDGET:
            stale.append((name, f"now {n} lines — at or below default budget, remove exception"))
        elif n > budget:
            stale.append((name, f"grew to {n} lines — raise budget or split"))

    assert not stale, (
        "Stale KNOWN_LARGE_MODULES entries:\n"
        + "\n".join(f"  {name}: {reason}" for name, reason in stale)
    )


def test_large_ui_files_do_not_exceed_loc_budget():
    """Tracked ui/ files must not grow beyond their LOC budgets (S1/S13/S14/S15 gate).

    Keys in KNOWN_LARGE_UI_FILES are paths relative to the ui/ directory
    (e.g. "dashboard.py", "widgets/hub_card.py", "pages/log_hub_page.py").
    Budget is set to current_actual + 200 margin; tighten after each split.
    """
    offenders = []
    for rel_path, budget in KNOWN_LARGE_UI_FILES.items():
        path = UI_ROOT / rel_path
        if not path.exists():
            continue
        n = _line_count(path)
        if n > budget:
            offenders.append((rel_path, n, budget))
    assert not offenders, (
        "UI files exceeding their LOC budget (file, actual, budget):\n"
        + "\n".join(f"  ui/{rel}: {actual} lines (budget {budget})" for rel, actual, budget in offenders)
        + "\n\nSplit per the S1/S13/S14/S15 plan in STABILITY_PLAN.md before adding more code."
    )
