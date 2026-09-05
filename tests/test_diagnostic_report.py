"""The diagnostic report (B2) — the file that makes A1-A3's evidence reachable.

A1 records that a session died, A2 records what kind of machine it died on, and A3
widened the net that catches the death. All three write files into
`%LOCALAPPDATA%\\NetSentinel\\` on a stranger's machine and nothing has ever read
them back out. This module is the read-out: one file the user can look at and
choose to send.

Two properties decide whether it is worth anything:

* **Nothing sensitive survives.** This is a network scanner, so its logs carry the
  user's LAN. A report that leaks it will not be sent, and should not be.
* **The diagnostic survives anyway.** Redaction that also removes the version
  string, the codepage pair or the shape of a path leaves a file that is safe and
  useless.
"""
from __future__ import annotations

import os
import sys

import pytest

_DEVANAGARI = "\u0928\u092e\u0938\u094d\u0924\u0947"


@pytest.fixture
def frozen(monkeypatch):
    """Model a PyInstaller build. Every channel but `source` implies one."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr("modules.utils.is_store_app", lambda: False)
    return monkeypatch


class TestInstallChannel:
    """Where the binary came from, because the channels fail differently.

    A Store MSIX runs in an AppContainer with a virtualized registry and a
    read-only install directory; a portable copy may be sitting on a USB stick in
    a folder the user can write to. "It crashed on launch" means different things
    in each, and the crash logs look identical.
    """

    def test_a_source_checkout_is_reported_as_source(self, monkeypatch):
        """No `sys.frozen` means a developer, not a shipped binary."""
        from modules.diagnostic_report import install_channel

        monkeypatch.delattr(sys, "frozen", raising=False)
        assert install_channel() == "source"

    def test_a_packaged_build_is_reported_as_store(self, frozen):
        """`is_store_app()` is the packaged-identity syscall, not a path guess.

        It answers from `GetPackageFamilyName`, so it is right even for an MSIX
        staged somewhere unexpected — which a path heuristic would not be.
        """
        from modules.diagnostic_report import install_channel

        frozen.setattr("modules.utils.is_store_app", lambda: True)
        assert install_channel() == "store"

    def test_an_exe_under_program_files_is_reported_as_installed(self, frozen, tmp_path):
        """Read the Program Files roots from the environment, never as English text.

        `%ProgramFiles%` is where the Inno installer's `{autopf}` resolves to, and
        the variable is correct on every locale and on both 32- and 64-bit hosts.
        Matching the literal string "Program Files" would be RULE-WIN23's defect
        wearing a different hat.

        The root is a real directory built with `os.path.join` rather than a
        hard-coded `C:\\Program Files`. That literal is not a valid path off Windows —
        `abspath` treats it as a *relative* name and `os.sep` is `/` — so on Linux and
        macOS this assertion measured the test's own string handling rather than the
        lookup, and failed. What is under test is that the roots come from the
        environment, and that is platform-independent.
        """
        import os

        from modules.diagnostic_report import install_channel

        root = str(tmp_path / "ProgramFiles")
        frozen.setenv("ProgramFiles", root)
        frozen.setattr(
            sys, "executable", os.path.join(root, "NetSentinel", "NetSentinel.exe")
        )
        assert install_channel() == "installed"

    def test_an_exe_anywhere_else_is_reported_as_portable(self, frozen):
        """The onefile exe run from wherever the user dropped it."""
        from modules.diagnostic_report import install_channel

        frozen.setenv("ProgramFiles", "C:\\Program Files")
        frozen.setattr(sys, "executable", "D:\\tools\\NetSentinel.exe")
        assert install_channel() == "portable"

    def test_winget_and_inno_are_not_claimed_to_be_distinguishable(self):
        """A field that cannot be measured must not be reported as if it were.

        The plan expected winget, Inno and portable to be separable by path. They
        are not: `.github/winget/NetSentinel.NetSentinel.installer.yaml` declares
        `InstallerType: inno` and points at the very same `NetSentinel-Setup` exe
        a direct download runs, which installs to `{autopf}` either way. Both land
        in the identical directory with the identical uninstall registration, so
        "winget" as a reported channel would be a guess presented as a
        measurement — the exact failure the whole A2/B2 workstream exists to end.
        """
        from modules.diagnostic_report import CHANNELS

        assert "winget" not in CHANNELS
        assert set(CHANNELS) == {"source", "store", "installed", "portable"}


class TestLogTail:
    """Bounding the report is what lets the crash log stay append-only.

    `netsentinel_crash.log` measures 6.78 MB on the machine this was written on
    and must never be rotated: `tools/monkey_test.py::_check_crash_log()` is the
    project's only detector for native SEH faults, and it baselines that file's
    byte size and seeks to the offset. Shrinking it makes the shrink read as
    "nothing new" *and* leaves a stale, too-large baseline, so every later fault
    in that chaos run goes unseen. Tailing here is what makes rotating there
    unnecessary.
    """

    def test_only_the_end_of_an_oversized_log_is_returned(self, tmp_path):
        """The tail, not the head — the last thing that happened is the evidence."""
        from modules.diagnostic_report import log_tail

        log = tmp_path / "big.log"
        log.write_text("".join(f"line {i}\n" for i in range(5000)), encoding="utf-8")

        out = log_tail(str(log), max_bytes=2000)

        assert len(out.encode("utf-8")) <= 2000
        assert "line 4999" in out
        assert "line 0\n" not in out

    def test_the_leading_partial_line_is_dropped(self, tmp_path):
        """Seeking to a byte offset lands mid-line; half a line reads as corruption."""
        from modules.diagnostic_report import log_tail

        log = tmp_path / "part.log"
        log.write_text("aaaaaaaaaaaaaaaaaaaa\nbbbb\ncccc\n", encoding="utf-8")

        out = log_tail(str(log), max_bytes=12)

        assert not out.startswith("a")
        assert "cccc" in out

    def test_a_log_that_is_not_utf8_still_reads(self, tmp_path):
        """A log can hold OEM-codepage bytes, and this one must not be the thing that raises.

        `netsentinel_stderr.log` is written utf-8 (RULE-WIN24), but a child
        process's output redirected into it, or a file written by an older build
        before that fix, is not. Refusing to read the log because of one byte
        would lose the whole report on exactly the machine that needed it.
        """
        from modules.diagnostic_report import log_tail

        log = tmp_path / "oem.log"
        log.write_bytes(b"start\nRundk\xf6rper failed\nend\n")

        out = log_tail(str(log), max_bytes=4096)

        assert "start" in out and "end" in out

    def test_a_missing_log_yields_no_text_and_no_exception(self, tmp_path):
        """Three of the four sinks are absent on a healthy machine.

        A report generator that raises when there has been no crash is a report
        generator nobody can use to report a crash.
        """
        from modules.diagnostic_report import log_tail

        assert log_tail(str(tmp_path / "nope.log")) == ""


@pytest.fixture
def appdata(tmp_path, monkeypatch):
    """A Devanagari app-data path, for the same reason the A1/A2 suites use one.

    A hi-IN machine's ANSI codepage is cp1252, which cannot represent this path at
    all, so every unencoded write on it fails deterministically (RULE-WIN24).
    Making it the default here means every test in this file exercises the
    encoding contract rather than only the one that names it.
    """
    from modules import session_record

    target = tmp_path / (_DEVANAGARI + "-home") / "NetSentinel"
    target.mkdir(parents=True)
    monkeypatch.setattr("modules.utils.get_app_data_dir", lambda: target)

    session_record._current_path = None
    yield target
    session_record._current_path = None


def _write_sinks(appdata, crash="", exceptions="", shutdown="", stderr=""):
    """Put text in the four crash sinks, exactly where the app writes them."""
    for name, text in (
        ("netsentinel_crash.log", crash),
        ("netsentinel_exceptions.log", exceptions),
        ("netsentinel_shutdown.log", shutdown),
        ("netsentinel_stderr.log", stderr),
    ):
        if text:
            (appdata / name).write_text(text, encoding="utf-8")


class TestBuildReport:
    def test_the_report_carries_the_fingerprint_the_dead_sessions_and_every_sink(
        self, appdata
    ):
        """One file that answers all three questions a field crash raises.

        *What kind of machine was it* (A2's fingerprint — the codepage pair the
        v2.2.8 triage had to infer from a market code), *did it die and where was
        the user* (A1's session record, the only trace an OOM kill or a hang
        leaves at all), and *what did the crash net catch* (the four sinks). Any
        one of the three alone leaves the reader guessing, which is the state this
        work exists to end.
        """
        from modules import session_record
        from modules.diagnostic_report import build_report

        session_record.begin_session(app_version="2.2.8")
        session_record.heartbeat("Network Logger")
        session_record._current_path = None  # the process died; nothing marked it clean

        _write_sinks(
            appdata,
            crash="Windows fatal exception: access violation",
            exceptions="Traceback (most recent call last):",
            shutdown="closeEvent: drain complete",
            stderr="qt.qpa.window: warning",
        )

        report = build_report(app_version="2.2.8")

        assert "ansi_codepage" in report
        assert "Network Logger" in report
        assert "access violation" in report
        assert "Traceback (most recent call last)" in report
        assert "drain complete" in report
        assert "qt.qpa.window" in report

    def test_a_machine_that_has_never_crashed_still_produces_a_report(self, appdata):
        """The healthy case is the common one, and it must not be an error path.

        Three of the four sinks do not exist until something goes wrong, and a
        user may open the feedback dialog simply to describe a UI annoyance. A
        report generator that only works after a crash cannot be used to report
        one.
        """
        from modules.diagnostic_report import build_report

        report = build_report(app_version="2.2.8")

        assert "2.2.8" in report
        assert len(report) > 0


class TestKnownDeviceNames:
    """Where the name denylist comes from, given the sanitizer will not guess.

    Read out of the app's own JSON caches rather than the database: `build_report()`
    is called from `app.py::_fatal()` on the crash path, where opening SQLite is a
    lock-contention risk in a process that is already dying, and where
    `MetricStore` is not available to inject anyway (ARCH RULE 2 — one instance,
    created in `app.py` and passed down; `modules/` must never construct one).
    """

    def test_hostnames_and_unit_names_are_harvested_from_the_caches(self, appdata):
        """The two shapes that actually leaked into the live report.

        `unit` is the mesh node's room name (`Floor2 Kitchen`) and `hostname` is
        the client's own name (`Google streamer`) — both from
        `mesh_enrichment_cache.json`, both nested several levels down, so the
        harvest has to walk rather than read known paths.
        """
        import json

        from modules.diagnostic_report import known_device_names

        (appdata / "mesh_enrichment_cache.json").write_text(
            json.dumps({
                "plugin_enrichments": {
                    "abc": {
                        "b8:7b:d4:ef:62:02": {
                            "hostname": "Google streamer",
                            "unit": "Floor2 Kitchen",
                        }
                    }
                }
            }),
            encoding="utf-8",
        )

        names = known_device_names()

        assert "Google streamer" in names
        assert "Floor2 Kitchen" in names

    def test_public_speedtest_server_names_are_not_harvested(self, appdata):
        """`speedtest_servers_cache.json` keys its ISP servers under `name`.

        Those are public infrastructure, not the user's devices, and there are
        hundreds of them. Pulling them into the denylist would redact
        `Telematica` and `Wien Energie Superschnell` out of every speed-test log
        line — destroying the diagnostic to protect nothing. This is why the key
        set deliberately excludes a bare `name`.
        """
        import json

        from modules.diagnostic_report import known_device_names

        (appdata / "speedtest_servers_cache.json").write_text(
            json.dumps([{"id": "1", "name": "Telematica", "host": "x.at:8080"}]),
            encoding="utf-8",
        )

        assert "Telematica" not in known_device_names()

    def test_an_unreadable_or_malformed_cache_costs_one_file_not_the_report(
        self, appdata
    ):
        """Best-effort, like everything else on this path.

        A half-written cache is an ordinary artefact of the crash being reported.
        Refusing to build a report because one JSON file is truncated would fail
        exactly when the report matters.
        """
        import json

        from modules.diagnostic_report import known_device_names

        (appdata / "broken.json").write_text("{not json", encoding="utf-8")
        (appdata / "good.json").write_text(
            json.dumps({"hostname": "Kontor"}), encoding="utf-8"
        )

        assert "Kontor" in known_device_names()

    def test_blank_names_are_not_collected(self, appdata):
        """`device_baseline.json` stores `"hostname": ""` for unresolved devices.

        An empty string in the denylist would match at every position in the text.
        """
        import json

        from modules.diagnostic_report import known_device_names

        (appdata / "device_baseline.json").write_text(
            json.dumps({"aa:bb": {"hostname": ""}, "cc:dd": {"hostname": "  "}}),
            encoding="utf-8",
        )

        assert all(n.strip() for n in known_device_names())


class TestRedaction:
    """The property that decides whether this file is sendable at all.

    Everything the crash sinks contain was written by a network scanner running on
    the user's own LAN. `netsentinel_stderr.log` on the machine this was written on
    already holds a live gateway address and the developer's account name — not a
    hypothetical.
    """

    def test_nothing_from_the_users_network_survives_into_the_report(self, appdata):
        """One assertion per class of thing that must not leave the machine."""
        from modules.diagnostic_report import build_report

        _write_sinks(
            appdata,
            exceptions=(
                "Traceback (most recent call last):\n"
                '  File "C:\\Users\\ossia\\AppData\\Local\\NetSentinel\\app.py", line 9\n'
                "ConnectionError: 192.168.68.42 (aa:bb:cc:dd:ee:ff) unreachable\n"
            ),
            stderr=(
                "SSID 1 : MyHomeNet\n"
                "neighbour fe80::1c2d:3e4f:5a6b:7c8d%12 timed out\n"
            ),
        )

        report = build_report(app_version="2.2.8")

        assert "192.168.68.42" not in report
        assert "aa:bb:cc:dd:ee:ff" not in report.lower()
        assert "fe80::1c2d:3e4f:5a6b:7c8d" not in report
        assert "MyHomeNet" not in report
        assert "ossia" not in report

    def test_a_device_name_from_the_real_caches_does_not_survive(self, appdata):
        """The end-to-end name path, with nothing supplied by hand.

        This is the RULE-DBG5 shape: `sanitize_text` gained a `names` parameter
        and `known_device_names()` gained a harvester, and both can be perfectly
        correct while `build_report()` never connects them — in which case every
        other test here still passes and the report still leaks. So the name is
        written only into a cache file, and the assertion is on the report.

        The line is the real one observed leaking on this machine, from
        `modules/deco_client.py:302`.
        """
        import json

        from modules.diagnostic_report import build_report

        (appdata / "mesh_enrichment_cache.json").write_text(
            json.dumps({"e": {"aa:bb": {"unit": "Vardagsrum", "hostname": "iPad"}}}),
            encoding="utf-8",
        )
        _write_sinks(
            appdata,
            stderr=(
                "Could not fetch clients for Vardagsrum (aa:bb:cc:dd:ee:ff): "
                "Response ended prematurely\niPad went offline\n"
            ),
        )

        report = build_report(app_version="2.2.8")

        assert "Vardagsrum" not in report
        assert "iPad" not in report
        assert "Response ended prematurely" in report, (
            "the surrounding diagnostic prose was eaten along with the name"
        )

    def test_the_shape_of_a_redacted_path_survives_for_rule_win24(self, appdata):
        """Redact the value, keep the property.

        The account name goes; the path around it stays, because *whether the path
        was representable in the ANSI codepage* is the whole hi-IN diagnosis, and
        that answer is carried separately as the A2 booleans in the same report.
        """
        from modules.diagnostic_report import build_report

        _write_sinks(
            appdata,
            exceptions='  File "C:\\Users\\ossia\\AppData\\Local\\NetSentinel\\app.py"\n',
        )

        report = build_report(app_version="2.2.8")

        assert "C:\\Users\\<user>\\AppData\\Local\\NetSentinel" in report
        assert "appdata_path_is_ascii" in report
        assert "appdata_path_encodable_in_acp" in report

    def test_the_four_part_store_version_is_not_eaten_as_an_ip_address(
        self, appdata, monkeypatch
    ):
        """`2.2.8.0` is a valid public IPv4 address, and the sanitizer removes those.

        It is also the MSIX package version — the join key between this report and
        a Partner Center failure row, which is the only thing the aggregate Store
        data is good for. Running the header through the sanitizer alongside the
        log tails would silently delete it, so the header is deliberately outside
        the redacted region. This test is what keeps that split from being
        "tidied up" by a later reader who sees an unsanitized string and assumes
        it is an oversight.
        """
        from modules.diagnostic_report import build_report

        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr("modules.utils.is_store_app", lambda: True)

        report = build_report(app_version="2.2.8")

        assert "2.2.8.0" in report
        assert "[IP redacted]" not in report.split("## Environment")[0]


class TestWriteReport:
    def test_the_report_lands_in_the_reports_folder_already_redacted(self, appdata):
        """`reports/` because it is the one folder the UI can already open.

        The whole point of B2 is reachability — a file the user cannot find is
        the same as the four write-only sinks it was built to replace.
        """
        from modules.diagnostic_report import write_report

        _write_sinks(appdata, exceptions="failed to reach 192.168.68.42\n")

        path = write_report(app_version="2.2.8")

        assert path is not None
        written = (appdata / "reports" / os.path.basename(path)).read_text(
            encoding="utf-8"
        )
        assert "192.168.68.42" not in written
        assert "NetSentinel diagnostic report" in written

    def test_writing_survives_an_app_data_path_the_codepage_cannot_encode(
        self, appdata
    ):
        """The file is written on the machine whose path broke the last report.

        `open()` with no `encoding=` uses the ANSI codepage under strict errors,
        and cp1252 cannot represent this fixture's directory at all — the
        RULE-WIN24 case. A report writer that raises here fails on precisely the
        machines it exists to describe.
        """
        from modules.diagnostic_report import write_report

        path = write_report(app_version="2.2.8")

        assert path is not None
        assert _DEVANAGARI in path

    def test_a_failed_write_reports_failure_rather_than_a_path(self, appdata, monkeypatch):
        """The UI has to be able to say "that did not work".

        Every other write in this workstream is instrumentation and swallows its
        own errors, because instrumentation must never break the path it
        instruments. This one is different: the user asked for a file, so
        pretending one exists is worse than admitting none does.
        """
        from modules import diagnostic_report

        def _no(*args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(diagnostic_report.os, "makedirs", _no)
        assert diagnostic_report.write_report(app_version="2.2.8") is None
