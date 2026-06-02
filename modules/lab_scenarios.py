"""Lab / scenario mode — scenario definitions and result serialisation."""

from __future__ import annotations

import datetime
import hashlib
import platform
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class LabStep:
    instruction: str
    scan_type: Optional[str]  # "rogue" | "dns" | "storm" | "subnet" | None (review step)
    hint: str
    solution: str


@dataclass
class LabScenario:
    id: str
    title: str
    goal: str
    effort: str  # "S" | "M" | "L"
    steps: List[LabStep]
    protocol: Optional[str] = None  # "ARP" | "DNS" | "TCP" | "DHCP" | "STP" | None


@dataclass
class LabResult:
    scenario_id: str
    scenario_title: str
    completed_at: str
    hints_used: int
    steps_completed: int
    steps_total: int
    findings: List[dict] = field(default_factory=list)
    verdict: str = "INCOMPLETE"  # "PASS" | "PARTIAL" | "INCOMPLETE"

    def to_dict(self) -> dict:
        machine_fp = hashlib.sha256(platform.node().encode()).hexdigest()[:16]
        return {
            "schema": "netsentinel-lab-result/1",
            "scenario_id": self.scenario_id,
            "scenario_title": self.scenario_title,
            "completed_at": self.completed_at,
            "hints_used": self.hints_used,
            "steps_completed": self.steps_completed,
            "steps_total": self.steps_total,
            "findings": self.findings,
            "verdict": self.verdict,
            "machine_fp": machine_fp,
        }


SCENARIOS: List[LabScenario] = [
    LabScenario(
        id="rogue_device",
        title="Find the Rogue Device",
        goal="Discover all devices on your network and identify any that are unknown or suspicious.",
        effort="M",
        protocol="ARP",
        steps=[
            LabStep(
                instruction="Click 'Run Check' to scan your network. NetSentinel will read the ARP table and check each device against its database.",
                scan_type="rogue",
                hint="The ARP table maps IP addresses to MAC addresses. Every device on your subnet must appear in it to communicate.",
                solution="A rogue device shows Risk = HIGH or UNKNOWN, or a vendor that does not match any expected device on your network.",
            ),
            LabStep(
                instruction="Review the device list. Can you identify which device (if any) is flagged as rogue? Note its IP address and vendor.",
                scan_type=None,
                hint="Sort by the Risk column. HIGH risk means the device's MAC OUI is not in the trusted database and it has no known hostname.",
                solution="The rogue device has Risk = HIGH and vendor = 'Unknown' or an unexpected manufacturer. Record the MAC address as evidence.",
            ),
        ],
    ),
    LabScenario(
        id="slow_dns",
        title="Diagnose Slow DNS",
        goal="Measure your DNS response times and identify whether slow name resolution is contributing to connectivity problems.",
        effort="M",
        protocol="DNS",
        steps=[
            LabStep(
                instruction="Click 'Run Check' to probe your DNS resolver. The scan runs for 60 seconds and measures ping and DNS latency in parallel.",
                scan_type="dns",
                hint="DNS latency above 100 ms is noticeable. Above 300 ms it slows every new page load even on a fast connection.",
                solution="High DNS latency means every new domain lookup adds that delay before the browser can start downloading.",
            ),
            LabStep(
                instruction="Review the result. Is average DNS latency above 100 ms? Are there ping outages that coincide with DNS failures?",
                scan_type=None,
                hint="A ping outage and DNS failure at the same timestamp means an upstream routing problem, not a device problem.",
                solution="If DNS is slow but pings are clean, try switching to 1.1.1.1 or 8.8.8.8. If both fail simultaneously, the fault is upstream with your ISP.",
            ),
        ],
    ),
    LabScenario(
        id="broadcast_storm",
        title="Identify the Broadcast Storm Source",
        goal="Listen for abnormal broadcast traffic and identify whether a broadcast storm is degrading your network.",
        effort="M",
        protocol="STP",
        steps=[
            LabStep(
                instruction="Click 'Run Check' to listen for broadcast packets for 6 seconds. Requires Npcap on Windows.",
                scan_type="storm",
                hint="A broadcast storm occurs when devices repeatedly forward the same frame, saturating the network. Usually caused by a loop or a misconfigured switch.",
                solution="A storm is detected when broadcast packets per second exceed the threshold. The top-source MAC is the device generating the flood.",
            ),
            LabStep(
                instruction="If a storm was detected, note the source MAC address. What vendor does it belong to? Which physical device is likely causing it?",
                scan_type=None,
                hint="Use the first 3 octets of the MAC (the OUI) to identify the vendor. Cross-reference with the Devices page to find the hostname and IP.",
                solution="Disconnect the identified device or the cable creating the loop. On managed switches, enable Spanning Tree Protocol (STP) to prevent future loops.",
            ),
        ],
    ),
    LabScenario(
        id="map_subnet",
        title="Map Your Subnet",
        goal="Build a complete picture of every device on your network: IP, MAC, vendor, and role.",
        effort="S",
        protocol="ARP",
        steps=[
            LabStep(
                instruction="Click 'Run Check' to load all devices from your most recent scan. If no scan has run yet, go to Overview and start one first.",
                scan_type="subnet",
                hint="A subnet is a logical network segment. All devices on a home /24 share the first three octets of their IP (e.g. 192.168.1.x).",
                solution="Your gateway is typically the lowest IP on the subnet — e.g. 192.168.1.1. All other devices fill the remaining addresses.",
            ),
            LabStep(
                instruction="From the device list, identify: (1) your gateway, (2) any device you do not recognise, (3) a device with an unexpected vendor.",
                scan_type=None,
                hint="The gateway has 'router' or 'gateway' in its hostname, or its IP ends in .1. Unknown devices have vendor = 'Unknown' or a blank hostname.",
                solution="Unknown devices should be investigated — they may be a neighbour on an open Wi-Fi, or a misconfigured IoT device. Authorise or block them from the Devices page.",
            ),
        ],
    ),
]


def get_scenario(scenario_id: str) -> Optional[LabScenario]:
    return next((s for s in SCENARIOS if s.id == scenario_id), None)
