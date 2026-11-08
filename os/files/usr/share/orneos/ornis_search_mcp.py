"""Built-in MCP server `ornis-search`: web search + page read via Orneos Search (Code gateway).

Started by Vibe with each Code session (ornis_code.mcp_servers). Packaged Plume:
`Plume --ornis-helper=search-mcp`. Calls app.orneos.eu `/ornis/code/v1/search|fetch`
with ORNEOS_CODE_TOKEN (never logs the query).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

TOOLS = [
    {
        "name": "web_search",
        "description": (
            "Search the web with Orneos Search (private European search). Use for facts, recent events, "
            "product listings, documentation you do not have locally, or when the user asks for a web search. "
            "Then use read_web_page on the most useful results."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string", "description": "Search terms, in the user's language"},
                "time_range": {
                    "type": "string",
                    "enum": ["day", "week", "month", "year"],
                    "description": "Optional: keep only recent results",
                },
                "language": {
                    "type": "string",
                    "description": "Optional language code of results, e.g. fr, en, de",
                },
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "read_web_page",
        "description": (
            "Read a public http(s) page as plain text (parts of ~8000 characters). "
            "Use after web_search. Ask for part 2+ only if part 1 was not enough. "
            "Do not use for app.orneos.eu or other Orneos URLs."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["url"],
            "properties": {
                "url": {"type": "string", "description": "http(s) address of the page"},
                "part": {"type": "integer", "description": "Part number, starting at 1", "minimum": 1},
            },
            "additionalProperties": False,
        },
    },
]


def _gateway() -> tuple[str, str]:
    url = (os.environ.get("ORNEOS_CODE_URL") or "").rstrip("/")
    token = os.environ.get("ORNEOS_CODE_TOKEN") or ""
    if not url or not token:
        # Fallback: gateway.json written next to cron context (no token on disk — token only in env)
        try:
            import ornis_cron  # noqa: PLC0415
            path = ornis_cron.ROOT / "gateway.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            url = url or str(data.get("url") or "").rstrip("/")
        except Exception:  # noqa: BLE001
            pass
    if not url:
        url = "https://app.orneos.eu/apps/orneos/ornis/code/v1"
    return url, token


def _post(path: str, body: dict) -> dict:
    base, token = _gateway()
    if not token:
        return {"error": "not_signed_in", "message": "Ornis Code is not signed in on this computer."}
    raw = json.dumps(body, ensure_ascii=False).encode()
    req = urllib.request.Request(
        f"{base}{path}",
        data=raw,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Ornis-Code/ornis-search",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace") or "{}")
            return data if isinstance(data, dict) else {"error": "bad_response"}
    except urllib.error.HTTPError as err:
        try:
            detail = json.loads(err.read().decode("utf-8", "replace") or "{}")
        except Exception:  # noqa: BLE001
            detail = {}
        code = str((detail or {}).get("code") or (detail or {}).get("type") or err.code)
        return {"error": code, "message": f"HTTP {err.code}: {code}"}
    except Exception as err:  # noqa: BLE001
        return {"error": "network", "message": str(err)[:200]}


def call_tool(name: str, args: dict) -> dict:
    args = args if isinstance(args, dict) else {}
    if name == "web_search":
        body = {"query": str(args.get("query") or "").strip()}
        if args.get("time_range"):
            body["time_range"] = str(args["time_range"])
        if args.get("language"):
            body["language"] = str(args["language"])
        out = _post("/search", body)
    elif name == "read_web_page":
        out = _post("/fetch", {
            "url": str(args.get("url") or "").strip(),
            "part": int(args.get("part") or 1),
        })
    else:
        return _err(f"unknown tool: {name}")
    if out.get("error") and "results" not in out and "text" not in out:
        return _err(str(out.get("message") or out.get("error")))
    return _ok(out)


def _ok(data) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False, indent=2)}]}


def _err(msg: str) -> dict:
    return {"content": [{"type": "text", "text": msg}], "isError": True}


def _read() -> dict | None:
    header = b""
    while b"\r\n\r\n" not in header:
        chunk = sys.stdin.buffer.read(1)
        if not chunk:
            return None
        header += chunk
        if len(header) > 8192:
            return None
    head = header.decode("utf-8", "replace")
    length = 0
    for line in head.split("\r\n"):
        if line.lower().startswith("content-length:"):
            try:
                length = int(line.split(":", 1)[1].strip())
            except ValueError:
                return None
    body = b""
    while len(body) < length:
        chunk = sys.stdin.buffer.read(length - len(body))
        if not chunk:
            return None
        body += chunk
    try:
        return json.loads(body.decode("utf-8"))
    except ValueError:
        return None


def _write(msg: dict) -> None:
    raw = json.dumps(msg, ensure_ascii=False).encode()
    sys.stdout.buffer.write(f"Content-Length: {len(raw)}\r\n\r\n".encode() + raw)
    sys.stdout.buffer.flush()


def handle(msg: dict) -> dict | None:
    mid = msg.get("id")
    method = msg.get("method") or ""
    params = msg.get("params") or {}
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": str(params.get("protocolVersion") or "2024-11-05"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "ornis-search", "version": "1.0.0"},
        }}
    if method in ("notifications/initialized", "initialized"):
        return None
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}}
    if method == "tools/call":
        result = call_tool(str(params.get("name") or ""), params.get("arguments") or {})
        return {"jsonrpc": "2.0", "id": mid, "result": result}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}
    if mid is not None:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"Method not found: {method}"}}
    return None


# Back-compat for older call sites
_handle = handle


def main() -> int:
    try:
        while True:
            msg = _read()
            if msg is None:
                return 0
            reply = handle(msg)
            if reply is not None:
                _write(reply)
    except Exception as err:  # noqa: BLE001
        print(f"ornis-search: {type(err).__name__}: {err}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
