"""
FirewallWorker — one-shot QThread that runs a single Windows Firewall
(netsh) operation off the GUI thread.

Moves the blocking modules.firewall_control subprocess calls out of
ui/pages/connections_page.py (RULE 4). One worker, three ops:

    op="block"   — requires exe_path, exe_name
    op="unblock" — requires exe_name
    op="list"    — no extra args

Emits result_ready(dict):
    {"op": ..., "ok": ..., "message": ..., "rules": [...]}
"rules" is populated only for op="list"; "ok"/"message" only for
op="block"/"unblock".
"""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal

from workers.base_worker import BaseWorker


class FirewallWorker(BaseWorker):
    """Run one block/unblock/list netsh operation, emit result_ready(dict)."""

    result_ready = pyqtSignal(dict)

    def __init__(
        self,
        op: str,
        exe_path: str = "",
        exe_name: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._op       = op
        self._exe_path = exe_path
        self._exe_name = exe_name

    def work(self) -> None:
        from modules import firewall_control

        if self._op == "block":
            ok, msg = firewall_control.block_process(self._exe_path, self._exe_name)
            self.result_ready.emit({"op": "block", "ok": ok, "message": msg})
        elif self._op == "unblock":
            ok, msg = firewall_control.unblock_process(self._exe_name)
            self.result_ready.emit({"op": "unblock", "ok": ok, "message": msg})
        elif self._op == "list":
            rules = firewall_control.get_blocked_rules()
            self.result_ready.emit({"op": "list", "rules": rules})
        else:
            raise ValueError(f"Unknown FirewallWorker op: {self._op!r}")
