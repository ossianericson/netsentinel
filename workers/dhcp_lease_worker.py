"""
dhcp_lease_worker.py — QThread worker for DHCP lease scanning.
"""

from __future__ import annotations

import concurrent.futures
from typing import List

from PyQt6.QtCore import pyqtSignal

from modules.dhcp_lease_scanner import DhcpLease, scan as _scan
from workers.base_worker import BaseWorker


class DhcpLeaseWorker(BaseWorker):
    """
    Runs dhcp_lease_scanner.scan() off the main thread.

    Signals:
        result_ready(list)  — emits the list of DhcpLease objects
        error(str)          — inherited from BaseWorker
    """

    result_ready: pyqtSignal = pyqtSignal(list)

    def work(self) -> None:
        leases: List[DhcpLease] = _scan()
        _enrich_missing_hostnames(leases)
        self.result_ready.emit(leases)


def _enrich_missing_hostnames(leases: List[DhcpLease], timeout: float = 6.0) -> None:
    """Fill in hostname="" leases via name_resolver (NetBIOS/mDNS/rDNS).

    dhcp_lease_scanner.py deliberately stays scoped to lease-file/ARP
    parsing (see its module docstring) — the Windows ARP-cache path and
    the Linux nmcli path have no hostname info at all, so this worker
    layer enriches them the same way other scan results are enriched
    (RULE-DW4).

    Bounded by an overall timeout: resolve_batch() does real NetBIOS/mDNS/
    rDNS network lookups whose total time scales with lease count, so a
    large ARP table must not block this one-shot worker indefinitely —
    a slow/incomplete batch just leaves the remaining hostnames blank
    (no worse than before this enrichment existed).
    """
    missing = [lease for lease in leases if not lease.hostname]
    if not missing:
        return
    from modules.name_resolver import resolve_batch
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = pool.submit(resolve_batch, missing, use_dhcp=False)
    try:
        resolved = future.result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        return  # non-fatal — batch is slow; leave remaining hostnames blank this cycle
    finally:
        pool.shutdown(wait=False)
    for lease in missing:
        name = resolved.get(lease.ip)
        if name and name.display_name and name.source != "ip-fallback":
            lease.hostname = name.display_name
