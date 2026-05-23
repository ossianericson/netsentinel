"""
One-click 'What's Wrong?' diagnosis page.

Three internal states managed via a QStackedWidget:
  0 — idle:    single 'Run Diagnosis' button
  1 — running: progress bar + step label + Cancel button
  2 — done:    verdict card + up to 5 finding cards + Run Again button
"""

from __future__ import annotations

from typing import Optional

import datetime as _dt

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication, QButtonGroup, QFrame, QHBoxLayout, QLabel, QProgressBar,
    QPushButton, QScrollArea, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
)

from modules.metric_store import MetricStore
from ui.styles import (
    ACCENT, AMBER, BG_CARD, BG_DARK, BORDER, GREEN, RED,
    TEXT_PRIMARY, TEXT_SECONDARY,
)

_SEV_COLOR = {
    "CRITICAL": RED,
    "HIGH":     RED,
    "MEDIUM":   AMBER,
    "LOW":      GREEN,
    "INFO":     ACCENT,
}

# Maps CorrelatedFinding.category → (button label, navigate_to target)
_CTA_MAP: dict[str, tuple[str, str]] = {
    "DNS Resolution Failure":                    ("Run DNS lookup →",          "DNS & Stability"),
    "DNS Leak Detected":                         ("Check DNS & Stability →",   "DNS & Stability"),
    "Chronic Connectivity Loss":                 ("Check Availability →",      "DNS & Stability"),
    "High Jitter — Unstable Latency":            ("Check Live Bandwidth →",    "Bandwidth Usage"),
    "Very Low Download Speed":                   ("Run Speed Test →",          "Speed Test"),
    "External ISP Issue":                        ("Run DNS lookup →",          "DNS & Stability"),
    "Local Network / Router Unreachable":        ("Check Live Bandwidth →",    "Bandwidth Usage"),
    "Broadcast Storm":                           ("Open Broadcast Storm →",    "Broadcast Storm"),
    "Degraded IoT Device — Excessive Broadcasting": ("Open IoT Behaviour →",  "IoT Behaviour"),
    "Rogue Network Bridge":                      ("Open Rogue Bridge (STP) →", "Rogue Bridge (STP)"),
}

_IDLE    = 0
_RUNNING = 1
_DONE    = 2


class DiagnosisPage(QWidget):

    navigate_to = pyqtSignal(str)  # emits "Overview" when back link is clicked

    def __init__(self, store: Optional[MetricStore] = None, parent=None):
        super().__init__(parent)
        self._store        = store
        self._worker       = None
        self._gateway_ip   = None
        self._gateway_mac  = None
        self._symptom      = ""   # set by symptom tile before _start()
        self._prev_finding_headlines: set[str] = set()
        self._last_findings: list = []
        self._setup_ui()

    def set_network_info(
        self,
        gateway_ip: Optional[str],
        gateway_mac: Optional[str],
    ) -> None:
        self._gateway_ip  = gateway_ip
        self._gateway_mac = gateway_mac

    # ── UI construction ───────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        self.setStyleSheet(f"QWidget {{ background:{BG_DARK}; }}")
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        # Back link
        back_btn = QPushButton("← Overview")
        back_btn.setFlat(True)
        back_btn.setStyleSheet(
            f"QPushButton {{ color:{ACCENT}; font-size:11px; background:transparent;"
            f" border:none; padding:0; text-align:left; }}"
            f"QPushButton:hover {{ color:#005A9E; }}"
        )
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.clicked.connect(lambda: self.navigate_to.emit("Overview"))
        root.addWidget(back_btn)

        title = QLabel("What's Wrong?")
        title.setStyleSheet(
            f"font-size:18px; font-weight:bold; color:{TEXT_PRIMARY}; background:transparent;"
        )
        sub = QLabel(
            "Runs all detection modules and produces a plain-English diagnosis of your network."
        )
        sub.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent;"
        )
        root.addWidget(title)
        root.addWidget(sub)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_idle())    # 0
        self._stack.addWidget(self._build_running()) # 1
        self._stack.addWidget(self._build_done())    # 2
        root.addWidget(self._stack, 1)

    def _build_idle(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background:transparent;")
        lay = QVBoxLayout(w)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(20)

        prompt = QLabel("What's happening?")
        prompt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        prompt.setStyleSheet(
            f"font-size:15px; font-weight:bold; color:{TEXT_PRIMARY}; background:transparent;"
        )
        lay.addWidget(prompt)

        _SYMPTOMS = [
            ("My internet is slow",          "slow"),
            ("My connection keeps dropping", "dropping"),
            ("I can't connect at all",       "noconn"),
        ]

        tiles_row = QHBoxLayout()
        tiles_row.setSpacing(12)
        self._symptom_group = QButtonGroup(w)
        self._symptom_group.setExclusive(True)

        _tile_base = (
            f"QPushButton {{ background:{BG_CARD}; color:{TEXT_PRIMARY};"
            f" border:2px solid {BORDER}; border-radius:8px;"
            f" font-size:12px; padding:18px 12px; }}"
            f"QPushButton:hover {{ border-color:{ACCENT}; color:{ACCENT}; }}"
            f"QPushButton:checked {{ border-color:{ACCENT}; background:{ACCENT};"
            f" color:#fff; }}"
        )

        self._symptom_btns: dict = {}
        for label, key in _SYMPTOMS:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setFixedHeight(72)
            btn.setMinimumWidth(160)
            btn.setStyleSheet(_tile_base)
            btn.setProperty("symptom_key", key)
            self._symptom_group.addButton(btn)
            self._symptom_btns[key] = btn
            tiles_row.addWidget(btn)

        # Default selection
        self._symptom_btns["slow"].setChecked(True)
        self._symptom = "slow"

        def _on_symptom_clicked(btn):
            self._symptom = btn.property("symptom_key")

        self._symptom_group.buttonClicked.connect(_on_symptom_clicked)

        lay.addLayout(tiles_row)

        run_btn = QPushButton("Run Diagnosis")
        run_btn.setFixedWidth(180)
        run_btn.setFixedHeight(44)
        run_btn.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:#fff; border:none;"
            f" font-size:13px; font-weight:bold; border-radius:6px; }}"
            f"QPushButton:hover {{ background:#005A9E; }}"
        )
        run_btn.clicked.connect(self._start)
        lay.addWidget(run_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        hint = QLabel("Takes about 30 seconds.")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent;"
        )
        lay.addWidget(hint)
        return w

    def _build_running(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background:transparent;")
        lay = QVBoxLayout(w)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(14)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setFixedWidth(420)
        self._progress_bar.setFixedHeight(10)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setStyleSheet(
            f"QProgressBar {{ background:#E0E8EF; border-radius:5px; border:none; }}"
            f"QProgressBar::chunk {{ background:{ACCENT}; border-radius:5px; }}"
        )

        self._step_lbl = QLabel("Starting…")
        self._step_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._step_lbl.setStyleSheet(
            f"font-size:13px; color:{TEXT_SECONDARY}; background:transparent;"
        )

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setFixedWidth(100)
        self._cancel_btn.setStyleSheet(
            f"QPushButton {{ background:{BG_CARD}; color:{TEXT_SECONDARY};"
            f" border:1px solid {BORDER}; padding:4px 14px; font-size:11px;"
            f" border-radius:4px; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; }}"
        )
        self._cancel_btn.clicked.connect(self._cancel)

        lay.addWidget(self._progress_bar, alignment=Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._step_lbl)
        lay.addWidget(self._cancel_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        return w

    def _build_done(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background:transparent;")
        outer = QVBoxLayout(w)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        # Verdict card
        self._verdict_card = QFrame()
        self._verdict_card.setObjectName("verdictCard")
        self._verdict_card.setStyleSheet(
            f"QFrame#verdictCard {{ background:{BG_CARD};"
            f" border-left:4px solid {ACCENT}; border-top:1px solid {BORDER};"
            f" border-right:1px solid {BORDER}; border-bottom:1px solid {BORDER}; }}"
        )
        vc_lay = QVBoxLayout(self._verdict_card)
        vc_lay.setContentsMargins(14, 10, 14, 10)
        vc_lay.setSpacing(4)

        self._verdict_title = QLabel("Diagnosis Result")
        self._verdict_title.setStyleSheet(
            f"font-size:13px; font-weight:bold; color:{TEXT_PRIMARY};"
            f" border:none; background:transparent;"
        )
        self._verdict_text = QLabel("–")
        self._verdict_text.setWordWrap(True)
        self._verdict_text.setStyleSheet(
            f"font-size:12px; color:{TEXT_PRIMARY}; border:none; background:transparent;"
        )
        vc_lay.addWidget(self._verdict_title)
        vc_lay.addWidget(self._verdict_text)
        outer.addWidget(self._verdict_card)

        # Diff badge — shown on re-runs when new findings appeared
        self._diff_lbl = QLabel("")
        self._diff_lbl.setStyleSheet(
            f"font-size:10px; color:{AMBER}; background:transparent;"
            f" border:none; padding:0 2px;"
        )
        self._diff_lbl.hide()
        outer.addWidget(self._diff_lbl)

        # "Do this first" hero finding card (top priority, always visible)
        self._hero_card_container = QWidget()
        self._hero_card_container.setStyleSheet("background:transparent;")
        self._hero_card_layout = QVBoxLayout(self._hero_card_container)
        self._hero_card_layout.setContentsMargins(0, 0, 0, 0)
        self._hero_card_layout.setSpacing(0)
        outer.addWidget(self._hero_card_container)

        # "Other findings" toggle + remaining cards
        self._other_toggle = QPushButton("▶  Other findings (0)")
        self._other_toggle.setFlat(True)
        self._other_toggle.setStyleSheet(
            f"QPushButton {{ color:{ACCENT}; font-size:11px; background:transparent;"
            f" border:none; padding:4px 0; text-align:left; }}"
            f"QPushButton:hover {{ color:#005A9E; }}"
        )
        self._other_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._other_toggle.clicked.connect(self._toggle_other_findings)
        self._other_expanded = False
        outer.addWidget(self._other_toggle)

        # Findings list in a scroll area
        self._findings_scroll = QScrollArea()
        self._findings_scroll.setWidgetResizable(True)
        self._findings_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._findings_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._findings_scroll.setStyleSheet(f"QScrollArea {{ background:{BG_DARK}; border:none; }}")

        self._findings_container = QWidget()
        self._findings_container.setStyleSheet(f"background:{BG_DARK};")
        self._findings_layout = QVBoxLayout(self._findings_container)
        self._findings_layout.setContentsMargins(0, 0, 0, 0)
        self._findings_layout.setSpacing(6)
        self._findings_layout.addStretch()

        self._findings_scroll.setWidget(self._findings_container)
        outer.addWidget(self._findings_scroll, 1)

        # "All clear" CTA — shown only when no findings
        self._grade_cta = QPushButton("Get a Network Grade score →")
        self._grade_cta.setFlat(True)
        self._grade_cta.setStyleSheet(
            f"QPushButton {{ color:{ACCENT}; font-size:11px; background:transparent;"
            f" border:none; padding:2px 0; text-align:left; }}"
            f"QPushButton:hover {{ color:#005A9E; }}"
        )
        self._grade_cta.setCursor(Qt.CursorShape.PointingHandCursor)
        self._grade_cta.clicked.connect(lambda: self.navigate_to.emit("Network Grade"))
        self._grade_cta.hide()
        outer.addWidget(self._grade_cta)

        # Run Again + Copy report buttons
        btn_row = QHBoxLayout()
        self._again_btn = QPushButton("Run Again")
        self._again_btn.setFixedWidth(120)
        _btn_qss = (
            f"QPushButton {{ background:{BG_CARD}; color:{ACCENT};"
            f" border:1px solid {ACCENT}; padding:4px 14px; font-size:11px;"
            f" border-radius:4px; }}"
            f"QPushButton:hover {{ background:{ACCENT}; color:#fff; }}"
        )
        self._again_btn.setStyleSheet(_btn_qss)
        self._again_btn.clicked.connect(self._reset)
        btn_row.addWidget(self._again_btn)

        self._copy_btn = QPushButton("Copy report")
        self._copy_btn.setFixedWidth(120)
        self._copy_btn.setStyleSheet(_btn_qss)
        self._copy_btn.clicked.connect(self._copy_report)
        btn_row.addWidget(self._copy_btn)
        btn_row.addStretch()
        outer.addLayout(btn_row)

        return w

    def _toggle_other_findings(self) -> None:
        self._other_expanded = not self._other_expanded
        self._findings_scroll.setVisible(self._other_expanded)
        n = self._findings_layout.count() - 1  # subtract stretch
        arrow = "▼" if self._other_expanded else "▶"
        self._other_toggle.setText(f"{arrow}  Other findings ({n})")

    # ── Finding card ──────────────────────────────────────────────────────────

    def _make_finding_card(self, finding, *, hero: bool = False) -> QFrame:
        sev      = getattr(finding, "severity",    "INFO")
        headline = getattr(finding, "headline",    "")
        remedy   = getattr(finding, "remediation", "")
        color    = _SEV_COLOR.get(sev, ACCENT)

        card = QFrame()
        card.setObjectName("findingCard")
        border_w = "4px" if hero else "3px"
        card.setStyleSheet(
            f"QFrame#findingCard {{ background:{BG_CARD};"
            f" border-left:{border_w} solid {color}; border-top:1px solid {BORDER};"
            f" border-right:1px solid {BORDER}; border-bottom:1px solid {BORDER}; }}"
        )
        lay = QVBoxLayout(card)
        lay.setContentsMargins(14 if hero else 12, 12 if hero else 8, 14 if hero else 12, 12 if hero else 8)
        lay.setSpacing(6 if hero else 4)

        if hero:
            do_this = QLabel("Do this first:")
            do_this.setStyleSheet(
                f"font-size:10px; font-weight:bold; color:{color}; text-transform:uppercase;"
                f" letter-spacing:1px; border:none; background:transparent;"
            )
            lay.addWidget(do_this)

        hdr = QHBoxLayout()
        badge = QLabel(sev)
        badge.setFixedWidth(68)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(
            f"font-size:9px; font-weight:bold; color:{color};"
            f" border:1px solid {color}; border-radius:3px; padding:1px 0;"
            f" background:transparent;"
        )
        hl = QLabel(headline)
        hl.setWordWrap(True)
        hl_size = "14px" if hero else "12px"
        hl.setStyleSheet(
            f"font-size:{hl_size}; font-weight:bold; color:{TEXT_PRIMARY};"
            f" border:none; background:transparent;"
        )
        hdr.addWidget(badge)
        hdr.addWidget(hl, 1)
        lay.addLayout(hdr)

        if remedy:
            rem = QLabel(remedy)
            rem.setWordWrap(True)
            rem_size = "12px" if hero else "11px"
            rem.setStyleSheet(
                f"font-size:{rem_size}; color:{TEXT_SECONDARY}; border:none; background:transparent;"
            )
            lay.addWidget(rem)

        category = getattr(finding, "category", "")
        if category in _CTA_MAP:
            cta_label, cta_target = _CTA_MAP[category]
            cta_btn = QPushButton(cta_label)
            cta_btn.setFlat(True)
            cta_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            cta_btn.setStyleSheet(
                f"QPushButton {{ color:{ACCENT}; font-size:11px; background:transparent;"
                f" border:none; padding:2px 0; text-align:left; }}"
                f"QPushButton:hover {{ color:#005A9E; }}"
            )
            cta_btn.clicked.connect(
                lambda _=False, t=cta_target: self.navigate_to.emit(t)
            )
            lay.addWidget(cta_btn)

        return card

    # ── State machine ─────────────────────────────────────────────────────────

    def _start(self) -> None:
        from workers.diagnosis_worker import DiagnosisWorker
        self._stack.setCurrentIndex(_RUNNING)
        self._progress_bar.setValue(0)
        self._step_lbl.setText("Starting…")
        self._worker = DiagnosisWorker(
            gateway_ip=self._gateway_ip,
            gateway_mac=self._gateway_mac,
            symptom=self._symptom,
            parent=self,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _cancel(self) -> None:
        if self._worker:
            self._worker.stop()
        self._reset()

    def _reset(self) -> None:
        if self._worker:
            self._worker.stop()
            self._worker.quit()
            self._worker.wait(3000)
            self._worker = None
        self._stack.setCurrentIndex(_IDLE)

    def _copy_report(self) -> None:
        """FLOW-3: copy plain-text diagnosis report to clipboard."""
        date_str = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
        verdict = self._verdict_title.text()
        summary = self._verdict_text.text()
        lines = [
            f"NetSentinel Diagnosis Report — {date_str}",
            f"Verdict: {verdict}",
            f"Summary: {summary}",
        ]
        if self._last_findings:
            lines.append("")
            lines.append("Findings:")
            for f in self._last_findings:
                h = getattr(f, "headline", "")
                if h:
                    lines.append(f"  • {h}")
            lines.append("")
            lines.append("Recommended actions:")
            for f in self._last_findings:
                r = getattr(f, "remediation", "")
                if r:
                    lines.append(f"  • {r}")
        QApplication.clipboard().setText("\n".join(lines))
        self._copy_btn.setText("Copied ✓")
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(2000, lambda: self._copy_btn.setText("Copy report"))

    def _on_progress(self, pct: int, msg: str) -> None:
        self._progress_bar.setValue(pct)
        self._step_lbl.setText(msg)

    def _on_finished(self, result) -> None:
        if result is None:
            self._reset()
            return
        self._show_result(result)

    def _show_result(self, result) -> None:
        sev      = getattr(result, "global_severity", "INFO")
        summary  = getattr(result, "plain_summary",   "") or "No issues detected."
        findings = getattr(result, "findings",        [])
        self._last_findings = list(findings)

        prev_headlines = self._prev_finding_headlines.copy()

        # Clear hero card
        while self._hero_card_layout.count():
            item = self._hero_card_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        # Clear other findings (preserve trailing stretch)
        while self._findings_layout.count() > 1:
            item = self._findings_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        if not findings:
            self._verdict_card.setStyleSheet(
                f"QFrame#verdictCard {{ background:{BG_CARD};"
                f" border-left:4px solid {GREEN}; border-top:1px solid {BORDER};"
                f" border-right:1px solid {BORDER}; border-bottom:1px solid {BORDER}; }}"
            )
            self._verdict_title.setText("Your network looks healthy")
            self._verdict_title.setStyleSheet(
                f"font-size:13px; font-weight:bold; color:{GREEN};"
                f" border:none; background:transparent;"
            )
            self._verdict_text.setText(
                "Gateway responding  ·  DNS working  ·  No broadcast storms"
                "  ·  No rogue devices  ·  No network loops"
            )
            self._hero_card_container.hide()
            self._other_toggle.hide()
            self._findings_scroll.hide()
            self._grade_cta.show()
        else:
            color = _SEV_COLOR.get(sev, ACCENT)
            self._verdict_card.setStyleSheet(
                f"QFrame#verdictCard {{ background:{BG_CARD};"
                f" border-left:4px solid {color}; border-top:1px solid {BORDER};"
                f" border-right:1px solid {BORDER}; border-bottom:1px solid {BORDER}; }}"
            )
            self._verdict_title.setText(f"Diagnosis — {sev}")
            self._verdict_title.setStyleSheet(
                f"font-size:13px; font-weight:bold; color:{color};"
                f" border:none; background:transparent;"
            )
            self._verdict_text.setText(summary)
            self._grade_cta.hide()

            # Hero card — "Do this first": top finding, larger label
            hero_finding = findings[0]
            hero = self._make_finding_card(hero_finding, hero=True)
            self._hero_card_layout.addWidget(hero)
            self._hero_card_container.show()

            # Remaining findings in the collapsible section
            rest = findings[1:5]
            if rest:
                for finding in rest:
                    card = self._make_finding_card(finding)
                    self._findings_layout.insertWidget(
                        self._findings_layout.count() - 1, card
                    )
                self._other_expanded = False
                self._findings_scroll.hide()
                self._other_toggle.setText(f"▶  Other findings ({len(rest)})")
                self._other_toggle.show()
            else:
                self._other_toggle.hide()
                self._findings_scroll.hide()

        # Update headline tracking and show diff badge on re-runs
        current_headlines = {getattr(f, "headline", "") for f in findings if getattr(f, "headline", "")}
        if prev_headlines:
            new_count = len(current_headlines - prev_headlines)
            gone_count = len(prev_headlines - current_headlines)
            parts = []
            if new_count:
                parts.append(f"▲ {new_count} new finding{'s' if new_count != 1 else ''}")
            if gone_count:
                parts.append(f"▼ {gone_count} resolved")
            if parts:
                self._diff_lbl.setText("  ·  ".join(parts) + " since last run")
                self._diff_lbl.show()
            else:
                self._diff_lbl.setText("No change since last run")
                self._diff_lbl.setStyleSheet(
                    f"font-size:10px; color:{TEXT_SECONDARY}; background:transparent;"
                    f" border:none; padding:0 2px;"
                )
                self._diff_lbl.show()
        else:
            self._diff_lbl.hide()
        self._prev_finding_headlines = current_headlines

        self._stack.setCurrentIndex(_DONE)
