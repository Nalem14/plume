"""The Orneos account of Plume where there is no Orneos Connect (Windows, macOS, another Linux).

Signing in is the cloud's Login Flow v2, as Connect does it: the browser opens the cloud's page (single sign-on,
two-step verification there), and the cloud hands back an app password, revocable in its settings. It goes to the
system's keychain; connect.json says who and where, so every app reads the account as on Orneos OS
(cloud.account()) and sees it arrive or leave by watching that file. Without a keychain, the password goes to
notify.token (only this user can read it), as Connect keeps it.
Signing out revokes the app password in the cloud, then forgets it here.
"""
import json
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from base64 import b64encode

from PySide6.QtCore import Property, QObject, Signal, Slot

import cloud
import system

POLL_EVERY, POLL_FOR = 2, 20 * 60


def device_name():
    """What the cloud lists under « Appareils & sessions »: Plume and this computer."""
    system_name = "Windows" if system.WINDOWS else "macOS" if system.MACOS else "Linux"
    return f"Plume ({system_name}, {socket.gethostname()})"


def _request(url, data=None, auth=None, method=None):
    headers = {"User-Agent": device_name(), "OCS-APIRequest": "true", "Accept": "application/json"}
    if auth:
        headers["Authorization"] = "Basic " + b64encode(f"{auth[0]}:{auth[1]}".encode()).decode()
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    req = urllib.request.Request(url, body, headers, method=method)
    with urllib.request.urlopen(req, timeout=20) as res:
        return json.loads(res.read() or b"{}")


def save(server, user, password):
    """The account for every app: the password in the keychain (else notify.token), then connect.json."""
    server = server.rstrip("/")
    keychain = system.secret_set(cloud.secret_entry(server, user), password)
    if keychain:
        cloud.TOKEN.unlink(missing_ok=True)
    else:
        system.private_write(cloud.TOKEN, password + "\n")
    system.private_write(cloud.CFG, json.dumps({"server": server, "user": user, "keychain": keychain,
                                                "by": "plume", "at": int(time.time())}))


def managed_here():
    """True when Plume signed this computer in (not Orneos Connect): Plume may sign it out."""
    try:
        return json.loads(cloud.CFG.read_text(encoding="utf-8")).get("by") == "plume"
    except (OSError, ValueError):
        return False


def sign_out():
    """Revoke the app password in the cloud (best effort: offline, it stays listed there), then forget it."""
    account = cloud.account()
    if account:
        server, user, password = account
        try:
            _request(server + "/ocs/v2.php/core/apppassword", auth=(user, password), method="DELETE")
        except (urllib.error.URLError, OSError, ValueError):
            pass
        system.secret_delete(cloud.secret_entry(server, user))
    cloud.TOKEN.unlink(missing_ok=True)
    cloud.CFG.unlink(missing_ok=True)


class SignIn(QObject):
    """The sign-in of Plume, for QML: state "" (nothing going on), "waiting" (the browser is open), "error"."""
    changed = Signal()
    _update = Signal(str, str)
    _open = Signal(str)                      # the browser from the main thread (Qt's way, see system.open_url)

    def __init__(self, texts, own=True):
        super().__init__()
        self._t = texts
        self._own = own                      # False on Orneos OS: Orneos Connect signs the computer in
        self._state, self._error, self._url = "", "", ""
        self._cancel = threading.Event()
        self._update.connect(self._apply)
        self._open.connect(system.open_url)

    def _apply(self, state, error):
        self._state, self._error = state, error
        self.changed.emit()

    @Property(str, notify=changed)
    def state(self):
        return self._state

    @Property(str, notify=changed)
    def error(self):
        return self._error

    @Property(bool, constant=True)
    def own(self):
        return self._own

    @Property(bool, notify=changed)
    def canSignOut(self):
        return self._own and managed_here()

    @Slot()
    def start(self):
        if self._state == "waiting":
            self.reopen()
            return
        self._cancel.clear()
        self._apply("waiting", "")
        threading.Thread(target=self._flow, daemon=True).start()

    @Slot()
    def cancel(self):
        self._cancel.set()
        self._apply("", "")

    @Slot()
    def reopen(self):
        if self._url:
            system.open_url(self._url)

    @Slot()
    def signOut(self):
        def run():
            sign_out()
            self._update.emit("", "")            # canSignOut changes
        threading.Thread(target=run, daemon=True).start()

    def _flow(self):
        try:
            start = _request(cloud.CLOUD + "/index.php/login/v2", data={})
            self._url = start["login"]
            self._open.emit(self._url)
            token, endpoint = start["poll"]["token"], start["poll"]["endpoint"]
            granted, deadline = None, time.time() + POLL_FOR
            while not granted:
                if self._cancel.wait(POLL_EVERY):
                    return
                if time.time() > deadline:
                    raise TimeoutError
                try:
                    granted = _request(endpoint, data={"token": token})
                except urllib.error.HTTPError as error:
                    if error.code != 404:            # 404 = not granted yet
                        raise
        except TimeoutError:
            return self._update.emit("error", self._t.get("signin_timeout", ""))
        except (urllib.error.URLError, OSError, ValueError, KeyError):
            return self._update.emit("error", self._t.get("signin_network", ""))
        save(granted["server"], granted["loginName"], granted["appPassword"])
        self._update.emit("", "")
