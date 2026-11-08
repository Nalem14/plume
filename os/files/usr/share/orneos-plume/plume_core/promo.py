"""Temporary offer of Orneos (admin > Offres on orneos.eu): a thin line above the account bar of every module,
never a window. Read from the cloud (app orneos, OCS /api/v1/offer, which asks orneos.eu), a few seconds after
the window shows, then every six hours. « × » hides it everywhere for this offer (site, cloud, Search).

Only Plume and Courrier (the `mail` edition on Orneos OS) ask: Agenda and Contacts stay quiet.
"""
import threading

from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot

import cloud

API = "/ocs/v2.php/apps/orneos/api/v1/offer"
EVERY_MS = 6 * 3600 * 1000


class Promo(QObject):
    changed = Signal()
    _loaded = Signal("QVariant")

    def __init__(self, plume, edition=""):
        super().__init__()
        self._plume = plume
        self._offer = None
        self._busy = False
        self._loaded.connect(self._set)
        self._timer = QTimer(self)
        self._timer.setInterval(EVERY_MS)
        self._timer.timeout.connect(self.check)
        if edition in ("", "mail"):
            plume.accountChanged.connect(lambda: QTimer.singleShot(6000, self.check))
            QTimer.singleShot(6000, self.check)
            self._timer.start()

    @Property("QVariant", notify=changed)
    def offer(self):
        return self._offer

    @Slot()
    def check(self):
        account = self._plume.account()
        if not account or self._busy:
            return
        self._busy = True
        threading.Thread(target=self._fetch, args=(account,), daemon=True).start()

    def _fetch(self, account):
        offer = None
        try:
            status, data = cloud.ocs(*account, API + "?format=json")
            o = (((data or {}).get("ocs") or {}).get("data") or {}).get("offer") if status == 200 else None
            if isinstance(o, dict) and o.get("id") and o.get("headline") and str(o.get("url", "")).startswith("https://"):
                offer = {k: o.get(k) for k in ("id", "headline", "text", "cta", "url", "hide")}
        except Exception:  # noqa: BLE001 - offline, old cloud: nothing to show, never an error
            offer = None
        self._loaded.emit(offer)

    def _set(self, offer):
        self._busy = False
        if offer != self._offer:
            self._offer = offer
            self.changed.emit()

    @Slot()
    def open(self):
        if self._offer:
            cloud.open_url(self._offer["url"])

    @Slot()
    def dismiss(self):
        """« × »: gone here at once, and everywhere else for this offer."""
        if not self._offer:
            return
        offer_id = int(self._offer["id"])
        self._offer = None
        self.changed.emit()
        account = self._plume.account()
        if account:
            threading.Thread(target=lambda: cloud.ocs(*account, API + "/dismiss?format=json", "PUT", {"offer": offer_id}),
                             daemon=True).start()
