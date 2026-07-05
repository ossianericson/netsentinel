"""
Regression test for a _fmt_err() misclassification bug found while dogfooding
the "Write a Plugin" AI prompts (Plan Phase 1/2, finding D16).

_fmt_err() classifies an exception into a DEPS:/NET:/AUTH:/ERR: prefix. The
original version (still used verbatim in deco_plugin.py / zte_plugin.py
before this fix, and copied into the wizard _TEMPLATE / template_plugin.py)
classified purely by scanning the exception message text for keywords like
"login", "password", "refused". That text usually includes the request URL
for a raw requests.exceptions.ConnectionError -- so a plugin that POSTs to
"/api/login" and gets connection-refused produces a message containing the
substring "login" purely from its own URL, which the keyword scan then
misreads as an AUTH failure instead of a NET failure.

The fix (applied to all four canonical _fmt_err implementations: hub_helpers
_TEMPLATE, plugins/template_plugin.py, plugins/deco_plugin.py,
plugins/zte_plugin.py) checks the exception TYPE NAME (Connection/Timeout)
and, for requests' HTTPError, response.status_code (401/403) BEFORE falling
back to message-keyword matching. This test drives the actual shipped
_fmt_err functions (not a reimplementation) against a real requests
ConnectionError whose URL contains "login", proving the bug is fixed
everywhere the pattern is copied.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
import requests

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PLUGINS_DIR = ROOT / "plugins"


def _load_fmt_err_from_file(path: Path):
    """Exec a plugin/template file in a fresh namespace and return its _fmt_err."""
    spec = importlib.util.spec_from_file_location(f"_fmterr_{path.stem}", str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._fmt_err


def _load_fmt_err_from_template_string() -> "callable":
    """Exec ui.widgets.hub_helpers._TEMPLATE (the wizard/guide template) and
    return its _fmt_err — the same string shown to the user in the "Write a
    Plugin" tab and used to generate new plugins via the wizard.
    """
    from ui.widgets.hub_helpers import _TEMPLATE
    ns: dict = {}
    exec(compile(_TEMPLATE, "<_TEMPLATE>", "exec"), ns)
    return ns["_fmt_err"]


def _connection_error_with_login_url() -> requests.exceptions.ConnectionError:
    """Produce a REAL requests ConnectionError whose message contains a URL
    with '/api/login' in it, by attempting a connection to a closed port.
    """
    try:
        requests.post("http://127.0.0.1:1/api/login", json={"password": "x"}, timeout=2)
    except requests.exceptions.ConnectionError as exc:
        assert "login" in str(exc).lower(), "test setup assumption failed: URL not in message"
        return exc
    raise AssertionError("expected a ConnectionError connecting to a closed port")


_FMT_ERR_SOURCES = {
    "hub_helpers._TEMPLATE":        _load_fmt_err_from_template_string,
    "plugins/template_plugin.py":   lambda: _load_fmt_err_from_file(PLUGINS_DIR / "template_plugin.py"),
    "plugins/deco_plugin.py":       lambda: _load_fmt_err_from_file(PLUGINS_DIR / "deco_plugin.py"),
    "plugins/zte_plugin.py":        lambda: _load_fmt_err_from_file(PLUGINS_DIR / "zte_plugin.py"),
}


@pytest.mark.parametrize("name", sorted(_FMT_ERR_SOURCES), ids=sorted(_FMT_ERR_SOURCES))
def test_fmt_err_classifies_connection_error_as_net_not_auth(name):
    """A ConnectionError whose message contains '/api/login' must still be
    NET:, not AUTH: -- the exact D16 regression.
    """
    fmt_err = _FMT_ERR_SOURCES[name]()
    exc = _connection_error_with_login_url()
    result = fmt_err(exc)
    assert result.startswith("NET:"), (
        f"{name}: expected NET: for a connection failure, got {result!r} "
        "(message-keyword-only classification would misread the '/api/login' "
        "URL in the exception text as an AUTH failure)"
    )


@pytest.mark.parametrize("name", sorted(_FMT_ERR_SOURCES), ids=sorted(_FMT_ERR_SOURCES))
def test_fmt_err_still_classifies_http_401_as_auth(name):
    """A real HTTP 401 response must still classify as AUTH: (status-code
    check), proving the fix didn't regress the common case.
    """
    fmt_err = _FMT_ERR_SOURCES[name]()
    resp = requests.Response()
    resp.status_code = 401
    exc = requests.exceptions.HTTPError("401 Client Error: Unauthorized", response=resp)
    result = fmt_err(exc)
    assert result.startswith("AUTH:"), f"{name}: expected AUTH: for HTTP 401, got {result!r}"


@pytest.mark.parametrize("name", sorted(_FMT_ERR_SOURCES), ids=sorted(_FMT_ERR_SOURCES))
def test_fmt_err_still_classifies_import_error_as_deps(name):
    fmt_err = _FMT_ERR_SOURCES[name]()
    result = fmt_err(ImportError("No module named 'somepkg'"))
    assert result.startswith("DEPS:"), f"{name}: expected DEPS: for ImportError, got {result!r}"


# ── D18: urllib.error.URLError wraps the real cause in .reason ────────────────
# Found while building Phase 3 stdlib-plugin e2e coverage: connecting to a
# closed port with urllib.request.urlopen() raises URLError, whose own type
# name doesn't match "Connection"/"Timeout" and whose message is OS-locale-
# dependent (not "refused" in English on this machine) -- so it fell through
# to unclassified ERR: until ha_plugin.py/synology_plugin.py/the templates
# also checked exc.reason's type.

_URLLIB_FMT_ERR_SOURCES = {
    "hub_helpers._TEMPLATE":      _load_fmt_err_from_template_string,
    "plugins/template_plugin.py": lambda: _load_fmt_err_from_file(PLUGINS_DIR / "template_plugin.py"),
    "plugins/ha_plugin.py":       lambda: _load_fmt_err_from_file(PLUGINS_DIR / "ha_plugin.py"),
    "plugins/synology_plugin.py": lambda: _load_fmt_err_from_file(PLUGINS_DIR / "synology_plugin.py"),
}


def _urlerror_connecting_to_closed_port():
    import urllib.error
    import urllib.request
    try:
        urllib.request.urlopen("http://127.0.0.1:1/api/login", timeout=2)
    except urllib.error.URLError as exc:
        return exc
    raise AssertionError("expected a URLError connecting to a closed port")


@pytest.mark.parametrize("name", sorted(_URLLIB_FMT_ERR_SOURCES), ids=sorted(_URLLIB_FMT_ERR_SOURCES))
def test_fmt_err_classifies_urllib_urlerror_as_net_not_err(name):
    fmt_err = _URLLIB_FMT_ERR_SOURCES[name]()
    exc = _urlerror_connecting_to_closed_port()
    result = fmt_err(exc)
    assert result.startswith("NET:"), (
        f"{name}: expected NET: for a urllib connection failure, got {result!r} "
        "(URLError's own type name and OS-locale message keywords both miss; "
        "only checking .reason's type name catches this)"
    )
