"""
SnmpTrapWorker — QThread that drives SnmpTrapReceiver (T2#10).

Signals
-------
trap_received(dict)
    Emitted for each decoded trap with keys:
    ts, src_ip, src_port, version, community, trap_oid, trap_type,
    varbinds (list of [oid, value] pairs), raw_error
error(str)
    Emitted on socket bind failure or unhandled exception.
status(str)
    Emitted when the listen port is confirmed (e.g. "Listening on UDP :162").
"""

from __future__ import annotations

import time
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal

from modules.snmp_trap_receiver import SnmpTrap, SnmpTrapReceiver, SNMP_TRAP_PORT


class SnmpTrapWorker(QThread):
    trap_received = pyqtSignal(dict)
    error         = pyqtSignal(str)
    status        = pyqtSignal(str)

    def __init__(
        self,
        port: int = SNMP_TRAP_PORT,
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
        receiver = SnmpTrapReceiver(port=self._port, bind_address=self._bind_address)
        try:
            actual_port = receiver.open()
            self.status.emit(f"Listening on UDP :{actual_port}")
        except OSError as exc:
            self.error.emit(f"Cannot bind UDP port {self._port}: {exc}")
            self._running = False
            return

        try:
            while self._running:
                trap = receiver.receive_one()   # blocks up to 1 s then returns None
                if trap is not None:
                    self.trap_received.emit(_trap_to_dict(trap))
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            receiver.close()


def _trap_to_dict(trap: SnmpTrap) -> dict:
    return {
        "ts":         trap.ts,
        "src_ip":     trap.src_ip,
        "src_port":   trap.src_port,
        "version":    trap.version,
        "community":  trap.community,
        "trap_oid":   trap.trap_oid,
        "trap_type":  trap.trap_type,
        "varbinds":   [[oid, val] for oid, val in trap.varbinds],
        "raw_error":  trap.raw_error,
    }
