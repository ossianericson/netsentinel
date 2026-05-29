"""
TP-Link Deco mesh API client.

Public surface (MeshUnit, MeshClient, DecoMeshClient, detect_deco) uses
generic "mesh" field names so other mesh providers can follow the same
dataclass contract.

Authentication
--------------
Uses tplinkrouterc6u.TPLinkDecoClient which handles the 3-step LuCI auth
(keys → auth → login) with AES-CBC + RSA-PKCS1v15 signing, compatible with
XE75 firmware 1.3-1.4 and similar.

Password security
-----------------
Passwords are NEVER stored in files.  The caller (mesh_router_page) is
responsible for obtaining the password from the OS keychain (keyring) or
by prompting the user.  This module accepts the password only as a plain
string argument to __init__.
"""

from __future__ import annotations

import json
import logging
from base64 import b64decode
from dataclasses import dataclass
from typing import Dict, List, Optional

import requests
import requests.exceptions

log = logging.getLogger(__name__)

# ── Data contracts ─────────────────────────────────────────────────────────────

@dataclass
class MeshUnit:
    """A single mesh node (router or satellite)."""
    name: str
    mac:  str    # normalised lower  "60:83:e7:88:a6:c4"
    ip:   str
    role: str    # "master" | "slave" | "unknown"


@dataclass
class MeshClient:
    """A client device currently connected to the mesh network."""
    name:          str
    mac:           str
    ip:            str
    unit_mac:      str
    unit_name:     str
    band:          str    # "2.4G" | "5G" | "6G" | "Wired"
    upload_kbps:   float = 0.0
    download_kbps: float = 0.0


class MeshAuthError(Exception):
    """Raised when login to the mesh gateway fails."""


class MeshApiError(Exception):
    """Raised when an authenticated API call returns an error."""


# ── Band mapping ───────────────────────────────────────────────────────────────

_BAND_MAP = {
    "band2_4":    "2.4G",
    "band5":      "5G",
    "band5_1":    "5G",
    "band6":      "6G",
    "wired":      "Wired",
    "ethernet":   "Wired",
}


def _decode_name(s: str) -> str:
    """Deco encodes device/client names as base64 strings."""
    try:
        return b64decode(s).decode("utf-8", errors="replace")
    except Exception:
        return s


def _norm_mac(mac: str) -> str:
    return mac.replace("-", ":").lower().strip()


# ── TP-Link detect ─────────────────────────────────────────────────────────────

def detect_deco(host: str, timeout: float = 3.0) -> bool:
    """Return True if `host` responds to the Deco LuCI key-exchange endpoint."""
    try:
        r = requests.post(
            f"http://{host}/cgi-bin/luci/;stok=/login",
            params={"form": "keys"},
            json={"operation": "read"},
            timeout=timeout,
            allow_redirects=True,
        )
        if r.status_code != 200:
            return False
        body = r.json()
        result = body.get("result", {})
        return bool(result.get("password") or result.get("key"))
    except Exception:
        return False


# ── DecoMeshClient ─────────────────────────────────────────────────────────────

class DecoMeshClient:
    """
    TP-Link Deco local web-API client (XE75/X90 compatible).

    Wraps tplinkrouterc6u.TPLinkDecoClient to handle the full auth flow.
    Password is passed only at construction — credential storage is the
    caller's responsibility (use OS keychain).

    Example
    -------
        c = DecoMeshClient("192.168.68.1", password)
        units   = c.get_mesh_units()
        clients = c.get_all_clients(units=units)
    """

    def __init__(self, host: str, password: str, timeout: float = 15.0) -> None:
        self.host     = host
        self._timeout = int(timeout)
        self._client  = None
        self._password = password   # kept only until first successful login

    def _ensure_client(self) -> None:
        """Lazy-init and authenticate the underlying library client."""
        if self._client is not None:
            return
        try:
            from tplinkrouterc6u import TPLinkDecoClient
        except ImportError as exc:
            raise MeshAuthError(
                "DEPS: tplinkrouterc6u not installed. "
                "Run: pip install tplinkrouterc6u"
            ) from exc

        client = TPLinkDecoClient(
            f"http://{self.host}",
            self._password,
            timeout=self._timeout,
        )
        try:
            client.authorize()
        except Exception as exc:
            raise MeshAuthError(
                f"Deco login failed for {self.host}: {exc}\n"
                "Check that the password is correct (local admin password, "
                "not TP-Link cloud account)."
            ) from exc

        self._client = client
        self._password = ""   # discard from memory after login
        log.debug("Deco authenticated against %s  stok=%.8s...", self.host, client._stok)

    def login(self) -> str:
        """Authenticate and return the stok session token."""
        self._ensure_client()
        return self._client._stok

    # ── raw request helper ────────────────────────────────────────────────────

    def _request(self, path: str, payload: dict) -> dict:
        """Authenticated, AES-encrypted API request. Returns the result dict."""
        self._ensure_client()
        try:
            result = self._client.request(path, json.dumps(payload))
        except Exception as exc:
            raise MeshApiError(f"Deco API call /{path} failed: {exc}") from exc
        return result or {}

    # ── public interface ──────────────────────────────────────────────────────

    def get_mesh_units(self) -> List[MeshUnit]:
        """Return all Deco mesh nodes (master + slaves)."""
        data = self._request(
            "admin/device?form=device_list",
            {"operation": "read"},
        )
        units: List[MeshUnit] = []
        for d in data.get("device_list", []):
            raw_mac = d.get("mac", "")
            name    = (
                _decode_name(d.get("custom_nickname") or "")
                or d.get("nickname")
                or _norm_mac(raw_mac)
            )
            units.append(MeshUnit(
                name = name,
                mac  = _norm_mac(raw_mac),
                ip   = d.get("device_ip", ""),
                role = d.get("role", "unknown"),
            ))
        return units

    def get_all_clients(
        self,
        units: Optional[List[MeshUnit]] = None,
    ) -> List[MeshClient]:
        """
        Return all currently online clients with node assignment and
        real-time rates.  One API call per mesh node to get node assignment.

        Pass `units` to avoid a redundant device_list call.
        """
        if units is None:
            units = self.get_mesh_units()

        clients: List[MeshClient] = []
        seen_macs: set = set()

        for unit in units:
            # Query per-node MAC to get only clients attached to this unit
            raw_mac = unit.mac.replace(":", "-").upper()
            try:
                data = self._request(
                    "admin/client?form=client_list",
                    {"operation": "read", "params": {"device_mac": raw_mac}},
                )
            except MeshApiError as exc:
                log.warning("Could not fetch clients for %s (%s): %s",
                            unit.name, raw_mac, exc)
                continue

            for c in data.get("client_list", []):
                if not c.get("online", False):
                    continue
                mac = _norm_mac(c.get("mac", ""))
                if mac in seen_macs:
                    continue
                seen_macs.add(mac)

                conn_raw = (c.get("connection_type") or c.get("wire_type") or "").lower()
                band     = _BAND_MAP.get(conn_raw, conn_raw or "Unknown")
                if band == "Unknown" and c.get("wire_type", "").lower() == "wired":
                    band = "Wired"

                clients.append(MeshClient(
                    name          = _decode_name(c.get("name") or "") or mac,
                    mac           = mac,
                    ip            = c.get("ip", ""),
                    unit_mac      = unit.mac,
                    unit_name     = unit.name,
                    band          = band,
                    upload_kbps   = float(c.get("up_speed") or 0),
                    download_kbps = float(c.get("down_speed") or 0),
                ))

        return clients
