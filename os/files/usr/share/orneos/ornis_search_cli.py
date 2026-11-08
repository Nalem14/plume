"""CLI for Orneos Search in Code — fallback when the ornis-search MCP fails to connect.

Packaged Plume: `Plume --ornis-helper=search-cli <cmd> …`
Same tools as the MCP (`web_search`, `read_web_page`), one JSON object on argv.
"""
from __future__ import annotations

import json
import sys

HERE = __file__.rsplit("/", 1)[0]
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import ornis_search_mcp  # noqa: E402

USAGE = """usage: ornis-search <command> [json-args]

commands:
  web_search   '{"query":"…","time_range":"week","language":"fr"}'
  read_web_page '{"url":"https://…","part":1}'
"""

ALIASES = {
    "search": "web_search",
    "fetch": "read_web_page",
    "read": "read_web_page",
}


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    argv = [a for a in argv if not a.startswith("--ornis-helper=")]
    if not argv or argv[0] in ("-h", "--help", "help"):
        sys.stdout.write(USAGE)
        return 0 if argv else 2
    cmd = ALIASES.get(argv[0], argv[0])
    raw = argv[1] if len(argv) > 1 else "{}"
    try:
        args = json.loads(raw) if raw.strip() else {}
    except ValueError as err:
        sys.stderr.write(f"ornis-search: bad JSON: {err}\n")
        return 2
    if not isinstance(args, dict):
        sys.stderr.write("ornis-search: args must be a JSON object\n")
        return 2
    if cmd not in ("web_search", "read_web_page"):
        sys.stderr.write(f"ornis-search: unknown command: {cmd}\n{USAGE}")
        return 2
    result = ornis_search_mcp.call_tool(cmd, args)
    text = ""
    for block in result.get("content") or []:
        if isinstance(block, dict) and block.get("type") == "text":
            text += str(block.get("text") or "")
    if result.get("isError"):
        sys.stderr.write((text or "error") + "\n")
        return 1
    sys.stdout.write(text + ("\n" if text and not text.endswith("\n") else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
