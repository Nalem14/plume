"""What the QML sees of the window: the account Connect stored, small preferences, dates in words, links.
(Tâches)

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
from tasks_core.strings import language, strings

CONFIG = cloud.CFG.parent / "tasks.json"
PREFS = {
    "view": "today",             # the list shown last
    "default_list": "",          # where new tasks go from the smart lists
    "collapsed": [],             # tasks whose subtasks are folded
    "mail_todos": True,          # mails tagged « À faire » become tasks
    "notify": True,              # reminders as notifications
    "morning": "09:00",          # « Aujourd'hui » reminders of tasks without a time: the summary of the day
    "summary": True,
    "search_done": False,
    "badge": True,
    "smart_lists": [],           # one's own smart lists: [{id, name, color, tags, lists, match, due, priority, flagged}]
    "tiles": [],                 # the order of the cards of the side column
    "tiles_hidden": [],          # the cards not shown
}
# per list: "sort_<view>" (manual | due | priority | title | created), "show_done_<list>", "sections_<list>" (order)


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
    actionRequested = Signal(str, str)      # "new" | "view" | "search" | "add" | "addjson", value

    def __init__(self):
        super().__init__()
        self._t = strings()
        self._lang = language()
        try:
            self._config = json.loads(CONFIG.read_text())
        except (OSError, json.JSONDecodeError):
            self._config = {}
        if not isinstance(self._config, dict):
            self._config = {}
        self._prefs = dict(PREFS)
        self._prefs.update({k: v for k, v in self._config.items() if k in PREFS or k.startswith(("sort_", "show_done_"))})
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
        if key not in PREFS and not key.startswith(("sort_", "show_done_", "sections_")):
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
            size = [1180, 760]
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
        cloud.open_url(cloud.cloud_link(path or "/apps/tasks/"))

    @Slot(str)
    def openFile(self, path):
        if path and os.path.exists(path):
            system.open_url(path)

    @Slot()
    def openConnect(self):
        system.launch("connect")

    @Slot()
    def openNotes(self):
        system.launch("notes")

    @Slot()
    def openPlume(self):
        system.launch("mail")

    @staticmethod
    def _spawn(cmd):
        system.spawn(cmd)

    def handle_args(self, args, activation_token=""):
        """--show=UID, --new, --view=today|scheduled|…, --search=WORDS, --add TEXT (natural language, from
        KRunner), --add-json JSON (from Notes), --refresh (Plume tagged a mail « À faire »), --agent (no window:
        reminders only)."""
        show = "--agent" not in args
        actions, i = [], 0
        while i < len(args):
            arg = args[i]
            if arg.startswith("--show="):
                actions.append(("show", arg.split("=", 1)[1]))
            elif arg == "--new":
                actions.append(("new", ""))
            elif arg.startswith(("--view=", "--search=")):
                actions.append((arg[2:].split("=", 1)[0], arg.split("=", 1)[1]))
            elif arg == "--refresh":
                actions.append(("refresh", ""))
                show = False
            elif arg in ("--add", "--add-json") and i + 1 < len(args):
                actions.append(("add" if arg == "--add" else "addjson", args[i + 1]))
                show = False
                i += 1
            i += 1
        if activation_token:
            os.environ["XDG_ACTIVATION_TOKEN"] = activation_token
        if show:
            self.raiseRequested.emit()          # first: the window exists for what follows
        for action, value in actions:
            if action == "show":
                self.showRequested.emit(value)
            else:
                self.actionRequested.emit(action, value)

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

    @Property(bool, constant=True)
    def month_first(self):
        """12/11 is the 11th of December in the US, the 12th of November elsewhere."""
        return os.environ.get("LC_TIME", os.environ.get("LANG", "")).startswith("en_US")

    @Slot(int, result=str)
    def clock(self, timestamp):
        moment = datetime.fromtimestamp(int(timestamp))
        return moment.strftime("%-I:%M %p").lower() if self.month_first else moment.strftime("%H:%M")

    def date_short(self, day):
        """« 12 nov. », « Nov 12 », « 12. Nov. » (and the year when it is not this one)."""
        months = self._t["months"].split(",")
        same = day.year == date.today().year
        if self._lang == "en":
            return f"{months[day.month - 1]} {day.day}" + ("" if same else f", {day.year}")
        if self._lang == "de":
            return f"{day.day}. {months[day.month - 1]}" + ("" if same else f" {day.year}")
        return f"{day.day} {months[day.month - 1]}" + ("" if same else f" {day.year}")

    @Slot(str, result=str)
    def dateLabel(self, iso):
        """« mardi 22 octobre » for the editor (iso: 2026-10-22 or 2026-10-22T18:00)."""
        if not iso:
            return ""
        day = date.fromisoformat(iso[:10])
        weekday = self._t["weekdays"].split(",")[day.weekday()]
        delta = (day - date.today()).days
        if delta == 0:
            return self._t["today"]
        if delta == 1:
            return self._t["tomorrow"]
        if delta == -1:
            return self._t["yesterday"]
        return f"{weekday} {self.date_short(day)}"

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
