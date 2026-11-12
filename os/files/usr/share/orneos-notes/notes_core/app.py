"""What the QML sees of the window: the account Connect stored, small preferences, dates in words, links.

The account is the app password of Orneos Connect (cloud.account()); its files are watched, so connecting,
reconnecting or signing out elsewhere shows here without a restart.
"""
import json
import os
import time
from datetime import date, datetime

from PySide6.QtCore import QFileSystemWatcher, QObject, Property, QSize, Qt, Signal, Slot
from PySide6.QtGui import QGuiApplication

import cloud
import system
from qmlvalue import js_property
from notes_core.strings import language, strings

CONFIG = cloud.CFG.parent / "notes.json"
PREFS = {
    "sort": "modified",          # modified | created | title
    "group_dates": True,         # Today, Yesterday, Previous 7 days… in the list
    "text_size": 16,             # the editor's body text, in pixels
    "quick_folder": "",          # where Quick Notes go
    "folder": "all",             # the folder shown last
    "expanded": [],              # folders open in the sidebar
    "empty_folders": [],         # folders made here that have no note yet (the cloud only knows folders with notes)
    "spell": True,
    "focus_mode": False,         # « Masquer les colonnes » (Ctrl+Maj+E): the editor alone
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
    showRequested = Signal(str)             # a note to open (KRunner, --show, a link from Tâches)
    actionRequested = Signal(str, str)      # "new" | "quick" | "folder" | "search" | "files", value

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

    # ---- account ---------------------------------------------------------------------------------------
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
        return {"user": user, "name": name, "email": email, "initials": initials(name)}

    # ---- texts, preferences, window --------------------------------------------------------------------
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
            CONFIG.write_text(json.dumps(self._config))
        except OSError:
            pass

    @Property(QSize, constant=True)
    def windowSize(self):
        size = self._config.get("window")
        if not (isinstance(size, list) and len(size) == 2):
            size = [1220, 780]
        return QSize(max(760, int(size[0])), max(500, int(size[1])))

    @Slot(int, int)
    def saveWindow(self, width, height):
        self._config["window"] = [width, height]
        self._write()

    # ---- the rest of the desktop -----------------------------------------------------------------------
    @Slot(str)
    def openUrl(self, url):
        if url.startswith(("https://", "http://", "mailto:")):
            cloud.open_url(url)

    @Slot(str)
    def openCloud(self, path):
        cloud.open_url(cloud.cloud_link(path or "/apps/notes/"))

    @Slot(str)
    def openFile(self, path):
        if path and os.path.exists(path):
            system.open_url(path)

    @Slot()
    def openConnect(self):
        system.launch("connect")

    @Slot()
    def openTasks(self):
        system.launch("tasks")

    @Slot(str)
    def openInOrnis(self, draft):
        system.launch("ornis", f"--draft={str(draft or '').strip()}")

    @Slot(str)
    def compose(self, mailto):
        """A message in Plume (the cloud's Mail without it)."""
        if system.has_app("mail"):
            system.launch("mail", mailto)
        else:
            cloud.open_url(cloud.cloud_link("/apps/mail/compose?uri=" + mailto))

    @staticmethod
    def _spawn(cmd):
        system.spawn(cmd)

    def handle_args(self, args, activation_token=""):
        """--show ID, --new, --quick (Meta+N), --daily (the note of the day), --folder=PATH, --search=WORDS, --files FILE… (« Ajouter à Notes »)."""
        files, taking = [], False
        for arg in args:
            if taking and not arg.startswith("--"):
                path = arg.removeprefix("file://")
                if os.path.exists(path):
                    files.append(os.path.abspath(path))
                continue
            taking = arg == "--files"
            if arg.startswith("--show="):
                self.showRequested.emit(arg.split("=", 1)[1])
            elif arg in ("--new", "--quick", "--daily"):
                self.actionRequested.emit(arg[2:], "")
            elif arg.startswith("--folder="):
                self.actionRequested.emit("folder", arg.split("=", 1)[1])
            elif arg.startswith("--search="):
                self.actionRequested.emit("search", arg.split("=", 1)[1])
        if files:
            self.actionRequested.emit("files", json.dumps(files))
        if activation_token:
            os.environ["XDG_ACTIVATION_TOKEN"] = activation_token
        if "--quick" not in args:
            self.raiseRequested.emit()

    @Slot(result=str)
    def modifier(self):
        """The key held during a click on the list: "shift" (a range), "ctrl" (one more), or ""."""
        held = QGuiApplication.queryKeyboardModifiers()
        if held & Qt.KeyboardModifier.ShiftModifier:
            return "shift"
        return "ctrl" if held & Qt.KeyboardModifier.ControlModifier else ""

    @Slot(str, int, result=str)
    def plural(self, key, count):
        """A count in words: "1 note", "3 notes" (French takes the singular for 0 and 1)."""
        one, _, many = self._t.get(key, "").partition("|")
        text = one if (count <= 1 if self._lang == "fr" else count == 1) or not many else many
        return text.replace("%1", str(count))

    def _day(self, tm):
        months = self._t["months_long"].split(",")
        if self._lang == "en":
            return f"{months[tm.month - 1]} {tm.day}, {tm.year}"
        if self._lang == "de":
            return f"{tm.day}. {months[tm.month - 1]} {tm.year}"
        return f"{tm.day} {months[tm.month - 1]} {tm.year}"

    @Slot(int, result=str)
    def short(self, timestamp):
        """What the list shows: the time today, « Hier », the weekday this week, else the date."""
        if not timestamp:
            return ""
        moment = datetime.fromtimestamp(int(timestamp))
        today = date.today()
        days = (today - moment.date()).days
        if days <= 0:
            return moment.strftime("%H:%M") if self._lang != "en" else moment.strftime("%-I:%M %p").lower()
        if days == 1:
            return self._t["yesterday"]
        if days < 7:
            return self._t["weekdays"].split(",")[moment.weekday()]
        if self._lang == "en":
            return moment.strftime("%m/%d/%y")
        return moment.strftime("%d/%m/%Y") if self._lang == "fr" else moment.strftime("%d.%m.%y")

    @Slot(int, result=str)
    def long(self, timestamp):
        """Above the note: « 20 octobre 2026 à 14:32 »."""
        if not timestamp:
            return ""
        moment = datetime.fromtimestamp(int(timestamp))
        clock = moment.strftime("%H:%M") if self._lang != "en" else moment.strftime("%-I:%M %p")
        return self._t["date_at"].replace("%1", self._day(moment)).replace("%2", clock)

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
