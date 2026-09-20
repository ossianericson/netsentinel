"""
packaging/version_info.py — Build the Windows VERSIONINFO resource for our PyInstaller exes.

Why this exists
---------------
None of the three shipped binaries carried a VERSIONINFO resource: no CompanyName,
no ProductName, no FileDescription, no FileVersion. Right-clicking NetSentinel.exe and
opening Properties showed no Details worth reading.

That is a reputation penalty on an unsigned binary. Microsoft Defender's dynamic test
flagged the v2.3.0 installer (winget PR #430336, `Validation-Defender-Error`) and cost
that submission three days; metadata-less PEs are part of the profile that invites it.
Populating it is free and cannot regress runtime behaviour.

Where the version comes from
----------------------------
`app.py`'s `setApplicationVersion("X.Y.Z")` — already the documented canonical source
(`tests/test_version_consistency.py::_canonical_version` uses this exact regex, and
RULE 11 makes `bump_version.py` responsible for keeping it current).

Deliberately NOT a generated `version_info.txt` that `bump_version.py` has to patch:
`_sub()` only *warns* on a no-match, so a 16th bump target could rot silently and ship
a stale version in the resource while every test stayed green. Reading the canonical
source at build time means there is nothing extra to keep in sync.

`_read_version()` raises rather than falling back to a placeholder. A build that cannot
determine its own version should fail loudly, not ship "0.0.0".
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

COMPANY_NAME = "NetSentinel Project"
PRODUCT_NAME = "NetSentinel"
COPYRIGHT = "Copyright (C) NetSentinel Project. MIT Licence."


def read_version() -> str:
    """Return "X.Y.Z" from app.py, or raise if it cannot be determined."""
    app_py = _ROOT / "app.py"
    try:
        text = app_py.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"cannot read {app_py} to determine the build version") from exc

    m = re.search(r'setApplicationVersion\(\s*"([^"]+)"\s*\)', text)
    if not m:
        raise RuntimeError(
            f"no setApplicationVersion(...) found in {app_py} - the canonical version "
            "source moved; update packaging/version_info.py to match"
        )
    return m.group(1)


def version_tuple(version: str) -> tuple[int, int, int, int]:
    """"2.3.0" -> (2, 3, 0, 0). Windows VERSIONINFO always wants four parts."""
    parts = [int(p) for p in version.split(".")]
    parts += [0] * (4 - len(parts))
    return tuple(parts[:4])  # type: ignore[return-value]


def build_version_info(*, internal_name: str, description: str):
    """Return a PyInstaller VSVersionInfo for one of our executables.

    Windows-only; the import lives inside the function so the specs can call this
    unguarded on macOS/Linux builds where `version=` is ignored anyway.
    """
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo,
        StringFileInfo,
        StringStruct,
        StringTable,
        VarFileInfo,
        VarStruct,
        VSVersionInfo,
    )

    version = read_version()
    vt = version_tuple(version)
    filename = internal_name if internal_name.endswith(".exe") else f"{internal_name}.exe"

    return VSVersionInfo(
        ffi=FixedFileInfo(
            filevers=vt,
            prodvers=vt,
            mask=0x3F,
            flags=0x0,
            OS=0x40004,      # VOS_NT_WINDOWS32
            fileType=0x1,    # VFT_APP
            subtype=0x0,
        ),
        kids=[
            StringFileInfo([
                # 040904B0 = US English, Unicode. Matches the encoding of these strings.
                StringTable("040904B0", [
                    StringStruct("CompanyName", COMPANY_NAME),
                    StringStruct("FileDescription", description),
                    StringStruct("FileVersion", version),
                    StringStruct("InternalName", internal_name),
                    StringStruct("LegalCopyright", COPYRIGHT),
                    StringStruct("OriginalFilename", filename),
                    StringStruct("ProductName", PRODUCT_NAME),
                    StringStruct("ProductVersion", version),
                ]),
            ]),
            VarFileInfo([VarStruct("Translation", [0x0409, 1200])]),
        ],
    )
