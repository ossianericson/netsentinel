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
        from modules.console_codec import apply_console_decoding

        raw = ("    Beskrivning . . . : " + _SWEDISH + " Wi-Fi 6 AX201\r\n").encode(oem)

        kwargs = apply_console_decoding({"text": True})
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

    # ``tools`` is included even though it is dev-only: tools/store_health.py writes the
    # Store failure snapshots, which are the only durable copy of data the Partner Center
    # API drops after 30 days, and a mojibaked or half-written snapshot is a silently
    # corrupted baseline for every later comparison. Verified free of violations when
    # added, so this costs nothing today and stops the next one.
    _ROOTS = ("modules", "ui", "workers", "plugins", "tools")

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
    def _is_faulthandler_fd(path: pathlib.Path, lineno: int) -> bool:
        """faulthandler writes bytes to the raw fd and never uses the text codec.

        That one handle is correct without an encoding and must not be "fixed".

        Keyed on the *surrounding source*, not on a hardcoded filename: the handle
        moved from ``app.py`` to ``modules/crash_net.py`` when the crash net was shared
        with ``cli.py`` and ``svc.py``, and an exemption pinned to a path would have
        turned a correct relocation into a spurious failure.
        """
        lines = path.read_text(encoding="utf-8").splitlines()
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
                if self._is_faulthandler_fd(f, n.lineno):
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


class TestWriteEncodingGuardIsNotVacuous:
    """The faulthandler exemption is keyed on nearby source text, so prove it is narrow.

    Widening an exemption is how a blocking gate quietly stops gating. These pin that
    it fires only for the raw-fd handle it exists for.
    """

    def test_the_exemption_fires_for_the_faulthandler_handle(self, tmp_path):
        f = tmp_path / "m.py"
        f.write_text(
            "import faulthandler\n"
            "fd = open(path, 'a')\n"
            "faulthandler.enable(file=fd)\n",
            encoding="utf-8",
        )
        assert TestWriteEncodingGuard._is_faulthandler_fd(f, 2)

    def test_the_exemption_does_not_fire_for_an_unrelated_write(self, tmp_path):
        f = tmp_path / "m.py"
        f.write_text(
            "def save(path, text):\n"
            "    with open(path, 'w') as fh:\n"
            "        fh.write(text)\n",
            encoding="utf-8",
        )
        assert not TestWriteEncodingGuard._is_faulthandler_fd(f, 2)


class TestFingerprintAndSessionsUnderNonAsciiPaths:
    """A2 and A1 are the evidence path — they must survive the machines they describe.

    Both run on a box that is already failing, and on hi-IN/ru-RU/zh-CN that box may
    have an app-data path its own ANSI codepage cannot represent. A fingerprint that
    raises while measuring the encoding problem, or a session record that cannot be
    read back, leaves exactly the anonymous counter this workstream exists to replace.
    """

    @staticmethod
    def _pin_ansi_codec(monkeypatch, codec: str = "cp1252") -> None:
        """Pin the codec the fingerprint reports as the machine's ANSI codepage.

        Without this the test asserts something different on every host: CI runs on
        Linux, where ``locale.getpreferredencoding()`` is UTF-8 and Devanagari IS
        encodable, so the interesting branch would never be taken. The module names
        this function separately for exactly that reason.
        """
        monkeypatch.setattr(
            "modules.environment_fingerprint._ansi_codec_name", lambda: codec
        )

    def test_the_fingerprint_is_computable_under_a_non_ascii_appdata_path(
        self, non_ascii_appdata, cp1252_machine, monkeypatch
    ):
        from modules.environment_fingerprint import fingerprint

        self._pin_ansi_codec(monkeypatch)
        fp = fingerprint()

        assert isinstance(fp, dict) and fp
        # The two fields whose entire job is to describe this situation must be honest
        # about it rather than defaulting to the comfortable answer.
        assert fp["appdata_path_is_ascii"] is False
        assert fp["appdata_path_encodable_in_acp"] is False, (
            "cp1252 cannot represent Devanagari, so the report has to say so — a True "
            "here sends a triage engineer looking somewhere else entirely"
        )

    def test_the_fingerprint_round_trips_through_json(
        self, non_ascii_appdata, monkeypatch
    ):
        """It is written into a session record and read back by the next launch."""
        import json

        from modules.environment_fingerprint import fingerprint

        self._pin_ansi_codec(monkeypatch)
        fp = fingerprint()
        assert json.loads(json.dumps(fp)) == fp

    def test_a_session_record_round_trips_through_a_non_ascii_path(
        self, non_ascii_appdata, cp1252_machine, monkeypatch
    ):
        """Write, heartbeat with a CJK page label, and read it back as unclean."""
        import modules.session_record as sr

        monkeypatch.setattr(sr, "_current_path", None)
        path = sr.begin_session("2.2.8")
        assert path is not None, "no record was written at all"

        sr.heartbeat("网络日志")

        # find_unclean_sessions() deliberately excludes the run in progress, so the
        # read-back has to be done as the *next launch* would see it.
        sr._current_path = None
        records = sr.find_unclean_sessions()

        assert len(records) == 1, records
        assert records[0]["clean_exit"] is False
        assert records[0]["last_page"] == "网络日志", (
            "a CJK page label did not survive the round-trip — that field is the only "
            "thing that will ever say WHERE the user was when the process was taken"
        )

    def test_a_clean_shutdown_still_reads_as_clean_on_a_non_ascii_path(
        self, non_ascii_appdata, cp1252_machine, monkeypatch
    ):
        """The other half: this must not turn every real quit into a phantom crash."""
        import modules.session_record as sr

        monkeypatch.setattr(sr, "_current_path", None)
        sr.begin_session("2.2.8")
        sr.end_session_clean()

        sr._current_path = None
        assert sr.find_unclean_sessions() == []


class TestRedactionAcrossScripts:
    """B2 promises "no addresses, MACs, SSIDs, device names or account name".

    Every redaction fixture shipped so far is ASCII. The account name, the SSID and the
    device names are all *user-supplied text* — the three fields most likely to be in
    the user's own script, and the three whose escape is a privacy incident rather than
    a missing diagnostic.
    """

    _LOG = (
        "2026-09-05 12:00:01 mesh poll 192.168.1.1 -> 10.0.0.42 failed\n"
        "2026-09-05 12:00:02 neighbour fe80::3e64:cfff:fee0:261c at 3c-64-cf-e0-26-1c\n"
        "2026-09-05 12:00:03 SSID 1 : Дача-Гостевая\n"
        "2026-09-05 12:00:04 SSID 2 : 客厅无线\n"
        "2026-09-05 12:00:05 Could not fetch clients for Гостиная (aa:bb:cc:dd:ee:01)\n"
        "2026-09-05 12:00:06 Could not fetch clients for 客厅电视 (aa:bb:cc:dd:ee:02)\n"
        '2026-09-05 12:00:07   File "C:\\Users\\Владимир\\AppData\\Local\\x.py", line 1\n'
    )

    _NAMES = ["Гостиная", "客厅电视", "Дача-Гостевая", "客厅无线"]

    def _clean(self, ip_map=None):
        from modules.report_sanitizer import sanitize_text

        return sanitize_text(self._LOG, ip_map if ip_map is not None else {},
                             names=self._NAMES)

    def test_private_addresses_are_aliased_not_left_in_place(self):
        """Pin the alias values, so the "did it survive" assertions below are exact."""
        ip_map: dict = {}
        self._clean(ip_map)
        assert ip_map == {"192.168.1.1": "192.168.1.2", "10.0.0.42": "192.168.1.3"}

    def test_no_address_or_mac_survives(self):
        out = self._clean()
        for leaked in ("192.168.1.1", "10.0.0.42", "fe80::3e64:cfff:fee0:261c",
                       "3c-64-cf-e0-26-1c", "aa:bb:cc:dd:ee:01", "aa:bb:cc:dd:ee:02"):
            assert leaked not in out, f"{leaked} survived redaction"

    def test_clock_timestamps_still_survive(self):
        """The IPv6 rule is shaped to spare `12:00:01`; a report with its times
        redacted cannot be correlated with anything."""
        out = self._clean()
        assert "12:00:01" in out and "12:00:07" in out

    def test_the_cyrillic_windows_account_name_is_removed(self):
        out = self._clean()
        assert "Владимир" not in out, "the account name survived %LOCALAPPDATA%"
        assert "AppData" in out, "the path SHAPE is the diagnostic and must survive"

    @pytest.mark.parametrize("name", ["Гостиная", "客厅电视", "Дача-Гостевая", "客厅无线"])
    def test_no_supplied_device_name_survives_in_any_script(self, name):
        assert name not in self._clean(), f"device name {name!r} survived"

    def test_a_cjk_name_embedded_in_cjk_prose_is_still_removed(self):
        r"""Why the token-edge lookarounds are ASCII-only, and must stay that way.

        ``_redact_names`` asserts "no adjacent ``[0-9A-Za-z_]``" rather than ``\b`` or
        a Unicode ``\w``. Chinese writes without inter-word spaces, so under a Unicode
        boundary a name sitting inside a longer CJK run would not match and the name
        would leak. The ASCII class errs the other way — it over-redacts a substring,
        costing diagnostic text rather than privacy, which is the correct direction for
        this module. Pinned so nobody "modernises" the class to ``\w``.
        """
        from modules.report_sanitizer import sanitize_text

        out = sanitize_text("设备客厅电视已离线", {}, names=["客厅电视"])
        assert "客厅电视" not in out
        assert "[name redacted]" in out

    def test_the_diagnostic_prose_around_a_redacted_name_survives(self):
        """Redaction that eats the message leaves a report nobody can triage."""
        out = self._clean()
        assert "Could not fetch clients for [name redacted] ([MAC redacted])" in out


# ── D5: the RULE-WIN21 codec is right for netsh and wrong for these two children ──

#: Stand-in for the live ``GetOEMCP()``. ``apply_console_decoding()`` names the ``"oem"``
#: codec, which exists only on Windows; cp850 (en-AU / sv-SE / es-BO) reproduces the same
#: ANSI/OEM mismatch on every host, the way
#: ``test_console_output_round_trips_through_the_configured_policy`` already does.
_OEM_STANDIN = "cp850"


def _frozen_kwargs(kwargs: dict) -> dict:
    """What ``SilentPopen.__init__`` does to a text-mode child in the shipped build.

    Mirrors ``modules.console_codec.apply_console_decoding`` — including the rule that
    matters here, that a caller naming its own ``encoding`` wins — with the OEM
    codepage pinned so the defect is reproducible off-Windows. The injection is
    installed only when frozen, so no source or CI run reaches it otherwise.
    """
    kwargs = dict(kwargs)
    if not (kwargs.get("text") or kwargs.get("universal_newlines")):
        return kwargs
    if "encoding" in kwargs or "errors" in kwargs:
        return kwargs
    kwargs["encoding"] = _OEM_STANDIN
    kwargs["errors"] = "replace"
    return kwargs


class TestNonConsoleChildrenAreNotDecodedAsOem:
    """RULE-WIN21's OEM codec is correct for ``netsh``/``ipconfig``/``ping`` and wrong
    for the two children that are not Windows console tools at all.

    ``netsh`` emits in the console codepage; an ``ssh`` session emits whatever the
    *remote* sent (a modern Linux box: UTF-8), and a Python child emits in the local
    **ANSI** codepage. Decoding either as OEM does not raise — ``errors="replace"`` —
    so the failure is silently corrupt data feeding a security report and a
    ``json.loads``.
    """

    def test_the_frozen_injection_still_yields_to_a_named_encoding(self):
        """The stand-in above is only honest while the real helper behaves this way."""
        from modules.console_codec import apply_console_decoding

        assert apply_console_decoding({"text": True}).get("encoding")
        assert apply_console_decoding(
            {"text": True, "encoding": "utf-8"}
        )["encoding"] == "utf-8"

    def test_a_utf8_remote_survives_the_openssh_ssh_fallback(self, tmp_path, monkeypatch):
        """A Linux remote's UTF-8 must reach the credentialed-scan parsers intact.

        ``_run_ssh_paramiko`` — the same function's other backend — already decodes
        ``utf-8``; only the ``openssh`` fallback goes through the console codec. That
        fallback is the shipped path, because ``paramiko`` is optional and is in
        neither ``requirements.txt`` nor any ``.spec``. Nothing about the *user's*
        locale is involved: the bytes come from the scanned host, so this is wrong on
        en-US too.
        """
        import subprocess as _sp
        import sys
        import threading

        from modules import credentialed_scan_helpers as h

        gecos = "José García"
        child = tmp_path / "fake_ssh_remote.py"
        child.write_text(
            "import sys\n"
            "sys.stdout.buffer.write(%r.encode('utf-8'))\n"
            % ("root:0:" + gecos + ":/bin/bash\n"),
            encoding="utf-8",
        )

        real_run = _sp.run
        monkeypatch.setattr(h.shutil, "which", lambda _name: "/usr/bin/ssh")
        monkeypatch.setattr(
            h.subprocess, "run",
            lambda _cmd, **kw: real_run([sys.executable, str(child)], **_frozen_kwargs(kw)),
        )

        cmd = "awk -F: '$3>=1000{print $1,$3,$6,$7}' /etc/passwd"
        out = h._run_ssh_subprocess(
            host="192.168.1.50", port=22, username="root", password=None,
            key_path=None, commands=[cmd], timeout=5,
            progress=None, stop=threading.Event(),
        )

        assert gecos in out[cmd], (
            "the remote's UTF-8 was decoded as the local OEM codepage: %r" % out[cmd]
        )

    def test_a_plugin_json_line_survives_a_non_utf8_ansi_codepage(self, tmp_path, monkeypatch):
        """The plugin JSON contract must not depend on the box's ANSI codepage.

        A Python child encodes a piped ``stdout`` with ``locale.getpreferredencoding()``
        — the ANSI codepage — while the parent decodes OEM, and the two differ on every
        Windows install. ``PYTHONIOENCODING`` here stands in for a ru-RU box's cp1251;
        the worker must pin **both** ends of the contract, so naming an encoding on the
        parent alone is not enough.
        """
        pytest.importorskip("PyQt6.QtCore")

        import subprocess as _sp

        from workers import plugin_worker as pw

        name = "Маршрутизатор"
        script = tmp_path / "cyrillic_plugin.py"
        script.write_text(
            "import json, sys\n"
            "if '--netsentinel' in sys.argv:\n"
            "    sys.stdout.write(json.dumps({\n"
            "        'info': {'name': %r, 'type': 'router', 'ip': '192.168.1.1'},\n"
            "        'status': {'wan_ip': None},\n"
            "        'clients': [],\n"
            "    }, ensure_ascii=False) + '\\n')\n"
            "    sys.exit(0)\n" % name,
            encoding="utf-8",
        )

        monkeypatch.setenv("PYTHONIOENCODING", "cp1251")
        real_run = _sp.run
        monkeypatch.setattr(
            pw.subprocess, "run",
            lambda cmd, **kw: real_run(cmd, **_frozen_kwargs(kw)),
        )

        results: list = []
        errors: list = []
        worker = pw.PluginWorker(script_path=str(script), timeout=30)
        worker.result.connect(results.append)
        worker.error.connect(errors.append)
        worker.work()

        assert not errors, "plugin run failed outright: %r" % errors
        assert results and results[0]["info"]["name"] == name, (
            "the plugin's JSON was decoded with the wrong codec: %r" % (results or errors)
        )


# ── D8: the NetBIOS name is not an ASCII structure ───────────────────────────

def _nbstat_response(name_field: bytes, suffix: int = 0x00, flags: int = 0x0400) -> bytes:
    """A minimal, valid NODE STATUS response carrying one name entry.

    Shaped to match `_parse_nbstat_response`'s own offset arithmetic: 12-byte
    header with ANCOUNT=1, a 34-byte uncompressed RR_NAME, then
    TYPE+CLASS+TTL+RDLENGTH, then the name-table count byte.
    """
    header = (b"\x00\x00" + b"\x84\x00" + b"\x00\x00" + b"\x00\x01"
              + b"\x00\x00" + b"\x00\x00")
    rr_name = b"\x20" + b"C" * 32 + b"\x00"            # 34 bytes, data[12] != 0xC0
    rr_fixed = b"\x00\x21" + b"\x00\x01" + b"\x00\x00\x00\x00" + b"\x00\x00"
    entry = name_field.ljust(15, b" ") + bytes([suffix]) + flags.to_bytes(2, "big")
    return header + rr_name + rr_fixed + b"\x01" + entry


class TestNetbiosNamesAreNotAscii:
    """A NetBIOS name is registered in the **OEM** character set, not ASCII.

    `decode("ascii", errors="ignore")` does not fail on a Cyrillic or CJK name — it
    *deletes* it, byte by byte, and returns whatever ASCII was left. So the device
    gets no hostname at all, or, worse, a silently truncated one, and the `except
    Exception` around the caller means nothing is ever logged about it.
    """

    def test_a_cyrillic_netbios_name_is_not_deleted(self):
        from modules.name_resolver import _parse_nbstat_response

        raw = "Петров".encode("cp866")   # 6 bytes, all >= 0x80
        got = _parse_nbstat_response(_nbstat_response(raw))

        assert got, "the whole name was deleted by an ASCII decode"
        assert len(got) == len(raw), (
            "every byte of a single-byte OEM name must map to one character: %r" % got
        )

    def test_a_mixed_name_is_not_silently_truncated(self):
        """The sharper failure: a *plausible* wrong answer instead of no answer."""
        from modules.name_resolver import _parse_nbstat_response

        raw = b"PC-" + "Петров".encode("cp866")
        got = _parse_nbstat_response(_nbstat_response(raw))

        assert got.startswith("PC-")
        assert got != "PC-", "the non-ASCII half was dropped, leaving a truncated name"
        assert len(got) == len(raw), got

    def test_an_ascii_name_is_unchanged(self):
        """The common case must not move."""
        from modules.name_resolver import _parse_nbstat_response

        assert _parse_nbstat_response(_nbstat_response(b"DESKTOP-LN2HAJ")) == "DESKTOP-LN2HAJ"

    def test_a_group_name_is_still_skipped(self):
        """The workgroup entry shares the <00> suffix and must not win."""
        from modules.name_resolver import _parse_nbstat_response

        assert _parse_nbstat_response(
            _nbstat_response(b"WORKGROUP", flags=0x8400)
        ) == ""
