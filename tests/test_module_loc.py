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
    # Singleton WAL-mode SQLite DB + all schema migrations + all query helpers.
    # Natural split: schema + migrations → metric_store_schema.py,
    # query helpers → metric_store_queries.py.
    "metric_store.py": 1700,
    # HTML/PDF/PNG card export + lab HTML + all save_* entry points.
    # Natural split: card generation → diagnostic_card_renderer.py,
    # lab HTML → lab_report_renderer.py.
    "report_exporter.py": 1300,
    # get_app_data_dir, is_admin, ping_sweep, plus many one-off helpers.
    # Natural split: path helpers → utils_paths.py,
    # network helpers → utils_net.py.
    "utils.py": 1100,
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

# S1 split target: dashboard.py → 3,000 lines after ui/nav/, ui/help.py,
# and ui/scan_wiring.py are extracted.  Budget is set to current actual + 200
# margin; tighten to 3,000 once the split lands.
KNOWN_LARGE_UI_FILES: dict[str, int] = {
    # Main window shell + 9-section nav builder + all scan-result handlers +
    # help panel + tray icon.  Natural split plan (S1):
    #   ui/nav/ package     — _RailButton, _FlyoutPanel, _build_pro_nav
    #   ui/help.py          — _PAGE_HELP dict, _build_help_panel, _section/_entry
    #   ui/scan_wiring.py   — all _on_*_result handlers (~2,000 lines)
    # Target after split: ≤3,000 lines.
    "dashboard.py": 13700,
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


def test_dashboard_does_not_exceed_loc_budget():
    """ui/dashboard.py must not grow beyond its tracked budget (S1 split gate).

    The current budget reflects the pre-split baseline.  After ui/nav/,
    ui/help.py, and ui/scan_wiring.py are extracted (S1), tighten this to
    3,000 lines in KNOWN_LARGE_UI_FILES to prevent re-accumulation.
    """
    offenders = []
    for name, budget in KNOWN_LARGE_UI_FILES.items():
        path = UI_ROOT / name
        if not path.exists():
            continue
        n = _line_count(path)
        if n > budget:
            offenders.append((name, n, budget))
    assert not offenders, (
        "UI files exceeding their LOC budget (file, actual, budget):\n"
        + "\n".join(f"  {name}: {actual} lines (budget {budget})" for name, actual, budget in offenders)
        + "\n\nSplit dashboard.py per the S1 plan before adding more code."
    )
