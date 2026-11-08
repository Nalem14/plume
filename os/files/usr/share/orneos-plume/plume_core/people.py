"""What the Contacts module sees: the address books, groups, a filtered list model, one card, edits.

The list is a real list model (thousands of contacts scroll without building them all); the filter
runs in SQLite. Groups are the cards' CATEGORIES, like in the cloud app (a group made empty here is
remembered on the computer until someone is put in it).
Deleting waits UNDO_MS before the cloud hears of it (« Annuler »); a card changed elsewhere while mine
was on its way is merged (vcard.merge), not lost.
"""
import base64
import json
import re
import threading
import time
import urllib.parse
import uuid
import zlib
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QAbstractListModel, QByteArray, QModelIndex, QObject, Property, Qt, Signal, Slot

from PySide6.QtCore import QCoreApplication, QTimer

import cloud
import links
import system
from plume_core import contacts_books, contacts_csv, ical, mime, vcard
from plume_core.app import initials
from plume_core.dav import DavError
from plume_core.store import fold

ROLES = ["contactId", "name", "initials", "subtitle", "section", "tint", "photo"]
UNDO_MS = 6000
PHOTOS = system.CACHE / "contact-photos"          # small copies of the cards' photos, for the list
PHOTO_PX = 192


class ContactList(QAbstractListModel):
    def __init__(self):
        super().__init__()
        self._rows = []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def roleNames(self):
        return {Qt.ItemDataRole.UserRole + i: QByteArray(name.encode()) for i, name in enumerate(ROLES)}

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        i = role - Qt.ItemDataRole.UserRole
        return self._rows[index.row()][i] if 0 <= i < len(ROLES) else None

    def set_rows(self, rows):
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def row_of(self, contact_id):
        for i, row in enumerate(self._rows):
            if row[0] == contact_id:
                return i
        return -1


def section(name):
    first = (name.strip()[:1] or "#").upper()
    base = vcard_ascii(first)
    return base if base.isalpha() else "#"


GENERATED = ("z-server-generated--", "z-app-generated--")


def generated(href):
    """The cloud's own read-only books: its accounts, and the people written to (contactsinteraction)."""
    return any(mark in (href or "") for mark in GENERATED)


def vcard_ascii(text):
    import unicodedata
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode() or text


LOOKUP_DAYS = 7          # an address that is no account of the cloud is asked again after a week




def _photo_name(contact_id, card_text):
    return f"{contact_id}-{zlib.crc32(card_text.encode()) & 0xffffffff:08x}.jpg"


def primary(emails):
    """The address to write to: the one marked preferred, else the first."""
    return next((e["value"] for e in emails if e.get("pref")), emails[0]["value"] if emails else "")


class People(QObject):
    changed = Signal()
    _cloudFound = Signal()
    _photosReady = Signal()
    filterChanged = Signal()
    waitingChanged = Signal()
    sortChanged = Signal()
    booksDone = Signal(str, bool)          # what (create, rename, delete, share, unshare), ok
    sharesRead = Signal(int, "QVariantList")

    def __init__(self, store, sync):
        super().__init__()
        self._store, self._sync = store, sync
        self._model = ContactList()
        self._query, self._book, self._group = "", 0, ""
        self._revision = 0
        self._total = 0
        self._asking = set()
        self._hiddenIds = {}               # undo token → ids waiting to be deleted
        self._undo = {}                    # undo token → what to put back (a merge)
        self._bases = {}                   # (collection id, href) → the card before my change (conflicts)
        self._making = set()               # photos being made
        sync.contactsChanged.connect(self._reload)
        self._cloudFound.connect(self._reload)
        self._photosReady.connect(self._reload)
        sync.busyChanged.connect(self.waitingChanged)
        self.changed.connect(self.waitingChanged)
        sync.on_conflict = self.merge_conflict
        app = QCoreApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._flush)
        self._reload()

    def _t(self, key, default):
        plume = getattr(self._sync, "_plume", None)
        return (getattr(plume, "_t", None) or {}).get(key, default)

    def _book_name(self, href, name):
        """The cloud names its own books in English: Accounts, Recently contacted."""
        if "z-server-generated--system" in (href or ""):
            return self._t("book_accounts", name)
        if "contactsinteraction--recent" in (href or ""):
            return self._t("book_recent", name)
        return name

    def _hidden(self):
        """Cards of the cloud's own books (accounts, recently contacted) whose address is already on a
        card of mine: one line per person in « All contacts » and the groups."""
        rows = self._store.query("SELECT p.id, p.emails, c.href FROM contacts p JOIN collections c ON c.id = p.collection_id")
        rank = lambda href: 2 if "contactsinteraction" in (href or "") else 1 if generated(href) else 0
        seen, hidden = set(), set()
        for r in sorted(rows, key=lambda r: rank(r["href"])):
            emails = {e.lower() for e in json.loads(r["emails"] or "[]")}
            if rank(r["href"]) and emails & seen:
                hidden.add(r["id"])
            seen |= emails
        return hidden

    def _deleting(self):
        return {i for ids in self._hiddenIds.values() for i in ids}

    # ---- the list -----------------------------------------------------------------------------------
    def _reload(self):
        self._revision += 1
        by_family = self.sortBy == "family"
        sql = ("SELECT p.id, p.name, p.org, p.emails, p.sort_key, "
               "CASE WHEN instr(p.vcard, 'PHOTO') > 0" + (" OR 1" if by_family else "") + " THEN p.vcard END AS card "
               "FROM contacts p JOIN collections c ON c.id = p.collection_id WHERE 1 = 1")
        args = []
        if self._book:
            sql += " AND p.collection_id = ?"
            args.append(self._book)
        if self._group:
            sql += " AND p.categories LIKE ?"
            args.append("%" + json.dumps(self._group)[1:-1] + "%")
        query = self._query.strip()
        if query:
            # accents and case aside (« elodie » finds « Élodie »), numbers without their spaces
            needle = "%" + fold(query) + "%"
            sql += " AND (p.sort_key LIKE ? OR fold(p.name) LIKE ? OR fold(p.emails) LIKE ? OR fold(p.org) LIKE ?"
            args += [needle, needle, needle, needle]
            numbers = "".join(ch for ch in query if ch.isdigit())
            if len(numbers) >= 3 and re.fullmatch(r"[\d\s.+()/-]+", query):
                local = vcard._digits(query)
                sql += " OR digits(replace(p.phones, '+33', '0')) LIKE ? OR digits(p.phones) LIKE ?"
                args += ["%" + local + "%", "%" + numbers + "%"]
            sql += ")"
        sql += " ORDER BY p.sort_key, p.id"
        rows = []
        everywhere = self._hidden()
        deleting = self._deleting()
        hidden = (set() if self._book else everywhere) | deleting
        self._total = self._store.query("SELECT COUNT(*) FROM contacts")[0][0] - len(everywhere | deleting)
        missing = []
        for r in self._store.query(sql, args):
            if r["id"] in hidden:
                continue
            emails = json.loads(r["emails"] or "[]")
            name = r["name"] or (emails[0] if emails else "")
            key = r["sort_key"]
            if by_family and r["card"]:
                family = _family(r["card"])
                if family:
                    key = fold(family) + " " + key
            photo = ""
            if r["card"] and "PHOTO" in r["card"]:
                path = PHOTOS / _photo_name(r["id"], r["card"])
                if path.exists():
                    photo = path.as_uri()
                elif r["id"] not in self._making:
                    missing.append((r["id"], r["card"]))
            rows.append([r["id"], name, initials(name), r["org"] or (emails[0] if emails else ""),
                         section(key if by_family else name), zlib.crc32(name.encode()) % 4, photo, key])
        if by_family:
            rows.sort(key=lambda row: (row[7], row[0]))
        self._model.set_rows([row[:7] for row in rows])
        self.changed.emit()
        if missing:
            self._make_photos(missing)

    def _make_photos(self, cards):
        """Small square copies of the cards' photos (a data: picture, or one the cloud serves)."""
        self._making.update(i for i, _ in cards)
        account = self._sync._plume.account() if hasattr(self._sync, "_plume") else None

        def run():
            from PySide6.QtGui import QImage
            PHOTOS.mkdir(parents=True, exist_ok=True)
            made = False
            for contact_id, text in cards:
                photo = vcard.parse(text).get("photo") or ""
                data = b""
                try:
                    if photo.startswith("data:") and ";base64," in photo:
                        data = base64.b64decode(photo.split(";base64,", 1)[1] + "==")
                    elif photo.startswith(("http://", "https://")) and account and \
                            urllib.parse.urlsplit(photo).hostname == urllib.parse.urlsplit(account[0]).hostname:
                        # only from our own cloud: an address elsewhere would tell that site the card was opened
                        data = _fetch(photo, account)
                except (ValueError, OSError):
                    data = b""
                image = QImage.fromData(data) if data else QImage()
                if image.isNull():
                    continue
                side = min(image.width(), image.height())
                image = image.copy((image.width() - side) // 2, (image.height() - side) // 2, side, side)
                image = image.scaled(PHOTO_PX, PHOTO_PX, Qt.AspectRatioMode.IgnoreAspectRatio,
                                     Qt.TransformationMode.SmoothTransformation)
                for old in PHOTOS.glob(f"{contact_id}-*.jpg"):
                    old.unlink(missing_ok=True)
                if image.convertToFormat(QImage.Format.Format_RGB32).save(str(PHOTOS / _photo_name(contact_id, text)), "JPG", 88):
                    made = True
            if made:
                self._photosReady.emit()
        threading.Thread(target=run, daemon=True).start()

    @Property(bool, notify=waitingChanged)
    def waiting(self):
        """No card yet and the first sync under way: the list shows its waiting shapes."""
        return self._model.rowCount() == 0 and not self._query.strip() and self._sync.busy()

    @Property(QObject, constant=True)
    def model(self):
        return self._model

    @Property(int, notify=changed)
    def revision(self):
        return self._revision

    @Property(int, notify=changed)
    def count(self):
        return self._model.rowCount()

    @Property("QVariantList", notify=changed)
    def books(self):
        rows = self._store.query(
            "SELECT c.id, c.href, c.name, c.readonly, c.shared, c.owner_name, COUNT(p.id) AS n FROM collections c "
            "LEFT JOIN contacts p ON p.collection_id = c.id WHERE c.kind = 'addressbook' GROUP BY c.id "
            "ORDER BY c.shared, c.sort, c.name")
        return [{"id": r["id"], "name": self._book_name(r["href"], r["name"]), "count": r["n"], "readonly": bool(r["readonly"]),
                 "shared": bool(r["shared"]), "ownerName": r["owner_name"], "generated": generated(r["href"]),
                 "mine": not r["shared"] and not generated(r["href"])} for r in rows]

    @Property(int, notify=changed)
    def total(self):
        return self._total

    def _extra_groups(self):
        return [g for g in (self._store.get("pref_contact_groups", []) or []) if isinstance(g, str)]

    @Property("QVariantList", notify=changed)
    def groups(self):
        counts = {}
        deleting = self._deleting()
        for r in self._store.query("SELECT id, categories FROM contacts WHERE categories NOT IN ('', '[]')"):
            if r["id"] in deleting:
                continue
            for name in json.loads(r["categories"] or "[]"):
                counts[name] = counts.get(name, 0) + 1
        extra = self._extra_groups()
        if any(g in counts for g in extra):          # a group made here now has people: the cards keep it
            self._store.set("pref_contact_groups", [g for g in extra if g not in counts])
        for g in extra:
            counts.setdefault(g, 0)
        return [{"name": n, "count": c} for n, c in sorted(counts.items(), key=lambda kv: kv[0].lower())]

    @Slot(str, result=bool)
    def createGroup(self, name):
        """An empty group, kept on this computer until a card is put in it (groups live on the cards)."""
        name = name.strip()
        if not name or any(g["name"] == name for g in self.groups):
            return False
        self._store.set("pref_contact_groups", self._extra_groups() + [name])
        self._reload()
        return True

    @Property(int, notify=changed)
    def defaultBook(self):
        for book in self.books:
            if not book["readonly"] and not book["shared"]:
                return book["id"]
        return next((b["id"] for b in self.books if not b["readonly"]), 0)

    @Property(str, notify=filterChanged)
    def query(self):
        return self._query

    @Property(int, notify=filterChanged)
    def book(self):
        return self._book

    @Property(str, notify=filterChanged)
    def group(self):
        return self._group

    @Property(str, notify=sortChanged)
    def sortBy(self):
        """« given » (Jean Dupont under J) or « family » (under D, as a French directory)."""
        return self._store.get("pref_contacts_sort", "given") or "given"

    @Slot(str)
    def setSortBy(self, value):
        if value in ("given", "family") and value != self.sortBy:
            self._store.set("pref_contacts_sort", value)
            self.sortChanged.emit()
            self._reload()

    @Slot(str, int, str)
    def setFilter(self, query, book, group):
        if (query, book, group) != (self._query, self._book, self._group):
            self._query, self._book, self._group = query, book, group
            self.filterChanged.emit()
            self._reload()

    @Slot(int, result=int)
    def rowOf(self, contact_id):
        return self._model.row_of(contact_id)

    @Property("QVariantList", notify=changed)
    def letters(self):
        """The list's letters, with the row each starts at (the index beside the list)."""
        out, seen = [], set()
        for i, row in enumerate(self._model._rows):
            if row[4] not in seen:
                seen.add(row[4])
                out.append({"letter": row[4], "row": i})
        return out

    @Slot(str, result=int)
    def rowForLetter(self, letter):
        """The first row at this letter or after it (a letter typed in the list)."""
        letter = vcard_ascii(letter[:1]).upper()
        for i, row in enumerate(self._model._rows):
            if row[4] >= letter and row[4] != "#":
                return i
        return -1

    @Slot(str, result=int)
    def idForEmail(self, email):
        """A card of my own address books with this address (0: none; « Ajouter aux contacts » in Courrier)."""
        email = (email or "").strip().lower()
        if not email:
            return 0
        rows = self._store.query("SELECT p.id, p.emails FROM contacts p JOIN collections c ON c.id = p.collection_id "
                                 "WHERE c.kind = 'addressbook' AND NOT c.readonly AND lower(p.emails) LIKE ?",
                                 (f"%{email}%",))
        for r in rows:
            if r["id"] not in self._deleting() and email in {e.lower() for e in json.loads(r["emails"] or "[]")}:
                return int(r["id"])
        return 0

    @Slot(str, int, result="QVariantMap")
    def emailOwner(self, email, exclude_id):
        """Another card of mine with this address (the editor says so before a second card is made)."""
        email = (email or "").strip().lower()
        if "@" not in email:
            return {}
        rows = self._store.query("SELECT p.id, p.name, p.emails FROM contacts p JOIN collections c ON c.id = p.collection_id "
                                 "WHERE NOT c.readonly AND lower(p.emails) LIKE ? AND p.id != ?", (f"%{email}%", exclude_id))
        for r in rows:
            if r["id"] not in self._deleting() and email in {e.lower() for e in json.loads(r["emails"] or "[]")}:
                return {"id": r["id"], "name": r["name"]}
        return {}

    @Slot(int, result=int)
    def idAt(self, row):
        return self._model._rows[row][0] if 0 <= row < len(self._model._rows) else 0

    @Slot(int, int, result="QVariantList")
    def idsBetween(self, a, b):
        """The ids of the rows from a to b (Maj+clic)."""
        lo, hi = sorted((max(a, 0), max(b, 0)))
        return [row[0] for row in self._model._rows[lo:hi + 1]]

    @Slot(result="QVariantList")
    def allIds(self):
        return [row[0] for row in self._model._rows]

    # ---- one card -----------------------------------------------------------------------------------
    def _row(self, contact_id):
        rows = self._store.query("SELECT p.*, c.name AS book, c.href AS book_href, c.readonly FROM contacts p "
                                 "JOIN collections c ON c.id = p.collection_id WHERE p.id = ?", (contact_id,))
        return rows[0] if rows else None

    @Slot(int, result="QVariantMap")
    def details(self, contact_id):
        row = self._row(contact_id)
        if row is None or contact_id in self._deleting():
            return {}
        card = vcard.parse(row["vcard"])
        photo_view = card["photo"] if card["photo"].startswith("data:") else ""
        if card["photo"] and not photo_view:
            path = PHOTOS / _photo_name(contact_id, row["vcard"])
            photo_view = path.as_uri() if path.exists() else ""
        card.update({"contactId": contact_id, "bookId": row["collection_id"], "bookName": self._book_name(row["book_href"], row["book"]),
                     "readonly": bool(row["readonly"]), "initials": initials(card["fn"]), "photoView": photo_view,
                     "tint": zlib.crc32(card["fn"].encode()) % 4, "upcoming": self._upcoming(card),
                     "cloudUser": self._cloud_user(card), "primaryEmail": primary(card["emails"]),
                     "birthdayIn": _days_until(card["bday"]), "anniversaryIn": _days_until(card["anniversary"]),
                     "age": _age(card["bday"])})
        return card

    @Slot("QVariantList", result="QVariantList")
    def recentMails(self, emails):
        """The last messages from or to this person in the cache (newest first), to open in Courrier."""
        emails = [str(e).strip().lower() for e in (emails or []) if str(e).strip()]
        if not emails:
            return []
        clause = " OR ".join("lower(m.from_email) = ? OR lower(m.recipients) LIKE ?" for _ in emails)
        args = []
        for e in emails:
            args += [e, f'%"{e}"%']
        try:
            rows = self._store.query(
                f"SELECT m.message_id, m.subject, m.date_ts, m.from_email, m.preview FROM messages m WHERE ({clause}) "
                "AND m.message_id != '' GROUP BY m.message_id ORDER BY m.date_ts DESC LIMIT 5", args)
        except Exception:
            return []
        return [{"messageId": r["message_id"], "subject": r["subject"], "date": int(r["date_ts"]) * 1000,
                 "incoming": r["from_email"].lower() in emails, "preview": r["preview"][:140]} for r in rows]

    @Slot(str)
    def openMail(self, message_id):
        links.open_link(links.mail_url(message_id))

    @Slot("QVariantList", result=str)
    def lastMailText(self, emails):
        """The text of the latest message this person sent that is in the cache (its signature, for Ornis)."""
        emails = [str(e).strip().lower() for e in (emails or []) if str(e).strip()]
        if not emails:
            return ""
        try:
            rows = self._store.query(
                "SELECT b.raw FROM messages m JOIN bodies b ON b.message_id = m.id WHERE lower(m.from_email) IN ("
                + ",".join("?" for _ in emails) + ") ORDER BY m.date_ts DESC LIMIT 3", emails)
        except Exception:
            return ""
        for r in rows:
            try:
                text = mime.read(bytes(r["raw"])).get("text") or ""
            except Exception:
                continue
            text = re.split(r"(?m)^(?:>|(?:Le|On|Am) .{5,80}(?:a écrit|wrote|schrieb)\s*:)", text)[0].strip()
            if text:
                return text[-3000:]               # the end: where the signature is
        return ""

    # ---- accounts of the cloud: Meet with them, « Compte Orneos » on their card -----------------------
    def _cloud_user(self, card):
        """The cloud account of this person: from the card (team members carry CLOUD:uid@server), else
        from their address, asked once to the cloud in the background (exact match only, as Talk does)."""
        account = self._sync._plume.account() if hasattr(self._sync, "_plume") else None
        if not account:
            return ""
        host = urllib.parse.urlsplit(account[0]).hostname or ""
        if "@" in card.get("cloud", ""):
            uid, _, server = card["cloud"].rpartition("@")
            if server.split("/")[0] == host and uid != account[1]:
                return uid
        known = self._store.get("cloud_accounts:" + account[1], {}) or {}
        ask = []
        for item in card["emails"]:
            email = item["value"].strip().lower()
            uid, at = (known.get(email) or ["", 0])[:2]
            if uid:
                return uid if uid != account[1] else ""
            if time.time() - at > LOOKUP_DAYS * 86400:
                ask.append(email)
        if ask:
            self._ask_cloud(account, ask)
        return ""

    def _ask_cloud(self, account, emails):
        emails = [e for e in emails if e not in self._asking]
        if not emails:
            return
        self._asking.update(emails)

        def run():
            found = {}
            for email in emails:
                query = urllib.parse.urlencode({"search": email, "itemType": "call", "itemId": "new",
                                                "shareTypes[]": 0, "limit": 5})
                status, data = cloud.ocs(account[0], account[1], account[2], "/ocs/v2.php/core/autocomplete/get?" + query)
                if status == 0:
                    continue                        # offline: asked again next time
                uid = ""
                people = ((data or {}).get("ocs") or {}).get("data") if isinstance(data, dict) else None
                for person in people if isinstance(people, list) else []:
                    if (person.get("source") or "users") != "users":
                        continue
                    seen = {str(person.get(k) or "").lower() for k in ("id", "subline", "shareWithDisplayNameUnique")}
                    if email in seen:
                        uid = str(person.get("id") or "")
                        break
                found[email] = [uid, int(time.time())]
            self._asking.difference_update(emails)
            if found:
                known = self._store.get("cloud_accounts:" + account[1], {}) or {}
                known.update(found)
                self._store.set("cloud_accounts:" + account[1], known)
                if any(v[0] for v in found.values()):
                    self._cloudFound.emit()
        threading.Thread(target=run, daemon=True).start()

    def _upcoming(self, card):
        """The next three events this person is part of (organizer or guest), within 90 days."""
        emails = [e["value"].lower() for e in card["emails"] if e.get("value")]
        if not emails:
            return []
        now = datetime.now(ical.local_zone())
        end = now + timedelta(days=90)
        clause = " OR ".join("lower(ics) LIKE ?" for _ in emails)
        rows = self._store.query(
            f"SELECT ics FROM events WHERE ({clause}) AND start_ts < ? AND (end_ts IS NULL OR end_ts >= ?)",
            [f"%{e}%" for e in emails] + [int(end.timestamp()), int(now.timestamp())])
        found = []
        for r in rows:
            for item in ical.occurrences(r["ics"], now, end, self._sync.addresses):
                found.append({"title": item["title"], "start": item["start"], "allDay": item["allDay"],
                              "location": item["location"]})
        found.sort(key=lambda i: i["start"])
        return found[:3]

    @Slot(str, result="QVariantList")
    def suggest(self, text):
        """Addresses for an attendee or recipient field: contacts whose name or address starts with text,
        then people written to or heard from recently. One line per address, even when several cards
        (or a card and a message) share it."""
        text = text.strip().lower()
        if len(text) < 1:
            return []
        out, seen = [], set()
        folded = fold(text)

        def add(name, email):
            key = (email or "").strip().lower()
            if not key or key in seen:
                return
            seen.add(key)
            out.append({"name": name or "", "email": email.strip(), "initials": initials(name or email)})
        for r in self._store.query("SELECT name, emails FROM contacts WHERE emails != '[]' AND "
                                   "(sort_key LIKE ? OR fold(name) LIKE ? OR lower(emails) LIKE ?) ORDER BY sort_key LIMIT 30",
                                   (folded + "%", "% " + folded + "%", "%" + text + "%")):
            for email in json.loads(r["emails"]):
                if folded in fold(r["name"]) or text in email.lower():
                    add(r["name"], email)
        if len(out) < 8:
            # people I wrote to (Envoyés), the latest first: a recipient's name or address starting with text
            try:
                sent = self._store.query(
                    "SELECT m.recipients FROM messages m JOIN mail_folders f ON f.id = m.folder_id "
                    "WHERE f.role = 'sent' AND fold(m.recipients) LIKE ? ORDER BY m.date_ts DESC LIMIT 40",
                    ("%" + folded + "%",))
            except Exception:
                sent = []
            for r in sent:
                try:
                    people = json.loads(r["recipients"] or "[]")
                except ValueError:
                    continue
                for person in people if isinstance(people, list) else []:
                    if not isinstance(person, dict):
                        continue
                    name, email = person.get("name") or "", person.get("email") or ""
                    words = fold(name).split()
                    if fold(email).startswith(folded) or any(w.startswith(folded) for w in words) \
                            or fold(name).startswith(folded):
                        add(name, email)
        if len(out) < 8:
            try:
                rows = self._store.query(
                    "SELECT from_name, from_email, MAX(date_ts) AS last FROM messages "
                    "WHERE lower(from_email) LIKE ? OR fold(from_name) LIKE ? OR fold(from_name) LIKE ? "
                    "GROUP BY lower(from_email) ORDER BY last DESC LIMIT 12",
                    (text + "%", folded + "%", "% " + folded + "%"))
            except Exception:
                rows = []
            for r in rows:
                if "noreply" not in r["from_email"].lower() and "no-reply" not in r["from_email"].lower():
                    add(r["from_name"], r["from_email"])
        return out[:8]

    # ---- edits --------------------------------------------------------------------------------------
    @Slot(str, result=str)
    def birthday(self, text):
        """A birthday as typed (31/12/1990, 31.12.1990, 1990-12-31, 31/12) → 1990-12-31 or --12-31;
        "" when empty, "?" when it is not a date."""
        text = text.strip().rstrip(".")
        if not text:
            return ""
        m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", text) or re.fullmatch(r"--(\d{1,2})-?(\d{2})", text)
        if m and len(m.groups()) == 3:
            year, month, day = m.groups()
        elif m:
            year, (month, day) = "", m.groups()
        else:
            m = re.fullmatch(r"(\d{1,2})[./ -](\d{1,2})(?:[./ -](\d{4}))?", text)
            if not m:
                return "?"
            day, month, year = m.group(1), m.group(2), m.group(3) or ""
        try:
            datetime(int(year or 2000), int(month), int(day))
        except ValueError:
            return "?"
        return f"{year}-{int(month):02d}-{int(day):02d}" if year else f"--{int(month):02d}-{int(day):02d}"

    @Slot(str, result=str)
    def birthdayText(self, value):
        """1990-12-31 → 31/12/1990 (31.12.1990 in German), --12-31 → 31/12, to edit."""
        sep = "." if (getattr(getattr(self._sync, "_plume", None), "_lang", "") == "de") else "/"
        if value.startswith("--") and len(value) == 7:
            return f"{value[5:7]}{sep}{value[2:4]}"
        if len(value) == 10:
            return f"{value[8:10]}{sep}{value[5:7]}{sep}{value[:4]}"
        return value

    @Slot(str, result=str)
    def photoFrom(self, path):
        """A picture file → a square JPEG of 256 px as a data: URL for the card ("" if it is not one)."""
        from PySide6.QtCore import QBuffer, QIODevice
        from PySide6.QtGui import QImage, QImageReader
        reader = QImageReader(mime.local_path(path))
        reader.setAutoTransform(True)
        image = reader.read()
        if image.isNull():
            return ""
        side = min(image.width(), image.height())
        image = image.copy((image.width() - side) // 2, (image.height() - side) // 2, side, side)
        image = image.scaled(256, 256, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        image = image.convertToFormat(QImage.Format.Format_RGB32)
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, "JPEG", 85)
        return "data:image/jpeg;base64," + base64.b64encode(bytes(buffer.data())).decode()

    def _write(self, collection_id, href, text, etag, base=None):
        """save_contact, remembering the card as it was (a refusal for a change elsewhere is merged)."""
        if base:
            self._bases[(collection_id, href)] = base
        self._sync.save_contact(collection_id, href, text, etag)

    def merge_conflict(self, client, collection_id, href, mine):
        """The cloud refused my card (changed elsewhere since): both changes in one card, sent again.
        Runs on the sync thread; False when there is nothing to merge with (Sync then restores theirs)."""
        base = self._bases.pop((collection_id, href), None)
        if not base:
            return False
        try:
            found = client.multiget(self._sync._href_of(collection_id), [href], "addressbook")
            if not found:
                return False
            etag, theirs = next(iter(found.values()))
            merged = vcard.merge(base, mine, theirs)
            new_etag = client.put(href, merged, "text/vcard; charset=utf-8", etag or None)
        except DavError:
            return False
        card = vcard.parse(merged)
        from plume_core.sync import sort_key
        self._store.execute(
            "UPDATE contacts SET etag = ?, uid = ?, name = ?, sort_key = ?, org = ?, emails = ?, phones = ?, "
            "categories = ?, vcard = ? WHERE collection_id = ? AND href = ?",
            (new_etag, card["uid"], card["fn"], sort_key(card["fn"]), card["org"],
             json.dumps([e["value"] for e in card["emails"]]), json.dumps([p["value"] for p in card["phones"]]),
             json.dumps(card["categories"]), merged, collection_id, href))
        self._sync.contactsChanged.emit()
        return True

    @Slot("QVariantMap", result=int)
    def save(self, fields):
        fields = {k: (v.toVariant() if hasattr(v, "toVariant") else v) for k, v in dict(fields).items()}
        contact_id = int(fields.pop("contactId", 0) or 0)
        book_id = int(fields.pop("bookId", 0) or 0) or self.defaultBook
        books = {b["id"]: b for b in self._store.query("SELECT * FROM collections WHERE kind = 'addressbook'")}
        target = books.get(book_id)
        if target is None or target["readonly"]:
            return 0
        for key in ("emails", "phones", "addresses", "categories", "related"):
            fields[key] = [dict(x) if not isinstance(x, str) else x for x in (fields.get(key) or [])]
        row = None
        if contact_id:
            found = self._store.query("SELECT p.*, c.readonly FROM contacts p JOIN collections c ON c.id = p.collection_id "
                                      "WHERE p.id = ?", (contact_id,))
            row = found[0] if found else None
        if row is not None:
            # the name as shown (« Dr Jeanne Petit ») stays when the given and family names did not change
            before = vcard.parse(row["vcard"])
            if (fields.get("given", ""), fields.get("family", "")) == (before["given"], before["family"]) and before["fn"]:
                fields["fn"] = before["fn"]
        if row is not None and row["readonly"]:
            # a card of a read-only book (an Orneos account, someone written to): edited into my contacts
            uid, text = vcard.build(fields, row["vcard"], new_uid=True)
            href = target["href"] + uid + ".vcf"
            self._write(target["id"], href, text, "")
        elif row is None:
            uid, text = vcard.build(fields)
            href = target["href"] + uid + ".vcf"
            self._write(target["id"], href, text, "")
        else:
            fields["uid"] = row["uid"]
            _, text = vcard.build(fields, row["vcard"])
            if row["collection_id"] != target["id"]:
                href = target["href"] + (row["uid"] or str(uuid.uuid4())) + ".vcf"
                self._write(target["id"], href, text, "")
                self._sync.delete("contacts", row["collection_id"], row["href"], row["etag"])
            else:
                href = row["href"]
                self._write(row["collection_id"], href, text, row["etag"], base=row["vcard"])
        found = self._store.query("SELECT id FROM contacts WHERE collection_id = ? AND href = ?", (target["id"], href))
        return found[0]["id"] if found else 0

    # ---- deleting, with « Annuler » ------------------------------------------------------------------
    @Slot(int)
    def remove(self, contact_id):
        rows = self._store.query("SELECT * FROM contacts WHERE id = ?", (contact_id,))
        if rows:
            self._sync.delete("contacts", rows[0]["collection_id"], rows[0]["href"], rows[0]["etag"])

    @Slot("QVariantList", result=str)
    def removeLater(self, ids):
        """Gone from the list now, from the cloud after UNDO_MS unless undoRemove(token) comes first.
        Cards of read-only books are left alone."""
        ids = _ids(ids)
        rows = self._store.query("SELECT p.id FROM contacts p JOIN collections c ON c.id = p.collection_id "
                                 "WHERE NOT c.readonly AND p.id IN (" + ",".join("?" for _ in ids) + ")", ids) if ids else []
        ids = [r["id"] for r in rows]
        if not ids:
            return ""
        token = uuid.uuid4().hex
        self._hiddenIds[token] = ids
        self._reload()
        QTimer.singleShot(UNDO_MS, lambda: self._commit(token))
        return token

    @Slot(str)
    def undoRemove(self, token):
        ids = self._hiddenIds.pop(token, None)
        restore = self._undo.pop(token, None)
        if restore:
            collection_id, href, text = restore
            self._write(collection_id, href, text, None)
        if ids is not None or restore:
            self._reload()

    def _commit(self, token):
        ids = self._hiddenIds.pop(token, None)
        self._undo.pop(token, None)
        for contact_id in ids or []:
            self.remove(contact_id)
        if ids:
            self._reload()

    def _flush(self):
        for token in list(self._hiddenIds):
            self._commit(token)

    @Slot("QVariantList", result=int)
    def countWritable(self, ids):
        ids = _ids(ids)
        if not ids:
            return 0
        return self._store.query("SELECT COUNT(*) FROM contacts p JOIN collections c ON c.id = p.collection_id "
                                 "WHERE NOT c.readonly AND p.id IN (" + ",".join("?" for _ in ids) + ")", ids)[0][0]

    # ---- groups (the cards' CATEGORIES) ------------------------------------------------------------
    def _members(self, group):
        rows = self._store.query("SELECT p.*, c.readonly FROM contacts p JOIN collections c ON c.id = p.collection_id "
                                 "WHERE p.categories LIKE ?", ("%" + json.dumps(group)[1:-1] + "%",))
        deleting = self._deleting()
        return [r for r in rows if group in json.loads(r["categories"] or "[]") and r["id"] not in deleting]

    def _rewrite(self, row, change):
        """The card again with its groups changed by change(list) → list (read-only books are left alone)."""
        if row["readonly"]:
            return False
        fields = vcard.parse(row["vcard"])
        groups = change(list(fields.get("categories") or []))
        if groups == fields.get("categories"):
            return False
        fields["categories"] = groups
        fields["uid"] = row["uid"]
        fields.pop("photo", None)
        _, text = vcard.build({"uid": row["uid"], "categories": groups}, row["vcard"])
        self._write(row["collection_id"], row["href"], text, row["etag"], base=row["vcard"])
        return True

    @Slot(int, str, bool)
    def setGroup(self, contact_id, group, on):
        """Add a card to a group (a new one too), or take it out."""
        self.setGroupMany([contact_id], group, on)

    @Slot("QVariantList", str, bool, result=int)
    def setGroupMany(self, ids, group, on):
        group = group.strip()
        ids = _ids(ids)
        if not group or not ids:
            return 0
        rows = self._store.query("SELECT p.*, c.readonly FROM contacts p JOIN collections c ON c.id = p.collection_id "
                                 "WHERE p.id IN (" + ",".join("?" for _ in ids) + ")", ids)
        return sum(self._rewrite(r, lambda groups: (groups + [group] if group not in groups else groups) if on
                                 else [g for g in groups if g != group]) for r in rows)

    @Slot(str, str, result=int)
    def renameGroup(self, old, new):
        """Every card of the group moves to the new name (merged when that group exists)."""
        new = new.strip()
        if not new or new == old:
            return 0
        extra = self._extra_groups()
        if old in extra:
            self._store.set("pref_contact_groups", [new if g == old else g for g in extra])
        changed = sum(self._rewrite(r, lambda groups: list(dict.fromkeys(new if g == old else g for g in groups)))
                      for r in self._members(old))
        if self._group == old:
            self.setFilter(self._query, self._book, new)
        self._reload()
        return changed

    @Slot(str, result=int)
    def deleteGroup(self, group):
        """The group goes; its contacts stay in their address book."""
        self._store.set("pref_contact_groups", [g for g in self._extra_groups() if g != group])
        changed = sum(self._rewrite(r, lambda groups: [g for g in groups if g != group]) for r in self._members(group))
        if self._group == group:
            self.setFilter(self._query, self._book, "")
        self._reload()
        return changed

    @Slot(str, result="QVariantMap")
    def groupInfo(self, group):
        """One address per member (the preferred one, else the first), to write to the whole group;
        and how many members have none."""
        out, without = [], 0
        for r in sorted(self._members(group), key=lambda r: r["sort_key"]):
            email = primary(vcard.parse(r["vcard"])["emails"])
            if not email:
                without += 1
            elif email not in out:
                out.append(email)
        return {"emails": out, "without": without}

    @Slot(str, result="QVariantList")
    def groupEmails(self, group):
        return self.groupInfo(group)["emails"]

    @Slot("QVariantList", result="QVariantList")
    def emailsOf(self, ids):
        out = []
        for contact_id in _ids(ids):
            row = self._row(contact_id)
            email = primary(vcard.parse(row["vcard"])["emails"]) if row else ""
            if email and email not in out:
                out.append(email)
        return out

    # ---- files ----------------------------------------------------------------------------------------
    @Slot(str, result=int)
    @Slot(str, str, result=int)
    @Slot(str, str, int, result=int)
    def exportFile(self, path, group="", contact_id=0):
        """My cards (not the cloud's accounts nor the people written to), the cards of a group, or one card,
        to a .vcf file."""
        if contact_id:
            rows = self._store.query("SELECT vcard FROM contacts WHERE id = ?", (contact_id,))
        elif group:
            rows = sorted(self._members(group), key=lambda r: r["sort_key"])
        else:
            skip = self._deleting()
            rows = [r for r in self._store.query(
                "SELECT p.id, p.vcard, c.href FROM contacts p JOIN collections c ON c.id = p.collection_id ORDER BY p.sort_key")
                if not generated(r["href"]) and r["id"] not in skip]
        return self._write_file(path, rows)

    @Slot(str, "QVariantList", result=int)
    def exportIds(self, path, ids):
        ids = _ids(ids)
        rows = self._store.query("SELECT vcard FROM contacts WHERE id IN (" + ",".join("?" for _ in ids) + ") "
                                 "ORDER BY sort_key", ids) if ids else []
        return self._write_file(path, rows)

    @staticmethod
    def _write_file(path, rows):
        try:
            Path(mime.local_path(path)).write_text("".join(r["vcard"] if r["vcard"].endswith("\n") else r["vcard"] + "\r\n"
                                                               for r in rows), encoding="utf-8")
        except OSError:
            return 0
        return len(rows)

    @Slot(str, result=str)
    def exportNameFor(self, label):
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in label.lower()).strip("-")[:60] or "contacts"
        return f"{safe}-{time.strftime('%Y-%m-%d')}.vcf"

    @Slot(str, result="QVariantMap")
    @Slot(str, int, result="QVariantMap")
    def importFile(self, path, book=0):
        """A .vcf (one or many cards) or a .csv (Google, Outlook) into an address book. Someone already there
        (same UID, or same address or number) is completed instead of added twice.
        Returns {added, updated, same} (all 0 and error when the file could not be read)."""
        book = book or self.defaultBook
        target = self._store.query("SELECT * FROM collections WHERE id = ? AND NOT readonly", (book,))
        result = {"added": 0, "updated": 0, "same": 0, "error": False}
        if not target:
            result["error"] = True
            return result
        target = target[0]
        local = mime.local_path(path)
        try:
            text = contacts_csv.decode(Path(local).read_bytes())
        except OSError:
            result["error"] = True
            return result
        if contacts_csv.is_csv(local, text[:2000]) and "BEGIN:VCARD" not in text[:2000].upper():
            incoming = [(f, None) for f in contacts_csv.parse(text)]
        else:
            incoming = [(vcard.parse(card), card) for card in vcard.split_file(text)]
        if not incoming:
            result["error"] = True
            return result
        mine = self._store.query("SELECT p.*, c.readonly FROM contacts p JOIN collections c ON c.id = p.collection_id "
                                 "WHERE NOT c.readonly")
        by_uid = {r["uid"]: r for r in mine if r["uid"]}
        by_email, by_phone = {}, {}
        for r in mine:
            for e in json.loads(r["emails"] or "[]"):
                by_email.setdefault(e.lower(), r)
            for p in json.loads(r["phones"] or "[]"):
                if len(vcard._digits(p)) >= 6:
                    by_phone.setdefault(vcard._digits(p), r)
        for fields, card in incoming:
            row = by_uid.get(fields.get("uid") or "") or next(
                (by_email[e["value"].lower()] for e in fields.get("emails", []) if e["value"].lower() in by_email), None) \
                or next((by_phone[vcard._digits(p["value"])] for p in fields.get("phones", [])
                         if vcard._digits(p["value"]) in by_phone), None)
            if row is not None:
                merged, changed = vcard.complete(vcard.parse(row["vcard"]), fields)
                if not changed:
                    result["same"] += 1
                    continue
                merged["uid"] = row["uid"]
                _, built = vcard.build(merged, row["vcard"])
                self._write(row["collection_id"], row["href"], built, row["etag"], base=row["vcard"])
                result["updated"] += 1
                continue
            uid = fields.get("uid") or str(uuid.uuid4())
            fields["uid"] = uid
            if card:
                fields.pop("photo", None)
                _, built = vcard.build(fields, card)
            else:
                _, built = vcard.build(fields)
            safe = "".join(ch for ch in uid if ch.isalnum() or ch in "-_.@")[:120] or str(uuid.uuid4())
            self._write(target["id"], target["href"] + safe + ".vcf", built, "")
            by_uid[uid] = {"uid": uid}
            result["added"] += 1
        return result

    @Slot(result=str)
    def exportName(self):
        return f"contacts-orneos-{time.strftime('%Y-%m-%d')}.vcf"

    # ---- duplicates ---------------------------------------------------------------------------------------
    @Property("QVariantList", notify=changed)
    def duplicates(self):
        """Groups of my cards that are surely one person: same address, same number, or same name with
        nothing that tells them apart. Each: {ids, names, reason}."""
        rows = [r for r in self._store.query(
            "SELECT p.id, p.name, p.emails, p.phones, p.sort_key, c.href FROM contacts p "
            "JOIN collections c ON c.id = p.collection_id WHERE NOT c.readonly") if not generated(r["href"])]
        deleting = self._deleting()
        rows = [r for r in rows if r["id"] not in deleting]
        parent = {r["id"]: r["id"] for r in rows}
        reason = {}

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def join(a, b, why):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra
                reason.setdefault(ra, why)
        seen = {}
        for r in rows:
            keys = [("email", e.lower()) for e in json.loads(r["emails"] or "[]")]
            keys += [("phone", vcard._digits(p)) for p in json.loads(r["phones"] or "[]") if len(vcard._digits(p)) >= 8]
            if r["sort_key"] and r["sort_key"] != "~" and " " in r["sort_key"].strip():
                keys.append(("name", r["sort_key"].strip()))
            for key in keys:
                if key in seen:
                    join(seen[key], r["id"], key[0])
                else:
                    seen[key] = r["id"]
        groups = {}
        names = {r["id"]: r["name"] for r in rows}
        for r in rows:
            groups.setdefault(find(r["id"]), []).append(r["id"])
        dismissed = set(self._store.get("pref_contacts_not_duplicates", []) or [])
        out = []
        for root, ids in groups.items():
            key = ",".join(str(i) for i in sorted(ids))
            if len(ids) > 1 and key not in dismissed:
                out.append({"ids": sorted(ids), "names": [names[i] for i in sorted(ids)],
                            "reason": reason.get(root, "name"), "key": key})
        return sorted(out, key=lambda d: fold(d["names"][0]))

    @Slot(str)
    def notDuplicates(self, key):
        """« Ce ne sont pas les mêmes »: this group is not proposed again."""
        kept = list(self._store.get("pref_contacts_not_duplicates", []) or [])
        if key not in kept:
            self._store.set("pref_contacts_not_duplicates", kept + [key])
        self._reload()

    @Slot("QVariantList", result="QVariantMap")
    def mergeIds(self, ids):
        """Several cards of one person into one: the fullest card is kept and completed by the others,
        which go after UNDO_MS. {id, token} (token for undoRemove, which also puts the kept card back)."""
        ids = _ids(ids)
        rows = [r for r in (self._row(i) for i in ids) if r is not None and not r["readonly"]]
        if len(rows) < 2:
            return {}
        rows.sort(key=lambda r: -len(r["vcard"]))
        keep, others = rows[0], rows[1:]
        fields = vcard.parse(keep["vcard"])
        for other in others:
            fields, _ = vcard.complete(fields, vcard.parse(other["vcard"]))
            fields["photo"] = fields["photo"] if fields["photo"] else None
        fields["uid"] = keep["uid"]
        _, text = vcard.build(fields, keep["vcard"])
        self._write(keep["collection_id"], keep["href"], text, keep["etag"], base=keep["vcard"])
        token = uuid.uuid4().hex
        self._hiddenIds[token] = [r["id"] for r in others]
        self._undo[token] = (keep["collection_id"], keep["href"], keep["vcard"])
        self._reload()
        QTimer.singleShot(UNDO_MS, lambda: self._commit(token))
        return {"id": keep["id"], "token": token}

    # ---- address books themselves (made, renamed, deleted, shared: the cloud's CardDAV) -----------------
    def _book_job(self, what, fn):
        def run():
            client = self._sync.client()
            if client is None:
                self.booksDone.emit(what, False)
                return
            ok = True
            try:
                fn(client)
            except DavError:
                ok = False
            try:
                self._sync._sync_all()
            except DavError:
                pass
            self.booksDone.emit(what, ok)
        self._sync._submit(run)

    @Slot(str)
    def createBook(self, name):
        home = (self._store.get("homes") or {}).get("books")
        if name.strip() and home:
            self._book_job("create", lambda client: contacts_books.make(client, home, name.strip()))

    def _book_href(self, book_id):
        rows = self._store.query("SELECT href, shared, readonly FROM collections WHERE id = ? AND kind = 'addressbook'",
                                 (book_id,))
        return rows[0] if rows else None

    @Slot(int, str)
    def renameBook(self, book_id, name):
        row = self._book_href(book_id)
        if row and name.strip() and not generated(row["href"]):
            self._store.execute("UPDATE collections SET name = ? WHERE id = ?", (name.strip(), book_id))
            self._reload()
            self._book_job("rename", lambda client: contacts_books.rename(client, row["href"], name.strip()))

    @Slot(int)
    def deleteBook(self, book_id):
        """Mine only (a shared one is left: the cloud would remove it for its owner). The cloud keeps it in
        its trash bin."""
        row = self._book_href(book_id)
        if not row or row["shared"] or generated(row["href"]) or book_id == self.defaultBook and \
                sum(1 for b in self.books if b["mine"]) < 2:
            return
        if self._book == book_id:
            self.setFilter(self._query, 0, "")
        self._store.execute("DELETE FROM contacts WHERE collection_id = ?", (book_id,))
        self._store.execute("DELETE FROM collections WHERE id = ?", (book_id,))
        self._reload()
        self._book_job("delete", lambda client: client.delete(row["href"]))

    @Slot(int)
    def loadShares(self, book_id):
        row = self._book_href(book_id)
        if not row:
            return

        def run():
            client = self._sync.client()
            try:
                found = contacts_books.shares(client, row["href"]) if client else []
            except (DavError, Exception):
                found = []
            self.sharesRead.emit(book_id, found)
        self._sync._submit(run)

    @Slot(int, str, bool)
    def shareBook(self, book_id, principal, read_only):
        row = self._book_href(book_id)
        if row and principal:
            self._book_job("share", lambda client: (contacts_books.share(client, row["href"], principal, read_only),
                                                    self.sharesRead.emit(book_id, contacts_books.shares(client, row["href"]))))

    @Slot(int, str)
    def unshareBook(self, book_id, principal):
        row = self._book_href(book_id)
        if row and principal:
            self._book_job("unshare", lambda client: (contacts_books.unshare(client, row["href"], principal),
                                                      self.sharesRead.emit(book_id, contacts_books.shares(client, row["href"]))))

    sharees = Signal(str, "QVariantList")

    @Slot(str)
    def findSharees(self, text):
        """Accounts and groups of the cloud for this text (its own autocomplete, exact rules of the cloud)."""
        account = self._sync._plume.account() if hasattr(self._sync, "_plume") else None
        text = text.strip()
        if not account or len(text) < 2:
            self.sharees.emit(text, [])
            return

        def run():
            query = urllib.parse.urlencode([("search", text), ("itemType", "addressbook"), ("itemId", "0"),
                                            ("shareTypes[]", 0), ("shareTypes[]", 1), ("limit", 8)])
            status, data = cloud.ocs(account[0], account[1], account[2], "/ocs/v2.php/core/autocomplete/get?" + query)
            people = ((data or {}).get("ocs") or {}).get("data") if isinstance(data, dict) else None
            out = []
            for person in people if isinstance(people, list) else []:
                source = person.get("source") or "users"
                if source not in ("users", "groups") or str(person.get("id")) == account[1]:
                    continue
                kind = "groups" if source == "groups" else "users"
                out.append({"principal": f"principals/{kind}/{person.get('id')}", "name": person.get("label") or person.get("id"),
                            "detail": person.get("subline") or "", "group": kind == "groups"})
            self.sharees.emit(text, out)
        threading.Thread(target=run, daemon=True).start()


def _ids(value):
    """Ids from QML (a list, or a JS array still wrapped)."""
    if hasattr(value, "toVariant"):
        value = value.toVariant()
    return [int(i) for i in value or []]


def _fetch(url, account):
    status, raw = cloud.dav(account[0], account[1], account[2], url, "GET")
    return raw if status == 200 and isinstance(raw, (bytes, bytearray)) else b""


def _family(card_text):
    m = re.search(r"(?m)^N(?:;[^:\r\n]*)?:([^;\r\n]*)", card_text)
    return vcard._unescape(m.group(1)).strip() if m else ""


def _days_until(value):
    """Days to the next occurrence of a yearly date (1990-12-31 or --12-31); -1 without one."""
    if not value:
        return -1
    try:
        month, day = (int(value[2:4]), int(value[5:7])) if value.startswith("--") else (int(value[5:7]), int(value[8:10]))
        today = datetime.now().date()
        for year in (today.year, today.year + 1):
            try:
                when = today.replace(year=year, month=month, day=day)
            except ValueError:
                when = today.replace(year=year, month=3, day=1)       # 29 February, in a common year
            if when >= today:
                return (when - today).days
    except (ValueError, IndexError):
        pass
    return -1


def _age(value):
    """The age at the next birthday (-1 when the year is not known)."""
    if not value or value.startswith("--"):
        return -1
    try:
        born = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return -1
    days = _days_until(value)
    return (datetime.now().date() + timedelta(days=days)).year - born.year if days >= 0 else -1
