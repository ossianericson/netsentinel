"""
threat_intel_worker.py — QThread workers for threat intelligence operations.

Two workers:
  ThreatFeedRefreshWorker  — downloads OSINT feeds and builds ThreatIntelDB
  AbuseIpDbWorker          — single-IP AbuseIPDB lookup (consent-gated)
"""

from __future__ import annotations

from typing import List, Optional

from PyQt6.QtCore import pyqtSignal

from modules.threat_intel import (
    AbuseIpDbResult,
    AbuseIpDbUnreachableError,
    ThreatEntry,
    ThreatIntelDB,
    lookup_abuseipdb,
    refresh_from_feeds,
)
from workers.base_worker import BaseWorker


class ThreatFeedRefreshWorker(BaseWorker):
    """
    Downloads all configured threat feeds, parses them, and emits a built
    ThreatIntelDB ready for the UI to use.

    Signals:
        progress(str)               — inherited from BaseWorker
        result_ready(ThreatIntelDB) — emitted when the DB is built
        error(str)                  — inherited from BaseWorker
    """

    result_ready: pyqtSignal = pyqtSignal(object)

    def work(self) -> None:
        entries: List[ThreatEntry] = refresh_from_feeds(
            progress_cb=self.progress.emit
        )
        db = ThreatIntelDB.from_entries(entries)
        self.result_ready.emit(db)


class AbuseIpDbWorker(BaseWorker):
    """
    Looks up a single IP address against AbuseIPDB.

    Only queries public IPs (private/loopback silently skipped).
    Caller is responsible for ensuring the user has given explicit consent.

    Signals:
        result_ready(AbuseIpDbResult)  — emitted on success
        no_result(str)                 — emitted when the IP is private or no API key is configured
        not_testable(str)              — emitted when the AbuseIPDB API itself could not be reached
        error(str)                     — inherited from BaseWorker
    """

    result_ready: pyqtSignal = pyqtSignal(object)
    no_result:    pyqtSignal = pyqtSignal(str)
    not_testable: pyqtSignal = pyqtSignal(str)

    def __init__(self, ip: str, api_key: str, parent=None):
        super().__init__(parent)
        self._ip      = ip
        self._api_key = api_key

    def work(self) -> None:
        try:
            result: Optional[AbuseIpDbResult] = lookup_abuseipdb(
                self._ip, self._api_key
            )
        except AbuseIpDbUnreachableError as exc:
            # Distinct from "private IP" / "no API key" below -- the API
            # itself could not be reached, so nothing about this IP was
            # confirmed either way.
            self.not_testable.emit(str(exc))
            return
        if result is None:
            self.no_result.emit(
                f"{self._ip} is a private/local address or no API key is configured."
            )
        else:
            self.result_ready.emit(result)
