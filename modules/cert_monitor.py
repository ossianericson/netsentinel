"""
CertMonitor — scheduled TLS certificate expiry checker (T2#6).

Iterates a list of CertTarget hosts, calls tls_checker.check_host_certs(),
and persists results to MetricStore.

Architecture rules observed:
  • Pure Python — no PyQt6, no ui/ imports (ARCH RULE 3).
  • MetricStore injected as constructor parameter.
  • All cert check I/O is in run_check(); callers decide scheduling.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional

from modules.tls_checker import CertInfo, check_host_certs
from modules.metric_store import MetricStore


@dataclass
class CertTarget:
    """Configuration for a single TLS cert check target."""
    host:  str
    ports: List[int] = field(default_factory=lambda: [443])
    label: str = ""


class CertMonitor:
    """
    Runs TLS certificate checks for a list of CertTarget hosts and persists
    results to the MetricStore.

    Parameters
    ----------
    store : MetricStore
        Injected MetricStore singleton.
    targets : list[CertTarget]
        Hosts (and ports) to check.
    on_result : callable | None
        Called synchronously with the full list of CertInfo after each run.
        Keep it fast — it runs on the caller's thread.
    """

    def __init__(
        self,
        store: MetricStore,
        targets: Optional[List[CertTarget]] = None,
        on_result: Optional[Callable[[List[CertInfo]], None]] = None,
    ):
        self._store     = store
        self._targets   = list(targets or [])
        self._on_result = on_result

    # ── Public API ────────────────────────────────────────────────────────────

    def set_targets(self, targets: List[CertTarget]) -> None:
        self._targets = list(targets)

    def get_targets(self) -> List[CertTarget]:
        return list(self._targets)

    def run_check(self) -> List[CertInfo]:
        """
        Check all configured targets.  Persists each result to MetricStore.
        Returns the full list of CertInfo objects (one per host:port checked).
        """
        results: List[CertInfo] = []
        for target in self._targets:
            try:
                infos = check_host_certs(target.host, target.ports)
            except Exception as exc:  # noqa: BLE001 — surface as error CertInfo
                infos = [CertInfo(host=target.host, port=p,
                                  error=str(exc))
                         for p in target.ports]
            for info in infos:
                self._store.record_cert_check(
                    host=info.host,
                    port=info.port,
                    days_remaining=info.days_remaining if not info.error else None,
                    subject=info.subject or None,
                    issuer=info.issuer or None,
                    not_after=info.not_after or None,
                    is_expired=bool(info.is_expired),
                    is_self_signed=bool(info.is_self_signed),
                    error=info.error or None,
                )
            results.extend(infos)

        if self._on_result:
            self._on_result(results)

        return results
