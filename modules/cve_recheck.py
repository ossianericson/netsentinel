"""
cve_recheck — scheduled CVE re-check for already-fingerprinted services
(V6 Sprint 3.2).

Re-runs modules.cve_lookup.lookup() for every distinct (host, service) pair
already present in the cve_lifecycle table (populated by a prior manual CVE
Lookup scan) and reports any CVE that was not previously tracked for that
pair.

Architecture rules observed:
  • Pure Python — no PyQt6, no ui/ imports (ARCH RULE 3).
  • MetricStore injected at call time — never instantiated here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Set, Tuple

from modules import cve_lookup
from modules.cve_lookup import CVEResult
from modules.metric_store import MetricStore


@dataclass
class CveRecheckReport:
    """Result of one scheduled CVE re-check run."""
    new_cves: List[Tuple[str, str, CVEResult]] = field(default_factory=list)   # (host, service, cve)


def run_cve_recheck(store: MetricStore) -> CveRecheckReport:
    """
    Re-check CVEs for every (host, service) pair already tracked in
    cve_lifecycle. Persists and reports only newly discovered CVE ids.
    """
    tracked = store.list_cve_lifecycles()
    pairs: Set[Tuple[str, str]] = {(r["host"], r["service"]) for r in tracked}
    known_ids: Set[Tuple[str, str, str]] = {(r["host"], r["service"], r["cve_id"]) for r in tracked}

    new_cves: List[Tuple[str, str, CVEResult]] = []
    for host, service in sorted(pairs):
        result = cve_lookup.lookup(service)
        for cve in result.cves:
            if (host, service, cve.cve_id) in known_ids:
                continue
            store.upsert_cve_lifecycle(
                cve_id=cve.cve_id,
                service=service,
                host=host,
                cvss_score=cve.cvss_score,
                severity=cve.severity,
                description=cve.description,
            )
            new_cves.append((host, service, cve))

    return CveRecheckReport(new_cves=new_cves)
