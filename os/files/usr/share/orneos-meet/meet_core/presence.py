"""Meet on the cloud's signaling server (the HPB of Talk, signaling.orneos.eu), outside of calls: a WebSocket of
our own, the same protocol as engine/signaling.js.

  - « roomlist » events: the cloud tells at once that a conversation changed (a call starts, a message, an
    invitation). The list is read again then, so a call rings within a second instead of the next read.
  - While a conversation is open in the window in front: we are in its room, like Talk web, to know who writes
    (startedTyping / stoppedTyping, sent to each session as Talk does) and to say that we do.

It has its own Talk (its own cookies, so its own Nextcloud session: the call's session is apart). Leaving the
room when the window goes behind matters: Talk does not notify (phone) the people who are in the room.
"""
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Signal

from meet_core import api

TYPING_TTL = 15           # a « startedTyping » with no news after that: no longer shown


class Presence(QObject):
    roomsChanged = Signal()           # a roomlist event: read the list again
    typingChanged = Signal()
    _ran = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ran.connect(lambda job: job(), Qt.ConnectionType.QueuedConnection)
        # entering and leaving conversations, one after the other: a leave never overtakes the join it undoes
        # (a session left behind in a room means no notification on the phone for it)
        self._serial = ThreadPoolExecutor(max_workers=1, thread_name_prefix="meet-presence")
        self._talk = None
        self._socket = None
        self._connected = False
        self._closed = True
        self._session = ""
        self._resume = ""
        self._next = 1
        self._callbacks = {}
        self._retry = 2000
        self._want = ""               # the conversation we should be in ("" = none)
        self._room = ""               # the one we are in, on the signaling server
        self._nc = {}                 # token -> its Nextcloud session (ours)
        self._sessions = {}           # signaling session -> {user, name}, in our room
        self._typing = {}             # session -> (name, user, until)
        self._typing_on = False
        self._settings = None
        self._reconnect = QTimer(self)
        self._reconnect.setSingleShot(True)
        self._reconnect.timeout.connect(self._connect)
        self._refresh = QTimer(self)  # roomlist events come in bursts: one read of the list
        self._refresh.setSingleShot(True)
        self._refresh.setInterval(400)
        self._refresh.timeout.connect(self.roomsChanged)
        self._expire = QTimer(self)
        self._expire.setInterval(3000)
        self._expire.timeout.connect(self._expire_typing)
        self._expire.start()

    # ---- life --------------------------------------------------------------------------------------------
    def start(self, account):
        self.stop()
        if not account:
            return
        try:
            from PySide6.QtWebSockets import QWebSocket  # noqa: F401 (absent: Meet works, only less fast)
        except ImportError:
            return
        server, user, password = account
        self._talk = api.Talk(server, user, password)
        self._closed = False
        self._connect()

    def stop(self):
        self._closed = True
        self._reconnect.stop()
        talk, room = self._talk, self._room
        if self._socket is not None:
            self._send({"type": "bye", "bye": {}})
            self._socket.close()
            self._socket.deleteLater()
            self._socket = None
        if talk and room:
            self._serial.submit(talk.leave, room)
        self._connected, self._session, self._resume, self._room = False, "", "", ""
        self._sessions, self._typing, self._nc = {}, {}, {}
        self._talk = None
        self.typingChanged.emit()

    def _connect(self):
        if self._closed or self._talk is None:
            return
        talk = self._talk

        def work():
            status, settings = talk.signaling_settings("")
            return settings if status == 200 and isinstance(settings, dict) else None

        def then(settings):
            if self._closed or talk is not self._talk:
                return
            if not settings or settings.get("signalingMode") != "external" or not settings.get("server"):
                self._later()
                return
            settings["backend"] = talk.server + "/ocs/v2.php/apps/spreed/api/v3/signaling/backend"
            self._settings = settings
            from PySide6.QtWebSockets import QWebSocket
            server = settings["server"][0] if isinstance(settings["server"], list) else settings["server"]
            url = server.rstrip("/").replace("https://", "wss://").replace("http://", "ws://") + "/spreed"
            socket = QWebSocket()
            socket.setParent(self)
            socket.connected.connect(self._hello)
            socket.textMessageReceived.connect(self._receive)
            socket.disconnected.connect(lambda s=socket: self._lost(s))
            self._socket = socket
            socket.open(QUrl(url))
        threading.Thread(target=lambda: self._ran.emit(lambda r=work(): then(r)), daemon=True).start()

    def _later(self):
        if not self._closed:
            self._reconnect.start(self._retry)
            self._retry = min(self._retry * 2, 60000)

    def _lost(self, socket):
        if socket is not self._socket:
            return
        socket.deleteLater()
        self._socket = None
        self._connected = False
        self._room = ""
        self._sessions = {}
        self._later()

    # ---- the protocol ------------------------------------------------------------------------------------
    def _send(self, message, callback=None):
        if self._socket is None:
            return
        if callback:
            message["id"] = str(self._next)
            self._callbacks[message["id"]] = callback
            self._next += 1
        self._socket.sendTextMessage(json.dumps(message))

    def _hello(self):
        if self._resume:
            self._send({"type": "hello", "hello": {"version": "1.0", "resumeid": self._resume}}, self._hello_answer)
            return
        params = self._settings.get("helloAuthParams") or {}
        version = "2.0" if params.get("2.0") else "1.0"
        self._send({"type": "hello", "hello": {"version": version, "features": [],
                                               "auth": {"url": self._settings["backend"], "params": params.get(version)}}},
                   self._hello_answer)

    def _hello_answer(self, data):
        if data.get("type") != "hello":
            self._resume = ""
            if self._socket is not None:
                self._socket.close()                  # a new ticket at the next try
            return
        self._retry = 2000
        self._connected = True
        self._session = data["hello"].get("sessionid", "")
        self._resume = data["hello"].get("resumeid", "")
        self._room = ""
        self._enter()
        self._refresh.start()                         # what changed while we were away

    def _receive(self, text):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return
        callback = self._callbacks.pop(data.get("id"), None) if data.get("id") else None
        if callback:
            callback(data)
            return
        kind = data.get("type")
        if kind == "event":
            self._event(data.get("event") or {})
        elif kind == "message":
            message = data.get("message") or {}
            payload = message.get("data") or {}
            sender = (message.get("sender") or {}).get("sessionid", "")
            if payload.get("type") in ("startedTyping", "stoppedTyping") and sender != self._session:
                self._typed(sender, payload["type"] == "startedTyping")
        elif kind == "error" and (data.get("error") or {}).get("code") in ("token_expired", "no_such_session"):
            self._resume = ""
            if self._socket is not None:
                self._socket.close()

    def _event(self, event):
        target, kind = event.get("target"), event.get("type")
        if target == "roomlist":
            self._refresh.start()
        elif target == "room" and kind == "join":
            for j in event.get("join") or []:
                sid = j.get("sessionid")
                if sid and sid != self._session:
                    user = j.get("user") or {}
                    self._sessions[sid] = {"user": j.get("userid") or "",
                                           "name": user.get("displayname") or user.get("displayName") or ""}
                    if self._typing_on:
                        self._to(sid, "startedTyping")
        elif target == "room" and kind == "leave":
            for sid in event.get("leave") or []:
                self._sessions.pop(sid, None)
                if self._typing.pop(sid, None):
                    self.typingChanged.emit()
        elif target == "room" and kind == "message":
            self._refresh.start()

    # ---- the open conversation ---------------------------------------------------------------------------
    def follow(self, token):
        """Be in this conversation ("" = in none): the window in front with it open."""
        if token == self._want:
            return
        self._want = token
        self._typing_on = False
        self._enter()

    def _enter(self):
        if not self._connected or self._talk is None or self._want == self._room:
            return
        talk, old, new = self._talk, self._room, self._want
        self._room = new
        self._sessions = {}
        if self._typing:
            self._typing = {}
            self.typingChanged.emit()

        def work():
            if old:
                talk.leave(old)
                self._nc.pop(old, None)
            if not new:
                return ""
            status, joined = talk.join(new, force=False)
            return joined.get("sessionId", "") if status == 200 and isinstance(joined, dict) else ""

        def then(nc_session):
            if self._room != new or not self._connected or talk is not self._talk:
                if nc_session and new != self._room:
                    self._serial.submit(talk.leave, new)
                return
            if not new:
                self._send({"type": "room", "room": {"roomid": "", "sessionid": ""}})
                return
            if not nc_session:
                self._room = ""                       # a password, the lobby, offline: no typing here
                return
            self._nc[new] = nc_session
            self._send({"type": "room", "room": {"roomid": new, "sessionid": nc_session}})
        self._serial.submit(lambda: self._ran.emit(lambda r=work(): then(r)))

    def typing(self, on):
        """We write (or stopped) in the open conversation: told to each one there, as Talk does."""
        if on == self._typing_on or not self._room:
            return
        self._typing_on = on
        for sid in self._sessions:
            self._to(sid, "startedTyping" if on else "stoppedTyping")

    def _to(self, sid, kind):
        self._send({"type": "message", "message": {"recipient": {"type": "session", "sessionid": sid},
                                                   "data": {"type": kind}}})

    def _typed(self, sid, on):
        if on:
            who = self._sessions.get(sid) or {}
            self._typing[sid] = (who.get("name") or "", who.get("user") or "", time.time() + TYPING_TTL)
        elif not self._typing.pop(sid, None):
            return
        self.typingChanged.emit()

    def _expire_typing(self):
        now = time.time()
        gone = [sid for sid, (_, _user, until) in self._typing.items() if until < now]
        for sid in gone:
            del self._typing[sid]
        if gone:
            self.typingChanged.emit()

    def typers(self):
        """Those who write in the open conversation: [(name, user id)], the name as the signaling server gave
        it ("" when it did not: the library finds it among the participants)."""
        return [(name, user) for name, user, _ in self._typing.values()]
