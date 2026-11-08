"""Voice messages (QML: `voice`): record one with the microphone, listen to those of the conversation.

Recorded by QtMultimedia in MP3, else in WAV (mono, 16 kHz: small enough), into the cache; sent like a file with
Talk's `voice-message` type (library.sendVoice). ⚠️ Talk keeps that type for audio/mpeg and audio/wav only: any
other file (AAC, Opus) arrives as a plain attachment in Talk web, Android and iOS. Listening downloads the file
once (cache) and plays it here. Without QtMultimedia (a Plume built without it), `available` is false and the
microphone button is not shown: nothing else changes.
"""
import threading
import time
import urllib.parse
from pathlib import Path

from PySide6.QtCore import Property, QObject, Qt, QTimer, QUrl, Signal, Slot

import cloud
import system

DIR = system.CACHE / "meet-voice"


class Voice(QObject):
    changed = Signal()
    tick = Signal()
    recorded = Signal(str)          # the file of a finished recording, to send
    failed = Signal(str)
    _fetched = Signal(str, str)     # key, local path ("" = failed)

    def __init__(self, library, parent=None):
        super().__init__(parent)
        self.library = library
        self._fetched.connect(self._play_file, Qt.ConnectionType.QueuedConnection)
        self._recording = False
        self._started = 0.0
        self._send_after = False
        self._playing = ""          # the key of the message playing
        self._loading = ""
        self._recorder = self._session = self._input = None
        self._player = self._output = None
        self._path = None
        try:
            from PySide6 import QtMultimedia  # noqa: F401
            self._available = True
        except ImportError:
            self._available = False
        self._timer = QTimer(self)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self.tick)

    @Property(bool, constant=True)
    def available(self):
        return self._available

    @Property(bool, notify=changed)
    def recording(self):
        return self._recording

    @Property(int, notify=tick)
    def elapsed(self):
        return int(time.time() - self._started) if self._recording else 0

    @Property(str, notify=changed)
    def playing(self):
        return self._playing

    @Property(str, notify=changed)
    def loading(self):
        return self._loading

    @Property(float, notify=tick)
    def progress(self):
        if not self._player or not self._player.duration():
            return 0.0
        return self._player.position() / self._player.duration()

    @Property(int, notify=tick)
    def position(self):
        return int(self._player.position() / 1000) if self._player else 0

    # ---- recording ---------------------------------------------------------------------------------------
    def _format(self):
        from PySide6.QtMultimedia import QMediaFormat
        for container, codec, ext in ((QMediaFormat.FileFormat.MP3, QMediaFormat.AudioCodec.MP3, "mp3"),
                                      (QMediaFormat.FileFormat.Wave, QMediaFormat.AudioCodec.Wave, "wav")):
            if codec in QMediaFormat(container).supportedAudioCodecs(QMediaFormat.ConversionMode.Encode):
                out = QMediaFormat(container)
                out.setAudioCodec(codec)
                return out, ext
        return None, ""

    @Slot()
    def record(self):
        if not self._available or self._recording:
            return
        from PySide6.QtMultimedia import QAudioInput, QMediaCaptureSession, QMediaDevices, QMediaRecorder
        if QMediaDevices.defaultAudioInput().isNull():
            self.failed.emit(self.library.app.t["voice_no_mic"])
            return
        fmt, ext = self._format()
        if fmt is None:
            self.failed.emit(self.library.app.t["voice_failed"])
            return
        self.stop_playing()
        DIR.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y-%m-%d %H-%M-%S")
        self._path = DIR / f"{self.library.app.t['voice_file']} {stamp}.{ext}"
        self._session = QMediaCaptureSession(self)
        self._input = QAudioInput(self)
        mic = self.library.app.pref("mic")
        for device in QMediaDevices.audioInputs():
            if mic and bytes(device.id()).decode(errors="ignore") == mic:
                self._input.setDevice(device)
        self._session.setAudioInput(self._input)
        self._recorder = QMediaRecorder(self)
        self._session.setRecorder(self._recorder)
        self._recorder.setMediaFormat(fmt)
        if ext == "wav":                   # uncompressed: the voice only (about 2 MB a minute)
            self._recorder.setAudioChannelCount(1)
            self._recorder.setAudioSampleRate(16000)
        else:
            self._recorder.setQuality(QMediaRecorder.Quality.HighQuality)
        self._recorder.setOutputLocation(QUrl.fromLocalFile(str(self._path)))
        self._recorder.recorderStateChanged.connect(self._state)
        self._recorder.errorOccurred.connect(lambda *_: self._fail())
        self._send_after = False                      # only « send » of this recording sends it
        self._recorder.record()
        self._recording = True
        self._started = time.time()
        self._timer.start()
        self.changed.emit()

    @Slot(bool)
    def finish(self, send):
        """Stop recording; send it (true) or throw it away."""
        if not self._recording or self._recorder is None:
            return
        self._send_after = send and time.time() - self._started >= 1
        self._recorder.stop()

    def _state(self, state):
        from PySide6.QtMultimedia import QMediaRecorder
        if state != QMediaRecorder.RecorderState.StoppedState:
            return
        self._recording = False
        self._timer.stop()
        path = self._recorder.actualLocation().toLocalFile() or str(self._path)
        self._recorder.deleteLater()
        self._recorder = None
        for done in (self._session, self._input):
            if done is not None:
                done.deleteLater()
        self._session = self._input = None
        self.changed.emit()
        if self._send_after:
            self.recorded.emit(path)
        else:
            try:
                Path(path).unlink(missing_ok=True)
            except OSError:
                pass

    def _fail(self):
        if self._recording:
            self._recording = False
            self._timer.stop()
            self.changed.emit()
        self.failed.emit(self.library.app.t["voice_failed"])

    # ---- listening ---------------------------------------------------------------------------------------
    @Slot(str, "QVariantMap")
    def play(self, key, file):
        """Play (or pause) the voice message `key`, its file as the message gives it (id, path, name)."""
        if not self._available:
            return
        if key == self._playing and self._player is not None:
            from PySide6.QtMultimedia import QMediaPlayer
            if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                self._player.pause()
                self._timer.stop()
            else:
                self._player.play()
                self._timer.start()
            self.changed.emit()
            return
        file = {k: (v.toVariant() if hasattr(v, "toVariant") else v) for k, v in dict(file).items()}
        if file.get("local"):                     # ours, still on its way: the recording itself
            self._play_file(key, QUrl(file["local"]).toLocalFile())
            return
        ext = str(file.get("name") or "").rpartition(".")[2] or "ogg"
        local = DIR / f"{file.get('id')}.{ext}"
        if local.exists():
            self._play_file(key, str(local))
            return
        talk = self.library.talk()
        if talk is None or not file.get("path"):
            return
        self._loading = key
        self.changed.emit()

        def work():
            url = f"/remote.php/dav/files/{urllib.parse.quote(talk.user)}/{urllib.parse.quote(file['path'].lstrip('/'))}"
            status, data = cloud.dav(talk.server, talk.user, talk.password, url, "GET")
            if status != 200 or not data:
                return ""
            DIR.mkdir(parents=True, exist_ok=True)
            local.write_bytes(data)
            return str(local)
        threading.Thread(target=lambda: self._fetched.emit(key, work()), daemon=True).start()

    def _play_file(self, key, path):
        if self._loading == key:
            self._loading = ""
        if not path:
            self.changed.emit()
            self.failed.emit(self.library.app.t["voice_unavailable"])
            return
        from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
        if self._player is None:
            self._player = QMediaPlayer(self)
            self._output = QAudioOutput(self)
            self._player.setAudioOutput(self._output)
            self._player.mediaStatusChanged.connect(self._media_status)
        self._player.stop()
        self._player.setSource(QUrl.fromLocalFile(path))
        self._player.play()
        self._playing = key
        self._timer.start()
        self.changed.emit()

    def _media_status(self, status):
        from PySide6.QtMultimedia import QMediaPlayer
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.stop_playing()

    @Slot()
    def stop_playing(self):
        if self._player is not None:
            self._player.stop()
        self._playing = ""
        self._timer.stop()
        self.changed.emit()
