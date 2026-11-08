"""What the QML sees of the tasks: the smart lists (Aujourd'hui, Programmées, Toutes, Avec drapeau,
Terminées, Courrier) and the lists of the account, the rows of the one shown (with their sections and
subtasks), one task, and every change, written to the local copy at once and sent to the cloud behind.

Network calls run on one worker thread (writes keep their order). Sync: at start, every 5 minutes (10 with
no window), a moment after each change, when the window comes back and as soon as the network returns. Each
sync also asks the cloud to bring the mails tagged « À faire » into the tasks (the orneos app does it, for
every device), so they show here at once.
"""
import json
import threading
import time
import traceback
import unicodedata
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

from PySide6.QtCore import QByteArray, QMimeData, QObject, Property, QTimer, Signal, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtNetwork import QNetworkInformation

import cloud
import system
import links
from dragguard import DragGuard
from tasks_core import parse as nl
from tasks_core import todo
from tasks_core.dav import Client, DavError
from tasks_core.store import COLORS, Store

EVERY_MS = 5 * 60 * 1000
UNDO_MS = 6000
LINGER_MS = 1800            # a task just ticked stays a moment, as on macOS
SMART = ("today", "scheduled", "all", "flagged", "completed", "mail")
WEEK = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")
MISSED_S = 36 * 3600         # a reminder missed while the computer was off still shows (marked missed) within this


def fold(text):
    return unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().lower()


def day_of(ts):
    return datetime.fromtimestamp(ts).date() if ts else None


class Library(QObject):
    changed = Signal()               # rows, counts, lists
    viewChanged = Signal()
    stateChanged = Signal()
    created = Signal(str)            # a task to open (from Notes, KRunner)
    done = Signal(str, bool, str)    # what, ok, message
    badge = Signal(int)              # overdue + today: the dock's count
    _sync_finished = Signal(str)
    _ran = Signal(object)
    sharesRead = Signal(str, "QVariantList")   # list href, who has it
    sharees = Signal(str, "QVariantList")      # text typed, accounts and groups found

    def __init__(self, app):
        super().__init__()
        self._drag = DragGuard(self, ['move', 'reorderList', 'setSection', 'reorder', 'flagMany', 'setDue', 'setDoneMany', 'scheduleUndated'])
        self._app = app
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tasks-sync")
        self._store = None
        self._state = "signed_out"
        self._online = True
        self._syncing = False
        self._queued = False
        self._view = app.pref("view") or "today"
        self._query = ""
        self._tasks = {}
        self._lists = []
        self._rows = []
        self._held = {}
        self._undone = None          # (what it was before a tick: {key: ics}, the copies made) for « Annuler »
        self._lingering = {}
        self._last_sync = 0.0
        self._version = None
        self._sync_finished.connect(self._after_sync)
        self._ran.connect(lambda fn: fn())

        self._timer = QTimer(self)
        self._timer.setInterval(EVERY_MS)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self._soon = QTimer(self)
        self._soon.setSingleShot(True)
        self._soon.setInterval(1200)
        self._soon.timeout.connect(self.refresh)
        self._release = QTimer(self)
        self._release.setSingleShot(True)
        self._release.timeout.connect(self._release_held)
        self._linger = QTimer(self)
        self._linger.setSingleShot(True)
        self._linger.timeout.connect(self._end_linger)
        # tasks written by another process (Notes, KRunner, « Ajouter à Tâches »): reloaded, then sent
        self._watch = QTimer(self)
        self._watch.setInterval(2000)
        self._watch.timeout.connect(self._check_outside)
        self._watch.start()
        # at midnight, « Aujourd'hui » becomes another day
        self._day = date.today()

        if QNetworkInformation.loadDefaultBackend() and QNetworkInformation.instance():
            QNetworkInformation.instance().reachabilityChanged.connect(self._reachability)
        app.accountChanged.connect(self._account_changed)
        app.prefsChanged.connect(self._rebuild)
        app.prefsChanged.connect(self._settings_changed)
        self._pushed = None
        self._account_changed()

    # ---- account and state -------------------------------------------------------------------------------
    def store(self):
        return self._store

    def _account_changed(self):
        account = self._app.account()
        user = account[1] if account else None
        if self._store is not None and self._store.user == user:
            return
        if self._store is not None:
            self._store.forget()
            self._store = None
        self._tasks, self._lists = {}, []
        if account is None:
            self._set_state("signed_out")
            self._rebuild()
            return
        self._store = Store(user, default_name=self._app.t["default_list"])
        self._set_state("ready" if self._store.loaded else "loading")
        self._reload()
        threading.Thread(target=self._load_profile, args=(account,), daemon=True).start()
        self.refresh()

    def _load_profile(self, account):
        info = cloud.userinfo(*account)
        if info:
            profile = {"name": str(info.get("displayname") or account[1]), "email": str(info.get("email") or "")}
            self._ran.emit(lambda: self._app.set_profile(profile))

    def _set_state(self, state):
        if state != self._state:
            self._state = state
            self.stateChanged.emit()

    @Property(str, notify=stateChanged)
    def state(self):
        return self._state

    @Property(bool, notify=stateChanged)
    def online(self):
        return self._online

    @Property(bool, notify=stateChanged)
    def syncing(self):
        return self._syncing

    @Property(int, notify=stateChanged)
    def pending(self):
        return self._store.pending_count() if self._store else 0

    @Property(int, notify=stateChanged)
    def syncedAt(self):
        return self._store.synced_at if self._store else 0

    def _reachability(self, reachability):
        if reachability == QNetworkInformation.Reachability.Online:
            self.refresh()

    def set_interval(self, minutes):
        self._timer.setInterval(int(minutes) * 60 * 1000)

    # ---- sync --------------------------------------------------------------------------------------------
    def client(self):
        account = self._app.account()
        if not account:
            return None
        server, user, password = account
        return Client(server + "/remote.php/dav/", user, password)


    # ---- drops of a drag started here (dragguard.py: the model changes once the drag is over, never inside it) ----
    @Slot()
    def dragStarted(self):
        self._drag.started()

    @Slot()
    def dragEnded(self):
        self._drag.ended()

    @Slot(str, "QVariant")
    def afterDrag(self, method, args):
        self._drag.call(method, args)

    @Slot()
    def refresh(self):
        if self._store is None:
            return
        if self._syncing:
            self._queued = True
            return
        self._syncing = True
        self._last_sync = time.monotonic()
        self.stateChanged.emit()
        store, client, account = self._store, self.client(), self._app.account()
        store.hold = tuple(self._held)

        def run():
            error = ""
            try:
                self._mail_bridge(account)
                store.sync(client, report=self._refused)
            except DavError as e:
                error = "offline" if e.status == 0 else "auth" if e.status == 401 else "server"
            except Exception:
                traceback.print_exc()
                error = "server"
            finally:
                client.close()
            self._sync_finished.emit(error)
        self._pool.submit(run)

    def _mail_bridge(self, account):
        """The mails tagged « À faire » become tasks (and the other way round), in the cloud: the orneos app
        does it for every device; asking here makes it immediate. Without the app (older cloud): nothing."""
        if not account or self._app.pref("mail_todos") is False:
            return
        server, user, password = account
        status, _ = cloud.rest(server, user, password, "/index.php/apps/orneos/api/mail-todos/sync", method="POST", body={})
        if status == 0:
            raise DavError(0, "offline")

    def stale(self, seconds):
        return time.monotonic() - self._last_sync > seconds

    def _refused(self, title, error):
        self._ran.emit(lambda: self.done.emit("sync", False, self._app.t["sync_refused"].replace("%1", title)))

    def _after_sync(self, error):
        self._syncing = False
        was_online = self._online
        self._online = error != "offline"
        if self._store is None:
            return
        if error and not self._store.loaded:
            self._set_state("offline_first" if error == "offline" else "error_first")
        else:
            self._set_state("ready")
        if error == "auth":
            self.done.emit("sync", False, self._app.t["error_auth"])
        elif error == "offline" and was_online and self._store.pending_count():
            self._app.toast.emit(self._app.t["offline_saved"])
        self.stateChanged.emit()
        self._reload()
        if not error:
            self._settings_changed()
        if self._queued:
            self._queued = False
            self.refresh()

    def _settings_changed(self):
        """The mails « À faire » follow the settings of Tâches: on or off, and the default list (the cloud's
        orneos app reads them, for every device)."""
        href = self.defaultList
        wanted = (self._app.pref("mail_todos") is not False, href.rstrip("/").rsplit("/", 1)[-1] if href and not href.startswith("local:") else "")
        account = self._app.account()
        if wanted == self._pushed or account is None:
            return
        self._pushed = wanted
        server, user, password = account

        def run():
            status, _ = cloud.rest(server, user, password, "/index.php/apps/orneos/api/mail-todos/settings", method="PUT",
                                   body={"enabled": wanted[0], "list": wanted[1]})
            if status != 200:
                self._ran.emit(lambda: setattr(self, "_pushed", None))   # told again next time
        threading.Thread(target=run, daemon=True).start()

    def _check_outside(self):
        if self._store is None:
            return
        if date.today() != self._day:
            self._day = date.today()
            self._rebuild()
        version = self._store.version()
        if self._version is not None and version != self._version and not self._syncing:
            self._reload()
            if self._store.pending_count():
                self._soon.start()
        self._version = version

    def shutdown(self):
        self._pool.shutdown(wait=False, cancel_futures=True)

    # ---- reading the copy ------------------------------------------------------------------------------------
    def _reload(self):
        if self._store is None:
            self._tasks, self._lists = {}, []
        else:
            self._tasks = {t["key"]: t for t in self._store.tasks()}
            self._lists = self._store.lists()
            self._version = self._store.version()
        self._rebuild()

    def tasks_now(self):
        return dict(self._tasks)

    def _list_info(self, href):
        return next((l for l in self._lists if l["href"] == href), None) or {"name": "", "color": COLORS[0], "readonly": 0}

    def _open(self, t):
        return not t.get("done") and not t.get("cancelled")

    def _today_end(self):
        return int(datetime.combine(date.today() + timedelta(days=1), datetime.min.time()).timestamp())

    def _in_view(self, t, view):
        if view == "completed":
            return bool(t.get("done"))
        if not self._open(t) and t["key"] not in self._lingering:
            if not (view.startswith("list:") and self._app.pref("show_done_" + view[5:])):
                return False
        if view == "today":
            return 0 < t.get("due_ts", 0) < self._today_end()
        if view == "scheduled":
            return t.get("due_ts", 0) > 0
        if view == "flagged":
            return bool(t.get("flagged"))
        if view == "mail":
            return bool(t.get("mail"))
        if view.startswith("list:"):
            return t["list"] == view[5:]
        if view.startswith("tag:"):
            return view[4:] in [x.lower() for x in t.get("tags") or []]
        if view.startswith("smart:"):
            rule = self._smart(view[6:])
            return bool(rule) and self._matches(t, rule)
        return True

    # ---- one's own smart lists: tags, date, priority, flag, lists; all the conditions or any of them ----------
    def _smart_lists(self):
        return [s for s in (self._app.pref("smart_lists") or []) if isinstance(s, dict) and s.get("id")]

    def _smart(self, sid):
        return next((s for s in self._smart_lists() if s["id"] == sid), None)

    def _matches(self, t, rule):
        tests = []
        tags = [str(x).lower() for x in rule.get("tags") or []]
        if tags:
            mine = [x.lower() for x in t.get("tags") or []]
            tests.append(any(x in mine for x in tags))
        due = rule.get("due") or ""
        if due:
            ts, end = t.get("due_ts", 0), self._today_end()
            tests.append({"none": not ts, "any": bool(ts), "overdue": 0 < ts < end - 86400 and self._open(t),
                          "today": 0 < ts < end, "week": 0 < ts < end + 6 * 86400}.get(due, True))
        priority = int(rule.get("priority") or 0)
        if priority:
            p = t.get("priority") or 0
            tests.append(0 < p <= {9: 9, 5: 5, 1: 4}.get(priority, 9))
        if rule.get("flagged"):
            tests.append(bool(t.get("flagged")))
        lists = rule.get("lists") or []
        if lists:
            tests.append(t["list"] in lists)
        if not tests:
            return True
        return any(tests) if rule.get("match") == "any" else all(tests)

    @Property("QVariantList", notify=changed)
    def smartLists(self):
        return self._smart_lists()

    @Slot("QVariantMap", result=str)
    def saveSmartList(self, rule):
        """A smart list made or changed (kept with the settings of Tâches, on this computer)."""
        rule = self._clean(rule)
        rule = {k: (list(v.toVariant()) if hasattr(v, "toVariant") else v) for k, v in rule.items()}
        if not str(rule.get("name") or "").strip():
            return ""
        sid = str(rule.get("id") or "") or "s" + format(int(time.time() * 1000) % 10 ** 10, "x")
        rule.update(id=sid, name=str(rule["name"]).strip())
        lists = [s for s in self._smart_lists() if s["id"] != sid]
        at = next((i for i, s in enumerate(self._smart_lists()) if s["id"] == sid), len(lists))
        lists.insert(at, rule)
        self._app.setPref("smart_lists", lists)
        self.setView("smart:" + sid)
        self.viewChanged.emit()
        return sid

    @Slot(str)
    def deleteSmartList(self, sid):
        self._app.setPref("smart_lists", [s for s in self._smart_lists() if s["id"] != sid])
        if self._view == "smart:" + sid:
            self.setView("today")

    # ---- the cards of the side column: in one's order, some hidden ----------------------------------------------
    @Property("QVariantList", notify=changed)
    def tiles(self):
        order = [v for v in (self._app.pref("tiles") or []) if v in SMART]
        order += [v for v in SMART if v not in order]
        hidden = set(self._app.pref("tiles_hidden") or [])
        return [{"view": v, "shown": v not in hidden} for v in order]

    @Slot(str, bool)
    def setTileShown(self, view, shown):
        hidden = [v for v in (self._app.pref("tiles_hidden") or []) if v != view]
        self._app.setPref("tiles_hidden", hidden if shown else hidden + [view])

    @Slot(str, int)
    def moveTile(self, view, step):
        order = [t["view"] for t in self.tiles]
        i = order.index(view)
        j = max(0, min(len(order) - 1, i + step))
        order.insert(j, order.pop(i))
        self._app.setPref("tiles", order)

    # ---- sections of a list (X-ORNEOS-SECTION on its tasks; their order kept here) -------------------------------
    def _sections(self, href):
        known = [str(x) for x in (self._app.pref("sections_" + href) or [])]
        found = sorted({t.get("section") for t in self._tasks.values() if t["list"] == href and t.get("section")} - set(known), key=fold)
        return known + found

    @Slot(str, result="QVariantList")
    def sections(self, href):
        return self._sections(href)

    @Slot(str, str)
    def addSection(self, href, name):
        name = name.strip()
        if name and name not in self._sections(href):
            self._app.setPref("sections_" + href, self._sections(href) + [name])

    @Slot(str, str, str)
    def renameSection(self, href, old, name):
        name = name.strip()
        if not name or name == old:
            return
        self._app.setPref("sections_" + href, [name if s == old else s for s in self._sections(href) if s != name])
        for t in list(self._tasks.values()):
            if t["list"] == href and t.get("section") == old and self._store:
                self._store.edit(t["key"], {"section": name})
        self._changed_here()

    @Slot(str, str)
    def deleteSection(self, href, name):
        """The section goes; its tasks stay in the list, out of any section."""
        self._app.setPref("sections_" + href, [s for s in self._sections(href) if s != name])
        for t in list(self._tasks.values()):
            if t["list"] == href and t.get("section") == name and self._store:
                self._store.edit(t["key"], {"section": ""})
        self._changed_here()

    @Slot(str, str, int)
    def nudgeSection(self, href, name, step):
        order = self._sections(href)
        if name not in order:
            return
        i = order.index(name)
        j = max(0, min(len(order) - 1, i + step))
        order.insert(j, order.pop(i))
        self._app.setPref("sections_" + href, order)

    @Slot("QVariantList", str)
    def setSection(self, keys, name):
        for key in keys:
            t = self._tasks.get(key)
            if t and self._store:
                self._store.edit(key, {"section": name})
                for child in self._descendants(t):
                    self._store.edit(child, {"section": name})
        self._changed_here()

    # ---- the sidebar -------------------------------------------------------------------------------------------
    @Property("QVariantMap", notify=changed)
    def counts(self):
        tasks = [t for t in self._tasks.values() if not t.get("cancelled")]
        open_ = [t for t in tasks if not t.get("done")]
        end = self._today_end()
        start = end - 86400
        out = {
            "today": sum(1 for t in open_ if 0 < t.get("due_ts", 0) < end),
            "overdue": sum(1 for t in open_ if 0 < t.get("due_ts", 0) < start),
            "scheduled": sum(1 for t in open_ if t.get("due_ts", 0)),
            "all": len(open_),
            "flagged": sum(1 for t in open_ if t.get("flagged")),
            "completed": sum(1 for t in tasks if t.get("done")),
            # the ring of « Aujourd'hui »: done since midnight
            "done_today": sum(1 for t in tasks if t.get("done") and t.get("done_ts", 0) >= start and 0 < t.get("due_ts", 0) < end),
            "mail": sum(1 for t in open_ if t.get("mail")),
        }
        for l in self._lists:
            out["list:" + l["href"]] = sum(1 for t in open_ if t["list"] == l["href"])
        for rule in self._smart_lists():
            out["smart:" + rule["id"]] = sum(1 for t in open_ if self._matches(t, rule))
        return out

    @Property("QVariantList", notify=changed)
    def lists(self):
        return [{"href": l["href"], "name": l["name"], "color": l["color"] or COLORS[0], "readonly": bool(l["readonly"]),
                 "shared": bool(l["shared"]), "owner": l["owner"], "events": bool(l["events"]),
                 "pending": l["state"] != ""} for l in self._lists]

    @Property("QVariantList", notify=changed)
    def writableLists(self):
        return [l for l in self.lists if not l["readonly"]]

    @Property("QVariantList", notify=changed)
    def tags(self):
        counts = {}
        for t in self._tasks.values():
            if self._open(t):
                for tag in t.get("tags") or []:
                    counts[tag.lower()] = counts.get(tag.lower(), 0) + 1
        return [{"tag": k, "count": v} for k, v in sorted(counts.items(), key=lambda x: (-x[1], x[0]))][:30]

    @Property(str, notify=changed)
    def defaultList(self):
        if self._store is None:
            return ""
        lists = [l for l in self._lists if not l["readonly"]]
        preferred = self._app.pref("default_list")
        if any(l["href"] == preferred for l in lists):
            return preferred
        return next((l["href"] for l in lists if not l["events"]), lists[0]["href"] if lists else "")

    # ---- the rows ------------------------------------------------------------------------------------------
    @Property(str, notify=viewChanged)
    def view(self):
        return self._view

    @Slot(str)
    def setView(self, view):
        if view != self._view:
            self._view = view
            if not view.startswith("tag:"):
                self._app.setPref("view", view)
            self._rebuild()
            self.viewChanged.emit()

    @Property(str, notify=changed)
    def query(self):
        return self._query

    @Slot(str)
    def setQuery(self, query):
        if query != self._query:
            self._query = query
            self._rebuild()
            self.viewChanged.emit()

    @Property("QVariantMap", notify=viewChanged)
    def heading(self):
        v = self._view
        t = self._app.t
        if self._query:
            return {"title": t["results"], "color": "#5B6B82", "icon": "search"}
        smart = {"today": ("#002FA7", "today"), "scheduled": ("#C8381E", "calendar"), "all": ("#0F2440", "inbox"),
                 "flagged": ("#F0A202", "flag"), "completed": ("#5B6B82", "done"), "mail": ("#1A5F7A", "mail")}
        if v in smart:
            return {"title": t["view_" + v], "color": smart[v][0], "icon": smart[v][1], "smart": True}
        if v.startswith("tag:"):
            return {"title": "#" + v[4:], "color": "#2F7D6D", "icon": "hash"}
        if v.startswith("smart:"):
            rule = self._smart(v[6:]) or {}
            return {"title": rule.get("name", ""), "color": rule.get("color") or "#5B6B82", "icon": "sort", "custom": True, "id": v[6:]}
        info = self._list_info(v[5:])
        return {"title": info["name"], "color": info["color"] or COLORS[0], "icon": "list", "readonly": bool(info["readonly"]),
                "owner": info.get("owner", ""), "list": v[5:]}

    def _due_label(self, t):
        if not t.get("due_ts"):
            return "", ""
        moment = datetime.fromtimestamp(t["due_ts"])
        day = moment.date()
        today = date.today()
        delta = (day - today).days
        tt = self._app.t
        clock = "" if t.get("all_day") else self._app.clock(t["due_ts"])
        if delta == 0:
            label = tt["today"]
        elif delta == 1:
            label = tt["tomorrow"]
        elif delta == -1:
            label = tt["yesterday"]
        elif 1 < delta < 7:
            label = tt["weekdays"].split(",")[day.weekday()]
        else:
            label = self._app.date_short(day)
        overdue = (moment < datetime.now()) if not t.get("all_day") else day < today
        state = "overdue" if overdue and self._open(t) else ("today" if delta == 0 else "")
        return (f"{label}, {clock}" if clock else label), state

    def _row(self, t, depth=0, children=(), section="", label="", color=""):
        info = self._list_info(t["list"])
        due, due_state = self._due_label(t)
        kids = [c for c in children]
        return {
            "key": t["key"], "uid": t.get("uid", ""), "title": t.get("title") or "", "notes": (t.get("notes") or "").split("\n")[0][:140],
            "due": due, "dueState": due_state, "dueTs": t.get("due_ts", 0), "allDay": bool(t.get("all_day")),
            "done": bool(t.get("done")), "flagged": bool(t.get("flagged")),
            "priority": {1: 3, 2: 3, 3: 3, 4: 3, 5: 2, 6: 1, 7: 1, 8: 1, 9: 1}.get(t.get("priority") or 0, 0),
            "tags": t.get("tags") or [], "repeat": t.get("repeat", ""), "alarm": bool(t.get("alarms")),
            "mail": bool(t.get("mail")), "mailFrom": t.get("mail_from", ""), "note": t.get("note", ""), "url": t.get("url", ""),
            "list": t["list"], "listName": info["name"], "listColor": info["color"] or COLORS[0], "readonly": bool(info["readonly"]),
            "pending": bool(t.get("pending")), "depth": depth, "children": len(kids),
            "childrenOpen": sum(1 for c in kids if self._open(c)), "collapsed": t["key"] in (self._app.pref("collapsed") or []),
            "parent": t.get("parent", ""), "section": section, "sectionLabel": label, "sectionColor": color,
            "lingering": t["key"] in self._lingering, "taskSection": t.get("section", ""),
            "links": [{"url": l["url"], "title": l.get("title") or "", "icon": links.ICONS.get(links.parse(l["url"])[0], "link")}
                      for l in (t.get("links") or [])[:3]],
        }

    def _section_row(self, href, name, key):
        """An empty section still shows: a row with no task, only there for its header."""
        return {"key": "~section:" + name, "empty": True, "title": "", "section": key, "sectionLabel": name, "sectionColor": "", "list": href,
                "depth": 0, "readonly": bool(self._list_info(href)["readonly"])}

    def _sort_key(self, sort):
        if sort == "due":
            return lambda t: (t.get("due_ts") or 2 ** 40, t.get("sort") or 0, fold(t.get("title")))
        if sort == "priority":
            return lambda t: ((t.get("priority") or 10), t.get("due_ts") or 2 ** 40, fold(t.get("title")))
        if sort == "title":
            return lambda t: fold(t.get("title"))
        if sort == "created":
            return lambda t: -(t.get("created") or 0)
        return lambda t: (t.get("sort") is None, t.get("sort") or 0, t.get("created") or 0)

    def _tree(self, tasks, sort, section="", label="", color=""):
        """Rows with each subtask under its parent (when the parent is in the same rows)."""
        by_uid = {t.get("uid"): t for t in tasks}
        kids = {}
        for t in tasks:
            if t.get("parent") in by_uid:
                kids.setdefault(t["parent"], []).append(t)
        all_kids = {}
        for t in self._tasks.values():
            if t.get("parent"):
                all_kids.setdefault(t["parent"], []).append(t)
        collapsed = set(self._app.pref("collapsed") or [])
        out = []

        def walk(t, depth):
            out.append(self._row(t, depth, all_kids.get(t.get("uid"), []), section, label, color))
            if t["key"] in collapsed:
                return
            for child in sorted(kids.get(t.get("uid"), []), key=self._sort_key(sort)):
                walk(child, depth + 1)
        for t in sorted([t for t in tasks if t.get("parent") not in by_uid], key=self._sort_key(sort)):
            walk(t, 0)
        return out

    def _rebuild(self):
        words = fold(self._query).split()
        view = "all" if words else self._view
        tt = self._app.t
        if words:
            # the title, the notes, the tags, the place and the name of the list; done ones when asked
            chosen = [t for t in self._tasks.values() if not t.get("cancelled") and (self._open(t) or self._app.pref("search_done"))
                      and all(w in fold(" ".join([t.get("title", ""), t.get("notes", ""), " ".join(t.get("tags") or []),
                                                   t.get("location", ""), self._list_info(t["list"])["name"]])) for w in words)]
        else:
            chosen = [t for t in self._tasks.values() if self._in_view(t, view)]
        sort = self._app.pref("sort_" + (view[5:] if view.startswith("list:") else view)) or ("due" if view in ("today", "scheduled") else "manual")
        rows = []
        if view in ("today", "scheduled"):
            today = date.today()
            groups = {}
            for t in chosen:
                day = day_of(t["due_ts"])
                if day < today and self._open(t):
                    key, label = "0", tt["overdue"]
                elif view == "today":
                    # the day as it goes: the ones without a time, then morning, afternoon, evening
                    hour = datetime.fromtimestamp(t["due_ts"]).hour
                    key, label = ("1", "") if t.get("all_day") else ("2", tt["morning"]) if hour < 12 else \
                        ("3", tt["afternoon"]) if hour < 18 else ("4", tt["evening"])
                else:
                    delta = (day - today).days
                    if delta <= 0:
                        key, label = "1", tt["today"]
                    elif delta == 1:
                        key, label = "2", tt["tomorrow"]
                    elif delta < 7:
                        key, label = f"3{delta}", tt["weekdays"].split(",")[day.weekday()].capitalize() + " " + str(day.day)
                    elif day.year == today.year:
                        key, label = f"4{day.month:02d}", tt["months_long"].split(",")[day.month - 1].capitalize()
                    else:
                        key, label = f"5{day.year}", str(day.year)
                groups.setdefault((key, label), []).append(t)
            if view == "today" and ("1", "") in groups and len(groups) > 1:
                groups[("1", tt["all_day_section"])] = groups.pop(("1", ""))
            for (key, label), tasks in sorted(groups.items()):
                tasks.sort(key=lambda t: (t["due_ts"], 1 if t.get("all_day") else 0, t.get("sort") or 0))
                rows += [self._row(t, 0, [], key, label, "#C8381E" if key == "0" else "") for t in tasks]
        elif view == "completed":
            chosen.sort(key=lambda t: -(t.get("done_ts") or 0))
            today = date.today()
            for t in chosen:
                day = day_of(t.get("done_ts")) or today
                delta = (today - day).days
                label = tt["today"] if delta <= 0 else tt["yesterday"] if delta == 1 else \
                    tt["previous_7"] if delta < 7 else tt["months_long"].split(",")[day.month - 1].capitalize() + \
                    ("" if day.year == today.year else f" {day.year}")
                rows.append(self._row(t, 0, [], label, label))
        elif view.startswith("list:"):
            open_ = [t for t in chosen if self._open(t) or t["key"] in self._lingering]
            names = self._sections(view[5:])
            if names:
                # out of any section first, then each section in its order (a subtask stays under its parent)
                by_uid = {t.get("uid"): t for t in open_}

                def root(t):
                    seen = 0
                    while t.get("parent") in by_uid and seen < 20:
                        t, seen = by_uid[t["parent"]], seen + 1
                    return t
                groups = {}
                for t in open_:
                    groups.setdefault(root(t).get("section") or "", []).append(t)
                rows = self._tree(groups.pop("", []), sort)
                for i, name in enumerate(names):
                    rows += self._tree(groups.get(name, []), sort, f"s{i:03d}", name) or \
                        [self._section_row(view[5:], name, f"s{i:03d}")]
            else:
                rows = self._tree(open_, sort)
            done = [t for t in chosen if not self._open(t) and t["key"] not in self._lingering]
            if done:
                done.sort(key=lambda t: -(t.get("done_ts") or 0))
                rows += [self._row(t, 0, [], "~done", tt["completed_section"]) for t in done]
        else:
            # Toutes, Avec drapeau, Courrier, a tag, a search: by list, in the order of the sidebar
            order = {l["href"]: i for i, l in enumerate(self._lists)}
            for href in sorted({t["list"] for t in chosen}, key=lambda h: order.get(h, 999)):
                info = self._list_info(href)
                part = [t for t in chosen if t["list"] == href]
                rows += self._tree(part, sort if view == "all" else sort, f"{order.get(href, 999):03d}", info["name"], info["color"])
        self._rows = rows
        self.changed.emit()
        self.badge.emit(self.counts.get("today", 0))

    @Property("QVariantList", notify=changed)
    def rows(self):
        return self._rows

    @Property(bool, notify=changed)
    def showDone(self):
        return bool(self._view.startswith("list:") and self._app.pref("show_done_" + self._view[5:]))

    @Slot()
    def toggleShowDone(self):
        if self._view.startswith("list:"):
            key = "show_done_" + self._view[5:]
            self._app.setPref(key, not self._app.pref(key))

    @Property(bool, notify=changed)
    def searchDone(self):
        return bool(self._app.pref("search_done"))

    @Slot()
    def toggleSearchDone(self):
        self._app.setPref("search_done", not self._app.pref("search_done"))

    @Property(str, notify=changed)
    def sort(self):
        v = self._view
        return self._app.pref("sort_" + (v[5:] if v.startswith("list:") else v)) or ("due" if v in ("today", "scheduled") else "manual")

    @Slot(str)
    def setSort(self, sort):
        v = self._view
        self._app.setPref("sort_" + (v[5:] if v.startswith("list:") else v), sort)

    # ---- one task ------------------------------------------------------------------------------------------
    @Slot(str, result="QVariantMap")
    def detail(self, key):
        t = self._tasks.get(key)
        if not t:
            return {}
        info = self._list_info(t["list"])
        subtasks = [self._row(c) for c in sorted((c for c in self._tasks.values() if c.get("parent") == t.get("uid") and c.get("uid")),
                                                 key=self._sort_key("manual"))]
        parent = next((p for p in self._tasks.values() if t.get("parent") and p.get("uid") == t["parent"]), None)
        due, state = self._due_label(t)
        return {**self._row(t), "notesFull": t.get("notes") or "", "dueValue": t.get("due") or "", "dueLabel": due,
                "dueState": state, "alarmKey": t.get("alarm") or "", "repeatKey": t.get("repeat") or "",
                "priorityValue": t.get("priority") or 0, "location": t.get("location", ""), "subtasks": subtasks,
                "parentKey": parent["key"] if parent else "", "parentTitle": parent.get("title", "") if parent else "",
                "created": t.get("created", 0), "modified": t.get("modified", 0), "listName": info["name"],
                "mailId": t.get("mail", ""), "doneTs": t.get("done_ts", 0), "links": self._shown_links(t),
                "rrule": t.get("rrule", ""), "repeatText": self.describeRule(t.get("rrule") if t.get("repeat") == "CUSTOM" else t.get("repeat", "")),
                "alarmText": self._alarm_text(t), "alarmAt": self._alarm_at(t)}

    def _alarm_text(self, t):
        """A reminder the presets do not say: its moment (or how many there are)."""
        alarms = t.get("alarms") or []
        if t.get("alarm") != "custom" or not alarms:
            return ""
        if len(alarms) > 1:
            return self._app.plural("reminder_several", len(alarms))
        return self._app.long(alarms[0]["at"])

    def _alarm_at(self, t):
        alarms = t.get("alarms") or []
        return datetime.fromtimestamp(alarms[0]["at"]).strftime("%Y-%m-%dT%H:%M") if alarms else ""

    # ---- repeats in words, and the parts of one for its editor ------------------------------------------------
    @Slot(str, result=str)
    def describeRule(self, value):
        """« Toutes les 2 semaines, lun., jeu. · jusqu'au 12 déc. » from a preset or an RRULE."""
        tt = self._app.t
        value = str(value or "")
        if not value:
            return ""
        if value in todo.REPEATS:
            return tt["repeat_" + value.lower()]
        parts = todo.rule_parts(value)
        unit = {"DAILY": "every_days", "WEEKLY": "every_weeks", "MONTHLY": "every_months", "YEARLY": "every_years"}.get(parts.get("FREQ", ""))
        if not unit:
            return tt["repeat_custom"]
        interval = int(parts.get("INTERVAL") or 1) if str(parts.get("INTERVAL") or "1").isdigit() else 1
        text = self._app.plural(unit, interval)
        days = [d[-2:] for d in (parts.get("BYDAY") or "").split(",") if d[-2:] in WEEK]
        if days and parts["FREQ"] == "WEEKLY":
            if sorted(days, key=WEEK.index) == list(WEEK[:5]):
                text += ", " + tt["repeat_on_weekdays"]
            else:
                names = tt["weekdays_short"].split(",")
                text += ", " + ", ".join(names[WEEK.index(d)] for d in sorted(days, key=WEEK.index))
        monthday = parts.get("BYMONTHDAY", "")
        if monthday.isdigit() and parts["FREQ"] == "MONTHLY":
            text += ", " + tt["repeat_on_day"].replace("%1", monthday)
        count = parts.get("COUNT", "")
        until = parts.get("UNTIL", "")
        if count.isdigit():
            text += " · " + self._app.plural("repeat_times", int(count))
        elif len(until) >= 8:
            try:
                text += " · " + tt["repeat_until"].replace("%1", self._app.date_short(date(int(until[:4]), int(until[4:6]), int(until[6:8]))))
            except ValueError:
                pass
        return text

    @Slot(str, result="QVariantMap")
    def ruleParts(self, value):
        """What the repeat editor shows: {freq, interval, days: ["MO"…], end: never|until|count, until: ISO, count}."""
        value = str(value or "")
        rule = todo.REPEATS.get(value, value)
        parts = todo.rule_parts(rule) if rule.startswith("FREQ=") else {}
        until = parts.get("UNTIL", "")
        until_iso = f"{until[:4]}-{until[4:6]}-{until[6:8]}" if len(until) >= 8 else ""
        return {"freq": parts.get("FREQ") or "WEEKLY", "interval": int(parts.get("INTERVAL") or 1) if str(parts.get("INTERVAL") or "1").isdigit() else 1,
                "days": [d[-2:] for d in (parts.get("BYDAY") or "").split(",") if d[-2:] in WEEK],
                "end": "count" if parts.get("COUNT") else "until" if until else "never",
                "until": until_iso, "count": int(parts["COUNT"]) if str(parts.get("COUNT") or "").isdigit() else 5}

    @Slot(str, "QVariantMap", result=str)
    def buildRule(self, key, choice):
        """The RRULE of the editor's choice (a preset when it is one): freq, interval, days, end, until, count."""
        choice = self._clean(choice)
        freq = str(choice.get("freq") or "WEEKLY")
        interval = max(1, int(choice.get("interval") or 1))
        parts = [f"FREQ={freq}"]
        if interval > 1:
            parts.append(f"INTERVAL={interval}")
        days = [d for d in WEEK if d in list(choice.get("days") or [])]
        if freq == "WEEKLY" and days:
            parts.append("BYDAY=" + ",".join(days))
        end = choice.get("end")
        if end == "count":
            parts.append(f"COUNT={max(1, int(choice.get('count') or 1))}")
        elif end == "until" and choice.get("until"):
            day = date.fromisoformat(str(choice["until"])[:10])
            t = self._tasks.get(key) or {}
            if t.get("due") and "T" in t["due"]:
                end_utc = datetime.combine(day, datetime.max.time().replace(microsecond=0)).astimezone(timezone.utc)
                parts.append("UNTIL=" + end_utc.strftime("%Y%m%dT%H%M%SZ"))
            else:
                parts.append("UNTIL=" + day.strftime("%Y%m%d"))
        rule = ";".join(parts)
        return next((k for k, v in todo.REPEATS.items() if v == rule), rule)

    def _align(self, due, rule):
        """The date moved to the first day the rule allows (a weekly repeat on Tuesdays and Thursdays starting on a
        Wednesday begins on Thursday), with its time."""
        parts = todo.rule_parts(rule)
        try:
            day = date.fromisoformat(due[:10])
        except ValueError:
            return due
        days = [d[-2:] for d in (parts.get("BYDAY") or "").split(",") if d[-2:] in WEEK]
        if parts.get("FREQ") == "WEEKLY" and days:
            for _ in range(7):
                if WEEK[day.weekday()] in days:
                    break
                day += timedelta(days=1)
        return day.isoformat() + due[10:]

    # ---- links to mails, notes and tasks (links.py): dropped on a task, picked, shown in its details ---------
    def _server(self):
        account = self._app.account()
        return account[0] if account else ""

    def _shown_links(self, t):
        out = []
        for link in t.get("links") or []:
            kind = links.parse(link["url"])[0]
            title = link.get("title") or links.describe(link["url"])["title"] or link["url"]
            out.append({"url": link["url"], "title": title, "kind": kind, "icon": links.ICONS.get(kind, "link")})
        return out

    def _task_links(self, keys):
        server = self._server()
        return [{"url": links.task_url(server, self._tasks[k].get("href"), self._tasks[k].get("uid", "")), "kind": "task",
                 "title": self._tasks[k].get("title") or ""} for k in keys if k in self._tasks]

    @Slot("QVariantList", result="QVariantMap")
    def dragData(self, keys):
        """A dragged task: its key for the lists and the order, a link for a note, another task or elsewhere."""
        keys = [str(k) for k in (keys.toVariant() if hasattr(keys, "toVariant") else keys)]
        items = self._task_links(keys)
        data = {"orneos/tasks": ",".join(keys)}
        if items:
            data.update({links.MIME: links.encode(items), "text/plain": "\n".join(i["url"] for i in items)})
        return data

    @Slot("QVariantList")
    def copyLinks(self, keys):
        items = self._task_links([str(k) for k in (keys.toVariant() if hasattr(keys, "toVariant") else keys)])
        if items:
            data = QMimeData()
            data.setData(links.MIME, QByteArray(links.encode(items).encode()))
            data.setText("\n".join(i["url"] for i in items))
            QGuiApplication.clipboard().setMimeData(data)
            self._app.toast.emit(self._app.t["link_copied"])

    def _add_links(self, key, items):
        t = self._tasks.get(key)
        if not t or not items:
            return False
        own = {i["url"] for i in self._task_links([key])}
        current = list(t.get("links") or [])
        known = {l["url"] for l in current}
        fresh = [{"url": i["url"], "title": i.get("title") or links.describe(i["url"])["title"]}
                 for i in items if i["url"] not in known and i["url"] not in own]
        if fresh:
            self.edit(key, {"links": current + fresh})
        return bool(fresh)

    @Slot(str, str, result=bool)
    def addLinks(self, key, payload):
        """Mails, notes or tasks dropped on a task (or picked): linked to it."""
        return self._add_links(key, links.decode(payload))

    @Slot(str, result=bool)
    def pasteLinks(self, key):
        data = QGuiApplication.clipboard().mimeData()
        if data is None:
            return False
        if data.hasFormat(links.MIME):
            return self._add_links(key, links.decode(bytes(data.data(links.MIME).data())))
        return self._add_links(key, links.decode(data.text())) if data.hasText() else False

    @Slot(str, str)
    def removeLink(self, key, url):
        t = self._tasks.get(key)
        if t:
            self.edit(key, {"links": [l for l in t.get("links") or [] if l["url"] != url]})

    @Slot(str, result="QVariantList")
    def newFromLinks(self, payload):
        """Mails, notes or tasks dropped among the tasks: one new task each, named after it, linked to it."""
        keys = []
        for item in links.decode(payload):
            title = item.get("title") or links.describe(item["url"])["title"]
            if item.get("kind") == "task" or not title:
                continue
            key = self.add({"title": title, "links": [{"url": item["url"], "title": title}]})
            if key:
                keys.append(key)
        return keys

    @Slot(str)
    def openLink(self, url):
        """A task opens here, a mail in Plume, a note in Notes, anything else in the browser."""
        kind, ref = links.parse(url)
        if kind == "task" and self.resolve(ref):
            self._app.showRequested.emit(ref)
        elif kind:
            links.open_link(url)
        else:
            self._app.openUrl(url)

    @Slot(str, result="QVariantList")
    def linkCandidates(self, query):
        return links.search(query, self._server())

    def _changed_here(self):
        self._reload()
        self.stateChanged.emit()
        self._soon.start()

    def _clean(self, data):
        data = data.toVariant() if hasattr(data, "toVariant") else data
        return {k: (v.toVariant() if hasattr(v, "toVariant") else v) for k, v in dict(data).items()}

    def _list_for_new(self, hint=""):
        if hint and any(l["href"] == hint and not l["readonly"] for l in self._lists):
            return hint
        if self._view.startswith("list:") and not self._list_info(self._view[5:])["readonly"]:
            return self._view[5:]
        return self.defaultList or self._store.default_list()

    def _next_sort(self, list_href, parent=""):
        values = [t.get("sort") or 0 for t in self._tasks.values() if t["list"] == list_href and t.get("parent", "") == parent]
        return (max(values) if values else 0) + 1

    @Slot("QVariantMap", result=str)
    def add(self, fields):
        """A new task. fields: title, notes, due, alarm, repeat, priority, flagged, tags, list, parent, note, url."""
        if self._store is None:
            return ""
        fields = self._clean(fields)
        if not str(fields.get("title") or "").strip():
            return ""
        target = self._list_for_new(fields.pop("list", ""))
        parent_key = fields.pop("parentKey", "")
        if parent_key and parent_key in self._tasks:
            fields["parent"] = self._tasks[parent_key]["uid"]
            target = self._tasks[parent_key]["list"]
        if self._view == "today" and not fields.get("due") and not fields.get("parent"):
            fields["due"] = date.today().isoformat()
        if self._view == "flagged":
            fields.setdefault("flagged", True)
        if self._view.startswith("tag:"):
            fields["tags"] = list(dict.fromkeys(list(fields.get("tags") or []) + [self._view[4:]]))
        if fields.get("due") and "T" in fields["due"] and "alarm" not in fields:
            fields["alarm"] = "0"           # a time given: reminded then, as on macOS
        if fields.get("repeat") and not fields.get("due"):
            fields["due"] = date.today().isoformat()
        fields["sort"] = self._next_sort(target, fields.get("parent", ""))
        key = self._store.add(target, fields)
        self._changed_here()
        return key

    @Slot(str, result="QVariantMap")
    def preview(self, text):
        """What the quick field understood, as chips: [{kind, text}], and the title left."""
        return self._understand(text, [])

    def _understand(self, text, keep):
        found = nl.parse(text, self._app.lang, keep=tuple(keep), month_first=self._app.month_first)
        tt = self._app.t
        chips = []
        for kind in found["chips"]:
            if kind == "day" or kind == "time":
                if any(c["kind"] == "day" for c in chips):
                    continue
                row = {"due_ts": int(datetime.fromisoformat(found["due"]).timestamp()) if found["due"] else 0,
                       "all_day": "T" not in found["due"], "done": False}
                chips.append({"kind": "day", "text": self._due_label(row)[0], "icon": "calendar"})
            elif kind == "repeat":
                chips.append({"kind": "repeat", "text": self.describeRule(found["repeat"]), "icon": "repeat"})
            elif kind == "priority":
                chips.append({"kind": "priority", "text": tt["priority_" + str(found["priority"])], "icon": "priority"})
            elif kind == "tags":
                chips.append({"kind": "tags", "text": " ".join("#" + x for x in found["tags"]), "icon": "hash"})
            elif kind == "list":
                match = next((l for l in self._lists if fold(l["name"]).replace(" ", "") .startswith(fold(found["list"]))
                              and not l["readonly"]), None)
                if match:
                    chips.append({"kind": "list", "text": match["name"], "icon": "list", "color": match["color"], "href": match["href"]})
                    found["list_href"] = match["href"]
                else:
                    found["title"] = (found["title"] + " @" + found["list"]).strip()
        found["chips"] = chips
        return found

    @Slot(str, "QVariantList", result=str)
    def quickAdd(self, text, keep):
        """The quick field: natural language, minus the chips the person removed."""
        return self.quickAddWith(text, keep, {})

    @Slot(str, "QVariantList", "QVariantMap", result=str)
    def quickAddWith(self, text, keep, extras):
        """The same, with what the buttons under the field chose (due, flagged, priority): they win over the words."""
        keep = [str(k) for k in (keep.toVariant() if hasattr(keep, "toVariant") else keep)]
        extras = self._clean(extras) if extras else {}
        found = self._understand(text, keep)
        if not found["title"]:
            return ""
        fields = {"title": found["title"]}
        for key in ("due", "repeat", "priority", "tags"):
            if found.get(key):
                fields[key] = found[key]
        if found.get("list_href"):
            fields["list"] = found["list_href"]
        for key in ("due", "flagged", "priority", "section"):
            if extras.get(key):
                fields[key] = extras[key]
        return self.add(fields)

    @Slot(str, "QVariantMap")
    def edit(self, key, fields):
        if self._store is None:
            return
        fields = self._clean(fields)
        if "list" in fields:
            self.move([key], fields.pop("list"))
        rule = str(fields.get("repeat") or "")
        if rule and rule != "CUSTOM":
            t = self._tasks.get(key) or {}
            due = fields.get("due", t.get("due")) or date.today().isoformat()
            fields["due"] = self._align(due, todo.REPEATS.get(rule, rule))
        if fields and self._store.edit(key, fields):
            self._changed_here()

    @Slot(str)
    def toggleDone(self, key):
        t = self._tasks.get(key)
        if not t or self._store is None:
            return
        done = not t.get("done")
        if not done:
            self._store.complete(key, False)
            self._changed_here()
            return
        # its open subtasks are done with it (as in the cloud's Tasks app); a repeating one moves to its next date
        kids = [k for k in self._descendants(t) if self._open(self._tasks[k])]
        before = {k: (self._store.task(k) or {}).get("ics") for k in [key] + kids}
        copies = [c for c in [self._store.complete(k, True) for k in [key] + kids] if c]
        self._undone = (before, copies)
        if self._view != "completed":
            self._lingering[key] = time.monotonic()
            self._linger.start(LINGER_MS)
        if t.get("mail"):
            # its mail loses « À faire » in the cloud on this sync
            self._soon.setInterval(300)
        self._changed_here()
        self._soon.setInterval(1200)
        after = self._tasks.get(key) or {}
        if t.get("repeat") and self._open(after) and after.get("due_ts"):
            self.done.emit("completed", True, self._app.t["done_next"].replace("%1", self._due_label(after)[0]))
        elif kids:
            self.done.emit("completed", True, self._app.plural("done_with_subtasks", len(kids)))

    def _descendants(self, t):
        out, todo_ = [], [t.get("uid")]
        while todo_:
            uid = todo_.pop()
            for c in self._tasks.values():
                if uid and c.get("parent") == uid and c["key"] not in out:
                    out.append(c["key"])
                    todo_.append(c.get("uid"))
        return out

    @Slot()
    def undoDone(self):
        """« Annuler » after a tick: the tasks as they were (a repeating one back on its date), the copies gone."""
        if self._store is None or not self._undone:
            return
        before, copies = self._undone
        self._undone = None
        for key, ics in before.items():
            if ics:
                self._store.restore(key, ics)
        if copies:
            self._store.delete(*copies)
        self._lingering.clear()
        self._changed_here()

    def _end_linger(self):
        now = time.monotonic()
        self._lingering = {k: v for k, v in self._lingering.items() if now - v < LINGER_MS / 1000 - 0.05}
        if self._lingering:
            self._linger.start(LINGER_MS)
        self._rebuild()

    @Slot("QVariantList", bool)
    def setDoneMany(self, keys, done):
        if self._store is None:
            return
        keys = [k for k in keys if k in self._tasks and bool(self._tasks[k].get("done")) != done]
        if done:
            keys += [k for key in list(keys) for k in self._descendants(self._tasks[key]) if k not in keys and self._open(self._tasks[k])]
        before = {k: (self._store.task(k) or {}).get("ics") for k in keys}
        copies = [c for c in [self._store.complete(k, done) for k in keys] if c]
        if done and self._view != "completed":
            now = time.monotonic()
            self._lingering.update({k: now for k in keys})
            self._linger.start(LINGER_MS)
        self._changed_here()
        if done and keys:
            self._undone = (before, copies)
            self.done.emit("completed", True, self._app.plural("done_many", len(keys)))

    @Slot("QVariantList", int)
    def setPriorityMany(self, keys, priority):
        for key in keys:
            if key in self._tasks and self._store:
                self._store.edit(key, {"priority": int(priority)})
        self._changed_here()

    @Slot("QVariantList")
    def scheduleUndated(self, keys):
        """Dropped on « Programmées »: the ones without a date get today."""
        self.setDue([k for k in keys if k in self._tasks and not self._tasks[k].get("due")], "today")

    @Slot(str)
    def toggleFlag(self, key):
        t = self._tasks.get(key)
        if t:
            self.edit(key, {"flagged": not t.get("flagged")})

    @Slot("QVariantList", bool)
    def flagMany(self, keys, on):
        for key in keys:
            if key in self._tasks and self._store:
                self._store.edit(key, {"flagged": on})
        self._changed_here()

    @Slot("QVariantList", str)
    def setDue(self, keys, preset):
        """today | tomorrow | weekend | nextweek | none: a date in one click (the time of the day is kept)."""
        today = date.today()
        day = {"today": today, "tomorrow": today + timedelta(days=1),
               "weekend": today + timedelta(days=(5 - today.weekday()) % 7 or 7),
               "nextweek": today + timedelta(days=7 - today.weekday())}.get(preset)
        for key in keys:
            t = self._tasks.get(key)
            if not t or self._store is None:
                continue
            due = ""
            if day is not None:
                clock = (t.get("due") or "")[10:] if "T" in (t.get("due") or "") else ""
                due = day.isoformat() + clock
            self._store.edit(key, {"due": due})
        self._changed_here()

    @Slot("QVariantList", str)
    def move(self, keys, list_href):
        if self._store is None or self._list_info(list_href)["readonly"]:
            return
        for key in keys:
            t = self._tasks.get(key)
            if not t:
                continue
            self._store.move(key, list_href)
            # its subtasks follow
            for child in [c for c in self._tasks.values() if c.get("parent") == t.get("uid")]:
                self._store.move(child["key"], list_href)
        self._changed_here()

    @Slot(str, str)
    def reorder(self, key, before):
        """Manual order: key goes just before `before` ("" = at the end), among the tasks of its list."""
        t = self._tasks.get(key)
        if not t or self._store is None:
            return
        siblings = sorted([x for x in self._tasks.values() if x["list"] == t["list"] and x.get("parent", "") == t.get("parent", "")
                           and x["key"] != key and self._open(x)], key=self._sort_key("manual"))
        at = next((i for i, x in enumerate(siblings) if x["key"] == before), len(siblings))
        siblings.insert(at, t)
        for i, x in enumerate(siblings, start=1):
            if x.get("sort") != i:
                self._store.edit(x["key"], {"sort": i})
        self._app.setPref("sort_" + t["list"], "manual")
        target = self._tasks.get(before)
        if target and target["list"] == t["list"] and (target.get("section") or "") != (t.get("section") or "") and not t.get("parent"):
            self._store.edit(key, {"section": target.get("section") or ""})
        self._changed_here()

    @Slot(str, int)
    def nudge(self, key, step):
        """Alt+↑ / Alt+↓: one place up or down among its siblings."""
        t = self._tasks.get(key)
        if not t:
            return
        siblings = sorted([x for x in self._tasks.values() if x["list"] == t["list"] and x.get("parent", "") == t.get("parent", "")
                           and self._open(x)], key=self._sort_key("manual"))
        i = next((i for i, x in enumerate(siblings) if x["key"] == key), -1)
        j = i + step
        if i < 0 or j < 0 or j >= len(siblings):
            return
        before = siblings[j]["key"] if step < 0 else (siblings[j + 1]["key"] if j + 1 < len(siblings) else "")
        self.reorder(key, before)

    @Slot(str)
    def indent(self, key):
        """Tab: a subtask of the task above it (in the same list)."""
        rows = [r for r in self._rows if r["list"] == (self._tasks.get(key) or {}).get("list")]
        i = next((i for i, r in enumerate(rows) if r["key"] == key), -1)
        if i <= 0:
            return
        above = next((r for r in reversed(rows[:i]) if r["depth"] <= rows[i]["depth"]), None)
        if above and above["key"] != key:
            self.edit(key, {"parent": above["uid"]})

    @Slot(str)
    def outdent(self, key):
        t = self._tasks.get(key)
        if t and t.get("parent"):
            parent = next((p for p in self._tasks.values() if p.get("uid") == t["parent"]), None)
            self.edit(key, {"parent": parent.get("parent", "") if parent else ""})

    @Slot(str)
    def toggleCollapsed(self, key):
        collapsed = list(self._app.pref("collapsed") or [])
        collapsed = [k for k in collapsed if k != key] if key in collapsed else collapsed + [key]
        self._app.setPref("collapsed", collapsed)

    @Slot("QVariantList")
    def delete(self, keys):
        keys = [k for k in keys if k in self._tasks and not self._list_info(self._tasks[k]["list"])["readonly"]]
        if not keys or self._store is None:
            return
        # with their subtasks
        uids = {self._tasks[k].get("uid") for k in keys}
        keys += [t["key"] for t in self._tasks.values() if t.get("parent") in uids and t["key"] not in keys]
        kept = {k: self._store.task(k) for k in keys if not self._tasks[k].get("href")}
        self._store.delete(*keys)
        for k in keys:
            self._held[k] = kept.get(k)
        self._release.start(UNDO_MS)
        self._reload()
        self.stateChanged.emit()
        self.done.emit("deleted", True, self._app.plural("deleted_many", len(keys)) if len(keys) > 1 else self._app.t["deleted_one"])

    @Slot()
    def undoDelete(self):
        if self._store is None:
            return
        for key, kept in list(self._held.items()):
            if kept is None:
                self._store.undelete(key)
            elif kept.get("ics"):
                index = todo.index(kept["ics"]) or {}
                with self._store.lock:
                    self._store.db.execute("INSERT OR REPLACE INTO tasks (key, list, uid, ics, data, rev) VALUES (?, ?, ?, ?, ?, 1)",
                                           (key, kept["list"], index.get("uid", ""), kept["ics"], json.dumps(index)))
        self._held.clear()
        self._release.stop()
        self._reload()
        self.stateChanged.emit()

    def _release_held(self):
        self._held.clear()
        self.refresh()

    @Slot(str)
    def clearCompleted(self, list_href):
        self.delete([t["key"] for t in self._tasks.values() if t["list"] == list_href and t.get("done")])

    # ---- lists ---------------------------------------------------------------------------------------------
    @Slot(str, str, result=str)
    def createList(self, name, color):
        if self._store is None or not name.strip():
            return ""
        href = self._store.create_list(name, color or None)
        self._changed_here()
        self.setView("list:" + href)
        return href

    @Slot(str, str, str)
    def editList(self, href, name, color):
        if self._store is None:
            return
        self._store.edit_list(href, name or None, color or None)
        self._changed_here()
        self.viewChanged.emit()

    @Slot(str)
    def deleteList(self, href):
        if self._store is None:
            return
        self._store.delete_list(href)
        if self._view == "list:" + href:
            self.setView("today")
        self._changed_here()

    @Slot(str, str)
    def reorderList(self, href, before):
        """A list dragged in the side column: just before `before` ("" = at the end)."""
        if self._store is None:
            return
        order = [l["href"] for l in self._lists if l["href"] != href]
        order.insert(order.index(before) if before in order else len(order), href)
        self._store.reorder_lists(order)
        self._changed_here()

    @Slot(str, int)
    def nudgeList(self, href, step):
        order = [l["href"] for l in self._lists]
        if href not in order:
            return
        i = order.index(href)
        j = max(0, min(len(order) - 1, i + step))
        order.insert(j, order.pop(i))
        self._store.reorder_lists(order)
        self._changed_here()

    def _list_job(self, href, job, what):
        client = self.client()
        if client is None or href.startswith("local:"):
            return

        def run():
            try:
                found = job(client)
                self.sharesRead.emit(href, found)
            except DavError as error:
                if what != "read":
                    self._ran.emit(lambda: self.done.emit("share", False, self._app.t["list_share_failed"]))
                try:
                    self.sharesRead.emit(href, client.shares(href))
                except DavError:
                    self.sharesRead.emit(href, [])
            finally:
                client.close()
                if what != "read":
                    self._ran.emit(self.refresh)
        self._pool.submit(run)

    @Slot(str)
    def loadShares(self, href):
        self._list_job(href, lambda c: c.shares(href), "read")

    @Slot(str, str, bool)
    def shareList(self, href, principal, read_only):
        self._list_job(href, lambda c: (c.share(href, principal, read_only), c.shares(href))[1], "share")

    @Slot(str, str)
    def unshareList(self, href, principal):
        self._list_job(href, lambda c: (c.unshare(href, principal), c.shares(href))[1], "unshare")

    @Slot(str)
    def findSharees(self, text):
        """Accounts and groups of the cloud for this text (its own autocomplete, so its rules of who sees whom)."""
        account = self._app.account()
        text = text.strip()
        if not account or len(text) < 2:
            self.sharees.emit(text, [])
            return

        def run():
            query = urllib.parse.urlencode([("search", text), ("itemType", "calendar"), ("itemId", "0"),
                                            ("shareTypes[]", 0), ("shareTypes[]", 1), ("limit", 8)])
            status, data = cloud.ocs(account[0], account[1], account[2], "/ocs/v2.php/core/autocomplete/get?" + query)
            people = ((data or {}).get("ocs") or {}).get("data") if isinstance(data, dict) else None
            out = []
            for person in people if isinstance(people, list) else []:
                source = person.get("source") or "users"
                if source not in ("users", "groups") or str(person.get("id")) == account[1]:
                    continue
                kind = "groups" if source == "groups" else "users"
                out.append({"principal": f"principals/{kind}/{person.get('id')}", "name": person.get("label") or person.get("id"),
                            "detail": person.get("subline") or "", "group": kind == "groups"})
            self.sharees.emit(text, out)
        threading.Thread(target=run, daemon=True).start()

    @Property("QVariantList", constant=True)
    def colors(self):
        return list(COLORS) + ["#5B6B82", "#7A5200", "#3D5AA8"]

    # ---- the rest of the desktop ------------------------------------------------------------------------------
    @Slot(str)
    def openMail(self, key):
        t = self._tasks.get(key)
        if not t:
            return
        if t.get("mail") and system.has_app("mail"):
            system.launch("mail", "--message-id=" + t["mail"])
        elif t.get("url"):
            cloud.open_url(cloud.cloud_link(t["url"]))

    @Slot(str)
    def openNote(self, key):
        t = self._tasks.get(key)
        if t and t.get("note"):
            system.launch("notes", "--show=" + t["note"])

    @Slot(str, result=str)
    def resolve(self, ref):
        """A task from its uid (notifications, KRunner) or its key."""
        if ref in self._tasks:
            return ref
        return self._store.by_uid(ref) if self._store else ""

    def add_from_outside(self, items):
        """--add-json from Notes or KRunner: [{title, due, note, noteTitle, list}]. Returns the keys made."""
        keys = []
        for item in items:
            if not isinstance(item, dict) or not str(item.get("title") or "").strip():
                continue
            fields = {"title": str(item["title"]).strip()}
            if item.get("due"):
                fields["due"] = str(item["due"])[:16]
            if item.get("note"):
                fields["note"] = str(item["note"])
                if item.get("noteTitle"):
                    fields["notes"] = self._app.t["from_note"].replace("%1", str(item["noteTitle"]))
            if item.get("notes"):
                fields["notes"] = str(item["notes"])
            if item.get("url"):
                fields["url"] = str(item["url"])
            fields["list"] = str(item.get("list") or "")
            view, self._view = self._view, "all"
            key = self.add(fields)
            self._view = view
            if key:
                keys.append(key)
        return keys

    # ---- for the reminders --------------------------------------------------------------------------------
    def alarms_due(self, now):
        """[(task, at)] of the reminders that are due and not shown yet (and the snoozed ones whose time came)."""
        if self._store is None:
            return []
        out = []
        snoozed = self._store.snoozed()
        for t in self._tasks.values():
            if not self._open(t):
                continue
            uid = t.get("uid", "")
            if uid in snoozed:
                if snoozed[uid] <= now:
                    out.append((t, snoozed[uid]))
                continue
            for alarm in t.get("alarms") or []:
                at = alarm["at"]
                if now - MISSED_S < at <= now and not self._store.fired(uid, at):
                    out.append((t, at))
        return out
