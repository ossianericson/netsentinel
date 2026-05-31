"""Tests for modules/cloud_metadata.py — cloud IMDS probe."""
import pytest
from modules.cloud_metadata import (
    CloudMetadataResult, NetworkExposureResult,
    _tcp_connect, check_local_imds, check_network_imds_exposure,
)


def test_import():
    import modules.cloud_metadata as m
    assert hasattr(m, "check_local_imds")
    assert hasattr(m, "check_network_imds_exposure")
    assert hasattr(m, "CloudMetadataResult")


def test_cloud_metadata_result_defaults():
    r = CloudMetadataResult()
    assert r.provider is None
    assert r.instance_id is None
    assert r.risk_level == "NONE"
    assert r.findings == []


def test_network_exposure_result_fields():
    r = NetworkExposureResult(device_ip="10.0.0.1")
    assert r.device_ip == "10.0.0.1"
    assert r.exposed is False
    assert r.risk_level == "NONE"


def test_check_local_imds_offline(monkeypatch):
    monkeypatch.setattr("modules.cloud_metadata._http_get", lambda *a, **kw: None)
    monkeypatch.setattr("modules.cloud_metadata._http_put", lambda *a, **kw: None)
    result = check_local_imds()
    assert isinstance(result, CloudMetadataResult)
    assert result.provider is None


def test_tcp_connect_refused():
    # Port 1 on loopback should be closed/refused
    assert _tcp_connect("127.0.0.1", 1, timeout=0.2) is False


def test_check_network_imds_empty_list():
    results = check_network_imds_exposure([])
    assert results == []
