"""What the QML sees of the window: the account Connect stored, small preferences, counts in words, the other
apps of the desktop.

The account is the app password of Orneos Connect (cloud.account()); its files are watched, so connecting,
reconnecting or signing out elsewhere shows here without a restart.
"""
import json
import os
import time

from PySide6.QtCore import QFileSystemWatcher, QObject, Property, QSize, Qt, Signal, Slot
from PySide6.QtGui import QGuiApplication

import cloud
import system
from qmlvalue import js_property
from photos_core.strings import language, strings

CONFIG = cloud.CFG.parent / "photos.json"
PREFS = {
    "mode": "all",               # the library by years, months or every photo
    "zoom": 1,                   # 0 small, 1 medium, 2 large thumbnails
    "info": False,               # the viewer's details open
    "memory_titles": {},         # titles Ornis gave the memories
    "places_mode": "cities",     # the places as cities or on the map
    "map_view": {},              # where the map was left: {lat, lon, zoom}
    "album_sort": "recent",      # the albums: newest, by name, the fullest first
}


def initials(name):
    parts = [p for p in str(name).replace(".", " ").replace("_", " ").split() if p]
    if not parts:
        return "?"
    return parts[0][:2].upper() if len(parts) == 1 else (parts[0][0] + parts[-1][0]).upper()


class App(QObject):
    accountChanged = Signal()
    prefsChanged = Signal()
    toast = Signal(str)
    raiseRequested = Signal()
    showRequested = Signal(int)             # a photo to open (a link from Notes, KRunner)
    actionRequested = Signal(str, str)      # "import" | "view" | "search", value

    def __init__(self):
        super().__init__()
        self._t = strings()
        self._lang = language()
        try:
            self._config = json.loads(CONFIG.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self._config = {}
        if not isinstance(self._config, dict):
            self._config = {}
        self._prefs = dict(PREFS)
        self._prefs.update({k: v for k, v in self._config.items() if k in PREFS})
        self._account = None
        self._profile = {}
        self._watcher = QFileSystemWatcher(self)
        self._watcher.directoryChanged.connect(self._files_changed)
        self._watcher.fileChanged.connect(self._files_changed)
        cloud.CFG.parent.mkdir(parents=True, exist_ok=True)
        self._watcher.addPath(str(cloud.CFG.parent))
        self._files_changed()

    # ---- account ---------------------------------------------------------------------------------------
    def _files_changed(self, *_):
        for path in (cloud.CFG, cloud.TOKEN):
            if path.exists() and str(path) not in self._watcher.files():
                self._watcher.addPath(str(path))
        account = cloud.account()
        if account != self._account:
            self._account = account
            self._profile = {}
            self.accountChanged.emit()

    def account(self):
        return self._account

    def set_profile(self, profile):
        self._profile = profile or {}
        self.accountChanged.emit()

    @Property(bool, notify=accountChanged)
    def connected(self):
        return self._account is not None

    @js_property(notify=accountChanged)
    def profile(self):
        if not self._account:
            return {}
        user = self._account[1]
        name = self._profile.get("name") or user
        email = self._profile.get("email") or (user if "@" in user else f"{user}@orneos.eu")
        return {"user": user, "name": name, "email": email, "initials": initials(name)}

    # ---- texts, preferences, window --------------------------------------------------------------------
    @js_property(constant=True)
    def t(self):
        return self._t

    @Property(str, constant=True)
    def lang(self):
        return self._lang

    @js_property(notify=prefsChanged)
    def prefs(self):
        return dict(self._prefs)

    def pref(self, key):
        return self._prefs.get(key, PREFS.get(key))

    @Slot(str, "QVariant")
    def setPref(self, key, value):
        if key not in PREFS:
            return
        value = value.toVariant() if hasattr(value, "toVariant") else value
        if self._prefs.get(key) == value:
            return
        self._prefs[key] = value
        self._config[key] = value
        self._write()
        self.prefsChanged.emit()

    def _write(self):
        try:
            CONFIG.parent.mkdir(parents=True, exist_ok=True)
            CONFIG.write_text(json.dumps(self._config))
        except OSError:
            pass

    @Property(str, constant=True)
    def mapCache(self):
        """Where the map keeps its tiles (shown again offline)."""
        return str(system.CACHE / "photos-map")

    @Property(QSize, constant=True)
    def windowSize(self):
        size = self._config.get("window")
        if not (isinstance(size, list) and len(size) == 2):
            size = [1280, 820]
        return QSize(max(800, int(size[0])), max(540, int(size[1])))

    @Slot(int, int)
    def saveWindow(self, width, height):
        self._config["window"] = [width, height]
        self._write()

    # ---- the rest of the desktop -----------------------------------------------------------------------
    @Slot(str)
    def openUrl(self, url):
        if url.startswith(("https://", "http://")):
            cloud.open_url(url)

    @Slot(str)
    def openCloud(self, path):
        cloud.open_url(cloud.cloud_link(path or "/apps/memories/"))

    @Slot()
    def openConnect(self):
        system.launch("connect")

    @Slot(str)
    def copyText(self, text):
        QGuiApplication.clipboard().setText(text)

    @Slot(float, float)
    def openMap(self, lat, lon):
        cloud.open_url(f"https://www.openstreetmap.org/?mlat={lat:.5f}&mlon={lon:.5f}#map=14/{lat:.5f}/{lon:.5f}")

    def handle_args(self, args, activation_token=""):
        """--show=FILEID, --view=VIEW, --search=WORDS, --import FILE… (« Ajouter à Photos » in Dolphin)."""
        files, taking = [], False
        for arg in args:
            if taking and not arg.startswith("--"):
                path = arg.removeprefix("file://")
                if os.path.exists(path):
                    files.append(os.path.abspath(path))
                continue
            taking = arg == "--import"
            if arg.startswith("--show="):
                ref = arg.split("=", 1)[1]
                if ref.isdigit():
                    self.showRequested.emit(int(ref))
            elif arg.startswith("--view="):
                self.actionRequested.emit("view", arg.split("=", 1)[1])
            elif arg.startswith("--search="):
                self.actionRequested.emit("search", arg.split("=", 1)[1])
        if files:
            self.actionRequested.emit("import", json.dumps(files))
        if activation_token:
            os.environ["XDG_ACTIVATION_TOKEN"] = activation_token
        self.raiseRequested.emit()

    @Slot(result=str)
    def modifier(self):
        """The key held during a click: "shift" (a range), "ctrl" (one more), or ""."""
        held = QGuiApplication.queryKeyboardModifiers()
        if held & Qt.KeyboardModifier.ShiftModifier:
            return "shift"
        return "ctrl" if held & Qt.KeyboardModifier.ControlModifier else ""

    @Slot(str, int, result=str)
    def plural(self, key, count):
        """A count in words: "1 photo", "3 photos" (French takes the singular for 0 and 1)."""
        one, _, many = self._t.get(key, "").partition("|")
        text = one if (count <= 1 if self._lang == "fr" else count == 1) or not many else many
        return text.replace("%1", f"{count:,}".replace(",", " " if self._lang == "fr" else "." if self._lang == "de" else ","))

    @Slot(int, result=str)
    def ago(self, timestamp):
        """« il y a 3 min », « il y a 2 h », then the date."""
        if not timestamp:
            return ""
        delta = time.time() - int(timestamp)
        if delta < 60:
            return self._t["ago_now"]
        if delta < 3600:
            return self._t["ago_minutes"].replace("%1", str(int(delta // 60)))
        if delta < 86400:
            return self._t["ago_hours"].replace("%1", str(int(delta // 3600)))
        days = int(delta // 86400)
        return self.plural("ago_days", days)

    @Slot(int, result=str)
    def duration(self, seconds):
        seconds = max(0, int(seconds))
        return f"{seconds // 60}:{seconds % 60:02d}" if seconds < 3600 else \
            f"{seconds // 3600}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"
