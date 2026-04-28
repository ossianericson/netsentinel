"""One-shot patch: replace old inline filter+spinboxes+checkboxes with ribbon layout."""
import pathlib, sys

TARGET = pathlib.Path(__file__).parent.parent / "ui" / "dashboard.py"
text = TARGET.read_text(encoding="utf-8")

# ── locate the block we need to replace ──────────────────────────────────────
START_MARKER = "        # ── Filter input (top-bar utility ribbon"
END_MARKER   = "        for c in (self._chk_stp, self._chk_storm, self._chk_wifi, self._chk_dns):\n            lay.addWidget(c)\n"

start = text.find(START_MARKER)
if start == -1:
    print("START MARKER NOT FOUND — trying alternate")
    START_MARKER = "        # ── Filter input"
    start = text.find(START_MARKER)

end = text.find(END_MARKER)
if end == -1:
    print("END MARKER NOT FOUND")
    sys.exit(1)

end += len(END_MARKER)
print(f"Replacing chars {start}–{end}")
print("Old snippet preview:", repr(text[start:start+80]))

NEW_BLOCK = '''\
        # ── Filter input — expands to fill all middle space ──────────────────
        _sep0 = QFrame()
        _sep0.setFrameShape(QFrame.Shape.VLine)
        _sep0.setStyleSheet(f"background:{SIDEBAR_HOVER}; max-width:1px; border:none;")
        lay.addWidget(_sep0)

        from PyQt6.QtWidgets import QSizePolicy as _QSP
        self._m1_search = QLineEdit()
        self._m1_search.setPlaceholderText("\\U0001f50d  Filter devices\\u2026")
        self._m1_search.setFixedHeight(34)
        self._m1_search.setMinimumWidth(180)
        self._m1_search.setSizePolicy(_QSP.Policy.Expanding, _QSP.Policy.Fixed)
        self._m1_search.setStyleSheet(
            f"QLineEdit {{ background:{SIDEBAR_HOVER}; color:{WHITE};"
            f" border:1px solid {SIDEBAR_SECTION_BG}; border-radius:3px;"
            " padding:0 10px; font-size:11px; }"
            f"QLineEdit:focus {{ border-color:{ACCENT}; }}"
        )
        self._m1_search.textChanged.connect(self._filter_m1_by_nl)
        lay.addWidget(self._m1_search, 1)

        # ── Scan Settings dropdown ────────────────────────────────────────────
        from PyQt6.QtWidgets import QMenu, QWidgetAction, QToolButton

        _spin_qss = (
            f"QSpinBox {{ background:{SIDEBAR_HOVER}; color:{WHITE};"
            f" border:1px solid {SIDEBAR_SECTION_BG}; border-radius:3px; font-size:11px;"
            f" padding:0 2px; }}"
            f"QSpinBox::up-button, QSpinBox::down-button"
            f" {{ width:14px; background:{SIDEBAR_SECTION_BG}; border:none; }}"
        )
        self._stp_duration = QSpinBox()
        self._stp_duration.setRange(10, 120)
        self._stp_duration.setValue(30)
        self._stp_duration.setFixedWidth(72)
        self._stp_duration.setFixedHeight(26)
        self._stp_duration.setToolTip("How long to listen for STP/BPDU frames")
        self._stp_duration.setStyleSheet(_spin_qss)

        self._storm_duration = QSpinBox()
        self._storm_duration.setRange(5, 60)
        self._storm_duration.setValue(10)
        self._storm_duration.setFixedWidth(72)
        self._storm_duration.setFixedHeight(26)
        self._storm_duration.setStyleSheet(_spin_qss)

        _chk_qss = (
            f"QCheckBox {{ color:{TEXT_PRIMARY}; font-size:11px; padding:4px 8px; }}"
            f"QCheckBox::indicator {{ width:12px; height:12px; border:1px solid {BORDER_MED};"
            f" border-radius:2px; background:{BG_CARD}; }}"
            f"QCheckBox::indicator:checked {{ background:{ACCENT}; border-color:{ACCENT}; }}"
        )
        self._chk_stp   = QCheckBox("STP detection")
        self._chk_storm = QCheckBox("Storm analysis")
        self._chk_wifi  = QCheckBox("WiFi scan")
        self._chk_dns   = QCheckBox("DNS check")
        for _c in (self._chk_stp, self._chk_storm, self._chk_wifi, self._chk_dns):
            _c.setChecked(True)
            _c.setStyleSheet(_chk_qss)

        _menu_s = QMenu()
        _menu_s.setStyleSheet(
            f"QMenu {{ background:{BG_CARD}; color:{TEXT_PRIMARY};"
            f" border:1px solid {BORDER}; padding:4px; }}"
            f"QMenu::item:selected {{ background:{BG_HOVER}; }}"
        )

        def _spin_row(label: str, spin: QSpinBox) -> QWidgetAction:
            _w = QWidget()
            _l = QHBoxLayout(_w)
            _l.setContentsMargins(8, 4, 8, 4)
            _l.setSpacing(8)
            _lbl = QLabel(label)
            _lbl.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:11px; min-width:130px;")
            _l.addWidget(_lbl)
            _l.addWidget(spin)
            _wa = QWidgetAction(_menu_s)
            _wa.setDefaultWidget(_w)
            return _wa

        _menu_s.addAction(_spin_row("STP listen (s):", self._stp_duration))
        _menu_s.addAction(_spin_row("Storm listen (s):", self._storm_duration))
        _menu_s.addSeparator()
        for _c in (self._chk_stp, self._chk_storm, self._chk_wifi, self._chk_dns):
            _cwa = QWidgetAction(_menu_s)
            _cwa.setDefaultWidget(_c)
            _menu_s.addAction(_cwa)

        _btn_settings = QToolButton()
        _btn_settings.setText("\u2699  Scan Settings")
        _btn_settings.setObjectName("btnNetRefresh")
        _btn_settings.setFixedHeight(34)
        _btn_settings.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        _btn_settings.setMenu(_menu_s)
        _btn_settings.setStyleSheet(
            f"QToolButton {{ background:{BG_CARD}; color:{TEXT_MUTED};"
            f" border:1px solid {SIDEBAR_HOVER}; border-radius:3px;"
            " padding:0 10px; font-size:11px; }"
            f"QToolButton:hover {{ background:{SIDEBAR_HOVER}; color:{WHITE}; }}"
            "QToolButton::menu-indicator { image: none; }"
        )
        lay.addWidget(_btn_settings)
'''

patched = text[:start] + NEW_BLOCK + text[end:]
TARGET.write_text(patched, encoding="utf-8")
print("DONE — file written successfully")
