"""Plume updates itself (Windows, macOS, AppImage; a newer .deb or .rpm is offered to the system's installer).

At start, then every 6 hours, Plume asks orneos.eu for the release of its channel (stable or unstable): version,
file, size, SHA-256 and an Ed25519 signature of "plume|<package>|<version>|<sha256>". The file is downloaded in the
background and kept only if both match: the binaries are not signed by Apple or Microsoft, this signature (key in
private/clients/plume-ed25519.key, public half below) is what says the file comes from Orneos. Then « Restart to
update », or the update is installed when Plume quits:
- Windows: the Inno Setup installer, silent, per user (no administrator), Plume started again on /RELAUNCH;
- macOS: Plume.app taken out of the DMG, swapped in by a small script once Plume has quit, started again;
- AppImage: the file replaced in place (rename), started again;
- .deb, .rpm: handed to the system's software installer (it asks for the administrator password itself).
A version is never replaced by an older one: going back means publishing a newer one.
"""
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
from base64 import b64decode
from pathlib import Path

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

import system

FEED = os.environ.get("PLUME_UPDATE_FEED") or "https://orneos.eu/updates/plume"
# the public half of private/clients/plume-ed25519.key (PLUME_UPDATE_KEY: the tests' own)
PUBLIC_KEY = os.environ.get("PLUME_UPDATE_KEY") or "wlSRVr3CTRogYQRRUVFedQRKOFyvAd/OqvxR8hx0n9Q="
EVERY = 6 * 3600 * 1000
FOLDER = system.CACHE / "updates"


def package():
    """How this Plume was installed: windows, mac, appimage, deb, rpm, or "" (from the sources, Orneos OS's own)."""
    marker = system.SHARE / "orneos" / "package"          # written by the .deb and the .rpm
    try:
        written = marker.read_text().strip()
    except OSError:
        written = ""
    if written in ("deb", "rpm"):
        return written
    if not system.FROZEN:
        return ""
    if system.WINDOWS:
        return "windows"
    if system.MACOS:
        return "mac"
    return "appimage" if os.environ.get("APPIMAGE") else ""


def newer(candidate, current):
    def parts(version):
        return [int(p) for p in str(version).split("-")[0].split(".") if p.isdigit()]
    return parts(candidate) > parts(current)


def verify(message: bytes, signature: str) -> bool:
    """The Ed25519 signature of the release, with the public key Plume carries."""
    try:
        from cryptography.exceptions import InvalidSignature  # noqa: PLC0415 - in Plume's packages
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey  # noqa: PLC0415
        key = Ed25519PublicKey.from_public_bytes(b64decode(PUBLIC_KEY))
        key.verify(b64decode(signature), message)
        return True
    except (ImportError, ValueError, InvalidSignature):
        return False
    except Exception:  # noqa: BLE001 - a malformed key or signature is a refusal, never a crash
        return False


def signed_text(kind, version, sha256):
    return f"plume|{kind}|{version}|{sha256}".encode()


class Updater(QObject):
    """For QML: state "" | "downloading" | "ready" | "installing" | "error", the version waiting, and installNow()."""
    changed = Signal()
    _update = Signal(str, str)
    _installed = Signal(bool)

    def __init__(self, version, channel="stable"):
        super().__init__()
        self._current = version
        self._channel = channel
        self._kind = package()
        self._state, self._version, self._file = "", "", None
        self._busy = threading.Lock()
        self._update.connect(self._apply)
        self._installed.connect(self._after_install)
        self._timer = QTimer(self)
        self._timer.setInterval(EVERY)
        self._timer.timeout.connect(self.check)
        if self._kind:
            self._timer.start()
            QTimer.singleShot(20_000, self.check)       # not while Plume opens

    def _apply(self, state, version):
        self._state, self._version = state, version
        self.changed.emit()

    @Property(bool, constant=True)
    def enabled(self):
        return bool(self._kind)

    @Property(bool, constant=True)
    def replaces(self):
        """True when Plume puts the update in itself (restart); a .deb or .rpm goes to the system's installer."""
        return self._kind in ("windows", "mac", "appimage")

    @Property(str, notify=changed)
    def state(self):
        return self._state

    @Property(str, notify=changed)
    def version(self):
        return self._version

    @Property(str, constant=True)
    def current(self):
        return self._current

    @Property(str, notify=changed)
    def channel(self):
        return self._channel

    @Slot(str)
    def setChannel(self, channel):
        if channel in ("stable", "unstable") and channel != self._channel:
            self._channel = channel
            self.changed.emit()
            self.check()

    @Slot()
    def check(self):
        if self._kind and self._state != "ready" and self._busy.acquire(blocking=False):
            threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            self._check_and_fetch()
        finally:
            self._busy.release()

    def _check_and_fetch(self):
        query = urllib.parse.urlencode({"package": self._kind, "arch": platform.machine().lower(),
                                        "version": self._current, "channel": self._channel})
        try:
            req = urllib.request.Request(f"{FEED}?{query}", headers={"User-Agent": f"Plume/{self._current}"})
            with urllib.request.urlopen(req, timeout=20) as res:
                release = json.loads(res.read() or b"{}")
        except (urllib.error.URLError, OSError, ValueError):
            return
        version = str(release.get("version") or "")
        if not version or not newer(version, self._current):
            return
        sha256, signature, url = str(release.get("sha256") or ""), str(release.get("signature") or ""), str(release.get("url") or "")
        if not verify(signed_text(self._kind, version, sha256), signature) or not url.startswith("https://"):
            return
        self._update.emit("downloading", version)
        FOLDER.mkdir(parents=True, exist_ok=True)
        name = Path(urllib.parse.urlparse(url).path).name
        target = FOLDER / name
        part = target.with_name(name + ".part")
        digest = hashlib.sha256()
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": f"Plume/{self._current}"}),
                                        timeout=60) as res, open(part, "wb") as out:
                while chunk := res.read(1 << 20):
                    digest.update(chunk)
                    out.write(chunk)
        except (urllib.error.URLError, OSError):
            part.unlink(missing_ok=True)
            return self._update.emit("error", version)
        if digest.hexdigest() != sha256.lower():
            part.unlink(missing_ok=True)
            return self._update.emit("error", version)
        os.replace(part, target)
        for old in FOLDER.iterdir():                     # earlier downloads
            if old != target:
                old.unlink(missing_ok=True)
        self._file = target
        self._update.emit("ready", version)

    # ---- installing ---------------------------------------------------------------------------------------
    @Slot()
    def installNow(self):
        """« Restart to update »: install, start Plume again, quit. On macOS the new Plume.app is copied out of
        the DMG first (seconds): in the background, the window says so instead of freezing."""
        if self._state != "ready":
            return
        if not self.replaces:
            self._install(relaunch=True)             # the system's installer takes it (Qt: main thread)
            return
        self._apply("installing", self._version)
        threading.Thread(target=lambda: self._installed.emit(self._install(relaunch=True)), daemon=True).start()

    def _after_install(self, ok):
        if ok:
            from PySide6.QtCore import QCoreApplication  # noqa: PLC0415
            QCoreApplication.quit()
        else:
            self._apply("ready", self._version)

    def install_on_quit(self):
        """Plume quits with an update waiting: it goes in now, without starting Plume again. The windows go
        first: the copy out of the DMG (macOS) takes a few seconds."""
        if self._state == "ready" and self._kind in ("windows", "mac", "appimage"):
            from PySide6.QtGui import QGuiApplication  # noqa: PLC0415
            for window in QGuiApplication.allWindows():
                window.hide()
            self._install(relaunch=False)

    def _install(self, relaunch):
        path = self._file
        if path is None or not path.exists():
            return False
        if self._kind == "windows":
            args = [str(path), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CURRENTUSER"]
            if relaunch:
                args.append("/RELAUNCH")
            return system.spawn(args)
        if self._kind == "mac":
            return self._install_mac(path, relaunch)
        if self._kind == "appimage":
            current = Path(os.environ["APPIMAGE"])
            fresh = current.with_name(current.name + ".new")
            shutil.copyfile(path, fresh)
            fresh.chmod(0o755)
            os.replace(fresh, current)               # the running one keeps its open file
            path.unlink(missing_ok=True)
            return system.spawn([str(current)]) if relaunch else True
        if self._kind in ("deb", "rpm"):
            system.open_url(str(path))               # the system's software installer
            return False
        return False

    def _install_mac(self, dmg, relaunch):
        bundle = Path(sys.executable).resolve()
        while bundle.suffix != ".app" and bundle != bundle.parent:
            bundle = bundle.parent
        if bundle.suffix != ".app":
            return False
        staging = Path(tempfile.mkdtemp(prefix="plume-update-"))
        mount = staging / "dmg"
        try:
            subprocess.run(["hdiutil", "attach", "-nobrowse", "-readonly", "-mountpoint", str(mount), str(dmg)],
                           check=True, capture_output=True, timeout=120)
            app = next(mount.glob("*.app"))
            subprocess.run(["ditto", str(app), str(staging / app.name)], check=True, capture_output=True, timeout=300)
        except (OSError, subprocess.SubprocessError, StopIteration):
            return False
        finally:
            subprocess.run(["hdiutil", "detach", str(mount), "-quiet"], capture_output=True, timeout=60)
        script = staging / "swap.sh"
        script.write_text(
            "#!/bin/sh\n"
            f"while kill -0 {os.getpid()} 2>/dev/null; do sleep 0.3; done\n"
            f'rm -rf "{bundle}.old" && mv "{bundle}" "{bundle}.old" && mv "{staging / app.name}" "{bundle}" '
            f'&& rm -rf "{bundle}.old"\n'
            + (f'open "{bundle}"\n' if relaunch else "")
            + f'rm -rf "{staging}"\n')
        script.chmod(0o700)
        dmg.unlink(missing_ok=True)
        return system.spawn(["/bin/sh", str(script)])
