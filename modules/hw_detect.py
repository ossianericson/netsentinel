"""
Hardware detection — probe a gateway IP and match against the plugin catalogue.

Used by the Hardware Hub to suggest plugin installation when NetSentinel can
identify the gateway make/model from HTTP fingerprints, OUI, or default IP.

All I/O is synchronous and should be called from a background thread.
"""

from __future__ import annotations

import json
import ssl
import sys
import urllib.request
from pathlib import Path
from typing import Optional


# ── Catalogue location ────────────────────────────────────────────────────────

def _catalogue_path() -> Path:
    """Return path to the bundled catalogue.json (works in dev and PyInstaller)."""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "data" / "catalogue.json"
    return Path(__file__).parent.parent / "data" / "catalogue.json"


_REMOTE_URL = (
    "https://raw.githubusercontent.com/ossianericson/netsentinel"
    "/main/data/catalogue.json"
)


def load_catalogue(try_remote: bool = False) -> dict:
    """Return catalogue dict.  Tries remote first if requested, falls back to bundled."""
    if try_remote:
        try:
            req = urllib.request.Request(
                _REMOTE_URL,
                headers={"User-Agent": "NetSentinel"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
                if data.get("version"):
                    return data
        except Exception:
            pass
    try:
        return json.loads(_catalogue_path().read_text("utf-8"))
    except Exception:
        return {"version": 1, "plugins": []}


# ── HTTP probing ──────────────────────────────────────────────────────────────

def _probe_http(ip: str, timeout: float = 3.0) -> tuple[str, dict[str, str]]:
    """Return (body_snippet, response_headers) from the device's web UI.

    Tries HTTP then HTTPS.  Returns empty strings on failure.
    """
    _ctx = ssl.create_default_context()
    _ctx.check_hostname = False
    _ctx.verify_mode = ssl.CERT_NONE

    for scheme in ("http", "https"):
        try:
            url = f"{scheme}://{ip}/"
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "NetSentinel/1.0"},
            )
            kw = {"timeout": timeout}
            if scheme == "https":
                kw["context"] = _ctx
            with urllib.request.urlopen(req, **kw) as resp:
                body    = resp.read(8192).decode("utf-8", errors="replace")
                headers = {k.lower(): v.lower() for k, v in resp.headers.items()}
                return body, headers
        except Exception:
            continue
    return "", {}


# ── OUI normalisation ─────────────────────────────────────────────────────────

def _norm_oui(mac: str) -> str:
    """Return upper-case colon-separated OUI prefix (first 3 octets)."""
    mac = mac.upper().replace("-", ":").strip()
    parts = mac.split(":")
    if len(parts) >= 3:
        return ":".join(parts[:3])
    return ""


# ── Scoring ───────────────────────────────────────────────────────────────────

def detect(
    ip: str,
    gateway_mac: Optional[str] = None,
    catalogue: Optional[dict] = None,
) -> list[dict]:
    """Probe *ip* and return catalogue matches ordered by descending confidence.

    Each result dict::

        {
          "plugin":     <catalogue entry dict>,
          "confidence": 0.0 – 1.0,
          "signals":    ["default IP 192.168.68.1", "page contains TP-Link", ...],
        }

    Confidence thresholds used by the UI:
        ≥ 0.7  → strong match  (green dot, offer one-click install)
        ≥ 0.4  → possible match (amber dot, show suggestion)
        < 0.4  → skip
    """
    if catalogue is None:
        catalogue = load_catalogue()

    body, headers = _probe_http(ip)
    body_lower = body.lower()
    oui = _norm_oui(gateway_mac) if gateway_mac else ""

    results: list[dict] = []

    for plugin in catalogue.get("plugins", []):
        fp         = plugin.get("fingerprints", {})
        confidence = 0.0
        signals: list[str] = []

        # ── Default IP (0.4) ─────────────────────────────────────────────────
        if ip in fp.get("default_ips", []):
            confidence += 0.4
            signals.append(f"gateway IP is {ip} (default for this device)")

        # ── HTTP title keywords (0.35 for first hit) ─────────────────────────
        for kw in fp.get("http_title_any", []):
            if kw.lower() in body_lower:
                confidence += 0.35
                signals.append(f'web UI contains "{kw}"')
                break

        # ── HTTP response headers (0.2 for first hit) ────────────────────────
        header_blob = " ".join(headers.values())
        for kw in fp.get("http_header_any", []):
            if kw.lower() in header_blob:
                confidence += 0.2
                signals.append(f'HTTP headers mention "{kw}"')
                break

        # ── OUI match (0.45) ─────────────────────────────────────────────────
        if oui:
            for prefix in fp.get("oui_prefixes", []):
                if oui == prefix.upper():
                    confidence += 0.45
                    signals.append(
                        f"MAC OUI {oui} matches {plugin.get('manufacturer', '')}"
                    )
                    break

        if confidence >= 0.4:
            results.append({
                "plugin":     plugin,
                "confidence": min(confidence, 1.0),
                "signals":    signals,
            })

    results.sort(key=lambda x: x["confidence"], reverse=True)
    return results


def already_installed(plugin_id: str, registered_paths: "list[str] | tuple" = ()) -> bool:
    """Return True if plugin_id appears in any of the registered plugin paths.

    Pass the path list from the UI layer; the module stays import-free.
    """
    return any(plugin_id in p.replace("\\", "/").split("/")[-1] for p in registered_paths)


def bundled_plugin_path(file_rel: str) -> Optional[Path]:
    """Return the absolute path to a bundled plugin file, or None if not found."""
    if hasattr(sys, "_MEIPASS"):
        p = Path(sys._MEIPASS) / file_rel
    else:
        p = Path(__file__).parent.parent / file_rel
    return p if p.exists() else None
