#!/usr/bin/python3
"""Ornis: the Orneos assistant in a window (Orneos OS), beside its quick panel in the top bar (Meta+O).

The same conversations as in the cloud and in the panel, with room to read them: Ornis reads and acts in the
account (agenda, mail, notes, tasks, files, Meet…), shows what it is looking at while it works, and asks before
it sends, creates or shares anything. Its links open in Plume, Notes and Tâches; a mail, a note or a task dropped
on the message box tells it what you mean. Scheduled Chat tasks (« every morning… ») are listed and removed here.
Local Code cron tasks also run while this process is alive.

It stays in the session (started at login with --agent): Code cron fires with the window closed. One instance:
a second launch hands its arguments over.
Usage: ornis [--agent | --new | --session=ID | --ask=TEXT | --scheduled | --code]
"""
import os
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
try:                                    # the artifacts of the answers (pages, drawings, diagrams) are drawn by Chromium
    from PySide6.QtWebEngineQuick import QtWebEngineQuick  # noqa: E402
except ImportError:                     # without it, the preview pane keeps its text rendering
    QtWebEngineQuick = None

from ornis_core import bundle  # noqa: E402
from ornis_core.bundle import dock_count  # noqa: E402, F401


def main():
    args = sys.argv[1:]
    QGuiApplication.setDesktopFileName("eu.orneos.assistant")
    if QtWebEngineQuick is not None:
        # the bots' browsers work unseen (Plume in the tray, a routine at 8 h): Chromium must not slow their pages down
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "") + " --disable-renderer-backgrounding"
                                                    " --disable-background-timer-throttling --disable-backgrounding-occluded-windows").strip()
        QtWebEngineQuick.initialize()   # before the application; Chromium itself starts only with a first artifact
    system.native_dialogs()          # the system's file picker, not Qt's own
    qt = QGuiApplication(sys.argv)
    qt.setApplicationName("Ornis")
    qt.setOrganizationName("Orneos")
    qt.setWindowIcon(system.icon("eu.orneos.ornis"))
    if module.hand_over("ornis", args):
        return 0
    system.add_fonts()
    QQuickStyle.setStyle("Basic")
    qt.setQuitOnLastWindowClosed(False)   # Code cron keeps running with the window closed

    ornis = bundle.build(qt)
    chat = ornis.context["chat"]
    engine = None

    def window():
        nonlocal engine
        if engine is None:
            engine = QQmlApplicationEngine()
            qmlvalue.use(engine)
            for name, obj in ornis.context.items():
                engine.rootContext().setContextProperty(name, obj)
            engine.load(QUrl.fromLocalFile(str(ornis.window)))
        roots = engine.rootObjects()
        return roots[0] if roots else None

    def raise_window():
        win = window()
        if win is not None and not win.isVisible():
            win.show()
    ornis.app.raiseRequested.connect(raise_window)

    def handle(args, token=""):
        if "--yield" in args:                    # Plume takes Ornis over: an agent without a window leaves
            shown = engine is not None and window() is not None and window().isVisible()
            if not shown:
                qt.quit()
            return
        show = "--agent" not in args
        if show:
            raise_window()
        ornis.app.handle_args(args, token)

    server = module.listen("ornis", handle)  # noqa: F841 (kept alive with the app)

    def state_changed(state):
        front = state == Qt.ApplicationState.ApplicationActive
        chat.set_active(front)
        if front:
            ornis.on_active()
    qt.applicationStateChanged.connect(state_changed)

    chat.set_active("--agent" not in args)
    if "--agent" not in args:
        raise_window()
    ornis.app.handle_args([a for a in args if a != "--agent"])
    return qt.exec()


if __name__ == "__main__":
    sys.exit(main())
