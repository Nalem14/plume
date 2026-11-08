#!/usr/bin/python3
"""Mots de passe: the passwords of the Orneos account as a native app (Orneos OS), like macOS Passwords.

The cloud's Passwords app holds them; this window keeps an encrypted copy, so everything works offline and
changes go up when the network is back. It opens with the app password of Orneos Connect, nothing to type,
and shows its content only after the session password (or a finger). Verification codes, Wi-Fi networks,
sharing with other Orneos accounts, a security review and Ornis (who never sees a password).

One instance per session: a second launch hands its arguments to the first window and exits.
Usage: orneos-passwords [--show ID | --new | --security | --wifi | --generator | otpauth://…]
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

from passwords_core import bundle  # noqa: E402


def main():
    args = sys.argv[1:]
    QGuiApplication.setDesktopFileName("eu.orneos.passwords")
    qt = QGuiApplication(sys.argv)
    qt.setApplicationName("Mots de passe")
    qt.setOrganizationName("Orneos")
    qt.setWindowIcon(system.icon("eu.orneos.passwords"))
    if module.hand_over("passwords", args):
        return 0
    system.add_fonts()
    QQuickStyle.setStyle("Basic")

    passwords = bundle.build(qt)
    server = module.listen("passwords", passwords.app.handle_args)  # noqa: F841 (kept alive with the app)
    qt.applicationStateChanged.connect(
        lambda state: passwords.on_active() if state == Qt.ApplicationState.ApplicationActive else None)
    # closing the window quits, unless a copied password is still to be pasted (App.windowClosed)
    qt.setQuitOnLastWindowClosed(False)

    engine = QQmlApplicationEngine()
    qmlvalue.use(engine)
    for name, obj in passwords.context.items():
        engine.rootContext().setContextProperty(name, obj)
    engine.load(QUrl.fromLocalFile(str(passwords.window)))
    if not engine.rootObjects():
        return 1
    passwords.app.handle_args(args)
    return qt.exec()


if __name__ == "__main__":
    sys.exit(main())
