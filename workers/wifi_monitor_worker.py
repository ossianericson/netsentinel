"""
WiFiMonitorWorker — QThread that puts a NIC into monitor mode via Npcap
and captures raw 802.11 management/probe/beacon frames.

Falls back silently (unsupported signal) if the adapter or Npcap
installation does not support monitor mode.

Signals
-------
frame_captured(dict)
    Emitted per frame. Keys: ts, frame_type, src, dst, ssid
error(str)
    Emitted on unrecoverable failure (e.g. scapy missing, no interfaces).
status(str)
    Emitted with human-readable state changes.
unsupported(str)
    Emitted when monitor mode is unavailable on the selected interface.
    The caller should surface this as a soft warning, not an error.
"""
from __future__ import annotations

import time

from PyQt6.QtCore import QThread, pyqtSignal


class WiFiMonitorWorker(QThread):
    frame_captured = pyqtSignal(dict)
    error          = pyqtSignal(str)
    status         = pyqtSignal(str)
    unsupported    = pyqtSignal(str)

    def __init__(self, iface: str = "", parent=None):
        super().__init__(parent)
        self._iface   = iface
        self._running = False

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        self._running = True
        try:
            import scapy.all as scapy
            from scapy.layers.dot11 import (
                Dot11, Dot11Beacon, Dot11ProbeReq, Dot11ProbeResp,
                Dot11Auth, Dot11AssoReq, Dot11AssoResp, Dot11Deauth, Dot11Elt,
            )
        except ImportError as exc:
            self.error.emit(f"scapy is not installed: {exc}")
            return

        iface = self._iface or self._pick_iface(scapy)
        if not iface:
            self.error.emit("No wireless interface found.")
            return

        self.status.emit(f"Starting monitor mode on {iface}…")

        def _on_packet(pkt):
            if not self._running:
                return
            if not pkt.haslayer(Dot11):
                return
            dot11 = pkt[Dot11]
            frame_type = _classify(pkt)
            ssid = ""
            if pkt.haslayer(Dot11Elt):
                try:
                    elt = pkt[Dot11Elt]
                    while elt and hasattr(elt, "ID"):
                        if elt.ID == 0:
                            raw = getattr(elt, "info", b"")
                            ssid = raw.decode("utf-8", errors="replace").strip("\x00")
                            break
                        elt = elt.payload if hasattr(elt, "payload") and elt.payload else None
                except Exception:
                    pass
            self.frame_captured.emit({
                "ts":         time.strftime("%H:%M:%S"),
                "frame_type": frame_type,
                "src":        dot11.addr2 or "—",
                "dst":        dot11.addr1 or "—",
                "ssid":       ssid,
            })

        def _classify(pkt) -> str:
            if pkt.haslayer(Dot11Beacon):    return "Beacon"
            if pkt.haslayer(Dot11ProbeReq):  return "Probe Request"
            if pkt.haslayer(Dot11ProbeResp): return "Probe Response"
            if pkt.haslayer(Dot11Auth):      return "Auth"
            if pkt.haslayer(Dot11AssoReq):   return "Association Req"
            if pkt.haslayer(Dot11AssoResp):  return "Association Resp"
            if pkt.haslayer(Dot11Deauth):    return "Deauth"
            dot11 = pkt.getlayer(Dot11)
            return f"Type {dot11.type}/{dot11.subtype}" if dot11 else "Unknown"

        try:
            scapy.sniff(
                iface=iface,
                monitor=True,
                prn=_on_packet,
                stop_filter=lambda _: not self._running,
                store=False,
            )
            self.status.emit("Capture stopped.")
        except OSError as exc:
            msg = str(exc)
            low = msg.lower()
            if any(k in low for k in ("monitor", "not supported", "permission", "adapter", "mode")):
                self.unsupported.emit(
                    f"Monitor mode unavailable on {iface}: {msg}. "
                    "Ensure Npcap is installed with WinPcap-compatible mode and the "
                    "adapter supports 802.11 monitor mode."
                )
            else:
                self.error.emit(f"Capture failed on {iface}: {msg}")
        except Exception as exc:
            self.error.emit(f"Capture error: {exc}")

    @staticmethod
    def _pick_iface(scapy) -> str:
        try:
            ifaces = scapy.get_if_list()
            for iface in ifaces:
                low = iface.lower()
                if any(k in low for k in ("wi-fi", "wifi", "wlan", "wireless", "802.11")):
                    return iface
            return ifaces[0] if ifaces else ""
        except Exception:
            return ""

    @staticmethod
    def list_interfaces() -> list[str]:
        try:
            import scapy.all as scapy
            return scapy.get_if_list()
        except Exception:
            return []
