"""Reminders, even with the window closed: Tâches stays in the session (started at login with --agent), reads
its copy every 30 s and shows a notification when a task's reminder comes, with « Terminé », « Dans 1 h »
and « Demain ». A reminder that came while the computer was off (up to a day and a half before) still shows,
marked « Rappel manqué » with its time. It keeps the copy in step meanwhile (every 10 minutes, and when the network returns), so a
task added on the phone reminds here too. The number of tasks for today (late ones included) shows on the
dock's icon.

Notifications go to Plasma's centre through notify-send (one waiting process per notification, which
prints the action chosen), the badge through the Unity launcher API that Plasma's task manager reads
(application://eu.orneos.tasks.desktop). In Plume (Windows, macOS), its tray shows them and a click opens
the task; the count goes to the tray and the app's icon (badgeChanged).
"""
import subprocess
import threading
import time
from datetime import datetime, timedelta

from PySide6.QtCore import QObject, QTimer, Signal, Slot

import system

try:
    from PySide6.QtDBus import QDBusConnection, QDBusMessage
except ImportError:                            # Windows, macOS: no session bus
    QDBusConnection = QDBusMessage = None

APP_URI = "application://eu.orneos.tasks.desktop"
SNOOZE_HOUR = 3600


def _djb2(text):
    h = 5381
    for ch in text.encode():
        h = ((h << 5) + h + ch) & 0xFFFFFFFF
    return h


class Reminders(QObject):
    _chosen = Signal(str, str)                 # task uid, action
    badgeChanged = Signal(int)

    def __init__(self, app, library, open_task):
        super().__init__()
        self._app = app
        self._library = library
        self._open_task = open_task            # callback: show a task in the window
        self._bus = QDBusConnection.sessionBus() if QDBusConnection is not None else None
        self._chosen.connect(self.onAction)
        self._timer = QTimer(self)
        self._timer.setInterval(30 * 1000)
        self._timer.timeout.connect(self.check)
        self._timer.start()
        library.badge.connect(self.set_badge)
        QTimer.singleShot(4000, self.check)

    @Slot()
    def check(self):
        if not self._app.pref("notify"):
            return
        store = self._library.store()
        if store is None:
            return
        now = int(time.time())
        for task, at in self._library.alarms_due(now):
            uid = task.get("uid", "")
            store.mark_fired(uid, at)
            store.unsnooze(uid)
            self._show(task, at, now)

    def _show(self, task, at=0, now=0):
        t = self._app.t
        when = ""
        if task.get("due_ts") and not task.get("all_day"):
            when = t["due_at"].replace("%1", datetime.fromtimestamp(task["due_ts"]).strftime("%H:%M"))
        if at and now - at > 15 * 60:
            when = t["reminder_missed"].replace("%1", self._app.long(at)) + (" · " + when if when else "")
        body = "\n".join(x for x in (when, (task.get("notes") or "").split("\n")[0][:120]) if x)
        uid = task.get("uid", "")
        if not system.has_notify_send():
            system.notify(task.get("title") or t["app_name"], body, lambda: self._chosen.emit(uid, "default"))
            return
        cmd = ["notify-send", "-a", t["app_name"], "-i", "eu.orneos.tasks", "-u", "normal", "--wait",
               "-h", "string:desktop-entry:eu.orneos.tasks", "-h", "string:category:x-orneos.reminder",
               f"--action=default={t['open']}", f"--action=done={t['mark_done']}",
               f"--action=later={t['later_hour']}", f"--action=tomorrow={t['later_tomorrow']}",
               task.get("title") or t["app_name"]]
        if body:
            cmd.append(body)

        def wait():
            try:
                out = subprocess.run(cmd, capture_output=True, text=True, timeout=6 * 3600).stdout.strip()
            except (OSError, subprocess.TimeoutExpired):
                return
            if out:
                self._chosen.emit(uid, out.splitlines()[-1])
        threading.Thread(target=wait, daemon=True).start()

    @Slot(str, str)
    def onAction(self, uid, action):
        store = self._library.store()
        key = self._library.resolve(uid)
        if not key or store is None:
            return
        if action == "done":
            self._library.toggleDone(key)
        elif action == "later":
            store.snooze(uid, time.time() + SNOOZE_HOUR)
        elif action == "tomorrow":
            morning = datetime.combine(datetime.now().date() + timedelta(days=1), datetime.min.time()).replace(hour=9)
            store.snooze(uid, morning.timestamp())
        else:
            self._open_task(key)

    @Slot(int)
    def set_badge(self, count):
        """The count on the dock's icon: today's tasks, late ones included (0 hides it)."""
        if not self._app.pref("badge"):
            count = 0
        self.badgeChanged.emit(int(count))
        if self._bus is None:
            return
        message = QDBusMessage.createSignal(f"/com/canonical/unity/launcherentry/{_djb2(APP_URI)}",
                                            "com.canonical.Unity.LauncherEntry", "Update")
        message.setArguments([APP_URI, {"count": int(count), "count-visible": count > 0, "urgent": False}])
        self._bus.send(message)
