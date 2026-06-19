"""
SyslogWorker — QThread that drives SyslogReceiver (T3#14).

Signals
-------
message_received(dict)
    Emitted for each decoded syslog message with keys:
    ts, src_ip, src_port, facility, facility_name, severity, severity_name,
    hostname, app_name, procid, message, raw, raw_error
error(str)
    Emitted on socket bind failure or unhandled exception.
status(str)
    Emitted when the listen port is confirmed (e.g. "Listening on UDP :514").
"""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from modules.syslog_receiver import SyslogMessage, SyslogReceiver, SYSLOG_PORT


class SyslogWorker(QThread):
    message_received = pyqtSignal(dict)
    error            = pyqtSignal(str)
    status           = pyqtSignal(str)

    def __init__(
        self,
        port: int = SYSLOG_PORT,
        bind_address: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self._port         = port
        self._bind_address = bind_address
        self._running      = False

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        self._running = True
        receiver = SyslogReceiver(port=self._port, bind_address=self._bind_address)
        try:
            actual_port = receiver.open()
            self.status.emit(f"Listening on UDP :{actual_port}")
        except OSError as exc:
            self.error.emit(f"Cannot bind syslog UDP port {self._port}: {exc}")
            self._running = False
            return

        try:
            while self._running:
                msg = receiver.receive_one()   # blocks up to 1 s, returns None on timeout
                if msg is not None:
                    self.message_received.emit(_msg_to_dict(msg))
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            receiver.close()


def _msg_to_dict(msg: SyslogMessage) -> dict:
    return {
        "ts":            msg.ts,
        "src_ip":        msg.src_ip,
        "src_port":      msg.src_port,
        "facility":      msg.facility,
        "facility_name": msg.facility_name,
        "severity":      msg.severity,
        "severity_name": msg.severity_name,
        "hostname":      msg.hostname,
        "app_name":      msg.app_name,
        "procid":        msg.procid,
        "message":       msg.message,
        "raw":           msg.raw,
        "raw_error":     msg.raw_error,
    }
