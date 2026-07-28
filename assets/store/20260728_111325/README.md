# Microsoft Store screenshots — v2.1.48

Captured 2026-07-28 with `python tools/store_screenshots.py` at 2048x1152, on a
populated, idle app (all scans completed first). Every file passed both capture
checks: breadcrumb confirmed the correct page was on screen, and the content
region was confirmed painted.

Replaces the v2.1.25 set (`20260705_200927`), which was 23 releases stale and
contained a mislabeled file — `06_service_diag.png` there was actually the
Network Map page, and Service Diagnostics had never been captured at all.

## Upload order

The Store accepts 10 screenshots and shows them top-down, so upload in this
order rather than filename order:

| Order | File | Why |
|---|---|---|
| 1 | `03_devices.png` | Densest, most immediately legible "it found my network" |
| 2 | `05_network_map.png` | Best single visual — clean hierarchy, traffic overlay on |
| 3 | `07_security_overview.png` | Grade + scan status: the audit pitch |
| 4 | `10_protocol_viz.png` | Strongest differentiator — ten protocols, real addresses, N+/CCNA |
| 5 | `01_home.png` | Landing page, populated and idle |
| 6 | `12_geo_map.png` | Striking, and needs no API key |
| 7 | `08_threat_intel.png` | |
| 8 | `09_speed_test.png` | |
| 9 | `04_app_traffic.png` | |
| 10 | `06_service_diag.png` | |

Filenames keep their capture-order prefixes so `--page <slug>` still round-trips
against `PAGES` in `tools/store_screenshots.py`.

## Not included

- `02_troubleshoot` — sparsest frame of the set (69% single-colour content region)
- `11_lab_mode` — Protocol Visualizer covers the education angle better

Both were captured and are reusable if a slot frees up.

## Known caveat

These show real network data: full MAC addresses and personal device/room names.
The Network Map page has a "Share (Sanitized PNG)" action; the capture path does
not use it. Decide whether that is acceptable before submitting.
