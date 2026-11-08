"""The tasks of the account, offline first: a copy of the lists and tasks of the cloud in SQLite, what changed
here since, and how the two meet again.

Each task keeps the version the cloud had when the two were last in step (its base). A change made here is
written at once and shows at once; it goes to the cloud on the next sync:

- the cloud did not move: the task is sent with If-Match on its ETag;
- the cloud changed it meanwhile (412): the two are merged property by property (todo.merge), the change
  made here winning on a property changed on both sides;
- the cloud no longer has it: it is created again rather than losing what was typed;
- deleted here, changed elsewhere: the change wins, the task comes back.

Lists too are made, renamed, recoloured and deleted here first, then in the cloud; a task moved to another
list is created there, then removed from the first. A sync reads only what changed in each list since the
last one (RFC 6578). Pure Python (no Qt): the window and the reminders run it on a worker thread; every
method takes the lock. Notes, KRunner and « Ajouter à Tâches » write here too (SQLite takes care of two
processes writing): the running instance sends their tasks.
"""
import hashlib
import json
import re
import sqlite3
import threading
import time
import uuid
from pathlib import Path

import system
from tasks_core import todo
from tasks_core.dav import DavError

DATA = system.DATA
DB = DATA / "tasks.db"
SCHEMA = """
CREATE TABLE IF NOT EXISTS lists (
    href TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT '', color TEXT NOT NULL DEFAULT '', ord INTEGER NOT NULL DEFAULT 0,
    token TEXT NOT NULL DEFAULT '', readonly INTEGER NOT NULL DEFAULT 0, shared INTEGER NOT NULL DEFAULT 0,
    owner TEXT NOT NULL DEFAULT '', events INTEGER NOT NULL DEFAULT 0, state TEXT NOT NULL DEFAULT '',
    b_name TEXT, b_color TEXT);
CREATE TABLE IF NOT EXISTS tasks (
    key TEXT PRIMARY KEY, href TEXT UNIQUE, list TEXT NOT NULL, uid TEXT NOT NULL DEFAULT '', etag TEXT NOT NULL DEFAULT '',
    ics TEXT NOT NULL, base TEXT, deleted INTEGER NOT NULL DEFAULT 0, rev INTEGER NOT NULL DEFAULT 0,
    old_href TEXT, old_etag TEXT, data TEXT NOT NULL DEFAULT '{}');
CREATE INDEX IF NOT EXISTS tasks_list ON tasks (list);
CREATE INDEX IF NOT EXISTS tasks_uid ON tasks (uid);
CREATE TABLE IF NOT EXISTS fired (uid TEXT NOT NULL, at INTEGER NOT NULL, PRIMARY KEY (uid, at));
CREATE TABLE IF NOT EXISTS snoozed (uid TEXT PRIMARY KEY, until INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT NOT NULL);
"""
DIRTY = "(deleted = 1 OR href IS NULL OR base IS NULL OR ics <> base)"
COLORS = ("#002FA7", "#F0A202", "#2F7D6D", "#C8381E", "#1A5F7A", "#7A4FBF", "#0F2440")


def slug(name):
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:30] or "liste"
    return f"{base}-{uuid.uuid4().hex[:6]}"


class Store:
    def __init__(self, user, path=None, default_name="Tâches", existing_only=False):
        self.user = user
        self.path = Path(path or DB)
        self.default_name = default_name
        self.lock = threading.RLock()
        if not existing_only:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        target = self.path.resolve().as_uri() + "?mode=rw" if existing_only else str(self.path)
        self.db = sqlite3.connect(target, uri=existing_only, check_same_thread=False, isolation_level=None, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.hold = ()
        with self.lock:
            self.db.execute("PRAGMA journal_mode=WAL")
            if not existing_only:
                self.db.executescript(SCHEMA)
            owner = self.meta("user")
            # Desktop widgets may write an existing task, but never initialize or reset an account.
            if existing_only and owner != user:
                self.db.close()
                raise ValueError("task account changed")
            if owner and owner != user:
                self._wipe()
            if not existing_only:
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
        self.db.executescript("DELETE FROM tasks; DELETE FROM lists; DELETE FROM fired; DELETE FROM snoozed; DELETE FROM meta;")

    def forget(self):
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

    def version(self):
        """Changes when anything was written (here or by another process): the window reloads then."""
        with self.lock:
            return self.db.execute("PRAGMA data_version").fetchone()[0], \
                self.db.execute("SELECT COALESCE(SUM(rev), 0) + COUNT(*) FROM tasks").fetchone()[0]

    # ---- what the window shows -------------------------------------------------------------------------------
    def lists(self):
        with self.lock:
            return [dict(r) for r in self.db.execute("SELECT * FROM lists WHERE state <> 'deleted' ORDER BY ord, name")]

    def list(self, href):
        with self.lock:
            row = self.db.execute("SELECT * FROM lists WHERE href = ?", (href,)).fetchone()
            return dict(row) if row else None

    def tasks(self):
        """Every task not deleted here: its index (todo.index) with key, list and pending."""
        with self.lock:
            rows = self.db.execute(f"SELECT key, list, href, data, {DIRTY} AS pending FROM tasks WHERE deleted = 0").fetchall()
        out = []
        for r in rows:
            data = json.loads(r["data"] or "{}")
            data.update(key=r["key"], list=r["list"], pending=bool(r["pending"]), href=r["href"] or "")
            out.append(data)
        return out

    def task(self, key):
        with self.lock:
            row = self.db.execute(f"SELECT *, {DIRTY} AS pending FROM tasks WHERE key = ?", (key,)).fetchone()
        if row is None:
            return None
        data = json.loads(row["data"] or "{}")
        data.update(key=row["key"], list=row["list"], pending=bool(row["pending"]), ics=row["ics"], href=row["href"] or "",
                    deleted=bool(row["deleted"]))
        return data

    def by_uid(self, uid):
        with self.lock:
            row = self.db.execute("SELECT key FROM tasks WHERE (uid = ? OR href LIKE ?) AND deleted = 0",
                                  (uid, "%/" + uid if uid.endswith(".ics") else uid)).fetchone()
            return row["key"] if row else ""

    def pending_count(self):
        with self.lock:
            tasks = self.db.execute(f"SELECT COUNT(*) FROM tasks WHERE {DIRTY}").fetchone()[0]
            return tasks + self.db.execute("SELECT COUNT(*) FROM lists WHERE state <> ''").fetchone()[0]

    # ---- lists, changed here -------------------------------------------------------------------------------
    def create_list(self, name, color=None):
        href = "local:" + uuid.uuid4().hex
        with self.lock:
            used = {r["color"] for r in self.lists()}
            color = color or next((c for c in COLORS if c not in used), COLORS[0])
            order = (self.db.execute("SELECT COALESCE(MAX(ord), 0) FROM lists").fetchone()[0] or 0) + 1
            self.db.execute("INSERT INTO lists (href, name, color, ord, state) VALUES (?, ?, ?, ?, 'new')",
                            (href, name.strip() or self.default_name, color, order))
        return href

    def default_list(self, preferred=""):
        """Where a task goes when nothing says: the chosen one, the first list that holds only tasks, any
        writable one, else a new « Tâches » (made in the cloud on the next sync)."""
        lists = [l for l in self.lists() if not l["readonly"]]
        for l in lists:
            if l["href"] == preferred:
                return l["href"]
        for l in lists:
            if not l["events"]:
                return l["href"]
        if lists:
            return lists[0]["href"]
        return self.create_list(self.default_name)

    def edit_list(self, href, name=None, color=None):
        with self.lock:
            row = self.list(href)
            if row is None or row["readonly"]:
                return
            if row["state"] == "" :
                self.db.execute("UPDATE lists SET b_name = name, b_color = color WHERE href = ?", (href,))
            self.db.execute("UPDATE lists SET name = COALESCE(?, name), color = COALESCE(?, color), "
                            "state = CASE WHEN state = 'new' THEN 'new' ELSE 'changed' END WHERE href = ?",
                            (name.strip() if name else None, color, href))

    def reorder_lists(self, hrefs):
        """The order of the side column (dragged there): here at once, in the cloud next (calendar-order)."""
        with self.lock:
            dirty = set(json.loads(self.meta("order_dirty", "[]") or "[]"))
            for i, href in enumerate(hrefs, start=1):
                row = self.list(href)
                if row is None or row["ord"] == i:
                    continue
                self.db.execute("UPDATE lists SET ord = ? WHERE href = ?", (i, href))
                dirty.add(href)
            self.set_meta("order_dirty", json.dumps(sorted(dirty)))

    def delete_list(self, href):
        """The list and its tasks: here at once, in the cloud next."""
        with self.lock:
            row = self.list(href)
            if row is None:
                return
            if row["state"] == "new":
                self.db.execute("DELETE FROM lists WHERE href = ?", (href,))
                self.db.execute("DELETE FROM tasks WHERE list = ?", (href,))
                return
            self.db.execute("UPDATE lists SET state = 'deleted' WHERE href = ?", (href,))
            self.db.execute("DELETE FROM tasks WHERE list = ?", (href,))

    # ---- tasks, changed here ---------------------------------------------------------------------------------
    def _write(self, key, ics, bump=True):
        data = todo.index(ics) or {}
        self.db.execute("UPDATE tasks SET ics = ?, data = ?, rev = rev + ? WHERE key = ?",
                        (ics, json.dumps(data), 1 if bump else 0, key))

    def add(self, list_href, fields, uid=None):
        uid, ics = todo.new(fields, uid)
        key = "t-" + uid
        with self.lock:
            self.db.execute("INSERT INTO tasks (key, list, uid, ics, data, rev) VALUES (?, ?, ?, ?, ?, 1)",
                            (key, list_href, uid, ics, json.dumps(todo.index(ics) or {})))
        return key

    def edit(self, key, fields):
        with self.lock:
            row = self.db.execute("SELECT ics FROM tasks WHERE key = ? AND deleted = 0", (key,)).fetchone()
            if row is None or self._readonly(key):
                return False
            ics = todo.update(row["ics"], fields)
            if ics == row["ics"]:
                return False
            self._write(key, ics)
            return True

    def _readonly(self, key):
        row = self.db.execute("SELECT l.readonly FROM tasks t JOIN lists l ON l.href = t.list WHERE t.key = ?", (key,)).fetchone()
        return bool(row and row["readonly"])

    def complete(self, key, done=True):
        """Done (or open again). A repeating task moves on to its next date; its done occurrence is kept as a
        new task. Returns the key of that copy, or ""."""
        with self.lock:
            row = self.db.execute("SELECT ics, list FROM tasks WHERE key = ? AND deleted = 0", (key,)).fetchone()
            if row is None or self._readonly(key):
                return ""
            ics, copy = todo.complete(row["ics"], done)
            self._write(key, ics)
            if copy:
                index = todo.index(copy) or {}
                copy_key = "t-" + index.get("uid", uuid.uuid4().hex)
                self.db.execute("INSERT INTO tasks (key, list, uid, ics, data, rev) VALUES (?, ?, ?, ?, ?, 1)",
                                (copy_key, row["list"], index.get("uid", ""), copy, json.dumps(index)))
                return copy_key
            return ""

    def move(self, key, list_href):
        """To another list: created there on the next sync, then removed from the first."""
        with self.lock:
            row = self.db.execute("SELECT * FROM tasks WHERE key = ? AND deleted = 0", (key,)).fetchone()
            if row is None or row["list"] == list_href or self._readonly(key):
                return
            if row["href"] and not row["old_href"]:
                self.db.execute("UPDATE tasks SET old_href = href, old_etag = etag WHERE key = ?", (key,))
            self.db.execute("UPDATE tasks SET list = ?, href = NULL, etag = '', base = NULL, rev = rev + 1 WHERE key = ?",
                            (list_href, key))

    def delete(self, *keys):
        with self.lock:
            for key in keys:
                row = self.db.execute("SELECT href, old_href FROM tasks WHERE key = ?", (key,)).fetchone()
                if row is None:
                    continue
                if row["href"] is None and row["old_href"] is None:
                    self.db.execute("DELETE FROM tasks WHERE key = ?", (key,))
                else:
                    self.db.execute("UPDATE tasks SET deleted = 1, rev = rev + 1 WHERE key = ?", (key,))

    def restore(self, key, ics):
        """A task as it was (« Annuler » after a tick): written again, sent on the next sync."""
        with self.lock:
            if self.db.execute("SELECT 1 FROM tasks WHERE key = ?", (key,)).fetchone():
                self._write(key, ics)

    def undelete(self, *keys):
        with self.lock:
            for key in keys:
                self.db.execute("UPDATE tasks SET deleted = 0, rev = rev + 1 WHERE key = ?", (key,))

    # ---- reminders -----------------------------------------------------------------------------------------
    def fired(self, uid, at):
        with self.lock:
            return self.db.execute("SELECT 1 FROM fired WHERE uid = ? AND at = ?", (uid, at)).fetchone() is not None

    def mark_fired(self, uid, at):
        with self.lock:
            self.db.execute("INSERT OR IGNORE INTO fired (uid, at) VALUES (?, ?)", (uid, at))
            self.db.execute("DELETE FROM fired WHERE at < ?", (int(time.time()) - 60 * 86400,))

    def snooze(self, uid, until):
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO snoozed (uid, until) VALUES (?, ?)", (uid, int(until)))

    def snoozed(self):
        with self.lock:
            return {r["uid"]: r["until"] for r in self.db.execute("SELECT * FROM snoozed")}

    def unsnooze(self, uid):
        with self.lock:
            self.db.execute("DELETE FROM snoozed WHERE uid = ?", (uid,))

    # ---- sync ------------------------------------------------------------------------------------------------
    def sync(self, client, report=None):
        home = self.meta("home")
        if not home:
            home, _books = client.homes()
            self.set_meta("home", home)
        self._push_lists(client, home)
        self._read_lists(client, home)
        self._push_tasks(client, report)
        for row in self.lists():
            if row["state"] in ("", "changed"):
                self._pull_list(client, row)
        self._push_tasks(client, report)
        self.set_meta("synced_at", int(time.time()))

    def _push_lists(self, client, home):
        with self.lock:
            rows = [dict(r) for r in self.db.execute("SELECT * FROM lists WHERE state <> ''")]
        for row in rows:
            if row["state"] == "new":
                href = client.make_list(home, slug(row["name"]), row["name"], row["color"])
                with self.lock:
                    self.db.execute("UPDATE lists SET href = ?, state = '' WHERE href = ?", (href, row["href"]))
                    self.db.execute("UPDATE tasks SET list = ? WHERE list = ?", (href, row["href"]))
            elif row["state"] == "changed":
                try:
                    client.set_list(row["href"], name=row["name"] if row["name"] != row["b_name"] else None,
                                    color=row["color"] if row["color"] != row["b_color"] else None)
                except DavError as error:
                    if error.status == 0:
                        raise
                with self.lock:
                    self.db.execute("UPDATE lists SET state = '' WHERE href = ?", (row["href"],))
            elif row["state"] == "deleted":
                try:
                    client.delete(row["href"])
                except DavError as error:
                    if error.status == 0:
                        raise
                with self.lock:
                    self.db.execute("DELETE FROM lists WHERE href = ?", (row["href"],))
        # the order changed here (lists dragged in the side column)
        for href in json.loads(self.meta("order_dirty", "[]") or "[]"):
            row = self.list(href)
            if row is not None and row["state"] == "" and not href.startswith("local:"):
                try:
                    client.set_list(href, order=row["ord"])
                except DavError as error:
                    if error.status == 0:
                        raise
        self.set_meta("order_dirty", "[]")

    def _read_lists(self, client, home):
        found = {c["href"]: c for c in client.collections(home)}
        with self.lock:
            local = {r["href"]: dict(r) for r in self.db.execute("SELECT * FROM lists")}
            for href, c in found.items():
                row = local.get(href)
                if row is None:
                    self.db.execute("INSERT INTO lists (href, name, color, ord, readonly, shared, owner, events) "
                                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                    (href, c["name"], c["color"] or COLORS[0], c["order"], int(c["readonly"]),
                                     int(c["shared"]), c["owner_name"], int(c.get("events", False))))
                elif row["state"] == "":
                    self.db.execute("UPDATE lists SET name = ?, color = ?, ord = ?, readonly = ?, shared = ?, owner = ?, "
                                    "events = ? WHERE href = ?",
                                    (c["name"], c["color"] or row["color"], c["order"], int(c["readonly"]), int(c["shared"]),
                                     c["owner_name"], int(c.get("events", False)), href))
            for href, row in local.items():
                if href in found or row["state"] in ("new", "deleted") or href.startswith("local:"):
                    continue
                # gone from the cloud: its tasks changed here go to the default list, the others go
                self.db.execute("DELETE FROM lists WHERE href = ?", (href,))
                kept = [r["key"] for r in self.db.execute(f"SELECT key FROM tasks WHERE list = ? AND {DIRTY}", (href,))]
                self.db.execute(f"DELETE FROM tasks WHERE list = ? AND NOT {DIRTY}", (href,))
                if kept:
                    target = self.default_list()
                    self.db.execute(f"UPDATE tasks SET list = ?, href = NULL, base = NULL, etag = '', old_href = NULL "
                                    f"WHERE key IN ({','.join('?' * len(kept))})", (target, *kept))

    def _apply_remote(self, list_href, href, etag, ics):
        index = todo.index(ics)
        if index is None:
            return
        with self.lock:
            row = self.db.execute(f"SELECT *, {DIRTY} AS dirty FROM tasks WHERE href = ?", (href,)).fetchone()
            if row is None:
                # a task this computer created and sent, whose answer was lost: found by its uid
                row = self.db.execute(f"SELECT *, {DIRTY} AS dirty FROM tasks WHERE uid = ? AND list = ? AND href IS NULL",
                                      (index["uid"], list_href)).fetchone()
                if row is None:
                    key = "t-" + index["uid"] if index["uid"] else "h-" + hashlib.md5(href.encode()).hexdigest()
                    if self.db.execute("SELECT 1 FROM tasks WHERE key = ?", (key,)).fetchone():
                        key = "h-" + hashlib.md5(href.encode()).hexdigest()
                    self.db.execute("INSERT OR REPLACE INTO tasks (key, href, list, uid, etag, ics, base, data) "
                                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                    (key, href, list_href, index["uid"], etag, ics, ics, json.dumps(index)))
                    return
                self.db.execute("UPDATE tasks SET href = ? WHERE key = ?", (href, row["key"]))
            if row["etag"] == etag and row["base"] is not None:
                return
            if not row["dirty"] or row["deleted"]:
                self.db.execute("UPDATE tasks SET etag = ?, ics = ?, base = ?, data = ?, deleted = 0 WHERE key = ?",
                                (etag, ics, ics, json.dumps(index), row["key"]))
            else:
                merged = todo.merge(row["base"], row["ics"], ics)
                self.db.execute("UPDATE tasks SET etag = ?, base = ?, ics = ?, data = ?, rev = rev + 1 WHERE key = ?",
                                (etag, ics, merged, json.dumps(todo.index(merged) or index), row["key"]))

    def _pull_list(self, client, row):
        href = row["href"]
        try:
            token, changed, deleted = client.sync(href, row["token"])
        except DavError as error:
            if error.status in (403, 409, 412) and row["token"]:
                token, changed, deleted = client.sync(href, "")
                deleted += self._unseen(href, set(changed))
            elif error.status == 0:
                raise
            else:
                changed = client.etags(href)
                token, deleted = "", self._unseen(href, set(changed))
        with self.lock:
            known = {r["href"]: r["etag"] for r in self.db.execute("SELECT href, etag FROM tasks WHERE list = ? AND href IS NOT NULL", (href,))}
        wanted = [h for h, etag in changed.items() if known.get(h) != etag]
        if wanted:
            for obj_href, (etag, data) in client.multiget(href, wanted).items():
                self._apply_remote(href, client.path(obj_href), etag, data)
        for gone in deleted:
            self._gone(client.path(gone))
        with self.lock:
            self.db.execute("UPDATE lists SET token = ? WHERE href = ?", (token, href))

    def _unseen(self, list_href, present):
        with self.lock:
            return [r["href"] for r in self.db.execute("SELECT href FROM tasks WHERE list = ? AND href IS NOT NULL", (list_href,))
                    if r["href"] not in present]

    def _gone(self, href):
        with self.lock:
            row = self.db.execute(f"SELECT key, deleted, {DIRTY} AS dirty FROM tasks WHERE href = ?", (href,)).fetchone()
            if row is None:
                return
            if row["deleted"] or not row["dirty"]:
                self.db.execute("DELETE FROM tasks WHERE key = ?", (row["key"],))
            else:
                # deleted elsewhere while it changed here: it goes up again
                self.db.execute("UPDATE tasks SET href = NULL, etag = '', base = NULL WHERE key = ?", (row["key"],))

    def _push_tasks(self, client, report):
        skip = set()
        while True:
            with self.lock:
                held = tuple(self.hold) + tuple(skip)
                where = f"{DIRTY} AND key NOT IN ({','.join('?' * len(held))})" if held else DIRTY
                row = self.db.execute(f"SELECT * FROM (SELECT t.*, l.state AS list_state FROM tasks t LEFT JOIN lists l "
                                      f"ON l.href = t.list) WHERE {where} LIMIT 1", held).fetchone()
                row = dict(row) if row else None
            if row is None:
                return
            if row["list_state"] == "new" or row["list"].startswith("local:"):
                skip.add(row["key"])        # its list is not in the cloud yet
                continue
            try:
                self._send(client, row)
            except DavError as error:
                if error.status in (0, 401, 423, 429) or error.status >= 500:
                    raise
                skip.add(row["key"])
                with self.lock:
                    if row["base"] is not None:
                        self.db.execute("UPDATE tasks SET ics = base, data = ?, deleted = 0 WHERE key = ?",
                                        (json.dumps(todo.index(row["base"]) or {}), row["key"]))
                if report:
                    report((json.loads(row["data"] or "{}")).get("title", ""), error)

    def _send(self, client, row):
        key = row["key"]
        if row["deleted"]:
            target = row["href"] or row["old_href"]
            if target:
                try:
                    client.delete(target, row["etag"] if row["href"] else row["old_etag"])
                except DavError as error:
                    if error.status != 412:
                        raise
                    fresh = client.get(target)
                    if fresh is not None:
                        with self.lock:
                            self.db.execute("UPDATE tasks SET href = ?, list = list, deleted = 0 WHERE key = ?", (target, key))
                        self._apply_remote(row["list"], target, fresh[0], fresh[1])
                        return
            with self.lock:
                current = self.db.execute("SELECT rev, deleted FROM tasks WHERE key = ?", (key,)).fetchone()
                if current and current["deleted"] and current["rev"] == row["rev"]:
                    self.db.execute("DELETE FROM tasks WHERE key = ?", (key,))
            return
        ics = row["ics"]
        if row["href"] is None:
            name = row["uid"] if re.fullmatch(r"[\w.@-]{1,200}", row["uid"] or "") else uuid.uuid4().hex
            href = client.path(row["list"]).rstrip("/") + "/" + name + ".ics"
            try:
                etag = client.put(href, ics, "text/calendar; charset=utf-8")
            except DavError as error:
                if error.status != 412:
                    raise
                fresh = client.get(href)           # sent before, the answer was lost: now an update
                etag = fresh[0] if fresh else ""
                ics = todo.merge(fresh[1], ics, fresh[1]) if fresh else ics
                etag = client.put(href, ics, "text/calendar; charset=utf-8", etag or None)
            if row["old_href"]:
                try:
                    client.delete(row["old_href"])
                except DavError as error:
                    if error.status not in (404, 412):
                        raise
            self._sent(key, row, href, etag, ics, client)
            return
        try:
            etag = client.put(row["href"], ics, "text/calendar; charset=utf-8", row["etag"] or None)
        except DavError as error:
            if error.status == 412:
                fresh = client.get(row["href"])
                if fresh is None:
                    with self.lock:
                        self.db.execute("UPDATE tasks SET href = NULL, etag = '', base = NULL WHERE key = ?", (key,))
                    return
                ics = todo.merge(row["base"], ics, fresh[1])
                etag = client.put(row["href"], ics, "text/calendar; charset=utf-8", fresh[0])
            elif error.status == 404:
                with self.lock:
                    self.db.execute("UPDATE tasks SET href = NULL, etag = '', base = NULL WHERE key = ?", (key,))
                return
            else:
                raise
        self._sent(key, row, row["href"], etag, ics, client)

    def _sent(self, key, row, href, etag, ics, client):
        if not etag:
            fresh = client.get(href)
            etag = fresh[0] if fresh else ""
        with self.lock:
            current = self.db.execute("SELECT rev FROM tasks WHERE key = ?", (key,)).fetchone()
            if current is None:
                return
            if current["rev"] == row["rev"]:
                self.db.execute("UPDATE tasks SET href = ?, etag = ?, base = ?, ics = ?, data = ?, old_href = NULL, "
                                "old_etag = NULL WHERE key = ?",
                                (href, etag, ics, ics, json.dumps(todo.index(ics) or {}), key))
            else:
                self.db.execute("UPDATE tasks SET href = ?, etag = ?, base = ?, old_href = NULL, old_etag = NULL WHERE key = ?",
                                (href, etag, ics, key))
