"""
One-click 'What's Wrong?' diagnosis page.

Three internal states managed via a QStackedWidget:
  0 — idle:    single 'Run Diagnosis' button
  1 — running: progress bar + step label + Cancel button
  2 — done:    verdict card + up to 5 finding cards + Run Again button
"""

from __future__ import annotations

import json as _json
import time as _t
from dataclasses import dataclass as _dc, field as _df
from typing import Any, List, Optional

import datetime as _dt

from PyQt6.QtCore import Qt, QSettings, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication, QButtonGroup, QComboBox, QDialog, QDialogButtonBox, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QProgressBar, QPushButton, QScrollArea,
    QStackedWidget, QVBoxLayout, QWidget,
)

from modules.metric_store import MetricStore
from ui import styles as _s
from ui.styles import (
    alpha,
)
from ui.widgets.device_detail_pane import _wire_close_icon
from ui.widgets.jargon_tooltip import JargonTooltip
from ui.dialog_utils import run_dialog

# Maps finding category names to the primary glossary term to show inline
_CATEGORY_TERM: dict[str, str] = {
    "DNS Resolution Failure":                    "DNS",
    "DNS Leak Detected":                         "DNS",
    "High Jitter — Unstable Latency":            "Jitter",
    "Rogue Network Bridge":                      "STP",
    "Broadcast Storm":                           "Broadcast Storm",
    "External ISP Issue":                        "Latency",
    "Chronic Connectivity Loss":                 "Packet Loss",
}

_SEV_COLOR_NAME = {
    "CRITICAL": "RED",
    "HIGH":     "RED",
    "MEDIUM":   "AMBER",
    "LOW":      "GREEN",
    "INFO":     "ACCENT",
}


def _sev_color(sev: str) -> str:
    return getattr(_s, _SEV_COLOR_NAME.get(sev, "ACCENT"))

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
    "Service Outage":                            ("Run Service Diagnostics →", "Service Diagnostics"),
    "External Routing Issue":                    ("Run Service Diagnostics →", "Service Diagnostics"),
}

_REMEDIATION: dict[str, list[str]] = {
    "DNS Resolution Failure": [
        "1. NetSentinel has already tested your DNS — see the result above.",
        "2. To fix slow or failing DNS, open your router's settings page and change the DNS server to 1.1.1.1 (Cloudflare) or 8.8.8.8 (Google). This fixes every device on your network at once.",
        "3. Restart your router after making the change.",
        "4. If still failing after a restart, contact your ISP.",
        "5. After the fix, go to DNS & Stability in NetSentinel and run a fresh test to confirm.",
    ],
    "DNS Leak Detected": [
        "1. Check your VPN settings — leaks often occur when split tunnelling is enabled.",
        "2. Use a DNS resolver that supports DNS-over-HTTPS (DoH), e.g. Cloudflare 1.1.1.1.",
        "3. Verify with dnsleaktest.com after each change.",
    ],
    "Chronic Connectivity Loss": [
        "1. NetSentinel's Connection Monitor is already tracking your packet loss. Check the Availability page for a full timeline of drops.",
        "2. Check all cable connections between your device, switch, and router.",
        "3. Look for interference on 2.4 GHz Wi-Fi — switch to 5 GHz if possible.",
        "4. If only one device is affected, try a different cable or switch to wired Ethernet.",
    ],
    "High Jitter — Unstable Latency": [
        "1. Run a speed test — high jitter often signals congestion on the WAN link.",
        "2. On Wi-Fi, move closer to the AP or switch bands (5 GHz for lower latency).",
        "3. Check QoS settings on your router and prioritise interactive traffic.",
        "4. If on a shared connection, identify bandwidth-hungry devices in Bandwidth Usage.",
    ],
    "Very Low Download Speed": [
        "1. Run the Speed Test page to confirm the result.",
        "2. Compare against your plan speed — if far below, restart the modem.",
        "3. Check for other heavy users or devices (torrents, backups) in Bandwidth Usage.",
        "4. If the problem persists, contact your ISP with test results.",
    ],
    "External ISP Issue": [
        "1. Power-cycle your modem (unplug, wait 30 s, replug).",
        "2. Test from a different device to confirm it's not device-specific.",
        "3. Check your ISP's status page for outages in your area.",
        "4. If your modem has a status page, look for red indicators on the WAN port.",
    ],
    "Local Network / Router Unreachable": [
        "1. Check the physical connection between your device and the router.",
        "2. Disconnect from Wi-Fi and reconnect, or unplug and replug the Ethernet cable.",
        "3. Reboot the router.",
        "4. If the router admin page is also unreachable, factory-reset it.",
    ],
    "Broadcast Storm": [
        "1. Open the Broadcast Storm page to see which devices are flooding.",
        "2. Disconnect suspect devices one at a time until the storm stops.",
        "3. Check for bridging loops — a switch or access point may be creating a cycle.",
        "4. Enable Spanning Tree Protocol (STP) on your managed switches.",
    ],
    "Degraded IoT Device — Excessive Broadcasting": [
        "1. Identify the MAC in IoT Behaviour and power-cycle that device.",
        "2. If it continues flooding after a reboot, isolate it on a VLAN.",
        "3. Check for firmware updates for the device.",
    ],
    "Rogue Network Bridge": [
        "1. Open Rogue Bridge (STP) to see which device sent BPDUs.",
        "2. Disconnect it if it is not a managed switch.",
        "3. Enable BPDU Guard on switch ports that connect end devices.",
    ],
    "Service Outage": [
        "1. The service appears to be down or unreachable from your network.",
        "2. Check the service's official status page (e.g. status.netflix.com, store.steampowered.com/status) for a known outage.",
        "3. Try from another device or a mobile hotspot to rule out local network issues.",
        "4. Open Service Diagnostics for a full DNS / TCP / latency / path breakdown.",
        "5. If only you are affected, power-cycle your modem and router.",
    ],
    "External Routing Issue": [
        "1. Your connection reaches the internet but the route to this service is degraded.",
        "2. This is typically an ISP or CDN routing problem outside your control.",
        "3. Power-cycling your modem can sometimes re-establish a better route.",
        "4. Connecting via a VPN may route around the congested path.",
        "5. Open Service Diagnostics with 'Include traceroute' enabled to inspect each hop.",
    ],
}

_IDLE    = 0
_RUNNING = 1
_DONE    = 2


# ── Service-unreachable integration helpers ───────────────────────────────────

@_dc
class _SvcFinding:
    severity: str
    headline: str
    remediation: str
    category: str
    verify_step: str = ""


@_dc
class _SynthDiagResult:
    global_severity: str
    plain_summary: str
    findings: List[Any] = _df(default_factory=list)


_LAYER_SEV_CAT: dict[str, tuple[str, str]] = {
    "device":        ("HIGH",   "Local Network / Router Unreachable"),
    "local_network": ("HIGH",   "Local Network / Router Unreachable"),
    "dns":           ("HIGH",   "DNS Resolution Failure"),
    "isp":           ("MEDIUM", "External ISP Issue"),
    "routing":       ("MEDIUM", "External Routing Issue"),
    "remote_outage": ("MEDIUM", "Service Outage"),
}

_LAYER_HEADLINE: dict[str, str] = {
    "device":        "Local device or adapter problem — cannot reach the service",
    "local_network": "Local network failure — service unreachable from this device",
    "dns":           "DNS resolution failed for service hosts",
    "isp":           "ISP-level connectivity problem detected",
    "routing":       "Routing anomaly between your ISP and the service",
    "remote_outage": "Service appears down or unreachable from multiple paths",
}


def _svc_result_to_diag(result: Any) -> _SynthDiagResult:
    layer = getattr(result, "failure_layer", "none")
    name  = getattr(result, "service_name",  "Service")
    summary = getattr(result, "summary", "") or ""

    if layer == "none" or layer not in _LAYER_SEV_CAT:
        return _SynthDiagResult(
            global_severity="INFO",
            plain_summary=summary or f"{name} is reachable.",
            findings=[],
        )

    sev, category = _LAYER_SEV_CAT[layer]
    headline = f"{name}: {_LAYER_HEADLINE.get(layer, 'Service unreachable')}"
    finding = _SvcFinding(
        severity=sev,
        headline=headline,
        remediation=summary,
        category=category,
    )
    return _SynthDiagResult(
        global_severity=sev,
        plain_summary=summary or f"{name}: {layer}",
        findings=[finding],
    )


def _save_diag_history(result) -> None:
    findings = getattr(result, "findings", [])
    entry = {
        "ts":       _t.time(),
        "severity": getattr(result, "global_severity", "INFO"),
        "summary":  getattr(result, "plain_summary",   "") or "",
        "findings": [
            {
                "severity":    getattr(f, "severity",    "INFO"),
                "headline":    getattr(f, "headline",    ""),
                "remediation": getattr(f, "remediation", ""),
                "category":    getattr(f, "category",    ""),
            }
            for f in findings[:5]
        ],
    }
    s = QSettings("NetSentinel", "NetSentinel")
    try:
        history = _json.loads(s.value("diagnosis/history", "[]"))
    except Exception:
        history = []
    history.insert(0, entry)
    s.setValue("diagnosis/history", _json.dumps(history[:5]))


class DiagnosisPage(QWidget):

    navigate_to          = pyqtSignal(str)  # emits "Dashboard" when back link is clicked
    diagnosis_saved      = pyqtSignal()     # emitted after each completed run
    scan_requested       = pyqtSignal()     # emitted when user clicks Run Diagnosis
    service_diag_requested = pyqtSignal(str)  # emitted for service_unreachable; arg = service_id

    def __init__(self, store: Optional[MetricStore] = None, parent=None):
        super().__init__(parent)
        self._store           = store
        self._worker          = None
        self._isp_worker      = None
        self._gateway_ip      = None
        self._gateway_mac     = None
        self._symptom         = ""   # set by symptom tile before _start()
        self._prev_finding_headlines: set[str] = set()
        self._last_findings: list = []
        self._last_result = None
        self._verify_workers: list = []  # keeps refs alive until verify completes
        self._setup_ui()

    # ── Public API (called by TroubleshootPage) ───────────────────────────────

    def preset_symptom(self, key: str) -> None:
        """Pre-select a symptom tile. Navigates to idle state and hides previous results."""
        btn = self._symptom_btns.get(key)
        if btn:
            btn.setChecked(True)
            self._symptom = key
            self._service_pick_row.setVisible(key == "service_unreachable")
            self._other_desc_row.setVisible(key == "other")
        if self._stack.currentIndex() != _IDLE:
            self._reset()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        QTimer.singleShot(600, self._maybe_show_coach_diagnosis)

    def _maybe_show_coach_diagnosis(self) -> None:
        if not self.isVisible():
            return
        qs = QSettings("NetSentinel", "NetSentinel")
        if not qs.value("tour/v1_done", False, type=bool):
            return
        key = "coach/diagnosis_shown"
        if qs.value(key, False, type=bool):
            return
        if self._stack.currentIndex() != 0:
            return
        win = self.window()
        if not (win and win.isVisible()):
            return
        target_btn = self._symptom_btns.get("slow")
        if not target_btn:
            return
        from ui.widgets.coach_mark import CoachMarkChain
        CoachMarkChain(
            win,
            [{
                "target": lambda b=target_btn: b,
                "title": "Describe your symptom",
                "body": (
                    "Pick the symptom closest to what you're experiencing. "
                    "NetSentinel runs targeted checks instead of a full scan "
                    "— takes 30 seconds."
                ),
            }],
            on_done=lambda: QSettings("NetSentinel", "NetSentinel").setValue(key, True),
        ).start()

    def set_network_info(
        self,
        gateway_ip: Optional[str],
        gateway_mac: Optional[str],
    ) -> None:
        self._gateway_ip  = gateway_ip
        self._gateway_mac = gateway_mac

    # ── ISP vs Router quick test (S3-4) ──────────────────────────────────────

    def _launch_isp_test(self) -> None:
        if self._isp_worker and self._isp_worker.isRunning():
            return
        self._isp_btn.setText("Testing… please wait")
        self._isp_btn.setEnabled(False)
        self._isp_result_card.hide()

        from workers.isp_vs_router_worker import IspVsRouterWorker
        self._isp_worker = IspVsRouterWorker(
            gateway_ip=self._gateway_ip,
            parent=self,
        )
        self._isp_worker.result_ready.connect(self._on_isp_result)
        self._isp_worker.error.connect(self._on_isp_error)
        self._isp_worker.start()

    def _on_isp_result(self, result) -> None:
        self._isp_btn.setText("Quick test: Is this my ISP or my router?")
        self._isp_btn.setEnabled(True)
        _CATEGORY_COLORS = {
            "local":    _s.RED,
            "isp":      _s.AMBER,
            "external": _s.AMBER,
            "all_ok":   _s.GREEN,
            "unknown":  _s.TEXT_SECONDARY,
        }
        color = _CATEGORY_COLORS.get(result.category, _s.TEXT_SECONDARY)
        self._isp_result_card.setStyleSheet(
            f"QFrame#ispResultCard {{ background:{_s.BG_CARD}; border:1px solid {color};"
            f" border-left:3px solid {color}; border-radius:4px; }}"
        )
        self._isp_verdict_lbl.setText(result.verdict)
        self._isp_verdict_lbl.setStyleSheet(
            f"font-size:12px; font-weight:bold; color:{color}; border:none; background:transparent;"
        )
        self._isp_detail_lbl.setText(result.plain_answer)
        self._isp_result_card.show()

    def _on_isp_error(self, msg: str) -> None:
        self._isp_btn.setText("Quick test: Is this my ISP or my router?")
        self._isp_btn.setEnabled(True)
        self._isp_verdict_lbl.setText("Test failed")
        self._isp_detail_lbl.setText(msg or "Could not run the quick test.")
        self._isp_result_card.show()

    # ── UI construction ───────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        _s.themed_ss(self, "QWidget {{ background:{BG_DARK}; }}")
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        # Back link
        back_btn = QPushButton("← Overview")
        back_btn.setFlat(True)
        _s.themed_ss(back_btn, "QPushButton {{ color:{ACCENT}; font-size:11px; background:transparent;"
            " border:none; padding:0; text-align:left; }}"
            "QPushButton:hover {{ color:{ACCENT_DARK}; }}"
            "QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}")
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.clicked.connect(lambda: self.navigate_to.emit("Dashboard"))
        root.addWidget(back_btn)

        from ui.widgets.page_header import PageHeaderBar
        _hdr = PageHeaderBar("What's Wrong?", subtitle="Diagnose your network problem in plain English — pick a symptom to begin.")
        _hdr.show_first_visit_banner(
            "whats_wrong",
            "Pick the option that best matches what you're seeing, then NetSentinel runs a "
            "short sequence of checks and gives you a plain-English verdict with a "
            "prioritised list of fixes.",
        )
        root.addWidget(_hdr)

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
        _s.themed_ss(prompt, "font-size:15px; font-weight:bold; color:{TEXT_PRIMARY}; background:transparent;")
        lay.addWidget(prompt)

        _SYMPTOMS = [
            ("My internet is slow",          "slow"),
            ("My connection keeps dropping", "dropping"),
            ("I can't connect at all",       "noconn"),
            ("A service is unreachable",     "service_unreachable"),
            ("Something else…",         "other"),
        ]

        tiles_row = QHBoxLayout()
        tiles_row.setSpacing(12)
        self._symptom_group = QButtonGroup(w)
        self._symptom_group.setExclusive(True)

        _tile_base = (
            "QPushButton {{ background:{BG_CARD}; color:{TEXT_PRIMARY};"
            " border:2px solid {BORDER}; border-radius:8px;"
            " font-size:12px; padding:18px 12px; }}"
            "QPushButton:hover {{ border-color:{ACCENT}; color:{ACCENT}; }}"
            "QPushButton:checked {{ border-color:{ACCENT}; background:{ACCENT};"
            " color:{WHITE}; }}"
        )

        self._symptom_btns: dict = {}
        for label, key in _SYMPTOMS:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setFixedHeight(72)
            btn.setMinimumWidth(160)
            _s.themed_ss(btn, _tile_base)
            btn.setProperty("symptom_key", key)
            self._symptom_group.addButton(btn)
            self._symptom_btns[key] = btn
            tiles_row.addWidget(btn)

        # Default selection
        self._symptom_btns["slow"].setChecked(True)
        self._symptom = "slow"

        def _on_symptom_clicked(btn):
            self._symptom = btn.property("symptom_key")
            self._service_pick_row.setVisible(self._symptom == "service_unreachable")
            self._other_desc_row.setVisible(self._symptom == "other")

        self._symptom_group.buttonClicked.connect(_on_symptom_clicked)

        lay.addLayout(tiles_row)

        # Service picker — shown only when "service_unreachable" tile is selected
        self._service_pick_row = QWidget()
        self._service_pick_row.setStyleSheet("background:transparent;")
        sp_lay = QHBoxLayout(self._service_pick_row)
        sp_lay.setContentsMargins(0, 0, 0, 0)
        sp_lay.setSpacing(8)
        sp_label = QLabel("Service:")
        _s.themed_ss(sp_label, "font-size:11px; color:{TEXT_SECONDARY}; background:transparent;")
        self._symptom_service_combo = QComboBox()
        self._symptom_service_combo.setMinimumWidth(200)
        from modules.service_diagnostics import SERVICE_CATALOG
        _streaming = sorted(
            (e for e in SERVICE_CATALOG.values() if e.category == "streaming"),
            key=lambda e: e.name,
        )
        _gaming = sorted(
            (e for e in SERVICE_CATALOG.values() if e.category == "gaming"),
            key=lambda e: e.name,
        )
        for _e in _streaming:
            self._symptom_service_combo.addItem(f"{_e.name}  (Streaming)", _e.id)
        for _e in _gaming:
            self._symptom_service_combo.addItem(f"{_e.name}  (Gaming)", _e.id)
        sp_lay.addWidget(sp_label)
        sp_lay.addWidget(self._symptom_service_combo)
        sp_lay.addStretch()
        lay.addWidget(self._service_pick_row)
        self._service_pick_row.setVisible(False)

        # Free-text description — shown only when "Something else…" tile is selected
        self._other_desc_row = QWidget()
        self._other_desc_row.setStyleSheet("background:transparent;")
        _od_lay = QHBoxLayout(self._other_desc_row)
        _od_lay.setContentsMargins(0, 0, 0, 0)
        _od_lay.setSpacing(8)
        _od_label = QLabel("Describe the issue:")
        _s.themed_ss(_od_label, "font-size:11px; color:{TEXT_SECONDARY}; background:transparent;")
        self._other_desc_edit = QLineEdit()
        self._other_desc_edit.setPlaceholderText("e.g. my printer can't be found, one device is much slower than others…")
        self._other_desc_edit.setFixedHeight(28)
        _s.themed_ss(self._other_desc_edit, "QLineEdit {{ background:{BG_CARD}; color:{TEXT_PRIMARY}; border:1px solid {BORDER};"
            " border-radius:4px; padding:0 6px; font-size:11px; }}"
            "QLineEdit:focus {{ border-color:{ACCENT}; }}")
        _od_lay.addWidget(_od_label)
        _od_lay.addWidget(self._other_desc_edit, 1)
        lay.addWidget(self._other_desc_row)
        self._other_desc_row.setVisible(False)

        _tile_hint = QLabel("Select a symptom, then click Run Diagnosis — NetSentinel runs targeted checks and shows plain-English results in 15–30 seconds.")
        _tile_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _tile_hint.setWordWrap(True)
        _s.themed_ss(_tile_hint, "font-size:11px; font-style:italic; color:{TEXT_SECONDARY}; background:transparent;")
        lay.addWidget(_tile_hint)

        run_btn = QPushButton("Run Diagnosis")
        run_btn.setFixedWidth(180)
        run_btn.setFixedHeight(44)
        _s.themed_ss(run_btn, "QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
            " font-size:13px; font-weight:bold; border-radius:6px; }}"
            "QPushButton:hover {{ background:{ACCENT_DARK}; }}"
            "QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}")
        run_btn.clicked.connect(self._start)
        lay.addWidget(run_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        hint = QLabel("Takes about 30 seconds.")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _s.themed_ss(hint, "font-size:11px; color:{TEXT_SECONDARY}; background:transparent;")
        lay.addWidget(hint)

        # ISP vs Router quick test (S3-4)
        sep_line = QFrame()
        sep_line.setFrameShape(QFrame.Shape.HLine)
        _s.themed_ss(sep_line, "color:{BORDER}; background:{BORDER}; border:none; max-height:1px;")
        lay.addWidget(sep_line)

        self._isp_btn = QPushButton("Quick test: Is this my ISP or my router?")
        self._isp_btn.setFixedHeight(32)
        _s.themed_ss(self._isp_btn, "QPushButton {{ background:transparent; color:{ACCENT}; border:1px solid {ACCENT};"
            " font-size:11px; border-radius:4px; padding:0 12px; }}"
            "QPushButton:hover {{ background:{BG_HOVER}; }}"
            "QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT_DARK}; }}")
        self._isp_btn.clicked.connect(self._launch_isp_test)
        lay.addWidget(self._isp_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        # ISP test result card — hidden until a test completes
        self._isp_result_card = QFrame()
        self._isp_result_card.setObjectName("ispResultCard")
        _s.themed_ss(self._isp_result_card, "QFrame#ispResultCard {{ background:{BG_CARD}; border:1px solid {BORDER};"
            " border-radius:4px; }}")
        _irc_lay = QVBoxLayout(self._isp_result_card)
        _irc_lay.setContentsMargins(12, 8, 12, 8)
        _irc_lay.setSpacing(4)
        self._isp_verdict_lbl = QLabel("–")
        self._isp_verdict_lbl.setWordWrap(True)
        _s.themed_ss(self._isp_verdict_lbl, "font-size:12px; font-weight:bold; color:{TEXT_PRIMARY}; border:none; background:transparent;")
        self._isp_detail_lbl = QLabel("")
        self._isp_detail_lbl.setWordWrap(True)
        _s.themed_ss(self._isp_detail_lbl, "font-size:11px; color:{TEXT_SECONDARY}; border:none; background:transparent;")
        _irc_lay.addWidget(self._isp_verdict_lbl)
        _irc_lay.addWidget(self._isp_detail_lbl)
        self._isp_result_card.hide()
        lay.addWidget(self._isp_result_card)

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
        _s.themed_ss(self._progress_bar, "QProgressBar {{ background:{PROGRESS_TRACK}; border-radius:5px; border:none; }}"
            "QProgressBar::chunk {{ background:{ACCENT}; border-radius:5px; }}")

        self._step_lbl = QLabel("Starting…")
        self._step_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _s.themed_ss(self._step_lbl, "font-size:13px; color:{TEXT_SECONDARY}; background:transparent;")

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setFixedWidth(100)
        _s.themed_ss(self._cancel_btn, "QPushButton {{ background:{BG_CARD}; color:{TEXT_SECONDARY};"
            " border:1px solid {BORDER}; padding:4px 14px; font-size:11px;"
            " border-radius:4px; }}"
            "QPushButton:hover {{ color:{TEXT_PRIMARY}; }}"
            "QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}")
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

        # Amber logger warning — shown when logger has never been started
        self._logger_warn = QFrame()
        self._logger_warn.setObjectName("loggerWarn")
        _s.themed_ss(self._logger_warn, lambda: (
            f"QFrame#loggerWarn {{ background:{alpha(_s.AMBER, 0x18)}; border:1px solid {alpha(_s.AMBER, 0x66)};"
            f" border-radius:3px; }}"
        ))
        _lw_lay = QHBoxLayout(self._logger_warn)
        _lw_lay.setContentsMargins(10, 6, 10, 6)
        _lw_lay.setSpacing(8)
        _lw_icon = QLabel("⚠")
        _s.themed_ss(_lw_icon, "font-size:13px; color:{AMBER}; background:transparent; border:none;")
        _lw_text = QLabel(
            "Network Logger has no data yet — some findings may be incomplete. "
            "Start the logger and let it run for a few hours for the best results."
        )
        _lw_text.setWordWrap(True)
        _s.themed_ss(_lw_text, "font-size:11px; color:{TEXT_PRIMARY}; background:transparent; border:none;")
        _lw_dismiss = QPushButton()
        _lw_dismiss.setFixedSize(18, 18)
        _wire_close_icon(_lw_dismiss)
        _s.themed_ss(_lw_dismiss, "QPushButton {{ background:transparent; border:none; padding:0; }}"
            "QPushButton:hover {{ background:transparent; }}"
            "QPushButton:pressed {{ background:transparent; }}")
        _lw_dismiss.clicked.connect(lambda: self._logger_warn.setVisible(False))
        _lw_lay.addWidget(_lw_icon)
        _lw_lay.addWidget(_lw_text, 1)
        _lw_lay.addWidget(_lw_dismiss)
        outer.addWidget(self._logger_warn)
        # Show only if logger has never been started
        from PyQt6.QtCore import QSettings as _QS2
        _logger_started = _QS2().value("logger_started_once", False, type=bool)
        self._logger_warn.setVisible(not _logger_started)

        # Symptom context label — shows which symptom the user reported (S3-3)
        self._symptom_ctx_lbl = QLabel("")
        _s.themed_ss(self._symptom_ctx_lbl, "font-size:10px; color:{TEXT_MUTED}; background:transparent; border:none; padding:0 2px;")
        self._symptom_ctx_lbl.hide()
        outer.addWidget(self._symptom_ctx_lbl)

        # Verdict card
        self._verdict_card = QFrame()
        self._verdict_card.setObjectName("verdictCard")
        _s.themed_ss(self._verdict_card, "QFrame#verdictCard {{ background:{BG_CARD};"
            " border-left:4px solid {ACCENT}; border-top:1px solid {BORDER};"
            " border-right:1px solid {BORDER}; border-bottom:1px solid {BORDER}; }}")
        vc_lay = QVBoxLayout(self._verdict_card)
        vc_lay.setContentsMargins(14, 10, 14, 10)
        vc_lay.setSpacing(4)

        self._verdict_title = QLabel("Diagnosis Result")
        _s.themed_ss(self._verdict_title, "font-size:13px; font-weight:bold; color:{TEXT_PRIMARY};"
            " border:none; background:transparent;")
        self._verdict_text = QLabel("–")
        self._verdict_text.setWordWrap(True)
        _s.themed_ss(self._verdict_text, "font-size:12px; color:{TEXT_PRIMARY}; border:none; background:transparent;")
        vc_lay.addWidget(self._verdict_title)
        vc_lay.addWidget(self._verdict_text)
        outer.addWidget(self._verdict_card)

        # Diff badge — shown on re-runs when new findings appeared
        self._diff_lbl = QLabel("")
        _s.themed_ss(self._diff_lbl, "font-size:10px; color:{AMBER}; background:transparent;"
            " border:none; padding:0 2px;")
        self._diff_lbl.hide()
        outer.addWidget(self._diff_lbl)

        # Quiet inline "Share this result" strip (Feature 3a) — surfaced on every
        # completed run so the shareable assets are one click away at the moment
        # the user has a result worth sharing. No modal, no confetti.
        self._share_card = QFrame()
        self._share_card.setObjectName("shareCard")
        _s.themed_ss(self._share_card, "QFrame#shareCard {{ background:{BG_CARD}; border:1px solid {BORDER};"
            " border-radius:4px; }}")
        _sc_lay = QHBoxLayout(self._share_card)
        _sc_lay.setContentsMargins(12, 6, 12, 6)
        _sc_lay.setSpacing(8)
        _share_lbl = QLabel("Share this result")
        _s.themed_ss(_share_lbl, "font-size:11px; font-weight:bold; color:{TEXT_SECONDARY};"
            " background:transparent; border:none;")
        _sc_lay.addWidget(_share_lbl)
        _sc_lay.addStretch()
        _share_btn_qss = (
            "QPushButton {{ background:transparent; color:{ACCENT};"
            " border:1px solid {ACCENT}; padding:3px 10px; font-size:10px;"
            " border-radius:4px; }}"
            "QPushButton:hover {{ background:{ACCENT}; color:{WHITE}; }}"
            "QPushButton:pressed {{ background:{ACCENT_DARK}; color:{WHITE}; }}"
        )
        self._share_img_btn = QPushButton("Copy as image")
        _s.themed_ss(self._share_img_btn, _share_btn_qss)
        self._share_img_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._share_img_btn.clicked.connect(self._copy_share_image)
        _sc_lay.addWidget(self._share_img_btn)
        self._share_md_btn = QPushButton("Copy as Markdown")
        _s.themed_ss(self._share_md_btn, _share_btn_qss)
        self._share_md_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._share_md_btn.clicked.connect(self._copy_share_markdown)
        _sc_lay.addWidget(self._share_md_btn)
        self._share_card.hide()
        outer.addWidget(self._share_card)

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
        _s.themed_ss(self._other_toggle, "QPushButton {{ color:{ACCENT}; font-size:11px; background:transparent;"
            " border:none; padding:4px 0; text-align:left; }}"
            "QPushButton:hover {{ color:{ACCENT_DARK}; }}"
            "QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}")
        self._other_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._other_toggle.clicked.connect(self._toggle_other_findings)
        self._other_expanded = False
        outer.addWidget(self._other_toggle)

        # Findings list in a scroll area
        self._findings_scroll = QScrollArea()
        self._findings_scroll.setWidgetResizable(True)
        self._findings_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._findings_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        _s.themed_ss(self._findings_scroll, "QScrollArea {{ background:{BG_DARK}; border:none; }}")

        self._findings_container = QWidget()
        _s.themed_ss(self._findings_container, "background:{BG_DARK};")
        self._findings_layout = QVBoxLayout(self._findings_container)
        self._findings_layout.setContentsMargins(0, 0, 0, 0)
        self._findings_layout.setSpacing(6)
        self._findings_layout.addStretch()

        self._findings_scroll.setWidget(self._findings_container)
        outer.addWidget(self._findings_scroll, 1)

        # "All clear" CTA — shown only when no findings
        self._grade_cta = QPushButton("Get a Network Grade score →")
        self._grade_cta.setFlat(True)
        _s.themed_ss(self._grade_cta, "QPushButton {{ color:{ACCENT}; font-size:11px; background:transparent;"
            " border:none; padding:2px 0; text-align:left; }}"
            "QPushButton:hover {{ color:{ACCENT_DARK}; }}"
            "QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}")
        self._grade_cta.setCursor(Qt.CursorShape.PointingHandCursor)
        self._grade_cta.clicked.connect(lambda: self.navigate_to.emit("Network Grade"))
        self._grade_cta.hide()
        outer.addWidget(self._grade_cta)

        # Run Again + Copy report buttons
        btn_row = QHBoxLayout()
        self._again_btn = QPushButton("Run Again")
        self._again_btn.setFixedWidth(120)
        _btn_qss = (
            "QPushButton {{ background:{BG_CARD}; color:{ACCENT};"
            " border:1px solid {ACCENT}; padding:4px 14px; font-size:11px;"
            " border-radius:4px; }}"
            "QPushButton:hover {{ background:{ACCENT}; color:{WHITE}; }}"
        )
        _s.themed_ss(self._again_btn, _btn_qss)
        self._again_btn.clicked.connect(self._reset)
        btn_row.addWidget(self._again_btn)

        self._copy_btn = QPushButton("Copy report")
        self._copy_btn.setFixedWidth(120)
        _s.themed_ss(self._copy_btn, _btn_qss)
        self._copy_btn.clicked.connect(self._copy_report)
        btn_row.addWidget(self._copy_btn)

        self._history_btn = QPushButton("History")
        self._history_btn.setFixedWidth(80)
        _s.themed_ss(self._history_btn, _btn_qss)
        self._history_btn.clicked.connect(self._show_history_dialog)
        btn_row.addWidget(self._history_btn)

        self._export_btn = QPushButton("Export…")
        self._export_btn.setFixedWidth(80)
        _s.themed_ss(self._export_btn, _btn_qss)
        self._export_btn.clicked.connect(self._export_report)
        btn_row.addWidget(self._export_btn)

        self._forum_btn = QPushButton("Copy for Reddit/Discord")
        self._forum_btn.setFixedWidth(170)
        _s.themed_ss(self._forum_btn, _btn_qss)
        self._forum_btn.clicked.connect(self._copy_forum_markdown)
        btn_row.addWidget(self._forum_btn)

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
        category = getattr(finding, "category",    "")
        color    = _sev_color(sev)

        card = QFrame()
        card.setObjectName("findingCard")
        border_w = "4px" if hero else "3px"
        card.setStyleSheet(
            f"QFrame#findingCard {{ background:{_s.BG_CARD};"
            f" border-left:{border_w} solid {color}; border-top:1px solid {_s.BORDER};"
            f" border-right:1px solid {_s.BORDER}; border-bottom:1px solid {_s.BORDER}; }}"
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
            f"font-size:{hl_size}; font-weight:bold; color:{_s.TEXT_PRIMARY};"
            f" border:none; background:transparent;"
        )
        hdr.addWidget(badge)
        hdr.addWidget(hl, 1)
        # Show a jargon tooltip chip for the primary technical term in this finding
        _term = _CATEGORY_TERM.get(category)
        if _term:
            _jt = JargonTooltip(_term)
            _s.themed_ss(_jt, "font-size:9px; color:{ACCENT}; text-decoration:underline dotted;"
                " background:transparent; padding:0 2px;")
            hdr.addWidget(_jt)
        lay.addLayout(hdr)

        if remedy:
            rem = QLabel(remedy)
            rem.setWordWrap(True)
            rem_size = "12px" if hero else "11px"
            rem.setStyleSheet(
                f"font-size:{rem_size}; color:{_s.TEXT_SECONDARY}; border:none; background:transparent;"
            )
            lay.addWidget(rem)

        # EXPLAIN-3: collapsible "▶ What to do" remediation expander
        steps = _REMEDIATION.get(category) or _REMEDIATION.get(headline)
        if steps:
            expander_btn = QPushButton("▶  What to do")
            expander_btn.setFlat(True)
            expander_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            expander_btn.setStyleSheet(
                f"QPushButton {{ color:{_s.ACCENT}; font-size:11px; background:transparent;"
                f" border:none; padding:2px 0; text-align:left; }}"
                f"QPushButton:hover {{ color:{color}; }}"
                f"QPushButton:pressed {{ background:{_s.BG_HOVER}; color:{_s.ACCENT}; }}"
            )
            steps_widget = QFrame()
            _s.themed_ss(steps_widget, "QFrame {{ background:{BG_HOVER}; border-left:2px solid {BORDER};"
                " border-top:none; border-right:none; border-bottom:none;"
                " margin-left:4px; }}")
            steps_widget.setVisible(False)
            sw_lay = QVBoxLayout(steps_widget)
            sw_lay.setContentsMargins(10, 6, 6, 6)
            sw_lay.setSpacing(3)
            for step in steps:
                sl = QLabel(step)
                sl.setWordWrap(True)
                _s.themed_ss(sl, "font-size:10px; color:{TEXT_SECONDARY}; background:transparent; border:none;")
                sw_lay.addWidget(sl)

            def _toggle_steps(checked: bool, btn=expander_btn, sw=steps_widget) -> None:
                sw.setVisible(checked)
                btn.setText(("▼" if checked else "▶") + "  What to do")

            expander_btn.setCheckable(True)
            expander_btn.toggled.connect(_toggle_steps)
            lay.addWidget(expander_btn)
            lay.addWidget(steps_widget)

        if category in _CTA_MAP:
            cta_label, cta_target = _CTA_MAP[category]
            cta_btn = QPushButton(cta_label)
            cta_btn.setFlat(True)
            cta_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            _s.themed_ss(cta_btn, "QPushButton {{ color:{ACCENT}; font-size:11px; background:transparent;"
                " border:none; padding:2px 0; text-align:left; }}"
                "QPushButton:hover {{ color:{ACCENT_DARK}; }}"
                "QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}")
            cta_btn.clicked.connect(
                lambda _=False, t=cta_target: self.navigate_to.emit(t)
            )
            lay.addWidget(cta_btn)

        # "Verify this fix" — shows verify_step text + re-check button
        verify_step = getattr(finding, "verify_step", "")
        if verify_step:
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            _s.themed_ss(sep, "color:{BORDER}; background:{BORDER}; border:none; max-height:1px;")
            lay.addWidget(sep)

            after_lbl = QLabel(f"After fixing: {verify_step}")
            after_lbl.setWordWrap(True)
            _s.themed_ss(after_lbl, "font-size:10px; color:{TEXT_SECONDARY}; background:transparent; border:none;")
            lay.addWidget(after_lbl)

            verify_row = QHBoxLayout()
            verify_row.setSpacing(8)

            verify_btn = QPushButton("▶  Verify this fix")
            verify_btn.setFlat(True)
            verify_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            _s.themed_ss(verify_btn, "QPushButton {{ color:{ACCENT}; font-size:11px; background:transparent;"
                " border:none; padding:2px 0; text-align:left; }}"
                "QPushButton:hover {{ color:{ACCENT_DARK}; }}"
                "QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}")

            verify_status = QLabel("")
            _s.themed_ss(verify_status, "font-size:10px; color:{TEXT_SECONDARY}; background:transparent; border:none;")

            verify_row.addWidget(verify_btn)
            verify_row.addWidget(verify_status)
            verify_row.addStretch()

            center = QHBoxLayout()
            center.addLayout(verify_row)
            lay.addLayout(center)

            verify_btn.clicked.connect(
                lambda _=False, cat=category, btn=verify_btn, lbl=verify_status:
                    self._run_verify(cat, btn, lbl)
            )

        return card

    # ── Verify loop ───────────────────────────────────────────────────────────

    def _run_verify(self, category: str, btn: QPushButton, status_lbl: QLabel) -> None:
        """Run a focused re-check for one finding category and update the inline status."""
        btn.setEnabled(False)
        btn.setText("Checking…")
        status_lbl.setText("")

        from workers.diagnosis_worker import DiagnosisWorker
        worker = DiagnosisWorker(
            gateway_ip=self._gateway_ip,
            gateway_mac=self._gateway_mac,
            focused_on=category,
            store=self._store,
            parent=self,
        )
        self._verify_workers.append(worker)

        def _on_done(result, _w=worker, _cat=category, _btn=btn, _lbl=status_lbl):
            if _w in self._verify_workers:
                self._verify_workers.remove(_w)
            _w.deleteLater()
            _btn.setText("▶  Verify this fix")
            _btn.setEnabled(True)
            findings = getattr(result, "findings", []) if result else []
            still_present = any(getattr(f, "category", "") == _cat for f in findings)
            if still_present:
                _lbl.setText("Still present — try next step")
                _s.themed_ss(_lbl, "font-size:10px; color:{AMBER}; background:transparent; border:none;")
            else:
                _lbl.setText("✓ Fixed!")
                _s.themed_ss(_lbl, "font-size:10px; color:{GREEN}; background:transparent; border:none;")

        worker.finished.connect(_on_done)
        worker.start()

    # ── State machine ─────────────────────────────────────────────────────────

    def _start(self) -> None:
        if self._symptom == "service_unreachable":
            idx = self._symptom_service_combo.currentIndex()
            service_id = self._symptom_service_combo.itemData(idx) if idx >= 0 else "netflix"
            self.service_diag_requested.emit(service_id)
            return
        # "Something else…" runs a full general diagnosis
        effective_symptom = "slow" if self._symptom == "other" else self._symptom
        self.scan_requested.emit()
        self._stack.setCurrentIndex(_RUNNING)
        self._progress_bar.setValue(0)
        self._step_lbl.setText("Starting…")
        from workers.diagnosis_worker import DiagnosisWorker
        self._worker = DiagnosisWorker(
            gateway_ip=self._gateway_ip,
            gateway_mac=self._gateway_mac,
            symptom=effective_symptom,
            store=self._store,
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
        self._share_card.hide()
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
        _t = QTimer(self)
        _t.setSingleShot(True)
        _t.timeout.connect(lambda: self._copy_btn.setText("Copy report"))
        _t.start(2000)

    def _copy_forum_markdown(self) -> None:
        """Copy a sanitized, forum-ready Markdown post to the clipboard."""
        from modules.forum_export import build_diagnosis_markdown
        if self._last_result is None:
            return
        md = build_diagnosis_markdown(self._last_result, symptom=self._symptom)
        QApplication.clipboard().setText(md)
        self._forum_btn.setText("Copied ✓")
        from PyQt6.QtCore import QTimer
        _t = QTimer(self)
        _t.setSingleShot(True)
        _t.timeout.connect(lambda: self._forum_btn.setText("Copy for Reddit/Discord"))
        _t.start(2000)

    def _copy_share_markdown(self) -> None:
        """Inline share card: copy sanitized forum Markdown to the clipboard."""
        from modules.forum_export import build_diagnosis_markdown
        if self._last_result is None:
            return
        md = build_diagnosis_markdown(self._last_result, symptom=self._symptom)
        QApplication.clipboard().setText(md)
        self._share_md_btn.setText("Copied ✓")
        _t2 = QTimer(self)
        _t2.setSingleShot(True)
        _t2.timeout.connect(lambda: self._share_md_btn.setText("Copy as Markdown"))
        _t2.start(2000)

    def _copy_share_image(self) -> None:
        """Inline share card: render the diagnosis health card and copy it to
        the clipboard as an image (sanitized findings, real last grade)."""
        if self._last_result is None:
            return
        from modules.diagnostic_card import build_card_data_from_diagnosis
        from ui.widgets.diagnostic_card_widget import render_card_widget
        card_data = build_card_data_from_diagnosis(self._last_result, self._store)
        widget = render_card_widget(card_data)
        widget.show()          # must be visible for grab() to paint correctly
        widget.hide()
        QApplication.clipboard().setPixmap(widget.grab())
        widget.deleteLater()
        self._share_img_btn.setText("Copied ✓")
        _t3 = QTimer(self)
        _t3.setSingleShot(True)
        _t3.timeout.connect(lambda: self._share_img_btn.setText("Copy as image"))
        _t3.start(2000)

    def _export_report(self) -> None:
        from PyQt6.QtWidgets import QFileDialog
        from ui.widgets.toast import ToastManager
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Diagnosis Report", "diagnosis_report.txt", "Text files (*.txt)",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if not path:
            return
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
                    lines.append(f"  [{getattr(f, 'severity', '')}] {h}")
            lines.append("")
            lines.append("Recommended actions:")
            for f in self._last_findings:
                r = getattr(f, "remediation", "")
                if r:
                    lines.append(f"  • {r}")
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("\n".join(lines))
            import os
            ToastManager.show(f"✓ Saved to {os.path.basename(path)}", "success")
        except Exception as exc:
            ToastManager.show(f"Export failed: {exc}", "error")

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
        self._last_result = result
        _save_diag_history(result)
        self.diagnosis_saved.emit()

        # Symptom context (S3-3) — remind the user what they reported
        _SYMPTOM_LABELS = {
            "slow":     "You reported: My internet is slow",
            "dropping": "You reported: My connection keeps dropping",
            "noconn":   "You reported: I can't connect at all",
            "other":    "You reported: Something else",
        }
        ctx = _SYMPTOM_LABELS.get(self._symptom, "")
        if ctx:
            self._symptom_ctx_lbl.setText(ctx)
            self._symptom_ctx_lbl.show()
        else:
            self._symptom_ctx_lbl.hide()

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
            _s.themed_ss(self._verdict_card, "QFrame#verdictCard {{ background:{BG_CARD};"
                " border-left:4px solid {GREEN}; border-top:1px solid {BORDER};"
                " border-right:1px solid {BORDER}; border-bottom:1px solid {BORDER}; }}")
            self._verdict_title.setText("Your network looks healthy")
            _s.themed_ss(self._verdict_title, "font-size:13px; font-weight:bold; color:{GREEN};"
                " border:none; background:transparent;")
            self._verdict_text.setText(
                "Gateway responding  ·  DNS working  ·  No broadcast storms"
                "  ·  No rogue devices  ·  No network loops"
            )
            self._hero_card_container.hide()
            self._other_toggle.hide()
            self._findings_scroll.hide()
            self._grade_cta.show()
        else:
            color = _sev_color(sev)
            self._verdict_card.setStyleSheet(
                f"QFrame#verdictCard {{ background:{_s.BG_CARD};"
                f" border-left:4px solid {color}; border-top:1px solid {_s.BORDER};"
                f" border-right:1px solid {_s.BORDER}; border-bottom:1px solid {_s.BORDER}; }}"
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
                _s.themed_ss(self._diff_lbl, "font-size:10px; color:{TEXT_SECONDARY}; background:transparent;"
                    " border:none; padding:0 2px;")
                self._diff_lbl.show()
        else:
            self._diff_lbl.hide()
        self._prev_finding_headlines = current_headlines

        self._share_card.show()
        self._stack.setCurrentIndex(_DONE)

    def _show_history_dialog(self) -> None:
        dlg = _DiagHistoryDialog(self)
        run_dialog(dlg)


class _DiagHistoryDialog(QDialog):
    """Shows the last 5 diagnosis results stored in QSettings."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Diagnosis History")
        self.setMinimumWidth(480)
        _s.themed_ss(self, "QDialog {{ background:{BG_DARK}; }} QLabel {{ background:transparent; border:none; }}")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 12)
        lay.setSpacing(10)

        try:
            s = QSettings("NetSentinel", "NetSentinel")
            history = _json.loads(s.value("diagnosis/history", "[]"))
        except Exception:
            history = []

        if not history:
            lbl = QLabel("No diagnosis runs recorded yet.")
            _s.themed_ss(lbl, "color:{TEXT_MUTED}; font-size:12px;")
            lay.addWidget(lbl)
        else:
            for entry in history:
                sev = entry.get("severity", "INFO")
                color = _sev_color(sev)
                ts = entry.get("ts", 0)
                dt_str = _dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else "–"
                findings = entry.get("findings", [])
                summary = entry.get("summary", "")

                card = QFrame()
                card.setStyleSheet(
                    f"QFrame {{ background:{_s.BG_CARD}; border-left:3px solid {color};"
                    f" border-top:1px solid {_s.BORDER}; border-right:1px solid {_s.BORDER};"
                    f" border-bottom:1px solid {_s.BORDER}; border-radius:3px; }}"
                )
                c_lay = QVBoxLayout(card)
                c_lay.setContentsMargins(12, 8, 12, 8)
                c_lay.setSpacing(4)

                hdr_row = QHBoxLayout()
                sev_lbl = QLabel(sev)
                sev_lbl.setStyleSheet(
                    f"color:{color}; font-weight:bold; font-size:11px;"
                    f" border:1px solid {color}; border-radius:3px; padding:1px 6px;"
                )
                time_lbl = QLabel(dt_str)
                _s.themed_ss(time_lbl, "color:{TEXT_MUTED}; font-size:11px;")
                n_lbl = QLabel(f"{len(findings)} finding{'s' if len(findings) != 1 else ''}")
                _s.themed_ss(n_lbl, "color:{TEXT_SECONDARY}; font-size:11px;")
                hdr_row.addWidget(sev_lbl)
                hdr_row.addWidget(time_lbl)
                hdr_row.addStretch()
                hdr_row.addWidget(n_lbl)
                c_lay.addLayout(hdr_row)

                if summary:
                    sum_lbl = QLabel(summary)
                    sum_lbl.setWordWrap(True)
                    _s.themed_ss(sum_lbl, "color:{TEXT_PRIMARY}; font-size:11px;")
                    c_lay.addWidget(sum_lbl)

                for f in findings[:3]:
                    hl = f.get("headline", "")
                    if hl:
                        f_lbl = QLabel(f"  • {hl}")
                        _s.themed_ss(f_lbl, "color:{TEXT_SECONDARY}; font-size:10px;")
                        c_lay.addWidget(f_lbl)

                lay.addWidget(card)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(self.reject)
        _s.themed_ss(bb, "QPushButton {{ background:{BG_CARD}; color:{TEXT_PRIMARY}; border:1px solid {BORDER};"
            " border-radius:4px; padding:4px 16px; }}"
            "QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}")
        lay.addWidget(bb)
