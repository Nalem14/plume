"""The `post_tool` hook of Ornis Code (Vibe's hooks.toml, written by ornis_code.write_home): as Claude Code does, a
tool output too long for the conversation (a build, a test run, a big grep, an MCP answer) is saved whole in the
project's .ornis/tmp/, and the model gets only its start, its end and the file's path, to read or grep when it needs
more. The conversation stays light (each step sends it all again) and nothing is lost.

Vibe gives the event as JSON on stdin; printing {"decision": "deny", "reason": …} replaces the text the model sees.
Light on purpose (no Qt, no app module): it runs for every tool call. Packaged Plume runs it as
`Plume --ornis-helper=code-hook` (ornis_local.dispatch_helper), elsewhere `python3 ornis_code_hook.py`."""
import json
import os
import re
import sys
import time

KEEP = 8000                 # characters past which the output leaves the conversation
HEAD, TAIL = 1500, 2500     # characters shown from its start and its end (errors and summaries are at the end)
LINE = 300                  # characters of one shown line
SKIP = {"read_file", "write_file", "edit", "todo", "ask_user_question", "skill"}   # a file already is the full text


def _clip(line: str) -> str:
    return line if len(line) <= LINE else line[:LINE] + " […]"


def shorten(text: str, saved: str) -> str:
    """The start and the end of a long output (whole lines, within HEAD and TAIL characters), then where the rest is."""
    lines = text.splitlines()
    size = len(text.encode("utf-8", "replace"))
    head, used = [], 0
    for line in lines:
        line = _clip(line)
        if used + len(line) > HEAD and head:
            break
        head.append(line)
        used += len(line) + 1
    tail, used = [], 0
    for line in reversed(lines[len(head):]):
        line = _clip(line)
        if used + len(line) > TAIL and tail:
            break
        tail.insert(0, line)
        used += len(line) + 1
    hidden = len(lines) - len(head) - len(tail)
    where = (f"The full output ({len(lines)} lines, {max(1, size // 1024)} KB) is saved in {saved}: read the part you "
             f"need (read_file with an offset) or grep it; do not run the command again to see it."
             if saved else
             f"The full output ({len(lines)} lines, {max(1, size // 1024)} KB) was not kept: narrow the command (grep, "
             f"head, tail, a filter) to see the part you need.")
    return "\n".join(head + ([f"[… {hidden} lines not shown …]"] if hidden > 0 else ["[…]"]) + tail) + \
        f"\n[Output too long for the conversation. {where}]"


def save(cwd: str, tool: str, call_id: str, text: str) -> str:
    """The whole output in .ornis/tmp of the project (only when the notebook exists: never made here)."""
    folder = os.path.join(cwd, ".ornis", "tmp")
    if not os.path.isdir(folder):
        return ""
    safe = re.sub(r"[^A-Za-z0-9_-]+", "-", tool)[:30].strip("-") or "tool"
    tail = re.sub(r"[^A-Za-z0-9]+", "", call_id)[-6:]
    name = f"{safe}-{time.strftime('%Y%m%d-%H%M%S')}{'-' + tail if tail else ''}.txt"
    try:
        with open(os.path.join(folder, name), "w", encoding="utf-8", errors="replace") as out:
            out.write(text)
    except OSError:
        return ""
    return f".ornis/tmp/{name}"


def handle(event: dict) -> dict | None:
    text = event.get("tool_output_text")
    if not isinstance(text, str) or len(text) <= KEEP:
        return None
    tool = str(event.get("tool_name") or "tool")
    short = tool.rsplit(".", 1)[-1]
    if short in SKIP:
        return None
    saved = save(str(event.get("cwd") or os.getcwd()), tool.replace(".", "_") if tool.startswith("mcp_") else short,
                 str(event.get("tool_call_id") or ""), text)
    return {"decision": "deny", "reason": shorten(text, saved)}


def _read() -> str:
    """stdin, also when Python has none: packaged Plume for Windows is a windowed program (sys.stdin is None there),
    but the pipe Vibe gives is still file descriptor 0."""
    if sys.stdin is not None:
        return sys.stdin.read()
    chunks = []
    while True:
        chunk = os.read(0, 65536)
        if not chunk:
            return b"".join(chunks).decode("utf-8", "replace")
        chunks.append(chunk)


def _write(text: str):
    if sys.stdout is not None:
        sys.stdout.write(text)
        sys.stdout.flush()
        return
    data = text.encode("utf-8")
    while data:
        data = data[os.write(1, data):]


def main() -> int:
    """Never fails: a hook that breaks would cost the model its tool's output; the output then stays as it was."""
    try:
        event = json.loads(_read() or "{}")
        if not isinstance(event, dict) or event.get("hook_event_name") != "post_tool":
            return 0
        answer = handle(event)
        if answer:
            _write(json.dumps(answer, ensure_ascii=False))
    except Exception:  # noqa: BLE001
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
