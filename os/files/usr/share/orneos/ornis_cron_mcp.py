"""Built-in MCP server `ornis-cron`: CRUD for local Code-mode cron tasks (cron.json).

Started by Vibe with each Code session (ornis_code.mcp_servers). Packaged Plume:
`Plume --ornis-helper=cron-mcp`. Stdio MCP (JSON-RPC, Content-Length framing).
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid

# share/orneos on the path when launched as a helper
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import ornis_cron  # noqa: E402

TOOLS = [
    {
        "name": "cron_list",
        "description": "List local Code-mode cron tasks on this computer (id, title, schedule, paused, next run, last runs).",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "cron_create",
        "description": (
            "Create a local Code cron task. schedule is a 5-field crontab or @daily/@hourly/@weekly/@monthly "
            "(wall-clock; min every 15 minutes; no @reboot). kind=chat opens a new Code conversation with prompt; "
            "kind=script runs command in the folder. Pick a short kebab-case id and a clear title/description."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["id", "title", "description", "kind", "schedule"],
            "properties": {
                "id": {"type": "string", "description": "kebab-case id, 3–40 chars (e.g. rapport-voitures)"},
                "title": {"type": "string"},
                "description": {"type": "string"},
                "kind": {"type": "string", "enum": ["chat", "script"]},
                "schedule": {"type": "string", "description": "crontab e.g. 0 8 * * * or @daily"},
                "prompt": {"type": "string", "description": "Required when kind=chat"},
                "command": {"type": "string", "description": "Required when kind=script"},
                "folder": {"type": "string", "description": "Project folder; defaults to ORNIS_CRON_FOLDER / cwd"},
                "paused": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "cron_update",
        "description": "Update fields of an existing cron task (title, description, schedule, prompt, command, paused).",
        "inputSchema": {
            "type": "object",
            "required": ["id"],
            "properties": {
                "id": {"type": "string"},
                "title": {"type": "string"},
                "description": {"type": "string"},
                "schedule": {"type": "string"},
                "prompt": {"type": "string"},
                "command": {"type": "string"},
                "paused": {"type": "boolean"},
                "kind": {"type": "string", "enum": ["chat", "script"]},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "cron_pause",
        "description": "Pause a cron task (keeps it, skips due times).",
        "inputSchema": {"type": "object", "required": ["id"], "properties": {"id": {"type": "string"}}, "additionalProperties": False},
    },
    {
        "name": "cron_resume",
        "description": "Resume a paused cron task.",
        "inputSchema": {"type": "object", "required": ["id"], "properties": {"id": {"type": "string"}}, "additionalProperties": False},
    },
    {
        "name": "cron_run",
        "description": "Queue a cron task to run soon (Ornis/Plume picks it up within ~20s). If a Code agent is already open on that folder, the run is deferred ~15 min instead of starting a second agent. The lightning button in the UI always starts immediately.",
        "inputSchema": {"type": "object", "required": ["id"], "properties": {"id": {"type": "string"}}, "additionalProperties": False},
    },
    {
        "name": "cron_delete",
        "description": "Delete a cron task. Past conversations stay on disk.",
        "inputSchema": {"type": "object", "required": ["id"], "properties": {"id": {"type": "string"}}, "additionalProperties": False},
    },
    {
        "name": "cron_history",
        "description": "List recent runs of a task (status, summary, linked session id).",
        "inputSchema": {
            "type": "object",
            "required": ["id"],
            "properties": {"id": {"type": "string"}, "limit": {"type": "integer"}},
            "additionalProperties": False,
        },
    },
]


def _context() -> dict:
    """Folder/lang from env, else the sidecar written by ornis_code.mcp_servers (thin MCP envs)."""
    try:
        path = ornis_cron.ROOT / "cron-mcp-context.json"
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}


def _folder(args: dict) -> str:
    ctx = _context()
    return str(args.get("folder") or os.environ.get("ORNIS_CRON_FOLDER")
               or ctx.get("folder") or os.getcwd()).strip()


def _lang() -> str:
    ctx = _context()
    return (os.environ.get("ORNIS_CRON_LANG") or ctx.get("lang") or "fr")[:2]


def _ok(data) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False, indent=2)}]}


def _err(msg: str) -> dict:
    return {"content": [{"type": "text", "text": json.dumps({"error": str(msg)}, ensure_ascii=False)}], "isError": True}


def call_tool(name: str, args: dict) -> dict:
    args = args or {}
    try:
        if name == "cron_list":
            rows = []
            for t in ornis_cron.tasks():
                last = (t.get("runs") or [{}])[0]
                rows.append({
                    "id": t.get("id"), "title": t.get("title"), "description": t.get("description"),
                    "kind": t.get("kind"), "schedule": t.get("schedule"),
                    "scheduleLabel": t.get("scheduleLabel"), "paused": t.get("paused"),
                    "folder": t.get("folder"), "next_run": t.get("next_run"),
                    "last_status": last.get("status"), "last_summary": last.get("summary"),
                })
            return _ok({"tasks": rows})
        if name == "cron_create":
            row = {
                "id": args["id"], "title": args.get("title") or args["id"],
                "description": args.get("description") or "",
                "kind": args.get("kind") or "chat",
                "schedule": args["schedule"],
                "prompt": args.get("prompt") or "",
                "command": args.get("command") or "",
                "folder": _folder(args),
                "paused": bool(args.get("paused", False)),
                "lang": _lang(),
                "pending": "create",
            }
            # ask-mode consent: leave paused until the app confirms when pending
            if row["pending"] and not args.get("paused"):
                # still schedule next_run; app may pause via pending UI
                pass
            created = ornis_cron.upsert(row, create=True)
            return _ok({"created": True, "task": {
                "id": created["id"], "title": created["title"], "schedule": created["schedule"],
                "scheduleLabel": created["scheduleLabel"], "kind": created["kind"],
                "folder": created["folder"], "next_run": created["next_run"],
            }, "hint": "Confirm to the user in one sentence: scheduleLabel, folder, where results will go."})
        if name == "cron_update":
            fields = {k: args[k] for k in ("title", "description", "schedule", "prompt", "command", "paused", "kind")
                      if k in args and args[k] is not None}
            if "schedule" in fields:
                fields["schedule"] = ornis_cron.validate_schedule(fields["schedule"])
            fields["pending"] = "update"
            updated = ornis_cron.patch(args["id"], fields, _lang())
            return _ok({"updated": True, "task": {
                "id": updated["id"], "title": updated["title"], "schedule": updated["schedule"],
                "scheduleLabel": updated["scheduleLabel"], "paused": updated["paused"],
            }})
        if name == "cron_pause":
            return _ok({"paused": True, "task": ornis_cron.set_paused(args["id"], True, _lang())["id"]})
        if name == "cron_resume":
            ornis_cron.set_paused(args["id"], False, _lang())
            ornis_cron.bump_next(args["id"])
            return _ok({"resumed": True, "id": args["id"]})
        if name == "cron_run":
            # Mark a manual trigger request the app picks up (next_run := now)
            t = ornis_cron.get(args["id"])
            if not t:
                raise ValueError(f"unknown task: {args['id']}")
            t["next_run"] = time.time() - 1
            t["force_run"] = True
            ornis_cron.upsert(t, create=False)
            return _ok({"queued": True, "id": args["id"],
                        "hint": "The running Ornis/Plume app will start it within about 20 seconds."})
        if name == "cron_delete":
            if not ornis_cron.remove(args["id"]):
                raise ValueError(f"unknown task: {args['id']}")
            return _ok({"deleted": True, "id": args["id"]})
        if name == "cron_history":
            t = ornis_cron.get(args["id"])
            if not t:
                raise ValueError(f"unknown task: {args['id']}")
            limit = max(1, min(40, int(args.get("limit") or 10)))
            return _ok({"id": t["id"], "runs": (t.get("runs") or [])[:limit]})
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


def handle(msg: dict) -> dict | None:
    mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": params.get("protocolVersion") or "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "ornis-cron", "version": "1.0.0"},
        }}
    if method == "notifications/initialized" or method == "initialized":
        return None
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}}
    if method == "tools/call":
        name = params.get("name") or ""
        args = params.get("arguments") or {}
        return {"jsonrpc": "2.0", "id": mid, "result": call_tool(name, args)}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}
    if mid is not None:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"Method not found: {method}"}}
    return None


def main() -> int:
    # Never print to stdout except MCP frames (Vibe treats any noise as transport failure)
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
        try:
            import ornis_cron  # noqa: PLC0415
            log = ornis_cron.ROOT / "cron-mcp.log"
            ornis_cron.ROOT.mkdir(parents=True, exist_ok=True)
            log.write_text(f"{type(err).__name__}: {err}\n", encoding="utf-8")
        except OSError:
            pass
        print(f"ornis-cron: {type(err).__name__}: {err}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
