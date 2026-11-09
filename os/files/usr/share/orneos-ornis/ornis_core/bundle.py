"""The objects of Ornis, made once: for its own window (ornis.py) or for its module in Plume."""
from pathlib import Path

from module import Bundle
from ornis_core.app import App
from ornis_core.bots import Bots
from ornis_core.chat import Chat
from ornis_core.code import CodeChat
from ornis_core.cron import Cron
from ornis_core.projects import Projects
from ornis_core.theme import Theme

QML = Path(__file__).resolve().parent.parent / "qml"


def dock_count():
    """The conversations with answers not read yet, on the dock's pin (Unity LauncherEntry, like Meet and Tâches)."""
    try:
        from PySide6.QtDBus import QDBusConnection, QDBusMessage  # noqa: PLC0415 - Linux only
        import cloud  # noqa: PLC0415
    except ImportError:
        return lambda count: None
    bus = QDBusConnection.sessionBus()
    uri = "application://eu.orneos.assistant.desktop"
    path = f"/com/canonical/unity/launcherentry/{cloud._djb2(uri)}"
    last = [None]

    def show(count):
        if count == last[0] or not bus.isConnected():
            return
        last[0] = count
        message = QDBusMessage.createSignal(path, "com.canonical.Unity.LauncherEntry", "Update")
        message.setArguments([uri, {"count": int(count), "count-visible": count > 0, "urgent": False}])
        bus.send(message)
    return show


def build(qt):
    theme = Theme(qt)
    app = App()
    chat = Chat(app)
    code = CodeChat(app)                    # the « Code » mode: Ornis works in a folder of the computer
    cron = Cron(app, code)                  # local Code cron tasks (not cloud scheduled Chat tasks)
    bots = Bots(app, code)                  # durable Code bots (SOUL, routines, peer messages)
    browser = None                          # the browsers of the person and of each bot (Chromium), when there
    try:
        from PySide6 import QtWebEngineQuick  # noqa: F401, PLC0415
        from ornis_core.browser import Browser  # noqa: PLC0415
        import ornis_mcp_http  # noqa: PLC0415
        browser = Browser(app)
        ornis_mcp_http.register("browser", browser.mcp_handle)
        # the window asks (OrnisView); a notification too, Plume may be in the tray
        browser.consentRequested.connect(lambda owner, name: app.toast.emit(
            app._t.get("browser_keychain_ask", "%1 demande le Trousseau").replace("%1", name)))
    except ImportError:
        pass
    projects = Projects(app, chat)          # the Work mode's projects (instructions, folder, conversations)
    chat.projects = projects
    app.project_folder = lambda sid: projects.local_folder(sid)

    def path_bases():
        """Where a path named in a message is looked for: the open group's shared folder and its members' folders,
        the Code folder (a bot's working folder), the bot's profile (memory/, skills/), the Work project's folder."""
        out = []
        try:
            import ornis_bots  # noqa: PLC0415
            if bots._group:
                out.append(ornis_bots.group_folder(bots._group))
                g = ornis_bots.get_group(bots._group) or {}
                out += [ornis_bots.working_folder(m) for m in g.get("members") or []]
            if code._folder:
                out.append(code._folder)
            if code._bot:
                out.append(str(ornis_bots.bot_dir(code._bot)))
        except Exception:  # noqa: BLE001
            if code._folder:
                out.append(code._folder)
        try:
            out.append(projects.local_folder(chat.current) or "")
        except Exception:  # noqa: BLE001
            pass
        try:                                     # last: the other bots' folders (a bot citing another's file)
            import ornis_bots  # noqa: PLC0415
            out += [ornis_bots.working_folder(b["id"]) for b in ornis_bots.list_bots(include_hidden=True)]
        except Exception:  # noqa: BLE001
            pass
        seen = set()
        return [b for b in out if b and not (b in seen or seen.add(b))]
    app.path_bases = path_bases
    projects.toast.connect(app.toast)
    cron.toast.connect(app.toast)
    bots.toast.connect(app.toast)
    chat.extra_badge = bots.unreadTotal     # one badge: conversations, bots and groups not read yet
    bots.badgeHint.connect(chat.refreshBadge)
    theme.setMode(app.pref("theme"))
    app.prefsChanged.connect(lambda: theme.setMode(app.pref("theme")))
    qt.aboutToQuit.connect(chat.flush)      # deletions still waiting for their undo
    qt.aboutToQuit.connect(code.shutdown)   # the coding agent stops with the window
    qt.aboutToQuit.connect(cron.shutdown)
    qt.aboutToQuit.connect(bots._worker.shutdown)
    chat.badgeChanged.connect(dock_count())

    def on_active():
        chat.refresh(False)

    context = {"app": app, "theme": theme, "chat": chat, "code": code, "cron": cron, "bots": bots, "projects": projects,
               "browser": browser}
    # chat in keep: its badgeChanged gives Plume's rail the conversations with answers not read yet
    return Bundle("ornis", app, context, QML / "OrnisView.qml", QML / "Main.qml", on_active, keep=[chat, code, cron, bots, projects] + ([browser] if browser else []))
