#!/usr/bin/python3
"""Notes: the notes of the Orneos account as a native app (Orneos OS), like macOS Notes.

The cloud's Notes app holds them (Markdown files in the Notes folder of the Drive); this window keeps a copy,
so everything works offline and changes go up when the network is back. It opens with the app password of
Orneos Connect, nothing to type. Folders, #tags, checklists, images, Quick Note (Meta+N), Ornis, and the
tasks of a note sent to Tâches.

One instance per session: a second launch hands its arguments to the first window and exits.
Usage: orneos-notes [--new | --quick | --daily | --show=ID | --folder=PATH | --search=WORDS | --files FILE…]
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

from notes_core import bundle  # noqa: E402


def main():
    args = sys.argv[1:]
    QGuiApplication.setDesktopFileName("eu.orneos.notes")
    qt = QGuiApplication(sys.argv)
    qt.setApplicationName("Notes")
    qt.setOrganizationName("Orneos")
    qt.setWindowIcon(system.icon("eu.orneos.notes"))
    if module.hand_over("notes", args):
        return 0
    system.add_fonts()
    QQuickStyle.setStyle("Basic")

    notes = bundle.build(qt, "--quick" in args)
    server = module.listen("notes", notes.app.handle_args)  # noqa: F841 (kept alive with the app)
    qt.applicationStateChanged.connect(
        lambda state: notes.on_active() if state == Qt.ApplicationState.ApplicationActive else None)

    engine = QQmlApplicationEngine()
    qmlvalue.use(engine)
    for name, obj in notes.context.items():
        engine.rootContext().setContextProperty(name, obj)
    engine.load(QUrl.fromLocalFile(str(notes.window)))
    if not engine.rootObjects():
        return 1
    notes.app.handle_args(args)
    return qt.exec()


if __name__ == "__main__":
    sys.exit(main())
