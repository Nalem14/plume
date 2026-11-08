"""The pictures of the window: thumbnails, large previews and the covers of albums and people, kept on disk.

QML asks with an address (Thumb.qml) and shows the file of the cache as soon as it is there: at once when it
is on disk, else when the cloud gave it (ready), the thumbnails of a whole screen in one request (Memories'
multipreview). Qt loads the files itself: no Python image provider, whose answers delivered from another
thread could lock against Qt's own image loader. A picture is
named after its photo's ETag, so an edited photo gets new ones. The cache is trimmed to a size, the least
recently seen first. Offline, what was seen before still shows; the rest stays a tinted tile.

Addresses: t/<size>/<fileid>/<etag> (grid), p/<size>/<fileid>/<etag> (viewer, editor),
c/<backend>/<cover>/<cover_etag>/<name> (cover of an album, person, place or tag).
"""
import hashlib
import os
import queue
import re
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, QUrl, Signal, Slot
from PySide6.QtGui import QImage

import system
from photos_core.api import Api, ApiError

ROOT = system.CACHE / "photos"
LIMIT = 1536 * 1024 * 1024        # bytes on disk, trimmed at start and every few hundred pictures
FAILED_FOR = 30                   # seconds before a picture the cloud did not give is asked again
SAFE = re.compile(r"[^A-Za-z0-9_.-]")


def _file(address):
    parts = address.split("/")
    kind = parts[0]
    if kind in ("t", "p") and len(parts) >= 4:
        return ROOT / f"{kind}{parts[1]}" / f"{parts[2]}-{SAFE.sub('_', parts[3])[:40]}.jpg"
    if kind == "c" and len(parts) >= 5:
        name = hashlib.sha1("/".join(parts[4:]).encode()).hexdigest()[:16]
        return ROOT / "covers" / f"{parts[1]}-{name}-{parts[2]}-{SAFE.sub('_', parts[3])[:40]}.jpg"
    return None


def trim(limit=LIMIT):
    """The least recently seen pictures go until the cache fits."""
    files = []
    for path in ROOT.rglob("*.jpg"):
        try:
            st = path.stat()
        except OSError:
            continue
        files.append((st.st_atime, st.st_size, path))
    total = sum(f[1] for f in files)
    for _, size, path in sorted(files):
        if total <= limit:
            break
        try:
            path.unlink()
            total -= size
        except OSError:
            pass
    return total


class Thumbs(QObject):
    """Fetches the pictures (a dispatcher gathers the thumbnails asked together into one request)."""
    ready = Signal(str, str)          # address, file URL ("" when the cloud did not give it)

    def __init__(self, account_fn):
        super().__init__()
        self._account = account_fn
        self._queue = queue.Queue()
        self._pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="photos-thumbs")
        self._local = threading.local()
        self._failed = {}
        self._waiting = {}                 # address → [callbacks] (one request for the same picture)
        self._lock = threading.Lock()
        self._fetched = 0
        ROOT.mkdir(parents=True, exist_ok=True)
        threading.Thread(target=self._dispatch, daemon=True, name="photos-dispatch").start()
        threading.Thread(target=trim, daemon=True).start()

    def forget(self):
        """Another account: none of the previous pictures stay."""
        import shutil
        shutil.rmtree(ROOT, ignore_errors=True)
        ROOT.mkdir(parents=True, exist_ok=True)
        self._failed.clear()

    def path(self, address):
        path = _file(address)
        return path if path is not None and path.exists() else None

    @Slot(str, result=str)
    def url(self, address):
        """The cached file of that picture, or "" (then want() it)."""
        path = self.path(address)
        return QUrl.fromLocalFile(str(path)).toString() if path else ""

    @Slot(str)
    def want(self, address):
        self.request(address, lambda image, a=address: self.ready.emit(a, self.url(a) if image is not None else ""),
                     read=False)

    def request(self, address, callback, read=True):
        """callback(QImage or None) once the picture is there (read=False: only on disk, not decoded)."""
        path = _file(address)
        if path is None:
            callback(None)
            return
        if path.exists():
            if read:
                self._pool.submit(self._read, path, callback)
            else:
                callback(True)
            return
        if time.monotonic() - self._failed.get(address, -FAILED_FOR) < FAILED_FOR:
            callback(None)
            return
        with self._lock:
            if address in self._waiting:
                self._waiting[address].append(callback)
                return
            self._waiting[address] = [callback]
        self._queue.put(address)

    @staticmethod
    def _read(path, callback):
        image = QImage(str(path))
        try:
            os.utime(path)
        except OSError:
            pass
        callback(image if not image.isNull() else None)

    def _api(self):
        account = self._account()
        if account is None:
            return None
        api = getattr(self._local, "api", None)
        if api is None or (api.server, api.user, api.password) != account:
            api = Api(account, timeout=30)
            self._local.api = api
        return api

    def _done(self, address, data):
        with self._lock:
            callbacks = self._waiting.pop(address, [])
        image = None
        if data:
            image = QImage.fromData(data)
            if image.isNull():
                image = None
        if image is not None:
            path = _file(address)
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                tmp = path.with_suffix(".part")
                tmp.write_bytes(data)
                tmp.replace(path)
            except OSError:
                pass
        if image is None:
            self._failed[address] = time.monotonic()
        for cb in callbacks:
            cb(image)
        self._fetched += 1
        if self._fetched % 400 == 0:
            threading.Thread(target=trim, daemon=True).start()

    def _dispatch(self):
        while True:
            first = self._queue.get()
            batch = [first]
            deadline = time.monotonic() + 0.03
            while len(batch) < 48:
                try:
                    batch.append(self._queue.get(timeout=max(0.0, deadline - time.monotonic())))
                except queue.Empty:
                    break
            grid = [a for a in batch if a.startswith("t/")]
            for address in batch:
                if not address.startswith("t/"):
                    self._pool.submit(self._one, address)
            for i in range(0, len(grid), 24):
                self._pool.submit(self._many, grid[i:i + 24])

    def _many(self, addresses):
        """A batch in one answer. Memories leaves out the photos it has no preview of yet (a new one): those
        are asked one by one, which makes the server write their preview for the next time."""
        api = self._api()
        got, answered = {}, False
        if api is not None:
            wanted = []
            for n, address in enumerate(addresses):
                _, size, fileid, _ = address.split("/", 3)
                wanted.append((n, int(fileid), int(size)))
            try:
                got = api.multipreview(wanted)
                answered = True
            except Exception:
                got = {}
        for n, address in enumerate(addresses):
            if str(n) in got or not answered:
                self._done(address, got.get(str(n)))
            else:
                self._pool.submit(self._one, address)

    def _one(self, address):
        api = self._api()
        data = None
        if api is not None:
            parts = address.split("/")
            try:
                if parts[0] in ("p", "t"):
                    data = api.preview(int(parts[2]), int(parts[1]))
                elif parts[0] == "c":
                    name = urllib.parse.unquote("/".join(parts[4:]))
                    data = api.cluster_preview(parts[1], name, int(parts[2] or 0))
            except ApiError:
                data = None
            except Exception:
                data = None
        self._done(address, data)
