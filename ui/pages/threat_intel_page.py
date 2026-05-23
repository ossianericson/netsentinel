"""
ThreatIntelPage — Threat Intelligence Feed page (item 7).

Layout:
  • KPI tiles: Total Indicators, Blocked IPs, Blocked Domains, Last Updated
  • Consent / AbuseIPDB settings card (API key stored in OS keychain)
  • Manual IP lookup card
  • Blocklist table: Indicator / Type / Categories / Source / Confidence / Last Seen
  • Toolbar: Refresh Feeds, Load from Cache, Export

All secrets (AbuseIPDB API key) stored in OS keychain (RULE 22-A).
All colours from ui/styles.py.
No blocking I/O on the main thread (all network ops in workers).
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QSettings, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from modules.threat_intel import AbuseIpDbResult, ThreatEntry, ThreatIntelDB, load_from_cache
from workers.threat_intel_worker import AbuseIpDbWorker, ThreatFeedRefreshWorker
from ui.widgets.skeleton import clear_skeleton_rows, insert_skeleton_rows
from ui.styles import (
    ACCENT,
    AMBER,
    BG_ALT_ROW,
    BG_CARD,
    BG_DARK,
    BG_HOVER,
    BORDER,
    GREEN,
    RED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TH_BG,
    TH_TEXT,
)

# ── Keyring helpers (RULE 22-A) ───────────────────────────────────────────────
_KR_SERVICE      = "NetSentinel"
_KR_ABUSE_API    = "threat/abuseipdb_key"

try:
    import keyring as _keyring
    _KEYRING_OK = True
except ImportError:
    _keyring = None  # type: ignore
    _KEYRING_OK = False


def _save_secret(key: str, value: str) -> None:
    if _KEYRING_OK and value:
        _keyring.set_password(_KR_SERVICE, key, value)
    elif _KEYRING_OK and not value:
        try:
            _keyring.delete_password(_KR_SERVICE, key)
        except Exception:
            pass


def _load_secret(key: str) -> str:
    if not _KEYRING_OK:
        return ""
    try:
        return _keyring.get_password(_KR_SERVICE, key) or ""
    except Exception:
        return ""


# ── UI helpers ────────────────────────────────────────────────────────────────

def _make_table(headers: list[str]) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.horizontalHeader().setStretchLastSection(True)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    t.verticalHeader().setVisible(False)
    t.verticalHeader().setDefaultSectionSize(24)
    t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    t.setAlternatingRowColors(True)
    t.setShowGrid(False)
    t.setStyleSheet(
        f"QTableWidget {{ background:{BG_CARD}; border:none; font-size:11px;"
        f" color:{TEXT_PRIMARY}; alternate-background-color:{BG_ALT_ROW}; }}"
        f"QHeaderView::section {{ background:{TH_BG}; color:{TH_TEXT}; font-size:11px;"
        f" font-weight:bold; padding:4px 8px; border:none; }}"
        f"QTableWidget::item:hover {{ background:{BG_HOVER}; }}"
        f"QTableWidget::item:selected {{ background:{ACCENT}; color:#fff; }}"
    )
    return t


def _cell(text: str, align=Qt.AlignmentFlag.AlignLeft) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setTextAlignment(int(align | Qt.AlignmentFlag.AlignVCenter))
    item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
    return item


def _make_kpi(label: str, value: str, color: str = ACCENT) -> QFrame:
    frame = QFrame()
    frame.setFixedHeight(60)
    frame.setStyleSheet(
        f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER};"
        f" border-left:3px solid {color}; }}"
    )
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(10, 6, 10, 6)
    lay.setSpacing(2)
    lbl = QLabel(label.upper())
    lbl.setStyleSheet(f"font-size:9px; font-weight:bold; color:{TEXT_SECONDARY}; border:none;")
    val = QLabel(value)
    val.setObjectName("kpi_value")
    val.setStyleSheet(f"font-size:22px; font-weight:bold; color:{TEXT_PRIMARY}; border:none;")
    lay.addWidget(lbl)
    lay.addWidget(val)
    return frame


def _card_frame(title: str) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setStyleSheet(f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER}; }}")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)
    hdr = QLabel(f"  {title}")
    hdr.setFixedHeight(32)
    hdr.setStyleSheet(
        f"font-size:13px; font-weight:bold; color:{TEXT_PRIMARY};"
        f" border-bottom:1px solid #ECECEC; background:{BG_CARD};"
    )
    lay.addWidget(hdr)
    return frame, lay


def _primary_btn(text: str) -> QPushButton:
    b = QPushButton(text)
    b.setFixedHeight(30)
    b.setStyleSheet(
        f"QPushButton {{ background:{ACCENT}; color:#fff; font-size:12px;"
        f" font-weight:bold; border:none; border-radius:4px; padding:0 14px; }}"
        f"QPushButton:hover {{ background:#006BBD; }}"
        f"QPushButton:disabled {{ background:#B0C4D8; color:#9BA8B4; }}"
    )
    return b


def _secondary_btn(text: str) -> QPushButton:
    b = QPushButton(text)
    b.setFixedHeight(30)
    b.setStyleSheet(
        f"QPushButton {{ background:#fff; color:{ACCENT}; font-size:12px;"
        f" border:1px solid {ACCENT}; border-radius:4px; padding:0 14px; }}"
        f"QPushButton:hover {{ background:{BG_HOVER}; }}"
        f"QPushButton:disabled {{ background:#F4F4F4; color:#9BA8B4; border-color:#B0C4D8; }}"
    )
    return b


# ── Page ─────────────────────────────────────────────────────────────────────

class ThreatIntelPage(QWidget):
    """Threat Intelligence Feed — IP/domain blocklist with AbuseIPDB lookup."""

    entries_updated = pyqtSignal(list)  # emitted after each feed load with list[ThreatEntry]
    show_on_map     = pyqtSignal(str)   # emitted when user picks "Show on Geolocation Map"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._db: Optional[ThreatIntelDB] = None
        self._refresh_worker: Optional[ThreatFeedRefreshWorker] = None
        self._abuse_worker:   Optional[AbuseIpDbWorker]          = None
        self._last_updated = ""
        self._setup_ui()
        self._restore_settings()
        # Try to load from local cache on startup (non-blocking — happens immediately)
        self._load_cache()

    # ── UI construction ───────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # Title
        title = QLabel("Threat Intelligence")
        title.setStyleSheet(f"font-size:18px; font-weight:bold; color:{TEXT_PRIMARY};")
        root.addWidget(title)

        sub = QLabel(
            "IP and domain reputation data from public OSINT feeds (Feodo Tracker, Emerging Threats). "
            "Optionally enrich with real-time AbuseIPDB lookups."
        )
        sub.setWordWrap(True)
        sub.setStyleSheet(f"font-size:11px; color:{TEXT_SECONDARY};")
        root.addWidget(sub)

        # KPI row
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(8)
        self._kpi_total   = _make_kpi("Total Indicators", "—")
        self._kpi_ips     = _make_kpi("Blocked IPs",      "—", RED)
        self._kpi_domains = _make_kpi("Blocked Domains",  "—", AMBER)
        self._kpi_updated = _make_kpi("Last Updated",     "—", GREEN)
        for w in (self._kpi_total, self._kpi_ips, self._kpi_domains, self._kpi_updated):
            kpi_row.addWidget(w)
        kpi_row.addStretch()
        root.addLayout(kpi_row)

        # Settings / consent card
        root.addWidget(self._build_settings_card())

        # Manual lookup card
        root.addWidget(self._build_lookup_card())

        # Toolbar
        tb = QHBoxLayout()
        tb.setSpacing(6)
        self._refresh_btn = _primary_btn("Update Feeds")
        self._refresh_btn.clicked.connect(self._run_refresh)
        self._cache_btn   = _secondary_btn("Load from Cache")
        self._cache_btn.clicked.connect(self._load_cache)
        self._status_lbl  = QLabel("Loading from local cache…")
        self._status_lbl.setStyleSheet(f"font-size:11px; color:{TEXT_SECONDARY};")
        tb.addWidget(self._refresh_btn)
        tb.addWidget(self._cache_btn)
        tb.addWidget(self._status_lbl)
        tb.addStretch()
        root.addLayout(tb)

        # Blocklist table card
        bl_card, bl_lay = _card_frame("Threat Indicators")
        self._table = _make_table(
            ["Indicator", "Type", "Categories", "Source", "Confidence", "Last Seen"]
        )
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_table_context_menu)
        bl_lay.addWidget(self._table)
        # Empty state shown when no blocklist data is loaded
        self._empty_lbl = QWidget()
        _el_lay = QVBoxLayout(self._empty_lbl)
        _el_lay.setContentsMargins(32, 32, 32, 32)
        _el_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _el_icon = QLabel("🧠")
        _el_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _el_icon.setStyleSheet(
            f"font-size:30px; background:transparent; border:none;"
        )
        _el_head = QLabel("No threat data loaded")
        _el_head.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _el_head.setStyleSheet(
            f"font-size:13px; font-weight:bold; color:{TEXT_PRIMARY};"
            f" background:transparent; border:none;"
        )
        _el_sub = QLabel("Download the latest IP/domain blocklists to start screening your network.")
        _el_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _el_sub.setWordWrap(True)
        _el_sub.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent; border:none;"
        )
        _el_cta = QPushButton("Update Feeds")
        _el_cta.setFixedHeight(28)
        _el_cta.setCursor(Qt.CursorShape.PointingHandCursor)
        _el_cta.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:#fff; border:none;"
            f" border-radius:4px; font-size:11px; font-weight:600; padding:0 16px; }}"
            f"QPushButton:hover {{ background:#1a6fc4; }}"
        )
        _el_cta.clicked.connect(self._run_refresh)
        _el_lay.addWidget(_el_icon)
        _el_lay.addWidget(_el_head)
        _el_lay.addSpacing(4)
        _el_lay.addWidget(_el_sub)
        _el_lay.addSpacing(10)
        _el_row = QHBoxLayout()
        _el_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _el_row.addWidget(_el_cta)
        _el_lay.addLayout(_el_row)
        bl_lay.addWidget(self._empty_lbl)
        root.addWidget(bl_card, stretch=1)

    def _build_settings_card(self) -> QWidget:
        card, lay = _card_frame("AbuseIPDB Integration (Optional)")
        body = QWidget()
        body.setStyleSheet(f"background:{BG_CARD};")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(16, 10, 16, 12)
        bl.setSpacing(6)

        self._consent_chk = QCheckBox(
            "Enable real-time AbuseIPDB lookups for public IPs during manual checks"
        )
        self._consent_chk.setStyleSheet(f"QCheckBox{{ color:{TEXT_PRIMARY}; font-size:11px; }}")
        self._consent_chk.stateChanged.connect(self._save_settings)
        bl.addWidget(self._consent_chk)

        key_row = QHBoxLayout()
        key_row.setSpacing(8)
        key_lbl = QLabel("AbuseIPDB API Key:")
        key_lbl.setFixedWidth(150)
        key_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        self._api_key_field = QLineEdit()
        self._api_key_field.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key_field.setPlaceholderText("Paste your API v2 key here")
        self._api_key_field.setFixedHeight(26)
        self._api_key_field.setStyleSheet(
            f"QLineEdit {{ border:1px solid {BORDER}; border-radius:2px; padding:0 6px;"
            f" font-size:11px; color:{TEXT_PRIMARY}; background:#fff; }}"
            f"QLineEdit:focus {{ border-color:{ACCENT}; }}"
        )
        self._api_key_field.editingFinished.connect(self._save_settings)
        key_row.addWidget(key_lbl)
        key_row.addWidget(self._api_key_field, 1)
        bl.addLayout(key_row)

        note = QLabel(
            "The API key is stored in the OS keychain (never in files or settings). "
            "Free tier: 1,000 checks/day. Register at abuseipdb.com. "
            "Only public IP addresses are ever sent — private addresses are always excluded."
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:10px;")
        bl.addWidget(note)

        lay.addWidget(body)
        return card

    def _build_lookup_card(self) -> QWidget:
        card, lay = _card_frame("Manual IP Lookup")
        body = QWidget()
        body.setStyleSheet(f"background:{BG_CARD};")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(16, 10, 16, 12)
        bl.setSpacing(6)

        row = QHBoxLayout()
        row.setSpacing(8)
        self._lookup_field = QLineEdit()
        self._lookup_field.setPlaceholderText("Enter an IP address to check")
        self._lookup_field.setFixedHeight(30)
        self._lookup_field.setFixedWidth(240)
        self._lookup_field.setStyleSheet(
            f"QLineEdit {{ border:1px solid {BORDER}; border-radius:4px; padding:0 8px;"
            f" font-size:11px; color:{TEXT_PRIMARY}; background:#fff; }}"
            f"QLineEdit:focus {{ border-color:{ACCENT}; }}"
        )
        self._lookup_field.returnPressed.connect(self._run_lookup)

        self._lookup_btn = _primary_btn("Check IP")
        self._lookup_btn.clicked.connect(self._run_lookup)

        self._lookup_result = QLabel("—")
        self._lookup_result.setWordWrap(True)
        self._lookup_result.setStyleSheet(f"font-size:11px; color:{TEXT_PRIMARY};")

        row.addWidget(self._lookup_field)
        row.addWidget(self._lookup_btn)
        row.addWidget(self._lookup_result, 1)
        bl.addLayout(row)

        lay.addWidget(body)
        return card

    # ── Settings persistence ──────────────────────────────────────────────────

    def _save_settings(self) -> None:
        qs = QSettings("NetSentinel", "NetSentinel")
        qs.setValue("threat/abuseipdb_enabled", self._consent_chk.isChecked())
        _save_secret(_KR_ABUSE_API, self._api_key_field.text())

    def _restore_settings(self) -> None:
        qs = QSettings("NetSentinel", "NetSentinel")
        self._consent_chk.setChecked(
            qs.value("threat/abuseipdb_enabled", False, type=bool)
        )
        self._api_key_field.setText(_load_secret(_KR_ABUSE_API))

    # ── Context menu ─────────────────────────────────────────────────────────

    def _on_table_context_menu(self, pos) -> None:
        row = self._table.rowAt(pos.y())
        if row < 0:
            return
        indicator_item = self._table.item(row, 0)
        itype_item     = self._table.item(row, 1)
        if indicator_item is None:
            return
        indicator = indicator_item.text()
        itype     = itype_item.text() if itype_item else ""

        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background:{BG_CARD}; color:{TEXT_PRIMARY}; border:1px solid {BORDER};"
            f" font-size:11px; }}"
            f"QMenu::item:selected {{ background:{ACCENT}; color:#fff; }}"
            f"QMenu::separator {{ height:1px; background:{BORDER}; margin:2px 0; }}"
        )

        if itype == "ip":
            act_map = menu.addAction("🌍  Show on Geolocation Map")
            act_map.triggered.connect(lambda: self.show_on_map.emit(indicator))
            menu.addSeparator()

        act_copy = menu.addAction("📋  Copy Indicator")
        act_copy.triggered.connect(lambda: QApplication.clipboard().setText(indicator))

        if itype == "ip":
            act_check = menu.addAction("🔎  Check IP (AbuseIPDB)")
            act_check.triggered.connect(lambda: self._check_ip_from_menu(indicator))

        menu.addSeparator()
        act_export = menu.addAction("↓  Export Row")
        act_export.triggered.connect(lambda: self._export_row(row))

        menu.exec(self._table.viewport().mapToGlobal(pos))

    def _check_ip_from_menu(self, ip: str) -> None:
        self._lookup_field.setText(ip)
        self._run_lookup()

    def _export_row(self, row: int) -> None:
        cols = self._table.columnCount()
        headers = [self._table.horizontalHeaderItem(c).text() for c in range(cols)]
        values  = [(self._table.item(row, c) or QTableWidgetItem("")).text()
                   for c in range(cols)]
        text = "\t".join(headers) + "\n" + "\t".join(values)
        QApplication.clipboard().setText(text)

    # ── Public API ────────────────────────────────────────────────────────────

    def check_ip(self, ip: str) -> None:
        """Pre-fill and trigger an AbuseIPDB lookup (called from other pages)."""
        self._lookup_field.setText(ip)
        self._run_lookup()

    # ── Feed operations ───────────────────────────────────────────────────────

    def _load_cache(self) -> None:
        """Load from local cache files without downloading."""
        try:
            db = ThreatIntelDB.from_cache()
            self._on_db_ready(db, from_cache=True)
        except Exception as e:
            self._status_lbl.setText(f"Cache load failed: {e}")

    def _run_refresh(self) -> None:
        if self._refresh_worker and self._refresh_worker.isRunning():
            return
        self._refresh_btn.setEnabled(False)
        self._cache_btn.setEnabled(False)
        self._status_lbl.setText("Downloading threat feeds…")
        self._refresh_worker = ThreatFeedRefreshWorker()
        self._refresh_worker.progress.connect(self._status_lbl.setText)
        self._refresh_worker.result_ready.connect(self._on_refresh_done)
        self._refresh_worker.error.connect(self._on_refresh_error)
        self._refresh_worker.start()
        insert_skeleton_rows(self._table, count=8)

    def _on_refresh_done(self, db: ThreatIntelDB) -> None:
        self._refresh_btn.setEnabled(True)
        self._cache_btn.setEnabled(True)
        self._on_db_ready(db, from_cache=False)

    def _on_refresh_error(self, msg: str) -> None:
        self._refresh_btn.setEnabled(True)
        self._cache_btn.setEnabled(True)
        self._status_lbl.setText(f"Feed refresh failed: {msg}")

    def _on_db_ready(self, db: ThreatIntelDB, from_cache: bool = False) -> None:
        self._db = db
        self._last_updated = datetime.now().strftime("%H:%M:%S")
        self._populate(db)
        source_label = "cache" if from_cache else "feeds"
        self._status_lbl.setText(
            f"{len(db)} indicator(s) loaded from {source_label}. "
            f"Last updated {self._last_updated}."
        )
        self.entries_updated.emit(db.all_entries())

    # ── Table population ──────────────────────────────────────────────────────

    def _populate(self, db: ThreatIntelDB) -> None:
        entries = db.all_entries()
        ip_count     = sum(1 for e in entries if e.itype == "ip")
        domain_count = sum(1 for e in entries if e.itype == "domain")

        def _set_kpi(frame: QFrame, value: str) -> None:
            frame.findChild(QLabel, "kpi_value").setText(value)

        _set_kpi(self._kpi_total,   str(len(entries)))
        _set_kpi(self._kpi_ips,     str(ip_count))
        _set_kpi(self._kpi_domains, str(domain_count))
        _set_kpi(self._kpi_updated, self._last_updated or "—")

        clear_skeleton_rows(self._table)
        self._table.setRowCount(0)
        self._table.setSortingEnabled(False)

        if not entries:
            self._empty_lbl.show()
            return

        self._empty_lbl.hide()
        for entry in entries:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, _cell(entry.indicator))

            type_item = _cell(entry.itype.upper(), Qt.AlignmentFlag.AlignCenter)
            type_item.setForeground(QColor(RED if entry.itype == "ip" else AMBER))
            self._table.setItem(row, 1, type_item)

            self._table.setItem(row, 2, _cell(", ".join(entry.categories)))
            self._table.setItem(row, 3, _cell(entry.source))

            conf_item = _cell(str(entry.confidence), Qt.AlignmentFlag.AlignCenter)
            if entry.confidence >= 80:
                conf_item.setForeground(QColor(RED))
            elif entry.confidence >= 50:
                conf_item.setForeground(QColor(AMBER))
            else:
                conf_item.setForeground(QColor(TEXT_SECONDARY))
            self._table.setItem(row, 4, conf_item)

            self._table.setItem(row, 5, _cell(entry.last_seen or "—"))

        self._table.setSortingEnabled(True)
        self._table.sortByColumn(4, Qt.SortOrder.DescendingOrder)

    # ── Manual lookup ─────────────────────────────────────────────────────────

    def _run_lookup(self) -> None:
        ip = self._lookup_field.text().strip()
        if not ip:
            return

        # First check local DB
        local_hit: Optional[ThreatEntry] = None
        if self._db:
            local_hit = self._db.check_ip(ip)

        if local_hit:
            cats = ", ".join(local_hit.categories) or "unknown"
            self._lookup_result.setText(
                f"<b style='color:{RED}'>THREAT</b> — found in {local_hit.source}: "
                f"{cats} (confidence: {local_hit.confidence}%)"
            )
            self._lookup_result.setTextFormat(Qt.TextFormat.RichText)
        else:
            self._lookup_result.setText(f"{ip}: not in local blocklist.")

        # AbuseIPDB (if consent given)
        if not self._consent_chk.isChecked():
            return
        api_key = _load_secret(_KR_ABUSE_API)
        if not api_key:
            self._lookup_result.setText(
                self._lookup_result.text()
                + " (AbuseIPDB: no API key configured)"
            )
            return

        if self._abuse_worker and self._abuse_worker.isRunning():
            return

        self._lookup_btn.setEnabled(False)
        self._abuse_worker = AbuseIpDbWorker(ip=ip, api_key=api_key)
        self._abuse_worker.result_ready.connect(self._on_abuse_result)
        self._abuse_worker.no_result.connect(
            lambda msg: self._on_abuse_no_result(msg, local_hit)
        )
        self._abuse_worker.error.connect(self._on_abuse_error)
        self._abuse_worker.start()

    def _on_abuse_result(self, result: AbuseIpDbResult) -> None:
        self._lookup_btn.setEnabled(True)
        score = result.abuse_score
        color = RED if score >= 25 else (AMBER if score >= 5 else GREEN)
        cats  = ", ".join(result.categories) if result.categories else "none"
        self._lookup_result.setText(
            f"<b style='color:{color}'>AbuseIPDB score: {score}/100</b> — "
            f"{result.isp} ({result.country}) | categories: {cats} | "
            f"reports: {result.total_reports}"
        )
        self._lookup_result.setTextFormat(Qt.TextFormat.RichText)

    def _on_abuse_no_result(self, msg: str, local_hit: Optional[ThreatEntry]) -> None:
        self._lookup_btn.setEnabled(True)
        base = self._lookup_result.text()
        self._lookup_result.setText(f"{base} | AbuseIPDB: {msg}")

    def _on_abuse_error(self, msg: str) -> None:
        self._lookup_btn.setEnabled(True)
        base = self._lookup_result.text()
        self._lookup_result.setText(f"{base} | AbuseIPDB error: {msg}")
