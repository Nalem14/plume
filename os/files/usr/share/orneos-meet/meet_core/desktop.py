"""Meet on the desktop: the count on its dock pin (Unity LauncherEntry, like Tâches and Agenda) and the
notifications that open a conversation when clicked (notify-send on Orneos OS, Plume's tray elsewhere)."""
import html
import subprocess
import threading

from PySide6.QtCore import QObject, Qt, Signal

import cloud
import system

APP_ID = "eu.orneos.meet"


def dock_count():
    try:
        from PySide6.QtDBus import QDBusConnection, QDBusMessage  # noqa: PLC0415 - Linux only
    except ImportError:
        return lambda count: system.badge(count)
    bus = QDBusConnection.sessionBus()
    uri = f"application://{APP_ID}.desktop"
    path = f"/com/canonical/unity/launcherentry/{cloud._djb2(uri)}"
    last = [None]

    def show(count):
        system.badge(count)
        if count == last[0] or not bus.isConnected():
            return
        last[0] = count
        message = QDBusMessage.createSignal(path, "com.canonical.Unity.LauncherEntry", "Update")
        message.setArguments([uri, {"count": int(count), "count-visible": count > 0, "urgent": False}])
        bus.send(message)
    return show


class Count(QObject):
    """The conversations waiting for the user (Plume shows it on its rail, as Tâches' count)."""
    badgeChanged = Signal(int)


class Notifier(QObject):
    """notify(title, body, key, label): a click (or its action) gives `clicked(key)` on the UI thread."""
    clicked = Signal(str)
    _click = Signal(str)

    def __init__(self):
        super().__init__()
        self._click.connect(self.clicked, Qt.ConnectionType.QueuedConnection)

    def notify(self, title, body, key, label="", urgent=False, actions=None):
        if not system.has_notify_send():
            system.notify(title, body, lambda: self.clicked.emit(key))
            return
        cmd = ["notify-send", "-a", "Meet", "-i", APP_ID, "-h", f"string:desktop-entry:{APP_ID}",
               f"--action=default={label or 'Ouvrir'}"]
        for name, text in (actions or []):
            cmd.append(f"--action={name}={text}")
        if urgent:
            cmd += ["-u", "critical"]
        cmd += [title, html.escape(body or "", quote=False)]   # the body is markup for Plasma: a message stays text

        def wait():
            try:
                out = subprocess.run(cmd, capture_output=True, text=True, timeout=600).stdout.strip()
            except (OSError, subprocess.TimeoutExpired):
                return
            if out == "default":
                self._click.emit(key)
            elif out:
                self._click.emit(f"{out}:{key}")
        threading.Thread(target=wait, daemon=True).start()
