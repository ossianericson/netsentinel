"""
Lab / scenario mode page.

Three internal panels managed via QStackedWidget:
  0 — picker:  4 scenario cards; click to start an exercise
  1 — runner:  step-by-step exercise with scan, hint, solution, and next controls
  2 — result:  verdict card, findings summary, export button
"""

from __future__ import annotations

import datetime
import threading
from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QProgressBar, QPushButton, QScrollArea, QStackedWidget, QVBoxLayout, QWidget,
)

from modules.lab_scenarios import LabResult, LabScenario, SCENARIOS
from modules.metric_store import MetricStore
from ui.styles import (
    ACCENT, ACCENT_DARK, AMBER, BG_CARD, BG_DARK,
    BG_HOVER, BORDER, GREEN, RED,
    TEXT_PRIMARY, TEXT_SECONDARY, WHITE,
)

_PICKER  = 0
_RUNNER  = 1
_RESULT  = 2

_EFFORT_COLOR = {"S": GREEN, "M": AMBER, "L": RED}


# ---------------------------------------------------------------------------
# Background scan worker
# ---------------------------------------------------------------------------

class _LabScanWorker(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(dict)  # {"ok": bool, "findings": [...], "summary": str}

    def __init__(self, scan_type: str, store: Optional[MetricStore] = None, parent=None):
        super().__init__(parent)
        self._scan_type  = scan_type
        self._store      = store
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        try:
            if self._scan_type == "rogue":
                self._run_rogue()
            elif self._scan_type == "dns":
                self._run_dns()
            elif self._scan_type == "storm":
                self._run_storm()
            elif self._scan_type == "subnet":
                self._run_subnet()
            elif self._scan_type == "port":
                self._run_port()
            elif self._scan_type == "dhcp":
                self._run_dhcp()
            else:
                self.finished.emit({"ok": False, "findings": [], "summary": "Unknown scan type"})
        except Exception as exc:
            self.finished.emit({"ok": False, "findings": [], "summary": str(exc)})

    def _run_rogue(self) -> None:
        from modules.rogue_device import scan
        from modules.utils import get_offenders_path
        self.progress.emit("Reading ARP table…")
        result = scan(get_offenders_path())
        devices = result.get("devices", [])
        findings = [
            {
                "ip":       d.ip,
                "mac":      d.mac,
                "vendor":   d.vendor,
                "hostname": d.hostname or "—",
                "risk":     d.risk_level,
            }
            for d in devices
        ]
        rogue_count = sum(1 for d in devices if d.risk_level in ("HIGH", "UNKNOWN"))
        self.finished.emit({
            "ok":       True,
            "findings": findings,
            "summary":  f"{len(devices)} device(s) found — {rogue_count} flagged HIGH/UNKNOWN",
        })

    def _run_dns(self) -> None:
        from modules import dns_correlator
        self.progress.emit("Measuring DNS latency and ping stability (60 s)…")
        result = dns_correlator.scan(
            stop_event=self._stop_event,
            progress_cb=lambda msg: self.progress.emit(msg),
        )
        dns_rtts = [p.rtt_ms for p in result.dns_series if p.rtt_ms is not None]
        avg_dns  = round(sum(dns_rtts) / len(dns_rtts), 1) if dns_rtts else None
        findings = [{
            "avg_dns_ms":        avg_dns if avg_dns is not None else "N/A",
            "outages":           len(result.micro_outages),
            "dns_only_failures": result.dns_only_failures,
            "verdict":           result.plain_verdict or "No issues detected",
        }]
        self.finished.emit({
            "ok":       True,
            "findings": findings,
            "summary":  result.plain_verdict or "DNS scan complete",
        })

    def _run_storm(self) -> None:
        from modules import storm_analyser
        self.progress.emit("Listening for broadcast traffic (6 s)…")
        result = storm_analyser.scan(
            duration=6,
            progress_cb=lambda msg: self.progress.emit(msg),
        )
        top = [{"mac": m, "count": c} for m, c in result.top_sources[:5]]
        findings = [{
            "storm_level":   result.storm_level,
            "bcast_per_sec": round(result.bcast_per_sec, 1),
            "top_source":    top[0]["mac"] if top else "—",
            "verdict":       result.plain_verdict or f"Storm level: {result.storm_level}",
        }]
        self.finished.emit({
            "ok":       True,
            "findings": findings,
            "summary":  result.plain_verdict or f"Storm level: {result.storm_level}",
        })

    def _run_port(self) -> None:
        from modules import port_scanner
        from modules.utils_net import get_network_info
        self.progress.emit("Detecting gateway IP…")
        net_info = get_network_info()
        gateway = net_info.get("gateway") if net_info else None
        if not gateway:
            self.finished.emit({
                "ok": False,
                "findings": [],
                "summary": "Could not determine gateway IP. Check your network connection.",
            })
            return
        self.progress.emit(f"Scanning ports on gateway {gateway}…")
        result = port_scanner.scan(gateway, mode="fast")
        findings = [
            {
                "port":    p.port,
                "name":    p.name,
                "risk":    p.risk,
                "banner":  p.banner or "—",
            }
            for p in result.open_ports
        ]
        high_risk = [p for p in result.open_ports if p.risk == "HIGH"]
        if not result.open_ports:
            summary = f"No open ports found on {gateway} ({result.scanned} ports scanned)."
        elif high_risk:
            names = ", ".join(str(p.port) for p in high_risk)
            summary = f"{len(result.open_ports)} open port(s) on {gateway} — HIGH RISK: {names}"
        else:
            summary = f"{len(result.open_ports)} open port(s) on {gateway}, none flagged high risk."
        self.finished.emit({"ok": True, "findings": findings, "summary": summary})

    def _run_dhcp(self) -> None:
        from modules import dhcp_lease_scanner
        self.progress.emit("Reading DHCP lease records…")
        leases = dhcp_lease_scanner.scan()
        verdict_str = dhcp_lease_scanner.verdict(leases)
        findings = [
            {
                "ip":       le.ip or "—",
                "mac":      le.mac or "—",
                "hostname": le.hostname or "—",
                "server":   le.server or "—",
                "source":   le.source or "—",
            }
            for le in leases
        ]
        ip_counts: dict[str, int] = {}
        for le in leases:
            if le.ip:
                ip_counts[le.ip] = ip_counts.get(le.ip, 0) + 1
        conflicts = [ip for ip, cnt in ip_counts.items() if cnt > 1]
        if conflicts:
            summary = f"{len(leases)} lease(s) — CONFLICT detected on: {', '.join(conflicts)}"
        else:
            summary = verdict_str or f"{len(leases)} lease(s) found, no conflicts detected."
        self.finished.emit({"ok": True, "findings": findings, "summary": summary})

    def _run_subnet(self) -> None:
        if not self._store:
            self.finished.emit({
                "ok":       False,
                "findings": [],
                "summary":  "No scan data available — run a scan from the Overview page first.",
            })
            return
        self.progress.emit("Loading devices from MetricStore…")
        devices = self._store.get_known_devices()
        findings = [
            {
                "ip":       d.ip or "—",
                "mac":      d.mac,
                "hostname": d.hostname or "—",
                "vendor":   d.vendor or "Unknown",
            }
            for d in devices.values()
        ]
        self.finished.emit({
            "ok":       True,
            "findings": findings,
            "summary":  f"{len(findings)} device(s) on subnet",
        })


# ---------------------------------------------------------------------------
# Main page
# ---------------------------------------------------------------------------

class LabModePage(QWidget):

    scan_requested   = pyqtSignal()    # emitted when user starts a lab exercise
    explore_protocol = pyqtSignal(str) # emitted when user clicks "See how this works →"; carries protocol key

    def __init__(self, store: Optional[MetricStore] = None, parent=None):
        super().__init__(parent)
        self._store            = store
        self._worker: Optional[_LabScanWorker] = None

        # runtime state
        self._scenario:         Optional[LabScenario] = None
        self._step_idx:         int                   = 0
        self._step_findings:    List[dict]             = []  # findings per completed step
        self._hints_used:           int  = 0
        self._hint_used_this_step:  bool = False
        self._solution_visible:     bool = False

        self._setup_ui()
        self.setStyleSheet(f"QWidget {{ background:{BG_DARK}; }}")

    # ------------------------------------------------------------------
    # UI build
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._stack = QStackedWidget()
        root.addWidget(self._stack)

        self._stack.addWidget(self._build_picker())
        self._stack.addWidget(self._build_runner())
        self._stack.addWidget(self._build_result())
        self._stack.setCurrentIndex(_PICKER)

    # ── Picker ─────────────────────────────────────���────────────────────

    def _build_picker(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(32, 28, 32, 24)
        outer.setSpacing(6)

        from ui.widgets.page_header import PageHeaderBar
        _hdr = PageHeaderBar("Lab Mode", subtitle="Guided exercises to learn real networking concepts using your live network.")
        _hdr.show_first_visit_banner(
            "lab_mode",
            "Each exercise walks you through a real networking concept using your actual "
            "devices, not a simulation. Hints are available if you get stuck, and you can "
            "reveal the full solution at any point.",
        )
        outer.addWidget(_hdr)
        outer.addSpacing(8)

        grid = QGridLayout()
        grid.setSpacing(12)
        for idx, scenario in enumerate(SCENARIOS):
            card = self._scenario_card(scenario)
            grid.addWidget(card, idx // 2, idx % 2)
        outer.addLayout(grid)
        outer.addStretch()
        return w

    def _scenario_card(self, scenario: LabScenario) -> QFrame:
        card = QFrame()
        card.setObjectName("labCard")
        card.setStyleSheet(
            f"QFrame#labCard {{ background:{BG_CARD}; border:1px solid {BORDER};"
            f" border-radius:8px; }}"
        )
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(6)

        header = QHBoxLayout()
        t = QLabel(scenario.title)
        t.setStyleSheet(
            f"font-size:13px; font-weight:bold; color:{TEXT_PRIMARY}; background:transparent;"
        )
        effort_color = _EFFORT_COLOR.get(scenario.effort, AMBER)
        e = QLabel(f"Effort: {scenario.effort}")
        e.setStyleSheet(
            f"font-size:10px; color:{effort_color}; background:transparent;"
        )
        header.addWidget(t)
        header.addStretch()
        header.addWidget(e)
        lay.addLayout(header)

        g = QLabel(scenario.goal)
        g.setWordWrap(True)
        g.setStyleSheet(f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent;")
        lay.addWidget(g)

        steps_lbl = QLabel(f"{len(scenario.steps)} steps")
        steps_lbl.setStyleSheet(f"font-size:10px; color:{TEXT_SECONDARY}; background:transparent;")
        lay.addWidget(steps_lbl)

        # Curriculum alignment badges
        try:
            from ui.widgets.objective_badge import ObjectiveBadge
            badge_row = QHBoxLayout()
            badge_row.setSpacing(4)
            for badge in ObjectiveBadge.for_scenario(scenario.title):
                badge_row.addWidget(badge)
            badge_row.addStretch()
            lay.addLayout(badge_row)
        except Exception:
            pass  # non-fatal — badge widget optional

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        btn = QPushButton("Start Exercise")
        btn.setFixedHeight(28)
        btn.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
            f" border-radius:4px; font-size:11px; }}"
            f"QPushButton:hover {{ background:{ACCENT_DARK}; color:{WHITE}; }}"
            f"QPushButton:pressed {{ background:{ACCENT_DARK}; color:{WHITE}; }}"
        )
        btn.clicked.connect(lambda _, s=scenario: self._start_scenario(s))
        btn.clicked.connect(lambda: self.scan_requested.emit())
        btn_row.addWidget(btn)

        if scenario.protocol:
            viz_btn = QPushButton(f"See how {scenario.protocol} works →")
            viz_btn.setFixedHeight(28)
            viz_btn.setStyleSheet(
                f"QPushButton {{ background:transparent; color:{ACCENT};"
                f" border:1px solid {ACCENT}; border-radius:4px; font-size:11px; }}"
                f"QPushButton:hover {{ background:{BG_HOVER}; color:{ACCENT}; }}"
                f"QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_PRIMARY}; }}"
            )
            _proto = scenario.protocol
            viz_btn.clicked.connect(lambda _, p=_proto: self.explore_protocol.emit(p))
            btn_row.addWidget(viz_btn)

        btn_row.addStretch()
        lay.addLayout(btn_row)
        return card

    # ── Runner ──────────────────────────────────────────────────────────

    def _build_runner(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(32, 20, 32, 24)
        outer.setSpacing(8)

        # back link
        self._runner_back = QPushButton("← Back to exercises")
        self._runner_back.setFlat(True)
        self._runner_back.setStyleSheet(
            f"QPushButton {{ color:{ACCENT}; font-size:11px; background:transparent;"
            f" border:none; text-align:left; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}"
        )
        self._runner_back.clicked.connect(self._go_picker)
        outer.addWidget(self._runner_back)

        # scenario title + step indicator
        hdr = QHBoxLayout()
        self._runner_title = QLabel()
        self._runner_title.setStyleSheet(
            f"font-size:17px; font-weight:bold; color:{TEXT_PRIMARY}; background:transparent;"
        )
        self._runner_step_lbl = QLabel()
        self._runner_step_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent;"
        )
        hdr.addWidget(self._runner_title)
        hdr.addStretch()
        hdr.addWidget(self._runner_step_lbl)
        outer.addLayout(hdr)
        outer.addSpacing(4)

        # instruction card
        self._instruction_card = QFrame()
        self._instruction_card.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER};"
            f" border-left:4px solid {ACCENT}; border-radius:6px; }}"
        )
        inst_lay = QVBoxLayout(self._instruction_card)
        inst_lay.setContentsMargins(14, 12, 14, 12)
        self._instruction_lbl = QLabel()
        self._instruction_lbl.setWordWrap(True)
        self._instruction_lbl.setStyleSheet(
            f"font-size:13px; color:{TEXT_PRIMARY}; background:transparent;"
        )
        inst_lay.addWidget(self._instruction_lbl)
        outer.addWidget(self._instruction_card)

        # progress bar + status
        self._prog_bar = QProgressBar()
        self._prog_bar.setRange(0, 0)
        self._prog_bar.setFixedHeight(6)
        self._prog_bar.setTextVisible(False)
        self._prog_bar.setStyleSheet(
            f"QProgressBar {{ background:{BG_CARD}; border:none; border-radius:3px; }}"
            f"QProgressBar::chunk {{ background:{ACCENT}; border-radius:3px; }}"
        )
        self._prog_bar.hide()
        outer.addWidget(self._prog_bar)

        self._prog_lbl = QLabel()
        self._prog_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent;"
        )
        self._prog_lbl.hide()
        outer.addWidget(self._prog_lbl)

        # summary label (shown after scan finishes)
        self._summary_card = QFrame()
        self._summary_card.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER}; border-radius:6px; }}"
        )
        sum_lay = QVBoxLayout(self._summary_card)
        sum_lay.setContentsMargins(14, 10, 14, 10)
        self._summary_lbl = QLabel()
        self._summary_lbl.setWordWrap(True)
        self._summary_lbl.setStyleSheet(
            f"font-size:12px; color:{TEXT_PRIMARY}; background:transparent;"
        )
        sum_lay.addWidget(self._summary_lbl)
        self._summary_card.hide()
        outer.addWidget(self._summary_card)

        # findings panel — expands to fill all available vertical space
        self._findings_scroll = QScrollArea()
        self._findings_scroll.setWidgetResizable(True)
        self._findings_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._findings_scroll.setStyleSheet("background:transparent;")
        self._findings_body = QWidget()
        self._findings_body.setStyleSheet("background:transparent;")
        self._findings_vbox = QVBoxLayout(self._findings_body)
        self._findings_vbox.setContentsMargins(0, 0, 0, 0)
        self._findings_vbox.setSpacing(3)
        self._findings_scroll.setWidget(self._findings_body)
        self._findings_scroll.hide()
        outer.addWidget(self._findings_scroll, 1)  # stretch=1: fills remaining height

        # hint panel (hidden until toggled) — above buttons so it doesn't push them off-screen
        self._hint_card = QFrame()
        self._hint_card.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:1px solid {AMBER}40;"
            f" border-left:4px solid {AMBER}; border-radius:6px; }}"
        )
        hint_lay = QVBoxLayout(self._hint_card)
        hint_lay.setContentsMargins(14, 10, 14, 10)
        self._hint_lbl = QLabel()
        self._hint_lbl.setWordWrap(True)
        self._hint_lbl.setStyleSheet(
            f"font-size:12px; color:{TEXT_SECONDARY}; background:transparent;"
        )
        hint_lay.addWidget(self._hint_lbl)
        self._hint_card.hide()
        outer.addWidget(self._hint_card)

        # solution panel (hidden until revealed) — above buttons
        self._solution_card = QFrame()
        self._solution_card.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:1px solid {GREEN}40;"
            f" border-left:4px solid {GREEN}; border-radius:6px; }}"
        )
        sol_lay = QVBoxLayout(self._solution_card)
        sol_lay.setContentsMargins(14, 10, 14, 10)
        sol_hdr = QLabel("Solution")
        sol_hdr.setStyleSheet(
            f"font-size:11px; font-weight:bold; color:{GREEN}; background:transparent;"
        )
        sol_lay.addWidget(sol_hdr)
        self._solution_lbl = QLabel()
        self._solution_lbl.setWordWrap(True)
        self._solution_lbl.setStyleSheet(
            f"font-size:12px; color:{TEXT_PRIMARY}; background:transparent;"
        )
        sol_lay.addWidget(self._solution_lbl)
        self._solution_card.hide()
        outer.addWidget(self._solution_card)

        # action buttons row
        btn_row = QHBoxLayout()
        self._run_btn = QPushButton("Run Check")
        self._run_btn.setFixedHeight(30)
        self._run_btn.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
            f" border-radius:4px; font-size:11px; padding:0 14px; }}"
            f"QPushButton:disabled {{ background:{BG_CARD}; color:{TEXT_SECONDARY}; }}"
            f"QPushButton:hover:!disabled {{ background:{ACCENT_DARK}; color:{WHITE}; }}"
            f"QPushButton:pressed {{ background:{ACCENT_DARK}; color:{WHITE}; }}"
        )
        self._run_btn.clicked.connect(self._run_check)

        self._hint_btn = QPushButton("Show Hint")
        self._hint_btn.setFixedHeight(30)
        self._hint_btn.setCheckable(True)
        self._hint_btn.setStyleSheet(
            f"QPushButton {{ background:{BG_CARD}; color:{TEXT_SECONDARY}; border:1px solid {BORDER};"
            f" border-radius:4px; font-size:11px; padding:0 14px; }}"
            f"QPushButton:hover {{ background:{BG_HOVER}; color:{TEXT_PRIMARY}; }}"
            f"QPushButton:checked {{ color:{ACCENT}; border-color:{ACCENT}; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_PRIMARY}; }}"
        )
        self._hint_btn.toggled.connect(self._toggle_hint)

        self._solution_btn = QPushButton("Reveal Solution")
        self._solution_btn.setFixedHeight(30)
        self._solution_btn.setStyleSheet(
            f"QPushButton {{ background:{BG_CARD}; color:{TEXT_SECONDARY}; border:1px solid {BORDER};"
            f" border-radius:4px; font-size:11px; padding:0 14px; }}"
            f"QPushButton:hover {{ background:{BG_HOVER}; color:{TEXT_PRIMARY}; border-color:{TEXT_PRIMARY}; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_PRIMARY}; }}"
        )
        self._solution_btn.clicked.connect(self._reveal_solution)

        self._next_btn = QPushButton("Next Step →")
        self._next_btn.setFixedHeight(30)
        self._next_btn.setEnabled(False)
        self._next_btn.setStyleSheet(
            f"QPushButton {{ background:{GREEN}; color:{WHITE}; border:none;"
            f" border-radius:4px; font-size:11px; padding:0 14px; }}"
            f"QPushButton:disabled {{ background:{BG_CARD}; color:{TEXT_SECONDARY}; }}"
            f"QPushButton:hover:!disabled {{ background:{GREEN}; color:{WHITE}; }}"
            f"QPushButton:pressed {{ background:{GREEN}; color:{WHITE}; }}"
        )
        self._next_btn.clicked.connect(self._next_step)

        btn_row.addWidget(self._run_btn)
        btn_row.addWidget(self._hint_btn)
        btn_row.addWidget(self._solution_btn)
        btn_row.addStretch()
        btn_row.addWidget(self._next_btn)
        outer.addLayout(btn_row)

        return w

    # ── Result ──────────────────────────────────────────────────────────

    def _build_result(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(32, 28, 32, 24)
        outer.setSpacing(10)

        self._result_title = QLabel()
        self._result_title.setStyleSheet(
            f"font-size:17px; font-weight:bold; color:{TEXT_PRIMARY}; background:transparent;"
        )
        outer.addWidget(self._result_title)

        self._verdict_card = QFrame()
        self._verdict_card.setObjectName("verdictCard")
        v_lay = QVBoxLayout(self._verdict_card)
        v_lay.setContentsMargins(16, 14, 16, 14)
        self._verdict_lbl = QLabel()
        self._verdict_lbl.setStyleSheet(
            f"font-size:15px; font-weight:bold; color:{TEXT_PRIMARY}; background:transparent;"
        )
        self._verdict_meta = QLabel()
        self._verdict_meta.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent;"
        )
        v_lay.addWidget(self._verdict_lbl)
        v_lay.addWidget(self._verdict_meta)
        outer.addWidget(self._verdict_card)

        outer.addStretch()

        btn_row = QHBoxLayout()
        export_btn = QPushButton("Export Report (HTML)")
        export_btn.setFixedHeight(30)
        export_btn.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
            f" border-radius:4px; font-size:11px; padding:0 14px; }}"
            f"QPushButton:hover {{ background:{ACCENT_DARK}; color:{WHITE}; }}"
            f"QPushButton:pressed {{ background:{ACCENT_DARK}; color:{WHITE}; }}"
        )
        export_btn.clicked.connect(self._export_report)

        again_btn = QPushButton("Try Again")
        again_btn.setFixedHeight(30)
        again_btn.setStyleSheet(
            f"QPushButton {{ background:{BG_CARD}; color:{TEXT_SECONDARY};"
            f" border:1px solid {BORDER}; border-radius:4px; font-size:11px; padding:0 14px; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
        again_btn.clicked.connect(lambda: self._start_scenario(self._scenario) if self._scenario else None)

        badge_btn = QPushButton("Download Badge (PNG)")
        badge_btn.setFixedHeight(30)
        badge_btn.setStyleSheet(
            f"QPushButton {{ background:{BG_CARD}; color:{TEXT_SECONDARY};"
            f" border:1px solid {BORDER}; border-radius:4px; font-size:11px; padding:0 14px; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
        badge_btn.clicked.connect(self._download_badge)
        self._badge_btn = badge_btn

        back_btn = QPushButton("← Back to Exercises")
        back_btn.setFixedHeight(30)
        back_btn.setFlat(True)
        back_btn.setStyleSheet(
            f"QPushButton {{ color:{ACCENT}; font-size:11px; background:transparent; border:none; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}"
        )
        back_btn.clicked.connect(self._go_picker)

        btn_row.addWidget(back_btn)
        btn_row.addStretch()
        btn_row.addWidget(again_btn)
        btn_row.addWidget(badge_btn)
        btn_row.addWidget(export_btn)
        outer.addLayout(btn_row)

        self._result_data: Optional[dict] = None
        return w

    # ------------------------------------------------------------------
    # Scenario flow
    # ------------------------------------------------------------------

    def _start_scenario(self, scenario: LabScenario) -> None:
        self._scenario      = scenario
        self._step_idx      = 0
        self._step_findings = []
        self._hints_used    = 0
        self._stack.setCurrentIndex(_RUNNER)
        self._load_step()

    def _load_step(self) -> None:
        assert self._scenario is not None
        step = self._scenario.steps[self._step_idx]
        total = len(self._scenario.steps)

        self._runner_title.setText(self._scenario.title)
        self._runner_step_lbl.setText(f"Step {self._step_idx + 1} of {total}")
        self._instruction_lbl.setText(step.instruction)
        self._hint_lbl.setText(step.hint)
        self._solution_lbl.setText(step.solution)

        # reset panel state
        self._summary_card.hide()
        self._findings_scroll.hide()
        self._hint_card.hide()
        self._hint_btn.setChecked(False)
        self._hint_btn.setText("Show Hint")
        self._solution_card.hide()
        self._solution_visible = False
        self._prog_bar.hide()
        self._prog_lbl.hide()

        is_last = self._step_idx == total - 1
        self._next_btn.setText("Finish Exercise" if is_last else "Next Step →")

        self._hint_used_this_step = False

        if step.scan_type is None:
            # review step — carry forward findings from the previous scan step
            self._run_btn.setEnabled(False)
            self._run_btn.setText("No scan required")
            self._solution_btn.setEnabled(True)
            self._next_btn.setEnabled(True)
            if self._step_findings:
                self._populate_findings(self._step_findings[-1])
        else:
            self._run_btn.setEnabled(True)
            self._run_btn.setText("Run Check")
            self._solution_btn.setEnabled(False)
            self._next_btn.setEnabled(False)

    def _run_check(self) -> None:
        assert self._scenario is not None
        step = self._scenario.steps[self._step_idx]
        if step.scan_type is None:
            return

        self._run_btn.setEnabled(False)
        self._run_btn.setText("Running…")
        self._prog_bar.show()
        self._prog_lbl.setText("Starting…")
        self._prog_lbl.show()
        self._summary_card.hide()
        self._solution_btn.setEnabled(False)
        self._next_btn.setEnabled(False)

        self._worker = _LabScanWorker(step.scan_type, store=self._store)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_scan_done)
        self._worker.start()

    def _on_progress(self, msg: str) -> None:
        self._prog_lbl.setText(msg)

    def _on_scan_done(self, result: dict) -> None:
        self._prog_bar.hide()
        self._prog_lbl.hide()
        self._run_btn.setText("Run Check")

        color = GREEN if result.get("ok") else AMBER
        self._summary_card.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:1px solid {color}40;"
            f" border-left:4px solid {color}; border-radius:6px; }}"
        )
        self._summary_lbl.setText(result.get("summary", "Done."))
        self._summary_card.show()

        findings = result.get("findings", [])
        self._step_findings.append(findings)
        self._populate_findings(findings)

        self._solution_btn.setEnabled(True)
        self._next_btn.setEnabled(True)

    def _populate_findings(self, findings: list) -> None:
        # clear previous rows
        while self._findings_vbox.count():
            item = self._findings_vbox.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not findings:
            self._findings_scroll.hide()
            return

        first = findings[0]
        is_device_list = "ip" in first or "mac" in first

        if is_device_list:
            # header row
            hdr = QLabel("  IP Address        MAC               Vendor                  Hostname        Risk")
            hdr.setStyleSheet(
                f"font-size:10px; font-weight:bold; color:{TEXT_SECONDARY};"
                f" background:transparent; font-family:monospace;"
            )
            self._findings_vbox.addWidget(hdr)

            for dev in findings:
                risk  = dev.get("risk", "")
                color = {
                    "HIGH":    RED,
                    "UNKNOWN": AMBER,
                }.get(risk, GREEN)

                row = QFrame()
                row.setStyleSheet(
                    f"QFrame {{ background:{BG_CARD}; border:1px solid {color}30;"
                    f" border-left:3px solid {color}; border-radius:4px; }}"
                )
                rl = QHBoxLayout(row)
                rl.setContentsMargins(8, 4, 8, 4)
                rl.setSpacing(0)

                def _cell(text: str, width: int) -> QLabel:
                    lbl = QLabel(text)
                    lbl.setFixedWidth(width)
                    lbl.setStyleSheet(
                        f"font-size:11px; color:{TEXT_PRIMARY}; background:transparent;"
                        f" font-family:monospace;"
                    )
                    return lbl

                rl.addWidget(_cell(dev.get("ip", "—"), 130))
                rl.addWidget(_cell(dev.get("mac", "—"), 145))
                rl.addWidget(_cell((dev.get("vendor") or "Unknown")[:22], 180))
                rl.addWidget(_cell((dev.get("hostname") or "—")[:20], 160))
                if risk:
                    risk_lbl = QLabel(risk)
                    risk_lbl.setStyleSheet(
                        f"font-size:10px; font-weight:bold; color:{color};"
                        f" background:transparent;"
                    )
                    rl.addWidget(risk_lbl)
                rl.addStretch()
                self._findings_vbox.addWidget(row)
        else:
            # key-value summary (dns / storm scans)
            for item in findings:
                for key, val in item.items():
                    row = QFrame()
                    row.setStyleSheet(
                        f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER};"
                        f" border-radius:4px; }}"
                    )
                    rl = QHBoxLayout(row)
                    rl.setContentsMargins(8, 4, 8, 4)
                    key_lbl = QLabel(str(key).replace("_", " ").title() + ":")
                    key_lbl.setFixedWidth(160)
                    key_lbl.setStyleSheet(
                        f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent;"
                    )
                    val_lbl = QLabel(str(val))
                    val_lbl.setWordWrap(True)
                    val_lbl.setStyleSheet(
                        f"font-size:11px; color:{TEXT_PRIMARY}; background:transparent;"
                    )
                    rl.addWidget(key_lbl)
                    rl.addWidget(val_lbl)
                    rl.addStretch()
                    self._findings_vbox.addWidget(row)

        self._findings_vbox.addStretch()
        self._findings_scroll.show()

    def _toggle_hint(self, checked: bool) -> None:
        self._hint_card.setVisible(checked)
        self._hint_btn.setText("Hide Hint" if checked else "Show Hint")
        if checked and not self._hint_used_this_step:
            self._hints_used += 1
            self._hint_used_this_step = True

    def _reveal_solution(self) -> None:
        self._solution_card.show()
        self._solution_btn.setEnabled(False)
        self._solution_visible = True
        self._next_btn.setEnabled(True)

    def _next_step(self) -> None:
        assert self._scenario is not None
        total = len(self._scenario.steps)
        if self._step_idx < total - 1:
            self._step_idx += 1
            self._load_step()
        else:
            self._finish_exercise()

    def _finish_exercise(self) -> None:
        assert self._scenario is not None
        total     = len(self._scenario.steps)
        completed = self._step_idx + 1

        verdict = "PASS" if completed == total else ("PARTIAL" if completed > 0 else "INCOMPLETE")

        all_findings: list = []
        for step_findings in self._step_findings:
            all_findings.extend(step_findings)

        result = LabResult(
            scenario_id=self._scenario.id,
            scenario_title=self._scenario.title,
            completed_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            hints_used=self._hints_used,
            steps_completed=completed,
            steps_total=total,
            findings=all_findings,
            verdict=verdict,
        )
        self._result_data = result.to_dict()
        self._show_result(result)

    def _show_result(self, result: LabResult) -> None:
        self._result_title.setText(result.scenario_title)

        color = {
            "PASS": GREEN, "PARTIAL": AMBER, "INCOMPLETE": AMBER,
        }.get(result.verdict, AMBER)
        icon  = {"PASS": "✓", "PARTIAL": "△", "INCOMPLETE": "✗"}.get(result.verdict, "△")

        self._verdict_card.setStyleSheet(
            f"QFrame#verdictCard {{ background:{BG_CARD};"
            f" border-left:4px solid {color}; border:1px solid {BORDER};"
            f" border-radius:6px; }}"
        )
        self._verdict_lbl.setText(f"{icon}  {result.verdict}")
        self._verdict_lbl.setStyleSheet(
            f"font-size:15px; font-weight:bold; color:{color}; background:transparent;"
        )
        self._verdict_meta.setText(
            f"Steps completed: {result.steps_completed} / {result.steps_total}"
            f"    Hints used: {result.hints_used}"
        )
        self._stack.setCurrentIndex(_RESULT)

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def _download_badge(self) -> None:
        if not self._result_data:
            return
        from modules.utils import get_app_data_dir
        default_name = (
            f"badge_{self._result_data['scenario_id']}_"
            f"{self._result_data['completed_at'][:10]}.png"
        )
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Lab Badge",
            str(get_app_data_dir() / "reports" / default_name),
            "PNG files (*.png)",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if not path:
            return
        from modules.lab_badge import render_lab_badge_png
        render_lab_badge_png(
            self._result_data["scenario_title"],
            self._result_data["completed_at"],
            Path(path),
        )

    def _export_report(self) -> None:
        if not self._result_data:
            return
        from modules.utils import get_app_data_dir
        default_name = (
            f"lab_{self._result_data['scenario_id']}_"
            f"{self._result_data['completed_at'][:10]}.html"
        )
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Lab Report",
            str(get_app_data_dir() / "reports" / default_name),
            "HTML files (*.html)",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if not path:
            return
        from modules.report_exporter import save_lab_report
        out = save_lab_report(self._result_data, Path(path))
        import webbrowser
        webbrowser.open(out.as_uri())

    # ------------------------------------------------------------------
    # Navigation helpers
    # ------------------------------------------------------------------

    def _go_picker(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(2000)
        self._stack.setCurrentIndex(_PICKER)

    def inject_live_challenge(self, scenario: LabScenario) -> None:
        """Start a dynamically-generated scenario from a live logger event."""
        self._start_scenario(scenario)
