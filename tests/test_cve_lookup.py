"""
Tests for modules/cve_lookup.py — pure logic (data classes + normalisation).
No live NVD API calls.
"""
from modules.cve_lookup import (
    CVEResult, CVELookupResult, _normalise_service_version,
)


# ── CVEResult ──────────────────────────────────────────────────────────────────

class TestCVEResult:
    def test_nvd_url(self):
        r = CVEResult(
            cve_id="CVE-2021-44228",
            description="Log4Shell",
            cvss_score=10.0,
            severity="CRITICAL",
            published="2021-12-10",
        )
        assert r.nvd_url == "https://nvd.nist.gov/vuln/detail/CVE-2021-44228"

    def test_defaults(self):
        r = CVEResult(
            cve_id="CVE-2023-0001",
            description="Test",
            cvss_score=5.0,
            severity="MEDIUM",
            published="2023-01-01",
        )
        assert r.references == []


# ── CVELookupResult ────────────────────────────────────────────────────────────

class TestCVELookupResult:
    def _make_cves(self):
        return [
            CVEResult("CVE-2021-0001", "Desc", 9.8, "CRITICAL", "2021-01-01"),
            CVEResult("CVE-2021-0002", "Desc", 8.1, "HIGH",     "2021-01-02"),
            CVEResult("CVE-2021-0003", "Desc", 6.5, "MEDIUM",   "2021-01-03"),
            CVEResult("CVE-2021-0004", "Desc", 9.1, "CRITICAL", "2021-01-04"),
        ]

    def test_critical_count(self):
        result = CVELookupResult(keyword="openssh", cves=self._make_cves())
        assert result.critical_count == 2

    def test_high_count(self):
        result = CVELookupResult(keyword="openssh", cves=self._make_cves())
        assert result.high_count == 1

    def test_top_score(self):
        result = CVELookupResult(keyword="openssh", cves=self._make_cves())
        assert result.top_score == 9.8

    def test_top_score_empty(self):
        result = CVELookupResult(keyword="unknown")
        assert result.top_score == 0.0

    def test_critical_count_empty(self):
        result = CVELookupResult(keyword="unknown")
        assert result.critical_count == 0

    def test_error_field(self):
        result = CVELookupResult(keyword="test", error="timeout")
        assert result.error == "timeout"

    def test_from_cache_flag(self):
        result = CVELookupResult(keyword="test", from_cache=True)
        assert result.from_cache is True


# ── _normalise_service_version ─────────────────────────────────────────────────

class TestNormaliseServiceVersion:
    def test_openssh(self):
        result = _normalise_service_version("OpenSSH 8.9p1 Ubuntu")
        assert result is not None
        assert "OpenSSH" in result
        assert "8.9" in result

    def test_apache(self):
        result = _normalise_service_version("Apache/2.4.54")
        assert result is not None
        assert "Apache" in result
        assert "2.4.54" in result

    def test_microsoft_iis(self):
        result = _normalise_service_version("Microsoft-IIS/10.0")
        assert result is not None
        assert "IIS" in result
        assert "10.0" in result

    def test_nginx(self):
        result = _normalise_service_version("nginx/1.22.1")
        assert result is not None
        assert "nginx" in result
        assert "1.22.1" in result

    def test_mysql(self):
        result = _normalise_service_version("MySQL 8.0.31")
        assert result is not None
        assert "MySQL" in result

    def test_tomcat(self):
        result = _normalise_service_version("Tomcat/9.0.65")
        assert result is not None
        assert "Tomcat" in result

    def test_empty_string_returns_none(self):
        assert _normalise_service_version("") is None

    def test_none_input_returns_none(self):
        assert _normalise_service_version(None) is None

    def test_no_version_no_digits_returns_none(self):
        # Plain word with no digits — not useful for CVE lookup
        result = _normalise_service_version("SomeWeirdThing")
        assert result is None

    def test_fallback_preserves_version_string(self):
        # Unknown service but has a version number
        result = _normalise_service_version("FancyDaemon 3.1.4")
        assert result is not None
        assert "3.1.4" in result

    def test_truncates_at_60_chars(self):
        long_banner = "nginx/1.22.1 " + "x" * 100
        result = _normalise_service_version(long_banner)
        if result:
            assert len(result) <= 60

    def test_vsftpd(self):
        result = _normalise_service_version("vsftpd 3.0.5")
        assert result is not None
        assert "vsftpd" in result

    def test_redis(self):
        result = _normalise_service_version("redis 7.0.5")
        assert result is not None
        assert "Redis" in result
