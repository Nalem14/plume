"""Meet's conversations and chat (QML: `meet`), offline first.

The list and the last messages come from the copy on this computer (store.py) at once; the cloud fills in.
The open conversation listens for new messages with Talk's long poll (one request that waits up to 30 s);
the list is read again every 15 s while the window is in front, every 20 s behind it (incoming calls).

Everything the user does shows at once (« UI sans attente »): a message appears as soon as it is typed and
is sent behind (offline: it waits in the outbox), a reaction, an edit or a deletion change the bubble at
once; only a refusal of the cloud comes back, the change undone. Blocking calls run on a worker pool; their
results come back on the UI thread through a queued signal.
"""
import datetime
import json
import mimetypes
import re
import sqlite3
import threading
import time
import urllib.parse
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import (QAbstractListModel, QByteArray, QModelIndex, QObject, Property, Qt, QTimer, QUrl,
                            Signal, Slot)

import cloud
import system
from qmlvalue import js_property
from meet_core import api, richtext
from meet_core.presence import Presence
from meet_core.store import Store

GROUP_SECONDS = 300           # a message within 5 min of the one before, same author: no name, no avatar
# Talk's messages that only change another one (its `parent` is the new version): not shown themselves
UPDATES = {"message_deleted", "message_edited", "reaction", "reaction_deleted", "reaction_revoked", "poll_voted",
           "history_cleared", "thread_created", "thread_renamed"}
# system messages that make noise in a list: shown, but folded together in a row
QUIET = {"call_joined", "call_left", "user_added", "user_removed", "moderator_promoted", "moderator_demoted"}
REACTIONS = ["👍", "❤️", "😂", "😮", "😢", "🙏", "👏", "🎉"]


def in_thread(m):
    """An answer inside a thread (Talk 25): shown in the thread, not in the chat (its first message is)."""
    return bool(m.get("isThread")) and int(m.get("threadId") or 0) not in (0, int(m.get("id") or 0))


def giphy_id(url):
    """The id of a Giphy GIF from its page (giphy.com/gifs/<slug>-<id>, what Talk web sends) or its media link."""
    m = re.match(r"^https?://(?:www\.)?giphy\.com/gifs/(?:[^/?#]*-)?([A-Za-z0-9]+)/?$", url.strip())
    m = m or re.match(r"^https?://media\d*\.giphy\.com/media/([A-Za-z0-9]+)/[^/?#]+\.gif", url.strip())
    return m.group(1) if m else ""


def first_link(text, server=""):
    """The first web address of a message (its preview under the bubble), "" for none, a GIF or a conversation
    of our cloud (a link to a message: its quote says it already)."""
    text = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith(">"))   # a quote: not ours
    m = re.search(r"https?://[^\s<>()\[\]\"']+", text)
    url = m.group(0).rstrip(".,;:!?") if m else ""
    return "" if giphy_id(url) or (server and url.startswith(server + "/call/")) else url


class MessageModel(QAbstractListModel):
    """The messages of the open conversation, oldest first. Rows are dicts (see Library._row)."""
    KEYS = ["key", "id", "actorType", "actorId", "name", "self", "time", "html", "plain", "system", "deleted",
            "edited", "reactions", "parent", "files", "poll", "location", "grouped", "day", "pending", "failed",
            "read", "mentioned", "emojiOnly", "voice", "gif", "link", "replyable", "ref", "avatar", "silent", "kind",
            "thread", "threadTitle", "threadReplies", "pinned", "album", "inAlbum"]
    ROLES = {Qt.ItemDataRole.UserRole + i: k.encode() for i, k in enumerate(KEYS)}
    ALBUM_SECONDS = 120           # pictures sent one after the other (a selection, a paste of several)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []

    @staticmethod
    def _picture(row):
        """A message that is one picture and nothing else (no caption, answer, reaction or thread): it can join an
        album."""
        files = row.get("files") or []
        if len(files) != 1 or row.get("system") or row.get("deleted") or row.get("parent") or row.get("poll") \
                or row.get("reactions") or row.get("thread") or row.get("voice"):
            return False
        f = files[0]
        if not (f.get("preview") or f.get("local")) or not str(f.get("mime") or "").startswith("image/"):
            return False
        text = (row.get("plain") or "").strip()
        return text in ("", str(f.get("name") or "")) or text.strip("{} ") == "file"

    def _regroup(self):
        """Pictures in a row from the same person, a moment apart, shown together like an album (WhatsApp): the first
        message carries them all (album), the others are folded under it (inAlbum). Returns the rows that changed."""
        changed, i, n = [], 0, len(self.rows)
        while i < n:
            j = i + 1
            if self._picture(self.rows[i]):
                while j < n and self._picture(self.rows[j]) and not self.rows[j].get("day") \
                        and self.rows[j].get("actorId") == self.rows[i].get("actorId") \
                        and self.rows[j].get("actorType") == self.rows[i].get("actorType") \
                        and int(self.rows[j].get("time") or 0) - int(self.rows[j - 1].get("time") or 0) <= self.ALBUM_SECONDS:
                    j += 1
            run = self.rows[i:j]
            for k, row in enumerate(run):
                album = [dict(r["files"][0], message=r["id"], key=r["key"]) for r in run] if k == 0 and len(run) > 1 else []
                folded = k > 0
                if "album" not in row or row["album"] != album or row.get("inAlbum") != folded:
                    row["album"], row["inAlbum"] = album, folded
                    changed.append(i + k)
            i = j
        return changed

    def _changed(self, indices):
        for i in indices:
            idx = self.index(i, 0)
            self.dataChanged.emit(idx, idx)

    def roleNames(self):
        return {k: QByteArray(v) for k, v in self.ROLES.items()}

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self.rows)):
            return None
        key = self.ROLES.get(role)
        return self.rows[index.row()].get(key.decode()) if key else None

    def reset(self, rows):
        self.beginResetModel()
        self.rows = list(rows)
        self._regroup()
        self.endResetModel()

    def append(self, rows):
        if not rows:
            return
        start = len(self.rows)
        self.beginInsertRows(QModelIndex(), start, start + len(rows) - 1)
        self.rows.extend(rows)
        changed = self._regroup()
        self.endInsertRows()
        self._changed([i for i in changed if i < start])

    def prepend(self, rows):
        if not rows:
            return
        self.beginInsertRows(QModelIndex(), 0, len(rows) - 1)
        self.rows[0:0] = rows
        changed = self._regroup()
        self.endInsertRows()
        self._changed([i for i in changed if i >= len(rows)])

    def find(self, key):
        for i, row in enumerate(self.rows):
            if row["key"] == key:
                return i
        return -1

    def replace(self, i, row):
        self.rows[i] = row
        self._changed(sorted(set(self._regroup()) | {i}))

    def remove(self, i):
        self.beginRemoveRows(QModelIndex(), i, i)
        del self.rows[i]
        changed = self._regroup()
        self.endRemoveRows()
        self._changed(changed)

    @Slot(int, result="QVariantMap")
    def get(self, i):
        return self.rows[i] if 0 <= i < len(self.rows) else {}

    @Slot(str, result=int)
    def indexOf(self, key):
        return self.find(key)

    @Slot(int, result=int)
    def idAt(self, i):
        """The message id of a row (0 for a message still being sent): where the view stood, kept per conversation."""
        return int(self.rows[i].get("id") or 0) if 0 <= i < len(self.rows) else 0


class Library(QObject):
    changed = Signal()                # rooms, counts
    roomChanged = Signal()            # the open conversation (details, participants)
    stateChanged = Signal()
    peopleChanged = Signal()          # the search for people
    done = Signal(str, bool, str)     # what, ok, message
    myStatusChanged = Signal()        # our own status (what the others see)
    badge = Signal(int)               # conversations waiting for the user: the dock's count
    arrived = Signal("QVariantMap")   # a new message elsewhere than in the open conversation (notifications)
    ringing = Signal("QVariantMap")   # a call starts somewhere we are not: {token, name, video, avatar}
    ringStopped = Signal(str)         # that call ended (or was answered elsewhere)
    missedCall = Signal("QVariantMap")  # a call to us (one-to-one) that nobody answered: {token, name, avatar}
    olderLoaded = Signal(int)         # rows added at the top (the view keeps its place)
    jumped = Signal(int)              # a message to show (search, link): the view scrolls to it
    unreadAt = Signal(int)            # the conversation just opened: its first unread message (the view starts there)
    latestShown = Signal()            # back from a message far up: the newest messages are in the list again
    arrivedHere = Signal(int)         # messages of others in the open conversation (the view counts them when up)
    detachedChanged = Signal()
    reactorsRead = Signal(int, "QVariantMap")   # message id, {emoji: [names]} (who reacted, for the tooltip)
    pollChanged = Signal(str)
    searchDone = Signal("QVariantList")
    typingChanged = Signal()
    extrasChanged = Signal()          # pinned message, scheduled, bans, breakout rooms, threads of the open one
    homeChanged = Signal()            # upcoming meetings, reminders, calendars (the home of Meet)
    meetingReady = Signal(str)        # « Nouvelle réunion »: its conversation, to call at once
    settingsChanged = Signal()        # the bots of the open conversation (its settings window)
    sharedChanged = Signal()          # what was shared in the open conversation (the details' tab)
    tagsChanged = Signal()            # the account's tags of conversations
    emailsImported = Signal("QVariantMap")   # a CSV of addresses: counted (testRun) or invited
    _ran = Signal(object)

    def __init__(self, app):
        super().__init__()
        self.app = app
        self._t = app.t
        self.model = MessageModel(self)
        self._pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="meet")
        self._ran.connect(lambda job: job(), Qt.ConnectionType.QueuedConnection)
        self._talk = None
        self._store = None
        self._state = "loading"       # loading | ready | offline | signed_out
        self._rooms = []              # as Talk gives them
        self._filter = app.pref("filter")
        self._query = ""
        self._current = ""
        self._room = {}
        self._participants = []
        self._people = []
        self._people_query = ""
        self._gen = 0                 # the long poll of the open conversation (a new one stops the old)
        self._older_done = set()
        self._loading_older = False
        self._active = True
        self._last_refresh = 0
        self._notified = {}           # token -> last message id told in a notification
        self._polls = {}
        self._missed = {"from": 0, "count": 0}   # what was not read when the conversation opened (Ornis sums it up)
        self._first_unread = 0        # the first of them, for the line « Nouveaux messages » (0 = none)
        self._unread_pending = False  # still to find (the cached messages may not have them yet)
        self._detached = False        # the list shows messages far up (a jump): the newest are only in the store
        self._missed_told = {}        # token -> id of the last « call_missed » told
        self._reactors = {}           # (token, message id) -> {emoji: [names]}
        self._jump_after = 0          # a link to a message: shown once the conversation is open
        self._typing = {}
        self._extras = {"pinned": {}, "scheduled": [], "bans": [], "breakout": [], "threads": []}
        self._followed = []
        self._settings = {"bots": [], "loaded": False}
        self._shared = {"loaded": False, "kinds": []}
        self._shared_loading = ""
        self._tags = []
        self._home = {"events": [], "reminders": [], "calendars": []}
        self._last_home = 0
        self._last_tags = 0
        self.thread_model = MessageModel(self)
        self._counted = set()             # thread answers already counted on their first message
        # the newest id seen per conversation, updates included (a reaction is unread in a one-to-one
        # conversation for Talk but never a row here: read up to it, or the badge comes back for ever)
        self._seen = {}
        self._after_create = None         # what to do once a conversation asked for exists (call it)
        self._thread = {}
        self.in_call = ""             # the conversation of our call (Calls sets it): it does not ring
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._previews = {}           # link → its preview (None while asked)
        self._gifs_loading = set()
        # our presence for the others (the cloud's user status): online while a window is in front, else away
        self._heartbeat = QTimer(self)
        self._heartbeat.setInterval(5 * 60 * 1000)
        self._heartbeat.timeout.connect(self._beat)
        self._last_front = time.time()
        self._beaten = ""
        self._my_status = {"status": "", "icon": "", "message": "", "clearAt": 0}
        self._outbox_timer = QTimer(self)
        self._outbox_timer.setInterval(20000)
        self._outbox_timer.timeout.connect(self._flush_outbox)
        self._sending = set()             # conversations with a message on its way (one at a time: in order, never twice)
        # the signaling server: rings at once, who is writing (presence.py)
        self.presence = Presence(self)
        self.presence.roomsChanged.connect(self._pushed)
        self.presence.typingChanged.connect(self.typingChanged)
        app.accountChanged.connect(self._account_changed)
        self._account_changed()

    # ---- plumbing ----------------------------------------------------------------------------------------
    def _bg(self, work, then=None):
        def run():
            try:
                result = work()
            except Exception as error:  # noqa: BLE001 (a failure of the network or the cloud)
                result = error
            if then is not None:
                self._ran.emit(lambda: then(result))
        return self._pool.submit(run)

    def talk(self):
        return self._talk

    def _set_state(self, state):
        if state != self._state:
            self._state = state
            self.stateChanged.emit()

    def _account_changed(self):
        account = self.app.account()
        if self._talk is not None and account and account == (self._talk.server, self._talk.user, self._talk.password):
            return                       # the same account (its profile came): nothing to start again
        if self._current:                # another account: nothing of the previous one stays open
            self._close_room()
        self._gen += 1
        self._sending, self._notified, self._counted, self._seen = set(), {}, set(), {}
        if not account:
            self._talk, self._store = None, None
            self.presence.stop()
            self._rooms, self._current, self._room = [], "", {}
            self.model.reset([])
            self._set_state("signed_out")
            self.changed.emit()
            self.roomChanged.emit()
            return
        server, user, password = account
        self._talk = api.Talk(server, user, password)
        try:
            self._store = Store(user)
        except sqlite3.Error:
            self._store = Store(user, path=system.DATA / f"meet-{uuid.uuid4().hex[:6]}.db")
        self._rooms = self._store.rooms()
        self._set_state("ready" if self._rooms else "loading")
        self.changed.emit()
        self._publish_badge()
        self.refresh()
        def profile(info):
            if isinstance(info, dict) and info:
                self.app.set_profile({"name": str(info.get("displayname") or user), "email": str(info.get("email") or "")})
        self._bg(lambda: cloud.userinfo(server, user, password), profile)
        self._outbox_timer.start()
        self._heartbeat.start()
        self._beaten = ""
        self._beat()
        self.presence.start(account)

    def set_active(self, active):
        """The window is in front (15 s between two reads of the list) or not (20 s: a call must ring soon)."""
        was = self._active
        self._active = active
        if active or was:
            self._last_front = time.time()
        self._timer.start(15000 if active else 20000)
        if active and self._beaten != "online":
            self._beat()
        self.presence.follow(self._current if active else "")
        if active:
            if time.time() - self._last_refresh > 10:
                self.refresh()
            if self._current:
                self._mark_read(self._current)

    def _beat(self):
        """Our heartbeat: « online » if a window was in front in the last 5 minutes, else « away ». The cloud
        answers with our status (a status chosen by hand stays as it is)."""
        talk = self._talk
        if talk is None:
            return
        status = "online" if self._active or time.time() - self._last_front < 300 else "away"
        self._beaten = status
        self._bg(lambda: (talk.heartbeat(status), talk.my_status())[1], self._read_my_status)

    def _read_my_status(self, result):
        status, data = result if isinstance(result, tuple) else (0, None)
        if status == 200 and isinstance(data, dict):
            self._my_status = {"status": data.get("status") or "", "icon": data.get("icon") or "",
                               "message": data.get("message") or "", "clearAt": int(data.get("clearAt") or 0)}
            self.myStatusChanged.emit()

    @js_property(notify=myStatusChanged)
    def myStatus(self):
        return self._my_status

    @Slot(str)
    def setMyStatus(self, status):
        """Online, away, do not disturb, busy, invisible: shown at once, the cloud follows."""
        talk = self._talk
        if talk is None or status == self._my_status.get("status"):
            return
        before = dict(self._my_status)
        self._my_status = dict(self._my_status, status=status)
        self.myStatusChanged.emit()

        def then(result):
            if not (isinstance(result, tuple) and result[0] == 200):
                self._my_status = before
                self.myStatusChanged.emit()
                self.done.emit("status", False, self._t["status_failed"])
            else:
                self._read_my_status(result)
        self._bg(lambda: talk.set_status(status), then)

    @Slot(str, str, int)
    def setMyStatusMessage(self, icon, message, clear_after):
        """The message the others read under our name (clear_after: seconds, 0 = never; -1 = end of today)."""
        talk = self._talk
        if talk is None:
            return
        icon, message = icon.strip(), message.strip()[:80]
        if clear_after == -1:
            end = datetime.datetime.now().replace(hour=23, minute=59, second=59)
            clear_at = int(end.timestamp())
        else:
            clear_at = int(time.time()) + clear_after if clear_after > 0 else None
        before = dict(self._my_status)
        self._my_status = dict(self._my_status, icon=icon, message=message, clearAt=clear_at or 0)
        self.myStatusChanged.emit()

        def then(result):
            if not (isinstance(result, tuple) and result[0] == 200):
                self._my_status = before
                self.myStatusChanged.emit()
                self.done.emit("status", False, self._t["status_failed"])
        self._bg(lambda: talk.set_status_message(icon, message, clear_at), then)

    def _pushed(self):
        """The signaling server says a conversation changed: the list now (at most once a second)."""
        if time.time() - self._last_refresh > 1:
            self.refresh()
        else:
            QTimer.singleShot(1200, self.refresh)

    @js_property(notify=typingChanged)
    def typing(self):
        """Who writes in the open conversation (names, each once). A session without a name is never dropped:
        its participant's name, else the conversation's (one-to-one), else « Invité »."""
        me = self._talk.user if self._talk else ""
        known = {p.get("actorId"): p.get("displayName") or "" for p in self._participants if p.get("actorType") == "users"}
        names = []
        for name, user in self.presence.typers():
            if user and user == me:           # our other computer or phone
                continue
            name = name or known.get(user, "") or \
                (self._room.get("displayName", "") if self._room.get("type") == api.ONE_TO_ONE else "") or self._t["guest"]
            if name not in names:
                names.append(name)
        return names

    @Slot(bool)
    def setTyping(self, on):
        # « Ne pas montrer quand j'écris » of Talk (typing privacy 1): as Talk web, nothing is sent
        talk = self._talk
        if on and talk is not None and talk._features is not None and int(talk.config("chat", "typing-privacy", 0) or 0) == 1:
            return
        self.presence.typing(on)

    def shutdown(self):
        self._gen += 1
        self.presence.stop()
        self._timer.stop()
        self._pool.shutdown(wait=False, cancel_futures=True)

    # ---- state for the QML -------------------------------------------------------------------------------
    @Property(str, notify=stateChanged)
    def state(self):
        return self._state

    @Property(QObject, constant=True)
    def messages(self):
        return self.model

    @js_property(constant=True)
    def quickReactions(self):
        return REACTIONS

    @Property(str, notify=changed)
    def filter(self):
        return self._filter

    @Slot(str)
    def setFilter(self, value):
        self._filter = value
        self.app.setPref("filter", value)
        self.changed.emit()

    @Slot(str)
    def setQuery(self, text):
        self._query = text.strip().lower()
        self.changed.emit()

    @js_property(notify=changed)
    def rooms(self):
        rows = []
        for r in self._rooms:
            if r.get("type") == api.CHANGELOG and not r.get("unreadMessages"):
                continue
            archived = bool(r.get("isArchived"))
            f = self._filter
            if f == "archived" and not archived:
                continue
            if f != "archived" and archived and not self._query:
                continue
            if f == "unread" and not r.get("unreadMessages"):
                continue
            if f == "mentions" and not (r.get("unreadMention") or r.get("unreadMentionDirect")):
                continue
            if f == "favorites" and not r.get("isFavorite"):
                continue
            if f.startswith("tag:") and f[4:] not in [str(t) for t in r.get("tagIds") or []]:
                continue
            if self._query and self._query not in (r.get("displayName") or "").lower():
                continue
            rows.append(self._room_row(r))
        # favourites first, then by activity (Talk's order)
        rows.sort(key=lambda row: (not row["favorite"], -row["activity"]))
        return rows

    @js_property(notify=changed)
    def allRooms(self):
        """Every conversation one can write in, the latest first, whatever the filter (« Transférer »)."""
        rows = [self._room_row(r) for r in self._rooms if r.get("type") != api.CHANGELOG and not r.get("isArchived")
                and not r.get("readOnly")]
        rows.sort(key=lambda row: -row["activity"])
        return rows

    @Slot(int, str)
    def forward(self, message_id, token):
        """A message to another conversation: its text as the others read it, its files shared there again."""
        row = next((r for r in self.model.rows if r["id"] == message_id), None)
        talk = self._talk
        if row is None or talk is None or not token or not self._store:
            return
        files = [f for f in row["files"] if f.get("path")]
        names = {f["name"] for f in files}
        text = "" if files and row["plain"].strip() in names else row["plain"].strip()
        if text:
            self._store.queue(token, text)
            self._send_next(token)
        for f in files:
            self._bg(lambda f=f: talk.share_file(token, f["path"], meta={"referenceId": uuid.uuid4().hex}),
                     lambda result: None if isinstance(result, tuple) and result[0] in (200, 201)
                     else self.done.emit("forward", False, self._t["share_failed"]))
        name = next((r.get("displayName") for r in self._rooms if r.get("token") == token), "")
        self.done.emit("forward", True, self._t["forwarded"].replace("%1", name or ""))

    @js_property(notify=changed)
    def counts(self):
        unread = sum(1 for r in self._rooms if r.get("unreadMessages") and not r.get("isArchived"))
        mentions = sum(1 for r in self._rooms if (r.get("unreadMention") or r.get("unreadMentionDirect"))
                       and not r.get("isArchived"))
        archived = sum(1 for r in self._rooms if r.get("isArchived"))
        favorites = sum(1 for r in self._rooms if r.get("isFavorite") and not r.get("isArchived"))
        return {"unread": unread, "mentions": mentions, "archived": archived, "favorites": favorites,
                "all": len(self._rooms)}

    def _room_row(self, r):
        last = r.get("lastMessage") or {}
        preview = ""
        if isinstance(last, dict) and last:
            parts = richtext.render(last, self._talk.user if self._talk else "")
            text = parts["plain"]
            if parts["files"] and not text.strip("{} "):
                text = "📎 " + parts["files"][0]["name"]
            if last.get("systemMessage"):
                preview = text
            else:
                who = "" if r.get("type") == api.ONE_TO_ONE else (last.get("actorDisplayName") or "")
                if last.get("actorId") == (self._talk.user if self._talk else "") and last.get("actorType") == "users":
                    who = self._t["you"]
                preview = (who + " : " if who and self.app.lang == "fr" else (who + ": " if who else "")) + text
        status = r.get("status") or ""
        return {
            "token": r["token"], "name": r.get("displayName") or r.get("name") or "",
            "type": int(r.get("type") or 0), "unread": int(r.get("unreadMessages") or 0),
            "mention": bool(r.get("unreadMention") or r.get("unreadMentionDirect")),
            "favorite": bool(r.get("isFavorite")), "archived": bool(r.get("isArchived")),
            "activity": int(r.get("lastActivity") or 0), "preview": preview.replace("\n", " ")[:160],
            "hasCall": bool(r.get("hasCall")), "status": status if r.get("type") == api.ONE_TO_ONE else "",
            "statusMessage": r.get("statusMessage") or "", "statusIcon": r.get("statusIcon") or "",
            "avatar": f"image://meet/room/{r['token']}/{r.get('avatarVersion', '')}",
            "readOnly": bool(r.get("readOnly")), "notify": int(r.get("notificationLevel") or 0),
            "description": r.get("description") or "", "lobby": int(r.get("lobbyState") or 0),
            "public": int(r.get("type") or 0) == api.PUBLIC, "event": r.get("objectType") == "event",
            "muted": int(r.get("notificationLevel") or 0) == api.NOTIFY_NEVER,
            "breakout": r.get("objectType") == "room",
        }

    @Property(str, notify=roomChanged)
    def current(self):
        return self._current

    @js_property(notify=roomChanged)
    def room(self):
        r = self._room
        if not r:
            return {}
        row = self._room_row(r)
        ptype = int(r.get("participantType") or 0)
        perms = int(r.get("permissions") or 0)
        row.update({
            "moderator": ptype in (api.OWNER, api.MODERATOR, api.GUEST_MODERATOR),
            "owner": ptype == api.OWNER,
            "canCall": bool(r.get("canStartCall", True)) or bool(r.get("hasCall")),
            "canPost": not r.get("readOnly") and bool(perms & 128 or perms == 0),
            "canLeave": bool(r.get("canLeaveConversation", True)),
            "canDelete": bool(r.get("canDeleteConversation")),
            "hasPassword": bool(r.get("hasPassword")),
            "link": f"{self._talk.server}/call/{r['token']}" if self._talk else "",
            "participants": len(self._participants),
            "callStart": int(r.get("callStartTime") or 0),
            "partner": r.get("name") if int(r.get("type") or 0) == api.ONE_TO_ONE else "",
            "expiration": int(r.get("messageExpiration") or 0),
            "draft": self._store.draft(r["token"])[0] if self._store else "",
            "draftReply": self._store.draft(r["token"])[1] if self._store else 0,
            "pinnedId": int(r.get("lastPinnedId") or 0) if int(r.get("lastPinnedId") or 0) != int(r.get("hiddenPinnedId") or 0) else 0,
            "hasScheduled": bool(r.get("hasScheduledMessages")),
            "lobbyTimer": int(r.get("lobbyTimer") or 0),
            "breakoutMode": int(r.get("breakoutRoomMode") or 0),
            "breakoutStatus": int(r.get("breakoutRoomStatus") or 0),
            "parentToken": str(r.get("objectId") or "") if r.get("objectType") == "room" else "",
            "threads": bool(self._talk and self._talk.has("threads")),
            "canBan": bool(self._talk and self._talk.has("ban-v1")),
            # the settings of Talk web (ConversationSettings.qml), each one only when the cloud has it
            "notifyCalls": int(r.get("notificationCalls") or 0) == 1,
            "important": bool(r.get("isImportant")), "sensitive": bool(r.get("isSensitive")),
            "listable": int(r.get("listable") or 0),
            "mentionModerators": int(r.get("mentionPermissions") or 0) == 1,
            "defaultPermissions": int(r.get("defaultPermissions") or 0),
            "preserved": bool(int(r.get("attributes") or 0) & 2),
            "objectType": r.get("objectType") or "",
            "customAvatar": bool(r.get("isCustomAvatar")),
            "tagIds": [str(t) for t in r.get("tagIds") or []],
            "emailGuests": sum(1 for p in self._participants if p.get("actorType") == "emails"),
            "can": {k: bool(self._talk and self._talk.has(f)) for k, f in (
                ("important", "important-conversations"), ("sensitive", "sensitive-conversations"),
                ("tags", "conversation-tags"), ("listable", "listable-rooms"), ("mentions", "mention-permissions"),
                ("bots", "bots-v1"), ("preserve", "preserve-conversation"), ("owner", "promote-demote-owner"),
                ("csv", "email-csv-import"), ("clear", "clear-history"), ("permissions", "conversation-permissions"),
                ("avatar", "avatar"), ("calls", "notification-calls"))},
        })
        return row

    @js_property(notify=roomChanged)
    def participants(self):
        out = []
        for p in self._participants:
            in_call = int(p.get("inCall") or 0)
            ptype = int(p.get("participantType") or 0)
            actor_type = p.get("actorType") or ""
            out.append({
                "attendee": int(p.get("attendeeId") or 0), "actorType": actor_type, "actorId": p.get("actorId") or "",
                "name": p.get("displayName") or p.get("actorId") or "", "inCall": in_call,
                "moderator": ptype in (api.OWNER, api.MODERATOR, api.GUEST_MODERATOR), "owner": ptype == api.OWNER,
                "guest": ptype in (api.GUEST, api.GUEST_MODERATOR), "status": p.get("status") or "",
                "statusMessage": p.get("statusMessage") or "",
                "self": actor_type == "users" and self._talk is not None and p.get("actorId") == self._talk.user,
                "avatar": f"image://meet/user/{urllib.parse.quote(p.get('actorId') or '')}" if actor_type == "users" else "",
                "group": actor_type in ("groups", "circles"),
                "email": actor_type == "emails", "address": p.get("invitedActorId") or "",
                # what this person may do here: their own (custom, bit 1) or the conversation's
                "permissions": int(p.get("permissions") or 0),
                "custom": bool(int(p.get("attendeePermissions") or 0) & 1),
            })
        out.sort(key=lambda p: (not p["self"], not p["inCall"], not p["moderator"], p["name"].lower()))
        return out

    @js_property(notify=peopleChanged)
    def people(self):
        return self._people

    @Property(int, notify=roomChanged)
    def missed(self):
        """Messages that were not read when the conversation opened."""
        return self._missed["count"]

    @Slot(result="QVariantList")
    def summaryLines(self):
        """The messages to sum up: those not read when it opened, else the last 60. « Name (HH:MM): text »."""
        rows = [r for r in self.model.rows if r["id"] and not r["system"] and not r["deleted"]]
        if self._missed["count"] and self._missed["from"]:
            unread = [r for r in rows if r["id"] > self._missed["from"]]
            rows = unread or rows[-60:]
        else:
            rows = rows[-60:]
        return [f'{r["name"] or self._t["guest"]} ({self.app.clock(r["time"])}): '
                + (r["plain"] or ", ".join(f["name"] for f in r["files"])) for r in rows]

    @Slot(int, result="QVariantList")
    def recentLines(self, count):
        """The last messages for Ornis (minutes, tasks, replies, a question): « Name (HH:MM): text »."""
        rows = [r for r in self.model.rows if r["id"] and not r["system"] and not r["deleted"]][-count:]
        return [f'{r["name"] or self._t["guest"]} ({self.app.day(r["time"])} {self.app.clock(r["time"])}): '
                + (r["plain"] or ", ".join(f["name"] for f in r["files"])) for r in rows]

    # ---- the list of conversations -----------------------------------------------------------------------
    @Slot()
    def refresh(self):
        talk = self._talk
        if talk is None:
            return
        self._last_refresh = time.time()

        def work():
            talk.features()
            return talk.rooms()

        def then(result):
            if isinstance(result, Exception) or talk is not self._talk:
                return
            status, rooms = result
            if status == 200 and isinstance(rooms, list):
                self._got_rooms(rooms)
                self._set_state("ready")
                if time.time() - self._last_home > 300:
                    self.loadHome()
                if time.time() - self._last_tags > 300 and talk.has("conversation-tags"):
                    self.loadTags()
            elif status == 0:
                self._set_state("offline")
            elif status == 401:
                self._set_state("signed_out")
        self._bg(work, then)

    def _got_rooms(self, rooms):
        before = {r["token"]: r for r in self._rooms}
        rooms.sort(key=lambda r: -int(r.get("lastActivity") or 0))
        if rooms == self._rooms:
            return                      # the read every 15 s, most often: nothing changed, nothing to redraw
        self._rooms = rooms
        if self._store:
            self._store.put_rooms(rooms)
        for r in rooms:
            old = before.get(r["token"])
            self._ring_check(r, old)
            last = r.get("lastMessage") or {}
            # something new elsewhere: told to the agent (notifications), once per message
            if old and isinstance(last, dict) and last.get("id") and r.get("unreadMessages") and \
                    (r["token"] != self._current or not self._active) and \
                    int(last.get("id")) > int(self._notified.get(r["token"], (old.get("lastMessage") or {}).get("id") or 0)):
                self._notified[r["token"]] = int(last["id"])
                if last.get("actorId") != self._talk.user and not last.get("systemMessage"):
                    level = int(r.get("notificationLevel") or 0)
                    self.arrived.emit({"token": r["token"], "room": r.get("displayName") or "",
                                       "name": last.get("actorDisplayName") or "",
                                       # a sensitive conversation: never its text outside of it
                                       "text": "" if r.get("isSensitive") else
                                       richtext.render(last, self._talk.user)["plain"][:200],
                                       "oneToOne": r.get("type") == api.ONE_TO_ONE,
                                       "mention": bool(r.get("unreadMention") or r.get("unreadMentionDirect")),
                                       # the conversation's own level: « Tous les messages » tells every one
                                       "always": level == api.NOTIFY_ALWAYS,
                                       "important": bool(r.get("isImportant")),
                                       "muted": level == api.NOTIFY_NEVER})
            self._missed_check(r, old)
        if self._current:
            room = next((r for r in rooms if r["token"] == self._current), None)
            if room is None:
                self._close_room()
            else:
                self._room = room
                self._update_read()
                self.roomChanged.emit()
                if self._active and (room.get("unreadMessages") or room.get("unreadMention")):
                    self._mark_read(self._current)        # looked at: read here and on every device
        self.changed.emit()
        self._publish_badge()

    def _update_read(self):
        """Our messages the others have read since they were shown: « Lu » on them now."""
        last_common = int(self._room.get("lastCommonReadMessage") or 0) if self._room else 0
        for i, row in enumerate(self.model.rows):
            if row["self"] and row["id"] and not row["read"] and row["id"] <= last_common:
                row = dict(row)
                row["read"] = True
                self.model.replace(i, row)

    def _dnd(self):
        """« Ne pas déranger »: only the important conversations ring and notify (as in Talk)."""
        return self._my_status.get("status") == "dnd"

    @Property(bool, notify=myStatusChanged)
    def dnd(self):
        return self._dnd()

    def _missed_check(self, r, old):
        """Talk writes « call_missed » in a one-to-one conversation when a call to us ended unanswered."""
        token = r["token"]
        last = r.get("lastMessage") or {}
        if not isinstance(last, dict) or last.get("systemMessage") != "call_missed":
            return
        mid = int(last.get("id") or 0)
        if old is None:                   # the first read: what was before is history
            self._missed_told[token] = mid
            return
        if mid <= self._missed_told.get(token, 0):
            return
        self._missed_told[token] = mid
        if self._talk is None or (last.get("actorType") == "users" and last.get("actorId") == self._talk.user):
            return                        # our own call that the other missed
        if int(r.get("notificationLevel") or 0) == api.NOTIFY_NEVER or (self._dnd() and not r.get("isImportant")):
            return
        self.missedCall.emit({"token": token, "name": r.get("displayName") or "",
                              "avatar": f"image://meet/room/{token}/{r.get('avatarVersion', '')}",
                              "open": token == self._current and self._active})

    @Slot(str)
    def declineRing(self, token):
        """« Refuser »: the card, the notification and the ring go (the call goes on for the others)."""
        self.ringStopped.emit(token)

    def _ring_check(self, r, old):
        """A call that starts in a conversation that rings (one-to-one, or calls notified), not ours, recent."""
        token = r["token"]
        was = bool(old and old.get("hasCall"))
        now = bool(r.get("hasCall"))
        if was and not now:
            self.ringStopped.emit(token)
            return
        if not now or was or old is None or self.in_call == token:
            return
        if int(r.get("notificationLevel") or 0) == api.NOTIFY_NEVER or r.get("isArchived"):
            return
        if self._dnd() and not r.get("isImportant"):
            return
        if r.get("type") != api.ONE_TO_ONE and not int(r.get("notificationCalls", 1) or 0):
            return
        if int(r.get("participantFlags") or 0) & api.IN_CALL:     # already in it (another device: no ring here)
            return
        start = int(r.get("callStartTime") or 0)
        if start and time.time() - start > 90:
            return
        last = r.get("lastMessage") or {}
        if isinstance(last, dict) and last.get("systemMessage") == "call_started" and \
                last.get("actorId") == (self._talk.user if self._talk else "") and last.get("actorType") == "users":
            return
        self.ringing.emit({"token": token, "name": r.get("displayName") or "",
                           "video": bool(int(r.get("callFlag") or 0) & api.WITH_VIDEO),
                           "avatar": f"image://meet/room/{token}/{r.get('avatarVersion', '')}",
                           "oneToOne": r.get("type") == api.ONE_TO_ONE, "elsewhere": bool(self.in_call)})

    def _publish_badge(self):
        count = 0
        for r in self._rooms:
            if r.get("isArchived") or int(r.get("notificationLevel") or 0) == api.NOTIFY_NEVER:
                continue
            if r.get("type") == api.ONE_TO_ONE and r.get("unreadMessages"):
                count += 1
            elif r.get("unreadMention") or r.get("unreadMentionDirect"):
                count += 1
        self.badge.emit(count)

    # ---- one conversation --------------------------------------------------------------------------------
    @Slot(str, int)
    def openAt(self, token, message_id):
        """A link to one message: the conversation opens on it (not on the newest, nor on the unread)."""
        if token == self._current:
            if message_id:
                self.jumpTo(message_id)
            return
        self._jump_after = int(message_id or 0)
        self.open(token)

    @Slot(str)
    def open(self, token):
        if not token or self._talk is None:
            return
        if token == self._current:
            self.roomChanged.emit()
            return
        self._gen += 1
        gen = self._gen
        self._current = token
        if self._active:
            self.presence.follow(token)
        self._room = next((r for r in self._rooms if r["token"] == token), None) or (self._store.room(token) or {"token": token})
        self._missed = {"from": int(self._room.get("lastReadMessage") or 0), "count": int(self._room.get("unreadMessages") or 0)}
        self._first_unread = 0
        self._unread_pending = self._missed["count"] > 0 and self._missed["from"] > 0 and not self._jump_after
        self._set_detached(False)
        self._participants = []
        self._settings = {"bots": [], "loaded": False}
        self._shared = {"loaded": False, "kinds": []}
        self.settingsChanged.emit()
        self.sharedChanged.emit()
        self._loading_older = False
        self._extras = {"pinned": {}, "scheduled": [], "bans": [], "breakout": [], "threads": []}
        self.extrasChanged.emit()
        cached = self._store.messages(token) if self._store else []
        self.model.reset(self._rows(cached, pending=self._store.outbox(token) if self._store else []))
        self.roomChanged.emit()
        self._find_first_unread(False)
        talk = self._talk

        def work():
            status, room = talk.room(token)
            status_m, messages = talk.messages(token, 0, future=False, limit=100)
            status_p, participants = talk.participants(token)
            return status, room, status_m, messages, status_p, participants

        def then(result):
            if isinstance(result, Exception) or gen != self._gen:
                return
            status, room, status_m, messages, status_p, participants = result
            if status == 404:
                self.done.emit("open", False, self._t["room_gone"])
                self._close_room()
                return
            if status == 200 and isinstance(room, dict):
                self._room = room
                if self._store:
                    self._store.put_room(room)
            if status_p == 200 and isinstance(participants, list):
                self._participants = participants
            if status_m == 200:
                # answers that came with their thread's first message: already in its count
                self._counted.update(int(m["id"]) for m in messages if in_thread(m))
                self._merge(token, messages)
            self.roomChanged.emit()
            if self._jump_after:
                jump, self._jump_after = self._jump_after, 0
                self._unread_pending = False
                self.jumpTo(jump)
            else:
                self._find_first_unread(True)
            if self._active:              # opened behind (a link, the agent): not read until seen
                self._mark_read(token)
            self._poll(token, gen)
            self._load_extras(token)
        self._bg(work, then)

    @Slot()
    def close(self):
        self._close_room()

    def _find_first_unread(self, final):
        """The first message of the others after the last one read when the conversation opened: the line
        « Nouveaux messages » goes above it and the view starts there. The cache may not have it yet (final:
        the cloud's messages are in)."""
        if not self._unread_pending:
            return
        last_read = self._missed["from"]
        for row in self.model.rows:
            if row["id"] and row["id"] > last_read and not row["self"] and not row["system"]:
                self._first_unread = row["id"]
                self._unread_pending = False
                self.unreadAt.emit(row["id"])
                return
        if final:
            self._unread_pending = False

    @Property(int, notify=unreadAt)
    def firstUnread(self):
        return self._first_unread

    @Property(bool, notify=detachedChanged)
    def detached(self):
        """The list shows messages far up (a search, a quote): « Aller aux derniers messages » loads them."""
        return self._detached

    def _set_detached(self, on):
        if on != self._detached:
            self._detached = on
            self.detachedChanged.emit()

    @Slot()
    def toLatest(self):
        """Back to the newest messages after a jump far up: the list from the store (the newest are there)."""
        if not self._detached or not self._current:
            self.latestShown.emit()
            return
        token = self._current
        self._set_detached(False)
        cached = self._store.messages(token) if self._store else []
        self.model.reset(self._rows(cached, pending=self._store.outbox(token) if self._store else []))
        self._older_done.discard(token)
        self.latestShown.emit()

    @Slot(int)
    def loadReactors(self, message_id):
        """Who reacted to a message (the tooltip of its reactions): asked once, then kept until it changes."""
        token, talk = self._current, self._talk
        if talk is None or not token or not message_id:
            return
        key = (token, int(message_id))
        if key in self._reactors:
            self.reactorsRead.emit(int(message_id), self._reactors[key])
            return

        def then(result):
            status, data = result if isinstance(result, tuple) else (0, None)
            if status != 200 or not isinstance(data, dict):
                return
            me = talk.user
            names = {}
            for emoji, actors in data.items():
                if isinstance(actors, list):
                    names[emoji] = [self._t["you"] if a.get("actorType") == "users" and a.get("actorId") == me
                                    else (a.get("actorDisplayName") or self._t["guest"]) for a in actors if isinstance(a, dict)]
            self._reactors[key] = names
            if token == self._current:
                self.reactorsRead.emit(int(message_id), names)
        self._bg(lambda: talk.reactions(token, message_id), then)

    def _close_room(self):
        self._gen += 1
        self._jump_after = 0
        self.presence.follow("")
        self._extras = {"pinned": {}, "scheduled": [], "bans": [], "breakout": [], "threads": []}
        self.extrasChanged.emit()
        self._current = ""
        self._room = {}
        self._participants = []
        self.model.reset([])
        self.roomChanged.emit()

    def _poll(self, token, gen):
        """The long poll of the open conversation, on its own thread (it waits up to 30 s)."""
        talk = self._talk

        def loop():
            last = max(self._store.last_id(token) if self._store else 0, self._seen.get(token, 0))
            while gen == self._gen and talk is self._talk:
                status, messages = talk.messages(token, last, future=True, timeout=30)
                if gen != self._gen:
                    return
                if status == 200 and messages:
                    last = max([last] + [int(m.get("id") or 0) for m in messages])
                    self._ran.emit(lambda m=messages: self._arrived(token, gen, m))
                elif status in (304, 200):
                    continue
                elif status == 404 or status == 412:
                    self._ran.emit(self.refresh)
                    return
                else:                               # offline, or the cloud is busy: again in a while
                    time.sleep(5)
        threading.Thread(target=loop, daemon=True, name="meet-poll").start()

    def _arrived(self, token, gen, messages):
        if gen != self._gen or token != self._current:
            return
        cleared = [int(m.get("id") or 0) for m in messages if m.get("systemMessage") == "history_cleared"]
        if cleared:
            self._history_cleared(token, max(cleared))
        self._merge(token, messages)
        if self._active:
            me = self._talk.user if self._talk else ""
            # a reaction of the other counts as unread in a one-to-one conversation (Talk): read too
            self._mark_read(token, force=any(not (m.get("actorType") == "users" and m.get("actorId") == me)
                                             and (m.get("systemMessage") not in UPDATES
                                                  or (m.get("systemMessage") == "reaction"
                                                      and self._room.get("type") == api.ONE_TO_ONE))
                                             for m in messages))
        # the list shows the last message at once (the next read of the list confirms)
        shown = [m for m in messages if m.get("systemMessage") not in UPDATES]
        if shown:
            for r in self._rooms:
                if r["token"] == token:
                    r["lastMessage"] = shown[-1]
                    r["lastActivity"] = int(shown[-1].get("timestamp") or time.time())
            self._rooms.sort(key=lambda r: -int(r.get("lastActivity") or 0))
            self.changed.emit()
        if any(m.get("systemMessage") in ("call_started", "call_ended", "call_ended_everyone", "user_added",
                                         "user_removed", "moderator_promoted", "moderator_demoted",
                                         "conversation_renamed", "description_set", "lobby_timer_reached",
                                         "message_pinned", "message_unpinned", "breakout_rooms_started",
                                         "breakout_rooms_stopped", "thread_created", "scheduled_message_sent",
                                         "owner_promoted", "owner_demoted", "avatar_set", "avatar_removed",
                                         "listable_none", "listable_users", "listable_all", "guests_allowed",
                                         "guests_disallowed", "password_set", "password_removed", "read_only",
                                         "read_only_off", "lobby_none", "lobby_non_moderators", "message_expiration_enabled",
                                         "message_expiration_disabled", "mention_permissions_moderators",
                                         "mention_permissions_everyone")
               for m in messages):
            self._reload_room(token)

    def _reload_room(self, token):
        talk = self._talk

        def then(result):
            if isinstance(result, Exception) or token != self._current:
                return
            (status, room), (status_p, participants) = result
            if status == 200 and isinstance(room, dict):
                self._room = room
            if status_p == 200 and isinstance(participants, list):
                self._participants = participants
            self.roomChanged.emit()
            self._load_extras(token)
        self._bg(lambda: (talk.room(token), talk.participants(token)), then)

    def _merge(self, token, messages):
        """New messages and updates of older ones, into the store and the model."""
        if not messages:
            return
        self._seen[token] = max([self._seen.get(token, 0)] + [int(m.get("id") or 0) for m in messages])
        updates = []
        new = []
        for m in messages:
            if m.get("systemMessage") in UPDATES:
                parent = m.get("parent")
                if isinstance(parent, dict) and parent.get("id"):
                    updates.append(parent)
            else:
                new.append(m)
        if self._store:
            self._store.put_messages(token, new + updates)
        if token != self._current:
            return
        for p in updates:
            self._reactors.pop((token, int(p["id"])), None)
            i = self.model.find(str(p["id"]))
            if i >= 0:
                self.model.replace(i, self._row(p, self.model.rows[i - 1] if i > 0 else None))
        known = {row["id"] for row in self.model.rows if row["id"]}
        for m in new:
            if in_thread(m) and int(m["id"]) not in self._counted:
                self._counted.add(int(m["id"]))
                i = self.model.find(str(int(m["threadId"])))
                if i >= 0:
                    row = dict(self.model.rows[i])
                    row["threadReplies"] = row["threadReplies"] + 1
                    self.model.replace(i, row)
            # an answer in the thread open beside the chat: there at once (ours is there already)
            if in_thread(m) and self._thread.get("token") == token and int(m["threadId"]) == self._thread.get("id") \
                    and self.thread_model.find(str(m["id"])) < 0 \
                    and not (m.get("referenceId") and self.thread_model.find("ref:" + m["referenceId"]) >= 0):
                rows = self.thread_model.rows
                self.thread_model.append([self._row(m, rows[-1] if rows else None)])
        new = [m for m in new if not in_thread(m)]
        fresh = [m for m in sorted(new, key=lambda m: int(m["id"])) if int(m["id"]) not in known]
        if not fresh:
            return
        me_ = self._talk.user if self._talk else ""
        others = sum(1 for m in fresh if not m.get("systemMessage") and not (m.get("actorType") == "users" and m.get("actorId") == me_))
        if self._detached:                # far up in the past: the newest wait in the store (toLatest)
            if others:
                self.arrivedHere.emit(others)
            return
        if others:
            self.arrivedHere.emit(others)
        # a pending message the cloud now has: the cloud's copy takes its place
        me = self._talk.user if self._talk else ""
        for m in fresh:
            ref = m.get("referenceId")
            if ref:
                i = self.model.find("ref:" + ref)
                if i >= 0:
                    self.model.remove(i)
            # one of our files: the oldest file on its way (Talk keeps no referenceId on a share)
            params = m.get("messageParameters")
            if m.get("actorId") == me and isinstance(params, dict) and any(
                    isinstance(p, dict) and p.get("type") == "file" for p in params.values()):
                i = next((n for n, row in enumerate(self.model.rows) if row.get("upload")), -1)
                if i >= 0:
                    self.model.remove(i)
        # older than what is shown (the first load): the whole list again
        first_shown = next((row["id"] for row in self.model.rows if row["id"]), 0)
        if first_shown and int(fresh[0]["id"]) < first_shown:
            cached = self._store.messages(token) if self._store else fresh
            self.model.reset(self._rows(cached, pending=self._store.outbox(token) if self._store else []))
            self._set_detached(False)
            return
        pending = [row for row in self.model.rows if row["pending"] or row["failed"]]
        for row in pending:
            self.model.remove(self.model.find(row["key"]))
        previous = self.model.rows[-1] if self.model.rows else None
        rows = []
        for m in fresh:
            row = self._row(m, previous)
            rows.append(row)
            previous = row
        self.model.append(rows)
        self.model.append(pending)

    @Slot()
    def loadOlder(self):
        token = self._current
        if not token or self._loading_older or token in self._older_done or self._talk is None:
            return
        first = next((row["id"] for row in self.model.rows if row["id"]), 0)
        if not first:
            return
        self._loading_older = True
        gen = self._gen
        talk = self._talk

        def then(result):
            self._loading_older = False
            if isinstance(result, Exception) or gen != self._gen:
                return
            status, messages = result
            if not isinstance(messages, list):
                messages = []
            shown = [m for m in messages if m.get("systemMessage") not in UPDATES and not in_thread(m) and int(m["id"]) < first]
            if status != 200 or not shown:
                if status in (200, 304):
                    self._older_done.add(token)
                return
            shown.sort(key=lambda m: int(m["id"]))
            rows, previous = [], None
            for m in shown:
                row = self._row(m, previous)
                rows.append(row)
                previous = row
            # the first row shown before may lose its name / day now that one comes before it
            if self.model.rows:
                self.model.replace(0, self._row(self._raw(self.model.rows[0]), previous))
            self.model.prepend(rows)
            self.olderLoaded.emit(len(rows))
        self._bg(lambda: talk.messages(token, first, future=False, limit=100), then)

    def _raw(self, row):
        return row.get("_raw") or {}

    def _rows(self, messages, pending=()):
        rows, previous = [], None
        for m in messages:
            if m.get("systemMessage") in UPDATES or in_thread(m):
                continue
            row = self._row(m, previous)
            rows.append(row)
            previous = row
        for p in pending:
            row = self._pending_row(p, previous)
            rows.append(row)
            previous = row
        return rows

    def _row(self, m, previous):
        me = self._talk.user if self._talk else ""
        own = m.get("actorType") == "users" and m.get("actorId") == me
        system_message = bool(m.get("systemMessage"))
        # our bubble is Klein: its links and mentions in white (in Klein they would not be read)
        parts = richtext.render(m, me, "#FFFFFF", "#FFFFFF") if own else richtext.render(m, me)
        ts = int(m.get("timestamp") or 0)
        day = ""
        if previous is None or time.localtime(previous.get("time") or 0)[:3] != time.localtime(ts)[:3]:
            day = self.app.day(ts) if ts else ""
        grouped = bool(previous) and not day and not system_message and not previous.get("system") and \
            previous.get("actorId") == m.get("actorId") and previous.get("actorType") == m.get("actorType") and \
            ts - int(previous.get("time") or 0) < GROUP_SECONDS
        reactions = []
        mine = set(m.get("reactionsSelf") or [])
        for emoji, count in (m.get("reactions") or {}).items() if isinstance(m.get("reactions"), dict) else []:
            reactions.append({"emoji": emoji, "count": int(count), "self": emoji in mine})
        parent = m.get("parent") if isinstance(m.get("parent"), dict) else None
        parent_row = None
        if parent and parent.get("id"):
            pp = richtext.render(parent, me)
            parent_row = {"id": int(parent["id"]), "name": parent.get("actorDisplayName") or "",
                          "text": (pp["plain"] or (pp["files"][0]["name"] if pp["files"] else ""))[:240],
                          "deleted": parent.get("messageType") == "comment_deleted"}
        last_common = int(self._room.get("lastCommonReadMessage") or 0) if self._room else 0
        actor_type = m.get("actorType") or ""
        row = {
            "key": str(m["id"]), "id": int(m["id"]), "actorType": actor_type, "actorId": m.get("actorId") or "",
            "name": m.get("actorDisplayName") or (self._t["guest"] if actor_type == "guests" else ""),
            "self": own, "time": ts, "html": parts["html"], "plain": parts["plain"], "system": system_message,
            "kind": m.get("systemMessage") or m.get("messageType") or "comment",
            "deleted": m.get("messageType") == "comment_deleted",
            "edited": bool(m.get("lastEditTimestamp")), "reactions": reactions, "parent": parent_row,
            "files": parts["files"], "poll": parts["poll"], "location": parts["location"], "grouped": grouped,
            "day": day, "pending": False, "failed": False, "read": own and int(m["id"]) <= last_common,
            "mentioned": parts["mentioned"] and not own, "emojiOnly": parts["emojiOnly"],
            # Talk takes a voice message in MP3 or WAV only: any other sound (ours of before, in .m4a) plays here too
            "voice": m.get("messageType") == "voice-message" or (len(parts["files"]) == 1 and parts["plain"].strip() ==
                     parts["files"][0]["name"] and str(parts["files"][0]["mime"]).startswith("audio/")),
            "gif": giphy_id(parts["plain"]) if not parts["files"] else "",
            "link": first_link(parts["plain"], self._talk.server if self._talk else "") if not parts["files"] and not system_message else "",
            "replyable": bool(m.get("isReplyable")),
            "ref": m.get("referenceId") or "", "silent": bool(m.get("silent")),
            "avatar": f"image://meet/user/{urllib.parse.quote(m.get('actorId') or '')}" if actor_type == "users" else "",
            "thread": int(m.get("threadId") or 0) if m.get("isThread") else 0,
            "threadTitle": m.get("threadTitle") or "", "threadReplies": int(m.get("threadReplies") or 0),
            "pinned": bool(self._room) and int(m["id"] or 0) == int(self._room.get("lastPinnedId") or -1),
            "_raw": m,
        }
        return row

    def _pending_row(self, p, previous):
        me = self._talk.user if self._talk else ""
        fake = {"id": 0, "actorType": "users", "actorId": me, "actorDisplayName": self.app.profile.get("name", me),
                "timestamp": p.get("at") or int(time.time()), "message": p.get("message", ""), "messageParameters": {},
                "messageType": "comment", "isReplyable": False, "referenceId": p["ref"], "markdown": True}
        if p.get("replyTo"):
            parent = next((r["_raw"] for r in self.model.rows if r["id"] == p["replyTo"]), None)
            if parent:
                fake["parent"] = parent
        row = self._row(fake, previous)
        row.update({"key": "ref:" + p["ref"], "id": 0, "pending": not p.get("failed"), "failed": bool(p.get("failed"))})
        return row

    def _mark_read(self, token, force=False):
        """force: messages just came while the conversation is looked at (the room's counts do not know them)."""
        r = self._room if self._room.get("token") == token else None
        if not r or not (force or r.get("unreadMessages") or r.get("unreadMention")):
            return
        # thread answers are not in the chat but count as unread: the last one known, wherever it is shown
        last = max([row["id"] for row in self.model.rows if row["id"]]
                   + [self._store.last_id(token) if self._store else 0, self._seen.get(token, 0),
                      int((r.get("lastMessage") or {}).get("id") or 0) if isinstance(r.get("lastMessage"), dict) else 0])
        r["unreadMessages"], r["unreadMention"], r["unreadMentionDirect"] = 0, False, False
        for room in self._rooms:
            if room["token"] == token:
                room.update({"unreadMessages": 0, "unreadMention": False, "unreadMentionDirect": False})
        self.changed.emit()
        self._publish_badge()
        talk = self._talk
        self._bg(lambda: talk.mark_read(token, last or None))

    # ---- writing -----------------------------------------------------------------------------------------
    @Slot(str, int, bool)
    def send(self, text, reply_to=0, silent=False):
        text = text.strip()
        token = self._current
        if not text or not token or not self._store:
            return
        if self._detached:
            self.toLatest()
        ref = self._store.queue(token, text, reply_to, silent)
        self._store.set_draft(token, "", 0)
        p = {"ref": ref, "message": text, "replyTo": reply_to, "silent": silent, "at": int(time.time())}
        self.model.append([self._pending_row(p, self.model.rows[-1] if self.model.rows else None)])
        self._send_next(token)

    def _send_next(self, token):
        """The oldest message of the outbox of this conversation, unless one is already on its way: the next
        one leaves once it is through. A slow answer is never sent again by the outbox timer meanwhile."""
        talk = self._talk
        if talk is None or not self._store or token in self._sending:
            return
        p = next((p for p in self._store.outbox(token) if not p["failed"]), None)
        if p is None:
            return
        self._sending.add(token)

        def then(result):
            self._sending.discard(token)
            if talk is not self._talk:
                return
            status, data = result if isinstance(result, tuple) else (0, None)
            if status in (200, 201):
                self._store.sent(p["ref"])
                if isinstance(data, dict) and data.get("id") and token == self._current:
                    self._merge(token, [data])
                self._send_next(token)
                return
            if status == 0:
                self._store.tried(p["ref"])            # offline: the outbox sends it later
                return
            # refused (read-only, removed from the conversation, too long…): the message stays, marked
            self._store.tried(p["ref"], failed=True)
            i = self.model.find("ref:" + p["ref"])
            if i >= 0:
                row = dict(self.model.rows[i])
                row.update({"pending": False, "failed": True})
                self.model.replace(i, row)
            self.done.emit("send", False, self._t["send_failed"])
            self._send_next(token)
        self._bg(lambda: talk.send(token, p["message"], p.get("replyTo") or 0, p.get("silent", False), p["ref"]), then)

    def _flush_outbox(self):
        if not self._store or self._talk is None:
            return
        for token in dict.fromkeys(p["token"] for p in self._store.outbox() if not p["failed"]):
            self._send_next(token)

    @Slot(str)
    def retry(self, key):
        if not key.startswith("ref:") or not self._store:
            return
        ref = key[4:]
        self._store.retry(ref)
        p = next((p for p in self._store.outbox(self._current) if p["ref"] == ref), None)
        i = self.model.find(key)
        if p and i >= 0:
            row = dict(self.model.rows[i])
            row.update({"pending": True, "failed": False})
            self.model.replace(i, row)
            self._send_next(self._current)

    @Slot(str)
    def discard(self, key):
        if key.startswith("ref:") and self._store:
            self._store.sent(key[4:])
            i = self.model.find(key)
            if i >= 0:
                self.model.remove(i)

    @Slot(str, int)
    @Slot(str, int, str)
    def saveDraft(self, text, reply_to=0, token=""):
        """The draft of the open conversation (or of `token`: the one just left, written to the last key)."""
        token = token or self._current
        if self._store and token:
            self._store.set_draft(token, text, reply_to)

    def _change(self, message_id, apply, call, what):
        """An optimistic change of one message: shown at once, undone if the cloud refuses."""
        i = self.model.find(str(message_id))
        if i < 0 or self._talk is None:
            return
        before = self.model.rows[i]
        raw = json.loads(json.dumps(before["_raw"]))
        apply(raw)
        self.model.replace(i, self._row(raw, self.model.rows[i - 1] if i > 0 else None))
        token = self._current

        def then(result):
            status, data = result if isinstance(result, tuple) else (0, None)
            j = self.model.find(str(message_id))
            if status in (200, 201, 202):
                if isinstance(data, dict) and data.get("parent") and j >= 0:
                    self.model.replace(j, self._row(data["parent"], self.model.rows[j - 1] if j > 0 else None))
                elif isinstance(data, dict) and data.get("id") == message_id and j >= 0:
                    self.model.replace(j, self._row(data, self.model.rows[j - 1] if j > 0 else None))
                if self._store:
                    self._store.put_messages(token, [self.model.rows[j]["_raw"]] if j >= 0 else [])
                return
            if j >= 0:
                self.model.replace(j, before)
            self.done.emit(what, False, self._t["offline_action"] if status == 0 else self._t[what + "_failed"])
        self._bg(call, then)

    @Slot(int, str)
    def react(self, message_id, emoji):
        self._reactors.pop((self._current, int(message_id or 0)), None)
        i = self.model.find(str(message_id))
        if i < 0:
            return
        on = emoji not in (self.model.rows[i]["_raw"].get("reactionsSelf") or [])

        def apply(raw):
            reactions = dict(raw.get("reactions") or {}) if isinstance(raw.get("reactions"), dict) else {}
            mine = list(raw.get("reactionsSelf") or [])
            if on:
                reactions[emoji] = int(reactions.get(emoji, 0)) + 1
                mine.append(emoji)
            else:
                reactions[emoji] = int(reactions.get(emoji, 1)) - 1
                if reactions[emoji] <= 0:
                    reactions.pop(emoji)
                mine = [e for e in mine if e != emoji]
            raw["reactions"], raw["reactionsSelf"] = reactions, mine
        talk, token = self._talk, self._current
        self._change(message_id, apply, lambda: talk.react(token, message_id, emoji, on), "react")

    @Slot(int, str)
    def edit(self, message_id, text):
        text = text.strip()
        if not text:
            return

        def apply(raw):
            raw["message"], raw["messageParameters"] = text, {}
            raw["lastEditTimestamp"] = int(time.time())
        talk, token = self._talk, self._current
        self._change(message_id, apply, lambda: talk.edit(token, message_id, text), "edit")

    @Slot(int)
    def remove(self, message_id):
        def apply(raw):
            raw["messageType"] = "comment_deleted"
            raw["message"], raw["messageParameters"], raw["reactions"] = self._t["deleted_message"], {}, {}
        talk, token = self._talk, self._current
        self._change(message_id, apply, lambda: talk.delete_message(token, message_id), "delete")

    @Slot(int, int)
    def remind(self, message_id, seconds):
        talk, token = self._talk, self._current
        if talk is None or not token:
            return
        at = int(time.time()) + int(seconds)

        def then(result):
            status = result[0] if isinstance(result, tuple) else 0
            self.done.emit("remind", status in (200, 201), self._t["reminder_set"] if status in (200, 201)
                           else self._t["remind_failed"])
        self._bg(lambda: talk.remind(token, message_id, at), then)

    @Slot(str, int)
    def schedule(self, text, at):
        talk, token = self._talk, self._current
        if talk is None or not token:
            return
        if not text.strip() or not talk.has("scheduled-messages"):
            self.done.emit("schedule", False, self._t["schedule_unavailable"])
            return

        def then(result):
            status = result[0] if isinstance(result, tuple) else 0
            self.done.emit("schedule", status in (200, 201), self._t["scheduled"] if status in (200, 201)
                           else self._t["schedule_failed"])
        self._bg(lambda: talk.schedule(token, text.strip(), at), then)

    # ---- files -------------------------------------------------------------------------------------------
    @Slot("QVariantList")
    def shareFiles(self, paths):
        self._upload(paths)

    @Slot("QVariantList", str, int)
    def sendFiles(self, paths, caption, reply_to):
        """Files with a message (Talk's caption, on the last one) and the message answered, like Talk web."""
        self._upload(paths, caption.strip(), reply_to)

    def _upload(self, paths, caption="", reply_to=0, voice=False):
        """Local files into the conversation: uploaded to the Talk folder of the cloud, then shared there. Each
        shows at once as our message on its way (its referenceId: the cloud's copy takes its place); a refusal
        takes it back and says so."""
        token, talk = self._current, self._talk
        # file:// links (a drop, the file dialog): decoded (%20, C:/ on Windows); plain paths as they are
        files = [Path(QUrl(str(p)).toLocalFile() if str(p).startswith("file:") else str(p)) for p in paths]
        files = [f for f in files if f.is_file()]
        if not files or not token or talk is None:
            return
        folder = talk.config("attachments", "folder", "/Talk") or "/Talk"
        user = urllib.parse.quote(talk.user)
        jobs, rows = [], []
        previous = self.model.rows[-1] if self.model.rows else None
        for i, f in enumerate(files):
            last = i == len(files) - 1
            kind = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
            meta = {"referenceId": uuid.uuid4().hex}
            if voice:
                meta["messageType"] = "voice-message"
            if last and caption:
                meta["caption"] = caption
            if last and reply_to:
                meta["replyTo"] = reply_to
            jobs.append((f, kind, meta))
            local = QUrl.fromLocalFile(str(f)).toString()
            p = {"ref": meta["referenceId"], "message": caption if last else "", "replyTo": reply_to if last else 0,
                 "at": int(time.time())}
            row = self._pending_row(p, previous)
            row["files"] = [{"id": "", "name": f.name, "size": f.stat().st_size, "mime": kind, "local": local,
                             "preview": kind.startswith("image/"), "path": ""}]
            row["voice"] = voice
            row["upload"] = True              # Talk gives no referenceId back on a share: replaced in order (_merge)
            rows.append(row)
            previous = row
        self.model.append(rows)

        def work():
            failed = []
            cloud.dav(talk.server, talk.user, talk.password, f"/remote.php/dav/files/{user}{urllib.parse.quote(folder)}", "MKCOL")
            for f, kind, meta in jobs:
                name = self._free_name(talk, user, folder, f.name)
                path = f"{folder.rstrip('/')}/{name}"
                status, _ = cloud._call(f"{talk.server}/remote.php/dav/files/{user}{urllib.parse.quote(path)}",
                                        talk.user, talk.password, "PUT", f.read_bytes(),
                                        {"Content-Type": kind}, timeout=300)
                if status in (200, 201, 204):
                    status, _ = talk.share_file(token, path, meta=meta)
                if status not in (200, 201):
                    failed.append(meta["referenceId"])
            return failed

        def then(failed):
            if isinstance(failed, Exception):
                failed = [m["referenceId"] for _, _, m in jobs]
            for ref in failed:
                i = self.model.find("ref:" + ref)
                if i >= 0:
                    self.model.remove(i)
            if failed:
                self.done.emit("share", False, self._t["share_failed"])
        self._bg(work, then)

    @Slot(result=str)
    def clipboardImage(self):
        """A picture copied (a screenshot, from a page): a PNG in the cache to send, "" when there is none."""
        from PySide6.QtGui import QGuiApplication  # noqa: PLC0415
        mime = QGuiApplication.clipboard().mimeData()
        if mime is None or not mime.hasImage() or mime.hasUrls():
            return ""
        image = QGuiApplication.clipboard().image()
        if image.isNull():
            return ""
        folder = system.CACHE / "meet-paste"
        folder.mkdir(parents=True, exist_ok=True)
        for old in folder.glob("*.png"):          # those of other days: already sent
            if time.time() - old.stat().st_mtime > 86400:
                old.unlink(missing_ok=True)
        path = folder / f"{self._t['pasted_image']} {time.strftime('%Y-%m-%d %H-%M-%S')}.png"
        return QUrl.fromLocalFile(str(path)).toString() if image.save(str(path), "PNG") else ""

    @Slot(result="QVariantList")
    def clipboardFiles(self):
        """Files copied in the file manager (their links), to attach."""
        from PySide6.QtGui import QGuiApplication  # noqa: PLC0415
        mime = QGuiApplication.clipboard().mimeData()
        if mime is None or not mime.hasUrls():
            return []
        return [u.toString() for u in mime.urls() if u.isLocalFile() and Path(u.toLocalFile()).is_file()]

    @Slot(str, result="QVariantMap")
    def fileInfo(self, link):
        """A local file to attach: its name, size, type, and whether it is a picture (shown as one)."""
        path = Path(QUrl(link).toLocalFile() if link.startswith("file:") else link)
        try:
            size = path.stat().st_size
        except OSError:
            return {}
        kind = mimetypes.guess_type(path.name)[0] or ""
        return {"url": QUrl.fromLocalFile(str(path)).toString(), "name": path.name, "size": size, "mime": kind,
                "image": kind.startswith("image/")}

    # ---- files kept here: opened with this computer's app, a picture in the viewer, a GIF -----------------
    @Slot("QVariantMap")
    def openFile(self, file):
        """A shared file: fetched once into the cache, opened with this computer's app for it (the cloud's page
        when it cannot be fetched: a folder, offline)."""
        file = {k: (v.toVariant() if hasattr(v, "toVariant") else v) for k, v in dict(file).items()}
        self.fetchFile(file, lambda path: system.open_url(QUrl.fromLocalFile(path).toString()) if path
                       else cloud.open_url(cloud.cloud_link(f"/f/{file.get('id')}")))

    @Slot("QVariantMap", str)
    def saveFile(self, file, target):
        """« Enregistrer sous… »: the file fetched, copied where asked."""
        file = {k: (v.toVariant() if hasattr(v, "toVariant") else v) for k, v in dict(file).items()}
        dest = Path(QUrl(target).toLocalFile() if target.startswith("file:") else target)

        def copy(path):
            if not path:
                self.done.emit("save", False, self._t["file_unavailable"])
                return
            try:
                dest.write_bytes(Path(path).read_bytes())
                self.done.emit("save", True, self._t["file_saved"])
            except OSError:
                self.done.emit("save", False, self._t["file_unavailable"])
        self.fetchFile(file, copy)

    @Slot("QVariantMap")
    def copyImage(self, file):
        """« Copier l'image »: the original fetched, put on the clipboard as a picture (and as its file, for
        Dolphin)."""
        from PySide6.QtCore import QMimeData  # noqa: PLC0415
        from PySide6.QtGui import QGuiApplication, QImage  # noqa: PLC0415
        file = {k: (v.toVariant() if hasattr(v, "toVariant") else v) for k, v in dict(file).items()}

        def put(path):
            image = QImage(path) if path else QImage()
            if image.isNull():
                self.done.emit("copy", False, self._t["file_unavailable"])
                return
            mime = QMimeData()
            mime.setImageData(image)
            mime.setUrls([QUrl.fromLocalFile(path)])
            QGuiApplication.clipboard().setMimeData(mime)
            self.done.emit("copy", True, self._t["image_copied"])
        self.fetchFile(file, put)

    fileReady = Signal(str, str)      # a file of the chat now on this computer: its id, its local address

    @Slot("QVariantMap")
    def fetchForView(self, file):
        """The original of a picture, for the viewer (fileReady)."""
        file = {k: (v.toVariant() if hasattr(v, "toVariant") else v) for k, v in dict(file).items()}
        self.fetchFile(file, lambda path: self.fileReady.emit(str(file.get("id")), QUrl.fromLocalFile(path).toString()) if path else None)

    def fetchFile(self, file, then):
        local = file.get("local") or ""
        if local:
            then(QUrl(local).toLocalFile())
            return
        talk = self._talk
        if talk is None or not file.get("path") or not file.get("id"):
            then("")
            return
        folder = system.CACHE / "meet-files" / str(file["id"])
        target = folder / Path(str(file.get("name") or "file")).name
        if target.exists() and target.stat().st_size == int(file.get("size") or target.stat().st_size):
            then(str(target))
            return

        def work():
            url = f"/remote.php/dav/files/{urllib.parse.quote(talk.user)}/{urllib.parse.quote(str(file['path']).lstrip('/'))}"
            status, data = cloud.dav(talk.server, talk.user, talk.password, url, "GET")
            if status != 200 or data is None:
                return ""
            folder.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            return str(target)
        self._bg(work, lambda path: then(path if isinstance(path, str) else ""))

    gifReady = Signal(str)            # a GIF of Giphy now in the cache (its id)
    gifsFound = Signal(str, "QVariantList")   # term, [{id, title, url}]
    previewReady = Signal(str)        # a link's preview now known (its address)

    @Slot(str, bool, result=str)
    def gif(self, gif_id, small):
        """A Giphy GIF (through the cloud's integration_giphy: Giphy never sees this computer) as a local file
        to animate, "" while it comes (gifReady): small for the picker, else the one of the chat."""
        gif_id = "".join(ch for ch in gif_id if ch.isalnum())
        if not gif_id:
            return ""
        version = "fixed_width_small" if small else "downsized"
        path = system.CACHE / "meet-gifs" / f"{gif_id}-{version}.gif"
        if path.exists():
            return QUrl.fromLocalFile(str(path)).toString()
        talk = self._talk
        if talk is None or path.name in self._gifs_loading:
            return ""
        self._gifs_loading.add(path.name)

        def work():
            status, data = talk._call(f"{talk.server}/index.php/apps/integration_giphy/gif/{gif_id}?preferredVersion={version}",
                                      headers={"Accept": "image/*"}, timeout=30)
            if status != 200 or not data:
                return False
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            return True

        def then(ok):
            self._gifs_loading.discard(path.name)
            if ok is True:
                self.gifReady.emit(gif_id)
        self._bg(work, then)
        return ""

    @Slot(str)
    def searchGifs(self, term):
        """GIFs for `term` (the trending ones when empty), through the cloud: gifsFound(term, entries)."""
        talk = self._talk
        if talk is None:
            return
        term = term.strip()

        def work():
            if term:
                return talk._req("GET", "/ocs/v2.php/apps/integration_giphy/api/v1/gifs/search", query={"term": term, "limit": 24})
            return talk._req("GET", "/ocs/v2.php/apps/integration_giphy/api/v1/gifs/trending", query={"limit": 24})

        def then(result):
            status, data = result if isinstance(result, tuple) else (0, None)
            entries = data.get("entries") if status == 200 and isinstance(data, dict) else None
            if entries is None:
                self.gifsFound.emit(term, [])
                if status not in (200, 0):
                    self.done.emit("gif", False, self._t["gifs_unavailable"])
                return
            found = []
            for e in entries:
                url = str(e.get("resourceUrl") or "")
                gid = giphy_id(url)
                if gid:
                    found.append({"id": gid, "title": str(e.get("title") or ""), "url": url})
            self.gifsFound.emit(term, found)
        self._bg(work, then)

    @Slot(str, result="QVariantMap")
    def preview(self, url):
        """The preview of a link (the cloud's references: its title, text and picture; a page of our cloud as
        the cloud names it), {} while it comes (previewReady) or when there is none."""
        if not url.startswith(("http://", "https://")):
            return {}
        if url in self._previews:
            return self._previews[url] or {}
        talk = self._talk
        if talk is None:
            return {}
        self._previews[url] = None

        def work():
            return talk._req("GET", "/ocs/v2.php/references/resolve", query={"reference": url})

        def then(result):
            status, data = result if isinstance(result, tuple) else (0, None)
            ref = (data.get("references") or {}).get(url) if status == 200 and isinstance(data, dict) else None
            og = ref.get("openGraphObject") if isinstance(ref, dict) else None
            if not isinstance(og, dict) or not (og.get("name") or og.get("description")):
                if status == 0:
                    self._previews.pop(url, None)        # offline: asked again later
                return
            thumb = str(og.get("thumb") or "")
            self._previews[url] = {"title": str(og.get("name") or ""), "text": str(og.get("description") or "")[:240],
                                   "image": "image://meet/ref/" + urllib.parse.quote(thumb, safe="") if thumb.startswith(talk.server) else "",
                                   "site": urllib.parse.urlsplit(url).hostname or ""}
            self.previewReady.emit(url)
        self._bg(work, then)
        return {}

    @staticmethod
    def _free_name(talk, user, folder, name):
        stem, dot, ext = name.rpartition(".")
        if not dot:
            stem, ext = name, ""
        candidate, n = name, 1
        while True:
            status, _ = cloud._call(f"{talk.server}/remote.php/dav/files/{user}{urllib.parse.quote(folder.rstrip('/') + '/' + candidate)}",
                                    talk.user, talk.password, "HEAD")
            if status == 404 or status == 0:
                return candidate
            n += 1
            candidate = f"{stem} ({n}).{ext}" if ext else f"{stem} ({n})"

    @Slot(str)
    def openInCloud(self, file_id):
        if file_id:
            cloud.open_url(cloud.cloud_link(f"/f/{file_id}"))

    # ---- the conversation itself -------------------------------------------------------------------------
    def _room_action(self, call, what, apply=None, reload=True):
        token, talk = self._current, self._talk
        if not token or talk is None:
            return
        before = json.loads(json.dumps(self._room))
        if apply:
            apply(self._room)
            for r in self._rooms:
                if r["token"] == token:
                    apply(r)
            self.changed.emit()
            self.roomChanged.emit()

        def then(result):
            status = result[0] if isinstance(result, tuple) else 0
            if status in (200, 201):
                if reload:
                    self._reload_room(token)
                    self.refresh()
                return
            if apply and token == self._current:
                self._room = before
                self.roomChanged.emit()
                self.refresh()
            # the cloud's own words when it gives some (a password too weak for its policy)
            data = result[1] if isinstance(result, tuple) and len(result) > 1 else None
            said = data.get("message") if isinstance(data, dict) and isinstance(data.get("message"), str) else ""
            self.done.emit(what, False, self._t["offline_action"] if status == 0 else said or self._t["room_action_failed"])
        self._bg(lambda: call(talk, token), then)

    @Slot(bool)
    def setFavorite(self, on):
        self._room_action(lambda t, k: t.favorite(k, on), "favorite", lambda r: r.update({"isFavorite": on}), False)

    @Slot(bool)
    def setArchived(self, on):
        self._room_action(lambda t, k: t.archive(k, on), "archive", lambda r: r.update({"isArchived": on}), False)

    @Slot(int)
    def setNotify(self, level):
        self._room_action(lambda t, k: t.notify_level(k, level), "notify",
                          lambda r: r.update({"notificationLevel": level}), False)

    @Slot(str)
    def rename(self, name):
        if name.strip():
            self._room_action(lambda t, k: t.rename(k, name.strip()), "rename",
                              lambda r: r.update({"displayName": name.strip(), "name": name.strip()}))

    @Slot(str)
    def setDescription(self, text):
        self._room_action(lambda t, k: t.set_description(k, text), "description", lambda r: r.update({"description": text}))

    @Slot(bool)
    def setPublic(self, on):
        self._room_action(lambda t, k: t.make_public(k, on), "public",
                          lambda r: r.update({"type": api.PUBLIC if on else api.GROUP}))

    @Slot(bool)
    def setLobby(self, on):
        self._room_action(lambda t, k: t.set_lobby(k, on), "lobby", lambda r: r.update({"lobbyState": 1 if on else 0}))

    @Slot(bool)
    def setReadOnly(self, on):
        self._room_action(lambda t, k: t.set_read_only(k, on), "readonly", lambda r: r.update({"readOnly": 1 if on else 0}))

    @Slot(str)
    def setPassword(self, password):
        self._room_action(lambda t, k: t.set_password(k, password), "password",
                          lambda r: r.update({"hasPassword": bool(password)}))

    @Slot(int)
    def setExpiration(self, seconds):
        self._room_action(lambda t, k: t.set_message_expiration(k, seconds), "expiration",
                          lambda r: r.update({"messageExpiration": seconds}))

    @Slot(int, bool)
    def setModerator(self, attendee, on):
        self._room_action(lambda t, k: t.set_moderator(k, attendee, on), "moderator")

    @Slot(int)
    def removeParticipant(self, attendee):
        self._participants = [p for p in self._participants if int(p.get("attendeeId") or 0) != attendee]
        self.roomChanged.emit()
        self._room_action(lambda t, k: t.remove_participant(k, attendee), "remove_participant")

    @Slot(str, str)
    def addParticipant(self, new, source):
        self._room_action(lambda t, k: t.add_participant(k, new, source), "add_participant")

    # ---- the settings of the open conversation (ConversationSettings.qml) -----------------------------------
    @Slot(bool)
    def setNotifyCalls(self, on):
        self._room_action(lambda t, k: t.notify_calls(k, on), "notify",
                          lambda r: r.update({"notificationCalls": 1 if on else 0}), False)

    @Slot(bool)
    def setImportant(self, on):
        self._room_action(lambda t, k: t.set_important(k, on), "important", lambda r: r.update({"isImportant": on}), False)

    @Slot(bool)
    def setSensitive(self, on):
        self._room_action(lambda t, k: t.set_sensitive(k, on), "sensitive", lambda r: r.update({"isSensitive": on}), False)

    @Slot(int)
    def setListable(self, scope):
        self._room_action(lambda t, k: t.set_listable(k, scope), "listable", lambda r: r.update({"listable": scope}))

    @Slot(bool)
    def setMentionModerators(self, on):
        self._room_action(lambda t, k: t.set_mention_permissions(k, on), "mentions",
                          lambda r: r.update({"mentionPermissions": 1 if on else 0}))

    @Slot(int)
    def setDefaultPermissions(self, permissions):
        """What everyone may do (0: Talk's own default, everything). Custom permissions of a person are reset."""
        self._room_action(lambda t, k: t.set_permissions(k, "default", permissions), "permissions",
                          lambda r: r.update({"defaultPermissions": permissions}))

    @Slot(int, str, int)
    def setAttendeePermissions(self, attendee, method, permissions):
        """One person: set (their own permissions), add or remove some (a call: the Custom bit is set by Talk)."""
        for p in self._participants:
            if int(p.get("attendeeId") or 0) == attendee and method == "set":
                p["permissions"] = permissions | 1
                p["attendeePermissions"] = permissions | 1
        self.roomChanged.emit()
        self._room_action(lambda t, k: t.set_attendee_permissions(k, attendee, method, permissions), "permissions")

    @Slot(int)
    def makeOwner(self, attendee):
        self._room_action(lambda t, k: t.set_moderator(k, attendee, True, owner=True), "moderator")

    @Slot(bool)
    def setPreserved(self, on):
        def flag(r):
            r["attributes"] = (int(r.get("attributes") or 0) | 2) if on else (int(r.get("attributes") or 0) & ~2)
        self._room_action(lambda t, k: t.preserve(k, on), "preserve", flag)

    @Slot()
    def clearHistory(self):
        token = self._current

        def call(t, k):
            result = t.clear_history(k)
            if result[0] in (200, 202):
                self._ran.emit(lambda: self._history_cleared(token, 0))
            return result
        self._room_action(call, "clear_history")

    def _history_cleared(self, token, until):
        """Every message before `until` (0: all) gone, here and in the store."""
        if self._store:
            with self._store.lock:
                if until:
                    self._store.db.execute("DELETE FROM messages WHERE token = ? AND id < ?", (token, until))
                else:
                    self._store.db.execute("DELETE FROM messages WHERE token = ?", (token,))
        if token == self._current:
            keep = [r["_raw"] for r in self.model.rows if r.get("_raw") and until and int(r["id"] or 0) >= until]
            self.model.reset(self._rows(keep))
            self._older_done.add(token)
            self._shared = {"loaded": False, "kinds": []}
            self.sharedChanged.emit()

    # the picture of the conversation: an emoji on a colour, a picture of this computer, or none
    @Slot(str, str)
    def setAvatarEmoji(self, emoji, color):
        self._room_action(lambda t, k: t.avatar_emoji(k, emoji, color.lstrip("#") or None), "avatar")

    @Slot(str)
    def setAvatarFile(self, url):
        """Any picture Qt reads (Talk only takes PNG and JPEG): its centre in a square of 512 px, in PNG."""
        local = QUrl(url).toLocalFile() if url.startswith("file:") else url
        talk, token = self._talk, self._current
        if not local or talk is None or not token:
            return

        def work():
            from PySide6.QtGui import QImage  # noqa: PLC0415
            image = QImage(local)
            if image.isNull():
                return (415, None)
            side = min(image.width(), image.height())
            image = image.copy((image.width() - side) // 2, (image.height() - side) // 2, side, side)
            if side > 512:
                image = image.scaled(512, 512, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
            out = system.DATA / f"meet-avatar-{uuid.uuid4().hex[:8]}.png"
            image.save(str(out), "PNG")
            try:
                return talk.upload_avatar(token, str(out))
            finally:
                out.unlink(missing_ok=True)

        def then(result):
            status = result[0] if isinstance(result, tuple) else 0
            if status in (200, 201):
                self._reload_room(token)
                self.refresh()
            else:
                self.done.emit("avatar", False, self._t["avatar_unreadable"] if status == 415
                               else self._t["offline_action"] if status == 0 else self._t["room_action_failed"])
        self._bg(work, then)

    @Slot()
    def removeAvatar(self):
        self._room_action(lambda t, k: t.delete_avatar(k), "avatar")

    # e-mail guests: their invitation again, a CSV of addresses
    @Slot(int)
    def resendInvitations(self, attendee):
        self._act(lambda t, k: t.resend_invitations(k, attendee or None), "resend", reload_extras=False,
                  ok_message=self._t["invitations_sent"])

    @Slot(str, bool)
    def importEmails(self, url, test_run):
        local = QUrl(url).toLocalFile() if url.startswith("file:") else url
        talk, token = self._talk, self._current
        if not local or talk is None or not token:
            return

        def then(result):
            status, data = result if isinstance(result, tuple) else (0, None)
            data = data if isinstance(data, dict) else {}
            out = {"ok": status == 200, "testRun": test_run, "file": url, "invites": int(data.get("invites") or 0),
                   "duplicates": int(data.get("duplicates") or 0), "invalid": int(data.get("invalid") or 0),
                   "message": data.get("message") or (self._t["offline_action"] if status == 0 else
                                                      self._t["csv_failed"] if status != 200 else "")}
            self.emailsImported.emit(out)
            if status == 200 and not test_run:
                self._reload_room(token)
        self._bg(lambda: talk.import_emails(token, local, test_run), then)

    # bots
    @js_property(notify=settingsChanged)
    def roomSettings(self):
        return self._settings

    @Slot()
    def loadRoomSettings(self):
        talk, token = self._talk, self._current
        moderator = int(self._room.get("participantType") or 0) in (api.OWNER, api.MODERATOR)
        if talk is None or not token or not moderator or not talk.has("bots-v1"):
            return

        def then(result):
            if isinstance(result, Exception) or token != self._current:
                return
            status, bots = result
            lang = self.app.lang
            rows = [{"id": int(b.get("id") or 0), "name": b.get("name") or "", "description": b.get("description") or "",
                     "state": int(b.get("state") or 0)} for b in bots] if status == 200 else []
            # the call summary comes in many languages: the user's first (its description names it)
            names = {"fr": "Français", "en": "English", "de": "Deutsch"}
            mine = names.get(lang, "")
            for b in rows:
                b["mine"] = bool(mine) and f"({mine}" in b["description"]
            rows.sort(key=lambda b: (not b["mine"], b["state"] == 0, b["name"].lower()))
            self._settings = {"bots": rows, "loaded": True}
            self.settingsChanged.emit()
        self._bg(lambda: talk.bots(token), then)

    @Slot(int, bool)
    def setBot(self, bot_id, on):
        self._settings = dict(self._settings, bots=[dict(b, state=1 if on else 0) if b["id"] == bot_id else b
                                                    for b in self._settings["bots"]])
        self.settingsChanged.emit()
        self._act(lambda t, k: t.set_bot(k, bot_id, on), "bot", reload_extras=False)

    # tags: the account's, to sort its conversations (the list filters by one)
    @js_property(notify=tagsChanged)
    def tags(self):
        counts = {}
        for r in self._rooms:
            if not r.get("isArchived"):
                for t in r.get("tagIds") or []:
                    counts[str(t)] = counts.get(str(t), 0) + 1
        return [dict(t, count=counts.get(t["id"], 0)) for t in self._tags]

    @Slot()
    def loadTags(self):
        talk = self._talk
        if talk is None:
            return
        self._last_tags = time.time()

        def then(result):
            if isinstance(result, Exception) or talk is not self._talk:
                return
            status, tags = result
            if status == 200:
                self._tags = [{"id": str(t.get("id")), "name": t.get("name") or ""} for t in tags
                              if t.get("type", "custom") == "custom"]
                self.tagsChanged.emit()
        self._bg(talk.tags, then)

    def _put_tags(self, token, ids):
        for r in self._rooms + ([self._room] if self._room.get("token") == token else []):
            if r.get("token") == token:
                r["tagIds"] = list(ids)
        self.changed.emit()
        self.roomChanged.emit()
        self.tagsChanged.emit()
        talk = self._talk

        def then(result):
            status = result[0] if isinstance(result, tuple) else 0
            if status not in (200, 201):
                self.done.emit("tags", False, self._t["offline_action"] if status == 0 else self._t["room_action_failed"])
                self.refresh()
        self._bg(lambda: talk.set_room_tags(token, ids), then)

    @Slot(str, bool)
    def setTag(self, tag_id, on):
        """The open conversation gets the tag, or loses it."""
        token = self._current
        ids = [str(t) for t in self._room.get("tagIds") or [] if str(t) != tag_id] + ([tag_id] if on else [])
        if token and self._talk:
            self._put_tags(token, ids)

    @Slot(str)
    def createTag(self, name):
        """A new tag, given to the open conversation at once."""
        name, talk, token = name.strip(), self._talk, self._current
        if not name or talk is None:
            return

        def then(result):
            status, tag = result if isinstance(result, tuple) else (0, None)
            if status in (200, 201) and isinstance(tag, dict) and tag.get("id"):
                self._tags.append({"id": str(tag["id"]), "name": tag.get("name") or name})
                self.tagsChanged.emit()
                if token:
                    self._put_tags(token, [str(t) for t in next((r.get("tagIds") or [] for r in self._rooms
                                                                 if r["token"] == token), [])] + [str(tag["id"])])
            else:
                self.done.emit("tags", False, self._t["offline_action"] if status == 0 else self._t["room_action_failed"])
        self._bg(lambda: talk.create_tag(name), then)

    @Slot(str, str)
    def renameTag(self, tag_id, name):
        talk = self._talk
        if not name.strip() or talk is None:
            return
        self._tags = [dict(t, name=name.strip()) if t["id"] == tag_id else t for t in self._tags]
        self.tagsChanged.emit()
        self._bg(lambda: talk.rename_tag(tag_id, name.strip()), lambda result: None)

    @Slot(str)
    def deleteTag(self, tag_id):
        talk = self._talk
        if talk is None:
            return
        self._tags = [t for t in self._tags if t["id"] != tag_id]
        for r in self._rooms:
            r["tagIds"] = [t for t in r.get("tagIds") or [] if str(t) != tag_id]
        if self._filter == "tag:" + tag_id:
            self.setFilter("all")
        self.tagsChanged.emit()
        self.changed.emit()
        self.roomChanged.emit()
        self._bg(lambda: talk.delete_tag(tag_id), lambda result: self.refresh())

    # what was shared: pictures and videos, files, voice messages, polls, places, the rest
    SHARED = ("media", "file", "voice", "audio", "poll", "location", "deckcard", "recording", "other")

    @js_property(notify=sharedChanged)
    def shared(self):
        return self._shared

    @Slot()
    @Slot(str)
    def loadShared(self, kind=""):
        """The last 20 of each kind (kind empty), or up to 200 of one."""
        talk, token = self._talk, self._current
        if talk is None or not token or (not kind and self._shared_loading == token):
            return
        if not kind:
            self._shared_loading = token
        me = talk.user

        def item(m):
            parts = richtext.render(m, me)
            return {"id": int(m.get("id") or 0), "name": m.get("actorDisplayName") or "", "time": int(m.get("timestamp") or 0),
                    "files": parts["files"], "poll": parts["poll"], "location": parts["location"],
                    "plain": parts["plain"][:200]}

        def work():
            if kind:
                status, data = talk.shared_items(token, kind, 200)
                items = list(data.values()) if isinstance(data, dict) else data if isinstance(data, list) else []
                return status, {kind: items}
            return talk.shared_items(token, "", 20)

        def then(result):
            if not kind and self._shared_loading == token:
                self._shared_loading = ""
            if isinstance(result, Exception) or token != self._current:
                return
            status, data = result
            if status != 200 or not isinstance(data, dict):
                self._shared = dict(self._shared, loaded=True, failed=True)
                self.sharedChanged.emit()
                return
            out = dict(self._shared) if kind else {}
            for name, items in data.items():
                items = list(items.values()) if isinstance(items, dict) else items or []
                rows = sorted((item(m) for m in items if isinstance(m, dict)), key=lambda r: -r["id"])
                out[name] = rows
                out[name + "_all"] = bool(kind) or len(rows) < 20
            out["kinds"] = [k for k in self.SHARED if out.get(k)]
            out["loaded"], out["failed"] = True, False
            self._shared = out
            self.sharedChanged.emit()
        self._bg(work, then)

    @Slot()
    def leaveRoom(self):
        token, talk = self._current, self._talk
        if not token or talk is None:
            return
        self._rooms = [r for r in self._rooms if r["token"] != token]
        if self._store:
            self._store.forget_room(token)
        self._close_room()
        self.changed.emit()

        def then(result):
            status = result[0] if isinstance(result, tuple) else 0
            if status not in (200, 201):
                self.done.emit("leave", False, self._t["leave_failed"])
                self.refresh()
        self._bg(lambda: talk.leave_room(token), then)

    @Slot()
    def deleteRoom(self):
        token, talk = self._current, self._talk
        if not token or talk is None:
            return
        self._rooms = [r for r in self._rooms if r["token"] != token]
        if self._store:
            self._store.forget_room(token)
        self._close_room()
        self.changed.emit()

        def then(result):
            status = result[0] if isinstance(result, tuple) else 0
            if status not in (200, 201):
                self.done.emit("delete_room", False, self._t["room_action_failed"])
                self.refresh()
        self._bg(lambda: talk.delete_room(token), then)

    # ---- new conversations, people -----------------------------------------------------------------------
    @Slot(str)
    def searchPeople(self, text):
        """People to write to or invite: accounts of the cloud (groups, teams) and Plume's contacts (email)."""
        self._people_query = text
        talk = self._talk
        if talk is None:
            return
        query = text.strip()
        token = self._current or "new"

        def work():
            out, seen = [], set()
            status, found = talk.autocomplete(query, "call", token) if query else (200, [])
            for p in found if isinstance(found, list) else []:
                source = p.get("source") or "users"
                key = (source, p.get("id"))
                if key in seen or (source == "users" and p.get("id") == talk.user):
                    continue
                seen.add(key)
                out.append({"id": p.get("id") or "", "source": source, "name": p.get("label") or p.get("id") or "",
                            "sub": p.get("subline") or p.get("shareWithDisplayNameUnique") or "",
                            "avatar": f"image://meet/user/{urllib.parse.quote(p.get('id') or '')}" if source == "users" else "",
                            "status": (p.get("status") or {}).get("status", "") if isinstance(p.get("status"), dict) else ""})
            for c in self._contacts(query):
                key = ("emails", c["email"])
                if key not in seen and not any(o["sub"] == c["email"] for o in out):
                    seen.add(key)
                    out.append({"id": c["email"], "source": "emails", "name": c["name"] or c["email"],
                                "sub": c["email"], "avatar": "", "status": ""})
            return out[:20]

        def then(result):
            if isinstance(result, Exception) or text != self._people_query:
                return
            self._people = result
            self.peopleChanged.emit()
        self._bg(work, then)

    @staticmethod
    def _contacts(query):
        """Plume's contacts (read-only copy of the address book), by name or email."""
        if len(query) < 2:
            return []
        db = system.CACHE / "plume.db"
        if not db.exists():
            return []
        try:
            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=2)
            rows = con.execute("SELECT name, emails FROM contacts WHERE name LIKE ? OR emails LIKE ? LIMIT 12",
                               (f"%{query}%", f"%{query}%")).fetchall()
            con.close()
        except sqlite3.Error:
            return []
        out = []
        for name, emails in rows:
            try:
                addresses = json.loads(emails or "[]")
            except json.JSONDecodeError:
                addresses = []
            for e in addresses[:2]:
                email = e.get("email") if isinstance(e, dict) else str(e)
                if email:
                    out.append({"name": name or "", "email": email})
        return out

    @Slot(str, str, "QVariantList", bool)
    def create(self, kind, name, invites, public=False):
        """kind: "one" (invites[0] is a user id) | "group" (name, the people to add) | "note" (note to self)."""
        talk = self._talk
        if talk is None:
            return

        def work():
            if kind == "one":
                return talk.create_room(api.ONE_TO_ONE, invite=invites[0]["id"]), []
            if kind == "note":
                return talk.create_room(api.NOTE_TO_SELF, name=name), []
            status, room = talk.create_room(api.PUBLIC if public else api.GROUP, name=name)
            failed = []
            if status in (200, 201) and isinstance(room, dict):
                for p in invites:
                    st, _ = talk.add_participant(room["token"], p["id"], p.get("source") or "users")
                    if st not in (200, 201):
                        failed.append(p.get("name") or p["id"])
            return (status, room), failed

        def then(result):
            if isinstance(result, Exception):
                result = ((0, None), [])
            (status, room), failed = result
            if status not in (200, 201) or not isinstance(room, dict):
                self.done.emit("create", False, self._t["create_failed"])
                return
            if not any(r["token"] == room["token"] for r in self._rooms):
                self._rooms.insert(0, room)
            self.changed.emit()
            self.open(room["token"])
            hook, self._after_create = self._after_create, None
            if hook:
                hook(room["token"])
            self.done.emit("created", True, self._t["some_not_added"].replace("%1", ", ".join(failed)) if failed else "")
            self.refresh()
        self._bg(work, then)

    @Slot(str)
    def openWith(self, user_id):
        """The one-to-one with someone (--to=USER, « Discuter » from a contact): opened, made if needed."""
        for r in self._rooms:
            if r.get("type") == api.ONE_TO_ONE and r.get("name") == user_id:
                self.open(r["token"])
                return
        self.create("one", "", [{"id": user_id, "source": "users"}], False)

    @Slot(str, str, bool)
    def openWithAddress(self, address, name, video):
        """« Discuter » / « Visio » from Contacts or Courrier: the account of the cloud that has this address (its
        one-to-one), else a conversation open by link that invites the address (Talk mails the link)."""
        talk = self._talk
        address = address.strip().lower()
        if talk is None or "@" not in address:
            return
        # the conversation already made for this address (not one more at each click), while it exists
        known_room = self._store.meta("invite:" + address) if self._store else ""
        if known_room and any(r["token"] == known_room for r in self._rooms):
            self.open(known_room)
            if video:
                self.meetingReady.emit(known_room)
            return

        def work():
            status, found = talk.autocomplete(address, "call", "new")
            for p in found if isinstance(found, list) else []:
                if (p.get("source") or "users") != "users":
                    continue
                known = {str(p.get(k) or "").lower() for k in ("id", "label", "subline", "shareWithDisplayNameUnique")}
                if address in known or (address.endswith("@orneos.eu") and address.split("@")[0] == str(p.get("id")).lower()):
                    return "user", p.get("id")
            status, room = talk.create_room(api.PUBLIC, name=(name or address)[:250])
            if status not in (200, 201) or not isinstance(room, dict):
                return "failed", status
            st, _ = talk.add_participant(room["token"], address, "emails")
            return "room", (room, st in (200, 201))

        def then(result):
            kind, value = result if isinstance(result, tuple) else ("failed", 0)
            if kind == "user":
                for r in self._rooms:
                    if r.get("type") == api.ONE_TO_ONE and r.get("name") == value:
                        self.open(r["token"])
                        if video:
                            self.meetingReady.emit(r["token"])
                        return
                self._after_create = (lambda token: self.meetingReady.emit(token)) if video else None
                self.create("one", "", [{"id": value, "source": "users"}], False)
                return
            if kind == "room":
                room, invited = value
                if self._store:
                    self._store.set_meta("invite:" + address, room["token"])
                self._rooms.insert(0, room)
                self.changed.emit()
                self.open(room["token"])
                self.done.emit("invite", True, self._t["invited_by_mail"].replace("%1", address) if invited
                               else self._t["some_not_added"].replace("%1", address))
                if video:
                    self.meetingReady.emit(room["token"])
                self.refresh()
                return
            self.done.emit("create", False, self._t["offline_action"] if value == 0 else self._t["create_failed"])
        self._bg(work, then)

    # ---- polls -------------------------------------------------------------------------------------------
    @Slot(str, "QVariantList", bool, bool)
    def createPoll(self, question, options, multiple, anonymous):
        talk, token = self._talk, self._current
        options = [str(o).strip() for o in options if str(o).strip()]
        if talk is None or not token or not question.strip() or len(options) < 2:
            return

        def then(result):
            status = result[0] if isinstance(result, tuple) else 0
            if status not in (200, 201):
                self.done.emit("poll", False, self._t["poll_failed"])
        self._bg(lambda: talk.create_poll(token, question.strip(), options, multiple, anonymous), then)

    @Slot(str, result="QVariantMap")
    def poll(self, poll_id):
        return self._polls.get(poll_id, {})

    @Slot(str)
    def loadPoll(self, poll_id):
        talk, token = self._talk, self._current

        def then(result):
            status, data = result if isinstance(result, tuple) else (0, None)
            if status == 200 and isinstance(data, dict):
                self._polls[poll_id] = data
                self.pollChanged.emit(poll_id)
        self._bg(lambda: talk.poll(token, poll_id), then)

    @Slot(str, "QVariantList")
    def vote(self, poll_id, option_ids):
        talk, token = self._talk, self._current

        def then(result):
            status, data = result if isinstance(result, tuple) else (0, None)
            if status == 200 and isinstance(data, dict):
                self._polls[poll_id] = data
                self.pollChanged.emit(poll_id)
            else:
                self.done.emit("vote", False, self._t["vote_failed"])
        self._bg(lambda: talk.vote(token, poll_id, [int(o) for o in option_ids]), then)

    @Slot(str)
    def closePoll(self, poll_id):
        talk, token = self._talk, self._current

        def then(result):
            status, data = result if isinstance(result, tuple) else (0, None)
            if status == 200 and isinstance(data, dict):
                self._polls[poll_id] = data
                self.pollChanged.emit(poll_id)
        self._bg(lambda: talk.close_poll(token, poll_id), then)

    # ---- search ------------------------------------------------------------------------------------------
    @Slot(str)
    def searchMessages(self, term):
        talk, token = self._talk, self._current
        if not term.strip() or not token:
            self.searchDone.emit([])
            return

        def then(result):
            status, entries = result if isinstance(result, tuple) else (0, [])
            out = []
            for e in entries if isinstance(entries, list) else []:
                attrs = e.get("attributes") or {}
                out.append({"title": e.get("title") or "", "text": e.get("subline") or "",
                            "id": int(attrs.get("messageId") or 0), "time": 0})
            self.searchDone.emit(out)
        self._bg(lambda: talk.search(token, term.strip()), then)

    @Slot(int)
    def jumpTo(self, message_id):
        """A message far up (a search result, a link): the messages around it replace the list."""
        talk, token, gen = self._talk, self._current, self._gen
        if self.model.find(str(message_id)) >= 0:
            self.jumped.emit(message_id)
            return

        def then(result):
            status, messages = result if isinstance(result, tuple) else (0, None)
            if gen != self._gen or status != 200 or not isinstance(messages, list):
                return
            messages.sort(key=lambda m: int(m["id"]))
            newest = self._store.last_id(token) if self._store else 0
            shown = max([int(m["id"]) for m in messages] or [0])
            self.model.reset(self._rows(messages))
            self._older_done.discard(token)
            self._set_detached(bool(newest) and shown < newest)
            self.jumped.emit(message_id)
        self._bg(lambda: talk.context(token, message_id), then)

    # ---- around the open conversation: pinned message, scheduled ones, bans, breakout rooms, threads ------
    @js_property(notify=extrasChanged)
    def extras(self):
        return self._extras

    def _load_extras(self, token):
        talk, room = self._talk, dict(self._room)
        if talk is None or not token:
            return
        moderator = int(room.get("participantType") or 0) in (api.OWNER, api.MODERATOR, api.GUEST_MODERATOR)
        pinned = int(room.get("lastPinnedId") or 0)
        if pinned and pinned == int(room.get("hiddenPinnedId") or 0):
            pinned = 0

        i = self.model.find(str(pinned)) if pinned else -1
        shown = self.model.rows[i]["_raw"] if i >= 0 else None      # read here: the model is the UI thread's

        def listed(result):
            status, items = result
            return items if status == 200 and isinstance(items, list) else []

        def work():
            out = {"pinned": {}, "scheduled": [], "bans": [], "breakout": [], "threads": []}
            if pinned:
                raw = shown
                if raw is None:
                    status, around = talk.context(token, pinned, limit=1)
                    raw = next((m for m in around or [] if int(m.get("id") or 0) == pinned), None) \
                        if status == 200 and isinstance(around, list) else None
                if raw:
                    parts = richtext.render(raw, talk.user)
                    out["pinned"] = {"id": pinned, "name": raw.get("actorDisplayName") or "",
                                     "text": (parts["plain"] or (parts["files"][0]["name"] if parts["files"] else ""))[:300]}
            if room.get("hasScheduledMessages") and talk.has("scheduled-messages"):
                items = listed(talk.scheduled(token))
                out["scheduled"] = [{"id": str(m.get("id")), "text": m.get("message") or "", "at": int(m.get("sendAt") or 0),
                                     "silent": bool(m.get("silent"))} for m in items]
                out["scheduled"].sort(key=lambda m: m["at"])
            if moderator and talk.has("ban-v1"):
                items = listed(talk.bans(token))
                out["bans"] = [{"id": int(b.get("id") or 0), "name": b.get("bannedDisplayName") or b.get("bannedActorId") or "",
                                "note": b.get("internalNote") or "", "time": int(b.get("bannedTime") or 0)} for b in items]
            if int(room.get("breakoutRoomMode") or 0) and room.get("objectType") != "room":
                items = listed(talk.breakout_rooms(token))
                out["breakout"] = [{"token": b.get("token"), "name": b.get("displayName") or "",
                                    "hasCall": bool(b.get("hasCall")),
                                    "assistance": int(b.get("breakoutRoomStatus") or 0) == 2} for b in items]
            if talk.has("threads"):
                items = listed(talk.threads(token, 20))
                for t in items:
                    thread = t.get("thread") if isinstance(t.get("thread"), dict) else t
                    out["threads"].append({"id": int(thread.get("id") or 0), "title": thread.get("title") or "",
                                           "replies": int(thread.get("numReplies") or 0),
                                           "activity": int(thread.get("lastActivity") or 0)})
            return out

        def then(result):
            if isinstance(result, Exception) or token != self._current:
                return
            self._extras = result
            self.extrasChanged.emit()
        self._bg(work, then)

    def _act(self, call, what, reload_extras=True, ok_message=""):
        """A change of the open conversation that has nothing to show before the cloud's answer."""
        token, talk = self._current, self._talk
        if not token or talk is None:
            return

        def then(result):
            status = result[0] if isinstance(result, tuple) else 0
            if status in (200, 201, 202):
                if ok_message:
                    self.done.emit(what, True, ok_message)
                if reload_extras and token == self._current:
                    self._reload_room(token)
                return
            self.done.emit(what, False, self._t["offline_action"] if status == 0 else self._t["room_action_failed"])
        self._bg(lambda: call(talk, token), then)

    # pinned
    @Slot(int, bool)
    def pin(self, message_id, on):
        if on:
            i = self.model.find(str(message_id))
            if i >= 0:
                parts = self.model.rows[i]
                self._extras = dict(self._extras, pinned={"id": message_id, "name": parts["name"], "text": parts["plain"][:300]})
                self.extrasChanged.emit()
        elif self._extras["pinned"].get("id") == message_id:
            self._extras = dict(self._extras, pinned={})
            self.extrasChanged.emit()
        self._act(lambda t, k: t.pin(k, message_id, on), "pin")

    @Slot(int)
    def hidePin(self, message_id):
        self._extras = dict(self._extras, pinned={})
        self.extrasChanged.emit()
        self._act(lambda t, k: t.hide_pin(k, message_id), "pin", reload_extras=False)

    @Slot()
    def markUnread(self):
        token = self._current
        for r in self._rooms:
            if r["token"] == token:
                r["unreadMessages"] = max(1, int(r.get("unreadMessages") or 0))
        self.changed.emit()
        self._act(lambda t, k: t.mark_unread(k), "unread", reload_extras=False)
        self._close_room()

    @Slot(int)
    def setLobbyTimer(self, timestamp):
        """The lobby closes the conversation until then (0: until a moderator opens it)."""
        self._room_action(lambda t, k: t.set_lobby(k, True, timestamp), "lobby",
                          lambda r: r.update({"lobbyState": 1, "lobbyTimer": timestamp}))

    # bans
    @Slot(int, str)
    def ban(self, attendee, note):
        p = next((p for p in self._participants if int(p.get("attendeeId") or 0) == attendee), None)
        if p is None:
            return
        self._participants = [x for x in self._participants if x is not p]
        self.roomChanged.emit()
        self._act(lambda t, k: t.ban(k, p.get("actorType") or "users", p.get("actorId") or "", note), "ban",
                  ok_message=self._t["banned"].replace("%1", p.get("displayName") or ""))

    @Slot(int)
    def unban(self, ban_id):
        self._extras = dict(self._extras, bans=[b for b in self._extras["bans"] if b["id"] != ban_id])
        self.extrasChanged.emit()
        self._act(lambda t, k: t.unban(k, ban_id), "unban")

    # scheduled messages
    @Slot(str, int, bool)
    def scheduleMessage(self, text, at, silent=False):
        talk, token = self._talk, self._current
        text = text.strip()
        if not text or talk is None or not token:
            return
        if not talk.has("scheduled-messages"):
            self.done.emit("schedule", False, self._t["schedule_unavailable"])
            return
        tmp = {"id": "tmp:" + uuid.uuid4().hex[:8], "text": text, "at": int(at), "silent": silent}
        self._extras = dict(self._extras, scheduled=sorted(self._extras["scheduled"] + [tmp], key=lambda m: m["at"]))
        self.extrasChanged.emit()

        def then(result):
            status = result[0] if isinstance(result, tuple) else 0
            if status not in (200, 201):
                self._extras = dict(self._extras, scheduled=[m for m in self._extras["scheduled"] if m["id"] != tmp["id"]])
                self.extrasChanged.emit()
                self.done.emit("schedule", False, self._t["schedule_failed"])
                return
            self.done.emit("schedule", True, self._t["scheduled"].replace("%1", self.app.when(int(at))))
            self._reload_room(token)
        self._bg(lambda: talk.schedule(token, text, at, 0, silent), then)

    @Slot(str, str, int)
    def editScheduled(self, message_id, text, at):
        items = [dict(m, text=text, at=at) if m["id"] == message_id else m for m in self._extras["scheduled"]]
        self._extras = dict(self._extras, scheduled=sorted(items, key=lambda m: m["at"]))
        self.extrasChanged.emit()
        self._act(lambda t, k: t.edit_scheduled(k, message_id, text, at), "schedule")

    @Slot(str)
    def deleteScheduled(self, message_id):
        self._extras = dict(self._extras, scheduled=[m for m in self._extras["scheduled"] if m["id"] != message_id])
        self.extrasChanged.emit()
        self._act(lambda t, k: t.delete_scheduled(k, message_id), "schedule")

    @Slot(str)
    def sendScheduledNow(self, message_id):
        m = next((m for m in self._extras["scheduled"] if m["id"] == message_id), None)
        talk, token = self._talk, self._current
        if not m or talk is None or not token:
            return
        self._extras = dict(self._extras, scheduled=[x for x in self._extras["scheduled"] if x["id"] != message_id])
        self.extrasChanged.emit()

        def then(result):
            status = result[0] if isinstance(result, tuple) else 0
            if status in (200, 201, 202, 204):           # sent now only once the cloud will not send it
                if token == self._current:
                    self.send(m["text"], 0, m.get("silent", False))
                elif self._store:
                    self._store.queue(token, m["text"], 0, m.get("silent", False))
                    self._send_next(token)
                return
            if token == self._current:
                self._reload_room(token)
            self.done.emit("schedule", False, self._t["offline_action"] if status == 0 else self._t["room_action_failed"])
        self._bg(lambda: talk.delete_scheduled(token, message_id), then)

    # breakout rooms (moderators set them up; everyone moves between them)
    @Slot(int, int)
    def configureBreakout(self, mode, amount):
        self._act(lambda t, k: t.configure_breakout(k, mode, amount), "breakout",
                  ok_message=self._t["breakout_ready"])

    @Slot(bool)
    def startBreakout(self, on):
        self._act(lambda t, k: t.start_breakout(k, on), "breakout")

    @Slot()
    def removeBreakout(self):
        self._act(lambda t, k: t.remove_breakout(k), "breakout")

    @Slot(str)
    def broadcast(self, text):
        if text.strip():
            self._act(lambda t, k: t.broadcast(k, text.strip()), "broadcast", reload_extras=False,
                      ok_message=self._t["broadcast_sent"])

    @Slot(bool)
    def askAssistance(self, on):
        self._act(lambda t, k: t.ask_assistance(k, on), "assistance",
                  ok_message=self._t["assistance_asked"] if on else "")

    @Slot(str, result=str)
    def switchBreakout(self, target):
        """Free mode: go to another breakout room (the call follows, Calls.switch)."""
        parent = self._room.get("objectId") if self._room.get("objectType") == "room" else self._current
        talk = self._talk
        if talk is None or not parent:
            return ""

        def then(result):
            status, data = result if isinstance(result, tuple) else (0, None)
            if status == 200:
                self.open(target)
            else:
                self.done.emit("breakout", False, self._t["room_action_failed"])
        self._bg(lambda: talk.switch_breakout(parent, target), then)
        return target

    # threads (Talk 25: `threads`)
    @Property(QObject, constant=True)
    def threadMessages(self):
        return self.thread_model

    @js_property(notify=extrasChanged)
    def thread(self):
        return self._thread

    threadsChanged = Signal()

    @js_property(notify=threadsChanged)
    def followedThreads(self):
        """The threads followed in every conversation, the most recent first: {token, room, id, title, who, text,
        replies, activity}."""
        return self._followed

    @Slot()
    def loadThreads(self):
        talk = self._talk
        if talk is None or not talk.has("threads"):
            return

        def then(result):
            status, items = result if isinstance(result, tuple) else (0, [])
            if status != 200:
                return
            names = {r["token"]: r.get("displayName") or r.get("name") or "" for r in self._rooms}
            out = []
            for t in items:
                thread = t.get("thread") if isinstance(t.get("thread"), dict) else {}
                last = t.get("last") if isinstance(t.get("last"), dict) else (t.get("first") or {})
                token, tid = thread.get("roomToken") or "", int(thread.get("id") or 0)
                if not token or not tid:
                    continue
                text, who = "", ""
                if last:
                    text = richtext.render(last, talk.user)["plain"].replace("\n", " ")[:160]
                    who = self._t["you"] if last.get("actorId") == talk.user and last.get("actorType") == "users" \
                        else (last.get("actorDisplayName") or "")
                out.append({"token": token, "room": names.get(token, ""), "id": tid,
                            "title": thread.get("title") or text[:60], "who": who, "text": text,
                            "replies": int(thread.get("numReplies") or 0),
                            "activity": int(thread.get("lastActivity") or 0)})
            out.sort(key=lambda x: -x["activity"])
            self._followed = out
            self.threadsChanged.emit()
        self._bg(lambda: talk.subscribed_threads(100), then)

    @Slot(int, str)
    def openThread(self, thread_id, title):
        talk, token = self._talk, self._current
        self._thread = {"id": thread_id, "title": title, "token": token}
        self.thread_model.reset([])
        self.extrasChanged.emit()
        if talk is None or not thread_id:
            return

        def then(result):
            status, messages = result if isinstance(result, tuple) else (0, [])
            if self._thread.get("id") != thread_id or status != 200:
                return
            messages = sorted([m for m in messages if m.get("systemMessage") not in UPDATES], key=lambda m: int(m["id"]))
            # the thread's first message may be older than the 100 last of the thread: it is in the list anyway
            first = next((r["_raw"] for r in self.model.rows if r["id"] == thread_id), None)
            if first and not any(int(m["id"]) == thread_id for m in messages):
                messages.insert(0, first)
            rows, previous = [], None
            for m in messages:
                row = self._row(m, previous)
                rows.append(row)
                previous = row
            self.thread_model.reset(rows)
        self._bg(lambda: talk.messages(token, 0, future=False, limit=100, thread=thread_id), then)

    @Slot()
    def closeThread(self):
        self._thread = {}
        self.thread_model.reset([])
        self.extrasChanged.emit()

    @Slot(str)
    def sendInThread(self, text):
        talk, token, thread = self._talk, self._current, dict(self._thread)
        text = text.strip()
        if not text or talk is None or not thread.get("id"):
            return
        me = talk.user
        fake = {"id": 0, "actorType": "users", "actorId": me, "actorDisplayName": self.app.profile.get("name", me),
                "timestamp": int(time.time()), "message": text, "messageParameters": {}, "messageType": "comment",
                "referenceId": uuid.uuid4().hex}
        row = self._row(fake, self.thread_model.rows[-1] if self.thread_model.rows else None)
        row.update({"key": "ref:" + fake["referenceId"], "pending": True})
        self.thread_model.append([row])

        def then(result):
            status, data = result if isinstance(result, tuple) else (0, None)
            i = self.thread_model.find(row["key"])
            if status in (200, 201) and isinstance(data, dict) and i >= 0:
                self.thread_model.replace(i, self._row(data, self.thread_model.rows[i - 1] if i > 0 else None))
                if token == self._current:
                    self._merge(token, [data])
            elif i >= 0:
                failed = dict(row, pending=False, failed=True)
                self.thread_model.replace(i, failed)
                self.done.emit("send", False, self._t["send_failed"])
        self._bg(lambda: talk.send(token, text, 0, False, fake["referenceId"], "", thread["id"]), then)

    @Slot(str, str)
    def startThread(self, title, text, open_it=False):
        """A new thread: its first message, with its title (Talk's threadTitle); open_it: shown beside at once."""
        talk, token = self._talk, self._current
        if talk is None or not token or not text.strip():
            return
        title = title.strip() or text.strip()[:60]

        def then(result):
            status, data = result if isinstance(result, tuple) else (0, None)
            if status in (200, 201) and isinstance(data, dict):
                self._merge(token, [data])
                self._load_extras(token)
                if open_it and token == self._current:
                    self.openThread(int(data.get("threadId") or data.get("id") or 0), title)
            else:
                self.done.emit("send", False, self._t["send_failed"])
        self._bg(lambda: talk.send(token, text.strip(), 0, False, uuid.uuid4().hex, title), then)

    @Slot(int, str)
    def threadFrom(self, message_id, title):
        """A thread about a message already sent: Talk only makes a thread with a new message (no thread can
        start from an old one), so its first message quotes that one and links to it; it opens beside."""
        row = next((r for r in self.model.rows if r["id"] == message_id), None)
        if row is None:
            return
        quote = "\n".join("> " + line for line in (row["plain"] or "").strip().splitlines()[:12])
        link = f"{self._talk.server}/call/{self._current}#message_{message_id}" if self._talk else ""
        text = f"{quote}\n\n[{row['name'] or self._t['app_name']}]({link})" if quote else f"[{self._t['app_name']}]({link})"
        self.startThread(title, text, True)

    # ---- the home of Meet: meetings to come, reminders, « Nouvelle réunion » ----------------------------
    @js_property(notify=homeChanged)
    def home(self):
        return self._home

    @Slot()
    def loadHome(self):
        talk = self._talk
        if talk is None:
            return
        self._last_home = time.time()

        def work():
            out = {"events": [], "reminders": [], "calendars": self._home.get("calendars") or []}
            status, events = talk.upcoming_events()
            for e in events:
                out["events"].append({
                    "title": e.get("eventName") or e.get("roomDisplayName") or "", "start": int(e.get("start") or 0),
                    "end": int(e.get("end") or 0), "token": e.get("roomToken") or "", "room": e.get("roomDisplayName") or "",
                    "avatar": f"image://meet/room/{e.get('roomToken')}/{e.get('roomAvatarVersion', '')}" if e.get("roomToken") else "",
                    "active": int(e.get("roomActiveSince") or 0) > 0, "accepted": int(e.get("accepted") or 0),
                    "invited": int(e.get("invited") or 0), "description": (e.get("eventDescription") or "")[:200]})
            out["events"].sort(key=lambda e: e["start"])
            status, reminders = talk.upcoming_reminders()
            for r in reminders:
                parts = richtext.render(r, talk.user)
                out["reminders"].append({"token": r.get("roomToken") or "", "id": int(r.get("messageId") or 0),
                                         "name": r.get("actorDisplayName") or "", "text": parts["plain"][:160],
                                         "at": int(r.get("reminderTimestamp") or 0)})
            if not out["calendars"]:
                out["calendars"] = self._calendars(talk)
            return out

        def then(result):
            if isinstance(result, Exception) or talk is not self._talk:
                return
            self._home = result
            self.homeChanged.emit()
        self._bg(work, then)

    @staticmethod
    def _calendars(talk):
        """The calendars where a meeting can go: those of the account that take events and can be written."""
        body = ('<?xml version="1.0"?><d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav" '
                'xmlns:cs="http://calendarserver.org/ns/" xmlns:oc="http://owncloud.org/ns"><d:prop><d:displayname/>'
                '<d:resourcetype/><c:supported-calendar-component-set/><oc:owner-principal/><d:current-user-privilege-set/>'
                '</d:prop></d:propfind>')
        status, raw = cloud.dav(talk.server, talk.user, talk.password,
                                f"/remote.php/dav/calendars/{urllib.parse.quote(talk.user)}/", "PROPFIND", body, "1")
        if status != 207 or not raw:
            return []
        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(raw)
        except ET.ParseError:
            return []
        ns = {"d": "DAV:", "c": "urn:ietf:params:xml:ns:caldav"}
        out = []
        for resp in root.findall("d:response", ns):
            href = (resp.findtext("d:href", "", ns) or "").rstrip("/")
            prop = resp.find("d:propstat/d:prop", ns)
            if prop is None or prop.find("d:resourcetype/c:calendar", ns) is None:
                continue
            comps = [c.get("name") for c in prop.findall("c:supported-calendar-component-set/c:comp", ns)]
            if comps and "VEVENT" not in comps:
                continue
            privileges = ET.tostring(prop.find("d:current-user-privilege-set", ns) or ET.Element("x")).decode()
            if "write" not in privileges and "all" not in privileges:
                continue
            uri = href.rsplit("/", 1)[-1]
            out.append({"uri": uri, "name": prop.findtext("d:displayname", "", ns) or uri})
        out.sort(key=lambda c: (c["uri"] != "personal", c["name"].lower()))
        return out

    @Slot(str, int, int, str, str)
    def scheduleMeeting(self, calendar, start, end, title, description):
        """« Programmer une réunion »: an event in the calendar for the open conversation, everyone invited."""
        talk, token = self._talk, self._current
        if talk is None or not token:
            return
        calendar = calendar or ((self._home.get("calendars") or [{}])[0].get("uri") or "personal")

        def then(result):
            status = result[0] if isinstance(result, tuple) else 0
            if status in (200, 201):
                self.done.emit("meeting", True, self._t["meeting_scheduled"])
                self.loadHome()
            else:
                error = (result[1] or {}).get("error", "") if isinstance(result, tuple) and isinstance(result[1], dict) else ""
                self.done.emit("meeting", False, self._t["offline_action"] if status == 0
                               else self._t["meeting_no_email" if error == "email" else "meeting_failed"])
        self._bg(lambda: talk.schedule_meeting(token, calendar, start, end, title, description), then)

    @Slot(str, int, int, str, "QVariantList")
    def planMeeting(self, title, start, end, calendar, invites):
        """« Programmer une réunion » from the home: its conversation (open by link), the people, then the event
        in the calendar with everyone invited (Talk writes the link of the conversation in it)."""
        talk = self._talk
        if talk is None:
            return
        calendar = calendar or ((self._home.get("calendars") or [{}])[0].get("uri") or "personal")
        people = [{k: (v.toVariant() if hasattr(v, "toVariant") else v) for k, v in dict(p).items()} for p in invites]

        def work():
            status, room = talk.create_room(api.PUBLIC, name=title.strip() or self._t["meeting_default"])
            if status not in (200, 201) or not isinstance(room, dict):
                return status, None, ""
            for person in people:
                talk.add_participant(room["token"], person["id"], person.get("source") or "users")
            status, data = talk.schedule_meeting(room["token"], calendar, start, end, title.strip())
            return status, room, (data or {}).get("error", "") if isinstance(data, dict) else ""

        def then(result):
            status, room, error = result if isinstance(result, tuple) and len(result) == 3 else (0, None, "")
            if room is None:
                self.done.emit("meeting", False, self._t["offline_action"] if status == 0 else self._t["meeting_failed"])
                return
            if not any(r["token"] == room["token"] for r in self._rooms):
                self._rooms.insert(0, room)
            self.changed.emit()
            self.done.emit("meeting", status in (200, 201), self._t["meeting_scheduled"] if status in (200, 201)
                           else self._t["meeting_no_email" if error == "email" else "meeting_failed"])
            self.loadHome()
            self.refresh()
        self._bg(work, then)

    @Slot(str)
    def meetNow(self, name):
        """« Nouvelle réunion »: a conversation open by link, its call at once (the link to share is in it)."""
        talk = self._talk
        if talk is None:
            return

        def then(result):
            status, room = result if isinstance(result, tuple) else (0, None)
            if status not in (200, 201) or not isinstance(room, dict):
                self.done.emit("create", False, self._t["create_failed"])
                return
            if not any(r["token"] == room["token"] for r in self._rooms):
                self._rooms.insert(0, room)
            self.changed.emit()
            self.open(room["token"])
            self.meetingReady.emit(room["token"])
            self.refresh()
        self._bg(lambda: talk.create_room(api.PUBLIC, name=name.strip() or self._t["meeting_default"]), then)

    # ---- voice messages ----------------------------------------------------------------------------------
    @Slot(str)
    def sendVoice(self, path):
        self._upload([path], voice=True)
