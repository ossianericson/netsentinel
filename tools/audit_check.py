"""Runtime audit: verify all 4 changes are instantiated correctly."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.argv = ['audit', '-platform', 'offscreen']
from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication(sys.argv)

results = []

# Change 1 — scan_complete signal on DnsZonePage
try:
    from ui.pages.dns_zone_page import DnsZonePage
    assert hasattr(DnsZonePage, 'scan_complete'), "no scan_complete signal"
    results.append("Change 1 OK: DnsZonePage.scan_complete signal exists")
except Exception as e:
    results.append(f"Change 1 FAIL: {e}")

# Change 2 — Scan Center card on HomePage
try:
    from ui.pages.home_page import HomePage
    home = HomePage()
    assert hasattr(home, '_scan_center_card'), "no _scan_center_card attr"
    n = len(home._scan_center_dot_labels)
    assert n == 5, f"expected 5 rows, got {n}"
    results.append(f"Change 2 OK: _scan_center_card with {n} rows")
except Exception as e:
    results.append(f"Change 2 FAIL: {e}")

# Change 3 — _ScanStatusTile in overview tile registry
try:
    from ui.widgets.overview_tile import _TILE_CLASSES, _DEFAULT_ORDER, _LAYOUT_VER
    assert 'scan_status' in _TILE_CLASSES, "scan_status not in _TILE_CLASSES"
    assert _DEFAULT_ORDER[0] == 'scan_status', f"not first, got {_DEFAULT_ORDER[0]}"
    assert _LAYOUT_VER == 4, f"_LAYOUT_VER={_LAYOUT_VER}"
    results.append(f"Change 3 OK: scan_status tile, LAYOUT_VER={_LAYOUT_VER}, first in order")
except Exception as e:
    results.append(f"Change 3 FAIL: {e}")

# Change 4 — Last run chip on Speed Test page
try:
    from ui.pages.speed_test_page import SpeedTestPage
    stp = SpeedTestPage(store=None)
    assert hasattr(stp, '_page_header_bar'), "no _page_header_bar"
    assert 'last_run' in stp._page_header_bar._chip_keys, "last_run chip missing"
    results.append("Change 4a OK: SpeedTestPage last_run chip present")
except Exception as e:
    results.append(f"Change 4a FAIL: {e}")

# Change 4 — Last run chip on DNS Zone page
try:
    from ui.pages.dns_zone_page import DnsZonePage
    dz = DnsZonePage()
    assert hasattr(dz, '_page_header_bar'), "no _page_header_bar on DnsZonePage"
    assert 'last_run' in dz._page_header_bar._chip_keys, "last_run chip missing"
    results.append("Change 4b OK: DnsZonePage last_run chip present")
except Exception as e:
    results.append(f"Change 4b FAIL: {e}")

print("\n".join(results))
