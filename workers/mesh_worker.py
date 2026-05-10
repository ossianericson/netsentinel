"""
Generic mesh enrichment worker.

Currently wraps DecoMeshClient (TP-Link Deco).  To add a new provider:
  1. Create modules/<brand>_client.py with the same MeshUnit / MeshClient /
     detect_<brand> surface as deco_client.py.
  2. Add a branch in MeshWorker.run() keyed on the new provider string.

Result dict emitted on success:
    {
        "provider": "deco",
        "host":     "192.168.68.1",
        "units":    List[MeshUnit],
        "clients":  List[MeshClient],
    }
"""

from PyQt6.QtCore import QThread, pyqtSignal


class MeshWorker(QThread):
    result = pyqtSignal(dict)   # see module docstring for shape
    error  = pyqtSignal(str)
    status = pyqtSignal(str)

    def __init__(self, host: str, password: str,
                 provider: str = "deco", parent=None) -> None:
        super().__init__(parent)
        self._host     = host
        self._password = password
        self._provider = provider

    def run(self) -> None:
        if self._provider == "deco":
            self._run_deco()
        else:
            self.error.emit(f"Unknown mesh provider: {self._provider!r}")

    # ── providers ─────────────────────────────────────────────────────────────

    def _run_deco(self) -> None:
        from modules.deco_client import DecoMeshClient, MeshAuthError, MeshApiError

        self.status.emit(f"Connecting to Deco at {self._host}…")
        try:
            client = DecoMeshClient(self._host, self._password)
            client.login()

            self.status.emit("Fetching mesh topology…")
            units = client.get_mesh_units()

            self.status.emit(f"Fetching clients ({len(units)} node(s) found)…")
            clients = client.get_all_clients(units=units)

            self.result.emit({
                "provider": "deco",
                "host":     self._host,
                "units":    units,
                "clients":  clients,
            })

        except MeshAuthError as exc:
            self.error.emit(f"Mesh auth failed: {exc}")
        except MeshApiError as exc:
            self.error.emit(f"Mesh API error: {exc}")
        except Exception as exc:
            self.error.emit(f"Mesh enrichment failed: {exc}")
