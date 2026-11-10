"""The conversations with Ornis, for the window: the list (the same as in the cloud and in the top-bar applet),
the open one, the reply being written (its text so far and the tools Ornis is using), the actions waiting for
the user's yes, the scheduled tasks and today's allowance. Pins are the cloud's (orneos app, the same as in the
browser), with a copy on this computer (ornis.json) for offline: a pin made offline is sent at the next refresh.
A deleted conversation stays for a few seconds, the time to undo, before the cloud forgets it.

Every call to the cloud runs in a thread (ornis_chat is blocking); results come back to the UI thread through
queued signals. A reply keeps going in the cloud when another conversation is opened: coming back follows it.
"""
import json
import mimetypes
import re
import threading
import time
import uuid
from datetime import date, datetime
from pathlib import Path

from PySide6.QtCore import Property, QObject, Qt, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QGuiApplication

from ornis_core import tools
import cloud
import system
from ornis_chat import Chat as Client, Error, MAX_ATTACHMENTS, MAX_BYTES, about_block, attachment_kind
from ornis_voice import Dictation

POLL = 0.6
UNDO_MS = 7000
EXPORTS = system.CACHE / "ornis-export"
FILES = system.CACHE / "ornis-files"        # pasted images and thumbnails of attachments (never the files themselves)
# The assistant names what it receives "2026-10-30_19.50.27 note.png": the user knows it as "note.png"
STAMP = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{2}\.\d{2}\.\d{2} ")


def _shown(name):
    return STAMP.sub("", str(name or ""))


def _group(ts):
    if not ts:
        return "older"
    day = datetime.fromtimestamp(ts).date()
    delta = (date.today() - day).days
    return "today" if delta <= 0 else "yesterday" if delta == 1 else "previous_7" if delta < 7 else "older"


def _host(url):
    """A source's site, as the card shows it"""
    from urllib.parse import urlparse
    host = urlparse(str(url or "")).hostname or ""
    return host[4:] if host.startswith("www.") else host


def _when(ts, lang):
    """14:32 today, else the day too (23/10 14:32), the year when it is not this one."""
    if not ts:
        return ""
    moment = datetime.fromtimestamp(ts)
    hour = moment.strftime("%H:%M")
    if moment.date() == date.today():
        return hour
    sep = "." if lang == "de" else "/"
    day = f"{moment.day:02d}{sep}{moment.month:02d}" + ("." if lang == "de" else "")
    if moment.year != date.today().year:
        day += ("" if lang == "de" else sep) + str(moment.year)
    return f"{day} {hour}"


class Chat(QObject):
    changed = Signal()             # list, open conversation, state
    streamChanged = Signal()       # the reply being written
    scheduledChanged = Signal()
    quotaChanged = Signal()
    usageChanged = Signal()        # the usage panel (Settings › Utilisation): 24 h hour by hour, the AI offer
    resetSettled = Signal()        # a banked reset finished (used or refused): the button can be pressed again
    regionChanged = Signal()       # where Ornis runs (Settings › Utilisation): Europe or « global »
    replied = Signal()             # a reply arrived (the view scrolls, the window may notify)
    laterChanged = Signal()        # the messages written while Ornis answers, sent one by one after the reply
    laterReturned = Signal(str)    # stopped: what was waiting goes back into the box
    _stepsRead = Signal(str, "QVariantList")
    _shared = Signal(str)            # the public link of a conversation shared (copied, said)
    problem = Signal(str)          # a refusal to show (toast)
    removed = Signal(str, str)     # a conversation just deleted (id, title): the window offers to undo
    exported = Signal(str)         # what an export did, for the toast
    _listed = Signal(object, str)
    _opened = Signal(str, object, object, str)
    _progress = Signal(int, object)
    _finished = Signal(int, str, object)
    _scheduled = Signal(object)
    _quota = Signal(object)
    _usageFetched = Signal(object)
    _resetFetched = Signal(object)
    _regionFetched = Signal(object)
    _failed = Signal(str)
    _archivedFetched = Signal(object, bool, int)   # the cloud's archived conversations (or [] and offline), the revision asked at
    _votesFetched = Signal(object, int)      # the cloud's votes, and the vote revision when they were asked
    archivedOne = Signal(str, str)  # a conversation archived (id, title): « Annuler » offered
    _forked = Signal(str, str, object, str)   # new session id, its title, the conversation so far, or a problem
    _ephemeralKept = Signal(str)   # an ephemeral conversation not deleted (offline): tried again at the next start
    _transcript = Signal(str, str, str)
    _pinned = Signal(object, int, str)
    badgeChanged = Signal(int)     # conversations with answers not read yet (dock, Plume's rail)
    workChanged = Signal()         # the Work mode: chosen, its estimate, the jobs, the one open
    _jobsFetched = Signal(object)
    _estimated = Signal(object)
    _jobFetched = Signal(str, object)
    _unreadFetched = Signal(object)
    _refreshed = Signal(str, object, object, int)
    filesChanged = Signal()        # the attachments of the message being written
    folderListed = Signal(str, "QVariantList", str)   # Drive picker: path, entries, problem
    _uploaded = Signal(str, str, str)                  # key, file id ("" = failed), thumbnail
    _described = Signal(str, str, str)                 # file id, name, thumbnail of a sent attachment
    imageReady = Signal(str, str)                      # file id, file:// of the image in large ("" = none)
    profileChanged = Signal()      # « Personnaliser Ornis »: the instructions and what Ornis remembers
    _profileFetched = Signal(object)
    mentionsChanged = Signal()     # @-mention suggestions for Composer.qml
    _mentionsFetched = Signal(int, object)
    slashesChanged = Signal()      # /-command and Skill suggestions for Composer.qml
    _slashesFetched = Signal(int, object)
    _screenshotDone = Signal(str)
    contextChanged = Signal()      # what the open conversation's next question carries (the gauge), measured by the agent
    consentChanged = Signal()      # Ornis asks to act on this computer: the request above the message box, or none
    _consentAsked = Signal(object)
    _contextFetched = Signal(str, object)

    def __init__(self, app):
        super().__init__()
        self._app = app
        self._t = app.t
        self.projects = None              # the Work mode's projects (ornis_core/projects.py), set by bundle.py
        self._new_project = ""            # the project of the new conversation being written
        self._state = "loading"
        self._sessions = []
        self._ephemeral_next = False   # the new conversation (not in the cloud yet) is ephemeral
        self._current = ""
        self._messages = []
        self._pending = []
        self._remembered = False
        self._busy = False
        self._run = 0                 # the reply being followed; a newer one makes older results stale
        self._task = ""
        self._stream = ""
        self._reasoning = ""              # what Ornis has thought so far in this answer (the model reasons)
        self._computer = None
        self._consent = None              # what Ornis asks to do on this computer, waiting for the user (ornis_consent)
        self._working = []
        self._slow = False
        self._error = ""
        self._scheduled_rows = []
        self._task_sessions = []            # the scheduled tasks' conversations (their own page, not the list)
        self._quota_info = None
        self._query = ""
        self._doomed = {}             # deleted here, not yet in the cloud (undo): id → the session
        self._pin_rev = 0             # each change of the pins here: an older answer of the cloud is stale
        self._files = []              # attachments of the next message: {key, name, kind, size, state, file_id, thumb}
        self._known = {}              # file id → {name, thumb} of the attachments already sent (shown in the history)
        self._inflight = {}           # key → attachment of a message already sent whose upload is still running
        self._unread = {}             # session id → answers not read yet: the cloud's, the same on every device
        self._unread_seen = None      # the previous count, to tell a new answer (None until the first read)
        self._work_mode = ""          # the next question starts a Work job ("work") or a deep research ("research")
        self._work_sent = None        # the conversation a job was just asked in (its job appears in a few seconds)
        self._estimate = {}           # what a job would take of today's allowance (orneos app)
        self._jobs = []               # the Work jobs, newest first
        self._profile = {}            # « Personnaliser Ornis » ({} until read; "failed": the cloud did not answer)
        self._mentions = []           # @-mention suggestions
        self._mention_rev = 0
        self._slashes = []            # /-command suggestions
        self._slash_rev = 0
        self._drive_cache = (0.0, [])
        self._new_mode = "agent"      # the mode of the conversation not created yet (agent | plan)
        self._context = {}            # the open conversation's context ({} until the agent measured it)
        self._front = False           # Ornis is what the user is looking at (its window in front, or its module in Plume)
        # Outside Orneos OS (Plume on Windows, macOS, Linux), nothing relays the cloud's bell: Plume tells new answers
        self._relay = not Path("/usr/libexec/orneos-notify").exists()
        for old in FILES.glob("*") if FILES.exists() else []:     # pasted images and thumbnails: a month at most
            if time.time() - old.stat().st_mtime > 30 * 86400:
                old.unlink(missing_ok=True)
        for signal, slot in ((self._listed, self._on_listed), (self._opened, self._on_opened), (self._progress, self._on_progress),
                             (self._finished, self._on_finished), (self._scheduled, self._on_scheduled),
                             (self._quota, self._on_quota), (self._usageFetched, self._on_usage), (self._resetFetched, self._on_reset), (self._regionFetched, self._on_region),
                             (self._failed, self.problem.emit),
                             (self._transcript, self._on_transcript), (self._pinned, self._on_pinned),
                             (self._uploaded, self._on_uploaded), (self._described, self._on_described),
                             (self._unreadFetched, self._on_unread), (self._jobsFetched, self._on_jobs),
                             (self._estimated, self._on_estimate), (self._jobFetched, self._on_job),
                             (self._profileFetched, self._on_profile), (self._mentionsFetched, self._on_mentions),
                             (self._slashesFetched, self._on_slashes), (self._contextFetched, self._on_context),
                             (self._screenshotDone, self._on_screenshot), (self._ephemeralKept, self._keep_ephemeral),
                             (self._archivedFetched, self._on_archived), (self._votesFetched, self._on_votes),
                             (self._forked, self._on_forked), (self._consentAsked, self._on_consent)):
            signal.connect(slot, Qt.ConnectionType.QueuedConnection)
        # dictation and reading aloud (ornis_voice): the box gets the text, a refusal is a toast
        self._voice = Dictation(self._dictated, self._t, getattr(app, "lang", "fr")[:2], self)
        self._voice.failed.connect(self.problem.emit)
        app.accountChanged.connect(self.refresh)
        app.computerChanged.connect(self.changed.emit)
        self.changed.connect(self.workChanged.emit)      # the open conversation's job follows it
        self._target = ""                 # what Ornis has written so far (the cloud); _stream catches up with it
        self._loading = False             # a conversation opened for the first time, its messages on their way
        self._seen_messages = {}          # conversation → its last messages: opened again, shown at once (30 at most)
        app.accountChanged.connect(self._seen_messages.clear)
        self._reveal = QTimer(self)       # the text unrolls smoothly instead of jumping by the cloud's steps
        self._reveal.setInterval(30)
        self._reveal.timeout.connect(self._unroll)
        self._timer = QTimer(self)        # the list and the allowance stay fresh while the window is open
        self._timer.setInterval(120_000)
        self._timer.timeout.connect(lambda: self.refresh(False))
        self._timer.start()
        self._unread_timer = QTimer(self)  # answers of scheduled tasks and of the other devices, within 30 s
        self._unread_timer.setInterval(30_000)
        self._unread_timer.timeout.connect(self._poll_unread)
        self._unread_timer.start()
        self._job_timer = QTimer(self)    # a job's steps, live while it works (2 s)
        self._job_timer.setInterval(2000)
        self._job_timer.timeout.connect(self._poll_job)
        self._refreshed.connect(self._on_refreshed, Qt.ConnectionType.QueuedConnection)
        self._stepsRead.connect(self._on_steps_read, Qt.ConnectionType.QueuedConnection)
        self._shared.connect(self._on_shared, Qt.ConnectionType.QueuedConnection)
        self.refresh()

    # ---- helpers -------------------------------------------------------------------------------------------
    def _client(self):
        account = self._app.account()
        return Client(*account) if account else None

    def _bg(self, fn):
        threading.Thread(target=fn, daemon=True).start()

    def _view(self, msg):
        files = []
        for a in msg.get("attachments") or []:
            known = self._known.get(a["file_id"], {})
            name = known.get("name") or a.get("name") or ""
            files.append({"name": _shown(name), "kind": attachment_kind(name) or ("image" if a.get("type") == "Image" else "document"),
                          "thumb": known.get("thumb") or a.get("thumb") or "", "file_id": str(a.get("file_id") or "")})
        return {"id": msg["id"], "role": msg["role"], "content": msg["content"], "time": msg["timestamp"],
                "when": _when(msg["timestamp"], self._app.lang), "tools": tools.families(msg.get("sources"), self._t),
                "files": files, "work": bool(msg.get("work")), "research": bool(msg.get("research")),
                "plan": bool(msg.get("plan")), "compact": bool(msg.get("compact")), "compactAnswer": False,
                "reasoning": str(msg.get("reasoning") or ""), "about": str(msg.get("about") or ""),
                "task": str(msg.get("task") or ""),
                # it stored a memory while answering: said under the answer (« Voir ou oublier »)
                "memorized": "store_memory" in [str(x) for x in (msg.get("sources") or [])],
                "vote": int((self._app.pref("votes") or {}).get(str(msg["id"]), 0)),
                "steps": tools.step_rows(self._steps_of.get(msg["id"]) if msg["id"] in getattr(self, "_steps_of", {}) else [], self._t),
                "stepsKnown": msg["id"] in getattr(self, "_steps_of", {})}

    # ---- properties ------------------------------------------------------------------------------------------
    @Property(str, notify=changed)
    def state(self):
        return self._state

    @Property("QVariantList", notify=changed)
    def sessions(self):
        """The list as the user chose to see it (filter, grouping: app prefs list_filter, list_group), pinned first by date."""
        return self._rows(self._app.pref("list_filter") or "all", self._app.pref("list_group") or "date")

    @Property("QVariantList", notify=changed)
    def allSessions(self):
        """Every conversation, newest first, whatever the filter (the projects' cards)."""
        return self._rows("all", "date", query=False)

    def _rows(self, kind, group, query=True):
        words = [w for w in self._query.lower().split() if w] if query else []
        proj = self.projects
        pname = (lambda sid: proj.name(proj.projectOf(sid))) if proj else (lambda sid: "")
        ephemeral = set(self._app.pref("ephemeral") or [])        # never listed: forgotten once left
        archived = set(self._app.pref("archived") or [])          # listed only under « Archivées »
        rows = [s for s in self._sessions if s["id"] not in ephemeral and (s["id"] in archived) == (kind == "archived")
                and all(w in (s["title"] or "").lower() or w in pname(s["id"]).lower() for w in words)]
        pins = self._pins()
        jobs = {j["session"] for j in self._jobs}
        out = []
        for s in rows:
            pid = proj.projectOf(s["id"]) if proj else ""
            ws = proj.name(pid) if pid else ""
            row = dict(
                s,
                pinned=s["id"] in pins,
                archived=s["id"] in archived,
                label=s["title"] or (self._first_question() if s["id"] == self._current else "") or self._t["untitled"],
                unread=self._unread.get(s["id"], 0),
                project=pid,
                projectName=ws,
                when=_when(s["timestamp"], self._app.lang),
                plan=self._app.sessionMode(s["id"]) == "plan",
                job=s["id"] in jobs,
            )
            if query and pid and not words and kind != "projects":
                continue                     # a conversation of a project lives under its project (a search finds it)
            if kind == "unread" and not row["unread"] or kind == "pinned" and not row["pinned"] \
                    or kind == "projects" and not ws or kind == "loose" and ws or kind == "pending" and not s.get("pending") \
                    or kind == "remembered" and not s.get("remembered") or kind == "jobs" and not row["job"]:
                continue
            if group == "project":
                row["group"] = ws or self._t["list_no_project"]
                row["order"] = (0 if ws else 1, ws.lower(), -int(s["timestamp"] or 0))
            elif group == "status":
                status = "pending" if s.get("pending") else "unread" if row["unread"] else "pinned" if row["pinned"] \
                    else "job" if row["job"] else "scheduled" if s.get("scheduled") else "other"
                rank = ("pending", "unread", "pinned", "job", "scheduled", "other").index(status)
                row["group"] = self._t["list_status_" + status]
                row["order"] = (rank, "", -int(s["timestamp"] or 0))
            else:
                row["group"] = self._t["pinned"] if row["pinned"] else self._t[_group(s["timestamp"])]
                row["order"] = (0 if row["pinned"] else 1, "", -int(s["timestamp"] or 0))
            out.append(row)
        out.sort(key=lambda r: r["order"])
        for r in out:
            del r["order"]
        return out

    @Property(str, notify=changed)
    def listFilter(self):
        return str(self._app.pref("list_filter") or "all")

    @Property(str, notify=changed)
    def listGroup(self):
        return str(self._app.pref("list_group") or "date")

    @Slot(str)
    def setListFilter(self, kind):
        self._app.setPref("list_filter", kind if kind in ("all", "unread", "pinned", "projects", "loose", "pending", "remembered", "jobs", "archived") else "all")
        self.changed.emit()

    @Slot(str)
    def setListGroup(self, group):
        self._app.setPref("list_group", group if group in ("date", "project", "status") else "date")
        self.changed.emit()

    # ---- the conversation's mode: Agent (every tool) or Plan (read-only, then « Run the plan ») ------------------
    @Property(str, notify=changed)
    def askMode(self):
        return self._app.sessionMode(self._current) if self._current else self._new_mode

    @Slot(str)
    def setAskMode(self, mode):
        mode = "plan" if mode == "plan" else "agent"
        if mode == "plan" and self._work_mode:          # a plan or a job, not both
            self._work_mode = ""
            self.workChanged.emit()
        if self._current:
            self._app.setSessionMode(self._current, mode)
        else:
            self._new_mode = mode
        self.changed.emit()
        self.workChanged.emit()                         # uiMode follows (« Run the plan » left the composer on Plan)

    @Property(str, notify=workChanged)
    def uiMode(self):
        """The one mode the composer shows: agent | plan | goal (a Work job) | research (a deep research)."""
        if self._work_mode == "research":
            return "research"
        if self._work_mode:
            return "goal"
        return "plan" if self.askMode == "plan" else "agent"

    @Slot(str)
    def setUiMode(self, mode):
        """Agent, Plan, Goal or Research from the composer's menu, a / command or Shift+Tab (paid plans checked by the view)."""
        if mode in ("goal", "research"):
            if self._ephemeral_next:            # a job is kept: not in an ephemeral conversation
                self._ephemeral_next = False
                self.changed.emit()
            self.setWorkKind("work" if mode == "goal" else "research")
        else:
            if self._work_mode:
                self._work_mode = ""
                self.workChanged.emit()
            self.setAskMode("plan" if mode == "plan" else "agent")

    @Property(bool, notify=changed)
    def planReady(self):
        """Ornis just proposed a plan (the last question was asked in plan mode, its answer is there)."""
        if self._busy or self._pending or len(self._messages) < 2:
            return False
        last, before = self._messages[-1], self._messages[-2]
        return last["role"] == "assistant" and before["role"] == "human" and bool(before.get("plan"))

    @Slot()
    def runPlan(self):
        """« Run the plan »: back to the agent mode, every tool, and Ornis carries out the plan it proposed."""
        if self._busy:
            return
        self.setAskMode("agent")
        self._send(self._t["plan_run_message"], [])

    # ---- context: what each question carries, « /compact » ----------------------------------------------------------
    @Property("QVariantMap", notify=contextChanged)
    def context(self):
        """{tokens, limit, percent, parts: [{key, label, tokens, percent}], compacted, compactedAt} or {} before a measure."""
        c = self._context or {}
        tokens = int(c.get("tokens") or 0)
        if not tokens:
            return {}
        limit = int(c.get("limit") or 40000)
        parts = c.get("parts") if isinstance(c.get("parts"), dict) else {}
        order = ("conversation", "tool_results", "files", "tools", "instructions", "memories", "skills", "user_rules")
        rows = [{"key": k, "label": self._t["context_" + k], "tokens": int(parts.get(k) or 0),
                 "percent": 100.0 * int(parts.get(k) or 0) / max(limit, tokens)} for k in order if int(parts.get(k) or 0) > 0]
        at = int(c.get("compacted_at") or 0)
        return {"tokens": tokens, "limit": limit, "percent": min(100, round(100 * tokens / limit)), "parts": rows,
                "compacted": str(c.get("compacted") or ""), "compactedAt": time.strftime("%H:%M", time.localtime(at)) if at else ""}

    def loadContext(self):
        sid = self._current
        client = self._client()
        if not sid or client is None:
            if self._context:
                self._context = {}
                self.contextChanged.emit()
            return

        def work():
            try:
                self._contextFetched.emit(sid, client.context(sid))
            except Error:
                pass
        self._bg(work)

    def _on_context(self, sid, data):
        if sid != self._current:
            return
        before = self._context
        self._context = data or {}
        self.contextChanged.emit()
        if (data or {}).get("compacted") == "auto" and before and int(before.get("compacted_at") or 0) != int(data.get("compacted_at") or 0):
            self.problem.emit(self._t["context_auto_done"])

    @Slot()
    def compact(self):
        """« /compact »: the agent replaces the conversation by a summary (shown as its answer); the next questions carry
        only that and what follows."""
        if self._busy:
            return
        if not self._current or not any(m["role"] == "assistant" for m in self._messages):
            self.problem.emit(self._t["context_nothing"])
            return
        self._send("/compact", [], mode="compact")

    @Property(int, notify=changed)
    def count(self):
        return len(self._sessions)

    def _pins(self):
        pins = self._app.pref("pinned")
        return set(pins) if isinstance(pins, list) else set()

    # ---- the Work mode ------------------------------------------------------------------------------------------
    @Property(bool, notify=workChanged)
    def workMode(self):
        return bool(self._work_mode)

    @Property(str, notify=workChanged)
    def workKind(self):
        """"work", "research" (the switch on beside « + ») or """""
        return self._work_mode

    @Property("QVariantMap", notify=workChanged)
    def workEstimate(self):
        """{allowed, limit, remaining, low, high, lowPercent, highPercent, enough} ({} until read)"""
        e = dict(self._estimate)
        limit = int(e.get("limit") or 0)
        if limit > 0:
            e["lowPercent"] = max(1, round(100 * int(e.get("low") or 0) / limit))
            e["highPercent"] = min(100, round(100 * int(e.get("high") or 0) / limit))
        e["enough"] = e.get("remaining") is None or int(e.get("remaining") or 0) >= int(e.get("low") or 0)
        return e

    @Property(bool, notify=workChanged)
    def paid(self):
        """A paid plan (Plus and above): Code, the reasoning and the Work modes. True until the cloud said otherwise
        (the cloud refuses them as well: the app only spares a useless try)."""
        return self._estimate.get("allowed") is not False

    @Property("QVariantList", notify=workChanged)
    def jobs(self):
        return [self._job_view(j) for j in self._jobs]

    @Property("QVariantMap", notify=workChanged)
    def currentJob(self):
        """The Work job of the open conversation ({} for an ordinary one)."""
        job = next((j for j in self._jobs if j["session"] == self._current), None)
        return self._job_view(job) if job else {}

    def _job_view(self, job):
        steps = [{"text": s, "done": i < int(job.get("done") or 0), "current": i == int(job.get("done") or 0) and job.get("status") == "running"}
                 for i, s in enumerate(job.get("plan") or [])]
        return dict(job, steps=steps, unread=self._unread.get(job["session"], 0), label=self._t["work_" + str(job.get("status") or "running")],
                    research=job.get("kind") == "research", sources=[dict(s, host=_host(s.get("url"))) for s in job.get("sources") or []],
                    folderName=str(job.get("folder") or "").rstrip("/").rsplit("/", 1)[-1])

    @Slot(bool)
    def setWorkMode(self, on):
        self.setWorkKind("work" if on else "")

    @Slot(str)
    def setWorkKind(self, kind):
        """The Work mode or the deep research (the same kind again: off)"""
        self._work_mode = kind if kind in ("work", "research") else ""
        if self._work_mode and self.askMode == "plan":     # a job or a plan, not both
            self.setAskMode("agent")
        self.workChanged.emit()
        if self._work_mode:
            self.loadEstimate()

    @Slot()
    def loadEstimate(self):
        client = self._client()
        if client is None:
            return

        def work():
            try:
                self._estimated.emit(client.work_estimate())
            except Error:
                pass
        self._bg(work)

    def _on_estimate(self, estimate):
        self._estimate = estimate or {}
        self.workChanged.emit()

    @Slot()
    def loadJobs(self):
        client = self._client()
        if client is None:
            return

        def work():
            try:
                self._jobsFetched.emit(client.work_jobs())
            except Error:
                pass
        self._bg(work)

    def _on_jobs(self, jobs):
        self._jobs = jobs or []
        self.workChanged.emit()
        self._follow_job()

    def _follow_job(self):
        """A job being done in the open conversation: its steps every 2 s until it stops."""
        job = next((j for j in self._jobs if j["session"] == self._current), None)
        live = (job is not None and job.get("status") == "running") or (
            self._busy and (job is not None or self._work_sent == self._current)
        )
        if live and not self._job_timer.isActive():
            self._job_timer.start()
        elif not live and self._job_timer.isActive():
            self._job_timer.stop()

    def _poll_job(self):
        client, sid = self._client(), self._current
        if client is None or not sid:
            return

        def work():
            try:
                self._jobFetched.emit(sid, client.work_job(sid))
            except Error:
                pass
        self._bg(work)

    def _on_job(self, sid, job):
        if not job:
            return
        job = dict(job, session=str(sid))
        prev = next((j for j in self._jobs if j["session"] == job["session"]), None)
        others = [j for j in self._jobs if j["session"] != job["session"]]
        self._jobs = [job] + others if prev is None else [
            job if j["session"] == job["session"] else j for j in self._jobs
        ]
        self.workChanged.emit()
        self._follow_job()
        if prev is not None and prev.get("status") != job.get("status") and job["session"] == self._current and not self._busy:
            self._reload_current()

    # ---- dictation (ornis_voice) -----------------------------------------------------------------------------------
    @Property(QObject, constant=True)
    def voice(self):
        return self._voice

    def _dictated(self, data, mime):
        client = self._client()
        if client is None:
            raise Error(0)
        return client.transcribe(data, mime)

    # ---- « Personnaliser Ornis »: the cloud keeps it, the agent reads it at each question --------------------
    @Property("QVariantMap", notify=profileChanged)
    def profile(self):
        return self._profile

    @Slot()
    def loadProfile(self):
        client = self._client()
        if client is None:
            return

        def work():
            try:
                self._profileFetched.emit(client.profile())
            except Error:
                self._profileFetched.emit({"failed": True})
        self._bg(work)

    def _on_profile(self, profile):
        self._profile = profile or {}
        self.profileChanged.emit()
        if getattr(self, "_slash_query", None) is not None:      # the « / » menu open: the user's commands join it
            self.searchSlashes(self._slash_query)

    @Slot("QVariantMap")
    def saveProfile(self, change):
        """Kept at once here; only a refusal comes back."""
        client = self._client()
        if client is None:
            return
        change = {k: change[k] for k in ("name", "about", "style", "enabled", "commands") if k in change}
        if "commands" in change:          # QML hands a list of maps: plain dicts for the JSON
            change["commands"] = [{"name": str(c.get("name") or ""), "text": str(c.get("text") or "")}
                                  for c in (change["commands"] or []) if hasattr(c, "get")]
        before = dict(self._profile)
        self._profile = dict(self._profile, **change)
        self.profileChanged.emit()
        self._app.toast.emit(self._t["commands_saved" if set(change) == {"commands"} else "profile_saved"])

        def work():
            try:
                client.save_profile(change)
            except Error:
                self._profileFetched.emit(before)
                self._failed.emit(self._t["profile_failed"])
        self._bg(work)

    @Slot(str, str)
    def forget(self, kind, item_id):
        """A memory (its file goes to the Drive's trash) or a conversation Ornis remembered."""
        client = self._client()
        if client is None:
            return
        key = "memories" if kind == "memory" else "remembered"
        before = dict(self._profile)
        self._profile = dict(self._profile, **{key: [m for m in self._profile.get(key) or [] if str(m.get("id")) != str(item_id)]})
        self.profileChanged.emit()
        if kind != "memory" and str(item_id) == self._current:
            self._remembered = False
            self.changed.emit()

        def work():
            try:
                if kind == "memory":
                    client.forget_memory(item_id)
                else:
                    client.forget_remembered(item_id)
            except Error:
                self._profileFetched.emit(before)
                self._failed.emit(self._t["profile_failed"])
        self._bg(work)

    @Slot(str)
    def sendWork(self, text):
        """The question that starts a Work job or a deep research (the agent asks the cloud for it: paid plans only)."""
        kind = self._work_mode or "work"
        self._work_mode = ""
        self.workChanged.emit()
        self._send(text, [], None, kind)

    @Slot()
    def resumeWork(self):
        """A stopped job goes on where it was (its plan and steps done are kept): the agent reads them first."""
        self._send(self._t["work_resume_message"], [])

    @Property(int, notify=changed)
    def unreadCount(self):
        return len(self._unread)

    # what else is unread in Ornis (Code bots and groups, set by bundle.py): one number for the dock and Plume's rail,
    # never two signals overwriting each other
    extra_badge = staticmethod(lambda: 0)

    @Slot()
    def refreshBadge(self):
        try:
            extra = int(self.extra_badge() or 0)
        except Exception:  # noqa: BLE001
            extra = 0
        self.badgeChanged.emit(len(self._unread) + extra)

    @Property(str, notify=changed)
    def current(self):
        return self._current

    def _first_question(self) -> str:
        """Until the cloud names a conversation: its first question, on one line (never « sans titre »)."""
        first = next((m for m in self._messages if m.get("role") == "human" and m.get("content")), None)
        text = " ".join(str(first["content"]).split()) if first else ""
        return text if len(text) <= 60 else text[:58].rstrip() + "…"

    @Property(str, notify=changed)
    def title(self):
        return next((s["title"] for s in self._sessions + self._task_sessions if s["id"] == self._current), "") or (
            self._t["new_chat"] if not self._current else self._first_question() or self._t["untitled"])

    @Property("QVariantList", notify=changed)
    def messages(self):
        out = [self._view(m) for m in self._messages]
        for i in range(1, len(out)):
            if out[i]["role"] == "assistant" and out[i - 1]["compact"]:
                out[i]["compactAnswer"] = True
        # the answers given before (regenerated, or to the question as it was before an edit): ‹ 1/2 › under the answer
        asked = -1
        for i, m in enumerate(out):
            if m["role"] == "human":
                asked += 1
                continue
            if i + 1 < len(out) and out[i + 1]["role"] == "assistant":
                continue                       # only the last answer of a question carries its versions
            older = self._versions_of(asked)
            m["versions"] = [dict(v, current=False) for v in older] + ([{"content": m["content"], "question": "", "current": True}] if older else [])
        return out

    # ---- versions: the cloud keeps one answer per question; the ones before stay on this computer -------------------
    VERSIONS = system.STATE / "ornis-versions.json"

    def _all_versions(self):
        if not hasattr(self, "_versions"):
            try:
                self._versions = json.loads(self.VERSIONS.read_text())
            except (OSError, ValueError):
                self._versions = {}
        return self._versions

    def _versions_of(self, asked):
        return list(self._all_versions().get(f"{self._current}:{asked}", [])) if self._current and asked >= 0 else []

    def _keep_version(self, asked, answer, question=""):
        """An answer about to be replaced (« Régénérer », an edited question): kept to be read again."""
        if not self._current or asked < 0 or not answer or not (answer.get("content") or "").strip():
            return
        all_ = self._all_versions()
        key = f"{self._current}:{asked}"
        kept = all_.pop(key, [])[-9:] + [{"content": answer["content"][:40000], "question": question[:400]}]
        all_[key] = kept
        while len(all_) > 300:
            all_.pop(next(iter(all_)))
        try:
            self.VERSIONS.parent.mkdir(parents=True, exist_ok=True)
            self.VERSIONS.write_text(json.dumps(all_, ensure_ascii=False))
        except OSError:
            pass

    @Property("QVariantList", notify=filesChanged)
    def attachments(self):
        return [{k: f[k] for k in ("key", "name", "kind", "state", "thumb")} for f in self._files]

    @Property(bool, notify=filesChanged)
    def uploading(self):
        return any(f["state"] == "uploading" for f in self._files)

    @Property("QVariantList", notify=changed)
    def pending(self):
        return [tools.action(a, self._t) for a in self._pending]

    @Property(bool, notify=changed)
    def remembered(self):
        return self._remembered

    @Property(bool, notify=streamChanged)
    def busy(self):
        return self._busy

    @Property(str, notify=streamChanged)
    def stream(self):
        return self._stream

    @Property(str, notify=streamChanged)
    def streamReasoning(self):
        """What Ornis thinks before and between its tools, as the cloud streams it (shown folded, live)."""
        return self._reasoning

    @Property(str, notify=streamChanged)
    def working(self):
        """« Ornis consulte votre agenda… » while it uses a tool, else « Ornis réfléchit… »."""
        if self._computer:
            if self._computer.get("phase") == "asking":
                return self._t["ornis_computer_asking"]
            return self._t["ornis_computer_running"].replace("%1", str(self._computer.get("summary") or "").split("\n")[0])
        if self._slow and not self._stream:
            return self._t["ornis_slow"]
        if self._working:
            return self._t["ornis_using"].replace("%1", self._working[-1]["label"])
        return self._t["ornis_working"]

    @Property("QVariantMap", notify=streamChanged)
    def computer(self):
        """What Ornis is doing on this computer right now ({phase: asking|running, summary, command}), else {}."""
        return self._computer or {}

    @Property("QVariantList", notify=streamChanged)
    def workingTools(self):
        return self._working

    @Property(str, notify=streamChanged)
    def error(self):
        return self._error

    @Property("QVariantList", notify=scheduledChanged)
    def scheduled(self):
        # the unread answers of each task's conversation, read now: they change more often than the tasks
        return [dict(r, unread=self._unread.get(r["session"], 0) if r["session"] else 0) for r in self._scheduled_rows]

    @Property(str, notify=changed)
    def currentTask(self):
        """The scheduled task whose conversation is open ("" for an ordinary conversation)."""
        return next((r["id"] for r in self._scheduled_rows if r["session"] and r["session"] == self._current), "")

    @Property("QVariantMap", notify=quotaChanged)
    def quota(self):
        return self._quota_info or {}

    @Property("QVariantMap", notify=usageChanged)
    def usage(self):
        """{used, limit, percent, hours, ai} (ornis_chat.Client.usage), {} until read; loadUsage reads it again."""
        return getattr(self, "_usage_info", None) or {}

    @Slot()
    def loadUsage(self):
        """Read when the usage panel opens, and after the browser was opened to change the offer (it may be done)."""
        def work():
            client = self._client()
            try:
                info = client.usage() if client else None
            except Exception:  # noqa: BLE001 - offline: the panel keeps what it had
                info = None
            if info is not None:
                self._usageFetched.emit(info)
                limit = int(info.get("limit") or 0)
                if limit > 0:          # the gauge follows at once (a new offer raises the limit)
                    used = int(info.get("used") or 0)
                    self._quota.emit({"used": used, "limit": limit, "percent": min(100, round(100 * used / limit))})
        self._bg(work)

    @Property("QVariantMap", notify=regionChanged)
    def region(self):
        """{region, effective, needs_consent, regions} (ornis_chat.Client.region), {} until read."""
        return getattr(self, "_region_info", None) or {}

    @Slot()
    def loadRegion(self):
        def work():
            client = self._client()
            try:
                info = client.region() if client else None
            except Exception:  # noqa: BLE001 - offline: the panel keeps what it had
                info = None
            if info is not None:
                self._regionFetched.emit(info)
        self._bg(work)

    @Slot(str, "QVariantList")
    def setRegion(self, region, accept):
        """« eu » at once; « global » with the countries the warning listed (the cloud refuses an incomplete list)."""
        def work():
            client = self._client()
            try:
                result = client.set_region(region, [str(c) for c in accept or []]) if client else {"error": "failed"}
            except Exception:  # noqa: BLE001
                result = {"error": "failed"}
            if not result.get("error"):
                result["_set"] = region
            self._regionFetched.emit(result)
        self._bg(work)

    @Slot()
    def useReset(self):
        """Spend one banked reset (Settings › Utilisation). The cloud refuses it while 80 % or more remains."""
        def work():
            client = self._client()
            try:
                result = client.use_reset() if client else None
            except Exception:  # noqa: BLE001 - the panel says it did not go through
                result = None
            self._resetFetched.emit(result if isinstance(result, dict) else {"ok": False, "reason": "failed"})
        self._bg(work)

    # ---- the list ----------------------------------------------------------------------------------------------
    @Slot()
    @Slot(bool)
    def refresh(self, first=True):
        client = self._client()
        if client is None:
            self._sessions, self._state = [], "signed_out"
            self.changed.emit()
            return

        rev, dirty, local = self._pin_rev, bool(self._app.pref("pins_dirty")), list(self._app.pref("pinned") or [])
        archived_dirty, archived = bool(self._app.pref("archived_dirty")), list(self._app.pref("archived") or [])
        vote_rev = self.__dict__.get("_vote_rev", 0)
        archive_rev = self.__dict__.get("_archive_rev", 0)
        if first:                       # ephemeral conversations left behind (the app closed, offline): gone now
            for session_id in list(self._app.pref("ephemeral") or []):
                if session_id != self._current:
                    self._forget(session_id)

        def work():
            try:
                self._listed.emit(client.sessions(), "")
            except Error as error:
                self._listed.emit(None, "offline" if error.code == 0 else "error")
            try:  # the pins made offline go up; otherwise the cloud's (changed in the browser) come down
                self._pinned.emit(client.set_pins(local) if dirty else client.pins(), rev, "")
            except Error:
                pass
            try:  # archived offline: sent; otherwise the cloud's (archived in the browser or elsewhere)
                self._archivedFetched.emit(client.set_archived(archived) if archived_dirty else client.archived(), False, archive_rev)
            except Error as error:
                self._archivedFetched.emit([], error.code == 0, archive_rev)
            try:
                self._votesFetched.emit(client.votes(), vote_rev)
            except Error:
                pass
            try:
                self._unreadFetched.emit(client.unread())
            except Error:
                pass
            self._quota.emit(client.quota())
        self._bg(work)
        self.loadJobs()
        self.loadEstimate()            # the plan: free plans have neither Code nor the reasoning
        self.loadScheduled()           # the Tasks list is ready (and its unread counts) before it is asked for
        if not first and self._current and not self._busy:
            self._reload_current()

    # ---- read / unread -----------------------------------------------------------------------------------------
    def _poll_unread(self):
        client = self._client()
        if client is None:
            return

        def work():
            try:
                self._unreadFetched.emit(client.unread())
            except Error:
                pass
        self._bg(work)
        if any(j.get("status") == "running" for j in self._jobs):
            self.loadJobs()

    def _on_unread(self, unread):
        before = self._unread_seen
        self._unread_seen = dict(unread)
        if self._front and self._current in unread and not self._busy:
            self._reload_current()  # mark read only after the new messages actually reached the view
        if self._unread != unread:
            self._unread = unread
            self.changed.emit()
            self.scheduledChanged.emit()
            self.loadJobs()
            self.loadScheduled()
        self.refreshBadge()
        if before is None or not self._relay or not self._app.pref("notify"):
            return
        for sid, count in unread.items():              # a new answer from elsewhere (a scheduled task, another device)
            if count > before.get(sid, 0) and not (self._busy and sid == self._current):
                title = next((s["title"] for s in self._sessions + self._task_sessions if s["id"] == sid), "") or self._t["app_name"]
                self._app.notify(title, self._t["reply_ready"], sid)

    def _mark(self, session_id):
        """Read in the cloud (its bell's notifications go too), wherever the user looks next."""
        client = self._client()
        if client is None or not session_id:
            return

        last = max((int(m["id"]) for m in self._messages if str(m.get("id", "")).isdigit()), default=0)
        if not last:
            return
        def work():
            try:
                self._unreadFetched.emit(client.mark_read(session_id, last))
            except Error:
                pass
        self._bg(work)

    def _read_current(self):
        """The conversation shown to the user is read (shown read at once, the cloud follows)."""
        sid = self._current
        if not self._front or not sid or sid not in self._unread:
            return
        self._unread = {k: v for k, v in self._unread.items() if k != sid}
        self.changed.emit()
        self.scheduledChanged.emit()
        self.refreshBadge()
        self._mark(sid)

    @Property(bool, notify=changed)
    def panelShown(self):
        """Plume shows Ornis as a side panel beside a module: its replies are seen there (no notification)."""
        return bool(getattr(self, "_panel", False))

    def set_panel(self, shown):
        self._panel = bool(shown)
        self.changed.emit()

    @Slot(bool)
    def set_active(self, front):
        """Ornis is in front (its window active, or its module shown in Plume): what it shows is read."""
        self._front = bool(front)
        if self._front:
            self._reload_current()
            self._poll_unread()

    def _reload_current(self):
        client, sid = self._client(), self._current
        if not client or not sid or self._busy or getattr(self, "_reloading", False):
            return
        self._reloading = True
        revision = self._run
        def work():
            try:
                self._refreshed.emit(sid, client.messages(sid), client.check_session(sid), revision)
            except Error:
                self._refreshed.emit(sid, None, None, revision)
        self._bg(work)

    def _on_refreshed(self, sid, messages, status, revision):
        self._reloading = False
        if sid == self._current and revision == self._run and not self._busy and messages is not None:
            self._on_opened(sid, messages, status, "")

    def _on_listed(self, rows, problem):
        if rows is None:
            if self._state == "loading":
                self._state = "offline_first" if problem == "offline" else "error_first"
                self.changed.emit()
            return
        first = self._state != "ready"
        if not first and rows == self._sessions:
            return                      # coming back to Ornis: the same list, nothing to redraw
        self._sessions, self._state = rows, "ready"
        self.changed.emit()
        if first:
            last = self._app.pref("session")
            if last and any(s["id"] == last for s in rows):
                self.open(last)

    @Slot(str)
    def setQuery(self, query):
        self._query = query or ""
        self.changed.emit()

    # ---- one conversation ------------------------------------------------------------------------------------
    @Slot(str)
    def open(self, session_id):
        session_id = str(session_id or "")
        if session_id == self._current and self._messages:
            return
        if self._current and self._current != session_id and self._current in (self._app.pref("ephemeral") or []):
            self._forget(self._current)          # an ephemeral conversation left: gone, in the cloud too
        self._ephemeral_next = False
        self._remember_messages()
        if getattr(self, "_later", None):
            self._clear_later(give_back=True)
        cached = self._seen_messages.get(session_id) if session_id else None
        # already seen: shown at once, the cloud is read again behind; else a skeleton until its messages arrive
        self._loading = bool(session_id) and cached is None
        self._current, self._messages, self._pending = session_id, list(cached or []), []
        self._remembered = next((s.get("remembered", False) for s in self._sessions + self._task_sessions if s["id"] == session_id), False)
        self._run += 1
        self._reveal.stop()
        self._target = ""
        self._busy, self._stream, self._working, self._error, self._slow = False, "", [], "", False
        self._app.setPref("session", session_id)
        self._app.activateSessionWorkspace(session_id)      # its project, or none: never the previous one's
        self._context = {}
        self.contextChanged.emit()
        if not session_id:
            self._new_mode = "agent"
            self._new_project = ""
        self.changed.emit()
        self.streamChanged.emit()
        self._follow_job()
        if not session_id:
            return
        if any(j["session"] == session_id for j in self._jobs):
            self._poll_job()
        client = self._client()

        def work():
            try:
                messages = client.messages(session_id)
                status = client.check_session(session_id)
                self._opened.emit(session_id, messages, status, "")
            except Error as error:
                self._opened.emit(session_id, None, None, "offline" if error.code == 0 else "failed")
        self._bg(work)

    def _remember_messages(self):
        if self._current and self._messages and not self._busy:
            self._seen_messages.pop(self._current, None)
            self._seen_messages[self._current] = [m for m in self._messages if not str(m.get("id", "")).startswith("local-")]
            while len(self._seen_messages) > 30:
                self._seen_messages.pop(next(iter(self._seen_messages)))

    @Property(bool, notify=changed)
    def loading(self):
        """A conversation opened for the first time: its messages are on their way (the view shows their shape)."""
        return self._loading

    def _on_opened(self, session_id, messages, status, problem):
        self._reloading = False
        if session_id == "__new__":
            if not self._current and self._busy:
                self._adopt(messages)
            return
        if session_id != self._current:
            return
        if self._loading:
            self._loading = False
            self.changed.emit()
        if messages is None:
            self._error = problem
            self.streamChanged.emit()
            return
        self._messages = messages
        self._pending = status["pending"]
        self._remembered = status["remembered"]
        self.changed.emit()
        self._describe(messages)
        self._read_current()
        self.loadContext()
        if status.get("task"):                 # a reply still being written (started here, in the applet or the cloud)
            self._follow(session_id, str(status["task"]))

    # ---- ephemeral conversations: not listed, no memories read or written (EPHEMERAL_TAG), deleted once left ------
    @Property(bool, notify=changed)
    def ephemeral(self):
        return (not self._current and self._ephemeral_next) or self._current in (self._app.pref("ephemeral") or [])

    @Slot(bool)
    def setEphemeral(self, on):
        """A new conversation only (one already in the cloud stays as it is). Not with a goal or a research:
        leaving would delete their work."""
        if self._current or self._ephemeral_next == bool(on):
            return
        self._ephemeral_next = bool(on)
        if on and self._work_mode:
            self.setUiMode("agent")
        self.changed.emit()

    def _forget(self, session_id, wait=False):
        self._sessions = [s for s in self._sessions if s["id"] != session_id]
        self._seen_messages.pop(session_id, None)
        client = self._client()
        if client is None:
            return                              # kept in the list: deleted at the next start
        self._app.setPref("ephemeral", [s for s in (self._app.pref("ephemeral") or []) if s != session_id])

        def work():
            try:
                client.delete(session_id)
            except Error as error:
                if error.code == 0:             # offline: back in the list, deleted at the next start
                    if wait:
                        self._keep_ephemeral(session_id)
                    else:
                        self._ephemeralKept.emit(session_id)
        if wait:
            work()
        else:
            self._bg(work)
        self.changed.emit()

    def _keep_ephemeral(self, session_id):
        self._app.setPref("ephemeral", list(self._app.pref("ephemeral") or []) + [session_id])

    @Slot()
    def newChat(self):
        self.open("")

    @Slot(str)
    def newChatInProject(self, pid):
        """A new conversation in a project of the Work mode: its folder on this computer is the workspace."""
        self.open("")
        self._new_project = pid
        self.projectFolderChanged()
        self.changed.emit()

    @Property(str, notify=changed)
    def project(self):
        """The project of the open conversation (or of the new one), "" when none."""
        if self._current:
            return self.projects.projectOf(self._current) if self.projects else ""
        return self._new_project

    @Property(str, notify=changed)
    def projectName(self):
        return self.projects.name(self.project) if self.projects and self.project else ""

    @Slot(str)
    def setProject(self, pid):
        """The project chip of the message box: the open conversation moves to a project (or the new one starts in it)."""
        if self._current:
            if self.projects:
                self.projects.assign(self._current, pid)
        else:
            self._new_project = pid
            self.projectFolderChanged()
            self.changed.emit()

    def projectFolderChanged(self):
        """The workspace follows the project's folder on this computer (computer tools), or goes."""
        if self._current:
            self._app.activateSessionWorkspace(self._current)
        else:
            self._app.useWorkspace(self.projects.local_folder(pid=self._new_project) if self.projects and self._new_project else "")

    @Slot(str)
    def newChatIn(self, path):
        """A new conversation in a project: its folder is the workspace of what follows."""
        self.open("")
        if path:
            self._app.useWorkspace(path)

    @Slot(str)
    def send(self, text):
        text = (text or "").strip()
        if self._busy and text:          # written while Ornis answers: sent after the reply, as in Claude Code
            self._later = list(getattr(self, "_later", [])) + [text]
            self._later_for = self._current
            self.laterChanged.emit()
            return
        self._send(text, [])

    @Property("QVariantList", notify=streamChanged)
    def liveSteps(self):
        """The tool calls of the reply being written, as they come: [{icon, label, detail}]."""
        return tools.step_rows(getattr(self, "_live_steps", []), self._t) if self._busy else []

    @Slot(str)
    def loadSteps(self, message_id):
        """An answer's steps, read once from its task (unfolded under the answer)."""
        message_id = str(message_id)
        known = getattr(self, "_steps_of", {})
        msg = next((m for m in self._messages if m["id"] == message_id), None)
        client = self._client()
        if message_id in known or not msg or not msg.get("task") or client is None:
            return
        self._steps_of = dict(known, **{message_id: []})        # asked once, even if the task is gone

        def work():
            try:
                found = client.task_steps(msg["task"])
            except Error:
                found = []
            self._stepsRead.emit(message_id, found)
        self._bg(work)

    def _on_shared(self, url):
        QGuiApplication.clipboard().setText(url)
        self.exported.emit(self._t["shared_link"])

    def _on_steps_read(self, message_id, found):
        self._steps_of = dict(getattr(self, "_steps_of", {}), **{message_id: list(found)})
        self.changed.emit()

    @Property("QVariantList", notify=laterChanged)
    def later(self):
        """The messages waiting for the reply being written (this conversation's only)."""
        return list(getattr(self, "_later", []))

    @Slot(int)
    def dropLater(self, index):
        later = list(getattr(self, "_later", []))
        if 0 <= index < len(later):
            del later[index]
            self._later = later
            self.laterChanged.emit()

    @Slot(int)
    def editLater(self, index):
        """« Modifier »: out of the queue, back into the box."""
        later = list(getattr(self, "_later", []))
        if 0 <= index < len(later):
            text = later.pop(index)
            self._later = later
            self.laterChanged.emit()
            self.laterReturned.emit(text)

    @Slot(int)
    def sendLaterNow(self, index):
        """« Envoyer maintenant »: the reply being written stops, this message goes at once (the others still wait)."""
        later = list(getattr(self, "_later", []))
        if not 0 <= index < len(later):
            return
        text = later.pop(index)
        self._later = []                     # stop() gives the queue back to the box: kept here instead
        if self._busy:
            self.stop()
        self._later, self._later_for = later, self._current
        self.laterChanged.emit()
        self._send(text, [])

    def _clear_later(self, give_back=False):
        later = list(getattr(self, "_later", []))
        self._later = []
        self.laterChanged.emit()
        if give_back and later:
            self.laterReturned.emit("\n\n".join(later))

    def _send_later(self):
        """The reply is there (and asks nothing): the next waiting message goes."""
        later = list(getattr(self, "_later", []))
        if not later or self._busy or self._pending or getattr(self, "_later_for", None) not in (self._current, ""):
            return
        text = later.pop(0)
        self._later = later
        self.laterChanged.emit()
        self._send(text, [])

    # ---- attachments -------------------------------------------------------------------------------------------
    def _check(self, name, size):
        """A refusal to show, or "" when Ornis can take the file."""
        if len(self._files) >= MAX_ATTACHMENTS:
            return self._t["attach_too_many"]
        if not attachment_kind(name):
            return self._t["attach_unsupported"].replace("%1", name)
        if size > MAX_BYTES:
            return self._t["attach_too_big"].replace("%1", name)
        return ""

    def _add(self, name, size, thumb="", file_id="", local=""):
        problem = self._check(name, size)
        if problem:
            self.problem.emit(problem)
            return None
        entry = {"key": uuid.uuid4().hex, "name": name, "kind": attachment_kind(name), "size": size,
                 "state": "ready" if file_id else "uploading", "file_id": file_id, "thumb": thumb, "local": local}
        self._files = self._files + [entry]
        self.filesChanged.emit()
        return entry

    def _upload(self, entry, path, temporary=False):
        """Sent to the Drive (Assistant folder) at once, while the question is written: sending waits for nothing."""
        client = self._client()
        key = entry["key"]

        def work():
            file_id = ""
            try:
                data = Path(path).read_bytes()
                file_id = client.upload(entry["name"], data, mimetypes.guess_type(entry["name"])[0] or "application/octet-stream") if client else ""
            except (OSError, Error):
                file_id = ""
            finally:
                if temporary and not entry["thumb"]:
                    Path(path).unlink(missing_ok=True)
            self._uploaded.emit(key, file_id, "")
        self._bg(work)

    def _on_uploaded(self, key, file_id, thumb):
        for f in self._files + [self._inflight.pop(key)] if key in self._inflight else self._files:
            if f["key"] == key:
                f["state"] = "ready" if file_id else "failed"
                f["file_id"] = file_id
                if thumb:
                    f["thumb"] = thumb
                if file_id:                  # its name (and vignette) in the history, without asking the cloud
                    self._known[file_id] = {"name": f["name"], "thumb": f["thumb"],
                                            "full": QUrl.fromLocalFile(f["local"]).toString() if f.get("local") else ""}
        self._files = list(self._files)
        self.filesChanged.emit()

    @Slot("QVariantList")
    def addFiles(self, urls):
        """Files from this computer (picked, dropped, pasted): those of the synced Orneos folder are already in the
        Drive and are only pointed at; the others are uploaded. A dropped folder pins the active workspace."""
        root = str(cloud.SYNC_DIR)
        for url in urls:
            path = url.toLocalFile() if isinstance(url, QUrl) else str(url).removeprefix("file://")
            item = Path(path)
            if not path:
                continue
            if item.is_dir():
                self._app.setWorkspace(path)
                continue
            if not item.is_file():
                continue
            size = item.stat().st_size
            thumb = QUrl.fromLocalFile(path).toString() if attachment_kind(item.name) == "image" else ""
            if path.startswith(root + "/"):
                entry = self._add(item.name, size, thumb)
                if entry:
                    self._resolve(entry, "/" + path[len(root) + 1:])
            else:
                entry = self._add(item.name, size, thumb, local=path)
                if entry:
                    self._upload(entry, path)

    @Slot()
    def captureScreenshot(self):
        """Captures the active screen and attaches the PNG to the composer."""
        def work():
            try:
                import ornis_desktop  # noqa: PLC0415
                res = ornis_desktop.screenshot("screen", 0)
                self._screenshotDone.emit(str(res.get("path") or "") if isinstance(res, dict) else "")
            except Exception:  # noqa: BLE001
                self._screenshotDone.emit("")
        self._bg(work)

    def _on_screenshot(self, path):
        if path and Path(path).is_file():
            self.addFiles([path])
            self._app.toast.emit(self._t["screenshot_attached"])
        else:
            self.problem.emit(self._t["screenshot_failed"])

    @Property("QVariantList", notify=mentionsChanged)
    def mentions(self):
        return self._mentions

    @Slot()
    def clearMentions(self):
        if self._mentions:
            self._mentions = []
            self.mentionsChanged.emit()

    @Slot(str)
    def searchMentions(self, query):
        """Builds @-mention candidates: quick actions, local files/folders, Drive files, installed skills & MCP servers."""
        self._mention_rev += 1
        rev = self._mention_rev
        q = str(query or "").strip().lower()
        local_enabled = bool(self._app.pref("local_tools"))
        ws = self._app.workspace

        def work():
            items = []
            actions = [
                ("action_local_file", self._t["mention_pick_local"], self._t["mention_local_sub"], "attach", ""),
                ("action_workspace", self._t["mention_pick_workspace"], ws or self._t["workspace_label"], "folder", ""),
                ("action_drive", self._t["mention_pick_drive"], self._t["mention_drive_sub"], "cloud", ""),
                ("action_screenshot", self._t["mention_screenshot"], self._t["mention_local_sub"], "image", ""),
            ]
            for kind, lbl, sub, ic, val in actions:
                if not local_enabled and kind in ("action_workspace", "action_screenshot"):
                    continue
                if not q or q in lbl.lower() or q in sub.lower() or q in kind:
                    items.append({"kind": kind, "label": lbl, "sub": sub, "icon": ic, "value": val})
            if local_enabled:
                # skills and MCP servers are actions: they are in « / », not here
                try:
                    import ornis_desktop  # noqa: PLC0415
                    root = Path(ws) if ws and Path(ws).is_dir() else Path.home()
                    if q:
                        found = ornis_desktop.find_files(q, str(root), limit=8)
                    else:
                        listing = ornis_desktop.list_folder(str(root), hidden=False, limit=12)
                        found = listing.get("items") if isinstance(listing, dict) else []
                    for entry in (found if isinstance(found, list) else [])[:8]:
                        if not isinstance(entry, dict) or not entry.get("path"):
                            continue
                        p = str(entry["path"])
                        name = str(entry.get("name") or Path(p).name)
                        is_dir = entry.get("type") == "folder"
                        try:
                            rel = "~/" + str(Path(p).relative_to(Path.home()))
                        except ValueError:
                            rel = p
                        items.append({
                            "kind": "local_folder" if is_dir else "local_file",
                            "label": name,
                            "sub": self._t["mention_local_sub"] + " · " + rel,
                            "icon": "folder" if is_dir else "file",
                            "value": p,
                            "attachable": bool(not is_dir and attachment_kind(name)),
                        })
                except Exception:  # noqa: BLE001
                    pass
            # Drive files (from local sync dir or cached root listing)
            try:
                sync_dir = cloud.SYNC_DIR
                if sync_dir.is_dir():
                    matches = []
                    for f in sync_dir.rglob("*") if q else sync_dir.iterdir():
                        if f.name.startswith("."):
                            continue
                        if f.is_file() and attachment_kind(f.name) and (not q or q in f.name.lower()):
                            matches.append(f)
                            if len(matches) >= 5:
                                break
                    for f in matches:
                        rel = "/" + str(f.relative_to(sync_dir))
                        items.append({
                            "kind": "cloud_local",
                            "label": f.name,
                            "sub": self._t["mention_drive_sub"] + " · " + rel,
                            "icon": "cloud",
                            "value": str(f),
                        })
                else:
                    now_ts, cached_rows = self._drive_cache
                    if time.time() - now_ts > 60:
                        client = self._client()
                        if client:
                            cached_rows = [r for r in client.folder("/") if not r.get("folder") and attachment_kind(r.get("name", ""))]
                            self._drive_cache = (time.time(), cached_rows)
                    for r in cached_rows:
                        if not q or q in str(r.get("name") or "").lower():
                            items.append({
                                "kind": "cloud_remote",
                                "label": str(r.get("name") or ""),
                                "sub": self._t["mention_drive_sub"] + " · " + str(r.get("path") or ""),
                                "icon": "cloud",
                                "value": str(r.get("path") or ""),
                                "file_id": str(r.get("file_id") or ""),
                                "size": int(r.get("size") or 0),
                            })
                            if len(items) >= 16:
                                break
            except Exception:  # noqa: BLE001
                pass
            self._mentionsFetched.emit(rev, items[:14])
        self._bg(work)

    def _on_mentions(self, rev, items):
        if rev != self._mention_rev:
            return
        self._mentions = items or []
        self.mentionsChanged.emit()

    @Property("QVariantList", notify=slashesChanged)
    def slashes(self):
        return self._slashes

    @Slot()
    def clearSlashes(self):
        if self._slashes:
            self._slashes = []
            self.slashesChanged.emit()

    @Slot(str)
    def searchSlashes(self, query):
        """Builds /-command and local Skill candidates for the composer slash menu."""
        self._slash_rev += 1
        rev = self._slash_rev
        q = str(query or "").strip().lower().lstrip("/")
        local_enabled = bool(self._app.pref("local_tools"))
        self._slash_query = query
        if "commands" not in self._profile and not getattr(self, "_profile_asked", False):
            self._profile_asked = True           # the user's own commands live with « Personnaliser Ornis »
            self.loadProfile()
        mine = [c for c in self._profile.get("commands") or [] if isinstance(c, dict)]

        def work():
            t = self._t
            builtins = [
                ("mode_plan", "/plan", t["slash_plan_sub"], "list", ""),
                ("mode_agent", "/agent", t["slash_agent_sub"], "ornis", ""),
                ("mode_goal", "/goal", t["slash_goal_sub"], "flag", ""),
                ("mode_research", "/" + t["slash_research_cmd"], t["slash_research_sub"], "globe", ""),
                ("compact", "/compact", t["slash_compact_sub"], "collapse", ""),
                ("new", "/" + t["slash_new_cmd"], t["slash_new_sub"], "compose", ""),
                ("prompt", "/" + t["slash_resume_cmd"], t["slash_resume_sub"], "note", t["slash_resume_value"]),
                ("mode_code", "/code", t["slash_code_mode_sub"], "code", ""),
                ("prompt", "/mail", t["slash_mail_sub"], "send", t["slash_mail_value"]),
                ("prompt", "/" + t["slash_task_cmd"], t["slash_task_sub"], "check", t["slash_task_value"]),
                ("prompt", "/note", t["slash_note_sub"], "edit", t["slash_note_value"]),
                ("undo", "/undo", t["slash_undo_sub"], "restore", ""),
            ]
            items = []
            # the user's own commands first: their text goes into the box (« Mes commandes », Settings › Personnalisation)
            for c in mine:
                name, text = str(c.get("name") or ""), str(c.get("text") or "")
                if name and (not q or q in name.lower() or q in text.lower()):
                    items.append({"kind": "prompt", "label": "/" + name, "sub": " ".join(text.split())[:80], "icon": "user",
                                  "value": text + ("" if text.endswith((" ", "\n")) else " ")})
            if not q or q in t["slash_commands_cmd"]:
                items.append({"kind": "commands", "label": "/" + t["slash_commands_cmd"], "sub": t["slash_commands_sub"],
                              "icon": "edit", "value": ""})
            for kind, cmd, sub, ic, val in builtins:
                if not local_enabled and kind == "undo":
                    continue
                if not q or q in cmd[1:].lower() or q in sub.lower():
                    items.append({"kind": kind, "label": cmd, "sub": sub, "icon": ic, "value": val})
            if local_enabled:
                try:
                    import ornis_extensions  # noqa: PLC0415
                    cat = ornis_extensions.catalogue()
                    for sk in cat.get("skills") or []:
                        name = str(sk.get("name") or "")
                        desc = str(sk.get("description") or self._t["mention_skill_sub"])
                        if name and (not q or q in name.lower() or q in desc.lower()):
                            items.append({
                                "kind": "skill",
                                "label": "/" + name,
                                "sub": desc[:80],
                                "icon": "sparkle",
                                "value": name,
                            })
                    for srv in cat.get("mcpServers") or []:
                        name = str(srv.get("name") or "")
                        tools_s = ", ".join(srv.get("tools") or []) or self._t["mention_mcp_sub"]
                        if name and (not q or q in name.lower() or "mcp" in q or q in tools_s.lower()):
                            items.append({"kind": "mcp", "label": "/mcp:" + name, "sub": tools_s[:80], "icon": "devices", "value": name})
                except Exception:  # noqa: BLE001
                    pass
            self._slashesFetched.emit(rev, items[:16])
        self._bg(work)

    def _on_slashes(self, rev, items):
        if rev != self._slash_rev:
            return
        self._slashes = items or []
        self.slashesChanged.emit()

    def _resolve(self, entry, cloud_path, fallback=""):
        """A file already in the Drive: its id (nothing uploaded); if the cloud does not know it yet (not synced),
        the local copy is uploaded instead."""
        client = self._client()
        key = entry["key"]

        def work():
            file_id = ""
            try:
                file_id = client.file_id(cloud_path)["file_id"] if client else ""
            except Error:
                file_id = ""
            thumb = ""
            if file_id and entry["kind"] == "image" and not entry["thumb"]:
                thumb = self._thumb(client, file_id)
            if not file_id and fallback:
                self._upload(entry, fallback)
                return
            self._uploaded.emit(key, file_id, thumb)
        self._bg(work)

    @Slot("QVariantList")
    def addCloudFiles(self, rows):
        """Files picked in the Drive: [{path, name, size, file_id}]"""
        for row in rows:
            row = dict(row)
            entry = self._add(str(row.get("name") or ""), int(row.get("size") or 0), file_id="")
            if entry:
                if row.get("file_id"):
                    entry["file_id"] = str(row["file_id"])
                self._resolve(entry, str(row.get("path") or ""))

    @Slot(result=bool)
    def paste(self):
        """Ctrl+V: an image or files from the clipboard become attachments (True); text is left to the box (False)."""
        mime = QGuiApplication.clipboard().mimeData()
        if mime is None:
            return False
        if mime.hasUrls() and any(u.isLocalFile() for u in mime.urls()):
            self.addFiles([u for u in mime.urls() if u.isLocalFile()])
            return True
        if mime.hasImage():
            image = QGuiApplication.clipboard().image()
            if image.isNull():
                return False
            FILES.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y-%m-%d %H.%M.%S")
            path = FILES / f"Image {stamp}.png"
            image.save(str(path), "PNG")
            entry = self._add(path.name, path.stat().st_size, QUrl.fromLocalFile(str(path)).toString(), local=str(path))
            if entry:
                self._upload(entry, str(path))
            return True
        return False

    # ---- links (@) and actions (/) shown as badges above the text ---------------------------------------------
    @Property("QVariantList", notify=filesChanged)
    def links(self):
        """What @ linked (files, folders) and / chose (a skill, an MCP server): badges, joined to the message at sending."""
        return list(getattr(self, "_links", []))

    @Slot("QVariantMap")
    def addLink(self, item):
        links = list(getattr(self, "_links", []))
        item = {k: item.get(k) for k in ("kind", "label", "value", "icon")}
        if not any(l["kind"] == item["kind"] and l["value"] == item["value"] for l in links) and len(links) < 12:
            links.append(item)
        self._links = links
        self.filesChanged.emit()

    @Slot(int)
    def removeLink(self, index):
        links = list(getattr(self, "_links", []))
        if 0 <= index < len(links):
            del links[index]
            self._links = links
            self.filesChanged.emit()

    # ---- what Plume has open (a message, an event, a contact), joined to the next question ----------------------
    @Property("QVariantMap", notify=filesChanged)
    def about(self):
        """{kind, label, icon} of what goes with the next question, or {} (the text itself stays here)."""
        a = getattr(self, "_about", None) or {}
        return {k: a.get(k, "") for k in ("kind", "label", "icon")} if a else {}

    @Slot("QVariantMap")
    def setAbout(self, item):
        """Plume's panel: what is open beside it ({} : nothing). Its text leaves with the next question only."""
        item = dict(item or {})
        self._about = {k: str(item.get(k) or "") for k in ("kind", "label", "icon", "text")} if item.get("text") else None
        self.filesChanged.emit()

    def _with_links(self, text):
        """The message as the agent reads it: the chosen skills and MCP servers first, the linked files after,
        then what Plume has open (once: the next question asks again only if something else is chosen)."""
        about = getattr(self, "_about", None)
        if about:
            self._about = None
            self.filesChanged.emit()
            text = text + about_block(about["label"], about["text"])
        resume = getattr(self, "_resume", {}).pop(self._current, None)
        if resume:                       # a branch's first question: the conversation it came from, read by the agent
            text = text + about_block(resume["label"], resume["text"], limit=12000)
        links = list(getattr(self, "_links", []))
        if not links:
            return text
        head = "".join(f"[Skill: {l['value']}] " if l["kind"] == "skill" else f"[MCP: {l['value']}] " if l["kind"] == "mcp" else ""
                       for l in links)
        paths = [l["value"] for l in links if l["kind"] in ("local_file", "local_folder")]
        tail = ("\n\n" + self._t["links_joined"] + " " + ", ".join(f"`{p}`" for p in paths)) if paths else ""
        self._links = []
        self.filesChanged.emit()
        return head + text + tail

    @Slot(str)
    def removeFile(self, key):
        self._files = [f for f in self._files if f["key"] != key]
        self.filesChanged.emit()

    @Slot(str)
    def browse(self, path):
        """The Drive picker asks for a folder: folderListed answers (folders, and files Ornis can read)."""
        client = self._client()
        path = str(path or "/")

        def work():
            try:
                rows = client.folder(path) if client else []
                rows = [dict(r, kind=attachment_kind(r["name"])) for r in rows if r["folder"] or attachment_kind(r["name"])]
                self.folderListed.emit(path, rows, "")
            except Error as error:
                self.folderListed.emit(path, [], "offline" if error.code == 0 else "failed")
        self._bg(work)

    @staticmethod
    def _thumb(client, file_id):
        """A small copy of an image of the Drive, for the vignettes (cache, never the file itself)."""
        data = client.preview(file_id, 192)
        if not data:
            return ""
        FILES.mkdir(parents=True, exist_ok=True)
        target = FILES / f"thumb-{file_id}.png"
        target.write_bytes(data)
        return QUrl.fromLocalFile(str(target)).toString()

    def _describe(self, messages):
        """Names (and thumbnails of images) of the attachments in a conversation, fetched once, after it shows."""
        wanted = {a["file_id"]: a for m in messages or [] for a in m.get("attachments") or [] if a["file_id"] not in self._known}
        if not wanted:
            return
        client = self._client()
        for file_id in wanted:
            self._known[file_id] = {}

        def work():
            for file_id, a in wanted.items():
                try:
                    name = client.file_name(file_id)
                except Error:
                    name = ""
                thumb = ""
                if attachment_kind(name) == "image" or a.get("type") == "Image":
                    target = FILES / f"thumb-{file_id}.png"
                    thumb = QUrl.fromLocalFile(str(target)).toString() if target.exists() else self._thumb(client, file_id)
                self._described.emit(file_id, name, thumb)
        self._bg(work)

    @Slot(str)
    def viewImage(self, file_id):
        """A sent image in large, for the viewer: the file of this computer when it came from here, otherwise the
        cloud's preview (1 600 px, cached). imageReady answers."""
        known = self._known.get(file_id, {})
        if known.get("full"):
            self.imageReady.emit(file_id, known["full"])
            return
        target = FILES / f"large-{file_id}.png"
        if target.exists():
            self.imageReady.emit(file_id, QUrl.fromLocalFile(str(target)).toString())
            return
        client = self._client()

        def work():
            data = client.preview(file_id, 1600) if client else b""
            if data:
                FILES.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            self.imageReady.emit(file_id, QUrl.fromLocalFile(str(target)).toString() if data else "")
        self._bg(work)

    def _on_described(self, file_id, name, thumb):
        self._known[file_id] = dict(self._known.get(file_id) or {}, name=name, thumb=thumb)
        self.changed.emit()

    @Slot(str, str)
    def edit(self, message_id, text):
        """My question, changed: it and everything after it are replaced by the new question and its answer."""
        if self._busy or not (text or "").strip():
            return
        at = next((i for i, m in enumerate(self._messages) if m["id"] == message_id and m["role"] == "human"), -1)
        if at < 0:
            return
        drop = [m["id"] for m in self._messages[at:] if not str(m["id"]).startswith("local-")]
        answer = next((m for m in reversed(self._messages[at:]) if m["role"] == "assistant"), None)
        if answer and not any(m["role"] == "human" for m in self._messages[at + 1:]):   # only the answer to this question
            self._keep_version(sum(1 for m in self._messages[:at] if m["role"] == "human"), answer, self._messages[at]["content"])
        files = list(self._messages[at].get("attachments") or [])     # the files of the question stay with it
        self._messages = self._messages[:at]
        self._send(text, drop, files)

    def _send(self, text, drop, kept=None, work=False, mode=None):
        text = (text or "").strip()
        client = self._client()
        entries = list(self._files) if kept is None else []
        files = kept if kept is not None else [{"file_id": f["file_id"], "type": "Image" if f["kind"] == "image" else "File",
                                                 "name": f["name"], "thumb": f["thumb"]} for f in entries]
        if (not text and not files) or client is None or self._busy:
            return
        about = (getattr(self, "_about", None) or {}).get("label", "") if kept is None else ""
        sent = self._with_links(text) if kept is None else text
        if any(f["state"] == "failed" for f in entries):
            self.problem.emit(self._t["attach_not_ready"])
            return
        if entries:                     # sent now; uploads still running are waited for in the background
            self._inflight.update({f["key"]: f for f in entries if f["state"] == "uploading"})
            self._files = []
            self.filesChanged.emit()
        session_id = self._current
        if mode is None:
            mode = "plan" if not work and self.askMode == "plan" else ""
        project = self.project
        first = not any(m["role"] == "human" for m in self._messages)
        ephemeral = self.ephemeral and not work
        remember = not session_id and bool(self._app.pref("remember_new")) and not ephemeral
        if remember:
            self._remembered = True
        # shown at once; the cloud keeps it
        self._messages = self._messages + [{"id": f"local-{time.time()}", "role": "human", "content": text,
                                            "timestamp": int(time.time()), "sources": [], "attachments": files,
                                            "plan": mode == "plan", "compact": mode == "compact", "about": about}]
        self._pending = []
        self._start_busy()
        self._work_sent = session_id if work else None
        self.changed.emit()
        run = self._run
        if work:
            self._job_timer.start()

        def post():
            nonlocal session_id
            try:
                if not session_id:
                    session_id = client.new_session()
                    if remember:
                        try:
                            client.remember(session_id, True)
                        except Error:
                            pass
                    self._opened.emit("__new__", session_id, None, "")
                for message_id in drop:          # an edited question: it and what followed go
                    client.delete_message(session_id, message_id)
                deadline = time.time() + 300
                while any(f["state"] == "uploading" for f in entries) and time.time() < deadline:
                    time.sleep(0.2)
                if entries:
                    if any(f["state"] != "ready" for f in entries):
                        self._failed.emit(self._t["attach_not_ready"])
                        self._finished.emit(run, "failed", None)
                        return
                    files[:] = [dict(a, file_id=f["file_id"]) for a, f in zip(files, entries)]
                task = client.send(session_id, sent, first, files, work, mode, project, fast=self._app.pref("reasoning") == "fast" or not self.paid,
                                   ephemeral=ephemeral)
            except Error as error:
                self._finished.emit(run, "offline" if error.code == 0 else "failed", None)
                return
            self._wait(client, run, session_id, task)
        self._bg(post)

    def _unroll(self):
        """A few characters at each tick, more when far behind: caught up within half a second, never held back."""
        if not self._target.startswith(self._stream):
            self._stream = ""
        left = len(self._target) - len(self._stream)
        if left <= 0:
            self._reveal.stop()
            return
        self._stream = self._target[:len(self._stream) + max(3, left // 6)]
        # a long answer is laid out again at each step: fewer, bigger steps keep the window free
        size = len(self._stream)
        self._reveal.setInterval(30 if size < 3000 else 80 if size < 10000 else 160)
        self.streamChanged.emit()

    def _start_busy(self):
        self._reveal.stop()
        self._target = ""
        self._run += 1
        self._computer = None
        self._busy, self._stream, self._working, self._error, self._slow = True, "", [], "", False
        self._reasoning = ""
        self.streamChanged.emit()

    def _follow(self, session_id, task):
        client = self._client()
        if client is None:
            return
        self._start_busy()
        run = self._run
        self._bg(lambda: self._wait(client, run, session_id, task))

    def _wait(self, client, run, session_id, task):
        self._task = task
        result = client.wait(session_id, task, timeout=300, on_progress=lambda r: self._progress.emit(run, r),
                             asker=self._asker(session_id))
        if result["state"] == "done":
            try:
                messages = client.messages(session_id)
                status = client.check_session(session_id)
            except Error:
                messages, status = None, {"pending": result.get("pending") or [], "remembered": self._remembered}
            self._finished.emit(run, "", {"session": session_id, "messages": messages, "status": status, "result": result})
        else:
            error = str(result.get("error") or "")
            self._finished.emit(run, "limit" if "quota" in error.lower() else "failed", {"session": session_id})
        self._quota.emit(client.quota())

    def _on_progress(self, run, result):
        if run != self._run:
            return
        self._target = result.get("text") or ""
        self._reasoning = result.get("reasoning") or self._reasoning
        if self._target and not self._reveal.isActive():
            self._reveal.start()
        self._computer = result.get("computer")
        self._working = tools.families(result.get("sources"), self._t)
        self._live_steps = result.get("steps") or getattr(self, "_live_steps", [])
        self._slow = bool(result.get("slow"))
        self.streamChanged.emit()

    def _on_finished(self, run, problem, data):
        if run != self._run:
            return
        self._busy, self._task, self._computer = False, "", None
        self._reveal.stop()
        self._target = ""
        self._app.refreshUndoable()
        if problem:
            self._error = problem
            self.streamChanged.emit()
            self.refresh(False)
            return
        if data["session"] == self._current:
            if data["messages"] is not None:
                self._messages = data["messages"]
            else:
                self._messages = self._messages + [data["result"]["message"]]
            last = next((m for m in reversed(self._messages) if m["role"] == "assistant"), None)
            if last and getattr(self, "_live_steps", None):        # seen live: no need to ask the task again
                self._steps_of = dict(getattr(self, "_steps_of", {}), **{last["id"]: self._live_steps})
            self._pending = data["status"]["pending"]
        self._live_steps = []
        self._stream, self._working, self._error, self._reasoning = "", [], "", ""
        self._describe(self._messages)
        self._job_timer.stop()
        if self._work_sent or any(j["session"] == data["session"] for j in self._jobs):
            self._work_sent = None
            self.loadJobs()
        sources = [str(s.get("id") or "") for s in ((data.get("result") or {}).get("sources") or []) if isinstance(s, dict)]
        if any(t in {"add_task", "complete_task", "update_task", "delete_task"} for t in sources):
            try:
                system.launch("tasks", "--refresh")
            except Exception:
                pass
        if data["session"] == self._current and self._front:     # Ornis answered under the user's eyes
            self._mark(self._current)
        if data["session"] == self._current:
            self.loadContext()
        self.streamChanged.emit()
        self.changed.emit()
        self.replied.emit()
        self.refresh(False)            # the title the cloud just gave the conversation
        if data["session"] == self._current:
            QTimer.singleShot(0, self._send_later)

    # ---- Ornis asks to act on this computer: above the message box (as the Code mode), not in a window -------------
    def _asker(self, session_id):
        """ornis_consent.ask's way through this app: called from the worker thread that follows the answer, it shows
        the request (consentChanged) and waits for « Autoriser » / « Toujours » / « Refuser », or the end of the time."""
        def ask(request):
            done = threading.Event()
            box = {"token": uuid.uuid4().hex, "request": dict(request), "session": session_id, "done": done,
                   "until": time.time() + int(request.get("seconds") or 90)}
            self._consentAsked.emit(box)
            if not done.wait(int(request.get("seconds") or 90)):
                self._consentAsked.emit({"close": box["token"]})
                return {"answer": "deny", "timeout": True}
            return box.get("answer") or {"answer": "deny"}
        return ask

    def _on_consent(self, box):
        if box.get("close"):
            if self._consent and self._consent["token"] == box["close"]:
                self._consent = None
                self.consentChanged.emit()
            return
        if self._consent:                       # one at a time: an older one still open is refused
            self._answer_consent("deny", "")
        self._consent = box
        self.consentChanged.emit()
        if QGuiApplication.focusWindow() is None:
            try:
                self._app.notify(self._t["perm_notify_title"], str(box["request"].get("summary") or "").split("\n")[0],
                                 box["session"])
            except Exception:  # noqa: BLE001
                pass

    def _answer_consent(self, choice, command):
        box, self._consent = self._consent, None
        if not box:
            return
        answer = {"answer": choice if choice in ("allow", "always", "deny") else "deny"}
        if answer["answer"] != "deny" and box["request"].get("command") is not None:
            answer["command"] = str(command or "").strip()
            if not answer["command"]:
                answer = {"answer": "deny"}
        box["answer"] = answer
        box["done"].set()
        self.consentChanged.emit()

    @Slot(str, str)
    def answerConsent(self, choice, command=""):
        """The user's answer to what Ornis asked to do on this computer: allow, always (this rule) or deny."""
        self._answer_consent(choice, command)

    @Property("QVariantMap", notify=consentChanged)
    def consent(self):
        """What Ornis asks to do on this computer, as shown above the message box ({} when nothing waits):
        {title, level, summary, reason, command, cwd, preview, warnings: [{tone, text}], always, careful, verb, until}."""
        box = self._consent
        if not box:
            return {}
        r, t = box["request"], self._t
        action, command = str(r.get("action") or ""), r.get("command")
        level = r.get("level") if r.get("level") in ("info", "light", "change", "admin") else "change"
        title = (t["perm_title_command"] if command is not None else t["perm_title_install"] if action == "install_app"
                 else t["perm_title_remove"] if action == "remove_app"
                 else t["perm_title_files"] if action in ("move_files", "write_file", "edit_file", "trash_files", "create_folder")
                 else t["perm_title"])
        warnings = []
        if r.get("sensitive"):
            warnings.append({"tone": "danger", "text": t["perm_sensitive"]})
        if command is not None and re.search(r"(curl|wget)[^|]*\|\s*(sudo\s+)?(ba|z)?sh\b", str(command)):
            warnings.append({"tone": "danger", "text": t["perm_remote"]})
        if action == "install_app" and r.get("source") == "rpm":
            warnings.append({"tone": "info", "text": t["perm_rpm"]})
        if action == "power":
            warnings.append({"tone": "warn", "text": t["perm_power"]})
        always = ""
        if r.get("can_always"):
            always = t["perm_always"].replace("%1", str(r.get("rule") or "")) if command is not None else t["perm_always_action"]
        title_of = next((x["title"] for x in self._sessions if x["id"] == box["session"]), "") if box["session"] != self._current else ""
        return {"title": title, "level": t["perm_" + level], "summary": str(r.get("summary") or ""),
                "reason": str(r.get("reason") or ""), "command": "" if command is None else str(command),
                "hasCommand": command is not None, "cwd": str(r.get("cwd") or "~") if command is not None else "",
                "preview": str(r.get("preview") or "")[:20000], "warnings": warnings, "always": always,
                "noAlways": bool(r.get("sensitive")), "careful": level == "admin" or bool(r.get("sensitive")),
                "verb": t["perm_run"] if command is not None else t["perm_install"] if action == "install_app" else t["perm_allow"],
                "mode": t.get("perm_mode_" + str(r.get("mode") or "ask"), ""), "until": int(box["until"] * 1000),
                "elsewhere": title_of}

    @Slot("QVariantList")
    def answerQuestions(self, answers):
        """The answers to the questions of Ornis (ask_user: [{question, chosen: [labels], note}]), given back to the
        agent as a change of its call, then it goes on."""
        at = next((i for i, a in enumerate(self._pending) if a.get("name") == "ask_user"), -1)
        if at < 0:
            return
        clean = [{"question": str(a.get("question") or ""), "chosen": [str(c) for c in (a.get("chosen") or [])],
                  "note": str(a.get("note") or "").strip()} for a in (answers or []) if isinstance(a, dict)]
        self.confirmEdited([{"index": at, "args": {"answers": json.dumps({"answers": clean}, ensure_ascii=False)}}])

    @Slot("QVariantList")
    def confirmEdited(self, edits):
        """Yes, with fields changed in the card ([{index, args: {key: text}}]): left in the cloud, then confirmed."""
        client = self._client()
        if client is None or not self._current or self._busy:
            return
        edits = [{"index": int(e.get("index") or 0), "args": {str(k): str(v) for k, v in dict(e.get("args") or {}).items()}}
                 for e in (edits or []) if isinstance(e, dict) and e.get("args")]
        if not edits:
            self.confirm(True)
            return
        session_id = self._current
        self._pending = []
        self._start_busy()
        self.changed.emit()
        run = self._run

        def work():
            try:
                client.put_edits(session_id, edits)
                task = client.generate(session_id, confirm=True)
            except Error as error:
                self._finished.emit(run, "offline" if error.code == 0 else "failed", None)
                return
            self._wait(client, run, session_id, task)
        self._bg(work)

    @Slot(bool)
    def confirm(self, accept):
        """Yes: Ornis runs the actions it prepared. No: Ornis is told, and answers without them."""
        client = self._client()
        if client is None or not self._current or self._busy:
            return
        session_id = self._current
        self._pending = []
        self._start_busy()
        self.changed.emit()
        run = self._run

        def work():
            try:
                task = client.generate(session_id, confirm=accept)
            except Error as error:
                self._finished.emit(run, "offline" if error.code == 0 else "failed", None)
                return
            self._wait(client, run, session_id, task)
        self._bg(work)

    @Slot()
    def stop(self):
        client, task = self._client(), self._task
        if self._consent:
            self._answer_consent("deny", "")
        self._clear_later(give_back=True)      # stopped to change course: what was waiting comes back to be edited
        self._run += 1
        self._reveal.stop()
        self._target = ""
        self._busy, self._stream, self._working = False, "", []
        self.streamChanged.emit()
        if client and task:
            self._bg(lambda: client.cancel(task))

    @Slot()
    def retry(self):
        """After a failure: the reply again, for the last message."""
        client = self._client()
        if client is None or not self._current:
            return
        session_id = self._current
        self._start_busy()
        run = self._run

        def work():
            try:
                task = client.generate(session_id)
            except Error as error:
                self._finished.emit(run, "offline" if error.code == 0 else "failed", None)
                return
            self._wait(client, run, session_id, task)
        self._bg(work)

    @Slot()
    def regenerate(self):
        last = next((m for m in reversed(self._messages) if m["role"] == "assistant"), None)
        client = self._client()
        if client is None or last is None or self._busy:
            return
        session_id = self._current
        self._keep_version(sum(1 for m in self._messages if m["role"] == "human") - 1, last)
        self._messages = [m for m in self._messages if m is not last]
        self._start_busy()
        self.changed.emit()
        run = self._run

        def work():
            try:
                task = client.regenerate(session_id, last["id"])
            except Error as error:
                self._finished.emit(run, "offline" if error.code == 0 else "failed", None)
                return
            self._wait(client, run, session_id, task)
        self._bg(work)

    # ---- the conversation's settings ------------------------------------------------------------------------------
    @Slot(str, str)
    def rename(self, session_id, title):
        title = (title or "").strip()
        client = self._client()
        if not title or client is None:
            return
        for s in self._sessions:
            if s["id"] == session_id:
                s["title"] = title
        self.changed.emit()

        def work():
            try:
                client.rename(session_id, title)
            except Error:
                self._failed.emit(self._t["failed"])
        self._bg(work)

    @Slot(str)
    def remove(self, session_id):
        """Gone at once; the cloud forgets it after UNDO_MS, unless « Annuler »."""
        session = next((s for s in self._sessions if s["id"] == session_id), None)
        if session is None or self._client() is None:
            return
        self._doomed[session_id] = session
        self._sessions = [s for s in self._sessions if s["id"] != session_id]
        self._seen_messages.pop(session_id, None)
        if session_id == self._current:
            self._messages = []
            self.open("")
        self.changed.emit()
        self.removed.emit(session_id, session["title"] or self._t["untitled"])
        QTimer.singleShot(UNDO_MS, lambda: self._commit(session_id))

    @Slot(str)
    def undoRemove(self, session_id):
        session = self._doomed.pop(session_id, None)
        if session is None:
            return
        self._sessions = sorted(self._sessions + [session], key=lambda s: -s["timestamp"])
        self.changed.emit()

    def _commit(self, session_id, wait=False):
        client = self._client()
        if self._doomed.pop(session_id, None) is None or client is None:
            return
        self._pin(session_id, False)

        def work():
            try:
                client.delete(session_id)
                client.forget_work(session_id)
            except Error:
                self._failed.emit(self._t["delete_failed"])
                self.refresh(False)
        if wait:
            work()
        else:
            self._bg(work)

    @Slot()
    def flush(self):
        """Leaving: the deletions still waiting for their undo reach the cloud now."""
        for session_id in list(self._doomed):
            self._commit(session_id, wait=True)
        for session_id in list(self._app.pref("ephemeral") or []):
            self._forget(session_id, wait=True)

    @Slot()
    def removeAll(self):
        """Every conversation, in the cloud too (the scheduled tasks stay: they have their own page)."""
        client = self._client()
        if client is None or self._busy:
            return
        ids = [s["id"] for s in self._sessions] + list(self._doomed)
        self._sessions, self._doomed = [], {}
        self._seen_messages.clear()
        self._messages = []
        if self._app.pref("pinned"):
            self._push([], list(self._app.pref("pinned")))
        self.open("")
        self.changed.emit()
        self._app.toast.emit(self._t["deleted_all"])

        def work():
            failed = 0
            for session_id in ids:
                try:
                    client.delete(session_id)
                    client.forget_work(session_id)
                except Error:
                    failed += 1
            if failed:
                self._failed.emit(self._t["delete_failed"])
                self.refresh(False)
        self._bg(work)

    @Slot(str, bool)
    def pin(self, session_id, on):
        self._pin(session_id, on)
        self.changed.emit()

    def _pin(self, session_id, on):
        before = list(self._app.pref("pinned") or [])
        pins = [p for p in before if p != session_id]
        if on:
            pins.insert(0, session_id)
        if pins != before:
            self._push(pins, before)

    def _push(self, pins, before):
        """Shown at once; the cloud follows. Offline: sent at the next refresh. Refused: undone, with a message."""
        self._pin_rev += 1
        rev = self._pin_rev
        self._app.setPref("pinned", pins)
        client = self._client()
        if client is None:
            self._app.setPref("pins_dirty", True)
            return

        def work():
            try:
                self._pinned.emit(client.set_pins(pins), rev, "")
            except Error as error:
                self._pinned.emit(before, rev, "offline" if error.code == 0 else "refused")
        self._bg(work)

    def _on_pinned(self, pins, rev, problem):
        if rev != self._pin_rev:
            return
        if problem == "offline":
            self._app.setPref("pins_dirty", True)
            return
        self._app.setPref("pins_dirty", False)
        if problem == "refused":
            self._app.setPref("pinned", pins)
            self.changed.emit()
            self.problem.emit(self._t["pin_failed"])
            return
        if not self._app.pref("pins_synced"):
            # first time with the cloud's pins: the ones of this computer join them
            self._app.setPref("pins_synced", True)
            mine = [p for p in (self._app.pref("pinned") or []) if p not in pins]
            if mine:
                self._push(pins + mine, pins)
                self.changed.emit()
                return
        if pins != self._app.pref("pinned"):
            self._app.setPref("pinned", pins)
            self.changed.emit()

    # ---- « Bifurquer » : a new conversation from an answer, the original untouched (ornis/README.md) -------------
    @Slot(str)
    def fork(self, message_id):
        """The messages up to this answer copied into a new conversation (shown at once in the cloud's list too);
        its first question carries them for the agent, which keeps its own state per conversation."""
        source, message_id = self._current, str(message_id)
        at = next((i for i, m in enumerate(self._messages) if str(m["id"]) == message_id), None)
        client = self._client()
        if not source or at is None or client is None or self._busy:
            return
        title = self._t["fork_title"].replace("%1", self.title or self._t["untitled"])
        so_far = "\n\n".join((self._t["fork_you"] if m["role"] == "human" else "Ornis") + " : " + str(m.get("content") or "")
                              for m in self._messages[:at + 1] if m["role"] in ("human", "assistant"))
        self._app.toast.emit(self._t["fork_started"])

        def work():
            try:
                new = client.fork(source, message_id, title)
                self._forked.emit(new, title, so_far[-12000:], "")
            except Error as error:
                self._forked.emit("", title, "", "offline" if error.code == 0 else "failed")
        self._bg(work)

    def _on_forked(self, session_id, title, so_far, problem):
        if problem:
            self.problem.emit(self._t["fork_failed"])
            return
        if not hasattr(self, "_resume"):
            self._resume = {}
        self._resume[session_id] = {"label": self._t["fork_label"].replace("%1", title), "text": so_far}
        self._sessions = [{"id": session_id, "title": title, "timestamp": int(time.time()), "remembered": False,
                           "scheduled": False, "pending": False}] + self._sessions
        self.open(session_id)

    # ---- archived conversations (the same on every device, orneos app) and 👍 / 👎 ------------------------------
    @Slot(str, bool)
    def archive(self, session_id, on):
        """Out of the list (or back), at once; the cloud follows (offline: at the next refresh)."""
        before = list(self._app.pref("archived") or [])
        ids = [i for i in before if i != session_id] + ([session_id] if on else [])
        if ids == before:
            return
        self._app.setPref("archived", ids)
        self._archive_rev = rev = self.__dict__.get("_archive_rev", 0) + 1     # older reads of the cloud are out of date
        if on:
            self._pin(session_id, False)
        self.changed.emit()
        if on:
            self.archivedOne.emit(session_id, next((s["title"] for s in self._sessions if s["id"] == session_id), "") or self._t["untitled"])
        client = self._client()
        if client is None:
            self._app.setPref("archived_dirty", True)
            return

        def work():
            try:
                self._archivedFetched.emit(client.set_archived(ids), False, rev)
            except Error as error:
                self._archivedFetched.emit([], error.code == 0, rev)
        self._bg(work)

    def _on_archived(self, ids, offline, rev):
        if rev != self.__dict__.get("_archive_rev", 0):
            return
        if offline:
            self._app.setPref("archived_dirty", True)
            return
        self._app.setPref("archived_dirty", False)
        if list(ids) != list(self._app.pref("archived") or []):
            self._app.setPref("archived", list(ids))
            self.changed.emit()

    @Slot(str, int)
    def vote(self, message_id, value):
        """👍 (1) or 👎 (-1) on an answer, the same again to take it back; only the signal goes to the cloud."""
        message_id = str(message_id)
        if not message_id.isdigit():
            return
        votes = dict(self._app.pref("votes") or {})
        value = 0 if int(votes.get(message_id, 0)) == value else value
        self._vote_rev = self.__dict__.get("_vote_rev", 0) + 1    # a read of the cloud asked before this is out of date
        if value:
            votes[message_id] = value
        else:
            votes.pop(message_id, None)
        self._app.setPref("votes", dict(list(votes.items())[-300:]))
        self.changed.emit()
        if value == 1:
            self._app.toast.emit(self._t["vote_thanks"])     # a 👎 opens its « why ? » under the answer instead
        client = self._client()
        if client is None:
            return
        # one after the other, in the order given (two quick clicks must not reach the cloud the other way round)
        queue = self.__dict__.setdefault("_vote_queue", [])
        queue.append((message_id, value))
        if len(queue) > 1:
            return

        def work():
            while queue:
                mid, v = queue[0]
                try:
                    client.vote(mid, v)
                except Error:
                    pass                 # a signal only: not worth a message
                queue.pop(0)
        self._bg(work)

    @Slot(str, str, str, bool)
    def voteDetail(self, message_id, reason, comment, share):
        """Why a 👎: a reason, the user's words, and the question with this answer only if `share` (ticked)."""
        message_id = str(message_id)
        at = next((i for i, m in enumerate(self._messages) if str(m["id"]) == message_id), None)
        client = self._client()
        if at is None or client is None or not message_id.isdigit():
            return
        excerpt = ""
        if share:
            asked = next((m for m in reversed(self._messages[:at]) if m["role"] == "human"), None)
            excerpt = (self._t["fork_you"] + " : " + str(asked.get("content") or "") + "\n\n" if asked else "") \
                + "Ornis : " + str(self._messages[at].get("content") or "")
        self._app.toast.emit(self._t["vote_sent"])

        def work():
            try:
                client.vote(message_id, -1, reason, comment.strip(), excerpt[:3000])
            except Error:
                pass
        self._bg(work)

    def _on_votes(self, votes, rev):
        if rev != self.__dict__.get("_vote_rev", 0):
            return
        if dict(votes) != dict(self._app.pref("votes") or {}):
            self._app.setPref("votes", dict(votes))
            self.changed.emit()

    @Slot(str, str)
    def export(self, session_id, target):
        """The conversation in Markdown: copied ("copy"), as a note in Notes ("notes"), in a file ("file:<path>"), or
        shared ("share": a file in the Drive, its read-only public link copied)."""
        client = self._client()
        if client is None or not session_id:
            return
        title = next((s["title"] for s in self._sessions if s["id"] == session_id), "") or self._t["untitled"]
        if session_id == self._current and self._messages:
            self._on_transcript(target, title, self._markdown(title, self._messages))
            return

        def work():
            try:
                self._transcript.emit(target, title, self._markdown(title, client.messages(session_id)))
            except Error:
                self._failed.emit(self._t["failed_offline"])
        self._bg(work)

    def _markdown(self, title, messages, heading=True):
        me, ornis = self._app.profile.get("name") or self._t["me"], self._t["app_name"]
        out = [f"# {title}", ""] if heading else []
        for m in messages:
            who = me if m["role"] == "human" else ornis
            out += [f"**{who}** · {_when(m['timestamp'], self._app.lang)}", "", (m["content"] or "").strip(), ""]
        return "\n".join(out).rstrip() + "\n"

    def _on_transcript(self, target, title, text):
        if target == "copy":
            QGuiApplication.clipboard().setText(text)
            self.exported.emit(self._t["copied_chat"])
        elif target == "notes":
            # Notes titles the note after the file, then takes its text: no heading of our own
            EXPORTS.mkdir(parents=True, exist_ok=True)
            name = "".join(ch for ch in title if ch not in '/\\:*?"<>|').strip()[:80] or self._t["app_name"]
            path = EXPORTS / f"{name}.md"
            path.write_text(text.split("\n", 2)[2] if text.startswith("# ") else text)
            self._app.spawn(["orneos-notes", "--files", str(path)])
            self.exported.emit(self._t["sent_notes"])
        elif target == "share":
            client = self._client()
            if client is None:
                return
            name = "".join(ch for ch in title if ch not in '/\\:*?"<>|').strip()[:80] or self._t["app_name"]
            folder = self._t["share_folder"]

            def work():
                try:
                    client.make_folder(folder)
                    path = f"{folder}/{name} {time.strftime('%Y-%m-%d %H.%M')}.md"
                    client.put_file(path, text.encode())
                    self._shared.emit(client.public_link(path))
                except Error:
                    self._failed.emit(self._t["share_failed"])
            self._bg(work)
        elif target.startswith("file:"):
            path = target[5:]
            try:
                Path(path).write_text(text)
            except OSError:
                self._failed.emit(self._t["export_failed"])
                return
            self.exported.emit(self._t["exported"])

    @Slot(bool)
    def setRemembered(self, on):
        client, session_id = self._client(), self._current
        if client is None or not session_id:
            return
        self._remembered = bool(on)
        self.changed.emit()

        def work():
            try:
                client.remember(session_id, bool(on))
            except Error:
                self._failed.emit(self._t["failed"])
        self._bg(work)

    # ---- scheduled tasks ---------------------------------------------------------------------------------------
    @Slot()
    def loadScheduled(self):
        client = self._client()
        if client is None:
            return

        def work():
            try:
                rows = client.assignments()
            except Error:
                self._scheduled.emit(None)
                return
            try:
                sessions = client.task_sessions()
            except Error:
                sessions = []
            self._scheduled.emit((rows, sessions))
        self._bg(work)

    def _on_scheduled(self, result):
        if result is None:
            return
        rows, sessions = result
        self._task_sessions = sessions
        # each task, with its conversation (the last runs' answers) once it has run
        latest = {}
        for session in sorted(sessions, key=lambda x: x["timestamp"]):
            latest[session["assignment"]] = session["id"]
        out = []
        for r in rows:
            last = datetime.fromtimestamp(r["last_run_at"]).strftime("%d/%m %H:%M") if r["last_run_at"] else ""
            out.append(dict(r, last=self._t["scheduled_last"].replace("%1", last) if last else self._t["scheduled_never"],
                            repeat=_rrule_words(r["recurrence"], self._app.lang), session=latest.get(r["id"], "")))
        self._scheduled_rows = out
        self.scheduledChanged.emit()
        self.changed.emit()                # currentTask

    @Slot(str)
    def deleteScheduled(self, assignment_id):
        client = self._client()
        if client is None:
            return
        # the task and its conversation (its results): the assistant would leave the conversation behind, shown nowhere
        session = next((r["session"] for r in self._scheduled_rows if r["id"] == assignment_id), "")
        self._scheduled_rows = [r for r in self._scheduled_rows if r["id"] != assignment_id]
        self._unread.pop(session, None)
        if session and self._current == session:
            self._current, self._messages, self._pending = "", [], []
        self.scheduledChanged.emit()
        self.changed.emit()
        self.refreshBadge()
        self._app.toast.emit(self._t["scheduled_deleted"])

        def work():
            try:
                client.delete_assignment(assignment_id)
                if session:
                    client.delete(session)
            except Error:
                self._failed.emit(self._t["failed"])
                self.loadScheduled()
        self._bg(work)

    def _on_usage(self, info):
        self._usage_info = info
        self.usageChanged.emit()

    def _on_region(self, info):
        info = info if isinstance(info, dict) else {}
        error = info.pop("error", None)
        chosen = info.pop("_set", None)
        if info.get("regions"):
            self._region_info = info
            self.regionChanged.emit()
        if error:
            self._app.toast.emit(self._t.get("region_" + str(error), self._t["region_failed"]))
        elif chosen in ("eu", "global"):
            self._app.toast.emit(self._t["region_done_" + chosen])

    def _on_reset(self, result):
        result = result if isinstance(result, dict) else {"ok": False, "reason": "failed"}
        reason = str(result.get("reason") or "failed")
        key = "reset_done" if result.get("ok") else ("reset_" + reason if reason in ("early", "none", "empty") else "reset_failed")
        self._app.toast.emit(self._t.get(key, self._t["reset_failed"]).replace("%1", str(result.get("available") or 0)))
        self.resetSettled.emit()
        if result.get("ok"):
            self.loadUsage()

    def _on_quota(self, info):
        if info != self._quota_info:
            self._quota_info = info
            self.quotaChanged.emit()

    # the new conversation got its id in the cloud: it becomes the open one (its messages are already here)
    def _adopt(self, session_id):
        self._current = session_id
        self._app.setPref("session", session_id)
        if self._new_project and self.projects:
            self.projects.assign(session_id, self._new_project)
        self._new_project = ""
        if self._new_mode == "plan":
            self._app.setSessionMode(session_id, "plan")
        if self._ephemeral_next:
            self._app.setPref("ephemeral", list(self._app.pref("ephemeral") or []) + [session_id])
            self._ephemeral_next = False
        self._sessions = [{"id": session_id, "title": "", "timestamp": int(time.time()), "remembered": False,
                           "scheduled": False, "pending": False}] + self._sessions
        self.changed.emit()


def _rrule_words(rule, lang):
    """FREQ=DAILY;BYHOUR=8 → « Tous les jours à 8 h », roughly; the raw rule for anything rarer."""
    parts = dict(p.split("=", 1) for p in str(rule or "").split(";") if "=" in p)
    freq = parts.get("FREQ", "")
    words = {
        "fr": {"DAILY": "Tous les jours", "WEEKLY": "Toutes les semaines", "MONTHLY": "Tous les mois", "HOURLY": "Toutes les heures",
               "YEARLY": "Tous les ans", "": "Une fois", "at": " à %1 h"},
        "en": {"DAILY": "Every day", "WEEKLY": "Every week", "MONTHLY": "Every month", "HOURLY": "Every hour",
               "YEARLY": "Every year", "": "Once", "at": " at %1:00"},
        "de": {"DAILY": "Täglich", "WEEKLY": "Wöchentlich", "MONTHLY": "Monatlich", "HOURLY": "Stündlich",
               "YEARLY": "Jährlich", "": "Einmal", "at": " um %1 Uhr"},
    }.get(lang) or {}
    if freq not in words:
        return rule
    out = words[freq]
    if parts.get("BYHOUR", "").isdigit():
        out += words["at"].replace("%1", parts["BYHOUR"])
    return out
