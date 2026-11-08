"""A native app as a module: one instance per user, its objects for QML, its view.

Each app (Courrier, Agenda, Contacts, Notes, Tâches, Ornis) answers on its own local socket. Its window or
Plume, whichever holds the socket, is the one that runs it: a second launch hands its arguments over and
exits, so two processes never sync the same copy. Plume holds the sockets of every module it shows.
"""
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QByteArray
from PySide6.QtNetwork import QLocalServer, QLocalSocket

import system


def socket_name(kind: str) -> str:
    return f"eu.orneos.{kind}-{system.user_id()}"


def hand_over(kind: str, args, wait_ms: int = 400) -> bool:
    """Give the arguments to the running instance. True when one took them."""
    sock = QLocalSocket()
    sock.connectToServer(socket_name(kind))
    if not sock.waitForConnected(wait_ms):
        return False
    payload = {"args": list(args), "token": os.environ.get("XDG_ACTIVATION_TOKEN", "")}
    sock.write(QByteArray(json.dumps(payload).encode()))
    sock.waitForBytesWritten(800)
    sock.disconnectFromServer()
    return True


def is_taken(kind: str) -> bool:
    sock = QLocalSocket()
    sock.connectToServer(socket_name(kind))
    taken = sock.waitForConnected(300)
    if taken:
        sock.disconnectFromServer()
    return taken


def listen(kind: str, on_args) -> QLocalServer:
    """Answer on the app's socket: on_args(args, activation_token) for each launch handed over."""
    QLocalServer.removeServer(socket_name(kind))
    server = QLocalServer()
    server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
    server.listen(socket_name(kind))

    def accept():
        sock = server.nextPendingConnection()
        buffer = bytearray()

        def read():
            buffer.extend(bytes(sock.readAll().data()))

        def done():
            read()
            sock.deleteLater()
            if not buffer:                      # is_taken() only looked: not a launch
                return
            try:
                payload = json.loads(buffer.decode() or "{}")
            except (UnicodeDecodeError, json.JSONDecodeError):
                payload = {}
            on_args(payload.get("args") or [], payload.get("token") or "")

        sock.readyRead.connect(read)
        sock.disconnected.connect(done)

    server.newConnection.connect(accept)
    return server


@dataclass
class Bundle:
    """What an app is made of, for its own window or for its module in Plume.

    app: the object that takes the command-line arguments (handle_args) and asks for the window (raiseRequested);
    context: the names QML reads (app, theme, notes…); view: the QML file of the view (an Item);
    window: its own window (Main.qml); on_active: when the window comes back to the front."""
    kind: str
    app: object
    context: dict
    view: Path
    window: Path
    on_active: object = None
    keep: list = field(default_factory=list)       # other objects to keep alive with the module
