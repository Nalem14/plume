"""Plume's local cache: one SQLite file in ~/.cache/orneos (it can be deleted, Plume fetches it again).

Light on purpose: recent mail and what the agenda and contacts need, never a full copy of the mailbox.
Migrations are numbered with PRAGMA user_version; add one, never change an old one.
"""
import json
import os
import sqlite3
import threading
from pathlib import Path

import system

CACHE = system.CACHE
# What the user set up is not cache: it lives in the configuration folder (Application Support, %APPDATA%,
# ~/.config), which cleaners leave alone. On 04/11, a cache cleaned on a Mac took the external mailboxes away.
# plume.db keeps a copy (the desktop widgets read it there) and is filled again from this file.
SETTINGS = system.CONFIG / "plume-settings.json"
DURABLE = {"mail_boxes", "mail_label_orneos", "trusted_senders", "unsubscribed", "mail_notify", "ornis_auto_summary",
           "mail_threads", "mail_folded", "module", "homes"}
DURABLE_PREFIXES = ("pref_", "window")


def durable(key: str) -> bool:
    return key in DURABLE or key.startswith(DURABLE_PREFIXES)


def fold(text):
    import unicodedata
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()


class StaleMailAccount(Exception):
    """A mail worker finished after its account was replaced."""

MIGRATIONS = [
    """
    CREATE TABLE kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    """,
    # Calendars and address books (CalDAV, CardDAV), kept in sync with sync-collection tokens
    """
    CREATE TABLE collections (
        id INTEGER PRIMARY KEY, kind TEXT NOT NULL, href TEXT NOT NULL UNIQUE, name TEXT NOT NULL DEFAULT '',
        color TEXT NOT NULL DEFAULT '', sort INTEGER NOT NULL DEFAULT 0, sync_token TEXT NOT NULL DEFAULT '',
        readonly INTEGER NOT NULL DEFAULT 0, shared INTEGER NOT NULL DEFAULT 0, owner_name TEXT NOT NULL DEFAULT '',
        enabled INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE events (
        id INTEGER PRIMARY KEY, collection_id INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
        href TEXT NOT NULL, etag TEXT NOT NULL DEFAULT '', uid TEXT NOT NULL DEFAULT '', title TEXT NOT NULL DEFAULT '',
        start_ts INTEGER NOT NULL, end_ts INTEGER, recurring INTEGER NOT NULL DEFAULT 0,
        pending INTEGER NOT NULL DEFAULT 0, ics TEXT NOT NULL, UNIQUE (collection_id, href));
    CREATE INDEX events_span ON events (start_ts, end_ts);
    CREATE TABLE contacts (
        id INTEGER PRIMARY KEY, collection_id INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
        href TEXT NOT NULL, etag TEXT NOT NULL DEFAULT '', uid TEXT NOT NULL DEFAULT '', name TEXT NOT NULL DEFAULT '',
        sort_key TEXT NOT NULL DEFAULT '', org TEXT NOT NULL DEFAULT '', emails TEXT NOT NULL DEFAULT '',
        phones TEXT NOT NULL DEFAULT '', categories TEXT NOT NULL DEFAULT '', vcard TEXT NOT NULL,
        UNIQUE (collection_id, href));
    CREATE INDEX contacts_sort ON contacts (sort_key);
    """,
    # Mail: folders, headers of the latest messages, bodies of the ones opened recently
    """
    CREATE TABLE mail_folders (
        id INTEGER PRIMARY KEY, path TEXT NOT NULL UNIQUE, name TEXT NOT NULL, full TEXT NOT NULL DEFAULT '',
        role TEXT NOT NULL DEFAULT '', delimiter TEXT NOT NULL DEFAULT '', noselect INTEGER NOT NULL DEFAULT 0,
        uidvalidity INTEGER NOT NULL DEFAULT 0, total INTEGER NOT NULL DEFAULT 0, unseen INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE messages (
        id INTEGER PRIMARY KEY, folder_id INTEGER NOT NULL REFERENCES mail_folders(id) ON DELETE CASCADE,
        uid INTEGER NOT NULL, message_id TEXT NOT NULL DEFAULT '', date_ts INTEGER NOT NULL DEFAULT 0,
        from_name TEXT NOT NULL DEFAULT '', from_email TEXT NOT NULL DEFAULT '', recipients TEXT NOT NULL DEFAULT '[]',
        subject TEXT NOT NULL DEFAULT '', preview TEXT NOT NULL DEFAULT '', seen INTEGER NOT NULL DEFAULT 0,
        flagged INTEGER NOT NULL DEFAULT 0, answered INTEGER NOT NULL DEFAULT 0, attachments INTEGER NOT NULL DEFAULT 0,
        size INTEGER NOT NULL DEFAULT 0, in_reply_to TEXT NOT NULL DEFAULT '', refs TEXT NOT NULL DEFAULT '',
        UNIQUE (folder_id, uid));
    CREATE INDEX messages_date ON messages (folder_id, date_ts DESC);
    CREATE TABLE bodies (
        message_id INTEGER PRIMARY KEY REFERENCES messages(id) ON DELETE CASCADE, raw BLOB NOT NULL,
        fetched_at INTEGER NOT NULL);
    CREATE TABLE drafts (id INTEGER PRIMARY KEY, data TEXT NOT NULL, updated_at INTEGER NOT NULL);
    """,
    # Several mailboxes (Orneos and external ones): folders belong to a box. The mail cache starts over
    # (it is only a cache: the latest headers come back on the next sync).
    """
    DROP TABLE bodies;
    DROP TABLE messages;
    DROP TABLE mail_folders;
    CREATE TABLE mail_folders (
        id INTEGER PRIMARY KEY, box TEXT NOT NULL DEFAULT 'orneos', path TEXT NOT NULL, name TEXT NOT NULL,
        full TEXT NOT NULL DEFAULT '', role TEXT NOT NULL DEFAULT '', delimiter TEXT NOT NULL DEFAULT '',
        noselect INTEGER NOT NULL DEFAULT 0, uidvalidity INTEGER NOT NULL DEFAULT 0, total INTEGER NOT NULL DEFAULT 0,
        unseen INTEGER NOT NULL DEFAULT 0, UNIQUE (box, path));
    CREATE TABLE messages (
        id INTEGER PRIMARY KEY, folder_id INTEGER NOT NULL REFERENCES mail_folders(id) ON DELETE CASCADE,
        uid INTEGER NOT NULL, message_id TEXT NOT NULL DEFAULT '', date_ts INTEGER NOT NULL DEFAULT 0,
        from_name TEXT NOT NULL DEFAULT '', from_email TEXT NOT NULL DEFAULT '', recipients TEXT NOT NULL DEFAULT '[]',
        subject TEXT NOT NULL DEFAULT '', preview TEXT NOT NULL DEFAULT '', seen INTEGER NOT NULL DEFAULT 0,
        flagged INTEGER NOT NULL DEFAULT 0, answered INTEGER NOT NULL DEFAULT 0, attachments INTEGER NOT NULL DEFAULT 0,
        size INTEGER NOT NULL DEFAULT 0, in_reply_to TEXT NOT NULL DEFAULT '', refs TEXT NOT NULL DEFAULT '',
        UNIQUE (folder_id, uid));
    CREATE INDEX messages_date ON messages (folder_id, date_ts DESC);
    CREATE TABLE bodies (
        message_id INTEGER PRIMARY KEY REFERENCES messages(id) ON DELETE CASCADE, raw BLOB NOT NULL,
        fetched_at INTEGER NOT NULL);
    """,
    # Tags of a message: the IMAP keywords $label1 … $label5 (Important, Work, Personal, To do, Later),
    # the same as the cloud's Mail app and Thunderbird, space-separated
    """
    ALTER TABLE messages ADD COLUMN tags TEXT NOT NULL DEFAULT '';
    """,
]


class Store:
    def __init__(self, path: Path | None = None, settings: Path | None = None):
        # a store of its own (tests) keeps its settings beside it, not in the user's configuration
        self._settings_path = settings or (SETTINGS if path is None else Path(path).with_name(Path(path).stem + "-settings.json"))
        self._settings_cache = (None, None)       # (mtime, data): Courrier, Agenda and Contacts share the file
        path = path or CACHE / "plume.db"
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.mail_context = threading.local()
        # shared by Courrier, Agenda and Contacts of Orneos OS (and Plume): a writer elsewhere is waited for
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None, timeout=30)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=NORMAL")
        self._db.execute("PRAGMA foreign_keys=ON")
        # fold(text): lower case without accents, for searches (SQLite's lower() only knows ASCII)
        self._db.create_function("fold", 1, fold, deterministic=True)
        # digits(text): the digits of a number (06 12 34 56 found by « 0612 »)
        self._db.create_function("digits", 1, lambda v: "".join(ch for ch in (v or "") if ch.isdigit()),
                                 deterministic=True)
        self._migrate()
        self._mirror()

    def _mirror(self):
        """A cache emptied since: the durable settings written back into it (the desktop widgets read it)."""
        data = self._settings()
        if not data:
            return
        with self._lock:
            have = {r[0] for r in self._db.execute("SELECT key FROM kv")}
            missing = [(k, json.dumps(v)) for k, v in data.items() if k not in have]
            if missing:
                self._db.executemany("INSERT OR IGNORE INTO kv (key, value) VALUES (?, ?)", missing)

    def _migrate(self):
        with self._lock:
            version = self._db.execute("PRAGMA user_version").fetchone()[0]
            for number, script in enumerate(MIGRATIONS[version:], start=version + 1):
                self._db.executescript("BEGIN;" + script + f"PRAGMA user_version={number};COMMIT;")

    def query(self, sql, args=()):
        with self._lock:
            return self._db.execute(sql, args).fetchall()

    def prepare_mail_account(self, server, user):
        """Scope the disposable mail cache to Connect's account, also for desktop widgets.

        Existing installations initialize this once. Drafts and external mailbox settings stay;
        only cached headers/bodies/folders are fetched again. Never deletes mail on the server.
        """
        owner = [server.rstrip("/"), user]
        with self._lock:
            if self.get("widget_mail_owner") == owner:
                return False
            self._db.execute("BEGIN IMMEDIATE")
            try:
                self._db.execute("DELETE FROM bodies")
                self._db.execute("DELETE FROM messages")
                self._db.execute("DELETE FROM mail_folders")
                self.set("widget_mail_owner", owner)
                self._db.execute("COMMIT")
            except Exception:
                self._db.execute("ROLLBACK")
                raise
        return True

    def execute(self, sql, args=()):
        with self._lock:
            self._check_mail_owner()
            return self._db.execute(sql, args)

    def many(self, sql, rows):
        with self._lock:
            self._check_mail_owner()
            self._db.execute("BEGIN")
            try:
                self._db.executemany(sql, rows)
                self._db.execute("COMMIT")
            except Exception:
                self._db.execute("ROLLBACK")
                raise

    def _check_mail_owner(self):
        owner = getattr(self.mail_context, "owner", None)
        if owner is not None and self.get("widget_mail_owner") != owner:
            raise StaleMailAccount()

    # ---- the durable settings -------------------------------------------------------------------------------------
    def _settings(self) -> dict:
        try:
            mtime = self._settings_path.stat().st_mtime_ns
        except OSError:
            return {}
        if self._settings_cache[0] == mtime:
            return self._settings_cache[1]
        try:
            data = json.loads(self._settings_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return self._settings_cache[1] or {}
        data = data if isinstance(data, dict) else {}
        self._settings_cache = (mtime, data)
        return data

    def _save_setting(self, key, value) -> None:
        with self._lock:
            data = dict(self._settings())
            data[key] = value
            try:
                self._settings_path.parent.mkdir(parents=True, exist_ok=True)
                tmp = self._settings_path.with_name(self._settings_path.name + f".{os.getpid()}.tmp")
                tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
                if not system.WINDOWS:
                    tmp.chmod(0o600)
                os.replace(tmp, self._settings_path)
            except OSError:
                return                                   # the copy in plume.db still holds it
            self._settings_cache = (None, None)

    def get(self, key, default=None):
        if durable(key):
            data = self._settings()
            if key in data:
                return data[key]
            value = self._kv_get(key, None)               # set before 1.0.59: moved out of the cache once
            if value is not None:
                self._save_setting(key, value)
                return value
            return default
        return self._kv_get(key, default)

    def _kv_get(self, key, default=None):
        rows = self.query("SELECT value FROM kv WHERE key = ?", (key,))
        if not rows:
            return default
        try:
            return json.loads(rows[0]["value"])
        except json.JSONDecodeError:
            return default

    def set(self, key, value):
        if durable(key):
            self._save_setting(key, value)
        self.execute("INSERT INTO kv (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                     (key, json.dumps(value)))
