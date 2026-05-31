"""Tests for modules/name_resolver.py — multi-method hostname resolution."""
import pytest


def test_name_resolver_import():
    from modules import name_resolver
    assert name_resolver is not None


def test_resolved_name_dataclass():
    from modules.name_resolver import ResolvedName
    rn = ResolvedName(ip="10.0.0.1", display_name="MyDevice", source="rdns")
    assert rn.ip == "10.0.0.1"
    assert rn.display_name == "MyDevice"
    assert rn.source == "rdns"


def test_resolve_returns_resolved_name_type():
    from modules.name_resolver import resolve, ResolvedName
    result = resolve("127.0.0.1", use_netbios=False, use_mdns=False, use_snmp=False)
    assert isinstance(result, ResolvedName)
    assert result.ip == "127.0.0.1"


def test_resolve_batch_returns_iterable():
    from modules.name_resolver import resolve_batch
    results = resolve_batch(["127.0.0.1"])
    assert results is not None


def test_rdns_helper_returns_string():
    from modules.name_resolver import _rdns
    result = _rdns("127.0.0.1", timeout=0.5)
    assert isinstance(result, str)


def test_public_api_signatures():
    from modules import name_resolver
    import inspect
    sig = inspect.signature(name_resolver.resolve)
    params = list(sig.parameters.keys())
    assert "ip" in params
