"""
Hardware integration test for deco_client.py.

Skipped automatically in CI (no router reachable). Run locally against a
real Deco mesh by setting environment variables:

    $env:DECO_HOST     = "192.168.68.1"
    $env:DECO_PASSWORD = "your-admin-password"
    python -m pytest tests/test_deco_client.py -v -s
"""
import os
import socket

import pytest

_HOST     = os.environ.get("DECO_HOST",     "192.168.68.1")
_PASSWORD = os.environ.get("DECO_PASSWORD", "")

def _router_reachable() -> bool:
    try:
        with socket.create_connection((_HOST, 80), timeout=2):
            return True
    except OSError:
        return False

pytestmark = pytest.mark.skipif(
    not _router_reachable(),
    reason=f"Deco router not reachable at {_HOST} — skipping hardware test",
)


def test_detect_deco():
    from modules.deco_client import detect_deco
    result = detect_deco(_HOST)
    print(f"detect_deco({_HOST}): {result}")


def test_login():
    if not _PASSWORD:
        pytest.skip("DECO_PASSWORD env var not set")
    from modules.deco_client import DecoMeshClient
    c = DecoMeshClient(_HOST, _PASSWORD)
    stok = c.login()
    assert stok and len(stok) > 4, f"Expected valid stok, got: {stok!r}"
    print(f"login OK  stok={stok[:12]}...")


def test_get_mesh_units():
    if not _PASSWORD:
        pytest.skip("DECO_PASSWORD env var not set")
    from modules.deco_client import DecoMeshClient
    c = DecoMeshClient(_HOST, _PASSWORD)
    c.login()
    units = c.get_mesh_units()
    assert len(units) > 0, "Expected at least one mesh unit"
    for u in units:
        print(f"  [{u.role:6s}] {u.name:25s} {u.mac}  {u.ip}")


def test_get_all_clients():
    if not _PASSWORD:
        pytest.skip("DECO_PASSWORD env var not set")
    from modules.deco_client import DecoMeshClient
    c = DecoMeshClient(_HOST, _PASSWORD)
    c.login()
    units = c.get_mesh_units()
    clients = c.get_all_clients(units=units)
    print(f"\nClients ({len(clients)}):")
    for cl in clients:
        print(f"  {cl.name:30s} {cl.mac:<20s} {cl.ip:<16s} {cl.band:<6s} "
              f"dn={cl.download_kbps:5.1f} up={cl.upload_kbps:5.1f}  "
              f"[{cl.unit_name}]")
