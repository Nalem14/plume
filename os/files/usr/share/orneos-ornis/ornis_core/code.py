"""The « Code » mode of the Ornis window (and of its module in Plume): Ornis works in a folder of the computer.
The engine is ornis_code (Mistral Vibe over ACP, through the cloud's gateway, in the sandbox); here, what the view
shows: the conversations of each project (kept on this computer only), the items of the open one (messages, tool
cards with their diffs and output, the plan, the permissions to give), the mode and what the context weighs.
"""
import difflib
import hashlib
import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path

from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtCore import QAbstractListModel, QByteArray, QModelIndex, QObject, Property, Qt, QTimer, QUrl, Signal, Slot

import ornis_code
import system
from ornis_core.chat import _when

INDEX = ornis_code.ROOT / "sessions.json"
HISTORY = ornis_code.ROOT / "history.json"     # the messages sent, per folder (↑ in the box brings them back)
PASTED = ornis_code.ROOT / "pasted"            # images pasted in the box, until they are sent
# put before the message that replaces one taken back to be edited (hidden when replayed)
RETRACT_NOTE = ("[The user took back their previous message (its file changes, if any, were undone) and replaces it with this one: "
                "follow this one instead.]\n\n")
# put before the next message after « Annuler ces modifications »: the agent's idea of the files is old (hidden when replayed)
# Vibe's own commands that make no sense in Ornis (they need a Mistral account, show Mistral's policy, change the
# engine's setup or install unrelated agents): hidden from « / » and refused when typed. Skills stay (unknown names).
HIDDEN_COMMANDS = {"teleport", "data-retention", "leanstall", "unleanstall", "proxy-setup", "reload", "log", "mcp", "help",
                   "model", "config", "status", "clear", "exit", "quit", "login", "logout", "theme", "terminal-setup", "usage",
                   "feedback", "bug", "upgrade", "update", "vim", "init-config", "setup"}
# put before each message in Plan mode (hidden when replayed): Ornis looks, then proposes; decide("plan") refuses the rest
PLAN_NOTE = ("[Plan mode: read only. Explore the project (read, search, read-only commands), change nothing, then answer with "
             "a numbered plan: the changes you would make, file by file, and how you would check them; write it also to "
             ".ornis/plans/ (allowed in Plan mode). The user runs it afterwards.]\n\n")
# Ask mode (as the « Ask » of IDE assistants): Ornis answers about the project, reads what it needs, changes nothing and
# writes no plan; decide("plan") refuses every write
ASK_NOTE = ("[Ask mode: read only. Answer the question about the project: read, search and run read-only commands as "
            "needed, explain with file paths and short excerpts. Change nothing, write no plan file, do not offer to "
            "apply changes yourself.]\n\n")
UNDONE_NOTE = "[The user undid your last changes: the files are back as they were before that turn. Read them again before editing.]\n\n"
# The model stops half way (Codestral, 02/11: after each file, or with a tool call written as text): the turn goes
# on by itself, a few times per message, with a line that says so. The agent reads why, the user only the line.
CONTINUE_NOTE = "[Ornis: continue] "
CONTINUE_TEXT = {
    "plan": "Continue now with the next items of your plan, in this turn, until everything is done and verified. "
            "Stop only to ask a real question.",
    "tool": "You wrote a tool call as text instead of calling the tool: nothing was run. Call the tool now, then go on "
            "with your plan.",
}
MAX_CONTINUE = 3
TOOL_KEYS = {"command", "path", "file_path", "content", "old_string", "new_string", "todos", "pattern", "query", "url"}
MAX_DIFF = 400                     # lines of a diff shown on a card
MAX_DIFF_INPUT = 4000              # lines of a file past which the card shows counts only (difflib would block the window)
MAX_OUTPUT = 12000                 # characters of a command's output kept on its card
SKIP_DIRS = ornis_code.HEAVY_DIRS | {".vscode", "coverage"}     # generated folders (also Unity's Library, Temp…)
MAX_FILES = 20000                  # files listed for @ in a folder
MAX_ATTACH = 10
KINDS = {"read": "eye", "edit": "edit", "delete": "trash", "move": "move", "search": "search", "execute": "terminal",
         "think": "ornis", "fetch": "globe", "switch_mode": "list", "other": "sparkle"}



MENTION = re.compile(r'(?:^|\s)@(?:"([^"\n]+)"|([^\s@"]+))')


def mentioned(text: str) -> list[str]:
    """The paths named with @ in a message: @src/app.py, or @"A LIRE.txt" when the name has a space (as Claude Code)."""
    return [quoted or bare.rstrip(",;:!?)") for quoted, bare in MENTION.findall(text or "")]

class Items(QAbstractListModel):
    """The items of the open conversation, changed one row at a time (a whole new list would rebuild every card)."""
    KIND, ITEM = Qt.ItemDataRole.UserRole + 1, Qt.ItemDataRole.UserRole + 2

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows: list[dict] = []
        # while a conversation is replayed (thousands of pieces): rows change silently, the view is told once at the end
        self.quiet = False

    def roleNames(self):
        return {self.KIND: QByteArray(b"kind"), self.ITEM: QByteArray(b"item")}

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.rows):
            return None
        row = self.rows[index.row()]
        return row.get("kind") if role == self.KIND else dict(row) if role == self.ITEM else None

    def reset(self, rows=()):
        self.beginResetModel()
        self.rows = list(rows)
        self.endResetModel()

    def append(self, row: dict) -> int:
        if self.quiet:
            self.rows.append(row)
            return len(self.rows) - 1
        self.beginInsertRows(QModelIndex(), len(self.rows), len(self.rows))
        self.rows.append(row)
        self.endInsertRows()
        return len(self.rows) - 1

    def touch(self, at: int) -> None:
        if not self.quiet and 0 <= at < len(self.rows):
            index = self.index(at)
            self.dataChanged.emit(index, index, [self.ITEM])

    def find(self, key: str, value) -> int:
        for at in range(len(self.rows) - 1, -1, -1):
            if self.rows[at].get(key) == value:
                return at
        return -1


def _text(content) -> str:
    """The text of an ACP content block (or a list of them)."""
    if isinstance(content, list):
        return "".join(_text(c) for c in content)
    if isinstance(content, dict):
        if content.get("type") == "text":
            return str(content.get("text") or "")
        if "content" in content:
            return _text(content["content"])
    return ""


def tool_as_text(text: str) -> bool:
    """True when a reply is only a tool call written out ({"command": "…"}, maybe in a ```json block)."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else ""
        t = t.rsplit("```", 1)[0].strip()
    if not t.startswith("{") or len(t) > 8000:
        return False
    try:
        data = json.loads(t)
    except ValueError:
        return False
    return isinstance(data, dict) and bool(TOOL_KEYS & set(data))


def repeating(text: str) -> bool:
    """True when the end of a reply is the same passage again and again (a model stuck in a loop: seen 02/11, a
    plugin.json written thousands of times). Looked at once per 2 000 characters, past 8 000: the last 200 characters
    found 8 times or more in the last 12 000. Real code repeats lines, rarely 200 characters in a row so often."""
    n = len(text)
    if n < 8000:
        return False
    tail = text[-200:]
    return len(tail.strip()) >= 40 and text.count(tail, max(0, n - 12000)) >= 8


def diff_lines(path: str, old: str | None, new: str) -> list[dict]:
    """A unified diff as lines for the card: {t: '+'|'-'|' '|'@', s: text}."""
    old_lines = (old or "").splitlines()
    new_lines = (new or "").splitlines()
    if len(old_lines) + len(new_lines) > MAX_DIFF_INPUT:        # a whole big file: its first lines, never a slow diff
        if not old_lines:
            return [{"t": "+", "s": s} for s in new_lines[:MAX_DIFF]] + [{"t": "@", "s": "…"}]
        return [{"t": "@", "s": f"{len(old_lines)} → {len(new_lines)}"}]
    out = []
    for line in difflib.unified_diff(old_lines, new_lines, lineterm="", n=2):
        if line.startswith(("---", "+++")):
            continue
        out.append({"t": "@" if line.startswith("@@") else line[:1] or " ", "s": line[1:] if not line.startswith("@@") else line})
        if len(out) >= MAX_DIFF:
            out.append({"t": "@", "s": "…"})
            break
    return out


def _bot_turn_note(bot: str) -> str:
    """The hidden memory line of a bot's turn (ornis_bots.turn_note); never a reason for a turn to fail."""
    try:
        import ornis_bots  # noqa: PLC0415
        return ornis_bots.turn_note(bot, ornis_code.COMPACT_AT)
    except Exception:  # noqa: BLE001
        return ""


def _bot_usage(bot: str, used: int):
    try:
        import ornis_bots  # noqa: PLC0415
        ornis_bots.note_usage(bot, used)
    except Exception:  # noqa: BLE001
        pass


def _bot_record(bot: str, asked: str, answer: str):
    """A finished turn into the bot's searchable history (off the window's thread: a file append)."""
    if not bot:
        return

    def work():
        try:
            import ornis_bots  # noqa: PLC0415
            ornis_bots.record_turn(bot, asked, answer)
        except Exception:  # noqa: BLE001
            pass
    threading.Thread(target=work, daemon=True, name="ornis-bot-history").start()


def _group_title(text: str) -> str:
    """« [Group message in « Title » (group id …)] » → Title (the pill in the bot's own thread)."""
    m = re.match(r"\[Group message in « (.*?) »", str(text or ""))
    return m.group(1) if m else ""


class CodeChat(QObject):
    changed = Signal()             # folder, conversation, state, mode, sessions
    statusChanged = Signal()       # bot: its live status (« Orla écrit un fichier… »)
    usageChanged = Signal()
    planChanged = Signal()
    problem = Signal(str)          # a message for the toast
    laterChanged = Signal()        # the messages written while Ornis works (waiting above the box)
    laterReturned = Signal(str)    # « Modifier », or a stopped turn: back into the box
    finished = Signal(str)         # an answer is complete (title): the window may notify
    cronDone = Signal(str, str, str, str)  # task_id, status, summary, session — local Code cron finished here
    cronSession = Signal(str, str, str)    # task_id, folder, session — session id known (sidebar can open it live)
    cronReply = Signal(str, str)           # task_id, the turn's last answer (a bot's reply posted in its group)
    unreadMarkAt = Signal(int)             # a bot's « Non lu » bar was placed at this row: the view goes there
    _update = Signal(object, str, object)   # the agent that sent it, session, update
    _permission = Signal(object, str, object, object)
    _question = Signal(object, str, object)   # request id, session, questions (Vibe's ask_user_question)
    _exited = Signal(int, str)
    _ready = Signal(object, str)   # agent or None, problem
    _progress = Signal(int)
    _done = Signal(str, object)    # session, result or error text
    _checked = Signal(str, str)    # session, the checkpoint taken before the turn
    _changes = Signal(int, str, object)  # opening, checkpoint, what the turn changed in the folder
    _restored = Signal(str, int, str)    # checkpoint, files moved back, problem
    _git_seen = Signal(str, object)      # folder, {branch, dirty}
    _file_restored = Signal(str, str, bool)   # checkpoint, file, whether it moved
    _committed = Signal(str)             # "" or git's problem
    _host_done = Signal(object, object)
    _measured = Signal(str, object)      # session, the parts of its last request as the gateway measured them
    attachmentsChanged = Signal()  # the files joined to the message being written

    def __init__(self, app):
        super().__init__()
        self._app = app
        self._items = Items(self)
        self._agent: ornis_code.Agent | None = None
        self._folder = ""
        self._session = ""
        self._bot = ""             # durable Code bot id (ornis_bots); empty for ordinary project sessions
        self._bot_brief = False    # next user message should carry the bot identity block
        self._title = ""
        self._state = "idle"       # idle | installing | starting | ready | error
        self._error = ""
        self._progress_pc = -1
        self._busy = False
        self._usage = {}
        self._parts_epoch = 0
        self._parts_hold = False
        self._compacting = False
        self._dismissed_tips = set()
        self._parts = {}           # what the last request carried, part by part (the gateway's measure)
        self._host = None
        self._retry_ids = set()
        self._gateway = None       # {token, url} of the gateway, once the agent started
        self._plan = []
        self._mode = app.pref("code_mode") if app.pref("code_mode") in ornis_code.MODES else "ask"
        self._replaying = False
        self._queued = ""          # a message written while the agent was starting
        self._tools: dict[str, int] = {}
        self._failures: dict = {}
        self._commands: list[dict] = []          # the agent's own « / » commands (available_commands_update)
        self._looped = False
        self._repeats: dict = {}                 # the same call that succeeded, again and again (a loop too)
        self._asked = None                       # Vibe's questions waiting for the user: {id, questions}
        self._attachments: list[dict] = []
        self._file_list: list[str] = []
        self._file_list_for = ""
        self._pending_text: dict[int, list[str]] = {}   # pieces not yet on their card, joined once (not text + piece)
        self._turn_rev = ""                      # the checkpoint taken before the turn running (ornis_code.Checkpoints)
        self._tell_undone = False                # changes undone: the agent hears it with the next message
        self._plan_mode = self._ask_mode = False  # Plan: read only, then « Exécuter le plan » (as in Claude Code)
        self._opening = 0                        # +1 at each opening: late work of a previous one is dropped
        self._continued = 0                      # turns gone on by themselves since my last message
        self._turn_start = 0                     # the row where the turn running began
        self._turn_asked = ""
        self._later: list[str] = []              # messages written while Ornis works: sent one by one after the turn
        self._forced = None                      # « Envoyer maintenant »: sent once the stopped turn is over
        self._retract = False                    # the last message was taken back to be edited: the agent hears it
        self._git = {}
        self._cron_job = None            # {task_id, title, prev_mode} while a scheduled Code task runs here
        self._last_status = None         # bot: what its status bubble shows (_status_tick)
        self._bg_bots: dict[str, dict] = {}  # bot_id -> stashed live state while another conversation is viewed
        self._bot_starts: dict[str, int] = {}  # bot_id -> its latest agent start (see _start)
        self._unread_mark = 0                  # a bot opened with N answers not read: the bar goes before them
        self.changed.connect(self.statusChanged)   # busy, bot or name changed: the bubble is read again
        try:
            self._history = json.loads(HISTORY.read_text())
        except (OSError, ValueError):
            self._history = {}
        try:
            self._index = json.loads(INDEX.read_text())
        except (OSError, ValueError):
            self._index = {}
        if not isinstance(self._index, dict):
            self._index = {}
        self._flush = QTimer(self)       # streamed text is written to its card ~20 times a second, not per piece
        self._flush.setInterval(50)
        self._flush.setSingleShot(True)
        self._flush.timeout.connect(self._write_text)
        self._measure = QTimer(self)     # the parts are asked once a step is over, not at each usage update
        self._measure.setInterval(1000)
        self._measure.setSingleShot(True)
        self._measure.timeout.connect(self._fetch_parts)
        for signal, slot in ((self._update, self._on_update), (self._permission, self._on_permission), (self._question, self._on_question), (self._exited, self._on_exit),
                             (self._ready, self._on_ready), (self._progress, self._on_progress), (self._done, self._on_done),
                             (self._checked, self._on_checked), (self._changes, self._on_changes), (self._restored, self._on_restored),
                             (self._host_done, self._on_host_done), (self._git_seen, self._on_git), (self._measured, self._on_measured),
                             (self._file_restored, self._on_file_restored), (self._committed, self._on_committed)):
            signal.connect(slot, Qt.ConnectionType.QueuedConnection)
        self._account_key = tuple((app.account() or ())[:2])
        app.accountChanged.connect(self._account_changed)
        # the panel on the right of a session: files, changes, plan, terminals (bench.py, terminal.py)
        from ornis_core.bench import Bench  # noqa: PLC0415
        from ornis_core.terminal import Terminals  # noqa: PLC0415
        self._bench = Bench(self)
        self._terminals = Terminals(self)
        self.finished.connect(lambda *_: self._bench.refresh())

    # ---- what the view reads ---------------------------------------------------------------------------------------
    @Property(QObject, constant=True)
    def items(self):
        return self._items

    @Property(bool, constant=True)
    def supported(self):
        return ornis_code.supported()

    @Property(QObject, constant=True)
    def bench(self):
        return self._bench

    @Property(QObject, constant=True)
    def terminals(self):
        return self._terminals

    @Property(str, constant=True)
    def homeFolder(self):
        """A session without a chosen folder works in the personal folder (as Claude Code's « Cet ordinateur »)."""
        return str(Path.home())

    @Property(bool, notify=changed)
    def planReady(self):
        """A plan proposed in Plan mode and not run yet: « Exécuter le plan » (the card, the panel's Plan tab)."""
        return any(r.get("kind") == "planready" and not r.get("done") for r in self._items.rows)

    @Property(str, notify=changed)
    def folder(self):
        return self._folder

    @Property(str, notify=changed)
    def bot(self):
        """Durable bot id when this conversation is a Bot Chat; empty otherwise."""
        return self._bot

    @Property(str, notify=changed)
    def folderName(self):
        if self._bot:
            try:
                import ornis_bots  # noqa: PLC0415
                profile = ornis_bots.get(self._bot)
                if profile:
                    return profile.get("title") or self._bot
            except Exception:  # noqa: BLE001
                return self._bot
        return self._display_name(self._folder) if self._folder else ""

    def _display_name(self, folder: str) -> str:
        """The folder's name; the personal folder is « Dossier personnel »."""
        try:
            if Path(folder).resolve() == Path.home().resolve():
                return self._app._t.get("code_home", "Home")
        except OSError:
            pass
        return Path(folder).name or folder

    @Property(str, notify=changed)
    def session(self):
        return self._session

    @Property(str, notify=changed)
    def title(self):
        return self._title

    @Property(str, notify=changed)
    def state(self):
        return self._state

    @Property(str, notify=changed)
    def error(self):
        return self._error

    @Property(int, notify=changed)
    def progress(self):
        return self._progress_pc

    @Property(bool, notify=changed)
    def busy(self):
        return self._busy

    @Property(str, notify=changed)
    def mode(self):
        # Bots always run Autonome (no rights picker in the UI).
        return "auto" if self._bot else self._mode

    @Property(bool, notify=changed)
    def chatTyping(self):
        """Bot chat: the live status bubble above the box (never written into the history)."""
        return bool(self._bot and self._busy and not self._replaying)   # reading the thread again is no work

    @Property(str, notify=statusChanged)
    def botStatus(self):
        """What the open bot is doing right now: « Orla réfléchit… », « Orla écrit un fichier… », …"""
        if not self._bot or not self._busy:
            return ""
        name = self.folderName or self._bot
        key, detail = self._bot_activity()
        tip = self._app._t.get(f"bots_status_{key}", "")
        if not tip:
            tip = self._app._t.get("bots_status_working", "%1 travaille…")
        text = tip.replace("%1", name)
        if detail and "%2" in text:
            text = text.replace("%2", detail)
        elif "%2" in text:
            text = text.replace(" %2", "").replace("%2", "")
        return text

    def _status_tick(self):
        """Refresh the bot's status bubble only when what it does changes (not at each streamed word: `changed`
        re-reads every binding of the view)."""
        if not self._bot:
            return
        now = self._bot_activity() if self._busy else None
        if now != self._last_status:
            self._last_status = now
            self.statusChanged.emit()

    def _bot_activity(self) -> tuple[str, str]:
        """(status_key, optional short detail) from the latest thing the bot did in this turn."""
        for at in sorted(self._pending_text, reverse=True):     # words not flushed yet: the newest first
            if self._pending_text[at] and 0 <= at < len(self._items.rows):
                kind = self._items.rows[at].get("kind")
                if kind == "agent":
                    return "writing", ""
                if kind == "thought":
                    return "thinking", ""
        for row in reversed(self._items.rows):
            kind = row.get("kind")
            if kind in ("agent", "thought"):
                if not str(row.get("content") or "").strip():
                    continue
                return ("writing" if kind == "agent" else "thinking"), ""
            if kind == "tool":
                if str(row.get("status") or "pending") in ("completed", "failed", "cancelled"):
                    return "working", ""                 # between two steps: the next one is not known yet
                tool = str(row.get("tool") or "other")
                short = Path(str(row.get("short") or row.get("path") or "")).name.strip()
                if tool in ("edit", "delete", "move"):
                    return ("write_file_named", short) if short else ("write_file", "")
                if tool == "read":
                    return ("read_named", short) if short else ("read", "")
                if tool == "search":
                    return "search", ""
                if tool == "execute":
                    return "command", ""
                if tool == "fetch":
                    return "fetch", ""
                if tool == "think":
                    return "thinking", ""
                return "tool", ""
            if kind in ("user", "peer"):
                break
        return "working", ""

    @Property(str, constant=True)
    def sandbox(self):
        return ornis_code.sandbox_kind()

    @Property("QVariantMap", notify=usageChanged)
    def usage(self):
        return self._usage

    @Property("QVariantMap", notify=usageChanged)
    def context(self):
        """The same shape as chat.context, for the shared gauge (ContextGauge.qml): measured against the size past which
        the agent summarises its start by itself."""
        used = int(self._parts.get("tokens") or self._usage.get("used") or 0)
        limit = ornis_code.COMPACT_AT
        measured = {k: int(v or 0) for k, v in (self._parts.get("parts") or {}).items()}
        total = sum(measured.values())
        if not total:                                 # not measured yet (or an older cloud): one part
            measured, total = {"conversation": used}, used
        rows = []
        for key in ("conversation", "tool_results", "tools", "instructions"):
            tokens = round(measured.get(key, 0) * used / total) if total else 0
            if tokens > 0:
                rows.append({"key": key, "label": self._app._t.get("context_" + key, key), "tokens": tokens,
                             "percent": 100.0 * tokens / max(limit, used)})
        import ornis_context
        files = ornis_context.inventory(self._folder) if self._folder else []
        tips = ornis_context.tips(files, measured, getattr(self._app, "_lang", "fr"), self._dismissed_tips)
        return {"files": files, "tips": tips, "tokens": used, "limit": limit, "percent": min(100, round(used * 100 / limit)) if limit else 0,
                "parts": rows if used else []}

    def _fetch_parts(self):
        """The gateway measured the last request of this computer (system, tools, results, conversation: numbers only);
        Vibe itself only gives a total."""
        gateway, session = self._gateway, self._session
        epoch = self._parts_epoch
        if not gateway or not session or self._parts_hold:
            return

        def work():
            import urllib.request
            try:
                request = urllib.request.Request(gateway["url"].rstrip("/") + "/context",
                                                 headers={"Authorization": "Bearer " + gateway["token"]})
                with urllib.request.urlopen(request, timeout=10) as response:
                    data = json.loads(response.read().decode() or "{}")
                if isinstance(data, dict) and isinstance(data.get("parts"), dict):
                    data["epoch"] = epoch
                    self._measured.emit(session, data)
            except Exception:  # noqa: BLE001 -- the gauge keeps its single part
                pass
        threading.Thread(target=work, daemon=True, name="ornis-code-context").start()

    def _on_measured(self, session, data):
        if session == self._session and not self._parts_hold and data.get("epoch") == self._parts_epoch:
            self._parts = data
            self.usageChanged.emit()

    @Slot(str)
    def dismissTip(self, key):
        self._dismissed_tips.add(key)
        self.usageChanged.emit()

    def _invalidate_parts(self):
        self._parts_epoch += 1
        self._parts_hold = True
        self._measure.stop()
        old = self._parts.get("parts") or {}
        used = int(self._usage.get("used") or 0)
        fixed = {k: min(used, int(old.get(k) or 0)) for k in ("tools", "instructions")}
        scale = min(1, used / max(1, sum(fixed.values())))
        fixed = {k: round(v * scale) for k, v in fixed.items()}
        self._parts = {"parts": dict(fixed, tool_results=0, conversation=max(0, used - sum(fixed.values())))}
        self.usageChanged.emit()

    @Slot()
    def compact(self):
        """« /compact »: the agent summarises the start of the conversation now (Vibe's own command)."""
        if self._session and not self._busy:
            self.send("/compact")

    @Property("QVariantList", notify=planChanged)
    def plan(self):
        return self._plan

    @Property(bool, notify=changed)
    def waiting(self):
        """A permission waits for the user (the composer says so)."""
        return any(r.get("permission") for r in self._items.rows)

    @Property("QVariantMap", notify=changed)
    def asking(self):
        """The permission waiting for the user, shown above the message box as in the Discussion mode ({} when none):
        {row, tool, icon, title, command, path, diff, options: [{id, kind, label}]}."""
        at = next((i for i, r in enumerate(self._items.rows) if r.get("permission")), -1)
        if at < 0:
            return {}
        r = self._items.rows[at]
        return {"row": at, "tool": r.get("tool") or "", "icon": r.get("icon") or "sparkle", "title": r.get("title") or "",
                "command": r.get("command") or "", "path": r.get("path") or "", "diff": (r.get("diff") or [])[:400],
                "options": r["permission"].get("options") or [], "approvalTitle": r["permission"].get("title", "")}

    @Property("QVariantList", notify=changed)
    def questions(self):
        """Ornis's questions waiting above the message box (QuestionsDock, as in the Discussion mode), [] when none."""
        return list(self._asked["questions"]) if self._asked else []

    def _on_question(self, request_id, sid, questions):
        if sid != self._session or self._agent is None:
            bg = next((b for b in self._bg_bots.values() if b.get("session") == sid and b.get("agent") is not None), None)
            if bg and bg.get("agent"):
                bg["agent"].answer(request_id, {"action": "decline"})
            return
        if self._cron_job:                       # scheduled task: nobody is watching — decide alone
            self._agent.answer(request_id, {"action": "decline"})
            return
        if self._asked:                          # an older form left open: Vibe gets « decline » for it
            self._agent.answer(self._asked["id"], {"action": "decline"})
        self._write_text()
        self._asked = {"id": request_id, "questions": questions}
        self.changed.emit()
        if hasattr(self._app, "notify") and QGuiApplication.focusWindow() is None:
            try:
                self._app.notify(self._title or self.folderName, questions[0]["question"] if questions else "", "")
            except Exception:  # noqa: BLE001
                pass

    @Slot("QVariantList")
    def answerQuestions(self, answers):
        asked, self._asked = self._asked, None
        if asked and self._agent:
            self._agent.answer(asked["id"], ornis_code.elicitation_content(
                asked["questions"], list(answers or []), "No preference: decide yourself, and say what you chose."))
        self.changed.emit()

    @Slot()
    def skipQuestions(self):
        asked, self._asked = self._asked, None
        if asked and self._agent:
            self._agent.answer(asked["id"], {"action": "decline"})
        self.changed.emit()

    @Slot(str, result="QVariantList")
    def sessionsOf(self, folder):
        """The conversations of a project, most recent first: {id, title, when, updated}."""
        rows = sorted(self._index.get(str(folder), []), key=lambda s: (not s.get("pinned"), -float(s.get("updated") or 0)))
        return [dict(s, when=_when(float(s.get("updated") or 0), self._app.lang)) for s in rows if not s.get("bot")]

    @Property("QVariantList", notify=changed)
    def recent(self):
        """Every Code conversation, most recent first (the sidebar's lists).
        Cron-linked runs stay under the Cron section unless the user is searching.
        Bot chats stay in the Bots tab only."""
        out = []
        for folder, rows in self._index.items():
            for s in rows:
                if s.get("bot"):
                    continue
                out.append(dict(s, folder=folder, folderName=self._display_name(folder),
                                when=_when(float(s.get("updated") or 0), self._app.lang),
                                cron=str(s.get("cron") or "")))
        return sorted(out, key=lambda s: (not s.get("pinned"), -float(s.get("updated") or 0)))

    @Slot()
    def reloadIndex(self):
        """Re-read sessions.json (a cron run just wrote one)."""
        try:
            self._index = json.loads(INDEX.read_text())
        except (OSError, ValueError):
            self._index = {}
        self.changed.emit()

    @Property("QVariantList", notify=changed)
    def folders(self):
        """The Code tab's folders: where Ornis has worked (and the one open), most recent first."""
        last = {}
        for folder, rows in self._index.items():
            rows = [r for r in rows if not r.get("bot")]
            if not rows:
                continue
            last[folder] = max([float(r.get("updated") or 0) for r in rows] + [0])
        if self._folder and not self._bot and self._folder not in last:
            last[self._folder] = time.time()
        folded = self._app.pref("projects_folded") or []
        out = []
        for folder in sorted(last, key=lambda f: -last[f]):
            try:
                sub = "~/" + str(Path(folder).relative_to(Path.home()))
            except ValueError:
                sub = folder
            name = self._display_name(folder)
            out.append({"path": folder, "name": name, "sub": sub, "active": folder == self._folder, "initial": name[:1].upper() or "?",
                        "tone": sum(ord(ch) for ch in folder) % 6, "folded": folder in folded, "missing": not Path(folder).is_dir()})
        return out

    @Slot(result=str)
    def markdown(self):
        """The open conversation as Markdown (« Copier la conversation », « Exporter en Markdown »)."""
        t = self._app._t
        out = [f"# {self._title or self.folderName}", "", f"_{self._folder}_", ""]
        for r in self._items.rows:
            kind = r.get("kind")
            if kind == "user":
                out += [f"**{t.get('you', 'Vous')}**", "", r.get("content", ""), ""]
            elif kind == "agent" and r.get("content"):
                out += ["**Ornis**", "", r["content"], ""]
            elif kind == "tool":
                out.append(f"- `{r.get('command') or r.get('short') or r.get('title') or r.get('tool')}`")
            elif kind == "changes":
                out += ["", f"_{t.get('code_files_changed', '%1').split('|')[-1].replace('%1', str(r.get('count', 0)))}_", ""]
        return "\n".join(out).strip() + "\n"

    @Slot()
    def copyConversation(self):
        self._app.copy(self.markdown())
        self.problem.emit(self._app._t.get("copied", ""))

    @Slot(str)
    def exportTo(self, path):
        try:
            Path(path).write_text(self.markdown(), encoding="utf-8")
            self.problem.emit(self._app._t.get("code_exported", "").replace("%1", Path(path).name))
        except OSError:
            self.problem.emit(self._app._t.get("code_export_failed", ""))

    @Slot(str)
    def forgetFolder(self, folder):
        """« Retirer de la liste »: the folder and its conversations leave the list (nothing is deleted in the folder)."""
        if folder == self._folder:
            self.close()
        if self._index.pop(folder, None) is not None:
            self._save()
        self.changed.emit()

    # ---- files: @ in the message, files dropped or chosen, a terminal --------------------------------------------
    @Property("QVariantList", notify=attachmentsChanged)
    def attachments(self):
        return self._attachments

    @Slot("QVariantList")
    def addFiles(self, urls):
        """Files dropped on the view or chosen: joined to the next message (the agent reads them itself)."""
        known = {a["path"] for a in self._attachments}
        for url in urls or []:
            text = str(url.toString() if hasattr(url, "toString") else url)
            path = Path(text[7:] if text.startswith("file://") else text)
            try:
                path = path.resolve()
            except OSError:
                continue
            if path.exists() and str(path) not in known and len(self._attachments) < MAX_ATTACH:
                known.add(str(path))
                self._attachments.append({"path": str(path), "name": path.name, "dir": path.is_dir(),
                                          "short": self._short(path)})
        self.attachmentsChanged.emit()

    @Slot(int)
    def removeAttachment(self, index):
        if 0 <= index < len(self._attachments):
            del self._attachments[index]
            self.attachmentsChanged.emit()

    def _short(self, path: Path) -> str:
        try:
            return str(path.relative_to(self._folder)) if self._folder else str(path)
        except ValueError:
            return str(path)

    def _warm_files(self):
        """The folder's list, made in the background (a big project takes seconds: never on the window's thread)."""
        folder = self._folder
        if not folder or self._file_list_for == folder or getattr(self, "_warming", "") == folder:
            return
        self._warming = folder
        threading.Thread(target=lambda: self._list_files(folder), daemon=True, name="ornis-code-files").start()

    def _list_files(self, folder: str = "") -> list[str]:
        """The project's files, relative (git's list when it is a repository: what .gitignore leaves out stays out)."""
        folder = folder or self._folder
        if self._file_list_for == folder and self._file_list:
            return self._file_list
        files: list[str] = []
        root = Path(folder)
        try:
            if (root / ".git").exists() and ornis_code.git_usable():
                out = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"], cwd=root, capture_output=True, text=True,
                                     timeout=10, creationflags=subprocess.CREATE_NO_WINDOW if system.WINDOWS else 0)
                if out.returncode == 0:
                    files = [f for f in out.stdout.splitlines() if f and not set(Path(f).parts) & SKIP_DIRS][:MAX_FILES]
        except (OSError, subprocess.SubprocessError):
            files = []
        if not files:
            for base, dirs, names in os.walk(root):
                dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith("."))
                rel = Path(base).relative_to(root)
                files += [str(rel / n) if str(rel) != "." else n for n in sorted(names)]
                if len(files) >= MAX_FILES:
                    break
        if folder == self._folder:
            self._file_list, self._file_list_for = files[:MAX_FILES], folder
            self._warming = ""
        return files[:MAX_FILES]

    @Slot()
    def refreshFiles(self):
        self._file_list_for = ""
        self._warm_files()

    @Slot(str, result="QVariantList")
    def files(self, query):
        """@-suggestions: the project's files whose path matches what follows the @ (the name first, then the path)."""
        if not self._folder:
            return []
        q = str(query or "").lower().strip()
        if self._file_list_for != self._folder:            # still being listed: the suggestions come at the next key
            self._warm_files()
            return []
        rows = self._file_list
        if not q:
            return [{"path": f, "name": Path(f).name} for f in rows[:12]]
        named = [f for f in rows if q in Path(f).name.lower()]
        pathed = [f for f in rows if q in f.lower() and f not in named]
        named.sort(key=lambda f: (not Path(f).name.lower().startswith(q), len(f)))
        return [{"path": f, "name": Path(f).name} for f in (named + pathed)[:12]]

    def _tree(self, folder: str = "") -> str:
        """The first message of a conversation starts with the folder's files: the model looks there instead of guessing
        paths (seen 02/11: twelve reads of files that do not exist)."""
        folder = folder or self._folder
        rows = [r for r in self._list_files(folder) if not r.replace("\\", "/").startswith(ornis_code.ORNIS_DIR + "/")]
        if not rows:
            return "[The working folder is empty.]\n\n"
        shown = rows[:300]
        more = f"\n… and {len(rows) - len(shown)} more files" if len(rows) > len(shown) else ""
        return (f"[Files of the working folder {folder} (relative paths; read them from here, never guess a path):\n"
                + "\n".join(shown) + more + "]\n\n")

    @Slot(str, result="QVariantList")
    def commands(self, query):
        """« / »: what can be done at once (ours first, then the agent's own commands), filtered by what follows the /."""
        t = self._app._t
        q = str(query or "").lower().lstrip("/")
        ours = [("new", "/" + t.get("slash_new_cmd", "new"), t.get("slash_compact_sub" if self._bot else "slash_new_code_sub", ""), "compose"),
                ("compact", "/compact", t.get("slash_compact_sub", ""), "collapse"),
                ("terminal", "/terminal", t.get("slash_terminal_sub", ""), "terminal"),
                ("undo", "/" + t.get("code_undo_cmd", "undo"), t.get("code_undo_sub", ""), "restore")]
        ours += [("init", "/init", t.get("code_init_sub", ""), "note"),
                 ("remember", "/" + t.get("code_remember_cmd", "remember"), t.get("code_remember_sub", ""), "book"),
                 ("notebook", "/ornis", t.get("code_notebook_sub", ""), "folder")]
        ours += [("plan", "/plan", t.get("code_plan_sub", ""), "list"), ("ask", "/ask", t.get("code_ask_sub", ""), "chat"),
                 ("code", "/code", t.get("code_code_sub", ""), "code"),
                 ("goal", "/goal", t.get("code_goal_sub", ""), "flag"),
                 ("research", "/" + t.get("slash_research_cmd", "research"), t.get("code_research_sub", ""), "search")]
        if any(c["name"] == "retry" for c in self._commands):     # Vibe's, under our name
            ours.append(("retry", "/" + t.get("slash_retry_cmd", "retry"), t.get("slash_retry_sub", ""), "refresh"))
        if self._bot:                             # a bot stays Agent + Autonome: these would do nothing there
            ours = [o for o in ours if o[0] not in ("plan", "ask", "code", "goal", "research", "init")]
        items = [{"kind": k, "label": cmd, "sub": sub, "icon": ic, "value": cmd + " " if k == "remember" else ""}
                 for k, cmd, sub, ic in ours if not q or q in cmd[1:].lower() or q in sub.lower()]
        if self._folder:                          # the project's own commands (.ornis/commands/<name>.md), after ours
            for c in ornis_code.project_commands(self._folder):
                if not q or q in c["name"] or q in c["description"].lower():
                    items.append({"kind": "project", "label": "/" + c["name"], "icon": "list", "value": "/" + c["name"] + " ",
                                     "sub": c["description"] or t.get("code_project_cmd_sub", "")})
        taken = {i["label"][1:] for i in items} | {"compact", "new", "clear", "retry"}
        for c in self._commands:
            if c["name"] not in taken and (not q or q in c["name"].lower() or q in c["description"].lower()):
                items.append({"kind": "agent", "label": "/" + c["name"], "sub": c["description"][:90] or t.get("slash_agent_cmd_sub", ""),
                              "icon": "sparkle", "value": "/" + c["name"] + " "})
        return items[:16]

    @Slot()
    def openNotebook(self):
        """/ornis: the project's .ornis folder in the file manager (made first if this folder never had a conversation).
        QDesktopServices passes the activation token: a window already open comes to the front (links._qt_open)."""
        if not self._folder:
            return
        ornis_code.prepare_project(self._folder, getattr(self._app, "_lang", "fr"))
        if self._bot:
            import ornis_bots
            root = ornis_bots.bot_dir(self._bot)
        else:
            root = ornis_code.ornis_dir(self._folder)
        if root.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(root)))

    @Slot()
    def openTerminal(self):
        """A terminal of the computer in the project's folder (Konsole, Terminal, Windows Terminal…)."""
        if not self._folder:
            return
        folder = self._folder

        def work():
            try:
                import ornis_shell
                ornis_shell.in_terminal("", folder)
            except Exception as error:  # noqa: BLE001
                print("Ornis Code: terminal", error)
        threading.Thread(target=work, daemon=True).start()

    def _note(self, text: str) -> str:
        """What goes before the text for the agent (hidden in the bubbles): taken back, undone, Plan."""
        note = ""
        if self._retract and not text.startswith("/"):
            self._retract = False
            note += RETRACT_NOTE
        if self._tell_undone and not text.startswith("/"):
            self._tell_undone = False
            note += UNDONE_NOTE
        if self._plan_mode and not text.startswith("/"):
            note += PLAN_NOTE
        elif self._ask_mode and not text.startswith("/"):
            note += ASK_NOTE
        return note

    def _blocks(self, text: str, note: str, attachments: list, first: bool, folder: str) -> list[dict]:
        """The message for the agent: the text, then each file joined or named with @ (it reads them; an image is
        given as an image). Made off the window's thread: the folder's list and the images take time."""
        head = ""
        if first or self._bot_brief:
            if first:
                head += ornis_code.project_context(folder) + self._tree(folder)
            if self._bot:
                try:
                    import ornis_bots  # noqa: PLC0415
                    bots_cli = str((ornis_code.ROOT / "bin" / "ornis-bots").resolve())
                    head += ornis_bots.identity_block(self._bot, bots_cli=bots_cli)
                except Exception:  # noqa: BLE001
                    pass
            self._bot_brief = False
        if self._bot and not text.startswith("/"):
            head += _bot_turn_note(self._bot)    # keep memory as it goes; save it before a summary
        blocks = [ornis_code.text_block(note + head + text)]
        seen = set()
        for a in attachments:
            seen.add(a["path"])
            image = ornis_code.image_block(Path(a["path"])) if not a.get("dir") else None
            blocks.append(image or ornis_code.file_block(Path(a["path"])))
        for name in mentioned(text):
            path = (Path(folder) / name).resolve()
            if path.exists() and path.is_relative_to(Path(folder).resolve()) and str(path) not in seen:
                seen.add(str(path))
                blocks.append(ornis_code.file_block(path))
        return blocks

    # ---- conversations ---------------------------------------------------------------------------------------------
    def _stash_bot(self, next_bot: str = ""):
        """Keep a busy or queued bot running in the background when the user switches to another bot or conversation."""
        if not self._bot or self._bot == next_bot:
            return
        if not (self._busy or self._queued or self._later):
            return
        self._write_text()
        self._bg_bots[self._bot] = {
            "bot": self._bot,
            "folder": self._folder,
            "session": self._session,
            "title": self._title,
            "agent": self._agent,
            "state": self._state,
            "busy": self._busy,
            "replaying": self._replaying,
            "queued": self._queued,
            "later": list(self._later),
            "rows": list(self._items.rows),
            "tools": dict(self._tools),
            "plan": list(self._plan),
            "usage": dict(self._usage),
            "parts": dict(self._parts),
            "asked": self._asked,
            "cron_job": self._cron_job,
            "bot_brief": self._bot_brief,
            "start": getattr(self, "_starts", 0),
        }
        self._agent = None
        self._busy = False
        self._replaying = False
        self._queued = ""
        self._later = []
        self._asked = None
        self._cron_job = None

    def markUnread(self, count: int):
        """Called as a bot opens: its last `count` answers came while you were away (bots.Bots.open)."""
        self._unread_mark = max(0, int(count or 0))
        if self._unread_mark and not self._replaying and self._items.rows:
            self._place_unread_mark()

    def _place_unread_mark(self):
        """The « Non lu » bar before the bot's answers you have not seen (as Slack), and the view goes there."""
        n, self._unread_mark = self._unread_mark, 0
        if not n or not self._bot:
            return
        rows = self._items.rows
        answers = [i for i, r in enumerate(rows) if r.get("kind") == "agent" and str(r.get("content") or "").strip()]
        if not answers:
            return
        at = answers[-min(n, len(answers))]
        # the bar goes above the turn that produced it (its notice or the message that started it)
        while at > 0 and rows[at - 1].get("kind") in ("tool", "thought", "notice", "peer"):
            at -= 1
        self._items.rows[:] = [r for r in rows if r.get("kind") != "unreadmark"]
        self._items.rows.insert(at, {"kind": "unreadmark", "id": f"unread-{time.time()}"})
        self._items.reset(list(self._items.rows))
        self.unreadMarkAt.emit(at)

    def _restore_bot(self, bot_id: str) -> bool:
        bg = self._bg_bots.pop(bot_id, None)
        if bg is None:
            return False
        self._cancel_host()
        if self._agent is not None and self._agent is not bg.get("agent"):
            old_agent, self._agent = self._agent, None
            threading.Thread(target=old_agent.close, daemon=True).start()
        self._opening += 1
        self._bot = bg["bot"]
        self._bot_brief = bool(bg.get("bot_brief"))
        self._folder = bg["folder"]
        self._session = bg["session"]
        self._title = bg["title"]
        self._agent = bg["agent"]
        self._state = bg["state"]
        self._busy = bool(bg["busy"])
        self._replaying = bool(bg["replaying"])
        self._queued = str(bg.get("queued") or "")
        self._later = list(bg.get("later") or [])
        self._tools = dict(bg.get("tools") or {})
        self._plan = list(bg.get("plan") or [])
        self._usage = dict(bg.get("usage") or {})
        self._parts = dict(bg.get("parts") or {})
        self._asked = bg.get("asked")
        self._cron_job = bg.get("cron_job")
        self._mode = "auto"
        self._plan_mode = self._ask_mode = False
        self._pending_text.clear()
        self._failures, self._looped, self._repeats = {}, False, {}
        self._items.quiet = bool(self._replaying)
        self._items.reset(list(bg.get("rows") or []))
        if self._agent is None and self._state not in ("starting", "installing"):
            # no agent and none coming (it failed or was closed while away): open it again, what waited is kept
            queued, later = self._queued or (self._later[0] if self._later else ""), self._later[1:]
            self._busy = self._replaying = False
            self._open(self._folder, self._session)
            self._queued, self._later = queued, later
            self.laterChanged.emit()
            self.changed.emit()
            return True
        self.syncBotExchanges()
        self._refresh_git()
        self._warm_files()
        self._app.useWorkspace(self._folder) if hasattr(self._app, "useWorkspace") else None
        self.planChanged.emit()
        self.usageChanged.emit()
        self.laterChanged.emit()
        self.changed.emit()
        self._status_tick()
        return True

    def _close_bg_bot(self, bot_id: str):
        bg = self._bg_bots.pop(bot_id, None)
        if bg and bg.get("agent") is not None:
            agent = bg["agent"]
            threading.Thread(target=agent.close, daemon=True).start()

    @Slot(str)
    def newIn(self, folder):
        """A new conversation in a folder (the agent starts if it is not running there)."""
        self._stash_bot("")
        self._bot, self._bot_brief = "", False
        self._open(str(folder), "")

    @Slot(str, str)
    def open(self, folder, session_id):
        import ornis_bots
        # a new conversation ("" session) must never land in a bot that has not spoken yet
        profile = next((b for b in ornis_bots.list_bots() if session_id and b.get("session") == session_id), None)
        if profile:
            self.openBot(profile["id"], ornis_bots.working_folder(profile["id"]), session_id)
            return
        self._stash_bot("")
        self._bot, self._bot_brief = "", False
        self._open(str(folder), str(session_id))

    @Slot(str, str, str)
    def openBot(self, bot_id, folder, session_id):
        """Open a bot's durable chat (one conversation forever; /new becomes /compact)."""
        bot_id = str(bot_id or "").strip()
        cron = getattr(self, "_bot_cron", None)
        worker = getattr(self, "_bot_peer_worker", None)
        if ((cron and cron._chat_busy and getattr(cron, "_running_bot", "") == bot_id
             and not (cron._ui_run and cron._ui_run.get("bot") == bot_id))
                or (worker and worker.bot == bot_id and (worker.busy or worker._cron_job))):
            opening = self._opening
            QTimer.singleShot(500, lambda: self.openBot(bot_id, folder, session_id)
                              if self._opening == opening else None)
            return
        self._stash_bot(bot_id)
        if bot_id and bot_id in self._bg_bots:
            self._restore_bot(bot_id)
            return
        folder = str(folder or "").strip()
        session_id = str(session_id or "").strip()
        self._bot = bot_id
        self._bot_brief = True
        self._mode = "auto"                        # bots: Autonome, Agent classique (no Plan)
        self._plan_mode = self._ask_mode = False
        if bot_id:
            try:
                import ornis_bots  # noqa: PLC0415
                if not folder:
                    folder = ornis_bots.working_folder(bot_id)
                if not session_id:
                    session_id = str((ornis_bots.get(bot_id) or {}).get("session") or "")
            except Exception:  # noqa: BLE001
                pass
        self._open(folder, session_id)
        if bot_id:
            try:
                import ornis_bots  # noqa: PLC0415
                profile = ornis_bots.get(bot_id) or {}
                if profile.get("title"):
                    self._title = profile["title"]
                    self.changed.emit()
            except Exception:  # noqa: BLE001
                pass
            if self._agent and self._session and hasattr(self._agent, "set_mode"):
                agent, sid = self._agent, self._session
                threading.Thread(target=lambda: agent.set_mode(sid, "auto"), daemon=True).start()

    @Slot()
    def clearBot(self):
        self.shutdown()
        self._starts = getattr(self, "_starts", 0) + 1
        self._busy, self._queued, self._state = False, "", "idle"
        self._bot, self._bot_brief = "", False
        self._session, self._title, self._folder = "", "", ""
        pref = self._app.pref("code_mode")
        self._mode = pref if pref in ornis_code.MODES else "ask"
        self._plan_mode = self._ask_mode = False
        self._items.reset()
        self.changed.emit()

    def runScheduled(self, folder: str, title: str, prompt: str, task_id: str,
                     bot: str = "", session_id: str = "") -> bool:
        """Run a local Code cron task in this view so the user can watch it live. False if Code is busy.
        With `bot`, resumes that bot's durable session instead of opening a fresh conversation."""
        folder = str(Path(folder).expanduser().resolve()) if folder else ""
        if not folder or not Path(folder).is_dir() or not str(prompt or "").strip():
            return False
        if self._busy or self._cron_job or self._host is not None:
            return False
        # The user has a window in front with a conversation open: never swap it under them (the cron then runs
        # on its own agent, and opens from the list once done) — unless it is already that bot's chat idle.
        same_bot = bool(bot and self._bot == bot and self._session and (not session_id or self._session == session_id))
        if self._session and QGuiApplication.focusWindow() is not None and not same_bot and not getattr(self, "_background", False):
            return False
        self._cron_job = {
            "task_id": str(task_id or ""),
            "title": str(title or "").strip() or str(task_id or "cron"),
            "prev_mode": self._mode,
            "bot": str(bot or ""),
        }
        self._mode = "auto"
        self._plan_mode = self._ask_mode = False
        if bot:
            self.openBot(bot, folder, session_id or "")
        else:
            self._bot, self._bot_brief = "", False
            self._open(folder, "")
        if self._cron_job is None:  # synchronous start failure (offline or unsupported)
            return False
        self._title = self._cron_job["title"]
        self._queued = str(prompt)
        if self._state == "ready" and not self._busy:
            QTimer.singleShot(0, self._attach)
        if bot:
            self._bot_brief = True
        self.changed.emit()
        return True

    def _last_answer(self) -> str:
        """The text of this turn's last answer (empty when the bot only worked, or said [SILENT])."""
        rows = self._items.rows[max(0, self._turn_start):]
        last = next((r for r in reversed(rows) if r.get("kind") == "agent" and str(r.get("content") or "").strip()), None)
        text = str((last or {}).get("content") or "").strip()
        # « [SILENT] » alone: nothing to post; at the end of a real answer: the answer without the marker
        return text.replace("[SILENT]", "").strip()

    def _bot_preview(self):
        """The bots list shows what the bot said last (one line), as a messaging app."""
        text = " ".join(self._last_answer().split())
        if text:
            try:
                import ornis_bots  # noqa: PLC0415
                ornis_bots.update(self._bot, {"preview": text[:120]})
            except (ValueError, OSError):
                pass

    def _finish_cron(self, status: str, summary: str, session: str = ""):
        job, self._cron_job = self._cron_job, None
        if not job:
            return
        if status == "ok":
            self.cronReply.emit(str(job.get("task_id") or ""), self._last_answer())
        if job.get("prev_mode") in ornis_code.MODES:
            self._mode = job["prev_mode"]
        self.cronDone.emit(str(job.get("task_id") or ""), status, summary[:300], session or self._session or "")
        self.changed.emit()

    def _open(self, folder: str, session_id: str):
        folder = str(Path(folder).expanduser().resolve()) if folder else ""
        if (session_id and session_id == self._session and folder == self._folder and self._agent is not None
                and self._agent.alive()):
            # already the one shown (sidebar, Activité, the Code tab): nothing to cancel nor to replay; a replay
            # under a turn still streaming wrote its text twice
            self.changed.emit()
            return
        # A second agent cannot load a session still held by a background cron agent
        if session_id and self._busy and session_id == self._session:
            self.changed.emit()
            return
        self._cancel_host()
        self._opening += 1
        self._items.quiet = False
        if not folder or not Path(folder).is_dir():
            self.problem.emit(self._app._t.get("code_folder_missing", ""))
            return
        if self._busy and self._agent and self._session:
            # Interrupting a live cron run (user opened something else): close the task as stopped
            if self._cron_job and self._session and session_id != self._session:
                self._finish_cron("error", self._app._t.get("code_stopped", "Arrêté"), self._session)
            self._agent.cancel(self._session)
        self._items.reset()
        self._parts_epoch += 1
        self._parts_hold = False
        self._compacting = False
        self._dismissed_tips.clear()
        self._tools.clear()
        self._retry_ids.clear()
        self._pending_text.clear()
        self._plan, self._usage, self._parts = [], {}, {}
        self.planChanged.emit()
        self.usageChanged.emit()
        # « reading again » belongs to the conversation left: its end is ignored (another session), and kept True here
        # every message to the new one waited for ever, nothing was sent (09/11, a bot opened during a replay)
        self._session, self._title, self._busy, self._queued = session_id, "", False, ""
        self._replaying = False
        if folder != self._folder:
            self._attachments, self._file_list_for = [], ""
            self.attachmentsChanged.emit()
        if session_id:
            self._title = next((s.get("title", "") for s in self._index.get(folder, []) if s.get("id") == session_id), "")
        same = (self._agent is not None and self._agent.alive() and self._folder == folder
                and getattr(self._agent, "bot", "") == self._bot)
        self._folder = folder
        self._later, self._retract, self._git, self._forced = [], False, {}, None
        self.laterChanged.emit()
        self._refresh_git()
        self._warm_files()
        self._app.useWorkspace(folder) if hasattr(self._app, "useWorkspace") else None
        if same and self._state == "ready":
            self._attach()
        else:
            self._start()
        self.changed.emit()

    @Slot()
    def close(self):
        """Back to no conversation (the agent stays, for the next one of this folder)."""
        self._cancel_host()
        self._opening += 1
        self._items.quiet = False
        self._session, self._title = "", ""
        self._items.reset()
        self.changed.emit()

    @Slot(str, str)
    def forget(self, folder, session_id):
        """Removes a conversation from the list (its history stays in the agent's home until it is cleaned)."""
        rows = [s for s in self._index.get(folder, []) if s.get("id") != session_id]
        if rows:
            self._index[folder] = rows
        else:
            self._index.pop(folder, None)
        self._save()
        if session_id == self._session:
            self.close()
        self.changed.emit()

    @Slot(str, str, str)
    def rename(self, folder, session_id, title):
        for s in self._index.get(folder, []):
            if s.get("id") == session_id:
                s["title"], s["renamed"] = title.strip() or s.get("title", ""), True
        if session_id == self._session:
            self._title = title.strip() or self._title
        self._save()
        self.changed.emit()

    # ---- the agent -------------------------------------------------------------------------------------------------
    def _start(self):
        if self._agent is not None:
            agent, self._agent = self._agent, None
            threading.Thread(target=agent.close, daemon=True).start()
        account = self._app.account()
        if not account:
            self._fail("code_offline")
            return
        if not ornis_code.supported():
            self._fail("code_unsupported")
            return
        self._state = "installing" if ornis_code.binary() is None else "starting"
        self._error, self._progress_pc = "", -1
        self.changed.emit()
        folder, bot = self._folder, self._bot
        # one agent at a time: a start overtaken by another (two conversations opened quickly) is closed when ready;
        # two agents on the same conversation each wrote the answer, mixed in one bubble (« Je reprends… » twice, 05/11)
        self._starts = getattr(self, "_starts", 0) + 1
        start = self._starts
        if bot:
            self._bot_starts[bot] = start         # this bot's latest start, wherever it is shown when ready
        holder = []

        def work():
            try:
                exe = ornis_code.install(lambda done, total: self._progress.emit(int(done * 100 / total) if total else -1))
                creds = ornis_code.credentials(*account)
                self._gateway = {"token": creds["token"], "url": creds["url"]}
                ornis_code.prepare_project(folder, getattr(self._app, "_lang", "fr"))   # its skills/ for skill_paths
                ornis_code.write_home(creds["url"], getattr(self._app, "_lang", "fr"), folder,
                                      self._app.pref("code_reasoning") or "high", bot=bot)
                agent = ornis_code.Agent(exe, Path(folder), creds["token"],
                                         on_update=lambda sid, u: self._update.emit(holder[0] if holder else None, sid, u),
                                         on_permission=lambda rid, sid, tool, opts: self._permission.emit(rid, sid, tool, opts),
                                         on_exit=lambda code, err: self._exited.emit(code, err),
                                         on_question=lambda rid, sid, qs: self._question.emit(rid, sid, qs),
                                         gateway_url=str(creds.get("url") or ""), bot=bot)
                holder.append(agent)
                agent.start()
                # Overtaken by another start: closed — unless it is still the latest start of its bot. That bot may
                # have been put in the background and brought back meanwhile (09/11: the agent was closed, the bot
                # stayed « travaille… » for ever with its message waiting); _on_ready places it or closes it.
                if not self._start_current(start, bot):
                    agent.close()
                    return
                self._ready.emit(agent, "")
            except ornis_code.Unavailable as error:
                self._ready.emit(None, f"code_{error.args[0] if error.args else 'failed'}")
            except Exception as error:  # noqa: BLE001
                print("Ornis Code:", type(error).__name__, error)
                self._ready.emit(None, "code_failed")
        threading.Thread(target=work, daemon=True, name="ornis-code-start").start()

    def _on_progress(self, pc):
        self._progress_pc = pc
        if self._state == "installing":
            self.changed.emit()

    def _start_current(self, start: int, bot: str = "") -> bool:
        """Whether an agent start is still wanted: the latest one, or the latest one of its bot."""
        return start == self._starts or bool(bot and self._bot_starts.get(bot) == start)

    def _on_ready(self, agent, problem):
        if agent is None:
            self._fail(problem)
            return
        bot = getattr(agent, "bot", "") or ""
        if bot and bot in self._bg_bots and self._bot != bot:
            bg = self._bg_bots[bot]
            if bg.get("agent") is not None and bg["agent"] is not agent:    # it has one already: never two
                threading.Thread(target=agent.close, daemon=True).start()
                return
            bg["agent"] = agent
            bg["state"] = "ready"
            self._bg_attach(bg)
            self.changed.emit()
            return
        if self._folder != str(agent.folder) or bot != self._bot or self._agent is not None:   # another folder, or another agent, meanwhile
            if agent is not self._agent:
                threading.Thread(target=agent.close, daemon=True).start()
            return
        self._agent, self._state = agent, "ready"
        self._attach()
        self.changed.emit()

    def _bg_attach(self, bg: dict):
        agent, sid, bot = bg.get("agent"), bg.get("session") or "", bg.get("bot") or ""
        if not agent:
            return
        if not sid:
            if bg.get("queued") or bg.get("later"):
                text = bg["queued"] if bg.get("queued") else bg["later"].pop(0)
                bg["queued"] = ""
                self._bg_send(bg, text)
            else:
                self._close_bg_bot(bot)
            return
        bg["busy"] = True
        bg["replaying"] = True

        def work():
            try:
                agent.load_session(sid)
                agent.set_mode(sid, "auto")
                self._done.emit(sid, {"loaded": True, "_bot": bot})
            except Exception as error:  # noqa: BLE001
                self._done.emit(sid, {"error": str(error), "loaded": True, "_bot": bot})
        threading.Thread(target=work, daemon=True).start()

    def _bg_send(self, bg: dict, shown: str):
        agent = bg.get("agent")
        bot = str(bg.get("bot") or "")
        folder = str(bg.get("folder") or "")
        sid = str(bg.get("session") or "")
        if not agent or not shown:
            return
        text = shown
        rows = bg.setdefault("rows", [])
        if not (rows and rows[-1].get("kind") == "user" and rows[-1].get("content") == shown):
            rows.append({"kind": "user", "role": "human", "content": shown, "id": f"local-{time.time()}"})
        bg["busy"] = True
        first = not sid and not text.startswith("/")
        brief = bool(bg.get("bot_brief"))
        bg["bot_brief"] = False

        def work():
            session = sid
            if first:
                ornis_code.prepare_project(folder, getattr(self._app, "_lang", "fr"))
            try:
                head = ""
                if first:
                    head += ornis_code.project_context(folder) + self._tree(folder)
                if bot and (first or brief):
                    try:
                        import ornis_bots  # noqa: PLC0415
                        bots_cli = str((ornis_code.ROOT / "bin" / "ornis-bots").resolve())
                        head += ornis_bots.identity_block(bot, bots_cli=bots_cli)
                    except Exception:  # noqa: BLE001
                        pass
                if bot and not text.startswith("/"):
                    head += _bot_turn_note(bot)
                blocks = [ornis_code.text_block(head + text)]
                if not session:
                    created = agent.new_session()
                    session = created.get("sessionId", "")
                    self._done.emit(session, {"created": True, "_bot": bot})
                    agent.set_mode(session, "auto")
                result = agent.prompt(session, blocks)
                self._done.emit(session, dict(result or {}, _bot=bot))
            except Exception as error:  # noqa: BLE001
                self._done.emit(session, {"error": str(error), "_bot": bot})
        threading.Thread(target=work, daemon=True, name="ornis-code-bg-prompt").start()

    def _attach(self):
        """Opens the conversation on the agent: an existing one (replayed) or a new one when the first message goes."""
        agent, sid, bot = self._agent, self._session, self._bot
        if not sid:
            if self._queued:
                text, self._queued = self._queued, ""
                self.send(text)
            elif self._later:
                text = self._later.pop(0)
                self.laterChanged.emit()
                self.send(text)
            return
        self._busy = True
        self._replaying = True
        self._items.quiet = True                 # drawn once, at the end (a long conversation froze the window)
        self.changed.emit()

        def work():
            try:
                agent.load_session(sid)
                agent.set_mode(sid, "auto" if bot else self._mode)
                self._done.emit(sid, {"loaded": True, "_bot": bot})
            except Exception as error:  # noqa: BLE001
                self._done.emit(sid, {"error": str(error), "loaded": True, "_bot": bot})
        threading.Thread(target=work, daemon=True).start()

    def _fail(self, problem):
        self._state, self._error, self._busy = "error", problem, False
        if self._cron_job:                       # the agent never came: the scheduled run ends here, not never
            self._queued = ""
            self._finish_cron("error", self._app._t.get(problem) or self._app._t.get("cron_failed", "Échec"),
                              self._session)
        self.changed.emit()

    def _on_exit(self, code, stderr):
        if self._agent is not None and not self._agent.alive():
            self._cancel_host()
            self._agent = None
            if self._busy:
                self._add_error("code_crashed")
            self._busy = False
            self._state = "idle"
            if self._cron_job:
                self._queued = ""
                self._finish_cron("error", self._app._t.get("code_crashed") or self._app._t.get("cron_failed", "Échec"),
                                  self._session)
            self.changed.emit()

    @Slot()
    def retry(self):
        if self._folder:
            if self._error == "code_token" and self._app.account():
                ornis_code.forget(*self._app.account()[:2])
            self._start()

    def _account_changed(self):
        key = tuple((self._app.account() or ())[:2])
        if key == self._account_key:             # the same account (its name or picture arrived)
            return
        self._cancel_host()
        self._account_key = key
        if self._cron_job:
            self._queued = ""
            self._finish_cron("error", self._app._t.get("code_stopped", "Arrêté"), self._session)
        if self._agent is not None:
            agent, self._agent = self._agent, None
            threading.Thread(target=agent.close, daemon=True).start()
        for bid in list(self._bg_bots):
            self._close_bg_bot(bid)
        self._state, self._session, self._folder = "idle", "", ""
        self._items.reset()
        self.changed.emit()

    # ---- sending -------------------------------------------------------------------------------------------------------
    def _expand(self, text: str) -> str:
        """/retenir … and the project's commands (.ornis/commands): the text the agent receives instead."""
        if not text.startswith("/") or len(text) < 2:
            return text
        word, _, args = text[1:].partition(" ")
        word = word.lower()
        t = self._app._t
        if word in ("remember", str(t.get("code_remember_cmd", "remember")).lower()):
            what = args.strip()
            if self._bot:
                import ornis_bots
                return (f"Update your own memory under {ornis_bots.bot_dir(self._bot) / 'memory'}: "
                        + (what or "save the useful lessons of this conversation, never secrets."))
            if not what:                          # alone: what this conversation taught, as Claude Code's memory
                return str(t.get("code_remember_all_text", "Save in the project's memory (.ornis/memory) what matters from this conversation."))
            return str(t.get("code_remember_text", "Remember this in the project's memory (.ornis/memory): %1")).replace("%1", what)
        if self._folder:                          # the project's own command wins over the agent's of that name
            return ornis_code.expand_command(self._folder, word, args) or text
        return text

    @Slot(str)
    def send(self, text):
        text = str(text or "").strip()
        if not text:
            return
        if self._bot and not text.startswith(("[Bot message from", "[Scheduled Code task:", "[Group message in")):
            import ornis_bots
            ornis_bots.update(self._bot, {"peer_depth": 0, "group_depth": 0, "human_turn": time.time()})
        shown, text = text, self._expand(text)    # the bubble keeps what the user wrote
        # A bot's durable chat: /new and /reset compact instead of forking
        if self._bot:
            word0 = shown[1:].split(None, 1)[0].lower() if shown.startswith("/") and len(shown) > 1 else ""
            if word0 in ("new", "reset", "nouveau", "neu"):
                shown, text = "/compact", "/compact"
        if (self._busy and not self._replaying) and (not shown.startswith("/") or text != shown):
            self._later.append(shown)                # sent after this turn, as in Claude Code (shown above the box)
            self._remember_prompt(shown)
            self.laterChanged.emit()
            return
        if text.lower() in ("/undo", "/" + str(self._app._t.get("code_undo_cmd", "undo")).lower()):
            self.undoLast()                      # ours, not the agent's
            return
        word = text[1:].split(None, 1)[0].lower() if text.startswith("/") and len(text) > 1 else ""
        if word in HIDDEN_COMMANDS:
            self.problem.emit(self._app._t.get("code_command_unknown", "").replace("%1", "/" + word))
            return
        retry = "/" + str(self._app._t.get("slash_retry_cmd", "retry")).lower()
        if text.lower() == retry or text.lower().startswith(retry + " "):
            text = "/retry" + text[len(retry):]  # Vibe's command, under our name
        if self._state != "ready" or self._agent is None or self._replaying:
            if self._replaying and self._queued:
                self._later.append(shown)
                self.laterChanged.emit()
            else:
                self._queued = shown                 # sent as soon as the agent is there (after a replay, if any)
            if not text.startswith("/") or text != shown:
                self._remember_prompt(shown)
            if not self._session:
                self._items.append({"kind": "user", "role": "human", "content": shown, "id": f"local-{time.time()}"})
            if self._state in ("idle", "error") and self._folder:
                self._start()
            return
        if self._busy:
            return
        if not text.startswith("/") or text != shown:
            self._remember_prompt(shown)
        agent = self._agent
        if not (self._items.rows and self._items.rows[-1].get("kind") == "user" and self._items.rows[-1].get("content") in (text, shown)):
            self._items.append({"kind": "user", "role": "human", "content": shown, "id": f"local-{time.time()}"})
        if (self._plan_mode or self._ask_mode) and not self._bot and not text.startswith("/"):
            self._items.rows[-1]["plan" if self._plan_mode else "askMode"] = True
            self._items.touch(len(self._items.rows) - 1)
        self._compacting = text == "/compact"
        if self._compacting:
            self._invalidate_parts()
        else:
            self._parts_hold = False
        if self._bot and shown.startswith("[Bot message from"):
            self._items.rows[-1].update(kind="notice", key="bots_silent", content="")
            self._items.touch(len(self._items.rows) - 1)
        elif self._bot and shown.startswith("[Group message in"):
            self._items.rows[-1].update(kind="notice", key="bots_group_turn", content=_group_title(shown))
            self._items.touch(len(self._items.rows) - 1)
        self._busy = True
        self._failures, self._looped, self._repeats = {}, False, {}
        self._continued, self._turn_start = 0, len(self._items.rows) - 1
        self._turn_asked = shown                 # the bot's history keeps what was asked (a routine, a group…)
        if self._plan and all(p.get("status") == "completed" for p in self._plan):
            self._plan = []                      # a finished to-do list is the last turn's, not this one's
            self.planChanged.emit()
        self.changed.emit()
        sid = self._session
        mode = "auto" if self._bot else self._mode
        note = self._note(text)
        attachments = list(self._attachments)
        first = not self._session and not text.startswith("/")
        files = [{"name": a["name"], "path": a["path"], "kind": "file"} for a in self._attachments]
        for name in mentioned(text):          # the files named with @ show on the message too
            try:
                path = (Path(self._folder) / name).resolve()
            except OSError:
                continue
            if path.exists() and path.is_relative_to(Path(self._folder).resolve()) and str(path) not in [f["path"] for f in files]:
                files.append({"name": name, "path": str(path), "kind": "file"})
        if files:                             # a click opens it in the panel on the right (CodeView.openInBench)
            self._items.rows[-1]["files"] = files
            self._items.touch(len(self._items.rows) - 1)
        self._attachments = []
        self.attachmentsChanged.emit()

        folder = self._folder
        bot = self._bot
        self._turn_rev = ""

        def work():
            session = sid
            if first:                         # the project's .ornis folder, made once (Ornis's memory, plans, tmp…),
                ornis_code.prepare_project(folder, getattr(self._app, "_lang", "fr"))   # before the checkpoint
            try:                              # the folder as it is now: « Annuler » brings it back after the turn
                rev = ornis_code.Checkpoints(folder).snapshot(text[:120])
                self._checked.emit(sid, rev)
            except Exception:  # noqa: BLE001 - a turn without checkpoint is still a turn
                pass
            try:
                blocks = self._blocks(text, note, attachments, first, folder)
                if not session:
                    created = agent.new_session()
                    session = created.get("sessionId", "")
                    self._done.emit(session, {"created": True, "_bot": bot})
                    agent.set_mode(session, mode)
                result = agent.prompt(session, blocks)
                self._done.emit(session, dict(result or {}, _bot=bot))
            except Exception as error:  # noqa: BLE001
                self._done.emit(session, {"error": str(error), "_bot": bot})
        threading.Thread(target=work, daemon=True, name="ornis-code-prompt").start()

    def _on_done(self, session, result):
        result = result if isinstance(result, dict) else {}
        bot_id = str(result.get("_bot") or "")
        bg = self._bg_bots.get(bot_id) if (bot_id and bot_id != self._bot) else None
        if bg is None and session != self._session:
            bg = next((b for b in self._bg_bots.values() if b.get("session") == session), None)
        if bg is not None:
            if result.get("created"):
                bg["session"] = session
                self._remember_for(bg["folder"], session, bg.get("title") or "", bg["bot"], touch=True)
                self.changed.emit()
                return
            if result.get("loaded"):
                bg["replaying"] = False
                bg["busy"] = False
                if not result.get("error") and (bg.get("queued") or bg.get("later")):
                    text = bg["queued"] if bg.get("queued") else bg["later"].pop(0)
                    bg["queued"] = ""
                    self._bg_send(bg, text)
                else:
                    self._close_bg_bot(bg["bot"])
                self.changed.emit()
                return
            bg["busy"] = False
            if not result.get("error"):
                rows = bg.get("rows") or []
                ask_at = next((i for i in range(len(rows) - 1, -1, -1) if rows[i].get("kind") == "user"), -1)
                answer = next((str(r.get("content") or "") for r in reversed(rows[ask_at + 1:])
                               if r.get("kind") == "agent" and str(r.get("content") or "").strip()), "")
                _bot_record(bg["bot"], str(rows[ask_at].get("content") or "") if ask_at >= 0 else "", answer)
            self._remember_for(bg["folder"], bg.get("session") or session, bg.get("title") or "", bg["bot"], touch=True)
            if bg.get("later") and not result.get("error"):
                text = bg["later"].pop(0)
                self._bg_send(bg, text)
            else:
                self._close_bg_bot(bg["bot"])
            self.changed.emit()
            return
        if result.get("created"):
            self._session = session
            title = self._title or ""
            self._remember(session, title)
            if self._cron_job:
                self.cronSession.emit(str(self._cron_job.get("task_id") or ""), self._folder, session)
            self.changed.emit()
            return
        if session != self._session:
            return
        if result.get("loaded"):
            self._replaying = False
            self._write_text()
            self._items.quiet = False
            self._items.reset(list(self._items.rows))
            self.syncBotExchanges()
            if self._unread_mark and not result.get("error"):
                self._place_unread_mark()
            self._busy = False
            if result.get("error"):
                self._add_error("code_lost")
                self._queued = ""
                if self._cron_job:
                    self._finish_cron("error", self._app._t.get("code_lost", ""), self._session)
            if self._cron_job and not result.get("error"):
                self.cronSession.emit(str(self._cron_job.get("task_id") or ""), self._folder, session)
            self.changed.emit()
            if self._queued:
                text, self._queued = self._queued, ""
                self.send(text)
            elif self._later:
                text = self._later.pop(0)
                self.laterChanged.emit()
                self.send(text)
            return
        if self._host is not None:
            self._host["drained"] = True
            if self._host["cancel"].is_set():
                self._host = None
            else:
                self._launch_host()
                return
        if self._compacting:
            self._invalidate_parts()
            self._compacting = False
            if self._bot:
                self._bot_brief = True           # next turn re-reads SOUL / memory after a compact
        self._write_text()
        self._busy = False
        for row in self._items.rows:         # what was still asked for is moot now
            row.pop("permission", None)
        self._asked = None
        error = str(result.get("error") or "")
        if self._forced is not None and ("cancel" in error.lower() or result.get("stopReason") == "cancelled"):
            error, result = "", dict(result, stopReason="end_turn")      # stopped for the next message: no « Arrêté »
        if error:
            low = error.lower()
            self._add_error("code_plus_text" if "plan_required" in low else
                            "code_quota" if "402" in low or "quota" in low else
                            "code_busy" if "rate limit" in low or "503" in low or "429" in low or "408" in low or "timeout" in low else
                            "code_stopped" if "cancel" in low else "code_error", error)
        elif result.get("stopReason") == "cancelled":
            repeat_key = "bots_looped_repeat" if self._bot else "code_looped_repeat"
            self._add_error({"text": "code_looped_text", "repeat": repeat_key}.get(self._looped) or
                            ("code_looped" if self._looped else "code_stopped"))
        why = self._why_continue(error, result)
        if why:
            self._remember(self._session, self._title)
            self._continue(why)                  # the same turn for « Annuler »: its checkpoint stays
            return
        self._remember(self._session, self._title)
        if self._bot and not error:
            self._bot_preview()
            _bot_record(self._bot, self._turn_asked, self._last_answer())
        if self._plan_mode and not error and result.get("stopReason") != "cancelled":
            self._items.append({"kind": "planready", "done": False})
        self.changed.emit()
        self._turn_changes()
        self._refresh_git()
        # a scheduled turn (routine, a message from a bot, a group turn) ends here, BEFORE what the person wrote
        # meanwhile goes: otherwise its job stayed open and the answer to that private message was taken as the
        # group's answer (09/11)
        if self._cron_job:
            status = "error" if error or result.get("stopReason") == "cancelled" else "ok"
            if status == "error":
                base_err = self._app._t.get("cron_failed", "Échec")
                summary = f"{base_err} — {error}"[:300] if error else base_err
            else:
                summary = self._app._t.get("cron_done", "Terminé")
            self._finish_cron(status, summary, session)
            if self._forced is None and not self._later:
                return                           # else: what waits goes now, or back into the box on an error
        if self._forced is not None:             # « Envoyer maintenant »: the turn was stopped for it
            text, self._forced = self._forced, None
            QTimer.singleShot(0, lambda: self.send(text))
            return
        if self._later and not error:            # what was written meanwhile goes now
            text = self._later.pop(0)
            self.laterChanged.emit()
            QTimer.singleShot(0, lambda: self.send(text))
            return
        if error and self._later:                # stopped or refused: what waited goes back into the box, not sent
            text, self._later = "\n\n".join(self._later), []
            self.laterChanged.emit()
            self.laterReturned.emit(text)
        if not error:
            self.finished.emit(self._title or self.folderName)

    def _why_continue(self, error, result) -> str:
        """Why the turn should go on by itself ('' when it is really over)."""
        if (error or self._forced is not None or result.get("stopReason") not in (None, "end_turn") or self._plan_mode or self._ask_mode or self._later
                or self._continued >= MAX_CONTINUE or not self._agent or not self._session):
            return ""
        rows = self._items.rows[max(0, self._turn_start):]
        last = next((r for r in reversed(rows) if r.get("kind") == "agent"), None)
        text = str((last or {}).get("content") or "").strip()
        if text and tool_as_text(text):
            return "tool"
        tools = [r for r in rows if r.get("kind") == "tool"]
        if any(r.get("status") == "failed" or r.get("answer") for r in tools):
            return ""                            # a step refused or failed: Ornis says so, the user decides
        pending = any(p.get("status") in ("pending", "in_progress") for p in self._plan)
        if pending and tools and not text.endswith("?"):
            return "plan"
        return ""

    def _continue(self, why: str):
        self._continued += 1
        self._items.append({"kind": "notice", "key": "code_continued_" + why, "id": f"notice-{time.time()}"})
        self._busy = True
        self.changed.emit()
        agent, sid, bot = self._agent, self._session, self._bot

        def work():
            try:
                res = agent.prompt(sid, [{"type": "text", "text": CONTINUE_NOTE + CONTINUE_TEXT[why]}])
                self._done.emit(sid, dict(res or {}, _bot=bot))
            except Exception as error:  # noqa: BLE001
                self._done.emit(sid, {"error": str(error), "_bot": bot})
        threading.Thread(target=work, daemon=True, name="ornis-code-continue").start()

    @Slot()
    def stop(self):
        host = self._host
        self._cancel_host()
        if host and not host["drained"]:
            self._host = host
            self._busy = True  # wait for ACP cancellation before accepting another prompt
            self.changed.emit()
        if self._agent and self._session and self._busy:
            self._agent.cancel(self._session)

    # ---- written while Ornis works: waiting above the box (QueueDock), as in the Chat mode ----------------------
    @Property("QVariantList", notify=laterChanged)
    def later(self):
        return list(self._later)

    @Slot(int)
    def dropLater(self, index):
        if 0 <= index < len(self._later):
            del self._later[index]
            self.laterChanged.emit()

    @Slot(int)
    def editLater(self, index):
        """« Modifier »: out of the queue, back into the box."""
        if 0 <= index < len(self._later):
            text = self._later.pop(index)
            self.laterChanged.emit()
            self.laterReturned.emit(text)

    @Slot(int)
    def sendLaterNow(self, index):
        """« Envoyer maintenant »: the turn stops (its changes stay, « Annuler » still undoes them), this one goes next."""
        if not 0 <= index < len(self._later):
            return
        text = self._later.pop(index)
        self.laterChanged.emit()
        if self._busy and self._agent and self._session:
            self._forced = text
            self.stop()
        else:
            self.send(text)

    @Slot(str)
    def setMode(self, mode):
        if self._bot:
            return                                 # bots stay Autonome; do not rewrite the session prefs
        if self._busy or mode not in ornis_code.MODES or mode == self._mode:
            return
        self._mode = mode
        self._app.setPref("code_mode", mode)
        if self._agent and self._session:
            agent, sid = self._agent, self._session
            threading.Thread(target=lambda: agent.set_mode(sid, mode), daemon=True).start()
        self.changed.emit()

    @Property(bool, notify=changed)
    def planMode(self):
        return False if self._bot else self._plan_mode

    @Property(bool, notify=changed)
    def replaying(self):
        """A conversation being read again (its rows come at the end): « Chargement… », never an empty welcome."""
        return bool(self._replaying)

    @Property(str, notify=changed)
    def agentMode(self):
        """The mode chip: « agent » (edits and runs), « plan » (read only, then a plan) or « ask » (read only, answers)."""
        if self._bot:
            return "agent"
        return "plan" if self._plan_mode else "ask" if self._ask_mode else "agent"

    @Slot(str)
    def setAgentMode(self, mode):
        if self._bot or self._busy or mode not in ("agent", "plan", "ask") or mode == self.agentMode:
            return
        if mode == "plan":
            self._ask_mode = False
            self.setPlanMode(True)
            return
        if self._plan_mode:
            self.setPlanMode(False)
        self._ask_mode = mode == "ask"
        if self._agent and self._session:          # read only: Vibe asks for each edit, decide("plan") refuses it
            agent, sid, m = self._agent, self._session, "ask" if self._ask_mode else self._mode
            threading.Thread(target=lambda: agent.set_mode(sid, m), daemon=True).start()
        self.changed.emit()

    @Slot(bool)
    def setPlanMode(self, on):
        """Plan: Ornis explores and proposes, nothing is changed (every edit and command that writes is refused)."""
        if self._bot:
            return                                 # bots stay in classic Agent + Autonome
        on = bool(on)
        if self._busy or on == self._plan_mode:
            return
        self._plan_mode = on
        if on:
            self._ask_mode = False
        if self._agent and self._session:          # Vibe asks for each edit then: decide("plan") refuses it
            agent, sid, mode = self._agent, self._session, "ask" if on else self._mode
            threading.Thread(target=lambda: agent.set_mode(sid, mode), daemon=True).start()
        self.changed.emit()

    @Slot()
    def runPlan(self):
        """« Exécuter le plan »: back to the chosen autonomy, and Ornis does what it proposed."""
        if self._busy:
            return
        self.setPlanMode(False)
        for i, row in enumerate(self._items.rows):
            if row.get("kind") == "planready" and not row.get("done"):
                row["done"] = True
                self._items.touch(i)
        self.send(self._app._t.get("code_run_plan_text", "Execute the plan above."))

    @Slot(int, str)
    def answer(self, row, option_id):
        """The user's choice on a card asking for a permission (an option id of the agent)."""
        if not 0 <= row < len(self._items.rows):
            return
        item = self._items.rows[row]
        asked = item.get("permission")
        if not asked or self._agent is None or option_id not in {o["id"] for o in asked.get("options", [])}:
            return
        choice = next(o for o in asked["options"] if o["id"] == option_id)
        item.pop("permission", None)
        approved = str(choice.get("kind") or "").startswith("allow")
        if approved and self._bot and asked.get("key"):
            try:
                import ornis_bots  # noqa: PLC0415
                # the key of the very call decide() saw (same locations): the next one is allowed alone
                ornis_bots.remember_approval(self._bot, asked["key"])
            except Exception:  # noqa: BLE001
                pass
        if asked.get("host") and approved:
            self._begin_host(row, asked)
        elif asked.get("request") is not None:
            self._agent.answer(asked["request"], {"outcome": {"outcome": "selected", "optionId": option_id}})
        item["answer"] = "allowed" if approved else "rejected"
        self._items.touch(row)
        self.changed.emit()

    @Slot(int)
    def copyCommand(self, at):
        if 0 <= at < len(self._items.rows):
            QGuiApplication.clipboard().setText(self._items.rows[at].get("command", ""))

    @Slot(int)
    def retryOutside(self, at):
        if self._busy or self._host or self.waiting or not 0 <= at < len(self._items.rows):
            return
        row = self._items.rows[at]
        if not row.get("retryOutside") or row.get("id") in self._retry_ids:
            return
        if not ornis_code.retry_outside(row.get("command", ""), row.get("output", ""), self._folder, self.sandbox):
            return
        row["permission"] = {"request": None, "host": True, "title": self._app._t.get("code_retry_outside", "Retry outside sandbox"), "options": [
            {"id": "host-once", "kind": "allow_once", "label": self._app._t.get("code_retry_outside", "Retry outside sandbox")},
            {"id": "host-no", "kind": "reject_once", "label": ""}]}
        self._items.touch(at)
        self.changed.emit()

    def _cancel_host(self):
        host, self._host = self._host, None
        if host:
            host["cancel"].set()
            if not host["drained"]:
                host["agent"].cancel(host["session"])
            if host["opening"] == self._opening and 0 <= host["row"] < len(self._items.rows):
                row = self._items.rows[host["row"]]
                row.update(status="failed", output=self._app._t.get("code_stopped", "Stopped"))
                self._items.touch(host["row"])
            self._busy = False
            self.changed.emit()
            self._turn_changes()

    def _begin_host(self, at, asked):
        row = self._items.rows[at]
        self._retry_ids.add(row["id"])
        host = {"agent": self._agent, "session": self._session, "opening": self._opening,
                "row": at, "command": row["command"], "folder": self._folder,
                "cancel": threading.Event(), "drained": not self._busy, "started": False}
        self._host = host
        row.update(hostOwned=True, retryOutside=False, status="in_progress", output="")
        self._busy = True
        if asked.get("request") is not None:
            outcome = {"outcome": "selected", "optionId": asked["reject"]} if asked.get("reject") else {"outcome": "cancelled"}
            self._agent.answer(asked["request"], {"outcome": outcome})
        if not host["drained"]:
            self._agent.cancel(self._session)
        else:
            self._launch_host()

    def _launch_host(self):
        host = self._host
        if not host or host["started"] or not host["drained"]:
            return
        host["started"] = True
        def work():
            import ornis_process
            import ornis_code_hook
            try:
                if host["cancel"].is_set():
                    return
                result = ornis_process.start(host["command"], cwd=host["folder"], wait=0, sandbox=False)
                while not result.get("done"):
                    if host["cancel"].is_set():
                        ornis_process.stop(result["job"])
                        return
                    result = ornis_process.status(result["job"], wait=.3)
                output = result.get("output", "")
                if result.get("job"):
                    try:
                        output = (ornis_process.JOBS / result["job"] / "output").read_text(errors="replace")
                    except OSError:
                        pass
                if len(output) > ornis_code_hook.KEEP:
                    output = ornis_code_hook.shorten(output, ornis_code_hook.save(host["folder"], "tool", str(host["row"]), output))
                result["output"] = output + "\n[exit " + str(result.get("exit_code")) + "]"
            except Exception as error:
                result = {"output": str(error), "exit_code": -1}
            self._host_done.emit(host, result)
        threading.Thread(target=work, daemon=True, name="ornis-host-command").start()

    def _on_host_done(self, host, result):
        if self._host is not host or host["cancel"].is_set() or host["opening"] != self._opening or host["agent"] is not self._agent:
            return
        self._host = None
        row = self._items.rows[host["row"]]
        row.update(output=result["output"], manual=bool(row.get("admin") and result.get("exit_code") != 0), status="completed" if result.get("exit_code") == 0 else "failed")
        self._items.touch(host["row"])
        note = "[Ornis: host result]\nCommand: " + host["command"] + "\n[Executed outside sandbox]\n" + result["output"] + "\nContinue using this result; do not repeat this command."
        def work():
            try:
                answer = host["agent"].prompt(host["session"], [{"type": "text", "text": note}])
            except Exception as error:
                answer = {"error": str(error)}
            self._done.emit(host["session"], answer)
        threading.Thread(target=work, daemon=True, name="ornis-host-continue").start()
        self.changed.emit()

    # ---- what the agent sends ------------------------------------------------------------------------------------------
    def _bg_update(self, bg: dict, update: dict):
        kind = update.get("sessionUpdate")
        rows = bg.setdefault("rows", [])
        if kind in ("agent_message_chunk", "agent_thought_chunk", "user_message_chunk"):
            text = _text(update.get("content"))
            role = {"agent_message_chunk": "agent", "agent_thought_chunk": "thought", "user_message_chunk": "user"}[kind]
            last = rows[-1] if rows else None
            if last is None or last.get("kind") != role or (role == "user" and not bg.get("replaying")):
                if role == "user" and not bg.get("replaying"):
                    return
                row = {"kind": role, "role": "human" if role == "user" else "assistant", "content": "",
                       "id": f"{role}-{len(rows)}"}
                rows.append(row)
            else:
                row = last
            row["content"] = row.get("content", "") + text
            self._clean_row_text(row, True)
        elif kind in ("tool_call", "tool_call_update"):
            tid = str(update.get("toolCallId") or "")
            tools = bg.setdefault("tools", {})
            at = tools.get(tid, -1)
            if at < 0 or at >= len(rows):
                row = {"kind": "tool", "id": tid, "title": "", "tool": "other", "status": "pending",
                       "icon": KINDS["other"], "diff": [], "output": "", "path": "", "command": ""}
                rows.append(row)
                tools[tid] = len(rows) - 1
            else:
                row = rows[at]
            raw = update.get("rawInput") if isinstance(update.get("rawInput"), dict) else None
            if raw is not None:
                row["raw"] = raw
                row["command"] = str(raw.get("command") or row.get("command") or "")
                row["path"] = str(raw.get("path") or raw.get("file_path") or row.get("path") or "")
            if update.get("title"):
                row["title"] = str(update["title"])
            if update.get("kind"):
                row["tool"] = str(update["kind"])
                row["icon"] = KINDS.get(row["tool"], KINDS["other"])
            if update.get("status"):
                row["status"] = str(update["status"])
        elif kind == "usage_update":
            _bot_usage(str(bg.get("bot") or ""), int(update.get("used") or 0))
        elif kind == "session_info_update":
            title = str(update.get("title") or "")
            if title:
                bg["title"] = title
                self._remember_for(bg["folder"], bg["session"], title, bg["bot"], touch=not bg.get("replaying"))

    def _on_update(self, agent, sid, update):
        if sid != self._session or agent is not self._agent:   # only the agent in use writes
            bg = next((b for b in self._bg_bots.values() if b.get("agent") is agent), None)
            if bg is not None:
                self._bg_update(bg, update)
            return
        kind = update.get("sessionUpdate")
        if kind in ("agent_message_chunk", "agent_thought_chunk", "user_message_chunk"):
            text = _text(update.get("content"))
            role = {"agent_message_chunk": "agent", "agent_thought_chunk": "thought", "user_message_chunk": "user"}[kind]
            last = self._items.rows[-1] if self._items.rows else None
            if last is None or last.get("kind") != role or (role == "user" and not self._replaying):
                if role == "user" and not self._replaying:
                    return                            # our own bubble is already there
                self._write_text()
                at = self._items.append({"kind": role, "role": "human" if role == "user" else "assistant", "content": "",
                                         "id": f"{role}-{len(self._items.rows)}"})
            else:
                at = len(self._items.rows) - 1
            self._pending_text.setdefault(at, []).append(text)
            if self._bot and role in ("agent", "thought") and not self._replaying:
                self._status_tick()                   # « écrit… » / « réfléchit… » without waiting for the flush
            if self._replaying:
                pass                                  # written when the row changes, and at the end of the replay
            elif not self._flush.isActive():
                self._flush.start()
        elif kind in ("tool_call", "tool_call_update"):
            self._write_text()
            self._tool(update)
        elif kind == "plan":
            self._repeats.clear()                     # advancing the plan starts a new step
            self._plan = [{"text": str(e.get("content") or ""), "status": str(e.get("status") or "pending")}
                          for e in update.get("entries") or []]
            self.planChanged.emit()
        elif kind == "usage_update":
            previous = int(self._usage.get("used") or 0)
            self._usage = {"used": int(update.get("used") or 0), "size": int(update.get("size") or 0)}
            if self._bot:
                _bot_usage(self._bot, self._usage["used"])
            if self._compacting or int(self._usage["used"]) < previous * .7:
                self._invalidate_parts()
                if self._bot:
                    self._bot_brief = True
            self.usageChanged.emit()
            if not self._replaying:                   # a replayed conversation: the gateway measured another request
                self._measure.start()
        elif kind == "session_info_update":
            title = str(update.get("title") or "")
            renamed = any(s.get("renamed") for s in self._index.get(self._folder, []) if s.get("id") == self._session)
            if title and not renamed:
                self._title = title
                self._remember(self._session, title, touch=not self._replaying)
                self.changed.emit()
        elif kind == "available_commands_update":
            self._commands = [{"name": str(c.get("name") or ""), "description": str(c.get("description") or "")}
                              for c in update.get("availableCommands") or []
                              if isinstance(c, dict) and c.get("name") and str(c["name"]).lower() not in HIDDEN_COMMANDS]
        elif kind == "current_mode_update":
            pass                                      # our mode decides (decide()), whatever the agent shows

    def syncBotExchanges(self):
        if not self._bot or self._replaying:
            return
        import ornis_bots
        profile = ornis_bots.get(self._bot) or {}
        seen = profile.get("exchange_seen") or {}
        messages = []
        for path in ornis_bots.EXCHANGES.glob("*.jsonl"):
            ids = path.stem.split("__")
            if len(ids) == 2 and self._bot in ids:
                messages += ornis_bots.read_exchange(*ids, limit=500)
        messages.sort(key=lambda row: float(row.get("at") or 0))
        groups = []
        for row in messages:
            peer = row["to"] if row["from"] == self._bot else row["from"]
            if (groups and groups[-1]["peer"] == peer and row["at"] - groups[-1]["at"] < 300
                    and groups[-1].get("burst", 0) == row.get("burst", 0)):
                groups[-1].update(count=groups[-1]["count"] + 1, at=row["at"])
            else:
                groups.append({"kind": "peer", "id": "exchange-" + row["id"], "peer": peer,
                               "count": 1, "at": row["at"], "burst": row.get("burst", 0), "content": ""})
        for group in groups:
            group["unread"] = group["at"] > float(seen.get(group["peer"]) or 0)
            at = next((i for i, r in enumerate(self._items.rows) if r.get("id") == group["id"]), -1)
            if at < 0:
                self._items.append(group)
            elif any(self._items.rows[at].get(k) != v for k, v in group.items()):
                self._items.rows[at].update(group)
                self._items.touch(at)

    @staticmethod
    def _clean_row_text(row: dict, is_bot: bool = False):
        if row.get("kind") == "user" and row["content"].startswith(CONTINUE_NOTE):
            rest = row["content"][len(CONTINUE_NOTE):]
            row.update(kind="notice", key="code_continued_" + ("tool" if rest.startswith("You wrote") else "plan"))
        if row.get("kind") == "user" and row["content"].startswith("[Ornis: host result]"):
            row.update(kind="notice", key="code_host_done", content="")
        for hidden in (RETRACT_NOTE, UNDONE_NOTE, PLAN_NOTE, ASK_NOTE):
            if row.get("kind") == "user" and row["content"].startswith(hidden):
                row["content"] = row["content"][len(hidden):]
        if row.get("kind") == "user":
            for _ in range(6):
                body = row["content"]
                if body.startswith(("[Project notebook", "[Bot identity for", "[Bot memory note")):
                    cut = body.find("\n]\n\n")
                    if cut < 0:
                        break
                    row["content"] = body[cut + 4:]
                elif body.startswith(("[Files of the working folder", "[The working folder is empty.]")):
                    cut = body.find("]\n\n")
                    if cut < 0:
                        break
                    row["content"] = body[cut + 3:]
                else:
                    break
            if row["content"].startswith("[Bot message from"):
                row.update(kind="notice", key="bots_silent", content="")
            elif row["content"].startswith("[Group message in"):
                row.update(kind="notice", key="bots_group_turn", content=_group_title(row["content"]))
        if is_bot and row.get("kind") == "agent" and row.get("content", "").strip() == "[SILENT]":
            # peer reply with nothing for the person: hide the bubble
            row.update(kind="notice", key="bots_silent", content="")
        if row.get("kind") == "user" and row["content"].startswith("[Project command /"):
            name = row["content"][len("[Project command "):].split(" ", 1)[0]
            if "]\n\n" in row["content"]:
                row["content"] = name             # the bubble shows the command, as when it was sent
        if row.get("kind") == "user" and row["content"].startswith("[Files of the working folder"):
            cut = row["content"].find("]\n\n")      # the folder's files we joined to the first message: not shown
            if cut >= 0:
                row["content"] = row["content"][cut + 3:]

    def _write_text(self):
        for at, pieces in self._pending_text.items():
            text = "".join(pieces)
            if 0 <= at < len(self._items.rows):
                row = self._items.rows[at]
                row["content"] = row.get("content", "") + text
                self._clean_row_text(row, bool(self._bot))
                step = len(row["content"]) // 2000
                if (not self._replaying and row.get("kind") in ("agent", "thought") and step > row.get("_step", 0)
                        and not row.update(_step=step) and repeating(row["content"])):
                    if self._agent and self._session and self._busy and not self._looped:
                        self._looped = "text"        # the model repeats itself: stopped before it eats the day's limit
                        self._agent.cancel(self._session)
                self._items.touch(at)
        self._pending_text.clear()
        self._status_tick()

    def _tool(self, update):
        tid = str(update.get("toolCallId") or "")
        at = self._tools.get(tid, -1)
        if at < 0:
            at = self._items.append({"kind": "tool", "id": tid, "title": "", "tool": "other", "status": "pending",
                                     "icon": KINDS["other"], "diff": [], "output": "", "path": "", "command": ""})
            self._tools[tid] = at
        row = self._items.rows[at]
        if row.get("hostOwned"):
            return
        raw = update.get("rawInput") if isinstance(update.get("rawInput"), dict) else None
        if raw is not None:
            row["raw"] = raw
            row["command"] = str(raw.get("command") or row.get("command") or "")
            row["path"] = str(raw.get("path") or raw.get("file_path") or row.get("path") or "")
        if update.get("title"):
            row["title"] = str(update["title"])
        if update.get("kind"):
            row["tool"] = str(update["kind"])
            row["icon"] = KINDS.get(row["tool"], KINDS["other"])
        if update.get("status"):
            row["status"] = str(update["status"])
        for loc in update.get("locations") or []:
            if isinstance(loc, dict) and loc.get("path") and not row.get("path"):
                row["path"] = str(loc["path"])
        for content in update.get("content") or []:
            if not isinstance(content, dict):
                continue
            if content.get("type") == "diff":
                row["path"] = str(content.get("path") or row.get("path") or "")
                row["diff"] = diff_lines(row["path"], content.get("oldText"), str(content.get("newText") or ""))
                row["added"] = sum(1 for d in row["diff"] if d["t"] == "+")
                row["removed"] = sum(1 for d in row["diff"] if d["t"] == "-")
            else:
                text = _text(content)
                if text:
                    row["output"] = (row.get("output", "") + text)[-MAX_OUTPUT:] if row["tool"] == "execute" else text[-MAX_OUTPUT:]
        if row.get("tool") == "execute":
            row["retryOutside"] = (row.get("status") == "failed" and tid not in self._retry_ids
                                    and ornis_code.retry_outside(row.get("command", ""), row.get("output", ""), self._folder, self.sandbox))
        if row.get("status") == "failed" and row.get("tool") in ("read", "search", "edit") and not row.get("_counted"):
            row["_counted"] = True               # the same failing call again and again: it goes round in circles
            key = (row.get("tool"), row.get("path") or row.get("title"))
            self._failures[key] = self._failures.get(key, 0) + 1
            if sum(self._failures.values()) >= 6 or self._failures[key] >= 3:
                if self._agent and self._session and self._busy and not self._looped:
                    self._looped = True
                    self._agent.cancel(self._session)
        if row.get("status") == "completed" and not row.get("_repeat"):
            # the same command or search, done again and again although it answered (04/11: one grep 40 times)
            row["_repeat"] = True
            tool_kind = row.get("tool")
            if tool_kind in ("edit", "delete", "move"):
                self._repeats.clear()             # an edit starts a new round of checks
            elif tool_kind not in ("other", "think"):
                what = json.dumps(row.get("raw") or {"command": row.get("command"), "path": row.get("path"), "title": row.get("title")}, sort_keys=True)
                if what:
                    key = (tool_kind, what)
                    fingerprint = hashlib.sha256(str(row.get("output") or "").encode("utf-8", "replace")).hexdigest()
                    previous, count = self._repeats.get(key, (None, 0))
                    if self._bot and self._repeats.get("_last") != key:
                        count = 0
                    self._repeats["_last"] = key
                    self._repeats[key] = (fingerprint, count + 1 if previous == fingerprint else 1)
                    limit = 10 if self._bot else (6 if tool_kind == "read" else 4)
                    if self._repeats[key][1] >= limit and self._agent and self._session and self._busy and not self._looped:
                        self._looped = "repeat"
                        self._agent.cancel(self._session)
        if row.get("path") and self._folder:
            try:
                row["short"] = str(Path(row["path"]).resolve().relative_to(self._folder))
            except ValueError:
                row["short"] = row["path"]
        self._items.touch(at)
        self._status_tick()                          # bot: refresh its live status bubble

    def _on_permission(self, request_id, sid, tool, options):
        tid = str((tool or {}).get("toolCallId") or "")
        if sid != self._session:
            bg = next((b for b in self._bg_bots.values() if b.get("session") == sid and b.get("agent") is not None), None)
            if bg is not None:
                if tid:
                    self._bg_update(bg, dict(tool, toolCallId=tid, sessionUpdate="tool_call"))
                at = (bg.get("tools") or {}).get(tid, -1)
                rows = bg.get("rows") or []
                row = rows[at] if 0 <= at < len(rows) else {}
                call = {"kind": row.get("tool") or (tool or {}).get("kind"),
                        "rawInput": row.get("raw") or (tool or {}).get("rawInput") or {},
                        "title": row.get("title") or (tool or {}).get("title"),
                        "locations": [*((tool or {}).get("locations") or []), *([{"path": row["path"]}] if row.get("path") else [])],
                        "content": (tool or {}).get("content") or []}
                verdict = ornis_code.decide("auto", call, sandboxed=bool(ornis_code.sandbox_kind()),
                                            folder=bg["folder"], bot=bg["bot"])
                if bg.get("cron_job") and verdict == "ask":
                    verdict = "reject"
                opts = [o for o in options or [] if isinstance(o, dict)]
                if verdict in ("allow", "reject") or at < 0:
                    want = "allow_once" if verdict == "allow" else "reject_once"
                    pick = next((o for o in opts if o.get("kind") == want), None) or next(
                        (o for o in opts if str(o.get("kind", "")).startswith("reject")), None)
                    outcome = {"outcome": "selected", "optionId": pick.get("optionId")} if pick else {"outcome": "cancelled"}
                    bg["agent"].answer(request_id, {"outcome": outcome})
                else:
                    choices = [{"id": o.get("optionId"), "kind": str(o.get("kind") or ""), "label": ""}
                               for o in opts if o.get("optionId") != "allow_always_permanent"]
                    reject = next((o.get("optionId") for o in opts if o.get("kind") == "reject_once"), None)
                    row["permission"] = {"request": request_id, "options": choices, "host": False, "reject": reject,
                                         "title": "", "key": ornis_code.approval_key(call, bg["folder"])}
                return
        if tid and sid == self._session:
            self._tool(dict(tool, toolCallId=tid))
        at = self._tools.get(tid, -1)
        row = self._items.rows[at] if at >= 0 else {}
        call = {"kind": row.get("tool"), "rawInput": row.get("raw") or {}, "title": row.get("title"),
                "locations": [*((tool or {}).get("locations") or []), *([{"path": row["path"]}] if row.get("path") else [])],
                "content": (tool or {}).get("content") or []}
        # Bots always decide as Autonome (even if a leftover prefs mode remains on _mode).
        mode = "plan" if ((self._plan_mode or self._ask_mode) and not self._bot) else ("auto" if self._bot else self._mode)
        verdict = ornis_code.decide(mode, call, sandboxed=bool(ornis_code.sandbox_kind()),
                                    folder=self._folder, bot=self._bot)
        if at < 0 or sid != self._session or self._host is not None:
            verdict = "reject"
        if self._cron_job and verdict == "ask":   # unattended: refuse what still needs a human
            verdict = "reject"
        opts = [o for o in options or [] if isinstance(o, dict)]
        if verdict in ("allow", "reject") or at < 0 or sid != self._session:
            want = "allow_once" if verdict == "allow" else "reject_once"
            pick = next((o for o in opts if o.get("kind") == want), None) or next(
                (o for o in opts if str(o.get("kind", "")).startswith("reject")), None)
            if self._agent:
                outcome = {"outcome": "selected", "optionId": pick.get("optionId")} if pick else {"outcome": "cancelled"}
                self._agent.answer(request_id, {"outcome": outcome})
            if at >= 0 and sid == self._session and verdict == "reject":
                row["answer"] = "plan" if (self._plan_mode or self._ask_mode) else "blocked"
                self._items.touch(at)
            return
        choices = []
        for o in opts:
            k = str(o.get("kind") or "")
            if o.get("optionId") == "allow_always_permanent" or (k == "allow_always" and (ornis_code.always_ask(call, self._folder) or row.get("tool") in ("read", "search", "edit", "delete", "move"))):
                continue                              # a lasting rule would skip our checks: only for this conversation
            label = ""
            meta = (o.get("_meta") or {}).get("required_permissions") or []
            if k == "allow_always" and meta:
                label = str(meta[0].get("label") or "")
            choices.append({"id": o.get("optionId"), "kind": k, "label": label})
        import ornis_shell
        admin = row.get("tool") == "execute" and ornis_shell.classify(row.get("command", "")).get("level") == "admin"
        reject = next((o.get("optionId") for o in opts if o.get("kind") == "reject_once"), None)
        row["permission"] = {"request": request_id, "options": choices, "host": admin, "reject": reject, "title": self._app._t.get("code_admin", "Administration") if admin else ""}
        if self._bot:
            row["permission"]["key"] = ornis_code.approval_key(call, self._folder)   # remembered on « Autoriser »
        row["admin"] = admin
        if admin:
            row["title"] = self._app._t.get("code_admin", "Administration")
        self._items.touch(at)
        self.changed.emit()
        if hasattr(self._app, "notify") and QGuiApplication.focusWindow() is None:
            try:
                self._app.notify(self._title or self.folderName, self._app._t.get("code_permission_wanted", ""), "")
            except Exception:  # noqa: BLE001
                pass

    # ---- checkpoints: what a turn changed, and « Annuler ces modifications » (as /rewind in Claude Code) ---------------
    def _on_checked(self, session, rev):
        if session == self._session or not session:
            self._turn_rev = rev

    def _turn_changes(self):
        rev, folder, session, opening = self._turn_rev, self._folder, self._session, self._opening
        self._turn_rev = ""
        if not rev or not folder:
            return
        found = next((s for s in self._index.get(folder, []) if s.get("id") == session), None)
        if found is not None:
            found["checkpoints"] = (found.get("checkpoints") or [])[-49:] + [rev]
            self._save()

        def work():
            try:
                self._changes.emit(opening, rev, ornis_code.Checkpoints(folder).changes(rev))
            except Exception:  # noqa: BLE001
                pass
        threading.Thread(target=work, daemon=True, name="ornis-code-changes").start()

    def _on_changes(self, opening, rev, files):
        if opening != self._opening or not files:
            return
        self._bench.refresh()
        self._items.append({"kind": "changes", "rev": rev, "files": files[:200], "count": len(files),
                            "added": sum(f["added"] for f in files), "removed": sum(f["removed"] for f in files), "undone": False})

    @Slot(str)
    def rewind(self, rev):
        """The folder back as it was before that turn (the turns after it are undone too)."""
        folder = self._folder
        if not rev or not folder or self._busy:
            return

        def work():
            try:
                self._restored.emit(rev, ornis_code.Checkpoints(folder).restore(rev), "")
            except Exception as error:  # noqa: BLE001
                self._restored.emit(rev, 0, str(error))
        threading.Thread(target=work, daemon=True, name="ornis-code-rewind").start()

    @Slot(str, str)
    def rewindFile(self, rev, path):
        """One file of a turn back as it was before it (the others stay as Ornis left them)."""
        folder = self._folder
        if not rev or not path or not folder or self._busy:
            return

        def work():
            try:
                ok = ornis_code.Checkpoints(folder).restore_file(rev, path)
            except Exception:  # noqa: BLE001
                ok = False
            self._file_restored.emit(rev, path, ok)
        threading.Thread(target=work, daemon=True, name="ornis-code-rewind-file").start()

    def _on_file_restored(self, rev, path, ok):
        t = self._app._t
        if not ok:
            self.problem.emit(t.get("code_undo_failed", ""))
            return
        for i, row in enumerate(self._items.rows):
            if row.get("kind") == "changes" and row.get("rev") == rev:
                row["reverted"] = list(row.get("reverted") or []) + [path]
                self._items.touch(i)
        if self._agent and self._session:
            self._tell_undone = True              # its view of that file is old: told with the next message
        self.refreshFiles()
        self._refresh_git()
        self._bench.refresh()

    @Slot(str, str)
    def commit(self, message, branch):
        """Git: everything changed in the folder committed, on a new branch first when one is named."""
        folder, message, branch = self._folder, (message or "").strip(), (branch or "").strip()
        if not folder or not message or self._busy:
            return

        def work():
            self._committed.emit(ornis_code.git_commit(folder, message, branch))
        threading.Thread(target=work, daemon=True, name="ornis-code-commit").start()

    def _on_committed(self, problem):
        t = self._app._t
        if problem:
            self.problem.emit(t.get("code_commit_failed", "").replace("%1", problem))
        else:
            self._app.toast.emit(t.get("code_committed", ""))
        self._refresh_git()
        self._bench.refresh()

    @Slot()
    def undoLast(self):
        """« /annuler »: the changes of the last turn that made some, even after the conversation was reopened."""
        for row in reversed(self._items.rows):
            if row.get("kind") == "changes" and not row.get("undone"):
                self.rewind(row["rev"])
                return
        found = next((s for s in self._index.get(self._folder, []) if s.get("id") == self._session), None)
        revs = (found or {}).get("checkpoints") or []
        if revs:
            self.rewind(revs[-1])
        else:
            self.problem.emit(self._app._t.get("code_nothing_to_undo", ""))

    def _on_restored(self, rev, count, problem):
        t = self._app._t
        if problem:
            self.problem.emit(t.get("code_undo_failed", ""))
            return
        # this turn and every later one are undone
        later = False
        for i, row in enumerate(self._items.rows):
            if row.get("kind") == "changes" and (row.get("rev") == rev or later):
                later = True
                if not row.get("undone"):
                    row["undone"] = True
                    self._items.touch(i)
        self.problem.emit(t.get("code_undone", "").replace("%1", str(count)) if count else t.get("code_nothing_to_undo", ""))
        if count and self._agent and self._session:
            self._tell_undone = True              # the agent hears it with the next message: its view of the files is old
        self.refreshFiles()
        self._bench.refresh()

    # ---- the box: the messages sent before (↑), taking the last one back, pasting an image ---------------------------
    def _remember_prompt(self, text):
        rows = [t for t in self._history.get(self._folder, []) if t != text][-99:] + [text]
        self._history[self._folder] = rows
        try:
            HISTORY.parent.mkdir(parents=True, exist_ok=True)
            system.private_write(HISTORY, json.dumps(self._history, ensure_ascii=False))
        except OSError:
            pass

    @Slot(int, result=str)
    def historyAt(self, back):
        """The message sent `back` times ago in this folder (1 = the last one), "" past the oldest."""
        rows = self._history.get(self._folder, [])
        return rows[-back] if 0 < back <= len(rows) else ""

    @Slot(result=str)
    def editLast(self):
        """« Modifier » my last message (as Échap Échap in Claude Code): it comes back in the box, it and what followed
        leave the conversation, its file changes are undone; the agent hears that the next message replaces it."""
        if self._busy:
            return ""
        at = max((i for i, r in enumerate(self._items.rows) if r.get("kind") == "user" and not r.get("queued")), default=-1)
        if at < 0:
            return ""
        text = self._items.rows[at].get("content", "")
        undo = next((r for r in self._items.rows[at:] if r.get("kind") == "changes" and not r.get("undone")), None)
        if undo:
            self.rewind(undo["rev"])
        self._items.reset(self._items.rows[:at])
        self._retract = bool(self._session)
        self.changed.emit()
        return text

    @Slot(result=bool)
    def paste(self):
        """Ctrl+V: an image (a screenshot) or files of the clipboard joined to the message; text is left to the box."""
        mime = QGuiApplication.clipboard().mimeData()
        if mime is None:
            return False
        if mime.hasUrls() and any(u.isLocalFile() for u in mime.urls()):
            self.addFiles([u.toLocalFile() for u in mime.urls() if u.isLocalFile()])
            return True
        if mime.hasImage():
            image = QGuiApplication.clipboard().image()
            if image.isNull():
                return False
            PASTED.mkdir(parents=True, exist_ok=True)
            path = PASTED / time.strftime("Capture %Y-%m-%d %H.%M.%S.png")
            image.save(str(path), "PNG")
            self.addFiles([str(path)])
            return True
        return False

    @Slot(str)
    def openPath(self, path):
        """A file of a card (read, changed) in the app of the computer that opens it (the editor)."""
        target = Path(path) if Path(path).is_absolute() else Path(self._folder) / path
        if target.exists():
            system.open_url(target.as_uri())

    @Slot(str, str, bool)
    def pin(self, folder, session, on):
        found = next((s for s in self._index.get(folder, []) if s.get("id") == session), None)
        if found is not None:
            found["pinned"] = bool(on)
            self._save()
            self.changed.emit()

    @Property(int, notify=changed)
    def lastUser(self):
        """The row of my last message sent (its « Modifier »), -1 when none."""
        return max((i for i, r in enumerate(self._items.rows) if r.get("kind") == "user" and not r.get("queued")), default=-1)

    @Property("QVariantMap", notify=changed)
    def git(self):
        return self._git

    def _refresh_git(self):
        folder = self._folder

        def work():
            info = ornis_code.git_info(folder) if folder else {}
            self._git_seen.emit(folder, info)
        threading.Thread(target=work, daemon=True, name="ornis-code-git").start()

    def _on_git(self, folder, info):
        if folder == self._folder and info != self._git:
            self._git = info
            self.changed.emit()

    def _add_error(self, key, detail=""):
        self._items.append({"kind": "error", "key": key, "detail": detail[:300]})

    # ---- the list of conversations ---------------------------------------------------------------------------------------
    def _remember(self, session, title, touch: bool = True):
        self._remember_for(self._folder, session, title, self._bot, touch=touch)

    def _remember_for(self, folder: str, session: str, title: str, bot: str = "", touch: bool = True):
        if not session or not folder:
            return
        self.reloadIndex()
        rows = self._index.setdefault(folder, [])
        found = next((s for s in rows if s.get("id") == session), None)
        now = time.time()
        if found is None:
            found = {"id": session, "title": title or "", "created": now, "updated": now}
            rows.append(found)
        if title and not found.get("renamed"):
            found["title"] = title
        if touch or "updated" not in found:
            found["updated"] = now
        if bot:
            found["bot"] = bot
            try:
                import ornis_bots  # noqa: PLC0415
                fields = {"session": session}          # its preview is its last answer (_bot_preview), not a title
                if touch:
                    fields["updated"] = now
                ornis_bots.update(bot, fields)
            except Exception:  # noqa: BLE001
                pass
        self._save()

    def _save(self):
        try:
            INDEX.parent.mkdir(parents=True, exist_ok=True)
            system.private_write(INDEX, json.dumps(self._index, ensure_ascii=False))
        except OSError:
            pass

    def shutdown(self):
        self._cancel_host()
        if self._cron_job:
            self._finish_cron("error", self._app._t.get("code_stopped", "Arrêté"), self._session)
        if self._agent is not None:
            self._agent.close()
            self._agent = None
        for bid in list(self._bg_bots):
            self._close_bg_bot(bid)
