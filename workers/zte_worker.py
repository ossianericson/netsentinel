"""
ZTE MC889 modem signal polling worker.

Emits live signal metrics on a fixed interval.  Automatic session renewal is
handled transparently by ZteMC889Client — the caller never manages cookies.

Result dict shape (all fields except ts/host are Optional):
    {
        "ts":               int,          # Unix seconds
        "host":             str,
        "wan_ip":           str | None,
        "wan_status":       str | None,
        "firmware_version": str | None,
        "network_type":     str | None,   # "LTE" | "NR5G" | "ENDC" | …
        "signal_bars":      int | None,
        "mcc":              str | None,
        "mnc":              str | None,
        "cell_id":          str | None,
        "enb_id":           str | None,
        "nr5g_rsrp_dbm":    float | None,
        "nr5g_sinr_db":     float | None,
        "nr5g_rsrq_db":     float | None,
        "nr5g_band":        str | None,
        "nr5g_pci":         str | None,
        "nr5g_arfcn":       str | None,
        "lte_rsrp_dbm":     float | None,
        "lte_snr_db":       float | None,
        "lte_rsrq_db":      float | None,
        "lte_band":         str | None,
        "lte_pci":          str | None,
        "lte_earfcn":       str | None,
        "endc_info":        str | None,
    }
"""

import dataclasses
import time

from PyQt6.QtCore import QThread, pyqtSignal


class ZteWorker(QThread):
    """
    Continuously polls a ZTE MC889 modem for signal metrics.

    Usage
    -----
        worker = ZteWorker("192.168.254.1", password, interval_s=30)
        worker.result.connect(my_slot)
        worker.error.connect(my_error_slot)
        worker.start()
        …
        worker.stop()
        worker.wait()
    """

    result = pyqtSignal(dict)   # see module docstring for shape
    error  = pyqtSignal(str)
    status = pyqtSignal(str)

    def __init__(
        self,
        host:       str,
        password:   str,
        interval_s: int = 30,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._host       = host
        self._password   = password
        self._interval_s = interval_s
        self._stop       = False

    def stop(self) -> None:
        """Request graceful shutdown.  Call wait() afterwards to join the thread."""
        self._stop = True

    def run(self) -> None:
        from modules.zte_client import ZteMC889Client, ZteAuthError, ZteApiError

        self.status.emit(f"Connecting to ZTE MC889 at {self._host}…")
        client = ZteMC889Client(self._host)
        try:
            client.login(self._password)
        except ZteAuthError as exc:
            self.error.emit(str(exc))
            return

        self.status.emit("ZTE authenticated — polling signal metrics…")

        while not self._stop:
            try:
                data = client.get_signal_data()
                payload = dataclasses.asdict(data)
                payload["host"] = self._host
                self.result.emit(payload)

            except ZteAuthError as exc:
                # Two consecutive auth failures — password is wrong or modem reset.
                # Cannot recover without new credentials; stop the loop.
                self.error.emit(f"ZTE auth failed: {exc}")
                return

            except ZteApiError as exc:
                # Session or network hiccup — non-fatal.  The next call to
                # get_signal_data() will attempt a reconnect automatically.
                self.error.emit(f"ZTE fetch failed: {exc}")

            except Exception as exc:
                self.error.emit(f"ZTE unexpected error: {exc}")

            # Interruptible sleep — wakes within 0.5 s of stop() being called
            deadline = time.monotonic() + self._interval_s
            while not self._stop and time.monotonic() < deadline:
                time.sleep(0.5)
