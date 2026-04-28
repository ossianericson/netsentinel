"""
threat_intel_worker.py — QThread workers for threat intelligence operations.

Two workers:
  ThreatFeedRefreshWorker  — downloads OSINT feeds and builds ThreatIntelDB
  AbuseIpDbWorker          — single-IP AbuseIPDB lookup (consent-gated)
"""

from __future__ import annotations

from typing import List, Optional
from PyQt6.QtCore import QThread, pyqtSignal

from modules.threat_intel import (
    AbuseIpDbResult,
    ThreatEntry,
    ThreatIntelDB,
    lookup_abuseipdb,
    refresh_from_feeds,
)


class ThreatFeedRefreshWorker(QThread):
    """
    Downloads all configured threat feeds, parses them, and emits a built
    ThreatIntelDB ready for the UI to use.

    Signals:
        progress(str)             — status message during download
        result_ready(ThreatIntelDB) — emitted when the DB is built
        error(str)                — emitted on unrecoverable failure
    """

    progress:     pyqtSignal = pyqtSignal(str)
    result_ready: pyqtSignal = pyqtSignal(object)
    error:        pyqtSignal = pyqtSignal(str)

    def run(self) -> None:
        try:
            entries: List[ThreatEntry] = refresh_from_feeds(
                progress_cb=self.progress.emit
            )
            db = ThreatIntelDB.from_entries(entries)
            self.result_ready.emit(db)
        except Exception as exc:
            self.error.emit(str(exc))


class AbuseIpDbWorker(QThread):
    """
    Looks up a single IP address against AbuseIPDB.

    Only queries public IPs (private/loopback silently skipped).
    Caller is responsible for ensuring the user has given explicit consent.

    Signals:
        result_ready(AbuseIpDbResult)  — emitted on success
        no_result(str)                 — emitted when IP is private or lookup returned nothing
        error(str)                     — emitted on network failure
    """

    result_ready: pyqtSignal = pyqtSignal(object)
    no_result:    pyqtSignal = pyqtSignal(str)
    error:        pyqtSignal = pyqtSignal(str)

    def __init__(self, ip: str, api_key: str, parent=None):
        super().__init__(parent)
        self._ip      = ip
        self._api_key = api_key

    def run(self) -> None:
        try:
            result: Optional[AbuseIpDbResult] = lookup_abuseipdb(
                self._ip, self._api_key
            )
            if result is None:
                self.no_result.emit(
                    f"{self._ip} is a private/local address or lookup returned no data."
                )
            else:
                self.result_ready.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))
