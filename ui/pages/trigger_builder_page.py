"""
TriggerBuilderPage — Visual rule builder for custom alert trigger expressions.

Layout
──────
  Top:    Page title + subtitle
  Left (splitter, 360px):
    - Rule table: Name | Severity | Expression | Status | Actions
    - Add / Edit / Delete buttons
  Right (splitter):
    - Expression editor card:
        • Raw expression text area (free-form)
        • OR dropdown-based builder row (metric | operator | value | window)
        • Live preview label — plain-English description of the expression
        • Validate / Test button
    - Fired log card: recent test fires

All metric fetches use MetricStore (injected). If MetricStore is None or
no data exists, the test fires with NaN values and shows a "no data" message.
"""

from __future__ import annotations

import math
from typing import List, Optional

from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from modules.trigger_expression import (
    TriggerFired,
    TriggerRule,
    evaluate,
    load_rules,
    new_rule_id,
    preview_expression,
    save_rules,
)
from ui.widgets.context_menu import install_copy_menu
from ui.styles import (
    ACCENT, ACCENT_DARK, AMBER, BG_ALT_ROW,
    BG_CARD, BG_HOVER, BORDER, CARD_HDR_BORDER,
    CARD_RADIUS, GREEN, INPUT_PLACEHOLDER,
    RED, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
    TH_BG, TH_TEXT, WHITE,
)


# ── Worker ────────────────────────────────────────────────────────────────────

class _EvalWorker(QThread):
    """Evaluate a single TriggerRule against MetricStore data off the main thread."""
    result_ready = pyqtSignal(bool, float, str)   # triggered, lhs_value, error

    def __init__(self, rule: TriggerRule, store: Optional[object]) -> None:
        super().__init__()
        self._rule = rule
        self._store = store

    def run(self) -> None:
        triggered, lhs, err = evaluate(self._rule, self._store)
        self.result_ready.emit(triggered, lhs, err)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _card(title: str) -> tuple[QWidget, QVBoxLayout]:
    card = QWidget()
    card.setObjectName("trigCard")
    card.setStyleSheet(
        f"QWidget#trigCard {{ background:{BG_CARD}; border:1px solid {BORDER}; border-radius:{CARD_RADIUS}; }}"
    )
    outer = QVBoxLayout(card)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)
    hdr = QLabel(title)
    hdr.setFixedHeight(32)
    hdr.setStyleSheet(
        f"background:{BG_CARD}; color:{TEXT_PRIMARY}; font-weight:600; font-size:11px;"
        f"padding:0 12px; border-bottom:1px solid {CARD_HDR_BORDER};"
    )
    outer.addWidget(hdr)
    inner_w = QWidget()
    inner_w.setStyleSheet(f"background:{BG_CARD};")
    inner = QVBoxLayout(inner_w)
    inner.setContentsMargins(10, 8, 10, 8)
    inner.setSpacing(5)
    outer.addWidget(inner_w, 1)
    return card, inner


def _btn(label: str, accent: bool = False) -> QPushButton:
    b = QPushButton(label)
    b.setFixedHeight(26)
    b.setFont(QFont("Segoe UI", 9))
    if accent:
        b.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
            f"  border-radius:3px; padding:0 10px; }}"
            f"QPushButton:hover {{ background:{ACCENT_DARK}; }}"
            f"QPushButton:disabled {{ background:{INPUT_PLACEHOLDER}; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
    else:
        b.setStyleSheet(
            f"QPushButton {{ background:{BG_CARD}; color:{TEXT_PRIMARY};"
            f"  border:1px solid {BORDER}; border-radius:3px; padding:0 10px; }}"
            f"QPushButton:hover {{ background:{BG_HOVER}; }}"
            f"QPushButton:disabled {{ color:{TEXT_MUTED}; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
    return b


def _table(headers: List[str]) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().setVisible(False)
    t.verticalHeader().setDefaultSectionSize(24)   # RULE 3
    t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    t.setAlternatingRowColors(True)
    t.horizontalHeader().setStretchLastSection(True)
    t.setStyleSheet(
        f"QTableWidget {{ border:none; font-size:11px; background:{BG_CARD};"
        f"  alternate-background-color:{BG_ALT_ROW}; gridline-color:{BORDER}; }}"
        f"QTableWidget::item:hover {{ background:{BG_HOVER}; }}"
        f"QHeaderView::section {{ background:{TH_BG}; color:{TH_TEXT};"
        f"  font-size:10px; font-weight:600; border:none; padding:0 8px; height:24px; }}"
    )
    return t


_SEV_COLOR = {"INFO": ACCENT, "WARNING": AMBER, "CRITICAL": RED}

_BUILDER_METRICS = [
    "rtt[\"<ip>\"]",
    "avg(rtt[\"<ip>\"], 5m)",
    "avg(rtt[\"<ip>\"], 1h)",
    "max(rtt[\"<ip>\"], 5m)",
    "loss%[\"<ip>\"]",
    "avg(loss%[\"<ip>\"], 5m)",
    "jitter[\"<ip>\"]",
    "state[\"<ip>\"]",
    "uptime%[\"<ip>\"]",
]

_BUILDER_OPS = [">", "<", ">=", "<=", "==", "!="]

_EXAMPLE_EXPRESSIONS = [
    ('RTT spike (5 min avg)', 'avg(rtt["192.168.1.1"], 5m) > 80'),
    ('Packet loss > 5%', 'loss%["192.168.1.1"] > 5'),
    ('Host down', 'state["192.168.1.1"] == "DOWN"'),
    ('High jitter', 'jitter["192.168.1.1"] > 30'),
    ('RTT spike AND packet loss', 'avg(rtt["8.8.8.8"], 5m) > 100 AND loss%["8.8.8.8"] > 3'),
    ('Low uptime (24 h)', 'uptime%["192.168.1.1"] < 95'),
]


# ── Rule editor dialog ────────────────────────────────────────────────────────

class _RuleEditorDialog(QDialog):
    """Add or edit a TriggerRule."""

    def __init__(self, rule: Optional[TriggerRule] = None,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit Trigger Rule" if rule else "New Trigger Rule")
        self.setMinimumWidth(560)
        self._rule = rule
        self._build_ui()
        if rule:
            self._populate(rule)

    def _build_ui(self) -> None:
        form = QFormLayout(self)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(8)
        form.setContentsMargins(16, 16, 16, 16)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g. Gateway RTT Spike")

        self._sev_combo = QComboBox()
        for s in ("INFO", "WARNING", "CRITICAL"):
            self._sev_combo.addItem(s)

        self._expr_edit = QPlainTextEdit()
        self._expr_edit.setFixedHeight(72)
        self._expr_edit.setFont(QFont("Cascadia Mono", 9))
        self._expr_edit.setPlaceholderText(
            'e.g.  avg(rtt["192.168.1.1"], 5m) > 80')
        self._expr_edit.textChanged.connect(self._on_expr_changed)

        self._preview_lbl = QLabel("—")
        self._preview_lbl.setWordWrap(True)
        self._preview_lbl.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:10px;"
            f"background:{BG_ALT_ROW}; border:1px solid {BORDER};"
            f"border-radius:3px; padding:4px 8px;")

        self._cooldown_spin = QLineEdit("300")
        self._cooldown_spin.setFixedWidth(80)
        self._cooldown_spin.setPlaceholderText("seconds")

        self._desc_edit = QLineEdit()
        self._desc_edit.setPlaceholderText("Optional description")

        self._enabled_cb = QCheckBox("Enabled")
        self._enabled_cb.setChecked(True)

        # Example loader
        self._example_combo = QComboBox()
        self._example_combo.addItem("— load example —")
        for label, _ in _EXAMPLE_EXPRESSIONS:
            self._example_combo.addItem(label)
        self._example_combo.currentIndexChanged.connect(self._on_load_example)

        self._validate_lbl = QLabel("")
        self._validate_lbl.setStyleSheet(f"color:{RED}; font-size:9px;")

        form.addRow("Name:", self._name_edit)
        form.addRow("Severity:", self._sev_combo)
        form.addRow("Example:", self._example_combo)
        form.addRow("Expression:", self._expr_edit)
        form.addRow("Preview:", self._preview_lbl)
        form.addRow("", self._validate_lbl)
        form.addRow("Cooldown (s):", self._cooldown_spin)
        form.addRow("Description:", self._desc_edit)
        form.addRow("", self._enabled_cb)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _populate(self, rule: TriggerRule) -> None:
        self._name_edit.setText(rule.name)
        idx = self._sev_combo.findText(rule.severity)
        if idx >= 0:
            self._sev_combo.setCurrentIndex(idx)
        self._expr_edit.setPlainText(rule.expression)
        self._cooldown_spin.setText(str(rule.cooldown_s))
        self._desc_edit.setText(rule.description)
        self._enabled_cb.setChecked(rule.enabled)

    def _on_expr_changed(self) -> None:
        expr = self._expr_edit.toPlainText().strip()
        preview = preview_expression(expr)
        self._preview_lbl.setText(preview)
        if "Syntax error" in preview or "error" in preview.lower():
            self._validate_lbl.setText(preview)
        else:
            self._validate_lbl.setText("")

    def _on_load_example(self, idx: int) -> None:
        if idx <= 0:
            return
        _, expr = _EXAMPLE_EXPRESSIONS[idx - 1]
        self._expr_edit.setPlainText(expr)
        self._example_combo.setCurrentIndex(0)

    def _on_ok(self) -> None:
        name = self._name_edit.text().strip()
        if not name:
            self._validate_lbl.setText("Name is required.")
            return
        expr = self._expr_edit.toPlainText().strip()
        if not expr:
            self._validate_lbl.setText("Expression is required.")
            return
        # Validate
        dummy = TriggerRule(id="x", name="x", expression=expr)
        err = dummy.validate()
        if err:
            self._validate_lbl.setText(f"Invalid expression: {err}")
            return
        try:
            cooldown = int(self._cooldown_spin.text())
        except ValueError:
            cooldown = 300

        rule_id = self._rule.id if self._rule else new_rule_id()
        self.result_rule = TriggerRule(
            id=rule_id,
            name=name,
            expression=expr,
            severity=self._sev_combo.currentText(),
            cooldown_s=cooldown,
            enabled=self._enabled_cb.isChecked(),
            description=self._desc_edit.text().strip(),
        )
        self.accept()


# ── Main page ─────────────────────────────────────────────────────────────────

class TriggerBuilderPage(QWidget):
    """Custom trigger expression rule builder."""

    scan_requested = pyqtSignal()  # emitted when user creates their first trigger rule

    def __init__(self, store: Optional[object] = None,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._store = store
        self._rules: List[TriggerRule] = load_rules()
        self._eval_worker: Optional[_EvalWorker] = None
        self._build_ui()
        self._refresh_table()

    def set_store(self, store: object) -> None:
        """Inject / replace MetricStore after construction."""
        self._store = store

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        title = QLabel("Custom Trigger Expressions")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        title.setStyleSheet(f"color:{TEXT_PRIMARY};")
        sub = QLabel(
            "Write custom alert conditions using metric functions. "
            "Rules are evaluated each monitoring cycle and fire an alert when true."
        )
        sub.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:10px;")
        sub.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(sub)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_rule_list_panel())
        splitter.addWidget(self._build_editor_panel())
        splitter.setSizes([380, 700])
        root.addWidget(splitter, 1)

    def _build_rule_list_panel(self) -> QWidget:
        panel = QWidget()
        panel.setMinimumWidth(300)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 4, 0)
        lay.setSpacing(6)

        card, inner = _card("Rules")

        # Stacked: page 0 = empty state, page 1 = rule table
        self._rules_stack = QStackedWidget()

        _empty_w = QWidget()
        _el = QVBoxLayout(_empty_w)
        _el.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _el.setSpacing(10)
        _el.setContentsMargins(12, 20, 12, 20)
        _empty_desc = QLabel(
            "Custom triggers alert you when a network metric\n"
            "crosses a threshold — e.g. RTT spikes or a host\n"
            "goes down. Create your first rule to get started."
        )
        _empty_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _empty_desc.setWordWrap(True)
        _empty_desc.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:10px; background:transparent;"
        )
        _btn_template = QPushButton("＋  Alert when host goes down →")
        _btn_template.setFixedHeight(28)
        _btn_template.setStyleSheet(
            f"QPushButton{{background:{ACCENT};color:{WHITE};border:none;"
            f"border-radius:3px;padding:0 10px;font-size:10px;font-weight:bold;}}"
            f"QPushButton:hover{{background:{ACCENT_DARK};}}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
        _btn_template.clicked.connect(self._on_add_template)
        _btn_template.clicked.connect(lambda: self.scan_requested.emit())
        _el.addWidget(_empty_desc)
        _el.addSpacing(4)
        _el.addWidget(_btn_template, alignment=Qt.AlignmentFlag.AlignCenter)
        self._rules_stack.addWidget(_empty_w)

        self._rule_table = _table(["Name", "Severity", "Enabled"])
        self._rule_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        self._rule_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents)
        self._rule_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents)
        self._rule_table.itemSelectionChanged.connect(self._on_rule_selected)

        def _trig_copy_expression():
            r = self._rule_table.currentRow()
            if r < 0 or r >= len(self._rules):
                return
            rule_id_data = self._rule_table.item(r, 0).data(Qt.ItemDataRole.UserRole)
            rule = next((x for x in self._rules if x.id == rule_id_data), None)
            if rule:
                from PyQt6.QtWidgets import QApplication as _QApp
                _QApp.clipboard().setText(rule.expression)

        install_copy_menu(self._rule_table, [
            ("separator",        None),
            ("Copy expression",  _trig_copy_expression),
        ])

        self._rules_stack.addWidget(self._rule_table)
        inner.addWidget(self._rules_stack)

        btn_row = QHBoxLayout()
        self._btn_add    = _btn("✚  Add", accent=True)
        self._btn_edit   = _btn("✎  Edit")
        self._btn_delete = _btn("✕  Delete")
        self._btn_toggle = _btn("◉  Toggle")
        for b in (self._btn_add, self._btn_edit, self._btn_delete, self._btn_toggle):
            btn_row.addWidget(b)
        self._btn_add.clicked.connect(self._on_add)
        self._btn_edit.clicked.connect(self._on_edit)
        self._btn_delete.clicked.connect(self._on_delete)
        self._btn_toggle.clicked.connect(self._on_toggle)
        inner.addLayout(btn_row)

        lay.addWidget(card)
        return panel

    def _build_editor_panel(self) -> QWidget:
        panel = QWidget()
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(4, 0, 0, 0)
        lay.setSpacing(6)

        # Expression preview card
        prev_card, prev_inner = _card("Expression Preview & Live Test")

        self._selected_name_lbl = QLabel("No rule selected.")
        self._selected_name_lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self._selected_name_lbl.setStyleSheet(f"color:{TEXT_PRIMARY};")

        self._expr_display = QPlainTextEdit()
        self._expr_display.setReadOnly(True)
        self._expr_display.setFixedHeight(60)
        self._expr_display.setFont(QFont("Cascadia Mono", 9))
        self._expr_display.setStyleSheet(
            f"background:{BG_ALT_ROW}; border:1px solid {BORDER}; "
            f"border-radius:3px; color:{TEXT_PRIMARY};")

        self._preview_lbl = QLabel("—")
        self._preview_lbl.setWordWrap(True)
        self._preview_lbl.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:10px; padding:4px 8px;"
            f"background:{BG_ALT_ROW}; border:1px solid {BORDER}; border-radius:3px;")

        btn_test = _btn("▶  Test Now", accent=True)
        btn_test.clicked.connect(self._on_test)
        self._test_status = QLabel("")
        self._test_status.setStyleSheet(f"font-size:10px; color:{TEXT_SECONDARY};")

        prev_inner.addWidget(self._selected_name_lbl)
        prev_inner.addWidget(QLabel("Expression:"))
        prev_inner.addWidget(self._expr_display)
        prev_inner.addWidget(QLabel("Plain English:"))
        prev_inner.addWidget(self._preview_lbl)
        row = QHBoxLayout()
        row.addWidget(btn_test)
        row.addWidget(self._test_status, 1)
        prev_inner.addLayout(row)

        # Syntax reference card
        ref_card, ref_inner = _card("Syntax Reference")
        ref_text = QLabel(
            "<b>Metrics:</b> rtt[\"ip\"]  loss%[\"ip\"]  jitter[\"ip\"]  "
            "state[\"ip\"]  uptime%[\"ip\"]<br>"
            "<b>Aggregates:</b> avg(rtt[\"ip\"], 5m)  max(…)  min(…)<br>"
            "<b>Windows:</b> 30s &nbsp; 5m &nbsp; 2h<br>"
            "<b>Operators:</b> &gt; &lt; &gt;= &lt;= == != AND OR NOT ( )<br>"
            "<b>Examples:</b><br>"
            "&nbsp;&nbsp;avg(rtt[\"192.168.1.1\"], 5m) &gt; 80<br>"
            "&nbsp;&nbsp;loss%[\"8.8.8.8\"] &gt; 5 AND state[\"8.8.8.8\"] != \"UP\""
        )
        ref_text.setTextFormat(Qt.TextFormat.RichText)
        ref_text.setWordWrap(True)
        ref_text.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:10px;")
        ref_inner.addWidget(ref_text)

        # Test fire log card
        log_card, log_inner = _card("Test / Evaluation Log")
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setFont(QFont("Cascadia Mono", 9))
        self._log.setMinimumHeight(120)
        self._log.setStyleSheet(
            f"background:{BG_ALT_ROW}; border:1px solid {BORDER}; color:{TEXT_PRIMARY};")
        log_inner.addWidget(self._log)

        lay.addWidget(prev_card)
        lay.addWidget(ref_card)
        lay.addWidget(log_card, 1)
        return panel

    # ── Rule list management ──────────────────────────────────────────────────

    def _refresh_table(self) -> None:
        self._rules_stack.setCurrentIndex(0 if not self._rules else 1)
        self._rule_table.setRowCount(0)
        for rule in self._rules:
            row = self._rule_table.rowCount()
            self._rule_table.insertRow(row)
            name_item = QTableWidgetItem(rule.name)
            sev_item  = QTableWidgetItem(rule.severity)
            sev_item.setForeground(QColor(_SEV_COLOR.get(rule.severity, ACCENT)))
            ena_item  = QTableWidgetItem("Yes" if rule.enabled else "No")
            ena_item.setForeground(QColor(GREEN if rule.enabled else TEXT_MUTED))
            for col, item in enumerate((name_item, sev_item, ena_item)):
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                self._rule_table.setItem(row, col, item)
            self._rule_table.item(row, 0).setData(
                Qt.ItemDataRole.UserRole, rule.id)

    def _selected_rule(self) -> Optional[TriggerRule]:
        row = self._rule_table.currentRow()
        if row < 0 or row >= len(self._rules):
            return None
        rule_id = self._rule_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        for r in self._rules:
            if r.id == rule_id:
                return r
        return None

    def _on_rule_selected(self) -> None:
        rule = self._selected_rule()
        if rule is None:
            self._selected_name_lbl.setText("No rule selected.")
            self._expr_display.setPlainText("")
            self._preview_lbl.setText("—")
            return
        self._selected_name_lbl.setText(rule.name)
        self._expr_display.setPlainText(rule.expression)
        self._preview_lbl.setText(preview_expression(rule.expression))

    def _on_add_template(self) -> None:
        template = TriggerRule(
            id=new_rule_id(),
            name="Host Down",
            expression='state["192.168.1.1"] == "DOWN"',
            severity="CRITICAL",
            cooldown_s=300,
            description="Alert when the gateway stops responding",
        )
        dlg = _RuleEditorDialog(rule=template, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._rules.append(dlg.result_rule)
            save_rules(self._rules)
            self._refresh_table()

    def _on_add(self) -> None:
        dlg = _RuleEditorDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._rules.append(dlg.result_rule)
            save_rules(self._rules)
            self._refresh_table()

    def _on_edit(self) -> None:
        rule = self._selected_rule()
        if rule is None:
            return
        dlg = _RuleEditorDialog(rule=rule, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            idx = next((i for i, r in enumerate(self._rules) if r.id == rule.id), -1)
            if idx >= 0:
                self._rules[idx] = dlg.result_rule
                save_rules(self._rules)
                self._refresh_table()
                self._on_rule_selected()

    def _on_delete(self) -> None:
        rule = self._selected_rule()
        if rule is None:
            return
        self._rules = [r for r in self._rules if r.id != rule.id]
        save_rules(self._rules)
        self._refresh_table()

    def _on_toggle(self) -> None:
        rule = self._selected_rule()
        if rule is None:
            return
        rule.enabled = not rule.enabled
        save_rules(self._rules)
        self._refresh_table()

    # ── Test evaluation ───────────────────────────────────────────────────────

    def _on_test(self) -> None:
        rule = self._selected_rule()
        if rule is None:
            self._test_status.setText("Select a rule first.")
            return
        if self._eval_worker and self._eval_worker.isRunning():
            return
        self._test_status.setText("Evaluating…")
        self._eval_worker = _EvalWorker(rule, self._store)
        self._eval_worker.result_ready.connect(
            lambda t, v, e: self._on_eval_result(rule, t, v, e))
        self._eval_worker.start()

    @pyqtSlot(bool, float, str)
    def _on_eval_result(self, rule: TriggerRule,
                        triggered: bool, lhs: float, error: str) -> None:
        if error:
            self._test_status.setText(
                f"Trigger evaluation failed — {error}. "
                "Check that the metric name and operator are correct."
            )
            self._test_status.setStyleSheet(f"font-size:10px; color:{RED};")
            self._log.appendPlainText(f"[ERROR] {rule.name}: {error}")
            return

        if math.isnan(lhs):
            lhs_str = "NaN (no data)"
        else:
            lhs_str = f"{lhs:.3f}"

        if triggered:
            msg = f"FIRED — {rule.name}  LHS={lhs_str}"
            self._test_status.setText(f"● TRIGGERED  (LHS = {lhs_str})")
            self._test_status.setStyleSheet(f"font-size:10px; color:{RED};")
        else:
            msg = f"OK — {rule.name}  LHS={lhs_str}  (not triggered)"
            self._test_status.setText(f"● Not triggered  (LHS = {lhs_str})")
            self._test_status.setStyleSheet(f"font-size:10px; color:{GREEN};")

        self._log.appendPlainText(msg)

    # ── Public: evaluate all enabled rules ────────────────────────────────────

    def evaluate_all(self) -> List[TriggerFired]:
        """
        Called by dashboard on each monitoring cycle.
        Returns a list of TriggerFired for any triggered rules.
        """
        fired: List[TriggerFired] = []
        for rule in self._rules:
            if not rule.enabled:
                continue
            triggered, lhs, error = evaluate(rule, self._store)
            if triggered and not error:
                tf = TriggerFired(
                    rule_id=rule.id,
                    rule_name=rule.name,
                    severity=rule.severity,
                    expression=rule.expression,
                    result_value=lhs,
                    message=(
                        f"Trigger fired: {rule.name}  "
                        f"({lhs:.2f if not math.isnan(lhs) else 'no data'})"
                    ),
                )
                fired.append(tf)
        return fired
