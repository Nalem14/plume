"""The call of the window (QML: `calls`): one at a time, its page (CallStage.qml shows it in a WebEngineView),
its controls, its duration, the devices chosen. A second call asked while one runs: the first is left.

A call started from the window opens on « Prêt à rejoindre ? » (our picture, the microphone's level, the
devices, the blur); answering a ring joins at once. The blur's files come from orneos.eu the first time
(vision.py), in a thread.
"""
import threading
import time

from PySide6.QtCore import Property, QObject, Qt, QTimer, Signal, Slot

from meet_core import vision
from meet_core.call import Call


class Calls(QObject):
    changed = Signal()           # a call starts or ends
    stateChanged = Signal()      # people, mute, screen… of the call
    tick = Signal()              # every second during a call (its duration)
    event = Signal("QVariantMap")
    failed = Signal(str)
    levelChanged = Signal()
    qualityChanged = Signal()
    _vision = Signal(object)

    def __init__(self, app, library, theme):
        super().__init__()
        self.app, self.library, self.theme = app, library, theme
        self._call = None
        self._token = ""
        self._name = ""
        self._started = 0
        self._devices = []
        self._level = 0.0
        self._blur_loading = False
        self._switch_to = ""            # breakout rooms: the room the call moves to once this one is left
        self._vision.connect(self._vision_ready, Qt.ConnectionType.QueuedConnection)
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self.tick)
        # the quality of the call, read every 4 s from the page (loss and round trip): 0 unknown, 1 poor, 2, 3 good
        self._quality = {"level": 0, "loss": 0.0, "rtt": 0}
        self._last_stats = None
        self._stats_timer = QTimer(self)
        self._stats_timer.setInterval(4000)
        self._stats_timer.timeout.connect(lambda: self._call and self._call.phase == "in_call" and self._call.send("stats"))
        theme.changed.connect(lambda: self._call and self._call.send("theme", "dark" if theme.dark else "light"))

    # ---- for the QML -------------------------------------------------------------------------------------
    @Property(bool, notify=changed)
    def active(self):
        return self._call is not None

    @Property(QObject, notify=changed)
    def call(self):
        return self._call

    @Property(str, notify=changed)
    def token(self):
        return self._token

    @Property(str, notify=changed)
    def name(self):
        return self._name

    @Property(str, notify=stateChanged)
    def phase(self):
        return self._call.phase if self._call else "idle"

    @Property("QVariantMap", notify=stateChanged)
    def state(self):
        return self._call.state if self._call else {}

    @Property(int, notify=tick)
    def elapsed(self):
        return int(time.time() - self._started) if self._started else 0

    @Property("QVariantList", notify=stateChanged)
    def devices(self):
        return self._devices

    @Property("QVariantMap", notify=qualityChanged)
    def quality(self):
        """{level: 0 (not yet) | 1 poor | 2 fair | 3 good, loss: % of packets lost, rtt: ms to the server}."""
        return dict(self._quality)

    def _read_stats(self, stats):
        lost, received = int(stats.get("lost") or 0), int(stats.get("received") or 0)
        rtt = int(stats.get("rtt") or 0)
        before, self._last_stats = self._last_stats, (lost, received)
        loss = 0.0
        if before is not None:
            d_lost, d_received = max(0, lost - before[0]), max(0, received - before[1])
            loss = 100.0 * d_lost / (d_lost + d_received) if d_lost + d_received else 0.0
        if not rtt and before is None:
            return
        level = 3 if loss < 2 and rtt < 250 else 2 if loss < 8 and rtt < 600 else 1
        quality = {"level": level, "loss": round(loss, 1), "rtt": rtt}
        if quality != self._quality:
            self._quality = quality
            self.qualityChanged.emit()

    @Property(float, notify=levelChanged)
    def level(self):
        """The microphone before the call (0 to 1), for the meter of « Prêt à rejoindre ? »."""
        return self._level

    @Property(bool, notify=stateChanged)
    def blurLoading(self):
        return self._blur_loading

    # ---- start, stop -------------------------------------------------------------------------------------
    @Slot(str)
    @Slot(str, bool, bool)
    @Slot(str, bool, bool, bool)
    def start(self, token, audio=None, video=None, preview=False):
        talk = self.library.talk()
        if talk is None or not token:
            return
        if self._call is not None:
            if token == self._token:
                return
            self._let_go()
        room = next((r for r in self.library.rooms if r["token"] == token), {}) or self.library.room
        people = {p["actorId"]: p["name"] for p in self.library.participants if p["actorType"] == "users"} \
            if self.library.current == token else {}
        avatars = {}                                  # the page draws initials; photos come with the next version
        self._token = token
        self._name = room.get("name", "") if isinstance(room, dict) else ""
        self._started = 0
        call = Call(talk, token, nick=self.app.profile.get("name", ""),
                    audio=self.app.pref("join_audio") if audio is None else audio,
                    video=self.app.pref("join_video") if video is None else video,
                    theme="dark" if self.theme.dark else "light", labels=self._labels(), people=people,
                    avatars=avatars, devices={"mic": self.app.pref("mic"), "camera": self.app.pref("camera")},
                    blur=self.app.pref("blur") == "blur", vision=vision.paths(), parent=self)
        call.stateChanged.connect(self._state_changed)
        call.event.connect(self._event)
        call.failed.connect(self._failed)
        call.ended.connect(self._ended)
        self._call = call
        self.library.in_call = token
        self.changed.emit()
        if preview:
            call.preview()
        else:
            call.prepare()
        if self.app.pref("blur") == "blur" and vision.paths() is None:
            self.setBlur(True)

    def _let_go(self):
        """Leave the call of the window for another one: it ends on its own, without touching the new one."""
        call = self._call
        for signal in (call.stateChanged, call.event, call.failed, call.ended):
            signal.disconnect()
        call.ended.connect(call.deleteLater)
        if call.phase in ("preview", "idle", "ended"):
            call.send("leave")
            call.deleteLater()
        else:
            call.hangup()                             # leaving: its `ended` comes and deletes it
        self._call, self._token, self._started, self._switch_to = None, "", 0, ""
        self.library.in_call = ""
        self._timer.stop()
        self._stats_timer.stop()
        self._last_stats = None
        self._quality = {"level": 0, "loss": 0.0, "rtt": 0}

    @Slot()
    def join(self):
        """« Rejoindre » of the check before the call."""
        if self._call is not None and self._call.phase == "preview":
            self._call.prepare()

    @Slot()
    @Slot(bool)
    def hangup(self, for_all=False):
        if self._call is None:
            return
        if self._call.phase == "preview":           # nothing was asked of the cloud yet
            self._call.send("leave")
            self._call._set_phase("ended")
            self._ended()
            return
        self._call.hangup(for_all)

    def shutdown(self):
        """The app quits: out of the call before the process ends (threads would not finish), so the others
        do not see us there until the cloud gives up on us."""
        call = self._call
        if call is None:
            return
        call.send("leave")
        if call.phase in ("joining", "in_call", "ready", "preparing", "leaving"):
            try:
                if call.phase in ("joining", "in_call", "leaving"):
                    call.talk.leave_call(call.token)
                call.talk.leave(call.token)
            except Exception:  # noqa: BLE001 (offline: nothing more to do)
                pass

    @Slot(bool)
    def setBlur(self, on):
        self.app.setPref("blur", "blur" if on else "")
        if not on:
            self.send("blur", False)
            return
        paths = vision.paths()
        if paths:
            self.send("blur", {"on": True, "vision": paths})
            return
        if self._blur_loading:
            return
        self._blur_loading = True
        self.stateChanged.emit()
        threading.Thread(target=lambda: self._vision.emit(vision.ensure()), daemon=True).start()

    def _vision_ready(self, paths):
        self._blur_loading = False
        self.stateChanged.emit()
        if not paths:
            self.failed.emit(self.app.t["blur_unavailable"])
            self.app.setPref("blur", "")
        elif self.app.pref("blur") == "blur":
            self.send("blur", {"on": True, "vision": paths})

    def _ended(self):
        self._stats_timer.stop()
        self._last_stats = None
        self._quality = {"level": 0, "loss": 0.0, "rtt": 0}
        self.qualityChanged.emit()
        call = self._call
        self._call, self._token, self._started = None, "", 0
        self.library.in_call = ""
        self._timer.stop()
        self.changed.emit()
        self.stateChanged.emit()
        if call is not None:
            call.deleteLater()
        self.library.refresh()
        if self._switch_to:                           # breakout rooms: the call goes on in the other room
            token, self._switch_to = self._switch_to, ""
            self.library.open(token)
            self.start(token, self.app.pref("join_audio"), self.app.pref("join_video"), False)

    def _state_changed(self):
        if self._call and self._call.phase == "in_call" and not self._started:
            self._started = time.time()
            self._timer.start()
            self._stats_timer.start()
        self.stateChanged.emit()

    def _event(self, data):
        if data.get("type") == "level":
            self._level = float(data.get("level") or 0)
            self.levelChanged.emit()
            return
        if data.get("type") == "error" and data.get("code") == "blur_slow":
            self.app.setPref("blur", "")              # not again on this computer, until asked
        if data.get("type") == "switchto" and data.get("token") and self._call is not None:
            # a moderator started (or ended) the breakout rooms: Talk moves us, like Talk web
            self._switch_to = data["token"]
            self.hangup()
            return
        if data.get("type") == "stats":
            self._read_stats(data.get("stats") or {})
            return
        if data.get("type") == "devices":
            self._devices = data.get("devices") or []
            self.stateChanged.emit()
        self.event.emit(data)

    def _failed(self, code):
        self.failed.emit(self.app.t.get("call_error_" + code, self.app.t["call_error"]))
        if self._call and self._call.phase == "ended":
            self._ended()

    def _labels(self):
        t = self.app.t
        return {k: t.get("stage_" + k, k) for k in ("you", "guest", "hand", "screenOf", "connecting",
                                                     "reconnecting", "aloneTitle", "aloneBody")}

    # ---- controls ----------------------------------------------------------------------------------------
    @Slot(str, "QVariant")
    def send(self, cmd, value=None):
        if self._call is None:
            return
        if cmd in ("mic", "camera", "speaker") and value:
            self.app.setPref(cmd, value)
        if cmd == "layout":
            self.app.setPref("layout", value)
        self._call.send(cmd, value)

    @Slot()
    def toggleAudio(self):
        self.send("audio", not self.state.get("audio", False))

    @Slot()
    def toggleVideo(self):
        self.send("video", not self.state.get("video", False))

    @Slot()
    def toggleScreen(self):
        self.send("screen", not self.state.get("screen", False))

    @Slot()
    def toggleHand(self):
        self.send("hand", not self.state.get("hand", False))
