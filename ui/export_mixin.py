"""
export_mixin.py — _ExportMixin: full-report generation, auto-report,
and Export All Data (zip) handlers for Dashboard.

Extracted from ui/dashboard.py (P7 — dashboard.py diet).
"""
from __future__ import annotations

import datetime
import webbrowser
from pathlib import Path

from PyQt6.QtCore import QSettings, pyqtSlot
from PyQt6.QtWidgets import QFileDialog


class _ExportMixin:
    """Mixin providing report export + "Export All Data" handlers for Dashboard.

    Extracted from ui/dashboard.py (P7 — dashboard.py diet).
    """

    @pyqtSlot()
    def _on_export_all(self) -> None:
        from PyQt6.QtWidgets import QFileDialog as _QFD
        import time as _t
        default = f"netsentinel-export-{_t.strftime('%Y%m%d-%H%M%S')}.zip"
        path, _ = _QFD.getSaveFileName(
            self, "Export All Data", default, "ZIP Archives (*.zip)"
        )
        if not path:
            return
        try:
            from modules.exporter import export_all_zip
            from pathlib import Path as _P
            export_all_zip(self._store, _P(path))
            from ui.widgets.toast import ToastManager
            ToastManager.instance().show_toast(f"Export saved to {path}", "info")
        except Exception as exc:
            from PyQt6.QtWidgets import QMessageBox as _MB
            _MB.warning(self, "Export Failed", str(exc))

    @pyqtSlot()
    def _run_full_report(self):
        """Run all modules + diagnostics, then auto-open the HTML report. No dialogs."""
        if self._active_count > 0:
            self._set_status("Scan already in progress — please wait.")
            return

        # Arm the auto-report flags
        self._auto_report_pending   = True
        self._auto_report_scan_done = False
        # Diagnostics: start them now; mark done immediately if they were already run
        self._auto_report_diag_done = False
        # Force all scan modules on for the full report run
        _rqs = QSettings("NetSentinel", "NetSentinel")
        for _k in ("stp", "storm", "wifi", "dns"):
            _rqs.setValue(f"scan/{_k}_enabled", True)
        if hasattr(self, "_overview_page"):
            self._overview_page.set_report_running(True)

        # Start diagnostics in the background (runs in parallel with the scan)
        if self._diag_worker and self._diag_worker.isRunning():
            self._auto_report_diag_done = True   # already running; result will arrive
        else:
            self._start_diagnostics()

        # Start the full scan (M1–M5 all checked above)
        self._start_full_scan()

    def _maybe_auto_report(self) -> None:
        """Generate and open the report once both scan and diagnostics are done."""
        if not self._auto_report_pending:
            return
        if not (self._auto_report_scan_done and self._auto_report_diag_done):
            return
        self._auto_report_pending   = False
        self._auto_report_scan_done = False
        self._auto_report_diag_done = False
        if hasattr(self, "_overview_page"):
            self._overview_page.set_report_running(False)
        try:
            import datetime as _dt
            from modules.utils import get_app_data_dir
            from modules.report_exporter import save_report
            _ts  = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            _out = get_app_data_dir() / "reports" / f"netsentinel_report_{_ts}.html"
            _out.parent.mkdir(parents=True, exist_ok=True)
            _level = "CLEAN"
            if self._m1_result and self._m1_result.get("high_risk_count", 0):
                _level = "HIGH"
            if self._m2_result and self._m2_result.get("rogue_count", 0):
                _level = "HIGH"
            _verdict = self._verdict._text.text() if hasattr(self._verdict, "_text") else ""
            save_report(
                _out,
                module1_data=self._m1_result,
                module2_data=self._m2_result,
                module3_data=self._m3_result,
                module4_data=self._m4_result,
                module5_data=self._m5_result,
                diagnostics_data=self._diag_result,
                network_info_data=self._net_info if self._net_info else None,
                overall_verdict=_verdict,
                overall_level=_level,
            )
            webbrowser.open(_out.as_uri())
            self._set_status(f"Report ready — {_out.name}")
        except Exception as _exc:
            self._set_status(f"Auto-report failed: {_exc}")
            if hasattr(self, "_overview_page"):
                self._overview_page.set_report_running(False)

    @pyqtSlot()
    def _export_report(self):
        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        default_dir = str(Path.home() / "Desktop")

        path_str, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export Report",
            str(Path(default_dir) / f"netsentinel_report_{ts}.html"),
            "HTML Report (*.html);;JSON Export (*.json);;CSV Device List (*.csv);;Nmap XML (*.xml);;All Files (*)",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if not path_str:
            return

        out = Path(path_str)

        # Determine overall level
        level = "CLEAN"
        if self._m1_result and self._m1_result.get("high_risk_count", 0):
            level = "HIGH"
        if self._m2_result and self._m2_result.get("rogue_count", 0):
            level = "HIGH"
        overall = self._verdict._text.text()

        try:
            suffix = out.suffix.lower()
            if suffix == ".json":
                from modules.report_exporter import save_json_report
                save_json_report(
                    out,
                    module1_data=self._m1_result,
                    module2_data=self._m2_result,
                    module3_data=self._m3_result,
                    module4_data=self._m4_result,
                    module5_data=self._m5_result,
                    diagnostics_data=self._diag_result,
                    network_info_data=self._net_info if self._net_info else None,
                    overall_verdict=overall,
                    overall_level=level,
                )
            elif suffix == ".csv":
                from modules.report_exporter import save_csv_report
                save_csv_report(out, self._m1_result)
            elif suffix == ".xml":
                from modules.report_exporter import save_nmap_xml_report
                ps_result = getattr(self, "_last_portscan_result", None)
                save_nmap_xml_report(out, self._m1_result, ps_result)
            else:
                from modules.report_exporter import save_report
                save_report(
                    out,
                    module1_data=self._m1_result,
                    module2_data=self._m2_result,
                    module3_data=self._m3_result,
                    module4_data=self._m4_result,
                    module5_data=self._m5_result,
                    diagnostics_data=self._diag_result,
                    network_info_data=self._net_info if self._net_info else None,
                    overall_verdict=overall,
                    overall_level=level,
                )
                webbrowser.open(out.as_uri())
            self._set_status(f"Report saved: {out.name}")
        except Exception as exc:
            self._set_status(f"Export failed: {exc}")
