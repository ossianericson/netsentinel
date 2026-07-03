"""
Shared data types for the Root Cause Correlator family.

Extracted from modules/root_cause_correlator.py to break the import cycle
with modules/root_cause_correlator_alerts.py (both files need these types;
neither should import the other's module).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


# ── Score constants (re-used from risk_scorer semantics) ─────────────────────
CRITICAL = "CRITICAL"
HIGH     = "HIGH"
MEDIUM   = "MEDIUM"
LOW      = "LOW"
INFO     = "INFO"


@dataclass
class CorrelatedFinding:
    source: str          # e.g. "ISP Check", "Storm Analyser", "STP Detector"
    category: str        # e.g. "External ISP Issue", "Rogue IoT Broadcaster", …
    severity: str        # CRITICAL / HIGH / MEDIUM / LOW / INFO
    headline: str        # one-line plain-English summary
    detail: str          # longer explanation
    remediation: str     # plain-English fix — written for a home user
    verify_step: str = ""  # "To confirm this is fixed: [step]" — shown below remediation


@dataclass
class CorrelationResult:
    findings: List[CorrelatedFinding] = field(default_factory=list)
    global_severity: str = INFO
    plain_summary: str = ""          # 1-2 sentences for the verdict panel
    isp_issue_detected: bool = False
    local_issue_detected: bool = False
    suppress_local_alerts: bool = False  # True when ISP is clearly to blame
    # Real measurements for share/export features — ping_ms/jitter_ms/loss_pct/
    # dns_ms/download_mbps, whichever are available. Empty dict when no source
    # data was supplied to correlate().
    metrics: dict = field(default_factory=dict)

    @property
    def finding_count(self) -> int:
        return len(self.findings)
