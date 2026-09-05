"""
nav/builder.py — _NavBuilderMixin.

Extracted from ui/dashboard.py (Sprint 19).
Covers: nav structure building (sections, rail items, flyout), nav runtime
(switching, crossfade, keyboard), help panel wiring, page-visit tracking,
pin management, command palette, and recent-action wiring.
"""
from __future__ import annotations

import time

from PyQt6.QtCore import Qt, QSettings, QSize, pyqtSlot
from PyQt6.QtWidgets import QLabel, QPushButton, QWidget

from ui.help import _PAGE_HELP
from ui.nav.labels import NavLabel as L, SPECIAL_LABELS
from ui.nav.lazy_page import _LazyPageHost
from ui.nav.rail import _NavEntry, _RailButton, _make_nav_icon
from ui.perf_audit import warn_if_nav_slow
from ui import styles as _s
from ui.dialog_utils import run_dialog

# Pages that auto-expand the tip bar on first visit (non-obvious interactions)
_AUTO_HELP_PAGES: frozenset[str] = frozenset({
    L.NETWORK_LOGGER, L.LAB_MODE, L.PROTOCOL_VISUALIZER,
    L.AUTOMATION_HOOKS, L.MQTT_HOME_ASSISTANT, L.TLS_EXPOSURE,
    L.SERVICE_HEARTBEAT, L.IOT_BEHAVIOUR, L.SCHEDULED_SCANS,
    L.TREND_FORECASTS, L.BANDWIDTH_USAGE, L.APP_TRAFFIC,
    L.ARP_SPOOF_WATCH, L.MONITOR_STATUS,
})


class _NavBuilderMixin:
    """
    Navigation building and runtime methods extracted from Dashboard.

    State variables (all created in Dashboard.__init__ / _build_ui):
        _nav            QListWidget — flat sidebar list
        _stack          QStackedWidget — page stack
        _nav_row_to_page        dict[int, int]
        _nav_item_icons         dict[int, str]
        _nav_item_labels        dict[int, str]
        _nav_label_to_widget    dict[str, QWidget]
        _nav_header_rows        set[int]
        _nav_section_groups     dict[int, dict]
        _nav_separators         set[int]
        _nav_action_rows        dict[int, Callable]
        _nav_admin_rows         set[int]
        _nav_audit_rows         set[int]
        _nav_current_section    int
        _nav_current_subgroup   int
        _nav_collapsed          bool
        _nav_sections           list[dict]
        _nav_page_to_section    dict[str, str]
        _nav_open_section       str
        _nav_flyout             _FlyoutPanel
        _nav_rail_buttons       dict[str, _RailButton]
        _nav_pinned_labels      list[str]
        _nav_current_page_label str
        _nav_history            list[str]
        _fade_anim              QPropertyAnimation | None
    """

    # C-2: freshness thresholds (seconds from scan timestamp before dot turns amber)
    _FRESH_SECONDS: dict[str, int] = {
        L.DEVICES:                30 * 60,
        L.PORT_SCAN_TCP:           2 * 3600,
        L.PORT_SCAN_UDP:           2 * 3600,
        L.CVE_LOOKUP:              6 * 3600,
        L.THREAT_INTEL:            1 * 3600,
        L.TLS_EXPOSURE:            2 * 3600,
        L.LOGIN_TEST:              6 * 3600,
        L.OS_DETECTION:            6 * 3600,
        L.EXPOSED_TO_INTERNET:     2 * 3600,
        L.FULL_DEVICE_DISCOVERY:   2 * 3600,
        L.SERVICE_DIAGNOSTICS:    30 * 60,
        L.NETWORK_LOGGER:          6 * 3600,
    }
    _DEFAULT_FRESH_SECONDS: int = 3600

    # ── Flat-nav structure helpers ────────────────────────────────────────────

    def _nav_add_section(self, label: str, icon: str = "■",
                         collapsed_by_default: bool = False,
                         fg_color: str = None) -> int:
        """Add a collapsible section header row."""
        from PyQt6.QtCore import QSize
        from PyQt6.QtGui import QColor, QFont as _QFont, QBrush
        from PyQt6.QtWidgets import QListWidgetItem
        # Insert 8px air-gap + 1px divider before every non-first section
        if self._nav.count() > 0:
            _div = QListWidgetItem()
            _div.setFlags(Qt.ItemFlag.NoItemFlags)
            _div.setSizeHint(QSize(0, 9))
            _div.setBackground(QBrush(QColor(_s.CHART_SPINE)))
            self._nav.addItem(_div)
            self._nav_separators.add(self._nav.count() - 1)
        item = QListWidgetItem()
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)   # clickable but not selectable
        item.setSizeHint(QSize(0, 28))
        item.setBackground(QBrush(QColor(_s.SIDEBAR_SECTION_BG)))
        f = _QFont("Segoe UI", 9)
        f.setBold(True)
        item.setFont(f)
        self._nav.addItem(item)
        row = self._nav.count() - 1
        self._nav_item_icons[row]    = icon
        self._nav_item_labels[row]   = label
        self._nav_header_rows.add(row)
        self._nav_section_groups[row] = {
            "children": [], "collapsed": collapsed_by_default, "level": 0,
            "fg_color": fg_color,
        }
        self._nav_current_section  = row
        self._nav_current_subgroup = -1
        self._nav_separators.add(row)          # legacy compat
        self._nav_refresh_item_text(row)
        return row

    def _nav_add_subgroup(self, label: str, icon: str = "▸",
                          collapsed_by_default: bool = True) -> int:
        """Add an indented collapsible sub-group header under the current section."""
        from PyQt6.QtCore import QSize
        from PyQt6.QtGui import QColor, QBrush
        from PyQt6.QtWidgets import QListWidgetItem
        item = QListWidgetItem()
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        item.setSizeHint(QSize(0, 26))
        item.setBackground(QBrush(QColor(_s.SIDEBAR_SECTION_BG)))
        self._nav.addItem(item)
        row = self._nav.count() - 1
        self._nav_item_icons[row]    = icon
        self._nav_item_labels[row]   = label
        self._nav_header_rows.add(row)
        self._nav_section_groups[row] = {
            "children": [], "collapsed": collapsed_by_default, "level": 1
        }
        self._nav_section_groups[self._nav_current_section]["children"].append(row)
        self._nav_separators.add(row)          # legacy compat
        self._nav_current_subgroup = row
        self._nav_refresh_item_text(row)
        return row

    def _nav_add_page(self, icon: str, label: str, widget: QWidget) -> int:
        """Add a page entry to the sidebar and the stacked widget. Returns nav row index."""
        from PyQt6.QtCore import QSize
        from PyQt6.QtWidgets import QListWidgetItem
        item = QListWidgetItem()
        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        item.setSizeHint(QSize(0, 30))
        self._nav.addItem(item)
        page_idx = self._stack.addWidget(widget)
        row = self._nav.count() - 1
        self._nav_row_to_page[row] = page_idx
        self._nav_item_icons[row]  = icon
        self._nav_item_labels[row] = label
        self._nav_label_to_widget[label] = widget
        parent = (self._nav_current_subgroup if self._nav_current_subgroup >= 0
                  else self._nav_current_section)
        if parent >= 0:
            self._nav_section_groups[parent]["children"].append(row)
        self._nav_refresh_item_text(row)
        return row

    def _nav_add_alias(self, icon: str, label: str, page_idx: int) -> int:
        """Add a nav entry that points to an already-registered page stack index."""
        from PyQt6.QtCore import QSize
        from PyQt6.QtWidgets import QListWidgetItem
        item = QListWidgetItem()
        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        item.setSizeHint(QSize(0, 30))
        self._nav.addItem(item)
        row = self._nav.count() - 1
        self._nav_row_to_page[row] = page_idx
        self._nav_item_icons[row]  = icon
        self._nav_item_labels[row] = label
        parent = (self._nav_current_subgroup if self._nav_current_subgroup >= 0
                  else self._nav_current_section)
        if parent >= 0:
            self._nav_section_groups[parent]["children"].append(row)
        self._nav_refresh_item_text(row)
        return row

    def _nav_set_page(self, nav_row: int):
        from PyQt6.QtCore import QPropertyAnimation
        if nav_row not in self._nav_row_to_page:
            return
        if self._fade_anim is not None and self._fade_anim.state() == QPropertyAnimation.State.Running:
            self._fade_anim.stop()
            w = self._stack.currentWidget()
            if w:
                w.setGraphicsEffect(None)
            self._fade_anim = None
        self._stack.setCurrentIndex(self._nav_row_to_page[nav_row])
        label = self._nav_item_labels.get(nav_row, "")
        if label:
            self.setWindowTitle(f"NetSentinel — {label}")

    def _nav_crossfade_to(self, target_widget) -> None:
        from PyQt6.QtWidgets import QGraphicsOpacityEffect
        from PyQt6.QtCore import QPropertyAnimation, QEasingCurve

        if self._fade_anim is not None and self._fade_anim.state() == QPropertyAnimation.State.Running:
            self._fade_anim.stop()
            self._fade_anim.deleteLater()  # drop C++ child so it doesn't outlive the navigation
            cur = self._stack.currentWidget()
            if cur:
                cur.setGraphicsEffect(None)
            self._fade_anim = None

        if self._stack.currentWidget() is target_widget:
            return

        cur = self._stack.currentWidget()
        if cur is None:
            self._stack.setCurrentWidget(target_widget)
            return

        effect = QGraphicsOpacityEffect(cur)
        cur.setGraphicsEffect(effect)

        # No widget parent — self._fade_anim holds the only strong reference.
        # When self._fade_anim is replaced below the Python ref drops to zero and
        # deleteLater() queues C++ cleanup so it never accumulates on a page widget.
        fade_out = QPropertyAnimation(effect, b"opacity")
        fade_out.setDuration(80)
        fade_out.setStartValue(1.0)
        fade_out.setEndValue(0.0)
        fade_out.setEasingCurve(QEasingCurve.Type.InQuad)
        self._fade_anim = fade_out

        def _on_fade_out_done():
            fade_out.deleteLater()
            cur.setGraphicsEffect(None)
            self._stack.setCurrentWidget(target_widget)
            in_effect = QGraphicsOpacityEffect(target_widget)
            target_widget.setGraphicsEffect(in_effect)
            fade_in = QPropertyAnimation(in_effect, b"opacity")  # no widget parent
            fade_in.setDuration(80)
            fade_in.setStartValue(0.0)
            fade_in.setEndValue(1.0)
            fade_in.setEasingCurve(QEasingCurve.Type.OutQuad)

            def _on_fade_in_done():
                target_widget.setGraphicsEffect(None)
                self._fade_anim = None
                fade_in.deleteLater()

            fade_in.finished.connect(_on_fade_in_done)
            self._fade_anim = fade_in
            fade_in.start()

        fade_out.finished.connect(_on_fade_out_done)
        fade_out.start()

    def _nav_refresh_item_text(self, row: int):
        """Rewrite displayed text for a nav row based on collapsed/expanded mode."""
        item = self._nav.item(row)
        if item is None:
            return
        icon  = self._nav_item_icons.get(row, "")
        label = self._nav_item_labels.get(row, "")
        if self._nav_collapsed:
            item.setText(icon)
            if row not in self._nav_header_rows:
                item.setToolTip(_s.safe_tooltip(label))
        elif row in self._nav_section_groups:
            grp   = self._nav_section_groups[row]
            arrow = "▶" if grp["collapsed"] else "▼"
            from PyQt6.QtGui import QColor
            if grp["level"] == 0:
                item.setText(f" {arrow}  {label.upper()}")
            else:
                item.setText(f"     {arrow}  {label}")
            _fg = grp.get("fg_color") or _s.SIDEBAR_SECTION_FG
            item.setForeground(QColor(_fg))
            item.setToolTip("")
        else:
            star = " ★" if label in self._nav_pinned_labels else ""
            item.setText(f"  {icon}  {label}{star}")
            item.setToolTip("")
            from PyQt6.QtGui import QColor
            if row in self._nav_audit_rows:
                item.setForeground(QColor(_s.AUDIT_RED))
            else:
                item.setForeground(QColor(_s.SIDEBAR_ITEM_FG))

    def _nav_toggle_section(self, header_row: int):
        """Collapse or expand a section / sub-group header."""
        if header_row not in self._nav_section_groups:
            return
        grp = self._nav_section_groups[header_row]
        grp["collapsed"] = not grp["collapsed"]
        self._nav_refresh_item_text(header_row)
        self._nav_apply_section_visibility(header_row, grp["collapsed"])
        from PyQt6.QtCore import QSettings as _QS
        _qs = _QS(str(self._settings_path()), _QS.Format.IniFormat)
        _qs.setValue(f"nav/group_{header_row}_collapsed", str(grp["collapsed"]))

    def _nav_apply_section_visibility(self, header_row: int, hide: bool):
        """Show/hide direct children; recurse into sub-group children."""
        for child_row in self._nav_section_groups[header_row]["children"]:
            child_item = self._nav.item(child_row)
            if child_item:
                child_item.setHidden(hide)
            if child_row in self._nav_section_groups:
                child_grp    = self._nav_section_groups[child_row]
                effective_hide = hide or child_grp["collapsed"]
                for sub_row in child_grp["children"]:
                    sub_item = self._nav.item(sub_row)
                    if sub_item:
                        sub_item.setHidden(effective_hide)

    @pyqtSlot()
    def _toggle_sidebar(self):
        """Show/hide the rail sidebar (VSCode-style: toggle entire panel)."""
        visible = not self._nav_rail_panel.isVisible()
        self._nav_rail_panel.setVisible(visible)
        self._sidebar_toggle_btn.setText("▶" if not visible else "◀")

    def _focus_nav_search(self) -> None:
        """Open the command palette — the search mechanism in the activity-rail nav.

        The old flat-panel _nav_search field is hidden in the current nav.
        Ctrl+F now opens the same Ctrl+K command palette so the keyboard
        shortcut always does something visible.
        """
        self._open_command_palette()

    @pyqtSlot(str)
    def _on_nav_search_changed(self, text: str):
        """Filter sidebar items to those whose label contains text."""
        text = text.strip().lower()
        if not text:
            for row in range(self._nav.count()):
                item = self._nav.item(row)
                if item:
                    item.setHidden(False)
            for hrow, grp in self._nav_section_groups.items():
                if grp["collapsed"]:
                    self._nav_apply_section_visibility(hrow, True)
            return
        for row in range(self._nav.count()):
            if row in self._nav_header_rows:
                continue
            label = self._nav_item_labels.get(row, "").lower()
            item  = self._nav.item(row)
            if item:
                item.setHidden(text not in label)

    def _on_nav_item_clicked(self, item):
        """Toggle section/sub-group headers when clicked."""
        row = self._nav.row(item)
        if row in self._nav_section_groups:
            self._nav_toggle_section(row)

    @pyqtSlot(int)
    def _on_nav_row_changed(self, row: int):
        """Navigate to the page for the selected nav row."""
        if row < 0 or row in self._nav_header_rows:
            return
        if row in self._nav_action_rows:
            self._nav_action_rows[row]()
            return
        self._nav_set_page(row)
        if hasattr(self, "_tray_manager"):
            self._tray_manager.reset_badge()

    def _nav_go_to(self, label: str) -> None:
        """Programmatically navigate to the page with the given rail label."""
        self._nav_rail_go_to(label)

    def _open_isp_from_home(self) -> None:
        self._nav_rail_go_to(L.NETWORK_HEALTH_REPORT)

    def _rebuild_nav_for_mode(self) -> None:
        """Clear all nav state and rebuild the full Pro rail."""
        # ── Reset flat-nav state ───────────────────────────────────────────────
        self._nav.clear()
        self._nav_row_to_page.clear()
        self._nav_item_icons.clear()
        self._nav_item_labels.clear()
        self._nav_header_rows.clear()
        self._nav_section_groups.clear()
        self._nav_separators.clear()
        self._nav_action_rows.clear()
        self._nav_admin_rows.clear()
        self._nav_audit_rows.clear()
        self._nav_current_section  = -1
        self._nav_current_subgroup = -1
        self._adv_tab_index_adv = -1
        self._adv_tab_index_mtr = -1

        # ── Reset rail-nav state ───────────────────────────────────────────────
        self._nav_sections.clear()
        self._nav_page_to_section.clear()
        self._nav_open_section = ""
        if hasattr(self, "_nav_flyout") and self._nav_flyout.maximumWidth() > 0:
            self._nav_flyout.close_panel()

        self._nav_flat_panel.setFixedWidth(0)
        self._nav_flat_panel.setVisible(False)
        self._nav_rail_panel.setVisible(True)

        self._build_pro_nav()

        if self._nav_pinned_labels:
            _pinned_entries = []
            for _lbl in self._nav_pinned_labels:
                _w = self._nav_label_to_widget.get(_lbl)
                if _w is not None:
                    _pinned_entries.append(_NavEntry(
                        label=_lbl, page=_w,
                        admin_required=False, audit_item=False, pinned=True,
                    ))
            if _pinned_entries and len(_pinned_entries) > 4:
                self._nav_sections.insert(0, {
                    "name": "Pinned", "icon": "pin", "entries": _pinned_entries,
                })
            self._nav_direct_pins: list = _pinned_entries if len(_pinned_entries) <= 4 else []
        else:
            self._nav_direct_pins = []

        self._nav_finalize_rail()
        self._proactive_wire_page_help_btns()
        _qs = QSettings(str(self._settings_path()), QSettings.Format.IniFormat)
        _last = _qs.value("nav/last_section", "")
        _open = _last if any(s["name"] == _last for s in self._nav_sections) \
                else (self._nav_sections[0]["name"] if self._nav_sections else "")
        if _open:
            self._nav_rail_toggle(_open)
            _sec = next((s for s in self._nav_sections if s["name"] == _open), None)
            if _sec and _sec["entries"]:
                self._nav_rail_go_to(_sec["entries"][0].label)
        _last_page = _qs.value("nav/last_page", "")
        if _last_page and _last_page in self._nav_label_to_widget:
            self._nav_rail_go_to(_last_page)

        from PyQt6.QtGui import QColor as _QColor
        for _arow in self._nav_audit_rows:
            _aitem = self._nav.item(_arow)
            if _aitem:
                _aitem.setForeground(_QColor(_s.AUDIT_RED))

        # C-1/C-2: restore scan dots/badges from QSettings; start staleness timer
        self._restore_scan_registry()
        self._start_staleness_timer()

    def _nav_ref(self, icon: str, label: str, widget: "QWidget") -> int:
        """Add a nav alias entry for a widget already registered in the stack."""
        idx = self._stack.indexOf(widget)
        if idx < 0:
            idx = self._stack.addWidget(widget)
        self._nav_label_to_widget[label] = widget
        return self._nav_add_alias(icon, label, idx)

    def _nav_flat_item(self, icon: str, label: str, widget: "QWidget",
                       admin_required: bool = False, audit_item: bool = False) -> int:
        """Add a flat-nav item and optionally mark it admin/audit for red styling."""
        row = self._nav_ref(icon, label, widget)
        if admin_required:
            self._nav_admin_rows.add(row)
        if audit_item:
            self._nav_audit_rows.add(row)
        return row

    def _nav_add_action(self, icon: str, label: str, action) -> int:
        """Add a nav item that calls *action* instead of navigating to a page."""
        from PyQt6.QtCore import QSize
        from PyQt6.QtWidgets import QListWidgetItem
        item = QListWidgetItem()
        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        item.setSizeHint(QSize(0, 30))
        self._nav.addItem(item)
        row = self._nav.count() - 1
        self._nav_item_icons[row]  = icon
        self._nav_item_labels[row] = label
        parent = (self._nav_current_subgroup if self._nav_current_subgroup >= 0
                  else self._nav_current_section)
        if parent >= 0:
            self._nav_section_groups[parent]["children"].append(row)
        self._nav_refresh_item_text(row)
        self._nav_action_rows[row] = action
        return row

    def _nav_add_spacer(self) -> None:
        """Add a non-selectable visual spacer row in the nav list."""
        from PyQt6.QtCore import QSize
        from PyQt6.QtGui import QColor, QBrush
        from PyQt6.QtWidgets import QListWidgetItem
        sep = QListWidgetItem()
        sep.setFlags(Qt.ItemFlag.NoItemFlags)
        sep.setSizeHint(QSize(0, 10))
        sep.setBackground(QBrush(QColor(_s.SIDEBAR_BG)))
        self._nav.addItem(sep)
        self._nav_header_rows.add(self._nav.count() - 1)

    def _nav_add_section_label(self, label: str, fg_color: str = None) -> int:
        """Add a NON-collapsible ALL-CAPS section divider label (not interactive)."""
        from PyQt6.QtCore import QSize
        from PyQt6.QtGui import QColor, QFont as _QFont
        from PyQt6.QtWidgets import QListWidgetItem
        item = QListWidgetItem()
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        item.setSizeHint(QSize(0, 26))
        f = _QFont("Segoe UI", 9)
        f.setBold(True)
        item.setFont(f)
        item.setText(f"  {label.upper()}")
        _fg = fg_color or _s.SIDEBAR_SECTION_FG
        item.setForeground(QColor(_fg))
        self._nav.addItem(item)
        row = self._nav.count() - 1
        self._nav_item_icons[row]  = ""
        self._nav_item_labels[row] = label
        self._nav_header_rows.add(row)
        return row

    # ── Rail-mode nav helpers ─────────────────────────────────────────────────

    def _nav_begin_section(self, name: str, icon: str) -> None:
        """Start a new section in rail mode."""
        self._nav_sections.append({"name": name, "icon": icon, "entries": []})

    def _nav_add_rail_item(
        self,
        label: str,
        widget: "QWidget",
        pinned: bool = False,
        admin_required: bool = False,
        audit_item: bool = False,
        npcap_required: bool = False,
    ) -> None:
        """Register a page under the current rail section."""
        if not self._nav_sections:
            return
        if self._stack.indexOf(widget) < 0:
            self._stack.addWidget(widget)
        self._nav_label_to_widget[label] = widget
        entry = _NavEntry(
            label=label,
            page=widget,
            admin_required=admin_required,
            audit_item=audit_item,
            npcap_required=npcap_required,
            pinned=label in self._nav_pinned_labels or pinned,
        )
        self._nav_sections[-1]["entries"].append(entry)
        self._nav_page_to_section[label] = self._nav_sections[-1]["name"]

    def _nav_finalize_rail(self) -> None:
        """Build _RailButton widgets from _nav_sections and wire them up."""
        stretch_idx = None
        for i in range(self._nav_rail_lay.count()):
            item = self._nav_rail_lay.itemAt(i)
            if item and item.spacerItem():
                stretch_idx = i
                break
        while stretch_idx and stretch_idx > 1:
            item = self._nav_rail_lay.takeAt(1)
            if item and item.widget():
                item.widget().deleteLater()
            stretch_idx -= 1

        self._nav_rail_buttons.clear()
        self._nav_rail_pin_buttons: dict = {}

        # "Recent" rail shortcut (S7-4) — last 3 pages visited, helps new users retrace
        # their steps. Rebuilt here (not in tabs.py) so it is correctly recreated and
        # positioned on every nav rebuild, exactly like quick-access pins and section
        # buttons below it — anything added directly in tabs.py after the stretch/Settings
        # would throw off the count()-2 insertion math used throughout this method.
        self._recent_rail_btn = QPushButton()
        self._recent_rail_btn.setFixedSize(56, 32)
        self._recent_rail_btn.setToolTip(_s.safe_tooltip("Recently visited pages"))
        self._recent_rail_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._recent_rail_btn.setCheckable(True)
        self._recent_rail_btn.setIcon(_make_nav_icon("log", 18, _s.TEXT_MUTED))
        self._recent_rail_btn.setIconSize(QSize(18, 18))
        self._recent_rail_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; outline: none; }}"
            f"QPushButton:hover {{ background: rgba(255,255,255,0.07); }}"
            f"QPushButton:checked {{ background: rgba(255,255,255,0.12); }}"
            f"QPushButton:focus, QPushButton:focus-visible {{"
            f" outline: none; border: none; }}"
        )
        self._recent_rail_btn.clicked.connect(self._toggle_recent_pages_flyout)
        insert_at = self._nav_rail_lay.count() - 2
        self._nav_rail_lay.insertWidget(insert_at, self._recent_rail_btn)

        direct_pins = getattr(self, "_nav_direct_pins", [])
        if direct_pins:
            qa_lbl = QLabel("QUICK\nACCESS")
            from PyQt6.QtCore import Qt as _Qt
            qa_lbl.setAlignment(_Qt.AlignmentFlag.AlignHCenter | _Qt.AlignmentFlag.AlignVCenter)
            qa_lbl.setFixedSize(56, 24)
            _s.themed_ss(
                qa_lbl,
                "color:{TEXT_MUTED}; font-size:7px; font-weight:bold;"
                " letter-spacing:0.5px; background:transparent;",
            )
            insert_at = self._nav_rail_lay.count() - 2
            self._nav_rail_lay.insertWidget(insert_at, qa_lbl)

            for entry in direct_pins:
                lbl = entry.label
                short = lbl.split()[0][:8]
                pin_btn = _RailButton("star", lbl)
                pin_btn._short_label = short
                pin_btn.setToolTip(_s.safe_tooltip(f"{lbl}\nRight-click to unpin or reorder"))
                pin_btn.clicked.connect(
                    lambda _c, label=lbl: (
                        self._nav_rail_go_to(label),
                        self._nav_flyout.close_panel() if hasattr(self, "_nav_flyout") else None,
                    )
                )
                pin_btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                pin_btn.customContextMenuRequested.connect(
                    lambda _pos, _l=lbl, _b=pin_btn: self._show_pin_btn_ctx_menu(_l, _b, _pos)
                )
                insert_at = self._nav_rail_lay.count() - 2
                self._nav_rail_lay.insertWidget(insert_at, pin_btn)
                self._nav_rail_pin_buttons[lbl] = pin_btn

        _SECTION_HINTS: dict = {
            "Monitor":        "Monitor  ·  Ctrl+L → Network Logger",
            "Security Audit": (
                "Security Audit\n"
                "Red text = active security probe\n"
                "[admin] badge = requires Run as Administrator\n"
                "Items without a badge run passively."
            ),
            "Analysis": (
                "Analysis\n"
                "[Npcap] badge = requires Npcap driver installed\n"
                "Other items run without additional drivers."
            ),
        }
        for sec in self._nav_sections:
            btn = _RailButton(sec["icon"], sec["name"])
            btn.clicked.connect(lambda _c, s=sec["name"]: self._nav_rail_toggle(s))
            if sec["name"] in _SECTION_HINTS:
                btn.setToolTip(_s.safe_tooltip(_SECTION_HINTS[sec["name"]]))
            insert_at = self._nav_rail_lay.count() - 2
            self._nav_rail_lay.insertWidget(insert_at, btn)
            self._nav_rail_buttons[sec["name"]] = btn

    def _nav_rail_toggle(self, section_name: str) -> None:
        """Toggle the flyout for the given section; close if already open."""
        if self._nav_open_section == section_name and self._nav_flyout.maximumWidth() > 0:
            if not self._nav_flyout.is_pinned:
                self._nav_flyout.close_panel()
                self._nav_open_section = ""
                self._nav_rail_buttons[section_name].setChecked(False)
            return
        self._nav_open_section = section_name
        for name, btn in self._nav_rail_buttons.items():
            btn.setChecked(name == section_name)
        if hasattr(self, "_recent_rail_btn"):
            self._recent_rail_btn.setChecked(False)
        sec = next((s for s in self._nav_sections if s["name"] == section_name), None)
        if sec is None:
            return
        # The "admin" pill is a WARNING, not a label — it means "you cannot run
        # this as you are". Suppress it when the process is already elevated so the
        # common admin case carries no noise. Re-evaluated on every flyout open,
        # which is correct: elevation never changes mid-session.
        _needs_admin_pill = not getattr(self, "_admin", False)
        entries = [
            (
                e.label,
                e.label in self._nav_pinned_labels,
                e.admin_required or e.audit_item or e.npcap_required,
                ("admin" if _needs_admin_pill else "") if e.admin_required
                else ("Npcap" if e.npcap_required else ""),
            )
            for e in sec["entries"]
        ]
        self._nav_flyout.load_section(
            title=section_name,
            entries=entries,
            active_label=self._nav_current_page_label,
            on_click=self._nav_rail_go_to,
            on_pin_toggle=self._on_rail_pin_toggle,
            on_pin_move=self._on_rail_pin_move,
        )
        for _lbl, _color in getattr(self, "_flyout_dots", {}).items():
            if _color:
                self._nav_flyout.apply_dot(_lbl, _color)
        self._nav_flyout.open()
        _qs = QSettings(str(self._settings_path()), QSettings.Format.IniFormat)
        _qs.setValue("nav/last_section", section_name)

    def _nav_rail_go_to(self, label: str, _push_history: bool = False) -> None:
        """Navigate to a page by label in rail mode. Flyout stays open."""
        _nav_go_to_t0 = time.perf_counter()
        widget = self._nav_label_to_widget.get(label)
        if widget is None:
            # RULE-NAV3 / P1 guard: a label with no registered page is dead
            # navigation. Silently no-oping here is the biggest recurring nav bug
            # class (a typo'd or renamed label routes nowhere, with no error).
            # SPECIAL_LABELS (e.g. "Settings" → modal dialog) legitimately have no
            # page and are left to no-op quietly; anything else is logged loudly
            # and hard-fails under pytest so a dead link can never ship silently.
            # The running app always degrades to a no-op — never crash a user's
            # session over a bad nav label. Static enforcement (compile-time typo
            # catching for all literals) lives in tests/test_nav_label_registry.py.
            if label not in SPECIAL_LABELS:
                import logging as _logging
                _logging.getLogger("nav").error(
                    "dead navigation: no page registered for label %r — pass a "
                    "ui.nav.labels.NavLabel member and confirm _build_pro_nav()", label,
                )
                import os as _os
                if _os.environ.get("PYTEST_CURRENT_TEST"):
                    raise AssertionError(
                        f"unknown nav label {label!r} passed to _nav_rail_go_to() "
                        f"— not a NavLabel member registered in _build_pro_nav()"
                    )
            return
        # Deferred-construction hook: if the label still points at a placeholder,
        # build the real page and re-point the stack/map before the crossfade so
        # the user lands on the real widget, not "Loading…".
        if isinstance(widget, _LazyPageHost):
            widget = self._materialize_host(widget)
        # experimental/theme_switch_deferred flush hook: if a theme switch
        # queued this page instead of refreshing it eagerly (dashboard.py
        # _on_theme_changed), bring it up to date now that it's about to be
        # shown. See Dashboard._theme_dirty_widgets.
        _dirty = getattr(self, "_theme_dirty_widgets", None)
        if _dirty and widget in _dirty:
            if hasattr(widget, "refresh_theme"):
                widget.refresh_theme()
            _dirty.discard(widget)
        if _push_history and hasattr(self, "_nav_history"):
            current = getattr(self, "_nav_current_page_label", None)
            if current and current != label:
                self._nav_history.append(current)
        elif hasattr(self, "_nav_history"):
            self._nav_history.clear()
        if hasattr(self, "_back_btn"):
            self._back_btn.setVisible(bool(self._nav_history))
        self._nav_current_page_label = label
        _qs_lp = QSettings(str(self._settings_path()), QSettings.Format.IniFormat)
        _qs_lp.setValue("nav/last_page", label)
        self._nav_crossfade_to(widget)
        self._nav_flyout.set_active(label)
        section = self._nav_page_to_section.get(label, "")
        if hasattr(self, "_breadcrumb_lbl"):
            self._breadcrumb_lbl.setText(f"{section}  ›  {label}" if section else label)
        if hasattr(self, "_help_panel"):
            self._update_help_panel(label)
        if hasattr(self, "_tray_manager"):
            self._tray_manager.reset_badge()
        if label in _AUTO_HELP_PAGES and _PAGE_HELP.get(label) and hasattr(self, "_tip_bar"):
            import json as _json
            _qs2 = QSettings("NetSentinel", "NetSentinel")
            try:
                _visited2 = _json.loads(_qs2.value("discover/visited_pages", "[]"))
            except Exception:
                _visited2 = []
            if label not in _visited2:
                self._tip_bar.setChecked(True)
        self._track_page_visit(label)
        # Session sentinel (A1): the last page reached is the only thing that will
        # ever say WHERE the user was when a memory kill or a hang ended the process
        # — those leave no traceback and no faulthandler entry to read.
        try:
            from modules.session_record import heartbeat
            heartbeat(label)
        except Exception:
            pass  # instrumentation must never be able to break navigation
        warn_if_nav_slow(label, (time.perf_counter() - _nav_go_to_t0) * 1000)

    def _nav_deep_link_go_to(self, label: str) -> None:
        """Navigate via a deep link — pushes the current page onto the back stack."""
        self._nav_rail_go_to(label, _push_history=True)

    @pyqtSlot()
    def _nav_go_back(self) -> None:
        if not self._nav_history:
            return
        prev = self._nav_history.pop()
        widget = self._nav_label_to_widget.get(prev)
        if widget is None:
            return
        self._nav_current_page_label = prev
        self._nav_crossfade_to(widget)
        self._nav_flyout.set_active(prev)
        section = self._nav_page_to_section.get(prev, "")
        if hasattr(self, "_breadcrumb_lbl"):
            self._breadcrumb_lbl.setText(f"{section}  ›  {prev}" if section else prev)
        if hasattr(self, "_back_btn"):
            self._back_btn.setVisible(bool(self._nav_history))

    def keyPressEvent(self, event) -> None:
        from PyQt6.QtCore import Qt as _Qt
        if event.key() == _Qt.Key.Key_Escape and self._nav_history:
            self._nav_go_back()
            event.accept()
        else:
            super().keyPressEvent(event)

    # ── Scan state registry ───────────────────────────────────────────────────

    def _nav_set_scan_state(
        self,
        label: str,
        state: str,
        ts: float | None = None,
        error: str | None = None,
        verdict: str | None = None,
    ) -> None:
        """Record a scan state transition and update the flyout dot for ``label``.

        Parameters
        ----------
        label:   canonical nav label string (e.g. ``"Port Scan (TCP)"``)
        state:   one of ``"never"`` | ``"running"`` | ``"fresh"`` | ``"stale"`` | ``"error"``
                 | ``"not_testable"`` (a scan ran but could not reach the target — distinct
                 from ``"error"``, which is reserved for genuine tool failures)
        ts:      Unix timestamp of the transition; defaults to ``time.time()``
        error:   human-readable error string (only meaningful when state is ``"error"``)
        verdict: short result summary stored in registry for tooltip display
        """
        import logging as _logging

        ts = ts if ts is not None else time.time()
        registry: dict = getattr(self, "_scan_registry", {})
        registry[label] = {"state": state, "ts": ts, "error": error, "verdict": verdict}
        if hasattr(self, "_scan_registry"):
            self._scan_registry = registry

        _dot_map = {
            "fresh":        _s.GREEN,
            "stale":        _s.AMBER,
            "running":      _s.ACCENT,
            "error":        _s.RED,
            "not_testable": _s.VIOLET,
            "never":        "",
        }
        color = _dot_map.get(state, "")

        dots: dict = getattr(self, "_flyout_dots", {})
        dots[label] = color
        if hasattr(self, "_flyout_dots"):
            self._flyout_dots = dots

        if hasattr(self, "_nav_flyout"):
            self._nav_flyout.apply_dot(label, color)
            # B-2: rich tooltip on the flyout item
            if state == "never":
                tip = "Never run"
            else:
                from ui.tabs_helpers import _scan_age_str
                age = _scan_age_str(ts)
                tip = f"Last run: {age}"
                if verdict:
                    tip += f" — {verdict}"
                elif error:
                    tip += f" — Error: {error}"
            self._nav_flyout.set_item_tooltip(label, tip)

        # B-1: aggregate section badge — worst state among all labels in this section
        _page_to_sec = getattr(self, "_nav_page_to_section", {})
        section = _page_to_sec.get(label, "")
        if section and hasattr(self, "_nav_rail_buttons"):
            _priority = {"": 0, _s.GREEN: 1, _s.ACCENT: 2, _s.VIOLET: 3, _s.AMBER: 4, _s.RED: 5}
            worst_color = ""
            for lbl, col in getattr(self, "_flyout_dots", {}).items():
                if _page_to_sec.get(lbl) == section:
                    if _priority.get(col, 0) > _priority.get(worst_color, 0):
                        worst_color = col
            btn = self._nav_rail_buttons.get(section)
            if btn:
                btn.set_badge(worst_color)

        _logging.getLogger("scan_registry").info(
            "[SCAN] %s  state=%s  ts=%d", label, state, int(ts)
        )

        # C-1: persist registry to QSettings so dots survive app restart
        try:
            import json as _json
            _qs_persist = QSettings("NetSentinel", "NetSentinel")
            _qs_persist.setValue("scan_registry/state", _json.dumps({
                k: {"state": v["state"], "ts": v["ts"],
                    "verdict": v.get("verdict"), "error": v.get("error")}
                for k, v in registry.items()
            }))
        except Exception:
            pass  # non-fatal — QSettings may be unavailable in headless test context
        # C-1: push updated registry to Security Overview scan status card
        if hasattr(self, "_security_overview_page"):
            self._security_overview_page.update_scan_registry(dict(registry))

    def _restore_scan_registry(self) -> None:
        """C-1: Re-apply _scan_registry dots/badges from the QSettings snapshot.

        Called once at the end of _rebuild_nav_for_mode() so flyout dots and
        rail badges reflect the last known scan state immediately on launch,
        before any new scans run.  'running' entries are skipped (treated as
        'never') because the scan never completed.
        """
        if getattr(self, "_scan_registry_restored", False):
            return  # idempotent — only restore once per session
        self._scan_registry_restored = True
        import json as _json
        try:
            _qs = QSettings("NetSentinel", "NetSentinel")
            raw = _qs.value("scan_registry/state", "")
        except Exception:
            return  # non-fatal — QSettings unavailable (headless test context)
        if not raw:
            return
        try:
            saved: dict = _json.loads(raw)
        except Exception:
            return  # non-fatal — malformed JSON in QSettings
        for label, entry in saved.items():
            state = entry.get("state", "never")
            if state == "running":
                state = "never"  # app was closed mid-scan; show as never on restart
            ts = entry.get("ts") or 0.0
            error = entry.get("error")
            verdict = entry.get("verdict")
            self._nav_set_scan_state(label, state, ts=ts, error=error, verdict=verdict)
        # Apply staleness immediately so dots are correct on launch, not on first tick
        self._check_and_stale_registry()

    def _start_staleness_timer(self) -> None:
        """C-2: Start a parented QTimer that promotes fresh → stale on threshold expiry.

        Uses QTimer(self) (RULE-WIN5) so the timer is destroyed with the widget.
        Idempotent — calling it a second time (e.g. on nav rebuild) is a no-op.
        """
        if getattr(self, "_staleness_timer", None) is not None:
            return  # already started
        from PyQt6.QtCore import QTimer as _QTimer
        t = _QTimer(self)
        t.setInterval(5 * 60 * 1000)  # check every 5 minutes
        t.timeout.connect(self._check_and_stale_registry)
        t.start()
        self._staleness_timer = t

    def _check_and_stale_registry(self) -> None:
        """C-2: Promote 'fresh' registry entries to 'stale' past their threshold."""
        registry: dict = getattr(self, "_scan_registry", {})
        now = time.time()
        for label, entry in list(registry.items()):
            if entry.get("state") != "fresh":
                continue
            ts = entry.get("ts") or 0.0
            threshold = self._FRESH_SECONDS.get(label, self._DEFAULT_FRESH_SECONDS)
            if (now - ts) > threshold:
                self._nav_set_scan_state(
                    label, "stale",
                    ts=ts,
                    error=entry.get("error"),
                    verdict=entry.get("verdict"),
                )

    # ── Page-navigation shortcuts ─────────────────────────────────────────────

    @pyqtSlot()
    def _on_modem_tile_clicked(self) -> None:
        label = getattr(self, "_active_modem_plugin_label", "")
        if label:
            self._nav_rail_go_to(label)
        else:
            self._nav_rail_go_to(L.HARDWARE)

    @pyqtSlot(str)
    def _on_inventory_device_selected(self, mac: str) -> None:
        """Navigate to Devices and scroll/select the row matching this MAC."""
        self._nav_rail_go_to(L.DEVICES)
        self._m1_highlight_mac(mac)

    @pyqtSlot(str)
    def _on_config_drift_detected(self, message: str) -> None:
        """Update the status bar and badges when snapshot comparison finds drift.

        No tray balloon here -- CONFIG_DRIFT is a real, gated rule type
        (ui/scan_wiring.py evaluates it via AlertEngine.evaluate_config_drift_checks()
        and surfaces it through _surface_alert_in_app() / the router). A second raw
        show_notification() here would have duplicated that gated balloon.
        """
        self._baseline_has_drift = True
        self._refresh_section_badges()
        self._set_status(f"⚠ {message}")

    # ── Help panel wiring ─────────────────────────────────────────────────────

    def _wire_page_help_btn(self, label: str, info: dict, page=None) -> None:
        """Attach ? help button to a page's PageHeaderBar (once).

        ``page`` defaults to the current stack widget so existing call-sites
        (lazy wiring on navigation) continue to work unchanged.
        """
        from ui.widgets.page_header import PageHeaderBar
        if page is None:
            page = self._stack.currentWidget()
        if page is None:
            return
        hdr = page.findChild(PageHeaderBar)
        if hdr is None or hasattr(hdr, "_help_btn"):
            return
        what = info.get("what", "")
        if what:
            tips = info.get("hidden") or []
            hdr.set_help(label, what, tips=tips)

    def _proactive_wire_page_help_btns(self) -> None:
        """Wire ? buttons on all registered pages that have a _PAGE_HELP entry.

        Called once after _nav_finalize_rail() so every page header has its ?
        button without the user needing to navigate there first.
        """
        for label, widget in self._nav_label_to_widget.items():
            info = _PAGE_HELP.get(label, {})
            if info.get("what"):
                self._wire_page_help_btn(label, info, page=widget)

    def _update_help_panel(self, label: str) -> None:
        """Refresh tip bar text and collapse the help panel when the page changes."""
        info = _PAGE_HELP.get(label, {})
        self._tip_bar_has_content = bool(info)

        if hasattr(self, "_tip_bar"):
            self._tip_bar.blockSignals(True)
            self._tip_bar.setChecked(False)
            self._tip_bar.blockSignals(False)
        if hasattr(self, "_help_panel"):
            self._help_panel.setVisible(False)

        if not info:
            if hasattr(self, "_tip_bar"):
                self._tip_bar.setText("ⓘ  Keyboard Shortcuts  ▾")
            if hasattr(self, "_help_what_lbl"):
                self._help_what_lbl.setText("")
            if hasattr(self, "_help_hidden_lbl"):
                self._help_hidden_lbl.setVisible(False)
            return

        if hasattr(self, "_tip_bar"):
            self._tip_bar.setText(f"ⓘ  Tips for {label}  ▾")

        what = info.get("what", "")
        bullets = info.get("hidden", [])
        if hasattr(self, "_help_what_lbl"):
            self._help_what_lbl.setText(what)
        if hasattr(self, "_help_hidden_lbl"):
            if bullets:
                hidden_text = "\n".join(f"  •  {b}" for b in bullets)
                self._help_hidden_lbl.setText(f"Hidden interactions:\n{hidden_text}")
                self._help_hidden_lbl.setVisible(True)
            else:
                self._help_hidden_lbl.setVisible(False)

        self._wire_page_help_btn(label, info)

    def _toggle_help_panel(self, checked: bool) -> None:
        if hasattr(self, "_help_panel"):
            self._help_panel.setVisible(checked)

    # ── Visited-feature tracking ──────────────────────────────────────────────

    _DISCOVERY_PAGES = [
        (L.NETWORK_LOGGER,      "Start logging your network — captures RTT, DNS latency, and outages automatically in the background"),
        (L.WHATS_WRONG,         "Pick a symptom and get a plain-English verdict with a prioritised fix list"),
        (L.NETWORK_GRADE,       "Get an A–F score for your network health across 8 dimensions"),
        (L.FEATURE_GUIDE,       "See everything this app can do — including features most users never find"),
        (L.PROTOCOL_VISUALIZER, "See animated diagrams of ARP, DNS, TCP and more — using your real devices"),
        (L.LAB_MODE,            "Try a guided exercise: find a rogue device or diagnose slow DNS on your live network"),
        (L.NETWORK_HEALTH_REPORT, "Generate a network health report — great for ISP support tickets"),
    ]

    def _track_page_visit(self, label: str) -> None:
        import json as _json
        qs = QSettings("NetSentinel", "NetSentinel")

        # F8 usage signal (Phase B4) — per-page visit count feeding the
        # suggestion engine's "never visited X" nudge. Wrapped so a QSettings
        # hiccup can never break navigation.
        try:
            key = f"usage/visits/{label}"
            qs.setValue(key, int(qs.value(key, 0, type=int)) + 1)
        except Exception:
            pass  # non-fatal — usage counting must not break nav

        raw = qs.value("discover/visited_pages", "[]")
        try:
            visited: list = _json.loads(raw)
        except Exception:
            visited = []
        if label not in visited:
            visited.append(label)
            qs.setValue("discover/visited_pages", _json.dumps(visited))
            self._refresh_home_suggestions()
            if not qs.value("nav/pin_hint_shown", False, type=bool):
                analysis_sec = next(
                    (s for s in self._nav_sections if s["name"] == "Analysis"), None
                )
                if analysis_sec:
                    analysis_labels = {e.label for e in analysis_sec["entries"]}
                    visited_analysis = [p for p in visited if p in analysis_labels]
                    if len(visited_analysis) >= 3:
                        qs.setValue("nav/pin_hint_shown", True)
                        self._set_status(
                            "Tip: right-click any page in the menu to pin it ★ for faster access"
                        )

        # "Recently visited" MRU list (S7-4) — most-recent-first, capped at 3, deduped
        recent_raw = qs.value("nav/recent_pages", "[]")
        try:
            recent: list = _json.loads(recent_raw)
        except Exception:
            recent = []
        if label in recent:
            recent.remove(label)
        recent.insert(0, label)
        qs.setValue("nav/recent_pages", _json.dumps(recent[:3]))

    def _get_recent_pages(self) -> list:
        """Return up to the 3 most-recently-visited page labels, most-recent-first (S7-4)."""
        import json as _json
        qs = QSettings("NetSentinel", "NetSentinel")
        raw = qs.value("nav/recent_pages", "[]")
        try:
            recent: list = _json.loads(raw)
        except Exception:
            recent = []
        return [lbl for lbl in recent if lbl in self._nav_label_to_widget][:3]

    def _toggle_recent_pages_flyout(self) -> None:
        """Open/close a flyout listing the last 3 distinct pages visited (S7-4).

        Helps new users retrace their steps without needing to have pinned anything.
        Reuses the existing flyout panel — no new rail section, no change to the
        9 documented sections.
        """
        if self._nav_open_section == "__recent__" and self._nav_flyout.maximumWidth() > 0:
            if not self._nav_flyout.is_pinned:
                self._nav_flyout.close_panel()
                self._nav_open_section = ""
                self._recent_rail_btn.setChecked(False)
            return

        recent = self._get_recent_pages()
        if not recent:
            self._recent_rail_btn.setChecked(False)
            self._set_status("No recently visited pages yet")
            return

        self._nav_open_section = "__recent__"
        for btn in self._nav_rail_buttons.values():
            btn.setChecked(False)
        self._recent_rail_btn.setChecked(True)

        entries = [(label, label in self._nav_pinned_labels, False, "") for label in recent]
        self._nav_flyout.load_section(
            title="Recent",
            entries=entries,
            active_label=self._nav_current_page_label,
            on_click=self._nav_rail_go_to,
            on_pin_toggle=self._on_rail_pin_toggle,
            on_pin_move=self._on_rail_pin_move,
        )
        self._nav_flyout.open()

    def _refresh_home_suggestions(self) -> None:
        if not hasattr(self, "_home_page"):
            return
        if getattr(self, "_pending_live_scenario", None) is not None:
            return
        import json as _json
        qs = QSettings("NetSentinel", "NetSentinel")
        raw = qs.value("discover/visited_pages", "[]")
        try:
            visited: set = set(_json.loads(raw))
        except Exception:
            visited = set()
        suggestions = []

        # High-priority nudge: severe speed-test drop vs. the user's typical
        drop = getattr(self, "_pending_speed_drop", None)
        if drop is not None:
            suggestions.append({
                "text": drop["headline"],
                "action_label": "Run Speed Test →",
                "target": "Speed Test",
                "priority": "high",
                "action_key": "speed_drop",
            })

        # High-priority nudge: security audit not yet run
        qs_ns = QSettings("NetSentinel", "NetSentinel")
        if not qs_ns.value("security/any_scan_done", False, type=bool):
            suggestions.append({
                "text": "Security audit not run — check for open ports, CVEs, and TLS issues",
                "action_label": "Open Security Audit →",
                "target": "Security Overview",
                "priority": "high",
                "action_key": "security_audit_nudge",
            })

        for page_label, description in self._DISCOVERY_PAGES:
            if page_label not in visited:
                suggestions.append({
                    "text": description,
                    "action_label": "Try it →",
                    "target": page_label,
                    "priority": "low",
                })
            if len(suggestions) >= 4:
                break
        self._home_page.set_suggestions(suggestions)

    def _on_speed_drop_detected(self, payload: dict) -> None:
        """Store the latest speed-drop verdict and surface it as a Home suggestion."""
        self._pending_speed_drop = payload
        self._refresh_home_suggestions()

    # ── Pin management ────────────────────────────────────────────────────────

    def _on_rail_pin_toggle(self, label: str, is_pinned: bool) -> None:
        """Update pinned list, persist, and rebuild nav so Pinned section appears/disappears."""
        if is_pinned:
            if label not in self._nav_pinned_labels:
                if len(self._nav_pinned_labels) >= 5:
                    self._set_status("Remove a pin first — max 5 Quick Access items")
                    return
                self._nav_pinned_labels.append(label)
        else:
            if label in self._nav_pinned_labels:
                self._nav_pinned_labels.remove(label)
        self._save_pinned_labels()
        self._rebuild_nav_for_mode()

    def _on_rail_pin_move(self, label: str, direction: int) -> None:
        """Move a pinned label up (-1) or down (+1) in the ordered list and rebuild."""
        if label not in self._nav_pinned_labels:
            return
        idx = self._nav_pinned_labels.index(label)
        new_idx = max(0, min(len(self._nav_pinned_labels) - 1, idx + direction))
        if new_idx == idx:
            return
        self._nav_pinned_labels.pop(idx)
        self._nav_pinned_labels.insert(new_idx, label)
        self._save_pinned_labels()
        self._rebuild_nav_for_mode()

    def _show_pin_btn_ctx_menu(self, label: str, btn, pos) -> None:
        """Context menu for quick-access star buttons: Unpin + Move up/down."""
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.addAction(f"Unpin  {label}").triggered.connect(
            lambda: self._on_rail_pin_toggle(label, False)
        )
        if label in self._nav_pinned_labels:
            idx = self._nav_pinned_labels.index(label)
            total = len(self._nav_pinned_labels)
            menu.addSeparator()
            up_act = menu.addAction("▲ Move up")
            up_act.setEnabled(idx > 0)
            up_act.triggered.connect(lambda: self._on_rail_pin_move(label, -1))
            dn_act = menu.addAction("▼ Move down")
            dn_act.setEnabled(idx < total - 1)
            dn_act.triggered.connect(lambda: self._on_rail_pin_move(label, 1))
        menu.exec(btn.mapToGlobal(pos))

    def _on_canvas_click(self) -> None:
        """Close flyout on canvas click (only if not pinned)."""
        if hasattr(self, "_nav_flyout") and not self._nav_flyout.is_pinned:
            if self._nav_flyout.maximumWidth() > 0:
                self._nav_flyout.close_panel()
                self._nav_open_section = ""
                for btn in self._nav_rail_buttons.values():
                    btn.setChecked(False)
                if hasattr(self, "_recent_rail_btn"):
                    self._recent_rail_btn.setChecked(False)

    def _build_pro_nav(self) -> None:
        """Full nav — activity rail + flyout. No mode switcher; this is the only nav."""
        self._nav_begin_section("Getting Started", "grid")
        self._nav_add_rail_item("Home",               self._home_page)
        self._nav_add_rail_item("Dashboard",            self._overview_page)
        self._nav_add_rail_item("Speed Test",          self._speed_test_page)
        self._nav_add_rail_item("DNS & Stability",     self._m5_tab)
        self._nav_add_rail_item("What's Wrong?",       self._diagnosis_page)
        self._nav_add_rail_item("Troubleshoot",        self._troubleshoot_page)

        self._nav_begin_section("Discover", "network")
        self._nav_add_rail_item("Devices",             self._m1_tab)
        self._nav_add_rail_item("Network Map",         self._topology_tab_widget)
        self._nav_add_rail_item("WiFi Networks",       self._m4_tab)
        self._nav_add_rail_item("WiFi Heatmap",        self._wifi_heatmap_page)
        self._nav_add_rail_item("DHCP Leases",         self._dhcp_lease_page)
        self._nav_add_rail_item("DNS Zone Map",        self._dns_zone_page)
        self._nav_add_rail_item("Home Automation",     self._ha_page)

        self._nav_begin_section("Monitor", "monitor")
        self._nav_add_rail_item("Network Logger",      self._logging_container)
        self._nav_add_rail_item("Live Bandwidth",      self._live_bandwidth_page)
        self._nav_add_rail_item("App Traffic",         self._app_traffic_page)
        self._nav_add_rail_item("Active Connections",  self._connections_page)
        self._nav_add_rail_item("Syslog Viewer",       self._syslog_page)
        self._nav_add_rail_item("SNMP Trap Receiver",  self._snmp_trap_page)
        self._nav_add_rail_item("Monitor Status",      self._monitor_overview_page)
        self._nav_add_rail_item("Network Timeline",    self._timeline_page)
        self._nav_add_rail_item("Availability History", self._history_page)
        self._nav_add_rail_item("Inventory Changes",   self._inventory_page)
        self._nav_add_rail_item("Bandwidth Usage",     self._bw_tab_widget)
        self._nav_add_rail_item("Service Heartbeat",   self._service_page)
        self._nav_add_rail_item("IPv6 Devices",        self._ipv6_tab_widget)
        self._nav_add_rail_item("Uptime & SLA",        self._uptime_page)

        self._nav_begin_section("Reports", "bar-chart")
        self._nav_add_rail_item("Network Grade",       self._benchmark_tab_widget)
        self._nav_add_rail_item("Network Health Report", self._reports_page)
        self._nav_add_rail_item("Network Doc",         self._network_doc_page)
        self._nav_add_rail_item("IP Calculator",       self._ip_calc_page)
        self._nav_add_rail_item("Notifications",       self._notifications_page)

        self._nav_begin_section("Analysis", "cpu")
        self._nav_add_rail_item("Broadcast Storm",     self._m3_tab,                  npcap_required=True)
        self._nav_add_rail_item("Rogue Bridge (STP)",  self._m2_tab,                  npcap_required=True)
        self._nav_add_rail_item("IoT Behaviour",       self._iot_baseline_tab_widget, npcap_required=True)
        self._nav_add_rail_item("802.11 Monitor",      self._wifi_monitor_page,       npcap_required=True)
        self._nav_add_rail_item("ARP Spoof Watch",     self._arp_tab_widget,          npcap_required=True)
        self._nav_add_rail_item("Hop-by-Hop Trace",    self._mtr_tab_widget)
        self._nav_add_rail_item("SNMP Device Info",    self._snmp_tab_widget)
        self._nav_add_rail_item("Tools & Wake-on-LAN", self._adv_tab_widget)
        self._nav_add_rail_item("Port Scanner",        self._port_scanner_tab_widget)
        self._nav_add_rail_item("Geolocation Map",       self._geo_map_page)
        self._nav_add_rail_item("Trend Forecasts",       self._trend_page)
        self._nav_add_rail_item("Service Diagnostics",    self._service_diagnostics_page)
        self._nav_add_rail_item("Root Cause Correlator", self._correlator_tab_widget)

        self._nav_begin_section("Automation", "zap")
        self._nav_add_rail_item("Automation Hooks",    self._automation_page)
        self._nav_add_rail_item("Scheduled Scans",     self._sched_tab_widget)
        self._nav_add_rail_item("Custom Triggers",     self._trigger_page)
        self._nav_add_rail_item("MQTT / Home Assistant", self._mqtt_page)
        self._nav_add_rail_item("REST API",            self._rest_api_page)
        self._nav_add_rail_item("Config Snapshots",    self._baseline_page)
        self._nav_add_rail_item("Maintenance Windows", self._maintenance_page)

        self._nav_begin_section("Security Audit", "shield")
        self._nav_add_rail_item("Security Overview",     self._security_overview_page,     audit_item=True)
        self._nav_add_rail_item("Port Scan (TCP)",       self._recon_syn_tab_widget,       admin_required=True, audit_item=True)
        self._nav_add_rail_item("Port Scan (UDP)",       self._recon_udp_tab_widget,       admin_required=True, audit_item=True)
        self._nav_add_rail_item("CVE Lookup",            self._recon_cve_tab_widget,       audit_item=True)
        self._nav_add_rail_item("Threat Intel",          self._threat_intel_page,          audit_item=True)
        self._nav_add_rail_item("TLS & Exposure",        self._cert_page,                  audit_item=True)
        self._nav_add_rail_item("Login Test",            self._recon_cred_tab_widget,      admin_required=True, audit_item=True)
        self._nav_add_rail_item("OS Detection",          self._recon_os_tab_widget,        admin_required=True, audit_item=True)
        self._nav_add_rail_item("Device Risk Score",     self._recon_risk_tab_widget,      audit_item=True)
        self._nav_add_rail_item("CVE Tracker",           self._cve_page,                   audit_item=True)
        self._nav_add_rail_item("Exposed to Internet",   self._recon_exposure_tab_widget,  audit_item=True)
        self._nav_add_rail_item("Full Device Discovery", self._recon_discovery_tab_widget, admin_required=True, audit_item=True)
        self._nav_add_rail_item("Windows Shares (SMB)",  self._recon_smb_tab_widget,       audit_item=True)
        self._nav_add_rail_item("Recon Plugins",         self._recon_plugin_tab_widget,    audit_item=True)
        self._nav_add_rail_item("Private Endpoint Check", self._recon_pe_tab_widget,       audit_item=True)
        self._nav_add_rail_item("Cloud Metadata Probe",  self._recon_cloud_tab_widget,     audit_item=True)
        self._nav_add_rail_item("DHCP Rogue Monitor",    self._dhcp_tab_widget,            admin_required=True, audit_item=True)

        self._nav_begin_section("Education", "book-open")
        self._nav_add_rail_item("Protocol Visualizer", self._protocol_viz_page)
        self._nav_add_rail_item("Lab Mode",            self._lab_mode_page)
        self._nav_add_rail_item("Feature Guide",       self._discover_page)
        self._nav_add_rail_item("Help & Reference",    self._help_tab_widget)

        self._nav_begin_section("Extend", "plug")
        self._nav_add_rail_item("Hardware",        self._hardware_integration_page)
        for _hw_p, _pg in getattr(self, "_plugin_pages", {}).items():
            self._nav_add_rail_item(_pg._label, _pg)

    def _load_pinned_labels(self) -> list:
        try:
            from PyQt6.QtCore import QSettings as _QS
            s = _QS(str(self._settings_path()), _QS.Format.IniFormat)
            raw = s.value("nav/pinned_labels", "")
            return list(filter(None, raw.split("|||"))) if raw else []
        except Exception:
            return []

    def _save_pinned_labels(self) -> None:
        try:
            from PyQt6.QtCore import QSettings as _QS
            s = _QS(str(self._settings_path()), _QS.Format.IniFormat)
            s.setValue("nav/pinned_labels", "|||".join(self._nav_pinned_labels))
        except Exception:
            pass  # non-fatal

    def _build_favourites_section(self) -> None:
        """Prepend a Favourites section when the user has pinned at least one page."""
        if not self._nav_pinned_labels:
            return
        self._nav_add_section_label("Favourites")
        for label in self._nav_pinned_labels:
            widget = self._nav_label_to_widget.get(label)
            if widget is not None:
                self._nav_ref("★", label, widget)

    def _toggle_pin_label(self, label: str) -> None:
        if label in self._nav_pinned_labels:
            self._nav_pinned_labels.remove(label)
        else:
            self._nav_pinned_labels.append(label)
        self._save_pinned_labels()
        self._rebuild_nav_for_mode()

    def _nav_context_menu(self, pos) -> None:
        from PyQt6.QtWidgets import QMenu
        item = self._nav.itemAt(pos)
        if item is None:
            return
        row = self._nav.row(item)
        if row in self._nav_header_rows or row in self._nav_action_rows:
            return
        label = self._nav_item_labels.get(row, "")
        if not label:
            return
        menu = QMenu()
        if label in self._nav_pinned_labels:
            act = menu.addAction("★  Remove from Favourites")
        else:
            act = menu.addAction("☆  Pin to Favourites")
        chosen = menu.exec(self._nav.viewport().mapToGlobal(pos))
        if chosen is act:
            self._toggle_pin_label(label)

    # ── Monitoring state helpers (NAV-2) ──────────────────────────────────────

    _MONITOR_PAGES: dict = {
        L.ARP_SPOOF_WATCH:     "_arp_worker",
        L.DHCP_ROGUE_MONITOR:  "_dhcp_worker",
        L.LIVE_BANDWIDTH:      "_bw_worker",
    }

    def _is_monitor_running(self, worker_attr: str) -> bool:
        w = getattr(self, worker_attr, None)
        return bool(w and w.isRunning())

    # ── Recent-action recording (RECUR-3) ─────────────────────────────────────

    def _record_recent_action(self, action_id: str, label: str, page: str, params: dict) -> None:
        import json as _json
        qs = QSettings("NetSentinel", "NetSentinel")
        try:
            existing: list = _json.loads(qs.value("recur/recent_actions", "[]"))
        except Exception:
            existing = []
        existing = [a for a in existing if a.get("id") != action_id]
        existing.insert(0, {"id": action_id, "label": label, "page": page, "params": params})
        qs.setValue("recur/recent_actions", _json.dumps(existing[:10]))

    def _build_palette_items(self) -> list:
        import json as _json

        recent_items: list = []
        try:
            recent = _json.loads(
                QSettings("NetSentinel", "NetSentinel").value("recur/recent_actions", "[]")
            )
        except Exception:
            recent = []
        if recent:
            recent_items.append({"label": "Recent", "kind": "separator"})
            for a in recent[:5]:
                recent_items.append({
                    "icon": "⟳", "label": a["label"], "kind": "recent",
                    "id": a["id"], "page": a["page"], "params": a.get("params", {}),
                })

        _PAGE_SHORTCUTS: dict[str, str] = {
            "Overview":        "Alt+1",
            "Devices":         "Alt+2",
            "Speed Test":      "Alt+3",
            "What's Wrong?":   "Alt+4",
            "Network Logger":  "Alt+5 / Ctrl+L",
            "Settings":        "Ctrl+,",
        }
        seen: set = set()
        pages = []
        for sec in self._nav_sections:
            for entry in sec["entries"]:
                if entry.label and entry.label not in seen:
                    seen.add(entry.label)
                    worker_attr = self._MONITOR_PAGES.get(entry.label)
                    sc = _PAGE_SHORTCUTS.get(entry.label, "")
                    if worker_attr:
                        running = self._is_monitor_running(worker_attr)
                        state = "● Monitoring" if running else "○ Not running"
                        pages.append({
                            "icon": "◎",
                            "label": f"{entry.label}  {state}",
                            "kind": "page",
                            "real_label": entry.label,
                            "shortcut": sc,
                        })
                        if not running:
                            pages.append({
                                "icon": "▶",
                                "label": f"Start {entry.label}",
                                "kind": "action",
                            })
                    else:
                        pages.append({"icon": "◎", "label": entry.label, "kind": "page", "shortcut": sc})

        if recent_items:
            pages_section = [{"label": "Pages", "kind": "separator"}] + pages
        else:
            pages_section = pages

        # Feature items — enable intent-based searches like "slow internet", "rogue device"
        feat_section: list = []
        try:
            from ui.pages.discover_data import _FEATURES as _feat_list
            _feat_items: list = []
            for _f in _feat_list:
                _pg = _f.get("page")
                if not _pg:
                    continue
                _name = _f["name"]
                _desc = _f["desc"]
                _first = _desc.split(".")[0] if "." in _desc else _desc[:80]
                _tags = " ".join(_f.get("tags", []))
                _feat_items.append({
                    "icon": _f.get("icon", "⬡"),
                    "label": f"{_name} — {_first}",
                    "kind": "page",
                    "real_label": _pg,
                    "search": f"{_name} {_desc} {_tags}".lower(),
                })
            if _feat_items:
                feat_section = [{"label": "Features", "kind": "separator"}] + _feat_items
        except Exception:
            pass  # non-fatal — discover_data not importable

        actions = [
            {"icon": "⟳", "label": "Run Full Scan",          "kind": "action"},
            {"icon": "⚡", "label": "Start Speed Test",       "kind": "action", "shortcut": "Alt+3"},
            {"icon": "◈", "label": "Run Diagnosis",          "kind": "action", "shortcut": "Alt+4"},
            {"icon": "▣", "label": "Export Report",          "kind": "action"},
            {"icon": "⊕", "label": "Add Monitored Service",  "kind": "action"},
            {"icon": "▲", "label": "View Alert History",     "kind": "action"},
            {"icon": "◆", "label": "Copy API Key",           "kind": "action"},
            {"icon": "▤", "label": "Open Network Doc",       "kind": "action"},
            {"icon": "⚙", "label": "Open Settings",          "kind": "action", "shortcut": "Ctrl+,"},
            {"icon": "◄", "label": "Toggle Sidebar",         "kind": "action"},
            {"icon": "◎", "label": "Give Feedback",          "kind": "action"},
        ]
        return recent_items + pages_section + feat_section + actions

    def _open_command_palette(self) -> None:
        from ui.command_palette import CommandPalette
        # Toggle: close if already visible
        existing = getattr(self, "_cmd_palette", None)
        if existing is not None:
            try:
                if existing.isVisible():
                    existing.reject()
                    return
                # Not visible → a stale palette closed by Esc/selection on a
                # prior open. It is a C++ child of this window, so it is NOT
                # freed until the window closes; without deleting it here, every
                # Ctrl+K after a close leaks a whole palette (its ~120 list items
                # + cached device/alert data), which is what drove the moderate
                # soak from ~600 MB to >1.2 GB and a Not-Responding hang.
                existing.deleteLater()
            except RuntimeError:
                pass  # non-fatal — palette may have already been deleted
        items = self._build_palette_items()
        pal = CommandPalette(items, parent=self)
        pal.load_recent_data(self._store)
        pal.page_requested.connect(self._nav_rail_go_to)
        pal.action_requested.connect(self._on_palette_action)
        self._cmd_palette = pal  # keep alive; prevents GC before user interaction
        pal.show()

    def _open_shortcut_overlay(self) -> None:
        """Show the keyboard shortcut reference overlay (KEYBOARD-1)."""
        from PyQt6.QtWidgets import QDialog, QDialogButtonBox
        dlg = QDialog(self)
        dlg.setWindowTitle("Keyboard Shortcuts")
        dlg.setMinimumWidth(420)
        dlg.setModal(True)
        dlg.setStyleSheet(
            f"QDialog {{ background:{_s.BG_CARD}; }}"
            f"QLabel {{ color:{_s.TEXT_PRIMARY}; background:transparent; }}"
        )
        from PyQt6.QtWidgets import QVBoxLayout as _QVL, QWidget as _QW, QHBoxLayout as _QHL
        vlay = _QVL(dlg)
        vlay.setContentsMargins(20, 16, 20, 16)
        vlay.setSpacing(8)
        hdr = QLabel("Keyboard Shortcuts")
        hdr.setStyleSheet(f"font-size:15px; font-weight:bold; color:{_s.TEXT_PRIMARY};")
        vlay.addWidget(hdr)
        shortcuts = [
            ("?",           "Show this reference"),
            ("Ctrl+K",      "Command palette"),
            ("Ctrl+F",      "Focus nav search"),
            ("Ctrl+,",      "Settings"),
            ("Ctrl+L",      "Network Logger"),
            ("Ctrl+Shift+H","Quick Check Window"),
            ("Ctrl+Q",      "Quit"),
            ("Alt+1",       "Overview"),
            ("Alt+2",       "Devices"),
            ("Alt+3",       "Speed Test"),
            ("Alt+4",       "What's Wrong?"),
            ("Alt+5",       "Network Logger"),
            ("J / K",       "Next / previous row in tables"),
            ("Escape",      "Close panel / flyout"),
        ]
        for key, desc in shortcuts:
            row_w = _QW()
            row_w.setStyleSheet("background:transparent;")
            row_lay = _QHL(row_w)
            row_lay.setContentsMargins(0, 2, 0, 2)
            key_lbl = QLabel(key)
            key_lbl.setFixedWidth(110)
            key_lbl.setStyleSheet(
                f"font-family:monospace; font-size:11px; font-weight:bold;"
                f" color:{_s.ACCENT}; background:{_s.CHART_SPINE};"
                f" border:1px solid {_s.BORDER}; border-radius:3px; padding:1px 5px;"
            )
            desc_lbl = QLabel(desc)
            desc_lbl.setStyleSheet(f"font-size:11px; color:{_s.TEXT_SECONDARY};")
            row_lay.addWidget(key_lbl)
            row_lay.addSpacing(12)
            row_lay.addWidget(desc_lbl, 1)
            vlay.addWidget(row_w)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(dlg.accept)
        btns.button(QDialogButtonBox.StandardButton.Close).setStyleSheet(
            f"QPushButton {{ background:{_s.ACCENT}; color:{_s.WHITE}; border:none;"
            f" border-radius:4px; padding:4px 14px; }}"
            f"QPushButton:pressed {{ color:{_s.TEXT_PRIMARY}; }}"
        )
        vlay.addSpacing(4)
        vlay.addWidget(btns)
        run_dialog(dlg)

    def _on_palette_action(self, action: str) -> None:
        if action.startswith("__device__"):
            ip_or_mac = action[len("__device__"):]
            self._nav_rail_go_to(L.INVENTORY_CHANGES)
            if hasattr(self, "_inventory_page"):
                self._inventory_page.select_device(ip_or_mac)
        elif action.startswith("__alert__"):
            import json as _json
            try:
                alert_dict = _json.loads(action[len("__alert__"):])
                if hasattr(self, "_notifications_page"):
                    self._nav_rail_go_to(L.NOTIFICATIONS)
                    self._notifications_page._alert_drawer.open(alert_dict)
            except Exception:
                pass  # non-fatal
        elif action.startswith("__recent__"):
            self._replay_recent_action(action[len("__recent__"):])
        elif action == "Run Full Scan":
            self._start_full_scan()
        elif action in ("Start Speed Test", "Run Speed Test"):
            self._nav_rail_go_to(L.SPEED_TEST)
            if hasattr(self, "_speed_test_page"):
                self._speed_test_page.scan_requested.emit()
        elif action in ("Run Diagnosis", "Diagnose Network"):
            self._open_diagnosis()
        elif action == "Export Report":
            self._export_report()
        elif action == "Add Monitored Service":
            self._nav_rail_go_to(L.SERVICE_HEARTBEAT)
        elif action == "View Alert History":
            self._nav_rail_go_to(L.NOTIFICATIONS)
            if hasattr(self, "_notifications_page"):
                self._notifications_page.switch_to_history_tab()
        elif action == "Copy API Key":
            try:
                from modules.rest_api import get_or_create_api_key
                from PyQt6.QtWidgets import QApplication as _QApp
                key = get_or_create_api_key()
                if key:
                    _QApp.clipboard().setText(key)
            except Exception:
                pass  # non-fatal — REST API may be disabled
        elif action == "Open Network Doc":
            self._nav_rail_go_to(L.NETWORK_DOC)
            if hasattr(self, "_network_doc_page"):
                self._network_doc_page._generate()
        elif action == "Open Settings":
            self._open_settings_dialog()
        elif action == "Toggle Sidebar":
            self._toggle_sidebar()
        elif action == "Give Feedback":
            from ui.widgets.feedback_dialog import show_feedback_dialog
            show_feedback_dialog(self)
        elif action == "Start ARP Spoof Watch":
            self._nav_rail_go_to(L.ARP_SPOOF_WATCH)
            self._start_arp_monitor()
        elif action == "Start DHCP Rogue Monitor":
            self._nav_rail_go_to(L.DHCP_ROGUE_MONITOR)
            self._start_dhcp_scan()
        elif action == "Start Bandwidth Monitor":
            self._nav_rail_go_to(L.LIVE_BANDWIDTH)
            self._start_bandwidth_monitor()

    def _replay_recent_action(self, action_id: str) -> None:
        import json as _json
        qs = QSettings("NetSentinel", "NetSentinel")
        try:
            recent: list = _json.loads(qs.value("recur/recent_actions", "[]"))
        except Exception:
            return
        action = next((a for a in recent if a.get("id") == action_id), None)
        if action is None:
            return
        page = action.get("page", "")
        params = action.get("params", {})
        self._nav_rail_go_to(page)
        if page == "Port Scan (TCP)" and hasattr(self, "_syn_host"):
            self._syn_host.setText(params.get("host", ""))
        elif page == "Port Scanner" and hasattr(self, "_ps_host"):
            self._ps_host.setText(params.get("host", ""))
        elif page == "Hop-by-Hop Trace" and hasattr(self, "_mtr_target"):
            self._mtr_target.setText(params.get("target", ""))

    def _on_overview_navigate(self, label: str) -> None:
        if label == "Diagnose Network":
            self._open_diagnosis()
        else:
            self._nav_rail_go_to(label)
            if label == "Notifications" and hasattr(self, "_notifications_page"):
                self._notifications_page.switch_to_history_tab(unacked_only=True)

    def _open_diagnosis(self) -> None:
        self._nav_rail_go_to(L.WHATS_WRONG)
