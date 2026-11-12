"""Where an Orneos app runs: Orneos OS (KDE, the files of Connect) or Plume on Windows, macOS or another Linux.

The only place that knows the system. Everything is chosen by what is there (kwallet-query, notify-send,
a tray), not by the name of the system: the Plume .rpm on Fedora takes the KDE path when KDE is there.
Packaged (PyInstaller), the files of /usr/share sit next to the executable (sys._MEIPASS), in the same tree.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path

_NON_ASCII = re.compile(r"[^\x00-\x7f]+")

WINDOWS = sys.platform == "win32"
MACOS = sys.platform == "darwin"
FROZEN = bool(getattr(sys, "frozen", False))
# /usr/share (or the bundle): orneos/, orneos-plume/, orneos-notes/… side by side
SHARE = Path(getattr(sys, "_MEIPASS", "") or Path(__file__).resolve().parent.parent)


def _home(*parts):
    return Path.home().joinpath(*parts)


def _xdg(name, *default):
    return Path(os.environ.get(name) or _home(*default))


if WINDOWS:
    _roaming = Path(os.environ.get("APPDATA") or _home("AppData", "Roaming"))
    _local = Path(os.environ.get("LOCALAPPDATA") or _home("AppData", "Local"))
    CONFIG, DATA, STATE = _roaming / "Orneos", _roaming / "Orneos", _local / "Orneos" / "State"
    CACHE = _local / "Orneos" / "Cache"
elif MACOS:
    CONFIG = DATA = STATE = _home("Library", "Application Support", "Orneos")
    CACHE = _home("Library", "Caches", "Orneos")
else:
    CONFIG = _xdg("XDG_CONFIG_HOME", ".config") / "orneos"
    DATA = _xdg("XDG_DATA_HOME", ".local", "share") / "orneos"
    STATE = _xdg("XDG_STATE_HOME", ".local", "state") / "orneos"
    CACHE = _xdg("XDG_CACHE_HOME", ".cache") / "orneos"


def runtime_dir() -> Path:
    """Short-lived files (a message opened in another app): gone at logout where the system allows it."""
    base = os.environ.get("XDG_RUNTIME_DIR")
    return Path(base) if base and not (WINDOWS or MACOS) else CACHE


def user_id() -> str:
    """Who runs the app, for the names of the single-instance sockets (one per user and per app)."""
    if hasattr(os, "getuid"):
        return str(os.getuid())
    return (os.environ.get("USERNAME") or "user").lower()


def fonts_dir() -> Path:
    system = Path("/usr/share/fonts/orneos")
    return system if system.is_dir() else SHARE / "fonts" / "orneos"


def add_fonts() -> None:
    from PySide6.QtGui import QFontDatabase  # noqa: PLC0415 - after the QGuiApplication
    for font in fonts_dir().glob("*.ttf"):
        QFontDatabase.addApplicationFont(str(font))


def icon(name: str):
    """The app's icon: the theme's on Orneos OS, the bundled one elsewhere. None in Plume.app: macOS shows
    the bundle's icon in the Dock (with the margin of its icon grid), a window icon would replace it with the
    bare tile, bigger than every other app."""
    from PySide6.QtGui import QIcon  # noqa: PLC0415
    if MACOS and FROZEN:
        return QIcon()
    themed = QIcon.fromTheme(name)
    if not themed.isNull():
        return themed
    for path in (SHARE / "icons" / "hicolor" / "scalable" / "apps" / f"{name}.svg",   # os/tools/apps.py
                 SHARE / "orneos" / "icons" / f"{name}.svg", SHARE / "orneos" / "icons" / f"{name}.png"):
        if path.is_file():
            return QIcon(str(path))
    return themed


# ---- opening things ----------------------------------------------------------------------------------
def open_url(url: str) -> None:
    """A web page, a file or a mailto: in the system's handler. Qt's way first: it hands the
    activation token over on Wayland and works on every system; xdg-open as the last resort.
    Qt only from the main thread: from a worker, macOS (NSWorkspace) crashes the app a moment later."""
    if not url:
        return
    try:
        from PySide6.QtCore import QUrl  # noqa: PLC0415
        from PySide6.QtGui import QDesktopServices, QGuiApplication  # noqa: PLC0415
        if QGuiApplication.instance() is not None and threading.current_thread() is threading.main_thread():
            target = QUrl(url) if "://" in url or url.startswith("mailto:") else QUrl.fromLocalFile(url)
            if QDesktopServices.openUrl(target):
                return
    except ImportError:
        pass
    opener = "open" if MACOS else None if WINDOWS else "xdg-open"
    if WINDOWS:
        os.startfile(url)  # noqa: S606 - the user's own link
    elif opener and shutil.which(opener):
        subprocess.Popen([opener, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def reveal(path: str) -> None:
    """A file shown selected in the system's file manager (Explorer, Finder, Dolphin, Files…); a folder opened there.
    Linux: the FileManager1 interface every file manager implements, else its folder in the default handler."""
    target = Path(path)
    if target.is_dir():
        open_url(str(target))
        return
    if WINDOWS:
        if spawn(["explorer", "/select," + str(target)]):
            return
    elif MACOS:
        if spawn(["open", "-R", str(target)]):
            return
    else:
        try:
            from PySide6.QtCore import QUrl  # noqa: PLC0415
            from PySide6.QtDBus import QDBusConnection, QDBusMessage  # noqa: PLC0415
            msg = QDBusMessage.createMethodCall("org.freedesktop.FileManager1", "/org/freedesktop/FileManager1",
                                                "org.freedesktop.FileManager1", "ShowItems")
            msg.setArguments([[QUrl.fromLocalFile(str(target)).toString()], ""])
            reply = QDBusConnection.sessionBus().call(msg, timeout=3000)
            if reply.type() != QDBusMessage.MessageType.ErrorMessage:
                return
        except Exception:  # noqa: BLE001 - no D-Bus (another session): the folder instead
            pass
    open_url(str(target.parent))


def native_dialogs() -> None:
    """The system's own file picker for « Joindre », « Enregistrer sous », « Importer »… Before the QGuiApplication.
    Windows and macOS always have it. On Linux, Qt finds it through its theme plugin for the desktop (KDE's, GTK's),
    which the packages of Plume (AppImage, .deb) do not carry: Qt then drew its own picker, plain and at the root of
    the disk. They carry the portal's (xdg-desktop-portal: the dialog of KDE, GNOME and the others), chosen here when
    the desktop's own is missing. Without a portal running, Qt falls back on its picker, as before."""
    if WINDOWS or MACOS or os.environ.get("QT_QPA_PLATFORMTHEME"):
        return
    try:
        from PySide6.QtCore import QLibraryInfo  # noqa: PLC0415
        themes = Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath)) / "platformthemes"
        names = {p.name.lower() for p in themes.iterdir()} if themes.is_dir() else set()
    except Exception:  # noqa: BLE001
        return
    desktop = (os.environ.get("XDG_CURRENT_DESKTOP") or "").lower()
    has = lambda part: any(part in n for n in names)  # noqa: E731
    if ("kde" in desktop and has("kde")) or ("kde" not in desktop and has("gtk3")):
        return                                 # the desktop's own theme is there (Orneos OS, Fedora's Qt)
    if has("xdgdesktopportal"):
        os.environ["QT_QPA_PLATFORMTHEME"] = "xdgdesktopportal"


def spawn(cmd) -> bool:
    """Start another program, detached. False when it is not there (another system, not installed)."""
    if not cmd or not (shutil.which(cmd[0]) or os.path.isfile(cmd[0])):
        return False
    kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if WINDOWS:
        kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0)
    else:
        kwargs["start_new_session"] = True
    try:
        subprocess.Popen(cmd, **kwargs)
    except OSError:
        return False
    return True


# ---- the other apps: a module of the same window in Plume, another program on Orneos OS ---------------
# The arguments are those of the program (--message-id=…, --show=…, mailto:…), so both ways take the same.
COMMANDS = {
    # Orneos OS: Courrier, Agenda and Contacts are each their own app (Plume, the suite, takes them in-process)
    "mail": ["orneos-mail"], "calendar": ["orneos-calendar"], "contacts": ["orneos-contacts"],
    "notes": ["orneos-notes"], "tasks": ["orneos-tasks"], "passwords": ["orneos-passwords"], "ornis": ["ornis"],
    "photos": ["orneos-photos"], "meet": ["orneos-meet"],
    "connect": ["orneos-connect"],          # signing in: Orneos Connect, or Plume's own (account.py)
}
_handlers = {}


def register(kind: str, handler) -> None:
    """Plume (the suite) takes this kind itself: handler(args) runs in the same process."""
    _handlers[kind] = handler


def has_app(kind: str) -> bool:
    return kind in _handlers or (kind in COMMANDS and shutil.which(COMMANDS[kind][0]) is not None)


def in_process(kind: str) -> bool:
    return kind in _handlers


def launch(kind: str, *args) -> bool:
    """Open that app (with these arguments). False when it is neither here nor installed."""
    if kind in _handlers:
        _handlers[kind](list(args))
        return True
    return kind in COMMANDS and spawn(COMMANDS[kind] + list(args))


# ---- secrets: KWallet on KDE, the system keychain elsewhere ---------------------------------------------
WALLET_FOLDER, WALLET = "Orneos", "kdewallet"
SERVICE = "Orneos"


def _kwallet():
    return shutil.which("kwallet-query") if os.environ.get("PLUME_NO_WALLET") != "1" else None


def _keyring():
    if os.environ.get("PLUME_NO_WALLET") == "1":
        return None
    try:
        import keyring  # noqa: PLC0415 - bundled with Plume, absent on Orneos OS
        from keyring.backends import fail  # noqa: PLC0415
    except ImportError:
        return None
    return None if isinstance(keyring.get_keyring(), fail.Keyring) else keyring


def secret_get(entry: str):
    tool = _kwallet()
    if tool:
        try:
            res = subprocess.run([tool, "-f", WALLET_FOLDER, "-r", entry, WALLET],
                                 capture_output=True, text=True, timeout=20)
            value = res.stdout.rstrip("\n")
            if res.returncode == 0 and value and "not found" not in value.lower():
                return value
        except (OSError, subprocess.TimeoutExpired):
            pass
        return None
    ring = _keyring()
    if ring:
        try:
            return ring.get_password(SERVICE, entry)
        except Exception:  # noqa: BLE001 - a locked or broken keychain is "nothing stored"
            return None
    return None


def secret_set(entry: str, value: str) -> bool:
    """True when the keychain took it; False and the caller keeps it in a file only this user can read."""
    tool = _kwallet()
    if tool:
        try:
            res = subprocess.run([tool, "-f", WALLET_FOLDER, "-w", entry, WALLET],
                                 input=value, capture_output=True, text=True, timeout=20)
            return res.returncode == 0 and secret_get(entry) == value
        except (OSError, subprocess.TimeoutExpired):
            return False
    ring = _keyring()
    if ring:
        try:
            ring.set_password(SERVICE, entry, value)
            return ring.get_password(SERVICE, entry) == value
        except Exception:  # noqa: BLE001
            return False
    return False


def secret_delete(entry: str) -> None:
    tool = _kwallet()
    if tool:
        try:
            subprocess.run([tool, "-f", WALLET_FOLDER, "-w", entry, WALLET], input="",
                           capture_output=True, text=True, timeout=20)
        except (OSError, subprocess.TimeoutExpired):
            pass
        return
    ring = _keyring()
    if ring:
        try:
            ring.delete_password(SERVICE, entry)
        except Exception:  # noqa: BLE001 - nothing to delete
            pass


def private_write(path: Path, text: str) -> None:
    """A file only this user can read (0600 where the system has modes), written whole."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.replace(tmp, path)



def _unmangle(text: str) -> str:
    """Undo UTF-8 read as cp1252 (« Ã© » for « é »), as many times as it happened: each run of non-ASCII letters is
    encoded back and decoded again until it no longer changes. A genuine « é » or an emoji stops at once."""
    def fix(match):
        s = match.group()
        while True:
            try:
                t = s.encode("cp1252").decode("utf-8")
            except UnicodeError:
                return s
            if t == s:
                return s
            s = t
    return _NON_ASCII.sub(fix, text)


def _unmangle_tree(value):
    if isinstance(value, str):
        return _unmangle(value)
    if isinstance(value, list):
        return [_unmangle_tree(v) for v in value]
    if isinstance(value, dict):
        return {_unmangle(str(k)): _unmangle_tree(v) for k, v in value.items()}
    return value


def read_json(path: Path, default, limit: int = 64 << 20, repair: bool = False):
    """A JSON file written by private_write, read as UTF-8 (never the system's code page: on Windows, Plume before
    1.3.2 read Ornis's sessions.json as cp1252 and wrote it back as UTF-8, each accent doubling at every save, until
    a 9 GB file that no longer fitted in memory, 12/11). Past `limit`, the file is unusable: it is set aside as
    .broken (replacing an older one) and `default` comes back. `repair` undoes that old double encoding."""
    try:
        if path.stat().st_size > limit:
            os.replace(path, path.with_suffix(path.suffix + ".broken"))
            return default
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
    except (OSError, ValueError):
        return default
    if repair and ("Ã" in text or "Â" in text):
        data = _unmangle_tree(data)
    return data if isinstance(data, type(default)) else default

# ---- notifications ---------------------------------------------------------------------------------
_notifier = None


def set_notifier(func) -> None:
    """Plume's tray shows the notifications where there is no notify-send (Windows, macOS)."""
    global _notifier
    _notifier = func


def has_notify_send() -> bool:
    return not WINDOWS and not MACOS and shutil.which("notify-send") is not None


_badge = None
_badge_counts = {}


def set_badge_hook(func) -> None:
    """Plume's tray shows the unread count (its tooltip, the Dock or the taskbar)."""
    global _badge
    _badge = func
    if func is not None:
        func(sum(_badge_counts.values()))


def badge(count: int, source: str = "mail") -> None:
    _badge_counts[source] = max(0, int(count))
    if _badge is not None:
        _badge(sum(_badge_counts.values()))


def notify(title: str, body: str = "", on_click=None) -> bool:
    """A notification without actions, through the tray. False when there is nobody to show it."""
    if _notifier is None:
        return False
    _notifier(title, body, on_click)
    return True


# ---- the AppImage ----------------------------------------------------------------------------------------
def integrate_appimage() -> None:
    """Nothing installs an AppImage: Plume puts itself in the menu and takes mailto:, webcal: and orneos:// links,
    pointing at its file. Written again when the file moved; nothing done when it is unchanged."""
    image, appdir = os.environ.get("APPIMAGE"), os.environ.get("APPDIR")
    if not image or not appdir or WINDOWS or MACOS:
        return
    data = _xdg("XDG_DATA_HOME", ".local", "share")
    try:
        entry = (Path(appdir) / f"{AUTOSTART_NAME}.desktop").read_text(encoding="utf-8")
        icon_svg = (SHARE / "icons" / "hicolor" / "scalable" / "apps" / f"{AUTOSTART_NAME}.svg").read_bytes()
    except OSError:
        return
    quoted = '"' + image.replace("\\", "\\\\").replace('"', '\\"') + '"' if " " in image else image
    entry = entry.replace("Exec=plume ", f"Exec={quoted} ")
    target = data / "applications" / f"{AUTOSTART_NAME}.desktop"
    icon = data / "icons" / "hicolor" / "scalable" / "apps" / f"{AUTOSTART_NAME}.svg"
    try:
        if target.is_file() and target.read_text(encoding="utf-8") == entry:
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        icon.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(entry)
        icon.write_bytes(icon_svg)
    except OSError:
        return
    if shutil.which("update-desktop-database"):
        subprocess.run(["update-desktop-database", str(target.parent)], capture_output=True, check=False)


# ---- opening with the session ---------------------------------------------------------------------------
AUTOSTART_NAME = "eu.orneos.plume"


def _self_command():
    """How to start this Plume again: the packaged executable (the AppImage file), else python3 plume.py."""
    if os.environ.get("APPIMAGE"):
        return [os.environ["APPIMAGE"]]
    if FROZEN:
        return [sys.executable]
    return [sys.executable, str(SHARE / "orneos-plume" / "plume.py")]


def _autostart_file() -> Path:
    if MACOS:
        return Path.home() / "Library" / "LaunchAgents" / f"{AUTOSTART_NAME}.plist"
    return _xdg("XDG_CONFIG_HOME", ".config") / "autostart" / f"{AUTOSTART_NAME}.desktop"


def autostart_enabled() -> bool:
    if WINDOWS:
        try:
            import winreg  # noqa: PLC0415
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
                winreg.QueryValueEx(key, "Plume")
            return True
        except OSError:
            return False
    return _autostart_file().is_file()


def set_autostart(on: bool) -> None:
    """Plume with the session, in the tray only (--background): reminders and new mail without the window."""
    command = _self_command() + ["--background"]
    if WINDOWS:
        import winreg  # noqa: PLC0415
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0,
                            winreg.KEY_SET_VALUE) as key:
            if on:
                winreg.SetValueEx(key, "Plume", 0, winreg.REG_SZ, subprocess.list2cmdline(command))
            else:
                try:
                    winreg.DeleteValue(key, "Plume")
                except OSError:
                    pass
        return
    path = _autostart_file()
    if not on:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if MACOS:
        from html import escape  # noqa: PLC0415
        args = "".join(f"<string>{escape(a)}</string>" for a in command)
        path.write_text('<?xml version="1.0" encoding="UTF-8"?>\n'
                        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
                        f'<plist version="1.0"><dict><key>Label</key><string>{AUTOSTART_NAME}</string>'
                        f'<key>ProgramArguments</key><array>{args}</array><key>RunAtLoad</key><true/></dict></plist>\n')
    else:
        exec_line = " ".join(f'"{a}"' if " " in a else a for a in command)
        path.write_text(f"[Desktop Entry]\nType=Application\nName=Plume\nExec={exec_line}\nIcon={AUTOSTART_NAME}\n"
                        "X-GNOME-Autostart-enabled=true\nNoDisplay=true\n")
