"""Code-mode local cron: sticky list, schedule timer, background chat/script runs.

Separate from chat.scheduled (cloud). Needs Plume or Ornis running. One chat agent at a time;
scripts may run two in parallel. See ornis_cron for storage and crontab math.
"""
from __future__ import annotations

import json
import subprocess
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot
from PySide6.QtGui import QGuiApplication

import ornis_code
import ornis_cron
import ornis_shell
import system
from ornis_core.chat import _when

CRON_NOTE = (
    "[Scheduled Code task: nobody is watching. Do not ask questions (decline any ask_user_question). "
    "Pick the reasonable option yourself and say so briefly. Write results into the project folder. "
    "End with two short lines: what you did, and where the files are.]\n\n"
)
SCRIPT_TIMEOUT = 600
MAX_SCRIPT_OUT = 12000


class Cron(QObject):
    changed = Signal()
    openSession = Signal(str, str)          # folder, session_id — open a run in Code
    showCode = Signal()                     # switch to Code view without reopening (live cron)
    manageRequested = Signal(str)           # task id ("" = new)
    consentChanged = Signal()
    toast = Signal(str)                     # undoable toast text
    finished = Signal(str, str, str)        # task_id, status, summary — for notifications
    _done = Signal(str, str, str, str, str)  # task_id, status, summary, folder, session
    _register = Signal(str, str, str, str)  # folder, session, title, task_id — from a worker, applied on the GUI thread

    def __init__(self, app, code):
        super().__init__()
        self._app = app
        self._code = code
        code._bot_cron = self
        self._tasks: list[dict] = []
        self._mtime = 0.0
        self._chat_busy = False
        self._script_n = 0
        self._consent = None                # {id, action, task, previous?}
        self._undo = None                   # {task snapshot or id, kind: create|update|delete}
        self._expanded: set[str] = set()
        self._follow: tuple[str, str] | None = None   # (folder, session) open when a background run ends
        self._bg_run: dict | None = None              # live background chat: {task, run, session, agent}
        self._ui_run: dict | None = None              # cron running inside CodeChat
        self._dirty = False                           # cron.json written by the tick's bookkeeping
        self._done.connect(self._on_done)
        self._register.connect(self._register_session)
        self._code.cronDone.connect(self._on_code_cron_done)
        self._code.cronSession.connect(self._on_code_cron_session)
        self._tick = QTimer(self)
        self._tick.setInterval(20_000)
        self._tick.timeout.connect(self._on_tick)
        self._tick.start()
        self._watch = QTimer(self)
        self._watch.setInterval(1500)
        self._watch.timeout.connect(self._reload_if_changed)
        self._watch.start()
        self._reload()
        QTimer.singleShot(600, lambda: self._notice_ai_changes(None))  # pending from a previous session
        QTimer.singleShot(2500, self._catch_up)

    # ---- QML ------------------------------------------------------------------------------------------------------

    @Property("QVariantList", notify=changed)
    def tasks(self):
        """Project Code cron tasks for the Sessions column (bot routines stay under Bots › Routines)."""
        return [self._view(t) for t in self._tasks if not t.get("bot")]

    @Slot(str, result="QVariantList")
    def botRoutines(self, bot_id):
        bot_id = str(bot_id or "").strip()
        return [self._view(t) for t in self._tasks if t.get("bot") == bot_id]

    @Property("QVariantMap", notify=consentChanged)
    def consent(self):
        return dict(self._consent) if self._consent else {}

    @Property(bool, notify=consentChanged)
    def waiting(self):
        return self._consent is not None

    @Slot(str)
    def toggleExpand(self, task_id):
        tid = str(task_id or "")
        if tid in self._expanded:
            self._expanded.discard(tid)
        else:
            self._expanded.add(tid)
        self.changed.emit()

    @Slot(str)
    def manage(self, task_id=""):
        self.manageRequested.emit(str(task_id or ""))

    @Slot(str, str)
    def openRun(self, folder, session_id):
        folder, session_id = str(folder or ""), str(session_id or "")
        if not folder or not session_id:
            return
        # Already the live Code conversation (cron running in the UI): just show it
        if (self._code.session == session_id and self._code.folder == folder
                and self._code._agent is not None and self._code._agent.alive()):
            self.openSession.emit(folder, session_id)
            return
        # Background agent still owns the session: a second load would fail with « n'a pas pu être ouverte »
        bg = self._bg_run or {}
        if bg.get("session") == session_id and bg.get("agent") is not None:
            self._follow = (folder, session_id)
            self.toast.emit(self._t("cron_watch_wait",
                                    "Toujours en cours — la conversation s'ouvrira dès qu'elle est terminée"))
            return
        self.openSession.emit(folder, session_id)

    @Slot(str)
    def pause(self, task_id):
        try:
            ornis_cron.set_paused(task_id, True, self._lang())
            self._reload()
            self.toast.emit(self._t("cron_paused", "Tâche en pause"))
        except ValueError as err:
            self.toast.emit(str(err))

    @Slot(str)
    def resume(self, task_id):
        try:
            ornis_cron.set_paused(task_id, False, self._lang())
            ornis_cron.bump_next(task_id)
            self._reload()
            self.toast.emit(self._t("cron_resumed", "Tâche reprise"))
        except ValueError as err:
            self.toast.emit(str(err))

    @Slot(str)
    def runNow(self, task_id):
        task = ornis_cron.get(task_id)
        if not task:
            self.toast.emit(self._t("cron_unknown", "Tâche introuvable"))
            return
        if any(r.get("status") == "running" for r in task.get("runs") or []):
            self.toast.emit(self._t("cron_already", "Cette tâche tourne déjà"))
            return
        if task.get("kind") == "chat" and self._chat_busy:
            self.toast.emit(self._t("cron_busy", "Une autre tâche cron tourne déjà"))
            return
        started = self._start(task, manual=True)
        if not started:
            self.toast.emit(self._t("cron_busy", "Une autre tâche cron tourne déjà"))

    @Slot(str)
    def remove(self, task_id):
        task = ornis_cron.get(task_id)
        if not task:
            return
        mode = self._mode()
        if mode == "ask":
            if self._consent:
                self.toast.emit(self._t("cron_busy", "Une autre tâche cron tourne déjà"))
                return
            self._consent = {"id": str(uuid.uuid4()), "action": "delete", "task": task,
                             "title": self._t("cron_confirm_delete", "Supprimer cette tâche cron ?"),
                             "detail": task.get("title") or task.get("id")}
            self.consentChanged.emit()
            return
        self._do_delete(task, undo=mode == "auto")

    @Slot("QVariantMap", result=str)
    def save(self, fields):
        """Create or update from the Manage sheet. Returns \"\" or an error string."""
        try:
            data = dict(fields or {})
            tid = str(data.get("id") or "").strip().lower()
            existing = ornis_cron.get(tid) if tid else None
            if not tid:
                # derive from title
                base = re_slug(str(data.get("title") or "tache"))
                tid = base
                n = 2
                while ornis_cron.get(tid):
                    tid = f"{base}-{n}"
                    n += 1
                data["id"] = tid
            data["folder"] = str(
                data.get("folder") or (existing or {}).get("folder") or self._code.folder or ""
            ).strip()
            if not data["folder"]:
                return self._t("cron_need_folder", "Ouvrez d'abord un dossier Code")
            data["lang"] = self._lang()
            data["schedule"] = ornis_cron.validate_schedule(str(data.get("schedule") or ""))
            mode = self._mode()
            if mode == "ask":
                if self._consent:
                    return self._t("cron_busy", "Une autre tâche cron tourne déjà")
                self._consent = {"id": str(uuid.uuid4()),
                                 "action": "update" if existing else "create",
                                 "task": data, "previous": existing,
                                 "title": self._t("cron_confirm_save", "Enregistrer cette tâche cron ?"),
                                 "detail": data.get("title") or tid}
                self.consentChanged.emit()
                return ""
            row = ornis_cron.upsert(data, create=not existing)
            self._reload()
            if mode in ("edits", "auto"):
                self._undo = {"kind": "update" if existing else "create", "previous": existing, "id": row["id"]}
                QTimer.singleShot(8000, self._clear_undo)
                self.toast.emit(self._t("cron_saved_undo", "Tâche enregistrée — Annuler"))
            else:
                self.toast.emit(self._t("cron_saved", "Tâche enregistrée"))
            return ""
        except ValueError as err:
            return str(err)

    @Slot()
    def undoLast(self):
        u = self._undo
        self._undo = None
        if not u:
            return
        try:
            if u["kind"] == "create":
                ornis_cron.remove(u["id"])
            elif u["kind"] == "delete" and u.get("previous"):
                ornis_cron.upsert(u["previous"], create=True)
            elif u["kind"] == "update" and u.get("previous"):
                ornis_cron.upsert(u["previous"], create=False)
            self._reload()
            self.toast.emit(self._t("cron_undone", "Modification annulée"))
        except ValueError as err:
            self.toast.emit(str(err))

    @Slot(str)
    def answerConsent(self, option):
        c = self._consent
        self._consent = None
        self.consentChanged.emit()
        if not c:
            return
        action, task = c.get("action"), c.get("task") or {}
        if option != "allow":
            try:
                if action == "ai" and (task.get("pending") == "create" or not c.get("previous")):
                    ornis_cron.remove(task.get("id"))
                elif action == "ai" and c.get("previous"):
                    prev = dict(c["previous"])
                    prev.pop("pending", None)
                    prev.pop("pending_previous", None)
                    prev["clear_pending"] = True
                    prev["lang"] = self._lang()
                    ornis_cron.upsert(prev, create=False)
                elif action == "ai":
                    ornis_cron.clear_flag(task.get("id"), "pending")
            except ValueError:
                pass
            self._reload()
            self.toast.emit(self._t("cron_cancelled", "Annulé"))
            QTimer.singleShot(120, lambda: self._notice_ai_changes(None))
            return
        try:
            if action == "delete":
                self._do_delete(task, undo=True)
            elif action in ("create", "update"):
                existing = c.get("previous")
                ornis_cron.upsert(task, create=action == "create" and not existing)
                self._reload()
                self.toast.emit(self._t("cron_saved", "Tâche enregistrée"))
            elif action == "ai":
                self._clear_pending(ornis_cron.get(task["id"]) or dict(task))
                self._reload()
                self.toast.emit(self._t("cron_saved", "Tâche enregistrée"))
        except ValueError as err:
            self.toast.emit(str(err))
        QTimer.singleShot(120, lambda: self._notice_ai_changes(None))

    @Slot(str, result="QVariantMap")
    def get(self, task_id):
        t = ornis_cron.get(task_id)
        return self._view(t) if t else {}

    @Slot(str, int, int, int, int, result=str)
    def plainSchedule(self, kind, hour=8, minute=0, weekday=1, every=15):
        try:
            return ornis_cron.validate_schedule(ornis_cron.plain_to_cron(kind, hour, minute, weekday, every))
        except ValueError as err:
            return ""

    @Slot(str, result=str)
    def labelOf(self, schedule):
        try:
            return ornis_cron.schedule_label(ornis_cron.validate_schedule(schedule), self._lang())
        except ValueError:
            return str(schedule or "")

    @Slot(str, result="QVariantList")
    def nextTimes(self, schedule):
        try:
            expr = ornis_cron.validate_schedule(schedule)
            return [_when(t, self._lang()) for t in ornis_cron.next_times(expr, 2)]
        except ValueError:
            return []

    @Slot(str, result=str)
    def validateSchedule(self, schedule):
        try:
            return ornis_cron.validate_schedule(schedule)
        except ValueError as err:
            return f"!{err}"

    def shutdown(self):
        self._tick.stop()
        self._watch.stop()

    # ---- internals ------------------------------------------------------------------------------------------------

    def _lang(self):
        return getattr(self._app, "lang", None) or getattr(self._app, "_lang", "fr") or "fr"

    def _t(self, key, fallback=""):
        return (getattr(self._app, "_t", None) or {}).get(key, fallback) or fallback

    def _mode(self):
        return str(self._app.pref("code_mode") or "ask")

    def _clear_undo(self):
        self._undo = None

    @staticmethod
    def _unwatched() -> bool:
        """No Ornis/Plume window has the focus: a scheduled run may bring Code to the front for when the user is back.
        With a window in use, the run never yanks the user out of what they are doing (the list opens it)."""
        return QGuiApplication.focusWindow() is None

    def _do_delete(self, task, undo=False):
        if undo:
            self._undo = {"kind": "delete", "previous": task, "id": task.get("id")}
            QTimer.singleShot(8000, self._clear_undo)
        ornis_cron.remove(task.get("id"))
        self._reload()
        self.toast.emit(self._t("cron_deleted_undo", "Tâche supprimée — Annuler") if undo
                        else self._t("cron_deleted", "Tâche supprimée"))

    def _reload_if_changed(self):
        mt = ornis_cron.mtime()
        if mt != self._mtime:
            prev = {t["id"]: t for t in self._tasks}
            self._reload()
            self._notice_ai_changes(prev)
            # Deleted outside the app (Ornis via MCP/CLI): no consent card for a delete, but always « Annuler »
            gone = [prev[tid] for tid in prev if not any(t.get("id") == tid for t in self._tasks)]
            if len(gone) == 1:
                self._undo = {"kind": "delete", "previous": gone[0], "id": gone[0].get("id")}
                QTimer.singleShot(8000, self._clear_undo)
                self.toast.emit(self._t("cron_ai_deleted", "Tâche cron supprimée — Annuler"))

    def _reload(self):
        self._mtime = ornis_cron.mtime()
        self._tasks = ornis_cron.tasks()
        self.changed.emit()

    def _clear_pending(self, task: dict) -> None:
        row = dict(task)
        row.pop("pending", None)
        row.pop("pending_previous", None)
        row["clear_pending"] = True
        row["lang"] = self._lang()
        ornis_cron.upsert(row, create=False)

    def _notice_ai_changes(self, prev: dict | None):
        """MCP wrote cron.json (or app restarted with pending): ask mode may need a card; else clear pending.

        prev=None on startup (every pending create/update needs a look). Otherwise prev is the
        task map from before the reload.
        """
        mode = self._mode()
        startup = prev is None
        prev = prev or {}
        for t in self._tasks:
            tid = t.get("id")
            pending = t.get("pending")
            if pending and t.get("bot"):
                try:
                    self._clear_pending(t)
                    self._reload()
                except ValueError:
                    pass
                continue
            if pending == "create":
                if mode == "ask":
                    if self._consent:
                        return
                    self._consent = {"id": str(uuid.uuid4()), "action": "ai", "task": t,
                                     "title": self._t("cron_confirm_ai", "Ornis a créé une tâche cron"),
                                     "detail": f"{t.get('title') or tid} — {t.get('scheduleLabel') or t.get('schedule')}"}
                    self.consentChanged.emit()
                    return  # one consent card at a time
                try:
                    self._clear_pending(t)
                    self._reload()
                    self.toast.emit(self._t("cron_ai_created", "Tâche cron créée — Annuler"))
                    self._undo = {"kind": "create", "id": tid, "previous": None}
                    QTimer.singleShot(8000, self._clear_undo)
                except ValueError:
                    pass
            elif pending == "update" and (startup or tid in prev):
                stored = t.get("pending_previous")
                if isinstance(stored, dict) and stored:
                    old = {**t, **stored, "runs": t.get("runs") or []}
                else:
                    old = prev.get(tid) if tid in prev else None
                new = t
                if mode == "ask":
                    if self._consent:
                        return
                    self._consent = {"id": str(uuid.uuid4()), "action": "ai", "task": new, "previous": old,
                                     "title": self._t("cron_confirm_ai_update", "Ornis a modifié une tâche cron"),
                                     "detail": new.get("title") or tid}
                    self.consentChanged.emit()
                    return
                try:
                    self._clear_pending(new)
                    self._reload()
                    self.toast.emit(self._t("cron_saved_undo", "Tâche enregistrée — Annuler"))
                    self._undo = {"kind": "update", "id": tid, "previous": old}
                    QTimer.singleShot(8000, self._clear_undo)
                except ValueError:
                    pass
            elif pending and not startup and tid in prev and mode != "ask":
                # stale pending from an older build: unblock
                try:
                    self._clear_pending(t)
                    self._reload()
                except ValueError:
                    pass

    def _view(self, t: dict) -> dict:
        if not t:
            return {}
        runs = list(t.get("runs") or [])
        sessions = []
        for r in runs:
            # Show deferred/missed/error even without a session id (otherwise auto skips look like « never ran »)
            if not r.get("session") and r.get("status") not in ("deferred", "missed", "error", "running"):
                continue
            sessions.append({
                "id": r.get("session") or "", "runId": r.get("id"), "status": r.get("status"),
                "summary": r.get("summary") or "",
                "when": _when(float(r.get("started") or 0), self._lang()),
                "folder": t.get("folder"),
            })
        running = any(r.get("status") == "running" for r in runs)
        return {
            "id": t.get("id"), "title": t.get("title") or t.get("id"),
            "description": t.get("description") or "",
            "folder": t.get("folder"), "kind": t.get("kind") or "chat",
            "prompt": t.get("prompt") or "", "command": t.get("command") or "",
            "schedule": t.get("schedule") or "",
            "scheduleLabel": ornis_cron.schedule_label(t.get("schedule") or "", self._lang()),
            "paused": bool(t.get("paused")),
            "bot": t.get("bot") or "",
            "nextRun": _when(float(t["next_run"]), self._lang()) if t.get("next_run") else "",
            "nextRunAt": float(t.get("next_run") or 0),
            "running": running,
            "expanded": t.get("id") in self._expanded,
            "sessions": sessions[:40],
            "shownSessions": sessions[:3],
            "moreSessions": max(0, len(sessions) - 3),
            "runs": [{**r, "when": _when(float(r.get("started") or 0), self._lang())} for r in runs[:20]],
            "pending": t.get("pending") or "",
        }

    def _code_busy(self) -> bool:
        """True when Code is mid-turn (not merely sitting on an idle agent in the folder)."""
        code = self._code
        return bool(getattr(code, "_busy", False) or getattr(code, "_cron_job", None)
                    or getattr(code, "_host", None) or getattr(code, "_queued", None))

    def _reap_stale(self, startup: bool = False) -> None:
        """Unblock the scheduler if a run stayed « running » after a lost UI/background handle."""
        now = time.time()
        # Recover a stuck chat gate (cronDone never fired, agent gone)
        if self._chat_busy and not self._ui_run and not self._bg_run:
            self._chat_busy = False
        changed = False
        for t in list(ornis_cron.tasks()):
            for r in list(t.get("runs") or []):
                if r.get("status") != "running":
                    continue
                rid = r.get("id")
                if self._ui_run and self._ui_run.get("run") == rid:
                    continue
                if self._bg_run and self._bg_run.get("run") == rid:
                    continue
                age = now - float(r.get("started") or 0)
                # chat turns can be long; scripts use SCRIPT_TIMEOUT. Still unblock after 15 min orphan.
                limit = 0 if startup else (SCRIPT_TIMEOUT + 60 if t.get("kind") == "script" else 15 * 60)
                if age <= limit:
                    continue
                try:
                    ornis_cron.update_run(t["id"], rid, {
                        "status": "error", "ended": now,
                        "summary": (self._t("cron_lost", "Interrompue") if startup
                                    else self._t("cron_timeout", "Délai dépassé (10 min)")),
                    })
                    changed = True
                except ValueError:
                    pass
        if changed:
            self._chat_busy = False
            self._reload()

    def _on_tick(self):
        self._reap_stale()
        now = time.time()
        for t in list(self._tasks):
            if t.get("paused") or t.get("pending"):
                continue
            if any(r.get("status") == "running" for r in t.get("runs") or []):
                continue
            force = bool(t.get("force_run"))
            nxt = float(t.get("next_run") or 0)
            if force or (nxt and nxt <= now + 1):
                # Long overdue without a force (the computer slept): the same rule as at startup — the last slot
                # runs if it is recent enough, else it is marked missed
                if not force and now - nxt > 120 and not self._owed(t, now):
                    continue
                # keep force_run until _start begins; never mark MCP/timer as manual
                # (manual bypasses same-folder defer — only the lightning button does that)
                self._start(t, manual=False)
        if self._dirty:
            self._dirty = False
            self._reload()

    def _owed(self, t: dict, now: float) -> bool:
        """An overdue task (app closed or computer asleep): True when its last slot should still run now.

        Otherwise records « missed » (once per slot) and moves next_run on."""
        try:
            prev = ornis_cron.previous_run(t["schedule"], now)
        except ValueError:
            return False
        if not prev:
            return False
        age = now - prev
        period = ornis_cron.period_seconds(t["schedule"])
        last = next((r for r in (t.get("runs") or [])
                     if r.get("status") in ("ok", "error", "deferred", "missed")), None)
        try:
            if float((last or {}).get("started") or 0) >= prev - 30:
                ornis_cron.bump_next(t["id"], now)        # that slot already ran (or was marked missed)
                self._dirty = True
                return False
            if age <= ornis_cron.CATCH_UP and age <= period:
                return True                               # one late run for the last slot
            ornis_cron.add_run(t["id"], {
                "id": str(uuid.uuid4()), "started": prev, "ended": now,
                "status": "missed",
                "summary": self._t("cron_missed", "Manquée : l'application était fermée"),
            })
            ornis_cron.bump_next(t["id"], now)
            self._dirty = True
        except ValueError:
            pass
        return False

    def _catch_up(self):
        now = time.time()
        self._reap_stale(startup=True)
        for t in list(ornis_cron.tasks()):
            if t.get("paused") or t.get("pending"):
                continue
            if any(r.get("status") == "running" for r in t.get("runs") or []):
                continue
            # next_run moves forward at every start, defer, creation and edit: only a past one was owed while closed
            # (a task created at 8:05 for « every day at 8:00 » does not owe today's 8:00)
            nxt = float(t.get("next_run") or 0)
            if not nxt or nxt > now:
                continue
            if self._owed(t, now):
                QTimer.singleShot(5000, lambda tid=t["id"]: self._start(ornis_cron.get(tid) or {}, manual=False))
        self._dirty = False
        self._reload()

    def _start(self, task: dict, manual: bool = False) -> bool:
        """Begin a run. Returns True once work has started (or a defer was recorded)."""
        if not task:
            return False
        tid = task["id"]
        task = ornis_cron.get(tid) or task
        if any(r.get("status") == "running" for r in task.get("runs") or []):
            return False
        bot = str(task.get("bot") or "")
        if bot:
            import ornis_bots
            if not ornis_bots.get(bot):
                return False
            task = dict(task, folder=ornis_bots.working_folder(bot))
            peer_worker = getattr(self._code, "_bot_peer_worker", None)
            bg_bots = getattr(self._code, "_bg_bots", {})
            if ((self._code.bot == bot and (self._code.busy or self._code._queued))
                    or bot in bg_bots
                    or (peer_worker is not None and peer_worker.bot == bot
                        and (peer_worker.busy or peer_worker._cron_job))):
                if manual:
                    ornis_cron.patch(tid, {"force_run": True}, self._lang())
                return False
        folder = str(task.get("folder") or "")
        # Only defer when Code is mid-turn on that folder. An idle agent left open used to
        # block every auto tick (manual lightning still worked) — seen 08/11 on Mac.
        if not bot and ornis_cron.defer_for_open_code(
                kind=str(task.get("kind") or ""), folder=folder,
                code_folder=str(self._code.folder or ""),
                agent_alive=bool(self._code._agent is not None and self._code._agent.alive()),
                code_busy=self._code_busy(), manual=manual):
            note = {"started": time.time(), "ended": time.time(), "status": "deferred",
                    "summary": self._t("cron_deferred", "Reportée : vous travaillez déjà dans ce dossier")}
            last = (task.get("runs") or [{}])[0]
            try:
                if last.get("status") == "deferred" and last.get("id"):
                    ornis_cron.update_run(tid, last["id"], note)   # one line per streak, not one every 15 min
                else:
                    ornis_cron.add_run(tid, {"id": str(uuid.uuid4()), **note})
            except ValueError:
                return False
            try:
                ornis_cron.set_next_run(tid, time.time() + ornis_cron.DEFER)
            except ValueError:
                pass
            try:
                ornis_cron.clear_flag(tid, "force_run")
            except ValueError:
                pass
            self._reload()
            return True
        if task.get("kind") == "chat":
            if self._chat_busy:
                return False  # keep force_run / due next_run for the next tick
            self._begin_run(tid, manual)
            self._run_chat(task)
            return True
        if self._script_n >= 2:
            return False
        self._begin_run(tid, manual)
        self._run_script(task)
        return True

    def _begin_run(self, tid: str, manual: bool) -> None:
        """Clear force_run and advance next_run once we are committed to starting."""
        try:
            ornis_cron.clear_flag(tid, "force_run")
        except ValueError:
            pass
        try:
            ornis_cron.bump_next(tid, time.time())
        except ValueError:
            pass
        self._reload()

    def _run_chat(self, task: dict):
        self._chat_busy = True
        self._running_bot = str(task.get("bot") or "")
        run_id = str(uuid.uuid4())
        started = time.time()
        ornis_cron.add_run(task["id"], {
            "id": run_id, "started": started, "status": "running",
            "summary": self._t("cron_starting", "Démarrage…"),
        })
        self._reload()
        bot = str(task.get("bot") or "").strip()
        folder = Path(task["folder"])
        session_id = ""
        if bot:
            try:
                import ornis_bots  # noqa: PLC0415
                profile = ornis_bots.get(bot) or {}
                folder = Path(ornis_bots.working_folder(bot))
                session_id = str(profile.get("session") or "")
            except Exception:  # noqa: BLE001
                pass
        day = datetime.now().strftime("%d %b").lstrip("0")
        title = f"{task.get('title') or task['id']} · {day}"
        prompt = CRON_NOTE + str(task.get("prompt") or "")
        # Prefer the Code view: the user sees the turn live and can open it from the list
        self._ui_run = {"task": task["id"], "run": run_id, "folder": str(folder), "title": title,
                        "started": started, "bot": bot}

        def start_ui():
            if self._code.runScheduled(str(folder), title, prompt, task["id"], bot=bot, session_id=session_id):
                if self._unwatched():
                    self.showCode.emit()
                return
            if bot and self._code.bot == bot and self._code.busy:
                QTimer.singleShot(400, start_ui)
                return
            self._ui_run = None
            self._run_chat_background(task, run_id, title, prompt, started)

        QTimer.singleShot(0, start_ui)

    def _on_code_cron_session(self, task_id, folder, session):
        ui = self._ui_run
        if not ui or ui.get("task") != task_id:
            return
        try:
            ornis_cron.update_run(task_id, ui["run"], {
                "session": session,
                "summary": self._t("cron_working", "En cours…"),
            })
        except ValueError:
            pass
        self._register_session(folder, session, ui.get("title") or task_id, task_id)
        self._reload()
        if self._unwatched() and not ui.get("bot"):
            self.openSession.emit(str(folder), str(session))

    def _on_code_cron_done(self, task_id, status, summary, session):
        ui = self._ui_run
        if not ui or ui.get("task") != task_id:
            return
        self._ui_run = None
        started = float(ui.get("started") or time.time())
        try:
            ornis_cron.update_run(task_id, ui["run"], {
                "status": status, "summary": (summary or "")[:300], "ended": time.time(),
                "session": session, "duration": round(time.time() - started, 1),
            })
        except ValueError:
            pass
        self._chat_busy = False
        self._done.emit(task_id, status, summary, str(ui.get("folder") or ""), session or "")

    def _run_chat_background(self, task, run_id, title, prompt, started):
        """Fallback when Code is already busy: own agent (not openable until done)."""
        bot = str(task.get("bot") or "").strip()
        folder = Path(task["folder"])
        resume = ""
        if bot:
            try:
                import ornis_bots  # noqa: PLC0415
                profile = ornis_bots.get(bot) or {}
                folder = Path(ornis_bots.working_folder(bot))
                resume = str(profile.get("session") or "")
            except Exception:  # noqa: BLE001
                pass
        try:
            ornis_cron.update_run(task["id"], run_id, {
                "summary": self._t("cron_background", "En cours en arrière-plan…"),
            })
        except ValueError:
            pass
        self._reload()
        # Held from now: the reaper frees _chat_busy when neither handle is set, and the agent takes seconds to start
        self._bg_run = {"task": task["id"], "run": run_id, "session": "", "agent": None}

        def work():
            session = ""
            status, summary = "error", self._t("cron_failed", "Échec")
            agent = None
            try:
                account = self._app.account()
                if not account:
                    raise RuntimeError("offline")
                exe = ornis_code.install(lambda *_: None)
                creds = ornis_code.credentials(*account)
                ornis_code.prepare_project(str(folder), self._lang())
                ornis_code.write_home(creds["url"], self._lang(), str(folder),
                                      self._app.pref("code_reasoning") or "high", bot=bot)

                def on_permission(rid, sid, tool, opts):
                    kind = str((tool or {}).get("kind") or "")
                    raw = (tool or {}).get("rawInput") if isinstance((tool or {}).get("rawInput"), dict) else {}
                    verdict = ornis_code.decide("auto", {"kind": kind, "rawInput": raw or {},
                                                         "locations": (tool or {}).get("locations") or [],
                                                         "content": (tool or {}).get("content") or []},
                                                sandboxed=bool(ornis_code.sandbox_kind()), folder=str(folder), bot=bot)
                    if verdict == "ask":
                        verdict = "reject"
                    want = "allow_once" if verdict == "allow" else "reject_once"
                    pick = next((o for o in (opts or []) if isinstance(o, dict) and o.get("kind") == want), None)
                    if agent:
                        outcome = {"outcome": "selected", "optionId": pick.get("optionId")} if pick else {"outcome": "cancelled"}
                        agent.answer(rid, {"outcome": outcome})

                def on_question(rid, sid, qs):
                    if agent:
                        agent.answer(rid, {"action": "decline"})

                last_beat = [0.0]

                def on_update(sid, update):
                    if not isinstance(update, dict):
                        return
                    now = time.time()
                    if now - last_beat[0] < 2.0:
                        return
                    kind = str(update.get("sessionUpdate") or "")
                    label = ""
                    if kind in ("tool_call", "tool_call_update"):
                        label = str(update.get("title") or update.get("kind") or "")[:120]
                    elif kind in ("agent_message_chunk", "agent_thought_chunk"):
                        label = self._t("cron_working", "En cours…")
                    if not label:
                        return
                    last_beat[0] = now
                    try:
                        ornis_cron.update_run(task["id"], run_id, {"summary": label})
                        self._done.emit("", "progress", label, str(folder), session)
                    except ValueError:
                        pass

                agent = ornis_code.Agent(exe, folder, creds["token"],
                                         on_permission=on_permission, on_question=on_question,
                                         on_update=on_update, sandbox=True,
                                         gateway_url=str(creds.get("url") or ""), bot=bot)
                agent.start()
                if resume:
                    agent.load_session(resume)
                    session = resume
                else:
                    created = agent.new_session()
                    session = created.get("sessionId") or ""
                self._bg_run = {"task": task["id"], "run": run_id, "session": session, "agent": agent, "bot": bot}
                agent.set_mode(session, "auto")
                self._register.emit(str(folder), session, title, task["id"])
                if bot and session:
                    try:
                        import ornis_bots  # noqa: PLC0415
                        ornis_bots.update(bot, {"session": session})
                    except Exception:  # noqa: BLE001
                        pass
                ornis_cron.update_run(task["id"], run_id, {
                    "session": session, "summary": self._t("cron_working", "En cours…"),
                })
                body = prompt
                if bot:
                    try:
                        import ornis_bots  # noqa: PLC0415
                        bots_cli = str((ornis_code.ROOT / "bin" / "ornis-bots").resolve())
                        body = ornis_bots.identity_block(bot, bots_cli=bots_cli) + prompt
                    except Exception:  # noqa: BLE001
                        pass
                result = agent.prompt(session, [{"type": "text", "text": body}])
                stop = str((result or {}).get("stopReason") or "")
                status = "ok" if stop in ("end_turn", "max_tokens", "") else "error"
                summary = self._t("cron_done", "Terminé") if status == "ok" else (stop or summary)
            except ornis_code.Unavailable as err:
                code = err.args[0] if err.args else "failed"
                status, summary = "error", self._t(f"code_{code}", str(code))
            except Exception as err:  # noqa: BLE001
                print("Ornis cron chat:", type(err).__name__, err, flush=True)
                detail = str(err).strip()
                base = self._t("cron_failed", "Échec")
                status, summary = "error", (f"{base} — {detail}" if detail else base)[:300]
            finally:
                self._bg_run = None
                try:
                    if agent:
                        agent.close()
                except Exception:  # noqa: BLE001
                    pass
                try:
                    ornis_cron.update_run(task["id"], run_id, {
                        "status": status, "summary": summary[:300], "ended": time.time(),
                        "session": session, "duration": round(time.time() - started, 1),
                    })
                except ValueError:
                    pass                        # task deleted meanwhile: still free the gate below
                self._chat_busy = False
                self._done.emit(task["id"], status, summary, str(folder), session)

        threading.Thread(target=work, daemon=True, name=f"ornis-cron-{task['id']}").start()

    def _on_done(self, task_id, status, summary, folder, session):
        if status == "progress":
            self._reload()
            return
        self._reload()
        self.finished.emit(task_id, status, summary)
        title = (ornis_cron.get(task_id) or {}).get("title") or task_id
        if hasattr(self._app, "notify"):
            try:
                self._app.notify(title, summary, session if status == "ok" else "")
            except Exception:  # noqa: BLE001
                pass
        if session and folder:
            self._register_session(folder, session, title, task_id)
        follow, self._follow = self._follow, None
        if follow and follow[1] == session:
            self.openSession.emit(follow[0], follow[1])

    def _register_session(self, folder, session, title, cron_id):
        try:
            idx = ornis_code.ROOT / "sessions.json"
            try:
                data = json.loads(idx.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                data = {}
            rows = data.setdefault(folder, [])
            found = next((s for s in rows if s.get("id") == session), None)
            if found is None:
                found = {"id": session, "created": time.time()}
                rows.append(found)
            found["title"] = title
            found["renamed"] = True
            found["cron"] = cron_id
            found["updated"] = time.time()
            bot = str((ornis_cron.get(cron_id) or {}).get("bot") or "")
            if bot:
                found["bot"] = bot
            system.private_write(idx, json.dumps(data, ensure_ascii=False))
            # refresh CodeChat index if it has one
            if hasattr(self._code, "reloadIndex"):
                self._code.reloadIndex()
            elif hasattr(self._code, "_index"):
                self._code._index = data
                self._code.changed.emit()
        except OSError as err:
            print("Ornis cron index:", err, flush=True)

    def _run_script(self, task: dict):
        command = str(task.get("command") or "").strip()
        info = ornis_shell.classify(command)
        if info.get("blocked") or ornis_code._against_itself(command, {}):
            ornis_cron.add_run(task["id"], {
                "id": str(uuid.uuid4()), "started": time.time(), "ended": time.time(),
                "status": "error",
                "summary": self._t("cron_blocked", "Commande refusée"),
            })
            self._reload()
            self.finished.emit(task["id"], "error", self._t("cron_blocked", "Commande refusée"))
            return
        if info.get("sensitive") or info.get("level") == "admin":
            ornis_cron.add_run(task["id"], {
                "id": str(uuid.uuid4()), "started": time.time(), "ended": time.time(),
                "status": "error",
                "summary": self._t("cron_needs_you", "Cette commande demande un accord : lancez-la à la main"),
            })
            self._reload()
            self.finished.emit(task["id"], "error", self._t("cron_needs_you", "Cette commande demande un accord"))
            return
        self._script_n += 1
        run_id = str(uuid.uuid4())
        started = time.time()
        ornis_cron.add_run(task["id"], {"id": run_id, "started": started, "status": "running", "summary": ""})
        self._reload()
        folder = Path(task["folder"])

        def work():
            status, summary = "error", ""
            try:
                flags = subprocess.CREATE_NO_WINDOW if system.WINDOWS else 0
                proc = subprocess.run(
                    command, shell=True, cwd=str(folder), capture_output=True, text=True,
                    timeout=SCRIPT_TIMEOUT, creationflags=flags)
                out = ((proc.stdout or "") + (proc.stderr or ""))[-MAX_SCRIPT_OUT:]
                tmp = folder / ".ornis" / "tmp"
                try:
                    tmp.mkdir(parents=True, exist_ok=True)
                    (tmp / f"cron-{task['id']}-{int(started)}.log").write_text(out, encoding="utf-8")
                except OSError:
                    pass
                status = "ok" if proc.returncode == 0 else "error"
                summary = (out.strip().splitlines() or [f"exit {proc.returncode}"])[-1][:200]
            except subprocess.TimeoutExpired:
                status, summary = "error", self._t("cron_timeout", "Délai dépassé (10 min)")
            except Exception as err:  # noqa: BLE001
                status, summary = "error", str(err)[:200]
            try:
                ornis_cron.update_run(task["id"], run_id, {
                    "status": status, "summary": summary, "ended": time.time(),
                    "duration": round(time.time() - started, 1),
                })
            except ValueError:
                pass                            # task deleted meanwhile: the slot is still given back
            self._script_n = max(0, self._script_n - 1)
            self._done.emit(task["id"], status, summary, str(folder), "")

        threading.Thread(target=work, daemon=True, name=f"ornis-cron-sh-{task['id']}").start()


def re_slug(text: str) -> str:
    import re as _re
    s = _re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    s = (s[:38] or "tache").strip("-")
    if len(s) < 3:
        s = (s + "-job")[:40]
    if not ornis_cron.ID_RE.match(s):
        s = "tache-" + s[:32]
    return s[:40]
