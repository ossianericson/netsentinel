"""
Plugin Registry — community plugin discovery and one-click install.

Fetches a JSON index of community plugins hosted on GitHub and downloads
individual plugin .py files into the local plugins directory.

Index format (array of objects)::

    [
      {
        "name":        "Open Port Reporter",
        "version":     "1.0.0",
        "description": "Lists devices with high-risk ports open.",
        "author":      "NetSentinel",
        "tags":        ["ports", "risk"],
        "url":         "https://raw.githubusercontent.com/.../open_port_reporter.py",
        "homepage":    "https://github.com/..."   // optional
      },
      ...
    ]

Public API::

    fetch_registry(url=REGISTRY_URL, timeout=10) -> List[RegistryEntry]
    install_plugin(entry, on_progress=None)       -> Path
    is_installed(entry)                           -> bool
    uninstall_plugin(entry)                       -> None
"""

from __future__ import annotations

import json
import logging
import re
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from modules.plugin_system import plugins_dir

log = logging.getLogger(__name__)

# Default hosted registry — points at the netsentinel-plugins GitHub repo.
# Users can override this in NetSentinel.ini under [plugins] registry_url=...
REGISTRY_URL = (
    "https://raw.githubusercontent.com/netsentinel/netsentinel-plugins"
    "/main/registry.json"
)

_SAFE_FILENAME_RE = re.compile(r"[^\w\-.]")


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class RegistryEntry:
    name:        str
    version:     str       = "?"
    description: str       = ""
    author:      str       = "Unknown"
    tags:        List[str] = field(default_factory=list)
    url:         str       = ""           # raw URL of the .py file
    homepage:    str       = ""           # human-readable project page
    sha256:      str       = ""           # optional hex digest; verified if non-empty

    @property
    def tag_str(self) -> str:
        return ", ".join(self.tags) if self.tags else "—"

    @property
    def filename(self) -> str:
        """Derive a safe local filename from name or the url basename."""
        if self.url:
            base = self.url.rstrip("/").rsplit("/", 1)[-1]
            if base.endswith(".py"):
                return base
        safe = _SAFE_FILENAME_RE.sub("_", self.name.lower()).strip("_") or "plugin"
        return safe + ".py"


# ── Network helpers ───────────────────────────────────────────────────────────

def _get(url: str, timeout: int = 10) -> bytes:
    """Minimal urllib GET with a descriptive User-Agent."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "NetSentinel-PluginRegistry/1.0"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return resp.read()


# ── Public API ────────────────────────────────────────────────────────────────

def fetch_registry(
    url:     str = REGISTRY_URL,
    timeout: int = 10,
) -> List[RegistryEntry]:
    """
    Download and parse the plugin index JSON.

    Returns a list of RegistryEntry objects, or raises on network / parse error.
    """
    raw = _get(url, timeout=timeout)
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, list):
        raise ValueError("Registry JSON root must be an array")
    entries = []
    for item in data:
        if not isinstance(item, dict):
            continue
        if not item.get("name") or not item.get("url"):
            continue          # skip malformed entries silently
        entries.append(RegistryEntry(
            name        = str(item["name"]),
            version     = str(item.get("version",     "?")),
            description = str(item.get("description", "")),
            author      = str(item.get("author",      "Unknown")),
            tags        = [str(t) for t in item.get("tags", [])],
            url         = str(item["url"]),
            homepage    = str(item.get("homepage",    "")),
            sha256      = str(item.get("sha256",      "")),
        ))
    return entries


def install_plugin(
    entry:       RegistryEntry,
    on_progress: Optional[Callable[[int, int], None]] = None,
) -> Path:
    """
    Download a plugin .py file into the local plugins directory.

    Parameters
    ----------
    entry       : the RegistryEntry to install.
    on_progress : optional callback(bytes_downloaded, total_bytes).
                  total_bytes may be -1 if Content-Length is unknown.

    Returns
    -------
    Path to the installed .py file.

    Raises
    ------
    ValueError  — if entry.url is empty or does not end with .py.
    urllib.error.URLError — on network failure.
    """
    if not entry.url:
        raise ValueError(f"Plugin '{entry.name}' has no download URL")
    if not entry.url.lower().endswith(".py"):
        raise ValueError(
            f"Plugin '{entry.name}' URL does not point to a .py file: {entry.url}"
        )

    dest_dir = plugins_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    # Windows MAX_PATH guard — truncate stem to 80 chars so the full
    # AppData path stays well under 260 characters.
    _fn   = entry.filename
    _stem = _fn[:-3] if _fn.endswith(".py") else _fn
    if len(_stem) > 80:
        _stem = _stem[:80]
    dest = dest_dir / (_stem + ".py")

    req = urllib.request.Request(
        entry.url,
        headers={"User-Agent": "NetSentinel-PluginRegistry/1.0"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
        total = int(resp.headers.get("Content-Length") or -1)
        chunk = 65536
        downloaded = 0
        buf = b""
        while True:
            block = resp.read(chunk)
            if not block:
                break
            buf += block
            downloaded += len(block)
            if on_progress:
                try:
                    on_progress(downloaded, total)
                except Exception:
                    pass  # non-fatal

    # Basic safety check — must look like a Python source file
    text = buf.decode("utf-8", errors="replace")
    if "PLUGIN_META" not in text:
        raise ValueError(
            f"Downloaded file for '{entry.name}' does not contain PLUGIN_META — "
            "refusing to install an unrecognised file."
        )

    # SHA-256 integrity check (when the registry entry provides a digest)
    if entry.sha256:
        import hashlib
        actual = hashlib.sha256(buf).hexdigest()
        if actual.lower() != entry.sha256.lower():
            raise ValueError(
                f"SHA-256 mismatch for '{entry.name}': "
                f"expected {entry.sha256}, got {actual}"
            )

    dest.write_bytes(buf)
    log.info("Plugin installed: %s → %s", entry.name, dest)
    return dest


def is_installed(entry: RegistryEntry) -> bool:
    """Return True if the plugin .py file already exists in plugins_dir()."""
    return (plugins_dir() / entry.filename).exists()


def uninstall_plugin(entry: RegistryEntry) -> None:
    """Remove an installed plugin file. No-op if not present."""
    p = plugins_dir() / entry.filename
    if p.exists():
        p.unlink()
        log.info("Plugin uninstalled: %s", entry.name)
