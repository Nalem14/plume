#!/usr/bin/python3
"""Plume: the mail, calendar, contacts, notes, tasks, passwords and Ornis of the Orneos account, as one native app.

One window, a module per app on a Klein rail, and the grid of the other apps of the cloud (in the browser).
Notes, Tâches, Mots de passe and Ornis are their own apps shown as modules (suite.py), with their objects and their views.
On Orneos OS the account is the app password of Orneos Connect (CalDAV, CardDAV); mail asks for the account
password once and keeps it in KWallet (the system's keychain elsewhere). Ornis (the Orneos assistant) works on
demand, through the cloud, with the same 24 h quota as everywhere.

On Orneos OS, Courrier, Agenda and Contacts are each their own app from the same code (an edition: one module, no
rail, its own window and dock pin); Plume, the suite, comes from its package beside them.

One instance per session (per edition): a second launch hands its arguments to the first window and exits.
Usage: plume [--mail | --calendar | --contacts | --notes | --tasks | --passwords | --ornis] [mailto:… | webcal://… | file.ics]
       plume --edition=mail|calendar|contacts [arguments as above]   (orneos-mail, orneos-calendar, orneos-contacts)
       plume --self-test=<report file>   (the packages' check: the views load, Chromium starts; then quits)
"""
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "orneos"))

import cloud  # noqa: E402
import module  # noqa: E402
import system  # noqa: E402
import qmlvalue  # noqa: E402
from account import SignIn  # noqa: E402
from updater import Updater  # noqa: E402
from PySide6.QtCore import QEvent, QEventLoop, Qt, QTimer, QUrl  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent  # noqa: E402
from PySide6.QtQuickControls2 import QQuickStyle  # noqa: E402
from PySide6.QtWebEngineQuick import QtWebEngineQuick  # noqa: E402

from plume_core import VERSION  # noqa: E402
from plume_core.agenda import Agenda  # noqa: E402
from plume_core.app import MODULES, Plume  # noqa: E402
from plume_core.mail import Mail  # noqa: E402
from plume_core.news import News  # noqa: E402
from plume_core.promo import Promo  # noqa: E402
from plume_core.ornis import Ornis  # noqa: E402
from plume_core.people import People  # noqa: E402
from plume_core.richtext import RichText  # noqa: E402
from plume_core.store import Store  # noqa: E402
from plume_core.suite import Suite, available  # noqa: E402
from plume_core.sync import Sync  # noqa: E402
from plume_core.theme import Theme  # noqa: E402


def opening(base):
    """macOS hands mailto:, webcal:, orneos:// and .ics files to the app as events, not as arguments. They come to
    the application object itself: its event(), not an event filter on the whole app, which PySide would wrap every
    object for (and crash on one being destroyed). Those arriving before Plume is ready wait for open_with."""
    class App(base):
        def __init__(self, argv):
            super().__init__(argv)
            self._on_args, self._waiting = None, []

        def open_with(self, on_args):
            self._on_args = on_args
            for args in self._waiting:
                on_args(args)
            self._waiting = []

        def event(self, event):
            if event.type() == QEvent.Type.FileOpen:
                url = event.url()
                args = [url.toLocalFile() if url.isLocalFile() else url.toString()]
                if self._on_args:
                    self._on_args(args)
                else:
                    self._waiting.append(args)
                return True
            return super().event(event)
    return App


def dock_count(app_id):
    """The count on an app's dock pin (Unity LauncherEntry, as Tâches does): Agenda shows the invitations waiting
    for an answer. Plasma drops it when the app quits. Courrier paints the unread count itself (cloud.mail_badge)."""
    try:
        from PySide6.QtDBus import QDBusConnection, QDBusMessage  # noqa: PLC0415 - Linux only
    except ImportError:
        return lambda count: None
    bus = QDBusConnection.sessionBus()
    uri = f"application://{app_id}.desktop"
    path = f"/com/canonical/unity/launcherentry/{cloud._djb2(uri)}"
    last = [None]

    def show(count):
        if count == last[0]:
            return
        last[0] = count
        message = QDBusMessage.createSignal(path, "com.canonical.Unity.LauncherEntry", "Update")
        message.setArguments([uri, {"count": int(count), "count-visible": count > 0, "urgent": False}])
        bus.send(message)
    return show


def wait(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


HOTKEY = [""]        # the global shortcut had (« Alt+Espace »), for the self-test


def self_test(engine, suite, report):
    """Every module's view is made, a page renders in Chromium (QtWebEngine), the keychain answers: the CI
    runs this on each package before publishing it. The result goes to the report (no console on Windows)."""
    results = {}
    window = engine.rootObjects()[0]
    host = window.contentItem()
    for kind in suite.modules:
        results["module " + kind] = suite.mount(kind, host) is not None
    component = QQmlComponent(engine)
    component.setData(b"import QtWebEngine\nWebEngineView { width: 200; height: 100 }", QUrl())
    view = component.create()
    if view is not None:
        view.setParentItem(host)
        view.setProperty("url", QUrl("data:text/html,<p>Plume</p>"))
        for _ in range(100):
            if view.property("loadProgress") == 100 and not view.property("loading"):
                break
            wait(200)
    results["chromium"] = view is not None and view.property("loadProgress") == 100
    results["keychain"] = system._keyring() is not None or not (system.WINDOWS or system.MACOS)
    results["fonts"] = any(system.fonts_dir().glob("*.ttf"))
    # the global shortcut of Ornis (Alt+Space), on Windows and macOS: said, never blocking (a CI runner may refuse it)
    results["shortcut " + (HOTKEY[0] or "none (not registered)")] = True
    lines = [("ok   " if ok else "FAIL ") + name for name, ok in results.items()]
    Path(report).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if all(results.values()) else 1


def main():
    args = sys.argv[1:]
    report = next((a.split("=", 1)[1] for a in args if a.startswith("--self-test=")), None)
    edition = next((a.split("=", 1)[1] for a in args if a.startswith("--edition=")), "")
    if edition not in ("", *MODULES):
        print("plume: --edition is mail, calendar or contacts", file=sys.stderr)
        return 2
    args = [a for a in args if not a.startswith("--edition=")]
    # the Wayland app id: the window goes with its own dock pin (Courrier, Agenda, Contacts or Plume)
    app_id = f"eu.orneos.{edition}" if edition else "eu.orneos.plume"
    QGuiApplication.setDesktopFileName(app_id)
    system.native_dialogs()              # « Joindre », « Enregistrer sous »: the system's file picker, not Qt's own
    # Mail bodies render in Chromium (no JavaScript, nothing remote unless allowed): set up before the app
    if os.environ.get("PLUME_NO_WEBENGINE") != "1":
        # the bots' browsers work unseen (Plume in the tray, a routine at 8 h): Chromium must not slow their pages down
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "") + " --disable-renderer-backgrounding"
                                                    " --disable-background-timer-throttling --disable-backgrounding-occluded-windows").strip()
        QtWebEngineQuick.initialize()
    # Orneos OS: Orneos Connect signs in, the dock and Plasma's notifications; elsewhere Plume does both, in the tray
    own = shutil.which("orneos-connect") is None and not edition
    if own:
        from PySide6.QtWidgets import QApplication  # noqa: PLC0415 - the tray's menu
        app = (opening(QApplication) if system.MACOS else QApplication)(sys.argv)
        app.setQuitOnLastWindowClosed(False)
    else:
        app = (opening(QGuiApplication) if system.MACOS else QGuiApplication)(sys.argv)
    app.setApplicationName("Plume")
    app.setApplicationVersion(VERSION)
    app.setOrganizationName("Orneos")
    app.setWindowIcon(system.icon(app_id))
    if report is None and module.hand_over(edition or "plume", args):
        return 0
    system.add_fonts()
    QQuickStyle.setStyle("Basic")

    store = Store()
    theme = Theme(app)
    plume = Plume(store, list(MODULES) + ([] if edition else available()), edition)
    plume.background = "--background" in args
    plume.keep_running = own
    sync = Sync(plume, store)
    agenda = Agenda(store, sync, plume)
    people = People(store, sync)
    mail = Mail(store, plume, theme, passive=edition not in ("", "mail"))
    rich = RichText(app)
    ornis = Ornis(plume, store)
    suite = Suite(app, plume, [] if edition else None)
    news = News(plume, edition)
    promo = Promo(plume, edition)
    # signing in: Orneos Connect on Orneos OS, the cloud's page in the browser elsewhere (account.py)
    signin = SignIn(plume.t, own=own)
    updater = Updater(VERSION, store.get("update_channel", "stable"))
    updater.changed.connect(lambda: store.set("update_channel", updater.channel))
    tray = None
    if own:
        from tray import Tray  # noqa: PLC0415 - Qt Widgets, only where Plume has a tray
        system.register("connect", lambda args: signin.start())
        if system.autostart_enabled():
            plume.setAutostart(True)      # Plume moved (new AppImage, other folder): the entry follows it
        tray = Tray(plume.t, app.windowIcon(), plume.raiseRequested.emit, [
            (plume.t["new_message"], lambda: plume.handle_args(["mailto:"])),
            (plume.t["tray_new_task"], lambda: system.launch("tasks", "--new")),
            *([(plume.t["tray_quick_note"], lambda: suite.handle("notes", ["--quick"]))] if "notes" in plume.modules else []),
            (plume.t["ask_ornis"], lambda: system.launch("ornis", "--new")),
        ], autostart=(lambda: plume.autostart, plume.setAutostart, plume.autostartChanged))
    if not edition and not (system.WINDOWS or system.MACOS):
        show_suite_count = dock_count(app_id)
        previous_badge = system._badge
        def suite_count(count):
            show_suite_count(count)
            if previous_badge:
                previous_badge(count)
        system.set_badge_hook(suite_count)
        app.aboutToQuit.connect(lambda: show_suite_count(0))
    if own:
        agenda.start_reminders()          # Orneos OS: the cloud's reminders come through orneos-notify
    sync.failed.connect(plume.syncFailed)
    sync.reached.connect(plume.reached)
    if edition == "calendar" and not (system.WINDOWS or system.MACOS):
        show_count = dock_count(app_id)
        agenda.changed.connect(lambda: show_count(agenda.pending))
        app.aboutToQuit.connect(lambda: show_count(0))
        QTimer.singleShot(0, lambda: show_count(agenda.pending))
    # invitations: who "me" is includes the external mailboxes; a mail's invitation goes to the calendar
    sync.extra_addresses = mail.addresses
    mail.invitationArrived.connect(agenda.receiveInvitation)
    agenda.replyMail.connect(mail.sendCalendarReply)
    # Windows and macOS: Alt+Space (as ChatGPT's) brings Plume up on a new conversation with Ornis (plume_core/hotkey.py)
    if own and "ornis" in plume.modules and (system.WINDOWS or system.MACOS) and store.get("ornis_hotkey", True):
        from plume_core.hotkey import install  # noqa: PLC0415 - Windows and macOS only
        shortcut = install(lambda: suite.ornisAction("--new"), plume.t["key_space"])
        HOTKEY[0] = shortcut
        if shortcut and tray is not None and hasattr(tray, "set_hint"):
            tray.set_hint(plume.t["ornis_hotkey"].replace("%1", shortcut))
    # and Ctrl+Alt+N a Quick Note of Notes, above the other windows (Orneos OS: Meta+N)
    if own and "notes" in plume.modules and (system.WINDOWS or system.MACOS) and store.get("notes_hotkey", True):
        from plume_core.hotkey import install  # noqa: PLC0415 - Windows and macOS only
        HOTKEY.append(install(lambda: suite.handle("notes", ["--quick"]), plume.t["key_space"], key="n"))
    server = module.listen(edition or "plume", plume.handle_args)  # noqa: F841 (kept alive with the app)
    for kind in plume.modules:            # the other apps open mail, calendar and contacts here
        if kind in MODULES:
            system.register(kind, lambda args, kind=kind: plume.handle_args(["--" + kind, *args]))

    def show_module(kind):
        plume.setModule(kind)
        plume.raiseRequested.emit()
    suite.raiseRequested.connect(show_module)

    def catch_up():
        if app.applicationState() != Qt.ApplicationState.ApplicationActive:
            return
        if edition:
            # Courrier, Agenda and Contacts share the cache: what another one wrote (an invitation) shows now
            sync.calendarsChanged.emit()
            sync.contactsChanged.emit()
        sync.refresh()
        mail.refresh()
    late = QTimer(app)
    late.setSingleShot(True)
    late.setInterval(1500)
    late.timeout.connect(catch_up)

    def state_changed(state):
        # Back to the front after a while: read what changed elsewhere (phone, cloud), once the window has
        # answered the first clicks. The module in front reads its own (suite.focus); the others when shown.
        if state == Qt.ApplicationState.ApplicationActive and plume.stale(60):
            late.start()
    app.applicationStateChanged.connect(state_changed)

    def front(*_):
        # the module someone looks at: Plume in front and that module shown (Meet marks read only then)
        shown = app.applicationState() == Qt.ApplicationState.ApplicationActive
        suite.focus(plume.module if shown else "")
    app.applicationStateChanged.connect(front)
    plume.changed.connect(front)
    front()
    from ornis_process import stop_all
    app.aboutToQuit.connect(stop_all)
    app.aboutToQuit.connect(sync.shutdown)
    app.aboutToQuit.connect(mail.flush)
    app.aboutToQuit.connect(mail.shutdown)
    app.aboutToQuit.connect(suite.give_back)
    app.aboutToQuit.connect(updater.install_on_quit)

    engine = QQmlApplicationEngine()
    qmlvalue.use(engine)
    # `app` too: the shared components (design/qml-kit) read their texts from it, as in the other apps
    for name, obj in (("plume", plume), ("app", plume), ("theme", theme), ("agenda", agenda), ("people", people), ("mail", mail),
                      ("rich", rich), ("ornis", ornis), ("suite", suite), ("signin", signin), ("updater", updater),
                      ("news", news), ("promo", promo)):
        engine.rootContext().setContextProperty(name, obj)
    suite.set_engine(engine)
    engine.load(QUrl.fromLocalFile(str(HERE / "qml" / "Main.qml")))
    if not engine.rootObjects():
        return 1
    if report is not None:
        return self_test(engine, suite, report)
    system.integrate_appimage()
    if system.MACOS:
        app.open_with(plume.handle_args)
    plume.handle_args(args)
    sync.refresh()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
