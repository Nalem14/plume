"""One call, from Python: the Nextcloud side (enter the conversation, join and leave the call) and the page that
does the media (engine/call.html in QtWebEngine), the two speaking through QWebChannel.

The page comes first, with the camera and the microphone only: « Prêt à rejoindre ? » (phase preview), nothing
asked of the cloud yet. Then Talk's order: signaling settings and a Nextcloud session (POST participants/active),
the page connects to the signaling server and enters the room with that session (command « connect »), then the
call is joined (POST /call) and the page publishes. Leaving does it backwards. Blocking cloud calls run in threads; their results come
back on the UI thread through a queued signal.
"""
import json
import threading
from pathlib import Path

from PySide6.QtCore import Property, QObject, Qt, QUrl, Signal, Slot
from PySide6.QtWebChannel import QWebChannel

from meet_core import api

ENGINE = Path(__file__).resolve().parent / "engine"
PAGE = QUrl.fromLocalFile(str(ENGINE / "call.html"))
# the name of a command's single value, as call.js reads it (else "id": mic, camera, speaker)
VALUE_KEY = {"reaction": "reaction", "layout": "layout", "pin": "session", "muteOther": "session", "theme": "theme"}


class Bridge(QObject):
    """What the page sees (window.bridge): its configuration, a way to tell, a way to be told."""
    command = Signal(str)               # Python -> page (JSON)
    received = Signal("QVariantMap")    # page -> Python

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self._config = json.dumps(config)

    @Property(str, constant=True)
    def config(self):
        return self._config

    @Slot(str)
    def event(self, text):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return
        if isinstance(data, dict):
            self.received.emit(data)


class Call(QObject):
    """A call in one conversation. ready -> the page can be loaded (url, channel); state -> people, mute…"""
    ready = Signal()
    stateChanged = Signal()
    event = Signal("QVariantMap")       # every message of the page (reactions, hands, joins), for the QML
    failed = Signal(str)                # signaling | network | password | no_media | …
    ended = Signal()
    _done = Signal(object, object)      # (callback, result) back on the UI thread

    def __init__(self, talk: api.Talk, token, nick="", audio=True, video=True, theme="light", labels=None,
                 people=None, avatars=None, password="", devices=None, blur=False, vision=None, parent=None):
        super().__init__(parent)
        self.talk, self.token, self.nick = talk, token, nick
        self._want = {"audio": audio, "video": video}
        self._theme, self._labels = theme, labels or {}
        self._people, self._avatars = people or {}, avatars or {}
        self._password = password
        self._devices = devices or {}
        self._blur, self._vision = blur, vision
        self._state = {}
        self._page_ready = False
        self._pending = None            # the settings for the page, until it is loaded
        self._rejoins = 0               # a long cut: the session of the conversation asked again (twice at most)
        self.detail = ""                # the last failure as the server told it (for the logs, never shown)
        self._phase = "idle"            # idle | preview | preparing | ready | joining | in_call | leaving | ended
        self.bridge = None
        self.channel = None
        self._done.connect(lambda cb, result: cb(result), Qt.ConnectionType.QueuedConnection)

    # ---- for the QML / the window ----------------------------------------------------------------------------
    @Property(str, notify=stateChanged)
    def phase(self):
        return self._phase

    @Property("QVariantMap", notify=stateChanged)
    def state(self):
        return dict(self._state)

    @Property(QUrl, constant=True)
    def url(self):
        return PAGE

    @Property(QObject, notify=ready)
    def webChannel(self):
        """For a QWebEnginePage (Python). QML's WebEngineView takes a WebChannel of its own: see bridgeObject."""
        return self.channel

    @Property(QObject, notify=ready)
    def bridgeObject(self):
        return self.bridge

    def _bg(self, work, then):
        def run():
            try:
                result = work()
            except Exception as error:  # noqa: BLE001 (any failure is a failed step, told to the user)
                result = error
            self._done.emit(then, result)
        threading.Thread(target=run, daemon=True).start()

    def _set_phase(self, phase):
        self._phase = phase
        self.stateChanged.emit()

    # ---- the steps -------------------------------------------------------------------------------------------
    def _make_page(self):
        """The bridge of the page (its configuration without the cloud's settings yet): `ready` loads it."""
        if self.bridge is not None:
            return
        config = {
            "settings": None, "token": self.token, "nick": self.nick, "userId": self.talk.user,
            "audio": self._want["audio"], "video": self._want["video"], "theme": self._theme,
            "labels": self._labels, "people": self._people, "avatars": self._avatars,
            "selfAvatar": self._avatars.get(self.talk.user, ""),
            "mic": self._devices.get("mic", ""), "camera": self._devices.get("camera", ""),
            "blur": self._blur, "vision": self._vision,
        }
        self.bridge = Bridge(config, self)
        self.bridge.received.connect(self._on_page)
        self.channel = QWebChannel(self)
        self.channel.registerObject("bridge", self.bridge)
        self.ready.emit()

    @Slot()
    def preview(self):
        """The page with our camera and microphone, before the call: the user joins with prepare()."""
        if self._phase not in ("idle", "ended"):
            return
        self._make_page()
        self._set_phase("preview")

    @Slot()
    def prepare(self):
        """Signaling settings + a Nextcloud session in the conversation; then the page connects."""
        if self._phase not in ("idle", "ended", "preview"):
            return
        self._make_page()
        self._set_phase("preparing")

        def work():
            status, settings = self.talk.signaling_settings(self.token)
            if status != 200 or not isinstance(settings, dict):
                self.detail = f"settings {status} {settings}"
                return ("network" if status == 0 else "signaling", None, None)
            status, joined = self.talk.join(self.token, self._password)
            if status == 403:
                return ("password", None, None)
            if status != 200 or not isinstance(joined, dict):
                self.detail = f"join {status} {joined}"
                return ("network" if status == 0 else "join", None, None)
            return (None, settings, joined)

        def then(result):
            if isinstance(result, Exception):
                result = ("network", None, None)
            error, settings, joined = result
            if self._phase != "preparing":            # hung up meanwhile: leave the conversation we just entered
                if joined:
                    self._bg(lambda: self.talk.leave(self.token), lambda _r: None)
                return
            if error:
                self._set_phase("ended")
                self.failed.emit(error)
                return
            if settings.get("signalingMode", "external") != "external" or not settings.get("server"):
                # without the high-performance backend there is no SFU: not supported (Orneos always has it)
                self._set_phase("ended")
                self._bg(lambda: self.talk.leave(self.token), lambda _r: None)
                self.failed.emit("signaling")
                return
            settings["backend"] = self.talk.server + "/ocs/v2.php/apps/spreed/api/v3/signaling/backend"
            self._pending = {"settings": settings, "ncSession": joined.get("sessionId", ""),
                             "nick": self.nick or joined.get("displayName", "")}
            self._set_phase("ready")
            self._connect_page()
        self._bg(work, then)

    def _connect_page(self):
        if self._page_ready and self._pending:
            data, self._pending = self._pending, None
            self.send("connect", data)

    def _on_page(self, data):
        kind = data.get("type")
        if kind == "loaded":
            self._page_ready = True
            self._connect_page()
        elif kind == "state":
            self._state = data.get("state") or {}
            self.stateChanged.emit()
        elif kind == "roomJoined" and self._phase == "ready":
            self._join_call()
        elif kind == "rejoined" and self._phase == "in_call":
            self._join_call(again=True)             # back after a cut: in the call again, then publish
        elif kind == "error":
            code = data.get("code") or "error"
            if code in ("no_media", "device", "screen_failed", "blur", "blur_slow"):
                self.event.emit(data)
            elif data.get("room") and self._phase == "in_call" and self._rejoins < 2:
                self._rejoins += 1                      # our session of the conversation expired during the cut
                self._new_session()
            else:                                     # the signaling refused us: this call cannot go on
                self.failed.emit(code)
                self.hangup()
        elif kind in ("ended",):
            self.hangup()
        self.event.emit(data)

    def _new_session(self):
        """A new Nextcloud session in the conversation, for the page to enter its room again (rejoin)."""
        def then(result):
            status, joined = result if isinstance(result, tuple) else (0, None)
            if self._phase != "in_call":
                return
            if status != 200 or not isinstance(joined, dict):
                self.detail = f"rejoin {status} {joined}"
                self.failed.emit("network" if status == 0 else "join")
                self.hangup()
                return
            self.send("rejoin", {"ncSession": joined.get("sessionId", "")})
        self._bg(lambda: self.talk.join(self.token, self._password), then)

    def _join_call(self, again=False):
        """POST /call, then the page publishes. again: back after a cut (the call was already ours)."""
        self._set_phase("joining")
        flags = api.IN_CALL
        if self._state.get("hasAudio", True):
            flags |= api.WITH_AUDIO
        if self._state.get("hasVideo", True):
            flags |= api.WITH_VIDEO

        def then(result):
            status = result[0] if isinstance(result, tuple) else 0
            if self._phase != "joining":
                return
            if status != 200:
                self.detail = f"call {status} {result[1] if isinstance(result, tuple) else result}"
                self._set_phase("ended")
                self.send("leave")
                self._bg(lambda: self.talk.leave(self.token), lambda _r: None)
                self.failed.emit("network" if status == 0 else "call")
                return
            self._set_phase("in_call")
            self.send("inCall")
        self._bg(lambda: self.talk.join_call(self.token, flags), then)

    @Slot(str, "QVariant")
    def send(self, cmd, value=None):
        """A command for the page: audio, video, screen, hand (bool), reaction (emoji), mic/camera/speaker (id)…"""
        if not self.bridge:
            return
        data = {"cmd": cmd}
        if isinstance(value, bool):
            data["on"] = value
        elif isinstance(value, dict):
            data.update(value)
        elif value is not None:
            data[VALUE_KEY.get(cmd, "id")] = value
        self.bridge.command.emit(json.dumps(data))

    @Slot()
    @Slot(bool)
    def hangup(self, for_all=False):
        if self._phase in ("leaving", "ended", "idle"):
            return
        was_in = self._phase in ("in_call", "joining")
        self._set_phase("leaving")
        self.send("leave")

        def work():
            if was_in:
                self.talk.leave_call(self.token, for_all)
            self.talk.leave(self.token)

        def then(_result):
            self._set_phase("ended")
            self.ended.emit()
        self._bg(work, then)


def setup_page(page, on_screen_request=None):
    """A QWebEnginePage for the call: media without a gesture, our camera and microphone allowed (the page is
    ours, the system asks the user), the screen chosen by on_screen_request(request) or the first screen."""
    from PySide6.QtWebEngineCore import QWebEnginePermission, QWebEngineSettings
    settings = page.settings()
    settings.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
    settings.setAttribute(QWebEngineSettings.WebAttribute.ScreenCaptureEnabled, True)
    settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
    media = {QWebEnginePermission.PermissionType.MediaAudioCapture,
             QWebEnginePermission.PermissionType.MediaVideoCapture,
             QWebEnginePermission.PermissionType.MediaAudioVideoCapture,
             QWebEnginePermission.PermissionType.DesktopVideoCapture,
             QWebEnginePermission.PermissionType.DesktopAudioVideoCapture}

    def permission(request):
        if request.permissionType() in media and request.origin().isLocalFile():
            request.grant()
        else:
            request.deny()
    page.permissionRequested.connect(permission)

    def desktop(request):
        if on_screen_request:
            on_screen_request(request)
            return
        screens = request.screensModel()
        if screens.rowCount() > 0:
            request.selectScreen(screens.index(0, 0))
        else:
            request.cancel()
    page.desktopMediaRequested.connect(desktop)
