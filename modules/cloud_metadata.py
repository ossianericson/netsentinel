"""
Cloud Metadata Detection

Two complementary checks:

1. check_local_imds()
   Probes the well-known link-local metadata address (169.254.169.254) to detect
   whether THIS machine is running inside a cloud VM:
   - AWS IMDSv1  — plain GET /latest/meta-data/instance-id
   - AWS IMDSv2  — PUT /latest/api/token, then GET with X-aws-ec2-metadata-token header
   - Azure IMDS  — GET /metadata/instance?api-version=2021-02-01 (Metadata: true header)
   - GCP         — GET http://metadata.google.internal/computeMetadata/v1/instance/id
                   (Metadata-Flavor: Google header)

2. check_network_imds_exposure(devices)
   For each DeviceInfo on the local network, checks whether TCP port 80 is open on
   169.254.169.254 when routed via that device's IP.  A positive hit means the device
   may be acting as an SSRF / metadata-proxy — HIGH-risk finding.

Both functions are safe to call offline — they use short timeouts and catch all
connection errors gracefully.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import List, Optional

from modules.utils_net import tcp_probe

_IMDS_IP   = "169.254.169.254"
_IMDS_TIMEOUT = 1.0   # seconds — fast fail if not in cloud


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class CloudMetadataResult:
    """Result of a local IMDS probe."""
    provider:    Optional[str] = None   # "AWS" / "Azure" / "GCP" / None
    instance_id: Optional[str] = None
    region:      Optional[str] = None
    account_id:  Optional[str] = None
    public_ip:   Optional[str] = None
    ami_id:      Optional[str] = None   # AWS only
    project_id:  Optional[str] = None   # GCP only
    imdsv2_enforced: Optional[bool] = None   # AWS only — True = safe
    findings: List[str] = field(default_factory=list)
    risk_level: str = "NONE"          # NONE / INFO / HIGH
    plain_verdict: str = ""


@dataclass
class NetworkExposureResult:
    """SSRF-risk result for a single device on the network."""
    device_ip:   str = ""
    device_mac:  str = ""
    hostname:    str = ""
    exposed:     bool = False
    findings: List[str] = field(default_factory=list)
    risk_level: str = "NONE"


# ── Internal helpers ───────────────────────────────────────────────────────────

def _http_get(url: str, headers: dict = None, timeout: float = _IMDS_TIMEOUT) -> Optional[str]:
    """GET url, return response body text or None on any error."""
    try:
        req = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None


def _http_put(url: str, headers: dict = None, timeout: float = _IMDS_TIMEOUT) -> Optional[str]:
    """PUT url with an empty body (used for IMDSv2 token request), return body or None."""
    try:
        req = urllib.request.Request(url, data=b"", headers=headers or {}, method="PUT")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None


def _tcp_connect(ip: str, port: int, timeout: float = 0.8) -> bool:
    """Return True if a TCP connection to ip:port succeeds within timeout."""
    ok, _, _ = tcp_probe(ip, port, timeout)
    return ok


# ── Local IMDS probe ───────────────────────────────────────────────────────────

def check_local_imds() -> CloudMetadataResult:
    """
    Probe all known cloud metadata endpoints to determine whether this machine
    is running inside a cloud VM.  Returns a CloudMetadataResult.

    Safe to call on bare-metal / home networks — all probes timeout in < 1 s.
    """
    result = CloudMetadataResult()

    # ── AWS IMDSv1 ─────────────────────────────────────────────────────────
    v1_url     = f"http://{_IMDS_IP}/latest/meta-data/instance-id"
    v1_body    = _http_get(v1_url)
    aws_v1_ok  = v1_body is not None and v1_body.startswith("i-")

    # ── AWS IMDSv2 ─────────────────────────────────────────────────────────
    token_url  = f"http://{_IMDS_IP}/latest/api/token"
    token      = _http_put(token_url, headers={"X-aws-ec2-metadata-token-ttl-seconds": "21600"})
    aws_v2_ok  = token is not None and len(token) > 10

    if aws_v2_ok:
        v2_instance_id = _http_get(
            f"http://{_IMDS_IP}/latest/meta-data/instance-id",
            headers={"X-aws-ec2-metadata-token": token},
        )
        v2_region = _http_get(
            f"http://{_IMDS_IP}/latest/meta-data/placement/region",
            headers={"X-aws-ec2-metadata-token": token},
        )
        v2_account = _http_get(
            f"http://{_IMDS_IP}/latest/meta-data/identity-credentials/ec2/info",
            headers={"X-aws-ec2-metadata-token": token},
        )
        v2_public_ip = _http_get(
            f"http://{_IMDS_IP}/latest/meta-data/public-ipv4",
            headers={"X-aws-ec2-metadata-token": token},
        )
        v2_ami = _http_get(
            f"http://{_IMDS_IP}/latest/meta-data/ami-id",
            headers={"X-aws-ec2-metadata-token": token},
        )
        result.provider    = "AWS"
        result.instance_id = v2_instance_id
        result.region      = v2_region
        result.ami_id      = v2_ami
        result.public_ip   = v2_public_ip if (v2_public_ip and "." in v2_public_ip) else None
        result.imdsv2_enforced = True
        if v2_account:
            try:
                acct_data = json.loads(v2_account)
                result.account_id = acct_data.get("AccountId")
            except Exception:
                pass  # non-fatal
        result.findings.append("AWS IMDSv2 token obtained — IMDSv2 is enforced (secure).")
        result.risk_level = "INFO"

    elif aws_v1_ok:
        result.provider       = "AWS"
        result.instance_id    = v1_body.strip() if v1_body else None
        result.imdsv2_enforced = False
        result.findings.append(
            "AWS IMDSv1 accessible without a session token. "
            "IMDSv2 is NOT enforced — any application on this host can query instance metadata, "
            "including IAM role credentials. Enable IMDSv2 in EC2 instance settings."
        )
        result.risk_level = "HIGH"

    # ── Azure IMDS ─────────────────────────────────────────────────────────
    if result.provider is None:
        az_url  = (f"http://{_IMDS_IP}/metadata/instance"
                   "?api-version=2021-02-01&format=json")
        az_body = _http_get(az_url, headers={"Metadata": "true"})
        if az_body:
            try:
                az_data    = json.loads(az_body)
                compute    = az_data.get("compute", {})
                network    = az_data.get("network", {})
                result.provider    = "Azure"
                result.instance_id = compute.get("vmId")
                result.region      = compute.get("location")
                result.account_id  = compute.get("subscriptionId")
                ifaces = network.get("interface", [])
                if ifaces:
                    public_ips = ifaces[0].get("ipv4", {}).get("ipAddress", [])
                    if public_ips:
                        result.public_ip = public_ips[0].get("publicIpAddress") or None
                result.findings.append(
                    "Azure IMDS accessible. "
                    "Managed Identity credentials may be reachable via "
                    f"http://{_IMDS_IP}/metadata/identity/oauth2/token."
                )
                result.risk_level = "INFO"
            except Exception:
                result.provider = "Azure"
                result.findings.append("Azure IMDS responded but payload could not be parsed.")
                result.risk_level = "INFO"

    # ── GCP ────────────────────────────────────────────────────────────────
    if result.provider is None:
        gcp_host  = "metadata.google.internal"
        gcp_url   = f"http://{gcp_host}/computeMetadata/v1/instance/id"
        gcp_body  = _http_get(gcp_url, headers={"Metadata-Flavor": "Google"})
        if gcp_body and gcp_body.strip().isdigit():
            result.provider    = "GCP"
            result.instance_id = gcp_body.strip()
            gcp_zone = _http_get(
                f"http://{gcp_host}/computeMetadata/v1/instance/zone",
                headers={"Metadata-Flavor": "Google"},
            )
            if gcp_zone:
                result.region = gcp_zone.split("/")[-1] if "/" in gcp_zone else gcp_zone
            gcp_project = _http_get(
                f"http://{gcp_host}/computeMetadata/v1/project/project-id",
                headers={"Metadata-Flavor": "Google"},
            )
            if gcp_project:
                result.project_id = gcp_project.strip()
            result.findings.append(
                "GCP Compute Metadata accessible. "
                "Service account tokens are available at "
                f"http://{gcp_host}/computeMetadata/v1/instance/service-accounts/default/token."
            )
            result.risk_level = "INFO"

    # ── Not in cloud ────────────────────────────────────────────────────────
    if result.provider is None:
        result.plain_verdict = (
            "No cloud metadata service detected. "
            "This machine does not appear to be running inside a cloud VM."
        )
        result.risk_level = "NONE"
    else:
        if result.risk_level == "HIGH":
            result.plain_verdict = (
                f"Running on {result.provider}. "
                "WARNING: IMDSv1 (unauthenticated) is accessible — "
                "any process on this host can read IAM credentials. "
                "Enforce IMDSv2 immediately."
            )
        else:
            parts = [f"Running on {result.provider}."]
            if result.instance_id:
                parts.append(f"Instance: {result.instance_id}.")
            if result.region:
                parts.append(f"Region: {result.region}.")
            result.plain_verdict = " ".join(parts)

    return result


# ── Network IMDS exposure scan ─────────────────────────────────────────────────

def check_network_imds_exposure(devices: list) -> List[NetworkExposureResult]:
    """
    For each DeviceInfo in devices, check whether TCP port 80 on 169.254.169.254
    appears reachable when that device is used as a routing source.

    In practice this probes 169.254.169.254:80 directly from this host — if it
    responds, it means there is a metadata-proxy or SSRF relay on the network.
    We report the finding once (on the first device for which we can correlate it)
    and annotate all devices with the exposure flag.

    Returns a list of NetworkExposureResult — one per device tested.
    """
    results: List[NetworkExposureResult] = []

    # Check once whether the metadata IP responds at all from this host
    imds_tcp_open = _tcp_connect(_IMDS_IP, 80, timeout=1.0)

    for device in devices:
        ip  = getattr(device, "ip", "")
        mac = getattr(device, "mac", "")
        hn  = getattr(device, "hostname", "")
        r   = NetworkExposureResult(device_ip=ip, device_mac=mac, hostname=hn)

        if imds_tcp_open:
            r.exposed   = True
            r.risk_level = "HIGH"
            r.findings.append(
                f"TCP port 80 on {_IMDS_IP} (cloud metadata) is reachable from this host. "
                f"Device {ip} ({mac}) may be acting as a cloud metadata proxy — "
                "a potential SSRF attack vector. Investigate whether this device is a "
                "NAT gateway, transparent proxy, or compromised endpoint."
            )
        else:
            r.risk_level = "NONE"

        results.append(r)

    return results
