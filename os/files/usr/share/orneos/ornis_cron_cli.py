"""CLI for local Code cron tasks — fallback when the ornis-cron MCP fails to connect.

Packaged Plume: `Plume --ornis-helper=cron-cli <cmd> …`
Dev: `python3 -I ornis_cron_cli.py <cmd> …`

Commands print one JSON object on stdout (no other noise). Exit 0 on success, 1 on error.
"""
from __future__ import annotations

import json
import sys

# share/orneos on the path when launched as a helper
HERE = __file__.rsplit("/", 1)[0] if "/" in __file__ else "."
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import ornis_cron_mcp  # noqa: E402


USAGE = """usage: ornis-cron <command> [json-args]

commands:
  list
  create   '{"id":"…","title":"…","schedule":"*/15 * * * *","kind":"chat","prompt":"…","folder":"…"}'
  update   '{"id":"…","schedule":"0 8 * * *",…}'
  pause    '{"id":"…"}'
  resume   '{"id":"…"}'
  run      '{"id":"…"}'
  delete   '{"id":"…"}'
  history  '{"id":"…","limit":10}'
"""


def system_windows() -> bool:
    return sys.platform.startswith("win")


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
    # drop Plume's --ornis-helper=cron-cli if still present
    argv = [a for a in argv if not a.startswith("--ornis-helper=")]
    if not argv or argv[0] in ("-h", "--help", "help"):
        sys.stdout.write(USAGE)
        return 0 if argv else 1
    cmd = argv[0].removeprefix("cron_")
    tool = f"cron_{cmd}" if not cmd.startswith("cron_") else cmd
    try:
        args = _parse_args(argv[1] if len(argv) > 1 else "")
    except (ValueError, json.JSONDecodeError) as err:
        sys.stdout.write(json.dumps({"error": str(err)}, ensure_ascii=False) + "\n")
        return 1
    # stdin JSON if no argv payload (handy for long prompts). Never for `list`, and only when something is
    # there: an agent's shell may hand over a pipe that never closes, and `read()` would hang the tool call.
    if len(argv) == 1 and tool != "cron_list" and sys.stdin is not None and not sys.stdin.isatty():
        try:
            if not system_windows():
                import select  # noqa: PLC0415
                ready, _, _ = select.select([sys.stdin], [], [], 1.0)
                if not ready:
                    raise EOFError
            extra = sys.stdin.read()
            if extra.strip():
                args = _parse_args(extra)
        except EOFError:
            pass
        except (ValueError, json.JSONDecodeError) as err:
            sys.stdout.write(json.dumps({"error": str(err)}, ensure_ascii=False) + "\n")
            return 1
    result = ornis_cron_mcp.call_tool(tool, args)
    text = ""
    for block in result.get("content") or []:
        if isinstance(block, dict) and block.get("type") == "text":
            text += str(block.get("text") or "")
    sys.stdout.write((text or json.dumps(result, ensure_ascii=False)) + "\n")
    return 1 if result.get("isError") else 0


if __name__ == "__main__":
    raise SystemExit(main())
