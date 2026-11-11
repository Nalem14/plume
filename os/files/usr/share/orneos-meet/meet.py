#!/usr/bin/python3
"""Meet: the conversations and calls of the Orneos account as a native app (Orneos OS), with the cloud's Talk.

Chats, one-to-one and group conversations, public links, calls with video and screen share: the same Talk as
the cloud, the phone and the old Meet, so everyone meets everyone. It opens with the app password of Orneos
Connect, nothing to type. The call runs in Chromium's WebRTC (QtWebEngine), the rest is QML.

It stays in the session (started at login with --agent): calls ring and messages notify with the window
closed. One instance: a second launch hands its arguments over.
Usage: orneos-meet [--agent | --room=TOKEN | --call=TOKEN | --to=USER | --new | --search=WORDS | <link /call/TOKEN>]
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
from PySide6.QtWebEngineQuick import QtWebEngineQuick  # noqa: E402

from meet_core import bundle  # noqa: E402


def main():
    args = sys.argv[1:]
    QtWebEngineQuick.initialize()                 # before the application: the call page needs it
    QGuiApplication.setDesktopFileName("eu.orneos.meet")
    system.native_dialogs()          # the system's file picker, not Qt's own
    qt = QGuiApplication(sys.argv)
    qt.setApplicationName("Meet")
    qt.setOrganizationName("Orneos")
    qt.setWindowIcon(system.icon("eu.orneos.meet"))
    if module.hand_over("meet", args):
        return 0
    system.add_fonts()
    QQuickStyle.setStyle("Basic")
    qt.setQuitOnLastWindowClosed(False)           # calls still ring

    meet = bundle.build(qt)
    library = meet.context["meet"]
    engine = None

    def window():
        nonlocal engine
        if engine is None:
            engine = QQmlApplicationEngine()
            qmlvalue.use(engine)
            bundle.add_images(engine, library)
            for name, obj in meet.context.items():
                engine.rootContext().setContextProperty(name, obj)
            engine.load(QUrl.fromLocalFile(str(meet.window)))
        roots = engine.rootObjects()
        return roots[0] if roots else None

    def raise_window():
        win = window()
        if win is not None and not win.isVisible():
            win.show()
    meet.app.raiseRequested.connect(raise_window)

    def handle(args, token=""):
        if "--yield" in args:                    # Plume takes Meet over: an agent without a window leaves
            shown = engine is not None and window() is not None and window().isVisible()
            if not shown and not meet.context["calls"].active:
                qt.quit()
            return
        meet.app.handle_args(args, token)
    server = module.listen("meet", handle)  # noqa: F841 (kept alive with the app)
    qt.applicationStateChanged.connect(
        lambda state: library.set_active(state == Qt.ApplicationState.ApplicationActive))

    library.set_active("--agent" not in args)
    meet.app.handle_args(args)
    return qt.exec()


if __name__ == "__main__":
    sys.exit(main())
