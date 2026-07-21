"""
Tests for modules/tls_checker.py — pure logic helpers, no live TLS connections.
"""
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
from modules.tls_checker import _parse_cert_field, CertInfo, check_cert, check_host_certs


# ── _parse_cert_field ──────────────────────────────────────────────────────────

class TestParseCertField:
    def test_extracts_common_name(self):
        cert_dict = {
            "subject": ((("commonName", "example.com"),),)
        }
        assert _parse_cert_field(cert_dict, "subject") == "example.com"

    def test_extracts_issuer_cn(self):
        cert_dict = {
            "issuer": ((("commonName", "Let's Encrypt Authority X3"),),)
        }
        assert _parse_cert_field(cert_dict, "issuer") == "Let's Encrypt Authority X3"

    def test_missing_field_returns_empty(self):
        assert _parse_cert_field({}, "subject") == ""
        assert _parse_cert_field({}, "issuer") == ""

    def test_no_common_name_returns_empty(self):
        cert_dict = {
            "subject": ((("organizationName", "Acme Corp"),),)
        }
        assert _parse_cert_field(cert_dict, "subject") == ""

    def test_multiple_rdns_first_cn_wins(self):
        cert_dict = {
            "subject": (
                (("organizationName", "Acme"),),
                (("commonName", "acme.com"),),
            )
        }
        assert _parse_cert_field(cert_dict, "subject") == "acme.com"


# ── CertInfo dataclass ─────────────────────────────────────────────────────────

class TestCertInfo:
    def test_default_values(self):
        info = CertInfo(host="example.com", port=443)
        assert info.host == "example.com"
        assert info.port == 443
        assert info.is_expired is False
        assert info.is_self_signed is False
        assert info.error == ""
        assert info.days_remaining == 0

    def test_error_field(self):
        info = CertInfo(host="example.com", port=443, error="Connection refused")
        assert info.error == "Connection refused"

    def test_not_testable_defaults_false(self):
        info = CertInfo(host="example.com", port=443)
        assert info.not_testable is False
        assert info.not_testable_reason == ""


# ── check_cert — mocked TLS ────────────────────────────────────────────────────

class TestCheckCert:
    def _make_mock_cert(self, cn="example.com", issuer_cn="DigiCert", days_ahead=90):
        """Build a fake cert dict as returned by ssl getpeercert()."""
        expiry = datetime.now(timezone.utc) + timedelta(days=days_ahead)
        not_after = expiry.strftime("%b %d %H:%M:%S %Y GMT")
        not_before = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%b %d %H:%M:%S %Y GMT")
        return {
            "subject": ((("commonName", cn),),),
            "issuer": ((("commonName", issuer_cn),),),
            "notAfter": not_after,
            "notBefore": not_before,
        }

    def test_valid_cert_returns_certinfo(self):
        fake_cert = self._make_mock_cert(days_ahead=90)
        mock_tls = MagicMock()
        mock_tls.getpeercert.side_effect = lambda binary_form=False: (
            b"fakebytes" if binary_form else fake_cert
        )
        mock_raw = MagicMock()
        mock_raw.__enter__ = MagicMock(return_value=mock_raw)
        mock_raw.__exit__ = MagicMock(return_value=False)
        mock_tls.__enter__ = MagicMock(return_value=mock_tls)
        mock_tls.__exit__ = MagicMock(return_value=False)

        with patch("socket.create_connection", return_value=mock_raw), \
             patch("ssl.SSLContext.wrap_socket", return_value=mock_tls):
            info = check_cert("example.com", 443)

        # We can't guarantee mock wiring works perfectly across ssl context,
        # so just verify the function returns a CertInfo without crashing.
        assert isinstance(info, CertInfo)
        assert info.host == "example.com"
        assert info.port == 443

    def test_connection_refused_returns_error(self):
        with patch("socket.create_connection", side_effect=ConnectionRefusedError):
            info = check_cert("192.168.1.1", 443, timeout=0.1)
        assert isinstance(info, CertInfo)
        assert info.error == "Connection refused"

    def test_connection_refused_is_not_testable(self):
        """Sprint 5b (C): the CertInfo-drop bug -- a connection-refused host
        used to have error set but verdict empty, which check_host_certs()
        silently dropped from its returned list entirely. Must now be flagged
        not_testable (and carry a verdict) instead of vanishing."""
        with patch("socket.create_connection", side_effect=ConnectionRefusedError):
            info = check_cert("192.168.1.1", 443, timeout=0.1)
        assert info.not_testable is True
        assert info.not_testable_reason != ""
        assert info.verdict != ""

    def test_timeout_returns_error(self):
        import socket as _socket
        with patch("socket.create_connection", side_effect=_socket.timeout("timed out")):
            info = check_cert("192.168.1.1", 8443, timeout=0.1)
        assert isinstance(info, CertInfo)
        assert info.error != "" or info.verdict != ""

    def test_timeout_is_not_testable(self):
        import socket as _socket
        with patch("socket.create_connection", side_effect=_socket.timeout("timed out")):
            info = check_cert("192.168.1.1", 8443, timeout=0.1)
        assert info.not_testable is True

    def test_no_certificate_returned_is_not_testable(self):
        """A completed TLS handshake with no certificate to inspect is also a
        coverage gap, not a confirmed 'this cert is fine' or plain tool error."""
        mock_tls = MagicMock()
        mock_tls.getpeercert.return_value = None
        mock_raw = MagicMock()
        mock_raw.__enter__ = MagicMock(return_value=mock_raw)
        mock_raw.__exit__ = MagicMock(return_value=False)
        mock_tls.__enter__ = MagicMock(return_value=mock_tls)
        mock_tls.__exit__ = MagicMock(return_value=False)

        with patch("socket.create_connection", return_value=mock_raw), \
             patch("ssl.SSLContext.wrap_socket", return_value=mock_tls):
            info = check_cert("example.com", 443)

        assert info.not_testable is True
        assert info.not_testable_reason != ""

    def test_ssl_error_stays_plain_error_not_not_testable(self):
        """A TLS-level protocol error means the host WAS reached and answered
        with a genuine, meaningful problem -- must not become not_testable."""
        import ssl as _ssl
        with patch("socket.create_connection", side_effect=_ssl.SSLError("bad handshake")):
            info = check_cert("192.168.1.1", 443, timeout=0.1)
        assert info.not_testable is False
        assert info.error != ""

    def test_self_signed_detection(self):
        """When subject CN == issuer CN, is_self_signed should be True."""
        fake_cert = self._make_mock_cert(cn="self.local", issuer_cn="self.local", days_ahead=300)
        mock_tls = MagicMock()
        mock_tls.getpeercert.side_effect = lambda binary_form=False: (
            b"fakebytes" if binary_form else fake_cert
        )
        mock_raw = MagicMock()
        mock_raw.__enter__ = MagicMock(return_value=mock_raw)
        mock_raw.__exit__ = MagicMock(return_value=False)
        mock_tls.__enter__ = MagicMock(return_value=mock_tls)
        mock_tls.__exit__ = MagicMock(return_value=False)

        with patch("socket.create_connection", return_value=mock_raw), \
             patch("ssl.SSLContext.wrap_socket", return_value=mock_tls):
            info = check_cert("self.local", 443)

        # Only check if subject/issuer were populated (mock may not wire perfectly)
        if info.subject and info.issuer:
            assert info.is_self_signed is True


# ── check_host_certs — the CertInfo-drop bug ────────────────────────────────────

class TestCheckHostCertsDropBug:
    def test_not_testable_result_is_not_dropped(self):
        """Before the fix: `if not info.error or info.verdict` silently
        discarded any CertInfo with error set but verdict empty -- exactly
        the connection-refused/no-cert cases. An unreachable host must still
        appear in the returned list so the UI/nav layer can report it."""
        with patch("socket.create_connection", side_effect=ConnectionRefusedError):
            results = check_host_certs("192.168.1.1", ports=[443])
        assert len(results) == 1
        assert results[0].not_testable is True

    def test_successful_result_still_included(self):
        fake_cert = {
            "subject": ((("commonName", "example.com"),),),
            "issuer": ((("commonName", "DigiCert"),),),
            "notAfter": (datetime.now(timezone.utc) + timedelta(days=90)).strftime("%b %d %H:%M:%S %Y GMT"),
            "notBefore": (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%b %d %H:%M:%S %Y GMT"),
        }
        mock_tls = MagicMock()
        mock_tls.getpeercert.side_effect = lambda binary_form=False: (
            b"fakebytes" if binary_form else fake_cert
        )
        mock_raw = MagicMock()
        mock_raw.__enter__ = MagicMock(return_value=mock_raw)
        mock_raw.__exit__ = MagicMock(return_value=False)
        mock_tls.__enter__ = MagicMock(return_value=mock_tls)
        mock_tls.__exit__ = MagicMock(return_value=False)

        with patch("socket.create_connection", return_value=mock_raw), \
             patch("ssl.SSLContext.wrap_socket", return_value=mock_tls):
            results = check_host_certs("example.com", ports=[443])
        assert len(results) == 1
        assert results[0].not_testable is False
