"""
NetSentinel Plugin Bundle — .nspkg format (P3-5)

A .nspkg file is a ZIP archive containing:
  plugin.py      — the hardware plugin script (required)
  manifest.json  — metadata: name, version, author, pypi_deps, min_ns_version (required)
  icon.png        — 64×64 plugin icon (optional)
  README.md       — usage notes (optional)

Public API
──────────
  unpack_nspkg(nspkg_path, dest_dir) -> (plugin_path, manifest)
  validate_manifest(manifest)         -> list[str]   # list of error strings
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

# Fields that manifest.json must contain
_REQUIRED_MANIFEST_KEYS = ("name", "version", "author")

# Minimum manifest schema understood by this version
_MANIFEST_VERSION = "1"


def validate_manifest(manifest: dict[str, Any]) -> list[str]:
    """Return a (possibly empty) list of error strings for a manifest dict."""
    errors: list[str] = []
    for key in _REQUIRED_MANIFEST_KEYS:
        if key not in manifest or not manifest[key]:
            errors.append(f"manifest.json missing required field: '{key}'")

    version = manifest.get("version", "")
    if version and not isinstance(version, str):
        errors.append("manifest 'version' must be a string")

    pypi = manifest.get("pypi_deps", [])
    if not isinstance(pypi, list):
        errors.append("manifest 'pypi_deps' must be a list of strings")

    min_ver = manifest.get("min_ns_version", "")
    if min_ver and not isinstance(min_ver, str):
        errors.append("manifest 'min_ns_version' must be a string")

    return errors


def unpack_nspkg(nspkg_path: str, dest_dir: Path) -> tuple[Path, dict]:
    """Unpack a .nspkg archive into dest_dir and return (plugin_path, manifest).

    Raises ValueError with a human-readable message on any validation failure.
    The dest_dir is created if it does not exist.
    """
    p = Path(nspkg_path)
    if not p.exists():
        raise ValueError(f"File not found: {nspkg_path}")

    if not zipfile.is_zipfile(str(p)):
        raise ValueError(f"Not a valid .nspkg (ZIP) file: {p.name}")

    with zipfile.ZipFile(str(p), "r") as zf:
        names = zf.namelist()

        # Validate required members
        if "plugin.py" not in names:
            raise ValueError(".nspkg does not contain plugin.py")
        if "manifest.json" not in names:
            raise ValueError(".nspkg does not contain manifest.json")

        # Parse manifest
        try:
            manifest: dict = json.loads(zf.read("manifest.json").decode("utf-8"))
        except Exception as exc:
            raise ValueError(f"Cannot parse manifest.json: {exc}") from exc

        errors = validate_manifest(manifest)
        if errors:
            raise ValueError("manifest.json invalid: " + "; ".join(errors))

        dest_dir.mkdir(parents=True, exist_ok=True)

        # Extract plugin.py
        plugin_source = zf.read("plugin.py")
        plugin_dest = dest_dir / "plugin.py"

        # Use plugin name from manifest to avoid collisions
        safe_name = _safe_filename(manifest.get("name", "plugin"))
        plugin_dest = dest_dir / f"{safe_name}.py"
        plugin_dest.write_bytes(plugin_source)

        # Extract optional icon.png
        if "icon.png" in names:
            (dest_dir / f"{safe_name}_icon.png").write_bytes(zf.read("icon.png"))

    manifest["_nspkg_sha256"] = hashlib.sha256(p.read_bytes()).hexdigest()
    manifest["_plugin_filename"] = plugin_dest.name
    return plugin_dest, manifest


def _safe_filename(name: str) -> str:
    """Convert a plugin display name to a safe Python module filename."""
    import re
    safe = re.sub(r"[^a-zA-Z0-9_]", "_", name.lower().strip())
    safe = re.sub(r"_+", "_", safe).strip("_")
    return safe or "plugin"
