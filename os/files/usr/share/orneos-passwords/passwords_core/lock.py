"""The lock, like macOS: the passwords show only after the session password (or a finger, when this computer
has a reader with an enrolled finger), at start, when the screen locks, and after some minutes away.

The finger: fprintd on Linux, Touch ID on a Mac (plume-touchid, a small helper beside Plume, plume/macos),
Windows Hello on Windows (its fingerprint, face or PIN, through PowerShell). The system only answers yes or no.

The session password is checked by unix_chkpwd, the helper PAM itself uses (it only checks the password of
the user who runs it); in Plume on Windows by LogonUser (the password of the Windows account, not its PIN),
on macOS by dscl -authonly: nothing is stored, nothing goes to the network. A few wrong attempts make the next
ones wait. An account without a password (or a system without the helper) has nothing to unlock with: the
app then stays open, and Settings says so.
"""
import getpass
import os
import shutil
import subprocess
import sys
import threading
import time

from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot

import system

try:
    from PySide6.QtDBus import QDBusConnection, QDBusInterface
except ImportError:                       # tests without D-Bus
    QDBusConnection = QDBusInterface = None

# Windows Hello from PowerShell: the WinRT call awaited through .NET (no module to install)
HELLO = r"""
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and
    $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, $type) { $t = $asTask.MakeGenericMethod($type).Invoke($null, @($op)); $t.Wait(-1) | Out-Null; $t.Result }
$v = [Windows.Security.Credentials.UI.UserConsentVerifier, Windows.Security.Credentials.UI, ContentType = WindowsRuntime]
if ($env:PLUME_HELLO_REASON) {
    Await ($v::RequestVerificationAsync($env:PLUME_HELLO_REASON)) ([Windows.Security.Credentials.UI.UserConsentVerificationResult])
} else {
    Await ($v::CheckAvailabilityAsync()) ([Windows.Security.Credentials.UI.UserConsentVerifierAvailability])
}
"""


def _touchid():
    """The Touch ID helper beside Plume's own executable (Plume.app/Contents/MacOS)."""
    path = os.path.join(os.path.dirname(os.path.realpath(sys.executable)), "plume-touchid")
    return path if os.access(path, os.X_OK) else ""


def _hello(reason=""):
    """Popen of the PowerShell above: availability, or a check with this reason."""
    env = dict(os.environ, PLUME_HELLO_REASON=reason)
    return subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", HELLO],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, env=env,
                            creationflags=0x08000000)    # CREATE_NO_WINDOW


CHKPWD = next((p for p in ("/usr/sbin/unix_chkpwd", "/sbin/unix_chkpwd", "/usr/bin/unix_chkpwd") if os.path.exists(p)), "")


def _windows_logon(password):
    """(accepted, Windows error code)."""
    import ctypes  # noqa: PLC0415 - Windows only
    from ctypes import wintypes  # noqa: PLC0415
    advapi, kernel = ctypes.WinDLL("advapi32", use_last_error=True), ctypes.WinDLL("kernel32")
    token = wintypes.HANDLE()
    domain = os.environ.get("USERDOMAIN") or "."
    # LOGON32_LOGON_INTERACTIVE, LOGON32_PROVIDER_DEFAULT: what the session itself was opened with
    ok = advapi.LogonUserW(getpass.getuser(), domain, password, 2, 0, ctypes.byref(token))
    if ok:
        kernel.CloseHandle(token)
        return True, 0
    return False, ctypes.get_last_error()


def _windows_check(password):
    return _windows_logon(password)[0]


def _macos_check(password):
    try:
        res = subprocess.run(["/usr/bin/dscl", "/Search", "-authonly", getpass.getuser(), password],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return res.returncode == 0


def check_password(password):
    """True when it is the session password of the user running this."""
    if system.WINDOWS:
        return bool(password) and _windows_check(password)
    if system.MACOS:
        return bool(password) and _macos_check(password)
    if not CHKPWD:
        return False
    try:
        res = subprocess.run([CHKPWD, getpass.getuser(), "nonull"], input=password.encode() + b"\0",
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return res.returncode == 0


def has_password():
    """False for an account that has no password at all (nothing to unlock with)."""
    if system.WINDOWS or system.MACOS:
        # Windows: not asked ahead (a wrong try counts towards the account's lockout); an account without a
        # password unlocks with an empty field once, then stays open (Lock.unlock)
        return True
    if not CHKPWD:
        return False
    try:
        res = subprocess.run([CHKPWD, getpass.getuser(), "nullok"], input=b"\0",
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return True
    return res.returncode != 0


class Lock(QObject):
    changed = Signal()
    failed = Signal(str)                  # why ("wrong", "wait", "finger"; "fingercancel": put aside, not failed)
    _result = Signal(bool, str)
    _finger_state = Signal(str)

    def __init__(self, app):
        super().__init__()
        self._app = app
        self._can = os.environ.get("PASSWORDS_NO_LOCK") != "1"
        self._locked = self._can
        self._checking = False
        self._failures = 0
        self._wait_until = 0.0
        self._finger = ""                 # "fprint", "touchid", "hello" or "" (none)
        self._finger_proc = None
        self._away_since = None
        self._active = self._shown = True
        self._result.connect(self._checked)
        self._finger_state.connect(self._set_finger)
        if self._can:
            threading.Thread(target=self._probe, daemon=True).start()
        self._screen = None
        if QDBusInterface is not None and self._can:
            bus = QDBusConnection.sessionBus()
            if bus.isConnected():
                self._screen = QDBusInterface("org.freedesktop.ScreenSaver", "/ScreenSaver",
                                              "org.freedesktop.ScreenSaver", bus)
        self._timer = QTimer(self)
        self._timer.setInterval(15000)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _probe(self):
        if not has_password():
            self._can = False
            self._result.emit(True, "nopassword")
            return
        self._finger_state.emit(self._finger_kind())

    @staticmethod
    def _finger_kind():
        try:
            if system.MACOS:
                helper = _touchid()
                return "touchid" if helper and subprocess.run([helper], timeout=10).returncode == 0 else ""
            if system.WINDOWS:
                out, _ = _hello().communicate(timeout=30)
                return "hello" if out.strip() == "Available" else ""
            if shutil.which("fprintd-list") and shutil.which("fprintd-verify"):
                out = subprocess.run(["fprintd-list", getpass.getuser()], capture_output=True, text=True, timeout=10).stdout
                return "fprint" if "finger" in out.lower() and "no fingers" not in out.lower() and " - #" in out else ""
        except (OSError, subprocess.SubprocessError):
            pass
        return ""

    def _set_finger(self, kind):
        self._finger = kind
        self.changed.emit()

    # ---- state -----------------------------------------------------------------------------------------
    @Property(bool, notify=changed)
    def locked(self):
        return self._locked

    @Property(bool, notify=changed)
    def available(self):
        """Something to unlock with (the account has a password)."""
        return self._can

    @Property(bool, notify=changed)
    def checking(self):
        return self._checking

    @Property(bool, notify=changed)
    def fingerprint(self):
        return bool(self._finger)

    @Property(str, notify=changed)
    def fingerprintKind(self):
        """"fprint" (the reader is listened to all along), "touchid" or "hello" (a dialog of the system)."""
        return self._finger

    @Property(bool, constant=True)
    def blankAllowed(self):
        """Windows: an empty field is how an account without a password says so."""
        return system.WINDOWS

    @Slot()
    def lock(self):
        if self._can and not self._locked:
            self.stopFingerprint()
            self._locked = True
            self.changed.emit()

    # ---- unlocking -------------------------------------------------------------------------------------
    @Slot(str)
    def unlock(self, password):
        if not self._locked or self._checking:
            return
        if time.monotonic() < self._wait_until:
            self.failed.emit("wait")
            return
        self._checking = True
        self.changed.emit()
        if not password and system.WINDOWS:
            def blank():
                ok, error = _windows_logon("")
                # ERROR_ACCOUNT_RESTRICTION: Windows refuses blank passwords to logons, so the account has none
                self._result.emit(ok or error == 1327, "blank")
            threading.Thread(target=blank, daemon=True).start()
            return
        threading.Thread(target=lambda: self._result.emit(check_password(password), "password"), daemon=True).start()

    @Slot(str)
    def startFingerprint(self, reason=""):
        if not self._finger or not self._locked or self._finger_proc is not None:
            return
        kind = self._finger

        def run():
            how = "finger"
            try:
                if kind == "touchid":
                    self._finger_proc = subprocess.Popen([_touchid(), "verify", reason or "Plume"])
                    code = self._finger_proc.wait(timeout=120)
                    ok, how = code == 0, "fingercancel" if code == 2 else "finger"
                elif kind == "hello":
                    self._finger_proc = _hello(reason or "Plume")
                    out, _ = self._finger_proc.communicate(timeout=120)
                    ok = out.strip() == "Verified"
                    how = "finger" if ok or out.strip() == "RetriesExhausted" else "fingercancel"
                else:
                    self._finger_proc = subprocess.Popen(["fprintd-verify", getpass.getuser()], stdout=subprocess.PIPE,
                                                         stderr=subprocess.STDOUT, text=True)
                    out, _ = self._finger_proc.communicate(timeout=40)
                    ok = "verify-match" in out
            except (OSError, subprocess.SubprocessError):
                ok = False
                if self._finger_proc:
                    self._finger_proc.kill()
            self._finger_proc = None
            self._result.emit(ok, how)
        threading.Thread(target=run, daemon=True).start()

    @Slot()
    def stopFingerprint(self):
        proc = self._finger_proc
        if proc is not None:
            try:
                proc.terminate()
            except OSError:
                pass

    def _checked(self, ok, how):
        if how == "nopassword" or (how == "blank" and ok):
            self._can = self._checking = False
            self._locked = False
            self.changed.emit()
            return
        if how == "blank":
            how = "password"
        if how == "password":
            self._checking = False
        if ok:
            self._failures = 0
            self._locked = False
            self._away_since = None
            self.stopFingerprint()
        elif how == "password":
            self._failures += 1
            if self._failures >= 3:
                self._wait_until = time.monotonic() + min(60, 5 * 2 ** (self._failures - 3))
            self.failed.emit("wrong")
        elif self._locked and how in ("finger", "fingercancel"):
            self.failed.emit(how)
        self.changed.emit()

    # ---- locking by itself -----------------------------------------------------------------------------
    def _call(self, method):
        if self._screen is None or not self._screen.isValid():
            return None
        reply = self._screen.call(method)
        args = reply.arguments() if reply is not None else []
        return args[0] if args else None

    def _tick(self):
        if not self._can or self._locked:
            return
        if self._call("GetActive"):
            self.lock()
            return
        minutes = int(self._app.pref("lock_minutes") or 0)
        if not minutes:
            return
        idle = self._call("GetSessionIdleTime")          # milliseconds, from KWin
        away = time.monotonic() - self._away_since if self._away_since else 0
        if (isinstance(idle, int) and idle >= minutes * 60000) or away >= minutes * 60:
            self.lock()

    @Slot(bool)
    def setActive(self, active):
        """The window is in front (True) or not: minutes away count from when it went behind."""
        self._active = active
        self._away()

    @Slot(bool)
    def setShown(self, shown):
        """The view is the one shown (in Plume, another module in front counts as away)."""
        self._shown = shown
        self._away()

    def _away(self):
        here = self._active and self._shown
        self._away_since = None if here else (self._away_since or time.monotonic())
