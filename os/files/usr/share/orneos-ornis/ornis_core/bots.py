"""Code-mode bots roster for the Ornis window (Plume / Orneos OS).

A bot is a durable profile (ornis_bots) with one canonical conversation run through CodeChat.
"""
from __future__ import annotations

import threading
import time

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

import ornis_bots
import ornis_cron

# Automatic peer replies without a human message in between (stops burning quota).
PEER_CHAIN_MAX = 3
PAGE = 60          # a group's messages loaded at once (older ones as you scroll up)


class Bots(QObject):
    changed = Signal()
    toast = Signal(str)
    badgeHint = Signal()          # the bots' and groups' unread total changed (bundle.py: into Ornis's one badge)

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
        self._worker.cronReply.connect(self._on_reply)
        code.cronReply.connect(self._on_reply)
        self._worker.changed.connect(self._on_code)
        self._query = ""
        self._delivering = False
        self._group = ""                 # the group open in the Group view
        self._group_rows: list[dict] = []
        self._group_limit = PAGE          # how many of the room's last messages are loaded (more as you scroll up)
        self._group_read_at = 0.0         # the person's previous visit: the « Non lu » bar
        self._group_anchor = ""           # where they were when they left (scrolled up), kept across restarts
        self._typing: dict[str, str] = {}   # bot id -> group id it is answering in
        self._stopping: set[str] = set()     # deliveries stopped by the person (no « could not answer » line)
        # CodeChat changes at each streamed word: the roster (which reads every profile on disk) is told at most
        # every 300 ms, not at each word
        self._relay = QTimer(self)
        self._relay.setSingleShot(True)
        self._relay.setInterval(300)
        self._relay.timeout.connect(self.changed)
        try:
            code.changed.connect(self._on_code)
            code.finished.connect(self._on_finished)
        except Exception:  # noqa: BLE001
            pass
        QTimer.singleShot(0, self._hook_cron)
        self._badge = 0
        self.changed.connect(self._check_badge)
        # a group turn cut by a crash or a quit left its mark: no turn runs at start, its hop count is stale
        for b in ornis_bots.list_bots():
            if b.get("group_turn"):
                try:
                    ornis_bots.update(b["id"], {"group_turn": "", "group_depth": 0})
                except ValueError:
                    pass
        self._tick = QTimer(self)
        self._tick.setInterval(12_000)
        self._tick.timeout.connect(self._drain_inbounds)
        self._tick.start()
        QTimer.singleShot(2500, self._drain_inbounds)

    def _on_code(self):
        if not self._relay.isActive():
            self._relay.start()

    def _on_finished(self, *_):
        self.changed.emit()
        QTimer.singleShot(400, self._drain_inbounds)

    def unreadTotal(self) -> int:
        """Bots and groups that spoke while you were elsewhere (what is open in front is not counted)."""
        total = sum(int(b.get("unread") or 0) for b in ornis_bots.list_bots()
                    if not (b["id"] == getattr(self._code, "bot", "") and not self._group))
        total += sum(int(g.get("unread") or 0) for g in ornis_bots.list_groups() if g["id"] != self._group)
        return total

    def _check_badge(self):
        total = self.unreadTotal()
        if total != self._badge:
            self._badge = total
            self.badgeHint.emit()

    def _hook_cron(self):
        cron = getattr(self._code, "_bot_cron", None)
        if cron is not None:
            cron.finished.connect(self._routine_done)

    def _routine_done(self, task_id, status, _summary):
        """A bot's routine ended on its own agent: a badge on the bot, unless its conversation is in front."""
        bid = str((ornis_cron.get(task_id) or {}).get("bot") or "")
        if bid and status == "ok" and not self._watching(bid):
            ornis_bots.bump_unread(bid)
        self.changed.emit()

    def _watching(self, bid: str) -> bool:
        """The person sees this bot's conversation right now (window in front, the bot open)."""
        from PySide6.QtGui import QGuiApplication  # noqa: PLC0415
        return bool(self._code.bot == bid and QGuiApplication.focusWindow() is not None)

    def _notify(self, title: str, text: str):
        if hasattr(self._app, "notify"):
            try:
                self._app.notify(title, text, "")
            except Exception:  # noqa: BLE001
                pass

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
        bg_bots = getattr(self._code, "_bg_bots", {}) or {}
        bg = bg_bots.get(b["id"])
        bg_busy = bool(bg and (bg.get("busy") or bg.get("queued") or bg.get("later")))
        busy = bool((getattr(self._code, "busy", False) and current == b["id"]) or bg_busy or self._occupied(b["id"]))
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
            "current": current == b["id"] and not self._group,
            "busy": busy,
            "unread": 0 if current == b["id"] else int(b.get("unread") or 0),
            "groups": [g["id"] for g in ornis_bots.groups_of(b["id"])],
            "paused": bool(b.get("paused")),
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
        self.release_worker(bot_id)                  # never two agents on one bot's conversation
        if self._group:
            self._leave_group()
        self._group, self._group_rows = "", []   # never a room's messages under an empty header
        unread = int(profile.get("unread") or 0)
        ornis_bots.clear_unread(bot_id)
        self._code.openBot(bot_id, folder, session)
        if unread and self._code.bot == bot_id:
            self._code.markUnread(unread)            # placed once its thread is replayed
        self.changed.emit()

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

    @Slot(result="QVariantList")
    def templates(self):
        """Starting points of « Nouveau bot » (ornis_bots.TEMPLATES)."""
        return list(ornis_bots.TEMPLATES.get(self._lang(), ornis_bots.TEMPLATES["en"]))

    @Slot(str, result="QVariantList")
    def skills(self, bot_id):
        profile = ornis_bots.get(bot_id) or {} if bot_id else {}
        owned = ornis_bots.list_skills(bot_id) if profile else []
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
    def setPaused(self, bot_id, paused):
        """On pause: no routine, no message nor group turn handled (they wait); the person can still write to it."""
        try:
            ornis_bots.update(bot_id, {"paused": bool(paused)})
        except ValueError as err:
            self.toast.emit(str(err))
            return
        self.toast.emit(self._t("bots_paused_on" if paused else "bots_paused_off", ""))
        self.changed.emit()
        if not paused:
            QTimer.singleShot(200, self._drain_inbounds)

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

    def _peer_done(self, task_id, status, summary="", *_):
        pending = self._pending.pop(task_id, None)
        stopped = task_id in self._stopping
        self._stopping.discard(task_id)
        low = str(summary or "").lower()
        quota = status != "ok" and ("402" in low or "quota" in low or "plan_required" in low)
        dropped = False
        if pending and status == "ok":
            ornis_bots.ack_inbound(pending[0], pending[1])
        elif pending:
            dropped = ornis_bots.fail_inbound(pending[0], pending[1])     # kept for a retry, dropped after 3 failures
        if pending and len(pending) > 2 and pending[2]:
            bid, gid = pending[0], pending[2]
            self._typing.pop(bid, None)
            try:
                ornis_bots.update(bid, {"group_turn": ""})       # out of the group turn: its hand-overs stop counting
            except ValueError:
                pass
            if (dropped or quota) and not stopped and ornis_bots.get_group(gid):
                # the room says it, once, in words (a bot that silently stopped « typing » looks broken)
                why = self._t("code_quota") if quota else self._t("cron_failed", "Échec")
                ornis_bots.group_notice(gid, self._t("groups_failed", "%1 n’a pas pu répondre : %2")
                                        .replace("%1", self._title(bid)).replace("%2", why))
                if quota and not dropped:
                    ornis_bots.ack_inbound(bid, pending[1])     # the limit will not lift in 5 s: no retries
            self._reload_group()
        self._code.reloadIndex()
        self.changed.emit()
        if status == "ok":
            QTimer.singleShot(400, self._drain_inbounds)
        else:
            QTimer.singleShot(5000, self._drain_inbounds)      # an error: try again later, not in a tight loop

    def _on_reply(self, task_id, text):
        """A delivered turn ended: a group answer goes to the room; a bot that spoke away from the person gets a
        badge (and a notification for a message that came from another bot)."""
        pending = self._pending.get(task_id)
        if not pending:
            return
        bid, _row_id, gid = pending[0], pending[1], (pending[2] if len(pending) > 2 else "")
        text = str(text or "").strip()
        if gid:
            self._typing.pop(bid, None)
            # already posted by the bot itself (group_post) during this very turn: not twice. Only since the turn
            # began: an answer the same as an earlier one (« OK », « Fait. ») is still posted
            started = float(pending[3]) if len(pending) > 3 else time.time()
            mine = [r for r in ornis_bots.read_group(gid, limit=20)
                    if r.get("from") == bid and float(r.get("at") or 0) >= started]
            if text and any(r.get("text", "").strip() == text for r in mine):
                text = ""
            if text:
                try:
                    ornis_bots.post_group(gid, bid, text, depth=ornis_bots.turn_depth(bid, gid))
                except ValueError:
                    pass
                if gid == self._group and self._front():
                    ornis_bots.update_group(gid, {"read_at": time.time()})
                if gid != self._group or not self._front():
                    try:
                        g = ornis_bots.get_group(gid) or {}
                        ornis_bots.update_group(gid, {"unread": int(g.get("unread") or 0) + 1})
                    except ValueError:
                        pass
                    if not self._front():
                        self._notify(f"{self._title(bid)} · {(ornis_bots.get_group(gid) or {}).get('title') or gid}", text)
            self._reload_group()
        elif text and not self._watching(bid):
            ornis_bots.bump_unread(bid)
        self.changed.emit()

    @staticmethod
    def _front() -> bool:
        from PySide6.QtGui import QGuiApplication  # noqa: PLC0415
        return QGuiApplication.focusWindow() is not None

    @staticmethod
    def _title(bid: str) -> str:
        return (ornis_bots.get(bid) or {}).get("title") or bid

    def release_worker(self, bot_id: str) -> None:
        """The background worker idle on this bot lets it go (its agent keeps the conversation in memory: another
        agent taking it — the window, a routine's own agent — would have its turns overwritten by a stale copy)."""
        w = self._worker
        if w.bot == bot_id and not w.busy and not w._cron_job:
            w.clearBot()

    def _occupied(self, bid):
        cron = getattr(self._code, "_bot_cron", None)
        return bool((cron and cron._chat_busy and getattr(cron, "_running_bot", "") == bid)
                    or (self._worker.bot == bid and (self._worker.busy or self._worker._cron_job)))

    def _drain_inbounds(self):
        """One delivery at a time, never take over a foreground conversation. Also shows the bots' notifications."""
        for row in ornis_bots.take_notices():
            bid = str(row.get("bot") or "")
            self._notify(row.get("title") or self._title(bid), row.get("text") or "")
            if bid and not self._watching(bid):
                ornis_bots.bump_unread(bid)
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
                bg_bots = getattr(code, "_bg_bots", {}) or {}
                if self._occupied(bid) or bid in bg_bots or (same and (code.busy or code._queued or code._cron_job)):
                    continue
                if profile.get("paused"):
                    continue                          # on pause: what waits for it stays in its inbox
                row = ornis_bots.peek_inbound(bid)
                if not row:
                    continue
                gid = str(row.get("group") or "")
                depth = int(row.get("depth") or (0 if gid else 1))
                sender_ok = (gid and row.get("from") == "user") or bool(ornis_bots.get(row.get("from") or ""))
                if (not gid and depth > PEER_CHAIN_MAX) or not sender_ok or (gid and not ornis_bots.get_group(gid)):
                    ornis_bots.ack_inbound(bid, row["id"])
                    continue
                if gid:
                    ornis_bots.update(bid, {"group_depth": depth, "group_turn": gid})
                    prompt = ornis_bots.group_prompt(bid, row)
                else:
                    ornis_bots.update(bid, {"peer_depth": depth})
                    prompt = (
                        f"[Bot message from {row.get('from')}]\n\n"
                        f"{row.get('text') or ''}\n\n"
                        "Reply to the sender using bot_message if useful. "
                        "If nothing needs a reply, end with [SILENT]. Do not continue a finished exchange."
                    )
                runner = code if same else self._worker
                task = f"{'group' if gid else 'peer'}-{row['id']}"
                started = runner.runScheduled(ornis_bots.working_folder(bid), profile.get("title") or bid,
                                              prompt, task, bot=bid,
                                              session_id=str(profile.get("session") or ""))
                if not started:
                    continue
                self._pending[task] = (bid, row["id"], gid, time.time())
                if gid:
                    self._typing[bid] = gid
                self.changed.emit()
                break
        finally:
            self._delivering = False

    # ---- groups ------------------------------------------------------------------------------------------------
    def _group_row(self, g: dict) -> dict:
        faces = []
        for mid in g["members"][:4]:
            p = ornis_bots.get(mid) or {}
            faces.append(p.get("face") or {})
        return {
            "id": g["id"], "title": g["title"], "description": g.get("description") or "",
            "members": g["members"], "lead": g["lead"], "reply": g["reply"], "faces": faces,
            "preview": g.get("preview") or "", "when": _when(float(g.get("updated") or 0), self._lang()),
            "unread": 0 if g["id"] == self._group else int(g.get("unread") or 0),
            "current": g["id"] == self._group,
            "busy": any(v == g["id"] for v in self._typing.values()),
        }

    @Property("QVariantList", notify=changed)
    def groups(self):
        q = self._query.lower().strip()
        return [self._group_row(g) for g in ornis_bots.list_groups()
                if not q or q in f"{g['title']} {g.get('description', '')} {' '.join(g['members'])}".lower()]

    @Property(str, notify=changed)
    def groupId(self):
        return self._group

    @Property("QVariantMap", notify=changed)
    def group(self):
        g = ornis_bots.get_group(self._group) if self._group else None
        if not g:
            return {}
        row = self._group_row(g)
        row["folder"] = ornis_bots.group_folder(g["id"])
        row["folderChosen"] = str(g.get("folder") or "")
        row["people"] = [{"id": m, "title": self._title(m), "face": (ornis_bots.get(m) or {}).get("face") or {},
                          "description": (ornis_bots.get(m) or {}).get("description") or "",
                          "lead": m == g["lead"], "typing": self._typing.get(m) == g["id"]} for m in g["members"]]
        return row

    @Property("QVariantList", notify=changed)
    def groupMessages(self):
        return self._group_rows

    @Property("QVariantList", notify=changed)
    def typing(self):
        """Who is answering in the open group right now (« Orla écrit… »)."""
        return [{"id": b, "title": self._title(b), "face": (ornis_bots.get(b) or {}).get("face") or {}}
                for b, gid in self._typing.items() if gid == self._group and self._group]

    @Property(bool, notify=changed)
    def groupHasMore(self):
        return bool(self._group) and ornis_bots.group_size(self._group) > len(self._group_rows)

    @Property(int, notify=changed)
    def groupFirstUnread(self):
        """Index of the « Non lu » bar in groupMessages (-1: nothing new since the last visit)."""
        return next((i for i, r in enumerate(self._group_rows) if r.get("unreadStart")), -1)

    @Property(int, notify=changed)
    def groupAnchor(self):
        """Index of the message the person had at the top when they left, scrolled up (-1: the end)."""
        if not self._group_anchor:
            return -1
        return next((i for i, r in enumerate(self._group_rows) if r.get("id") == self._group_anchor), -1)

    @Slot(result=int)
    def loadOlderGroup(self):
        """Scrolled to the top: the page before. Returns how many rows came in (the view keeps its place)."""
        if not self.groupHasMore:
            return 0
        before = len(self._group_rows)
        self._group_limit += PAGE
        self._reload_group()
        self.changed.emit()
        return len(self._group_rows) - before

    @Slot(str)
    def setGroupAnchor(self, message_id):
        """Where the person is in the room (the top message, "" at the end): saved, to come back there."""
        message_id = str(message_id or "")
        if not self._group or message_id == self._group_anchor:
            return
        self._group_anchor = message_id
        try:
            ornis_bots.update_group(self._group, {"anchor": message_id})
        except ValueError:
            pass

    def _reload_group(self):
        if not self._group:
            self._group_rows = []
            return
        rows = []
        prev = None
        lang = self._lang()
        everything = ornis_bots.read_group(self._group, limit=100000)
        # the window holds at least the first unread and the saved place, whatever the page
        need = self._group_limit
        for i, r in enumerate(everything):
            if (r.get("id") == self._group_anchor
                    or (self._group_read_at and float(r.get("at") or 0) > self._group_read_at and r.get("from") != "user")):
                need = max(need, len(everything) - i + 5)
                break
        self._group_limit = need
        marked = False
        for r in everything[-need:]:
            sender = str(r.get("from") or "")
            if sender == "system":
                rows.append({"id": r.get("id"), "from": "system", "system": True, "mine": False, "text": r.get("text") or "",
                             "title": "", "face": {}, "time": "", "day": "", "first": True, "last": True,
                             "_day": prev["_day"] if prev else "", "_at": float(r.get("at") or 0)})
                prev = rows[-1]
                continue
            mine = sender == "user"
            p = {} if mine else (ornis_bots.get(sender) or {})
            at = float(r.get("at") or 0)
            day = time.strftime("%Y-%m-%d", time.localtime(at))
            rows.append({
                "id": r.get("id"), "from": sender, "mine": mine, "text": r.get("text") or "",
                "title": "" if mine else (p.get("title") or sender), "face": p.get("face") or {},
                "time": time.strftime("%H:%M", time.localtime(at)),
                "day": _day(at, lang) if not prev or prev["_day"] != day else "",
                # one name and one face per run of messages from the same sender (as a chat app)
                "first": not prev or prev["from"] != sender or at - prev["_at"] > 600 or (prev["_day"] != day),
                "_day": day, "_at": at,
            })
            if (not marked and self._group_read_at and at > self._group_read_at and not mine):
                rows[-1]["unreadStart"] = True
                marked = True
            prev = rows[-1]
        for i, r in enumerate(rows):
            nxt = rows[i + 1] if i + 1 < len(rows) else None
            r["last"] = not nxt or nxt["first"]
        self._group_rows = rows

    @Slot(str)
    def openGroup(self, group_id):
        g = ornis_bots.get_group(group_id)
        if not g:
            self.toast.emit(self._t("groups_missing", "Ce groupe n’existe plus"))
            return
        if self._group and self._group != g["id"]:
            self._leave_group()
        self._group = g["id"]
        self._group_limit = PAGE
        self._group_read_at = float(g.get("read_at") or 0)
        self._group_anchor = str(g.get("anchor") or "")
        ornis_bots.update_group(g["id"], {"unread": 0, "read_at": time.time()})
        self._reload_group()
        self.changed.emit()

    def _leave_group(self):
        """Leaving a room: what is there now counts as read."""
        try:
            ornis_bots.update_group(self._group, {"read_at": time.time(), "unread": 0})
        except ValueError:
            pass

    @Slot()
    def closeGroup(self):
        if self._group:
            self._leave_group()
        self._group, self._group_rows = "", []
        self.changed.emit()

    @Slot(str, result=bool)
    def postGroup(self, text):
        text = str(text or "").strip()
        if not self._group or not text:
            return False
        try:
            row = ornis_bots.post_group(self._group, "user", text)
        except ValueError as err:
            self.toast.emit(str(err))
            return False
        for mid in ornis_bots.get_group(self._group)["members"]:
            ornis_bots.update(mid, {"group_depth": 0, "peer_depth": 0})     # a human spoke: the hops start again
        self._group_read_at, self._group_anchor = 0.0, ""                   # you answered: no « Non lu » bar any more
        ornis_bots.update_group(self._group, {"read_at": time.time(), "anchor": ""})
        if not row.get("targets"):
            self.toast.emit(self._t("groups_nobody", "Personne n’est concerné : mentionnez un bot avec @"))
        self._reload_group()
        self.changed.emit()
        QTimer.singleShot(100, self._drain_inbounds)
        return True

    @Slot(str, str, "QVariantList", str, str, str, result=str)
    def createGroup(self, title, description, members, lead, reply, folder=""):
        try:
            g = ornis_bots.create_group({"title": title, "description": description, "members": list(members or []),
                                         "lead": lead, "reply": reply, "folder": folder})
        except ValueError as err:
            self.toast.emit(str(err))
            return ""
        self._resandbox(g["members"])
        self.openGroup(g["id"])
        return g["id"]

    def _resandbox(self, members):
        """A shared folder is writable from an agent's next start: the idle agents of these bots start again."""
        for runner in (self._code, self._worker):
            agent = getattr(runner, "_agent", None)
            if runner.bot in members and agent is not None and not runner.busy and not runner._cron_job:
                runner._agent = None
                runner._state = "idle"
                threading.Thread(target=agent.close, daemon=True).start()

    @Slot(str, result=str)
    def groupFolder(self, group_id):
        try:
            return ornis_bots.group_folder(group_id)
        except (ValueError, OSError):
            return ""

    @Slot(str, "QVariantMap", result=bool)
    def updateGroup(self, group_id, fields):
        try:
            g = ornis_bots.update_group(group_id, dict(fields or {}))
            if "folder" in (fields or {}) or "members" in (fields or {}):
                self._resandbox(g["members"])
        except ValueError as err:
            self.toast.emit(str(err))
            return False
        self._reload_group()
        self.changed.emit()
        return True

    @Slot(str)
    def removeGroup(self, group_id):
        ornis_bots.remove_group(group_id)
        if self._group == group_id:
            self._group, self._group_rows = "", []
        self.changed.emit()

    @Slot(str, result="QVariantMap")
    def groupInfo(self, group_id):
        g = ornis_bots.get_group(group_id)
        return dict(g) if g else {}

    @Slot()
    def stopGroup(self):
        """Stop the bots answering in the open group, and what still waits for them there."""
        gid = self._group
        if not gid:
            return
        for task, p in self._pending.items():
            if len(p) > 2 and p[2] == gid:
                self._stopping.add(task)
        for bid in [b for b, g in self._typing.items() if g == gid]:
            runner = self._code if self._code.bot == bid else self._worker
            if runner.busy:
                runner.stop()
        ornis_bots.drop_group_inbox(gid)
        self.changed.emit()


def _day(ts: float, lang: str) -> str:
    local = time.localtime(ts)
    today = time.localtime()
    if local[:3] == today[:3]:
        return {"fr": "Aujourd’hui", "en": "Today", "de": "Heute"}.get(lang, "Today")
    if time.strftime("%Y-%m-%d", local) == time.strftime("%Y-%m-%d", time.localtime(time.time() - 86400)):
        return {"fr": "Hier", "en": "Yesterday", "de": "Gestern"}.get(lang, "Yesterday")
    return time.strftime("%d/%m/%Y", local)


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
