"""Calendar and contact sync: one worker thread, so network calls never block the window and writes
keep their order.

Reading: every 5 minutes, when the window comes back to the front, and after each write. Each
collection asks the server only what changed since its token (RFC 6578), then fetches those objects.
Writing is optimistic: the cache changes at once (the window redraws), the server follows; when it
refuses (conflict, rights), the collection is read again and the window is told.
"""
import json
import os
import traceback
import unicodedata
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from plume_core import ical, vcard
from plume_core.dav import Client, DavError

EVERY_MS = 5 * 60 * 1000


def sort_key(name):
    base = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower().strip()
    return base or "~"


class Sync(QObject):
    calendarsChanged = Signal()
    contactsChanged = Signal()
    busyChanged = Signal()
    failed = Signal(str)
    reached = Signal(str, bool)                # the cloud answered (or not): Plume.reached

    def __init__(self, plume, store):
        super().__init__()
        self._plume, self._store = plume, store
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="plume-sync")
        self._client = None
        self._busy = False
        self._addresses = set(store.get("my_addresses", []))
        self.extra_addresses = lambda: set()   # the external mailboxes of Plume (set by plume.py)
        self._timer = QTimer(self)
        self._timer.setInterval(EVERY_MS)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        plume.accountChanged.connect(self._account_changed)
        self._account = plume.account()

    def _account_changed(self):
        if plume_account_key(self._plume.account()) == plume_account_key(self._account):
            return
        previous = self._account
        self._account = self._plume.account()
        self._client = None
        if previous is not None:
            # Another account: nothing of the previous one stays on screen
            self._submit(self._forget)
        self.refresh()

    def _forget(self):
        self._store.execute("DELETE FROM collections")
        self._store.set("homes", None)
        self.calendarsChanged.emit()
        self.contactsChanged.emit()

    @property
    def addresses(self):
        """Who "me" is in invitations: the cloud's addresses for this account, then Plume's other mailboxes."""
        return self._addresses | self.extra_addresses()

    def server_addresses(self):
        """The addresses the cloud answers invitations for by itself (its scheduling)."""
        return set(self._addresses)

    def client(self):
        account = self._account
        if account is None:
            return None
        if self._client is None:
            server, user, password = account
            root = os.environ.get("PLUME_DAV_ROOT") or server + "/remote.php/dav/"
            self._client = Client(root, user, password)
        return self._client

    def busy(self):
        return self._busy

    @Slot()
    def refresh(self):
        if self._account is not None:
            self._submit(self._sync_all)

    def _submit(self, fn, *args):
        def run():
            try:
                fn(*args)
                self.reached.emit("dav", True)
            except DavError as error:
                if error.status in (401, 403) and fn is self._sync_all:
                    self.failed.emit("auth")
                elif error.status == 0:
                    self.reached.emit("dav", False)
                    self.failed.emit("offline")
                else:
                    self.failed.emit("server")
            except Exception:
                traceback.print_exc()
                self.failed.emit("server")
        return self._pool.submit(run)

    # ---- reading ------------------------------------------------------------------------------------
    def _sync_all(self):
        client = self.client()
        if client is None:
            return
        self._busy = True
        self.busyChanged.emit()
        try:
            homes = self._store.get("homes")
            if not homes or homes.get("user") != client.user:
                calendars, books = client.homes()
                homes = {"user": client.user, "calendars": calendars, "books": books, "principal": client.principal}
                self._store.set("homes", homes)
            self._load_addresses(client, homes)
            changed_cal = self._sync_kind(client, homes["calendars"], "calendar")
            changed_card = self._sync_kind(client, homes["books"], "addressbook") if homes.get("books") else False
        finally:
            self._busy = False
            self.busyChanged.emit()
        if changed_cal:
            self.calendarsChanged.emit()
        if changed_card:
            self.contactsChanged.emit()

    def _load_addresses(self, client, homes):
        """The user's own addresses (calendar-user-address-set): who "me" is in invitations."""
        found = set()
        try:
            status, doc = client._xml(
                "PROPFIND", homes["principal"],
                '<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:prop>'
                '<c:calendar-user-address-set/></d:prop></d:propfind>', "0")
            if doc is not None:
                for node in doc.iter("{DAV:}href"):
                    value = (node.text or "").strip()
                    if value.lower().startswith("mailto:"):
                        found.add(value[7:].lower())
        except DavError:
            pass
        profile = self._plume.profile
        for value in (profile.get("email"), f"{client.user}@orneos.eu"):
            if value:
                found.add(value.lower())
        if found != self._addresses:
            self._addresses = found
            self._store.set("my_addresses", sorted(found))

    def _sync_kind(self, client, home, kind):
        remote = client.collections(home, kind)
        rows = {r["href"]: r for r in self._store.query("SELECT * FROM collections WHERE kind = ?", (kind,))}
        changed = False
        for gone in set(rows) - {c["href"] for c in remote}:
            self._store.execute("DELETE FROM collections WHERE href = ?", (gone,))
            changed = True
        for col in remote:
            row = rows.get(col["href"])
            values = (col["name"], col["color"], col["order"], int(col["readonly"]), int(col["shared"]), col["owner_name"])
            if row is None:
                self._store.execute(
                    "INSERT INTO collections (kind, href, name, color, sort, readonly, shared, owner_name) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (kind, col["href"]) + values)
                row = self._store.query("SELECT * FROM collections WHERE href = ?", (col["href"],))[0]
                changed = True
            elif (row["name"], row["color"], row["sort"], row["readonly"], row["shared"], row["owner_name"]) != values:
                self._store.execute(
                    "UPDATE collections SET name = ?, color = ?, sort = ?, readonly = ?, shared = ?, owner_name = ? "
                    "WHERE id = ?", values + (row["id"],))
                changed = True
            if col["sync_token"] and col["sync_token"] == row["sync_token"]:
                continue
            changed |= self._sync_collection(client, row["id"], col["href"], row["sync_token"], kind)
        return changed

    def _sync_collection(self, client, collection_id, href, token, kind):
        table = "events" if kind == "calendar" else "contacts"
        local = {r["href"]: r["etag"] for r in self._store.query(f"SELECT href, etag FROM {table} WHERE collection_id = ?", (collection_id,))}
        local_paths = {client.path(h): h for h in local}
        try:
            try:
                new_token, changed, deleted = client.sync(href, token)
            except DavError as error:
                if not token or error.status not in (403, 409, 400):
                    raise
                new_token, changed, deleted = client.sync(href, "")
                token = ""
            if not token:
                # Full listing: whatever the cache has and the server did not list is gone
                listed = {client.path(h) for h in changed}
                deleted = [h for p, h in local_paths.items() if p not in listed]
        except DavError as error:
            if error.status in (0, 401):
                raise
            # No sync-collection on this server: compare every etag
            new_token = ""
            remote = client.etags(href)
            changed = {h: e for h, e in remote.items() if local.get(local_paths.get(client.path(h), h)) != e}
            listed = {client.path(h) for h in remote}
            deleted = [h for p, h in local_paths.items() if p not in listed]
        stale = {h: e for h, e in changed.items() if local.get(local_paths.get(client.path(h), h)) != e}
        fetched = client.multiget(href, stale.keys(), kind) if stale else {}
        rows = []
        for ref, (etag, data) in fetched.items():
            ref = local_paths.get(client.path(ref), ref)
            if kind == "calendar":
                info = ical.index(data, self.addresses)
                if info is None:
                    continue
                rows.append((collection_id, ref, etag or stale.get(ref, ""), info["uid"], info["title"], info["start_ts"],
                             info["end_ts"], int(info["recurring"]), int(info["pending"]), data))
            else:
                card = vcard.parse(data)
                rows.append((collection_id, ref, etag or stale.get(ref, ""), card["uid"], card["fn"], sort_key(card["fn"]),
                             card["org"], json.dumps([e["value"] for e in card["emails"]]),
                             json.dumps([p["value"] for p in card["phones"]]), json.dumps(card["categories"]), data))
        if kind == "calendar":
            self._store.many(
                "INSERT INTO events (collection_id, href, etag, uid, title, start_ts, end_ts, recurring, pending, ics) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(collection_id, href) DO UPDATE SET etag = excluded.etag, "
                "uid = excluded.uid, title = excluded.title, start_ts = excluded.start_ts, end_ts = excluded.end_ts, "
                "recurring = excluded.recurring, pending = excluded.pending, ics = excluded.ics", rows)
        else:
            self._store.many(
                "INSERT INTO contacts (collection_id, href, etag, uid, name, sort_key, org, emails, phones, categories, vcard) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(collection_id, href) DO UPDATE SET etag = excluded.etag, "
                "uid = excluded.uid, name = excluded.name, sort_key = excluded.sort_key, org = excluded.org, "
                "emails = excluded.emails, phones = excluded.phones, categories = excluded.categories, vcard = excluded.vcard", rows)
        gone = [(collection_id, local_paths.get(client.path(h), h)) for h in deleted]
        if gone:
            self._store.many(f"DELETE FROM {table} WHERE collection_id = ? AND href = ?", gone)
        self._store.execute("UPDATE collections SET sync_token = ? WHERE id = ?", (new_token or "", collection_id))
        return bool(rows or gone)

    def resync(self, collection_id):
        def run():
            client = self.client()
            row = self._store.query("SELECT * FROM collections WHERE id = ?", (collection_id,))
            if client is None or not row:
                return
            kind = row[0]["kind"]
            self._sync_collection(client, collection_id, row[0]["href"], row[0]["sync_token"], kind)
            (self.calendarsChanged if kind == "calendar" else self.contactsChanged).emit()
        self._submit(run)

    # ---- calendars: made, renamed, recoloured, deleted (the list shows it at once, the cloud follows) -----
    def _calendar_home(self):
        homes = self._store.get("homes") or {}
        return homes.get("calendars")

    def create_calendar(self, name, color, url=""):
        """A new calendar, or one followed from a link (url): it shows once the cloud has made it."""
        def run():
            client, home = self.client(), self._calendar_home()
            if client is None or not home:
                return
            if url:
                client.subscribe(home, url, name, color)
            else:
                client.make_calendar(home, name, color)
            self._sync_all()
        self._submit(run)

    def update_calendar(self, collection_id, name=None, color=None):
        row = self._store.query("SELECT * FROM collections WHERE id = ?", (collection_id,))
        if not row:
            return
        if name is not None:
            self._store.execute("UPDATE collections SET name = ? WHERE id = ?", (name, collection_id))
        if color is not None:
            self._store.execute("UPDATE collections SET color = ? WHERE id = ?", (color, collection_id))
        self.calendarsChanged.emit()
        href = row[0]["href"]

        def run():
            client = self.client()
            if client is None:
                return
            try:
                client.update_calendar(href, name, color)
            finally:
                self._sync_all()            # refused: the cloud's name and colour come back
        self._submit(run)

    def delete_calendar(self, collection_id):
        """Gone from the list now; the cloud keeps it in its trash bin (30 days)."""
        row = self._store.query("SELECT * FROM collections WHERE id = ?", (collection_id,))
        if not row:
            return
        href = row[0]["href"]
        self._store.execute("DELETE FROM events WHERE collection_id = ?", (collection_id,))
        self._store.execute("DELETE FROM collections WHERE id = ?", (collection_id,))
        self.calendarsChanged.emit()

        def run():
            client = self.client()
            if client is None:
                return
            try:
                client.delete(href)
            finally:
                self._sync_all()
        self._submit(run)

    # ---- writing ------------------------------------------------------------------------------------
    def save_event(self, collection_id, href, ics, etag):
        """Write an event: in the cache now (the window redraws), on the server next."""
        info = ical.index(ics, self.addresses)
        if info is None:
            return False
        self._store.execute(
            "INSERT INTO events (collection_id, href, etag, uid, title, start_ts, end_ts, recurring, pending, ics) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(collection_id, href) DO UPDATE SET uid = excluded.uid, "
            "title = excluded.title, start_ts = excluded.start_ts, end_ts = excluded.end_ts, "
            "recurring = excluded.recurring, pending = excluded.pending, ics = excluded.ics",
            (collection_id, href, etag or "", info["uid"], info["title"], info["start_ts"], info["end_ts"],
             int(info["recurring"]), int(info["pending"]), ics))
        self.calendarsChanged.emit()
        self.push(collection_id, href, ics, "text/calendar; charset=utf-8", etag, "events")
        return True

    def save_contact(self, collection_id, href, card_text, etag):
        card = vcard.parse(card_text)
        self._store.execute(
            "INSERT INTO contacts (collection_id, href, etag, uid, name, sort_key, org, emails, phones, categories, vcard) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(collection_id, href) DO UPDATE SET uid = excluded.uid, "
            "name = excluded.name, sort_key = excluded.sort_key, org = excluded.org, emails = excluded.emails, "
            "phones = excluded.phones, categories = excluded.categories, vcard = excluded.vcard",
            (collection_id, href, etag or "", card["uid"], card["fn"], sort_key(card["fn"]), card["org"],
             json.dumps([e["value"] for e in card["emails"]]), json.dumps([p["value"] for p in card["phones"]]),
             json.dumps(card["categories"]), card_text))
        self.contactsChanged.emit()
        self.push(collection_id, href, card_text, "text/vcard; charset=utf-8", etag, "contacts")

    def delete(self, table, collection_id, href, etag):
        self._store.execute(f"DELETE FROM {table} WHERE collection_id = ? AND href = ?", (collection_id, href))
        (self.calendarsChanged if table == "events" else self.contactsChanged).emit()
        self.remove(collection_id, href, etag, table)

    def move_event(self, collection_id, href, target_id, target_href):
        """An event into another calendar: in the cache now, on the server next (MOVE)."""
        self._store.execute("UPDATE events SET collection_id = ?, href = ?, etag = '' WHERE collection_id = ? AND href = ?",
                            (target_id, target_href, collection_id, href))
        self.calendarsChanged.emit()

        def run():
            client = self.client()
            try:
                etag = client.move(href, target_href)
                self._store.execute("UPDATE events SET etag = ? WHERE collection_id = ? AND href = ?",
                                    (etag, target_id, target_href))
            except DavError as error:
                self.failed.emit("offline" if error.status == 0 else "save")
                self._store.execute("UPDATE events SET collection_id = ?, href = ? WHERE collection_id = ? AND href = ?",
                                    (collection_id, href, target_id, target_href))
                self._restore(client, collection_id, href, "events")
        self._submit(run)

    def push(self, collection_id, href, data, content_type, etag, table):
        """PUT data (create when etag is empty), then keep the server's new etag. etag None: the one the
        cache holds when the write leaves (a change right after a creation waits for its etag)."""
        def run():
            client = self.client()
            nonlocal etag
            if etag is None:
                rows = self._store.query(f"SELECT etag FROM {table} WHERE collection_id = ? AND href = ?", (collection_id, href))
                etag = rows[0]["etag"] if rows else ""
            try:
                new_etag = client.put(href, data, content_type, etag or None)
                self._store.execute(f"UPDATE {table} SET etag = ? WHERE collection_id = ? AND href = ?",
                                    (new_etag, collection_id, href))
            except DavError as error:
                # a card changed elsewhere meanwhile: both changes kept (People.merge_conflict)
                merge = getattr(self, "on_conflict", None) if table == "contacts" and error.status == 412 else None
                if merge and merge(client, collection_id, href, data):
                    return
                self.failed.emit("conflict" if error.status == 412 else "offline" if error.status == 0 else "save")
                self._restore(client, collection_id, href, table)
        self._submit(run)

    def remove(self, collection_id, href, etag, table):
        def run():
            client = self.client()
            try:
                client.delete(href, etag or None)
            except DavError as error:
                self.failed.emit("conflict" if error.status == 412 else "offline" if error.status == 0 else "save")
                self._restore(client, collection_id, href, table)
        self._submit(run)

    def _restore(self, client, collection_id, href, table):
        """After a refused write: the server's version of this object again, or nothing if it has none."""
        kind = "calendar" if table == "events" else "addressbook"
        try:
            found = client.multiget(self._href_of(collection_id), [href], kind)
        except DavError:
            found = None
        if found is not None and not found:
            self._store.execute(f"DELETE FROM {table} WHERE collection_id = ? AND href = ?", (collection_id, href))
        elif found:
            etag, data = next(iter(found.values()))
            if table == "events":
                info = ical.index(data, self.addresses)
                if info:
                    self._store.execute(
                        "UPDATE events SET etag = ?, uid = ?, title = ?, start_ts = ?, end_ts = ?, recurring = ?, "
                        "pending = ?, ics = ? WHERE collection_id = ? AND href = ?",
                        (etag, info["uid"], info["title"], info["start_ts"], info["end_ts"], int(info["recurring"]),
                         int(info["pending"]), data, collection_id, href))
            else:
                card = vcard.parse(data)
                self._store.execute(
                    "UPDATE contacts SET etag = ?, uid = ?, name = ?, sort_key = ?, org = ?, emails = ?, phones = ?, "
                    "categories = ?, vcard = ? WHERE collection_id = ? AND href = ?",
                    (etag, card["uid"], card["fn"], sort_key(card["fn"]), card["org"],
                     json.dumps([e["value"] for e in card["emails"]]), json.dumps([p["value"] for p in card["phones"]]),
                     json.dumps(card["categories"]), data, collection_id, href))
        (self.calendarsChanged if table == "events" else self.contactsChanged).emit()

    def _href_of(self, collection_id):
        rows = self._store.query("SELECT href FROM collections WHERE id = ?", (collection_id,))
        return rows[0]["href"] if rows else ""

    def shutdown(self):
        self._pool.shutdown(wait=False, cancel_futures=True)


def plume_account_key(account):
    return (account[0], account[1]) if account else None
