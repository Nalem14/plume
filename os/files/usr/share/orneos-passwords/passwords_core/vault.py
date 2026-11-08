"""The passwords of the account, offline first: the cloud's copy, the changes not sent yet, and their merge.

Everything is kept in one encrypted file (core.secure). A change is written there at once and shows at once;
it goes to the cloud on the next sync (right away when online, else when the network comes back). Pending
changes are kept per entry, with the fields that changed and the revision they started from:

- the cloud has not moved: the entry is sent as is;
- the cloud changed it meanwhile (409 "outdated revision"): the cloud's version is taken, with the fields
  changed here on top. A field changed on both sides keeps the value from here; the cloud's goes into the
  entry's history (the Passwords app keeps every revision), so nothing is lost;
- the cloud no longer has it: it is created again, rather than losing what was typed.

Pure Python (no Qt): the window runs it on a worker thread; every method holding state takes the lock.
"""
import copy
import json
import threading
import time
import uuid

from passwords_core import secure
from passwords_core.api import ApiError

FIELDS = ("label", "username", "password", "url", "notes", "customFields", "folder", "tags", "favorite")
VERSION = 1


def normalize(raw):
    """An entry as kept here, from an API object. None for one this app cannot read (client-side encrypted)."""
    if not isinstance(raw, dict) or not raw.get("id"):
        return None
    if (raw.get("cseType") or "none") != "none":
        return None
    fields = raw.get("customFields")
    if isinstance(fields, str):
        try:
            fields = json.loads(fields or "[]")
        except json.JSONDecodeError:
            fields = []
    fields = [{"label": str(f.get("label") or ""), "type": str(f.get("type") or "text"), "value": str(f.get("value") or "")}
              for f in (fields or []) if isinstance(f, dict) and f.get("type") != "data"]
    tags = [t if isinstance(t, str) else t.get("id") for t in (raw.get("tags") or []) if t]
    return {
        "id": raw["id"], "revision": raw.get("revision") or "", "label": raw.get("label") or "",
        "username": raw.get("username") or "", "password": raw.get("password") or "", "url": raw.get("url") or "",
        "notes": raw.get("notes") or "", "customFields": fields, "folder": raw.get("folder") or "",
        "tags": [t for t in tags if t], "favorite": bool(raw.get("favorite")), "trashed": bool(raw.get("trashed")),
        "created": int(raw.get("created") or 0), "updated": int(raw.get("updated") or 0),
        "edited": int(raw.get("edited") or 0), "status": int(raw.get("status") or 0),
        "statusCode": raw.get("statusCode") or "", "share": raw.get("share") or "", "shared": bool(raw.get("shared")),
        "editable": raw.get("editable", True) is not False, "hidden": bool(raw.get("hidden")),
    }


class Vault:
    def __init__(self, user, path=None):
        self.user = user
        self.path = path
        self.lock = threading.RLock()
        self.server = {}           # id → entry, as the cloud has it
        self.folders = {}
        self.tags = {}
        self.shares = []
        self.pending = []          # [{seq, kind, id, base, fields, entry}]
        self.synced_at = 0
        self.unreadable = 0        # entries protected by a master password (client-side encryption)
        self.cse = False
        self._seq = 0
        self.loaded = False

    # ---- disk ------------------------------------------------------------------------------------------------
    def load(self):
        data = secure.load(self.user, self.path)
        with self.lock:
            if data and data.get("version") == VERSION and data.get("user") == self.user:
                self.server = data.get("server") or {}
                self.folders = data.get("folders") or {}
                self.tags = data.get("tags") or {}
                self.shares = data.get("shares") or []
                self.pending = data.get("pending") or []
                self.synced_at = int(data.get("synced_at") or 0)
                self.unreadable = int(data.get("unreadable") or 0)
                self.cse = bool(data.get("cse"))
                self._seq = max([op["seq"] for op in self.pending] + [0])
                self.loaded = True
            return self.loaded

    def save(self):
        with self.lock:
            payload = {"version": VERSION, "user": self.user, "server": self.server, "folders": self.folders,
                       "tags": self.tags, "shares": self.shares, "pending": self.pending,
                       "synced_at": self.synced_at, "unreadable": self.unreadable, "cse": self.cse}
            return secure.save(self.user, payload, self.path)

    # ---- what the window shows -----------------------------------------------------------------------------
    def entries(self):
        """id → entry: the cloud's copy with the pending changes applied ("pending": True on those)."""
        with self.lock:
            out = {k: dict(v) for k, v in self.server.items()}
            for op in self.pending:
                entry_id = op["id"]
                if op["kind"] == "save":
                    base = out.get(entry_id)
                    changed = {f: copy.deepcopy(op["entry"].get(f)) for f in op["fields"]}
                    merged = {**base, **changed} if base else copy.deepcopy(op["entry"])
                    merged["pending"] = True
                    out[entry_id] = merged
                elif entry_id in out and op["kind"] in ("trash", "restore"):
                    out[entry_id]["trashed"] = op["kind"] == "trash"
                    out[entry_id]["pending"] = True
                elif op["kind"] == "purge":
                    out.pop(entry_id, None)
            return out

    def entry(self, entry_id):
        return self.entries().get(entry_id)

    def pending_count(self):
        with self.lock:
            return len(self.pending)

    # ---- changes made here ---------------------------------------------------------------------------------
    def _next(self):
        self._seq += 1
        return self._seq

    def save_entry(self, entry, fields=None):
        """Create (no id) or change an entry. fields: the ones that changed (all of them by default).
        Returns the entry's id (a local one until the cloud gives its own)."""
        with self.lock:
            entry = copy.deepcopy(dict(entry))
            entry.pop("pending", None)
            entry_id = entry.get("id") or ""
            if not entry_id:
                entry_id = "local-" + uuid.uuid4().hex
                entry.update({"id": entry_id, "created": int(time.time()), "trashed": False, "editable": True})
            entry["updated"] = int(time.time())
            fields = [f for f in (fields or FIELDS) if f in FIELDS]
            current = self.entries().get(entry_id) or {}
            if current and current.get("password") != entry.get("password"):
                entry["edited"] = int(time.time())
            for op in self.pending:
                if op["kind"] == "save" and op["id"] == entry_id:
                    op["fields"] = sorted(set(op["fields"]) | set(fields))
                    op["entry"] = {**op["entry"], **{f: entry.get(f) for f in fields},
                                   "updated": entry["updated"], "edited": entry.get("edited", op["entry"].get("edited", 0))}
                    op["seq"] = self._next()
                    break
            else:
                base = self.server.get(entry_id)
                full = {**(base or {}), **entry}
                self.pending.append({"seq": self._next(), "kind": "save", "id": entry_id,
                                     "base": base.get("revision") if base else None, "fields": fields, "entry": full})
            self.save()
            return entry_id

    def _queue(self, kind, ids):
        """One change for one entry or several (a selection): the vault is written once."""
        with self.lock:
            for entry_id in ids:
                self._queue_one(kind, entry_id)
            self.save()

    def _queue_one(self, kind, entry_id):
        if kind == "purge" and entry_id not in self.server:
            # never reached the cloud: forgotten here, nothing to send
            self.pending = [op for op in self.pending if op["id"] != entry_id]
            return
        if kind in ("trash", "restore"):
            opposite = "restore" if kind == "trash" else "trash"
            last = next((op for op in reversed(self.pending) if op["id"] == entry_id and op["kind"] in ("trash", "restore")), None)
            if last and last["kind"] == opposite:
                self.pending.remove(last)      # trashed then restored before any sync: nothing to send
                return
        self.pending.append({"seq": self._next(), "kind": kind, "id": entry_id, "base": None, "fields": [], "entry": {}})

    def trash(self, *ids):
        self._queue("trash", ids)

    def restore(self, *ids):
        self._queue("restore", ids)

    def purge(self, *ids):
        self._queue("purge", ids)

    # ---- sync --------------------------------------------------------------------------------------------
    def _replace_id(self, old, new):
        for op in self.pending:
            if op["id"] == old:
                op["id"] = new
                if op["entry"]:
                    op["entry"]["id"] = new

    def _done(self, op, revision=None):
        """An operation reached the cloud. If the entry changed again here meanwhile (another seq), the
        operation stays, now based on the new revision."""
        with self.lock:
            for current in self.pending:
                if current["kind"] == op["kind"] and current["id"] == op["id"]:
                    if current["seq"] == op["seq"]:
                        self.pending.remove(current)
                    elif revision:
                        current["base"] = revision
                    break
            self.save()

    def push(self, api, report=None):
        """Send the pending changes in order. Stops (ApiError 0) when the network goes; refused ones are
        dropped (the next pull shows the cloud's version) and told through report(kind, entry, error)."""
        while True:
            with self.lock:
                if not self.pending:
                    return
                op = copy.deepcopy(self.pending[0])
            try:
                self._send(api, op)
            except ApiError as error:
                if error.status in (0, 401, 423) or error.status >= 500:
                    raise
                with self.lock:
                    self.pending = [p for p in self.pending if p["seq"] != op["seq"]]
                    self.save()
                if report:
                    report(op["kind"], op.get("entry") or self.server.get(op["id"]) or {}, error)

    def _send(self, api, op):
        kind, entry_id = op["kind"], op["id"]
        if kind == "save":
            entry = op["entry"]
            if op["base"] is None or entry_id.startswith("local-"):
                made = api.create(entry)
                new_id, revision = made["id"], made.get("revision")
                with self.lock:
                    self._replace_id(entry_id, new_id)
                    op["id"] = new_id
                    stored = {**entry, "id": new_id, "revision": revision or "", "pending": False}
                    stored.pop("pending", None)
                    self.server[new_id] = stored
                self._done(op, revision)
                return
            try:
                result = api.update(entry, op["base"])
            except ApiError as error:
                if error.status == 409:
                    fresh = normalize(api.show(entry_id))
                    if fresh is None:
                        raise
                    merged = {**fresh, **{f: entry.get(f) for f in op["fields"]}}
                    result = api.update(merged, fresh["revision"])
                    entry = merged
                elif error.status == 404:
                    # gone from the cloud (deleted elsewhere): kept, as a new entry
                    made = api.create(entry)
                    with self.lock:
                        self._replace_id(entry_id, made["id"])
                        self.server.pop(entry_id, None)
                        op["id"] = made["id"]
                        self.server[made["id"]] = {**entry, "id": made["id"], "revision": made.get("revision") or ""}
                    self._done(op, made.get("revision"))
                    return
                else:
                    raise
            with self.lock:
                stored = {**self.server.get(entry_id, {}), **{f: entry.get(f) for f in FIELDS}}
                stored["revision"] = (result or {}).get("revision") or stored.get("revision", "")
                stored.pop("pending", None)
                self.server[entry_id] = stored
            self._done(op, stored["revision"])
            return
        if kind == "trash":
            current = self.server.get(entry_id)
            if current is not None and not current.get("trashed"):
                try:
                    api.delete(entry_id)
                except ApiError as error:
                    if error.status != 404:
                        raise
                with self.lock:
                    if entry_id in self.server:
                        self.server[entry_id]["trashed"] = True
        elif kind == "restore":
            try:
                api.restore(entry_id)
            except ApiError as error:
                if error.status != 404:
                    raise
            with self.lock:
                if entry_id in self.server:
                    self.server[entry_id]["trashed"] = False
        elif kind == "purge":
            current = self.server.get(entry_id)
            try:
                if current is not None and not current.get("trashed"):
                    api.delete(entry_id)              # first to the trash: a purge is a second delete
                api.delete(entry_id)
            except ApiError as error:
                if error.status != 404:
                    raise
            with self.lock:
                self.server.pop(entry_id, None)
        self._done(op)

    def pull(self, api):
        """Read everything from the cloud (a few hundred entries: one request each for the lists)."""
        cse = api.locked()
        if cse:
            with self.lock:
                self.cse = True
                self.save()
            return
        raw = list(api.passwords()) + list(api.trashed())
        folders = api.folders()
        tags = api.tags()
        try:
            shares = api.shares()
        except ApiError as error:
            if error.status == 0:
                raise
            shares = []
        server, unreadable = {}, 0
        for item in raw:
            entry = normalize(item)
            if entry is None:
                unreadable += 1
            elif not entry["hidden"]:
                server[entry["id"]] = entry
        with self.lock:
            self.server = server
            self.unreadable = unreadable
            self.cse = False
            self.folders = {f["id"]: {"id": f["id"], "label": f.get("label") or "", "parent": f.get("parent") or "",
                                      "trashed": bool(f.get("trashed")), "revision": f.get("revision") or "",
                                      "favorite": bool(f.get("favorite"))}
                            for f in folders if isinstance(f, dict) and f.get("id") and not f.get("hidden")}
            self.tags = {t["id"]: {"id": t["id"], "label": t.get("label") or "", "color": t.get("color") or ""}
                         for t in tags if isinstance(t, dict) and t.get("id") and not t.get("hidden")}
            self.shares = [{"id": s["id"], "password": s.get("password") if isinstance(s.get("password"), str) else (s.get("password") or {}).get("id"),
                            "owner": (s.get("owner") or {}), "receiver": (s.get("receiver") or {}),
                            "editable": bool(s.get("editable"))}
                           for s in shares if isinstance(s, dict) and s.get("id")]
            self.synced_at = int(time.time())
            self.save()

    def sync(self, api, report=None):
        self.push(api, report)
        self.pull(api)
        self.push(api, report)        # what changed here while reading
