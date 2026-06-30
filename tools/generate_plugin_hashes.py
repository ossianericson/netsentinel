"""
Generate data/plugin_hashes.json — SHA-256 hashes of all bundled plugins (P4-2).

Run at build time (before PyInstaller / release):
    python tools/generate_plugin_hashes.py

Updates data/plugin_hashes.json in place.  The file is checked at runtime by
modules/plugin_tools.verify_signature() to detect tampered bundled plugins.
Only bundled plugins (in plugins/) are signed; user-added plugins are not.
"""

import hashlib
import json
import sys
from pathlib import Path

ROOT        = Path(__file__).parent.parent
PLUGINS_DIR = ROOT / "plugins"
OUT_FILE    = ROOT / "data" / "plugin_hashes.json"


def main() -> None:
    if not PLUGINS_DIR.is_dir():
        print(f"Error: plugins/ directory not found at {PLUGINS_DIR}", file=sys.stderr)
        sys.exit(1)

    hashes: dict[str, str] = {}
    for pyf in sorted(PLUGINS_DIR.glob("*.py")):
        if pyf.name.startswith("_"):
            continue
        # Normalise CRLF→LF before hashing so build-time digests match the
        # runtime check in modules.plugin_tools.verify_signature() regardless of
        # the checkout's line endings (Windows CRLF vs Linux/macOS LF).
        normalised = pyf.read_bytes().replace(b"\r\n", b"\n")
        sha256 = hashlib.sha256(normalised).hexdigest()
        hashes[pyf.name] = sha256
        print(f"  {pyf.name:<40}  {sha256[:16]}…")

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(
        json.dumps(hashes, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"\nOK  {len(hashes)} plugin hashes written to {OUT_FILE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
