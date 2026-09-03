"""Locale and encoding robustness harness — the class behind the Store crash cluster.

Microsoft Store recorded 13 failures clustered in India (5), Australia (3), Sweden (2),
Bolivia (2) and the US (1). Two hypotheses were available, and they cover that evidence
very differently:

* **Label translation** — ``ipconfig``/``netsh`` labels are translated, English regexes
  miss. Explains sv-SE and es-BO only; en-AU and en-US are English locales.
* **Codepage/encoding** — every one of those locales pairs **ANSI cp1252** with a
  *different* OEM codepage (cp437 on en-US and hi-IN; cp850 on en-AU, sv-SE, es-BO).
  This is the only hypothesis consistent with all five countries.

So the encoding half gets the deeper coverage here. Attribution to those specific 13
events remains **unproven** — every case below is an independently confirmed defect,
which is a weaker and different claim.

No localized Windows VM is available, so everything here is simulation. That is a real
limit for translated *labels*, but not for the two classes that matter most: a non-ASCII
**path** is fully reproducible on an ASCII-username host by redirecting the app-data
directory, and a codepage mismatch is reproducible by pinning the codec directly.
"""
from __future__ import annotations

import ast
import builtins
import pathlib

import pytest

# Real scripts from the affected locales. Devanagari is the sharp case: hi-IN Windows
# uses cp1252 as its ANSI codepage, which cannot represent it *at all* — so a Devanagari
# username makes an unencoded write fail deterministically, not probabilistically.
_DEVANAGARI = "नमस्ते"
_SWEDISH = "Ångström"
_SPANISH = "Señal-Móvil"

_REPO = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture
def cp1252_machine(monkeypatch):
    """Make every encoding-less ``open()`` resolve to cp1252, as on a real Windows box.

    The test host's own locale is irrelevant to these defects — what matters is that a
    codec unable to represent the payload gets chosen when nobody names one. Pinning it
    makes the class deterministic everywhere instead of reproducing only on a non-UTF-8
    host, which is precisely why it never reproduced in development.
    """
    real_open = builtins.open

    def _ansi_open(file, mode="r", *args, **kwargs):
        if "b" not in str(mode) and "encoding" not in kwargs:
            kwargs["encoding"] = "cp1252"
        return real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", _ansi_open)


@pytest.fixture
def non_ascii_appdata(tmp_path, monkeypatch):
    """Redirect the app-data dir to a path containing non-Latin scripts.

    This is the part the "no VM" constraint appeared to block and does not: the failing
    ingredient is the *path characters*, not the OS locale, and those can be created on
    any filesystem. ``tests/test_uia_warmup.py`` already redirects ``LOCALAPPDATA`` the
    same way for its end-to-end run.
    """
    home = tmp_path / (_DEVANAGARI + "-" + _SWEDISH)
    appdata = home / "NetSentinel"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("LOCALAPPDATA", str(home))
    monkeypatch.setattr("modules.utils.get_app_data_dir", lambda: appdata)
    return appdata


class TestNonAsciiAppDataPaths:
    """Every write path must survive a user whose account name is not Latin script."""

    def test_app_data_dir_with_non_latin_username_is_writable(self, non_ascii_appdata):
        from modules.utils import get_app_data_dir

        target = get_app_data_dir() / "probe.txt"
        target.write_text(_DEVANAGARI + " " + _SWEDISH + " " + _SPANISH,
                          encoding="utf-8")
        assert _DEVANAGARI in target.read_text(encoding="utf-8")

    def test_replacement_stderr_survives_a_devanagari_path(
        self, non_ascii_appdata, cp1252_machine, monkeypatch
    ):
        """The stderr replacement must write a traceback naming its own directory.

        This is what makes hi-IN qualitatively worse than the other locales: the path is
        *in* almost every traceback, and cp1252 cannot encode it, so the error-reporting
        stream fails on exactly the input it exists to record.
        """
        import app as _app

        monkeypatch.setattr(_app.sys, "stderr", None)
        _app._ensure_std_streams()

        stream = _app.sys.stderr
        try:
            stream.write('  File "' + str(non_ascii_appdata) + '", line 1\n')
            stream.flush()
        finally:
            try:
                stream.close()
            except Exception:
                pass  # non-fatal — the assertion is that write() above did not raise

        assert (non_ascii_appdata / "netsentinel_stderr.log").exists()

    def test_the_crash_report_writer_survives_a_devanagari_path(
        self, non_ascii_appdata, cp1252_machine, monkeypatch
    ):
        """RULE-WIN19's writer, exercised against a real non-ASCII directory."""
        from PyQt6 import QtWidgets

        import app as _app

        class _NoGui:
            def __init__(self, *a, **k):
                raise RuntimeError("no GUI available")

        monkeypatch.setattr(QtWidgets, "QMessageBox", _NoGui)

        with pytest.raises(SystemExit):
            _app._fatal("Unhandled Error",
                        "path: " + str(non_ascii_appdata) + " " + _SWEDISH)

        written = (non_ascii_appdata / "netsentinel_error.log").read_text(
            encoding="utf-8", errors="replace"
        )
        assert "Unhandled Error" in written


class TestOemCodepageDecoding:
    """The OEM/ANSI split — the only hypothesis consistent with all five countries."""

    # Bytes cp1252 leaves *undefined* but cp437/cp850 use as real characters. A strict
    # cp1252 decode of console output containing any of these raises UnicodeDecodeError.
    _UNDEFINED_IN_CP1252 = bytes([0x81, 0x8D, 0x8F, 0x90, 0x9D])

    def test_the_bytes_that_break_cp1252_are_decodable_as_oem(self):
        with pytest.raises(UnicodeDecodeError):
            self._UNDEFINED_IN_CP1252.decode("cp1252", errors="strict")

        for oem in ("cp437", "cp850"):
            assert self._UNDEFINED_IN_CP1252.decode(oem)

    @pytest.mark.parametrize("oem,locales", [
        ("cp437", "en-US / hi-IN"),
        ("cp850", "en-AU / sv-SE / es-BO"),
    ])
    def test_console_output_round_trips_through_the_configured_policy(self, oem, locales):
        """An accented adapter name must survive the decode the app actually configures."""
        import app as _app

        raw = ("    Beskrivning . . . : " + _SWEDISH + " Wi-Fi 6 AX201\r\n").encode(oem)

        kwargs = _app._apply_console_decoding({"text": True})
        assert kwargs["errors"] == "replace", locales

        # "oem" resolves to the live GetOEMCP(), which this host may not share, so assert
        # the property that actually matters: the configured error policy never raises.
        decoded = raw.decode(oem, errors=kwargs["errors"])
        assert "Wi-Fi 6 AX201" in decoded

    def test_a_strict_ansi_decode_of_oem_output_is_what_used_to_crash(self):
        """Pin the failure mode itself, so the reason for the codec cannot be forgotten."""
        raw = ("Adapter: " + _SWEDISH + "\r\n").encode("cp850")
        with pytest.raises(UnicodeDecodeError):
            raw.decode("cp1252", errors="strict")


class TestNonAsciiDataThroughParsers:
    """Non-ASCII *data* — SSIDs, hostnames, adapter names — must not break parsing."""

    def test_a_non_ascii_ssid_survives_the_wifi_parser(self, monkeypatch, fake_windows):
        import modules.wifi_scanner as ws

        raw = (
            "Interface name : Wi-Fi\n\n"
            "SSID 1 : " + _SWEDISH + "-Guest\n"
            "    Network type            : Infrastructure\n"
            "    Authentication          : WPA2-Personal\n"
            "    BSSID 1                 : aa:bb:cc:dd:ee:01\n"
            "         Signal             : 82%\n"
            "         Channel            : 6\n"
        )
        monkeypatch.setattr(ws.subprocess, "check_output", lambda *a, **k: raw)

        networks, _ssid, _ch = ws._scan_windows()
        assert any(_SWEDISH in n.ssid for n in networks), (
            "non-ASCII SSID was dropped: " + repr([n.ssid for n in networks])
        )

    def test_a_devanagari_station_row_is_still_matched_by_shape(
        self, monkeypatch, fake_windows
    ):
        """The station matcher keys on the MAC, so a translated status column is inert."""
        import modules.wifi_scanner as ws

        raw = (
            "    BSSID                  : 02:1a:2b:3c:4d:5e\n"
            "    " + _DEVANAGARI + "       : 1\n"
            "         aa:bb:cc:dd:ee:07     " + _DEVANAGARI + "\n"
        )
        monkeypatch.setattr(ws.subprocess, "check_output", lambda *a, **k: raw)

        macs = {c.mac for c in ws._get_connected_clients()}
        assert "aa:bb:cc:dd:ee:07" in macs
        assert "02:1a:2b:3c:4d:5e" not in macs, (
            "the AP's own BSSID was reported as a connected client"
        )


class TestWriteEncodingGuard:
    """Structural guard: the class closed in this program must stay closed.

    A sweep found zero unencoded text writes left. Without a guard that is a fact about
    one afternoon rather than an invariant — the next unencoded ``open(..., "w")`` would
    reintroduce exactly the defect that motivated all of this (RULE-ENFORCE1).
    """

    _ROOTS = ("modules", "ui", "workers", "plugins")

    @staticmethod
    def _source_files():
        files = [
            p
            for r in TestWriteEncodingGuard._ROOTS
            for p in (_REPO / r).rglob("*.py")
        ]
        files += [_REPO / n for n in ("app.py", "cli.py", "svc.py")]
        return [f for f in files if f.exists()]

    @staticmethod
    def _is_faulthandler_fd(lineno: int) -> bool:
        """faulthandler writes bytes to the raw fd and never uses the text codec.

        That one handle is correct without an encoding and must not be "fixed".
        """
        lines = (_REPO / "app.py").read_text(encoding="utf-8").splitlines()
        window = "\n".join(lines[max(0, lineno - 3): lineno + 2])
        return "faulthandler" in window

    def test_no_text_write_omits_its_encoding(self):
        offenders = []
        for f in self._source_files():
            try:
                tree = ast.parse(f.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            rel = f.relative_to(_REPO).as_posix()
            for n in ast.walk(tree):
                if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                        and n.func.id == "open"):
                    continue
                if "encoding" in {k.arg for k in n.keywords}:
                    continue
                mode = ""
                if len(n.args) >= 2 and isinstance(n.args[1], ast.Constant):
                    mode = str(n.args[1].value)
                for k in n.keywords:
                    if k.arg == "mode" and isinstance(k.value, ast.Constant):
                        mode = str(k.value.value)
                if "b" in mode:
                    continue
                if not any(c in mode for c in "wax+"):
                    continue
                if rel == "app.py" and self._is_faulthandler_fd(n.lineno):
                    continue
                offenders.append((rel, n.lineno, mode))

        assert not offenders, (
            "text-mode write with no encoding= — inherits the ANSI codepage under "
            "errors='strict', which cannot represent a Devanagari path or a Swedish "
            "adapter name (RULE-WIN19 / RULE-WIN24): " + repr(offenders)
        )

    def test_no_write_text_or_filehandler_omits_its_encoding(self):
        bad = []
        for f in self._source_files():
            try:
                tree = ast.parse(f.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for n in ast.walk(tree):
                if (isinstance(n, ast.Call)
                        and isinstance(n.func, ast.Attribute)
                        and n.func.attr in {"write_text", "FileHandler"}
                        and "encoding" not in {k.arg for k in n.keywords}):
                    bad.append(
                        (f.relative_to(_REPO).as_posix(), n.lineno, n.func.attr)
                    )
        assert not bad, "text write with no encoding= (RULE-WIN24): " + repr(bad)
