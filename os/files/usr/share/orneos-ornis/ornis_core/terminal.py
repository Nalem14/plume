"""The terminals of the Code panel: the user's own shell in the project's folder, drawn by xterm.js (qml/terminal/)
and fed by a pseudo-terminal here (Linux and macOS; Windows when pywinpty is there, else the computer's terminal).

The page speaks to this object through QWebChannel (window.bridge): it writes what is typed, says its size, and gets
what the shell prints. It is the user's shell, as the terminal of Claude Code's and Cursor's: not Ornis's sandbox."""
import codecs
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid

from PySide6.QtCore import QObject, QSocketNotifier, Property, Signal, Slot

WINDOWS = sys.platform.startswith("win")
MAX_CHUNK = 65536


def _shell() -> list[str]:
    if WINDOWS:                              # PowerShell, as Windows Terminal opens it
        return [shutil.which("pwsh") or shutil.which("powershell") or os.environ.get("COMSPEC") or "cmd.exe"]
    shell = os.environ.get("SHELL") or ""
    if not shell:
        try:
            import pwd  # noqa: PLC0415
            shell = pwd.getpwuid(os.getuid()).pw_shell
        except (ImportError, KeyError, OSError):
            shell = ""
    shell = shell if shell and os.path.exists(shell) else shutil.which("bash") or "/bin/sh"
    # macOS: a login shell, as Terminal.app (an app started from the Dock has not the PATH of Homebrew)
    return [shell, "-l"] if sys.platform == "darwin" else [shell]


def _environment() -> dict:
    """The user's whole environment (ssh-agent, PATH of their tools…): it is their own terminal. Only what a packaged
    app adds for itself is taken back (PyInstaller's library paths)."""
    env = dict(os.environ)
    for key in ("LD_LIBRARY_PATH", "QT_PLUGIN_PATH", "QML2_IMPORT_PATH", "QTWEBENGINEPROCESS_PATH", "PYTHONHOME", "PYTHONPATH"):
        if key + "_ORIG" in env:
            env[key] = env.pop(key + "_ORIG")
        elif getattr(sys, "frozen", False):
            env.pop(key, None)
    env.update(TERM="xterm-256color", COLORTERM="truecolor", TERM_PROGRAM="Ornis")
    return env


class _Posix:
    """One shell on a pseudo-terminal; its output read on the window's thread when it comes (QSocketNotifier)."""

    def __init__(self, cwd, cols, rows, on_data, on_exit):
        import fcntl  # noqa: PLC0415
        import pty  # noqa: PLC0415
        import termios  # noqa: PLC0415
        self.master, slave = pty.openpty()
        self._resize(cols, rows)

        def controlling():                   # the child's own session, this terminal as its controlling one
            fcntl.ioctl(0, termios.TIOCSCTTY, 0)
        self.proc = subprocess.Popen(_shell(), stdin=slave, stdout=slave, stderr=slave, cwd=cwd, env=_environment(),
                                     start_new_session=True, preexec_fn=controlling, close_fds=True)
        os.close(slave)
        os.set_blocking(self.master, False)
        self.decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self.on_data, self.on_exit = on_data, on_exit
        self.notifier = QSocketNotifier(self.master, QSocketNotifier.Type.Read)
        self.notifier.activated.connect(self._read)

    def _resize(self, cols, rows):
        import fcntl  # noqa: PLC0415
        import struct  # noqa: PLC0415
        import termios  # noqa: PLC0415
        try:
            fcntl.ioctl(self.master, termios.TIOCSWINSZ, struct.pack("HHHH", max(2, rows), max(2, cols), 0, 0))
        except OSError:
            pass

    def _read(self, *_):
        try:
            data = os.read(self.master, MAX_CHUNK)
        except BlockingIOError:
            return
        except OSError:
            data = b""
        if data:
            text = self.decoder.decode(data)
            if text:
                self.on_data(text)
            return
        self.notifier.setEnabled(False)          # the shell is gone (EIO, or end of file)
        try:
            os.close(self.master)
        except OSError:
            pass
        code = self.proc.poll()
        self.on_exit(0 if code is None else code)

    def write(self, text):
        data = text.encode("utf-8")
        while data:
            try:
                done = os.write(self.master, data)
            except BlockingIOError:
                time.sleep(0.005)
                continue
            except OSError:
                return
            data = data[done:]

    def resize(self, cols, rows):
        self._resize(cols, rows)

    def kill(self):
        self.notifier.setEnabled(False)
        try:
            self.proc.terminate()
        except OSError:
            pass
        try:
            os.close(self.master)
        except OSError:
            pass


class _Windows:
    """pywinpty (ConPTY): read on a thread, handed to the window's thread by a signal."""

    def __init__(self, cwd, cols, rows, on_data, on_exit):
        from winpty import PtyProcess  # noqa: PLC0415
        self.proc = PtyProcess.spawn(_shell(), cwd=cwd, env=_environment(), dimensions=(rows, cols))
        self.on_data, self.on_exit = on_data, on_exit
        threading.Thread(target=self._pump, daemon=True, name="ornis-terminal").start()

    def _pump(self):
        while True:
            try:
                text = self.proc.read(MAX_CHUNK)
            except EOFError:
                break
            except Exception:  # noqa: BLE001
                break
            if text:
                self.on_data(text)
        self.on_exit(self.proc.exitstatus or 0)

    def write(self, text):
        try:
            self.proc.write(text)
        except Exception:  # noqa: BLE001
            pass

    def resize(self, cols, rows):
        try:
            self.proc.setwinsize(rows, cols)
        except Exception:  # noqa: BLE001
            pass

    def kill(self):
        try:
            self.proc.terminate(force=True)
        except Exception:  # noqa: BLE001
            pass


def available() -> bool:
    if WINDOWS:
        try:
            import winpty  # noqa: F401, PLC0415
            return True
        except ImportError:
            return False
    try:
        import pty  # noqa: F401, PLC0415
        return True
    except ImportError:
        return False


class Terminals(QObject):
    """Every terminal of the panel, by id. The page (window.bridge) and QML both use it."""
    output = Signal(str, str)        # id, text
    exited = Signal(str, int)        # id, exit code
    listChanged = Signal()
    _data = Signal(str, str)         # from a reading thread (Windows) to the window's thread
    _gone = Signal(str, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._live: dict = {}
        self._order: list = []           # [{id, title, cwd, alive}]
        self._buffer: dict = {}          # what each printed, kept for a page loaded again (bounded)
        self._data.connect(self._on_data)
        self._gone.connect(self._on_gone)

    @Property(bool, constant=True)
    def available(self):
        return available()

    @Property("QVariantList", notify=listChanged)
    def list(self):
        return [dict(t) for t in self._order]

    @Slot(str, int, int, result=str)
    def start(self, cwd, cols=100, rows=30):
        """A new shell in that folder: its id ("" when it cannot start)."""
        if not available():
            return ""
        ident = uuid.uuid4().hex[:8]
        cwd = cwd if cwd and os.path.isdir(cwd) else os.path.expanduser("~")
        try:
            kind = _Windows if WINDOWS else _Posix
            self._live[ident] = kind(cwd, cols or 100, rows or 30,
                                     lambda text, i=ident: self._data.emit(i, text),
                                     lambda code, i=ident: self._gone.emit(i, code))
        except Exception as error:  # noqa: BLE001
            print("Ornis terminal:", type(error).__name__, error)
            return ""
        number = 1 + max([t.get("number", 0) for t in self._order] + [0])
        self._order.append({"id": ident, "number": number, "cwd": cwd, "alive": True})
        self._buffer[ident] = ""
        self.listChanged.emit()
        return ident

    def _on_data(self, ident, text):
        self._buffer[ident] = (self._buffer.get(ident, "") + text)[-200000:]
        self.output.emit(ident, text)

    def _on_gone(self, ident, code):
        self._live.pop(ident, None)
        for t in self._order:
            if t["id"] == ident:
                t["alive"] = False
        self.listChanged.emit()
        self.exited.emit(ident, code)

    @Slot(str, str)
    def write(self, ident, text):
        term = self._live.get(ident)
        if term:
            term.write(text)

    @Slot(str, int, int)
    def resize(self, ident, cols, rows):
        term = self._live.get(ident)
        if term and cols > 0 and rows > 0:
            term.resize(cols, rows)

    @Slot(str, result=str)
    def history(self, ident):
        """What it printed so far (a page loaded again draws it back)."""
        return self._buffer.get(ident, "")

    @Slot(str)
    def close(self, ident):
        term = self._live.pop(ident, None)
        if term:
            term.kill()
        self._order = [t for t in self._order if t["id"] != ident]
        self._buffer.pop(ident, None)
        self.listChanged.emit()

    @Slot()
    def closeAll(self):
        for ident in list(self._live):
            self.close(ident)
        self._order, self._buffer = [], {}
        self.listChanged.emit()
