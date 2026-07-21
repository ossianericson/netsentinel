"""
Automation Page — rule builder and automation log panel.

Displays:
  - Rule table: Name | Trigger | Match | Script | Enabled | Actions
  - Rule editor dialog (Add / Edit)
  - Automation Log panel: streaming stdout/stderr from script runs
  - Built-in templates row (WoL, Log to File)
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import (
    Qt, QThread, pyqtSignal, pyqtSlot,
)
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QSplitter, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from ui import styles as _s
from modules.automation_hooks import (
    AutomationEngine, AutomationRule, Trigger,
    template_wol, template_log_to_file, get_engine,
)
from ui.widgets.context_menu import install_copy_menu
from ui.widgets.empty_state_card import EmptyStateCard
from ui.dialog_utils import run_dialog


# ── Card / layout helpers ─────────────────────────────────────────────────────

def _card(title: str) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("card")
    _s.themed_ss(frame, "QFrame#card {{ background:{BG_CARD}; border:1px solid {BORDER}; border-radius:{CARD_RADIUS}; }}")
    outer = QVBoxLayout(frame)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)
    hdr = QFrame()
    hdr.setFixedHeight(32)
    _s.themed_ss(hdr, "background:{BG_CARD}; border-bottom:1px solid {CARD_HDR_BORDER}; border-radius:0px;")
    hdr_lay = QHBoxLayout(hdr)
    hdr_lay.setContentsMargins(12, 0, 10, 0)
    t = QLabel(title.upper())
    _s.themed_ss(t, "color:{TEXT_PRIMARY}; font-weight:bold; font-size:11px;"
        " letter-spacing:0.5px; background:transparent; border:none;")
    hdr_lay.addWidget(t)
    hdr_lay.addStretch()
    outer.addWidget(hdr)
    body = QVBoxLayout()
    body.setContentsMargins(0, 0, 0, 0)
    body.setSpacing(0)
    outer.addLayout(body, 1)
    return frame, body, hdr_lay


def _table_style() -> str:
    return (
        f"QTableWidget {{ border:none; font-size:11px; color:{_s.TEXT_PRIMARY}; }}"
        f"QHeaderView::section {{"
        f"  background:{_s.TH_BG}; color:{_s.TH_TEXT}; font-size:11px;"
        f"  font-weight:bold; padding:4px 5px; border:none;"
        f"  border-right:1px solid {_s.TH_BORDER};"
        f"}}"
        f"QTableWidget::item:selected {{ background:{_s.TABLE_SEL}; color:{_s.TEXT_PRIMARY}; }}"
        f"QTableWidget::item:alternate {{ background:{_s.BG_ALT_ROW}; }}"
        f"QTableWidget::item {{ border-bottom:1px solid {_s.TABLE_ROW_BORDER}; }}"
        f"QTableWidget::item:hover {{ background:{_s.BG_HOVER}; }}"
    )


# ── Rule Editor Dialog ────────────────────────────────────────────────────────

_TRIGGER_LABELS = {
    Trigger.DEVICE_JOINED.value: "Device Joined",
    Trigger.DEVICE_LEFT.value:   "Device Left",
    Trigger.ALERT_FIRED.value:   "Alert Fired",
}
_MATCH_FIELDS = ["any", "mac", "ip", "hostname", "alert_level"]


class RuleEditorDialog(QDialog):
    """Modal dialog for creating or editing an automation rule."""

    def __init__(self, rule: Optional[AutomationRule] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Automation Rule" if rule else "New Automation Rule")
        self.setMinimumWidth(520)
        self._rule = rule or AutomationRule()

        form = QFormLayout(self)
        form.setContentsMargins(16, 16, 16, 8)
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        _lbl_qss = "color:{TEXT_PRIMARY}; font-size:11px;"
        _in_qss  = (
            "QLineEdit {{ background:{BG_CARD}; border:1px solid {BORDER};"
            " border-radius:2px; padding:3px 6px; font-size:11px; color:{TEXT_PRIMARY}; }}"
            "QLineEdit:focus {{ border-color:{ACCENT}; }}"
        )
        _cb_qss = (
            "QComboBox {{ background:{BG_CARD}; border:1px solid {BORDER};"
            " border-radius:2px; padding:3px 6px; font-size:11px; color:{TEXT_PRIMARY}; }}"
        )

        self._name = QLineEdit(self._rule.name)
        _s.themed_ss(self._name, _in_qss)

        self._trigger = QComboBox()
        _s.themed_ss(self._trigger, _cb_qss)
        for val, lbl in _TRIGGER_LABELS.items():
            self._trigger.addItem(lbl, val)
        idx = self._trigger.findData(self._rule.trigger)
        if idx >= 0:
            self._trigger.setCurrentIndex(idx)

        self._match_field = QComboBox()
        _s.themed_ss(self._match_field, _cb_qss)
        for f in _MATCH_FIELDS:
            self._match_field.addItem(f)
        fi = self._match_field.findText(self._rule.match_field)
        if fi >= 0:
            self._match_field.setCurrentIndex(fi)

        self._match_value = QLineEdit(self._rule.match_value)
        self._match_value.setPlaceholderText("* = any")
        _s.themed_ss(self._match_value, _in_qss)

        # Script path row with Browse button
        script_row = QHBoxLayout()
        self._script_path = QLineEdit(self._rule.script_path)
        self._script_path.setPlaceholderText("Path to .ps1 / .bat / .py / .sh")
        _s.themed_ss(self._script_path, _in_qss)
        btn_browse = QPushButton("Browse…")
        btn_browse.setFixedWidth(72)
        _s.themed_ss(btn_browse, "QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
            " border-radius:2px; padding:3px 8px; font-size:11px; }}"
            "QPushButton:hover {{ background:{ACCENT_DARK}; color:{WHITE}; }}"
            "QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}")
        btn_browse.clicked.connect(self._browse)
        script_row.addWidget(self._script_path, 1)
        script_row.addWidget(btn_browse)

        self._args = QLineEdit(self._rule.args)
        self._args.setPlaceholderText("e.g. -Target $MAC  (use $MAC, $IP, $HOSTNAME, $ALERT_LEVEL)")
        _s.themed_ss(self._args, _in_qss)

        self._webhook_url = QLineEdit(self._rule.webhook_url)
        self._webhook_url.setPlaceholderText("https://hooks.slack.com/... (optional)")
        _s.themed_ss(self._webhook_url, _in_qss)

        self._description = QLineEdit(self._rule.description)
        _s.themed_ss(self._description, _in_qss)

        self._enabled = QCheckBox("Rule enabled")
        self._enabled.setChecked(self._rule.enabled)
        _s.themed_ss(self._enabled, "color:{TEXT_PRIMARY}; font-size:11px;")

        for label, widget in [
            ("Name:",        self._name),
            ("Trigger:",     self._trigger),
            ("Match field:", self._match_field),
            ("Match value:", self._match_value),
            ("Script:",      None),
            ("Args:",        self._args),
            ("Webhook URL:", self._webhook_url),
            ("Notes:",       self._description),
            ("",             self._enabled),
        ]:
            lbl = QLabel(label)
            _s.themed_ss(lbl, _lbl_qss)
            if label == "Script:":
                w = QWidget()
                w.setLayout(script_row)
                form.addRow(lbl, w)
            else:
                form.addRow(lbl, widget)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel,
        )
        btns.accepted.connect(self._commit)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Script",
            str(Path.home()),
            "Scripts (*.ps1 *.bat *.cmd *.py *.sh *.exe);;All files (*)",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if path:
            self._script_path.setText(path)

    def _commit(self) -> None:
        self._rule.name        = self._name.text().strip() or "Rule"
        self._rule.trigger     = self._trigger.currentData()
        self._rule.match_field = self._match_field.currentText()
        self._rule.match_value = self._match_value.text().strip() or "*"
        self._rule.script_path = self._script_path.text().strip()
        self._rule.args        = self._args.text().strip()
        self._rule.webhook_url = self._webhook_url.text().strip()
        self._rule.description = self._description.text().strip()
        self._rule.enabled     = self._enabled.isChecked()
        self.accept()

    def get_rule(self) -> AutomationRule:
        return self._rule


# ── Test-run worker ───────────────────────────────────────────────────────────

class _TestRunWorker(QThread):
    """Run a rule's script once with dummy event data for testing."""

    log_line = pyqtSignal(str, str, str)   # rule_id, stream, text
    finished = pyqtSignal()

    def __init__(self, rule: AutomationRule, parent=None):
        super().__init__(parent)
        self._rule = rule

    def run(self) -> None:
        dummy = {
            "mac": "AA:BB:CC:DD:EE:FF",
            "ip":  "192.168.1.100",
            "hostname": "test-device",
            "alert_level": "HIGH",
        }
        engine = get_engine()
        engine._run_rule(self._rule, dummy, self.log_line.emit)
        self.finished.emit()


# ── Main page ─────────────────────────────────────────────────────────────────

class AutomationPage(QWidget):
    """
    Automation Hooks page — build trigger → script rules and view their output.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._engine: AutomationEngine = get_engine()
        self._test_worker = None
        self._content_stack = None  # set in _setup_ui
        self._setup_ui()
        self._reload_table()

    # ── UI construction ───────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # Page header
        from ui.widgets.page_header import PageHeaderBar
        _hdr = PageHeaderBar("Automation Hooks", subtitle="Run custom commands automatically when network events occur.")
        _hdr.show_first_visit_banner(
            "automation_hooks",
            "Each rule pairs a trigger — like a device going offline — with a shell command "
            "to run automatically. Start with one simple rule before building out a full pipeline.",
        )
        root.addWidget(_hdr)

        splitter = QSplitter(Qt.Orientation.Vertical)

        # ── Rules card ────────────────────────────────────────────────────────
        rules_frame, rules_body, rules_hdr_lay = _card("Automation Rules")

        # Toolbar in card header
        btn_add = QPushButton("+ Add Rule")
        btn_add.setFixedHeight(22)
        _s.themed_ss(btn_add, "QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
            " border-radius:2px; padding:0 10px; font-size:11px; }}"
            "QPushButton:hover {{ background:{ACCENT_DARK}; color:{WHITE}; }}"
            "QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}")
        btn_add.clicked.connect(self._add_rule)
        self._btn_edit = QPushButton("Edit")
        self._btn_edit.setFixedHeight(22)
        self._btn_edit.setEnabled(False)
        self._btn_edit.clicked.connect(self._edit_rule)
        self._btn_del  = QPushButton("Delete")
        self._btn_del.setFixedHeight(22)
        self._btn_del.setEnabled(False)
        self._btn_del.clicked.connect(self._delete_rule)
        self._btn_test = QPushButton("▶ Test")
        self._btn_test.setFixedHeight(22)
        self._btn_test.setEnabled(False)
        self._btn_test.clicked.connect(self._test_rule)

        for btn in (self._btn_edit, self._btn_del, self._btn_test):
            _s.themed_ss(btn, "QPushButton {{ background:{BG_CARD}; color:{TEXT_PRIMARY};"
                " border:1px solid {BORDER}; border-radius:2px;"
                " padding:0 8px; font-size:11px; }}"
                "QPushButton:hover {{ background:{BG_HOVER}; }}"
                "QPushButton:disabled {{ color:{TEXT_MUTED}; }}"
                "QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}")
        rules_hdr_lay.addWidget(btn_add)
        rules_hdr_lay.addSpacing(6)
        rules_hdr_lay.addWidget(self._btn_edit)
        rules_hdr_lay.addWidget(self._btn_del)
        rules_hdr_lay.addWidget(self._btn_test)

        # Templates row
        tpl_row = QHBoxLayout()
        tpl_row.setContentsMargins(8, 6, 8, 4)
        tpl_row.setSpacing(6)
        tpl_lbl = QLabel("Templates:")
        _s.themed_ss(tpl_lbl, "color:{TEXT_MUTED}; font-size:10px; border:none; background:transparent;")
        tpl_row.addWidget(tpl_lbl)
        for label, fn in [("WoL on Join", template_wol), ("Log to File", template_log_to_file)]:
            b = QPushButton(label)
            b.setFixedHeight(20)
            _s.themed_ss(b, "QPushButton {{ background:transparent; color:{ACCENT}; border:1px solid {ACCENT};"
                " border-radius:2px; padding:0 8px; font-size:10px; }}"
                "QPushButton:hover {{ background:{ACCENT}; color:{WHITE}; }}"
                "QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}")
            b.clicked.connect(lambda _, f=fn: self._add_template(f))
            tpl_row.addWidget(b)
        tpl_row.addStretch()

        # Rules table
        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(
            ["Name", "Trigger", "Match", "Script", "Enabled", ""]
        )
        self._table.horizontalHeader().setStretchLastSection(False)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self._table.setColumnWidth(1, 120)
        self._table.setColumnWidth(2, 140)
        self._table.setColumnWidth(4, 60)
        self._table.setColumnWidth(5, 24)
        self._table.setAlternatingRowColors(True)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(24)
        _s.themed_ss(self._table, _table_style)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        self._table.doubleClicked.connect(self._edit_rule)

        def _auto_copy_name():
            r = self._table.currentRow()
            if r >= 0:
                it = self._table.item(r, 0)
                if it:
                    from PyQt6.QtWidgets import QApplication as _QApp
                    _QApp.clipboard().setText(it.text())

        def _auto_run_now():
            self._test_rule()

        def _auto_toggle_enabled():
            rule = self._selected_rule()
            if rule is None:
                return
            rule.enabled = not rule.enabled
            self._engine.update_rule(rule)
            self._reload_table()

        install_copy_menu(self._table, [
            ("separator",         None),
            ("Copy name",         _auto_copy_name),
            ("separator",         None),
            ("Enable / Disable",  _auto_toggle_enabled),
            ("separator",         None),
            ("Run now",           _auto_run_now),
        ])

        rules_body.addLayout(tpl_row)
        rules_body.addWidget(self._table)
        splitter.addWidget(rules_frame)

        # ── Log card ──────────────────────────────────────────────────────────
        log_frame, log_body, log_hdr_lay = _card("Automation Log")
        btn_clear = QPushButton("Clear")
        btn_clear.setFixedHeight(22)
        _s.themed_ss(btn_clear, "QPushButton {{ background:transparent; color:{TEXT_MUTED}; border:1px solid {BORDER};"
            " border-radius:2px; padding:0 8px; font-size:11px; }}"
            "QPushButton:hover {{ background:{BG_HOVER}; }}"
            "QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_MUTED}; }}")
        btn_clear.clicked.connect(self._clear_log)
        log_hdr_lay.addWidget(btn_clear)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setFont(QFont("Consolas", 9))
        _s.themed_ss(self._log, "QPlainTextEdit {{ background:{BG_CARD}; color:{TEXT_PRIMARY};"
            " border:none; padding:4px 8px; }}")
        self._log.setMaximumBlockCount(2000)
        self._log.appendPlainText("Ready. Use ▶ Test to run a rule with dummy event data.")
        log_body.addWidget(self._log)
        splitter.addWidget(log_frame)

        splitter.setSizes([350, 200])

        # ── Empty state + content stack ───────────────────────────────────────
        from PyQt6.QtWidgets import QStackedWidget
        self._content_stack = QStackedWidget()

        _empty = EmptyStateCard(
            icon="⚙",
            title="Automation Hooks",
            what_it_shows=(
                "Event-driven rules that run a shell command or script when "
                "something happens on your network — device joined, alert fired, etc."
            ),
            why_it_matters=(
                "Automate repetitive responses: send a WoL packet when a device "
                "rejoins, log every alert to a file, or ping a webhook."
            ),
            btn_label="Add First Rule",
        )
        _empty.clicked.connect(self._add_rule)
        self._content_stack.addWidget(_empty)    # index 0 — empty state
        self._content_stack.addWidget(splitter)  # index 1 — content
        root.addWidget(self._content_stack, 1)

    # ── Table management ──────────────────────────────────────────────────────

    def _reload_table(self) -> None:
        rules = self._engine.get_rules()
        self._table.setRowCount(0)
        for rule in rules:
            self._append_row(rule)
        self._on_selection_changed()
        if self._content_stack is not None:
            self._content_stack.setCurrentIndex(1 if rules else 0)

    def _append_row(self, rule: AutomationRule) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)

        self._table.setItem(row, 0, QTableWidgetItem(rule.name))

        trig_item = QTableWidgetItem(_TRIGGER_LABELS.get(rule.trigger, rule.trigger))
        trig_color = {"device_joined": _s.GREEN, "device_left": _s.AMBER, "alert_fired": _s.RED}
        trig_item.setForeground(QColor(trig_color.get(rule.trigger, _s.TEXT_MUTED)))
        self._table.setItem(row, 1, trig_item)

        match_str = f"{rule.match_field}={rule.match_value}" if rule.match_field not in ("any", "") else "any"
        self._table.setItem(row, 2, QTableWidgetItem(match_str))
        self._table.setItem(row, 3, QTableWidgetItem(rule.script_path))

        enabled_item = QTableWidgetItem("● Yes" if rule.enabled else "○ No")
        enabled_item.setForeground(QColor(_s.GREEN if rule.enabled else _s.TEXT_MUTED))
        self._table.setItem(row, 4, enabled_item)

        # Store rule id in col 5
        id_item = QTableWidgetItem(rule.id)
        id_item.setForeground(QColor(_s.TEXT_MUTED))
        self._table.setItem(row, 5, id_item)

    def _selected_rule_id(self) -> Optional[str]:
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, 5)
        return item.text() if item else None

    def _selected_rule(self) -> Optional[AutomationRule]:
        rule_id = self._selected_rule_id()
        if not rule_id:
            return None
        for r in self._engine.get_rules():
            if r.id == rule_id:
                return r
        return None

    @pyqtSlot()
    def _on_selection_changed(self) -> None:
        has = self._selected_rule_id() is not None
        self._btn_edit.setEnabled(has)
        self._btn_del.setEnabled(has)
        self._btn_test.setEnabled(has)

    # ── Rule actions ──────────────────────────────────────────────────────────

    @pyqtSlot()
    def prefill_rule(self, rule_name: str, match_value: str) -> None:
        """Open the rule editor pre-filled with ALERT_FIRED trigger and a match value."""
        seed = AutomationRule()
        seed.name        = f"On: {rule_name}" if rule_name else "New Rule"
        seed.trigger     = Trigger.ALERT_FIRED.value
        seed.match_field = "alert_level"
        seed.match_value = match_value or "*"
        dlg = RuleEditorDialog(rule=seed, parent=self)
        if run_dialog(dlg) == QDialog.DialogCode.Accepted:
            self._engine.add_rule(dlg.get_rule())
            self._reload_table()

    def _add_rule(self) -> None:
        dlg = RuleEditorDialog(parent=self)
        if run_dialog(dlg) == QDialog.DialogCode.Accepted:
            self._engine.add_rule(dlg.get_rule())
            self._reload_table()

    @pyqtSlot()
    def _edit_rule(self) -> None:
        rule = self._selected_rule()
        if not rule:
            return
        dlg = RuleEditorDialog(rule=rule, parent=self)
        if run_dialog(dlg) == QDialog.DialogCode.Accepted:
            self._engine.update_rule(dlg.get_rule())
            self._reload_table()

    @pyqtSlot()
    def _delete_rule(self) -> None:
        rule_id = self._selected_rule_id()
        if rule_id:
            self._engine.delete_rule(rule_id)
            self._reload_table()

    @pyqtSlot()
    def _test_rule(self) -> None:
        rule = self._selected_rule()
        if not rule:
            return
        if self._test_worker and self._test_worker.isRunning():
            return
        self._btn_test.setEnabled(False)
        self._btn_test.setText("⏳")
        self._log.appendPlainText(f"\n── Test run: '{rule.name}' ──")
        self._test_worker = _TestRunWorker(rule, parent=self)
        self._test_worker.log_line.connect(self._on_log_line)
        self._test_worker.finished.connect(self._on_test_done)
        self._test_worker.start()

    def _add_template(self, factory) -> None:
        rule = factory()
        dlg = RuleEditorDialog(rule=rule, parent=self)
        if run_dialog(dlg) == QDialog.DialogCode.Accepted:
            self._engine.add_rule(dlg.get_rule())
            self._reload_table()

    # ── Log panel ─────────────────────────────────────────────────────────────

    @pyqtSlot(str, str, str)
    def _on_log_line(self, rule_id: str, stream: str, text: str) -> None:
        prefix = {"stdout": "  ", "stderr": "! ", "system": "# "}.get(stream, "  ")
        self._log.appendPlainText(f"{prefix}{text}")

    @pyqtSlot()
    def _on_test_done(self) -> None:
        self._btn_test.setText("▶ Test")
        self._on_selection_changed()
        self._log.appendPlainText("── Done ──\n")

    @pyqtSlot()
    def _clear_log(self) -> None:
        self._log.clear()

    # ── Public slot: evaluate event from outside ──────────────────────────────

    def evaluate_event(self, trigger: str, event_data: dict) -> None:
        """Called by the dashboard when a network event fires."""
        self._engine.evaluate(trigger, event_data, self._on_log_line)
