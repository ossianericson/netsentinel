"""
REST API — read-only local HTTP API for NetSentinel (Tier 2 item 5).

Exposes network scan data to external tools (Grafana, Home Assistant,
scripts) over a lightweight Flask server bound to 127.0.0.1 by default.

Security design (mandatory constraints from architecture.instructions.md):
  • Binds 127.0.0.1:8765 by default — never 0.0.0.0 without explicit opt-in
  • Binding to 0.0.0.0 requires the user to toggle "Allow external access" in
    Settings AND acknowledge the warning label displayed there
  • API key: secrets.token_hex(32), stored in OS keychain (RULE 22-A)
  • Every request must present the key in the X-API-Key header or ?api_key=
  • Disabled by default — user must explicitly enable in Settings
  • Read-only: no POST/PUT/DELETE endpoints are exposed

Endpoints:
  GET /health                    — server heartbeat + uptime
  GET /devices                   — current known device inventory
  GET /alerts                    — recent fired alerts (last 24h)
  GET /uptime/<ip>               — uptime stats for a specific host
  GET /speed-history             — speed test history (last 7 days)

Flask is an optional dependency. If not installed the module still imports
cleanly — the worker will surface the missing dependency gracefully.
"""
from __future__ import annotations

import secrets
import time
from typing import Optional

from modules.metric_store import MetricStore

# ── Keyring helper (RULE 22-A) ────────────────────────────────────────────────
_KR_SERVICE     = "NetSentinel"
_KR_API_KEY_KEY = "rest_api/api_key"

try:
    import keyring as _keyring
    _KEYRING_OK = True
except ImportError:
    _keyring = None  # type: ignore
    _KEYRING_OK = False


def get_or_create_api_key() -> str:
    """
    Return the stored API key, generating a new one if none exists.
    The key is stored in the OS keychain (RULE 22-A).
    """
    if _KEYRING_OK:
        existing = _keyring.get_password(_KR_SERVICE, _KR_API_KEY_KEY)
        if existing:
            return existing
    # Generate a new key
    key = secrets.token_hex(32)
    if _KEYRING_OK:
        _keyring.set_password(_KR_SERVICE, _KR_API_KEY_KEY, key)
    return key


def regenerate_api_key() -> str:
    """Generate and store a brand-new API key, invalidating the previous one."""
    key = secrets.token_hex(32)
    if _KEYRING_OK:
        _keyring.set_password(_KR_SERVICE, _KR_API_KEY_KEY, key)
    return key


def get_stored_api_key() -> str:
    """Return the stored API key, or empty string if none set."""
    if not _KEYRING_OK:
        return ""
    try:
        return _keyring.get_password(_KR_SERVICE, _KR_API_KEY_KEY) or ""
    except Exception:
        return ""


# ── Flask app factory ─────────────────────────────────────────────────────────

FLASK_AVAILABLE = False
try:
    from flask import Flask, jsonify, request, abort  # type: ignore
    FLASK_AVAILABLE = True
except ImportError:
    pass

_start_ts: float = time.time()


def create_app(store: MetricStore) -> "Flask":
    """
    Build the Flask application.  store is the MetricStore singleton injected
    from app.py — all endpoints are read-only queries against this store.
    """
    if not FLASK_AVAILABLE:
        raise ImportError(
            "Flask is required for the REST API. Install it with:\n"
            "  pip install flask"
        )

    app = Flask("netsentinel_api")
    app.config["JSON_SORT_KEYS"] = False

    # ── Auth middleware ───────────────────────────────────────────────────────

    @app.before_request
    def _auth():
        # Health endpoint is public (useful for monitoring tools without auth)
        if request.path == "/health":
            return None
        expected = get_stored_api_key()
        if not expected:
            abort(503, description="API key not configured — enable the REST API in Settings first.")
        provided = (
            request.headers.get("X-API-Key", "")
            or request.args.get("api_key", "")
        )
        if not secrets.compare_digest(provided, expected):
            abort(401, description="Invalid or missing API key.")
        return None

    # ── Error handlers ────────────────────────────────────────────────────────

    @app.errorhandler(401)
    def _err401(e):
        return jsonify({"error": str(e)}), 401

    @app.errorhandler(404)
    def _err404(e):
        return jsonify({"error": "Not found"}), 404

    @app.errorhandler(503)
    def _err503(e):
        return jsonify({"error": str(e)}), 503

    # ── Endpoints ─────────────────────────────────────────────────────────────

    @app.route("/health")
    def health():
        return jsonify({
            "status":     "ok",
            "uptime_s":   round(time.time() - _start_ts, 1),
            "version":    "1.5.1",
        })

    @app.route("/devices")
    def devices():
        rows = store._execute_read(
            "SELECT mac, ip, hostname, vendor, device_type, "
            "first_seen, last_seen, is_authorized, category, custom_name, room "
            "FROM known_device ORDER BY last_seen DESC",
            (),
        )
        return jsonify([dict(r) for r in rows])

    @app.route("/alerts")
    def alerts():
        hours = float(request.args.get("hours", 24))
        rows = store.get_recent_alerts(hours=hours)
        return jsonify(rows)

    @app.route("/uptime/<ip>")
    def uptime(ip: str):
        hours = float(request.args.get("hours", 24))
        since = int(time.time()) - int(hours * 3600)
        rows = store._execute_read(
            "SELECT ts, state, rtt_ms FROM device_state "
            "WHERE ip=? AND ts>=? ORDER BY ts ASC",
            (ip, since),
        )
        if not rows:
            return jsonify({"ip": ip, "error": "No data found for this host."}), 404
        states = [dict(r) for r in rows]
        total  = len(states)
        up     = sum(1 for s in states if s["state"] == "UP")
        pct    = round((up / total * 100), 2) if total else 0.0
        rtts   = [s["rtt_ms"] for s in states if s["rtt_ms"] is not None and s["rtt_ms"] >= 0]
        return jsonify({
            "ip":          ip,
            "hours":       hours,
            "uptime_pct":  pct,
            "samples":     total,
            "avg_rtt_ms":  round(sum(rtts) / len(rtts), 2) if rtts else None,
            "history":     states,
        })

    @app.route("/speed-history")
    def speed_history():
        hours = float(request.args.get("hours", 168))  # 7 days default
        points = store.query_speed_test_history(hours=hours)
        return jsonify([
            {
                "ts":            p.ts,
                "download_mbps": p.download_mbps,
                "upload_mbps":   p.upload_mbps,
                "ping_ms":       p.ping_ms,
                "server":        p.server_name,
            }
            for p in points
        ])

    return app


# ── Server runner (called from worker thread) ─────────────────────────────────

def run_server(
    store: MetricStore,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> None:
    """
    Start the Flask development server.  This is a blocking call — run it
    from a daemon thread.  The server logs to stderr (suppressed by the worker).
    """
    import logging
    import os

    # Suppress Flask startup banner and werkzeug request logging
    log = logging.getLogger("werkzeug")
    log.setLevel(logging.ERROR)
    os.environ["WERKZEUG_RUN_MAIN"] = "true"

    app = create_app(store)
    app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)
