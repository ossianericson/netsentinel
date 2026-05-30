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
    # S13-1 delivered: TabBuilderMixin extracted to ui/tabs.py (3,302 lines).
    # Next target: ≤3,000 lines once remaining recon tab builders are extracted.
    "dashboard.py": 6740,  # actual 6,540 + 200 margin (S13-1: TabBuilderMixin → tabs.py)

    # TabBuilderMixin: _build_tabs + all scan/log/net/tools tab content builders.
    # Next split: extract large scan_tabs (recon) and advanced_tools groups.
    "tabs.py": 3400,  # actual 3,302 + margin (S13-1 extraction)

    # Help panel: _PAGE_HELP dict + build_help_tab() + _page_header helper.
    "help.py": 1200,  # actual 1,133 + margin (S13-2 extraction)

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
    # If new scan types are added, split by domain: security_wiring.py, monitor_wiring.py.
    "scan_wiring.py": 1300,  # actual 1,274 + margin (Sprint 4 new file; S15-1)

    # Notification channel config panels.  Split target (S14-3):
    #   extract per-channel config panels → notifications_channels.py
    "pages/notifications_page.py": 2050,  # actual 2,025 + margin (S14-3 tracking)

    # Log Hub unified chronological monitor.  Split target (S14-3):
    #   extract LogSourcePanel base class → log_source_panel.py
    "pages/log_hub_page.py": 1900,  # actual 1,848 + margin (S14-3 tracking)

    # Settings page with per-section panels.  Split target (S14-3):
    #   extract per-section QWidget subclasses → settings_sections.py
    "pages/settings_page.py": 1750,  # actual 1,730 + margin (S14-3 tracking)

    # Speed test page + modem signal panel.  Split target (S14-3):
    #   extract modem signal panel → modem_signal_panel.py
    "pages/speed_test_page.py": 1600,  # actual 1,537 + margin (S14-3 tracking)

    # Feature guide with filter bar + feature card widget.  Split target (S14-3):
    #   extract feature card widget → feature_card.py
    "pages/discover_page.py": 1400,  # actual 1,358 + margin (S14-3 tracking)

    # Landing page — hero, suggestions, tips, dashboard strip, GettingStartedCard, FreshnessStrip.
    # Sprint 7 (S14-1): FreshnessStrip + GettingStartedCard + 3 standalone classes extracted
    #   to ui/widgets/home_widgets.py; home_page.py 3,032 → 2,238 lines.
    # Next target: extract RecurringSection and HeroCard sections from _setup_ui() → ≤1,500 lines.
    "pages/home_page.py": 2440,  # actual 2,238 + 200 margin (Sprint 7 S14-1)

    # home_widgets.py grew in Sprint 7 (S14-1) to hold extracted classes.
    # Further split: move welcome pages to their own files if > 1,500 lines.
    "widgets/home_widgets.py": 1370,  # actual 1,166 + 200 margin (Sprint 7 S14-1)
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
