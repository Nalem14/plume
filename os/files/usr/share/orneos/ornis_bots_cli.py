"""CLI for local Code-mode bots — fallback when the ornis-bots MCP fails to connect.

Packaged Plume: `Plume --ornis-helper=bots-cli <cmd> …`
Dev: `python3 -I ornis_bots_cli.py <cmd> …`

Commands print one JSON object on stdout (no other noise). Exit 0 on success, 1 on error.
"""
from __future__ import annotations

import json
import sys

HERE = __file__.rsplit("/", 1)[0] if "/" in __file__ else "."
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import ornis_bots_mcp  # noqa: E402

USAGE = """usage: ornis-bots <command> [json-args]

commands:
  list
  create   '{"id":"…","title":"…","description":"…"}'
  update   '{"id":"…","title":"…",…}'
  soul     '{"id":"…","soul":"…"}'
  skills   '{"id":"…","enabled_skills":["…"]}'
  message  '{"target":"…","message":"…"}'   (from= ORNIS_BOT_ID)
  exchange '{"peer":"…"}'
  notify   '{"title":"…","message":"…"}'
  groups
  group-read '{"group":"…"}'
  history '{"query":"…"}'          (your thread before its summaries)
  group-post '{"group":"…","message":"…"}'
  group-create '{"title":"…","members":["…","…"]}'
  delete   '{"id":"…","confirm":true}'
"""

CMD_MAP = {
    "list": "bot_list",
    "create": "bot_create",
    "update": "bot_update",
    "soul": "bot_set_soul",
    "skills": "bot_skills",
    "message": "bot_message",
    "exchange": "bot_exchange",
    "notify": "notify_user",
    "groups": "group_list",
    "history": "history_search",
    "group-read": "group_read",
    "group-post": "group_post",
    "group-create": "group_create",
    "delete": "bot_delete",
}


def _parse_args(raw: str) -> dict:
    raw = (raw or "").strip()
    if not raw:
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("arguments must be a JSON object")
    return data


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    argv = [a for a in argv if not a.startswith("--ornis-helper=")]
    if not argv or argv[0] in ("-h", "--help", "help"):
        sys.stdout.write(USAGE)
        return 0 if argv else 1
    cmd = argv[0].removeprefix("bot_")
    tool = CMD_MAP.get(cmd) or (cmd if cmd.startswith(("bot_", "group_")) or cmd == "notify_user" else f"bot_{cmd}")
    try:
        args = _parse_args(argv[1] if len(argv) > 1 else "")
    except (ValueError, json.JSONDecodeError) as err:
        sys.stdout.write(json.dumps({"error": str(err)}, ensure_ascii=False) + "\n")
        return 1
    if len(argv) == 1 and not sys.stdin.isatty():
        try:
            extra = sys.stdin.read()
            if extra.strip():
                args = _parse_args(extra)
        except (ValueError, json.JSONDecodeError) as err:
            sys.stdout.write(json.dumps({"error": str(err)}, ensure_ascii=False) + "\n")
            return 1
    result = ornis_bots_mcp.call_tool(tool, args)
    text = ""
    for block in result.get("content") or []:
        if isinstance(block, dict) and block.get("type") == "text":
            text += str(block.get("text") or "")
    sys.stdout.write((text or json.dumps(result, ensure_ascii=False)) + "\n")
    return 1 if result.get("isError") else 0


if __name__ == "__main__":
    raise SystemExit(main())
