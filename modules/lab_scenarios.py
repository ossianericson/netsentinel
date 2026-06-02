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
    LabScenario(
        id="trace_dns_resolvers",
        title="Measure Your DNS Resolver Speed",
        goal="Compare your DNS resolver's latency and understand why DNS speed affects every website you visit.",
        effort="M",
        protocol="DNS",
        steps=[
            LabStep(
                instruction="Click 'Run Check' to measure your current DNS resolver's latency. The scan runs for 30–60 seconds and samples DNS lookups in parallel with ping.",
                scan_type="dns",
                hint="DNS resolvers translate domain names (google.com) into IP addresses. Every new website visit starts with a DNS lookup — even on a fast connection, a slow resolver adds noticeable delay.",
                solution="Average DNS latency under 50 ms is excellent. 50–150 ms is normal. Above 150 ms, a faster resolver like 1.1.1.1 (Cloudflare) or 8.8.8.8 (Google) will noticeably improve browsing speed.",
            ),
            LabStep(
                instruction="Review the results. Is DNS latency higher than ping latency? A large gap means the resolver is slow. Note what DNS resolver IP your network is currently using.",
                scan_type=None,
                hint="Your DNS resolver IP is shown on the DNS & Stability page. ISP-assigned resolvers are often slower than public alternatives because they do not use Anycast routing.",
                solution="To change DNS: log in to your router's admin page and update the DNS server field to 1.1.1.1 (primary) and 8.8.8.8 (secondary). Changing it on the router fixes all devices at once.",
            ),
        ],
    ),
    LabScenario(
        id="find_open_port",
        title="Find an Open Port",
        goal="Run a port scan against your gateway and identify which services are accessible from inside your network.",
        effort="M",
        protocol="TCP",
        steps=[
            LabStep(
                instruction="Click 'Run Check' to scan common TCP ports on your gateway. NetSentinel tests well-known ports without requiring administrator privileges.",
                scan_type="port",
                hint="A port is an endpoint number that allows multiple services to share one IP address. Port 80 is HTTP, 443 is HTTPS, 22 is SSH, 23 is Telnet. Open ports are potential attack surfaces.",
                solution="Every open port is a service accepting connections. Ports 80/443 on a router usually mean the admin panel is exposed. Port 23 (Telnet) is critical risk — it sends credentials in plain text.",
            ),
            LabStep(
                instruction="Review the open ports found. Which services do you recognise? Are any flagged HIGH risk? What would you do about them?",
                scan_type=None,
                hint="HIGH risk ports are ones with known vulnerabilities or weak authentication defaults: Telnet (23), FTP (21), SNMP (161). Log in to your router to disable any services you do not use.",
                solution="Disable unused services on your router: go to Administration > Services and disable anything you do not need. If Telnet is open, disable remote admin entirely or switch to SSH.",
            ),
        ],
    ),
    LabScenario(
        id="dhcp_conflict",
        title="Detect a DHCP Conflict",
        goal="Scan DHCP lease records and identify whether any two devices share the same IP address.",
        effort="S",
        protocol="DHCP",
        steps=[
            LabStep(
                instruction="Click 'Run Check' to read DHCP lease records. NetSentinel reads the ARP table and lease files to build a map of IP-to-MAC assignments.",
                scan_type="dhcp",
                hint="DHCP assigns IP addresses automatically. A conflict occurs when two devices claim the same IP — usually because a device was given a static IP that overlaps the DHCP pool. Symptoms include random disconnections.",
                solution="A conflict appears as two different MAC addresses assigned to the same IP. Look for rows where the same IP appears more than once with different MAC addresses.",
            ),
            LabStep(
                instruction="Review the lease list. Are there duplicate IPs? Is the server column consistent? Multiple DHCP server IPs could indicate a rogue DHCP server.",
                scan_type=None,
                hint="A rogue DHCP server shows a different server IP than your router's IP. It can redirect traffic by assigning different DNS settings to clients. Check the 'server' column in the results.",
                solution="If you see a rogue DHCP server IP that is not your router: locate and disconnect the device providing it. On managed switches, enable DHCP Snooping to block unauthorised DHCP offers.",
            ),
        ],
    ),
    LabScenario(
        id="measure_jitter",
        title="Measure Network Jitter",
        goal="Record ping round-trip times over 60 seconds and identify whether jitter is affecting your connection quality.",
        effort="M",
        protocol="DNS",
        steps=[
            LabStep(
                instruction="Click 'Run Check' to log RTT (round-trip time) and DNS latency over 60 seconds. NetSentinel samples both in parallel to separate network instability from DNS resolver problems.",
                scan_type="dns",
                hint="Jitter is the variation in packet arrival time. 20 ms ± 2 ms is stable. 20 ms ± 40 ms is high jitter — causing choppy VoIP, lag spikes in games, and video call stuttering.",
                solution="High jitter alongside normal average RTT means the link is congested or unstable. Check how many devices are downloading concurrently. On Wi-Fi, interference from neighbouring networks also causes jitter.",
            ),
            LabStep(
                instruction="Look at the outages count and DNS-only failures. If DNS failures appear without ping outages, the DNS resolver is intermittent. If both fail together, the network itself is dropping packets.",
                scan_type=None,
                hint="'DNS-only failures' = ping worked but DNS did not — points to a slow or flaky resolver, not the network. 'Outages' = both ping and DNS failed simultaneously — points to a connectivity problem.",
                solution="For DNS failures with ping success: change your DNS resolver on the router to 1.1.1.1. For simultaneous outages: contact your ISP with the outage count and timestamps from this scan as evidence.",
            ),
        ],
    ),
    LabScenario(
        id="identify_vendors",
        title="Identify Device Manufacturers",
        goal="Use OUI (Organisationally Unique Identifier) lookup to identify what kind of device each MAC address belongs to.",
        effort="S",
        protocol="ARP",
        steps=[
            LabStep(
                instruction="Click 'Run Check' to load all known devices and their manufacturer data. NetSentinel matches the first 3 bytes of each MAC address against its OUI database.",
                scan_type="subnet",
                hint="The first 3 octets of a MAC address (the OUI) identify the manufacturer. For example, B4:E9:4A belongs to Ubiquiti. Unknown vendor means the OUI is not in the database — common with newer IoT devices.",
                solution="Every device on your network should be identifiable. An 'Unknown' vendor combined with no hostname is a red flag — it may be a misconfigured IoT device or an intruder.",
            ),
            LabStep(
                instruction="From the list, find the vendor for each device. Can you match every device to something physical in your home or office? Note any you cannot explain.",
                scan_type=None,
                hint="Look for unexpected vendors: a phone manufacturer you do not own, an industrial IoT vendor, or a virtual machine platform (VMware, Parallels). These all have distinct OUI prefixes.",
                solution="Devices you cannot identify should be investigated. Go to the Devices page, right-click the device, and choose 'Block' to quarantine it while you investigate. Check your router's wireless client list for when it joined.",
            ),
        ],
    ),
    LabScenario(
        id="topology_walkthrough",
        title="Read a Network Topology Map",
        goal="Interpret the network topology diagram and identify the role of each device — gateway, client, server, and unknown.",
        effort="S",
        protocol="ARP",
        steps=[
            LabStep(
                instruction="Click 'Run Check' to load your network's device list. Once loaded, navigate to the Network Map page (Discover section) to see the topology diagram.",
                scan_type="subnet",
                hint="The topology diagram shows your network as a graph. The central node is usually your gateway (router). Devices connect through it. A device with many connections but no known hostname could be an undocumented switch.",
                solution="Your gateway is the device with the most connections and typically has an IP ending in .1. Workstations and phones connect through it. Devices with many connections may be secondary switches or access points.",
            ),
            LabStep(
                instruction="In the device list below, identify: (1) your gateway IP, (2) any device with vendor 'Unknown', (3) a device whose role you cannot determine. Record its IP and MAC.",
                scan_type=None,
                hint="On the Network Map page, you can hover over any node to see its IP, MAC, and vendor. Nodes not directly connected to the gateway may be behind a secondary switch or access point.",
                solution="Unknown devices at the network edge are often IoT devices like smart TVs or security cameras. Go to the Devices page to label and track them. Labelling all devices is the first step in a network audit.",
            ),
        ],
    ),
]


def get_scenario(scenario_id: str) -> Optional[LabScenario]:
    return next((s for s in SCENARIOS if s.id == scenario_id), None)
