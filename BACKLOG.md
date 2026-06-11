# NetSentinel — Backlog

## Status: Feature Complete

As of **v2.1.0** (2026-06-11), the NetSentinel feature set is complete.

The 9-hour overnight chaos run (June 2026) completed 10,001 UIA interactions across mild / moderate / wild chaos levels with zero application crashes and all 62 pages functional. The app is production-stable and ready for Microsoft Store submission.

All future development is **polish and user-requested changes only**:
- UX refinements and discoverability improvements
- Bug fixes and regression hardening
- Cross-feature cohesion glue
- Documentation accuracy

---

## Completed Items (condensed — see README.md changelog for detail)

### v2.1.0 (2026-06-11) — Sprint 5
- ✅ What's Wrong? "A service is unreachable" symptom tile with service combobox (`diagnosis_page.py`)
- ✅ `service_page.py` "Diagnose →" context action — navigates to Service Diagnostics pre-loaded for the selected service
- ✅ Service-unreachable tile navigates correctly to `ServiceDiagnosticsPage` on finding click
- ✅ Vendor/type enrichment now shows on first scan (async OUI lookup for Unknown devices)
- ✅ `service_diagnostics_probes.py`: IPv6 cast fix, `CREATE_NO_WINDOW` guard, traceroute host reference fix

### v2.0.0 (2026-06-11) — Sprints 1–4
- ✅ Sprint 1: Device identification improvements — vendor/type field enrichment; improved gateway ARP reliability
- ✅ Sprint 2: `modules/service_mapper.py` — device_type/vendor → `ServiceInfo` list engine
- ✅ Sprint 3: Service connectivity diagnostics engine — `modules/service_diagnostics.py` (catalog, `DiagnosticEngine`, failure-layer classification) + `modules/service_diagnostics_probes.py` (DNS/TCP/HTTPS/ICMP/traceroute probes) + `workers/service_diagnostics_worker.py`
- ✅ Sprint 4: `ui/pages/service_diagnostics_page.py` — Service Diagnostics page in Monitor section; service picker, traceroute toggle, live probe results with failure-layer verdict

### v1.9.99 (2026-06-11)
- ✅ Fixed `RPC_E_WRONG_THREAD` crash in snap-layout maximize button (`ui/header.py`)
- ✅ Fixed Deco plugin crash loop on app restart (`app.py` pre-import of `tplinkrouterc6u`)
- ✅ Monkey test health-monitor timeout raised to 45 s (`tools/monkey_test.py`)
- ✅ Eliminated linear memory leak in navigation animations and chart redraws

### v1.9.95–v1.9.98
- ✅ Validated 10,001 UIA chaos interactions — 0 crashes (Microsoft Store ready)
- ✅ CVE Tracker empty state + Threat Intel cross-navigation
- ✅ Feature Guide group mapping corrections (8 entries fixed)

### Earlier sprints (v1.9.40–v1.9.94)
- ✅ All features in the "Implemented Features" section of `CLAUDE.md`
- ✅ 3,099-test suite stabilised
- ✅ Dashboard decomposition complete (13,483 → 1,967 lines)
- ✅ Guided tour, onboarding rewrite
- ✅ CodeQL hardening

---

## Next Session Queue

No outstanding backlog items. Take new user-requested features or bug reports as they arrive.
