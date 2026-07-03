"""
tabs_analysis_isp.py — _AnalysisIspMixin: ISP Accountability Report export,
email complaint copy, and forum (Reddit) post copy for the Network Grade page.

Extracted from ui/tabs_analysis.py to keep that file within its LOC budget
(RULE-AH1). Dashboard inherits _AnalysisIspMixin via TabBuilderMixin.

Requires the host Dashboard to provide: self._m1_result, self._diag_result,
self._bm_stack, self._bm_verdict_label, self._pending_isp_report,
self._logger_worker, self._last_benchmark_result, and self._start_diagnostics().
"""
from __future__ import annotations

import datetime
import webbrowser
from pathlib import Path

from PyQt6.QtCore import pyqtSlot
from PyQt6.QtWidgets import QFileDialog

from ui.styles import BG_CARD, BG_DARK, BORDER, TEXT_PRIMARY


class _AnalysisIspMixin:
    """ISP report / complaint / forum-post handlers for the benchmark tab."""

    @pyqtSlot()
    def _export_isp_report(self):
        if self._m1_result is None and getattr(self, "_diag_result", None) is None:
            self._bm_stack.setCurrentIndex(1)
            self._bm_verdict_label.setText("Running diagnostics to build the ISP report…")
            self._pending_isp_report = True
            self._start_diagnostics()
            return

        try:
            from modules.report_exporter import save_isp_report
            from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLineEdit as _QLE

            # Collect optional ISP name & account ref from user
            dlg = QDialog(self)
            dlg.setWindowTitle("Network Health Report — Optional Details")
            dlg.setMinimumWidth(380)
            dlg.setStyleSheet(f"background:{BG_DARK}; color:{TEXT_PRIMARY};")
            form = QFormLayout(dlg)
            isp_edit = _QLE()
            isp_edit.setPlaceholderText("e.g. BT, Virgin Media, Comcast…")
            isp_edit.setStyleSheet(f"background:{BG_CARD}; color:{TEXT_PRIMARY}; border:1px solid {BORDER}; border-radius:4px; padding:4px;")
            ref_edit = _QLE()
            ref_edit.setPlaceholderText("e.g. REF-123456 (optional)")
            ref_edit.setStyleSheet(f"background:{BG_CARD}; color:{TEXT_PRIMARY}; border:1px solid {BORDER}; border-radius:4px; padding:4px;")
            form.addRow("ISP Name:", isp_edit)
            form.addRow("Account / Ticket Ref:", ref_edit)
            btns = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
            )
            btns.accepted.connect(dlg.accept)
            btns.rejected.connect(dlg.reject)
            form.addRow(btns)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return

            isp_name   = isp_edit.text().strip()
            account_ref = ref_edit.text().strip()

            # Gather data
            log_summary = None
            if self._logger_worker:
                try:
                    log_summary = self._logger_worker.get_summary()
                except Exception:
                    pass  # non-fatal — logger worker may be unavailable
            bm_result = getattr(self, "_last_benchmark_result", None)

            # Pick save path
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            default_name = f"ISP_Report_{ts}.html"
            docs_dir = Path.home() / "Documents" / "NetSentinel" / "reports"
            docs_dir.mkdir(parents=True, exist_ok=True)
            path_str, _ = QFileDialog.getSaveFileName(
                self, "Save Network Health Report", str(docs_dir / default_name),
                "HTML Report (*.html);;All Files (*)",
                options=QFileDialog.Option.DontUseNativeDialog,
            )
            if not path_str:
                return

            out = save_isp_report(
                output_path=Path(path_str),
                log_summary=log_summary,
                diag_result=self._diag_result,
                benchmark_result=bm_result,
                m1_result=self._m1_result,
                isp_name=isp_name,
                account_ref=account_ref,
            )
            webbrowser.open(out.as_uri())
        except Exception as exc:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Network Health Report Error", str(exc))

    @pyqtSlot()
    def _copy_isp_complaint(self):
        """Copy a ready-to-email ISP complaint script using NetSentinel's own measurements."""
        try:
            from PyQt6.QtWidgets import (
                QCheckBox as _QCB, QDialog, QDialogButtonBox,
                QFormLayout, QLineEdit as _QLE,
            )
            from modules.report_isp import generate_isp_complaint_text

            dlg = QDialog(self)
            dlg.setWindowTitle("Copy ISP Complaint — Details")
            dlg.setMinimumWidth(400)
            dlg.setStyleSheet(f"background:{BG_DARK}; color:{TEXT_PRIMARY};")
            form = QFormLayout(dlg)

            isp_edit = _QLE()
            isp_edit.setPlaceholderText("e.g. BT, Virgin Media, Comcast…")
            isp_edit.setStyleSheet(
                f"background:{BG_CARD}; color:{TEXT_PRIMARY}; border:1px solid {BORDER};"
                f" border-radius:4px; padding:4px;"
            )
            ref_edit = _QLE()
            ref_edit.setPlaceholderText("e.g. REF-123456 (optional)")
            ref_edit.setStyleSheet(
                f"background:{BG_CARD}; color:{TEXT_PRIMARY}; border:1px solid {BORDER};"
                f" border-radius:4px; padding:4px;"
            )
            legal_chk = _QCB("Include UK/EU SLA legal statement (Ofcom / Consumer Rights Act)")
            legal_chk.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:11px;")

            form.addRow("ISP Name:", isp_edit)
            form.addRow("Account / Ticket Ref:", ref_edit)
            form.addRow("", legal_chk)

            btns = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
            )
            btns.accepted.connect(dlg.accept)
            btns.rejected.connect(dlg.reject)
            form.addRow(btns)

            if dlg.exec() != QDialog.DialogCode.Accepted:
                return

            log_summary = None
            if self._logger_worker:
                try:
                    log_summary = self._logger_worker.get_summary()
                except Exception:
                    pass  # non-fatal — logger worker may be unavailable
            bm_result = getattr(self, "_last_benchmark_result", None)

            text = generate_isp_complaint_text(
                log_summary=log_summary,
                diag_result=getattr(self, "_diag_result", None),
                benchmark_result=bm_result,
                isp_name=isp_edit.text().strip(),
                account_ref=ref_edit.text().strip(),
                include_legal=legal_chk.isChecked(),
            )
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(text)
            from ui.widgets.toast import ToastManager
            ToastManager.instance().show_toast("ISP complaint copied to clipboard", "info")
        except Exception as exc:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Copy Failed", str(exc))

    @pyqtSlot()
    def _copy_isp_reddit_post(self):
        """Copy a sanitized, forum-ready Markdown post presenting ISP evidence.
        Reuses the same measurements as the complaint email; the public WAN IP
        is never included (modules/forum_export + report_sanitizer)."""
        try:
            from modules.forum_export import build_isp_forum_markdown
            log_summary = None
            if self._logger_worker:
                try:
                    log_summary = self._logger_worker.get_summary()
                except Exception:
                    pass  # non-fatal — logger worker may be unavailable
            md = build_isp_forum_markdown(
                log_summary=log_summary,
                diag_result=getattr(self, "_diag_result", None),
                benchmark_result=getattr(self, "_last_benchmark_result", None),
            )
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(md)
            from ui.widgets.toast import ToastManager
            ToastManager.show("Reddit post copied — sanitized and safe to paste", "success")
        except Exception as exc:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Copy Failed", str(exc))
