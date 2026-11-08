"""The sounds of calls (réglage « Sonnerie et sons d'appel »): the ring while a call waits for an answer, a short
sound when someone joins or leaves the call we are in.

They are Talk's own sounds, read from our cloud the first time (apps/spreed/img/*.ogg, the ones Talk web plays) and
kept in the cache: nothing to ship, the same sounds as on the other devices. Played by QtMultimedia; without it
(a Plume built without), the system's notification still rings: nothing else changes.
"""
import threading
import time

from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Signal

import cloud
import system

DIR = system.CACHE / "meet-sounds"
FILES = {"ring": "LibremPhoneCall.ogg", "join": "join_call.ogg", "leave": "leave_call.ogg"}
RING_MS = 45000                     # as the card of the window: then it is a missed call, not a ring


class Sounds(QObject):
    _fetched = Signal(str)          # the sound now in the cache: play it if still wanted

    def __init__(self, app, library, parent=None):
        super().__init__(parent)
        self.app, self.library = app, library
        self._fetched.connect(self._ready, Qt.ConnectionType.QueuedConnection)
        self._players = {}
        self._wanted = ""           # the sound waiting for its file
        self._ringing = ""          # the conversation that rings
        self._fetching = set()
        self._last_short = 0.0       # people already in the call arrive together: one sound, not one each
        self._stop = QTimer(self)
        self._stop.setSingleShot(True)
        self._stop.timeout.connect(lambda: self.ring(""))
        try:
            from PySide6 import QtMultimedia  # noqa: F401
            self._available = True
        except ImportError:
            self._available = False

    def _on(self):
        return self._available and bool(self.app.pref("sounds"))

    # ---- what bundle.py asks --------------------------------------------------------------------------------
    def ring(self, token):
        """Ring for this conversation ("" = stop)."""
        if token == self._ringing:
            return
        self._ringing = token
        if not token:
            self._stop.stop()
            self._halt("ring")
            return
        self._stop.start(RING_MS)
        self._play("ring", loop=True)

    def stop_ring(self, token=""):
        if not token or token == self._ringing:
            self.ring("")

    def play(self, name):
        """A short sound: « join » or « leave »."""
        if time.time() - self._last_short < 1.5 or self._ringing:
            return
        self._last_short = time.time()
        self._play(name, loop=False)

    # ---- playing ------------------------------------------------------------------------------------------
    def _play(self, name, loop):
        if not self._on():
            return
        path = DIR / FILES[name]
        if not path.exists():
            self._wanted = name
            self._fetch(name)
            return
        from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
        player = self._players.get(name)
        if player is None:
            player = QMediaPlayer(self)
            output = QAudioOutput(player)
            output.setVolume(0.8 if name == "ring" else 0.5)
            player.setAudioOutput(output)
            player.setSource(QUrl.fromLocalFile(str(path)))
            self._players[name] = player
        player.setLoops(QMediaPlayer.Loops.Infinite if loop else 1)
        player.stop()
        player.play()

    def _halt(self, name):
        player = self._players.get(name)
        if player is not None:
            player.stop()
        if self._wanted == name:
            self._wanted = ""

    def _fetch(self, name):
        talk = self.library.talk()
        if talk is None or name in self._fetching:
            return
        self._fetching.add(name)

        def work():
            status, data = cloud._call(f"{talk.server}/apps/spreed/img/{FILES[name]}", talk.user, talk.password,
                                       headers={"Accept": "audio/ogg"})
            if status == 200 and data and data[:4] == b"OggS":
                DIR.mkdir(parents=True, exist_ok=True)
                tmp = DIR / (FILES[name] + ".part")
                tmp.write_bytes(data)
                tmp.replace(DIR / FILES[name])
            self._fetched.emit(name)
        threading.Thread(target=work, daemon=True).start()

    def _ready(self, name):
        self._fetching.discard(name)
        if self._wanted != name or not (DIR / FILES[name]).exists():
            return
        self._wanted = ""
        if name == "ring":
            if self._ringing:
                self._play("ring", loop=True)
        else:
            self._play(name, loop=False)
