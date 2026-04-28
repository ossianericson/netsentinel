"""
Inject ThreatIntelPage into dashboard.py.

Two changes:
1. Instantiate page after dns_zone_page (line ~799)
2. Register in Security Audit section before the first recon page
"""
import sys

SRC = "ui/dashboard.py"

with open(SRC, "r", encoding="utf-8") as f:
    content = f.read()

# ── Change 1: instantiate page ────────────────────────────────────────────────
OLD1 = (
    "        from ui.pages.dns_zone_page import DnsZonePage\n"
    "        self._dns_zone_page = DnsZonePage(parent=None)\n"
)
NEW1 = OLD1 + (
    "\n"
    "        from ui.pages.threat_intel_page import ThreatIntelPage\n"
    "        self._threat_intel_page = ThreatIntelPage(parent=None)\n"
)

if OLD1 not in content:
    print("ERROR: instantiation anchor not found")
    sys.exit(1)

content = content.replace(OLD1, NEW1, 1)
print("Change 1 applied (page instantiation)")

# ── Change 2: nav registration in Security Audit ──────────────────────────────
# Insert as first item in Security Audit section, before TLS Certificates.
# Anchor: the line starting the recon section pages list.
OLD2 = (
    "        self._nav_recon_rows = [\n"
    "            self._nav_add_page(\"\ufffd\", \"TLS Certificates\","
)
NEW2 = (
    "        self._nav_recon_rows = [\n"
    "            self._nav_add_page(\"\U0001f9e0\", \"Threat Intelligence\",   self._threat_intel_page),\n"
    "            self._nav_add_page(\"\ufffd\", \"TLS Certificates\","
)

if OLD2 not in content:
    print("ERROR: security audit nav anchor not found")
    sys.exit(1)

content = content.replace(OLD2, NEW2, 1)
print("Change 2 applied (nav registration)")

with open(SRC, "w", encoding="utf-8") as f:
    f.write(content)

print("dashboard.py updated successfully")
