#!/usr/bin/python3
"""Tâches: the tasks and reminders of the Orneos account as a native app (Orneos OS), like macOS Reminders.

The lists live in the cloud (CalDAV, the same as the cloud's Tasks app and the phone); this app keeps a copy,
so everything works offline and changes go up when the network is back. It opens with the app password of
Orneos Connect, nothing to type. Smart lists, subtasks, dates in plain words, repeats, flags, tags, Ornis,
the mails tagged « À faire » in Plume, and the tasks sent from Notes.

It stays in the session (started at login with --agent): reminders come even with the window closed. One
instance: a second launch hands its arguments over (and opens the window, unless it only adds a task).
Usage: orneos-tasks [--agent | --new | --show=UID | --view=today|scheduled|all|flagged|completed|mail |
                     --search=WORDS | --add "Appeler Inès demain 18h" | --add-json JSON | --refresh]
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "orneos"))

import module  # noqa: E402
import system  # noqa: E402
import qmlvalue  # noqa: E402
from PySide6.QtCore import Qt, QUrl  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402
from PySide6.QtQuickControls2 import QQuickStyle  # noqa: E402

from tasks_core import bundle  # noqa: E402


def main():
    args = sys.argv[1:]
    QGuiApplication.setDesktopFileName("eu.orneos.tasks")
    qt = QGuiApplication(sys.argv)
    qt.setApplicationName("Tâches")
    qt.setOrganizationName("Orneos")
    qt.setWindowIcon(system.icon("eu.orneos.tasks"))
    if module.hand_over("tasks", args):
        return 0
    system.add_fonts()
    QQuickStyle.setStyle("Basic")
    qt.setQuitOnLastWindowClosed(False)          # the reminders stay

    tasks = bundle.build(qt)
    library = tasks.context["tasks"]
    engine = None

    def window():
        """The window is made the first time it is asked for (an agent started at login has none)."""
        nonlocal engine
        if engine is None:
            engine = QQmlApplicationEngine()
            qmlvalue.use(engine)
            for name, obj in tasks.context.items():
                engine.rootContext().setContextProperty(name, obj)
            engine.load(QUrl.fromLocalFile(str(tasks.window)))
            library.set_interval(5)
        roots = engine.rootObjects()
        return roots[0] if roots else None

    def raise_window():
        win = window()
        if win is not None and not win.isVisible():
            win.show()
    tasks.app.raiseRequested.connect(raise_window)

    def handle(args, token=""):
        # Plume (the suite) takes Tâches over on Orneos OS: an agent without a window leaves it the reminders
        if "--yield" in args:
            if engine is None or not (window() and window().isVisible()):
                qt.quit()
            return
        tasks.app.handle_args(args, token)
    server = module.listen("tasks", handle)  # noqa: F841 (kept alive with the app)
    qt.applicationStateChanged.connect(
        lambda state: tasks.on_active() if state == Qt.ApplicationState.ApplicationActive else None)

    library.set_interval(10 if "--agent" in args else 5)
    tasks.app.handle_args(args)
    return qt.exec()


if __name__ == "__main__":
    sys.exit(main())
