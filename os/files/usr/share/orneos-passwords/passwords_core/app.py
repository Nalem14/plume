"""What the QML sees of the window: the account Connect stored, small preferences, the clipboard, links.

The account is the app password of Orneos Connect (cloud.account()); its files are watched, so connecting,
reconnecting or signing out elsewhere shows here without a restart.

The clipboard: a copied password or code is marked secret, so the clipboard history keeps it out (Klipper:
x-kde-passwordManagerHint; Windows: ExcludeClipboardContentFromMonitorProcessing; macOS: the concealed type
of nspasteboard.org), and it is cleared after a while if it is still there. A window closed meanwhile stays
alive in the background until then: on Wayland, the clipboard empties when the app that owns it quits.
"""
import json
import os
import time

from PySide6.QtCore import QFileSystemWatcher, QMimeData, QObject, Property, QSize, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QGuiApplication

import cloud
import system
from qmlvalue import js_property
from passwords_core.strings import language, strings

CONFIG = cloud.CFG.parent / "passwords.json"
PREFS = {
    "lock_minutes": 10,        # 0: only when the screen locks
    "clipboard_seconds": 60,
    "sort": "name",            # name | recent
    "show_wifi": True,
    "ignored": [],             # entries whose security warnings were dismissed
    "category": "all",
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
    showRequested = Signal(str)          # an entry to open (KRunner, --show)
    actionRequested = Signal(str, str)   # "new" | "security" | "wifi" | "generator" | "otpauth", value
    copied = Signal(str)                 # what was copied: "password", "username", "code"…

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
        self._secret = ""
        self._closed = False
        self._clear = QTimer(self)
        self._clear.setSingleShot(True)
        self._clear.timeout.connect(self._clear_clipboard)
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

    @Property(QSize, constant=True)
    def windowSize(self):
        size = self._config.get("window")
        if not (isinstance(size, list) and len(size) == 2):
            size = [1180, 760]
        return QSize(max(820, int(size[0])), max(540, int(size[1])))

    @Slot(int, int)
    def saveWindow(self, width, height):
        self._config["window"] = [width, height]
        self._write()

    # ---- clipboard -------------------------------------------------------------------------------------
    @Slot(str, str)
    def copy(self, value, what=""):
        """Copy a value. Secrets (password, code, Wi-Fi key) are hidden from Klipper and cleared later."""
        if not value:
            return
        secret = what in ("password", "code", "wifi", "field")
        if secret:
            data = QMimeData()
            data.setText(value)
            data.setData("x-kde-passwordManagerHint", b"secret")
            if system.WINDOWS:
                for name in ("ExcludeClipboardContentFromMonitorProcessing", "CanIncludeInClipboardHistory",
                             "CanUploadToCloudClipboard"):
                    data.setData(f'application/x-qt-windows-mime;value="{name}"', b"\0\0\0\0")
            elif system.MACOS:
                data.setData("application/x-qt-mac-pasteboard-mime;value=\"org.nspasteboard.ConcealedType\"", b"")
            QGuiApplication.clipboard().setMimeData(data)
            self._secret = value
            self._clear.start(max(10, int(self._prefs.get("clipboard_seconds") or 60)) * 1000)
        else:
            QGuiApplication.clipboard().setText(value)
        self.copied.emit(what)

    def shutdown(self):
        """Quitting: a secret still in the clipboard goes with the app. (It must be cleared before Python
        tears down: the QMimeData made here would otherwise be freed twice, and the app would crash on exit.)"""
        board = QGuiApplication.clipboard()
        if self._secret and board.text() == self._secret:
            board.clear()
        self._secret = ""

    def _clear_clipboard(self):
        board = QGuiApplication.clipboard()
        if self._secret and board.text() == self._secret:
            board.clear()
        self._secret = ""
        if self._closed:
            QGuiApplication.quit()

    @Slot()
    def windowClosed(self):
        """The window was closed: quit, or stay in the background until the copied secret is cleared."""
        self._closed = True
        if not (self._secret and self._clear.isActive()):
            QGuiApplication.quit()

    # ---- the rest of the desktop -----------------------------------------------------------------------
    @Slot(str)
    def openUrl(self, url):
        if url.startswith(("https://", "http://")):
            cloud.open_url(url)

    @Slot(str)
    def openCloud(self, path):
        cloud.open_url(cloud.cloud_link(path or "/apps/passwords/"))

    @Slot()
    def openConnect(self):
        system.launch("connect")

    @Slot()
    def openAccount(self):
        slug = {"fr": "tableau-de-bord/compte", "en": "dashboard/account", "de": "dashboard/konto"}[self._lang]
        cloud.open_url(f"https://orneos.eu/{self._lang}/{slug}#security")

    @Slot(str)
    def askOrnis(self, question):
        # Orneos OS: the top-bar applet (Super+O); Plume: its Ornis module; else the cloud's assistant
        if system.in_process("ornis"):
            system.launch("ornis", *(["--ask=" + question] if question else []))
        elif not system.spawn(["/usr/libexec/orneos-ornis", "--ask", question] if question
                              else ["/usr/libexec/orneos-ornis", "--open"]):
            cloud.open_url(cloud.cloud_link("/apps/assistant/"))

    def handle_args(self, args, activation_token=""):
        """--show ID (KRunner), --new, --security, --wifi, --generator, otpauth://… (a link in Firefox)."""
        i = 0
        while i < len(args):
            arg = args[i]
            if arg == "--show" and i + 1 < len(args):
                self.showRequested.emit(args[i + 1])
                i += 1
            elif arg in ("--new", "--security", "--wifi", "--generator"):
                self.actionRequested.emit(arg[2:], "")
            elif arg.lower().startswith("otpauth://"):
                self.actionRequested.emit("otpauth", arg)
            i += 1
        if activation_token:
            os.environ["XDG_ACTIVATION_TOKEN"] = activation_token
        self.raiseRequested.emit()

    @Slot(result=str)
    def modifier(self):
        """The key held during a click on the list: "shift" (a range), "ctrl" (one more), or ""."""
        held = QGuiApplication.queryKeyboardModifiers()
        if held & Qt.KeyboardModifier.ShiftModifier:
            return "shift"
        return "ctrl" if held & Qt.KeyboardModifier.ControlModifier else ""

    @Slot(str, int, result=str)
    def plural(self, key, count):
        """A count in words: "1 élément", "3 éléments" (French takes the singular for 0 and 1)."""
        one, _, many = self._t.get(key, "").partition("|")
        text = one if (count <= 1 if self._lang == "fr" else count == 1) or not many else many
        return text.replace("%1", str(count))

    @Slot(int, result=str)
    def ago(self, timestamp):
        """« à l'instant », « il y a 5 min », « hier », or the date."""
        if not timestamp:
            return ""
        delta = time.time() - int(timestamp)
        t = self._t
        if delta < 60:
            return t["ago_now"]
        if delta < 3600:
            return t["ago_minutes"].replace("%1", str(int(delta // 60)))
        if delta < 86400:
            return t["ago_hours"].replace("%1", str(int(delta // 3600)))
        if delta < 2 * 86400:
            return t["ago_yesterday"]
        months = t["months"].split(",")
        tm = time.localtime(int(timestamp))
        same_year = tm.tm_year == time.localtime().tm_year
        if self._lang == "en":
            return f"{months[tm.tm_mon - 1]} {tm.tm_mday}" + ("" if same_year else f", {tm.tm_year}")
        day = f"{tm.tm_mday}." if self._lang == "de" else str(tm.tm_mday)
        return f"{day} {months[tm.tm_mon - 1]}" + ("" if same_year else f" {tm.tm_year}")
