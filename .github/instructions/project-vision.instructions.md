---
applyTo: "**"
---

# NetSentinel — Project Vision & Purpose

## What This Product Is

NetSentinel is a **professional-grade network security scanner and monitor** for Windows, macOS, and Linux. It is a desktop GUI application (PyQt6) targeting IT administrators, network engineers, and security-aware home lab users who need an enterprise-quality tool — not a toy.

The tool performs:
- **Layer 2 rogue device detection** — ARP scanning, MAC/OUI classification, rogue bridge (STP) detection
- **Broadcast storm analysis** — real-time packet capture and storm level measurement
- **WiFi network enumeration** — rogue SSIDs, co-channel interference
- **DNS & connectivity monitoring** — latency graphing, outage detection, DNS leak testing
- **Active security audit** — SYN/UDP port scanning, OS fingerprinting, CVE lookup, credential testing (requires admin)
- **Background network logging** — continuous ping/RTT/jitter/DNS logging with analysis
- **Network topology visualisation** — live matplotlib graph showing device relationships
- **IoT behaviour baselining** — detect devices going outside their normal behaviour

## Core Product Values

1. **Information density over decoration** — every pixel of screen space must carry useful data
2. **Professional, not playful** — the UI should feel like an enterprise monitoring tool, not a gaming dashboard
3. **Actionable output** — every scan result must include a clear severity indicator and remediation path
4. **Zero unnecessary friction** — one click to run, right-click to act, keyboard shortcuts everywhere

## Target Users

- IT administrators managing SMB/enterprise networks
- Security engineers doing periodic audits
- Home lab enthusiasts who want a real tool, not a script

## Non-Goals

- Do not add consumer-style gamification (glow effects, neon colours, oversized animations)
- Do not abstract away technical detail — show MAC addresses, full IP ranges, exact RTTs
- Do not add cloud sync, accounts, or telemetry
