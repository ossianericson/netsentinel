"""
Regression tests for claims-audit findings F-08, F-09, F-10, F-15, F-76 -- each is a
docs/feature-reference.md or README.md row claiming behaviour the underlying code
does not deliver. These assert the corrected wording stays correct.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parent.parent
FEATURE_REF = (ROOT / "docs" / "feature-reference.md").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")


def test_f08_dhcp_rogue_points_at_real_active_detector():
    """F-08: DHCP Rogue was attributed to dhcp_fingerprint.py (a passive OS-hint mapper
    with zero rogue-server logic) instead of the real active-probe detector."""
    assert "modules/dhcp_fingerprint.py" not in FEATURE_REF.split("DHCP Rogue")[1][:300]
    idx = FEATURE_REF.index("**DHCP Rogue**")
    row = FEATURE_REF[idx: idx + 300]
    assert "modules/dhcp_detector.py" in row
    assert "Passive" not in row


def test_f09_scan_plugins_no_sandbox_claim():
    """F-09: plugin_system.py has zero sandboxing (bare exec_module, in-process)."""
    idx = FEATURE_REF.index("**Scan Plugins**")
    row = FEATURE_REF[idx: idx + 200]
    assert "sandbox" not in row.lower()


def test_f10_login_test_ssh_only():
    """F-10: only SSH exists; SMB/FTP/Telnet were never implemented."""
    idx = FEATURE_REF.index("**Login Test**")
    row = FEATURE_REF[idx: idx + 200]
    assert "SMB" not in row
    assert "FTP" not in row
    assert "Telnet" not in row
    assert "SSH" in row


def test_f15_full_discovery_no_ssdp_claim():
    """F-15: combined_discovery.py's own docstring lists ARP/mDNS/ICMP/SYN only --
    no SSDP. SSDP exists solely in the unrelated passive_observer.py."""
    idx = FEATURE_REF.index("**Full Discovery**")
    row = FEATURE_REF[idx: idx + 200]
    assert "SSDP" not in row

    idx2 = README.index("Full device discovery")
    row2 = README[idx2: idx2 + 200]
    assert "SSDP" not in row2


def test_f76_plugin_count_is_ten():
    """F-76: only 10 vendor integrations exist, not 12."""
    assert "12 bundled plugins" not in FEATURE_REF
    assert "10 bundled plugins" in FEATURE_REF
    assert "12 bundled plugins" not in README
    assert "10 bundled plugins" in README
