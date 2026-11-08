"""Orneos news, "Quoi de neuf": the announcements of the cloud's Announcement center not read yet, shown once
in a window, like Discord's. The read state lives in the cloud (app orneos, OCS /api/v1/news): read here, read
in the browser and on Orneos OS too, and the other way round.

Only Plume and Courrier (the `mail` edition on Orneos OS) ask, a few seconds after the window shows, then every
six hours while they run: Agenda and Contacts, the same code, stay quiet so that one window opens, not three.
"""
import threading
import time

from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot

import cloud

API = "/ocs/v2.php/apps/orneos/api/v1/news"
EVERY_MS = 6 * 3600 * 1000


class News(QObject):
    changed = Signal()
    _loaded = Signal(int, list, str)

    def __init__(self, plume, edition=""):
        super().__init__()
        self._plume = plume
        self._items = []
        self._busy = False
        self._active = False
        self._account = plume.account()
        self._generation = 0
        self._last_check = 0
        self._enabled = edition in ("", "mail")
        self._loaded.connect(self._received)
        self._timer = QTimer(self)
        self._timer.setInterval(EVERY_MS)
        self._timer.timeout.connect(self.check)
        if self._enabled:
            plume.accountChanged.connect(self._account_changed)
            QTimer.singleShot(4000, self.check)
            self._timer.start()

    @Property("QVariantList", notify=changed)
    def items(self):
        return self._items

    @Property(int, notify=changed)
    def generation(self):
        return self._generation

    def _account_changed(self):
        account = self._plume.account()
        if account == self._account:
            return
        self._account = account
        self._generation += 1
        self._busy = False
        self._last_check = 0
        self._items = []
        self.changed.emit()
        QTimer.singleShot(4000, self.check)

    @Slot(bool)
    def setActive(self, active):
        self._active = active
        if active:
            QTimer.singleShot(600, self.check)

    def _received(self, generation, items, url):
        if generation == self._generation:
            self._set(items, url)

    @Slot()
    def check(self):
        account = self._plume.account()
        self._account_changed()
        if not self._enabled or not self._active or not account or self._busy or self._items:
            return
        if self._last_check and time.monotonic() - self._last_check < 60:
            return
        self._busy = True
        self._last_check = time.monotonic()
        threading.Thread(target=self._fetch, args=(account, self._generation), daemon=True).start()

    def _fetch(self, account, generation):
        try:
            status, data = cloud.ocs(*account, API + "?format=json")
            data = ((data or {}).get("ocs") or {}).get("data") or {}
            items = [{"time": int(i.get("time") or 0), "subject": str(i.get("subject") or ""),
                      "html": str(i.get("html") or "")} for i in data.get("unread") or [] if i.get("subject")]
            self._loaded.emit(generation, items if status == 200 else [], str(data.get("url") or ""))
        except Exception:  # noqa: BLE001 - offline, old cloud: no news, never an error
            self._loaded.emit(generation, [], "")

    def _set(self, items, url):
        self._busy = False
        if items != self._items:
            self._items = items
            self.changed.emit()

    @Slot()
    @Slot(int)
    def markRead(self, generation=None):
        """The window was closed: everything shown is read, here and everywhere."""
        if generation is not None and generation != self._generation:
            return
        if not self._items or self._account != self._plume.account():
            return
        newest = max(i["time"] for i in self._items)
        self._items = []
        self.changed.emit()
        account = self._plume.account()
        if account:
            threading.Thread(target=lambda: cloud.ocs(*account, API + "/read?format=json", "PUT", {"time": newest}),
                             daemon=True).start()

    @Slot()
    def openAll(self):
        cloud.open_url(cloud.cloud_link("/apps/announcementcenter/"))
        self.markRead()
