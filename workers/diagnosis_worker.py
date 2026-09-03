"""Orchestrates all detection modules for one-click 'What's Wrong?' diagnosis."""

from __future__ import annotations

import logging
import threading
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal

from modules.utils import get_offenders_path

log = logging.getLogger(__name__)


_DIAG_STEP_CATEGORIES = frozenset({
    "DNS Resolution Failure", "DNS Leak Detected", "Very Low Download Speed",
    "Local Network / Router Unreachable", "External ISP Issue",
    "Chronic Connectivity Loss", "High Jitter — Unstable Latency",
})
_STORM_STEP_CATEGORIES = frozenset({
    "Broadcast Storm", "Degraded IoT Device — Excessive Broadcasting",
    "High Jitter — Unstable Latency",
})
_STP_STEP_CATEGORIES = frozenset({
    "Rogue Network Bridge",
})


class DiagnosisWorker(QThread):
    """Runs all detection modules sequentially, skipping any that fail."""

    progress = pyqtSignal(int, str)  # (0–100, step label)
    finished = pyqtSignal(object)    # CorrelationResult | None (None = cancelled/error)

    def __init__(
        self,
        gateway_ip: Optional[str] = None,
        gateway_mac: Optional[str] = None,
        symptom: str = "",
        focused_on: Optional[str] = None,
        store=None,
        parent=None,
    ):
        super().__init__(parent)
        self._gateway_ip  = gateway_ip
        self._gateway_mac = gateway_mac
        self._symptom     = symptom      # "slow" | "dropping" | "noconn" | ""
        self._focused_on  = focused_on   # category name → run only relevant steps
        self._store       = store        # MetricStore — optional, for recent_alerts (V6 5.1)
        self._stop        = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        # Thin wrapper: the body guards each diagnostic step individually, but the
        # progress/finished emits between steps are unguarded, and an escape from
        # run() is routed through sys.excepthook on this worker thread. finished
        # already carries None for "cancelled or error", so consumers need no change.
        try:
            self._run_body()
        except Exception:
            log.exception("Diagnosis worker failed")
            self.finished.emit(None)

    def _run_body(self) -> None:
        from modules.root_cause_correlator import correlate

        # Focused mode: only run steps relevant to the named finding category.
        # Used by the "Verify this fix" button to do a fast re-check.
        if self._focused_on:
            _run_diag  = self._focused_on in _DIAG_STEP_CATEGORIES
            _run_storm = self._focused_on in _STORM_STEP_CATEGORIES
            _run_stp   = self._focused_on in _STP_STEP_CATEGORIES
        else:
            # Symptom routing: skip steps that can't explain the reported symptom.
            # "noconn" → gateway/DNS are the priority; storm/STP are secondary noise.
            # "slow"   → diagnostics + storm matter; STP loops are less likely.
            # "dropping" → all steps relevant; STP/storm are primary suspects.
            # ""       → run everything (default / command-palette entry).
            _run_diag  = True
            _run_storm = self._symptom in ("dropping", "slow", "")
            _run_stp   = self._symptom in ("dropping", "")

        diag_result: object          = None
        storm_result: object         = None
        stp_bpdus: list              = []
        fingerprint_devices: list    = []

        # ── Step 1: Network diagnostics (~15 s) ───────────────────────────────
        if _run_diag:
            self.progress.emit(5, "Checking your router…")
            try:
                from modules import network_diagnostics
                diag_result = network_diagnostics.scan(
                    gateway_ip=self._gateway_ip,
                    progress_cb=lambda msg: self.progress.emit(20, msg),
                    stop_event=self._stop,
                )
            except Exception:
                log.exception("diagnosis: network_diagnostics failed, skipping")
            if self._stop.is_set():
                self.finished.emit(None)
                return

        # ── Step 2: Broadcast storm analysis (~6 s) — skipped for "noconn" ───
        if _run_storm:
            self.progress.emit(55, "Scanning for broadcast problems…")
            try:
                from modules import storm_analyser
                storm_result = storm_analyser.scan(duration=6)
            except Exception:
                log.exception("diagnosis: storm_analyser failed, skipping")
            if self._stop.is_set():
                self.finished.emit(None)
                return

        # ── Step 3: Rogue device fingerprint (fast ARP scan) ──────────────────
        self.progress.emit(65, "Scanning for problem devices…")
        try:
            from modules import rogue_device
            rd_result = rogue_device.scan(get_offenders_path())
            fingerprint_devices = rd_result.get("devices", [])
        except Exception:
            log.exception("diagnosis: rogue_device failed, skipping")
        if self._stop.is_set():
            self.finished.emit(None)
            return

        # ── Step 4: STP / rogue bridge detection (~6 s) — skipped for "slow" / "noconn"
        if _run_stp:
            self.progress.emit(75, "Listening for network loops…")
            try:
                from modules import stp_detector
                stp_detector.scan(
                    gateway_mac=self._gateway_mac,
                    on_bpdu=stp_bpdus.append,
                    on_error=lambda msg: log.warning("stp_detector: %s", msg),
                    duration=6,
                    stop_event=self._stop,
                )
            except Exception:
                log.exception("diagnosis: stp_detector failed, skipping")
            if self._stop.is_set():
                self.finished.emit(None)
                return

        # ── Step 5: Correlate all findings ────────────────────────────────────
        self.progress.emit(95, "Putting it all together…")
        recent_alerts: Optional[list] = None
        if self._store is not None:
            try:
                recent_alerts = self._store.get_recent_alerts(hours=24.0, limit=200)
            except Exception:
                recent_alerts = None  # non-fatal — recent-alert correlation is best-effort
        try:
            result = correlate(
                diag_result=diag_result,
                storm_result=storm_result,
                stp_bpdus=stp_bpdus or None,
                fingerprint_devices=fingerprint_devices or None,
                gateway_mac=self._gateway_mac,
                recent_alerts=recent_alerts,
            )
        except Exception:
            log.exception("diagnosis: correlate failed")
            self.finished.emit(None)
            return

        self.finished.emit(result)
