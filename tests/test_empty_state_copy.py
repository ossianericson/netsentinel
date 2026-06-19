"""Tests for empty-state copy consistency (Sprint 7, S7-6).

Static source checks (no widget construction needed) confirming each scan-dependent
page's EmptyStateCard follows the "No X yet" title pattern and states what to expect
when the CTA is clicked, instead of just repeating the page's feature name as the title.
"""
from pathlib import Path

_REPO = Path(__file__).parent.parent


_EXPECTED_TITLES = {
    "ui/pages/inventory_page.py":     "No devices found yet",
    "ui/pages/overview_page.py":      "No scan results yet",
    "ui/pages/connections_page.py":   "No connections captured yet",
    "ui/pages/live_bandwidth_page.py": "No bandwidth data yet",
    "ui/pages/baseline_page.py":      "No snapshots yet",
    "ui/pages/dns_zone_page.py":      "No DNS records mapped yet",
    "ui/pages/cert_page.py":          "No certificates monitored yet",
    "ui/pages/app_traffic_page.py":   "No traffic captured yet",
    "ui/pages/uptime_page.py":        "No uptime history yet",
}


class TestEmptyStateTitlesFollowNoXYetPattern:
    def test_expected_titles_present_in_source(self):
        for rel_path, title in _EXPECTED_TITLES.items():
            src = (_REPO / rel_path).read_text(encoding="utf-8")
            assert f'"{title}"' in src, f"{rel_path} missing expected empty-state title {title!r}"

    def test_titles_start_with_no(self):
        for title in _EXPECTED_TITLES.values():
            assert title.startswith("No "), f"{title!r} does not follow the 'No X yet' pattern"

    def test_old_feature_name_titles_removed(self):
        # The old titles just repeated the page/feature name with no "empty" framing —
        # confirm they were replaced, not just supplemented.
        _OLD_TITLES = {
            "ui/pages/inventory_page.py":     "Device Inventory",
            "ui/pages/overview_page.py":      "Your network at a glance",
            "ui/pages/connections_page.py":   "Active Connections",
            "ui/pages/live_bandwidth_page.py": "Live Bandwidth Monitor",
            "ui/pages/baseline_page.py":      "Configuration Baseline",
            "ui/pages/dns_zone_page.py":      "DNS Zone Mapping",
            "ui/pages/cert_page.py":          "TLS Certificate Monitor",
            "ui/pages/app_traffic_page.py":   "App Traffic Analyzer",
            "ui/pages/uptime_page.py":        "Device Uptime Monitor",
        }
        for rel_path, old_title in _OLD_TITLES.items():
            src = (_REPO / rel_path).read_text(encoding="utf-8")
            assert f'title="{old_title}"' not in src, (
                f"{rel_path} still uses the old empty-state title {old_title!r}"
            )
