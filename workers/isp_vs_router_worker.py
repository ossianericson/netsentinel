"""
workers/isp_vs_router_worker.py — QThread wrapper for isp_vs_router_test.
"""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from modules.isp_vs_router_test import IspVsRouterResult, run_isp_vs_router_test


class IspVsRouterWorker(QThread):
    """Run the 5-hop ISP-vs-router test off the main thread."""

    result_ready = pyqtSignal(object)  # IspVsRouterResult
    error        = pyqtSignal(str)
    progress     = pyqtSignal(str)

    def __init__(
        self,
        gateway_ip: str | None = None,
        isp_dns_ip: str | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._gateway_ip = gateway_ip
        self._isp_dns_ip = isp_dns_ip

    def run(self) -> None:
        try:
            result: IspVsRouterResult = run_isp_vs_router_test(
                gateway_ip=self._gateway_ip,
                isp_dns_ip=self._isp_dns_ip,
                progress_cb=lambda msg: self.progress.emit(msg),
            )
            self.result_ready.emit(result)
        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))

    def stop(self) -> None:
        self.requestInterruption()
        self.wait(3000)
