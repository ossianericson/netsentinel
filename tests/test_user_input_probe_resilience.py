"""Exception coverage on the paths that carry user-typed and remote-supplied input.

Both defects here are regional in the same way: they need input that a developer on an
English, low-latency LAN never produces — a non-ASCII hostname, or a link lossy enough
to reset mid-body — so they survived every local test run.
"""
from __future__ import annotations

import pytest

from modules.utils_net import tcp_probe


class TestTcpProbeExceptionCoverage:
    """``tcp_probe()`` caught only ``OSError``; two other types reach it.

    Both come from **user-typed** targets (Service Monitor, Private Endpoint,
    Availability), and callers ``cloud_metadata._tcp_connect`` / ``ha_detector._tcp_open``
    have no local guard — so an escaping exception propagates into a worker rather than
    being reported as an unreachable host.
    """

    def test_an_idna_invalid_hostname_is_reported_not_raised(self):
        """``socket.create_connection`` raises ``UnicodeError`` on a bad IDNA label.

        A label over 63 bytes cannot be IDNA-encoded. Non-ASCII hostnames are ordinary
        wherever the script is not Latin, which is what makes this regional.
        """
        ok, rtt, err = tcp_probe("न" * 80 + ".example", 80, timeout=0.1)
        assert ok is False
        assert rtt == -1.0
        assert err, "the failure must be reported through the error channel, not raised"

    @pytest.mark.parametrize("port", [-1, 70000])
    def test_an_out_of_range_port_is_reported_not_raised(self, port):
        """``OverflowError`` is not an ``OSError``; a typo'd port must not crash a worker."""
        ok, rtt, err = tcp_probe("127.0.0.1", port, timeout=0.1)
        assert ok is False
        assert rtt == -1.0
        assert err

    def test_a_normal_refused_connection_still_works(self):
        """The widened tuple must not change the ordinary failure contract."""
        ok, rtt, err = tcp_probe("127.0.0.1", 1, timeout=0.5)
        assert ok is False
        assert rtt == -1.0
        assert err


class TestDecoErrorClassification:
    """A mid-body reset must read as INFRA_UNREACHABLE, never as a bad password.

    ``deco_client`` catches ``(Timeout, ConnectionError)``. ``SSLError``/``ProxyError``/
    ``ConnectTimeout`` are ``ConnectionError`` subclasses so they are covered, but
    ``ChunkedEncodingError`` is a bare ``RequestException`` and is not — so a reset part-way
    through a response body on a lossy link fell to the generic handler and came back as
    ``AUTH:``, which ``hardware_integration_page`` deliberately treats as *reachable*.

    The user is told their password is wrong when the real problem is the link — and lossy
    links are precisely the regional condition this program is about.
    """

    def test_a_mid_body_reset_is_not_reported_as_an_auth_failure(self, monkeypatch):
        import requests
        import tplinkrouterc6u

        import modules.deco_client as dc

        class _ChunkedFail:
            def __init__(self, *a, **k):
                pass

            def authorize(self):
                raise requests.exceptions.ChunkedEncodingError("connection broken")

        # deco_client imports TPLinkDecoClient lazily inside _ensure_client(), so the
        # patch has to land on the source module rather than on deco_client itself.
        monkeypatch.setattr(tplinkrouterc6u, "TPLinkDecoClient", _ChunkedFail)

        client = dc.DecoMeshClient(host="192.0.2.1", password="correct-horse")
        with pytest.raises(Exception) as excinfo:
            client._ensure_client()

        exc = excinfo.value
        assert not isinstance(exc, dc.MeshAuthError), (
            "a lossy-link reset raised MeshAuthError — the user is told to re-enter a "
            "password that was never wrong, and the link problem is never surfaced"
        )
        assert "password" not in str(exc).lower()

    def test_the_reset_reaches_the_plugin_classifier_as_a_non_auth_failure(self, monkeypatch):
        """Assert the consumer's verdict, not just the exception type (RULE-DBG5).

        ``hardware_integration_page`` decides reachability purely on whether the string
        starts with ``AUTH:`` — so the classification that matters is the one
        ``deco_plugin._fmt_err()`` produces, not the class raised inside deco_client.
        """
        import requests
        import tplinkrouterc6u

        import modules.deco_client as dc
        from plugins import deco_plugin

        class _ChunkedFail:
            def __init__(self, *a, **k):
                pass

            def authorize(self):
                raise requests.exceptions.ChunkedEncodingError("connection broken")

        monkeypatch.setattr(tplinkrouterc6u, "TPLinkDecoClient", _ChunkedFail)

        client = dc.DecoMeshClient(host="192.0.2.1", password="correct-horse")
        try:
            client._ensure_client()
        except Exception as exc:  # noqa: BLE001 — the classifier is what is under test
            verdict = deco_plugin._fmt_err(exc)
        else:
            raise AssertionError(
                "_ensure_client() did not raise; the classifier under test was "
                "never exercised"
            )

        assert not verdict.startswith("AUTH:"), (
            f"classified as an auth failure ({verdict!r}); hardware_integration_page "
            "treats an AUTH: prefix as *reachable*, so no INFRA_UNREACHABLE is raised "
            "for a router that is genuinely unreachable over a lossy link"
        )
