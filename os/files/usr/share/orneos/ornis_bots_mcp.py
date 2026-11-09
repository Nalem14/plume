"""Built-in MCP server `ornis-bots`: local Code-mode bots (profiles, peer messages, groups, notifications).

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
        "description": ("Update your own profile, or one of a bot you created: title, description, folder (inside your "
                        "working folder), face, hidden flag or enabled Ornis skills."),
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
        "description": "Replace the SOUL.md (persona and standing instructions) of yourself or of a bot you created.",
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
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "bot_exchange",
        "description": "Read your past messages with another bot (oldest first), to recall what was agreed.",
        "inputSchema": {
            "type": "object",
            "required": ["peer"],
            "properties": {"peer": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 100}},
            "additionalProperties": False,
        },
    },
    {
        "name": "notify_user",
        "description": (
            "Show a desktop notification to the person (6 per hour at most). Only for what they must see soon: "
            "a result they asked to be told about, or a problem that blocks you. Not for ordinary answers."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["message"],
            "properties": {"title": {"type": "string"}, "message": {"type": "string", "description": "One or two sentences"}},
            "additionalProperties": False,
        },
    },
    {
        "name": "group_list",
        "description": "List the groups (rooms shared by several bots and the person) with their members and lead.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "group_read",
        "description": "Read the last messages of a group you belong to.",
        "inputSchema": {
            "type": "object",
            "required": ["group"],
            "properties": {"group": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 100}},
            "additionalProperties": False,
        },
    },
    {
        "name": "group_post",
        "description": (
            "Post a message in a group you belong to (a routine's result, a hand-over). Members named with @id get it "
            "as a turn; nobody else is woken. In a group turn, your final answer is already posted: do not repeat it."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["group", "message"],
            "properties": {"group": {"type": "string"}, "message": {"type": "string"}},
            "additionalProperties": False,
        },
    },
    {
        "name": "group_create",
        "description": (
            "Create a group of bots (at least two, you included) for a shared project, when the person asks for it. "
            "The lead answers messages that name nobody; reply \"all\" makes every member answer."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["title", "members"],
            "properties": {
                "title": {"type": "string"},
                "description": {"type": "string", "description": "What the group is for"},
                "members": {"type": "array", "items": {"type": "string"}},
                "lead": {"type": "string"},
                "reply": {"type": "string", "enum": ["lead", "all"]},
                "folder": {"type": "string", "description": "Shared folder (inside your working folder); default: the group's own"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "bot_delete",
        "description": ("Permanently delete a bot profile you created. Requires confirm: true. Do not call without an "
                        "explicit request of the person. A bot cannot delete itself nor a bot it did not create."),
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


def _actor(ctx: dict | None) -> str:
    """The bot calling (its session's context, else the CLI's environment); empty for an ordinary session."""
    if ctx is not None:
        return str(ctx.get("bot") or "").strip()
    return str(os.environ.get("ORNIS_BOT_ID") or "").strip()


def _ok(data) -> dict:
    res = {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False, indent=2)}]}
    if isinstance(data, dict):
        res["structuredContent"] = data
    return res


def _err(msg: str) -> dict:
    return {"content": [{"type": "text", "text": json.dumps({"error": str(msg)}, ensure_ascii=False)}], "isError": True}


def call_tool(name: str, args: dict, ctx: dict | None = None) -> dict:
    args = args or {}
    actor = _actor(ctx)
    try:
        if name == "bot_list":
            rows = []
            for b in ornis_bots.list_bots(include_hidden=bool(args.get("include_hidden", True))):
                rows.append({
                    "id": b["id"], "title": b.get("title"), "description": b.get("description"),
                    "folder": b.get("folder"), "hidden": b.get("hidden"), "face": b.get("face"),
                    "yours": bool(actor and (b["id"] == actor or b.get("created_by") == actor)),
                })
            return _ok({"bots": rows, "you": actor or None})
        if name == "bot_create":
            created = ornis_bots.create(args, lang=(ctx or {}).get("lang") or _lang(), actor=actor)
            return _ok({"created": True, "bot": {
                "id": created["id"], "title": created["title"],
                "description": created.get("description"), "folder": created.get("folder"),
                "face": created.get("face"),
            }, "hint": "Confirm to the user in one sentence: title, role, where it works."})
        if name == "bot_update":
            ornis_bots.check_manage(actor, args["id"])
            if actor and "folder" in args:
                ornis_bots._check_folder_scope(actor, args.get("folder"))
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
            ornis_bots.check_manage(actor, args["id"])
            ornis_bots.set_soul(args["id"], args.get("soul") or "")
            return _ok({"soul": True, "id": args["id"], "chars": len(args.get("soul") or "")})
        if name == "bot_skills":
            if "enabled_skills" in args and args["enabled_skills"] is not None:
                ornis_bots.check_manage(actor, args["id"])
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
            if not actor:
                raise ValueError("bot_message is for bots: this session is not a bot")
            row = ornis_bots.append_exchange(actor, args["target"], args.get("message") or "")
            return _ok({
                "queued": True, "id": row["id"], "from": row["from"], "to": row["to"],
                "hint": "Delivery is queued into the peer's durable chat; do not wait for a reply here.",
            })
        if name == "bot_exchange":
            if not actor:
                raise ValueError("bot_exchange is for bots: this session is not a bot")
            rows = ornis_bots.read_exchange(actor, args["peer"], limit=int(args.get("limit") or 30))
            return _ok({"messages": [{"from": r.get("from"), "to": r.get("to"), "text": r.get("text"),
                                      "at": r.get("at")} for r in rows]})
        if name == "notify_user":
            if not actor:
                raise ValueError("notify_user is for bots: this session is not a bot")
            row = ornis_bots.push_notice(actor, args.get("title") or "", args.get("message") or "")
            return _ok({"notified": True, "id": row["id"]})
        if name == "group_list":
            return _ok({"groups": [{"id": g["id"], "title": g["title"], "description": g["description"],
                                    "members": g["members"], "lead": g["lead"], "reply": g["reply"],
                                    "folder": ornis_bots.group_folder(g["id"]) if actor in g["members"] else None,
                                    "member": bool(actor in g["members"])} for g in ornis_bots.list_groups()]})
        if name == "group_read":
            g = ornis_bots.get_group(args["group"])
            if not g:
                raise ValueError(f"unknown group: {args['group']}")
            if actor and actor not in g["members"]:
                raise ValueError("you are not a member of this group")
            rows = ornis_bots.read_group(g["id"], limit=int(args.get("limit") or 30))
            return _ok({"group": g["id"], "messages": [{"from": r.get("from"), "text": r.get("text"), "at": r.get("at")}
                                                       for r in rows]})
        if name == "group_post":
            if not actor:
                raise ValueError("group_post is for bots: this session is not a bot")
            row = ornis_bots.post_group(args["group"], actor, args.get("message") or "",
                                        depth=ornis_bots.turn_depth(actor, args["group"]))
            return _ok({"posted": True, "id": row["id"], "delivered_to": row.get("targets") or []})
        if name == "group_create":
            g = ornis_bots.create_group(args, actor=actor)
            return _ok({"created": True, "group": {"id": g["id"], "title": g["title"], "members": g["members"],
                                                   "lead": g["lead"], "reply": g["reply"],
                                                   "folder": ornis_bots.group_folder(g["id"])}})
        if name == "bot_delete":
            if not ornis_bots.remove(args["id"], confirm=bool(args.get("confirm")), actor=actor):
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
            "serverInfo": {"name": "ornis-bots", "version": "1.1.0"},
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
