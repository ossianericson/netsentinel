"""The formatted application log every entry point configures (D4, finding F4).

Before this module there was **no root logging configuration anywhere in the tree**.
A ``log.warning`` therefore fell through to ``logging.lastResort``, which writes the
*message only* — no timestamp, no level, no logger name — and ``debug``/``info`` were
dropped entirely at the default ``WARNING`` root level. Seven sites across ``app.py``,
``ui/shutdown.py`` and ``ui/styles.py`` each carry their own ``FileHandler`` precisely
because a bare ``log.info()`` went nowhere.

The cost is diagnosability, and it is measurable: ``netsentinel_stderr.log``'s newest
2,000 lines still hold 785 ``Tight layout not applied`` warnings, and nothing in the
file can say whether current code wrote them or a build from three months ago sharing
the same append-only file.

Two contracts here are load-bearing beyond "it logs":

* **Encoding.** The handler is process-lifetime and its records carry hostnames, SSIDs,
  vendor names and ``%LOCALAPPDATA%`` paths, so a Devanagari username is enough to make
  an unencoded write fail deterministically (hi-IN Windows uses cp1252 as its ANSI
  codepage). Every test here runs on a non-Latin app-data path for that reason
  (RULE-WIN19 / RULE-WIN24), as ``test_crash_net.py`` does.
* **Additivity.** ``configure()`` must never clear handlers it did not install. pytest
  attaches its own to root, ``tools/debug_launch.py`` attaches another, and a
  ``basicConfig(force=True)``-style reset would silently blind both.
"""
from __future__ import annotations

import ast
import logging
import os
import pathlib
import re
import subprocess
import sys
import warnings

import pytest

_DEVANAGARI = "नमस्ते"
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

#: 2026-09-16 18:05:09,123 WARNING modules.availability_monitor: Availability monitor error: boom
_LINE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) "
    r"(?P<level>[A-Z]+) (?P<logger>[\w.]+): (?P<msg>.*)$"
)

#: Every logger whose level `configure()` owns. Restored wholesale between tests —
#: logging state is process-global and leaks into every later test module otherwise.
_TOUCHED = (
    "", "app", "cli", "svc", "__main__", "modules", "ui", "workers",
    "netsentinel", "py.warnings", "qt",
)


@pytest.fixture
def appdata(tmp_path, monkeypatch):
    """Redirect the app-data dir, using a non-Latin path (see the module docstring)."""
    home = tmp_path / (_DEVANAGARI + "-home")
    target = home / "NetSentinel"
    target.mkdir(parents=True)
    monkeypatch.setenv("LOCALAPPDATA", str(home))
    monkeypatch.setattr("modules.utils.get_app_data_dir", lambda: target)
    return target


@pytest.fixture(autouse=True)
def pristine_logging(monkeypatch):
    """Undo everything `configure()` touches, including handlers it added to root.

    Removing our handler is also what resets the module's idempotency state: it is
    detected by scanning root's handlers, not by a module-level flag, so there is no
    second copy of "did we configure yet" to get out of step with reality.
    """
    monkeypatch.delenv("NETSENTINEL_LOG_LEVEL", raising=False)
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_levels = {name: logging.getLogger(name).level for name in _TOUCHED}
    saved_showwarning = warnings.showwarning
    try:
        yield
    finally:
        for handler in list(root.handlers):
            if handler not in saved_handlers:
                root.removeHandler(handler)
                handler.close()
        root.handlers[:] = saved_handlers
        for name, level in saved_levels.items():
            logging.getLogger(name).setLevel(level)
        logging.captureWarnings(False)
        warnings.showwarning = saved_showwarning


def _lines(path: pathlib.Path) -> list:
    return [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _records(path: pathlib.Path) -> list:
    return [m.groupdict() for m in (_LINE.match(ln) for ln in _lines(path)) if m]


# ── The finding itself ───────────────────────────────────────────────────────────

def test_a_warning_carries_a_timestamp_a_level_and_a_logger(appdata):
    """F4: this exact record used to reach stderr as 'Availability monitor error: boom'."""
    from modules import app_logging

    path = app_logging.configure(app_version="2.3.0")
    assert path, "configure() could not open the log at all"
    logging.getLogger("modules.availability_monitor").warning(
        "%s monitor error: %s", "Availability", "boom"
    )

    written = [r for r in _records(pathlib.Path(path)) if "boom" in r["msg"]]
    assert written, f"the warning never reached {path}: {_lines(pathlib.Path(path))}"
    assert written[0]["level"] == "WARNING"
    assert written[0]["logger"] == "modules.availability_monitor"
    assert written[0]["msg"] == "Availability monitor error: boom"


def test_an_info_record_from_app_code_is_kept(appdata):
    """The other half of F4: info was dropped, so four modules grew private handlers."""
    from modules import app_logging

    path = app_logging.configure()
    logging.getLogger("ui.dashboard").info("theme switch took %dms", 42)

    assert any(r["msg"] == "theme switch took 42ms" for r in _records(pathlib.Path(path)))


def test_debug_is_dropped_by_default_and_kept_when_opted_in(appdata, monkeypatch):
    """D6 lets a broad handler discharge its duty with debug(exc_info=True) — so there
    has to be a way to turn debug on, and a reason it is not on by default."""
    from modules import app_logging

    path = pathlib.Path(app_logging.configure())
    logging.getLogger("modules.utils_net").debug("arp probe failed: %s", "timeout")
    assert not [r for r in _records(path) if "arp probe" in r["msg"]]

    for handler in list(logging.getLogger().handlers):
        if isinstance(handler, app_logging.AppLogHandler):
            logging.getLogger().removeHandler(handler)
            handler.close()
    monkeypatch.setenv("NETSENTINEL_LOG_LEVEL", "debug")
    app_logging.configure()
    logging.getLogger("modules.utils_net").debug("arp probe failed: %s", "timeout")

    kept = [r for r in _records(path) if "arp probe" in r["msg"]]
    assert kept and kept[0]["level"] == "DEBUG"


def test_a_third_party_library_contributes_warnings_but_not_chatter(appdata):
    """Root stays at WARNING; only NetSentinel's own package loggers drop to INFO.

    Turning root itself down to INFO pulls in matplotlib's font manager, urllib3's
    connection pool and PIL's plugin probing — thousands of lines an hour that bury
    the record this log exists to carry.
    """
    from modules import app_logging

    path = pathlib.Path(app_logging.configure())
    logging.getLogger("matplotlib.font_manager").info("findfont: score 10.05")
    logging.getLogger("matplotlib").warning("Tight layout not applied")

    assert not [r for r in _records(path) if "findfont" in r["msg"]]
    assert [r for r in _records(path) if "Tight layout" in r["msg"]]


# ── Contracts that keep it from breaking something else ──────────────────────────

def test_configure_twice_adds_one_handler_and_one_header(appdata):
    """Entry points can double-call (app.py --audit re-enters), and tests will."""
    from modules import app_logging

    first = app_logging.configure(app_version="2.3.0")
    second = app_logging.configure(app_version="2.3.0")

    assert first == second
    handlers = [
        h for h in logging.getLogger().handlers
        if isinstance(h, app_logging.AppLogHandler)
    ]
    assert len(handlers) == 1
    headers = [r for r in _records(pathlib.Path(first)) if "session start" in r["msg"]]
    assert len(headers) == 1


def test_the_session_header_names_the_version_channel_and_pid(appdata):
    """Which build wrote these lines is the question the log could never answer."""
    from modules import app_logging

    path = pathlib.Path(app_logging.configure(app_version="2.3.0"))
    header = [r for r in _records(path) if "session start" in r["msg"]]

    assert header, f"no session header in {_lines(path)}"
    msg = header[0]["msg"]
    assert "version=2.3.0" in msg
    assert "channel=source" in msg          # not frozen under pytest
    assert f"pid={os.getpid()}" in msg


def test_a_version_the_caller_does_not_know_is_recorded_as_unknown(appdata):
    """svc.py has no version constant of its own; the header must still be honest."""
    from modules import app_logging

    path = pathlib.Path(app_logging.configure())
    header = [r for r in _records(path) if "session start" in r["msg"]]

    assert "version=unknown" in header[0]["msg"]


def test_a_message_the_ansi_codepage_cannot_encode_is_still_written(appdata):
    """RULE-WIN19/24. The hostname of a device on the user's own LAN is enough."""
    from modules import app_logging

    path = pathlib.Path(app_logging.configure())
    logging.getLogger("modules.name_resolver").warning("resolved %s", _DEVANAGARI)

    assert any(_DEVANAGARI in r["msg"] for r in _records(path))


def test_handlers_installed_by_something_else_survive(appdata):
    """pytest and tools/debug_launch.py both attach their own root handler."""
    from modules import app_logging

    other = logging.StreamHandler(stream=sys.stdout)
    logging.getLogger().addHandler(other)
    try:
        app_logging.configure()
        assert other in logging.getLogger().handlers
    finally:
        logging.getLogger().removeHandler(other)


def test_a_log_that_cannot_be_opened_returns_none_and_never_raises(tmp_path, monkeypatch):
    """Housekeeping must never be the reason an app fails to launch (log_rotation's rule)."""
    from modules import app_logging

    blocker = tmp_path / "not-a-directory"
    blocker.write_text("", encoding="utf-8")
    monkeypatch.setattr("modules.utils.get_app_data_dir", lambda: blocker)

    assert app_logging.configure(app_version="2.3.0") is None
    logging.getLogger("modules.anything").warning("must not raise")


def test_a_python_warning_is_captured_with_the_same_shape(appdata):
    """matplotlib's 'Tight layout not applied' is a warnings.warn, not a log record.

    Without capture it reaches raw stderr and stays undatable — the 785-line shape in
    netsentinel_stderr.log that started this finding.
    """
    from modules import app_logging

    path = pathlib.Path(app_logging.configure())
    with warnings.catch_warnings():
        warnings.simplefilter("always")
        warnings.warn("Tight layout not applied", UserWarning, stacklevel=1)

    captured = [r for r in _records(path) if "Tight layout" in r["msg"]]
    assert captured and captured[0]["logger"] == "py.warnings"


# ── The repeating-record limiter (2.3) ───────────────────────────────────────────

def test_the_limiter_keeps_the_first_few_then_suppresses_the_flood(appdata):
    """The Deco per-node warning stays (owner decision 2026-07-16) — the flood does not."""
    from modules.app_logging import RepeatLimiter

    limiter = RepeatLimiter(max_per_window=3, window_s=300)
    log = logging.getLogger("modules.deco_client")
    records = [
        log.makeRecord(log.name, logging.WARNING, __file__, 1,
                       "Could not fetch clients for %s (%s): %s",
                       ("node-a", "192.168.1.5", "timeout"), None)
        for _ in range(10)
    ]

    assert sum(1 for r in records if limiter.filter(r)) == 3


def test_the_limiter_is_keyed_on_the_template_not_the_rendered_message(appdata):
    """Six nodes failing the same way is one shape; a different template is a different
    event and must not be muted by the first one's flood."""
    from modules.app_logging import RepeatLimiter

    limiter = RepeatLimiter(max_per_window=2, window_s=300)
    log = logging.getLogger("modules.deco_client")

    def rec(template, *args):
        return log.makeRecord(log.name, logging.WARNING, __file__, 1, template, args, None)

    same = [rec("Could not fetch clients for %s: %s", f"node-{i}", "timeout") for i in range(5)]
    other = rec("Deco login failed: %s", "401")

    assert sum(1 for r in same if limiter.filter(r)) == 2
    assert limiter.filter(other) is True


def test_the_next_window_says_how_many_were_suppressed(appdata, monkeypatch):
    """A silently dropped flood is the failure this whole audit is about."""
    from modules import app_logging
    from modules.app_logging import RepeatLimiter

    now = [1000.0]
    monkeypatch.setattr(app_logging.time, "monotonic", lambda: now[0])
    limiter = RepeatLimiter(max_per_window=1, window_s=60)
    log = logging.getLogger("modules.deco_client")

    def rec():
        return log.makeRecord(log.name, logging.WARNING, __file__, 1,
                              "Could not fetch clients for %s: %s", ("node-a", "timeout"), None)

    assert limiter.filter(rec()) is True
    for _ in range(9):
        assert limiter.filter(rec()) is False

    now[0] += 61.0
    survivor = rec()
    assert limiter.filter(survivor) is True
    assert "9" in survivor.getMessage(), survivor.getMessage()
    assert "suppressed" in survivor.getMessage()


def test_the_limiter_is_attached_to_the_handler_configure_installs(appdata):
    from modules import app_logging

    app_logging.configure()
    handler = next(
        h for h in logging.getLogger().handlers
        if isinstance(h, app_logging.AppLogHandler)
    )
    assert any(isinstance(f, app_logging.RepeatLimiter) for f in handler.filters)


# ── Rotation ownership (D-c) ─────────────────────────────────────────────────────

def test_the_app_log_is_bounded_by_log_rotation_and_not_exempt():
    """One owner, deliberately. A RotatingFileHandler would roll over mid-session, and
    NetSentinel.exe, NetSentinelCLI.exe and the service can all hold this file at once —
    on Windows the rename inside a rollover then fails while another process has it open.
    Bounding at startup, before any handle is opened, has no such race.
    """
    from modules.app_logging import LOG_NAME
    from modules.log_rotation import EXEMPT_LOGS

    assert LOG_NAME.endswith(".log")
    assert LOG_NAME not in EXEMPT_LOGS


def test_the_diagnostic_report_carries_the_app_log(appdata):
    from modules.app_logging import log_path
    from modules.diagnostic_report import _sink_paths

    assert log_path() in [path for _heading, path in _sink_paths()]


# ── Wiring guard ─────────────────────────────────────────────────────────────────
# RULE-WIN26 is about placement, not logic: a correct helper wired into one entry point
# leaves the other two binaries exactly as blind as before. That is the failure mode the
# console codec and the crash net both actually shipped with, so assert the call sites.

_ENTRY_POINTS = ("app.py", "cli.py", "svc.py")


def _calls_configure(source: str) -> bool:
    tree = ast.parse(source)
    aliases = {
        (a.asname or a.name)
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "modules.app_logging"
        for a in node.names
        if a.name == "configure"
    }
    if not aliases:
        return False
    return any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in aliases
        for n in ast.walk(tree)
    )


@pytest.mark.parametrize("entry_point", _ENTRY_POINTS)
def test_every_entry_point_configures_the_app_log(entry_point):
    src = (_REPO_ROOT / entry_point).read_text(encoding="utf-8")
    assert _calls_configure(src), (
        f"{entry_point} never calls modules.app_logging.configure(), so every "
        f"log.warning in this binary is still a bare message on stderr with no "
        f"timestamp, level or logger — and every log.info is still dropped."
    )


def test_the_wiring_guard_rejects_an_import_with_no_call():
    assert not _calls_configure("from modules.app_logging import configure\n")


@pytest.mark.parametrize("entry_point", ("cli", "svc"))
def test_importing_an_entry_point_does_not_open_the_log(entry_point, tmp_path):
    """Configuring at module scope makes `import cli` a file-creating side effect.

    Found live, not reasoned about: `tests/test_cli.py` spawns `python cli.py …`
    children, and the first version of this wiring had them create and append to
    netsentinel_app.log in the developer's REAL %LOCALAPPDATA% — conftest redirects
    that variable with `setdefault`, which never overrides a real Windows value. Any
    importer (a test, a tool, PyInstaller's own analysis pass) inherited a root
    handler capturing its records into the user's app-data directory.

    app.py is excluded: it configures inside main(), and importing it is already a
    heavyweight operation this test has no reason to perform.
    """
    home = tmp_path / "appdata"
    home.mkdir()
    env = dict(os.environ, LOCALAPPDATA=str(home), XDG_CONFIG_HOME=str(home))
    result = subprocess.run(
        [sys.executable, "-c", f"import {entry_point}"],
        cwd=str(_REPO_ROOT), capture_output=True, text=True, timeout=180, env=env,
    )

    assert result.returncode == 0, result.stderr
    written = list((home / "NetSentinel").glob("netsentinel_app.log"))
    assert not written, f"importing {entry_point}.py created {written}"


@pytest.mark.parametrize("entry_point", _ENTRY_POINTS)
def test_the_log_is_configured_after_rotation_not_before(entry_point):
    """Windows cannot rename a file that is open. rotate_logs() bounds every log at
    startup, so a handler opened first would exempt this one from rotation forever.
    """
    src = (_REPO_ROOT / entry_point).read_text(encoding="utf-8")
    rotate = src.index("rotate_logs")
    # The import, not the first mention: app.py's _smoke_test() list names
    # "modules.app_logging" hundreds of lines before main() runs anything, and a
    # bare-substring match read that string as "the log is opened here".
    configure = src.index("from modules.app_logging import")
    assert rotate < configure, (
        f"{entry_point} opens the app log before rotate_logs() runs, so the log it is "
        f"about to write to can never be rotated"
    )


# ── The Qt bridge (D-b) ──────────────────────────────────────────────────────────

def test_a_qt_warning_becomes_a_log_record_instead_of_a_bare_stderr_line(appdata):
    """'Unknown property cursor' and 'QProcess: Destroyed while process is still running'
    are Qt messages, not Python ones. They were written straight to stderr with no
    timestamp, which is why nobody can tell whether current code still emits them.
    """
    from PyQt6.QtCore import QtMsgType

    import app as app_module
    from modules import app_logging

    path = pathlib.Path(app_logging.configure())
    app_module._qt_message_handler(QtMsgType.QtWarningMsg, None, "Unknown property cursor")

    written = [r for r in _records(path) if "Unknown property cursor" in r["msg"]]
    assert written and written[0]["logger"] == "qt"
    assert written[0]["level"] == "WARNING"


def test_the_qt_font_metrics_noise_is_still_suppressed(appdata):
    """matplotlib's QtAgg backend measures with pixel-size QFonts; this fires per repaint."""
    from PyQt6.QtCore import QtMsgType

    import app as app_module
    from modules import app_logging

    path = pathlib.Path(app_logging.configure())
    app_module._qt_message_handler(QtMsgType.QtWarningMsg, None, "QFont::setPointSize: Point size <= 0")

    assert not [r for r in _records(path) if "Point size" in r["msg"]]
