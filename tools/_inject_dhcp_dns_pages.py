"""
Safely inject DhcpLeasePage and DnsZonePage into dashboard.py.

Two changes:
1. Instantiate both pages after LiveBandwidthPage (line ~792)
2. Register them in the Discover nav subgroup after "Network Info"
"""
import sys

SRC = "ui/dashboard.py"

with open(SRC, "r", encoding="utf-8") as f:
    content = f.read()

# ── Change 1: instantiate pages ───────────────────────────────────────────────
OLD1 = (
    "        from ui.pages.live_bandwidth_page import LiveBandwidthPage\n"
    "        self._live_bandwidth_page = LiveBandwidthPage(parent=None)\n"
)
NEW1 = OLD1 + (
    "\n"
    "        from ui.pages.dhcp_lease_page import DhcpLeasePage\n"
    "        self._dhcp_lease_page = DhcpLeasePage(parent=None)\n"
    "\n"
    "        from ui.pages.dns_zone_page import DnsZonePage\n"
    "        self._dns_zone_page = DnsZonePage(parent=None)\n"
)

if OLD1 not in content:
    print("ERROR: anchor for instantiation not found")
    sys.exit(1)

content = content.replace(OLD1, NEW1, 1)
print("Change 1 applied (page instantiation)")

# ── Change 2: nav registration in Discover subgroup ──────────────────────────
# Insert after the Network Info page in the Discover subgroup.
# We use a unique ASCII marker (the _nav_current_subgroup reset after Discover)
# Anchor: the line "        self._nav_current_subgroup = -1\n" immediately
# after the Network Info entry; we'll match the Discover block specifically.

DISCOVER_BLOCK_ANCHOR = (
    "        self._nav_add_page(\"\u2139\",  \"Network Info\",         net)\n"
    "        self._nav_current_subgroup = -1\n"
)
DISCOVER_BLOCK_NEW = (
    "        self._nav_add_page(\"\u2139\",  \"Network Info\",         net)\n"
    "        self._nav_add_page(\"\U0001f4cb\", \"DHCP Lease Inventory\",  self._dhcp_lease_page)\n"
    "        self._nav_add_page(\"\U0001f5fa\", \"DNS Zone Map\",          self._dns_zone_page)\n"
    "        self._nav_current_subgroup = -1\n"
)

if DISCOVER_BLOCK_ANCHOR not in content:
    print("ERROR: anchor for nav registration not found")
    sys.exit(1)

content = content.replace(DISCOVER_BLOCK_ANCHOR, DISCOVER_BLOCK_NEW, 1)
print("Change 2 applied (nav registration)")

with open(SRC, "w", encoding="utf-8") as f:
    f.write(content)

print("dashboard.py updated successfully")
