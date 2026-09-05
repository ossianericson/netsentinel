"""One readable file out of four write-only crash sinks (B2).

The app has had a good crash net for a long time and it was entirely one-way:
`faulthandler` to `netsentinel_crash.log`, `sys.excepthook` and
`threading.excepthook` to `netsentinel_exceptions.log`, the shutdown drain to
`netsentinel_shutdown.log`, and the replaced stderr stream to
`netsentinel_stderr.log` — all landing under `%LOCALAPPDATA%` on a stranger's
machine, forever, with nothing in the UI that even says they exist. A1 and A2
added session records and an environment fingerprint beside them, and made the
same one-way trip.

This module reads all of it back out as a single file the user can look at and
decide to send. Two constraints shape everything here:

**Redaction happens before anything is written, and it happens to the untrusted
sections only.** The log tails are free text from a network scanner and go through
`modules.report_sanitizer`. The header does not, and that is deliberate: a
four-part version like `2.2.8.0` is a syntactically valid public IPv4 address, so
running the header through the sanitizer would redact the MSIX package version —
the one field that joins a local report to a Partner Center failure row.

**The crash log is tailed, never rotated.** `tools/monkey_test.py::_check_crash_log()`
is the only detector the project has for native SEH faults, and it works by
baselining that file's byte size and seeking to the offset. Bounding the report is
this module's job precisely so bounding the file never becomes anyone's.
"""
from __future__ import annotations

import json
import os
import sys

#: What has been taken out of the report, in the words shown to the user.
#:
#: Lives here rather than in the UI because it is a statement about what this
#: module does, and because all three surfaces that offer a report must make the
#: identical promise: the feedback dialog's checkbox, the Home unclean-exit
#: strip, and `app.py::_fatal()`. The last of those runs on the crash path and
#: must not import the UI layer to get a string.
REDACTION_NOTE = (
    "Addresses, MAC addresses, Wi-Fi names, your device names and your Windows "
    "username have been removed from it. Nothing was sent anywhere."
)

__all__ = [
    "CHANNELS",
    "REDACTION_NOTE",
    "TAIL_BYTES",
    "build_report",
    "install_channel",
    "known_device_names",
    "log_tail",
    "write_report",
]

#: Bytes kept from the end of each sink. Four sinks, so the log sections of a
#: report total at most ~64 KB — small enough to read and to attach, large enough
#: to hold the last several tracebacks including their frames.
TAIL_BYTES = 16 * 1024

#: JSON keys whose values name the user's own equipment. A bare `name` is
#: deliberately absent -- see known_device_names().
NAME_KEYS = frozenset({"hostname", "unit", "label", "device_name", "friendly_name", "ssid"})

#: Caps so the harvest stays cheap on the crash path. The real caches measure
#: 4-11 KB; anything far larger is not a device inventory.
MAX_NAME_CACHE_BYTES = 2 * 1024 * 1024
MAX_NAMES = 2000

#: Every install channel this module is willing to claim.
#:
#: Note what is absent. The plan for this work expected winget, Inno and portable
#: to be separable, but `.github/winget/NetSentinel.NetSentinel.installer.yaml`
#: declares `InstallerType: inno` and points at the same `NetSentinel-Setup` exe a
#: direct download runs — so a winget install and a hand-run installer produce the
#: same files in the same `{autopf}` directory with the same uninstall entry.
#: Reporting "winget" would be a guess wearing a measurement's clothes, which is
#: the habit this entire workstream exists to break.
CHANNELS = ("source", "store", "installed", "portable")


def log_tail(path: str, max_bytes: int = TAIL_BYTES) -> str:
    """The last *max_bytes* of a log, or "" if there is nothing readable there.

    Read as bytes and decoded here rather than opened in text mode, for two
    reasons that both matter on the machines this runs on. Text mode cannot seek
    to an arbitrary offset, and a log is not guaranteed to be UTF-8 — a child
    process's redirected output, or a file an older build wrote before RULE-WIN24
    named an encoding, can hold raw OEM-codepage bytes. `errors="replace"` means
    one bad byte costs one character instead of the entire report.

    Three of the four sinks do not exist on a machine that has never crashed, so
    a missing file is the normal case and returns "" rather than raising.
    """
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            if size > max_bytes:
                f.seek(size - max_bytes)
            raw = f.read()
    except OSError:
        return ""  # absent, locked, or gone since getsize — an empty section, not a failure

    text = raw.decode("utf-8", errors="replace")
    if size > max_bytes:
        # The seek landed mid-line. Half a line at the top of a section reads as
        # corruption to whoever opens the report, so drop it.
        newline = text.find("\n")
        text = text[newline + 1:] if newline != -1 else text
    return text


def _program_files_roots() -> list:
    """Every Program Files root this process can see, from the environment.

    Read from `%ProgramFiles%` and friends rather than matched as text: the
    literal string is not something to depend on across locales or WOW64, and
    hard-coding it would be RULE-WIN23's defect in a new place.
    """
    names = ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432")
    roots = []
    for name in names:
        value = os.environ.get(name)
        if value:
            roots.append(os.path.normcase(os.path.abspath(value)))
    return roots


def install_channel() -> str:
    """Which of `CHANNELS` this build came from.

    Worth carrying because the channels fail in different ways: a Store MSIX runs
    in an AppContainer with a virtualized registry and a read-only install
    directory, while a portable copy may be running from a folder — or a USB
    stick — the user can write to. "It crashed on launch" is a different claim in
    each, and the crash logs look identical.
    """
    if not getattr(sys, "frozen", False):
        return "source"

    from modules.utils import is_store_app

    try:
        if is_store_app():
            return "store"
    except Exception:
        pass  # identity probe failed; fall through to the path check rather than lose the field

    try:
        exe = os.path.normcase(os.path.abspath(sys.executable))
    except Exception:
        return "portable"  # no resolvable path: the weaker claim is the honest one
    for root in _program_files_roots():
        if exe.startswith(root + os.sep):
            return "installed"
    return "portable"


def _sink_paths() -> list:
    """The four crash sinks, as (heading, path) pairs, in the order they matter.

    Two of the paths come from `modules.crash_net`, which owns them. The other two
    are rebuilt here rather than imported: `netsentinel_shutdown.log` belongs to
    `ui/shutdown.py` and `netsentinel_stderr.log` to `app.py`, and `modules/`
    cannot import either (ARCH RULE 1). The names are the contract.
    """
    from modules.crash_net import crash_log_path, exceptions_log_path
    from modules.utils import get_app_data_dir

    app_dir = str(get_app_data_dir())
    return [
        ("Native faults (netsentinel_crash.log)", crash_log_path()),
        ("Unhandled exceptions (netsentinel_exceptions.log)", exceptions_log_path()),
        ("Shutdown drain (netsentinel_shutdown.log)",
         os.path.join(app_dir, "netsentinel_shutdown.log")),
        ("Standard error (netsentinel_stderr.log)",
         os.path.join(app_dir, "netsentinel_stderr.log")),
    ]


def _redact(text: str, ip_map: dict, names=None) -> str:
    """Scrub one untrusted chunk. The single redaction point in this module.

    `ip_map` is threaded through every call in one report so an address gets the
    same alias everywhere it appears — a report where the same host is three
    different aliases cannot be reasoned about. `names` is threaded for the same
    reason and gathered once per report, since the harvest touches the disk.
    """
    from modules.report_sanitizer import sanitize_text

    return sanitize_text(text, ip_map, names=names)


def _format_session(record: dict, ip_map: dict, names=None) -> str:
    """One line for one session that never reported a clean shutdown.

    `last_page` is redacted like any other free text even though it comes from a
    fixed set of nav labels. The value is not what is being protected; the habit
    is — an unredacted path into the report is one refactor away from carrying
    something else.
    """
    import datetime

    started = record.get("started_at")
    when = "unknown"
    if isinstance(started, (int, float)):
        when = datetime.datetime.fromtimestamp(started).isoformat(timespec="seconds")

    last_beat = record.get("last_beat")
    lived = ""
    if isinstance(started, (int, float)) and isinstance(last_beat, (int, float)):
        lived = f", alive at least {int(last_beat - started)}s"

    page = _redact(str(record.get("last_page") or "unknown"), ip_map, names)
    version = record.get("app_version") or "unknown"
    return f"- {when} - version {version}, last page: {page}{lived}"


def build_report(app_version: str = "") -> str:
    """The whole report, already redacted, as text.

    The header is deliberately **not** run through the sanitizer. Its two sources
    are the A2 fingerprint, whose fields are pinned by an allowlist test to
    locale and encoding facts and nothing about the network, and the version
    metadata — and `2.2.8.0` is a syntactically valid public IPv4 address, so
    sanitizing the header would redact the MSIX package version. That version is
    the join key between this file and a Partner Center failure row, which is the
    single thing the aggregate Store data is good for.

    Everything below the header is untrusted and goes through `_redact()`.
    """
    import datetime

    from modules.environment_fingerprint import fingerprint
    from modules.session_record import find_unclean_sessions

    ip_map: dict = {}
    # Gathered once: the harvest reads every JSON cache in app-data, and this
    # runs on the crash path.
    names = known_device_names()
    channel = install_channel()
    out = [
        "# NetSentinel diagnostic report",
        "",
        "Generated locally and never sent anywhere. Addresses, MACs, SSIDs, device",
        "names and the Windows account name have been removed; the rest is verbatim.",
        "",
        f"Generated:       {datetime.datetime.now().isoformat(timespec='seconds')}",
        f"App version:     {app_version or 'unknown'}",
        f"Install channel: {channel}",
    ]
    if channel == "store" and app_version:
        # Derived, not measured, and labelled as such: RULE-R4 pins the MSIX
        # Identity Version to exactly X.Y.Z.0 and bump_version.py generates it, so
        # this is the packageVersion a Partner Center row will carry.
        out.append(f"Store package:   {app_version}.0 (derived from the app version)")

    out += ["", "## Environment", ""]
    for key, value in fingerprint().items():
        out.append(f"{key}: {value}")

    out += ["", "## Sessions that never shut down cleanly", ""]
    unclean = find_unclean_sessions()
    if unclean:
        out += [_format_session(r, ip_map, names) for r in unclean]
    else:
        out.append("None recorded. Every previous run ended through a real shutdown.")

    for heading, path in _sink_paths():
        tail = log_tail(path)
        out += ["", f"## {heading}", ""]
        if tail.strip():
            out += ["```", _redact(tail, ip_map, names).rstrip(), "```"]
        else:
            out.append("Empty or not present.")

    return "\n".join(out) + "\n"


def write_report(app_version: str = "") -> str | None:
    """Write the report and return its path, or None if it could not be written.

    Lands in `get_app_data_dir()/reports/` (RULE 23) because that is the one
    folder the UI already knows how to open. The whole point of B2 is
    reachability — a file the user cannot find is no better than the four
    write-only sinks it was built to surface.

    `encoding="utf-8", errors="replace"` for the reason the report itself exists
    to describe: `open()` with no encoding uses the ANSI codepage under strict
    errors, and cp1252 cannot represent a Devanagari account name at all
    (RULE-WIN24) — the machine most in need of a report is the one where the
    default would raise.

    Unlike everything else in this workstream, a failure here is reported rather
    than swallowed. Instrumentation must not break the path it instruments, but
    this file was explicitly asked for by a person, and telling them a report
    exists when it does not is worse than telling them it failed.
    """
    import datetime

    from modules.utils import get_app_data_dir

    text = build_report(app_version=app_version)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    try:
        out_dir = os.path.join(str(get_app_data_dir()), "reports")
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, f"netsentinel-diagnostic-{stamp}.md")
        with open(path, "w", encoding="utf-8", errors="replace") as f:
            f.write(text)
    except OSError:
        return None
    return path


def known_device_names() -> set:
    """Device, client and room names this install knows about, for redaction.

    Read out of the app's own JSON caches under `get_app_data_dir()` rather than
    out of the database. `build_report()` is reachable from `app.py::_fatal()` on
    the crash path, where opening SQLite in an already-dying process is a
    lock-contention risk — and where there is no `MetricStore` to inject anyway
    (ARCH RULE 2: one instance, created in `app.py` and passed down; `modules/`
    must never construct its own).

    The key set is the whole design. A bare `name` is deliberately absent:
    `speedtest_servers_cache.json` files its ISP servers under it, and pulling a
    few hundred public server names into the denylist would redact `Telematica`
    out of every speed-test log line — destroying the diagnostic to protect
    nothing. Every key here identifies the user's own equipment.
    """
    names: set = set()
    try:
        from modules.utils import get_app_data_dir

        directory = str(get_app_data_dir())
        entries = os.listdir(directory)
    except OSError:
        return names  # no app-data dir: redact nothing extra rather than fail

    for entry in entries:
        if not entry.endswith(".json"):
            continue
        path = os.path.join(directory, entry)
        try:
            if os.path.getsize(path) > MAX_NAME_CACHE_BYTES:
                continue
            with open(path, encoding="utf-8", errors="replace") as f:
                _harvest_names(json.load(f), names)
        except (OSError, ValueError, RecursionError):
            continue  # a half-written cache is an ordinary artefact of the crash
    return names


def _harvest_names(node, out: set, depth: int = 0) -> None:
    """Walk a decoded JSON tree collecting values under the name keys.

    Walks rather than reading known paths because the same key appears at very
    different depths across caches — `mesh_enrichment_cache.json` nests
    `hostname` three levels down under a plugin id and a MAC, while
    `device_baseline.json` puts it one level down under a MAC.
    """
    if depth > 8 or len(out) >= MAX_NAMES:
        return
    if isinstance(node, dict):
        for key, value in node.items():
            if key in NAME_KEYS and isinstance(value, str) and value.strip():
                out.add(value.strip())
            else:
                _harvest_names(value, out, depth + 1)
    elif isinstance(node, list):
        for item in node:
            _harvest_names(item, out, depth + 1)
