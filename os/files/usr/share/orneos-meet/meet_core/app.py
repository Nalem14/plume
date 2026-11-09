"""What the QML sees of the window: the account Connect stored, small preferences, dates in words, links. (Meet)

The account is the app password of Orneos Connect (cloud.account()); its files are watched, so connecting,
reconnecting or signing out elsewhere shows here without a restart.
"""
import json
import re
import os
import time
import urllib.parse
from datetime import date, datetime

from PySide6.QtCore import QFileSystemWatcher, QObject, Property, QSize, Signal, Slot

import cloud
import links
import meeting
import system
from qmlvalue import js_property
from meet_core.strings import language, strings

CONFIG = cloud.CFG.parent / "meet.json"
PREFS = {
    "filter": "all",             # all | unread | mentions | favorites | archived
    "camera": "",                # the devices chosen last
    "mic": "",
    "speaker": "",
    "join_audio": True,          # how a call starts
    "join_video": True,
    "enter_sends": True,         # Entrée sends, Maj+Entrée goes to the line (else Ctrl+Entrée sends)
    "notify": True,              # new messages as notifications (when the window is not in front)
    "sounds": True,              # the ring and the join / leave sounds
    "layout": "grid",            # grid | speaker
    "blur": "",                  # "" | blur | image
    "badge": True,
    "quick_reactions": ["👍", "👀", "🎉"],   # pinned beside a message (made for work: « vu », « bravo »)
    "recent_emojis": [],         # the last ones used, first in the picker
}


def initials(name):
    parts = [p for p in str(name).replace(".", " ").replace("_", " ").split() if p]
    if not parts:
        return "?"
    return parts[0][:2].upper() if len(parts) == 1 else (parts[0][0] + parts[-1][0]).upper()


class App(QObject):
    accountChanged = Signal()
    prefsChanged = Signal()
    toast = Signal(str)
    raiseRequested = Signal()
    actionRequested = Signal(str, str)      # "room" | "call" | "new" | "to" | "search", value

    def __init__(self):
        super().__init__()
        self._t = strings()
        self._lang = language()
        try:
            self._config = json.loads(CONFIG.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self._config = {}
        if not isinstance(self._config, dict):
            self._config = {}
        self._prefs = dict(PREFS)
        self._prefs.update({k: v for k, v in self._config.items() if k in PREFS})
        self._account = None
        self._profile = {}
        self._watcher = QFileSystemWatcher(self)
        self._watcher.directoryChanged.connect(self._files_changed)
        self._watcher.fileChanged.connect(self._files_changed)
        cloud.CFG.parent.mkdir(parents=True, exist_ok=True)
        self._watcher.addPath(str(cloud.CFG.parent))
        self._files_changed()

    # ---- account -----------------------------------------------------------------------------------------
    def _files_changed(self, *_):
        for path in (cloud.CFG, cloud.TOKEN):
            if path.exists() and str(path) not in self._watcher.files():
                self._watcher.addPath(str(path))
        account = cloud.account()
        if account != self._account:
            self._account = account
            self._profile = {}
            self.accountChanged.emit()

    def account(self):
        return self._account

    def set_profile(self, profile):
        self._profile = profile or {}
        self.accountChanged.emit()

    @Property(bool, notify=accountChanged)
    def connected(self):
        return self._account is not None

    @js_property(notify=accountChanged)
    def profile(self):
        if not self._account:
            return {}
        user = self._account[1]
        name = self._profile.get("name") or user
        email = self._profile.get("email") or (user if "@" in user else f"{user}@orneos.eu")
        return {"user": user, "name": name, "email": email, "initials": initials(name),
                "avatar": f"image://meet/user/{urllib.parse.quote(user)}"}

    # ---- texts, preferences, window ----------------------------------------------------------------------
    @js_property(constant=True)
    def t(self):
        return self._t

    @Property(str, constant=True)
    def lang(self):
        return self._lang

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
            CONFIG.write_text(json.dumps(self._config), encoding="utf-8")
        except OSError:
            pass

    @Property(QSize, constant=True)
    def windowSize(self):
        size = self._config.get("window")
        if not (isinstance(size, list) and len(size) == 2):
            size = [1180, 760]
        return QSize(max(760, int(size[0])), max(500, int(size[1])))

    @Slot(int, int)
    def saveWindow(self, width, height):
        self._config["window"] = [width, height]
        self._write()

    # ---- the rest of the desktop -------------------------------------------------------------------------
    @Slot(str)
    def openUrl(self, url):
        token = meeting.talk_token(url)
        if token:                                  # another conversation of our cloud: here, not in the browser
            self.actionRequested.emit("room", token + _message_of(url))
            return
        if links.is_link(url):                     # a note, a task, a mail: its own app
            links.open_link(url)
            return
        if url.startswith(("https://", "http://", "mailto:")):
            cloud.open_url(url)

    @Slot(str)
    def openCloud(self, path):
        cloud.open_url(cloud.cloud_link(path or "/apps/spreed/"))

    @Slot()
    def openConnect(self):
        system.launch("connect")

    @Slot(str, str, result=bool)
    def toNotes(self, title, markdown):
        """A new note in Notes (minutes of a meeting, a message): a Markdown file its « Ajouter à Notes » takes."""
        if not system.has_app("notes"):
            return False
        folder = system.CACHE / "meet-notes"
        folder.mkdir(parents=True, exist_ok=True)
        name = "".join(ch for ch in title if ch not in '/\\:*?"<>|').strip()[:80] or "Meet"
        path = folder / f"{name}.md"
        path.write_text(markdown.strip() + "\n", encoding="utf-8")
        return system.launch("notes", "--files", str(path))

    @Slot("QVariantList", str, result=bool)
    def toTasks(self, items, link):
        """Tasks in Tâches ([{title, due}]), each with the link of the conversation."""
        if not system.has_app("tasks"):
            return False
        out = []
        for item in items:
            item = item.toVariant() if hasattr(item, "toVariant") else item
            if isinstance(item, dict) and str(item.get("title") or "").strip():
                out.append({"title": str(item["title"]).strip(), "due": str(item.get("due") or "")[:10],
                            "url": link, "notes": str(item.get("who") or "")})
        return bool(out) and system.launch("tasks", "--add-json", json.dumps(out, ensure_ascii=False))

    @Slot(str, result="QVariantList")
    def parseJson(self, text):
        """Ornis's JSON answer (a list), even with words or code fences around it."""
        start, end = text.find("["), text.rfind("]")
        if start < 0 or end <= start:
            return []
        try:
            data = json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            return []
        return data if isinstance(data, list) else []

    @Slot(str)
    def copy(self, text):
        from PySide6.QtGui import QGuiApplication
        QGuiApplication.clipboard().setText(text)

    def handle_args(self, args, activation_token=""):
        """--room=TOKEN (open a conversation), --call=TOKEN (and join its call), --new (a new conversation),
        --to=USER (the one-to-one with someone, made if needed), --to=ADDRESS [--name=NAME] [--video] (from
        Contacts or Courrier: the account with that address, else a conversation that invites it; --video calls),
        --search=WORDS, a /call/TOKEN link, --agent (no window: calls ring and messages notify)."""
        show = "--agent" not in args
        actions = []
        name = next((a.split("=", 1)[1] for a in args if a.startswith("--name=")), "")
        for arg in args:
            if arg.startswith("--to=") and "@" in arg:
                actions.append(("address", json.dumps({"address": arg[5:], "name": name, "video": "--video" in args})))
            elif arg.startswith(("--room=", "--call=", "--to=", "--search=")):
                key, _, value = arg[2:].partition("=")
                actions.append((key, value))
            elif arg == "--new":
                actions.append(("new", ""))
            elif "/call/" in arg:
                actions.append(("room", arg.rsplit("/call/", 1)[1].split("#")[0].split("?")[0].strip("/") + _message_of(arg)))
        if activation_token:
            os.environ["XDG_ACTIVATION_TOKEN"] = activation_token
        if show:
            self.raiseRequested.emit()
        for action, value in actions:
            self.actionRequested.emit(action, value)

    # ---- words -------------------------------------------------------------------------------------------
    @Slot(str, int, result=str)
    def plural(self, key, count):
        one, _, many = self._t.get(key, "").partition("|")
        text = one if (count <= 1 if self._lang == "fr" else count == 1) or not many else many
        return text.replace("%1", str(count))

    @Slot("QVariantList", result=str)
    def typingText(self, names):
        """« Alex écrit… », « Alex et Sam écrivent… », « Plusieurs personnes écrivent… »."""
        names = [str(n) for n in names if n]
        if not names:
            return ""
        if len(names) == 1:
            return self._t["typing_one"].replace("%1", names[0])
        if len(names) == 2:
            return self._t["typing_two"].replace("%1", names[0]).replace("%2", names[1])
        return self._t["typing_many"]

    @Slot(int, result=str)
    def clock(self, timestamp):
        moment = datetime.fromtimestamp(int(timestamp))
        return moment.strftime("%-I:%M %p").lower() if self._lang == "en" else moment.strftime("%H:%M")

    @Slot(int, result=str)
    def short(self, timestamp):
        """The list of conversations: the time today, « Hier », the weekday this week, else the date."""
        if not timestamp:
            return ""
        moment = datetime.fromtimestamp(int(timestamp))
        days = (date.today() - moment.date()).days
        if days <= 0:
            return self.clock(timestamp)
        if days == 1:
            return self._t["yesterday"]
        if days < 7:
            return self._t["weekdays"].split(",")[moment.weekday()]
        if self._lang == "en":
            return moment.strftime("%m/%d/%y")
        return moment.strftime("%d/%m/%Y") if self._lang == "fr" else moment.strftime("%d.%m.%y")

    @Slot(int, result=str)
    def day(self, timestamp):
        """Between the messages: « Aujourd'hui », « Hier », « mardi 22 octobre » (and the year if not this one)."""
        moment = datetime.fromtimestamp(int(timestamp)).date()
        days = (date.today() - moment).days
        if days == 0:
            return self._t["today"]
        if days == 1:
            return self._t["yesterday"]
        if days == -1:
            return self._t["tomorrow"]
        weekday = self._t["weekdays_long"].split(",")[moment.weekday()]
        month = self._t["months_long"].split(",")[moment.month - 1]
        year = "" if moment.year == date.today().year else f" {moment.year}"
        if self._lang == "en":
            return f"{weekday}, {month} {moment.day}{year}"
        if self._lang == "de":
            return f"{weekday}, {moment.day}. {month}{year}"
        return f"{weekday} {moment.day} {month}{year}"

    @Slot(int, result=str)
    def when(self, timestamp):
        """A moment to come: « 14:30 » today, « demain 09:00 », « jeudi 24 oct. 09:00 »."""
        if not timestamp:
            return ""
        moment = datetime.fromtimestamp(int(timestamp))
        days = (moment.date() - date.today()).days
        if days == 0:
            return self.clock(timestamp)
        if days == 1:
            return self._t["tomorrow"] + " " + self.clock(timestamp)
        return self.day(timestamp) + " " + self.clock(timestamp)

    @Slot(int, result=str)
    def ago(self, timestamp):
        if not timestamp:
            return ""
        delta = time.time() - int(timestamp)
        if delta < 60:
            return self._t["ago_now"]
        if delta < 3600:
            return self._t["ago_minutes"].replace("%1", str(int(delta // 60)))
        if delta < 86400:
            return self._t["ago_hours"].replace("%1", str(int(delta // 3600)))
        return self.short(timestamp)

    @Slot(int, result=str)
    def duration(self, seconds):
        seconds = max(0, int(seconds))
        h, rest = divmod(seconds, 3600)
        m, s = divmod(rest, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

    @Slot(int, result=str)
    def size(self, num):
        return cloud.format_bytes(int(num), self._lang)


def _message_of(url):
    """"#<id>" for a link to one message (…/call/<token>#message_<id>), else "": the conversation opens there."""
    m = re.search(r"#message_(\d+)", str(url))
    return "#" + m.group(1) if m else ""
