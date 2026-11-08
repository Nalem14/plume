"""What the QML sees of the library: the view chosen in the sidebar (the whole library by years, months or
every photo, favourites, videos, memories, people, places, an album, a search), its rows already laid out, and
every change, shown at once and sent to the cloud behind.

Network calls run on one worker thread (writes keep their order); thumbnails have their own (thumbs.py).
Sync: at start, every 5 minutes, a moment after each change, when the window comes back to the front and as
soon as the network returns.
"""
import json
import mimetypes
import os
import threading
import time
import traceback
import unicodedata
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path

from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtNetwork import QNetworkInformation

import cloud
import links
import system
from photos_core import edit as editing
from photos_core import layout
from photos_core.api import Api, ApiError
from photos_core import store as store_mod
from photos_core.store import Store

EVERY_MS = 5 * 60 * 1000
UNDO_MS = 6000
VIDEOS = system.CACHE / "photos-videos"
TARGETS = (110, 180, 280)          # row heights of the three zoom levels
URI_SAFE = "-_.!~*'()"
MEMBERS = ("albums", "recognize", "places", "tags", "map")   # views whose photos the cloud lists when opened
MEDIA = ("image/", "video/")
SMALL = 3                           # a person seen fewer times, unnamed, waits behind « show the others »


def cluster_preview(backend, cid):
    """The address of the picture Memories makes for a place or a theme with no cover chosen yet."""
    return f"c/{backend}/0//{urllib.parse.quote(str(cid), safe=URI_SAFE)}"


def short_place(address):
    """« Biarritz, Bayonne, Pyrénées-Atlantiques, …, France » → « Biarritz, France »: the town and the country
    (the map under it says the rest)."""
    names = [n.strip() for n in address.split(",") if n.strip()]
    return ", ".join(names[:1] + names[-1:]) if len(names) > 2 else ", ".join(names)


def file_size(n, lang):
    """1,2 Mo, 14 Ko: a file's size as people read it."""
    units = ("o", "Ko", "Mo", "Go") if lang == "fr" else ("B", "KB", "MB", "GB")
    value, unit = float(n), 0
    while value >= 1000 and unit < 3:
        value /= 1024
        unit += 1
    text = f"{value:.0f}" if unit < 2 or value >= 10 else f"{value:.1f}"
    return f"{text.replace('.', ',') if lang in ('fr', 'de') else text} {units[unit]}"


def fold(text):
    return unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().lower().strip()


def pictures_dir():
    """Where downloads go: the XDG pictures folder, in an « Orneos » folder."""
    base = None
    try:
        out = os.popen("xdg-user-dir PICTURES 2>/dev/null").read().strip()
        base = Path(out) if out and out != str(Path.home()) else None
    except OSError:
        base = None
    return (base or Path.home() / "Pictures") / "Orneos"


class Library(QObject):
    changed = Signal()               # the lists of the sidebar, the counts
    viewChanged = Signal()           # the rows of the view shown
    stateChanged = Signal()
    done = Signal(str, bool, str)    # what, ok, message
    infoReady = Signal(int, "QVariantMap")
    videoReady = Signal(int, str)
    collaboratorsReady = Signal(str, "QVariantList")
    shareReady = Signal(str)         # an album made to share photos is in the cloud: its people can be chosen
    peopleFound = Signal("QVariantList")
    editSaved = Signal(int, int)     # the photo, the one now shown (itself, or its copy)
    foldersReady = Signal("QVariantMap")
    mapReady = Signal(str, int, "QVariantList")   # the part of the map, the grid level, its clusters
    mapStartReady = Signal(float, float)
    tasksChanged = Signal()
    _sync_finished = Signal(str)
    _ran = Signal(object)

    def __init__(self, app, thumbs):
        super().__init__()
        self._app = app
        self._thumbs = thumbs
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="photos-sync")
        self._side = ThreadPoolExecutor(max_workers=2, thread_name_prefix="photos-jobs")
        self._local = ThreadPoolExecutor(max_workers=1, thread_name_prefix="photos-local")   # big writes, in order
        self._store = None
        self._state = "signed_out"
        self._online = True
        self._syncing = False
        self._last_error = ""
        self._queued = False
        self._last_sync = 0.0
        self._leaving = 0                # the window closed, the last changes on their way: which closing (leave)
        self._closings = 0
        self._pushed = False
        self._view = "library"
        self._mode = app.pref("mode") or "all"
        self._zoom = int(app.pref("zoom") if app.pref("zoom") is not None else 1)
        self._width = 900
        self._all = []                   # the library, newest first
        self._shown = []                 # the photos of the view shown
        self._rows, self._order = [], []
        self._cards = []                 # years, months, memories, people, places, albums: the view's cards
        self._lists = {}                 # albums, shared, people, places, tags, memories
        self._counts = {}
        self._pending = {"photos": set(), "albums": set(), "uploads": 0}
        self._held = {}                  # fileid → operation number, deletions that can still be undone
        self._tasks = {}                 # (kind, album) → {"text", "done", "total", "after"}: many photos on their way
        self._loading = set()            # clusters whose photos are on their way
        self._map = {}                   # (bounds, zoom) → the clusters of the map seen in this session
        self._search = {"query": "", "chips": [], "ids": [], "busy": False, "ornis": False}
        self._trash = []
        self._all_people = False         # the small unnamed groups shown too
        self._share_after = ""           # the album made to share photos, waited for
        self._sync_finished.connect(self._after_sync)
        self._ran.connect(lambda fn: fn())

        self._timer = QTimer(self)
        self._timer.setInterval(EVERY_MS)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self._soon = QTimer(self)
        self._soon.setSingleShot(True)
        self._soon.setInterval(1500)
        self._soon.timeout.connect(self.refresh)
        self._release = QTimer(self)
        self._release.setSingleShot(True)
        self._release.timeout.connect(self._release_held)
        self._relayout = QTimer(self)
        self._relayout.setSingleShot(True)
        self._relayout.setInterval(60)
        self._relayout.timeout.connect(self._layout)

        if QNetworkInformation.loadDefaultBackend() and QNetworkInformation.instance():
            QNetworkInformation.instance().reachabilityChanged.connect(self._reachability)
        app.accountChanged.connect(self._account_changed)
        self._account_changed()

    # ---- account and state -------------------------------------------------------------------------------
    def _account_changed(self):
        account = self._app.account()
        user = account[1] if account else None
        if self._store is not None and self._store.user == user:
            return
        if self._store is not None:
            self._store.forget()
            self._store = None
            self._thumbs.forget()
        self._held.clear()
        self._tasks.clear()
        self.tasksChanged.emit()
        if account is None:
            self._set_state("signed_out")
            self._reload()
            return
        self._store = Store(user)
        self._set_state("ready" if self._store.loaded else "loading")
        self._reload()
        threading.Thread(target=self._load_profile, args=(account,), daemon=True).start()
        self.refresh()

    def _load_profile(self, account):
        info = cloud.userinfo(*account)
        if info:
            profile = {"name": str(info.get("displayname") or info.get("display-name") or account[1]),
                       "email": str(info.get("email") or "")}
            self._ran.emit(lambda: self._app.set_profile(profile))

    def _set_state(self, state):
        if state != self._state:
            self._state = state
            self.stateChanged.emit()

    @Property(str, notify=stateChanged)
    def state(self):
        return self._state

    @Property(bool, notify=stateChanged)
    def online(self):
        return self._online

    @Property(bool, notify=stateChanged)
    def syncing(self):
        return self._syncing

    @Property(int, notify=stateChanged)
    def pending(self):
        return self._store.pending_count() if self._store else 0

    @Property(int, notify=stateChanged)
    def uploads(self):
        return self._pending["uploads"]

    @Property(int, notify=stateChanged)
    def syncedAt(self):
        return self._store.synced_at if self._store else 0

    def _reachability(self, reachability):
        if reachability == QNetworkInformation.Reachability.Online:
            self.refresh()

    # ---- sync --------------------------------------------------------------------------------------------
    def api(self):
        account = self._app.account()
        return Api(account) if account else None

    @Slot()
    def refresh(self):
        if self._store is None:
            return
        if self._syncing:
            self._queued = True
            return
        api = self.api()
        if api is None:
            return
        self._syncing = True
        self._last_sync = time.monotonic()
        self.stateChanged.emit()
        store = self._store
        store.hold = tuple(self._held)
        watched = [self._cluster()] if self._cluster() else [("archive", "all")] if self._view == "archive" else []

        def run():
            error = ""
            try:
                store.sync(api, report=self._refused, members=watched,
                           progress=lambda kind, data: self._ran.emit(lambda: self._advance(kind, data)))
            except ApiError as e:
                error = "offline" if e.status == 0 else "auth" if e.status == 401 else "server"
            except Exception:
                traceback.print_exc()
                error = "server"
            finally:
                api.close()
            self._sync_finished.emit(error)
        self._pool.submit(run)

    def stale(self, seconds):
        return time.monotonic() - self._last_sync > seconds

    def _refused(self, kind, data, status):
        key = {"upload": "refused_upload", "delete": "refused_delete"}.get(kind, "refused_change")
        name = str(data.get("name") or data.get("new") or "")
        self._ran.emit(lambda: self.done.emit(kind, False, self._app.t[key].replace("%1", name)))

    def _after_sync(self, error):
        self._syncing = False
        repeated = error == self._last_error          # a failure says so once, not at every sync after it
        self._last_error = error
        was_online = self._online
        self._online = error != "offline"
        if self._store is None:
            return
        if error and not self._store.loaded:
            self._set_state("offline_first" if error == "offline" else "error_first")
        else:
            self._set_state("ready" if self._store.loaded or not error else self._state)
        if repeated:
            pass
        elif error == "auth":
            self._app.toast.emit(self._app.t["error_auth"])
        elif error == "server":
            self._app.toast.emit(self._app.t["error_server"])
        elif error == "offline" and was_online and self._store.pending_count():
            self._app.toast.emit(self._app.t["offline_saved"])
        self.stateChanged.emit()
        self._reload()
        if self._view == "trash" and not error:
            self.loadTrash()
        if self._queued:
            self._queued = False
            self.refresh()

    # ---- many photos at once: written behind the window, followed until the cloud has them ----------------------
    @Property("QVariantList", notify=tasksChanged)
    def tasks(self):
        return [{"text": t["text"], "done": t["done"], "total": t["total"]} for t in self._tasks.values()]

    def _in_background(self, work, then):
        """work(store) off the window's thread (a few hundred photos write in one go, nothing freezes), then
        then(result) back on it."""
        store = self._store
        if store is None:
            return

        def run():
            try:
                result = work(store)
            except Exception:
                traceback.print_exc()
                result = None
            self._ran.emit(lambda: then(result) if self._store is store else None)
        self._local.submit(run)

    def _track(self, kind, album, text, total, after):
        """Shown in the sidebar until the cloud has them all, then « after » in a toast."""
        task = self._tasks.get((kind, album))
        if task:
            task["total"] += total
        else:
            self._tasks[(kind, album)] = {"text": text, "done": 0, "total": total, "after": after}
        self.tasksChanged.emit()

    def _advance(self, kind, data):
        if kind == "album_create" and data.get("album") == self._share_after:
            self._share_after = ""
            self.shareReady.emit(data["album"])
        task = self._tasks.get((kind, data.get("album")))
        if not task:
            return
        task["done"] += 1
        if task["done"] >= task["total"]:
            del self._tasks[(kind, data.get("album"))]
            self.done.emit("album", True, task["after"](task["total"]))
        self.tasksChanged.emit()

    def _changed_here(self):
        """A change made in the window: shown now, sent a moment later."""
        self._reload()
        self.stateChanged.emit()
        self._soon.start()

    @Slot(result=bool)
    def leave(self):
        """The window closes. What waits for the cloud (an import, albums) goes up in the background, the window
        hidden, then Photos quits: True while it does. The socket stays open the while, so a launch brings the
        window back (stay) instead of reaching a window that is gone."""
        if self._store is None or not self._store.pending_count() or not self._online or self._held:
            return False
        api = self.api()
        if api is None:
            return False
        self._closings += 1
        self._leaving = closing = self._closings
        self._timer.stop()
        store = self._store

        def run():
            try:
                store.push(api)
            except Exception:
                traceback.print_exc()
            finally:
                api.close()
            self._ran.emit(lambda: self._left(closing))
        self._pool.submit(run)          # after a sync on its way: the same worker, in order
        return True

    def _left(self, closing):
        if self._leaving == closing:    # not an earlier closing the window came back from
            self._pushed = True
            QGuiApplication.quit()

    @Slot()
    def stay(self):
        """The window comes back while Photos was leaving: it keeps running."""
        if self._leaving:
            self._leaving = 0
            self._timer.start()

    def shutdown(self):
        if self._pushed:
            return
        if self._store is not None and self._store.pending_count() and self._online and not self._held:
            api = self.api()
            if api is not None:
                try:
                    self._store.push(api)
                except Exception:
                    pass
                finally:
                    api.close()

    # ---- what is shown -----------------------------------------------------------------------------------
    def _reload(self):
        """Read the copy again: the library, the lists of the sidebar, the view."""
        store = self._store
        if store is None:
            self._all, self._lists, self._counts = [], {}, {}
            self._pending = {"photos": set(), "albums": set(), "uploads": 0}
            self.changed.emit()
            self._layout()
            return
        self._all = store.photos()
        self._pending = store.pending()
        me = store.user
        albums, shared = [], []
        for a in store.clusters("albums"):
            item = {"id": a["id"], "name": a["name"], "count": a["count"], "cover": a["cover"], "etag": a["cover_etag"],
                    "owner": a["data"].get("user") or me, "ownerName": a["data"].get("user_display") or "",
                    "created": int(a["data"].get("created") or 0), "pending": a["id"] in self._pending["albums"]}
            (albums if item["owner"] == me else shared).append(item)
        order = self._app.pref("album_sort") or "recent"
        for group in (albums, shared):
            if order == "name":
                group.sort(key=lambda a: fold(a["name"]))
            elif order == "size":
                group.sort(key=lambda a: -a["count"])
            else:
                group.sort(key=lambda a: -a["created"])
        people = [{"id": c["id"], "name": c["name"] if not c["name"].isdigit() else "", "count": c["count"],
                   "cover": c["cover"], "etag": c["cover_etag"], "dav": c["name"] or c["id"]}
                  for c in store.clusters("recognize")]
        people.sort(key=lambda p: (not p["name"], -p["count"]))     # the named first, the most seen first
        places = [{"id": c["id"], "name": c["name"], "count": c["count"], "cover": c["cover"], "etag": c["cover_etag"]}
                  for c in store.clusters("places")]
        tags = [{"id": c["id"], "name": c["name"], "count": c["count"], "cover": c["cover"], "etag": c["cover_etag"]}
                for c in store.clusters("tags")]
        words = self._words()
        memories = layout.memories(self._all, words)
        titles = self._app.pref("memory_titles") or {}
        for m in memories:
            if m["kind"] == "event" and titles.get(m["key"]):
                m["sub"], m["title"] = m["title"], titles[m["key"]]
        self._lists = {"albums": albums, "shared": shared, "people": people, "places": places, "tags": tags,
                       "memories": memories}
        self._counts = {"library": len(self._all), "favorites": sum(1 for p in self._all if p["fav"]),
                        "videos": sum(1 for p in self._all if p["video"]), "people": len(people),
                        "places": len(places), "memories": len(self._lists["memories"]),
                        "albums": len(albums) + len(shared), "trash": len(self._trash),
                        "archive": len(store.archived())}
        shown = self._cluster()
        if shown and shown[0] != "map" and store.cluster(*shown) is None and shown[1] not in self._loading:
            self._view = "library"                 # the album or person is gone (deleted, merged)
        self.changed.emit()
        self._layout()

    def _cluster(self):
        """(backend, id) when the view is one album, person, place, theme or square of the map; None for the
        lists themselves."""
        kind, _, ref = self._view.partition(":")
        return (kind, ref) if ref and kind in MEMBERS else None

    def _words(self):
        return layout.Words(self._app.t, self._app.lang)

    def _photos_of_view(self):
        view = self._view
        kind, _, ref = view.partition(":")
        if view == "library":
            return self._all
        if view == "favorites":
            return [p for p in self._all if p["fav"]]
        if view == "videos":
            return [p for p in self._all if p["video"]]
        if kind in MEMBERS and self._store is not None:
            return self._store.photo_rows(self._store.members(kind, ref))
        if kind == "memory":
            m = next((m for m in self._lists.get("memories", []) if m["key"] == ref), None)
            if not m:
                return []
            if m["kind"] == "onthisday":
                year = int(ref[3:])
                return [p for p in self._all if layout.day_date(p["dayid"]).year == year
                        and m["first"] <= p["dayid"] <= m["last"]]
            return [p for p in self._all if m["first"] <= p["dayid"] <= m["last"]]
        if view == "archive" and self._store is not None:
            return self._store.photo_rows(self._store.archived())
        if view == "search":
            ids = set(self._search["ids"])
            return [p for p in self._all if p["fileid"] in ids] if self._store else []
        return []

    def _layout(self):
        view = self._view
        words = self._words()
        self._cards = []
        if view == "library" and self._mode == "years":
            self._shown = self._all
            self._cards = layout.years(self._all)
            self._rows = []
        elif view == "library" and self._mode == "months":
            self._shown = self._all
            self._cards = layout.months(self._all, words)
            self._rows = []
        elif view in ("people", "places", "memories", "albums"):
            self._shown = []
            self._rows = []
            self._cards = self._lists.get(view, []) if view != "albums" else \
                self._lists.get("albums", []) + self._lists.get("shared", [])
            if view == "people" and not self._all_people:
                self._cards = [c for c in self._cards if c["name"] or c["count"] >= SMALL]
        elif view == "trash":
            self._shown, self._rows = [], []
            self._cards = self._trash
        else:
            self._shown = self._photos_of_view()
            turns = self._pending.get("turns") or {}
            if turns:                               # a rotation on its way: shown turned already
                self._shown = [dict(p, w=p["h"], h=p["w"], turn=turns[p["fileid"]]) if turns.get(p["fileid"], 0) % 180
                               else dict(p, turn=turns[p["fileid"]]) if p["fileid"] in turns else p for p in self._shown]
            target = TARGETS[max(0, min(2, self._zoom))]
            by = "month" if self._zoom == 0 and view == "library" else "day"
            self._rows = layout.grid(self._shown, self._width - 2, target, words, by, self._pending["photos"])
        self._order = [p["fileid"] for p in self._shown]
        self.viewChanged.emit()

    @Slot(int)
    def setWidth(self, width):
        width = int(width)
        if width > 100 and abs(width - self._width) > 1:
            self._width = width
            self._relayout.start()

    @Property(str, notify=viewChanged)
    def view(self):
        return self._view

    @Slot(str)
    def setView(self, view):
        if view == self._view:
            return
        self._view = view
        kind, _, ref = view.partition(":")
        if ref and kind in MEMBERS and self._store is not None \
                and not self._store.has_members(kind, ref):
            self._load_members(kind, ref)
        if view == "trash":
            self.loadTrash()
        if view == "archive" and self._store is not None and not self._store.has_members("archive", "all"):
            self._load_members("archive", "all")
        self._layout()

    def _load_members(self, kind, ref):
        self._loading.add(ref)
        self.viewChanged.emit()
        store = self._store

        def fn(api):
            return store.load_members(api, kind, ref)

        def then(_):
            self._loading.discard(ref)
            if self._view in (f"{kind}:{ref}", kind):
                self._layout()

        def failed():
            self._loading.discard(ref)
            self.viewChanged.emit()
        self._job("members", fn, then, quiet=True, undo=failed)

    @Property(bool, notify=viewChanged)
    def loadingView(self):
        ref = self._view.partition(":")[2] or ("all" if self._view == "archive" else "")
        return bool(ref) and ref in self._loading

    @Property(str, notify=viewChanged)
    def mode(self):
        return self._mode

    @Slot(str)
    def setMode(self, mode):
        if mode in ("years", "months", "all") and mode != self._mode:
            self._mode = mode
            self._app.setPref("mode", mode)
            self._layout()

    @Property(int, notify=viewChanged)
    def zoom(self):
        return self._zoom

    @Slot(int)
    def setZoom(self, zoom):
        zoom = max(0, min(2, int(zoom)))
        if zoom != self._zoom:
            self._zoom = zoom
            self._app.setPref("zoom", zoom)
            self._layout()

    @Property("QVariantList", notify=viewChanged)
    def rows(self):
        return self._rows

    @Property("QVariantList", notify=viewChanged)
    def cards(self):
        return self._cards

    @Property("QVariantList", notify=viewChanged)
    def order(self):
        return self._order

    @Property("QVariantMap", notify=changed)
    def lists(self):
        return self._lists

    @Property("QVariantMap", notify=changed)
    def counts(self):
        return dict(self._counts, trash=len(self._trash))

    @Property("QVariantList", notify=changed)
    def folders(self):
        return self._store.folders if self._store else []

    @Property("QVariantMap", notify=viewChanged)
    def heading(self):
        """The head of the view: its title, a line of figures, what it is (album of someone else, a person)."""
        t, view = self._app.t, self._view
        kind, _, ref = view.partition(":")
        title, extra = t.get("view_" + kind, ""), {}
        if not ref and ":" not in view and view != "search":
            kind = "list"                       # the library, favourites, the albums, the places…
        shown = self._shown
        if kind == "albums":
            album = self._store.cluster("albums", ref) if self._store else None
            title = album["name"] if album else ref.partition("/")[2]
            owner = (album or {}).get("data", {}).get("user") if album else ref.partition("/")[0]
            extra = {"own": owner == (self._store.user if self._store else ""), "owner": owner or ""}
        elif kind == "recognize":
            c = self._store.cluster("recognize", ref) if self._store else None
            name = (c or {}).get("name", "")
            title = name if name and not name.isdigit() else t["person_unnamed"]
            extra = {"named": bool(name and not name.isdigit()), "dav": name or ref}
        elif kind in ("places", "tags"):
            c = self._store.cluster(kind, ref) if self._store else None
            title = (c or {}).get("name", "")
        elif kind == "memory":
            m = next((m for m in self._lists.get("memories", []) if m["key"] == ref), None)
            title = (m or {}).get("title", "")
        elif kind == "search":
            title = self._search["query"]
        elif kind == "map":
            title = t["map_photos"]
        videos = sum(1 for p in shown if p["video"])
        figures = []
        if view in ("people", "places", "memories", "albums"):
            figures.append(self._app.plural("count_" + view, len(self._cards)))
            if view == "people":
                extra["hidden"] = 0 if self._all_people else len(self._lists.get("people", [])) - len(self._cards)
                extra["allPeople"] = self._all_people
        elif view == "trash":
            figures.append(self._app.plural("count_items", len(self._trash)))
        else:
            figures.append(self._app.plural("count_photos", len(shown) - videos))
            if videos:
                figures.append(self._app.plural("count_videos", videos))
            if shown:
                first, last = layout.day_date(shown[-1]["dayid"]), layout.day_date(shown[0]["dayid"])
                figures.append(str(first.year) if first.year == last.year else f"{first.year}–{last.year}")
        return dict({"title": title, "meta": " · ".join(f for f in figures if f), "kind": kind, "ref": ref,
                     "covers": self._covers(kind, ref)}, **extra)

    def _covers(self, kind, ref):
        """The pictures of the head, as {address, round}: the cover of one album, person, place or theme (else
        its newest photo); for the library, the lists and a search, the three newest photos or first cards."""
        out = []
        if kind in ("albums", "recognize", "places", "tags") and self._store is not None:
            c = self._store.cluster(kind, ref)
            if c and kind in ("places", "tags") and not c["cover"]:
                out.append({"address": cluster_preview(kind, ref), "round": False})
            elif c and c["cover"]:
                if kind in ("albums", "recognize"):
                    name = f"{self._store.user}/{ref}" if kind == "recognize" else ref
                    name = urllib.parse.quote(name, safe=URI_SAFE)       # as encodeURIComponent: the same cached file
                    out.append({"address": f"c/{kind}/{c['cover']}/{c['cover_etag']}/{name}",
                                "round": kind == "recognize"})
                else:
                    out.append({"address": f"t/512/{c['cover']}/{c['cover_etag']}", "round": False})
            if out:
                return out                     # one album, person, place or theme: its own cover alone
        seen = {o["address"].split("/")[2] for o in out}
        if not self._shown and kind == "list" and self._view in ("places", "tags"):
            return [{"address": cluster_preview(self._view, c["id"]) if not c.get("cover") else f"t/512/{c['cover']}/{c['etag']}",
                     "round": False} for c in self._cards[:3]]
        source = self._shown or [{"fileid": card.get("fileid") or card.get("cover"), "etag": card.get("etag")}
                                 for card in self._cards]
        many = 1 if kind in ("albums", "places", "tags", "memory", "map") else 3
        for item in source:
            if len(out) >= many:
                break
            if item.get("fileid") and str(item["fileid"]) not in seen and item.get("etag") is not None:
                seen.add(str(item["fileid"]))
                out.append({"address": f"t/512/{item['fileid']}/{item['etag']}", "round": False})
        return out

    # ---- the map ---------------------------------------------------------------------------------------
    @Slot(str, int)
    def loadMap(self, bounds, zoom):
        """The photos with a position in that part of the map, grouped by Memories on a grid that follows the
        zoom; what was seen comes back at once, offline too."""
        key = (bounds, int(zoom))
        if key in self._map:
            self.mapReady.emit(bounds, key[1], self._map[key])
            return

        def fn(api):
            return api.map_clusters(bounds, key[1])

        def then(rows):
            out = []
            for r in rows or []:
                center, preview = r.get("center") or [0, 0], r.get("preview") or {}
                out.append({"lat": float(center[0]), "lon": float(center[1]), "count": int(r.get("count") or 0),
                            "cover": int(preview.get("fileid") or 0), "etag": str(preview.get("etag") or "")})
            if len(self._map) > 300:
                self._map.clear()
            self._map[key] = out
            self.mapReady.emit(bounds, key[1], out)
        self._job("map", fn, then, quiet=True)

    @Slot()
    def loadMapStart(self):
        """Where the map opens the first time: the newest photo taken with a position."""
        def then(pos):
            if pos and pos.get("lat") is not None:
                self.mapStartReady.emit(float(pos["lat"]), float(pos["lon"]))
        self._job("map", lambda api: api.map_start(), then, quiet=True)

    # ---- one photo ---------------------------------------------------------------------------------------
    @Slot(int, result="QVariantMap")
    def photo(self, fileid):
        p = self._store.photo(fileid) if self._store else None
        if not p:
            return {}
        d = layout.day_date(p["dayid"])
        return {"fileid": p["fileid"], "etag": p["etag"], "name": p["name"], "w": p["w"], "h": p["h"],
                "video": bool(p["video"]), "duration": p["duration"], "fav": bool(p["fav"]),
                "day": self._words().day(d), "dayid": p["dayid"], "size": p["size"],
                "pending": p["fileid"] in self._pending["photos"], "outside": bool(p.get("outside")),
                "archived": bool(p.get("archived")), "turn": (self._pending.get("turns") or {}).get(p["fileid"], 0)}

    @Slot(int)
    def loadInfo(self, fileid):
        """The details of the viewer: date and time, camera, lens, exposure, place, people, albums."""
        store = self._store

        def fn(api):
            info = api.info(fileid)
            if info.get("filename") and store is not None:
                store.set_path(fileid, info["filename"])
            return info

        user = store.user if store is not None else ""

        def then(info):
            exif = info.get("exif") or {}
            people = [{"id": str(c.get("id")), "name": c.get("title") or c.get("name") or ""}
                      for c in (info.get("clusters") or {}).get("recognize", []) if isinstance(c, dict)]
            albums = [{"id": str(c.get("cluster_id") or ""), "name": c.get("name") or ""}
                      for c in (info.get("clusters") or {}).get("albums", []) if isinstance(c, dict)]
            taken = int(info.get("datetaken") or 0)
            when = ""
            if taken:
                moment = datetime.fromtimestamp(taken, timezone.utc)      # the local time it was taken
                clock = moment.strftime("%H:%M") if self._app.lang != "en" else moment.strftime("%-I:%M %p")
                when = self._app.t["date_at"].replace("%1", self._long_day(moment.date())).replace("%2", clock)
            camera = " ".join(x for x in (str(exif.get("Make") or ""), str(exif.get("Model") or "")) if x).strip()
            if camera.lower().startswith((str(exif.get("Make") or "").lower() + " ") * 2):
                camera = str(exif.get("Model") or "")
            exposure = []
            if exif.get("FNumber"):
                exposure.append(f"ƒ/{float(exif['FNumber']):g}")
            if exif.get("ExposureTime"):
                e = float(exif["ExposureTime"])
                exposure.append(f"1/{round(1 / e)} s" if 0 < e < 1 else f"{e:g} s")
            if exif.get("ISO"):
                exposure.append(f"ISO {exif['ISO']}")
            if exif.get("FocalLength"):
                exposure.append(f"{float(exif['FocalLength']):g} mm")
            w, h = int(info.get("w") or 0), int(info.get("h") or 0)
            dims = f"{w} × {h}" + (f" · {w * h / 1e6:.1f} Mpx" if w and h else "") if w and h else ""
            size = file_size(int(info.get("size") or 0), self._app.lang) if info.get("size") else ""
            lat, lon = exif.get("GPSLatitude"), exif.get("GPSLongitude")
            self.infoReady.emit(fileid, {
                "when": when, "name": str(info.get("basename") or ""), "path": str(info.get("filename") or ""),
                "dims": " · ".join(x for x in (dims, size) if x), "camera": camera,
                "lens": str(exif.get("LensModel") or ""), "exposure": "  ".join(exposure),
                "place": short_place(str(info.get("address") or "")), "lat": float(lat) if lat not in (None, "") else 0.0,
                "lon": float(lon) if lon not in (None, "") else 0.0, "hasGps": lat not in (None, "") and lon not in (None, ""),
                "people": people, "albums": albums,
                "description": str(exif.get("Description") or exif.get("ImageDescription") or exif.get("Caption-Abstract") or ""),
                "taken": datetime.fromtimestamp(taken, timezone.utc).strftime("%Y-%m-%dT%H:%M") if taken else "",
                # only a photo of another account (an album shared with me) says whose it is
                "owner": str(info.get("ownername") or "") if str(info.get("owneruid") or "") not in ("", user) else ""})
        self._job("info", fn, then, quiet=True)

    def _long_day(self, d):
        months = self._app.t["months_long"].split(",")
        if self._app.lang == "en":
            return f"{months[d.month - 1]} {d.day}, {d.year}"
        if self._app.lang == "de":
            return f"{d.day}. {months[d.month - 1]} {d.year}"
        return f"{d.day} {months[d.month - 1]} {d.year}"

    @Slot(int, int, result="QVariantList")
    def between(self, a, b):
        """The photos from one place of the order to another (Maj+clic)."""
        lo, hi = sorted((max(0, a), max(0, b)))
        return self._order[lo:hi + 1]

    @Slot(int, result=int)
    def indexOf(self, fileid):
        try:
            return self._order.index(int(fileid))
        except ValueError:
            return -1

    @Slot("QVariantList", result="QVariantMap")
    def dragData(self, fileids):
        """What a drag of photos carries: the photos for this window (an album in the sidebar), links for Notes
        and Tâches, the cloud addresses as text."""
        account = self._app.account()
        server = account[0] if account else cloud.CLOUD
        items = []
        for f in fileids[:50]:
            p = self._store.photo(int(f)) if self._store else None
            if p:
                items.append({"url": links.photo_url(server, p["fileid"]), "title": p["name"], "kind": "photo"})
        return {links.MIME: json.dumps(items), "application/x-orneos-photos": json.dumps([int(f) for f in fileids]),
                "text/plain": "\n".join(i["url"] for i in items)}

    # ---- changes -----------------------------------------------------------------------------------------
    def _mine(self, fileids):
        if self._store is None:
            return []
        return [p for p in self._store.photo_rows(fileids) if not p["outside"]]

    @Slot("QVariantList")
    def toggleFavorite(self, fileids):
        photos = self._mine(fileids)
        if not photos:
            return
        on = not all(p["fav"] for p in photos)
        self._store.queue_many("fav", [{"fileid": p["fileid"], "on": on} for p in photos if bool(p["fav"]) != on])
        self._changed_here()

    @Slot("QVariantList")
    def delete(self, fileids):
        """To the cloud's trash, with a few seconds to change one's mind."""
        photos = self._mine(fileids)
        if not photos:
            return
        numbers = self._store.queue_many("delete", [{"fileid": p["fileid"], "name": p["name"]} for p in photos])
        self._held.update(zip((p["fileid"] for p in photos), numbers))
        self._release.start(UNDO_MS)
        self._reload()
        self.stateChanged.emit()
        label = self._app.plural("deleted_many", len(photos)) if len(photos) > 1 else self._app.t["deleted_one"]
        self.done.emit("deleted", True, label)

    @Slot()
    def undoDelete(self):
        if self._store is None:
            return
        for n in self._held.values():
            self._store.unqueue(n)
        self._held.clear()
        self._release.stop()
        self._reload()
        self.stateChanged.emit()

    def _release_held(self):
        self._held.clear()
        if self._store is not None:
            self._store.hold = ()
        self.refresh()

    def _album_id(self, name):
        return f"{self._store.user}/{name}"

    @Slot(str, "QVariantList", result=str)
    def createAlbum(self, name, fileids):
        name = " ".join(str(name).replace("/", "-").split())
        if not name or self._store is None:
            return ""
        album = self._album_id(name)
        if self._store.cluster("albums", album) is not None:
            self.done.emit("album", False, self._app.t["album_exists"].replace("%1", name))
            return ""
        self._store.queue("album_create", album=album, name=name)
        self._changed_here()
        if fileids:
            self._add_photos(album, name, None, fileids)
        return album

    def _album(self, album):
        a = self._store.cluster("albums", album) if self._store else None
        if not a:
            return None, None, None
        owner = a["data"].get("user") or self._store.user
        return a, a["name"], owner

    @Slot(str, "QVariantList")
    def addToAlbum(self, album, fileids):
        a, name, owner = self._album(album)
        if a:
            self._add_photos(album, name, owner, fileids)

    def _add_photos(self, album, name, owner, fileids):
        """Before: « Adding 175 photos… »; during: the sidebar counts them up to the cloud; after: « added »."""
        t, plural = self._app.t, self._app.plural
        self.done.emit("album", True, plural("adding_to", len(fileids)).replace("%2", name))

        def work(store):
            known = store.members("albums", album)
            items = [{"album": album, "name": name, "owner": owner, "fileid": p["fileid"], "etag": p["etag"]}
                     for p in store.photo_rows(fileids) if not p["outside"] and p["fileid"] not in known]
            store.queue_many("album_add", items)
            return len(items)

        def then(added):
            if added is None:
                self.done.emit("album", False, t["error_server"])
                return
            if added:
                self._track("album_add", album, t["task_album_add"].replace("%1", name), added,
                            lambda n: plural("added_to", n).replace("%2", name))
            else:
                self.done.emit("album", True, t["already_in"].replace("%1", name))
            self._changed_here()
        self._in_background(work, then)

    @Slot(str, "QVariantList")
    def removeFromAlbum(self, album, fileids):
        a, name, owner = self._album(album)
        if not a:
            return
        t, plural = self._app.t, self._app.plural
        if len(fileids) > 1:
            self.done.emit("album", True, plural("removing_from", len(fileids)).replace("%2", name))

        def work(store):
            items = [{"album": album, "name": name, "owner": owner, "fileid": p["fileid"], "basename": p["name"]}
                     for p in store.photo_rows(fileids)]
            store.queue_many("album_remove", items)
            return len(items)

        def then(removed):
            if removed and removed > 1:
                self._track("album_remove", album, t["task_album_remove"].replace("%1", name), removed,
                            lambda n: plural("removed_from", n).replace("%2", name))
            self._changed_here()
        self._in_background(work, then)

    @Slot(str, str)
    def renameAlbum(self, album, new):
        a, name, owner = self._album(album)
        new = " ".join(str(new).replace("/", "-").split())
        if not a or not new or new == name or owner != self._store.user:
            return
        new_id = self._album_id(new)
        if self._store.cluster("albums", new_id) is not None:
            self.done.emit("album", False, self._app.t["album_exists"].replace("%1", new))
            return
        self._store.queue("album_rename", album=album, name=name, new=new, new_id=new_id)
        for kind in ("album_add", "album_remove"):
            if (kind, album) in self._tasks:
                self._tasks[(kind, new_id)] = self._tasks.pop((kind, album))
        if self._view == "albums:" + album:
            self._view = "albums:" + new_id
        self._changed_here()

    @Slot(str)
    def deleteAlbum(self, album):
        """The album goes; its photos stay in the library."""
        a, name, owner = self._album(album)
        if not a or owner != self._store.user:
            return
        self._store.queue("album_delete", album=album, name=name)
        for kind in ("album_add", "album_remove"):
            self._tasks.pop((kind, album), None)
        self.tasksChanged.emit()
        if self._view == "albums:" + album:
            self._view = "albums"
        self._changed_here()
        self.done.emit("album", True, self._app.t["album_deleted"].replace("%1", name))

    @Slot(str, str)
    def renamePerson(self, pid, new):
        c = self._store.cluster("recognize", pid) if self._store else None
        new = " ".join(str(new).replace("/", "-").split())
        if not c or not new:
            return
        self._store.queue("face_rename", id=pid, name=c["name"], dav=c["name"] or pid, new=new)
        self._changed_here()

    @Slot(str, str)
    def mergePerson(self, pid, into):
        c = self._store.cluster("recognize", pid) if self._store else None
        target = self._store.cluster("recognize", into) if self._store else None
        if not c or not target or pid == into:
            return
        self._store.queue("face_merge", id=pid, into=into, dav=c["name"] or pid, into_dav=target["name"] or into)
        self._view = "recognize:" + into
        if not self._store.has_members("recognize", into):
            self._load_members("recognize", into)
        self._changed_here()

    @Slot(str, "QVariantList")
    def notThisPerson(self, pid, fileids):
        c = self._store.cluster("recognize", pid) if self._store else None
        if not c:
            return
        for f in fileids:
            self._store.queue("face_remove", id=pid, dav=c["name"] or pid, fileid=int(f))
        self._changed_here()

    @Slot(bool)
    def setShowAllPeople(self, on):
        if bool(on) != self._all_people:
            self._all_people = bool(on)
            self._layout()

    @Slot(str)
    def setAlbumSort(self, order):
        if order in ("recent", "name", "size"):
            self._app.setPref("album_sort", order)
            self._reload()

    @Slot(str, "QVariantList")
    def mergePeople(self, pid, others):
        """Several groups Recognize took for other persons, gathered: into the named one (this one when it has
        a name, else the first named among them), the view following."""
        if self._store is None:
            return
        ids = [str(o) for o in others if str(o) != str(pid)]
        group = [pid] + ids
        named = [g for g in group if (self._store.cluster("recognize", g) or {}).get("name", "")
                 and not self._store.cluster("recognize", g)["name"].isdigit()]
        into = named[0] if named else pid
        for g in group:
            if g != into:
                self.mergePerson(g, into)

    @Slot(int)
    def setCover(self, fileid):
        """This photo as the picture of the album or the person shown."""
        kind, _, ref = self._view.partition(":")
        p = self._store.photo(fileid) if self._store else None
        if kind not in ("albums", "recognize") or not ref or not p:
            return
        if kind == "albums" and (self._album(ref)[2] or "") != self._store.user:
            return
        self._store.queue("cover", backend=kind, id=ref, fileid=int(fileid), etag=p["etag"])
        self._changed_here()
        self.done.emit("cover", True, self._app.t["cover_set"])

    @Slot("QVariantList", str, str)
    def setDate(self, fileids, day, clock):
        """Taken on another day (« YYYY-MM-DD »), at that time (« HH:MM ») or, left empty, each at its own."""
        try:
            d = date.fromisoformat(str(day))
        except ValueError:
            return
        dayid = (d - date(1970, 1, 1)).days
        clock = str(clock).strip()
        when = (clock + ":00")[:8] if clock else ""
        photos = self._mine(fileids)
        if not photos:
            return
        self._store.queue_many("date", [{"fileid": p["fileid"], "day": d.isoformat(), "time": when,
                                         "dayid": dayid, "old_dayid": p["dayid"]} for p in photos])
        self._changed_here()
        self.done.emit("date", True, self._app.plural("date_changed", len(photos)))

    @Slot("QVariantList", int)
    def rotate(self, fileids, turn):
        photos = [p for p in self._mine(fileids) if not p["video"]]
        if not photos:
            return
        self._store.queue_many("rotate", [{"fileid": p["fileid"], "turn": int(turn) % 360} for p in photos])
        self._changed_here()

    @Slot(int, str)
    def setDescription(self, fileid, text):
        if not self._mine([fileid]):
            return
        self._store.queue("description", fileid=int(fileid), text=str(text).strip())
        self._changed_here()

    @Slot("QVariantList", bool)
    def archive(self, fileids, on):
        """Out of the timeline, kept in « Archive » (a screenshot, a receipt), or back in it."""
        photos = [p for p in self._mine(fileids) if bool(p.get("archived")) != bool(on)]
        if not photos:
            return
        if self._store is not None:
            self._store.set_meta_quiet("members:archive:all", 1)
        self._store.queue_many("archive", [{"fileid": p["fileid"], "on": bool(on), "name": p["name"]} for p in photos])
        self._changed_here()
        key = "archived" if on else "unarchived"
        self.done.emit("archive", True, self._app.plural(key, len(photos)))

    @Slot(str)
    def leaveAlbum(self, album):
        a, name, owner = self._album(album)
        if not a or owner == self._store.user:
            return
        self._store.queue("album_leave", album=album, name=name, owner=owner)
        if self._view == "albums:" + album:
            self._view = "albums"
        self._changed_here()
        self.done.emit("album", True, self._app.t["album_left"].replace("%1", name))

    @Slot("QVariantList", str)
    def shareWith(self, fileids, name):
        """Photos shared with accounts go into a new album (as on a phone): made, filled, then its people chosen."""
        album = self.createAlbum(name, fileids)
        if album:
            self._share_after = album
            self.refresh()

    @Slot(int)
    def copyImage(self, fileid):
        """The photo itself on the clipboard (a large preview: pasted in a mail, a chat)."""
        def fn(api):
            return api.preview(fileid, 2048)

        def then(raw):
            from PySide6.QtGui import QImage
            image = QImage.fromData(raw)
            if image.isNull():
                self.done.emit("copy", False, self._app.t["error_server"])
                return
            QGuiApplication.clipboard().setImage(image)
            self.done.emit("copy", True, self._app.t["image_copied"])
        self._job("copy", fn, then)

    @Slot("QVariantList")
    def importFiles(self, paths):
        """Photos and videos of the computer into the library (its first folder, by year and month)."""
        if self._store is None:
            return
        folder = (self._store.folders or ["/Photos"])[0].rstrip("/") or "/Photos"
        count = 0
        for raw in paths:
            path = Path(str(raw).removeprefix("file://"))
            mime = mimetypes.guess_type(path.name)[0] or ""
            if not path.is_file() or not mime.startswith(MEDIA):
                continue
            try:
                staged = self._store.stage(path)
                mtime = int(path.stat().st_mtime)
            except OSError:
                continue
            when = datetime.fromtimestamp(mtime)
            self._store.queue("upload", staged=staged.name, folder=f"{folder}/{when:%Y}/{when:%m}", name=path.name,
                              mtime=mtime)
            count += 1
        if not count:
            self.done.emit("import", False, self._app.t["import_none"])
            return
        self._changed_here()
        self.done.emit("import", True, self._app.plural("import_queued", count))

    # ---- things that need the cloud now --------------------------------------------------------------------
    def _job(self, what, fn, then=None, quiet=False, undo=None):
        api = self.api()
        if api is None:
            return

        def failed(message):
            if undo:
                self._ran.emit(undo)
            if not quiet:
                self.done.emit(what, False, message)

        def run():
            try:
                result = fn(api)
            except ApiError as error:
                failed(self._app.t["error_offline_action"] if error.status == 0 else self._app.t["error_server"])
                return
            except Exception:
                traceback.print_exc()
                failed(self._app.t["error_server"])
                return
            finally:
                api.close()
            if then:
                self._ran.emit(lambda: then(result))
        self._side.submit(run)

    @Slot("QVariantList")
    def shareLink(self, fileids):
        photos = self._mine(fileids)
        if not photos:
            return
        self.done.emit("share", True, self._app.t["share_making"])
        store = self._store

        def fn(api):
            return [api.share_link(store.path_of(api, p["fileid"])) for p in photos[:20]]

        def then(urls):
            QGuiApplication.clipboard().setText("\n".join(urls))
            self.done.emit("share", True, self._app.t["share_copied"] if len(urls) == 1 else
                           self._app.plural("share_copied_many", len(urls)))
        self._job("share", fn, then)

    @Slot("QVariantList")
    def download(self, fileids):
        photos = [self._store.photo(int(f)) for f in fileids] if self._store else []
        photos = [p for p in photos if p]
        if not photos:
            return
        target = pictures_dir()
        self.done.emit("download", True, self._app.plural("downloading", len(photos)))

        def fn(api):
            target.mkdir(parents=True, exist_ok=True)
            saved = []
            for p in photos:
                dest = target / p["name"]
                n = 1
                while dest.exists():
                    n += 1
                    dest = target / f"{Path(p['name']).stem} ({n}){Path(p['name']).suffix}"
                api.download(p["fileid"], dest)
                saved.append(str(dest))
            return saved

        def then(saved):
            self.done.emit("download", True, self._app.plural("downloaded", len(saved)).replace("%2", str(target)))
        self._job("download", fn, then)

    @Slot()
    def openDownloads(self):
        system.open_url(str(pictures_dir()))

    @Slot(int)
    def loadVideo(self, fileid):
        """A video plays from a copy on the computer (kept in the cache)."""
        p = self._store.photo(fileid) if self._store else None
        if not p:
            return
        path = VIDEOS / f"{p['fileid']}-{p['etag']}{Path(p['name']).suffix or '.mp4'}"
        if path.exists():
            self.videoReady.emit(fileid, path.as_uri())
            return

        def fn(api):
            VIDEOS.mkdir(parents=True, exist_ok=True)
            for old in VIDEOS.glob(f"{p['fileid']}-*"):
                old.unlink(missing_ok=True)
            api.download(p["fileid"], path)
            return path.as_uri()
        self._job("video", fn, lambda uri: self.videoReady.emit(fileid, uri))

    @Slot(str)
    def openExternal(self, uri):
        """The video (or photo) in the computer's own player."""
        system.open_url(uri)

    @Slot(str)
    def loadCollaborators(self, album):
        a, name, owner = self._album(album)
        if not a or owner != self._store.user:
            return
        self._job("collaborators", lambda api: api.album_collaborators(name),
                  lambda people: self.collaboratorsReady.emit(album, self._with_link(people)))

    def _with_link(self, people):
        account = self._app.account()
        out = []
        for p in people:
            p = dict(p)
            if p["type"] == 3 and account:
                p["url"] = f"{account[0]}/apps/memories/a/{p['id']}"
            out.append(p)
        return out

    @Slot(str, "QVariantList")
    def setCollaborators(self, album, people):
        """Shown at once; a refusal puts the previous list back."""
        a, name, owner = self._album(album)
        if not a:
            return
        people = [dict(p.toVariant() if hasattr(p, "toVariant") else p) for p in people]
        self.collaboratorsReady.emit(album, self._with_link(people))

        def fn(api):
            api.album_set_collaborators(name, people)
            return api.album_collaborators(name)

        def then(fresh):
            fresh = self._with_link(fresh)
            self.collaboratorsReady.emit(album, fresh)
            link = next((p for p in fresh if p.get("url")), None)
            if link and not any(p.get("type") == 3 and p.get("url") for p in people):
                QGuiApplication.clipboard().setText(link["url"])
                self.done.emit("share", True, self._app.t["share_copied"])

        def undo():
            self.loadCollaborators(album)
        self._job("share", fn, then, undo=undo)

    @Slot(str)
    def searchPeople(self, term):
        term = str(term).strip()
        if len(term) < 1:
            self.peopleFound.emit([])
            return
        self._job("people", lambda api: api.people_search(term), lambda rows: self.peopleFound.emit(rows), quiet=True)

    @Slot(int, "QVariantMap", bool)
    def saveEdit(self, fileid, change, copy):
        """The edit is applied by the cloud; the window shows the result as soon as it is saved."""
        p = self._store.photo(fileid) if self._store else None
        if not p:
            return
        change = {k: (v.toVariant() if hasattr(v, "toVariant") else v) for k, v in dict(change).items()}
        if editing.is_identity(change):
            return
        name, ext = editing.target(p["name"], copy, self._app.t["edited_suffix"])
        state = editing.state(change)
        store = self._store
        self.done.emit("edit", True, self._app.t["edit_saving"])

        def fn(api):
            out = api.edit(fileid, name, ext, state)
            store.pull(api, recheck=[p["dayid"]])
            return int(out.get("fileid") or fileid)

        def then(new):
            self._reload()
            self.editSaved.emit(fileid, new)
            self.done.emit("edit", True, self._app.t["edit_saved"] if new == fileid else self._app.t["edit_saved_copy"])
        self._job("edit", fn, then)

    @Slot(int)
    def revertEdit(self, fileid):
        """Back to the photo as it was first: its oldest version in Files."""
        store = self._store
        p = store.photo(fileid) if store else None
        if not p:
            return
        day = p["dayid"]

        def fn(api):
            versions = api.versions(fileid)
            if not versions:
                return False
            api.restore_version(versions[0])
            store.pull(api, recheck=[day])
            return True

        def then(ok):
            self._reload()
            self.editSaved.emit(fileid, fileid)
            self.done.emit("edit", ok, self._app.t["edit_reverted"] if ok else self._app.t["edit_no_original"])
        self._job("edit", fn, then)

    # ---- the trash -----------------------------------------------------------------------------------------
    @Slot()
    def loadTrash(self):
        def then(rows):
            self._trash = [{"path": r.get("trash_path", ""), "fileid": int(r.get("fileid") or 0), "name": r.get("basename", ""),
                            "etag": r.get("etag", ""), "video": str(r.get("mimetype", "")).startswith("video/"),
                            "deleted": int(r.get("deletion_time") or 0)}
                           for r in sorted(rows, key=lambda r: -int(r.get("deletion_time") or 0))]
            self.changed.emit()
            if self._view == "trash":
                self._layout()
        self._job("trash", lambda api: api.trash(), then, quiet=True)

    @Slot("QVariantList")
    def restore(self, paths):
        paths = [str(p) for p in paths]
        kept = list(self._trash)
        self._trash = [t for t in self._trash if t["path"] not in paths]
        self._layout()
        self.changed.emit()

        def fn(api):
            for path in paths:
                api.restore(path)

        def undo():
            self._trash = kept
            self._layout()
        self._job("restore", fn, lambda _: (self.done.emit("restore", True, self._app.plural("restored", len(paths))),
                                            self.refresh()), undo=undo)

    @Slot("QVariantList")
    def purge(self, paths):
        paths = [str(p) for p in paths]
        kept = list(self._trash)
        self._trash = [t for t in self._trash if t["path"] not in paths]
        self._layout()
        self.changed.emit()

        def undo():
            self._trash = kept
            self._layout()
        self._job("purge", lambda api: [api.purge(p) for p in paths], undo=undo)

    # ---- search ------------------------------------------------------------------------------------------
    @Property("QVariantMap", notify=viewChanged)
    def search(self):
        return {k: v for k, v in self._search.items() if k != "ids"}

    @Slot(str, result=str)
    def quickMatch(self, query):
        """A name typed whole (a person, a place, an album, a theme) opens it without asking Ornis."""
        q = fold(query)
        if not q:
            return ""
        for kind, key in (("people", "recognize"), ("places", "places"), ("albums", "albums"), ("shared", "albums"),
                          ("tags", "tags")):
            for item in self._lists.get(kind, []):
                if item.get("name") and fold(item["name"]) == q:
                    return f"{key}:{item['id']}"
        return ""

    @Slot("QVariantMap")
    def runSearch(self, plan):
        """The filters Ornis made of a sentence (or the words themselves): narrowed on the cloud by person,
        place, theme and favourites, then by dates here."""
        plan = {k: (v.toVariant() if hasattr(v, "toVariant") else v) for k, v in dict(plan).items()}
        filters, chips = {}, []
        user = self._store.user if self._store else ""
        for kind, key, list_name in (("people", "recognize", "people"), ("places", "places", "places"),
                                     ("tags", "tags", "tags")):
            for wanted in plan.get(kind) or []:
                item = next((i for i in self._lists.get(list_name, []) if fold(i.get("name")) == fold(wanted)), None)
                if item and key not in filters:
                    filters[key] = f"{user}/{item['id']}" if key == "recognize" else item["id"] if key == "places" else item["name"]
                    chips.append({"kind": kind, "text": item["name"] or self._app.t["person_unnamed"]})
        for wanted in plan.get("albums") or []:
            item = next((i for i in self._lists.get("albums", []) + self._lists.get("shared", [])
                         if fold(i["name"]) == fold(wanted)), None)
            if item:
                filters.setdefault("albums", item["id"])
                chips.append({"kind": "albums", "text": item["name"]})
        if plan.get("favorites"):
            filters["fav"] = 1
            chips.append({"kind": "favorites", "text": self._app.t["view_favorites"]})
        if plan.get("videos"):
            filters["vid"] = 1
            chips.append({"kind": "videos", "text": self._app.t["view_videos"]})
        first, last = self._day(plan.get("from")), self._day(plan.get("to"))
        if first or last:
            words = self._words()
            chips.append({"kind": "dates", "text": words.span(layout.day_date(first or last), layout.day_date(last or first))})
        self._search = {"query": str(plan.get("query") or ""), "chips": chips, "ids": [], "busy": True,
                        "ornis": bool(plan.get("ornis"))}
        self._view = "search"
        self._layout()
        store = self._store

        def keep(ids):
            wanted = set(ids)
            rows = [p for p in self._all if p["fileid"] in wanted]
            return [p["fileid"] for p in rows
                    if (not first or p["dayid"] >= first) and (not last or p["dayid"] <= last)]

        def fn(api):
            if filters:
                return store.search(api, filters)
            return [p["fileid"] for p in self._all]

        def then(ids):
            if self._view != "search":
                return
            self._search["ids"] = keep(ids)
            self._search["busy"] = False
            self._layout()

        def failed():
            self._search["busy"] = False
            ids = [p["fileid"] for p in self._all] if not filters else []
            self._search["ids"] = keep(ids)
            self._layout()
        if not filters:
            then([p["fileid"] for p in self._all] if (first or last) else [])
            return
        self._job("search", fn, then, undo=failed)

    @staticmethod
    def _day(text):
        try:
            return layout.dayid_of(date.fromisoformat(str(text)[:10])) if text else 0
        except ValueError:
            return 0

    def search_context(self):
        """What Ornis may know to read a search: the names only (never a photo)."""
        names = lambda key: [i["name"] for i in self._lists.get(key, []) if i.get("name")][:80]  # noqa: E731
        return {"people": names("people"), "places": names("places"), "tags": names("tags"),
                "albums": names("albums") + names("shared")}

    # ---- memories ------------------------------------------------------------------------------------------
    def memory_facts(self):
        """For Ornis to title the memories: their dates, their size and, when the cloud knows it, the place of
        their cover (asked on the worker)."""
        return [{"key": m["key"], "first": layout.day_date(m["first"]).isoformat(), "last": layout.day_date(m["last"]).isoformat(),
                 "count": m["count"], "cover": m["fileid"]} for m in self._lists.get("memories", []) if m["kind"] == "event"]

    @Slot("QVariantMap")
    def setMemoryTitles(self, titles):
        titles = {k: (v.toVariant() if hasattr(v, "toVariant") else v) for k, v in dict(titles).items()}
        saved = dict(self._app.pref("memory_titles") or {})
        saved.update({k: str(v) for k, v in titles.items() if v})
        self._app.setPref("memory_titles", saved)
        self._reload()

    # ---- settings ------------------------------------------------------------------------------------------
    @Slot()
    def loadFolders(self):
        """The library's folders and whether the phone's uploads (InstantUpload) sit outside them."""
        store = self._store

        def fn(api):
            config = api.config()
            path = str(config.get("timeline_path") or "")
            if store is not None:
                store.set_meta("timeline_path", path)
            folders = [p for p in path.split(";") if p.strip()]
            phone = store_mod.PHONE_FOLDER
            outside = api.exists(phone) and not any(phone.startswith(f.rstrip("/") + "/") or f.rstrip("/") == phone
                                                     for f in folders)
            return {"folders": folders, "suggest": phone if outside else ""}
        self._job("folders", fn, lambda data: self.foldersReady.emit(data))

    @Slot("QVariantList")
    def setFolders(self, folders):
        folders = [str(f).strip() for f in folders if str(f).strip()]
        if not folders or self._store is None:
            return
        value = ";".join(folders)
        before = self._store.meta("timeline_path") or ""
        self._store.set_meta("timeline_path", value)
        self.changed.emit()
        self.foldersReady.emit({"folders": folders, "suggest": ""})

        def fn(api):
            api.set_config("timelinePath", value)

        def undo():
            self._store.set_meta("timeline_path", before)
            self.changed.emit()
            self.loadFolders()
        self._job("folders", fn, lambda _: self.refresh(), undo=undo)

    @Slot(result=str)
    def cacheSize(self):
        from photos_core import thumbs
        total = sum(p.stat().st_size for p in thumbs.ROOT.rglob("*") if p.is_file()) if thumbs.ROOT.exists() else 0
        total += sum(p.stat().st_size for p in VIDEOS.glob("*") if p.is_file()) if VIDEOS.exists() else 0
        return cloud.format_bytes(total, self._app.lang)

    @Slot()
    def clearCache(self):
        import shutil
        self._thumbs.forget()
        shutil.rmtree(VIDEOS, ignore_errors=True)
        self.done.emit("cache", True, self._app.t["cache_cleared"])
