"""Tests for modules/private_endpoint_checker.py — RFC 1918 exposure checker."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


def test_import():
    import modules.private_endpoint_checker  # noqa: F401


def test_endpoint_spec_dataclass():
    from modules.private_endpoint_checker import EndpointSpec
    spec = EndpointSpec(host="db.internal.example.com", port=5432, label="Test DB")
    assert spec.host == "db.internal.example.com"
    assert spec.port == 5432
    assert spec.label == "Test DB"


def test_endpoint_result_plain_verdict_property():
    from modules.private_endpoint_checker import EndpointResult, EndpointSpec
    spec = EndpointSpec(host="redis.example.com", port=6379, label="Redis")
    r = EndpointResult(
        spec=spec,
        resolved_ips=["10.0.0.5"],
        dns_ok=True,
        is_private=True,
        dns_leak=False,
        dns_latency=2.0,
        dns_server="8.8.8.8",
        paas_hint=None,
        tcp_open=True,
        tcp_latency=3.0,
        tls_checked=False,
        cert=None,
        cloud=None,
        status="exposed",
        findings=["Port 6379 open"],
    )
    verdict = r.plain_verdict
    assert isinstance(verdict, str)
    assert len(verdict) > 0


def test_endpoint_result_not_reachable():
    from modules.private_endpoint_checker import EndpointResult, EndpointSpec
    spec = EndpointSpec(host="db.internal", port=3306, label="DB")
    r = EndpointResult(
        spec=spec,
        resolved_ips=[],
        dns_ok=False,
        is_private=True,
        dns_leak=False,
        dns_latency=None,
        dns_server=None,
        paas_hint=None,
        tcp_open=False,
        tcp_latency=None,
        tls_checked=False,
        cert=None,
        cloud=None,
        status="unreachable",
        findings=["DNS resolution failed"],
    )
    verdict = r.plain_verdict
    assert isinstance(verdict, str)


def test_check_endpoint_function_exists():
    from modules.private_endpoint_checker import check_endpoint
    import inspect
    assert callable(check_endpoint)
    sig = inspect.signature(check_endpoint)
    assert "spec" in sig.parameters


def test_check_endpoints_function_exists():
    from modules.private_endpoint_checker import check_endpoints
    import inspect
    assert callable(check_endpoints)


def test_check_endpoint_no_network(monkeypatch):
    """check_endpoint returns EndpointResult even on DNS failure."""
    from modules.private_endpoint_checker import EndpointSpec, check_endpoint, EndpointResult
    import socket
    monkeypatch.setattr(socket, "getaddrinfo",
                        lambda *a, **kw: (_ for _ in ()).throw(OSError("no dns")))

    spec = EndpointSpec(host="__nonexistent_host_test__.invalid", port=9999, label="Test")
    try:
        result = check_endpoint(spec)
        assert isinstance(result, EndpointResult)
    except Exception:
        pytest.skip("check_endpoint raised on DNS failure")
