"""Dictation and reading aloud for Ornis in the native apps (Ornis, Plume), as the other assistants have them.

Dictation: the microphone records (QtMultimedia, MP3 else WAV mono 16 kHz, as Meet's voice messages) into the cache;
at « stop » the file is read, deleted, and sent to the cloud (/ornis/transcribe: Voxtral, counted in the day's Ornis
allowance, nothing kept); its text comes back to the box. Escape (cancel) throws the recording away.
Reading aloud: QtTextToSpeech with a voice of the system (on the device, nothing sent; on Orneos OS, Piper's natural
voices through speech-dispatcher); `canSpeak` is false without the module or a voice for the language, and the
button is not shown.
Without QtMultimedia (a build without it), `available` is false and the microphone is not shown: nothing else changes.
"""
import re
import threading
import time
from pathlib import Path

from PySide6.QtCore import Property, QObject, Qt, QTimer, QUrl, Signal, Slot

import system

DIR = system.CACHE / "ornis-dictation"
MAX_SECONDS = 600
PIPER = re.compile(r"^[a-z]{2,3}_[A-Z]{2}-.+-(x_low|low|medium|high)$")


class Dictation(QObject):
    changed = Signal()
    tick = Signal()
    text = Signal(str)              # what was said, for the box
    failed = Signal(str)            # a message to show
    speakingChanged = Signal()
    _done = Signal(str, str)        # text, problem

    def __init__(self, transcribe, strings, lang="fr", parent=None):
        """transcribe(data: bytes, mime: str) -> str, run in a thread; raises with .code 429 when the allowance is out."""
        super().__init__(parent)
        self._transcribe = transcribe
        self._t = strings
        self._lang = lang
        self._done.connect(self._on_done, Qt.ConnectionType.QueuedConnection)
        self._recording = self._busy = self._cancel = False
        self._started = 0.0
        self._recorder = self._session = self._input = None
        self._path = None
        try:
            from PySide6 import QtMultimedia  # noqa: F401
            self._available = True
        except ImportError:
            self._available = False
        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._on_tick)
        self._speech = None
        self._speaking = ""
        for old in DIR.glob("*") if DIR.exists() else []:    # a recording left by a crash: never kept
            old.unlink(missing_ok=True)

    @Property(bool, constant=True)
    def available(self):
        return self._available

    @Property(bool, notify=changed)
    def recording(self):
        return self._recording

    @Property(bool, notify=changed)
    def busy(self):
        return self._busy

    @Property(int, notify=tick)
    def elapsed(self):
        return int(time.time() - self._started) if self._recording else 0

    # ---- dictation ---------------------------------------------------------------------------------------------
    def _format(self):
        from PySide6.QtMultimedia import QMediaFormat
        for container, codec, ext, mime in ((QMediaFormat.FileFormat.MP3, QMediaFormat.AudioCodec.MP3, "mp3", "audio/mpeg"),
                                            (QMediaFormat.FileFormat.Wave, QMediaFormat.AudioCodec.Wave, "wav", "audio/wav")):
            if codec in QMediaFormat(container).supportedAudioCodecs(QMediaFormat.ConversionMode.Encode):
                out = QMediaFormat(container)
                out.setAudioCodec(codec)
                return out, ext, mime
        return None, "", ""

    @Slot()
    def toggle(self):
        if self._recording:
            self.stop()
        elif not self._busy:
            self.start()

    @Slot()
    def start(self):
        if not self._available or self._recording or self._busy:
            return
        from PySide6.QtMultimedia import QAudioInput, QMediaCaptureSession, QMediaDevices, QMediaRecorder
        if QMediaDevices.defaultAudioInput().isNull():
            self.failed.emit(self._t["dictate_no_mic"])
            return
        fmt, ext, self._mime = self._format()
        if fmt is None:
            self.failed.emit(self._t["dictate_failed"])
            return
        self.stop_speaking()
        DIR.mkdir(parents=True, exist_ok=True)
        self._path = DIR / f"dictation-{int(time.time() * 1000)}.{ext}"
        self._session = QMediaCaptureSession(self)
        self._input = QAudioInput(self)
        self._session.setAudioInput(self._input)
        self._recorder = QMediaRecorder(self)
        self._session.setRecorder(self._recorder)
        self._recorder.setMediaFormat(fmt)
        self._recorder.setAudioChannelCount(1)
        self._recorder.setAudioSampleRate(16000)
        if ext == "mp3":
            self._recorder.setAudioBitRate(48000)
        self._recorder.setOutputLocation(QUrl.fromLocalFile(str(self._path)))
        self._recorder.recorderStateChanged.connect(self._state)
        self._recorder.errorOccurred.connect(lambda *_: self._fail())
        self._cancel = False
        self._recorder.record()
        self._recording = True
        self._started = time.time()
        self._timer.start()
        self.changed.emit()

    @Slot()
    def stop(self):
        """Stop and transcribe (a recording under a second is dropped: a click by mistake)."""
        if self._recording and self._recorder is not None:
            self._cancel = time.time() - self._started < 1
            self._recorder.stop()

    @Slot()
    def cancel(self):
        if self._recording and self._recorder is not None:
            self._cancel = True
            self._recorder.stop()

    def _on_tick(self):
        if self._recording and time.time() - self._started >= MAX_SECONDS:
            self.stop()
        self.tick.emit()

    def _state(self, state):
        from PySide6.QtMultimedia import QMediaRecorder
        if state != QMediaRecorder.RecorderState.StoppedState:
            return
        self._recording = False
        self._timer.stop()
        path = Path(self._recorder.actualLocation().toLocalFile() or str(self._path))
        self._recorder.deleteLater()
        self._recorder = None
        for done in (self._session, self._input):
            if done is not None:
                done.deleteLater()
        self._session = self._input = None
        if self._cancel:
            path.unlink(missing_ok=True)
            self.changed.emit()
            return
        self._send(path, self._mime)

    def _send(self, path, mime):
        self._busy = True
        self.changed.emit()

        def work():
            try:
                data = path.read_bytes()
            except OSError:
                data = b""
            path.unlink(missing_ok=True)          # never kept, even when the cloud fails
            if not data:
                self._done.emit("", self._t["dictate_failed"])
                return
            try:
                said = self._transcribe(data, mime)
            except Exception as error:  # noqa: BLE001 - any failure is the same message for the user
                self._done.emit("", self._t["dictate_quota"] if getattr(error, "code", 0) == 429 else self._t["dictate_failed"])
                return
            self._done.emit(said, "" if said else self._t["dictate_none"])
        threading.Thread(target=work, daemon=True).start()

    def _on_done(self, said, problem):
        self._busy = False
        self.changed.emit()
        if said:
            self.text.emit(said)
        elif problem:
            self.failed.emit(problem)

    def _fail(self):
        if self._recording:
            self._recording = False
            self._timer.stop()
            self.changed.emit()
        self.failed.emit(self._t["dictate_failed"])

    # ---- reading aloud ------------------------------------------------------------------------------------------
    def _engine(self):
        if self._speech is None:
            try:
                from PySide6.QtTextToSpeech import QTextToSpeech
            except ImportError:
                self._speech = False
                return None
            engine = QTextToSpeech(self)
            # every region of the language: speech-dispatcher files Piper's English under en_US, eSpeak's under en_GB…
            voices = []
            for locale in engine.availableLocales():
                if locale.name().lower().startswith(self._lang):
                    engine.setLocale(locale)
                    voices += engine.availableVoices()
            if not voices:
                engine.deleteLater()
                self._speech = False
                return None
            # Orneos OS: Piper's natural voices (named like fr_FR-siwis-medium) before eSpeak NG's robotic ones
            voices.sort(key=lambda v: not PIPER.match(v.name()))
            engine.setVoice(voices[0])
            engine.stateChanged.connect(self._speech_state)
            self._speech = engine
        return self._speech or None

    @Property(bool, constant=True)
    def canSpeak(self):
        return self._engine() is not None

    @Property(str, notify=speakingChanged)
    def speaking(self):
        return self._speaking

    @Slot(str, str)
    def speak(self, key, markdown_text):
        """Read an answer (its key: the message id); the same again, or another, stops it."""
        engine = self._engine()
        again = self._speaking == key
        self.stop_speaking()
        if engine is None or again:
            return
        self._speaking = key
        self.speakingChanged.emit()
        engine.say(plain(markdown_text))

    @Slot(str, result=str)
    def plainText(self, markdown_text):
        """An answer as it is said, for a screen reader's announcement too"""
        return plain(markdown_text)

    @Slot()
    def stop_speaking(self):
        if self._speech:
            self._speech.stop()
        if self._speaking:
            self._speaking = ""
            self.speakingChanged.emit()

    def _speech_state(self, state):
        from PySide6.QtTextToSpeech import QTextToSpeech
        if state in (QTextToSpeech.State.Ready, QTextToSpeech.State.Error) and self._speaking:
            self._speaking = ""
            self.speakingChanged.emit()


def plain(text: str) -> str:
    """Markdown as it is said: no marks, links by their words, code blocks left out."""
    text = re.sub(r"```.*?```", " ", text or "", flags=re.S)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"^\s{0,3}(#{1,6}|>|[-*+]|\d+[.)])\s+", "", text, flags=re.M)
    text = re.sub(r"[*_`~|]+", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n(?: ?\n)+", "\n", text).strip()
