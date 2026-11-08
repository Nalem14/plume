"""What the Agenda module sees: calendars, occurrences of a range, one event, and the edits.

Occurrences are expanded from the cache on demand (a week is a few dozen objects), so the window never
waits for the network. `revision` moves whenever the cache changes: views read their range again.
"""
import json
import sqlite3
import threading
import time
import urllib.parse
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QObject, QTimer, Property, Signal, Slot

import cloud
import system
from plume_core import ical

FALLBACK_COLORS = ["#002FA7", "#2F7D6D", "#F0A202", "#1A5F7A", "#C8381E", "#6B7A93"]
UNDO_MS = 6000          # a deleted event can come back this long; the cloud only hears of it after


class Agenda(QObject):
    changed = Signal()
    busyChanged = Signal()
    meetCreated = Signal(str)
    replyMail = Signal("QVariantMap")       # an answer to an invitation that Plume mails itself (Mail sends it)
    freeBusyReady = Signal("QVariantMap")   # {key, people: [{email, known, busy: [[from, to] minutes of the day]}]}

    def __init__(self, store, sync, plume):
        super().__init__()
        self._store, self._sync, self._plume = store, sync, plume
        self._revision = 0
        self._hidden = {}               # deletions waiting for their « Annuler »: token → (event, rid, scope, from ts)
        app = QCoreApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._flush_removals)
        sync.calendarsChanged.connect(self._bump)
        sync.busyChanged.connect(self.busyChanged)

    def _bump(self):
        self._revision += 1
        self.changed.emit()

    @Property(int, notify=changed)
    def revision(self):
        return self._revision

    @Property(bool, notify=busyChanged)
    def busy(self):
        return self._sync.busy()

    def _calendars(self):
        rows = self._store.query("SELECT * FROM collections WHERE kind = 'calendar' ORDER BY shared, sort, name")
        return [{
            "id": r["id"], "name": r["name"], "color": self._color(r), "enabled": bool(r["enabled"]),
            "readonly": bool(r["readonly"]), "shared": bool(r["shared"]), "ownerName": r["owner_name"],
            "personal": r["href"].rstrip("/").endswith("/personal"),
            # read-only and mine: a calendar followed from a link (holidays, a club…)
            "followed": bool(r["readonly"]) and not bool(r["shared"]),
        } for r in rows]

    @staticmethod
    def _color(row):
        color = row["color"] or ""
        return color if len(color) == 7 and color.startswith("#") else FALLBACK_COLORS[row["id"] % len(FALLBACK_COLORS)]

    @Property("QVariantList", notify=changed)
    def calendars(self):
        return self._calendars()

    @Property(int, notify=changed)
    def pending(self):
        rows = self._store.query("SELECT COUNT(*) FROM events e JOIN collections c ON c.id = e.collection_id "
                                 "WHERE e.pending = 1 AND c.enabled = 1 AND (e.end_ts IS NULL OR e.end_ts >= ?)",
                                 (int(time.time()),))
        return rows[0][0]

    @Property(int, notify=changed)
    def defaultCalendar(self):
        """The cloud's own "Personnel" calendar when there is one, else the first one of the user's."""
        for cal in self._calendars():
            if cal["personal"] and not cal["readonly"]:
                return cal["id"]
        for cal in self._calendars():
            if not cal["readonly"] and not cal["shared"]:
                return cal["id"]
        for cal in self._calendars():
            if not cal["readonly"]:
                return cal["id"]
        return 0

    @Slot(int, bool)
    def setEnabled(self, calendar_id, enabled):
        self._store.execute("UPDATE collections SET enabled = ? WHERE id = ?", (int(enabled), calendar_id))
        self._bump()

    @Slot()
    def refresh(self):
        self._sync.refresh()

    # ---- the calendars themselves ------------------------------------------------------------------------
    @Slot(str, str)
    def createCalendar(self, name, color):
        if name.strip():
            self._sync.create_calendar(name.strip()[:120], color)

    @Slot(str, str, str)
    def subscribeCalendar(self, url, name, color):
        """A calendar followed from a link (holidays, a club, a school): read-only, kept up to date by the cloud."""
        url = url.strip()
        if url.lower().startswith("webcals://"):
            url = "https://" + url[10:]
        elif url.lower().startswith("webcal://"):
            url = "https://" + url[9:]
        if url.startswith(("https://", "http://")):
            self._sync.create_calendar((name.strip() or urllib.parse.urlsplit(url).netloc)[:120], color, url)

    @Slot(int, str)
    def renameCalendar(self, calendar_id, name):
        if name.strip():
            self._sync.update_calendar(calendar_id, name=name.strip()[:120])

    @Slot(int, str)
    def recolorCalendar(self, calendar_id, color):
        self._sync.update_calendar(calendar_id, color=color)

    @Slot(int, str, str)
    def editCalendar(self, calendar_id, name, color):
        """Name and colour in one change (the calendar's window): two, the sync after the first read the cloud before
        the second was sent, and the colour went back for a moment."""
        name = name.strip()[:120]
        self._sync.update_calendar(calendar_id, name=name or None, color=color or None)

    @Slot(int)
    def deleteCalendar(self, calendar_id):
        if self.defaultCalendar == calendar_id and len([c for c in self._calendars() if not c["readonly"]]) <= 1:
            return                          # the last calendar one can write in stays
        self._sync.delete_calendar(calendar_id)

    @Slot(int, result=int)
    def eventCount(self, calendar_id):
        return self._store.query("SELECT COUNT(*) FROM events WHERE collection_id = ?", (calendar_id,))[0][0]

    # ---- reading ------------------------------------------------------------------------------------
    @Slot(str, int, result="QVariantList")
    def occurrences(self, start_iso, days):
        tz = ical.local_zone()
        start = datetime.fromisoformat(start_iso[:10]).replace(tzinfo=tz)
        end = start + timedelta(days=days)
        rows = self._store.query(
            "SELECT e.id, e.ics, e.collection_id, c.color, c.readonly, c.id AS cid FROM events e "
            "JOIN collections c ON c.id = e.collection_id WHERE c.enabled = 1 AND e.start_ts < ? "
            "AND (e.end_ts IS NULL OR e.end_ts >= ?)", (int(end.timestamp()), int(start.timestamp())))
        found = []
        hidden = list(self._hidden.values())
        for row in rows:
            color = self._color({"color": row["color"], "id": row["cid"]})
            for item in ical.occurrences(row["ics"], start, end, self._sync.addresses):
                if any(h[0] == row["id"] and (h[2] == "all" or (h[2] == "this" and h[1] == item["rid"])
                                              or (h[2] == "future" and item["startTs"] >= h[3])) for h in hidden):
                    continue
                # movable: mine to change (not someone else's invitation, not a read-only calendar)
                mine = not item["organizer"] or item["organizer"] in self._sync.addresses
                item.update({"key": f"{row['id']}:{item['rid']}", "eventId": row["id"], "calendarId": row["collection_id"],
                             "color": color, "readonly": bool(row["readonly"]), "movable": not row["readonly"] and mine})
                found.append(item)
        found.sort(key=lambda i: (not i["allDay"], i["startTs"], -(i["endTs"] - i["startTs"]), i["title"]))
        return found

    @Slot(str, int, result="QVariantList")
    def tasks(self, start_iso, days):
        """Tasks of Tâches due in the range, read in its cache (read-only): shown beside the events, a click opens
        them in Tâches. Done and deleted ones are not."""
        path = system.DATA / "tasks.db"
        if not path.exists():
            return []
        tz = ical.local_zone()
        start = datetime.fromisoformat(start_iso[:10]).replace(tzinfo=tz)
        end = start + timedelta(days=days)
        try:
            db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1)
            db.row_factory = sqlite3.Row
            try:
                rows = db.execute("SELECT t.uid, t.data, l.color, l.name FROM tasks t LEFT JOIN lists l ON l.href = t.list "
                                  "WHERE t.deleted = 0").fetchall()
            finally:
                db.close()
        except sqlite3.Error:
            return []
        found = []
        for row in rows:
            try:
                data = json.loads(row["data"] or "{}")
            except json.JSONDecodeError:
                continue
            due = int(data.get("due_ts") or 0)
            if not due or data.get("done") or data.get("cancelled") or not (start.timestamp() <= due < end.timestamp()):
                continue
            when = datetime.fromtimestamp(due, tz)
            all_day = bool(data.get("all_day"))
            day = when.replace(hour=0, minute=0, second=0, microsecond=0)
            found.append({
                "key": "task:" + row["uid"], "task": True, "uid": row["uid"], "eventId": 0, "rid": "",
                "title": data.get("title") or "", "location": "", "listName": row["name"] or "",
                "start": day.isoformat(), "end": (day + timedelta(days=1)).isoformat(),
                "startTs": day.timestamp(), "endTs": (day + timedelta(days=1)).timestamp(),
                "allDay": True, "time": "" if all_day else when.strftime("%H:%M"), "dueTs": due,
                "color": row["color"] if row["color"] and len(row["color"]) >= 7 else "#6B7A93",
                "recurring": False, "myStatus": "", "meet": "", "meetName": "", "readonly": True, "movable": False,
                "flagged": bool(data.get("flagged")),
            })
        found.sort(key=lambda t: (t["startTs"], t["time"] or "99", t["title"]))
        return found

    @Slot(str)
    def openTask(self, uid):
        if not system.launch("tasks", "--show=" + uid):
            self._plume.toast.emit(self._plume.t["app_missing"])

    @Slot(str, result="QVariantList")
    def search(self, text):
        """Events whose title, place, notes or guests hold every word: a year back, two years ahead, the next
        ones first then the past ones (most recent first)."""
        words = [w for w in text.lower().split() if w]
        if not words:
            return []
        tz = ical.local_zone()
        now = datetime.now(tz)
        start, end = now - timedelta(days=365), now + timedelta(days=730)
        where = " AND ".join(["lower(e.ics) LIKE ?"] * len(words))
        rows = self._store.query(
            "SELECT e.id, e.ics, e.collection_id, c.color, c.readonly, c.id AS cid FROM events e "
            f"JOIN collections c ON c.id = e.collection_id WHERE c.enabled = 1 AND {where} LIMIT 300",
            tuple(f"%{w}%" for w in words))
        found = []
        for row in rows:
            color = self._color({"color": row["color"], "id": row["cid"]})
            info = ical.details(row["ics"], "", self._sync.addresses)
            haystack = " ".join([info.get("title", ""), info.get("location", ""), info.get("description", "")]
                                + [a.get("name", "") + " " + a["email"] for a in info.get("attendees", [])]).lower()
            if not all(w in haystack for w in words):
                continue
            for item in ical.occurrences(row["ics"], start, end, self._sync.addresses)[:60]:
                item.update({"key": f"{row['id']}:{item['rid']}", "eventId": row["id"], "calendarId": row["collection_id"],
                             "color": color, "readonly": bool(row["readonly"]), "movable": False})
                found.append(item)
        stamp = now.timestamp()
        upcoming = sorted((i for i in found if i["endTs"] >= stamp), key=lambda i: i["startTs"])
        past = sorted((i for i in found if i["endTs"] < stamp), key=lambda i: -i["startTs"])
        return (upcoming + past)[:200]

    @Slot(int, str, result="QVariantMap")
    def details(self, event_id, rid):
        rows = self._store.query("SELECT e.ics, e.collection_id, c.name, c.color, c.readonly, c.id AS cid "
                                 "FROM events e JOIN collections c ON c.id = e.collection_id WHERE e.id = ?", (event_id,))
        if not rows:
            return {}
        row = rows[0]
        info = ical.details(row["ics"], rid, self._sync.addresses)
        info.update({"eventId": event_id, "calendarId": row["collection_id"], "calendarName": row["name"],
                     "color": self._color({"color": row["color"], "id": row["cid"]}), "readonly": bool(row["readonly"]),
                     "canRespond": info.get("myStatus", "") != "" and info.get("organizer", "") not in self._sync.addresses})
        return info

    @Slot(str, result="QVariantList")
    def invitations(self, kind):
        """Invitations from someone else: "new" (no answer yet, not over) or "history" (answered, from
        30 days ago on). Recurring ones are dated by their next occurrence."""
        tz = ical.local_zone()
        now = datetime.now(tz)
        since = now - timedelta(days=30) if kind == "history" else now
        rows = self._store.query(
            "SELECT e.id, e.ics, c.name, c.color, c.id AS cid FROM events e JOIN collections c ON c.id = e.collection_id "
            "WHERE c.enabled = 1 AND e.ics LIKE '%ATTENDEE%' AND (e.end_ts IS NULL OR e.end_ts >= ?)",
            (int(since.timestamp()),))
        found = []
        for row in rows:
            info = ical.details(row["ics"], "", self._sync.addresses)
            status = info.get("myStatus", "")
            if not status or info.get("organizer", "") in self._sync.addresses:
                continue
            if (kind == "new") != (status == "NEEDS-ACTION"):
                continue
            start, all_day, rid = info["start"], info["allDay"], ""
            if info.get("recurring"):
                upcoming = ical.occurrences(row["ics"], since, now + timedelta(days=400), self._sync.addresses)
                if not upcoming:
                    continue
                first = min(upcoming, key=lambda o: o["startTs"])
                start, all_day, rid = first["start"], first["allDay"], first["rid"]
            found.append({
                "eventId": row["id"], "rid": rid, "title": info["title"], "location": info["location"],
                "start": start, "allDay": all_day, "status": status, "recurring": info.get("recurring", False),
                "organizer": info.get("organizerName") or info.get("organizer", ""),
                "organizerEmail": info.get("organizer", ""),
                "calendarId": row["cid"], "calendarName": row["name"],
                "color": self._color({"color": row["color"], "id": row["cid"]}),
            })
        found.sort(key=lambda i: i["start"], reverse=(kind == "history"))
        return found

    # ---- writing ------------------------------------------------------------------------------------
    def _me(self):
        profile = self._plume.profile
        email = profile.get("email", "")
        return {"email": email, "name": profile.get("name", "")}

    def _event(self, event_id):
        rows = self._store.query("SELECT * FROM events WHERE id = ?", (event_id,))
        return rows[0] if rows else None

    def _collection(self, collection_id):
        rows = self._store.query("SELECT * FROM collections WHERE id = ?", (collection_id,))
        return rows[0] if rows else None

    @Slot("QVariantMap", result=bool)
    def save(self, fields):
        """Create (eventId 0) or edit an event. fields: the editor's values, plus rid and scope."""
        fields = dict(fields)
        event_id = int(fields.pop("eventId", 0) or 0)
        target = self._collection(int(fields.pop("calendarId", 0) or 0) or self.defaultCalendar)
        rid, scope = fields.pop("rid", ""), fields.pop("scope", "all")
        if target is None or target["readonly"]:
            return False
        if "attendees" in fields:
            fields["attendees"] = [str(a) for a in fields["attendees"]]
        if "alarms" in fields:
            fields["alarms"] = [str(a) for a in fields["alarms"]]
        if isinstance(fields.get("repeat"), dict):
            fields["repeat"] = dict(fields["repeat"])
            fields["repeat"]["byday"] = [str(d) for d in fields["repeat"].get("byday") or []]
        if not event_id:
            uid, ics = ical.new_event(fields, self._me())
            return self._sync.save_event(target["id"], target["href"] + uid + ".ics", ics, "")
        row = self._event(event_id)
        if row is None:
            return False
        if rid and scope == "future":
            split = ical.split_series(row["ics"], rid, fields, self._me())
            if split is not None:
                old, uid, ics = split
                self._sync.save_event(row["collection_id"], row["href"], old, row["etag"])
                return self._sync.save_event(target["id"], target["href"] + uid + ".ics", ics, "")
            scope = "all"                   # the first occurrence: the whole series
        ics = ical.update_event(row["ics"], fields, rid, scope, self._me())
        if row["collection_id"] != target["id"]:
            # Another calendar: the object moves first, then the change is written there
            href = self._move(row, target)
            return self._sync.save_event(target["id"], href, ics, None)
        return self._sync.save_event(row["collection_id"], row["href"], ics, row["etag"])

    def _move(self, row, target):
        href = target["href"] + row["href"].rstrip("/").rsplit("/", 1)[-1]
        self._sync.move_event(row["collection_id"], row["href"], target["id"], href)
        return href

    @Slot(int, int)
    def moveEvent(self, event_id, calendar_id):
        """Into another calendar, as it is (an invitation too: the organizer is told nothing)."""
        row, target = self._event(event_id), self._collection(calendar_id)
        if row is not None and target is not None and not target["readonly"] and row["collection_id"] != target["id"]:
            self._move(row, target)

    @Slot(int, str, str)
    def remove(self, event_id, rid, scope):
        row = self._event(event_id)
        if row is None:
            return
        if rid and scope == "this":
            self._sync.save_event(row["collection_id"], row["href"], ical.delete_occurrence(row["ics"], rid), row["etag"])
        elif rid and scope == "future" and (ended := ical.end_series(row["ics"], rid)) is not None:
            self._sync.save_event(row["collection_id"], row["href"], ended, row["etag"])
        else:
            self._sync.delete("events", row["collection_id"], row["href"], row["etag"])

    @Slot(int, str, str, str, result=str)
    def removeLater(self, event_id, rid, scope, start_iso):
        """Gone from the views now, from the cloud after UNDO_MS unless undoRemove(token) comes first."""
        token = uuid.uuid4().hex
        try:
            since = datetime.fromisoformat(start_iso).timestamp() if start_iso else 0
        except ValueError:
            since = 0
        self._hidden[token] = (event_id, rid, scope, since)
        self._bump()
        QTimer.singleShot(UNDO_MS, lambda: self._commit_removal(token))
        return token

    @Slot(str)
    def undoRemove(self, token):
        if self._hidden.pop(token, None) is not None:
            self._bump()

    def _commit_removal(self, token):
        entry = self._hidden.pop(token, None)
        if entry is not None:
            self.remove(entry[0], entry[1], entry[2])
            self._bump()

    def _flush_removals(self):
        for token in list(self._hidden):
            self._commit_removal(token)

    @Slot(int, str)
    def respond(self, event_id, status):
        row = self._event(event_id)
        if row is not None and status in ("ACCEPTED", "TENTATIVE", "DECLINED"):
            # etag None: the one known when the write leaves (an invitation just added may still wait for it)
            self._sync.save_event(row["collection_id"], row["href"],
                                  ical.set_status(row["ics"], self._sync.addresses, status), None)
            if ical.client_scheduled(row["ics"]):
                self._reply_by_mail(row["ics"], status)

    # ---- invitations received by mail ------------------------------------------------------------------
    # An invitation sent to an address the cloud knows as mine is answered by the cloud (its scheduling
    # mails the organizer when my answer changes). One sent to another mailbox of Plume (Gmail…) is kept
    # with SCHEDULE-AGENT=CLIENT and Plume mails the answer itself, from that mailbox.
    def _by_uid(self, uid):
        rows = self._store.query("SELECT * FROM events WHERE uid = ? ORDER BY id LIMIT 1", (uid,)) if uid else []
        return rows[0] if rows else None

    def _my_address(self, info):
        mine = self._sync.addresses
        return next((a["email"] for a in info.get("attendees", []) if a["email"] in mine), "")

    def _keep(self, ics, info, status=""):
        """The invitation into the default calendar (or over the copy already there); its event id."""
        address = self._my_address(info)
        client = bool(address) and address not in self._sync.server_addresses()
        stored = ical.stored_copy(ics, client)
        row = self._by_uid(info["uid"])
        if row is not None:
            self._sync.save_event(row["collection_id"], row["href"], stored, None)
        else:
            target = self._collection(self.defaultCalendar)
            if target is None or target["readonly"]:
                return 0
            safe = "".join(ch for ch in info["uid"] if ch.isalnum() or ch in "-_.@")[:120] or str(uuid.uuid4())
            if not self._sync.save_event(target["id"], target["href"] + safe + ".ics", stored, ""):
                return 0
        row = self._by_uid(info["uid"])
        if row is not None and status:
            self.respond(row["id"], status)
        return row["id"] if row is not None else 0

    @Slot(str)
    def receiveInvitation(self, ics):
        """A mail brought an invitation: it waits in the calendar for an answer (Invitations), like on a
        phone. A newer version of one already there (SEQUENCE) replaces it; a past one is left alone."""
        info = ical.invitation(ics, self._sync.addresses)
        if not info or info["method"] not in ("REQUEST", "ADD") or not info["myStatus"] \
                or info["organizer"] in self._sync.addresses:
            return
        if not info["recurring"] and info["end"] and datetime.fromisoformat(info["end"]) < datetime.now(ical.local_zone()):
            return
        row = self._by_uid(info["uid"])
        if row is None or info["sequence"] > ical.sequence(row["ics"]):
            self._keep(ics, info)

    @Slot(str, result="QVariantMap")
    def invitation(self, ics):
        """The invitation card of a mail: the event, and what the calendar knows of it (added, my answer)."""
        info = ical.invitation(ics, self._sync.addresses)
        if not info:
            return {}
        row = self._by_uid(info["uid"])
        stored = ical.details(row["ics"], "", self._sync.addresses) if row is not None else {}
        info.update({
            "eventId": row["id"] if row is not None else 0,
            "status": stored.get("myStatus", "") if row is not None else info.get("myStatus", ""),
            "outdated": row is not None and info["method"] == "REQUEST" and info["sequence"] < ical.sequence(row["ics"]),
            "canRespond": info["method"] in ("REQUEST", "ADD") and bool(info.get("myStatus"))
                          and info.get("organizer", "") not in self._sync.addresses,
            "mine": info.get("organizer", "") in self._sync.addresses,
        })
        return info

    @Slot(str, str)
    def answerInvitation(self, ics, status):
        """Accept, maybe or decline from the mail: the event goes to the calendar first if needed."""
        info = ical.invitation(ics, self._sync.addresses)
        if not info or status not in ("ACCEPTED", "TENTATIVE", "DECLINED"):
            return
        row = self._by_uid(info["uid"])
        if row is None:
            self._keep(ics, info, status)
        else:
            self.respond(row["id"], status)

    @Slot(str, result=int)
    def addInvitation(self, ics):
        """« Add to calendar » for an event I am not asked to answer (sent for information)."""
        info = ical.invitation(ics, self._sync.addresses)
        if not info:
            return 0
        row = self._by_uid(info["uid"])
        return row["id"] if row is not None else self._keep(ics, info)

    @Slot(str)
    def removeInvitation(self, ics):
        """A cancelled event leaves the calendar (from the cancellation mail)."""
        info = ical.invitation(ics, self._sync.addresses)
        row = self._by_uid(info.get("uid", "")) if info else None
        if row is not None:
            self._sync.delete("events", row["collection_id"], row["href"], row["etag"])

    def _reply_by_mail(self, ics, status):
        info = ical.details(ics, "", self._sync.addresses)
        address = self._my_address(info)
        if not address or not info.get("organizer"):
            return
        t = self._plume.t
        title = info.get("title") or t["untitled"]
        subject = t["invite_subject_" + status].replace("%1", title)
        name = self._me().get("name", "")
        self.replyMail.emit({
            "ics": ical.reply(ics, address, status, name), "from": address, "subject": subject,
            "to": f'{info.get("organizerName") or ""} <{info["organizer"]}>'.strip(),
            "text": t["invite_text_" + status].replace("%1", name or address).replace("%2", title),
        })

    @Slot(str)
    def createMeet(self, title):
        """A public Talk room for the event; meetCreated gives its link ("" when the cloud said no)."""
        account = self._plume.account()
        if account is None:
            self.meetCreated.emit("")
            return

        def run():
            _, body = cloud.ocs(*account, "/ocs/v2.php/apps/spreed/api/v4/room", "POST",
                                {"roomType": 3, "roomName": (title or "Orneos Meet")[:250]})
            token = ((body.get("ocs") or {}).get("data") or {}).get("token") if isinstance(body, dict) else None
            self.meetCreated.emit(f"{account[0]}/call/{token}" if token else "")
        threading.Thread(target=run, daemon=True).start()

    # ---- to Notes and Tâches (their own apps, or their modules in Plume) ------------------------------------
    def _summary(self, event_id, rid):
        info = self.details(event_id, rid)
        if not info:
            return None, []
        t = self._plume.t
        tz = ical.local_zone()
        start = datetime.fromisoformat(info["start"]).astimezone(tz) if info.get("start") else None
        lines = []
        if start is not None:
            lines.append(start.strftime("%d/%m/%Y") + ("" if info["allDay"] else " · " + start.strftime("%H:%M")
                         + " – " + datetime.fromisoformat(info["end"]).astimezone(tz).strftime("%H:%M")))
        if info.get("location"):
            lines.append(t["location"] + " : " + info["location"])
        if info.get("meet"):
            lines.append(info["meet"])
        guests = [a.get("name") or a["email"] for a in info.get("attendees") or []]
        if guests:
            lines.append(t["guests"] + " : " + ", ".join(guests))
        return info, lines

    @Slot(int, str, result=bool)
    def toNotes(self, event_id, rid):
        """A note for the event (title, when, where, guests, its description): to prepare it or take minutes."""
        info, lines = self._summary(event_id, rid)
        if info is None or not system.has_app("notes"):
            return False
        title = info.get("title") or self._plume.t["untitled"]
        body = "# " + title + "\n\n" + "\n".join("- " + line for line in lines)
        if info.get("description"):
            body += "\n\n" + info["description"].strip()
        folder = system.CACHE / "plume-notes"
        folder.mkdir(parents=True, exist_ok=True)
        name = "".join(ch for ch in title if ch not in '/\\:*?"<>|').strip()[:80] or "Agenda"
        path = folder / f"{name}.md"
        path.write_text(body.strip() + "\n", encoding="utf-8")
        return system.launch("notes", "--files", str(path))

    @Slot(int, str, result=bool)
    def toTasks(self, event_id, rid):
        """A task due when the event starts, its details in the notes."""
        info, lines = self._summary(event_id, rid)
        if info is None or not system.has_app("tasks"):
            return False
        item = {"title": info.get("title") or self._plume.t["untitled"], "notes": "\n".join(lines)}
        if info.get("start") and not info.get("allDay"):
            item["due"] = datetime.fromisoformat(info["start"]).astimezone(ical.local_zone()).strftime("%Y-%m-%dT%H:%M")
        elif info.get("start"):
            item["due"] = info["start"][:10]
        return system.launch("tasks", "--add-json", json.dumps([item]))

    # ---- reminders where Plume shows them itself (Windows, macOS, Linux without Orneos OS) -------------
    # On Orneos OS the cloud's own reminders reach Plasma through orneos-notify: Plume stays quiet there.
    def start_reminders(self):
        self._fired = list(self._store.get("cal_reminded", []) or [])
        self._reminder_timer = QTimer(self)
        self._reminder_timer.setInterval(30000)
        self._reminder_timer.timeout.connect(self._check_reminders)
        self._reminder_timer.start()
        QTimer.singleShot(4000, self._check_reminders)

    def _check_reminders(self):
        tz = ical.local_zone()
        now = datetime.now(tz)
        stamp = now.timestamp()
        due = []
        for occ in self.occurrences((now - timedelta(days=1)).date().isoformat(), 9):
            if occ.get("myStatus") == "DECLINED":
                continue
            for minutes in occ.get("alarms") or []:
                when = occ["startTs"] - minutes * 60
                key = f"{occ['key']}:{minutes}"
                # a reminder missed while Plume was closed still comes for 10 minutes, never later
                if stamp - 600 <= when <= stamp and key not in self._fired:
                    due.append((occ, key))
        if not due:
            return
        for occ, key in due:
            self._fired.append(key)
            self._notify(occ)
        self._fired = self._fired[-400:]
        self._store.set("cal_reminded", self._fired)

    def _notify(self, occ):
        t = self._plume.t
        tz = ical.local_zone()
        start = datetime.fromisoformat(occ["start"]).astimezone(tz)
        today = datetime.now(tz).date()
        day = t["today"] if start.date() == today else t["tomorrow"] if start.date() == today + timedelta(days=1) \
            else start.strftime("%d/%m")
        if occ["allDay"]:
            when = day
        elif start.date() == today:
            when = t["today_at"].replace("%1", start.strftime("%H:%M"))
        elif start.date() == today + timedelta(days=1):
            when = t["tomorrow_at"].replace("%1", start.strftime("%H:%M"))
        else:
            when = t["day_at"].replace("%1", day).replace("%2", start.strftime("%H:%M"))
        body = " · ".join(x for x in (when, occ.get("location") or "", occ.get("meetName") and t["join_on"].replace("%1", occ["meetName"]) or "") if x)
        value = f"{occ['eventId']}|{occ['start']}"
        system.notify(occ["title"] or t["untitled"], body,
                      lambda: (self._plume.handle_args(["--calendar", "--event=" + value]), self._plume.raiseRequested.emit()))

    @Slot(str, result=int)
    def importFile(self, path):
        """Events of an .ics file into the default calendar; returns how many were added."""
        target = self._collection(self.defaultCalendar)
        if target is None:
            return 0
        try:
            local = urllib.parse.unquote(path[7:]) if path.startswith("file://") else path
            text = Path(local).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return 0
        cal = ical.parse(text)
        if cal is None:
            return 0
        by_uid = {}
        for event in cal.walk("VEVENT"):
            by_uid.setdefault(str(event.get("UID") or uuid.uuid4()), []).append(event)
        zones = [z for z in cal.walk("VTIMEZONE")]
        added = 0
        for uid, events in by_uid.items():
            out = ical.Calendar()
            out.add("PRODID", ical.PRODID)
            out.add("VERSION", "2.0")
            for zone in zones:
                out.add_component(zone)
            for event in events:
                event.pop("METHOD", None)
                out.add_component(event)
            safe = "".join(ch for ch in uid if ch.isalnum() or ch in "-_.@")[:120] or str(uuid.uuid4())
            if self._sync.save_event(target["id"], target["href"] + safe + ".ics", out.to_ical().decode(), ""):
                added += 1
        return added

    @Slot(str, "QVariantList", result=str)
    def freeBusy(self, day, emails):
        """When the guests of the cloud are busy on this day (local midnight to midnight), in the background:
        freeBusyReady comes with the returned key. Guests outside the cloud come back as unknown."""
        emails = sorted({str(e).strip().lower() for e in emails if "@" in str(e)})
        key = day + "|" + ",".join(emails)
        client = self._sync.client()
        mine = sorted(a for a in self._sync._addresses if "@" in a)
        if not emails or client is None or not mine:
            return ""
        zone = ical.local_zone()
        start = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=zone)
        end = start + timedelta(days=1)

        def minutes(stamp):
            when = datetime.strptime(stamp[:16].rstrip("Z"), "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc).astimezone(zone)
            return max(0, min(1440, round((when - start).total_seconds() / 60)))

        def run():
            found = None
            for organizer in mine:
                try:
                    found = client.freebusy(organizer, emails, start.astimezone(timezone.utc), end.astimezone(timezone.utc))
                    break
                except Exception:                    # not this address of mine, offline, a server without scheduling
                    continue
            people = []
            for email in emails:
                busy = (found or {}).get(email)
                people.append({"email": email, "known": busy is not None,
                               "busy": [[minutes(a), minutes(b)] for a, b in busy or [] if len(a) >= 15 and len(b) >= 15]})
            self.freeBusyReady.emit({"key": key, "people": people if found is not None else []})
        threading.Thread(target=run, daemon=True).start()
        return key
