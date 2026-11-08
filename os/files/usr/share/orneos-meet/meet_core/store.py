"""Meet's copy on this computer (SQLite, DATA/meet.db): the conversations, their last messages, the drafts and
what was written offline. The window opens on it at once; the cloud fills in what changed.

Messages are kept as Talk gives them (JSON), the last KEEP of each conversation. A message written offline
goes to the outbox with a reference id (Talk's `referenceId`), shown at once as « pending », sent when the
network comes back, and matched with the cloud's copy by that id (no double). Pure Python, one lock: the
window and its worker thread both use it.
"""
import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path

import system

DB = system.DATA / "meet.db"
KEEP = 400
SCHEMA = """
CREATE TABLE IF NOT EXISTS rooms (token TEXT PRIMARY KEY, data TEXT NOT NULL, activity INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS messages (token TEXT NOT NULL, id INTEGER NOT NULL, data TEXT NOT NULL, PRIMARY KEY (token, id));
CREATE TABLE IF NOT EXISTS outbox (ref TEXT PRIMARY KEY, token TEXT NOT NULL, body TEXT NOT NULL, at INTEGER NOT NULL,
    tries INTEGER NOT NULL DEFAULT 0, failed INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS drafts (token TEXT PRIMARY KEY, text TEXT NOT NULL, reply INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT NOT NULL);
"""


class Store:
    def __init__(self, user, path=None):
        self.user = user
        self.path = Path(path or DB)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(str(self.path), check_same_thread=False, isolation_level=None, timeout=10)
        self.db.row_factory = sqlite3.Row
        with self.lock:
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.executescript(SCHEMA)
            owner = self.meta("user")
            if owner and owner != user:            # another account on this computer: start clean
                for table in ("rooms", "messages", "outbox", "drafts", "meta"):
                    self.db.execute(f"DELETE FROM {table}")
            self.set_meta("user", user)

    # ---- meta --------------------------------------------------------------------------------------------
    def meta(self, key, default=""):
        with self.lock:
            row = self.db.execute("SELECT v FROM meta WHERE k = ?", (key,)).fetchone()
        return row[0] if row else default

    def set_meta(self, key, value):
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO meta (k, v) VALUES (?, ?)", (key, str(value)))

    # ---- conversations -----------------------------------------------------------------------------------
    def rooms(self):
        with self.lock:
            rows = self.db.execute("SELECT data FROM rooms ORDER BY activity DESC").fetchall()
        return [json.loads(r[0]) for r in rows]

    def room(self, token):
        with self.lock:
            row = self.db.execute("SELECT data FROM rooms WHERE token = ?", (token,)).fetchone()
        return json.loads(row[0]) if row else None

    def put_rooms(self, rooms, complete=True):
        """The conversations from the cloud; complete=True: the ones missing are gone (left, deleted)."""
        with self.lock:
            self.db.execute("BEGIN")
            try:
                if complete:
                    keep = {r["token"] for r in rooms}
                    for (token,) in self.db.execute("SELECT token FROM rooms").fetchall():
                        if token not in keep:
                            self._forget(token)
                for r in rooms:
                    self.db.execute("INSERT OR REPLACE INTO rooms (token, data, activity) VALUES (?, ?, ?)",
                                    (r["token"], json.dumps(r), int(r.get("lastActivity") or 0)))
                self.db.execute("COMMIT")
            except Exception:
                self.db.execute("ROLLBACK")
                raise

    def put_room(self, room):
        self.put_rooms([room], complete=False)

    def forget_room(self, token):
        with self.lock:
            self._forget(token)

    def _forget(self, token):
        for table in ("rooms", "messages", "outbox", "drafts"):
            self.db.execute(f"DELETE FROM {table} WHERE token = ?", (token,))

    # ---- messages ----------------------------------------------------------------------------------------
    def messages(self, token, limit=KEEP):
        with self.lock:
            rows = self.db.execute("SELECT data FROM messages WHERE token = ? ORDER BY id DESC LIMIT ?",
                                   (token, limit)).fetchall()
        return [json.loads(r[0]) for r in reversed(rows)]

    def put_messages(self, token, messages):
        if not messages:
            return
        with self.lock:
            self.db.execute("BEGIN")
            try:
                for m in messages:
                    if not isinstance(m, dict) or "id" not in m:
                        continue
                    self.db.execute("INSERT OR REPLACE INTO messages (token, id, data) VALUES (?, ?, ?)",
                                    (token, int(m["id"]), json.dumps(m)))
                    ref = m.get("referenceId")
                    if ref:
                        self.db.execute("DELETE FROM outbox WHERE ref = ?", (ref,))
                # only the last KEEP stay on this computer
                self.db.execute("DELETE FROM messages WHERE token = ? AND id NOT IN "
                                "(SELECT id FROM messages WHERE token = ? ORDER BY id DESC LIMIT ?)",
                                (token, token, KEEP))
                self.db.execute("COMMIT")
            except Exception:
                self.db.execute("ROLLBACK")
                raise

    def last_id(self, token):
        with self.lock:
            row = self.db.execute("SELECT MAX(id) FROM messages WHERE token = ?", (token,)).fetchone()
        return int(row[0] or 0)

    # ---- outbox ------------------------------------------------------------------------------------------
    def queue(self, token, text, reply_to=0, silent=False):
        ref = uuid.uuid4().hex
        body = {"message": text, "replyTo": reply_to, "silent": silent}
        with self.lock:
            self.db.execute("INSERT INTO outbox (ref, token, body, at) VALUES (?, ?, ?, ?)",
                            (ref, token, json.dumps(body), int(time.time())))
        return ref

    def outbox(self, token=None):
        with self.lock:
            if token:
                rows = self.db.execute("SELECT * FROM outbox WHERE token = ? ORDER BY at, rowid", (token,)).fetchall()
            else:
                rows = self.db.execute("SELECT * FROM outbox ORDER BY at, rowid").fetchall()
        return [{"ref": r["ref"], "token": r["token"], "at": r["at"], "tries": r["tries"], "failed": bool(r["failed"]),
                 **json.loads(r["body"])} for r in rows]

    def sent(self, ref):
        with self.lock:
            self.db.execute("DELETE FROM outbox WHERE ref = ?", (ref,))

    def tried(self, ref, failed=False):
        with self.lock:
            self.db.execute("UPDATE outbox SET tries = tries + 1, failed = ? WHERE ref = ?", (int(failed), ref))

    def retry(self, ref):
        with self.lock:
            self.db.execute("UPDATE outbox SET failed = 0 WHERE ref = ?", (ref,))

    # ---- drafts ------------------------------------------------------------------------------------------
    def draft(self, token):
        with self.lock:
            row = self.db.execute("SELECT text, reply FROM drafts WHERE token = ?", (token,)).fetchone()
        return (row[0], row[1]) if row else ("", 0)

    def set_draft(self, token, text, reply=0):
        with self.lock:
            if text.strip() or reply:
                self.db.execute("INSERT OR REPLACE INTO drafts (token, text, reply) VALUES (?, ?, ?)",
                                (token, text, int(reply)))
            else:
                self.db.execute("DELETE FROM drafts WHERE token = ?", (token,))
