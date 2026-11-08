"""The objects of Ornis, made once: for its own window (ornis.py) or for its module in Plume."""
from pathlib import Path

from module import Bundle
from ornis_core.app import App
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
    projects = Projects(app, chat)          # the Work mode's projects (instructions, folder, conversations)
    chat.projects = projects
    app.project_folder = lambda sid: projects.local_folder(sid)
    projects.toast.connect(app.toast)
    cron.toast.connect(app.toast)
    theme.setMode(app.pref("theme"))
    app.prefsChanged.connect(lambda: theme.setMode(app.pref("theme")))
    qt.aboutToQuit.connect(chat.flush)      # deletions still waiting for their undo
    qt.aboutToQuit.connect(code.shutdown)   # the coding agent stops with the window
    qt.aboutToQuit.connect(cron.shutdown)
    chat.badgeChanged.connect(dock_count())

    def on_active():
        chat.refresh(False)

    context = {"app": app, "theme": theme, "chat": chat, "code": code, "cron": cron, "projects": projects}
    # chat in keep: its badgeChanged gives Plume's rail the conversations with answers not read yet
    return Bundle("ornis", app, context, QML / "OrnisView.qml", QML / "Main.qml", on_active, keep=[chat, code, cron, projects])
