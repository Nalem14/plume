"""What the QML sees of Plume: the account Connect stored, the current module, the unread count.

The account is the app password of Orneos Connect (cloud.account()). Files it reads are watched, so
connecting, reconnecting or signing out elsewhere shows up here without a restart. The unread count is
the one orneos-notify already writes for the dock (mail.badge): one number for the whole desktop.
"""
import json
import os
import threading
import time
import urllib.parse

from PySide6.QtCore import QFileSystemWatcher, QObject, Property, QSize, Qt, Signal, Slot
from PySide6.QtGui import QGuiApplication

import cloud
import links
import meeting
import system
from qmlvalue import js_property
from plume_core import mime
from plume_core.strings import language, strings

MODULES = ("mail", "calendar", "contacts")
# Plume, the suite, adds the apps it shows as modules (suite.py): notes, tasks, ornis.
# On Orneos OS each of the three is its own app (an edition: Courrier, Agenda, Contacts, `plume --edition=mail`):
# one module, no rail; what belongs to another module opens that app (system.launch).
# small preferences of the window (the mail and Ornis ones live with their module)
PREFS = {"mail_advance": True, "mail_confirm": True, "ornis_asked": False, "ornis_panel": False,
         # Courrier: seconds before an opened message counts as read (0: at once), a warning when the text speaks
         # of an attachment and there is none
         "mail_read_delay": 0, "mail_attach_check": True,
         # Agenda: the view it opens on, the hour its grid shows first, a new event's length (minutes), reminder
         # and calendar (0: the cloud's « Personnel »)
         # and calendar (0: the cloud's « Personnel »), the tasks of Tâches shown on their day
         "cal_view": "week", "cal_day_start": 7, "cal_duration": 60, "cal_reminder": "10", "cal_default": 0,
         "cal_tasks": True}


def initials(name: str) -> str:
    parts = [p for p in name.replace(".", " ").replace("_", " ").split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


class Plume(QObject):
    changed = Signal()
    prefsChanged = Signal()
    settingsRequested = Signal(str)
    accountChanged = Signal()
    unreadChanged = Signal()
    raiseRequested = Signal()
    autostartChanged = Signal()
    toast = Signal(str)
    planRequested = Signal(str)
    eventProposed = Signal("QVariantMap")
    calendarRequested = Signal(str, str)       # "invitations" | "date" | "event" (id|start), value
    filesToSend = Signal("QVariantList")
    composeRequested = Signal(str)
    messageRequested = Signal(str)             # a Message-ID to open (a task of Tâches made from a mail)
    contactRequested = Signal(int)             # a contact id to select (Ctrl+K)
    importRequested = Signal(str)
    actionRequested = Signal(str)              # new_message, new_event, new_contact
    connectionChanged = Signal()
    _profileLoaded = Signal(dict)

    def __init__(self, store, modules=MODULES, edition=""):
        super().__init__()
        self._store = store
        self._t = strings()
        self._lang = language()
        self._edition = edition
        self._modules = [edition] if edition else list(modules)
        module = edition or store.get("module", "mail")
        self._module = module if module in self._modules else self._modules[0]
        self._account = None
        self._profile = {}
        self._unread = 0
        self._last_sync = 0.0
        self._online = {"mail": True, "dav": True}
        self._profileLoaded.connect(self._set_profile)
        self._watcher = QFileSystemWatcher(self)
        self._watcher.directoryChanged.connect(self._files_changed)
        self._watcher.fileChanged.connect(self._files_changed)
        for folder in (cloud.CFG.parent, cloud.STATE):
            folder.mkdir(parents=True, exist_ok=True)
            self._watcher.addPath(str(folder))
        self._files_changed()

    # ---- account and unread count, from the files Connect and orneos-notify keep ------------------------
    def _files_changed(self, *_):
        for path in (cloud.CFG, cloud.TOKEN, cloud.STATE / "mail.badge"):
            if path.exists() and str(path) not in self._watcher.files():
                self._watcher.addPath(str(path))
        account = cloud.account()
        if account != self._account:
            self._account = account
            self._profile = {}
            self.accountChanged.emit()
            if account:
                threading.Thread(target=self._load_profile, args=(account,), daemon=True).start()
        try:
            unread = int((cloud.STATE / "mail.badge").read_text(encoding="utf-8").strip() or 0)
        except (OSError, ValueError):
            unread = 0
        if unread != self._unread:
            self._unread = unread
            self.unreadChanged.emit()

    def _load_profile(self, account):
        info = cloud.userinfo(*account)
        if info:
            self._profileLoaded.emit({
                "name": str(info.get("displayname") or info.get("display-name") or account[1]),
                "email": str(info.get("email") or ""),
            })

    def _set_profile(self, profile):
        self._profile = profile
        self.accountChanged.emit()

    def account(self):
        """(server, user, app password) or None: for the sync workers."""
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
        email = self._profile.get("email") or (user if "@" in user else f"{user}@orneos.eu")
        return {"user": user, "name": name, "email": email, "initials": initials(name)}

    @Property(int, notify=unreadChanged)
    def unread(self):
        return self._unread

    # ---- navigation ---------------------------------------------------------------------------------
    @Property(str, notify=changed)
    def module(self):
        return self._module

    @Property("QVariantList", constant=True)
    def modules(self):
        return self._modules

    @Property(str, constant=True)
    def edition(self):
        """"" for Plume; mail, calendar or contacts for one app of Orneos OS."""
        return self._edition

    @Property(str, constant=True)
    def appName(self):
        return self._t[self._edition] if self._edition else "Plume"

    @Slot(result=str)
    def modifier(self):
        """The key held during a click on a list: "shift" (a range), "ctrl" (one more), or ""."""
        held = QGuiApplication.queryKeyboardModifiers()
        if held & Qt.KeyboardModifier.ShiftModifier:
            return "shift"
        return "ctrl" if held & Qt.KeyboardModifier.ControlModifier else ""

    @Slot(str)
    def setModule(self, module):
        if module in self._modules and module != self._module:
            self._module = module
            self._store.set("module", module)
            self.changed.emit()
        elif module not in self._modules:
            system.launch(module)                  # Orneos OS: Courrier, Agenda or Contacts, their own app

    @Slot(str, str)
    def open(self, module, arg=""):
        """A module, here or in its own app, with what to do there (--new-event…)."""
        self.handle_args(["--" + module] + ([arg] if arg else []))

    @js_property(notify=prefsChanged)
    def prefs(self):
        return {key: self._store.get("pref_" + key, default) for key, default in PREFS.items()}

    @Slot(str, "QVariant")
    def setPref(self, key, value):
        if key in PREFS:
            self._store.set("pref_" + key, value.toVariant() if hasattr(value, "toVariant") else value)
            self.prefsChanged.emit()

    @Slot(str)
    def openSettings(self, section=""):
        self.settingsRequested.emit(section)

    @js_property(constant=True)
    def t(self):
        return self._t

    @Property(str, constant=True)
    def lang(self):
        return self._lang

    @Property(bool, constant=True)
    def noWebEngine(self):
        return os.environ.get("PLUME_NO_WEBENGINE") == "1"

    @Property(str, constant=True)
    def locale(self):
        return {"fr": "fr_FR", "en": "en_GB", "de": "de_DE"}[self._lang]

    @Slot(str)
    def syncFailed(self, kind):
        """A sync or a save went wrong: one short line at the bottom of the window."""
        self.toast.emit(self._t.get("error_" + kind, self._t["error_server"]))

    @Slot(str, bool)
    def reached(self, kind, ok):
        """The mail server ("mail") or the cloud ("dav") answered, or not. Offline is the only state the
        windows show, with when it last answered ("Hors ligne · à jour il y a 5 min")."""
        changed = ok != self._online.get(kind)
        self._online[kind] = ok
        if ok and time.time() - int(self._store.get("reached_" + kind, 0) or 0) > 60:
            self._store.set("reached_" + kind, int(time.time()))
            changed = True
        if changed:
            self.connectionChanged.emit()

    @js_property(notify=connectionChanged)
    def connection(self):
        return {kind: {"online": online, "at": int(self._store.get("reached_" + kind, 0) or 0)}
                for kind, online in self._online.items()}

    @Slot(str, result=str)
    def offlineLine(self, kind):
        """« Hors ligne · à jour il y a 5 min »."""
        at = int(self._store.get("reached_" + kind, 0) or 0)
        if not at:
            return self._t["offline"]
        delta = time.time() - at
        when = (self._t["ago_now"] if delta < 60 else
                self._t["ago_minutes"].replace("%1", str(int(delta // 60))) if delta < 3600 else
                self._t["ago_hours"].replace("%1", str(int(delta // 3600))) if delta < 86400 else
                self._t["ago_days"].replace("%1", str(int(delta // 86400))))
        return self._t["offline"] + " · " + self._t["synced_at"].replace("%1", when)

    def stale(self, seconds):
        now = time.monotonic()
        if now - self._last_sync < seconds:
            return False
        self._last_sync = now
        return True

    def _window_key(self):
        return "window_" + self._edition if self._edition else "window"

    @Property(QSize, constant=True)
    def windowSize(self):
        size = self._store.get(self._window_key(), [1100, 760] if self._edition else [1280, 800])
        return QSize(max(900, int(size[0])), max(580, int(size[1])))

    # set by plume.py before the window: started with the session (tray only), and the window only hides
    background = False
    keep_running = False

    @Property(bool, constant=True)
    def startHidden(self):
        return self.background

    @Property(bool, constant=True)
    def keepRunning(self):
        return self.keep_running

    # opening with the session (Windows, macOS, Linux without Orneos OS): the Settings' switch and the tray's
    @Property(bool, notify=autostartChanged)
    def autostart(self):
        return system.autostart_enabled()

    @Slot(bool)
    def setAutostart(self, on):
        try:
            system.set_autostart(bool(on))
        except OSError as error:
            print(f"plume: autostart: {error}", flush=True)
        self.autostartChanged.emit()

    @Property(bool, constant=True)
    def windowMaximized(self):
        return bool(self._store.get(self._window_key() + "_maximized" if self._edition else "maximized", False))

    @Slot(int, int, bool)
    def saveWindow(self, width, height, maximized):
        if not maximized:
            self._store.set(self._window_key(), [width, height])
        self._store.set(self._window_key() + "_maximized" if self._edition else "maximized", maximized)

    def handle_args(self, args, activation_token=""):
        """Arguments of `plume`, from the command line or a second launch: a module, mailto:, an .ics,
        --invitations, --date=YYYY-MM-DD (from the clock), --message-id=<id> (a task of Tâches),
        --attach FILE… (« Send with Orneos Mail »), orneos://… (a link to a mail, a note or a task),
        --event=<id>|<start>, --plan=<address>, --propose=<json>, --new-message|event|contact.
        Files are attached only through --attach: a mailto: link from a web page never attaches anything.
        What belongs to a module of another app (Courrier, Agenda, Contacts on Orneos OS) is handed to it."""
        files = []
        attaching = False
        shown = False

        def here(module, arg):
            """The module in this window (True), or the argument handed to its own app."""
            nonlocal shown
            if module in self._modules:
                self.setModule(module)
                shown = True
                return True
            system.launch(module, arg)
            return False

        for arg in args:
            if attaching and not arg.startswith("--"):
                path = mime.local_path(arg)
                if os.path.isfile(path):
                    files.append(os.path.abspath(path))
                continue
            attaching = arg == "--attach"
            value = arg.split("=", 1)[1] if "=" in arg else ""
            if arg in ("--background", "--attach"):
                continue                           # started with the session: the tray only
            if arg in ("--mail", "--calendar", "--contacts", "--notes", "--tasks", "--passwords", "--ornis", "--meet"):
                if arg[2:] in self._modules:
                    shown = True
                self.setModule(arg[2:])
            elif arg == "--invitations":
                if here("calendar", arg):
                    self.calendarRequested.emit("invitations", "")
            elif arg.startswith("--message-id="):
                if here("mail", arg):
                    self.messageRequested.emit(value)
            elif arg.startswith("--date="):
                if here("calendar", arg):
                    self.calendarRequested.emit("date", value[:10])
            elif arg.startswith("--event="):
                if here("calendar", arg):
                    self.calendarRequested.emit("event", value)
            elif arg.startswith("--plan="):
                if here("calendar", arg):
                    self.planRequested.emit(value)
            elif arg.startswith("--propose="):
                try:
                    event = json.loads(value)
                except ValueError:
                    continue
                if here("calendar", arg):
                    self.eventProposed.emit(event)
            elif arg in ("--new-message", "--new-event", "--new-contact"):
                if here({"message": "mail", "event": "calendar", "contact": "contacts"}[arg[6:]], arg):
                    self.actionRequested.emit(arg[2:].replace("-", "_"))
            elif arg.lower().startswith("otpauth://"):
                system.launch("passwords", arg)     # a site's two-factor code: Mots de passe sets it up
            elif arg.startswith("orneos://"):
                # Windows and macOS hand Plume the links between mails, notes and tasks (orneos-link on Orneos OS)
                links.open_link(arg)
            elif arg.startswith("mailto:"):
                if here("mail", arg):
                    self.composeRequested.emit(arg)
            elif arg.startswith(("webcal:", "webcals:")):
                # a subscription, kept by the cloud: Agenda asks for its name and colour, then the cloud follows it
                if "calendar" in self._modules or system.has_app("calendar"):
                    if here("calendar", arg):
                        self.calendarRequested.emit("subscribe", arg)
                elif not system.spawn(["/usr/libexec/orneos-open", arg]):
                    cloud.open_url(cloud.cloud_link("/apps/calendar/"))
            elif arg.lower().endswith(".ics"):
                if here("calendar", arg):
                    self.importRequested.emit(arg)
        if files:
            if "mail" in self._modules:
                self.setModule("mail")
                self.filesToSend.emit(files)
                shown = True
            else:
                system.launch("mail", "--attach", *files)
        if activation_token:
            # Qt Wayland hands this token to xdg-activation on the next requestActivate()
            os.environ["XDG_ACTIVATION_TOKEN"] = activation_token
        # nothing for this window (all of it went to another app): it stays where it is
        if "--background" not in args and (shown or not args or not self._edition):
            self.raiseRequested.emit()

    # ---- the rest of the desktop -----------------------------------------------------------------------
    @Slot()
    def openConnect(self):
        system.launch("connect")

    @Slot(str)
    def openCloud(self, path):
        cloud.open_url(cloud.cloud_link(path))

    @Slot(str)
    def compose(self, address):
        """Write to someone (an address or a mailto: link), in Plume's composer."""
        uri = address if address.startswith("mailto:") else "mailto:" + address
        self.handle_args([uri])

    @Slot(str)
    def composeInCloud(self, uri):
        """Mail not connected yet in Plume: the cloud's composer, with the same address."""
        cloud.open_url(cloud.cloud_link("/apps/mail/compose?uri=" + urllib.parse.quote(uri, safe="")))

    @Slot(str)
    def planWith(self, address):
        """A new event with this person as guest (from a contact card)."""
        self.handle_args(["--plan=" + address])

    @Slot("QVariantMap")
    def proposeEvent(self, event):
        """An event found by Ornis (in a message): the calendar opens its editor with it, to check and add."""
        event = event.toVariant() if hasattr(event, "toVariant") else dict(event)
        self.handle_args(["--propose=" + json.dumps(event, default=str)])

    @Slot(int, str)
    def showEvent(self, event_id, start):
        """An event in the calendar (from a mail's invitation): its week, its card open."""
        self.handle_args([f"--event={event_id}|{start}"])

    @Slot(str)
    def openUrl(self, url):
        if meeting.join(url):            # « Rejoindre » an Orneos Meet call: the Meet module or app
            return
        if url.startswith(("https://", "http://")):
            cloud.open_url(url)

    @Slot(str, str, bool)
    def meetWith(self, address, name, video):
        """« Discuter » / « Visio » with a contact or a sender: Meet (its module or app) finds their account."""
        args = [f"--to={address}"] + ([f"--name={name}"] if name else []) + (["--video"] if video else [])
        if not system.launch("meet", *args):
            cloud.open_url(cloud.cloud_link("/apps/spreed/"))

    @Slot(str)
    def copyText(self, text):
        QGuiApplication.clipboard().setText(text)
        self.toast.emit(self.t["copied"])

    @Slot()
    def openAccount(self):
        slug = {"fr": "tableau-de-bord/compte", "en": "dashboard/account", "de": "dashboard/konto"}[self._lang]
        cloud.open_url(f"https://orneos.eu/{self._lang}/{slug}")

    @Slot(str, result="QVariantList")
    def searchAll(self, query):
        """Ctrl+K: unified search across mails, events, contacts, notes, tasks, Meet, and password titles."""
        server = self._account[0] if self._account else ""
        items = links.search_all(query, server, limit=4)
        icons = {"mail": "mail", "event": "calendar", "contact": "contacts", "note": "note",
                 "task": "checklist", "meet": "video", "password": "key"}
        labels = {k: self._t.get(f"palette_kind_{k}", k) for k in icons}
        for it in items:
            it["icon"] = icons.get(it["kind"], "search")
            it["kindLabel"] = labels.get(it["kind"], "")
        return items

    @Slot(str, str, str)
    def openItem(self, kind, ref, url=""):
        """Ctrl+K: open a search result directly in its module or app."""
        if kind == "mail" and ref:
            self.handle_args(["--mail", f"--message-id={ref}"])
        elif kind == "event" and ref:
            self.handle_args(["--calendar", f"--event={ref}"])
        elif kind == "contact" and ref.isdigit():
            if "contacts" in self._modules:
                self.setModule("contacts")
                self.contactRequested.emit(int(ref))
            else:
                system.launch("contacts")
        elif kind == "password" and ref:
            system.launch("passwords", f"--show={ref}")
        elif url:
            links.open_link(url)

    @Slot(str, result="QVariantList")
    def parseLinks(self, payload):
        """Parse an application/x-orneos-link JSON or plain URL into [{url, title, kind}]."""
        return links.decode(payload)

    @Slot(str, str, result=bool)
    def addTaskFromLink(self, title, url):
        """Create a task in Tâches from a dragged mail/note/event."""
        item = {"title": (title or self._t["untitled"]).strip(), "notes": url or ""}
        ok = system.launch("tasks", "--add-json", json.dumps([item]))
        if ok:
            self.toast.emit(self._t.get("task_added", self._t["tasks"]))
        return ok

    @Slot(result="QVariantMap")
    def morningBriefData(self):
        """Gather today's events, top unread inbox mails, and priority open tasks in <20 ms from local caches."""
        from datetime import datetime
        import sqlite3
        now = datetime.now()
        day_start = int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
        day_end = day_start + 86400
        events, mails, tasks_out = [], [], []
        db_path = system.CACHE / "plume.db"
        if db_path.exists():
            try:
                db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=1)
                db.row_factory = sqlite3.Row
                try:
                    for r in db.execute("SELECT id, title, start_ts FROM events WHERE start_ts >= ? AND start_ts < ? "
                                        "ORDER BY start_ts ASC LIMIT 8", (day_start, day_end)):
                        dt = datetime.fromtimestamp(r["start_ts"]).strftime("%H:%M")
                        iso = datetime.fromtimestamp(r["start_ts"]).strftime("%Y-%m-%dT%H:%M")
                        events.append({"id": r["id"], "ref": f"{r['id']}|{iso}", "title": r["title"] or self._t["untitled"], "time": dt})
                    for r in db.execute("SELECT m.message_id, m.subject, m.from_name, m.from_email FROM messages m "
                                        "JOIN mail_folders f ON f.id = m.folder_id "
                                        "WHERE f.role = 'inbox' AND m.seen = 0 ORDER BY m.date_ts DESC LIMIT 5"):
                        mails.append({"ref": r["message_id"], "title": r["subject"] or self._t["subject_empty"],
                                      "from": r["from_name"] or r["from_email"] or ""})
                finally:
                    db.close()
            except sqlite3.Error:
                pass
        t_path = system.DATA / "tasks.db"
        if t_path.exists():
            try:
                tdb = sqlite3.connect(f"file:{t_path}?mode=ro", uri=True, timeout=1)
                tdb.row_factory = sqlite3.Row
                try:
                    for r in tdb.execute("SELECT uid, data FROM tasks WHERE deleted = 0 ORDER BY rowid DESC LIMIT 60"):
                        try:
                            d = json.loads(r["data"] or "{}")
                        except ValueError:
                            continue
                        if d.get("done") or d.get("cancelled") or not d.get("title"):
                            continue
                        due = d.get("due_ts") or 0
                        if due and due > day_end and not d.get("priority"):
                            continue
                        tasks_out.append({"uid": r["uid"], "title": str(d["title"]), "priority": int(d.get("priority") or 0)})
                        if len(tasks_out) >= 5:
                            break
                finally:
                    tdb.close()
            except sqlite3.Error:
                pass
        intro = {
            "fr": f"Fais-moi un brief clair et motivant de ma journée ({now.strftime('%d/%m/%Y')}) :",
            "en": f"Give me a clear, motivating brief for my day ({now.strftime('%Y-%m-%d')}):",
            "de": f"Gib mir ein klares, motivierendes Briefing für meinen Tag ({now.strftime('%d.%m.%Y')}):",
        }[self._lang]
        prompt_parts = [intro]
        if events:
            prompt_parts.append(self._t["brief_events"] + " : " + "; ".join(f"{e['time']} {e['title']}" for e in events))
        if mails:
            prompt_parts.append(self._t["brief_mails"] + " : " + "; ".join(f"{m['title']} ({m['from']})" for m in mails))
        if tasks_out:
            prompt_parts.append(self._t["brief_tasks"] + " : " + "; ".join(t["title"] for t in tasks_out))
        return {"events": events, "mails": mails, "tasks": tasks_out, "prompt": "\n".join(prompt_parts)}

    @Slot(str)
    def askOrnis(self, question):
        # Orneos OS: the top-bar applet (Super+O); Plume: its Ornis module; else the cloud's assistant
        question = question.strip()
        if system.in_process("ornis"):
            system.launch("ornis", *(["--ask=" + question] if question else []))
        elif not system.spawn(["/usr/libexec/orneos-ornis", "--ask", question] if question
                              else ["/usr/libexec/orneos-ornis", "--open"]):
            cloud.open_url(cloud.cloud_link("/apps/assistant/"))

    @staticmethod
    def _spawn(cmd):
        system.spawn(cmd)
