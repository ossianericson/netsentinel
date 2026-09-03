"""Contract tests against the REAL ``tplinkrouterc6u`` library.

Every other Deco test fakes the library — ``tests/test_deco_auth.py`` reimplements
the login protocol by hand, and ``tests/test_deco_unreachable_not_auth.py`` does
``monkeypatch.setitem(sys.modules, "tplinkrouterc6u", mod)``. So a breaking library
change passes the entire suite silently and surfaces in a user's Deco page instead.

``modules/deco_client.py`` depends on three things the library does not protect with
semver:

1. ``TPLinkDecoClient.__init__`` accepting ``timeout`` and ``verify_ssl``.
2. ``self._client._stok`` — a **private** attribute, read at deco_client.py's
   ``login()``.
3. ``authorize()`` raising a ``requests`` exception type on an unreachable host,
   which is what separates INFRA_UNREACHABLE from "wrong password".

The ``_stok`` dependency is two classes deep and fails *silently*: ``__init__``
(``TplinkEncryption``) seeds it to ``''`` while a different method
(``TplinkEncryption.authorize``) fills it in, and ``TPLinkDecoClient`` overrides
``authorize`` without touching it. A library change that stops populating it yields
an empty-string token, not an ``AttributeError`` — there is no loud failure to rely
on, which is exactly why this needs an explicit assertion.

`requirements.txt` pins ``~=5.32``, which admits any 5.x minor, so these can move
under us without a Dependabot PR at all.
"""
from __future__ import annotations

import inspect

import pytest

tplinkrouterc6u = pytest.importorskip("tplinkrouterc6u")


@pytest.fixture
def deco_cls():
    from tplinkrouterc6u import TPLinkDecoClient
    return TPLinkDecoClient


def test_constructor_still_accepts_timeout_and_verify_ssl(deco_cls):
    """deco_client.py passes both as keywords; a rename breaks construction outright."""
    params = inspect.signature(deco_cls.__init__).parameters
    assert "timeout" in params, "DecoMeshClient._ensure_client() passes timeout="
    assert "verify_ssl" in params, "DecoMeshClient._ensure_client() passes verify_ssl="
    assert "host" in params and "password" in params


def test_stok_exists_immediately_after_construction(deco_cls):
    """deco_client.login() reads `_client._stok`; it must never AttributeError."""
    client = deco_cls("https://192.0.2.1", "unused-password", timeout=1)
    assert hasattr(client, "_stok"), (
        "TplinkEncryption.__init__ no longer seeds _stok — deco_client.py:login() "
        "would raise AttributeError"
    )
    assert client._stok == "", "pre-auth _stok is expected to be the empty string"


def test_some_class_in_the_mro_still_populates_stok_from_a_response(deco_cls):
    """Guard the SILENT failure: _stok seeded but never filled = empty token forever.

    Because ``__init__`` sets it to ``''``, a library change that stops assigning the
    real value produces a working-looking client that returns an empty session token.
    Nothing raises. This asserts some class in the MRO still assigns ``_stok`` from
    parsed response data, rather than only clearing it (``logout`` does that).
    """
    populating = []
    for cls in deco_cls.__mro__:
        try:
            src = inspect.getsource(cls)
        except (OSError, TypeError):
            continue
        for line in src.splitlines():
            stripped = line.strip()
            if stripped.startswith("self._stok") and "=" in stripped:
                value = stripped.split("=", 1)[1].strip()
                if value not in ("''", '""'):
                    populating.append((cls.__name__, stripped))

    assert populating, (
        "No class in TPLinkDecoClient's MRO assigns _stok a real value any more — "
        "deco_client.login() would silently return an empty session token. "
        "Check whether the library moved to a different token attribute."
    )


def test_deco_overrides_authorize_but_still_delegates_upward(deco_cls):
    """TPLinkDecoClient.authorize() must still reach the inherited implementation.

    Deco's own override is a retry wrapper (`self._retry_request(super().authorize)`)
    and never touches `_stok` itself. If it stopped delegating, authentication would
    appear to succeed while leaving the token empty.
    """
    try:
        src = inspect.getsource(deco_cls.authorize)
    except (OSError, TypeError):  # pragma: no cover — library shipped without .py
        pytest.skip("tplinkrouterc6u source unavailable for introspection")
    else:
        assert "super()" in src, (
            "TPLinkDecoClient.authorize() no longer delegates to its parent — the "
            "inherited implementation is what populates _stok"
        )


def test_authorize_propagates_transport_failures_as_requests_exceptions(deco_cls, monkeypatch):
    """An unreachable Deco must raise something deco_client.py classifies as INFRA.

    deco_client.py catches exactly ``(requests.exceptions.Timeout,
    requests.exceptions.ConnectionError)`` and treats anything else as an auth
    failure — so if the library ever wrapped transport errors in its own exception
    type, an unplugged router would be reported to the user as a wrong password.

    Driven through a patched transport rather than a real connection: deterministic,
    no network, and no dependence on how a CI runner treats TEST-NET-1.
    """
    import requests

    def _boom(*args, **kwargs):
        raise requests.exceptions.ConnectionError("simulated unreachable host")

    monkeypatch.setattr(requests.Session, "request", _boom)
    monkeypatch.setattr(requests, "request", _boom, raising=False)
    monkeypatch.setattr(requests, "post", _boom, raising=False)
    monkeypatch.setattr(requests, "get", _boom, raising=False)

    client = deco_cls("https://192.0.2.1", "unused-password", timeout=1)
    with pytest.raises((requests.exceptions.Timeout, requests.exceptions.ConnectionError)):
        client.authorize()


def test_deco_client_catch_tuple_matches_what_the_library_raises():
    """Pin the two halves together so they cannot drift apart independently."""
    import requests

    import modules.deco_client as dc

    src = inspect.getsource(dc)
    assert "requests.exceptions.Timeout" in src
    assert "requests.exceptions.ConnectionError" in src
    # SSLError/ProxyError/ConnectTimeout are ConnectionError subclasses, so the
    # tuple covers them implicitly. ChunkedEncodingError is NOT — it is a bare
    # RequestException — so it has to be named explicitly, which it now is. This
    # assertion pins the library taxonomy that makes the explicit entry necessary:
    # if a future requests release reparents it, the tuple can be simplified.
    assert not issubclass(
        requests.exceptions.ChunkedEncodingError,
        (requests.exceptions.Timeout, requests.exceptions.ConnectionError),
    ), "ChunkedEncodingError became catchable — deco_client's tuple can be simplified"
    # And pin the other half: the gap this used to document is closed, and must stay
    # closed. A mid-body reset on a lossy link classified as AUTH: is reported to the
    # user as a wrong password and treated as *reachable* by hardware_integration_page.
    assert "requests.exceptions.ChunkedEncodingError" in src, (
        "deco_client no longer names ChunkedEncodingError — a mid-body reset would "
        "again be misreported as an authentication failure"
    )


@pytest.mark.live
def test_real_unreachable_host_raises_a_caught_exception_type(deco_cls):
    """The same contract against a genuinely unroutable address (RFC 5737).

    Marked ``live`` — excluded from the default run — because a CI runner behind an
    intercepting proxy can answer TEST-NET-1 and turn this into a flake. Run it
    explicitly (``pytest -m live -k deco``) when validating a tplinkrouterc6u bump.

    Note the cost: Deco's ``_retry_request`` swallows ``ConnectTimeout`` and retries
    three times before re-raising, so this takes ~4x the timeout.
    """
    import requests

    client = deco_cls("https://192.0.2.1", "unused-password", timeout=1)
    with pytest.raises((requests.exceptions.Timeout, requests.exceptions.ConnectionError)):
        client.authorize()
