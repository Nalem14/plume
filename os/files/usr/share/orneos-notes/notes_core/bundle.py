"""The objects of Notes, made once: for its own window (notes.py) or for its module in Plume."""
from pathlib import Path

from module import Bundle
from notes_core.app import App
from notes_core.editor import EditorHelper
from notes_core.library import Library
from notes_core.ornis import Ornis
from notes_core.theme import Theme

QML = Path(__file__).resolve().parent.parent / "qml"


def build(qt, quick=False):
    theme = Theme(qt)
    app = App()
    library = Library(app)
    ornis = Ornis(app)
    qt.aboutToQuit.connect(library.shutdown)

    def on_active():
        if library.stale(60):
            library.refresh()

    context = {"app": app, "theme": theme, "notes": library, "ornis": ornis,
               "editorHelper": EditorHelper(theme), "quickHelper": EditorHelper(theme), "startQuick": quick}
    return Bundle("notes", app, context, QML / "NotesView.qml", QML / "Main.qml", on_active)
