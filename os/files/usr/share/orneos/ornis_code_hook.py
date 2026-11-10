"""The `post_tool` hook of Ornis Code (Vibe's hooks.toml, written by ornis_code.write_home): as Claude Code does, a
tool output too long for the conversation (a build, a test run, a big grep, an MCP answer) is saved whole in the
project's .ornis/tmp/, and the model gets only its start, its end and the file's path, to read or grep when it needs
more. The conversation stays light (each step sends it all again) and nothing is lost.

It also keeps a turn from going round in circles (lot 1 of docs/plans/2026-11-10-harness-hermes.md, as the editor
extension): the same call with the same result, or the same cycle of 2 to 4 calls, seen three times in a row gets a
warning joined to its result (`loop_note`; CodeChat stops the turn at the fifth), and a long result identical to one
already given in the turn becomes a reference to it. Its state is a small file per session in VIBE_HOME/hook-state,
removed by the `post_agent` event at the end of each turn of the main agent.

And what the session has seen of the files (lot 2, as the extension's memo.js): a file read again whole, unchanged, within
the last RECENT calls (the gateway keeps them whole) comes back as a reference; `write_file` over a file of the project
never read in the session, or changed since, is refused before it runs (`pre_tool`); the AGENTS.md (ORNIS.md, CLAUDE.md)
of a sub-folder is joined once to the first result that touches it; a file written is checked for syntax errors
(Python, JSON, TOML in this process, PHP and JavaScript when `php` / `node` are there). CodeChat forgets the reads after a
summary (`forget_reads`): they left the context.

Vibe gives the event as JSON on stdin; printing {"decision": "deny", "reason": …} replaces the text the model sees,
{"hook_specific_output": {"additional_context": …}} adds to it.
Light on purpose (no Qt, no app module): it runs for every tool call. Packaged Plume runs it as
`Plume --ornis-helper=code-hook` (ornis_local.dispatch_helper), elsewhere `python3 ornis_code_hook.py`."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

KEEP = 30000                # characters past which the output leaves the conversation (Claude Code ~30 000; Hermes 100 000)
HEAD, TAIL = 1500, 2500     # characters shown from its start and its end (errors and summaries are at the end)
LINE = 300                  # characters of one shown line
SKIP = {"read_file", "write_file", "edit", "todo", "ask_user_question", "skill"}   # a file already is the full text
WARN_LAPS = 3               # the same call (or cycle of calls), same results, this many times in a row: a warning
MAX_PERIOD = 4
STUB_MIN = 512              # a result this long, identical to an earlier one of the turn, becomes a reference
UNCOUNTED = {"todo", "ask_user_question", "agents_spawn"}
LOOP_NOTE = ("You already made this exact call (or this same series of calls) several times with the same result. "
             "Do not run it again: use the result you have, or change your approach.")
SAME_NOTE = "[Same result as your earlier call #{n}: unchanged.]"
RECENT = 6                  # calls within which an earlier whole read is surely still in the context
HINT_FILES = ("AGENTS.md", "ORNIS.md", "CLAUDE.md")
HINT_CAP = 4000
UNCHANGED_NOTE = "[{path} is unchanged since you read it whole (call #{n}): use that content, it is still above.]"
UNSEEN_NOTE = ("write_file would replace {path}, which you have not read in this conversation: nothing was written. Read "
               "it first, then use edit for a change, or write_file to rewrite it whole.")
CHANGED_NOTE = ("write_file would replace {path}, which changed since you read it (by the person or a command): nothing "
                "was written. Read it again first.")
HINT_NOTE = "[Instructions for the files of {dir}/ ({file}), shown once:]\n{text}"
SYNTAX_NOTE = "Syntax check of {path} failed:\n{error}\nFix it before going on."


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


def _state_path(event: dict, home: str = "") -> str:
    home = home or os.environ.get("VIBE_HOME") or ""
    session = re.sub(r"[^A-Za-z0-9_-]+", "", str(event.get("session_id") or ""))[:80]
    return os.path.join(home, "hook-state", session + ".json") if home and session else ""


def _load(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(path: str, state: dict) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f)
        os.replace(tmp, path)
    except OSError:
        pass


def _cycle_key(rounds: list) -> str:
    """The same cycle whatever call it is seen from (A,B and B,A): its smallest rotation."""
    return f"{len(rounds)}:" + min("|".join(rounds[i:] + rounds[:i]) for i in range(len(rounds)))


def loop_note(rounds: list, warned: list) -> bool:
    """True when the last calls repeat one call or one cycle of 2 to 4 calls WARN_LAPS times (once per pattern)."""
    found = False
    for period in range(1, MAX_PERIOD + 1):
        if len(rounds) < period * WARN_LAPS:
            continue
        last = rounds[-period:]
        if period > 1 and len(set(last)) == 1:
            continue                                  # one call repeated: the period-1 case
        laps, end = 0, len(rounds)
        while end - period >= 0 and rounds[end - period:end] == last:
            laps, end = laps + 1, end - period
        key = _cycle_key(last)
        if laps >= WARN_LAPS and key not in warned:
            warned.append(key)
            found = True
    return found


def count(event: dict) -> None:
    """One call more in this session (the reference window counts calls)."""
    path = _state_path(event)
    if path:
        state = _load(path)
        state["n"] = int(state.get("n") or 0) + 1
        _save(path, state)


def watch(event: dict, answer: dict | None) -> dict | None:
    """The loop warning and the reference to an identical result, joined to the answer of the long-output step."""
    path = _state_path(event)
    tool = str(event.get("tool_name") or "tool").rsplit(".", 1)[-1]
    text = event.get("tool_output_text")
    if not path or tool in UNCOUNTED or not isinstance(text, str):
        return answer
    state = _load(path)
    rounds, warned, seen = state.get("rounds") or [], state.get("warned") or [], state.get("seen") or {}
    number = int(state.get("n") or 0)
    try:
        what = json.dumps(event.get("tool_input") or {}, sort_keys=True, ensure_ascii=False)
    except (TypeError, ValueError):
        what = str(event.get("tool_input"))
    digest = hashlib.sha256(f"{tool}\0{what}\0{text}".encode("utf-8", "replace")).hexdigest()[:24]
    rounds = (rounds + [digest])[-(MAX_PERIOD * WARN_LAPS + 4):]
    if answer is None and len(text) >= STUB_MIN and event.get("tool_status") == "success":
        if digest in seen and number - int(seen[digest]) <= RECENT:     # still whole in the context
            answer = {"decision": "deny", "reason": SAME_NOTE.format(n=seen[digest])}
        else:
            seen[digest] = number
    if loop_note(rounds, warned):
        answer = dict(answer or {})
        answer.setdefault("hook_specific_output", {})["additional_context"] = LOOP_NOTE
    state.update(rounds=rounds, warned=warned[-20:], seen=dict(list(seen.items())[-200:]))
    _save(path, state)
    return answer


def end_turn(event: dict) -> None:
    """post_agent of the main agent: the next turn starts with no history of calls (what was read stays known)."""
    if event.get("parent_session_id"):
        return
    path = _state_path(event)
    if path and os.path.exists(path):
        state = _load(path)
        for key in ("rounds", "warned", "seen"):
            state.pop(key, None)
        _save(path, state)


def forget_reads(home: str, session: str) -> None:
    """After a summary (CodeChat): the reads and the folder instructions joined to them are gone from the context."""
    path = _state_path({"session_id": session}, home)
    if path and os.path.exists(path):
        state = _load(path)
        for seen in (state.get("files") or {}).values():
            seen["read"] = 0
        state["hinted"] = []
        _save(path, state)


# ---- what the session has seen of the files ---------------------------------------------------------------------------
def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:24]


def _disk(path: str) -> str | None:
    try:
        if os.path.isfile(path):
            with open(path, encoding="utf-8", errors="replace") as f:
                return f.read()
    except OSError:
        pass
    return None


def _target(event: dict) -> str:
    args = event.get("tool_input") if isinstance(event.get("tool_input"), dict) else {}
    raw = str(args.get("file_path") or args.get("path") or "")
    if not raw:
        return ""
    cwd = str(event.get("cwd") or os.getcwd())
    return os.path.realpath(raw if os.path.isabs(raw) else os.path.join(cwd, raw))


def _inside(path: str, root: str) -> bool:
    root = os.path.realpath(root)
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def _rel(path: str, root: str) -> str:
    try:
        return os.path.relpath(path, os.path.realpath(root)).replace(os.sep, "/")
    except ValueError:
        return path


def guard_write(event: dict) -> dict | None:
    """pre_tool of write_file: never over a file of the project the session did not read, or that changed since."""
    if str(event.get("tool_name") or "").rsplit(".", 1)[-1] != "write_file":
        return None
    target, cwd = _target(event), str(event.get("cwd") or os.getcwd())
    text = _disk(target) if target else None
    if not text or not _inside(target, cwd) or ".ornis" in _rel(target, cwd).split("/"):
        return None
    path = _state_path(event)
    if not path:
        return None
    seen = (_load(path).get("files") or {}).get(target)
    if not seen:
        return {"decision": "deny", "reason": UNSEEN_NOTE.format(path=_rel(target, cwd))}
    if seen.get("hash") != _digest(text):
        return {"decision": "deny", "reason": CHANGED_NOTE.format(path=_rel(target, cwd))}
    return None


def _hints(state: dict, target: str, cwd: str) -> str:
    root = os.path.realpath(cwd)
    folder = target if os.path.isdir(target) else os.path.dirname(target)
    hinted, found = state.setdefault("hinted", []), []
    while _inside(folder, root) and folder != root:
        if folder not in hinted:
            hinted.append(folder)
            for name in HINT_FILES:
                text = (_disk(os.path.join(folder, name)) or "").strip()
                if text and not os.path.islink(os.path.join(folder, name)):
                    shown = text if len(text) <= HINT_CAP else text[:HINT_CAP] + "\n[…]"
                    found.insert(0, HINT_NOTE.format(dir=_rel(folder, root), file=name, text=shown))
                    break
        folder = os.path.dirname(folder)
    return "\n\n".join(found)


def _syntax(target: str) -> str:
    """The first syntax error of a file just written, or ''. Only cheap checks; a missing checker says nothing."""
    ext = os.path.splitext(target)[1].lower()
    text = _disk(target)
    if text is None or len(text) > 2_000_000:
        return ""
    try:
        if ext == ".py":
            compile(text, target, "exec", dont_inherit=True)
        elif ext == ".json":
            json.loads(text)
        elif ext == ".toml":
            import tomllib  # noqa: PLC0415
            tomllib.loads(text)
        elif ext in (".php", ".js", ".mjs", ".cjs"):
            tool = shutil.which("php" if ext == ".php" else "node")
            if not tool:
                return ""
            argv = [tool, "-l", target] if ext == ".php" else [tool, "--check", target]
            run = subprocess.run(argv, capture_output=True, text=True, timeout=8, stdin=subprocess.DEVNULL)
            if run.returncode != 0:
                return ((run.stdout or "") + (run.stderr or "")).strip()[-1500:] or "error"
    except SyntaxError as error:
        return f"line {error.lineno}: {error.msg}"
    except ValueError as error:                       # json and tomllib errors
        return str(error)[:500]
    except (OSError, subprocess.SubprocessError, ImportError):
        return ""
    return ""


def files(event: dict, answer: dict | None) -> dict | None:
    """post_tool: references for an unchanged read, the sub-folders' instructions, the syntax of a file written."""
    path, target = _state_path(event), _target(event)
    tool = str(event.get("tool_name") or "").rsplit(".", 1)[-1]
    if not path or not target or event.get("tool_status") != "success":
        return answer
    cwd = str(event.get("cwd") or os.getcwd())
    state = _load(path)
    number = int(state.get("n") or 0)
    known = state.setdefault("files", {})
    extra = []
    if tool in ("read_file", "write_file", "edit"):
        text = _disk(target)
        if text is not None:
            args = event.get("tool_input") if isinstance(event.get("tool_input"), dict) else {}
            output = event.get("tool_output") if isinstance(event.get("tool_output"), dict) else {}
            whole = (tool == "read_file" and not args.get("offset") and not output.get("was_truncated")
                     and (args.get("limit") is None or (output.get("total_lines") or 0) <= int(args.get("limit") or 0)))
            before = known.get(target) or {}
            digest = _digest(text)
            if (whole and answer is None and before.get("read") and before.get("hash") == digest
                    and number - int(before["read"]) <= RECENT):
                answer = {"decision": "deny", "reason": UNCHANGED_NOTE.format(path=_rel(target, cwd), n=before["read"])}
            else:
                read = number if whole else (before.get("read", 0) if before.get("hash") == digest else 0)
                known[target] = {"hash": digest, "read": read}
            if tool in ("write_file", "edit") and _inside(target, cwd):
                error = _syntax(target)
                if error:
                    extra.append(SYNTAX_NOTE.format(path=_rel(target, cwd), error=error))
    if _inside(target, cwd):
        hint = _hints(state, target, cwd)
        if hint:
            extra.append(hint)
    if len(known) > 400:
        state["files"] = dict(list(known.items())[-400:])
    _save(path, state)
    if extra:
        answer = dict(answer or {})
        out = answer.setdefault("hook_specific_output", {})
        out["additional_context"] = "\n\n".join(([out["additional_context"]] if out.get("additional_context") else []) + extra)
    return answer


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
        if not isinstance(event, dict):
            return 0
        if event.get("hook_event_name") == "post_agent":
            end_turn(event)
            return 0
        if event.get("hook_event_name") == "pre_tool":
            answer = guard_write(event)
            if answer:
                _write(json.dumps(answer, ensure_ascii=False))
            return 0
        if event.get("hook_event_name") != "post_tool":
            return 0
        count(event)
        answer = files(event, watch(event, handle(event)))
        if answer:
            _write(json.dumps(answer, ensure_ascii=False))
    except Exception:  # noqa: BLE001
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
