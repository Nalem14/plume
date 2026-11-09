"""Built-in MCP server `ornis-bots`: CRUD for local Code-mode bots.

Started by Vibe with each Code session (ornis_code.mcp_servers). Packaged Plume:
`Plume --ornis-helper=bots-mcp`. Stdio MCP (JSON-RPC, Content-Length framing).
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import ornis_bots  # noqa: E402

TOOLS = [
    {
        "name": "bot_list",
        "description": "List local Code-mode bots on this computer (id, title, description, folder, hidden).",
        "inputSchema": {
            "type": "object",
            "properties": {"include_hidden": {"type": "boolean"}},
            "additionalProperties": False,
        },
    },
    {
        "name": "bot_create",
        "description": (
            "Create a durable bot profile. Pick a short kebab-case id, a title and a one-line description. "
            "Optional folder is its working directory; otherwise it uses its own workspace. "
            "A weekly Entretien routine is added automatically."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["id", "title"],
            "properties": {
                "id": {"type": "string", "description": "kebab-case id, 2–40 chars"},
                "title": {"type": "string"},
                "description": {"type": "string"},
                "folder": {"type": "string"},
                "soul": {"type": "string", "description": "Initial SOUL.md text"},
                "enabled_skills": {"type": "array", "items": {"type": "string"}},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "bot_update",
        "description": "Update a bot's title, description, folder, face, hidden flag or enabled Ornis skills.",
        "inputSchema": {
            "type": "object",
            "required": ["id"],
            "properties": {
                "id": {"type": "string"},
                "title": {"type": "string"},
                "description": {"type": "string"},
                "folder": {"type": "string"},
                "hidden": {"type": "boolean"},
                "enabled_skills": {"type": "array", "items": {"type": "string"}},
                "shape": {"type": "string"},
                "color": {"type": "string"},
                "lock_face": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "bot_set_soul",
        "description": "Replace this bot's SOUL.md (persona and standing instructions).",
        "inputSchema": {
            "type": "object",
            "required": ["id", "soul"],
            "properties": {"id": {"type": "string"}, "soul": {"type": "string"}},
            "additionalProperties": False,
        },
    },
    {
        "name": "bot_skills",
        "description": "List skills owned by a bot, and optionally set which Ornis-global skills it may use.",
        "inputSchema": {
            "type": "object",
            "required": ["id"],
            "properties": {
                "id": {"type": "string"},
                "enabled_skills": {"type": "array", "items": {"type": "string"},
                                  "description": "When set, replaces the enabled Ornis skills list"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "bot_message",
        "description": (
            "Send a message to another bot's durable chat. Fire-and-forget: returns queued; "
            "the target picks it up on its next turn. Compose your own message; do not forward "
            "the person's words verbatim."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["target", "message"],
            "properties": {
                "target": {"type": "string", "description": "Peer bot id"},
                "message": {"type": "string"},
                "from": {"type": "string", "description": "Sender id; defaults to ORNIS_BOT_ID"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "bot_delete",
        "description": "Permanently delete a bot profile. Requires confirm: true. Do not call without an explicit user request.",
        "inputSchema": {
            "type": "object",
            "required": ["id", "confirm"],
            "properties": {
                "id": {"type": "string"},
                "confirm": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
    },
]


def _lang() -> str:
    return (os.environ.get("ORNIS_BOT_LANG") or os.environ.get("ORNIS_CRON_LANG") or "fr")[:2]


def _sender(args: dict) -> str:
    return str(args.get("from") or os.environ.get("ORNIS_BOT_ID") or "").strip()


def _ok(data) -> dict:
    res = {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False, indent=2)}]}
    if isinstance(data, dict):
        res["structuredContent"] = data
    return res


def _err(msg: str) -> dict:
    return {"content": [{"type": "text", "text": json.dumps({"error": str(msg)}, ensure_ascii=False)}], "isError": True}


def call_tool(name: str, args: dict, ctx: dict | None = None) -> dict:
    args = args or {}
    try:
        if name == "bot_list":
            rows = []
            for b in ornis_bots.list_bots(include_hidden=bool(args.get("include_hidden", True))):
                rows.append({
                    "id": b["id"], "title": b.get("title"), "description": b.get("description"),
                    "folder": b.get("folder"), "hidden": b.get("hidden"),
                    "preview": b.get("preview"), "session": b.get("session"),
                    "face": b.get("face"),
                })
            return _ok({"bots": rows})
        if name == "bot_create":
            created = ornis_bots.create(args, lang=(ctx or {}).get("lang") or _lang())
            return _ok({"created": True, "bot": {
                "id": created["id"], "title": created["title"],
                "description": created.get("description"), "folder": created.get("folder"),
                "face": created.get("face"),
            }, "hint": "Confirm to the user in one sentence: title, role, where it works."})
        if name == "bot_update":
            fields = {k: args[k] for k in ("title", "description", "folder", "hidden", "enabled_skills")
                      if k in args and args[k] is not None}
            if any(k in args for k in ("shape", "color", "lock_face")):
                face = {}
                if "shape" in args and args["shape"]:
                    face["shape"] = args["shape"]
                if "color" in args and args["color"]:
                    face["color"] = args["color"]
                if "lock_face" in args:
                    face["locked"] = bool(args["lock_face"])
                fields["face"] = face
            if "enabled_skills" in fields:
                ornis_bots.set_enabled_skills(args["id"], fields.pop("enabled_skills"))
            updated = ornis_bots.update(args["id"], fields) if fields else ornis_bots.get(args["id"])
            if not updated:
                raise ValueError(f"unknown bot: {args['id']}")
            return _ok({"updated": True, "bot": {
                "id": updated["id"], "title": updated["title"],
                "description": updated.get("description"), "folder": updated.get("folder"),
                "hidden": updated.get("hidden"), "face": updated.get("face"),
                "enabled_skills": updated.get("enabled_skills"),
            }})
        if name == "bot_set_soul":
            ornis_bots.set_soul(args["id"], args.get("soul") or "")
            return _ok({"soul": True, "id": args["id"], "chars": len(args.get("soul") or "")})
        if name == "bot_skills":
            if "enabled_skills" in args and args["enabled_skills"] is not None:
                ornis_bots.set_enabled_skills(args["id"], list(args["enabled_skills"] or []))
            profile = ornis_bots.get(args["id"])
            if not profile:
                raise ValueError(f"unknown bot: {args['id']}")
            return _ok({
                "id": profile["id"],
                "owned": ornis_bots.list_skills(args["id"]),
                "enabled_skills": profile.get("enabled_skills") or [],
            })
        if name == "bot_message":
            sender = str(ctx.get("bot") or "") if ctx is not None else _sender(args)
            if not sender:
                raise ValueError("from / ORNIS_BOT_ID is required")
            row = ornis_bots.append_exchange(sender, args["target"], args.get("message") or "")
            return _ok({
                "queued": True, "id": row["id"], "from": row["from"], "to": row["to"],
                "hint": "Delivery is queued into the peer's durable chat; do not wait for a reply here.",
            })
        if name == "bot_delete":
            if not ornis_bots.remove(args["id"], confirm=bool(args.get("confirm"))):
                raise ValueError(f"unknown bot: {args['id']}")
            return _ok({"deleted": True, "id": args["id"]})
        return _err(f"unknown tool: {name}")
    except (ValueError, KeyError, TypeError) as err:
        return _err(str(err))


def _read_message():
    headers = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            break
        if b":" in line:
            k, v = line.decode("utf-8", "replace").split(":", 1)
            headers[k.strip().lower()] = v.strip()
    length = int(headers.get("content-length", "0"))
    if length <= 0:
        return None
    body = sys.stdin.buffer.read(length)
    return json.loads(body.decode("utf-8"))


def _write_message(msg: dict) -> None:
    data = json.dumps(msg, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(data)}\r\n\r\n".encode("ascii") + data)
    sys.stdout.buffer.flush()


def handle(msg: dict, ctx: dict | None = None) -> dict | None:
    mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": params.get("protocolVersion") or "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "ornis-bots", "version": "1.0.0"},
        }}
    if method == "notifications/initialized" or method == "initialized":
        return None
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}}
    if method == "tools/call":
        name = params.get("name") or ""
        args = params.get("arguments") or {}
        return {"jsonrpc": "2.0", "id": mid, "result": call_tool(name, args, ctx)}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}
    if mid is not None:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"Method not found: {method}"}}
    return None


def main() -> int:
    try:
        while True:
            try:
                msg = _read_message()
            except (ValueError, OSError):
                return 1
            if msg is None:
                return 0
            reply = handle(msg)
            if reply is not None:
                _write_message(reply)
    except Exception as err:  # noqa: BLE001
        print(f"ornis-bots: {type(err).__name__}: {err}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
