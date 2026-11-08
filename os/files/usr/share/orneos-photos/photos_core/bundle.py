"""The objects of Photos, made once for its window (photos.py)."""
from pathlib import Path

from module import Bundle
from photos_core.app import App
from photos_core.library import Library
from photos_core.ornis import Ornis
from photos_core.theme import Theme
from photos_core.thumbs import Thumbs

QML = Path(__file__).resolve().parent.parent / "qml"


def build(qt):
    theme = Theme(qt)
    app = App()
    thumbs = Thumbs(app.account)
    library = Library(app, thumbs)
    ornis = Ornis(app, library)
    qt.aboutToQuit.connect(library.shutdown)

    def on_active():
        if library.stale(60):
            library.refresh()

    context = {"app": app, "theme": theme, "photos": library, "ornis": ornis, "thumbs": thumbs}
    return Bundle("photos", app, context, QML / "PhotosView.qml", QML / "Main.qml", on_active)
