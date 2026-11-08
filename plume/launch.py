"""The executable of packaged Plume (PyInstaller): it runs orneos-plume/plume.py from the bundle.

PyInstaller brings Python, Qt and the libraries; the apps themselves are copied as they are on Orneos OS (the
tree of /usr/share: orneos/, orneos-plume/, orneos-notes/…, see stage.py), so they find their QML and each other
the same way everywhere. Nothing is written next to them: on macOS that would break the app's signature.
"""
import faulthandler
import os
import runpy
import ssl
import sys

sys.dont_write_bytecode = True
SHARE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
ENTRY = os.path.join(SHARE, "orneos-plume", "plume.py")


def certificates():
    """HTTPS needs the authorities. Windows gives its own store; the OpenSSL bundled for macOS (and Linux, when the
    path it was built with is missing) finds none, and every request fails: certifi's then, unless one is set."""
    if sys.platform == "win32" or os.environ.get("SSL_CERT_FILE"):
        return
    paths = ssl.get_default_verify_paths()
    if paths.cafile or (paths.capath and os.listdir(paths.capath)):
        return
    try:
        import certifi  # noqa: PLC0415
        os.environ["SSL_CERT_FILE"] = certifi.where()
    except ImportError:
        pass


def log_file():
    """Started from the Finder or the Start menu, Plume has no terminal: what it would print (Python, Qt, and a
    crash's trace) goes to a file instead, emptied past 1 MB."""
    if sys.platform == "darwin":
        path = os.path.expanduser("~/Library/Logs/Plume.log")
    elif sys.platform == "win32":
        path = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "Orneos", "State", "plume.log")
    else:
        base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
        path = os.path.join(base, "orneos", "plume.log")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        big = os.path.exists(path) and os.path.getsize(path) > 1 << 20
        out = open(path, "w" if big else "a", buffering=1, encoding="utf-8", errors="replace")  # noqa: SIM115
    except OSError:
        return
    try:
        os.dup2(out.fileno(), 2)             # Qt's messages, written by C++
    except OSError:
        pass
    sys.stdout = sys.stderr = out
    faulthandler.enable(out)


sys.path.insert(0, os.path.join(SHARE, "orneos"))
from ornis_local import dispatch_helper
dispatch_helper()
certificates()
if getattr(sys, "frozen", False) and not any(a.startswith("--self-test=") for a in sys.argv[1:]):
    log_file()
sys.argv[0] = ENTRY
runpy.run_path(ENTRY, run_name="__main__")
