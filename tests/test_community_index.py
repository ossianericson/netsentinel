"""tests/test_community_index.py — P3-4: community plugin index download + SHA-256 verification"""
import hashlib
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from PyQt6.QtWidgets import QApplication


def _wait(condition, timeout=6.0, step=0.05) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if condition():
            return True
        time.sleep(step)
    return False


def _thread_cleanup(thread) -> None:
    """RULE-WIN4: QThread is a QObject — deleteLater() must be called explicitly.
    topLevelWidgets() only catches QWidget subclasses; QThread escapes conftest cleanup."""
    try:
        thread.deleteLater()
    except RuntimeError:
        pass  # non-fatal — object already deleted
    app = QApplication.instance()
    if app:
        try:
            from PyQt6.QtCore import QCoreApplication, QEvent
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
        except Exception:
            pass  # non-fatal — best-effort cleanup
        for _ in range(3):
            app.processEvents()


# ── Helpers ───────────────────────────────────────────────────────────────────

_PLUGIN_SRC = b"""\
HARDWARE_NAME = "Example Router"
HARDWARE_TYPE = "router"
HARDWARE_IP   = "192.168.1.1"

def get_info():
    return {"name": HARDWARE_NAME, "type": HARDWARE_TYPE}

def get_status():
    return {"connected_clients": 0, "extra": {}}
"""


class _MockHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler that serves either the index JSON or the plugin source."""

    index_data: bytes = b"[]"
    plugin_data: bytes = _PLUGIN_SRC

    def do_GET(self):
        if self.path == "/index.json":
            self._serve(self.index_data, "application/json")
        elif self.path == "/plugin.py":
            self._serve(self.plugin_data, "text/plain")
        else:
            self.send_response(404)
            self.end_headers()

    def _serve(self, body: bytes, ct: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass  # silence request log during tests


def _start_server(handler_class):
    srv = HTTPServer(("127.0.0.1", 0), handler_class)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv, srv.server_address[1]


# ── _CommunityIndexThread ─────────────────────────────────────────────────────

def test_community_index_thread_import():
    from ui.pages.hardware_integration_page import _CommunityIndexThread
    assert _CommunityIndexThread is not None


def test_community_index_thread_fetches_list():
    from ui.pages.hardware_integration_page import _CommunityIndexThread

    index = [{"name": "Test", "author": "Bob", "desc": "A plugin",
              "pypi": "", "file_url": "", "sha256": ""}]

    class _H(_MockHandler):
        index_data = json.dumps(index).encode()

    srv, port = _start_server(_H)
    thread = None
    try:
        url = f"http://127.0.0.1:{port}/index.json"
        thread = _CommunityIndexThread(url)
        results = []
        errors = []
        thread.done.connect(results.append)
        thread.error.connect(errors.append)
        thread.start()
        assert _wait(lambda: not thread.isRunning()), "Thread timed out"
        assert not errors, f"Unexpected errors: {errors}"
        assert len(results) == 1
        assert results[0] == index
    finally:
        if thread is not None:
            _thread_cleanup(thread)
        srv.shutdown()


def test_community_index_thread_error_on_bad_url():
    from ui.pages.hardware_integration_page import _CommunityIndexThread

    # Port 1 is always refused on any OS
    thread = _CommunityIndexThread("http://127.0.0.1:1/nonexistent.json")
    errors = []
    thread.error.connect(errors.append)
    thread.start()
    try:
        assert _wait(lambda: not thread.isRunning()), "Thread timed out"
        # Flush the Qt event queue — the error signal is posted cross-thread and may
        # still be pending in the queue when isRunning() first returns False (macOS).
        app = QApplication.instance()
        if app:
            for _ in range(3):
                app.processEvents()
        assert errors
    finally:
        _thread_cleanup(thread)


def test_community_index_thread_error_on_non_list():
    from ui.pages.hardware_integration_page import _CommunityIndexThread

    class _H(_MockHandler):
        index_data = b'{"not": "a list"}'

    srv, port = _start_server(_H)
    thread = None
    try:
        thread = _CommunityIndexThread(f"http://127.0.0.1:{port}/index.json")
        errors = []
        thread.error.connect(errors.append)
        thread.start()
        assert _wait(lambda: not thread.isRunning()), "Thread timed out"
        assert errors
    finally:
        if thread is not None:
            _thread_cleanup(thread)
        srv.shutdown()


# ── _CommunityDownloadThread ──────────────────────────────────────────────────

def test_community_download_thread_import():
    from ui.pages.hardware_integration_page import _CommunityDownloadThread
    assert _CommunityDownloadThread is not None


def test_community_download_thread_success(tmp_path, monkeypatch):
    from ui.pages.hardware_integration_page import _CommunityDownloadThread

    monkeypatch.setattr("modules.utils.get_app_data_dir", lambda: tmp_path)

    class _H(_MockHandler):
        pass  # serves _PLUGIN_SRC on /plugin.py

    srv, port = _start_server(_H)
    thread = None
    try:
        sha = hashlib.sha256(_PLUGIN_SRC).hexdigest()
        thread = _CommunityDownloadThread(
            f"http://127.0.0.1:{port}/plugin.py", sha, "Example Router"
        )
        results = []
        errors = []
        thread.done.connect(results.append)
        thread.error.connect(errors.append)
        thread.start()
        assert _wait(lambda: not thread.isRunning(), timeout=8), "Thread timed out"
        assert not errors, f"Unexpected errors: {errors}"
        assert len(results) == 1
        assert Path(results[0]).exists()
        assert Path(results[0]).read_bytes() == _PLUGIN_SRC
    finally:
        if thread is not None:
            _thread_cleanup(thread)
        srv.shutdown()


def test_community_download_thread_sha256_mismatch(tmp_path, monkeypatch):
    from ui.pages.hardware_integration_page import _CommunityDownloadThread

    monkeypatch.setattr("modules.utils.get_app_data_dir", lambda: tmp_path)

    class _H(_MockHandler):
        pass

    srv, port = _start_server(_H)
    thread = None
    try:
        thread = _CommunityDownloadThread(
            f"http://127.0.0.1:{port}/plugin.py",
            "a" * 64,   # wrong SHA-256
            "Example Router",
        )
        errors = []
        thread.error.connect(errors.append)
        thread.start()
        assert _wait(lambda: not thread.isRunning(), timeout=8), "Thread timed out"
        assert errors
        assert any("mismatch" in e.lower() for e in errors)
    finally:
        if thread is not None:
            _thread_cleanup(thread)
        srv.shutdown()


def test_community_download_thread_no_sha256_check(tmp_path, monkeypatch):
    """Empty sha256 string means skip verification — download should succeed."""
    from ui.pages.hardware_integration_page import _CommunityDownloadThread

    monkeypatch.setattr("modules.utils.get_app_data_dir", lambda: tmp_path)

    class _H(_MockHandler):
        pass

    srv, port = _start_server(_H)
    thread = None
    try:
        thread = _CommunityDownloadThread(
            f"http://127.0.0.1:{port}/plugin.py", "", "Example Router"
        )
        results = []
        thread.done.connect(results.append)
        thread.start()
        assert _wait(lambda: not thread.isRunning(), timeout=8), "Thread timed out"
        assert results
    finally:
        if thread is not None:
            _thread_cleanup(thread)
        srv.shutdown()
