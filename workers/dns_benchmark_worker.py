"""
DnsBenchmarkWorker — QThread wrapper for network_diagnostics.run_dns_benchmark() (F-23).

Runs once and emits its result — the DNS & Stability page's "DNS Benchmark" tab
starts one of these each time the user clicks "Run Benchmark".

Signals
-------
result(list)   — list of DnsResult (network_diagnostics.DnsResult)
error(str)     — inherited from BaseWorker

Usage
-----
    worker = DnsBenchmarkWorker()
    worker.result.connect(my_page.on_dns_benchmark_result)
    worker.start()
"""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal

from workers.base_worker import BaseWorker


class DnsBenchmarkWorker(BaseWorker):
    """One-shot QThread that compares DNS resolver latency."""

    result = pyqtSignal(list)   # list of DnsResult

    def work(self) -> None:
        from modules.network_diagnostics import run_dns_benchmark
        data = run_dns_benchmark()
        self.result.emit(data)
