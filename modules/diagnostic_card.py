"""
Diagnostic card — compact shareable summary of network health.

  CardData          — data contract for the card renderer and HTML generator
  build_card_data() — assembles CardData from existing results; no new scans

The QWidget renderer lives in ui/widgets/diagnostic_card_widget.py (ARCH RULE 1).
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class CardData:
    grade:        str        # "A"–"F" or "N/A"
    score:        float      # 0–100
    isp:          str        # ISP org name, public IP, or "–"
    findings:     List[str]  # exactly 3 plain-English strings
    device_count: int
    generated_at: str        # "YYYY-MM-DD HH:MM"

    def to_dict(self) -> dict:
        return {
            "grade":        self.grade,
            "score":        self.score,
            "isp":          self.isp,
            "findings":     self.findings,
            "device_count": self.device_count,
            "generated_at": self.generated_at,
        }


_KNOWN_RESOLVERS = {"cloudflare", "google", "opendns", "quad9", "level3", "verisign"}


def build_card_data(
    benchmark_result=None,
    diag_result=None,
    store=None,
) -> CardData:
    """
    Assemble CardData from existing in-memory scan results.
    Never triggers a new scan — uses whatever is already available.
    """
    grade = getattr(benchmark_result, "overall_grade", "N/A") if benchmark_result else "N/A"
    score = getattr(benchmark_result, "overall_score", 0.0)  if benchmark_result else 0.0

    # Top 3 findings: worst-scoring dimensions first
    findings: List[str] = []
    if benchmark_result and hasattr(benchmark_result, "dimensions"):
        dims = sorted(benchmark_result.dimensions, key=lambda d: d.score)
        for d in dims[:3]:
            findings.append(d.verdict)
    while len(findings) < 3:
        findings.append("No issues detected")

    # ISP: try DNS leak org entries, skip known public resolvers; fall back to public IP
    isp = "–"
    if diag_result:
        dl = getattr(diag_result, "dns_leak", None)
        if dl:
            for e in getattr(dl, "entries", []):
                org = (e.org or "").strip()
                if org and not any(r in org.lower() for r in _KNOWN_RESOLVERS):
                    isp = org
                    break
        if isp == "–":
            pub = getattr(diag_result, "public_ip", "")
            if pub:
                isp = pub

    device_count = 0
    if store:
        try:
            device_count = len(store.get_known_devices())
        except Exception:
            pass

    return CardData(
        grade=grade,
        score=score,
        isp=isp,
        findings=findings[:3],
        device_count=device_count,
        generated_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
    )
