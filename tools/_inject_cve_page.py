"""
One-shot script: inject CvePage into dashboard.py.
Run once, then delete or keep for reference.
"""
import pathlib

src = pathlib.Path(__file__).parent.parent / "ui" / "dashboard.py"
text = src.read_text(encoding="utf-8")
changes = 0

# ── Change 1: instantiate CvePage after ThreatIntelPage ───────────────────────
OLD1 = (
    "        from ui.pages.threat_intel_page import ThreatIntelPage\n"
    "        self._threat_intel_page = ThreatIntelPage(parent=None)\n"
)
NEW1 = (
    "        from ui.pages.threat_intel_page import ThreatIntelPage\n"
    "        self._threat_intel_page = ThreatIntelPage(parent=None)\n"
    "\n"
    "        from ui.pages.cve_page import CvePage\n"
    "        self._cve_page = CvePage(self._store, parent=None)\n"
)
if OLD1 in text:
    text = text.replace(OLD1, NEW1, 1)
    changes += 1
    print("Change 1 applied: CvePage instantiation added")
else:
    print("Change 1 SKIPPED (already applied or source changed)")

# ── Change 2: add CVE Tracker nav entry after "Known CVEs" row ───────────────
# We find the nav_add_page line for "Known CVEs" and insert after it.
# Using a unique enough fragment to locate the line safely.
OLD2 = '"Known CVEs",             self._recon_cve_tab_widget),'
NEW2 = (
    '"Known CVEs",             self._recon_cve_tab_widget),\n'
    "            self._nav_add_page(\"\U0001f4cb\", \"CVE Tracker\",              self._cve_page),"
)
if OLD2 in text and "CVE Tracker" not in text:
    text = text.replace(OLD2, NEW2, 1)
    changes += 1
    print("Change 2 applied: CVE Tracker nav entry added")
else:
    print("Change 2 SKIPPED (already applied or source changed)")

src.write_text(text, encoding="utf-8")
print(f"dashboard.py updated ({changes} change(s) applied)")
