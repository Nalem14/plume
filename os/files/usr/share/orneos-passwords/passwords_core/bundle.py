"""The objects of Mots de passe, made once: for its own window (passwords.py) or for its module in Plume."""
from pathlib import Path

from PySide6.QtCore import Qt

from module import Bundle
from passwords_core.app import App
from passwords_core.keeper import Keeper
from passwords_core.lock import Lock
from passwords_core.ornis import Ornis
from passwords_core.qr import Scanner
from passwords_core.theme import Theme
from passwords_core.wifi import Wifi

QML = Path(__file__).resolve().parent.parent / "qml"


def build(qt):
    theme = Theme(qt)
    app = App()
    keeper = Keeper(app)
    lock = Lock(app)
    qt.applicationStateChanged.connect(
        lambda state: lock.setActive(state == Qt.ApplicationState.ApplicationActive))
    qt.aboutToQuit.connect(keeper.shutdown)
    qt.aboutToQuit.connect(app.shutdown)

    def on_active():
        if keeper.stale(60):
            keeper.refresh()

    context = {"app": app, "theme": theme, "vault": keeper, "lock": lock, "wifi": Wifi(), "ornis": Ornis(app),
               "scanner": Scanner()}
    return Bundle("passwords", app, context, QML / "PasswordsView.qml", QML / "Main.qml", on_active)
