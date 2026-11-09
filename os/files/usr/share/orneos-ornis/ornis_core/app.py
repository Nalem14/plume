"""What the QML sees of the window: the account Connect stored, small preferences, links, the clipboard.

The account is the app password of Orneos Connect (cloud.account()); its files are watched, so connecting,
reconnecting or signing out elsewhere shows here without a restart. A link Ornis gives opens where it lives:
a note in Notes, a task in Tâches, a mail in Plume (links.py), a page of the cloud through the single sign-on.
"""
import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import quote, unquote

from PySide6.QtCore import QCoreApplication, QFileSystemWatcher, QObject, Property, QSize, QStandardPaths, Qt, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import (QBrush, QColor, QFont, QGuiApplication, QTextBlockFormat, QTextCharFormat, QTextCursor, QTextDocument,
                           QTextFormat, QTextFrameFormat, QTextLength)

import cloud
import system
import ornis_consent
import links
import ornis_chat
from qmlvalue import js_property
from ornis_core.strings import language, strings

CONFIG = cloud.CFG.parent / "ornis.json"
PREFS = {
    "local_tools": True,
    "reasoning": "think",        # think (the model reasons) | fast (« Rapide »: no reasoning, FAST_TAG)
    "code_mode": "ask",        # Code: what Ornis does without asking (ask, edits, auto: ornis_code.MODES)
    "session": "",               # the conversation shown last
    "sidebar": True,             # the conversations on the left (Ctrl+B hides them)
    "pinned": [],                # pinned conversations, newest pin first: the cloud's (orneos app), kept here for offline
    "pins_dirty": False,         # pinned or unpinned offline: sent at the next refresh
    "pins_synced": False,        # this computer's earlier pins have joined the cloud's
    "theme": "system",           # system | light | dark
    "text_size": "normal",       # small | normal | large
    "width": "normal",           # how wide the conversation reads: narrow | normal | wide
    "enter_sends": True,         # Enter sends (Shift+Enter: a new line); off, Ctrl+Enter sends
    "remember_new": False,       # new conversations are remembered (the assistant's memories)
    "show_tools": True,          # what Ornis used, under each reply
    "code_reasoning": "high",    # off/none, low, medium, high; read when Code starts
    "reasoning_open": False,     # its reasoning unfolded above each reply (folded by default)
    "suggestions": True,         # ideas on a new conversation
    "notify": True,              # a notification when a reply arrives while the window is in the background
    "workspaces": [],            # recent/pinned project folders: [{"path": "...", "name": "..."}]
    "session_workspaces": {},    # session_id -> workspace path (before projects: moved into them once)
    "projects_migrated": False,
    "session_modes": {},         # session_id -> "plan" (absent: the agent mode)
    "archived": [],              # archived conversations (out of the list, kept): the cloud's (orneos app), kept here for offline
    "archived_dirty": False,     # archived or brought back offline: sent at the next refresh
    "votes": {},                 # 👍 / 👎 given to Ornis's answers: {message id: 1 | -1} (the cloud's, kept here)
    "ephemeral": [],             # ephemeral conversations, deleted in the cloud once left (or at the next start)
    "list_filter": "all",        # the conversations shown: all | unread | pinned | projects | loose | pending | remembered | jobs
    "list_group": "date",        # how they are grouped: date | project | status
    "projects_folded": [],       # project folders whose conversations are folded in the Projects list
    "bench_tab": "",             # the Code panel on the right: files | changes | plan | terminal, "" when closed
    "bench_width": 440,          # its width (dragged)
    "plans_built": [],           # the plans already run (.ornis/plans/*.md): « Relancer » instead of « Exécuter »
}
TEXT_SIZES = {"small": 14, "normal": 15, "large": 17}
WIDTHS = {"narrow": 680, "normal": 780, "wide": 1000}
_FENCE_RE = re.compile(r"```([A-Za-z0-9_+.-]*)[ \t]*\n([\s\S]*?)(?:```|$)")


def initials(name):
    parts = [p for p in str(name).replace(".", " ").replace("_", " ").split() if p]
    if not parts:
        return "?"
    return parts[0][:2].upper() if len(parts) == 1 else (parts[0][0] + parts[-1][0]).upper()


# What a reply draws at most: a model that repeats itself writes hundreds of kilobytes, and laying that out froze the
# window for seconds at each step of the text and again when the conversation was reopened (seen 02/11 in Code).
# The rest stays in the message: « Copier », « Copier le code » and « Aperçu » give all of it.
SHOW_LINES = 200                   # lines of a code block drawn
SHOW_CHARS = 16000                 # characters of a code block, or of a piece of prose, drawn


def _shown_code(code):
    lines = code.split("\n")
    shown = "\n".join(lines[:SHOW_LINES])
    if len(shown) > SHOW_CHARS:
        shown = shown[:SHOW_CHARS]
    more = len(lines) - shown.count("\n") - 1
    return shown, max(0, more)


# Web sources cited by the agent (« [site](url) », ornis/agent PERSONA) become numbered marks [1] [2], one number per
# address in the whole reply, as the other assistants show them; a link to the cloud or written in the sentence
# (more than five words) stays a link. The mark keeps its address: a click opens it, hovering shows the site.
_CITE_RE = re.compile(r"(?:\(\s*)?\[([^\]\n]{1,48})\]\((https?://[^)\s]+)\)(?:\s*\))?")
_cloud_host = {}


def _own_host():
    if "host" not in _cloud_host:
        acc = cloud.account()
        _cloud_host["host"] = re.sub(r"^https?://", "", acc[0]).split("/")[0].split(":")[0].lower() if acc else ""
    return _cloud_host["host"]


# Follow-ups: the agent ends an answer with « → idea · idea » (ornis/agent/patch.py); the apps draw them as buttons
_FOLLOW_RE = re.compile(r"(?:^|\n)[ \t]*(?:→|->)[ \t]*([^\n]{2,240})\s*$")


def split_followups(text):
    """(the answer without its last « → … » line, [the ideas]) — at most three, each a short request."""
    raw = str(text or "")
    m = _FOLLOW_RE.search(raw)
    if not m or "```" in raw[m.start():]:
        return raw, []
    ideas = [i.strip(" .«»\"*") for i in re.split(r"\s+·\s+|\s+\|\s+", m.group(1))]
    ideas = [i for i in ideas if 1 < len(i) <= 90][:3]
    return (raw[:m.start()].rstrip(), ideas) if ideas else (raw, [])


def number_sources(text, numbers):
    """The citations of a piece of prose as [n](url), numbers shared by the reply's pieces ({url: n})."""
    own = {_own_host(), "app.orneos.eu"} - {""}

    def mark(m):
        label, url = m.group(1), m.group(2)
        host = re.sub(r"^https?://", "", url).split("/")[0].split(":")[0].lower()
        if host in own or len(label.split()) > 5:
            return m.group(0)
        n = numbers.setdefault(url, len(numbers) + 1)
        return f" [\u2009{n}\u2009]({url})"        # thin spaces: air inside the tinted mark
    return _CITE_RE.sub(mark, text)


def _prose(text):
    more = 0
    if len(text) > SHOW_CHARS:
        cut = text.rfind("\n\n", 0, SHOW_CHARS)
        cut = cut if cut > SHOW_CHARS // 2 else SHOW_CHARS
        more, text = len(text) - cut, text[:cut]
    return {"kind": "prose", "text": text, "lang": "", "code": "", "lines": 0, "previewable": False, "artifact": "", "title": "",
            "shown": "", "more": more}


VENDOR = Path(__file__).resolve().parent.parent / "qml" / "vendor"


def artifact_kind(lang: str, code: str) -> str:
    """'html', 'svg' or 'mermaid' when a code block is something to look at (an artifact), else ''."""
    head = code.lstrip()[:200].lower()
    if lang == "mermaid":
        return "mermaid"
    if lang == "svg" or (lang in ("xml", "") and head.startswith("<svg")):
        return "svg" if "<svg" in code[:2000].lower() else ""
    if lang in ("html", "htm") or (lang == "" and head.startswith(("<!doctype html", "<html"))):
        # a whole page, or a fragment big enough to be meant as one (not a one-line tag shown as an example)
        return "html" if head.startswith(("<!doctype", "<html")) or len(code.splitlines()) >= 8 else ""
    return ""


def artifact_title(kind: str, code: str, t: dict) -> str:
    found = re.search(r"<title[^>]*>(.*?)</title>", code, re.I | re.S) or re.search(r"<h1[^>]*>(.*?)</h1>", code, re.I | re.S)
    if found:
        title = re.sub(r"<[^>]+>", "", found.group(1)).strip()
        if title:
            return title[:80]
    if kind == "mermaid":
        first = code.strip().split("\n", 1)[0].split()[0].lower() if code.strip() else ""
        return t.get("artifact_diagram", "Diagram") + (f" · {first}" if first else "")
    return t.get("artifact_" + kind, kind.upper())


def artifact_page(kind: str, code: str, dark: bool, lang: str) -> str:
    """The page shown for an artifact. A page of the answer is kept as it is (with its scripts); a drawing or a
    diagram is centred on the theme's background. Nothing on the computer is reachable from it (the view)."""
    bg, fg = ("#0d1626", "#e6ebf2") if dark else ("#ffffff", "#0f1b2d")
    base = (f"<!doctype html><html lang='{lang}'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'>"
            f"<style>html,body{{margin:0;background:{bg};color:{fg};font-family:system-ui,sans-serif}}"
            ".wrap{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px;box-sizing:border-box}"
            ".wrap svg{max-width:100%;height:auto}pre.mermaid{margin:0}</style>")
    if kind == "svg":
        return base + f"</head><body><div class='wrap'>{code}</div></body></html>"
    if kind == "mermaid":
        try:
            library = (VENDOR / "mermaid.min.js").read_text(encoding="utf-8")
        except OSError:
            library = ""
        source = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        # the Ornis colours (design/tokens.json: Klein, Nuit) rather than Mermaid's own
        colours = ({"primaryColor": "#16233a", "primaryBorderColor": "#7a9bff", "primaryTextColor": "#e6ebf2", "lineColor": "#8a9bb5",
                    "secondaryColor": "#1d2d48", "tertiaryColor": "#0d1626", "edgeLabelBackground": bg, "clusterBkg": "#111d31"}
                   if dark else
                   {"primaryColor": "#e8eefb", "primaryBorderColor": "#002fa7", "primaryTextColor": "#0f1b2d", "lineColor": "#5a6b85",
                    "secondaryColor": "#fff4dc", "tertiaryColor": "#f5f7fb", "edgeLabelBackground": bg, "clusterBkg": "#f5f7fb"})
        colours["fontFamily"] = "system-ui, sans-serif"
        settings = json.dumps({"startOnLoad": True, "theme": "base", "securityLevel": "strict", "themeVariables": colours})
        return (base + f"<script>{library}</script></head><body><div class='wrap'><pre class='mermaid'>{source}</pre></div>"
                f"<script>mermaid.initialize({settings});</script></body></html>")
    low = code.lstrip()[:200].lower()
    if low.startswith(("<!doctype", "<html")):
        return code
    return base + f"</head><body>{code}</body></html>"


_PATH_EXT = re.compile(r"\.[A-Za-z0-9]{1,6}$")


def _looks_like_path(text: str) -> bool:
    """`dossier/fichier.md`, `./src/`, `~/Notes`, `rapport.pdf`: what a message names as a file or folder (not a
    command, code, an address or a sentence)."""
    t = text.strip()
    if not t or len(t) > 260 or t != text.strip("`") or any(c in t for c in "\n\t\"'<>|*?;=(){}[]$`"):
        return False
    absolute = t.startswith(("/", "~/")) or bool(re.match(r"^[A-Za-z]:[\\/]", t))
    if re.match(r"^[a-z][a-z0-9+.-]*://", t, re.I) or t.startswith(("-", "@", "#")) or (" " in t and not absolute):
        return False                             # a full path may hold a space (« Application Support »)
    t = re.sub(r":\d+(?::\d+)?$", "", t)      # src/app.py:42
    if "/" in t or "\\" in t or t.startswith("~"):
        return bool(re.search(r"[\w.-]", t)) and not re.fullmatch(r"[\d/.:-]+", t)   # not a date, a ratio
    return bool(_PATH_EXT.search(t)) and not re.fullmatch(r"[\d.]+", t) \
        and bool(re.search(r"\.(md|txt|pdf|csv|json|ya?ml|toml|py|js|ts|tsx|jsx|html?|css|sh|png|jpe?g|gif|svg|webp|"
                           r"docx?|xlsx?|pptx?|odt|ods|zip|log|ini|cfg|conf|xml|sql|php|rb|go|rs|java|kt|swift|c|h|cpp|qml)$",
                           t, re.I))


def _resolve_local(ref: str, bases) -> Path | None:
    """The file or folder a message names: absolute, ~, or relative to one of the conversation's folders."""
    raw = re.sub(r":\d+(?::\d+)?$", "", str(ref or "").strip().strip("`"))
    if not raw:
        return None
    path = Path(raw).expanduser()
    tries = [path] if path.is_absolute() else [Path(b) / path for b in bases if b] + [Path.home() / path]
    for candidate in tries:
        try:
            if candidate.exists():
                return candidate.resolve()
        except OSError:
            continue
    if path.is_absolute():
        return None
    # named by its name or the end of its path only (« 01-offre-lancement.md », written by another bot):
    # looked for under the same folders, a few thousand entries each at most
    want = path.parts
    for base in bases:
        seen = 0
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d not in (".git", "node_modules", "__pycache__", ".venv", "venv")]
            seen += len(dirs) + len(files)
            if seen > 5000:
                break
            for name in files + dirs:
                if name == want[-1]:
                    found = Path(root) / name
                    if found.parts[-len(want):] == want:
                        return found.resolve()
    return None


class App(QObject):
    accountChanged = Signal()
    notificationClicked = Signal(str)       # the conversation of a notification the user clicked
    prefsChanged = Signal()
    computerChanged = Signal()                  # the permissions of Ornis on this computer (ornis_consent)
    undoChanged = Signal()
    previewRequested = Signal(str, str, str)    # title, lang, code
    toast = Signal(str)
    raiseRequested = Signal()
    actionRequested = Signal(str, str)      # "session" | "ask" | "draft" | "new" | "scheduled" | "code" | "mode", value
    _profileRead = Signal(object)
    _clicked = Signal(str)

    def __init__(self):
        super().__init__()
        self._t = strings()
        self.project_folder = None       # session id → the folder of its project here (Projects.local_folder, bundle.py)
        self.path_bases = lambda: []     # the folders a relative path of a message is read from (bundle.py)
        self._html = {}                  # markdown() cache: (text, colours, size) → HTML
        self._blocks = {}                # messageBlocks() cache: text → blocks
        self._lang = language()
        try:
            self._config = json.loads(CONFIG.read_text())
        except (OSError, json.JSONDecodeError):
            self._config = {}
        if not isinstance(self._config, dict):
            self._config = {}
        self._prefs = dict(PREFS)
        self._prefs.update({k: v for k, v in self._config.items() if k in PREFS})
        self._account = None
        self._profile = {}
        self._computer = ornis_consent.settings()
        self._undoable = {}
        if self._computer.get("workspace"):
            self._remember_workspace(str(self._computer["workspace"]))
        self.refreshUndoable()
        self._profileRead.connect(self._set_profile, Qt.ConnectionType.QueuedConnection)
        self._clicked.connect(self.notificationClicked.emit, Qt.ConnectionType.QueuedConnection)
        self._watcher = QFileSystemWatcher(self)
        self._watcher.directoryChanged.connect(self._files_changed)
        self._watcher.fileChanged.connect(self._files_changed)
        cloud.CFG.parent.mkdir(parents=True, exist_ok=True)
        self._watcher.addPath(str(cloud.CFG.parent))
        self._files_changed()
        self._clock = QTimer(self)          # an autonomous mode ends by itself, without touching the file
        self._clock.timeout.connect(self._files_changed)
        self._clock.start(30000)

    # ---- account ---------------------------------------------------------------------------------------
    def _files_changed(self, *_):
        # the same folder holds ornis-computer.json: the mode changed in its window, the applet or a notification
        computer = ornis_consent.settings()
        if computer != getattr(self, "_computer", computer):
            self._computer = computer
            self.computerChanged.emit()
        for path in (cloud.CFG, cloud.TOKEN):
            if path.exists() and str(path) not in self._watcher.files():
                self._watcher.addPath(str(path))
        account = cloud.account()
        if account != self._account:
            self._account = account
            self._profile = {}
            self.accountChanged.emit()
            if account:
                threading.Thread(target=lambda: self._profileRead.emit(cloud.userinfo(*account)), daemon=True).start()

    def _set_profile(self, profile):
        self._profile = {"name": (profile or {}).get("displayname") or "", "email": (profile or {}).get("email") or ""}
        self.accountChanged.emit()

    def account(self):
        return self._account

    @Property(bool, notify=accountChanged)
    def connected(self):
        return self._account is not None

    @js_property(notify=accountChanged)
    def profile(self):
        if not self._account:
            return {}
        user = self._account[1]
        name = self._profile.get("name") or user
        return {"user": user, "name": name, "first": name.split()[0] if name.split() else name, "initials": initials(name),
                "email": self._profile.get("email") or ""}

    # ---- texts, preferences, window --------------------------------------------------------------------
    @js_property(constant=True)
    def t(self):
        return self._t

    @Property(str, constant=True)
    def lang(self):
        return self._lang

    @Slot(str, int, result=str)
    def plural(self, key, count):
        one, _, many = self._t.get(key, "").partition("|")
        return (one if count == 1 or not many else many).replace("%1", str(count))

    @js_property(notify=prefsChanged)
    def prefs(self):
        return dict(self._prefs)

    def pref(self, key):
        return self._prefs.get(key, PREFS.get(key))

    @Slot(str, "QVariant")
    def setPref(self, key, value):
        if key not in PREFS:
            return
        value = value.toVariant() if hasattr(value, "toVariant") else value
        if self._prefs.get(key) == value:
            return
        self._prefs[key] = value
        self._config[key] = value
        self._write()
        self.prefsChanged.emit()

    def _write(self):
        try:
            CONFIG.parent.mkdir(parents=True, exist_ok=True)
            CONFIG.write_text(json.dumps(self._config))
        except OSError:
            pass

    @Property(int, notify=prefsChanged)
    def textSize(self):
        return TEXT_SIZES.get(self.pref("text_size"), 15)

    @Property(int, notify=prefsChanged)
    def readingWidth(self):
        return WIDTHS.get(self.pref("width"), 780)

    # ---- Ornis on this computer ----------------------------------------------------------------------------
    @Property(str, constant=True)
    def computerEnvironment(self):
        import ornis_local
        state = ornis_local.status()
        return state["os"] + " · " + state["shell"]

    @Property(str, notify=computerChanged)
    def computerMode(self):
        return ornis_consent.settings()["mode"]

    @Property(str, notify=computerChanged)
    def computerUntil(self):
        """HH:MM when the mode ends by itself, else empty."""
        until = ornis_consent.settings()["until"]
        return time.strftime("%H:%M", time.localtime(until)) if until else ""

    @Property(str, notify=computerChanged)
    def workspace(self):
        return str(ornis_consent.settings().get("workspace") or "")

    @Property(str, notify=computerChanged)
    def workspaceName(self):
        ws = str(ornis_consent.settings().get("workspace") or "")
        return Path(ws).name if ws else ""

    def _remember_workspace(self, ws: str):
        ws = str(ws or "").strip()
        if not ws:
            return
        items = [w for w in (self.pref("workspaces") or []) if isinstance(w, dict) and w.get("path") and w.get("path") != ws]
        items.insert(0, {"path": ws, "name": Path(ws).name or ws})
        self.setPref("workspaces", items[:20])

    def bindSessionWorkspace(self, session_id: str, ws: str = ""):
        sid = str(session_id or "").strip()
        ws = str(ws or self.workspace or "").strip()
        if not sid or not ws:
            return
        mapping = dict(self.pref("session_workspaces") or {})
        if mapping.get(sid) != ws:
            mapping[sid] = ws
            self.setPref("session_workspaces", mapping)
            self.computerChanged.emit()

    def sessionWorkspace(self, session_id: str) -> str:
        """The folder of the conversation's project on this computer (its workspace for the computer tools)."""
        folder = self.project_folder(session_id) if self.project_folder else ""
        if folder:
            return folder
        mapping = self.pref("session_workspaces") or {}
        return str(mapping.get(str(session_id or ""), "") or "")

    def activateSessionWorkspace(self, session_id: str):
        """The open conversation's project becomes the workspace; a conversation without one (or a new one) has none:
        the previous conversation's project never follows to the next (it was then bound to every message sent)."""
        ws = self.sessionWorkspace(session_id) if session_id else ""
        if ws and not Path(ws).is_dir():
            ws = ""
        if ws == self.workspace:
            return
        ornis_consent.set_workspace(ws)
        self._computer = ornis_consent.settings()
        if ws:
            self._remember_workspace(ws)
        self.computerChanged.emit()

    def useWorkspace(self, path):
        """The workspace for what follows (a new conversation in a project), without binding the open conversation."""
        raw = str(path or "").strip()
        if raw.startswith("file://"):
            raw = QUrl(raw).toLocalFile()
        ornis_consent.set_workspace(raw)
        self._computer = ornis_consent.settings()
        if self._computer.get("workspace"):
            self._remember_workspace(self._computer["workspace"])
        self.computerChanged.emit()

    @Slot(str, str)
    def setSessionWorkspace(self, session_id, path):
        """« Project » of a conversation's menu: moves it to a project ("" : out of any). The open one follows at once."""
        sid = str(session_id or "").strip()
        if not sid:
            return
        mapping = dict(self.pref("session_workspaces") or {})
        if path:
            mapping[sid] = str(path)
        else:
            mapping.pop(sid, None)
        self.setPref("session_workspaces", mapping)
        if sid == str(self.pref("session") or ""):
            self.activateSessionWorkspace(sid)
        self.computerChanged.emit()

    def sessionMode(self, session_id: str) -> str:
        return str((self.pref("session_modes") or {}).get(str(session_id or ""), "") or "agent")

    def setSessionMode(self, session_id: str, mode: str):
        mapping = dict(self.pref("session_modes") or {})
        if mode == "plan":
            mapping[str(session_id)] = "plan"
        else:
            mapping.pop(str(session_id), None)
        if len(mapping) > 200:
            mapping = dict(list(mapping.items())[-200:])
        self.setPref("session_modes", mapping)

    @Slot(str)
    def toggleProjectFold(self, path):
        folded = [p for p in (self.pref("projects_folded") or []) if p != path]
        if path not in (self.pref("projects_folded") or []):
            folded.append(path)
        self.setPref("projects_folded", folded[-50:])

    @Slot(str)
    def openFolder(self, path):
        from PySide6.QtGui import QDesktopServices
        if path and Path(path).is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    @Property("QVariantList", notify=computerChanged)
    def projects(self):
        active = self.workspace
        seen = set()
        out = []
        raw_list = list(self.pref("workspaces") or [])
        if active and not any(isinstance(w, dict) and w.get("path") == active for w in raw_list):
            raw_list.insert(0, {"path": active, "name": Path(active).name or active})
        mapping = self.pref("session_workspaces") or {}
        for item in raw_list:
            if not isinstance(item, dict):
                continue
            p = str(item.get("path") or "").strip()
            if not p or p in seen:
                continue
            seen.add(p)
            try:
                rel = "~/" + str(Path(p).relative_to(Path.home()))
            except ValueError:
                rel = p
            count = sum(1 for v in mapping.values() if v == p)
            name = str(item.get("name") or Path(p).name or p)
            out.append({
                "path": p,
                "name": name,
                "sub": rel,
                "active": p == active,
                "count": count,
                "initial": (name[:1] or "?").upper(),
                "tone": sum(ord(ch) for ch in p) % 6,          # the tile's colour: one of the app families
                "folded": p in (self.pref("projects_folded") or []),
                "missing": not Path(p).is_dir(),
            })
        return out

    @Slot(str)
    def setWorkspace(self, path_or_url):
        raw = str(path_or_url or "").strip()
        if raw.startswith("file://"):
            raw = QUrl(raw).toLocalFile()
        ornis_consent.set_workspace(raw)
        self._computer = ornis_consent.settings()
        ws = self._computer.get("workspace") or ""
        if ws:
            self._remember_workspace(ws)
            cur = str(self.pref("session") or "")
            if cur:
                self.bindSessionWorkspace(cur, ws)
        self.computerChanged.emit()
        if ws:
            self.toast.emit(self._t["workspace_pinned"].replace("%1", Path(ws).name))

    @Slot(str)
    def removeProject(self, path):
        target = str(path or "").strip()
        if not target:
            return
        items = [w for w in (self.pref("workspaces") or []) if isinstance(w, dict) and w.get("path") != target]
        self.setPref("workspaces", items)
        if self.workspace == target:
            ornis_consent.set_workspace("")
            self._computer = ornis_consent.settings()
        self.computerChanged.emit()

    @Slot()
    def clearWorkspace(self):
        """The × of the project chip: the open conversation leaves its project (and the workspace goes)."""
        cur = str(self.pref("session") or "")
        mapping = dict(self.pref("session_workspaces") or {})
        if cur and cur in mapping:
            mapping.pop(cur)
            self.setPref("session_workspaces", mapping)
        ornis_consent.set_workspace("")
        self._computer = ornis_consent.settings()
        self.computerChanged.emit()

    @Property("QVariantMap", notify=undoChanged)
    def undoable(self):
        return dict(self._undoable)

    @Slot()
    def refreshUndoable(self):
        try:
            import ornis_desktop  # noqa: PLC0415
            items = ornis_desktop.undoable_entries(limit=5)
            first = items[0] if items else None
            nxt = {
                "count": len(items),
                "id": first["id"] if first else "",
                "name": first["name"] if first else "",
                "path": first["path"] if first else "",
            } if first else {}
        except Exception:  # noqa: BLE001
            nxt = {}
        if nxt != self._undoable:
            self._undoable = nxt
            self.undoChanged.emit()

    @Slot()
    def undoLastLocalChange(self):
        try:
            import ornis_desktop  # noqa: PLC0415
            res = ornis_desktop.undo_latest()
            self.refreshUndoable()
            name = Path(str(res.get("restored") or res.get("removed") or "")).name
            self.toast.emit(self._t["undo_done"].replace("%1", name or "fichier"))
        except Exception:  # noqa: BLE001
            self.refreshUndoable()
            self.toast.emit(self._t["undo_empty"])

    @Slot(str)
    def stopLocalCommand(self, job):
        if not job:
            return
        import ornis_shell  # noqa: PLC0415
        threading.Thread(target=lambda: ornis_shell.stop(str(job)), daemon=True).start()

    @Slot(str)
    def setComputerMode(self, mode):
        # autonomous starts for an hour from here; longer is a deliberate choice in the permissions window
        ornis_consent.set_mode(mode, 60 if mode == "full" else 0)
        self._computer = ornis_consent.settings()
        self.computerChanged.emit()

    @Slot()
    def openComputer(self):
        self._helper()

    @Slot()
    def openExtensions(self):
        self._helper("--extensions")

    def _helper(self, *args):
        """« Ornis on this computer » (or its Skills and MCP servers): a window of its own. When it dies at start, the
        user is told and its error goes to the log; a silent button was all one saw of a crash (02/11)."""
        import ornis_local  # noqa: PLC0415
        try:
            proc = subprocess.Popen([*ornis_local.helper("computer"), *args], stdout=subprocess.DEVNULL,
                                    stderr=subprocess.PIPE, start_new_session=os.name != "nt")
        except OSError as error:
            print("ornis: computer window:", error, flush=True)
            self.toast.emit(self._t["helper_failed"])
            return

        def watch():
            try:
                _, err = proc.communicate(timeout=8)
            except subprocess.TimeoutExpired:
                threading.Thread(target=proc.communicate, daemon=True).start()   # open: its pipe is drained
                return
            if proc.returncode:
                print("ornis: computer window:", (err or b"").decode(errors="replace")[-2000:], flush=True)
                self.toast.emit(self._t["helper_failed"])
        threading.Thread(target=watch, daemon=True).start()

    @Property(QSize, constant=True)
    def windowSize(self):
        size = self._config.get("window")
        if not (isinstance(size, list) and len(size) == 2):
            size = [1080, 760]
        return QSize(max(640, int(size[0])), max(460, int(size[1])))

    @Slot(int, int)
    def saveWindow(self, width, height):
        self._config["window"] = [width, height]
        self._write()

    # ---- links, the clipboard, the rest of the desktop -----------------------------------------------------
    @Slot(str)
    def openLink(self, url):
        """A link of a reply: a note, a task or a mail in its app; the cloud signed in; the rest in the browser."""
        url = str(url or "").strip()
        if not url:
            return
        if url.startswith("ornis-copy:"):
            self.copy(unquote(url[len("ornis-copy:"):]))
        elif url.startswith("ornis-path:"):
            self.openLocal(unquote(url[len("ornis-path:"):]))
        elif url.startswith("file://"):
            self.openLocal(QUrl(url).toLocalFile())
        elif links.is_link(url):
            links.open_link(url)
        elif url.startswith(cloud.CLOUD):
            cloud.open_url(cloud.cloud_link(url))
        elif url.startswith(("https://", "http://", "mailto:")):
            cloud.open_url(url)

    @Slot(str)
    def openLocal(self, ref):
        """A file or folder named in a message: a file in the system's preview (Quick Look on a Mac; elsewhere the app
        that opens it), a folder in the file manager. A relative path is read from the conversation's folders
        (the project, the bot's folder and profile, the group's shared folder: `path_bases`, set by the bundle)."""
        found = _resolve_local(ref, self.path_bases())
        if found is None:
            self.toast.emit(self._t["path_missing"].replace("%1", str(ref)))
            return
        if found.is_file() and system.MACOS and Path("/usr/bin/qlmanage").exists():
            subprocess.Popen(["/usr/bin/qlmanage", "-p", str(found)], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
            return
        system.open_url(str(found))

    @Slot(str)
    def openCloud(self, path):
        cloud.open_url(cloud.cloud_link(path or "/apps/assistant/"))

    @Slot()
    @Slot(str)
    def openAiOffers(self, offer=""):
        """The account's AI offers on orneos.eu (AiOffersController): it knows the plan, so it offers the right thing
        (an offer on a paid plan, a plan and an offer together otherwise, the owner for a team member), one step and
        back here. ?offer= preselects one, ?from= says where to come back."""
        here = "plume" if "plume" in (QCoreApplication.applicationName() or "").lower() else "ornis"
        query = "?from=" + here + ("&offer=" + offer if offer in ("boost", "pro", "max", "ultra") else "")
        cloud.open_url("https://orneos.eu/" + self._lang + "/" + {"fr": "tableau-de-bord/ia", "de": "dashboard/ki"}.get(self._lang, "dashboard/ai") + query)

    @Slot()
    def openPlans(self):
        """« More Ornis »: the AI offers, which lead to the plans when the account has none."""
        self.openAiOffers()

    @Slot()
    def openExtra(self):
        self.openAiOffers()

    @Slot()
    def openConnect(self):
        system.launch("connect")

    @Slot(str)
    def copy(self, text):
        if not text:
            return
        clip = QGuiApplication.clipboard()
        if clip is not None:
            clip.setText(text)
        else:
            cloud.copy_to_clipboard(text)
        self.toast.emit(self._t["copied"])

    @Slot(str, str, result=str)
    @Slot(str, str, int, result=str)
    @Slot(str, str, int, str, str, result=str)
    def markdown(self, text, link_color, size=15, line_color="#d9dee8", field_color="#f2f4f8"):
        """A reply as HTML: Qt's Markdown with air between paragraphs, lists indented like text, links in the accent;
        tables with thin rules (the header bold), code on a tinted block with « Copy code » under it, formulas as plain symbols.
        Kept in a small cache: the conversation is laid out again on many changes, and each conversion costs."""
        key = (text, link_color, size, line_color, field_color)
        cached = self._html.get(key)
        if cached is not None:
            self._html[key] = self._html.pop(key)       # the most recent last
            return cached
        html = self._markdown_html(text, link_color, size, line_color, field_color)
        self._html[key] = html
        while len(self._html) > 400:
            self._html.pop(next(iter(self._html)))
        return html

    def _markdown_html(self, text, link_color, size, line_color, field_color):
        doc = QTextDocument()
        font = QFont("Schibsted Grotesk")
        font.setPixelSize(size)
        doc.setDefaultFont(font)
        doc.setIndentWidth(22)
        doc.setMarkdown(ornis_chat.plain_math(text or ""), QTextDocument.MarkdownFeature.MarkdownDialectGitHub)
        cursor = QTextCursor(doc)
        tables, codes = [], []                     # code blocks: [last block position, their text]
        block = doc.begin()
        while block.isValid():
            fmt = QTextBlockFormat(block.blockFormat())
            in_list = block.textList() is not None
            nxt = block.next()
            same_list = in_list and nxt.isValid() and nxt.textList() is block.textList()
            code = fmt.hasProperty(QTextFormat.Property.BlockCodeFence) or fmt.nonBreakableLines()
            next_code = nxt.isValid() and (nxt.blockFormat().hasProperty(QTextFormat.Property.BlockCodeFence) or nxt.blockFormat().nonBreakableLines())
            cursor.setPosition(block.position())
            table = cursor.currentTable()
            if table is not None and table not in tables:
                tables.append(table)
            if code:
                prev = block.previous()
                first = not (prev.isValid() and (prev.blockFormat().hasProperty(QTextFormat.Property.BlockCodeFence) or prev.blockFormat().nonBreakableLines()))
                fmt.setBackground(QColor(field_color))
                fmt.setTopMargin(6 if first else 0)
                fmt.setBottomMargin(0 if next_code else 4)
                if first:
                    codes.append([block.position(), []])
                codes[-1][0] = block.position() + block.length() - 1
                codes[-1][1].append(block.text())
            else:
                fmt.setTopMargin(0)
                fmt.setBottomMargin(3 if same_list else 10)
                fmt.setLineHeight(135, 1)          # proportional line height
            cursor.setBlockFormat(fmt)
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if (frag.isValid() and not code and not frag.charFormat().isAnchor()
                        and frag.charFormat().fontFixedPitch() and _looks_like_path(frag.text())):
                    # `workspace/notes.md`, `.ornis/plans/`: a link that opens it (a preview, or the folder)
                    ref = QTextCharFormat()
                    ref.setAnchor(True)
                    ref.setAnchorHref("ornis-path:" + quote(frag.text().strip()))
                    ref.setForeground(QColor(link_color))
                    cursor.setPosition(frag.position())
                    cursor.setPosition(frag.position() + frag.length(), QTextCursor.MoveMode.KeepAnchor)
                    cursor.mergeCharFormat(ref)
                elif frag.isValid() and frag.charFormat().isAnchor():
                    link = QTextCharFormat()
                    link.setForeground(QColor(link_color))
                    link.setFontUnderline(False)
                    if frag.text().strip().isdigit() and frag.charFormat().anchorHref().startswith("http"):
                        link.setBackground(QColor(field_color))      # a numbered source: a small tinted mark
                        link.setFontPointSize(max(8, size * 0.6))       # as « Copier le code » (the document is in pixels)
                        link.setFontWeight(QFont.Weight.DemiBold)
                    cursor.setPosition(frag.position())
                    cursor.setPosition(frag.position() + frag.length(), QTextCursor.MoveMode.KeepAnchor)
                    cursor.mergeCharFormat(link)
                it += 1
            block = nxt
        for table in tables:
            tfmt = table.format()
            tfmt.setBorder(1)
            tfmt.setBorderStyle(QTextFrameFormat.BorderStyle.BorderStyle_Solid)
            tfmt.setBorderBrush(QBrush(QColor(line_color)))
            tfmt.setBorderCollapse(True)
            tfmt.setCellSpacing(0)
            tfmt.setCellPadding(6)
            tfmt.setTopMargin(2)
            tfmt.setBottomMargin(12)
            table.setFormat(tfmt)
        for position, lines in reversed(codes):   # « Copy code » under each block (a link: copy, not open)
            cursor.setPosition(position)
            label = QTextCharFormat()
            label.setAnchor(True)
            label.setAnchorHref("ornis-copy:" + quote("\n".join(lines)))
            label.setForeground(QColor(link_color))
            label.setFontPointSize(max(8, size * 0.62))
            bfmt = QTextBlockFormat()
            bfmt.setTopMargin(2)
            bfmt.setBottomMargin(10)
            cursor.insertBlock(bfmt, QTextCharFormat())
            cursor.insertText(self._t["copy_code"], label)
        return doc.toHtml()

    @Slot(str, result="QVariantList")
    def messageBlocks(self, text):
        """Splits a reply into prose and fenced code blocks so QML renders code with a header, language and icon buttons.
        Kept in a small cache, as markdown(): each step of a reply being written asks again for the whole text."""
        raw = str(text or "")
        cached = self._blocks.get(raw)
        if cached is not None:
            return cached
        blocks = self._message_blocks(raw)
        self._blocks[raw] = blocks
        while len(self._blocks) > 200:
            self._blocks.pop(next(iter(self._blocks)))
        return blocks

    @Slot(str, result="QVariantList")
    def followups(self, text):
        """The ideas the answer ends with (« → … · … »), shown as buttons under the last answer."""
        return split_followups(text)[1]

    def _message_blocks(self, raw):
        raw = split_followups(raw)[0]     # its « → … » line: buttons, not text
        numbers = {}                    # the reply's web sources: one number per address, in order
        if "```" not in raw:
            return [_prose(number_sources(raw, numbers))] if raw.strip() else []
        blocks = []
        pos = 0
        for m in _FENCE_RE.finditer(raw):
            before = raw[pos:m.start()].strip("\n")
            if before.strip():
                blocks.append(_prose(number_sources(before, numbers)))
            lang = (m.group(1) or "").strip()
            code = m.group(2).rstrip("\n")
            low = lang.lower()
            previewable = low in ("markdown", "md", "html", "svg", "mermaid", "json", "csv", "txt", "python", "py", "js", "ts", "sh", "bash", "sql", "css", "qml", "php") or len(code.splitlines()) >= 4
            kind = artifact_kind(low, code)
            shown, more = _shown_code(code)
            blocks.append({
                "shown": shown,
                "more": more,
                "kind": "code",
                "text": "",
                "lang": lang or kind or "code",
                "code": code,
                "lines": max(1, len(code.splitlines())),
                "previewable": previewable or bool(kind),
                "artifact": kind,
                "title": artifact_title(kind, code, self._t) if kind else "",
            })
            pos = m.end()
        tail = raw[pos:].strip("\n")
        if tail.strip():
            blocks.append(_prose(number_sources(tail, numbers)))
        return blocks

    @Slot(str, str, bool, result=str)
    def artifactUrl(self, lang, code, dark):
        """An artifact (a page, a drawing, a diagram) as a complete page in a private file, for the sandboxed web view
        (loadHtml stops at 2 MB, Mermaid alone is more). Only the last few stay."""
        kind = artifact_kind(str(lang or "").lower(), str(code or "")) or "html"
        folder = system.runtime_dir() / "ornis-artifacts"
        folder.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(folder, 0o700)
        except OSError:
            pass
        page = artifact_page(kind, str(code or ""), bool(dark), self._lang)
        import hashlib
        path = folder / (hashlib.sha256(page.encode()).hexdigest()[:20] + ".html")
        if not path.exists():
            system.private_write(path, page)
        for old in sorted(folder.glob("*.html"), key=lambda p: p.stat().st_mtime)[:-12]:
            old.unlink(missing_ok=True)
        return QUrl.fromLocalFile(str(path)).toString()

    @Slot(str, str, str)
    def openPreview(self, title, lang, code):
        self.previewRequested.emit(str(title or self._t["preview_title"]), str(lang or "code"), str(code or ""))

    @Slot(str, str)
    def savePreviewToNotes(self, title, content):
        folder = system.CACHE / "ornis-export"
        folder.mkdir(parents=True, exist_ok=True)
        name = "".join(ch for ch in str(title or "") if ch not in '/\\:*?"<>|').strip()[:80] or "Ornis"
        path = folder / f"{name}.md"
        try:
            path.write_text(str(content or ""), encoding="utf-8")
            self.spawn(["orneos-notes", "--files", str(path)])
            self.toast.emit(self._t["sent_notes"])
        except OSError:
            self.toast.emit(self._t["export_failed"])

    @Slot(str, str)
    def savePreviewToFile(self, path_or_url, content):
        raw = str(path_or_url or "").strip()
        if raw.startswith("file://"):
            raw = QUrl(raw).toLocalFile()
        if not raw:
            return
        try:
            Path(raw).write_text(str(content or ""), encoding="utf-8")
            self.toast.emit(self._t["exported"])
        except OSError:
            self.toast.emit(self._t["export_failed"])

    @Slot(str, result=str)
    def dropped(self, payload):
        """What a drop on the composer adds to the message: links from Plume, Notes and Tâches as their title
        and address (Ornis reads the cloud ones), files of the synced Orneos folder as their path in Drive."""
        try:
            items = links.decode(payload)
        except Exception:  # noqa: BLE001 - anything that is not our MIME
            items = []
        parts = []
        for item in items:
            url, title, kind = item.get("url", ""), item.get("title", ""), item.get("kind", "")
            if kind == "mail":
                parts.append(f"« {title} » (mail)" if title else "")
            elif url:
                parts.append(f"[{title or url}]({url})")
        return " ".join(p for p in parts if p)

    @Slot("QVariantList", result=str)
    def droppedFiles(self, urls):
        out = []
        root = str(cloud.SYNC_DIR)
        for url in urls:
            path = str(url.toLocalFile() if hasattr(url, "toLocalFile") else url).removeprefix("file://")
            if path.startswith(root + "/"):
                out.append("/" + path[len(root) + 1:])
            elif path.startswith(("http://", "https://")):
                out.append(path)
        return " ".join(out)

    @Slot(str, result=QUrl)
    def exportUrl(self, title):
        """Where « Exporter en Markdown… » proposes to save: Documents, named after the conversation."""
        folder = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation) or str(Path.home())
        name = "".join(ch for ch in str(title or "") if ch not in '/\\:*?"<>|').strip()[:80] or "Ornis"
        return QUrl.fromLocalFile(str(Path(folder) / f"{name}.md"))

    @Slot(QUrl, result=str)
    def localPath(self, url):
        return url.toLocalFile()

    @Slot(str, str, str)
    def notify(self, title, body, session_id):
        """A reply arrived while the window was elsewhere: a notification; clicking it opens the conversation."""
        body = " ".join(str(body or "").split())
        if not system.has_notify_send():
            system.notify(str(title or "Ornis"), body[:180], lambda: self._clicked.emit(session_id))
            return
        cmd = ["notify-send", "--app-name=Ornis", "--icon=eu.orneos.ornis", "--hint=string:desktop-entry:eu.orneos.assistant",
               f"--action=default={self._t['open']}", "--wait", str(title or "Ornis"), body[:180] + ("…" if len(body) > 180 else "")]

        def run():
            try:
                out = subprocess.run(cmd, capture_output=True, text=True, timeout=600).stdout.strip()
            except (OSError, subprocess.SubprocessError):
                return
            if out == "default":
                self._clicked.emit(session_id)
        threading.Thread(target=run, daemon=True).start()

    def spawn(self, cmd):
        self._spawn(cmd)

    @staticmethod
    def _spawn(cmd):
        system.spawn(cmd)

    def handle_args(self, args, activation_token=""):
        """--session=ID (from the top-bar applet), --ask=TEXT (KRunner, other apps), --draft=TEXT, --new, --scheduled,
        --code (the Code view), --mode=plan|goal|research (a new conversation in that mode).
        --agent: stay in the background (Code cron); no window raise."""
        args = [a for a in (args or []) if a != "--agent"]
        acted = False
        for arg in args:
            if arg.startswith("--session="):
                self.actionRequested.emit("session", arg.split("=", 1)[1]); acted = True
            elif arg.startswith("--ask="):
                self.actionRequested.emit("ask", arg.split("=", 1)[1]); acted = True
            elif arg.startswith("--draft="):
                self.actionRequested.emit("draft", arg.split("=", 1)[1]); acted = True
            elif arg in ("--new", "--scheduled", "--code"):
                self.actionRequested.emit(arg[2:], ""); acted = True
            elif arg.startswith("--mode="):        # a new conversation in that mode (Plume's Ctrl+K)
                self.actionRequested.emit("mode", arg.split("=", 1)[1]); acted = True
        if activation_token:
            os.environ["XDG_ACTIVATION_TOKEN"] = activation_token
        if acted or args:                        # empty (agent start): leave the window closed
            self.raiseRequested.emit()
