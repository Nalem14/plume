"""Links between the things of the account, as macOS links them: a mail, a note, a task or a photo dragged into
a note or onto a task becomes a link with its title, and a click opens it in its own app.

The addresses work beyond Orneos OS when they can: a note or a task is linked by its address in the cloud
(the cloud's Notes and Tasks open it on the web, on a phone), a photo by its file in the cloud (/f/<id>), a mail
by its Message-ID (orneos://mail/…,
Plume finds it in any mailbox). orneos:// is handled by /usr/libexec/orneos-link (eu.orneos.link.desktop);
the native apps send their own clicks there too, so a cloud address of a note opens in Notes, not the browser.

Dragged or copied, a link travels as MIME (JSON [{url, title, kind}]) beside text/plain (its address).
Pure Python; reading the titles opens the other apps' caches read-only (nothing is written there).
"""
import json
import re
import sqlite3
import sys
import urllib.parse

import system

MIME = "application/x-orneos-link"
KINDS = ("mail", "note", "task", "photo", "meet")
ICONS = {"mail": "mail", "note": "note", "task": "done", "photo": "image", "meet": "video"}
NOTE_PATH = re.compile(r"^https?://[^/]+(?:/index\.php)?/apps/notes/(?:#/)?note/(\d+)")
TASK_PATH = re.compile(r"^https?://[^/]+(?:/index\.php)?/apps/tasks/#/calendars/([^/]+)/tasks/([^/?#]+)")
PHOTO_PATH = re.compile(r"^https?://[^/]+(?:/index\.php)?/f/(\d+)$")
# a conversation of Meet: only our cloud's (another Nextcloud's call opens in the browser)
MEET_PATH = re.compile(r"^https://(?:app\.orneos\.eu|cloud\.bucaille-thommy\.fr)(?:/index\.php)?/call/([a-z0-9]{4,30})"
                       r"(?:[/?#]|$)", re.I)
DATA = system.DATA
CACHE = system.CACHE


# ---- addresses ---------------------------------------------------------------------------------------------
def mail_url(message_id):
    return "orneos://mail/" + urllib.parse.quote(str(message_id).strip().strip("<>"), safe="@.-_")


def note_url(server, rid, key=""):
    """The note in the cloud (its id there), or orneos://note/<key> while it exists only here."""
    return f"{server.rstrip('/')}/apps/notes/note/{int(rid)}" if rid else f"orneos://note/{key}"


def task_url(server, href, uid=""):
    """The task in the cloud's Tasks (its list and file), or orneos://task/<uid> before it reached the cloud."""
    parts = [p for p in str(href or "").split("/") if p]
    if server and len(parts) >= 2 and parts[-1].endswith(".ics"):
        return f"{server.rstrip('/')}/apps/tasks/#/calendars/{parts[-2]}/tasks/{parts[-1]}"
    return "orneos://task/" + urllib.parse.quote(uid, safe="@.-_")


def photo_url(server, fileid):
    """A photo by its file in the cloud: Files opens it on the web, Photos here."""
    return f"{server.rstrip('/')}/f/{int(fileid)}"


def meet_url(server, token):
    """A conversation of Meet by its address in the cloud (Talk opens it on the web, Meet here)."""
    return f"{server.rstrip('/')}/call/{token}"


def parse(url):
    """(kind, ref) of a link to a mail, a note or a task: the Message-ID with its <>, a note's cloud id (or
    its key here), a task's file name in the cloud (or its uid). ("", "") for any other address."""
    url = str(url or "").strip()
    if url.startswith("orneos://"):
        kind, _, ref = url[9:].partition("/")
        ref = urllib.parse.unquote(ref)
        if kind == "mail" and ref:
            return "mail", f"<{ref}>"
        if kind in ("note", "task", "photo", "meet", "call") and ref:
            return kind, ref
        return "", ""
    m = NOTE_PATH.match(url)
    if m:
        return "note", m.group(1)
    m = TASK_PATH.match(url)
    if m:
        return "task", urllib.parse.unquote(m.group(2))
    m = PHOTO_PATH.match(url)
    if m:
        return "photo", m.group(1)
    m = MEET_PATH.match(url)
    if m:
        # a link to one message of it (« Copier le lien du message »): "token#id", Meet opens it there
        message = re.search(r"#message_(\d+)", url)
        return "meet", m.group(1).lower() + ("#" + message.group(1) if message else "")
    return "", ""


def is_link(url):
    return parse(url)[0] != ""


# ---- opening ------------------------------------------------------------------------------------------------
def _qt_open(url):
    """Through Qt when the caller is a Qt app: Qt asks the compositor for an activation token and hands it to
    xdg-open, then orneos-link, then the app (which passes it on to its running window). Without it, KWin keeps
    an app that is already open (Plume) behind: the click seems to do nothing."""
    if "PySide6.QtGui" not in sys.modules:
        return False
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices, QGuiApplication
    return QGuiApplication.instance() is not None and QDesktopServices.openUrl(QUrl(url))


def open_link(url):
    """In its own app (Plume, Notes, Tâches, Meet); any other address in the browser. True when something opened.
    In Plume, a mail, a note or a task opens in its module of the same window. orneos://call/<token> joins the
    call of a conversation (meeting.join)."""
    kind, ref = parse(url)
    app = {"mail": "mail", "note": "notes", "task": "tasks", "photo": "photos", "meet": "meet", "call": "meet"}.get(kind)
    arg = {"mail": "--message-id=", "meet": "--room=", "call": "--call="}.get(kind, "--show=") + ref
    if app and system.in_process(app):
        return system.launch(app, arg)
    if app and system.has_app(app):
        if _qt_open(mail_url(ref) if kind == "mail" else f"orneos://{kind}/" + urllib.parse.quote(ref, safe="@.-_")):
            return True
        return system.launch(app, arg)
    if str(url).startswith(("https://", "http://", "mailto:")):
        system.open_url(str(url))
        return True
    return False


# ---- what a link is called (the caches of Plume, Notes and Tâches, read-only) ---------------------------------
def _query(path, sql, args):
    if not path.exists():
        return None
    try:
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1)
        db.row_factory = sqlite3.Row
        try:
            return db.execute(sql, args).fetchone()
        finally:
            db.close()
    except sqlite3.Error:
        return None


def describe(url):
    """{url, kind, title, sub} of a link, its title read where the thing lives; title "" when unknown here."""
    kind, ref = parse(url)
    out = {"url": url, "kind": kind, "title": "", "sub": ""}
    if kind == "mail":
        row = _query(CACHE / "plume.db", "SELECT subject, from_name, from_email FROM messages WHERE message_id = ? "
                                         "ORDER BY date_ts DESC LIMIT 1", (ref,))
        if row is not None:
            out.update(title=row["subject"] or "", sub=row["from_name"] or row["from_email"] or "")
    elif kind == "note":
        sql = "SELECT title, content FROM notes WHERE " + ("rid = ?" if ref.isdigit() else "key = ?")
        row = _query(DATA / "notes.db", sql, (int(ref) if ref.isdigit() else ref,))
        if row is not None:
            first = next((l.strip("# ").strip() for l in (row["content"] or "").split("\n") if l.strip()), "")
            out["title"] = first or row["title"] or ""
    elif kind == "photo" and ref.isdigit():
        row = _query(DATA / "photos.db", "SELECT name FROM photos WHERE fileid = ?", (int(ref),))
        if row is not None:
            out["title"] = row["name"] or ""
    elif kind == "meet":
        row = _query(DATA / "meet.db", "SELECT data FROM rooms WHERE token = ?", (ref.partition("#")[0],))
        if row is not None:
            try:
                out["title"] = str(json.loads(row["data"] or "{}").get("displayName") or "")
            except json.JSONDecodeError:
                pass
    elif kind == "task":
        row = _query(DATA / "tasks.db", "SELECT data FROM tasks WHERE uid = ? OR href LIKE ? LIMIT 1", (ref, "%/" + ref))
        if row is not None:
            try:
                out["title"] = str(json.loads(row["data"] or "{}").get("title") or "")
            except json.JSONDecodeError:
                pass
    return out


def _rows(path, sql, args):
    if not path.exists():
        return []
    try:
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1)
        db.row_factory = sqlite3.Row
        try:
            return db.execute(sql, args).fetchall()
        finally:
            db.close()
    except sqlite3.Error:
        return []


def search(query, server="", kinds=KINDS, limit=8):
    """Things to link, for « Lier à… »: notes, tasks, conversations of Meet and recent mails whose title has the words typed (the
    most recent first when nothing is typed). [{url, kind, title, sub}]."""
    words = [w for w in str(query or "").lower().split() if w]
    like = "%" + "%".join(words) + "%" if words else "%"
    out = []
    if "note" in kinds:
        for r in _rows(DATA / "notes.db", "SELECT key, rid, title, category FROM notes WHERE deleted = 0 AND "
                                          "lower(title || ' ' || content) LIKE ? ORDER BY modified DESC LIMIT ?", (like, limit)):
            out.append({"url": note_url(server, r["rid"], r["key"]), "kind": "note", "title": r["title"], "sub": r["category"]})
    if "task" in kinds:
        found = []
        for r in _rows(DATA / "tasks.db", "SELECT uid, href, data FROM tasks WHERE deleted = 0 AND lower(data) LIKE ? "
                                          "ORDER BY rowid DESC LIMIT ?", (like, limit * 3)):
            try:
                data = json.loads(r["data"] or "{}")
            except json.JSONDecodeError:
                continue
            title = str(data.get("title") or "")
            if title and (not words or all(w in title.lower() for w in words)) and not data.get("done"):
                found.append({"url": task_url(server, r["href"], r["uid"]), "kind": "task", "title": title, "sub": ""})
        out += found[:limit]
    if "meet" in kinds and server:
        found = []
        for r in _rows(DATA / "meet.db", "SELECT token, data FROM rooms ORDER BY activity DESC LIMIT 200", ()):
            try:
                data = json.loads(r["data"] or "{}")
            except json.JSONDecodeError:
                continue
            title = str(data.get("displayName") or "")
            if title and int(data.get("type") or 0) != 4 and (not words or all(w in title.lower() for w in words)):
                found.append({"url": meet_url(server, r["token"]), "kind": "meet", "title": title, "sub": ""})
        out += found[:limit]
    if "mail" in kinds:
        seen = set()
        for r in _rows(CACHE / "plume.db", "SELECT message_id, subject, from_name, from_email FROM messages WHERE "
                                           "message_id <> '' AND lower(subject || ' ' || from_name) LIKE ? "
                                           "ORDER BY date_ts DESC LIMIT ?", (like, limit * 2)):
            if r["message_id"] in seen:
                continue
            seen.add(r["message_id"])
            out.append({"url": mail_url(r["message_id"]), "kind": "mail", "title": r["subject"] or "",
                        "sub": r["from_name"] or r["from_email"] or ""})
            if len(seen) >= limit:
                break
    return out


# ---- dragging and copying ------------------------------------------------------------------------------------
def encode(items):
    """The MIME payload of links being dragged or copied: [{url, title, kind}]."""
    return json.dumps([{"url": i["url"], "title": i.get("title") or "", "kind": i.get("kind") or parse(i["url"])[0]}
                       for i in items if i.get("url")], ensure_ascii=False)


def decode(payload):
    """Links from a MIME payload (or a plain address that is one); [] when there are none."""
    text = payload.decode("utf-8", "replace") if isinstance(payload, (bytes, bytearray)) else str(payload or "")
    text = text.strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            items = json.loads(text)
        except json.JSONDecodeError:
            return []
        return [{"url": str(i["url"]), "title": str(i.get("title") or ""), "kind": str(i.get("kind") or parse(i["url"])[0])}
                for i in items if isinstance(i, dict) and i.get("url")]
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if lines and all(is_link(l) for l in lines):
        return [dict(describe(l)) for l in lines]
    return []


def markdown(item):
    """A link written in a note: [title](address), its brackets escaped."""
    title = (item.get("title") or "").replace("[", "(").replace("]", ")").strip() or item["url"]
    return f"[{title}]({item['url']})"
