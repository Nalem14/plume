"""Local Streamable-HTTP bridge for Ornis Code's built-in MCP servers.

Vibe spawns stdio MCP children inside the same OS sandbox as itself (seatbelt on
macOS, bwrap on Linux). On a Mac without a real python3, those children re-enter
Plume via `--ornis-helper=*mcp` and fail (mcp_transport_failed), while the bash
CLI can retry outside the sandbox.

Hosting cron + search + bots here — in the already-running Ornis/Plume process — and
advertising `type: http` URLs keeps MCP outside that sandbox. Vibe talks to
127.0.0.1 only; a bearer token in Authorization is required.
"""
from __future__ import annotations

import json
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

_lock = threading.Lock()
_server: ThreadingHTTPServer | None = None
_token = ""
_base = ""
_contexts: dict[str, dict] = {}     # key in /mcp/cron/<key> → {folder, lang, bot}: one shared server per session


def context_key(folder: str, lang: str = "fr", bot: str = "") -> str:
    """A stable key for a Code session's folder (the cron MCP files new tasks there, not in the last folder opened)."""
    import hashlib  # noqa: PLC0415
    folder, lang, bot = str(folder or "").strip(), (lang or "fr")[:2], str(bot or "").strip()
    key = hashlib.sha256(f"{folder}\0{lang}\0{bot}".encode("utf-8")).hexdigest()[:16]
    with _lock:
        _contexts[key] = {"folder": folder, "lang": lang, "bot": bot}
    return key


def _dispatch(kind: str, msg: dict, key: str = "") -> dict | None:
    if kind == "cron":
        import ornis_cron_mcp  # noqa: PLC0415
        return ornis_cron_mcp.handle(msg, _contexts.get(key))
    if kind == "search":
        import ornis_search_mcp  # noqa: PLC0415
        # search module uses _handle; expose the same shape as cron
        handle = getattr(ornis_search_mcp, "handle", None) or ornis_search_mcp._handle
        return handle(msg)
    if kind == "bots":
        import ornis_bots_mcp  # noqa: PLC0415
        return ornis_bots_mcp.handle(msg, _contexts.get(key))
    return {"jsonrpc": "2.0", "id": msg.get("id"),
            "error": {"code": -32601, "message": f"unknown MCP: {kind}"}}


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003 — silence access log
        return

    def _unauthorized(self) -> None:
        self.send_response(401)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"error":"unauthorized"}')

    def _check_auth(self) -> bool:
        auth = self.headers.get("Authorization") or ""
        expected = "Bearer " + _token
        return bool(_token) and secrets.compare_digest(auth, expected)

    def _parts(self) -> tuple[str | None, str]:
        path = urlparse(self.path).path.rstrip("/")
        # /mcp/cron, /mcp/cron/<context key>, /mcp/search or /mcp/bots[/<key>]
        parts = [p for p in path.split("/") if p]
        if len(parts) in (2, 3) and parts[0] == "mcp" and parts[1] in ("cron", "search", "bots"):
            return parts[1], (parts[2] if len(parts) == 3 else "")
        return None, ""

    def _kind(self) -> str | None:
        return self._parts()[0]

    def do_GET(self) -> None:  # noqa: N802
        if not self._check_auth():
            self._unauthorized()
            return
        if self._kind() is None:
            self.send_response(404)
            self.end_headers()
            return
        # Standalone SSE not needed for our tools; older clients may probe.
        self.send_response(405)
        self.send_header("Allow", "POST")
        self.end_headers()

    def do_DELETE(self) -> None:  # noqa: N802
        if not self._check_auth():
            self._unauthorized()
            return
        self.send_response(405)
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        if not self._check_auth():
            self._unauthorized()
            return
        kind, key = self._parts()
        if kind is None:
            self.send_response(404)
            self.end_headers()
            return
        try:
            length = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            length = 0
        if length <= 0 or length > 4_000_000:
            self.send_response(400)
            self.end_headers()
            return
        raw = self.rfile.read(length)
        try:
            msg = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            self.send_response(400)
            self.end_headers()
            return
        if not isinstance(msg, dict):
            self.send_response(400)
            self.end_headers()
            return

        # Notifications / responses: 202 with empty body (Streamable HTTP)
        if msg.get("id") is None and msg.get("method"):
            _dispatch(kind, msg, key)  # may be notifications/initialized
            self.send_response(202)
            self.end_headers()
            return
        if msg.get("method") is None:
            self.send_response(202)
            self.end_headers()
            return

        reply = _dispatch(kind, msg, key)
        if reply is None:
            self.send_response(202)
            self.end_headers()
            return
        body = json.dumps(reply, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def ensure() -> dict | None:
    """Start the bridge once. Returns {base, token, cron_url, search_url, bots_url} or None."""
    global _server, _token, _base
    with _lock:
        if _server is not None and _base and _token:
            return {
                "base": _base, "token": _token,
                "cron_url": f"{_base}/cron", "search_url": f"{_base}/search",
                "bots_url": f"{_base}/bots",
            }
        try:
            # Bind loopback only; port chosen by the OS
            httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        except OSError:
            return None
        _token = secrets.token_urlsafe(24)
        host, port = httpd.server_address[:2]
        _base = f"http://{host}:{port}/mcp"
        _server = httpd
        thread = threading.Thread(target=httpd.serve_forever, name="ornis-mcp-http", daemon=True)
        thread.start()
        # Sidecar for diagnosis (no token)
        try:
            import ornis_cron  # noqa: PLC0415
            ornis_cron.ROOT.mkdir(parents=True, exist_ok=True)
            (ornis_cron.ROOT / "mcp-http.json").write_text(
                json.dumps({"base": _base, "pid": os.getpid()}, ensure_ascii=False),
                encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
        return {
            "base": _base, "token": _token,
            "cron_url": f"{_base}/cron", "search_url": f"{_base}/search",
            "bots_url": f"{_base}/bots",
        }


def stop() -> None:
    """Tests only."""
    global _server, _token, _base
    with _lock:
        if _server is not None:
            try:
                _server.shutdown()
            except Exception:  # noqa: BLE001
                pass
            _server = None
            _token = ""
            _base = ""
