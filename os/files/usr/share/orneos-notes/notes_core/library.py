"""What the QML sees of the notes: the folders and tags of the sidebar, the list of the one chosen (grouped by
date, like macOS), one note, the recently deleted ones, and every change, written to the local copy at once
and sent to the cloud behind.

Network calls run on one worker thread (writes keep their order); images on a small pool of their own.
Sync: at start, every 5 minutes, a moment after each change, when the window comes back to the front and as
soon as the network returns.
"""
import difflib
import json
import mimetypes
import os
import re
import threading
import time
import traceback
import unicodedata
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QByteArray, QMimeData, QObject, Property, Qt, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QFont, QGuiApplication, QImage, QPageSize, QPdfWriter, QTextDocument
from PySide6.QtNetwork import QNetworkInformation

import cloud
import system
import links
from dragguard import DragGuard
from notes_core import markdown
from notes_core.api import Api, ApiError
from notes_core.store import Store

EVERY_MS = 5 * 60 * 1000
IMAGES = system.CACHE / "notes-images"
UNDO_MS = 6000
TEXT = (".txt", ".md", ".markdown", ".csv", ".json", ".xml", ".html", ".htm", ".log", ".ini", ".conf", ".yaml", ".yml",
        ".py", ".js", ".sh", ".tex", ".rst", ".org")
MAX_FILE = 25 * 1024 * 1024


def fold(text):
    return unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().lower()


class Library(QObject):
    changed = Signal()               # the list, the counts, the folders
    folderChanged = Signal()
    stateChanged = Signal()
    noteUpdated = Signal(str)        # a note changed by a sync (the editor takes it if it has nothing unsaved)
    imagesChanged = Signal()
    trashChanged = Signal()
    created = Signal(str)            # a new note to open (files from Dolphin, a Quick Note)
    done = Signal(str, bool, str)    # what, ok, message
    sharesChanged = Signal(str)      # the people a note is shared with (its key)
    recipientsReady = Signal("QVariantList")
    versionsReady = Signal(str, "QVariantList")      # a note's earlier versions (its key)
    versionReady = Signal(str, str, str)             # key, version, its text
    _sync_finished = Signal(str)
    _ran = Signal(object)

    def __init__(self, app):
        super().__init__()
        self._drag = DragGuard(self, ['moveFolder', 'moveTo'])
        self._app = app
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="notes-sync")
        self._fetch = ThreadPoolExecutor(max_workers=3, thread_name_prefix="notes-images")
        self._store = None
        self._state = "signed_out"
        self._online = True
        self._syncing = False
        self._queued = False
        self._folder = app.pref("folder") or "all"
        self._query = ""
        self._notes = {}
        self._items = []
        self._trash = []
        self._trash_content = {}
        self._asked = set()
        self._held = {}
        self._shares = {}                # key: [{id, type, with, name, editable}] as the cloud last gave them
        self._share_changes = {}         # key: {share id: what shows until the cloud has it (a dict, None = gone)}
        self._sharing = None             # ({note id: [people, link]}, {note id: {id, owner, editable}}), « Partagées »
        self._last_sync = 0.0
        self._told_locked = set()        # notes said to be open in the cloud's editor (told once while they stay so)
        self._locked_now = set()
        self._trash_loading = set()      # deleted notes whose text is on its way
        self._open = ""                  # the note shown (a shared one is read again more often)
        self._sync_finished.connect(self._after_sync)
        self._ran.connect(lambda fn: fn())
        IMAGES.mkdir(parents=True, exist_ok=True)

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
        # a note shared with others, open and in front: read again every 30 s, so their changes show soon
        self._shared_poll = QTimer(self)
        self._shared_poll.setInterval(30 * 1000)
        self._shared_poll.timeout.connect(self._poll_shared)
        self._shared_poll.start()

        if QNetworkInformation.loadDefaultBackend() and QNetworkInformation.instance():
            QNetworkInformation.instance().reachabilityChanged.connect(self._reachability)
        app.accountChanged.connect(self._account_changed)
        app.prefsChanged.connect(self._rebuild)
        self._account_changed()

    # ---- account and state -------------------------------------------------------------------------------
    def _account_changed(self):
        account = self._app.account()
        user = account[1] if account else None
        if self._store is not None and self._store.user == user:
            return
        if self._store is not None:
            self._store.forget()               # another account (or signed out): nothing of the previous stays
            self._store = None
        self._notes, self._trash = {}, []
        self._shares, self._share_changes, self._sharing = {}, {}, None
        if account is None:
            self._set_state("signed_out")
            self._rebuild()
            return
        self._store = Store(user, untitled=self._app.t["untitled"], conflict=self._app.t["conflict_copy"])
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
    def syncedAt(self):
        return self._store.synced_at if self._store else 0

    def _reachability(self, reachability):
        if reachability == QNetworkInformation.Reachability.Online:
            self.refresh()

    # ---- sync --------------------------------------------------------------------------------------------
    def api(self):
        account = self._app.account()
        return Api(account) if account else None


    # ---- drops of a drag started here (dragguard.py: the model changes once the drag is over, never inside it) ----
    @Slot()
    def dragStarted(self):
        self._drag.started()

    @Slot()
    def dragEnded(self):
        self._drag.ended()

    @Slot(str, "QVariant")
    def afterDrag(self, method, args):
        self._drag.call(method, args)

    @Slot()
    def refresh(self):
        if self._store is None:
            return
        if self._syncing:
            self._queued = True
            return
        self._syncing = True
        self._last_sync = time.monotonic()
        self._locked_now = set()
        self.stateChanged.emit()
        store, api = self._store, self.api()
        store.hold = tuple(self._held)
        before = {k: n["content"] for k, n in self._notes.items()}

        def run():
            error = ""
            try:
                store.sync(api, report=self._refused, locked=self._locked)
            except ApiError as e:
                error = "offline" if e.status == 0 else "auth" if e.status == 401 else "server"
            except Exception:
                traceback.print_exc()
                error = "server"
            finally:
                api.close()
            self._before = before
            self._sync_finished.emit(error)
        self._pool.submit(run)

    def stale(self, seconds):
        return time.monotonic() - self._last_sync > seconds

    def _locked(self, key, title):
        """A note open in the cloud's editor (locked there): its change waits, said once while it stays locked."""
        self._locked_now.add(key)
        if key not in self._told_locked:
            self._told_locked.add(key)
            self._ran.emit(lambda: self._app.toast.emit(self._app.t["sync_locked"].replace("%1", title)))

    def _refused(self, title, error):
        self._ran.emit(lambda: self._app.toast.emit(self._app.t["sync_refused"].replace("%1", title)))

    def _after_sync(self, error):
        self._syncing = False
        was_online = self._online
        self._online = error != "offline"
        if self._store is None:
            return
        if error and not self._store.loaded:
            self._set_state("offline_first" if error == "offline" else "error_first")
        else:
            self._set_state("ready" if self._store.loaded or not error else self._state)
        if error == "auth":
            self._app.toast.emit(self._app.t["error_auth"])
        elif error == "server":
            self._app.toast.emit(self._app.t["error_server"])
        elif error == "offline" and was_online and self._store.pending_count():
            self._app.toast.emit(self._app.t["offline_saved"])
        if not error:
            self._told_locked &= self._locked_now       # unlocked since: a new lock will be told again
        self.stateChanged.emit()
        before = getattr(self, "_before", {})
        self._reload()
        for key, note in self._notes.items():
            if key in before and before[key] != note["content"]:
                self.noteUpdated.emit(key)
        if self._folder == "trash" and not error:
            self.loadTrash()
        if (self._sharing is None or self._folder == "shared") and not error:
            self.loadSharing()
        if self._queued:
            self._queued = False
            self.refresh()

    def shutdown(self):
        if self._store is not None and self._store.pending_count() and self._online:
            # a last try, briefly: what was typed just before closing goes up when it can
            try:
                api = self.api()
                self._store.hold = ()
                self._store.push(api)
                api.close()
            except Exception:
                pass
        self._pool.shutdown(wait=False, cancel_futures=True)
        self._fetch.shutdown(wait=False, cancel_futures=True)

    # ---- the sidebar: folders and tags ---------------------------------------------------------------------
    def _reload(self):
        self._notes = {n["key"]: n for n in self._store.notes()} if self._store else {}
        self._rebuild()

    def _categories(self):
        cats = {n["category"] for n in self._notes.values()}
        cats |= {c for c in (self._app.pref("empty_folders") or []) if c}
        full = set()
        for c in cats:
            parts = [p for p in c.split("/") if p]
            for i in range(1, len(parts) + 1):
                full.add("/".join(parts[:i]))
        return sorted(full, key=lambda c: [fold(p) for p in c.split("/")])

    @Property("QVariantList", notify=changed)
    def folders(self):
        """The folder tree, flattened: [{path, name, depth, count, children, open}], only under open folders.
        "" is « Notes », the notes outside any folder."""
        counts = {}
        for n in self._notes.values():
            counts[n["category"]] = counts.get(n["category"], 0) + 1
        open_ = set(self._app.pref("expanded") or [])
        rows = [{"path": "", "name": self._app.t["folder_root"], "depth": 0, "count": counts.get("", 0),
                 "children": False, "open": False}]
        cats = self._categories()
        for c in cats:
            ancestors = ["/".join(c.split("/")[:i]) for i in range(1, c.count("/") + 1)]
            if any(a not in open_ for a in ancestors):
                continue
            rows.append({"path": c, "name": c.rsplit("/", 1)[-1], "depth": c.count("/"),
                         "count": sum(v for k, v in counts.items() if k == c or k.startswith(c + "/")),
                         "children": any(x.startswith(c + "/") for x in cats), "open": c in open_})
        return rows

    @Property("QVariantList", notify=changed)
    def allFolders(self):
        """Every folder (to move notes there), with its full path as its name."""
        return [{"path": "", "name": self._app.t["folder_root"]}] + \
               [{"path": c, "name": c.replace("/", " › ")} for c in self._categories()]

    @Slot(str)
    def toggleFolder(self, path):
        open_ = [p for p in (self._app.pref("expanded") or []) if p != path]
        if path not in (self._app.pref("expanded") or []):
            open_.append(path)
        self._app.setPref("expanded", open_)

    @Property("QVariantList", notify=changed)
    def tags(self):
        counts = {}
        for n in self._notes.values():
            for tag in markdown.tags(n["content"]):
                counts[tag] = counts.get(tag, 0) + 1
        return [{"tag": t, "count": c} for t, c in sorted(counts.items(), key=lambda x: (-x[1], x[0]))][:40]

    @Property("QVariantMap", notify=changed)
    def counts(self):
        return {"all": len(self._notes), "pinned": sum(1 for n in self._notes.values() if n["favorite"]),
                "shared": sum(1 for n in self._notes.values() if self._shared_kind(n)),
                "trash": len(self._trash) + (len(self._store.deleted_here()) if self._store else 0)}

    # ---- the list ------------------------------------------------------------------------------------------
    @Property(str, notify=folderChanged)
    def folder(self):
        return self._folder

    @Property(str, notify=folderChanged)
    def heading(self):
        f = self._folder
        if self._query:
            return self._app.t["results"]
        if f == "all":
            return self._app.t["all_notes"]
        if f == "trash":
            return self._app.t["trash"]
        if f == "shared":
            return self._app.t["shared_notes"]
        if f.startswith("tag:"):
            return "#" + f[4:]
        path = f[7:]
        return path.rsplit("/", 1)[-1] if path else self._app.t["folder_root"]

    @Slot(str)
    def setFolder(self, folder):
        if folder != self._folder:
            self._folder = folder
            if not folder.startswith("tag:") and folder not in ("trash", "shared"):
                self._app.setPref("folder", folder)
            self._rebuild()
            self.folderChanged.emit()
            if folder == "trash":
                self.loadTrash()
            if folder == "shared":
                self.loadSharing()

    @Property(str, notify=changed)
    def query(self):
        return self._query

    @Slot(str)
    def setQuery(self, query):
        if query != self._query:
            self._query = query
            self._rebuild()
            self.folderChanged.emit()

    def _in(self, n, folder):
        if folder == "all":
            return True
        if folder == "shared":
            return self._shared_kind(n) != ""
        if folder.startswith("tag:"):
            return folder[4:] in markdown.tags(n["content"])
        if folder.startswith("folder:"):
            return n["category"] == folder[7:]
        return False

    def _section(self, n, sort):
        if n["favorite"]:
            return "pinned", self._app.t["pinned"]
        if not self._app.pref("group_dates") or sort == "title":
            return "notes", self._app.t["notes"]
        stamp = n["created"] if sort == "created" else n["modified"]
        day = datetime.fromtimestamp(stamp or 0).date()
        today = date.today()
        delta = (today - day).days
        if delta <= 0:
            return "today", self._app.t["today"]
        if delta == 1:
            return "yesterday", self._app.t["yesterday"]
        if delta < 7:
            return "week", self._app.t["previous_7"]
        if delta < 30:
            return "month", self._app.t["previous_30"]
        months = self._app.t["months_long"].split(",")
        if day.year == today.year:
            return f"m{day.month:02d}", months[day.month - 1].capitalize()
        return f"y{day.year}", str(day.year)

    def _thumb(self, n):
        for _alt, ref in markdown.images(n["content"]):
            if markdown.is_attachment(ref):
                return self._image_url(n, ref, fetch=False)
        return ""

    def _row(self, n, words=(), sort="modified"):
        title = markdown.title_of(n["content"]) or n["title"] or self._app.t["untitled"]
        preview = markdown.preview(n["content"])
        if words:
            hay = fold(n["content"])
            at = min([hay.find(w) for w in words if hay.find(w) >= 0] or [-1])
            if at > 60:
                flat = " ".join(n["content"].split())
                at_flat = fold(flat).find(words[0])
                if at_flat > 0:
                    preview = "…" + flat[max(0, at_flat - 30):at_flat + 130]
        section, label = self._section(n, sort) if not words else ("results", self._app.t["results"])
        done, total = markdown.checklist(n["content"])
        return {"key": n["key"], "rid": n["rid"] or 0, "title": title, "preview": preview or self._app.t["no_text"],
                "modified": n["modified"], "created": n["created"], "folder": n["category"],
                "folderName": n["category"].rsplit("/", 1)[-1] if n["category"] else self._app.t["folder_root"],
                "pinned": bool(n["favorite"]), "pending": bool(n["pending"]), "shared": bool(n["shared"]),
                "readonly": bool(n["readonly"]), "thumb": self._thumb(n), "section": section, "sectionLabel": label,
                "checks": f"{done}/{total}" if total else "", "trashed": False, **self._sharing_of(n)}

    def _rebuild(self):
        words = fold(self._query).split()
        sort = self._app.pref("sort") or "modified"
        if self._folder == "trash" and not words:
            self._items = self._trash_rows()
            self.changed.emit()
            return
        folder = "all" if words else self._folder
        chosen = [n for n in self._notes.values() if self._in(n, folder)
                  and (not words or all(w in fold(n["content"] + " " + n["category"]) for w in words))]
        if sort == "title":
            chosen.sort(key=lambda n: fold(markdown.title_of(n["content"]) or n["title"]))
        else:
            chosen.sort(key=lambda n: -(n["created"] if sort == "created" else n["modified"]))
        if not words:
            chosen.sort(key=lambda n: 0 if n["favorite"] else 1)
        self._items = [self._row(n, words, sort) for n in chosen]
        self.changed.emit()

    @Property("QVariantList", notify=changed)
    def items(self):
        return self._items

    # ---- one note ------------------------------------------------------------------------------------------
    @Slot(str, result="QVariantMap")
    def detail(self, key):
        if key.startswith("trash:") or key.startswith("deleted:"):
            return self._trash_detail(key)
        n = self._notes.get(key) or (self._store.note(key) if self._store else None)
        if not n:
            return {}
        images = []
        for alt, ref in markdown.images(n["content"]):
            if markdown.is_attachment(ref):
                images.append({"ref": ref, "alt": alt, "url": self._image_url(n, ref)})
        done, total = markdown.checklist(n["content"])
        files = [{"ref": ref, "name": label or urllib.parse.unquote(ref).rsplit("/", 1)[-1]}
                 for label, ref in markdown.files(n["content"])]
        return {"key": key, "rid": n["rid"] or 0, "content": n["content"], "title": markdown.title_of(n["content"]),
                "files": files, "backlinks": self._backlinks(n), **self._conflict_of(key),
                "folder": n["category"], "folderName": n["category"].replace("/", " › ") if n["category"] else self._app.t["folder_root"],
                "pinned": bool(n["favorite"]), "readonly": bool(n["readonly"]), "shared": bool(n["shared"]),
                "pending": bool(n["pending"]), "modified": n["modified"], "created": n["created"], "images": images,
                "done": done, "total": total, "tags": markdown.tags(n["content"]), "trashed": False,
                "words": len(re.findall(r"\w+", n["content"]))}

    @Slot(str, str)
    def setContent(self, key, content):
        if self._store and self._store.edit(key, content=content):
            n = self._store.note(key)
            if n:
                self._notes[key] = n
            self._rebuild()
            self.stateChanged.emit()
            self._soon.start()

    @Slot(str, result=str)
    def create(self, folder=""):
        """A new empty note, in the folder shown (« Toutes les notes »: outside any folder)."""
        if self._store is None:
            return ""
        if folder == "" and self._folder.startswith("folder:"):
            folder = self._folder[7:]
        if self._folder.startswith("tag:"):
            # from a #tag: the new note has it (and stays in the list shown), as on macOS
            key = self._store.create("\n\n#" + self._folder[4:] + " ", folder)
            self._query = ""
            self._reload()
            return key
        key = self._store.create("", folder)
        if self._folder not in ("all", "folder:" + folder):
            self._folder = "folder:" + folder if not self._folder.startswith("folder:") else self._folder
            self.folderChanged.emit()
        self._query = ""
        self._reload()
        return key

    @Slot(str, result=str)
    def createQuick(self, content):
        if self._store is None:
            return ""
        key = self._store.create(content, self._app.pref("quick_folder") or "")
        self._reload()
        return key

    def _changed_here(self):
        self._reload()
        self.stateChanged.emit()
        self._soon.start()

    @Slot(str)
    def togglePin(self, key):
        n = self._notes.get(key)
        if n and self._store:
            self._store.edit(key, favorite=not n["favorite"])
            self._changed_here()

    @Slot("QVariantList", bool)
    def pinMany(self, keys, on):
        for key in keys:
            if key in self._notes and self._store:
                self._store.edit(key, favorite=on)
        self._changed_here()

    @Slot("QVariantList", str)
    def moveTo(self, keys, folder):
        for key in keys:
            if key in self._notes and self._store and not self._notes[key]["readonly"]:
                self._store.edit(key, category=folder)
        self._forget_empty(folder)
        self._changed_here()

    @Slot(str, result=str)
    def duplicate(self, key):
        n = self._notes.get(key)
        if not n or self._store is None:
            return ""
        title = markdown.title_of(n["content"])
        content = n["content"]
        if title:
            content = content.replace(title, self._app.t["copy_of"].replace("%1", title), 1)
        new = self._store.create(content, n["category"])
        # its own copy of the images and files: the original's would go with it
        missing = []
        for ref in dict.fromkeys(markdown.attachments(content)):
            path = self._local_attachment(n, ref)
            if path is None:
                missing.append(ref)
                continue
            content = self._copy_attachment(new, ref, path, content)
        self._store.edit(new, content=content)
        if missing and n["rid"]:
            rid = n["rid"]

            def fetch(api):
                return {ref: api.attachment(rid, urllib.parse.unquote(ref)) for ref in missing}

            def then(files):
                current = (self._store.note(new) or {}).get("content") if self._store else None
                if current is None:
                    return
                folder = IMAGES / "copies"
                folder.mkdir(parents=True, exist_ok=True)
                for ref, data in files.items():
                    tmp = folder / urllib.parse.unquote(ref).rsplit("/", 1)[-1]
                    tmp.write_bytes(data)
                    current = self._copy_attachment(new, ref, tmp, current)
                    tmp.unlink(missing_ok=True)
                self._store.edit(new, content=current)
                self._changed_here()
                self.noteUpdated.emit(new)
            self._job("duplicate", fetch, then, quiet=True)
        self._changed_here()
        return new

    def _local_attachment(self, n, ref):
        """The file of an attachment on this computer (added here, or seen once), else None."""
        local = self._store.local_file(n["key"], urllib.parse.unquote(ref)) if self._store else None
        if local:
            return local
        if n["rid"]:
            path = self._cache_path(n["rid"], ref)
            if path.is_file():
                return path
        return None

    def _copy_attachment(self, key, ref, path, content):
        """path attached to note key in place of ref: content with the new link."""
        name = urllib.parse.unquote(ref).rsplit("/", 1)[-1]
        kind = mimetypes.guess_type(name)[0] or "application/octet-stream"
        try:
            data = Path(path).read_bytes()
        except OSError:
            return content
        new_ref = self._store.add_upload(key, name, data, kind)
        if not new_ref:
            return content
        return content.replace(f"]({ref})", f"]({urllib.parse.quote(new_ref, safe='/.()')})")

    @Slot("QVariantList")
    def delete(self, keys):
        """To « Récemment supprimées » (the cloud's trash), with a few seconds to change one's mind."""
        keys = [k for k in keys if k in self._notes and not self._notes[k]["readonly"]]
        if not keys or self._store is None:
            return
        never_sent = [k for k in keys if not self._notes[k]["rid"]]
        kept = {k: dict(self._notes[k]) for k in never_sent}
        self._store.delete(*keys)
        for k in keys:
            self._held[k] = kept.get(k)
        self._store.hold = tuple(self._held)       # a sync already running leaves them too, while « Annuler » shows
        self._release.start(UNDO_MS)
        self._reload()
        self.stateChanged.emit()
        label = self._app.plural("deleted_many", len(keys)) if len(keys) > 1 else self._app.t["deleted_one"]
        self.done.emit("deleted", True, label)

    @Slot(str)
    def discard(self, key):
        """A Quick Note closed without a word: it goes without a trace."""
        n = self._notes.get(key)
        if n and self._store and not n["content"].strip():
            self._store.delete(key)
            self._reload()
            self.stateChanged.emit()

    @Slot()
    def undoDelete(self):
        if self._store is None:
            return
        for key, kept in list(self._held.items()):
            if kept is None:
                self._store.undelete(key)
            else:
                new = self._store.create(kept["content"], kept["category"], kept["favorite"])
                self._held.pop(key, None)
                self.created.emit(new)
        self._held.clear()
        self._store.hold = ()
        self._release.stop()
        self._reload()
        self.stateChanged.emit()

    def _release_held(self):
        self._held.clear()
        self.refresh()

    # ---- folders -----------------------------------------------------------------------------------------
    def _forget_empty(self, folder):
        empties = [f for f in (self._app.pref("empty_folders") or []) if f != folder]
        if empties != (self._app.pref("empty_folders") or []):
            self._app.setPref("empty_folders", empties)

    @Slot(str, str, result=str)
    def createFolder(self, parent, name):
        name = name.strip().replace("/", "-")
        if not name:
            return ""
        path = f"{parent}/{name}" if parent else name
        if path not in self._categories():
            self._app.setPref("empty_folders", list(self._app.pref("empty_folders") or []) + [path])
        if parent:
            self._app.setPref("expanded", list(set((self._app.pref("expanded") or []) + [parent])))
        self.setFolder("folder:" + path)
        self.changed.emit()
        return path

    @Slot(str, str)
    def renameFolder(self, path, name):
        name = name.strip().replace("/", "-")
        if not name or self._store is None:
            return
        new = (path.rsplit("/", 1)[0] + "/" + name) if "/" in path else name
        self._store.rename_folder(path, new)
        empties = [new + f[len(path):] if f == path or f.startswith(path + "/") else f
                   for f in (self._app.pref("empty_folders") or [])]
        self._app.setPref("empty_folders", empties)
        if self._folder == "folder:" + path:
            self._folder = "folder:" + new
            self.folderChanged.emit()
        self._changed_here()

    @Slot(str, bool)
    def deleteFolder(self, path, with_notes):
        """The folder goes; its notes too (to « Récemment supprimées »), or back to « Notes »."""
        if self._store is None:
            return
        inside = [k for k, n in self._notes.items() if n["category"] == path or n["category"].startswith(path + "/")]
        if with_notes:
            self.delete(inside)
        else:
            for key in inside:
                self._store.edit(key, category="")
        self._app.setPref("empty_folders", [f for f in (self._app.pref("empty_folders") or [])
                                            if f != path and not f.startswith(path + "/")])
        if self._folder == "folder:" + path or self._folder.startswith("folder:" + path + "/"):
            self.setFolder("all")
        self._changed_here()

    # ---- recently deleted ----------------------------------------------------------------------------------
    def _trash_rows(self):
        rows = []
        for n in (self._store.deleted_here() if self._store else []):
            rows.append({"key": "deleted:" + n["key"], "title": markdown.title_of(n["content"]) or self._app.t["untitled"],
                         "preview": markdown.preview(n["content"]) or self._app.t["no_text"], "modified": n["modified"],
                         "folder": n["category"], "folderName": n["category"] or self._app.t["folder_root"], "pinned": False,
                         "pending": True, "shared": False, "readonly": False, "thumb": "", "section": "trash",
                         "sectionLabel": "", "checks": "", "trashed": True})
        for t in self._trash:
            rows.append({"key": "trash:" + t["href"], "title": t["title"], "preview": self._app.t["deleted_on"].replace("%1", self._app.short(t["deleted"])),
                         "modified": t["deleted"], "folder": t["category"], "folderName": t["category"] or self._app.t["folder_root"],
                         "pinned": False, "pending": False, "shared": False, "readonly": True, "thumb": "", "section": "trash",
                         "sectionLabel": "", "checks": "", "trashed": True})
        return rows

    def _trash_detail(self, key):
        if key.startswith("deleted:"):
            n = self._store.note(key[8:]) if self._store else None
            if not n:
                return {}
            return {"key": key, "content": n["content"], "title": markdown.title_of(n["content"]), "folder": n["category"],
                    "folderName": n["category"] or self._app.t["folder_root"], "readonly": True, "trashed": True,
                    "modified": n["modified"], "created": n["created"], "images": [], "pinned": False, "pending": True,
                    "tags": [], "done": 0, "total": 0, "words": 0}
        href = key[6:]
        item = next((t for t in self._trash if t["href"] == href), None)
        if not item:
            return {}
        content = self._trash_content.get(href)
        if content is None and href not in self._trash_loading:
            self._trash_loading.add(href)

            def got(text):
                self._trash_loading.discard(href)
                self._trash_content[href] = text
                self.trashChanged.emit()
            self._job("trash", lambda api: api.trash_content(href), got,
                      undo=lambda: self._trash_loading.discard(href))
        return {"key": key, "content": content or "", "title": item["title"], "folder": item["category"],
                "folderName": item["category"] or self._app.t["folder_root"], "readonly": True, "trashed": True,
                "modified": item["deleted"], "created": 0, "images": [], "pinned": False, "pending": False, "tags": [],
                "done": 0, "total": 0, "words": 0, "loading": content is None}

    @Slot()
    def loadTrash(self):
        if self._store is None:
            return
        path = self._store.meta("notes_path", "Notes")

        def then(rows):
            self._trash = rows
            if self._folder == "trash":
                self._rebuild()
            self.trashChanged.emit()
        self._job("trash", lambda api: api.trash(path), then, quiet=True)

    @Slot("QVariantList")
    def restore(self, keys):
        for key in keys:
            if key.startswith("deleted:") and self._store:
                self._store.undelete(key[8:])
            elif key.startswith("trash:"):
                href = key[6:]
                self._trash = [t for t in self._trash if t["href"] != href]
                self._job("restore", lambda api, h=href: api.restore(h), lambda _r: self.refresh())
        self._changed_here()
        self.done.emit("restored", True, self._app.plural("restored_many", len(keys)))

    @Slot("QVariantList")
    def purge(self, keys):
        hrefs = [k[6:] for k in keys if k.startswith("trash:")]
        local = [k[8:] for k in keys if k.startswith("deleted:")]
        self._trash = [t for t in self._trash if t["href"] not in hrefs]
        if self._store and local:
            # deleted here, not yet in the cloud: straight to the cloud's trash, then out of it
            notes = {k: self._store.note(k) for k in local}

            def job(api):
                for k, n in notes.items():
                    if n and n["rid"]:
                        api.delete(n["rid"])
                path = self._store.meta("notes_path", "Notes")
                trash = api.trash(path)
                for n in notes.values():
                    if not n or not n["rid"]:
                        continue
                    found = self._trash_item(n, trash, path)
                    if found:
                        api.purge(found["href"])
                        trash.remove(found)
                with self._store.lock:
                    for k in local:
                        self._store.db.execute("DELETE FROM notes WHERE key = ?", (k,))
            self._job("purge", job, lambda _r: (self._reload(), self.loadTrash()))
        for href in hrefs:
            self._job("purge", lambda api, h=href: api.purge(h), lambda _r: None)
        self._rebuild()

    @staticmethod
    def _trash_item(n, trash, notes_path):
        """The cloud's trash entry of note n: the one deleted from its own file (the newest when it was deleted
        more than once); without its path, only when a single entry has its title in its folder."""
        own = (n["path"] or "").strip("/")
        if own:
            same = [t for t in trash if t.get("original") == own]
            return same[0] if same else None
        same = [t for t in trash if t["title"] == n["title"] and t["category"] == n["category"]]
        return same[0] if len(same) == 1 else None

    # ---- images and files ------------------------------------------------------------------------------------
    def _cache_path(self, rid, ref):
        safe = re.sub(r"[^\w.\-]+", "_", ref)
        return IMAGES / str(rid) / safe

    def _image_url(self, n, ref, fetch=True):
        local = self._store.local_file(n["key"], urllib.parse.unquote(ref)) if self._store else None
        if local:
            return QUrl.fromLocalFile(str(local)).toString()
        if not n["rid"]:
            return ""
        path = self._cache_path(n["rid"], ref)
        if path.is_file():
            return QUrl.fromLocalFile(str(path)).toString()
        if fetch and (n["rid"], ref) not in self._asked:
            self._asked.add((n["rid"], ref))
            api = self.api()
            if api is not None:
                def run(rid=n["rid"]):
                    try:
                        data = api.attachment(rid, urllib.parse.unquote(ref))
                    except ApiError:
                        self._asked.discard((rid, ref))
                        return
                    finally:
                        api.close()
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(data)
                    self._ran.emit(lambda: (self._rebuild(), self.imagesChanged.emit()))
                self._fetch.submit(run)
        return ""

    def _attach(self, key, path):
        """The Markdown that shows (an image) or links (another file) a file attached to the note."""
        try:
            if os.path.getsize(path) > MAX_FILE:
                self._app.toast.emit(self._app.t["file_too_big"].replace("%1", os.path.basename(path)))
                return ""
            data = Path(path).read_bytes()
        except OSError:
            return ""
        name = os.path.basename(path)
        kind = mimetypes.guess_type(name)[0] or "application/octet-stream"
        ref = self._store.add_upload(key, name, data, kind)
        if not ref:
            return ""
        link = urllib.parse.quote(ref, safe="/.()")
        return f"![{Path(name).stem}]({link})" if kind.startswith("image/") else f"[📎 {name}]({link})"

    @Slot(str, "QVariantList", result=str)
    def attach(self, key, urls):
        """Files dropped on a note, or picked with « Joindre un fichier »: the text to insert at the cursor."""
        parts = []
        for url in urls:
            url = str(url.toString() if hasattr(url, "toString") else url)
            path = QUrl(url).toLocalFile() if url.startswith("file:") else url
            if os.path.isfile(path):
                text = self._attach(key, path)
                if text:
                    parts.append(text)
        if parts:
            self.stateChanged.emit()
            self._soon.start()
        return "\n".join(parts)

    # ---- links to mails, notes and tasks (links.py): dropped, pasted or picked, shown as chips -----------------
    def _server(self):
        account = self._app.account()
        return account[0] if account else ""

    def _note_links(self, keys):
        out = []
        for key in keys:
            n = self._notes.get(key)
            if n:
                out.append({"url": links.note_url(self._server(), n["rid"], key), "kind": "note",
                            "title": markdown.title_of(n["content"]) or self._app.t["untitled"]})
        return out

    @Slot("QVariantList", result="QVariantMap")
    def dragData(self, keys):
        """A dragged note: its key for the sidebar's folders, a link for another note, Tâches or anything else."""
        keys = [str(k) for k in (keys.toVariant() if hasattr(keys, "toVariant") else keys)]
        items = self._note_links(keys)
        data = {"orneos/notes": ",".join(keys)}
        if items:
            data.update({links.MIME: links.encode(items), "text/plain": "\n".join(i["url"] for i in items)})
        return data

    @Slot("QVariantList")
    def copyLinks(self, keys):
        items = self._note_links([str(k) for k in (keys.toVariant() if hasattr(keys, "toVariant") else keys)])
        if items:
            data = QMimeData()
            data.setData(links.MIME, QByteArray(links.encode(items).encode()))
            data.setText("\n".join(i["url"] for i in items))
            QGuiApplication.clipboard().setMimeData(data)
            self._app.toast.emit(self._app.t["link_copied"])

    def _markdown(self, items, key):
        own = {i["url"] for i in self._note_links([key])}
        items = [i for i in items if i["url"] not in own]
        for item in items:
            if not item.get("title"):
                item["title"] = links.describe(item["url"])["title"]
        if len(items) <= 1:
            return links.markdown(items[0]) if items else ""
        return "\n".join("- " + links.markdown(i) for i in items)

    @Slot(str, str, result=str)
    def linksMarkdown(self, payload, key):
        """Links dropped on the note (from Plume, Tâches, the list), as Markdown; "" when there are none."""
        return self._markdown(links.decode(payload), key)

    @Slot(str, result=str)
    def pasteLinks(self, key):
        """Links copied in Plume, Notes or Tâches (or a pasted address of one), as Markdown; "" otherwise."""
        data = QGuiApplication.clipboard().mimeData()
        if data is None:
            return ""
        if data.hasFormat(links.MIME):
            return self._markdown(links.decode(bytes(data.data(links.MIME).data())), key)
        return self._markdown(links.decode(data.text()), key) if data.hasText() else ""

    @Slot(str)
    def openLink(self, url):
        """A link of the note: a note opens here, a mail in Plume, a task in Tâches, anything else in the browser."""
        kind, ref = links.parse(url)
        if kind == "note" and self.resolve(ref):
            self._app.showRequested.emit(ref)
        elif kind:
            links.open_link(url)
        else:
            self._app.openUrl(url)

    @Slot(str, result="QVariantList")
    def linkCandidates(self, query):
        return links.search(query, self._server())

    @Slot(str, result=str)
    def pasteImage(self, key):
        """An image in the clipboard (a screenshot): attached to the note, "" when the clipboard has none."""
        data = QGuiApplication.clipboard().mimeData()
        if data is None or not data.hasImage() or data.hasText() and not data.hasUrls() and data.text().strip():
            return ""
        image = QGuiApplication.clipboard().image()
        if image.isNull() or self._store is None:
            return ""
        folder = IMAGES / "pasted"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{self._app.t['image_name']} {time.strftime('%Y-%m-%d %H.%M.%S')}.png"
        image.save(str(path), "PNG")
        text = self._attach(key, str(path))
        try:
            path.unlink()
        except OSError:
            pass
        self.stateChanged.emit()
        self._soon.start()
        return text

    @Slot(str, str)
    def openImage(self, key, ref):
        n = self._notes.get(key)
        if not n:
            return
        url = self._image_url(n, ref)
        if url:
            self._app.openFile(QUrl(url).toLocalFile())

    @Slot("QVariantList", result=str)
    def from_files(self, paths):
        """« Ajouter à Notes » in Dolphin: one note, titled after the first file; text files give their text,
        the others are attached (images show in the note)."""
        if self._store is None or not paths:
            return ""
        first = Path(paths[0])
        key = self._store.create(f"# {first.stem}\n\n", self._app.pref("quick_folder") or "")
        body = [f"# {first.stem}" if len(paths) == 1 else f"# {first.stem} (+{len(paths) - 1})", ""]
        for raw in paths:
            path = Path(raw)
            if path.suffix.lower() in TEXT and path.stat().st_size < 512 * 1024:
                try:
                    text = path.read_text(errors="replace")
                except OSError:
                    continue
                if len(paths) > 1:
                    body.append(f"## {path.name}")
                body += [text.rstrip(), ""]
            else:
                attached = self._attach(key, str(path))
                if attached:
                    body += [attached, ""]
        self._store.edit(key, content="\n".join(body).rstrip() + "\n")
        self._changed_here()
        self.created.emit(key)
        return key

    # ---- sending a note elsewhere ------------------------------------------------------------------------------
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
        self._pool.submit(run)

    @Slot(str)
    def shareLink(self, key):
        n = self._notes.get(key)
        if not n:
            return
        if not n["rid"] or not n["path"]:
            self.done.emit("share", False, self._app.t["share_wait_sync"])
            return
        # at once: the link is on its way (copied as soon as the cloud gives it)
        self.done.emit("share", True, self._app.t["share_making"])

        def then(url):
            if url:
                QGuiApplication.clipboard().setText(url)
                self.done.emit("share", True, self._app.t["share_copied"])
                self.loadSharing()
                self.refresh()
            else:
                self.done.emit("share", False, self._app.t["error_server"])
        self._job("share", lambda api: api.share_link(n["path"]), then)

    # ---- shared with people (accounts, groups, teams, e-mail addresses), as in the cloud ----------------------
    def _shared_kind(self, n):
        """"out" (shared by the account, with people or a public link), "in" (shared with it), or ""."""
        if not self._sharing or not n["rid"]:
            return "out" if n["shared"] else ""
        if int(n["rid"]) in self._sharing[1]:
            return "in"
        return "out" if self._sharing[0].get(int(n["rid"])) else ""

    def _sharing_of(self, n):
        """What the list says of a shared note: with whom (or « public link »), or who shared it."""
        kind = self._shared_kind(n)
        if kind == "in":
            return {"sharedKind": "in", "sharedWho": self._sharing[1][int(n["rid"])]["owner"]}
        if kind == "out" and self._sharing:
            rows = self._sharing[0].get(int(n["rid"]), [])
            names = [r["name"] for r in rows if r["type"] != 3] + ([self._app.t["public_link"]] if any(r["type"] == 3 for r in rows) else [])
            return {"sharedKind": "out", "sharedWho": ", ".join(names)}
        return {"sharedKind": kind, "sharedWho": ""}

    @Slot()
    def loadSharing(self):
        """Every share of the account (« Partagées », the list's marks); the dialog starts from it."""
        def then(result):
            out, received = result
            self._sharing = (out, received)
            for key, n in self._notes.items():
                if n["rid"] and int(n["rid"]) in out:
                    self._shares[key] = [r for r in out[int(n["rid"])] if r["type"] != 3]
            self._rebuild()
            for key in self._notes:
                self.sharesChanged.emit(key)
        self._job("sharing", lambda api: api.sharing(), then, quiet=True)

    @Slot(str, result="QVariantMap")
    def sharedWithMe(self, key):
        """{owner, editable} when the note was shared with the account, {} otherwise."""
        n = self._notes.get(key)
        if not n or not n["rid"] or not self._sharing:
            return {}
        got = self._sharing[1].get(int(n["rid"]))
        return {"owner": got["owner"], "editable": got["editable"]} if got else {}

    @Slot(str)
    def leaveShare(self, key):
        """No longer receive a note shared with the account: it leaves the list at once (and the cloud's Notes)."""
        n = self._notes.get(key)
        got = self._sharing[1].get(int(n["rid"])) if n and n["rid"] and self._sharing else None
        if not got:
            return
        self._sharing[1].pop(int(n["rid"]))
        self._rebuild()
        self.done.emit("share", True, self._app.t["share_left"])

        def back():
            self._sharing[1][int(n["rid"])] = got
            self._rebuild()
        self._job("share", lambda api: api.unshare(got["id"]), lambda _r: self.refresh(), undo=back)

    @Slot(str, result="QVariantList")
    def shares(self, key):
        """Who the note is shared with: what the cloud said, with the changes on their way (pending)."""
        changes = self._share_changes.get(key, {})
        rows = [dict(r, **changes[r["id"]], pending=True) if changes.get(r["id"]) else dict(r)
                for r in self._shares.get(key, []) if not (r["id"] in changes and changes[r["id"]] is None)]
        return rows + [dict(c, pending=True) for i, c in changes.items() if c and i.startswith("pending-")]

    def _share_change(self, key, share_id, value):
        if value is False:
            self._share_changes.get(key, {}).pop(share_id, None)
        else:
            self._share_changes.setdefault(key, {})[share_id] = value
        self.sharesChanged.emit(key)

    @Slot(str)
    def loadShares(self, key):
        n = self._notes.get(key)
        if not n or not n["rid"] or not n["path"]:
            return

        def then(rows):
            self._shares[key] = rows
            self.sharesChanged.emit(key)
        self._job("shares", lambda api: api.shares(n["path"]), then, quiet=True)

    @Slot(str, str)
    def findRecipients(self, key, search):
        if len(search.strip()) < 2:
            self.recipientsReady.emit([])
            return
        me = (self._app.account() or ("", ""))[1]
        taken = {(r["type"], r["with"]) for r in self.shares(key)}

        def find(api):
            try:
                return api.sharees(search.strip())
            except ApiError:
                return []
        self._job("recipients", find, lambda rows: self.recipientsReady.emit(
            [r for r in rows if (r["type"], r["with"]) not in taken and not (r["type"] == 0 and r["with"] == me)]), quiet=True)

    @Slot(str, int, str, str, bool)
    def shareWith(self, key, share_type, share_with, name, editable):
        """Shown at once under « Partagée avec »; the cloud follows (a refusal comes back in a dialog)."""
        n = self._notes.get(key)
        if not n:
            return
        if not n["rid"] or not n["path"]:
            self.done.emit("share", False, self._app.t["share_wait_sync"])
            return
        local = "pending-" + str(time.monotonic_ns())
        self._share_change(key, local, {"id": local, "type": share_type, "with": share_with, "name": name or share_with,
                                        "editable": bool(editable)})

        def settle(_result=None):
            self._share_change(key, local, False)
            self.loadShares(key)
            self.loadSharing()
            self.refresh()
        self._job("share", lambda api: api.share(n["path"], share_type, share_with, editable), settle,
                  undo=lambda: self._share_change(key, local, False))

    @Slot(str, str, bool)
    def setShareEditable(self, key, share_id, editable):
        row = next((r for r in self._shares.get(key, []) if r["id"] == share_id), None)
        if row is None:
            return
        self._share_change(key, share_id, dict(row, editable=bool(editable)))

        def settle(_result=None):
            self._shares[key] = [dict(r, editable=bool(editable)) if r["id"] == share_id else r for r in self._shares.get(key, [])]
            self._share_change(key, share_id, False)
        self._job("share", lambda api: api.update_share(share_id, editable), settle,
                  undo=lambda: self._share_change(key, share_id, False))

    @Slot(str, str)
    def unshare(self, key, share_id):
        if share_id.startswith("pending-"):
            return
        self._share_change(key, share_id, None)

        def settle(_result=None):
            self._shares[key] = [r for r in self._shares.get(key, []) if r["id"] != share_id]
            self._share_change(key, share_id, False)
            self.loadSharing()
            self.refresh()
        self._job("share", lambda api: api.unshare(share_id), settle, undo=lambda: self._share_change(key, share_id, False))

    @Slot(str)
    def openInCloud(self, key):
        n = self._notes.get(key)
        self._app.openCloud(f"/apps/notes/note/{n['rid']}" if n and n["rid"] else "/apps/notes/")

    @Slot(str)
    def mail(self, key):
        n = self._notes.get(key)
        if not n:
            return
        title = markdown.title_of(n["content"]) or self._app.t["untitled"]
        body = n["content"]
        lines = body.split("\n")
        if lines and markdown.plain(lines[0]) == title:
            body = "\n".join(lines[1:]).lstrip("\n")
        self._app.compose("mailto:?subject=" + urllib.parse.quote(title) + "&body=" + urllib.parse.quote(body))

    @Slot(str, result=str)
    def exportName(self, key):
        n = self._notes.get(key) or {}
        title = re.sub(r'[\\/:*?"<>|]+', "-", markdown.title_of(n.get("content", "")) or self._app.t["untitled"])
        folder = Path.home() / ("Documents" if (Path.home() / "Documents").is_dir() else "")
        return str(folder / title)

    @Slot(str, str, result=bool)
    def exportFile(self, key, path):
        """A note as Markdown (.md, the cloud's own file) or as PDF, with its images."""
        n = self._notes.get(key)
        path = QUrl(path).toLocalFile() if path.startswith("file:") else path
        if not n or not path:
            return False
        try:
            if path.lower().endswith(".pdf"):
                content = n["content"]
                for _alt, ref in markdown.images(content):
                    url = self._image_url(n, ref, fetch=False) if markdown.is_attachment(ref) else ""
                    content = content.replace(f"]({ref})", f"]({url})" if url else "]()")
                doc = QTextDocument()
                font = QFont("Schibsted Grotesk")
                font.setPointSizeF(11)
                doc.setDefaultFont(font)
                doc.setMarkdown(content)
                writer = QPdfWriter(path)
                writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
                writer.setResolution(144)
                writer.setTitle(markdown.title_of(n["content"]))
                writer.setCreator("Orneos Notes")
                doc.setPageSize(writer.pageLayout().paintRectPixels(144).size().toSizeF())
                doc.print_(writer)
            else:
                Path(path).write_text(n["content"], encoding="utf-8")
            return True
        except Exception:
            traceback.print_exc()
            return False

    # ---- the note shown: a shared one is read again more often --------------------------------------------------
    @Slot(str)
    def setOpen(self, key):
        self._open = key or ""

    def _poll_shared(self):
        n = self._notes.get(self._open)
        if (n is None or not self._online or self._syncing
                or QGuiApplication.applicationState() != Qt.ApplicationState.ApplicationActive):
            return
        if n["shared"] or self._shared_kind(n):
            self.refresh()

    # ---- notes that link to this one -------------------------------------------------------------------------
    def _backlinks(self, n):
        marks = ["orneos://note/" + n["key"]]
        if n["rid"]:
            marks += [f"/apps/notes/note/{int(n['rid'])})", f"/apps/notes/#/note/{int(n['rid'])})"]
        out = []
        for other in self._notes.values():
            if other["key"] != n["key"] and any(m in other["content"] for m in marks):
                out.append({"key": other["key"], "title": markdown.title_of(other["content"]) or self._app.t["untitled"],
                            "modified": other["modified"]})
        return sorted(out, key=lambda x: -x["modified"])[:12]

    # ---- #tags: renamed (merged when the new one exists) or taken off every note ---------------------------------
    def _retag(self, fn):
        changed = []
        for key, n in list(self._notes.items()):
            if n["readonly"] or self._store is None:
                continue
            text = fn(n["content"])
            if text != n["content"] and self._store.edit(key, content=text):
                changed.append(key)
        if changed:
            self._changed_here()
            for key in changed:
                self.noteUpdated.emit(key)
        return len(changed)

    @Slot(str, str)
    def renameTag(self, old, new):
        new = re.sub(r"[^\w\-/]+", "-", new.strip().lstrip("#")).strip("-/")
        if not new or new.lower() == old.lower():
            return
        count = self._retag(lambda text: markdown.rename_tag(text, old, new))
        if self._folder == "tag:" + old:
            self.setFolder("tag:" + new.lower())
        self.done.emit("tag", True, self._app.plural("tag_renamed", count))

    @Slot(str)
    def deleteTag(self, tag):
        count = self._retag(lambda text: markdown.remove_tag(text, tag))
        if self._folder == "tag:" + tag:
            self.setFolder("all")
        self.done.emit("tag", True, self._app.plural("tag_removed", count))

    @Property("QVariantList", notify=changed)
    def allTags(self):
        counts = {}
        for n in self._notes.values():
            for tag in markdown.tags(n["content"]):
                counts[tag] = counts.get(tag, 0) + 1
        return [{"tag": t, "count": c} for t, c in sorted(counts.items(), key=lambda x: (-x[1], x[0]))]

    # ---- a folder dragged into another ----------------------------------------------------------------------------
    @Slot(str, str, result=bool)
    def moveFolder(self, path, parent):
        if self._store is None or not path or parent == path or parent.startswith(path + "/"):
            return False
        leaf = path.rsplit("/", 1)[-1]
        new = f"{parent}/{leaf}" if parent else leaf
        if new == path:
            return False
        if new in self._categories():
            self.done.emit("folder", False, self._app.t["folder_exists"].replace("%1", leaf))
            return False
        self._store.rename_folder(path, new)
        self._app.setPref("empty_folders", [new + f[len(path):] if f == path or f.startswith(path + "/") else f
                                            for f in (self._app.pref("empty_folders") or [])])
        if parent:
            self._app.setPref("expanded", list(set((self._app.pref("expanded") or []) + [parent])))
        if self._folder == "folder:" + path or self._folder.startswith("folder:" + path + "/"):
            self._folder = "folder:" + new + self._folder[len("folder:" + path):]
            self.folderChanged.emit()
        self._changed_here()
        return True

    # ---- the other version kept by a conflict -------------------------------------------------------------------
    def _conflicts(self):
        if self._store is None:
            return {}
        found = self._store.conflicts()
        for copy, original in list(found.items()):
            gone = [k for k in (copy, original) if not (self._store.note(k) or {"deleted": 1}).get("deleted") == 0]
            if gone:
                # one of the two left (deleted, merged by hand): the pair is over
                self._store.forget_conflict(copy)
            if gone or copy not in self._notes or original not in self._notes:
                found.pop(copy)       # not shown until the window has both (the sync that made it reloads them)
        return found

    def _conflict_of(self, key):
        found = self._conflicts()
        out = {"conflictOf": {}, "conflictCopies": []}
        if key in found:
            original = self._notes[found[key]]
            out["conflictOf"] = {"key": original["key"], "title": markdown.title_of(original["content"]) or self._app.t["untitled"]}
        out["conflictCopies"] = [{"key": copy, "title": markdown.title_of(self._notes[copy]["content"])}
                                 for copy, original in found.items() if original == key]
        return out

    def _unmark(self, text):
        """The copy's text without the « (autre version) » its title took."""
        before, _, after = self._app.t["conflict_copy"].partition("%1")
        lines = text.split("\n")
        for i, line in enumerate(lines):
            if markdown.plain(line):
                if after and after in line:
                    line = line.replace(after, "", 1)
                if before and before in line:
                    line = line.replace(before, "", 1)
                lines[i] = line
                break
        return "\n".join(lines)

    @Slot(str, result="QVariantList")
    def conflictDiff(self, copy):
        """The note (here) beside its other version, line by line: [{kind: same | here | other, text}]."""
        original = self._conflicts().get(copy)
        if not original:
            return []
        ours = self._notes[original]["content"].split("\n")
        theirs = self._unmark(self._notes[copy]["content"]).split("\n")
        out = []
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, ours, theirs, autojunk=False).get_opcodes():
            if tag == "equal":
                out += [{"kind": "same", "text": line} for line in ours[i1:i2]]
                continue
            out += [{"kind": "here", "text": line} for line in ours[i1:i2]]
            out += [{"kind": "other", "text": line} for line in theirs[j1:j2]]
        return out

    @Slot(str, result=str)
    def keepOther(self, copy):
        """The other version replaces the note; the copy goes (to « Récemment supprimées »). Returns the note."""
        original = self._conflicts().get(copy)
        if not original or self._store is None:
            return ""
        self._store.edit(original, content=self._unmark(self._notes[copy]["content"]))
        self._store.forget_conflict(copy)
        self._reload()
        self.noteUpdated.emit(original)
        self.delete([copy])
        return original

    @Slot(str, result=str)
    def keepHere(self, copy):
        """The note stays as it is here; the other version goes."""
        original = self._conflicts().get(copy, "")
        if self._store is not None:
            self._store.forget_conflict(copy)
        self.delete([copy])
        return original

    @Slot(str)
    def keepBoth(self, copy):
        if self._store is not None:
            self._store.forget_conflict(copy)
            self._reload()

    # ---- earlier versions (the cloud keeps those of the last 90 days) -----------------------------------------------
    @Slot(str)
    def loadVersions(self, key):
        n = self._notes.get(key)
        if not n or not n["rid"]:
            self.versionsReady.emit(key, [])
            return
        rid = n["rid"]

        def then(rows):
            self.versionsReady.emit(key, [dict(r, when=self._app.long(r["modified"])) for r in rows])
        self._job("versions", lambda api: api.versions(rid), then, undo=lambda: self.versionsReady.emit(key, []))

    @Slot(str, str)
    def loadVersion(self, key, href):
        self._job("versions", lambda api: api.version_content(href), lambda text: self.versionReady.emit(key, href, text))

    @Slot(str, str, result="QVariantList")
    def compare(self, before, after):
        """Two texts line by line: [{kind: same | here | other, text}] (here: only in before, other: only in after)."""
        a, b = (before or "").split("\n"), (after or "").split("\n")
        out = []
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
            if tag == "equal":
                out += [{"kind": "same", "text": line} for line in a[i1:i2]]
            else:
                out += [{"kind": "here", "text": line} for line in a[i1:i2]]
                out += [{"kind": "other", "text": line} for line in b[j1:j2]]
        return out

    # ---- text copied from a web page, a mail, a document: its formatting as Markdown ------------------------------
    @Slot(result=str)
    def pasteRich(self):
        data = QGuiApplication.clipboard().mimeData()
        if data is None or not data.hasHtml() or data.hasFormat(links.MIME):
            return ""
        html = data.html()
        if not re.search(r"<(b|strong|i|em|h[1-6]|li|a\s|table|blockquote|pre|s|del|strike)\b", html, re.I):
            return ""
        doc = QTextDocument()
        doc.setHtml(html)
        text = doc.toMarkdown(QTextDocument.MarkdownFeature.MarkdownDialectGitHub)
        text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)          # remote images: not fetched into a note
        text = "\n".join(line.rstrip() for line in text.split("\n"))
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        plain = (data.text() or "").strip()
        return "" if not text or text == plain else text

    # ---- print: the PDF, opened in the system's viewer (it prints) --------------------------------------------------
    @Slot(str)
    def printNote(self, key):
        folder = system.CACHE / "notes-print"
        folder.mkdir(parents=True, exist_ok=True)
        for old in folder.glob("*.pdf"):
            old.unlink(missing_ok=True)
        path = folder / (Path(self.exportName(key)).name + ".pdf")
        if self.exportFile(key, str(path)):
            self._app.openFile(str(path))
        else:
            self.done.emit("print", False, self._app.t["export_failed"])

    # ---- attachments: open, save, copy -----------------------------------------------------------------------------
    def _with_attachment(self, key, ref, then):
        """then(path) with the attachment on this computer (fetched from the cloud first when needed)."""
        n = self._notes.get(key)
        if not n:
            return
        path = self._local_attachment(n, ref)
        if path is not None:
            then(path)
            return
        if not n["rid"]:
            return
        target = self._cache_path(n["rid"], ref)

        def fetch(api):
            data = api.attachment(n["rid"], urllib.parse.unquote(ref))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            return target
        self._job("attachment", fetch, lambda p: (self.imagesChanged.emit(), then(p)))

    @Slot(str, str)
    def openAttachment(self, key, ref):
        self._with_attachment(key, ref, lambda path: self._app.openFile(str(path)))

    @Slot(str, str, str)
    def saveAttachment(self, key, ref, dest):
        dest = QUrl(dest).toLocalFile() if dest.startswith("file:") else dest

        def write(path):
            try:
                Path(dest).write_bytes(Path(path).read_bytes())
                self.done.emit("saved", True, self._app.t["attachment_saved"])
            except OSError:
                self.done.emit("saved", False, self._app.t["export_failed"])
        self._with_attachment(key, ref, write)

    @Slot(str, str)
    def copyImage(self, key, ref):
        def copy(path):
            image = QImage(str(path))
            if not image.isNull():
                QGuiApplication.clipboard().setImage(image)
                self.done.emit("copied", True, self._app.t["image_copied"])
        self._with_attachment(key, ref, copy)

    @Slot(str, result=str)
    def attachmentName(self, ref):
        return urllib.parse.unquote(ref).rsplit("/", 1)[-1]

    # ---- templates and the note of the day ----------------------------------------------------------------------------
    def _template_folder(self):
        return self._app.t["templates_folder"]

    @Property("QVariantList", notify=changed)
    def templates(self):
        """Ready-made ones, then the notes of the « Modèles » folder (the person's own)."""
        out = [{"id": "builtin:" + name, "title": self._app.t["template_" + name], "own": False}
               for name in ("meeting", "project", "journal", "list")]
        folder = self._template_folder()
        own = [n for n in self._notes.values() if n["category"] == folder]
        out += [{"id": n["key"], "title": markdown.title_of(n["content"]) or self._app.t["untitled"], "own": True}
                for n in sorted(own, key=lambda n: fold(markdown.title_of(n["content"])))]
        return out

    def _fill(self, text):
        today = datetime.now()
        return (text.replace("{date}", self._app._day(today))
                .replace("{time}", today.strftime("%H:%M")))

    @Slot(str, result=str)
    def createFrom(self, template):
        """A new note from a template, in the folder shown (never in « Modèles » itself)."""
        if self._store is None:
            return ""
        if template.startswith("builtin:"):
            content = self._app.t.get("template_" + template[8:] + "_text", "")
        else:
            n = self._notes.get(template)
            content = n["content"] if n else ""
        folder = self._folder[7:] if self._folder.startswith("folder:") else ""
        if folder == self._template_folder():
            folder = ""
        key = self._store.create(self._fill(content), folder)
        if self._folder not in ("all", "folder:" + folder):
            self._folder = "folder:" + folder
            self.folderChanged.emit()
        self._query = ""
        self._changed_here()
        return key

    @Slot(result=str)
    def daily(self):
        """Today's note in « Journal »: opened when it is there, made when it is not."""
        if self._store is None:
            return ""
        folder = self._app.t["daily_folder"]
        title = self._app.t["daily_title"].replace("%1", self._app._day(datetime.now()))
        for n in self._notes.values():
            if n["category"] == folder and markdown.title_of(n["content"]) == title:
                return n["key"]
        key = self._store.create(f"# {title}\n\n", folder)
        self._changed_here()
        return key

    # ---- Tâches ------------------------------------------------------------------------------------------------
    @Slot(str, result="QVariantList")
    def openItems(self, key):
        n = self._notes.get(key)
        return markdown.open_items(n["content"]) if n else []

    @Slot(str, "QVariantList")
    def sendToTasks(self, key, items):
        """Items (a checklist, or what Ornis found) become tasks, each with a link back to this note."""
        n = self._notes.get(key) or {}
        out = []
        for item in items:
            item = item.toVariant() if hasattr(item, "toVariant") else item
            if isinstance(item, str):
                item = {"title": item}
            if isinstance(item, dict) and str(item.get("title") or "").strip():
                out.append({"title": str(item["title"]).strip()[:250], "due": str(item.get("due") or ""),
                            "note": str(n.get("rid") or ""), "noteTitle": markdown.title_of(n.get("content", ""))})
        if not out:
            return
        system.launch("tasks", "--add-json", json.dumps(out, ensure_ascii=False))
        self.done.emit("tasks", True, self._app.plural("tasks_sent", len(out)))

    @Slot(str, result=str)
    def resolve(self, ref):
        """A note from its cloud id (links from Tâches, KRunner) or its key."""
        if ref in self._notes:
            return ref
        if ref.isdigit() and self._store:
            return self._store.by_rid(int(ref))
        return ""

    @Slot(str, result="QVariantList")
    def relevant(self, question):
        """The notes that answer a question best (Ornis reads only those): by the words they share with it."""
        words = [w for w in fold(question).split() if len(w) > 2]
        scored = []
        for n in self._notes.values():
            hay = fold(n["content"])
            title = fold(markdown.title_of(n["content"]))
            score = sum(hay.count(w) + 3 * title.count(w) for w in words)
            if score:
                scored.append((-score, -n["modified"], n["key"]))
        return [k for _s, _m, k in sorted(scored)[:6]]
