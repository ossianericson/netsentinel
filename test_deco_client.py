"""Quick smoke test for the new deco_client.py module."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from modules.deco_client import DecoMeshClient, detect_deco

host = "192.168.68.1"
password = "a8-/Ba8+ZZJ_b9z"

print(f"detect_deco({host}):", detect_deco(host))

c = DecoMeshClient(host, password)
stok = c.login()
print(f"login OK  stok={stok[:12]}...")

units = c.get_mesh_units()
print(f"\nMesh units ({len(units)}):")
for u in units:
    print(f"  [{u.role:6s}] {u.name:25s} {u.mac}  {u.ip}")

clients = c.get_all_clients(units=units)
print(f"\nClients ({len(clients)}):")
for cl in clients:
    print(f"  {cl.name:30s} {cl.mac:<20s} {cl.ip:<16s} {cl.band:<6s} "
          f"dn={cl.download_kbps:5.1f} up={cl.upload_kbps:5.1f}  "
          f"[{cl.unit_name}]")
