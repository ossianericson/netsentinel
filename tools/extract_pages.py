"""
extract_pages.py — Sprint 4 S3-1 and S3-2 extraction helpers.

Uses Python file I/O (utf-8) to avoid PowerShell encoding issues.
Run from repo root:
    python tools/extract_pages.py
"""
from pathlib import Path

ROOT = Path(__file__).parent.parent


def read_utf8(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines(keepends=False)


def write_utf8(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  Wrote {path} ({len(lines)} lines)")


# ── S3-2: overview_tile.py ─────────────────────────────────────────────────────

def extract_overview_tile() -> None:
    src = ROOT / "ui" / "pages" / "overview_page.py"
    tile_dst = ROOT / "ui" / "widgets" / "overview_tile.py"
    page_dst = src

    lines = read_utf8(src)
    print(f"overview_page.py: {len(lines)} lines")

    # Lines 0-26 are module docstring (0-indexed)
    # Lines 27+ start at the `from __future__` import block
    # tile section = lines 27..1887 (0-indexed)
    # OverviewPage starts at line 1889 (0-indexed 1888)
    tile_section = lines[27:1888]
    overview_class = lines[1888:]

    header = [
        '"""',
        "overview_tile.py — Tile widget classes for the Overview dashboard.",
        "",
        "Extracted from ui/pages/overview_page.py (Sprint 4, S3-2).",
        "OverviewPage is defined in overview_page.py and imports from here.",
        '"""',
    ]
    write_utf8(tile_dst, header + tile_section)

    # New overview_page.py: module docstring + imports + import from tile + OverviewPage
    new_imports = [
        "",
        "from __future__ import annotations",
        "",
        "import datetime",
        "from typing import Callable, Dict, List, Optional",
        "",
        "from PyQt6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QSettings, QSize, Qt, QThread, QTimer, QVariantAnimation, pyqtSignal, pyqtSlot",
        "from PyQt6.QtGui import QColor, QCursor, QPainter, QPixmap",
        "from PyQt6.QtWidgets import (",
        "    QApplication, QCheckBox, QFileDialog, QMenu,",
        "    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,",
        "    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,",
        ")",
        "",
        "from modules.metric_store import MetricStore",
        "from ui.styles import (",
        "    ACCENT, ACCENT_LITE, ACCENT_DARK, AMBER,",
        "    BG_CARD, BG_DARK, BG_HOVER, BORDER,",
        "    GREEN, RED, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,",
        ")",
        "from ui.widgets.overview_tile import (",
        "    _MIME_TYPE, _COLS, _SETTINGS_KEY, _TILE_HEIGHT, _EXPANDED_HEIGHT, _LAYOUT_VER,",
        "    _AnimatedNumberLabel, _BaseTile,",
        "    DeviceCountTile, ServiceStatusTile, TlsStatusTile, RttSummaryTile,",
        "    NetworkGradeTile, AlertFeedTile, EventFeedTile, HaDevicesTile,",
        "    LiveBandwidthTile, DnsStabilityTile, ModemSignalTile, TopTalkersTile,",
        "    RecentEventsTile, TrendStatusTile, _DnsPoller, _SecurityScanPanel,",
        "    _TILE_CLASSES, _DEFAULT_ORDER,",
        ")",
        "",
        "",
    ]
    write_utf8(page_dst, lines[0:27] + new_imports + overview_class)
    print(f"  New overview_page.py has {27 + len(new_imports) + len(overview_class)} logical lines")


# ── S3-1: hub_card.py ─────────────────────────────────────────────────────────

def extract_hub_card() -> None:
    src = ROOT / "ui" / "pages" / "hardware_integration_page.py"
    hub_dst = ROOT / "ui" / "widgets" / "hub_card.py"
    page_dst = src

    lines = read_utf8(src)
    print(f"hardware_integration_page.py: {len(lines)} lines")

    # Lines 0-85: imports (0-indexed 0..85)
    # Lines 86-2226: helpers + classes (hub card content)
    # Lines 2227+: HardwareIntegrationPage
    hub_content = lines[0:2227]  # all imports + helpers + classes

    hub_header = [
        '"""',
        "hub_card.py — HubCard widget, panel classes, and helper functions.",
        "",
        "Extracted from ui/pages/hardware_integration_page.py (Sprint 4, S3-1).",
        "HardwareIntegrationPage is defined in hardware_integration_page.py and imports from here.",
        '"""',
    ]
    # Replace the original module docstring (first triple-quoted string) with our new one
    # The original docstring ends before line 24 (approximately), then imports start
    # Find where the imports start after the docstring
    import_start = 0
    for i, line in enumerate(hub_content):
        if line.startswith("from __future__") or line.startswith("import ") and i > 5:
            import_start = i
            break

    # Write: our new header + everything from import_start onwards
    write_utf8(hub_dst, hub_header + hub_content[import_start:])

    # New hardware_integration_page.py: keep lines 0-85 (imports)
    # + import from hub_card + HardwareIntegrationPage (lines 2227+)
    page_imports = lines[0:86]
    page_class = lines[2227:]

    hub_import_block = [
        "",
        "from ui.widgets.hub_card import (",
        "    HubCard, PipInstallDialog, _PluginConnectionTester,",
        "    _CommunityIndexThread, _CommunityDownloadThread,",
        "    _btn, _instance_id,",
        "    _validate_script,",
        "    _load_paths, _save_paths,",
        "    _load_instances, _save_instances,",
        "    _is_consented, _record_consent,",
        "    _migrate_stale_paths,",
        "    _load_last_result, _save_last_result,",
        "    _record_success, _record_error, _reset_health,",
        "    _load_instance_config,",
        "    _TEMPLATE, _path_hash,",
        "    _step_card, _para, _sub_header, _copy_text, _code_chip, _prompt_block,",
        "    _ModemDetailPanel, _RouterDetailPanel, _classify_error, _safe_set_text,",
        "    _CIRCUIT_BREAK_THRESHOLD, _DEGRADED_HOURS, _load_health, _save_health,",
        ")",
        "",
        "",
    ]
    write_utf8(page_dst, page_imports + hub_import_block + page_class)
    print(f"  New hardware_integration_page.py has {len(page_imports) + len(hub_import_block) + len(page_class)} logical lines")


if __name__ == "__main__":
    print("=== S3-2: Extracting overview_tile.py ===")
    extract_overview_tile()
    print()
    print("=== S3-1: Extracting hub_card.py ===")
    extract_hub_card()
    print()
    print("Done.")
