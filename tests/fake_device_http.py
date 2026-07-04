"""
fake_device_http — a minimal in-process HTTP server simulating a generic
router admin panel, for hardware-plugin transport tests.

Not a pytest test module itself; imported by:
  tests/test_ai_prompt_pipeline.py
  tests/test_stdlib_plugins_e2e.py (Phase 3)

Simulates the two most common "local API" shapes described in the in-app
"Write a Plugin" AI prompts (ui/pages/plugin_guide.py):

  * A JSON login endpoint returning a session token, then a JSON status
    endpoint gated on that token (Bearer header OR session cookie).
  * Wrong credentials -> 401.
  * A "device offline" mode (server refuses to start / connections refused)
    is simulated simply by not starting the server — point a plugin at an
    unused port instead.

Usage:
    with FakeRouterServer() as srv:
        srv.password = "correct-horse"
        # srv.url == "http://127.0.0.1:<port>"
        ...

Two more classes below simulate the exact API shapes of the two bundled
plugins that use ONLY stdlib urllib (no third-party library to fake):
FakeHomeAssistantServer (Bearer-token REST, ha_plugin.py) and
FakeSynologyServer (SID query-param SRM API, synology_plugin.py).
"""
from __future__ import annotations

import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit


class _Handler(BaseHTTPRequestHandler):
    server: "FakeRouterServer"  # type: ignore[assignment]

    def log_message(self, format, *args):  # noqa: A002 - silence stdout spam
        pass  # quiet by design — test output stays readable

    def _send_json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        auth = self.headers.get("Authorization", "")
        cookie = self.headers.get("Cookie", "")
        token = self.server.session_token
        return bool(token) and (
            auth == f"Bearer {token}" or f"session={token}" in cookie
        )

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length else b""
        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            data = {}

        if self.path == "/api/login":
            if data.get("password") == self.server.password:
                self.server.session_token = uuid.uuid4().hex
                self._send_json(200, {"token": self.server.session_token})
            else:
                self._send_json(401, {"error": "invalid credentials"})
            return

        self._send_json(404, {"error": "not found"})

    def do_GET(self) -> None:
        if self.path == "/api/status":
            if not self._authorized():
                self._send_json(401, {"error": "unauthorized"})
                return
            self._send_json(200, {
                "wan_ip": "203.0.113.42",
                "uptime_sec": 123456,
                "clients": [
                    {"name": "laptop", "ip": "192.168.1.50", "mac": "aa:bb:cc:dd:ee:01"},
                    {"name": "phone", "ip": "192.168.1.51", "mac": "aa:bb:cc:dd:ee:02"},
                ],
            })
            return
        self._send_json(404, {"error": "not found"})


class FakeRouterServer(HTTPServer):
    """Threaded stdlib HTTP server simulating a generic router admin panel."""

    def __init__(self, password: str = "correct-horse") -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.password = password
        self.session_token: str = ""
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        host, port = self.server_address
        return f"http://{host}:{port}"

    def __enter__(self) -> "FakeRouterServer":
        self._thread = threading.Thread(target=self.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self.shutdown()
        self.server_close()
        if self._thread:
            self._thread.join(timeout=2)


class _HAHandler(BaseHTTPRequestHandler):
    server: "FakeHomeAssistantServer"  # type: ignore[assignment]

    def log_message(self, format, *args):  # noqa: A002
        pass  # quiet by design — test output stays readable

    def _send_json(self, code: int, payload) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if self.headers.get("Authorization", "") != f"Bearer {self.server.token}":
            self._send_json(401, {"message": "401: Unauthorized"})
            return
        if path == "/api/config":
            self._send_json(200, {"version": "2024.1.0", "location_name": "Home"})
            return
        if path == "/api/states":
            self._send_json(200, self.server.states)
            return
        self._send_json(404, {"message": "not found"})


class FakeHomeAssistantServer(HTTPServer):
    """Threaded stdlib HTTP server simulating a Home Assistant REST API.

    ha_plugin.py hardcodes port 8123 in the URL it builds
    (f"http://{host}:8123/..."). Rather than bind this server to the fixed
    port 8123 (which could collide with a real HA instance running on the
    test machine), tests redirect urllib.request.urlopen to this server's
    actual ephemeral port — see _redirect_urllib() in test_stdlib_plugins_e2e.py.
    """

    def __init__(self, token: str = "test-token") -> None:
        super().__init__(("127.0.0.1", 0), _HAHandler)
        self.token = token
        self.states = [
            {
                "entity_id": "device_tracker.phone",
                "state": "home",
                "attributes": {
                    "friendly_name": "Phone", "ip": "192.168.1.50",
                    "mac": "aa:bb:cc:dd:ee:01", "ssid": "MyWifi", "source_type": "router",
                },
            },
            {
                "entity_id": "device_tracker.laptop",
                "state": "not_home",
                "attributes": {"friendly_name": "Laptop"},
            },
        ]
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        host, port = self.server_address
        return f"http://{host}:{port}"

    def __enter__(self) -> "FakeHomeAssistantServer":
        self._thread = threading.Thread(target=self.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self.shutdown()
        self.server_close()
        if self._thread:
            self._thread.join(timeout=2)


class _SynologyHandler(BaseHTTPRequestHandler):
    server: "FakeSynologyServer"  # type: ignore[assignment]

    def log_message(self, format, *args):  # noqa: A002
        pass  # quiet by design — test output stays readable

    def _send_json(self, payload) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        split = urlsplit(self.path)
        qs = {k: v[0] for k, v in parse_qs(split.query).items()}
        api = qs.get("api", "")

        if split.path == "/webapi/auth.cgi" and api == "SYNO.API.Auth":
            if qs.get("passwd") == self.server.password:
                self.server.sid = uuid.uuid4().hex
                self._send_json({"success": True, "data": {"sid": self.server.sid}})
            else:
                self._send_json({"success": False, "error": {"code": 400}})
            return

        if split.path == "/webapi/entry.cgi":
            if qs.get("_sid") != self.server.sid or not self.server.sid:
                self._send_json({"success": False, "error": {"code": 119}})
                return
            if api == "SYNO.Core.System":
                self._send_json({"data": {"uptime": 246810, "ram_size": "2048", "model": "RT6600ax"}})
                return
            if api == "SYNO.Core.Network.NSMDevice":
                self._send_json({"data": {"devices": [
                    {"ip_addr": "192.168.1.80", "mac": "aa:bb:cc:dd:ee:09",
                     "hostname": "console", "band": "1"},
                ]}})
                return

        self._send_json({"success": False, "error": {"code": 404}})


class FakeSynologyServer(HTTPServer):
    """Threaded stdlib HTTP server simulating the Synology SRM webapi (SID auth)."""

    def __init__(self, password: str = "correct-horse") -> None:
        super().__init__(("127.0.0.1", 0), _SynologyHandler)
        self.password = password
        self.sid: str = ""
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        host, port = self.server_address
        return f"http://{host}:{port}"

    def __enter__(self) -> "FakeSynologyServer":
        self._thread = threading.Thread(target=self.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self.shutdown()
        self.server_close()
        if self._thread:
            self._thread.join(timeout=2)
