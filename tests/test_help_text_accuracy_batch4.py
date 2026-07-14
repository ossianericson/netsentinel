"""
Regression tests for six doc-only claims-audit fixes to ui/help.py's live
_PAGE_HELP copy (F-30, F-32, F-44, F-45, F-67, F-82) -- each corrects a
sentence that described behaviour the app doesn't actually have.
"""
from __future__ import annotations

from ui.help import _PAGE_HELP


def _what_text(page: str) -> str:
    return _PAGE_HELP[page]["what"]


def _hidden_text(page: str) -> str:
    return " ".join(_PAGE_HELP[page].get("hidden", []))


class TestF30NetworkHealthReportContent:
    """The 'Network Health Report' nav page routes to ReportsPage, whose
    generated HTML has Device Uptime / TLS Certificate Status / Service
    Heartbeat Status / Recent Device Events sections -- not an MTR hop
    table, packet-loss %, or outage log (that belongs to the separate ISP
    Report export on the Network Grade page)."""

    def test_help_no_longer_claims_mtr_or_packet_loss(self):
        text = _what_text("Network Health Report")
        assert "MTR" not in text
        assert "packet-loss" not in text

    def test_help_describes_the_real_sections(self):
        text = _what_text("Network Health Report")
        assert "uptime" in text.lower()
        assert "TLS" in text
        assert "heartbeat" in text.lower()


class TestF32GeolocationBundledClaim:
    """modules/geo_locator.py's module docstring states explicitly that
    NetSentinel does NOT bundle the GeoLite2-City .mmdb file -- the user
    must download it once."""

    def test_help_no_longer_claims_bundled(self):
        text = _hidden_text("Geolocation Map")
        assert "bundled with the app" not in text

    def test_help_describes_the_real_download_flow(self):
        text = _hidden_text("Geolocation Map")
        assert "download" in text.lower()


class TestF44TlsExposureScope:
    """ui/pages/cert_page.py (the real widget behind 'TLS & Exposure') has
    zero exposure/internet/UPnP code -- it is TLS-only. The separate
    'Exposed to Internet' feature never probes from the internet side
    either -- it reads the router's local UPnP port-mapping table."""

    def test_tls_help_no_longer_claims_exposure_checking(self):
        text = _what_text("TLS & Exposure")
        assert "checks for accidental internet exposure" not in text.lower()
        assert "separate page" in text

    def test_exposed_help_no_longer_claims_external_probing(self):
        text = _what_text("Exposed to Internet")
        assert "UPnP" in text
        assert "no active probes are sent from outside" in text.lower()


class TestF45LoginTestScope:
    """ui/tabs_recon.py requires the user to manually type Host/Username/
    Password -- there is no factory-default password list anywhere in
    modules/credentialed_scan.py, and nothing runs automatically against
    discovered devices."""

    def test_help_no_longer_claims_default_credentials(self):
        text = _what_text("Login Test")
        assert "default credentials" not in text.lower()

    def test_help_describes_the_real_manual_ssh_flow(self):
        text = _what_text("Login Test")
        assert "ssh" in text.lower()
        assert "credentials you supply" in text.lower()


class TestF67NetworkDocExportFormat:
    """ui/pages/network_doc_page.py's _save_as() only offers an HTML file
    filter -- there is no PDF export path for Network Doc."""

    def test_help_no_longer_claims_pdf_export(self):
        text = _hidden_text("Network Doc")
        assert "PDF" not in text

    def test_help_states_html_only(self):
        text = _hidden_text("Network Doc")
        assert "Export as HTML" in text


class TestF82HomeAutomationClaims:
    """The literal string 'not connected' does not appear anywhere in
    home_automation_page.py, and device presence is fed by the same
    AvailabilityWorker used elsewhere (~60s default poll), not a
    sub-second push path."""

    def test_help_no_longer_claims_not_connected_string(self):
        text = _hidden_text("Home Automation")
        assert "not connected" not in text

    def test_help_no_longer_claims_seconds_latency(self):
        text = _hidden_text("Home Automation")
        assert "within seconds" not in text.lower()

    def test_help_describes_the_real_poll_interval(self):
        text = _hidden_text("Home Automation")
        assert "60 second" in text.lower()
