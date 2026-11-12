"""Plume, the suite: Notes, Tâches, Mots de passe, Ornis, Meet and the Photothèque as modules of the same window, beside
mail, calendar and contacts. The Photothèque opens from the grid of apps, not from the rail (GRID).

Each module is the app itself (its bundle: the same objects and the same view as its own window), made the first
time it is needed, its view in its own QML context (its "app", "theme"… hide Plume's names of the same kind).
Tâches and Meet are made at once: reminders and incoming calls come with Plume (in the tray), window or not.

Plume holds the socket of each module it runs, so Notes, Tâches or Ornis launched on their own (a link, KRunner,
a notification) hand their arguments over to the module. On Orneos OS, a Tâches agent already running (the
reminders of the session) is asked to leave them to Plume; an app open in its own window keeps its module, and
the module only offers to bring that window up.
"""
import importlib
import json
import os
import sys
import time
from pathlib import Path

from PySide6.QtCore import QObject, Property, QUrl, Signal, Slot
from PySide6.QtQml import QQmlComponent, QQmlContext, QQmlEngine
from PySide6.QtQuick import QQuickItem

import module
import system

# module → (folder in /usr/share, its core package)
# (in the order of the rail, after Courrier, Agenda, Contacts: Meet first, the people's other app)
MODULES = {"meet": ("orneos-meet", "meet_core"), "notes": ("orneos-notes", "notes_core"),
           "tasks": ("orneos-tasks", "tasks_core"), "passwords": ("orneos-passwords", "passwords_core"),
           "ornis": ("orneos-ornis", "ornis_core"), "photos": ("orneos-photos", "photos_core")}
GRID = ("photos",)                               # modules opened from the grid of apps (the rail keeps the daily ones)
STARTED = ("tasks", "meet", "ornis")             # made with Plume: the reminders, the calls that ring
BACKGROUND = ("--refresh", "--add", "--add-json", "--agent")
# written by os/tools/apps.py (PLUME_CATALOGUE: the tests' own)
CATALOGUE = Path(os.environ.get("PLUME_CATALOGUE") or system.SHARE / "orneos" / "apps.json")
# cloud apps Plume shows itself: not in the grid (the assistant is the Ornis module)
SHOWN = {"mail": "mail", "calendar": "calendar", "contacts": "contacts", "notes": "notes", "tasks": "tasks",
         "passwords": "passwords", "assistant": "ornis", "meet": "meet", "photos": "photos"}
NATIVE_ICONS = {"photos": "image"}               # the glyph of a module of the grid (Plume's icons.js)


def available():
    """The modules whose app is there beside Plume (all of them in the packages)."""
    return [kind for kind, (folder, _) in MODULES.items() if (system.SHARE / folder).is_dir()]


class Suite(QObject):
    changed = Signal()
    badgesChanged = Signal()
    callChanged = Signal()              # Meet's call starts or ends (the rail shows it while another module is in front)
    raiseRequested = Signal(str)        # a module asks for the window (a link, a notification)

    def __init__(self, qt, plume, kinds=None):
        super().__init__()
        self._qt = qt
        self._plume = plume
        self._engine = None
        self._bundles = {}
        self._front = ""                  # the module in front ("" : Plume behind), see focus
        self._servers = {}
        self._views = {}
        self._elsewhere = set()          # running in their own window: the module offers to bring it up
        self._badges = {}                # the count of a module on the rail (Tâches: today's tasks)
        self._call = {"active": False, "name": "", "label": ""}
        self._yielded = set()            # agents of Orneos OS that left their module to Plume
        self._kinds = available() if kinds is None else kinds    # none in Courrier, Agenda, Contacts (Orneos OS)
        for kind in self._kinds:
            folder = str(system.SHARE / MODULES[kind][0])
            if folder not in sys.path:
                sys.path.append(folder)
            system.register(kind, lambda args, kind=kind: self.handle(kind, args))
        for kind in STARTED:
            if kind in self._kinds:
                self.bundle(kind)

    def set_engine(self, engine):
        self._engine = engine

    @Property("QVariantList", constant=True)
    def modules(self):
        return self._kinds

    @Property("QVariantList", notify=changed)
    def elsewhere(self):
        return sorted(self._elsewhere)

    @Property("QVariantMap", notify=badgesChanged)
    def badges(self):
        return dict(self._badges)

    @Property("QVariantMap", notify=callChanged)
    def call(self):
        """Meet's call: {active, name, label} (label: « Appel en cours », in Meet's words)."""
        return dict(self._call)

    def _watch_call(self, built):
        calls, t = built.context["calls"], built.app.t

        def changed():
            now = {"active": bool(calls.active), "name": calls.name, "label": t.get("call_ongoing", "")}
            if now != self._call:
                self._call = now
                self.callChanged.emit()
        calls.changed.connect(changed)

    @Property("QVariantList", constant=True)
    def grid(self):
        """The modules opened from the grid, not the rail: [{key, name, icon, glyph}] (their own window's name)."""
        out = []
        for kind in GRID:
            if kind in self._kinds:
                icon = system.SHARE / "icons" / "hicolor" / "scalable" / "apps" / f"eu.orneos.{kind}.svg"
                out.append({"key": kind, "name": self._plume.t.get(kind, kind), "glyph": NATIVE_ICONS.get(kind, "apps"),
                            "icon": QUrl.fromLocalFile(str(icon)).toString() if icon.is_file() else ""})
        return out

    @Property("QVariantList", constant=True)
    def apps(self):
        """The grid: [{name, apps: [{key, name, url, icon}]}] by group, from the list of Orneos OS (apps.json)."""
        try:
            catalogue = json.loads(CATALOGUE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        lang = self._plume.lang
        mine = set(self._plume.modules)
        icons = system.SHARE / "icons" / "hicolor" / "scalable" / "apps"
        groups = []
        for group in catalogue.get("groups", []):
            apps = [{"key": a["key"], "name": a["names"].get(lang) or a["names"]["en"], "url": a["url"],
                     "icon": QUrl.fromLocalFile(str(icons / f"eu.orneos.{a['key']}.svg")).toString()}
                    for a in catalogue.get("apps", [])
                    if a.get("group") == group["key"] and SHOWN.get(a["key"]) not in mine]
            if apps:
                groups.append({"name": group["names"].get(lang) or group["names"]["en"], "apps": apps})
        return groups

    def _set_badge(self, kind, count):
        if self._badges.get(kind) != count:
            self._badges[kind] = count
            self.badgesChanged.emit()
            if kind in ("ornis", "meet"):
                system.badge(count, kind)

    # ---- the apps -----------------------------------------------------------------------------------------
    def _claim(self, kind):
        """The module's socket, or False when its own app holds it (its window is open)."""
        if module.is_taken(kind):
            module.hand_over(kind, ["--yield"])
            deadline = time.monotonic() + 2
            while module.is_taken(kind) and time.monotonic() < deadline:
                time.sleep(0.1)
            if module.is_taken(kind):
                return False
            self._yielded.add(kind)
        self._servers[kind] = module.listen(kind, lambda args, token, kind=kind: self.handle(kind, args, token))
        return True

    def bundle(self, kind):
        """The module's objects, made once (None while its own app runs it)."""
        if kind in self._bundles:
            return self._bundles[kind]
        if kind not in self._kinds or kind in self._elsewhere:
            return None
        if not self._claim(kind):
            self._elsewhere.add(kind)
            self.changed.emit()
            return None
        maker = importlib.import_module(MODULES[kind][1] + ".bundle")
        built = maker.build(self._qt)
        built.prepare = getattr(maker, "prepare_engine", None)   # what a module adds to the engine (pictures)
        built.app.raiseRequested.connect(lambda kind=kind: self.raiseRequested.emit(kind))
        if kind == "tasks":
            built.context["tasks"].set_interval(5)
        elif kind == "meet":
            built.context["meet"].set_active(self._front == "meet")
            self._watch_call(built)
        elif kind == "ornis":
            built.context["chat"].set_active(self._front == "ornis")
        for obj in built.keep:          # the reminders of Tâches give today's count, Meet the conversations waiting
            if hasattr(obj, "badgeChanged"):
                obj.badgeChanged.connect(lambda count, kind=kind: self._set_badge(kind, count))
                initial = getattr(obj, "unreadCount", getattr(obj, "badge", 0))
                if isinstance(initial, int) and initial > 0:
                    self._set_badge(kind, initial)
        self._bundles[kind] = built
        return built

    def handle(self, kind, args, token=""):
        """Arguments for a module (system.launch, its socket): its app takes them as its own window would."""
        if kind in self._elsewhere:
            module.hand_over(kind, args)
            return
        built = self.bundle(kind)
        if built is None:
            return
        # the view first (shown, so made), then the arguments: what they ask (a note, a question) reaches it.
        # Tâches only adds or reads tasks in the background (Notes, a mail tagged « À faire »).
        # a Quick Note (tray, Ctrl+Alt+N) opens over the other apps without Plume, once Notes is made
        quick = kind == "notes" and list(args) == ["--quick"] and kind in self._views
        if not quick and not any(arg in BACKGROUND for arg in args):
            self.raiseRequested.emit(kind)
        built.app.handle_args(list(args), token)

    @Slot(str)
    def openElsewhere(self, kind):
        """The app holds its module in its own window: bring that window up."""
        module.hand_over(kind, [])

    def give_back(self):
        """Plume quits: the agents it took over (the reminders of Tâches on Orneos OS) start again."""
        for kind, server in self._servers.items():
            server.close()
            if kind in self._yielded:
                system.spawn(system.COMMANDS[kind] + ["--agent"])

    # ---- Ornis beside a module (Ctrl+J): the same conversations, made from the Ornis module's objects ------------
    @Property(bool, notify=changed)
    def ornisPanel(self):
        """Ornis can open beside the other modules (its module is in this Plume and not in its own window)."""
        return "ornis" in self._kinds and "ornis" not in self._elsewhere

    @Slot(QQuickItem, result=QQuickItem)
    def mountPanel(self, host):
        """Ornis's side panel inside host (made once), or None."""
        if "panel" in self._views:
            return self._views["panel"]
        built = self.bundle("ornis")
        if built is None or self._engine is None:
            return None
        if built.prepare:
            built.prepare(self._engine, built)
        context = QQmlContext(self._engine.rootContext(), self._engine)
        for name, obj in built.context.items():
            context.setContextProperty(name, obj)
        component = QQmlComponent(self._engine, QUrl.fromLocalFile(str(Path(built.view).with_name("Panel.qml"))))
        view = component.create(context)
        if view is None:
            for error in component.errors():
                print("plume: ornis panel", error.toString(), file=sys.stderr)
            return None
        QQmlEngine.setObjectOwnership(view, QQmlEngine.ObjectOwnership.CppOwnership)
        view.setParentItem(host)
        self._views["panel"] = view
        built.keep += [context, component]
        return view

    @Slot(bool)
    def setPanelShown(self, shown):
        """The panel opened or closed: what it shows is read (as the module in front), its replies notify no one."""
        self._panel = bool(shown)
        built = self._bundles.get("ornis")
        if built is not None:
            built.context["chat"].set_panel(self._panel)
            built.context["chat"].set_active(self._front == "ornis" or (self._panel and self._front != ""))

    @Slot(str, "QVariantMap")
    def setPanelAbout(self, kind, item):
        """What the module beside has open (a message, an event, a contact): goes with the next question."""
        built = self._bundles.get("ornis")
        if built is not None:
            built.context["chat"].setAbout(item)

    @Slot(str)
    def ornisAction(self, arg):
        """Ctrl+K: the Ornis module in front, doing that (--new, --code, --scheduled, --mode=…, --session=…)."""
        self.handle("ornis", [arg])

    @Slot(str, result="QVariantList")
    def ornisFind(self, query):
        """Ctrl+K: Ornis's conversations whose title has every word typed (5 at most, newest first; [] before the
        module was ever shown: the palette never starts it)."""
        built = self._bundles.get("ornis")
        words = [w for w in str(query or "").lower().split() if w]
        if built is None or not words:
            return []
        out = []
        for row in built.context["chat"].allSessions:
            label = str(row.get("label") or "")
            if all(w in label.lower() for w in words):
                out.append({"id": str(row.get("id") or ""), "label": label, "when": str(row.get("when") or "")})
                if len(out) == 5:
                    break
        return out

    @Slot()
    def expandPanel(self):
        """« Open in Ornis »: the module, on the conversation of the panel."""
        built = self._bundles.get("ornis")
        if built is None:
            return
        current = built.context["chat"].current
        self.handle("ornis", [f"--session={current}"] if current else ["--new"])

    def focus(self, kind):
        """The module in front, "" while Plume is behind or minimised. Meet reads a conversation only when
        someone looks at it: otherwise its messages stay unread, with their notification and the dock's count."""
        self._front = kind
        built = self._bundles.get("meet")
        if built is not None:
            built.context["meet"].set_active(kind == "meet")
        built = self._bundles.get("ornis")
        if built is not None:          # Ornis in front (or beside, Ctrl+J): the conversation it shows is read (on every device)
            built.context["chat"].set_active(kind == "ornis" or (getattr(self, "_panel", False) and kind != ""))
        if kind and kind != "meet":
            active_bundle = self._bundles.get(kind)
            if active_bundle is not None and active_bundle.on_active:
                active_bundle.on_active()

    # ---- the views ----------------------------------------------------------------------------------------
    @Slot(str, QQuickItem, result=QQuickItem)
    def mount(self, kind, host):
        """The module's view inside host (made once), or None (its app runs elsewhere, or it failed)."""
        if kind in self._views:
            return self._views[kind]
        built = self.bundle(kind)
        if built is None or self._engine is None:
            return None
        if built.prepare:
            built.prepare(self._engine, built)
        context = QQmlContext(self._engine.rootContext(), self._engine)
        for name, obj in built.context.items():
            context.setContextProperty(name, obj)
        component = QQmlComponent(self._engine, QUrl.fromLocalFile(str(built.view)))
        view = component.create(context)
        if view is None:
            for error in component.errors():
                print("plume:", kind, error.toString(), file=sys.stderr)
            return None
        QQmlEngine.setObjectOwnership(view, QQmlEngine.ObjectOwnership.CppOwnership)
        view.setParentItem(host)
        self._views[kind] = view
        built.keep += [context, component]
        return view
