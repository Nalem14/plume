"""Ornis Code: the « Code » mode of the Ornis apps (Orneos OS, Plume). Ornis works in a folder of the computer
(a site, a script, data, documents): it reads, edits, runs commands and checks its work, like a developer.

- The agent is Mistral Vibe (Apache-2.0), its ready-made `vibe-acp` build, driven over the Agent Client Protocol
  (JSON-RPC on stdio, https://agentclientprotocol.com): any ACP agent could take its place. It is fetched from
  orneos.eu on the first use (RUNTIME: archive and sha256 per system, tools/ornis-code-runtime.sh publishes them).
- It reaches the model only through the gateway of the cloud (`/apps/orneos/ornis/code/v1`, OrnisCodeController),
  with a token of this computer (asked once with the app password, kept in the system's keyring): never with our
  Mistral key, counted in the Ornis quota of the account. The model is chosen by the cloud.
- Conversations stay on the computer (Vibe's sessions, in its home under DATA/ornis-code/home): nothing goes to
  the cloud but what the model has to read.
- Where the system allows it, the whole agent runs in a sandbox (bubblewrap on Linux, sandbox-exec on macOS): it
  writes only in the project, its home and the developer caches; .ssh, .gnupg… are hidden.
- Vibe never approves anything by itself: each permission comes back here (`decide`) and follows the same rules
  as Ornis on this computer (ornis_shell.classify): destructive commands refused, secrets always asked.
"""
import json
import os
import platform
import re
import shutil
import subprocess
import tarfile
import threading
import time
import urllib.request
import zipfile
from pathlib import Path

import system

VERSION = "3.0.4"
BASE = f"https://orneos.eu/downloads/ornis/vibe-{VERSION}/"
RUNTIME = {      # (system, machine): (archive, sha256) — tools/ornis-code-runtime.sh prints them
    ("linux", "x86_64"): (f"vibe-acp-linux-x86_64-{VERSION}.tar.gz", "83d9cd21758a99719382e1c8c55420e9693d7e3358b3d3a744727e2291a9d5b3"),
    ("linux", "aarch64"): (f"vibe-acp-linux-aarch64-{VERSION}.tar.gz", "dfac99ccd25de9780f54f0dc32aa90a3838810a0becc8f7fe393ea07748d3107"),
    ("darwin", "arm64"): (f"vibe-acp-darwin-aarch64-{VERSION}.tar.gz", "cc9c1d94ccb7890b36e82b096031e80d6c78d68f891e527e01c0865a04f90008"),
    ("darwin", "x86_64"): (f"vibe-acp-darwin-x86_64-{VERSION}.tar.gz", "9f94678a670b9c13b5f20bc4878075b37f9ba537bec32cbccee45ff8e78e165e"),
    ("windows", "amd64"): (f"vibe-acp-windows-x86_64-{VERSION}.zip", "e853cc56f586bf3e618d2d82eca5659db2f781f070252b24ea273f6c156b5aec"),
}
ROOT = system.DATA / "ornis-code"
COMPACT_AT = 64_000          # the agent summarises its start beyond this (each step sends the whole context again)
SECRET_DIRS = (".ssh", ".gnupg", ".pki", ".aws", ".kube", ".password-store", ".docker", ".config/gh", ".netrc")
CACHE_DIRS = (".cache", ".npm", ".cargo", ".rustup", ".m2", ".gradle", "go", ".local/share/pnpm", ".bun", ".deno")
MODES = ("ask", "edits", "auto")   # Demander / Modifier le projet sans demander (default) / Autonome


class Unavailable(Exception):
    """Code cannot run here (system without a build, download refused, no token)."""


# ---- the agent's build -----------------------------------------------------------------------------------------
def target() -> tuple[str, str] | None:
    sysname = "windows" if system.WINDOWS else "darwin" if system.MACOS else "linux"
    machine = platform.machine().lower()
    machine = {"amd64": "x86_64", "x64": "x86_64", "arm64": "aarch64"}.get(machine, machine)
    if sysname == "windows":
        machine = "amd64" if machine == "x86_64" else machine
    if sysname == "darwin":
        machine = "arm64" if machine == "aarch64" else machine
    key = (sysname, machine)
    return key if key in RUNTIME else None


def supported() -> bool:
    return target() is not None


def _runtime_dir() -> Path:
    return ROOT / f"vibe-{VERSION}"


def binary() -> Path | None:
    """The installed `vibe-acp`, or None."""
    exe = _runtime_dir() / ("vibe-acp.exe" if system.WINDOWS else "vibe-acp")
    return exe if exe.is_file() and (_runtime_dir() / ".ok").is_file() else None


def install(on_progress=None) -> Path:
    """Fetch, check and unpack the agent (about 70 to 120 MB, once). on_progress(done, total) in bytes."""
    key = target()
    if key is None:
        raise Unavailable("system")
    if (exe := binary()) is not None:
        return exe
    name, digest = RUNTIME[key]
    ROOT.mkdir(parents=True, exist_ok=True)
    part = ROOT / (name + ".part")
    import hashlib
    sha = hashlib.sha256()
    try:
        with urllib.request.urlopen(BASE + name, timeout=60) as response, open(part, "wb") as out:
            total = int(response.headers.get("Content-Length") or 0)
            done = 0
            while chunk := response.read(1 << 20):
                out.write(chunk)
                sha.update(chunk)
                done += len(chunk)
                if on_progress:
                    on_progress(done, total)
    except OSError as error:
        part.unlink(missing_ok=True)
        raise Unavailable("download") from error
    if sha.hexdigest() != digest:
        part.unlink(missing_ok=True)
        raise Unavailable("integrity")
    work = ROOT / f".unpack-{os.getpid()}"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()
    try:
        if name.endswith(".zip"):
            with zipfile.ZipFile(part) as archive:
                archive.extractall(work)
        else:
            with tarfile.open(part) as archive:
                archive.extractall(work, filter="data")
        exe_name = "vibe-acp.exe" if system.WINDOWS else "vibe-acp"
        found = next((p for p in work.rglob(exe_name) if p.is_file()), None)
        if found is None:
            raise Unavailable("archive")
        shutil.rmtree(_runtime_dir(), ignore_errors=True)
        found.parent.rename(_runtime_dir())
        if not system.WINDOWS:
            os.chmod(_runtime_dir() / exe_name, 0o755)
        (_runtime_dir() / ".ok").write_text(digest)
    finally:
        shutil.rmtree(work, ignore_errors=True)
        part.unlink(missing_ok=True)
    for old in ROOT.glob("vibe-*"):          # an older version of the agent
        if old != _runtime_dir() and old.is_dir():
            shutil.rmtree(old, ignore_errors=True)
    return _runtime_dir() / ("vibe-acp.exe" if system.WINDOWS else "vibe-acp")


# ---- the token of this computer and the agent's home ------------------------------------------------------------
def _secret_entry(server: str, user: str) -> str:
    return f"ornis-code:{user}@{server.rstrip('/')}"


def credentials(server: str, user: str, password: str, renew: bool = False) -> dict:
    """{token, url} for the gateway: kept in the keyring, asked to the cloud the first time (or when refused)."""
    entry = _secret_entry(server, user)
    if not renew:
        try:
            saved = json.loads(system.secret_get(entry) or "")
            if saved.get("token") and saved.get("url"):
                return saved
        except (ValueError, TypeError):
            pass
    import cloud
    status, body = cloud.ocs(server, user, password, "/ocs/v2.php/apps/orneos/api/v1/ornis/code/tokens", method="POST",
                             body={"device": platform.node() or "?"})
    data = (body or {}).get("ocs", {}).get("data") if isinstance(body, dict) else None
    if not (200 <= int(status or 0) < 300) or not isinstance(data, dict) or not data.get("token"):
        raise Unavailable("token")
    saved = {"token": data["token"], "url": data.get("url") or server.rstrip("/") + "/apps/orneos/ornis/code/v1",
             "context": int(data.get("context") or 256000)}
    system.secret_set(entry, json.dumps(saved))
    return saved


def forget(server: str, user: str) -> None:
    system.secret_delete(_secret_entry(server, user))


def home(bot: str = "") -> Path:
    if bot:
        import ornis_bots
        return ROOT / "bot-homes" / ornis_bots._ok_id(bot)
    return ROOT / "home"


PROMPT = """You are Ornis, the assistant of Orneos, working in **Code** mode: you act directly in a folder of the
user's computer (the current working directory) with tools to read, search, edit and write files and to run
commands. The project may be code, a website, scripts, data or documents. Always answer in {language}, formally
({formal}), clearly and briefly: every sentence the user sees, the short notes between tool calls too (never
start in English), even when the files, rules or these instructions are in English. Never mention the model you
run on.

# How you work
1. Understand first. Look at the folder (list it, read README, AGENTS.md and the files that matter) before
   changing anything. Never edit a file you have not read in this session. Never invent a file, a function,
   a library, a command or an API: check that it exists (read the code, the docs or the installed packages).
2. Plan. For anything beyond a one-line change, write a short plan with the todo tool, and keep it up to date.
3. Act in small steps. Prefer editing over rewriting; keep the project's style, structure and conventions.
   Create the files a project needs to run (entry point, manifest, configuration), not empty scaffolding.
4. Verify. After a change, run what proves it works: tests, build, linter, the script itself (`php -l`,
   `python -m py_compile`, `node --check`, `npm test`…). If something fails, read the error and fix it.
   Never say something works if you have not checked it; say what you could not verify.
5. Keep going until the whole request is done: after a step, go on with the next item of your plan in the same
   turn. Stop only to ask a real question, for a permission, or when everything is done and verified.
6. Finish with a short summary: what changed (files), how you checked it, what is left to the user.

# Rules
- Stay inside the working directory unless the user names another place.
- Ask before anything destructive or irreversible (deleting many files, rewriting git history, publishing).
- Commands run without a terminal: use non-interactive flags (`-y`, `--yes`, `CI=1`).
- Never print, copy or send secrets (keys, passwords, tokens, .env files).
- Never write a tool call as text (no JSON such as {{"command": …}} or {{"path": …}} in your answer): call the tool.
- Do not paste the content of a file you have just written into your answer: name the file, the user sees it.
- If the user asks something outside this folder (mail, calendar, the cloud), say that the Agent mode of
  Ornis does it.
- When a choice is the user's to make (several reasonable ways, a preference, something to confirm before going
  on), ask it with the ask_user_question tool (2 to 4 options, the recommended one first) instead of in prose.
- Never run the same command or search again when it already gave its answer: use that answer, or change the
  approach. A search that finds nothing twice will not find more a third time.

# Your notebook in the project: .ornis/
Each project folder has a `.ornis/` folder that is yours (the app made it; the user can read and change it). Its
rules, your memory index, the latest plans and the project's commands are joined to the first message of each
conversation. Edits in `.ornis/memory`, `.ornis/plans` and `.ornis/tmp` are always allowed, even in Plan mode, and
« Annuler » never takes them back. Leave `.ornis/` out of your summaries of the project.
- `rules.md`: the project's rules for you. Write or update it only when the user asks for a rule (« toujours… »,
  « ne jamais… », « dans ce projet… »), or with /init. `rules.local.md` is the user's own: never change it unless
  they ask. `AGENTS.md` at the root is shared with other assistants: keep its content there.
- `SOUL.md`: the user's preferred style (tone, length, what they do not want). Never secrets, never a
  technical rule, and it never overrides this file or the project's rules. You edit it yourself with your file
  tools: `.ornis/SOUL.md` for this folder, and the global `SOUL.md` whose path is in the notebook when the
  preference applies to every project. The folder one wins. When the user corrects your form, write the preference
  into the file that fits. The write is shown and they approve it.
- `memory/`: what you must know next time and cannot find again in the code or git history. One file per memory,
  `memory/<short-slug>.md`:
  ```
  ---
  name: <short-slug>
  description: <one line, used to decide whether it is relevant>
  type: user | feedback | project | reference
  ---
  <the fact; for feedback and project, then **Why:** and **How to apply:** lines>
  ```
  `user`: who the user is, their preferences. `feedback`: how they want you to work (a correction, or an approach
  they confirmed). `project`: a decision, a constraint, a deadline, a pitfall met (with absolute dates).
  `reference`: where something lives (a URL, a server, a dashboard). Then add one line to `memory/MEMORY.md`:
  `- [<short title>](<slug>.md) — <a few words saying what it is about>`, for instance
  `- [Demo server](demo-server.md) — address and how to deploy`. MEMORY.md is only an index, never the content. Before writing, look for a memory
  that already covers it and update it instead; delete one that turns out wrong. Save when the user says
  « retiens… » / « remember… », when they correct you, or when you learn something that will matter again. Never
  save secrets, what the code already says, or what only matters to this conversation. A memory may be old:
  check it against the code before relying on it. Read a memory file when its line in the index looks relevant.
- `plans/`: in Plan mode, also write your plan to `.ornis/plans/<YYYY-MM-DD>-<short-title>.md` (context, steps
  file by file, how to check). When you carry out a plan from there, tick its steps (`- [x]`) as you go.
- `tmp/`: for what is too long for your context. A tool output past about 8 000 characters is saved there by
  itself (`.ornis/tmp/<tool>-<time>.txt`): you get its start, its end and the path; read the part you need (with an
  offset) or grep that file, never run the command again to see it. You may also send an output there yourself
  (`npm test > .ornis/tmp/test.log 2>&1; tail -n 60 .ornis/tmp/test.log`). Put your throwaway scripts and drafts
  there rather than in the project. Emptied after 7 days; never put anything that must last.
- `commands/`: the user's « / » commands (`<name>.md`, `$ARGUMENTS`). Write one only when the user asks.
- `skills/`: this project's procedures, the way you learn: memory keeps facts, a skill keeps how to do something
  that comes back (deploy, release, add a page, migrate the data, reproduce a bug). One folder per skill,
  `.ornis/skills/<name>/SKILL.md`:
  ```
  ---
  name: <name, lowercase with dashes>
  description: <what it does and when to use it: you decide from this line alone>
  ---
  <the steps, the exact commands, the checks, the pitfalls met>
  ```
  Only there: never in .vibe/skills, .agents/skills or .claude/skills (not read here). Use a skill when its
  description fits the request (skill tool, or read its SKILL.md). After you worked out a
  procedure of several steps that will come back, offer in one line to make it a skill; write it when the user
  agrees or asks. When a step of a skill proves wrong or outdated, fix the skill yourself and say so.
- Write your notebook (memory, plans, skills, rules) in {language}, so the user can read it, unless the project's
  rules ask for another language. Code, comments and commit messages follow the project's conventions.

# MCP servers and skills (Ornis's extensions)
The MCP servers and skills the user set up for Ornis are already yours: their tools are in your tool list (an MCP
tool is named after its server), the skills in your skills. They are added in Ornis's Settings › Extensions
(« Skills et serveurs MCP »), or by asking Ornis in Agent mode, which adds one after the user's approval (a remote
server's token is kept in the computer's keychain). You cannot add one from Code mode. So, when the user asks for an
MCP server (or gives you a token for one):
- if its tools are in your list, use them;
- otherwise say in two sentences where to add it (Settings › Extensions: name, the server's https address or its
  command, the token), or to ask Ornis in Agent mode; then the next Code conversation has it. Never install,
  write or start an MCP server, a « config » or a script yourself for this, and never invent its address.
- Never change Ornis's own files ({home}: config.toml, AGENTS.md, logs) nor another assistant's configuration
  (~/.claude.json, ~/.gemini, ~/.codex, ~/.cursor…): you may read one to tell the user what it contains.
- Never stop or start `vibe-acp`, `ornis` or `plume` processes: that is you, the conversation would stop.

# Web search (Orneos Search)
When you need facts from the web, recent news, product listings, docs you do not have in the folder, or the user asks
to search online: use the `ornis-search` tools `web_search` then `read_web_page` on the useful links. Do not invent
URLs, and do not use a browser or curl for ordinary search. Never search for passwords or private account data.
- If `web_search` is **not** in your tool list (MCP failed): run the local CLI instead (one shell command):
  `{search_cli}` web_search '{{"query":"…","language":"fr"}}'
  Then `{search_cli}` read_web_page '{{"url":"https://…","part":1}}' on useful links. Do not invent a search engine.

# Local cron tasks (Code only, this computer)
When the user asks for something recurring (« every morning », « chaque matin », « tous les lundis », « every hour »,
« le 1er du mois », « toutes les 15 minutes »), create a **local Code cron task** with the `ornis-cron` MCP tools
(`cron_create`, …). Do not say you will remember, and do not invent a reminder elsewhere. Vibe's own `cron` / `/loop`
tool is disabled here: never try to re-enable it, and never edit `cron.json` by hand.
- If `cron_create` is **not** in your tool list (MCP failed): do **not** search the disk or invent a system crontab.
  Run the local CLI instead (one shell command), then confirm to the user:
  `{cron_cli}` create '{{"id":"rapport-voitures","title":"…","description":"…","kind":"chat","schedule":"*/15 * * * *","prompt":"…","folder":"{cwd}"}}'
  Other commands: `list`, `update`, `pause`, `resume`, `run`, `delete`, `history` — same JSON object as the MCP tools.
  Only if that CLI is missing, tell the user to click **+** under « Tâches cron ».
- `schedule` is a classic 5-field crontab (minute hour day month weekday) or `@hourly` / `@daily` / `@weekly` /
  `@monthly`. Wall-clock hours. Minimum every 15 minutes (`* * * * *` and `*/5` are refused). No `@reboot`.
- « Morning » with no hour → `0 8 * * *`. Weekdays at 8 → `0 8 * * 1-5`. Lists, ranges and steps are fine
  (`0,30 9-18 * * 1-5`, `*/15 9-17 * * 1-5`).
- Pick a short kebab-case `id` (e.g. `rapport-voitures`), a clear `title` and a one-line `description`.
- `kind=chat` + `prompt`: each due time opens a **new** Code conversation in this folder with that prompt; runs appear
  under the task in the left column. `kind=script` + `command`: runs the shell command in the folder.
- After creating or changing one, confirm in one sentence: the plain schedule label, the crontab, the folder, and where
  the result will be written.
"""


HOOKS = """# Written by Ornis (ornis_code.py): changes are replaced at the next start.
[[hooks]]
name = "ornis-long-output"
type = "post_tool"
description = "A long tool output goes to .ornis/tmp; the model keeps its start, its end and the path"
timeout = 15.0
command = {command}
"""


def hook_command() -> str:
    """The shell command of the hook: packaged Plume runs it itself (no Python on Windows or macOS)."""
    import shlex  # noqa: PLC0415
    import sys  # noqa: PLC0415
    argv = [sys.executable, "--ornis-helper=code-hook"] if system.FROZEN else \
        [sys.executable, "-I", str(Path(__file__).resolve().with_name("ornis_code_hook.py"))]
    if system.WINDOWS:
        return " ".join(f'"{a}"' for a in argv)
    return " ".join(shlex.quote(a) for a in argv)


def _skill_paths(folder: str = "", bot: str = "") -> list[str]:
    """Folders Vibe may load skills from: the project's .ornis/skills, plus a bot's own and enabled ones."""
    paths = []
    if folder and (ornis_dir(folder) / "skills").is_dir():
        paths.append(str(ornis_dir(folder).resolve() / "skills"))
    if bot:
        try:
            import ornis_bots  # noqa: PLC0415
            root = ornis_bots.bot_dir(bot)
            for sub in ("skills", "enabled-skills"):
                p = root / sub
                if p.is_dir():
                    paths.append(str(p.resolve()))
        except (ValueError, OSError):
            pass
    return paths


def write_home(url: str, language: str = "fr", folder: str = "", reasoning: str = "high",
               bot: str = "") -> Path:
    """The agent's configuration: our gateway as its only provider, nothing sent to anyone else (telemetry,
    updates, Mistral's sign-in, connectors), our instructions."""
    root = home(bot)
    root.mkdir(parents=True, exist_ok=True)
    lang = {"fr": ("French", "use « vous »"), "de": ("German", "use « Sie »")}.get(language[:2], ("English", "polite"))
    # Vibe's runtime keeps its own system prompt and adds the user-level AGENTS.md of its home to it
    ensure_cron_bins(folder, language[:2], bot)
    cron_cli = str((ROOT / "bin" / "ornis-cron").resolve())
    search_cli = str((ROOT / "bin" / "ornis-search").resolve())
    bots_cli = str((ROOT / "bin" / "ornis-bots").resolve())
    cwd = str(Path(folder).resolve()) if folder else str(Path.home())
    (root / "AGENTS.md").write_text(
        PROMPT.format(language=lang[0], formal=lang[1], home=str(root),
                      cron_cli=cron_cli, search_cli=search_cli, bots_cli=bots_cli, cwd=cwd),
        encoding="utf-8")
    reasoning = "none" if reasoning == "off" else reasoning
    reasoning = reasoning if reasoning in ("none", "low", "medium", "high") else "high"
    skills = _skill_paths(folder, bot)
    config = f"""# Written by Ornis (ornis_code.py): changes are replaced at the next start.
active_model = "orneos-code"
default_agent = "ask"
enable_telemetry = false
enable_otel = false
enable_update_checks = false
enable_auto_update = false
enable_notifications = false
enable_connectors = false
# MCP: the servers come only from Ornis's settings (ornis_extensions), given with each session (session/new,
# mcpServers); Vibe disables even those when enable_mcp is false (MCP never worked in Code before 04/11)
enable_mcp = true
enable_subagents = false
enable_background_processes = false
include_commit_signature = false
auto_compact_threshold = {COMPACT_AT}
disabled_tools = ["cron", "unified_harness_scratchpad", "wait", "web_search", "task"]
# Vibe's own skills (05/11: « skill-creator » made Ornis write its skills in .vibe/skills, which nobody reads here;
# « vibe:* » does not catch them all): ours go to .ornis/skills
disabled_skills = ["vibe", "vibe:*", "skill-creator", "create-plugin", "worktree", "*:skill-creator", "*:create-plugin", "*:worktree"]
# the project's own skills (.ornis/skills) and, for a bot, its profile skills: Vibe reads .vibe/skills only in a
# trusted folder, and we trust none
skill_paths = {json.dumps(skills)}

[session_logging]
save_dir = {json.dumps(str(home() / "logs" / "session"))}

# What one tool call may put in the context (Vibe: 64 KB a read, 64 KB a grep, 16 KB a command, about 16 k
# tokens for one read, sent again at every step): smaller, the agent reads the next part when it needs it
[tools.read_file]
permission = "ask"
max_read_bytes = 24000

# grep and commands: more is captured, but past 8 000 characters the hook (hooks.toml, ornis_code_hook) saves the
# whole output in .ornis/tmp and leaves the model its start, its end and the file's path, as Claude Code does
[tools.grep]
permission = "ask"
max_output_bytes = 60000

[tools.bash]
max_output_bytes = 100000

[[providers]]
name = "orneos"
api_base = {json.dumps(url.rstrip('/'))}
api_key_env_var = "ORNEOS_CODE_TOKEN"
backend = "generic"
api_style = "openai"

[[models]]
name = "orneos-code"
provider = "orneos"
alias = "orneos-code"
display_name = "Ornis"
temperature = 0.2
# the gateway's model (DeepSeek V4.1 Flash) reasons: shown in the view as Ornis's thoughts, as in the Discussion
thinking = "{reasoning}"
max_context_length = 256000
"""
    (root / "config.toml").write_text(config, encoding="utf-8")
    (root / "hooks.toml").write_text(HOOKS.format(command=json.dumps(hook_command())), encoding="utf-8")
    # a project's .vibe/config.toml (its own MCP servers, commands) is read only for a folder Vibe trusts: none
    for name in ("trusted_folders.toml",):
        try:
            (root / name).unlink()
        except OSError:
            pass
    if bot:
        import ornis_bots
        ornis_bots.set_enabled_skills(bot, (ornis_bots.get(bot) or {}).get("enabled_skills") or [])
    else:
        link_skills(root)
    return root


# ---- the project's .ornis folder ------------------------------------------------------------------------------------
# Like .claude/ for Claude Code: Ornis's notebook in each project folder. Vibe reads a project's AGENTS.md only in a
# folder it trusts (none: see write_home), so the app reads these files itself and joins them to the first message
# of each conversation (project_context). Layout (README_TEXT tells the user, PROMPT tells the agent):
#   rules.md          Ornis's rules for this project (next to AGENTS.md, which every assistant reads)
#   rules.local.md    the user's own rules here, out of git
#   SOUL.md           optional personal style, out of git (a global one lives in system.CONFIG)
#   memory/           MEMORY.md (the index, one line per memory) + one file per memory, out of git
#   plans/            the plans written in Plan mode (AAAA-MM-JJ-titre.md)
#   commands/         the project's « / » commands (<name>.md, $ARGUMENTS)
#   skills/           the project's skills (<name>/SKILL.md): procedures Ornis learnt here (skill_paths of Vibe)
#   tmp/              long command outputs and scratch files, out of git, emptied after TMP_DAYS
ORNIS_DIR = ".ornis"
NOTEBOOK = ("memory", "plans", "tmp")    # Ornis writes there in every mode (Plan too); never in the checkpoints
TMP_DAYS = 7
RULES_CAP = 8000                         # characters of one rules file joined to the first message (the rest: read it)
MEMORY_CAP = 6000                        # characters of MEMORY.md joined (Claude Code keeps 200 lines)
SOUL_CAP = 4000                          # characters of a SOUL.md joined (the folder's, then the global one)
GITIGNORE = """# Written by Ornis: your memory, personal rules and temporary files stay out of git.
# Remove « memory/ » to share Ornis's memory of the project with your team.
memory/
tmp/
rules.local.md
SOUL.md
"""
README_TEXT = {
    "fr": """# .ornis — le carnet d'Ornis pour ce projet

Ornis (mode Code) lit ce dossier au début de chaque conversation et y écrit ce qu'il doit retenir.
Vous pouvez tout lire et tout modifier.

- `rules.md` : les règles à suivre dans ce projet (style, commandes, interdits). `ORNIS.md` à la racine
  est le guide d'Ornis. `AGENTS.md` (sinon `CLAUDE.md`) est le guide partagé, et passe après.
- `rules.local.md` : vos règles personnelles ici (pas dans git).
- `SOUL.md` : facultatif, votre style préféré (ton, concision, exemples), sans secrets. Hors de git. Ornis l’écrit lui-même ; toute écriture vous est demandée. Un `SOUL.md` global (dossier de configuration) vaut pour tous les projets et passe après celui-ci.
- `memory/` : ce qu'Ornis a retenu (vos préférences, les décisions, les pièges). `MEMORY.md` en est le sommaire.
  Dites « retiens que… » ou tapez `/retenir …`. Pas dans git.
- `plans/` : les plans écrits en mode Plan.
- `commands/` : vos commandes « / » pour ce projet. `deploy.md` devient `/deploy` ; `$ARGUMENTS` y reçoit ce qui
  suit la commande.
- `skills/` : les marches à suivre de ce projet (déployer, publier…), une par dossier avec son `SKILL.md`. Ornis
  s'en sert quand c'est utile, en propose après une procédure qui reviendra, et les corrige quand une étape change.
- `tmp/` : sorties longues et brouillons, effacés au bout de 7 jours. Pas dans git.
""",
    "en": """# .ornis — Ornis's notebook for this project

Ornis (Code mode) reads this folder at the start of each conversation and writes here what it must remember.
You can read and change everything.

- `rules.md`: the rules to follow in this project (style, commands, don'ts). `ORNIS.md` at the root is
  Ornis's guide. `AGENTS.md` (or `CLAUDE.md` if there is no `AGENTS.md`) is the shared guide, and comes after.
- `rules.local.md`: your own rules here (not in git).
- `SOUL.md`: optional personal style (tone, brevity, examples), never secrets. Not in git. Ornis writes it; every write asks for your approval. A global `SOUL.md` (config folder) applies to every project and comes after this one.
- `memory/`: what Ornis remembers (your preferences, decisions, pitfalls). `MEMORY.md` is its index.
  Say « remember that… » or type `/remember …`. Not in git.
- `plans/`: the plans written in Plan mode.
- `commands/`: your « / » commands for this project. `deploy.md` becomes `/deploy`; `$ARGUMENTS` receives what
  follows the command.
- `skills/`: this project's procedures (deploy, release…), one per folder with its `SKILL.md`. Ornis uses them when
  useful, offers new ones after a procedure that will come back, and fixes them when a step changes.
- `tmp/`: long outputs and drafts, deleted after 7 days. Not in git.
""",
    "de": """# .ornis — Ornis' Notizbuch für dieses Projekt

Ornis (Code-Modus) liest diesen Ordner zu Beginn jedes Gesprächs und schreibt hier hinein, was es sich merken soll.
Sie können alles lesen und ändern.

- `rules.md`: die Regeln dieses Projekts (Stil, Befehle, Verbote). `ORNIS.md` im Stammverzeichnis ist
  Ornis' Leitfaden. `AGENTS.md` (sonst `CLAUDE.md`) gilt für alle Assistenten und kommt danach.
- `rules.local.md`: Ihre eigenen Regeln hier (nicht in git).
- `SOUL.md`: optionaler persönlicher Stil (Ton, Kürze, Beispiele), niemals Geheimnisse. Nicht in git. Ornis schreibt sie selbst; jede Änderung benötigt Ihre Zustimmung. Eine globale `SOUL.md` (Konfigurationsordner) gilt für alle Projekte und kommt nach dieser.
- `memory/`: was Ornis sich gemerkt hat (Ihre Vorlieben, Entscheidungen, Fallstricke). `MEMORY.md` ist das
  Verzeichnis. Sagen Sie « merk dir, dass… » oder tippen Sie `/merken …`. Nicht in git.
- `plans/`: die im Plan-Modus geschriebenen Pläne.
- `commands/`: Ihre « / »-Befehle für dieses Projekt. `deploy.md` wird zu `/deploy`; `$ARGUMENTS` erhält, was
  nach dem Befehl steht.
- `skills/`: die Abläufe dieses Projekts (Bereitstellen, Veröffentlichen…), einer pro Ordner mit seiner `SKILL.md`.
  Ornis nutzt sie bei Bedarf, schlägt nach einem wiederkehrenden Ablauf neue vor und korrigiert sie, wenn sich ein
  Schritt ändert.
- `tmp/`: lange Ausgaben und Entwürfe, nach 7 Tagen gelöscht. Nicht in git.
""",
}
MEMORY_INDEX = "# Memory of this project\n\n"


def ornis_dir(folder) -> Path:
    return Path(folder) / ORNIS_DIR


def _plain_folder(folder) -> bool:
    """Not the user's home, a system folder or the root: Ornis does not leave its notebook there."""
    try:
        path = Path(folder).resolve()
    except OSError:
        return False
    if not path.is_dir() or path == Path.home().resolve() or len(path.parts) <= 1:
        return False
    return os.access(path, os.W_OK)


def prepare_project(folder, language: str = "fr") -> None:
    """The .ornis folder of a project, made on its first Code conversation (nothing already there is rewritten);
    old files of tmp/ go."""
    if not _plain_folder(folder):
        return
    root = ornis_dir(folder)
    try:
        for sub in ("memory", "plans", "commands", "skills", "tmp"):
            (root / sub).mkdir(parents=True, exist_ok=True)
        for name, text in ((".gitignore", GITIGNORE), ("README.md", README_TEXT.get(language[:2], README_TEXT["en"])),
                           ("memory/MEMORY.md", MEMORY_INDEX)):
            if not (root / name).exists():
                (root / name).write_text(text, encoding="utf-8")
        ignore = root / ".gitignore"
        if "SOUL.md" not in ignore.read_text().splitlines():
            with ignore.open("a") as out:
                out.write("\nSOUL.md\n")
        limit = time.time() - TMP_DAYS * 86400
        for base, dirs, names in os.walk(root / "tmp", topdown=False):
            for n in names:
                p = Path(base) / n
                if p.lstat().st_mtime < limit:
                    p.unlink()
            if Path(base) != root / "tmp" and not os.listdir(base):
                os.rmdir(base)
    except OSError as error:
        print("Ornis Code: .ornis", error)


def _read_capped(path: Path, cap: int, label: str) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""
    if not text:
        return ""
    if len(text) > cap:
        text = text[:cap].rsplit("\n", 1)[0] + f"\n[… cut here: read the rest of {label} when you need it]"
    return f"## {label}\n{text}\n\n"


def project_context(folder) -> str:
    """What the first message of a conversation carries about the project: its rules, the user's own rules here,
    Ornis's memory index, the latest plans and the project's commands. Empty when there is nothing."""
    root = Path(folder)
    notebook = ornis_dir(folder)
    parts = ""
    # The closer rule wins: personal, then the notebook, then Ornis's root guide, then the shared one.
    parts += _read_capped(notebook / "rules.local.md", RULES_CAP, ".ornis/rules.local.md (the user's own rules here)")
    parts += _read_capped(notebook / "rules.md", RULES_CAP, ".ornis/rules.md (the project's rules for you)")
    parts += _read_capped(root / "ORNIS.md", RULES_CAP, "ORNIS.md (Ornis's guide, at the root)")
    shared = "AGENTS.md" if (root / "AGENTS.md").is_file() else "CLAUDE.md"
    parts += _read_capped(root / shared, RULES_CAP, f"{shared} (shared project guide, at the root)")
    global_soul = system.CONFIG / "SOUL.md"
    parts += ("Style files you edit yourself (the write is shown and the person approves it): "
              f"`.ornis/SOUL.md` for this folder, and `{global_soul}` for every project. "
              "The folder one wins. Style only: never a secret, never a technical rule.\n\n")
    soul = notebook / "SOUL.md" if (notebook / "SOUL.md").is_file() else root / "SOUL.md"
    parts += _read_capped(soul, SOUL_CAP, "SOUL.md (personal style only; you edit .ornis/SOUL.md; technical and safety rules take precedence; never store secrets)")
    parts += _read_capped(global_soul, SOUL_CAP, f"SOUL.md (global style at {global_soul}; you edit this file; the folder's SOUL.md wins; never secrets)")

    index = _read_capped(notebook / "memory" / "MEMORY.md", MEMORY_CAP, ".ornis/memory/MEMORY.md (what you remember)")
    if index and index.strip() != f"## .ornis/memory/MEMORY.md (what you remember)\n{MEMORY_INDEX.strip()}":
        parts += index
    remaining = MEMORY_CAP
    try:
        for memory in sorted((notebook / "memory").glob("*.md"))[:100]:
            if memory.name == "MEMORY.md" or remaining <= 0 or memory.is_symlink():
                continue
            text = _read_capped(memory, remaining, str(memory.relative_to(root)))
            parts += text
            remaining -= len(text)
    except OSError:
        pass
    try:
        plans = sorted((p for p in (notebook / "plans").glob("*.md") if p.is_file()), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        plans = []
    if plans:
        parts += "## .ornis/plans (latest first)\n" + "\n".join(f"- {p.name}" for p in plans[:8]) + "\n\n"
    skills = project_skills(folder)
    if skills:
        parts += "## .ornis/skills (this project's procedures: load one with the skill tool, or read its SKILL.md)\n" + \
            "\n".join(f"- {k['name']}: {k['description']}" for k in skills) + "\n\n"
    commands = project_commands(folder)
    if commands:
        parts += "## .ornis/commands (the user's « / » commands here)\n" + "\n".join(
            f"- /{c['name']}: {c['description']}" for c in commands) + "\n\n"
    # the model does not know the date (seen 05/11: a plan named 2025-11-05-…): plans and memories need it
    today = time.strftime("%Y-%m-%d (%A)")
    if not parts:
        return f"[Project notebook: .ornis/ is empty so far. Today is {today}.\n]\n\n"
    return (f"[Project notebook, read at the start of this conversation. Today is {today}. Instructions here OVERRIDE "
            "your defaults; the closer to the folder, the higher the priority (rules.local.md, then rules.md, then "
            "ORNIS.md, then AGENTS.md or CLAUDE.md). Use your memory, keep it up to date.\n\n" + parts.rstrip() + "\n]\n\n")


COMMAND_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,40}$")


def project_commands(folder) -> list[dict]:
    """The project's « / » commands: .ornis/commands/<name>.md, its description from a `description:` line of the
    front matter, otherwise its first line."""
    out = []
    try:
        files = sorted((ornis_dir(folder) / "commands").glob("*.md"))
    except OSError:
        return out
    for path in files[:40]:
        name = path.stem.lower()
        if not COMMAND_NAME.match(name):
            continue
        try:
            head = path.read_text(encoding="utf-8", errors="replace")[:2000]
        except OSError:
            continue
        description = ""
        meta = re.match(r"^---\s*\n(.*?)\n---\s*\n?", head, re.S)
        if meta:
            found = re.search(r"^description:\s*(.+)$", meta.group(1), re.M)
            description = found.group(1).strip().strip("\"'") if found else ""
            head = head[meta.end():]
        if not description:
            description = next((line.strip("# ").strip() for line in head.splitlines() if line.strip()), "")
        out.append({"name": name, "description": description[:120], "path": str(path)})
    return out


def project_skills(folder) -> list[dict]:
    """The project's skills: .ornis/skills/<name>/SKILL.md, with the name and description of their front matter."""
    out = []
    try:
        files = sorted((ornis_dir(folder) / "skills").glob("*/SKILL.md"))
    except OSError:
        return out
    for path in files[:40]:
        try:
            head = path.read_text(encoding="utf-8", errors="replace")[:3000]
        except OSError:
            continue
        meta = re.match(r"^---\s*\n(.*?)\n---", head, re.S)
        fields = dict(re.findall(r"^(name|description):\s*(.+)$", meta.group(1), re.M)) if meta else {}
        out.append({"name": fields.get("name", path.parent.name).strip().strip("\"'"),
                    "description": fields.get("description", "").strip().strip("\"'")[:200], "path": str(path)})
    return out


def expand_command(folder, name: str, args: str) -> str | None:
    """The text of a project command, with what follows it in place of $ARGUMENTS (or after it)."""
    name = name.lower()
    if not COMMAND_NAME.match(name):
        return None
    path = ornis_dir(folder) / "commands" / f"{name}.md"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    text = re.sub(r"^---\s*\n.*?\n---\s*\n?", "", text, count=1, flags=re.S).strip()
    if "$ARGUMENTS" in text:
        text = text.replace("$ARGUMENTS", args.strip())
    elif args.strip():
        text += "\n\n" + args.strip()
    return f"[Project command /{name} (.ornis/commands/{name}.md)]\n\n{text}"


def in_notebook(folder, raw: dict, bot: str = "") -> bool:
    """A file call whose every path is in Ornis's notebook (.ornis/memory, plans or tmp) of this project,
    or in a bot's profile memory/skills/tmp when `bot` is set."""
    if not isinstance(raw, dict):
        return False
    paths = [raw.get(k) for k in ("path", "file_path", "filePath", "target_file") if isinstance(raw.get(k), str) and raw.get(k)]
    if not paths:
        return False
    allowed = []
    if folder:
        base = ornis_dir(folder).resolve()
        allowed = [base / sub for sub in NOTEBOOK]
    if bot:
        try:
            import ornis_bots  # noqa: PLC0415
            root = ornis_bots.bot_dir(bot).resolve()
            allowed += [root / sub for sub in ("memory", "skills", "tmp")]
            allowed.append(root / "SOUL.md")
        except (ValueError, OSError):
            pass
    if not allowed:
        return False
    for p in paths:
        path = Path(p) if os.path.isabs(p) else Path(folder or ".") / p
        try:
            path = path.resolve()
        except OSError:
            return False
        if not any(path == a or a in path.parents for a in allowed):
            return False
    return True


def notebook_path(rel: str) -> bool:
    """A project path (relative, with /) in Ornis's notebook: left out of the checkpoints (undoing a turn never takes
    back what Ornis learnt) and of the folder's list given to the model."""
    parts = rel.replace("\\", "/").split("/")
    return len(parts) >= 3 and parts[0] == ORNIS_DIR and parts[1] in NOTEBOOK


# ---- the sandbox --------------------------------------------------------------------------------------------------
def sandbox_kind() -> str:
    try:
        import ornis_local
        return ornis_local.sandbox_available()
    except Exception:  # noqa: BLE001
        return ""


def global_soul_file() -> Path | None:
    """The one config file the agent may write. A symlink is refused. An empty file is created so the
    sandbox can bind it before the first edit."""
    soul = system.CONFIG / "SOUL.md"
    try:
        if soul.is_symlink() or soul.parent.is_symlink():
            return None
        soul.parent.mkdir(parents=True, exist_ok=True)
        if not soul.exists():
            soul.write_text("", encoding="utf-8")
        if not soul.is_file() or soul.is_symlink():
            return None
        return soul.resolve()
    except OSError:
        return None


def wrap(argv: list[str], folder: Path, bot: str = "") -> list[str]:
    """The agent in the system's sandbox: it writes only in the project, its home, the developer caches and /tmp."""
    kind = sandbox_kind()
    user_home = Path.home().resolve()
    # ROOT holds cron.json + cron-mcp context: MCP children inherit this seatbelt/bwrap
    writable = [folder.resolve(), home().resolve(), ROOT.resolve()]
    soul = global_soul_file()
    if soul:
        writable.append(soul)
    if bot:
        try:
            import ornis_bots  # noqa: PLC0415
            root = ornis_bots.bot_dir(bot)
            writable += [(root / sub).resolve() for sub in ("memory", "skills", "tmp")]
            writable.append((root / "SOUL.md").resolve())
        except Exception:  # noqa: BLE001
            pass
    writable += [user_home / c for c in CACHE_DIRS if (user_home / c).is_dir()]
    if kind == "bwrap":
        cmd = ["bwrap", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "--bind", "/tmp", "/tmp"]
        for path in writable:
            cmd += ["--bind", str(path), str(path)]
        for secret in SECRET_DIRS:
            path = user_home / secret
            if path.is_dir():
                cmd += ["--tmpfs", str(path)]
            elif path.is_file():
                cmd += ["--ro-bind", "/dev/null", str(path)]
        return [*cmd, "--chdir", str(folder), "--die-with-parent", "--", *argv]
    if kind == "seatbelt":
        allow = "".join(f'(allow file-write* (subpath "{p}"))' for p in writable)
        hide = "".join(f'(deny file-read* (subpath "{user_home / s}"))' for s in SECRET_DIRS)
        profile = ("(version 1)(allow default)"
                   f'(deny file-write* (subpath "{user_home}"))' + allow +
                   '(allow file-write* (subpath "/tmp") (subpath "/private/tmp") (subpath "/private/var/folders") (subpath "/dev"))'
                   + hide)
        return ["sandbox-exec", "-p", profile, *argv]
    return argv


# ---- approvals ----------------------------------------------------------------------------------------------------
SELF_PROCESS = re.compile(r"\b(p?kill|killall|taskkill|stop-process)\b[^|;&]*\b(vibe-acp|vibe|ornis|plume)\b", re.I)


def _against_itself(command: str, raw: dict) -> bool:
    """A command that stops the agent itself (seen 04/11: `pkill -f vibe-acp`, the conversation died), or an edit
    of its own configuration (it had turned `disabled_skills` off in config.toml)."""
    if command and (SELF_PROCESS.search(command) or re.search(r"(^|[\s/;&|])vibe-acp\b(?![^|;&]*\bgrep\b)", command)):
        return True                              # a second agent started on the same home answers the same turns
    own = str(home())
    paths = [str(raw.get(k) or "") for k in ("path", "file_path", "filepath", "target") if raw.get(k)]
    if command and own in command and re.search(r"(>|\btee\b|\bsed\s+-i|\brm\b|\bmv\b|\bcp\b|\bchmod\b)", command):
        return True
    return any(Path(p).expanduser().resolve().is_relative_to(Path(own).resolve()) for p in paths if p)


# File tools must pass the same checks as commands, including aliases and symlinks.
FILE_PATH_KEYS = ("path", "file_path", "filePath", "filepath", "target_file", "target", "source", "destination", "old_path", "new_path")
SECRET_PATH = re.compile(
    r"(^|/)(?:\.env(?:$|[./])|\.(?:ssh|gnupg|aws|azure|kube|password-store)(?:/|$)|"
    r"\.(?:netrc|npmrc|yarnrc\.yml|git-credentials|pgpass|my\.cnf|pypirc)(?:/|$)|"
    r"id_(?:rsa|ed25519|ecdsa|dsa)(?:$|[./])|(?:credentials|auth)\.json$|"
    r"secrets?\.(?:ya?ml|json|toml)$)|"
    r"\.(?:pem|key|p12|pfx|p8|jks|keystore|kdbx|asc|gpg|tfvars)$|"
    r"(^|/)\.docker/config\.json$|(^|/)\.config/(?:gh|gcloud)(?:/|$)", re.I)
PROTECTED_PATH = re.compile(r"(^|/)(?:\.(?:git|vscode|idea|husky|devcontainer)(?:/|$)|"
                            r"SOUL\.md$|\.github/workflows(?:/|$)|\.gitlab-ci\.yml$)", re.I)


def file_paths(tool: dict) -> list[str]:
    raw = tool.get("rawInput") if isinstance(tool.get("rawInput"), dict) else {}
    paths = [raw[k] for k in FILE_PATH_KEYS if isinstance(raw.get(k), str) and raw[k]]
    for item in [*(tool.get("locations") or []), *(tool.get("content") or [])]:
        if isinstance(item, dict) and isinstance(item.get("path"), str):
            paths.append(item["path"])
    return paths


def retry_outside(command: str, output: str, folder: str, sandbox: str) -> bool:
    import ornis_shell
    if sandbox not in ("bwrap", "seatbelt") or always_ask({"kind": "execute", "rawInput": {"command": command}}, folder):
        return False
    info = ornis_shell.classify(command)
    if not info.get("simple") or info.get("level") == "admin" or info.get("sensitive") or info.get("blocked"):
        return False
    return bool(re.search(r"EACCES|EPERM|Permission denied|Operation not permitted|Read-only file system|bwrap:.*(?:bind|mount|namespace)|sandbox-exec:.*(?:deny|denied|Operation)", output, re.I))


def always_ask(tool: dict, folder: str = "", reusable: bool = True) -> bool:
    """No reusable approval for secrets, or modifications of executable configuration."""
    from ornis_consent import sensitive
    raw = tool.get("rawInput") if isinstance(tool.get("rawInput"), dict) else {}
    command = str(raw.get("command") or "")
    writing = tool.get("kind") not in ("read", "search", "think", "fetch") or bool(command)
    if command:
        import ornis_shell
        if reusable and not ornis_shell.rule_for(command, folder):
            return True
    paths = file_paths(tool)
    if command:
        paths += re.split(r"[\s\"'=;|&]+", command)
    for name in paths:
        normalized = name.replace("\\", "/")
        candidates = [normalized]
        if folder and name:
            try:
                path = Path(normalized).expanduser()
                candidates.append(str((path if path.is_absolute() else Path(folder) / path).resolve()).replace("\\", "/"))
            except (OSError, RuntimeError, ValueError):
                return True
        if any(sensitive(path) or SECRET_PATH.search(path) or (writing and PROTECTED_PATH.search(path)) for path in candidates):
            return True
    return False


def approval_key(tool: dict, folder: str = "") -> str:
    """Stable key so a bot can remember one « Autoriser » for the same kind of action."""
    kind = str(tool.get("kind") or "")
    raw = tool.get("rawInput") if isinstance(tool.get("rawInput"), dict) else {}
    command = str(raw.get("command") or "") if kind == "execute" or "command" in raw else ""
    if command:
        # What still asks a bot is a secret, sudo or « curl | sh »: only this very command is remembered, never its
        # program (one « cat .env » allowed must not open « cat ~/.ssh/id_rsa », one sudo every sudo).
        return "cmd:exact:" + " ".join(command.split())
    found = set()
    for p in file_paths(tool):
        if not p:
            continue
        try:
            path = Path(p.replace("\\", "/")).expanduser()
            if not path.is_absolute() and folder:
                path = Path(folder) / path          # relative to the bot's folder, not to Plume's cwd
            found.add(str(path.resolve()).replace("\\", "/"))
        except (OSError, RuntimeError, ValueError):
            found.add(p.replace("\\", "/"))
    if found:
        return f"{kind}:{sorted(found)[0]}"
    title = str(tool.get("title") or "").strip()[:80]
    return f"{kind}:{title}" if kind and title else ""


def _bot_remembers(bot: str, tool: dict, folder: str = "") -> bool:
    if not bot:
        return False
    try:
        import ornis_bots
        return ornis_bots.has_approval(bot, approval_key(tool, folder))
    except Exception:  # noqa: BLE001
        return False


def decide(mode: str, tool: dict, sandboxed: bool = False, folder: str = "", bot: str = "") -> str:
    """What to do with a permission the agent asks: 'allow', 'ask' (the user chooses) or 'reject'.
    tool: the tool call as the agent described it (kind, rawInput, title). In the default mode (« edits »), an
    ordinary command (tests, a build) runs without asking when the agent is in the sandbox: it can only write in
    the project; without one, only the commands that read.
    A bot in Autonome works alone: only secrets / admin / remote scripts ask once, then the answer is remembered."""
    kind = str(tool.get("kind") or "")
    raw = tool.get("rawInput") if isinstance(tool.get("rawInput"), dict) else {}
    command = str(raw.get("command") or "") if kind == "execute" or "command" in raw else ""
    remembered = _bot_remembers(bot, tool, folder)
    if _against_itself(command, raw if kind not in ("read", "search", "think", "fetch") else {}):
        return "reject"                              # never in any mode: Ornis would stop itself or loosen its rules
    if command:
        import ornis_shell
        if ornis_shell.classify(command).get("blocked"):
            return "reject"
    if always_ask(tool, folder, reusable=False):
        if remembered:
            return "allow"
        return "reject" if mode == "plan" and kind not in ("read", "search", "think", "fetch") else "ask"
    if kind in ("edit", "delete") and in_notebook(folder, raw, bot):
        return "allow"                               # its own notebook (memory, plans, tmp): in every mode, Plan too
    if mode == "plan":                               # Plan: Ornis looks, never changes anything
        if kind in ("read", "search", "think", "fetch"):
            return "allow"
        if command:
            try:
                import ornis_shell
                info = ornis_shell.classify(command)
            except Exception:  # noqa: BLE001
                return "reject"
            return "allow" if info.get("read_only") and not info.get("sensitive") and not info.get("blocked") else "reject"
        return "reject"
    # Bot Autonome: act alone. Only true secrets (above), admin elevation and « curl | sh » ask once.
    if bot and mode == "auto":
        if command:
            try:
                import ornis_shell
                info = ornis_shell.classify(command)
            except Exception:  # noqa: BLE001
                info = {"level": "change", "sensitive": True, "blocked": ""}
            if info.get("blocked"):
                return "reject"
            risky = info.get("level") == "admin" or (
                info.get("sensitive") and ornis_shell.REMOTE_SCRIPT.search(command))
            if risky:
                return "allow" if remembered else "ask"
            return "allow"
        return "allow"
    if command:
        try:
            import ornis_shell
            info = ornis_shell.classify(command)
        except Exception:  # noqa: BLE001
            info = {"level": "change", "sensitive": True, "blocked": ""}
        if info.get("blocked"):
            return "reject"                          # never, in any mode
        if info.get("sensitive") or info.get("level") == "admin":
            return "ask"                             # secrets, sudo, a script from the web: always asked
        if mode == "auto" or (mode == "edits" and (info.get("read_only") or sandboxed)):
            return "allow"
        return "ask"
    if kind in ("read", "search", "think", "fetch") and mode != "ask":
        return "allow"
    if kind in ("edit", "delete", "move") and mode in ("edits", "auto"):
        return "allow" if kind == "edit" or mode == "auto" else "ask"
    return "allow" if mode == "auto" else "ask"


# ---- the ACP connection -------------------------------------------------------------------------------------------
class Agent:
    """One `vibe-acp` process and its JSON-RPC connection. Callbacks run on the reader thread:
    on_update(session_id, update), on_permission(request_id, session_id, tool_call_id, options),
    on_exit(code, stderr_tail)."""

    def __init__(self, exe: Path, folder: Path, token: str, on_update=None, on_permission=None, on_exit=None,
                 sandbox: bool = True, on_question=None, gateway_url: str = "", bot: str = ""):
        self.folder = Path(folder).resolve()
        self.bot = str(bot or "").strip()
        self.on_update, self.on_permission, self.on_exit = on_update, on_permission, on_exit
        self.on_question = on_question               # (request_id, session_id, questions): Vibe's ask_user_question
        env = dict(os.environ, VIBE_HOME=str(home(self.bot)), ORNEOS_CODE_TOKEN=token, NO_COLOR="1", CI="1",
                   PYTHONUNBUFFERED="1", ORNIS_CRON_FOLDER=str(self.folder))
        env["ORNIS_BOT_ID"] = self.bot
        if gateway_url:
            env["ORNEOS_CODE_URL"] = str(gateway_url).rstrip("/")
            # URL only (no token) so the search MCP can find the gateway if env was trimmed
            try:
                ROOT.mkdir(parents=True, exist_ok=True)
                (ROOT / "gateway.json").write_text(
                    json.dumps({"url": env["ORNEOS_CODE_URL"]}, ensure_ascii=False), encoding="utf-8")
            except OSError:
                pass
        for key in ("MISTRAL_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
            env.pop(key, None)                       # only our gateway
        argv = wrap([str(exe)], self.folder, self.bot) if sandbox else [str(exe)]
        flags = subprocess.CREATE_NO_WINDOW if system.WINDOWS else 0
        self._lock = threading.Lock()
        self._next = 0
        self._waiting: dict[int, list] = {}
        self._stderr: list[str] = []
        self.info: dict = {}
        # The process is started by its own reader thread, which lives as long as it: bwrap --die-with-parent
        # (PR_SET_PDEATHSIG) kills the agent when the *thread* that started it ends, not the program. Started from
        # a short-lived thread, the agent died a few seconds after the project opened (Orneos OS only).
        started, failure = threading.Event(), []

        def run():
            try:
                self._proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                              stderr=subprocess.PIPE, cwd=str(self.folder), env=env,
                                              creationflags=flags)
            except Exception as error:  # noqa: BLE001
                failure.append(error)
                started.set()
                return
            started.set()
            threading.Thread(target=self._read_errors, daemon=True, name="ornis-code-err").start()
            self._read()
        threading.Thread(target=run, daemon=True, name="ornis-code-acp").start()
        started.wait()
        if failure:
            raise failure[0]

    # -- plumbing
    def _send(self, message: dict) -> None:
        data = (json.dumps(message, ensure_ascii=False) + "\n").encode()
        with self._lock:
            try:
                self._proc.stdin.write(data)
                self._proc.stdin.flush()
            except (OSError, ValueError):
                pass

    def call(self, method: str, params: dict, timeout: float = 120) -> dict:
        """A request; returns its result, raises RuntimeError with the agent's message on an error."""
        with self._lock:
            self._next += 1
            ident = self._next
            slot = [threading.Event(), None]
            self._waiting[ident] = slot
        self._send({"jsonrpc": "2.0", "id": ident, "method": method, "params": params})
        if not slot[0].wait(timeout):
            self._waiting.pop(ident, None)
            raise TimeoutError(method)
        reply = slot[1] or {}
        if "error" in reply:
            error = reply["error"] or {}
            raise RuntimeError(str(error.get("message") or error.get("code") or "error"))
        return reply.get("result") or {}

    def notify(self, method: str, params: dict) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def answer(self, request_id, result: dict | None = None, error: str = "") -> None:
        if error:
            self._send({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": error}})
        else:
            self._send({"jsonrpc": "2.0", "id": request_id, "result": result or {}})

    def _read(self) -> None:
        for line in self._proc.stdout:
            try:
                message = json.loads(line)
            except ValueError:
                continue
            method = message.get("method")
            if method and "id" in message:                    # the agent asks us something
                params = message.get("params") or {}
                if method == "session/request_permission" and self.on_permission:
                    tool = params.get("toolCall") or {}
                    self.on_permission(message["id"], params.get("sessionId", ""), tool, params.get("options") or [])
                elif method == "elicitation/create":
                    asked = questions_from_schema(params.get("requestedSchema") or {}) if params.get("mode") == "form" else []
                    if asked and self.on_question:
                        self.on_question(message["id"], params.get("sessionId", ""), asked)
                    else:
                        self.answer(message["id"], {"action": "decline"})
                else:
                    self.answer(message["id"], error="not supported")   # fs/terminal: the agent does it itself
            elif method:
                params = message.get("params") or {}
                if method == "session/update" and self.on_update:
                    self.on_update(params.get("sessionId", ""), params.get("update") or {})
            else:
                slot = self._waiting.pop(message.get("id"), None)
                if slot:
                    slot[1] = message
                    slot[0].set()
        code = self._proc.wait()
        for slot in list(self._waiting.values()):
            slot[1] = {"error": {"message": "exited"}}
            slot[0].set()
        self._waiting.clear()
        if self.on_exit:
            self.on_exit(code, "".join(self._stderr[-20:]))

    def _read_errors(self) -> None:
        for line in self._proc.stderr:
            self._stderr.append(line.decode("utf-8", "replace"))
            del self._stderr[:-200]

    # -- the protocol
    def start(self) -> dict:
        self.info = self.call("initialize", {"protocolVersion": 1, "clientInfo": {"name": "ornis", "version": VERSION},
                                             "clientCapabilities": {"fs": {"readTextFile": False, "writeTextFile": False},
                                                                    "terminal": False,
                                                                    # Vibe's ask_user_question: our QuestionsDock
                                                                    "elicitation": {"form": {}}}}, timeout=60)
        return self.info

    def new_session(self) -> dict:
        return self.call("session/new", {"cwd": str(self.folder),
                                         "mcpServers": mcp_servers(str(self.folder), self.bot)}, timeout=60)

    def load_session(self, session_id: str) -> dict:
        """Opens a conversation of this folder again: the agent replays it as updates first."""
        return self.call("session/load", {"sessionId": session_id, "cwd": str(self.folder),
                                          "mcpServers": mcp_servers(str(self.folder), self.bot)}, timeout=120)

    def list_sessions(self) -> list[dict]:
        try:
            return list(self.call("session/list", {"cwd": str(self.folder)}, timeout=30).get("sessions") or [])
        except (RuntimeError, TimeoutError):
            return []

    def set_mode(self, session_id: str, mode: str) -> None:
        # Ornis decides each approval. accept-edits would bypass protected-path checks.
        self.call("session/set_mode", {"sessionId": session_id, "modeId": "ask"}, timeout=30)

    def prompt(self, session_id: str, blocks: list[dict]) -> dict:
        """Sends a message; returns when the agent has finished ({stopReason}). Updates arrive meanwhile."""
        return self.call("session/prompt", {"sessionId": session_id, "prompt": blocks}, timeout=3600)

    def cancel(self, session_id: str) -> None:
        self.notify("session/cancel", {"sessionId": session_id})

    def alive(self) -> bool:
        return self._proc.poll() is None

    def close(self) -> None:
        if self._proc.poll() is None:
            try:
                self._proc.stdin.close()
            except OSError:
                pass
            try:
                self._proc.wait(3)
            except subprocess.TimeoutExpired:
                self._proc.kill()


# ---- Vibe's questions (ask_user_question → ACP elicitation/create, a form: one property q0, q1… per question) -------
def questions_from_schema(schema: dict) -> list[dict]:
    """The questions as the dock shows them: [{key, question, header, multi, options: [{label, description}]}]."""
    out = []
    for key, prop in (schema.get("properties") or {}).items():
        if not isinstance(prop, dict):
            continue
        multi = prop.get("type") == "array"
        raw = ((prop.get("items") or {}).get("anyOf") or (prop.get("items") or {}).get("enum") or []) if multi else \
            (prop.get("oneOf") or prop.get("enum") or [])
        options = []
        for o in raw:
            label = str((o.get("const") or o.get("title")) if isinstance(o, dict) else o or "").strip()
            if label:
                options.append({"label": label[:120], "description": ""})
        question = str(prop.get("description") or prop.get("title") or "").strip()
        if question:
            out.append({"key": str(key), "question": question[:500], "header": str(prop.get("title") or "")[:24],
                        "multi": multi, "options": options[:8]})
    return out[:4]


def elicitation_content(questions: list[dict], answers: list, undecided: str) -> dict:
    """What goes back to Vibe ({action: accept, content}): each question answered (Vibe refuses an empty one: the
    words « decide yourself » then); « Autre » text is taken by Vibe as the user's own answer."""
    content = {}
    for i, q in enumerate(questions):
        a = answers[i] if i < len(answers) and isinstance(answers[i], dict) else {}
        chosen = [str(c) for c in a.get("chosen") or [] if str(c).strip()]
        note = str(a.get("note") or "").strip()[:2000]
        if q.get("multi"):
            content[q["key"]] = (chosen + ([note] if note else [])) or [undecided]
        else:
            content[q["key"]] = (chosen[0] + (" — " + note if note else "")) if chosen else (note or undecided)
    return {"action": "accept", "content": content}


def text_block(text: str) -> dict:
    return {"type": "text", "text": text}


IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp"}
MAX_IMAGE = 8 * 1024 * 1024


def image_block(path: Path) -> dict | None:
    """An image joined to the message, given to the model itself (a screenshot of a bug, a mock-up); None if too big."""
    import base64  # noqa: PLC0415
    path = Path(path)
    mime = IMAGE_TYPES.get(path.suffix.lower())
    try:
        if not mime or path.stat().st_size > MAX_IMAGE:
            return None
        return {"type": "image", "mimeType": mime, "data": base64.b64encode(path.read_bytes()).decode()}
    except OSError:
        return None


def _usable_python() -> str | None:
    """A real Python 3 binary — not macOS's /usr/bin/python3 stub that only opens Xcode."""
    import shutil  # noqa: PLC0415
    import subprocess  # noqa: PLC0415
    candidates: list[str] = []
    # Prefer Homebrew / pyenv before PATH (Mac CLT stub is often first as python3)
    for fixed in (
        "/opt/homebrew/bin/python3",
        "/usr/local/bin/python3",
        str(Path.home() / ".pyenv/shims/python3"),
    ):
        if Path(fixed).is_file():
            candidates.append(fixed)
    for name in ("python3", "python"):
        py = shutil.which(name)
        if py:
            candidates.append(py)
    seen: set[str] = set()
    for py in candidates:
        try:
            resolved = str(Path(py).resolve())
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        # Reject the CLT stub before it prompts (common mcp_transport_failed on Mac)
        try:
            if system.MACOS and resolved == str(Path("/usr/bin/python3").resolve()):
                probe = subprocess.run(
                    [resolved, "-c", "import sys; print(sys.version_info[0])"],
                    capture_output=True, timeout=2, text=True)
                if probe.returncode != 0 or not (probe.stdout or "").strip().startswith("3"):
                    continue
            else:
                probe = subprocess.run(
                    [resolved, "-c", "import sys; print(sys.version_info[0])"],
                    capture_output=True, timeout=2, text=True)
                if probe.returncode != 0 or not (probe.stdout or "").strip().startswith("3"):
                    continue
            return resolved
        except (OSError, subprocess.TimeoutExpired):
            continue
    return None


def cron_cli_command() -> list[str]:
    """Argv to run the cron CLI (same tools as MCP, for the shell fallback)."""
    import sys  # noqa: PLC0415
    if system.FROZEN:
        return [str(Path(sys.executable).resolve()), "--ornis-helper=cron-cli"]
    return [str(Path(sys.executable).resolve()), "-I",
            str(Path(__file__).resolve().with_name("ornis_cron_cli.py"))]


def search_cli_command() -> list[str]:
    """Argv to run the search CLI (same tools as MCP, for the shell fallback)."""
    import sys  # noqa: PLC0415
    if system.FROZEN:
        return [str(Path(sys.executable).resolve()), "--ornis-helper=search-cli"]
    return [str(Path(sys.executable).resolve()), "-I",
            str(Path(__file__).resolve().with_name("ornis_search_cli.py"))]


def bots_cli_command() -> list[str]:
    """Argv to run the bots CLI (same tools as MCP, for the shell fallback)."""
    import sys  # noqa: PLC0415
    if system.FROZEN:
        return [str(Path(sys.executable).resolve()), "--ornis-helper=bots-cli"]
    return [str(Path(sys.executable).resolve()), "-I",
            str(Path(__file__).resolve().with_name("ornis_bots_cli.py"))]


def _script(name: str) -> Path:
    """Source or bundled path of a share/orneos script."""
    import sys  # noqa: PLC0415
    path = Path(__file__).resolve().with_name(name)
    if system.FROZEN:
        bundled = Path(getattr(sys, "_MEIPASS", "") or "") / "orneos" / name
        if bundled.is_file():
            return bundled
    return path


def ensure_cron_bins(folder: str = "", lang: str = "fr", bot: str = "") -> Path:
    """Shell launchers under DATA/ornis-code/bin: stdio MCP wrappers + CLIs for the agent.

    Preferred path for Vibe is HTTP MCP (see mcp_servers / ornis_mcp_http): stdio children
    inherit seatbelt and break Plume re-entry on Mac. Stdio wrappers remain as a fallback
    when the local HTTP bridge cannot bind. CLIs are what the agent runs when MCP is down
    (bash can retry outside the sandbox).
    """
    import shlex  # noqa: PLC0415
    import sys  # noqa: PLC0415
    bin_dir = ROOT / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    folder = str(folder or "").strip()
    lang = (lang or "fr")[:2]
    bot = str(bot or os.environ.get("ORNIS_BOT_ID") or "").strip()
    (ROOT / "cron-mcp-context.json").write_text(
        json.dumps({"folder": folder, "lang": lang, "bot": bot}, ensure_ascii=False), encoding="utf-8")

    exe = str(Path(sys.executable).resolve())
    py = _usable_python()
    share = str(Path(__file__).resolve().parent)
    if system.FROZEN:
        bundled_dir = Path(getattr(sys, "_MEIPASS", "") or "") / "orneos"
        if bundled_dir.is_dir():
            share = str(bundled_dir)

    def _mcp_exec(helper: str, script_name: str) -> str:
        script = _script(script_name)
        if py and script.is_file():
            return f"exec {shlex.quote(py)} -I {shlex.quote(str(script))}"
        return f"exec {shlex.quote(exe)} --ornis-helper={helper}"

    py_path = share + ((os.pathsep + os.environ["PYTHONPATH"]) if os.environ.get("PYTHONPATH") else "")
    exports = [
        f'ornis_default_folder={shlex.quote(folder)}',
        'export ORNIS_CRON_FOLDER="${ORNIS_CRON_FOLDER-$ornis_default_folder}"',
        f'export ORNIS_CRON_LANG={shlex.quote(lang)}',
        f'export ORNIS_BOT_LANG={shlex.quote(lang)}',
        f'export PYTHONPATH={shlex.quote(py_path)}',
        'export TMPDIR="${TMPDIR:-/tmp}"',
        'export HOME="${HOME:-$(cd ~ && pwd)}"',
    ]
    if bot:
        exports.append(f'export ORNIS_BOT_ID="${{ORNIS_BOT_ID-{bot}}}"')
    if system.MACOS and system.FROZEN:
        frameworks = Path(exe).parent.parent / "Frameworks"
        if frameworks.is_dir():
            exports.append(f'export DYLD_FRAMEWORK_PATH={shlex.quote(str(frameworks))}')
            exports.append(f'export DYLD_LIBRARY_PATH={shlex.quote(str(frameworks))}')

    # Force /bin/sh as the ACP command (vibe execve's it); script is the arg — more reliable
    # than relying on the kernel shebang for a file under Application Support.
    mcp_sh = bin_dir / "ornis-cron-mcp"
    mcp_sh.write_text(
        "#!/bin/sh\n# Written by Ornis (ornis_code.ensure_cron_bins). Stdio MCP entry for Vibe.\n"
        + "\n".join(exports) + "\n" + _mcp_exec("cron-mcp", "ornis_cron_mcp.py") + "\n",
        encoding="utf-8")
    mcp_sh.chmod(0o755)

    # --- CLI for the agent (bash tool) when MCP tools are missing
    script_cli = _script("ornis_cron_cli.py")
    if py and script_cli.is_file():
        cli_exec = f"exec {shlex.quote(py)} -I {shlex.quote(str(script_cli))}"
    else:
        cli_exec = "exec " + " ".join(shlex.quote(a) for a in cron_cli_command())
    cli_sh = bin_dir / "ornis-cron"
    cli_sh.write_text(
        "#!/bin/sh\n# Written by Ornis. Fallback when ornis-cron MCP is not connected.\n"
        + "\n".join(exports) + "\n" + cli_exec + ' "$@"\n',
        encoding="utf-8")
    cli_sh.chmod(0o755)

    # --- Search MCP + CLI
    search_exports = list(exports)
    for key in ("ORNEOS_CODE_TOKEN", "ORNEOS_CODE_URL"):
        if os.environ.get(key):
            search_exports.append(f"export {key}={shlex.quote(os.environ[key])}")
    search_sh = bin_dir / "ornis-search-mcp"
    search_sh.write_text(
        "#!/bin/sh\n# Written by Ornis. Orneos Search MCP for Code (web_search / read_web_page).\n"
        + "\n".join(search_exports) + "\n" + _mcp_exec("search-mcp", "ornis_search_mcp.py") + "\n",
        encoding="utf-8")
    search_sh.chmod(0o755)

    script_scli = _script("ornis_search_cli.py")
    if py and script_scli.is_file():
        scli_exec = f"exec {shlex.quote(py)} -I {shlex.quote(str(script_scli))}"
    else:
        scli_exec = "exec " + " ".join(shlex.quote(a) for a in search_cli_command())
    scli_sh = bin_dir / "ornis-search"
    scli_sh.write_text(
        "#!/bin/sh\n# Written by Ornis. Fallback when ornis-search MCP is not connected.\n"
        + "\n".join(search_exports) + "\n" + scli_exec + ' "$@"\n',
        encoding="utf-8")
    scli_sh.chmod(0o755)

    # --- Bots MCP + CLI
    bots_sh = bin_dir / "ornis-bots-mcp"
    bots_sh.write_text(
        "#!/bin/sh\n# Written by Ornis. Code-mode bots MCP (profiles, SOUL, peer messages).\n"
        + "\n".join(exports) + "\n" + _mcp_exec("bots-mcp", "ornis_bots_mcp.py") + "\n",
        encoding="utf-8")
    bots_sh.chmod(0o755)

    script_bcli = _script("ornis_bots_cli.py")
    if py and script_bcli.is_file():
        bcli_exec = f"exec {shlex.quote(py)} -I {shlex.quote(str(script_bcli))}"
    else:
        bcli_exec = "exec " + " ".join(shlex.quote(a) for a in bots_cli_command())
    bcli_sh = bin_dir / "ornis-bots"
    bcli_sh.write_text(
        "#!/bin/sh\n# Written by Ornis. Fallback when ornis-bots MCP is not connected.\n"
        + "\n".join(exports) + "\n" + bcli_exec + ' "$@"\n',
        encoding="utf-8")
    bcli_sh.chmod(0o755)
    return bin_dir


def cron_mcp_command() -> list[str]:
    """`/bin/sh` + wrapper path — never the wrapper alone (shebang under seatbelt is fragile)."""
    ensure_cron_bins()
    return ["/bin/sh", str((ROOT / "bin" / "ornis-cron-mcp").resolve())]


def search_mcp_command() -> list[str]:
    ensure_cron_bins()
    return ["/bin/sh", str((ROOT / "bin" / "ornis-search-mcp").resolve())]


def bots_mcp_command() -> list[str]:
    ensure_cron_bins()
    return ["/bin/sh", str((ROOT / "bin" / "ornis-bots-mcp").resolve())]


def _mcp_base_env(folder: str, bot: str = "") -> list[dict]:
    """Env for Vibe's stdio MCP spawn (merged over a short default list — include TMPDIR)."""
    keys = (
        "HOME", "LOGNAME", "PATH", "SHELL", "TERM", "USER", "TMPDIR", "LANG", "LC_ALL",
        "XDG_RUNTIME_DIR", "XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME",
        "APPDATA", "LOCALAPPDATA", "USERPROFILE", "HOMEDRIVE", "HOMEPATH",
        "SYSTEMROOT", "WINDIR", "PATHEXT", "TEMP", "TMP", "SSL_CERT_FILE",
        "ORNEOS_CODE_TOKEN", "ORNEOS_CODE_URL",
    )
    env = [{"name": k, "value": os.environ[k]} for k in keys if os.environ.get(k)]
    folder = str(folder or os.environ.get("ORNIS_CRON_FOLDER") or "").strip()
    lang = (os.environ.get("ORNIS_CRON_LANG") or "fr")[:2]
    bot = str(bot or os.environ.get("ORNIS_BOT_ID") or "").strip()
    ensure_cron_bins(folder, lang, bot)
    share = str(Path(__file__).resolve().parent)
    if system.FROZEN:
        import sys  # noqa: PLC0415
        bundled = Path(getattr(sys, "_MEIPASS", "") or "") / "orneos"
        if bundled.is_dir():
            share = str(bundled)
    existing_pp = os.environ.get("PYTHONPATH") or ""
    env.append({"name": "PYTHONPATH",
                "value": share + (os.pathsep + existing_pp if existing_pp else "")})
    env.append({"name": "ORNIS_CRON_FOLDER", "value": folder})
    env.append({"name": "ORNIS_CRON_LANG", "value": lang})
    env.append({"name": "ORNIS_BOT_LANG", "value": lang})
    if bot:
        env.append({"name": "ORNIS_BOT_ID", "value": bot})
    return env


def _cron_mcp_env(folder: str, bot: str = "") -> list[dict]:
    return _mcp_base_env(folder, bot)


def _search_mcp_env(folder: str, bot: str = "") -> list[dict]:
    return _mcp_base_env(folder, bot)


def _bots_mcp_env(folder: str, bot: str = "") -> list[dict]:
    return _mcp_base_env(folder, bot)


def mcp_servers(folder: str = "", bot: str = "") -> list[dict]:
    """Built-in Code MCPs (cron + Orneos Search + bots) plus the servers from Ornis settings.

    Prefer the in-process HTTP bridge (ornis_mcp_http) so Vibe's seatbelt never has to
    re-spawn Plume. Fall back to stdio wrappers when the bridge cannot start.
    Secrets stay where they are: an env entry names a variable of this computer, its value is read here."""
    bot = str(bot or os.environ.get("ORNIS_BOT_ID") or "").strip()
    ensure_cron_bins(folder, bot=bot)
    try:
        import ornis_mcp_http  # noqa: PLC0415
        bridge = ornis_mcp_http.ensure()
    except Exception:  # noqa: BLE001
        bridge = None
    if bridge:
        auth = [{"name": "Authorization", "value": "Bearer " + bridge["token"]}]
        key = ornis_mcp_http.context_key(folder, (os.environ.get("ORNIS_CRON_LANG") or "fr"), bot)
        out = [
            {"type": "http", "name": "ornis-cron", "url": f"{bridge['cron_url']}/{key}", "headers": auth},
            {"type": "http", "name": "ornis-search", "url": bridge["search_url"], "headers": auth},
            {"type": "http", "name": "ornis-bots", "url": f"{bridge['bots_url']}/{key}", "headers": auth},
        ]
    else:
        cron_cmd = cron_mcp_command()
        search_cmd = search_mcp_command()
        bots_cmd = bots_mcp_command()
        out = [
            {"name": "ornis-cron", "command": cron_cmd[0], "args": cron_cmd[1:], "env": _cron_mcp_env(folder, bot)},
            {"name": "ornis-search", "command": search_cmd[0], "args": search_cmd[1:], "env": _search_mcp_env(folder, bot)},
            {"name": "ornis-bots", "command": bots_cmd[0], "args": bots_cmd[1:], "env": _bots_mcp_env(folder, bot)},
        ]
    try:
        import ornis_extensions  # noqa: PLC0415
        servers = ornis_extensions.settings().get("mcpServers") or {}
    except Exception:  # noqa: BLE001
        return out
    for name, item in servers.items():
        if item.get("disabled") or name in ("ornis-cron", "ornis-search", "ornis-bots"):
            continue
        if item.get("url"):
            headers = [{"name": h, "value": os.environ.get(v, "")} for h, v in (item.get("headersEnv") or {}).items() if os.environ.get(v)]
            bearer = ornis_extensions.token(name, item)         # the keychain, else the named variable
            if bearer:
                headers.append({"name": "Authorization", "value": "Bearer " + bearer})
            out.append({"type": "http", "name": name, "url": item["url"], "headers": headers})
        else:
            env = [{"name": k, "value": os.environ.get(v, "")} for k, v in (item.get("env") or {}).items() if os.environ.get(v) is not None]
            out.append({"name": name, "command": item["command"], "args": list(item.get("args") or []), "env": env})
    return out


def link_skills(root: Path) -> None:
    """The skills the user installed for Ornis (ornis_extensions.SKILLS) are the coding agent's too (VIBE_HOME/skills)."""
    try:
        import ornis_extensions  # noqa: PLC0415
        src = ornis_extensions.SKILLS
    except Exception:  # noqa: BLE001
        return
    target = root / "skills"
    if not src.is_dir():
        return
    try:
        if target.is_symlink() or not target.exists():
            if target.is_symlink():
                target.unlink()
            target.symlink_to(src, target_is_directory=True)
            return
    except OSError:
        pass                                    # Windows without the right to link: a copy, made again each start
    try:
        if target.exists() and not target.is_symlink():
            shutil.rmtree(target)
        shutil.copytree(src, target, symlinks=False)
    except OSError:
        pass


_GIT = None


def git_usable() -> bool:
    """git can run without side effect: on a Mac without the developer tools, /usr/bin/git only opens their installer."""
    global _GIT
    if _GIT is None:
        _GIT = bool(shutil.which("git"))
        if _GIT and platform.system() == "Darwin" and not Path("/Library/Developer/CommandLineTools/usr/bin/git").exists():
            try:
                _GIT = subprocess.run(["xcode-select", "-p"], capture_output=True, timeout=5).returncode == 0
            except (OSError, subprocess.SubprocessError):
                _GIT = False
    return _GIT


def git_info(folder) -> dict:
    """{branch, dirty} of the project when it is a git repository (and git is there): shown by the conversation."""
    folder = Path(folder)
    if not (folder / ".git").exists() or not git_usable():
        return {}
    try:
        branch = subprocess.run(["git", "-C", str(folder), "branch", "--show-current"], capture_output=True, text=True, timeout=10).stdout.strip()
        status = subprocess.run(["git", "-C", str(folder), "status", "--porcelain"], capture_output=True, text=True, timeout=20).stdout
        return {"branch": branch or "HEAD", "dirty": len([l for l in status.splitlines() if l.strip()])}
    except (OSError, subprocess.SubprocessError):
        return {}


def file_block(path: Path) -> dict:
    """A file of the computer joined to the message (a link the agent reads itself)."""
    path = Path(path).resolve()
    return {"type": "resource_link", "uri": path.as_uri(), "name": path.name}


def session_meta(update: dict) -> dict:
    """{title, updated} from a session_info_update."""
    return {"title": str(update.get("title") or ""), "updated": str(update.get("updatedAt") or "")}


def now() -> float:
    return time.time()


# ---- checkpoints: the folder as it was before each turn, to come back to (as /rewind in Claude Code) -------------------
# Kept on this computer, never in the project (its git, if any, is untouched): each file's content once (by its sha256),
# and per checkpoint the list of files. Pure Python: no git needed (Windows, a Mac without the developer tools). The
# heavy folders and the project's ignored files (git ls-files when the folder is a repository) are left out, a large
# file too; a file not changed since the last look (same size and time) is not read again.
CHECKPOINTS = ROOT / "checkpoints"
HEAVY_DIRS = {".git", "node_modules", "vendor", "__pycache__", ".venv", "venv", "dist", "build", "target", ".next", ".cache",
              ".gradle", ".idea", ".mypy_cache", ".pytest_cache", ".tox",
              # Unity, Unreal, Xcode, .NET, CocoaPods: generated, huge, never what Ornis changes
              "Library", "Temp", "Logs", "obj", "UserSettings", "MemoryCaptures", "Intermediate", "Saved", "DerivedDataCache",
              "DerivedData", "Pods", ".vs", "packages"}
# what Ornis never edits (images, sounds, videos, 3D models, archives, binaries): not kept, so a checkpoint stays quick
BINARY = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tga", ".tif", ".tiff", ".psd", ".exr", ".hdr", ".ico", ".icns",
          ".wav", ".mp3", ".ogg", ".flac", ".aif", ".aiff", ".mp4", ".mov", ".avi", ".mkv", ".webm", ".fbx", ".obj", ".blend",
          ".glb", ".gltf", ".dae", ".3ds", ".max", ".zip", ".7z", ".rar", ".tar", ".gz", ".unitypackage", ".dll", ".so", ".dylib",
          ".exe", ".bin", ".pdb", ".ttf", ".otf", ".woff", ".woff2", ".pdf", ".asset", ".bundle", ".pak", ".sqlite", ".db"}
MAX_FILE = 2 * 1024 * 1024
MAX_FILES = 20000
KEEP_CHECKPOINTS = 200


class Checkpoints:
    def __init__(self, folder):
        import hashlib  # noqa: PLC0415
        self.folder = Path(folder).resolve()
        self.store = CHECKPOINTS / hashlib.sha1(str(self.folder).encode()).hexdigest()[:16]

    def _files(self):
        """The project's files (relative paths): git's list when it is a repository (ignored files left out)."""
        root = self.folder
        if (root / ".git").exists() and git_usable():
            try:
                out = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                                     capture_output=True, timeout=60)
                if out.returncode == 0:
                    return [p for p in out.stdout.decode(errors="ignore").split("\0")
                            if p and not set(Path(p).parts) & HEAVY_DIRS and not notebook_path(p)][:MAX_FILES]
            except (OSError, subprocess.SubprocessError):
                pass
        rows = []
        for base, dirs, names in os.walk(root):
            dirs[:] = [d for d in dirs if d not in HEAVY_DIRS]
            for n in names:
                rel = os.path.relpath(os.path.join(base, n), root).replace(os.sep, "/")
                if notebook_path(rel):
                    continue
                rows.append(rel)
                if len(rows) >= MAX_FILES:
                    return rows
        return rows

    def _scan(self) -> dict:
        """{path: sha256} of the folder now; each new content kept in the store."""
        import hashlib  # noqa: PLC0415
        objects = self.store / "objects"
        cache_file = self.store / "cache.json"
        try:
            cache = json.loads(cache_file.read_text())
        except (OSError, ValueError):
            cache = {}
        out, fresh = {}, {}
        for rel in self._files():
            path = self.folder / rel
            try:
                st = path.stat()
            except OSError:
                continue
            if not path.is_file() or st.st_size > MAX_FILE or path.suffix.lower() in BINARY:
                continue
            key = [st.st_size, st.st_mtime_ns]
            known = cache.get(rel)
            if known and known[:2] == key and (objects / known[2][:2] / known[2]).exists():
                sha = known[2]
            else:
                try:
                    data = path.read_bytes()
                except OSError:
                    continue
                sha = hashlib.sha256(data).hexdigest()
                blob = objects / sha[:2] / sha
                if not blob.exists():
                    blob.parent.mkdir(parents=True, exist_ok=True)
                    tmp = blob.with_suffix(".tmp")
                    tmp.write_bytes(data)
                    tmp.replace(blob)
            out[rel] = sha
            fresh[rel] = key + [sha]
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(fresh))
        return out

    def _manifest(self, rev) -> dict:
        try:
            return json.loads((self.store / "manifests" / f"{rev}.json").read_text())
        except (OSError, ValueError):
            raise RuntimeError("unknown checkpoint")

    def snapshot(self, label="") -> str:
        """The folder now, as a checkpoint: its id."""
        files = self._scan()
        rev = f"{int(time.time() * 1000):x}"
        folder = self.store / "manifests"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{rev}.json").write_text(json.dumps(files))
        old = sorted(folder.glob("*.json"))[:-KEEP_CHECKPOINTS]
        for f in old:
            f.unlink(missing_ok=True)
        return rev

    @staticmethod
    def _lines(path: Path) -> int:
        try:
            data = path.read_bytes()
        except OSError:
            return 0
        return 0 if b"\0" in data[:8000] else data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)

    def changes(self, rev) -> list:
        """What changed in the folder since a checkpoint: [{path, status (A, M, D), added, removed}]."""
        import difflib  # noqa: PLC0415
        before, now = self._manifest(rev), self._scan()
        objects = self.store / "objects"
        out = []
        for path in sorted(set(before) | set(now)):
            a, b = before.get(path), now.get(path)
            if a == b:
                continue
            status = "A" if a is None else "D" if b is None else "M"
            added = removed = 0
            if status == "A":
                added = self._lines(objects / b[:2] / b)
            elif status == "D":
                removed = self._lines(objects / a[:2] / a)
            else:
                try:
                    old = (objects / a[:2] / a).read_bytes()
                    new = (objects / b[:2] / b).read_bytes()
                    if b"\0" not in old[:8000] + new[:8000]:
                        for line in difflib.unified_diff(old.decode(errors="replace").splitlines(), new.decode(errors="replace").splitlines(), n=0, lineterm=""):
                            if line.startswith("+") and not line.startswith("+++"):
                                added += 1
                            elif line.startswith("-") and not line.startswith("---"):
                                removed += 1
                except OSError:
                    pass
            out.append({"path": path, "status": status, "added": added, "removed": removed})
        return out

    def restore(self, rev) -> int:
        """The folder back as it was at a checkpoint (files changed, removed or added since): how many files moved.
        What it was just before is kept as a checkpoint too, so a restore can itself be undone."""
        before = self._manifest(rev)
        changed = self.changes(rev)
        if not changed:
            return 0
        self.snapshot("before restore")
        objects = self.store / "objects"
        for c in changed:
            target = self.folder / c["path"]
            if c["status"] == "A":                 # made since: removed
                try:
                    target.unlink()
                except OSError:
                    pass
                continue
            sha = before[c["path"]]
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                tmp = target.with_name(target.name + ".ornis-tmp")
                shutil.copyfile(objects / sha[:2] / sha, tmp)
                tmp.replace(target)
            except OSError:
                pass
        self._scan()
        return len(changed)

    def restore_file(self, rev, path) -> bool:
        """One file back as it was at a checkpoint (removed if it was made since): whether it moved."""
        before = self._manifest(rev)
        path = str(path)
        target = (self.folder / path).resolve()
        if self.folder.resolve() not in target.parents:          # never outside the project
            return False
        sha = before.get(path)
        try:
            if sha is None:
                if not target.exists():
                    return False
                target.unlink()
                return True
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(target.name + ".ornis-tmp")
            shutil.copyfile(self.store / "objects" / sha[:2] / sha, tmp)
            tmp.replace(target)
            return True
        except OSError:
            return False


def git_commit(folder, message, branch="") -> str:
    """Everything changed in the project committed (on a new branch first when one is named): "" or the problem."""
    folder = Path(folder)
    if not (folder / ".git").exists() or not git_usable():
        return "no git"
    run = lambda *args: subprocess.run(["git", "-C", str(folder), *args], capture_output=True, text=True, timeout=60)  # noqa: E731
    try:
        if branch:
            done = run("switch", "-c", branch)
            if done.returncode:
                return (done.stderr or done.stdout).strip()[:300]
        done = run("add", "-A")
        if done.returncode == 0:
            done = run("commit", "-m", message)
        return "" if done.returncode == 0 else (done.stderr or done.stdout).strip()[:300]
    except (OSError, subprocess.SubprocessError) as error:
        return str(error)[:300]
