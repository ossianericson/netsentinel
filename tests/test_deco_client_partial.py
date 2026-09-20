"""S3.4 — a Deco client list missing a node's clients must say so (RULE-SURF1, matrix F1d).

``DecoMeshClient.get_all_clients`` queries each mesh node in turn. When one node's call
fails it logs a warning — kept, per the 2026-07-16 owner decision — and moves on, which
is right: one unreachable satellite should not blank the whole mesh. What was wrong is
the return value. It was a plain ``list`` shaped exactly like a complete one, so every
caller counted the survivors as "all clients" and a node's worth of devices silently
vanished from the device map.

The real ``get_all_clients`` runs here; only ``_request`` — the HTTP transport, which
needs a router — is replaced (RULE-DBG5: the field must be populated by the real
producer, not handed in by the test).
"""
from __future__ import annotations

import logging

import pytest

from modules.deco_client import DecoMeshClient, MeshApiError, MeshUnit


def _units():
    return [
        MeshUnit(name="Vardagsrum", mac="3c:64:cf:e0:26:1c", ip="192.168.68.1", role="master", online=True),
        MeshUnit(name="Floor2", mac="60:83:e7:88:a6:c4", ip="192.168.68.2", role="slave", online=True),
    ]


def _client(failing_mac: str | None):
    client = DecoMeshClient("192.168.68.1", "unused")

    def _request(path, payload):
        mac = payload["params"]["device_mac"]
        if mac == failing_mac:
            raise MeshApiError("Svaret avslutades i förtid")
        return {"client_list": [{
            "mac": f"aa-bb-cc-00-00-{mac[-2:]}", "online": True, "ip": "192.168.68.50",
            "name": "", "connection_type": "band5",
        }]}

    client._request = _request  # type: ignore[method-assign]
    return client


def test_a_failed_node_is_named_on_the_result(caplog):
    with caplog.at_level(logging.WARNING, logger="modules.deco_client"):
        result = _client(failing_mac="60-83-E7-88-A6-C4").get_all_clients(units=_units())

    assert isinstance(result, list), "callers iterate and len() it; it must stay a list"
    assert len(result) == 1
    assert result.failed_nodes == ["Floor2"]
    assert any("Floor2" in r.getMessage() for r in caplog.records), "the warning stays (2026-07-16)"


def test_a_complete_result_names_no_failed_nodes():
    result = _client(failing_mac=None).get_all_clients(units=_units())

    assert len(result) == 2
    assert result.failed_nodes == []


def test_every_node_failing_is_not_an_empty_mesh():
    """Zero clients with two failed nodes means "could not see", never "nobody is home"."""
    client = DecoMeshClient("192.168.68.1", "unused")

    def _all_fail(path, payload):
        raise MeshApiError("timeout")

    client._request = _all_fail  # type: ignore[method-assign]
    result = client.get_all_clients(units=_units())

    assert list(result) == []
    assert result.failed_nodes == ["Vardagsrum", "Floor2"]


@pytest.mark.parametrize("failing", [None, "60-83-E7-88-A6-C4"])
def test_the_result_still_behaves_like_the_list_callers_already_use(failing):
    """plugins/deco_plugin.py builds dicts from it and len()s it; no caller changes."""
    result = _client(failing).get_all_clients(units=_units())

    rows = [{"mac": c.mac, "unit": c.unit_name} for c in result]
    assert len(rows) == len(result)
    assert result == list(result)
