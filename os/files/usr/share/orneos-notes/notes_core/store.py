"""The notes of the account, offline first: a copy of the cloud's notes in SQLite, what changed here since,
and how the two meet again.

Each note keeps the version the cloud had when the two were last in step (its base). A change made here is
written at once and shows at once; it goes to the cloud on the next sync (right away when online, else when
the network comes back):

- the cloud did not move: the note is sent with If-Match on its ETag;
- the cloud changed it meanwhile (412): the three versions are merged line by line (notes_core.merge). When both
  sides changed the same lines, the text from here is kept and the cloud's goes to a copy of the note,
  "Titre (autre version)", in the same folder: nothing anyone typed is lost;
- the cloud no longer has it: it is created again rather than losing what was typed;
- deleted here, changed elsewhere: the change wins, the note comes back.

Folders are the notes' categories ("Travail/Projets"): renaming one is a change of each of its notes, so it
works offline too. Images pasted into a note wait here until the note exists in the cloud, then go up as its
attachments. Pure Python (no Qt): the window runs it on a worker thread; every method takes the lock.
"""
import json
import re
import sqlite3
import threading
import time
import uuid
from pathlib import Path

import system
from notes_core import markdown
from notes_core.api import ApiError
from notes_core.merge import merge

DATA = system.DATA
DB = DATA / "notes.db"
FILES = DATA / "notes-files"
SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    key TEXT PRIMARY KEY, rid INTEGER UNIQUE, etag TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '', category TEXT NOT NULL DEFAULT '', favorite INTEGER NOT NULL DEFAULT 0,
    modified INTEGER NOT NULL DEFAULT 0, content TEXT NOT NULL DEFAULT '',
    b_category TEXT, b_favorite INTEGER, b_content TEXT,
    deleted INTEGER NOT NULL DEFAULT 0, readonly INTEGER NOT NULL DEFAULT 0, shared INTEGER NOT NULL DEFAULT 0,
    path TEXT NOT NULL DEFAULT '', rev INTEGER NOT NULL DEFAULT 0, created INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS uploads (
    id INTEGER PRIMARY KEY, note_key TEXT NOT NULL, ref TEXT NOT NULL, name TEXT NOT NULL, file TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'application/octet-stream');
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT NOT NULL);
"""
DIRTY = ("(deleted = 1 OR rid IS NULL OR b_content IS NULL OR content <> b_content OR category <> b_category "
         "OR favorite <> b_favorite)")


class Store:
    def __init__(self, user, path=None, untitled="Nouvelle note", conflict="%1 (autre version)"):
        self.user = user
        self.path = Path(path or DB)
        self.untitled = untitled
        self.conflict = conflict
        self.lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path), check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        with self.lock:
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.executescript(SCHEMA)
            owner = self.meta("user")
            if owner and owner != user:
                self._wipe()
            self.set_meta("user", user)

    # ---- small helpers ---------------------------------------------------------------------------------------
    def meta(self, key, default=""):
        with self.lock:
            row = self.db.execute("SELECT v FROM meta WHERE k = ?", (key,)).fetchone()
            return row["v"] if row else default

    def set_meta(self, key, value):
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO meta (k, v) VALUES (?, ?)", (key, str(value)))

    def _wipe(self):
        self.db.executescript("DELETE FROM notes; DELETE FROM uploads; DELETE FROM meta;")

    def forget(self):
        """Signed out, or another account: the copy goes (the cloud keeps everything)."""
        with self.lock:
            self._wipe()

    def close(self):
        with self.lock:
            self.db.close()

    @property
    def synced_at(self):
        return int(self.meta("synced_at", "0") or 0)

    @property
    def loaded(self):
        return self.synced_at > 0

    # ---- what the window shows -------------------------------------------------------------------------------
    def notes(self):
        """Every note not deleted here, as dicts (with "pending" for those the cloud has not seen yet)."""
        with self.lock:
            rows = self.db.execute(f"SELECT *, {DIRTY} AS pending FROM notes WHERE deleted = 0").fetchall()
            return [dict(r) for r in rows]

    def note(self, key):
        with self.lock:
            row = self.db.execute(f"SELECT *, {DIRTY} AS pending FROM notes WHERE key = ?", (key,)).fetchone()
            return dict(row) if row else None

    def by_rid(self, rid):
        with self.lock:
            row = self.db.execute("SELECT key FROM notes WHERE rid = ?", (int(rid),)).fetchone()
            return row["key"] if row else ""

    def deleted_here(self):
        """Notes deleted here and not yet in the cloud's trash (shown first in « Récemment supprimées »)."""
        with self.lock:
            return [dict(r) for r in self.db.execute("SELECT * FROM notes WHERE deleted = 1 ORDER BY modified DESC")]

    def pending_count(self):
        with self.lock:
            notes = self.db.execute(f"SELECT COUNT(*) FROM notes WHERE {DIRTY}").fetchone()[0]
            return notes + self.db.execute("SELECT COUNT(*) FROM uploads").fetchone()[0]

    # ---- changes made here -----------------------------------------------------------------------------------
    def create(self, content="", category="", favorite=False):
        key = "local-" + uuid.uuid4().hex
        now = int(time.time())
        with self.lock:
            self.db.execute("INSERT INTO notes (key, content, category, favorite, modified, created, rev) "
                            "VALUES (?, ?, ?, ?, ?, ?, 1)", (key, content, category, int(bool(favorite)), now, now))
        return key

    def edit(self, key, **fields):
        """content, category, favorite: the note changes here (and later in the cloud)."""
        allowed = {k: v for k, v in fields.items() if k in ("content", "category", "favorite")}
        if not allowed:
            return False
        with self.lock:
            row = self.note(key)
            if row is None or row["readonly"]:
                return False
            if "favorite" in allowed:
                allowed["favorite"] = int(bool(allowed["favorite"]))
            if all(row[k] == v for k, v in allowed.items()):
                return False
            sets = ", ".join(f"{k} = ?" for k in allowed)
            # changing only the pin does not make the note « modified » (it would jump to the top of the list)
            stamp = ", modified = ?" if set(allowed) - {"favorite"} else ""
            values = list(allowed.values()) + ([int(time.time())] if stamp else []) + [key]
            self.db.execute(f"UPDATE notes SET {sets}{stamp}, rev = rev + 1 WHERE key = ?", values)
            return True

    def delete(self, *keys):
        """To the cloud's trash on the next sync (a note never sent is simply forgotten)."""
        with self.lock:
            for key in keys:
                row = self.note(key)
                if row is None:
                    continue
                if row["rid"] is None:
                    self.db.execute("DELETE FROM notes WHERE key = ?", (key,))
                    self.db.execute("DELETE FROM uploads WHERE note_key = ?", (key,))
                else:
                    self.db.execute("UPDATE notes SET deleted = 1, rev = rev + 1 WHERE key = ?", (key,))

    def undelete(self, *keys):
        with self.lock:
            for key in keys:
                self.db.execute("UPDATE notes SET deleted = 0, rev = rev + 1 WHERE key = ?", (key,))

    def rename_folder(self, old, new):
        """Every note of old (and of its subfolders) moves to new."""
        old, new = old.strip("/"), new.strip("/")
        with self.lock:
            for row in self.notes():
                cat = row["category"]
                if cat == old or cat.startswith(old + "/"):
                    self.edit(row["key"], category=new + cat[len(old):])

    def add_upload(self, key, name, data, content_type):
        """An image (or a file) for a note: kept here, linked from the note at once, sent once the note exists
        in the cloud. Returns the link to put in the note."""
        row = self.note(key)
        if row is None:
            return ""
        safe = re.sub(r'[\\/:*?"<>|\n\r]+', "-", name).strip() or "image.png"
        folder = FILES / key
        folder.mkdir(parents=True, exist_ok=True)
        target, n = folder / safe, 1
        while target.exists():
            n += 1
            stem, dot, ext = safe.rpartition(".")
            target = folder / (f"{stem} ({n}).{ext}" if dot else f"{safe} ({n})")
        target.write_bytes(data)
        ref = f".attachments.{row['rid'] or key}/{target.name}"
        with self.lock:
            self.db.execute("INSERT INTO uploads (note_key, ref, name, file, type) VALUES (?, ?, ?, ?, ?)",
                            (key, ref, target.name, str(target), content_type))
        return ref

    def local_file(self, key, ref):
        """The file of an image added here (before or after it went up), else None."""
        name = ref.rsplit("/", 1)[-1]
        path = FILES / key / name
        return path if path.is_file() else None

    # ---- conflict copies: which note each « (autre version) » comes from ---------------------------------------
    def conflicts(self):
        """{copy key: original key} of the copies made by a conflict that are still here."""
        try:
            found = json.loads(self.meta("conflicts", "{}") or "{}")
        except json.JSONDecodeError:
            found = {}
        return found if isinstance(found, dict) else {}

    def _record_conflict(self, copy, original):
        with self.lock:
            found = self.conflicts()
            found[copy] = original
            self.set_meta("conflicts", json.dumps(found))

    def forget_conflict(self, copy):
        with self.lock:
            found = self.conflicts()
            if found.pop(copy, None) is not None:
                self.set_meta("conflicts", json.dumps(found))

    # ---- sync ------------------------------------------------------------------------------------------------
    def _title(self, content):
        return markdown.title_of(content) or self.untitled

    def _store_remote(self, key, remote):
        """The cloud's note becomes both this note and its base."""
        content = remote.get("content") or ""
        self.db.execute(
            "UPDATE notes SET rid = ?, etag = ?, title = ?, category = ?, favorite = ?, modified = ?, content = ?, "
            "b_category = ?, b_favorite = ?, b_content = ?, deleted = 0, readonly = ?, shared = ?, path = ? WHERE key = ?",
            (int(remote["id"]), remote.get("etag") or "", remote.get("title") or "", remote.get("category") or "",
             int(bool(remote.get("favorite"))), int(remote.get("modified") or 0), content,
             remote.get("category") or "", int(bool(remote.get("favorite"))), content,
             int(bool(remote.get("readonly"))), int(bool(remote.get("isShared"))), remote.get("internalPath") or "", key))

    def _insert_remote(self, remote):
        key = "n" + str(int(remote["id"]))
        with self.lock:
            self.db.execute("INSERT OR IGNORE INTO notes (key, created) VALUES (?, ?)",
                            (key, int(remote.get("modified") or time.time())))
            self._store_remote(key, remote)
        return key

    def _conflict_copy(self, text):
        """The cloud's version of a note whose same lines changed here too: its title says so."""
        lines = text.split("\n")
        for i, line in enumerate(lines):
            title = markdown.plain(line)
            if title:
                renamed = self.conflict.replace("%1", title)
                lines[i] = line.replace(title, renamed, 1) if title in line else renamed
                break
        return "\n".join(lines)

    def _merge_into(self, row, remote):
        """The cloud changed a note that also changed here: one version of both (or the cloud's in a copy).
        Returns True when the merged note still has to go up."""
        theirs = remote.get("content") or ""
        base = row["b_content"] if row["b_content"] is not None else ""
        text, clean = merge(base, row["content"], theirs)
        category = row["category"] if row["b_category"] is None or row["category"] != row["b_category"] else (remote.get("category") or "")
        favorite = row["favorite"] if row["b_favorite"] is None or row["favorite"] != row["b_favorite"] else int(bool(remote.get("favorite")))
        with self.lock:
            self.db.execute(
                "UPDATE notes SET rid = ?, etag = ?, title = ?, b_category = ?, b_favorite = ?, b_content = ?, "
                "content = ?, category = ?, favorite = ?, deleted = 0, readonly = ?, shared = ?, path = ?, rev = rev + 1 "
                "WHERE key = ?",
                (int(remote["id"]), remote.get("etag") or "", remote.get("title") or "", remote.get("category") or "",
                 int(bool(remote.get("favorite"))), theirs, text, category, favorite, int(bool(remote.get("readonly"))),
                 int(bool(remote.get("isShared"))), remote.get("internalPath") or "", row["key"]))
            if not clean and theirs.strip():
                copy = self.create(self._conflict_copy(theirs), remote.get("category") or "")
                self._record_conflict(copy, row["key"])
        return text != theirs or category != (remote.get("category") or "") or favorite != int(bool(remote.get("favorite")))

    def push(self, api, report=None, locked=None):
        """Send what changed here. Stops (ApiError 0) when the network goes; a note the cloud refuses (rights)
        is told through report(title, error) and taken back as the cloud has it on the next read. A note
        locked in the cloud (423: open in the cloud's editor) keeps its change for a later sync, told through
        locked(key, title), and the other notes go on."""
        while True:
            with self.lock:
                held = ",".join("?" * len(self.hold))
                where = f"{DIRTY} AND key NOT IN ({held})" if self.hold else DIRTY
                row = self.db.execute(f"SELECT * FROM notes WHERE {where} ORDER BY modified LIMIT 1 OFFSET ?",
                                      (*self.hold, self._skip)).fetchone()
                row = dict(row) if row else None
            if row is None:
                break
            try:
                self._send(api, row)
            except ApiError as error:
                if error.status == 423:
                    self._skip += 1
                    if locked:
                        locked(row["key"], self._title(row["content"]))
                    continue
                if error.status in (0, 401, 429) or error.status >= 500:
                    raise
                with self.lock:
                    if row["rid"] is not None and row["b_content"] is not None:
                        # back to the cloud's version, so a refused change is not sent again and again; what
                        # was typed here stays, in a new note
                        if row["content"] != row["b_content"] and not row["deleted"]:
                            copy = self.create(self._conflict_copy(row["content"]), "")
                            self._record_conflict(copy, row["key"])
                        self.db.execute("UPDATE notes SET content = b_content, category = b_category, "
                                        "favorite = b_favorite, deleted = 0 WHERE key = ?", (row["key"],))
                    else:
                        self._skip += 1
                if report:
                    report(self._title(row["content"]), error)
        self._send_uploads(api)

    _skip = 0
    hold = ()           # notes deleted a moment ago: not sent while « Annuler » is still on screen

    def _send(self, api, row):
        key = row["key"]
        if row["deleted"]:
            if row["rid"] is not None:
                # changed elsewhere since: that change wins over the delete, the note comes back
                try:
                    fresh = api.note(row["rid"])
                except ApiError as error:
                    if error.status != 404:
                        raise
                    fresh = None
                if fresh and fresh.get("etag") and fresh.get("etag") != row["etag"]:
                    with self.lock:
                        self._store_remote(key, fresh)
                    return
                if fresh:
                    api.delete(row["rid"])
            with self.lock:
                current = self.note(key)
                if current is not None and current["deleted"] and current["rev"] == row["rev"]:
                    self.db.execute("DELETE FROM notes WHERE key = ?", (key,))
            return
        note = {"title": self._title(row["content"]), "content": row["content"], "category": row["category"],
                "favorite": row["favorite"], "modified": row["modified"]}
        if row["rid"] is None:
            remote = api.create(note)
            self._sent(key, row, remote)
            return
        try:
            remote = api.update(row["rid"], note, row["etag"])
        except ApiError as error:
            if error.status == 412:
                fresh = error.body if isinstance(error.body, dict) and error.body.get("id") else api.note(row["rid"])
                if self._merge_into(row, fresh):
                    merged = self.note(key)
                    note.update(content=merged["content"], category=merged["category"], favorite=merged["favorite"],
                                title=self._title(merged["content"]))
                    remote = api.update(row["rid"], note, fresh.get("etag") or "")
                    row = merged
                else:
                    with self.lock:
                        self._store_remote(key, fresh)
                    return
            elif error.status == 404:
                remote = api.create(note)
            else:
                raise
        self._sent(key, row, remote)

    def _sent(self, key, row, remote):
        """The cloud has the note as it was sent: its base moves on; a change typed meanwhile stays to send."""
        if not isinstance(remote, dict) or remote.get("id") is None:
            raise ApiError(500, "bad answer")
        with self.lock:
            current = self.note(key)
            if current is None:
                return
            content = remote.get("content") if remote.get("content") is not None else row["content"]
            if current["rev"] == row["rev"]:
                self._store_remote(key, {**remote, "content": content})
            else:
                self.db.execute("UPDATE notes SET rid = ?, etag = ?, title = ?, b_content = ?, b_category = ?, "
                                "b_favorite = ?, path = ? WHERE key = ?",
                                (int(remote["id"]), remote.get("etag") or "", remote.get("title") or "", content,
                                 remote.get("category") or "", int(bool(remote.get("favorite"))),
                                 remote.get("internalPath") or "", key))
            old_ref = f".attachments.{key}/"
            new_ref = f".attachments.{int(remote['id'])}/"
            self.db.execute("UPDATE uploads SET ref = replace(ref, ?, ?) WHERE note_key = ?", (old_ref, new_ref, key))

    def _send_uploads(self, api):
        """Images added here, for notes the cloud has: up, and the note's link follows the cloud's file name."""
        with self.lock:
            rows = [dict(r) for r in self.db.execute(
                "SELECT u.*, n.rid, n.content FROM uploads u JOIN notes n ON n.key = u.note_key "
                "WHERE n.rid IS NOT NULL AND n.deleted = 0")]
        for up in rows:
            try:
                data = Path(up["file"]).read_bytes()
            except OSError:
                with self.lock:
                    self.db.execute("DELETE FROM uploads WHERE id = ?", (up["id"],))
                continue
            ref = api.upload(up["rid"], up["name"], data, up["type"])
            with self.lock:
                self.db.execute("DELETE FROM uploads WHERE id = ?", (up["id"],))
                note = self.note(up["note_key"])
                if not ref or note is None:
                    continue
                for before in {f".attachments.{up['note_key']}/{up['name']}", up["ref"]}:
                    if before != ref and before in note["content"]:
                        self.edit(up["note_key"], content=note["content"].replace(before, ref))
                        note = self.note(up["note_key"])
                name = ref.rsplit("/", 1)[-1]
                if name != up["name"]:
                    try:
                        Path(up["file"]).rename(Path(up["file"]).with_name(name))
                    except OSError:
                        pass

    def pull(self, api):
        """Read the cloud: the list without contents (ids and ETags), then the notes that changed."""
        listed = api.notes_meta()
        changed = []
        with self.lock:
            local = {r["rid"]: dict(r) for r in self.db.execute(f"SELECT *, {DIRTY} AS dirty FROM notes WHERE rid IS NOT NULL")}
        seen = set()
        for meta in listed:
            rid = int(meta["id"])
            seen.add(rid)
            row = local.get(rid)
            if row is None or row["etag"] != meta.get("etag"):
                changed.append(rid)
            elif row and (row["readonly"] != int(bool(meta.get("readonly"))) or row["path"] != (meta.get("internalPath") or "")
                          or row["shared"] != int(bool(meta.get("isShared")))):
                with self.lock:
                    self.db.execute("UPDATE notes SET readonly = ?, shared = ?, path = ? WHERE key = ?",
                                    (int(bool(meta.get("readonly"))), int(bool(meta.get("isShared"))),
                                     meta.get("internalPath") or "", row["key"]))
        fresh = api.notes_full() if len(changed) > 12 else [api.note(rid) for rid in changed]
        for remote in fresh:
            if not isinstance(remote, dict) or remote.get("id") is None or int(remote["id"]) not in changed:
                continue
            row = local.get(int(remote["id"]))
            if row is None:
                self._insert_remote(remote)
            elif not row["dirty"] or row["deleted"]:
                with self.lock:
                    self._store_remote(row["key"], remote)        # an edit elsewhere wins over a delete here
            else:
                self._merge_into(row, remote)
        for rid, row in local.items():
            if rid in seen:
                continue
            with self.lock:
                if row["deleted"] or not row["dirty"]:
                    self.db.execute("DELETE FROM notes WHERE key = ?", (row["key"],))
                else:
                    # deleted in the cloud while it changed here: it goes up again as a new note
                    self.db.execute("UPDATE notes SET rid = NULL, etag = '', b_content = NULL, b_category = NULL, "
                                    "b_favorite = NULL WHERE key = ?", (row["key"],))
        self.set_meta("synced_at", int(time.time()))

    def sync(self, api, report=None, locked=None):
        self._skip = 0
        if not self.meta("settings_at") or time.time() - int(self.meta("settings_at") or 0) > 6 * 3600:
            try:
                settings = api.settings()
                self.set_meta("notes_path", settings.get("notesPath") or "Notes")
                self.set_meta("file_suffix", settings.get("fileSuffix") or ".md")
                self.set_meta("settings_at", int(time.time()))
            except ApiError as error:
                if error.status == 0:
                    raise
        self.push(api, report, locked)
        self.pull(api)
        self.push(api, report, locked)        # what changed here while reading, and the merges
