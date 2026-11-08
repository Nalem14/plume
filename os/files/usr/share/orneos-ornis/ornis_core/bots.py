"""Code-mode bots roster for the Ornis window (Plume / Orneos OS).

A bot is a durable profile (ornis_bots) with one canonical conversation run through CodeChat.
"""
from __future__ import annotations

import time

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

import ornis_bots
import ornis_cron

# Automatic peer replies without a human message in between (stops burning quota).
PEER_CHAIN_MAX = 3


class Bots(QObject):
    changed = Signal()
    toast = Signal(str)

    def __init__(self, app, code):
        super().__init__()
        self._app = app
        self._code = code
        from ornis_core.code import CodeChat
        self._worker = CodeChat(app)
        self._worker._background = True
        code._bot_peer_worker = self._worker
        self._pending = {}
        self._open_requested = ""
        self._worker.cronDone.connect(self._peer_done)
        code.cronDone.connect(self._peer_done)
        self._query = ""
        self._delivering = False
        # when CodeChat finishes a turn for a bot, refresh the roster preview and drain peer inbox
        try:
            code.changed.connect(self._on_code)
            code.finished.connect(self._on_finished)
        except Exception:  # noqa: BLE001
            pass
        self._tick = QTimer(self)
        self._tick.setInterval(12_000)
        self._tick.timeout.connect(self._drain_inbounds)
        self._tick.start()
        QTimer.singleShot(2500, self._drain_inbounds)

    def _on_code(self):
        self.changed.emit()

    def _on_finished(self, *_):
        self.changed.emit()
        QTimer.singleShot(400, self._drain_inbounds)

    def _t(self, key, fallback=""):
        return self._app._t.get(key, fallback)

    def _lang(self) -> str:
        return getattr(self._app, "_lang", "fr")[:2]

    @Property(str, notify=changed)
    def query(self):
        return self._query

    @Slot(str)
    def setQuery(self, text):
        self._query = str(text or "")
        self.changed.emit()

    @Property("QVariantList", notify=changed)
    def list(self):
        q = self._query.lower().strip()
        rows = []
        for b in ornis_bots.list_bots(include_hidden=True):
            if b.get("hidden"):
                continue
            hay = f"{b.get('title', '')} {b.get('description', '')} {b.get('id', '')} {b.get('preview', '')}".lower()
            if q and q not in hay:
                continue
            rows.append(self._row(b))
        return rows

    @Property("QVariantList", notify=changed)
    def hidden(self):
        q = self._query.lower().strip()
        rows = []
        for b in ornis_bots.list_bots(include_hidden=True):
            if not b.get("hidden"):
                continue
            hay = f"{b.get('title', '')} {b.get('id', '')}".lower()
            if q and q not in hay:
                continue
            rows.append(self._row(b))
        return rows

    def _row(self, b: dict) -> dict:
        current = getattr(self._code, "bot", None) or ""
        busy = bool((getattr(self._code, "busy", False) and current == b["id"]) or self._occupied(b["id"]))
        return {
            "id": b["id"],
            "title": b.get("title") or b["id"],
            "description": b.get("description") or "",
            "preview": b.get("preview") or "",
            "folder": b.get("folder") or "",
            "session": b.get("session") or "",
            "hidden": bool(b.get("hidden")),
            "face": b.get("face") or {},
            "when": _when(float(b.get("updated") or 0), self._lang()),
            "updated": float(b.get("updated") or 0),
            "current": current == b["id"],
            "busy": busy,
            "unread": 0,
        }

    @Property("QVariantMap", notify=changed)
    def current(self):
        bid = getattr(self._code, "bot", None) or ""
        if not bid:
            return {}
        b = ornis_bots.get(bid)
        return self._row(b) if b else {}

    @Slot(str)
    def open(self, bot_id):
        self._open_requested = bot_id
        profile = ornis_bots.get(bot_id)
        if not profile:
            self.toast.emit(self._t("bots_missing", "Ce bot n'existe plus"))
            return
        if self._occupied(bot_id):
            self.toast.emit(self._t("cron_watch_wait", "La conversation s’ouvrira à la fin du travail en cours"))
            opening = self._code._opening
            QTimer.singleShot(500, lambda: self._open_when_idle(bot_id, opening))
            return
        folder = ornis_bots.working_folder(bot_id)
        session = str(profile.get("session") or "")
        self._code.openBot(bot_id, folder, session)

    def _open_when_idle(self, bot_id, opening):
        if self._open_requested != bot_id or self._code._opening != opening:
            return
        if self._occupied(bot_id):
            QTimer.singleShot(500, lambda: self._open_when_idle(bot_id, opening))
        else:
            self.open(bot_id)

    @Slot(str, str, str, str, result="QVariantMap")
    def create(self, bot_id, title, description, folder):
        try:
            created = ornis_bots.create({
                "id": bot_id, "title": title, "description": description,
                "folder": folder or "",
            }, lang=self._lang())
        except ValueError as err:
            self.toast.emit(str(err))
            return {}
        self.changed.emit()
        self.open(created["id"])
        return self._row(created)

    @Slot(str, "QVariantMap", result="QVariantMap")
    def update(self, bot_id, fields):
        try:
            data = dict(fields or {})
            if "enabled_skills" in data:
                ornis_bots.set_enabled_skills(bot_id, list(data.pop("enabled_skills") or []))
            if any(k in data for k in ("shape", "color", "lock_face", "locked")):
                face = {}
                if data.get("shape"):
                    face["shape"] = data.pop("shape")
                if data.get("color"):
                    face["color"] = data.pop("color")
                if "lock_face" in data or "locked" in data:
                    face["locked"] = bool(data.pop("lock_face", data.pop("locked", False)))
                data["face"] = face
            updated = ornis_bots.update(bot_id, data)
        except ValueError as err:
            self.toast.emit(str(err))
            return {}
        if self._code.bot == bot_id:
            self._code._bot_brief = True
            if "folder" in data and not self._code.busy:
                self.open(bot_id)
        self.changed.emit()
        return self._row(updated) if updated else {}

    @Slot(str, str)
    def setSoul(self, bot_id, text):
        try:
            ornis_bots.set_soul(bot_id, text)
        except ValueError as err:
            self.toast.emit(str(err))
            return
        self.changed.emit()

    @Slot(str, result=str)
    def soul(self, bot_id):
        return ornis_bots.read_soul(bot_id)

    @Slot(str, result="QVariantList")
    def skills(self, bot_id):
        profile = ornis_bots.get(bot_id) or {}
        owned = ornis_bots.list_skills(bot_id)
        enabled = set(profile.get("enabled_skills") or [])
        try:
            import ornis_extensions  # noqa: PLC0415
            global_skills = ornis_extensions.list_skills()
        except Exception:  # noqa: BLE001
            global_skills = []
        rows = [{"name": s["name"], "description": s.get("description") or "", "owned": True, "on": True}
                for s in owned]
        for s in global_skills:
            rows.append({
                "name": s["name"], "description": s.get("description") or "",
                "owned": False, "on": s["name"] in enabled,
            })
        return rows

    @Slot(str, bool)
    def setHidden(self, bot_id, hidden):
        try:
            ornis_bots.update(bot_id, {"hidden": bool(hidden)})
        except ValueError as err:
            self.toast.emit(str(err))
            return
        self.changed.emit()

    @Slot(str)
    def remove(self, bot_id):
        if self._occupied(bot_id):
            self.toast.emit(self._t("cron_already", "Ce bot travaille encore"))
            return
        if self._code.bot == bot_id:
            self._code.clearBot()
        try:
            ornis_bots.remove(bot_id, confirm=True)
        except ValueError as err:
            self.toast.emit(str(err))
            return
        if getattr(self._code, "bot", "") == bot_id:
            self._code.clearBot()
        self.changed.emit()

    @Slot(str, result="QVariantList")
    def routines(self, bot_id):
        """Cron tasks attached to this bot (shown as Routines)."""
        out = []
        for t in ornis_cron.tasks():
            if t.get("bot") != bot_id:
                continue
            out.append({
                "id": t.get("id"), "title": t.get("title") or t.get("id"),
                "description": t.get("description") or "",
                "schedule": t.get("schedule"), "scheduleLabel": t.get("scheduleLabel"),
                "prompt": t.get("prompt") or "", "paused": bool(t.get("paused")),
                "next_run": t.get("next_run"), "kind": t.get("kind") or "chat",
            })
        return out

    @Slot(str, "QVariantMap", result="QVariantMap")
    def patchRoutine(self, task_id, fields):
        try:
            updated = ornis_cron.patch(task_id, dict(fields or {}), self._lang())
        except ValueError as err:
            self.toast.emit(str(err))
            return {}
        self.changed.emit()
        return {
            "id": updated.get("id"), "title": updated.get("title"),
            "prompt": updated.get("prompt"), "schedule": updated.get("schedule"),
            "scheduleLabel": updated.get("scheduleLabel"), "paused": updated.get("paused"),
        }

    @Slot(str, str, result="QVariantList")
    def exchange(self, a, b):
        return ornis_bots.read_exchange(a, b, limit=200)

    @Slot(str, str)
    def markSeen(self, bot_id, peer):
        ornis_bots.mark_exchange_seen(bot_id, peer)
        if self._code.bot == bot_id:
            for i, row in enumerate(self._code._items.rows):
                if row.get("kind") == "peer" and row.get("peer") == peer:
                    row["unread"] = False
                    self._code._items.touch(i)
        self.changed.emit()

    @Slot(result="QVariantList")
    def shapes(self):
        return list(ornis_bots.SHAPES)

    @Slot(result="QVariantList")
    def colors(self):
        return list(ornis_bots.COLORS)

    @Slot(str, result="QVariantMap")
    def faceFor(self, title):
        return ornis_bots.face_from_name(title)

    @Slot(result="QVariantMap")
    def randomFace(self):
        import random  # noqa: PLC0415
        return {
            "shape": random.choice(list(ornis_bots.SHAPES)),
            "color": random.choice(list(ornis_bots.COLORS)),
            "locked": False,
        }

    @Slot(str, result=str)
    def profilePath(self, bot_id):
        try:
            return str(ornis_bots.bot_dir(bot_id))
        except ValueError:
            return ""

    @Slot(str, result=str)
    def memoryPath(self, bot_id):
        try:
            path = ornis_bots.bot_dir(bot_id) / "memory"
            path.mkdir(parents=True, exist_ok=True)
            return str(path)
        except ValueError:
            return ""

    def _peer_done(self, task_id, status, *_):
        pending = self._pending.pop(task_id, None)
        if pending and status == "ok":
            ornis_bots.ack_inbound(*pending)
        self._code.reloadIndex()
        self.changed.emit()
        if status == "ok":
            QTimer.singleShot(400, self._drain_inbounds)

    def _occupied(self, bid):
        cron = getattr(self._code, "_bot_cron", None)
        return bool((cron and cron._chat_busy and getattr(cron, "_running_bot", "") == bid)
                    or (self._worker.bot == bid and (self._worker.busy or self._worker._cron_job)))

    def _drain_inbounds(self):
        """One delivery at a time, never take over a foreground conversation."""
        self._code.syncBotExchanges()
        self.changed.emit()
        if self._delivering or self._worker.busy or self._worker._cron_job:
            return
        self._delivering = True
        try:
            for profile in ornis_bots.list_bots(include_hidden=True):
                bid = profile["id"]
                code = self._code
                same = code.bot == bid
                if self._occupied(bid) or (same and (code.busy or code._queued or code._cron_job)):
                    continue
                row = ornis_bots.peek_inbound(bid)
                if not row:
                    continue
                depth = int(row.get("depth") or 1)
                if depth > PEER_CHAIN_MAX or not ornis_bots.get(row.get("from") or ""):
                    ornis_bots.ack_inbound(bid, row["id"])
                    continue
                ornis_bots.update(bid, {"peer_depth": depth})
                prompt = (
                    f"[Bot message from {row.get('from')}]\n\n"
                    f"{row.get('text') or ''}\n\n"
                    "Reply to the sender using bot_message if useful. "
                    "If nothing needs a reply, end with [SILENT]. Do not continue a finished exchange."
                )
                runner = code if same else self._worker
                started = runner.runScheduled(ornis_bots.working_folder(bid), profile.get("title") or bid,
                                              prompt, f"peer-{row['id']}", bot=bid,
                                              session_id=str(profile.get("session") or ""))
                if not started:
                    continue
                self._pending[f"peer-{row['id']}"] = (bid, row["id"])
                self.changed.emit()
                break
        finally:
            self._delivering = False


def _when(ts: float, lang: str) -> str:
    if not ts:
        return ""
    age = time.time() - ts
    if age < 60:
        return {"fr": "à l'instant", "en": "now", "de": "gerade"}.get(lang, "now")
    if age < 3600:
        n = int(age // 60)
        return f"{n} min"
    if age < 86400:
        n = int(age // 3600)
        return f"{n} h"
    if age < 86400 * 14:
        n = int(age // 86400)
        return f"{n} j" if lang == "fr" else f"{n}d"
    return time.strftime("%d/%m", time.localtime(ts))
