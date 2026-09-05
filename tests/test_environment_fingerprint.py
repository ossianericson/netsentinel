"""The environment fingerprint (A2) — the field the v2.2.8 analysis had to guess.

Thirteen Store failures across en-AU, en-US, sv-SE, es-BO and hi-IN were triaged by
*inferring* each machine's codepage pair from its market code, because Partner Center
gives a market and a count and nothing else. Every field here is one of those
inferences, measured instead.

The fingerprint describes the machine's **text and locale configuration** — the axis
the regional failures live on. It deliberately carries nothing about the user's
network: no IPs, MACs, SSIDs, hostnames, usernames or device counts. A report that
leaks the LAN of a network scanner will not be sent, and should not be.
"""
from __future__ import annotations

import pytest

_DEVANAGARI = "नमस्ते"


@pytest.fixture
def devanagari_appdata(tmp_path, monkeypatch):
    """Point get_app_data_dir() at a path the ANSI codepage cannot represent.

    This is the RULE-WIN24 case as it actually arrives: a hi-IN machine whose account
    name is Devanagari, whose ANSI codepage is cp1252, and whose every traceback frame
    therefore contains characters that codepage cannot encode.
    """
    target = tmp_path / (_DEVANAGARI + "-home") / "NetSentinel"
    target.mkdir(parents=True)
    monkeypatch.setattr("modules.utils.get_app_data_dir", lambda: target)
    return target


def test_a_non_ascii_appdata_path_is_reported_as_non_ascii(devanagari_appdata):
    """The RULE-WIN24 signal, as a boolean.

    B2 redacts the username out of every path before a report is written, which
    destroys exactly the property that made the hi-IN case diagnosable. Carrying the
    answer as a boolean here is what lets the value be redacted without losing it.
    """
    from modules.environment_fingerprint import fingerprint

    assert fingerprint()["appdata_path_is_ascii"] is False


def test_a_path_the_ansi_codepage_cannot_encode_is_flagged_separately(
    devanagari_appdata, monkeypatch
):
    """Non-ASCII and not-encodable-in-ACP are two different machines.

    ``Müller`` is non-ASCII and encodes fine in cp1252; ``नमस्ते`` does not encode at
    all. Only the second breaks an ANSI-codepage Win32 call, so collapsing the two into
    one boolean would put the German and Indian cases in the same bucket — which is the
    bucket the v2.2.8 triage was already stuck in.
    """
    from modules import environment_fingerprint as ef

    monkeypatch.setattr(ef, "_ansi_codec_name", lambda: "cp1252")
    assert ef.fingerprint()["appdata_path_encodable_in_acp"] is False

    monkeypatch.setattr(ef, "_ansi_codec_name", lambda: "utf-8")
    assert ef.fingerprint()["appdata_path_encodable_in_acp"] is True


def test_the_ansi_and_oem_codepages_are_reported_as_usable_codecs():
    """The exact RULE-WIN21 mismatch, measured.

    cp1252+cp437 vs cp1252+cp850 is what separated en-US from sv-SE in the v2.2.8
    analysis — and it was inferred from the market code, never read off the machine.
    Asserting the pair resolves to real codecs rather than pinning this host's numbers
    keeps the test honest on every machine while still catching the failure that
    matters: a truncated or garbage value from an undeclared ctypes call (RULE-WIN11),
    which would look like a plausible integer and mean nothing.
    """
    import codecs
    import sys

    from modules.environment_fingerprint import fingerprint

    fp = fingerprint()
    if sys.platform != "win32":
        assert fp["ansi_codepage"] is None and fp["oem_codepage"] is None
        return
    for key in ("ansi_codepage", "oem_codepage"):
        assert isinstance(fp[key], int) and fp[key] > 0, f"{key} = {fp[key]!r}"
        codecs.lookup(f"cp{fp[key]}")   # raises LookupError on a nonsense codepage


def test_the_real_ui_locale_is_reported_not_the_store_market():
    """en-IN and hi-IN are the same Store market and two different machines.

    Both report `IN`, but en-IN runs English UI strings under cp1252/cp437 while hi-IN
    runs Devanagari — which is the entire question the India failures turned on. Only
    the OS locale name can tell them apart, and Partner Center never carries it.
    """
    import re
    import sys

    from modules.environment_fingerprint import fingerprint

    got = fingerprint()["user_locale"]
    if sys.platform != "win32":
        assert got is None
        return
    assert isinstance(got, str) and re.fullmatch(r"[A-Za-z]{2,3}(-[0-9A-Za-z]+)*", got), (
        f"user_locale={got!r} is not a BCP-47 locale name"
    )


def test_the_codecs_open_and_the_filesystem_actually_use_are_recorded():
    """`text=True` and `open()` decode with the preferred encoding; paths use another.

    RULE-WIN21 is about the gap between what a console child *emits* and what Python
    *assumes*, so the assumed side has to be on the record too — otherwise a report
    from a failing machine shows the symptom without the half of the pair that
    explains it.
    """
    import codecs
    import locale
    import sys

    from modules.environment_fingerprint import fingerprint

    fp = fingerprint()
    assert fp["preferred_encoding"] == locale.getpreferredencoding(False)
    assert fp["filesystem_encoding"] == sys.getfilesystemencoding()
    for key in ("preferred_encoding", "filesystem_encoding"):
        codecs.lookup(fp[key])   # a name nothing can decode with is not an answer


def test_the_timezone_and_utc_offset_are_recorded():
    """The v2.2.8 UTC-vs-naive timestamp bug class needs the machine's clock context.

    A log line whose timestamps are hours away from the session record's is a *bug*
    on one machine and a *timezone* on another, and nothing in the report can tell
    those apart without the offset.
    """
    import datetime

    from modules.environment_fingerprint import fingerprint

    fp = fingerprint()
    expected = datetime.datetime.now().astimezone().utcoffset()
    assert expected is not None
    assert fp["utc_offset_minutes"] == int(expected.total_seconds() // 60)
    assert isinstance(fp["tz_name"], str) and fp["tz_name"]


def test_the_build_packaging_and_privilege_context_are_recorded():
    """A Store MSIX and a portable copy fail differently, and so do admin and non-admin.

    Every one of these sits at the top of a crash hypothesis — "was it elevated?",
    "was Npcap there?", "is this the sandboxed package?" — and none of them can be
    recovered after the fact from a log file.
    """
    import platform

    from modules.environment_fingerprint import fingerprint

    fp = fingerprint()
    assert fp["os_version"] == platform.platform()
    assert fp["arch"] == platform.machine()
    assert fp["python_version"] == platform.python_version()
    for key in ("is_store_app", "is_admin", "npcap_present"):
        assert isinstance(fp[key], bool), f"{key} = {fp[key]!r}"


#: Every field the fingerprint is allowed to carry. Deliberately duplicated here rather
#: than read off the implementation: the point is that adding a field has to be a
#: deliberate edit to the *privacy* gate, not a silent consequence of editing the dict.
ALLOWED_FIELDS = frozenset({
    "ansi_codepage", "oem_codepage", "user_locale", "preferred_encoding",
    "filesystem_encoding", "tz_name", "utc_offset_minutes",
    "appdata_path_is_ascii", "appdata_path_encodable_in_acp",
    "os_version", "arch", "python_version",
    "is_store_app", "is_admin", "npcap_present",
})


def test_the_fingerprint_carries_nothing_outside_the_allowlist_and_serializes():
    """PRIVACY.md promises zero telemetry, and B2 will put this into a shareable file.

    This is a network scanner: the moment a field can carry an IP, MAC, SSID, hostname
    or path, the report stops being something a user can reasonably send. A closed key
    set is the only check that stays true as fields are added — an "obviously nothing
    sensitive here" review does not.
    """
    import json

    from modules.environment_fingerprint import fingerprint

    fp = fingerprint()
    extra = set(fp) - ALLOWED_FIELDS
    assert not extra, (
        f"fingerprint() grew field(s) {sorted(extra)} that the privacy allowlist does "
        f"not cover. Add them here only after confirming they cannot carry an IP, MAC, "
        f"SSID, hostname, username or path."
    )
    assert set(fp) == ALLOWED_FIELDS, f"missing field(s): {sorted(ALLOWED_FIELDS - set(fp))}"

    # Must survive the trip into a session record / diagnostic report unchanged.
    assert json.loads(json.dumps(fp)) == fp


def test_a_probe_that_raises_does_not_destroy_the_rest_of_the_record(monkeypatch):
    """This is diagnostic plumbing for a machine that is already failing.

    A fingerprint that raises when one probe fails hands back nothing at all — on
    exactly the box where the other fourteen fields were the only evidence available.
    Every field is independently best-effort, and an unanswerable one reports None.
    """
    def _boom():
        raise OSError("the app-data directory is not reachable")

    monkeypatch.setattr("modules.utils.get_app_data_dir", _boom)

    from modules.environment_fingerprint import fingerprint

    fp = fingerprint()
    assert set(fp) == ALLOWED_FIELDS
    assert fp["appdata_path_is_ascii"] is None
    assert fp["appdata_path_encodable_in_acp"] is None
    assert fp["preferred_encoding"], "an unrelated field was lost with the failing one"
