#!/usr/bin/python3
"""Photos: the photo library of the Orneos account as a native app (Orneos OS), like Photos on macOS.

The cloud holds the photos (the folders of the library, Memories' timeline, Recognize's people, the albums of
the Photos app); this window keeps a copy of the library and its thumbnails, so it opens at once and stays
readable offline, and every change (favourites, albums, deletions, imports) goes up when the network is back.
It opens with the app password of Orneos Connect, nothing to type. People and places, edits applied by the
cloud, search in plain words with Ornis.

One instance per session: a second launch hands its arguments to the first window and exits.
Usage: orneos-photos [--show=FILEID | --view=VIEW | --search=WORDS | --import FILE…]
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

from photos_core import bundle  # noqa: E402


def main():
    args = sys.argv[1:]
    QGuiApplication.setDesktopFileName("eu.orneos.photos")
    system.native_dialogs()          # the system's file picker, not Qt's own
    qt = QGuiApplication(sys.argv)
    qt.setApplicationName("Photos")
    qt.setOrganizationName("Orneos")
    qt.setWindowIcon(system.icon("eu.orneos.photos"))
    qt.setQuitOnLastWindowClosed(False)     # Main.qml quits, once the last changes are sent (photos.leave)
    if module.hand_over("photos", args):
        return 0
    system.add_fonts()
    QQuickStyle.setStyle("Basic")

    photos = bundle.build(qt)
    server = module.listen("photos", photos.app.handle_args)  # noqa: F841 (kept alive with the app)
    qt.applicationStateChanged.connect(
        lambda state: photos.on_active() if state == Qt.ApplicationState.ApplicationActive else None)

    engine = QQmlApplicationEngine()
    qmlvalue.use(engine)
    for name, obj in photos.context.items():
        engine.rootContext().setContextProperty(name, obj)
    engine.load(QUrl.fromLocalFile(str(photos.window)))
    if not engine.rootObjects():
        return 1
    photos.app.handle_args(args)
    return qt.exec()


if __name__ == "__main__":
    sys.exit(main())
