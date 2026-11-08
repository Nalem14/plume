"""What the Mail module sees: the mailboxes (Orneos, with its identities and signature from the cloud's Mail
app, and the external ones added in the settings), folders with unread counts, the list of the selected
folder (one line per conversation), the opened message or conversation, and every action.

Each mailbox has one worker thread that owns its IMAP session (commands keep their order, the window never
waits) and a second connection in IDLE on its inbox, so new mail shows up at once. The cache stays light:
the latest 300 messages per folder (more on demand) and the last bodies opened. Writes are optimistic, like
the calendar: the window changes first, the server follows.
"""
import base64
import datetime
import imaplib
import json
import os
import re
import shutil
import smtplib
import socket
import ssl
import threading
import time
import urllib.parse
import urllib.request
import uuid
import zlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import QAbstractListModel, QByteArray, QMimeData, QModelIndex, QObject, Property, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QGuiApplication, QImage

import cloud
import system
import links
from dragguard import DragGuard
from qmlvalue import js_property
from plume_core import autoconfig, ical, imap, mailqueue, mime, oauth, richtext, secrets
from plume_core.app import initials
from plume_core.store import StaleMailAccount

LATEST = 300
PAGE = 200
BODIES = 300
INVITES_DAYS = 60                   # invitations older than this are not added on their own (only from the card)
INVITES_MAX = 20                    # at most this many invitations read per sync (a first sync brings 300 mails)
UNDO_MS = 6000
READ_IDLE = 240                     # seconds after which the session that opens messages is made again (_job)
THREAD_AT_ONCE = 4                  # from this many other messages, the opened one shows before them (open)
ORNEOS = "orneos"
ROLE_ORDER = ["inbox", "flagged", "drafts", "sent", "archive", "snoozed", "junk", "trash"]
# Exchange (Outlook.com, Microsoft 365) lists its own folders over IMAP: Outlook's notes, the outbox of its app and
# "Sync Issues" with its subfolders; no mail of the user there, Outlook's web page does not show them either
EXCHANGE_HOSTS = ("office365.com", "outlook.com")
EXCHANGE_HIDDEN = {"notes", "outbox", "boîte d'envoi", "sync issues", "problèmes de synchronisation", "notizen",
                   "postausgang", "synchronisierungsprobleme"}
TAG_FOLDER = -10                                # virtual folders -11 … -15: the messages with tag 1 … 5
ROLES = ["messageId", "uid", "fromName", "fromEmail", "initials", "subject", "preview", "date", "seen",
         "flagged", "answered", "attachments", "tint", "folderId", "section", "count", "boxLabel", "tags", "box", "where"]
DOWNLOADS = system.CACHE / "plume-attachments"
MESSAGES_MIME = "application/x-plume-messages"  # lines dragged onto a folder of the list (their ids)
OUTBOX = -3                                     # virtual folder: the messages waiting to be sent
OUTBOX_ROW = -1000                              # its lines: -1000, -1001… (not messages of the cache)
RETRY_MS = 30 * 1000                            # what is queued tries again this often while it waits
RECOVERY = system.DATA / "plume-composing.json" # the message being written, kept while it is written
SNOOZED = system.DATA / "plume-snoozed.json"     # messages put away until a time: [{box, mid, until, subject}]
TEMPLATES = system.DATA / "plume-templates.json" # answers written once, used again: [{name, subject, html, text}]
SNOOZE_FOLDER = "Snoozed"                       # the folder they wait in (the cloud's Mail app uses the same name)
# a send refused for good (the address, the size, the sign-in): said, and the message comes back to the composer;
# anything else (no network, the server busy: 4xx) waits in the outbox and leaves when the server answers
PERMANENT_SMTP = (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused, smtplib.SMTPAuthenticationError)
REF = re.compile(r"<[^<>\s]+>")


def smtp_endpoint():
    """The Orneos SMTP server: (host, port, security)."""
    value = os.environ.get("PLUME_SMTP", "")
    security = "plain" if os.environ.get("PLUME_MAIL_PLAIN") == "1" else "ssl"
    if value:
        host, _, port = value.partition(":")
        return host, int(port or 465), security
    return "mail.orneos.eu", 465, security


# ---- search: words, and filters written in the field (fr, en, de) ---------------------------------------
FILTER_KEYS = {"de": "from", "from": "from", "von": "from", "à": "to", "a": "to", "to": "to", "an": "to",
               "objet": "subject", "subject": "subject", "betreff": "subject", "avant": "before", "before": "before",
               "vor": "before", "après": "after", "apres": "after", "after": "after", "nach": "after",
               "est": "is", "is": "is", "ist": "is", "avec": "has", "has": "has", "mit": "has"}
IS_VALUES = {"non-lu": "unread", "nonlu": "unread", "unread": "unread", "ungelesen": "unread",
             "lu": "read", "read": "read", "gelesen": "read",
             "favori": "flagged", "favoris": "flagged", "starred": "flagged", "flagged": "flagged", "markiert": "flagged"}
HAS_VALUES = {"pj": "attachment", "piece-jointe": "attachment", "pièce-jointe": "attachment", "attachment": "attachment",
              "attachments": "attachment", "anhang": "attachment"}
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


def _day(text):
    """dd/mm/yyyy, dd.mm.yyyy, yyyy-mm-dd (or dd/mm: this year) → local midnight timestamp, or None."""
    m = re.fullmatch(r"(\d{1,2})[/.](\d{1,2})(?:[/.](\d{2,4}))?", text) or None
    try:
        if m:
            year = int(m.group(3) or time.localtime().tm_year)
            year += 2000 if year < 100 else 0
            day = (year, int(m.group(2)), int(m.group(1)))
        else:
            m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
            if not m:
                return None
            day = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return time.mktime(day + (0, 0, 0, 0, 0, -1))
    except (ValueError, OverflowError):
        return None


def parse_query(text):
    """What the search field asks: free words and filters (de:camille objet:"point budget" avec:pj est:non-lu
    avant:01/11/2026). An unknown key stays a word. {"words", "from", "to", "subject", "before", "after",
    "unread", "read", "flagged", "attachment"}."""
    out = {"words": [], "from": [], "to": [], "subject": [], "before": None, "after": None,
           "unread": False, "read": False, "flagged": False, "attachment": False}
    for m in re.finditer(r'(\S+?):"([^"]*)"|"([^"]*)"|(\S+)', text or ""):
        if m.group(3) is not None:
            if m.group(3).strip():
                out["words"].append(m.group(3).strip())
            continue
        key, value = (m.group(1), m.group(2)) if m.group(1) else (m.group(4).partition(":")[0], m.group(4).partition(":")[2])
        kind = FILTER_KEYS.get(key.lower()) if ":" in m.group(0) else None
        value = value.strip()
        if kind in ("from", "to", "subject") and value:
            out[kind].append(value)
        elif kind in ("before", "after") and _day(value) is not None:
            out[kind] = _day(value)
        elif kind == "is" and value.lower() in IS_VALUES:
            out[IS_VALUES[value.lower()]] = True
        elif kind == "has" and value.lower() in HAS_VALUES:
            out["attachment"] = True
        elif m.group(0).strip():
            out["words"].append(m.group(0).strip().strip('"'))
    return out


def imap_criteria(q):
    """The server's side of a search: everything it can check (attachments are checked here)."""
    out = [("TEXT", w) for w in q["words"]] + [("FROM", v) for v in q["from"]] + [("TO", v) for v in q["to"]] \
        + [("SUBJECT", v) for v in q["subject"]]
    for key, flag in (("unread", "UNSEEN"), ("read", "SEEN"), ("flagged", "FLAGGED")):
        if q[key]:
            out.append((flag, None))
    for key, word in (("before", "BEFORE"), ("after", "SINCE")):
        if q[key] is not None:
            t = time.localtime(q[key])
            out.append((word, f"{t.tm_mday:02d}-{MONTHS[t.tm_mon - 1]}-{t.tm_year}"))
    return out


class Box:
    """One mailbox: the Orneos one, or an external one (its own servers, login and password, or signed in with
    Google or Microsoft: oauth names the provider and password holds what oauth.py keeps)."""

    def __init__(self, key, address, login="", imap_server=None, smtp_server=None, name="", save_sent=True, oauth=""):
        self.key, self.address, self.login, self.name = key, address, login or address, name
        self.imap_server, self.smtp_server, self.save_sent = imap_server, smtp_server, save_sent
        self.oauth = oauth
        self.password = None
        self.conn = None
        self.status = "connecting"          # connecting, ready, auth, offline
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"plume-{key}")
        # opening a message has its own session: it never waits behind a sync (the folders, their counts)
        self.read_conn = None
        self.read_used = 0.0
        self.read_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"plume-{key}-read")
        self.idle_stop = threading.Event()
        self.important = 0

    def connect(self, timeout=30):
        if self.oauth:
            token = oauth.access_token(self.address, self.password)
            return imap.Connection(self.login, token, timeout=timeout, server=self.imap_server, xoauth2=True)
        return imap.Connection(self.login, self.password, timeout=timeout, server=self.imap_server)

    def smtp(self):
        return autoconfig.smtp_session(self.smtp_server or smtp_endpoint(), timeout=30)

    def sign_in(self, session):
        """Signs an SMTP session in. A token that cannot be had fails like a refused password, or like no network."""
        if not self.oauth:
            session.login(self.login, self.password)
            return
        try:
            token = oauth.access_token(self.address, self.password)
        except imap.MailError as error:
            if error.kind == "offline":
                raise OSError("no access token") from error
            raise smtplib.SMTPAuthenticationError(535, b"access token refused") from error
        autoconfig.smtp_login(session, self.login, token, xoauth2=True)


class MessageList(QAbstractListModel):
    def __init__(self):
        super().__init__()
        self._rows = []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def roleNames(self):
        return {Qt.ItemDataRole.UserRole + i: QByteArray(n.encode()) for i, n in enumerate(ROLES)}

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        i = role - Qt.ItemDataRole.UserRole
        return self._rows[index.row()][ROLES[i]] if 0 <= i < len(ROLES) else None

    def set_rows(self, rows):
        if [r["messageId"] for r in rows] == [r["messageId"] for r in self._rows]:
            for i, row in enumerate(rows):
                if row != self._rows[i]:
                    self._rows[i] = row
                    self.dataChanged.emit(self.index(i), self.index(i))
            return
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def update(self, message_id, **changes):
        for i, row in enumerate(self._rows):
            if row["messageId"] == message_id:
                row.update(changes)
                self.dataChanged.emit(self.index(i), self.index(i))
                return

    def remove(self, ids):
        ids = set(ids)
        for i in reversed(range(len(self._rows))):
            if self._rows[i]["messageId"] in ids:
                self.beginRemoveRows(QModelIndex(), i, i)
                self._rows.pop(i)
                self.endRemoveRows()

    def row(self, i):
        return self._rows[i] if 0 <= i < len(self._rows) else None

    def index_of(self, message_id):
        return next((i for i, r in enumerate(self._rows) if r["messageId"] == message_id), -1)


class Mail(QObject):
    changed = Signal()
    currentChanged = Signal()
    reveal = Signal(int)                         # a message to show (opened from a task of Tâches)
    busyChanged = Signal()
    boxesChanged = Signal()
    setupResult = Signal(bool, str)
    boxResult = Signal(bool, str, str)            # ok, reason, address
    oauthChanged = Signal()                       # the providers Plume can sign in with are known
    providerFound = Signal(str, str)              # address, note: its domain was looked up (MX)
    sendQueued = Signal()
    moveQueued = Signal(str, int)                 # what happened (archive, trash, forever, junk, inbox, folder), messages
    moveCancelled = Signal(int)                   # the line back in the list
    sendCancelled = Signal("QVariantMap")
    composeRecovered = Signal("QVariantMap")      # a message being written when Plume stopped (crash, power cut)
    shareLinkReady = Signal(str, str)
    invitationArrived = Signal(str)            # the iCalendar text of an invitation (the calendar takes it)
    _run = Signal(object)

    def __init__(self, store, plume, theme, passive=False):
        super().__init__()
        self._drag = DragGuard(self, ["moveTo"])
        self._store, self._plume, self._theme = store, plume, theme
        # Agenda and Contacts of Orneos OS: mail only to answer invitations (SMTP); Courrier reads the mailboxes
        self._passive = passive
        self._run.connect(lambda fn: fn())
        self._model = MessageList()
        self._folders_made = None               # the folder list, until the next change (folders)
        self.boxesChanged.connect(self._forget_folders)
        self._state = "loading"
        self._account = store.get("mail_account") or {}
        self._boxes = {}
        self._oauth_apps = []                   # providers Plume can sign in with (their app is published)
        self._sign_in = None                    # the sign-in going on in the browser: {"cancel": Event, "flow"}
        self._folder_id = int(store.get("mail_folder", 0) or 0)
        self._query = ""
        self._unread_only = False
        self._server_hits = set()                # ids of the messages the servers found (their bodies too)
        self._everywhere = False                # a search in every folder of every mailbox
        self._depth = {}
        self._current = {}
        self._current_raw = None
        self._current_thread = None             # (members, raws) of an opened conversation
        self._members = {}                      # list row id → ids of its conversation in this list
        self._thread_of = {}                    # message id → conversation key
        self._threads_made = None               # (what the cache held, _thread_of then), see _threads
        self._sync_waiting = set()              # folders whose sync waits on their worker (_queue_sync)
        self._shown_seq = 0                     # the message read last (_show: an older reading is dropped)
        self._read_memo = {}                    # the messages of the open conversation, read (_show)
        self._hidden = set()                    # moved, waiting for the few seconds that allow undoing it
        self._moves = []
        self._busy = 0
        self._closed = False
        # what the servers still have to do (sends, drafts, reads, moves), kept on disk until they did it
        self._queue = mailqueue.Queue()
        self._flushing, self._flush_again = set(), set()
        self._running = set()                   # queued operations being done right now (a send cannot be undone)
        self._send_timers = {}
        self._queue_timer = QTimer(self)
        self._queue_timer.setInterval(RETRY_MS)
        self._queue_timer.timeout.connect(self._flush_all)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(5 * 60 * 1000)
        self._refresh_timer.timeout.connect(self.refresh)
        # IDLE watches the inbox; another folder shown is read again every minute while the window is in front
        self._shown_timer = QTimer(self)
        self._shown_timer.setInterval(60 * 1000)
        self._shown_timer.timeout.connect(self._poll_shown)
        self._read_timer = QTimer(self)             # « marked read after a few seconds » (setting)
        self._read_timer.setSingleShot(True)
        self._read_timer.timeout.connect(self._mark_shown_read)
        self._to_read = []
        self._snooze_timer = QTimer(self)           # messages put away until a time: back in the inbox then
        self._snooze_timer.setInterval(60 * 1000)
        self._snooze_timer.timeout.connect(self._wake_snoozed)
        # the dock's unread badge follows Plume at once while it runs (orneos-notify only polls the cloud)
        self._badge = None
        self._badge_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="plume-badge")
        self._badge_timer = QTimer(self)
        self._badge_timer.setSingleShot(True)
        self._badge_timer.setInterval(600)
        self._badge_timer.timeout.connect(self._write_badge)
        self.changed.connect(self._badge_timer.start)
        # back in front: the inboxes again (an IDLE that died during sleep only shows at the next 5 min refresh)
        self._last_sync = 0.0
        app = QGuiApplication.instance()
        if app is not None and not passive:
            app.applicationStateChanged.connect(self._state_changed)
        plume.accountChanged.connect(self._load_account)
        self._load_account()

    # ---- the Orneos mailbox -------------------------------------------------------------------------
    def _set_state(self, state):
        if state != self._state:
            self._state = state
            self._emit_changed()

    def _load_account(self):
        account = self._plume.account()
        if account is None:
            self._stop_all()
            self._set_state("noaccount")
            return
        server, user, password = account
        cache_owner = self._store.get("widget_mail_owner")
        if cache_owner != [server.rstrip("/"), user]:
            self._stop_all()
            self._store.prepare_mail_account(server, user)
            if cache_owner is not None:
                self._account = {}
            self._folder_id = 0
        if not self._account.get("address"):
            self._account = {"address": user if "@" in user else f"{user}@orneos.eu", "login": "", "name": "",
                             "identities": [], "signature": ""}
        threading.Thread(target=self._fetch_identities, args=(account,), daemon=True).start()
        self._try_saved_password()

    def _fetch_identities(self, account):
        """Address, name, signature and aliases from the cloud's Mail app (the same as in the browser)."""
        try:
            rows = cloud.mail_accounts(*account)
        except Exception:
            rows = []
        main = next((r for r in rows if "orneos" in str(r.get("imapHost", ""))), rows[0] if rows else None)
        if not main:
            return
        identities = [{"email": main.get("emailAddress", ""), "name": main.get("name", ""),
                       "signature": mime.signature_html(main.get("signature")), "accountId": main.get("id"), "aliasId": 0}]
        status, body = cloud.rest(*account, f"/apps/mail/api/accounts/{main.get('id')}/aliases")
        for alias in (body if isinstance(body, list) else (body or {}).get("data") or []) if status == 200 else []:
            if isinstance(alias, dict) and alias.get("alias"):
                identities.append({"email": alias["alias"], "name": alias.get("name") or main.get("name", ""),
                                   "signature": mime.signature_html(alias.get("signature") or main.get("signature")),
                                   "accountId": main.get("id"), "aliasId": alias.get("id") or 0,
                                   "inherits": not alias.get("signature")})
        info = {"address": main.get("emailAddress", "") or self._account.get("address", ""),
                "login": main.get("imapUser") or main.get("emailAddress", ""), "name": main.get("name", ""),
                "identities": identities, "signature": main.get("signature") or "",
                "signatureAbove": bool(main.get("signatureAboveQuote"))}

        def apply():
            if account != self._plume.account():
                return
            changed_address = info["address"].lower() != self._account.get("address", "").lower()
            self._account = info
            self._store.set("mail_account", info)
            self._emit_changed()
            if changed_address:
                self._try_saved_password()
        self._run.emit(apply)

    def _login(self):
        return self._account.get("login") or self._account.get("address", "")

    def _try_saved_password(self):
        address = self._account.get("address", "")

        def lookup():
            password = secrets.get(address) if address else None

            def apply():
                if password:
                    self._start(password)
                else:
                    self._set_state("setup")
            self._run.emit(apply)
        threading.Thread(target=lookup, daemon=True).start()

    @Slot(str)
    def setup(self, password):
        """The one time the password is asked: checked on the server, then kept in the wallet."""
        login = self._login()

        def check():
            try:
                imap.Connection(login, password, timeout=20).close()
            except imap.MailError as error:
                kind = error.kind
                self._run.emit(lambda: self.setupResult.emit(False, kind))
                return
            secrets.put(self._account.get("address", login), password)

            def apply():
                self.setupResult.emit(True, "")
                self._start(password)
            self._run.emit(apply)
        threading.Thread(target=check, daemon=True).start()

    @Slot()
    def forgetPassword(self):
        secrets.forget(self._account.get("address", ""))
        self._stop_box(ORNEOS)
        self._set_state("setup")

    def _start(self, password):
        if ORNEOS in self._boxes:
            self._stop_box(ORNEOS)
        box = Box(ORNEOS, self._account.get("address", ""), self._login(), name=self._account.get("name", ""))
        box.password = password
        box.status = "ready"
        self._boxes[ORNEOS] = box
        self._set_state("ready")
        if not self._passive:
            self._refresh_timer.start()
            self._shown_timer.start()
            self._snooze_timer.start()
            QTimer.singleShot(3000, self._wake_snoozed)
        self._reload_list()
        self._start_box(box)
        self._start_external()
        if not self._passive:
            self._recover()

    def _stop_box(self, key):
        box = self._boxes.pop(key, None)
        if box is None:
            return
        box.idle_stop.set()
        conn, box.conn = box.conn, None
        if conn is not None:
            box.pool.submit(conn.close)
        box.pool.shutdown(wait=False)
        conn, box.read_conn = box.read_conn, None
        if conn is not None:
            box.read_pool.submit(conn.close)
        box.read_pool.shutdown(wait=False)

    def _poll_shown(self):
        if self._state != "ready" or self._closed or self._folder_id <= 0:
            return
        if QGuiApplication.applicationState() != Qt.ApplicationState.ApplicationActive:
            return
        folder = self._folder(self._folder_id)
        if folder is not None and folder["role"] != "inbox":
            self._queue_sync(folder["id"], folder["box"], quiet=True)

    def _stop_all(self):
        self._refresh_timer.stop()
        self._shown_timer.stop()
        for key in list(self._boxes):
            self._stop_box(key)

    def _write_badge(self):
        if self._state != "ready" or self._closed or self._passive:
            return
        count = self.inboxUnseen
        if count == self._badge:
            return
        self._badge = count

        def write():
            try:
                cloud.mail_badge_owner(os.getpid())
                cloud.mail_badge(count)
            except Exception:
                pass
        self._badge_pool.submit(write)

    def shutdown(self):
        """On quit. Sends and drafts still queued finish first; reading is simply dropped."""
        self._closed = True
        try:
            if not self._passive:
                cloud.mail_badge_owner(None)          # orneos-notify takes the badge back
        except Exception:
            pass
        self._refresh_timer.stop()
        for box in list(self._boxes.values()):
            box.idle_stop.set()
            keep = box.important > 0
            box.read_pool.shutdown(wait=False, cancel_futures=True)
            box.pool.shutdown(wait=keep, cancel_futures=not keep)

    # ---- external mailboxes ---------------------------------------------------------------------------
    def _configs(self):
        return [c for c in (self._store.get("mail_boxes") or []) if isinstance(c, dict) and c.get("key")]

    def _save_configs(self, configs):
        self._store.set("mail_boxes", configs)
        self.boxesChanged.emit()

    @staticmethod
    def _server(value):
        return (value["host"], int(value["port"]), value["security"]) if value else None

    def _box_of(self, config):
        return Box(config["key"], config["address"], config.get("login") or config["address"],
                   self._server(config.get("imap")), self._server(config.get("smtp")), config.get("name", ""),
                   config.get("saveSent", True), config.get("oauth", ""))

    def _start_external(self):
        for config in self._configs():
            if config["key"] not in self._boxes:
                self._open_external(config)

    def _open_external(self, config, password=None):
        box = self._box_of(config)
        self._boxes[box.key] = box
        self.boxesChanged.emit()

        def lookup():
            found = password or secrets.get(box.address)

            def apply():
                if self._boxes.get(box.key) is not box:
                    return
                if not found:
                    box.status = "auth"
                    self.boxesChanged.emit()
                    return
                box.password = found
                box.status = "ready"
                self.boxesChanged.emit()
                self._start_box(box)
            self._run.emit(apply)
        threading.Thread(target=lookup, daemon=True).start()

    def _start_box(self, box):
        if self._passive:
            return
        self._job(lambda conn: self._sync_folders(conn, box.key), box.key)
        self._job(lambda conn: self._sync_folder(conn, self._inbox_id(box.key)), box.key)
        self._job(lambda conn: self._sync_sent(conn, box.key), box.key, quiet=True)
        if self._folder_id > 0 and self._box_key(self._folder_id) == box.key:
            folder = self._folder_id
            self._job(lambda conn: self._sync_folder(conn, folder), box.key)
        self._start_idle(box)
        self._flush(box.key)

    @Property("QVariantList", notify=boxesChanged)
    def boxes(self):
        """The external mailboxes, for the settings: address, name, servers, state."""
        out = []
        for config in self._configs():
            box = self._boxes.get(config["key"])
            out.append({"key": config["key"], "address": config["address"], "name": config.get("name", ""),
                        "label": config.get("label", ""),
                        "imapHost": (config.get("imap") or {}).get("host", ""), "oauth": config.get("oauth", ""),
                        "status": box.status if box else "connecting"})
        return out

    @Slot(str, result=str)
    def providerNote(self, address):
        """What the provider asks for, from what is known already. A domain of its own is then looked up by
        its MX in the background: providerFound(address, note) when that tells more."""
        address = address.strip()
        if "@" not in address or "." not in address.rpartition("@")[2]:
            return ""
        if not autoconfig.looked_up(address):
            def run():
                note = autoconfig.note_for(address, lookup=True)
                if note:
                    self._run.emit(lambda: self.providerFound.emit(address, note))
            threading.Thread(target=run, daemon=True).start()
        return autoconfig.note_for(address)

    @Slot("QVariantMap")
    def addBox(self, fields):
        """Add an external mailbox: from its address and password (servers found on their own), or with the
        servers given by hand (imapHost, imapPort, imapSecurity, smtpHost…). boxResult(ok, reason, address)."""
        fields = {k: (v.toVariant() if hasattr(v, "toVariant") else v) for k, v in dict(fields).items()}
        address = str(fields.get("address", "")).strip()
        password = str(fields.get("password", ""))
        name = str(fields.get("name", "")).strip()
        if "@" not in address or not password:
            self.boxResult.emit(False, "missing", address)
            return
        taken = {self._account.get("address", "").lower()} | {c["address"].lower() for c in self._configs()}
        if address.lower() in taken:
            self.boxResult.emit(False, "exists", address)
            return
        manual = bool(str(fields.get("imapHost") or "").strip())

        def run():
            if manual:
                config = {"imap": {"host": fields["imapHost"].strip(), "port": int(fields.get("imapPort") or 993),
                                   "security": fields.get("imapSecurity") or "ssl"},
                          "smtp": {"host": (fields.get("smtpHost") or fields["imapHost"]).strip(),
                                   "port": int(fields.get("smtpPort") or 465), "security": fields.get("smtpSecurity") or "ssl"},
                          "login": (fields.get("login") or address).strip(), "saveSent": True}
                reason = autoconfig.check_imap(config, password)
                if reason:
                    config = None
            else:
                config, reason = autoconfig.discover(address, password)
            if config is not None:
                smtp = autoconfig.check_smtp(config, password)
                if smtp:
                    config, reason = None, "smtp_" + smtp
            if config is None:
                self._run.emit(lambda: self.boxResult.emit(False, reason, address))
                return
            secrets.put(address, password)
            config.update({"key": "x" + uuid.uuid4().hex[:8], "address": address, "name": name, "signature": ""})

            def apply():
                self._save_configs(self._configs() + [config])
                if self._state == "ready":
                    self._open_external(config, password)
                self._emit_changed()
                self.boxResult.emit(True, "", address)
            self._run.emit(apply)
        threading.Thread(target=run, daemon=True).start()

    # ---- signing in with Google or Microsoft --------------------------------------------------------------------
    @Property("QVariantList", notify=oauthChanged)
    def oauthProviders(self):
        return self._oauth_apps

    @Slot()
    def loadOauth(self):
        """Which providers can be signed in with (asked to orneos.eu, kept an hour): oauthChanged."""
        def run():
            found = sorted(oauth.apps())

            def apply():
                self._oauth_apps = found
                self.oauthChanged.emit()
            self._run.emit(apply)
        threading.Thread(target=run, daemon=True).start()

    @Slot(str, result=str)
    def oauthProviderOf(self, address):
        """The provider whose page this address signs in with, when Plume can: "google", "microsoft" or ""."""
        found = autoconfig.oauth_provider(address.strip()) if "@" in address else ""
        return found if found in self._oauth_apps else ""

    @Slot(str, str, str)
    def signInBox(self, provider, hint, name):
        """Adds a mailbox with the provider's own page, in the browser: Plume learns the address from it.
        boxResult(ok, reason, address) once it is over ("cancelled" when cancelSignIn() came first)."""
        self._sign_in_flow(provider, hint, name, None)

    @Slot(str)
    def reconnectBox(self, key):
        """A mailbox signed in with Google or Microsoft whose sign-in no longer works: the page again."""
        config = next((c for c in self._configs() if c["key"] == key), None)
        if config is not None and config.get("oauth"):
            self._sign_in_flow(config["oauth"], config["address"], config.get("name", ""), config)

    @Slot()
    def cancelSignIn(self):
        current, self._sign_in = self._sign_in, None
        if current:
            current["cancel"].set()
            if current["flow"]:
                current["flow"].cancel()

    def _sign_in_flow(self, provider, hint, name, existing):
        self.cancelSignIn()
        t = self._plume.t
        current = {"cancel": threading.Event(), "flow": None}
        self._sign_in = current
        pages = (oauth.page(t["oauth_page_done_title"], t["oauth_page_done"]),
                 oauth.page(t["oauth_page_failed_title"], t["oauth_page_failed"]))

        def fail(reason, address=hint):
            self._run.emit(lambda: self.boxResult.emit(False, reason, address))

        def run():
            try:
                flow = oauth.SignIn(provider, hint, *pages)
                current["flow"] = flow
                if current["cancel"].is_set():
                    flow.cancel()
                self._run.emit(lambda: system.open_url(flow.url))
                got = flow.wait()
            except oauth.OAuthError as error:
                fail("net" if error.kind == "offline" else error.kind)
                return
            finally:
                if self._sign_in is current:
                    self._sign_in = None
            address = got["address"]
            if existing is not None:
                if address.lower() != existing["address"].lower():
                    fail("other_account", address)
                    return
            else:
                taken = {self._account.get("address", "").lower()} | {c["address"].lower() for c in self._configs()}
                if address.lower() in taken:
                    fail("exists", address)
                    return
            conf = oauth.PROVIDERS[provider]
            config = {"imap": dict(conf["imap"]), "smtp": dict(conf["smtp"]), "login": address, "saveSent": False,
                      "oauth": provider}
            reason = autoconfig.check_imap(config, got["access"], xoauth2=True)
            if reason:
                fail({"auth": "oauth_imap", "offline": "net"}.get(reason, reason), address)
                return
            reason = autoconfig.check_smtp(config, got["access"], xoauth2=True)
            if reason:
                fail("oauth_smtp" if reason == "auth" else "smtp_" + reason, address)
                return
            secrets.put(address, got["secret"])
            oauth.forget(address)
            oauth.remember(address, got["access"], got["expires"])

            def apply():
                if existing is not None:
                    self._stop_box(existing["key"])
                    self._open_external(existing, got["secret"])
                else:
                    config.update({"key": "x" + uuid.uuid4().hex[:8], "address": address,
                                   "name": name or got["name"], "signature": ""})
                    self._save_configs(self._configs() + [config])
                    if self._state == "ready":
                        self._open_external(config, got["secret"])
                    self._emit_changed()
                self.boxResult.emit(True, "", address)
            self._run.emit(apply)
        threading.Thread(target=run, daemon=True).start()

    @Slot(str, str)
    def setBoxPassword(self, key, password):
        """A new password for an external mailbox (it changed on the provider's side)."""
        config = next((c for c in self._configs() if c["key"] == key), None)
        if config is None:
            return

        def run():
            reason = autoconfig.check_imap(config, password)
            if reason:
                self._run.emit(lambda: self.boxResult.emit(False, reason, config["address"]))
                return
            secrets.put(config["address"], password)

            def apply():
                self._stop_box(key)
                self._open_external(config, password)
                self.boxResult.emit(True, "", config["address"])
            self._run.emit(apply)
        threading.Thread(target=run, daemon=True).start()

    @Slot(str, result="QVariantMap")
    def boxConfig(self, key):
        """The servers of an external mailbox, for the settings."""
        config = next((c for c in self._configs() if c["key"] == key), None) or {}
        imap_, smtp_ = config.get("imap") or {}, config.get("smtp") or {}
        return {"imapHost": imap_.get("host", ""), "imapPort": imap_.get("port", 993), "imapSecurity": imap_.get("security", "ssl"),
                "smtpHost": smtp_.get("host", ""), "smtpPort": smtp_.get("port", 465), "smtpSecurity": smtp_.get("security", "ssl"),
                "login": config.get("login") or config.get("address", ""), "saveSent": config.get("saveSent", True),
                "oauth": config.get("oauth", "")}

    @Slot(str, "QVariantMap")
    def updateBoxServers(self, key, fields):
        """Other servers (or login, or « copy in Sent ») for an external mailbox: checked like when it was added,
        with its password (the one kept, unless a new one is given). boxResult(ok, reason, address)."""
        fields = self._plain(fields)
        config = next((c for c in self._configs() if c["key"] == key), None)
        if config is None:
            return
        changed = dict(config)
        changed.update({"imap": {"host": str(fields.get("imapHost") or "").strip(), "port": int(fields.get("imapPort") or 993),
                                 "security": fields.get("imapSecurity") or "ssl"},
                        "smtp": {"host": str(fields.get("smtpHost") or fields.get("imapHost") or "").strip(),
                                 "port": int(fields.get("smtpPort") or 465), "security": fields.get("smtpSecurity") or "ssl"},
                        "login": str(fields.get("login") or config["address"]).strip(), "saveSent": bool(fields.get("saveSent", True))})
        new_password = str(fields.get("password") or "")

        def run():
            password = new_password or secrets.get(config["address"])
            reason = "auth" if not password else ("" if changed.get("oauth") else autoconfig.check_imap(changed, password))
            if not reason and not changed.get("oauth"):
                smtp = autoconfig.check_smtp(changed, password)
                reason = "smtp_" + smtp if smtp else ""
            if reason:
                self._run.emit(lambda: self.boxResult.emit(False, reason, config["address"]))
                return
            if new_password:
                secrets.put(config["address"], new_password)

            def apply():
                self._save_configs([changed if c["key"] == key else c for c in self._configs()])
                self._stop_box(key)
                if self._state == "ready":
                    self._open_external(changed, password)
                self.boxResult.emit(True, "", config["address"])
            self._run.emit(apply)
        threading.Thread(target=run, daemon=True).start()

    @Slot(str)
    def removeBox(self, key):
        """Plume stops reading this mailbox: its cache and its password go; nothing changes on its server."""
        config = next((c for c in self._configs() if c["key"] == key), None)
        if config is None or key == ORNEOS:
            return
        self._stop_box(key)
        secrets.forget(config["address"])
        oauth.forget(config["address"])
        if self._box_key(self._folder_id) == key or (self._folder_id == -2 and len(self._configs()) == 1):
            self._folder_id = self._inbox_id(ORNEOS)
            self._current, self._current_raw, self._current_thread = {}, None, None
            self.currentChanged.emit()
        self._store.execute("DELETE FROM mail_folders WHERE box = ?", (key,))
        self._save_configs([c for c in self._configs() if c["key"] != key])
        self._reload_list()

    # ---- workers --------------------------------------------------------------------------------------
    def _job(self, fn, key=ORNEOS, quiet=False, important=False, after=None, read=False):
        """Run fn(connection) on the worker of this mailbox; reconnect once when the session dropped.
        important: a send or a draft, which quitting waits for. after: called on the main thread once it is
        over, whether it worked or not. read: on the session that only reads messages (opening one)."""
        box = self._boxes.get(key)
        if box is None or box.password is None:
            if after is not None:
                after()
            return
        if important:
            box.important += 1
        cache_owner = self._store.get("widget_mail_owner")
        session = "read_conn" if read else "conn"

        def run():
            self._store.mail_context.owner = cache_owner
            self._run.emit(lambda: self._busy_delta(1))
            try:
                self._store._check_mail_owner()
                if read and box.read_conn is not None and time.monotonic() - box.read_used > READ_IDLE:
                    # a session left alone that long may have been dropped on the way (a router, sleep): its next
                    # command would wait for the timeout. A new one is quicker.
                    stale, box.read_conn = box.read_conn, None
                    try:
                        stale.imap.shutdown()       # no LOGOUT: it would wait for the same answer
                    except Exception:  # noqa: BLE001
                        pass
                if read:
                    box.read_used = time.monotonic()
                for attempt in (1, 2):
                    try:
                        if getattr(box, session) is None:
                            setattr(box, session, box.connect())
                        fn(getattr(box, session))
                        if box.key == ORNEOS:
                            self._run.emit(lambda: self._plume.reached("mail", True))
                        if box.status != "ready":
                            box.status = "ready"
                            self._run.emit(self.boxesChanged.emit)
                        return
                    except imap.MailError as error:
                        setattr(box, session, None)
                        if error.kind == "auth":
                            self._run.emit(lambda: self._auth_failed(box))
                            return
                        if attempt == 2:
                            if box.key == ORNEOS and error.kind == "offline":
                                self._run.emit(lambda: self._plume.reached("mail", False))
                            if box.key != ORNEOS and box.status != "offline":
                                box.status = "offline"
                                self._run.emit(self.boxesChanged.emit)
                            if not quiet:
                                self._run.emit(lambda k=error.kind: self._plume.syncFailed("offline" if k == "offline" else "server"))
                    except (imaplib.IMAP4.abort, imaplib.IMAP4.error, OSError, ssl.SSLError):
                        setattr(box, session, None)
                        if attempt == 2 and box.key == ORNEOS:
                            self._run.emit(lambda: self._plume.reached("mail", False))
                        if attempt == 2 and not quiet:
                            self._run.emit(lambda: self._plume.syncFailed("offline"))
            except StaleMailAccount:
                return
            finally:
                self._store.mail_context.owner = None
                if important:
                    box.important -= 1
                self._run.emit(lambda: self._busy_delta(-1))
                if after is not None:
                    self._run.emit(after)
        if self._closed:
            if important:
                run()               # quitting already: do it now rather than lose it
            return
        try:
            (box.read_pool if read else box.pool).submit(run)
        except RuntimeError:        # the mailbox was just removed
            pass

    def _busy_delta(self, n):
        self._busy = max(0, self._busy + n)
        self.busyChanged.emit()

    def _auth_failed(self, box):
        """The password changed (account settings, reset), or the provider no longer accepts the sign-in:
        asked again, once."""
        secrets.forget(box.address)
        oauth.forget(box.address)
        if box.key == ORNEOS:
            self._stop_box(ORNEOS)
            self._set_state("setup")
            return
        box.password = None
        box.status = "auth"
        box.idle_stop.set()
        self.boxesChanged.emit()
        self._plume.toast.emit(self._plume.t["box_auth_oauth" if box.oauth else "box_auth"].replace("%1", box.address))

    # ---- what the servers still have to do --------------------------------------------------------------
    # Sends, drafts, reads, stars, tags, moves: the window changes at once and the operation is written to disk
    # (mailqueue.py), then done by the mailbox's worker. Without network it waits, and goes when the server
    # answers again (every RETRY_MS, at each sync, at the next start). Only Courrier (or Plume) does them:
    # Agenda and Contacts of Orneos OS, which open the mailboxes too, never touch the queue.
    def _owner(self):
        owner = self._store.get("widget_mail_owner")
        return "|".join(owner) if isinstance(owner, list) else ""

    def _enqueue(self, op, raw=None, flush=True):
        op = self._queue.add(dict(op, owner=self._owner()), raw)
        self._queue_timer.start()
        if flush:
            self._flush(op["box"])
        return op

    def _queued(self, key):
        """{(path, uid)} whose flags wait to reach the server (a sync must not put the old ones back), and
        {(path, uid)} moved or deleted here (a sync must not bring them back); "*" stands for a whole folder."""
        flags, gone = set(), set()
        for op in self._queue.items(box=key, owner=self._owner()):
            kind = op["kind"]
            if kind == "flag":
                flags |= {(path, uid) for path, uids in op["by_path"].items() for uid in uids}
            elif kind == "flag_all":
                flags.add((op["path"], "*"))
            elif kind == "move":
                gone |= {(path, uid) for path, uids in op["by_path"].items() for uid in uids}
            elif kind == "empty":
                gone.add((op["path"], "*"))
            elif kind in ("draft", "send") and op.get("drop"):
                gone.add((op["drop"]["path"], op["drop"]["uid"]))
        return flags, gone

    def _flush_all(self):
        mine = self._queue.items(owner=self._owner())
        if not mine:
            self._queue_timer.stop()
            return
        for key in {op["box"] for op in mine}:
            self._flush(key)

    def _flush(self, key, important=False):
        """The queued operations of a mailbox, in their order, on its worker."""
        if self._passive or key not in self._boxes:
            return
        if key in self._flushing:
            self._flush_again.add(key)
            return
        waiting = self._queue.items(box=key, owner=self._owner())
        if not any(op["kind"] != "send" or op.get("due", 0) <= time.time() + 0.25 for op in waiting):
            return                              # only messages planned for later: nothing to do yet
        self._flushing.add(key)
        owner = self._owner()
        box = self._boxes[key]

        ran, tried = [False], set()

        def run(conn):
            ran[0] = True
            synced = set()
            for op in self._queue.items(box=key, owner=owner):
                if op["kind"] == "send" and op.get("due", 0) > time.time() + 0.25:
                    continue                    # still in the seconds it can be cancelled (timers may fire a bit early)
                if op["kind"] == "send":
                    tried.add(op["id"])
                if self._queue.get(op["id"]) is None:
                    continue                    # cancelled meanwhile
                self._running.add(op["id"])
                try:
                    synced |= self._apply(conn, box, op)
                except imap.MailError as error:
                    if error.kind != "server":
                        raise                   # no network: everything waits, in its order
                    self._queue.remove(op["id"])  # refused by the server (gone, not allowed): dropped
                finally:
                    self._running.discard(op["id"])
            if synced:
                self._sync_folders(conn, key)
                for role in synced:
                    folder = self._role_folder(role, key)
                    if folder is not None:
                        self._sync_folder(conn, folder["id"])

        def after():
            self._flushing.discard(key)
            # a message that should have left and is still here could not (no network): said once
            for op in self._queue.items(box=key, kind="send", owner=owner):
                if not op.get("smtp_done") and (op["id"] in tried or not ran[0] and op.get("due", 0) <= time.time()) \
                        and not (op.get("fields") or {}).get("scheduled"):
                    self._offline_send(op)
            self._emit_changed()
            if self._folder_id == OUTBOX:
                self._reload_list()
            if key in self._flush_again:
                self._flush_again.discard(key)
                self._flush(key)
            elif self._queue.items(owner=self._owner()):
                self._queue_timer.start()
        self._job(run, key, quiet=True, important=important, after=after)

    def _apply(self, conn, box, op):
        """One queued operation, on the worker. Returns the roles of the folders to read again. Raises when the
        server could not be reached (the operation waits); a refusal for good removes it."""
        kind = op["kind"]
        if kind == "flag":
            for path, uids in op["by_path"].items():
                conn.select(path)
                conn.flags(uids, op["flag"], op["on"])
        elif kind == "flag_all":
            conn.select(op["path"])
            conn.flags(conn.uids("UNSEEN"), "\\Seen", True)
        elif kind == "empty":
            conn.select(op["path"])
            conn.delete(conn.uids("ALL"))
        elif kind == "move":
            dest = op.get("dest")
            if dest is None and op.get("create"):
                conn.create(op["create"])
                dest = op["create"]
            done = list(op.get("done") or [])
            for path, uids in op["by_path"].items():
                if path in done:
                    continue
                conn.select(path)
                if op.get("forever") or dest is None:
                    conn.delete(uids)
                else:
                    conn.move(uids, dest)
                done.append(path)
                self._queue.update(op["id"], done=done)
            self._queue.remove(op["id"])
            return {"inbox"}
        elif kind == "draft":
            raw = self._queue.raw(op["id"])
            if raw is not None and not op.get("appended"):
                drafts = self._role_folder("drafts", box.key)
                path = drafts["path"] if drafts else "Drafts"
                if not drafts:
                    conn.create(path)
                conn.append(path, raw, "(\\Seen \\Draft)")
                self._queue.update(op["id"], appended=True)
            self._drop(conn, op.get("drop"))
            self._queue.remove(op["id"])
            return {"drafts"}
        elif kind == "send":
            return self._apply_send(conn, box, op)
        elif kind == "unsnooze":
            folder = self._role_folder("snoozed", box.key)
            inbox = self._role_folder("inbox", box.key)
            path = folder["path"] if folder else SNOOZE_FOLDER
            try:
                conn.select(path)
            except imap.MailError:
                self._queue.remove(op["id"])        # no such folder any more: nothing to bring back
                return set()
            uids = conn.search_criteria([("HEADER Message-ID", op["mid"])])
            if uids:
                conn.flags(uids, "\\Seen", False)
                conn.move(uids, inbox["path"] if inbox else "INBOX")
            self._queue.remove(op["id"])
            return {"inbox", "snoozed"}
        self._queue.remove(op["id"])
        return set()

    def _drop(self, conn, where):
        """A message removed from the server by its folder and UID (the draft a new version replaces)."""
        if not where:
            return
        conn.select(where["path"])
        conn.delete([where["uid"]])

    def _apply_send(self, conn, box, op):
        raw = self._queue.raw(op["id"])
        if raw is None:
            self._queue.remove(op["id"])
            return set()
        fields = op.get("fields") or {}
        if not op.get("smtp_done"):
            try:
                with box.smtp() as smtp:
                    box.sign_in(smtp)
                    smtp.sendmail(op["sender"], op["recipients"], raw)
            except PERMANENT_SMTP + (smtplib.SMTPResponseException,) as error:
                code = getattr(error, "smtp_code", 550)
                if isinstance(error, PERMANENT_SMTP) or code >= 500:
                    self._queue.remove(op["id"])
                    back = dict(fields, drop=op.get("drop"))
                    self._run.emit(lambda: (self._plume.toast.emit(self._plume.t["send_failed"]), self.sendCancelled.emit(back)))
                    return set()
                self._offline_send(op)
                raise OSError("SMTP busy") from error
            except (smtplib.SMTPException, OSError, socket.timeout, ssl.SSLError) as error:
                self._offline_send(op)
                raise OSError("SMTP unreachable") from error
            self._queue.update(op["id"], smtp_done=True)
            self._run.emit(lambda: self._plume.toast.emit(self._plume.t["sent_later" if op.get("told") else "sent"]))
        # the message left: what follows is the copy in Sent, the original answered, the draft gone (each once)
        if box.save_sent and not op.get("saved"):
            sent = self._role_folder("sent", box.key)
            path = sent["path"] if sent else "Sent"
            if not sent:
                conn.create(path)
            conn.append(path, mime.keep_bcc(raw, fields.get("bcc")))
            self._queue.update(op["id"], saved=True)
        reply = op.get("reply")
        if reply and not op.get("answered"):
            conn.select(reply["path"])
            conn.flags([reply["uid"]], "\\Answered", True)
            self._store.execute("UPDATE messages SET answered = 1 WHERE uid = ? AND folder_id IN "
                                "(SELECT id FROM mail_folders WHERE box = ? AND path = ?)", (reply["uid"], box.key, reply["path"]))
            self._queue.update(op["id"], answered=True)
        self._drop(conn, op.get("drop"))
        self._queue.remove(op["id"])
        return {"sent", "drafts"} if op.get("drop") else {"sent"}

    def _offline_send(self, op):
        """A message that cannot leave now: said once, it waits in the outbox."""
        if op.get("told"):
            return
        self._queue.update(op["id"], told=True)
        op["told"] = True
        self._run.emit(lambda: (self._plume.toast.emit(self._plume.t["send_offline"]), self._emit_changed()))


    # ---- folders ------------------------------------------------------------------------------------
    @Slot()
    def refresh(self):
        if self._state != "ready" or self._passive:
            return
        self._last_sync = time.monotonic()
        self._flush_all()
        for box in list(self._boxes.values()):
            if box.password is None:
                continue
            self._job(lambda conn, k=box.key: self._sync_folders(conn, k), box.key)
            self._sync_shown(box)
            self._job(lambda conn, k=box.key: self._sync_sent(conn, k), box.key, quiet=True)

    def _sync_shown(self, box):
        """Its inbox, always (the counts of the rail and the dock come from there, the list must follow), and
        the folder shown when it is one of this mailbox's."""
        inbox = self._inbox_id(box.key)
        self._queue_sync(inbox, box.key, quiet=True)
        if self._folder_id > 0 and self._folder_id != inbox and self._box_key(self._folder_id) == box.key:
            self._queue_sync(self._folder_id, box.key)

    def _queue_sync(self, folder_id, key, quiet=False):
        """A folder read again on its mailbox's worker, unless that is already waiting there (coming back to the
        window, the minute's poll and the 5 minutes' refresh ask for the same inbox)."""
        if folder_id in self._sync_waiting:
            return
        self._sync_waiting.add(folder_id)

        def run(conn):
            self._sync_waiting.discard(folder_id)
            self._sync_folder(conn, folder_id)
        self._job(run, key, quiet=quiet, after=lambda: self._sync_waiting.discard(folder_id))

    def _state_changed(self, state):
        if state != Qt.ApplicationState.ApplicationActive or self._state != "ready" or self._closed:
            return
        if time.monotonic() - self._last_sync < 20:
            return
        self._last_sync = time.monotonic()
        for box in list(self._boxes.values()):
            if box.password is not None:
                self._sync_shown(box)

    @Slot(str)
    def syncBox(self, key):
        """One mailbox again, now (its menu in the folder list): its folders, the folder shown (or its inbox)
        and Sent, then a word when it is up to date. A mailbox that lost its connection tries again."""
        box = self._boxes.get(key)
        if box is None or box.password is None:
            return
        folder = self._folder_id if self._folder_id > 0 and self._box_key(self._folder_id) == key else self._inbox_id(key)
        self._job(lambda conn: self._sync_folders(conn, key), key)
        self._job(lambda conn: self._sync_folder(conn, folder), key)
        self._job(lambda conn: self._sync_sent(conn, key), key, quiet=True)
        text = self._plume.t["box_synced"].replace("%1", box.address)
        self._job(lambda conn: self._run.emit(lambda: self._plume.toast.emit(text)), key, quiet=True)

    @Slot(int, str)
    def syncFolder(self, folder_id, label):
        """One folder again, now (its menu): Favoris and the unified inbox follow every mailbox."""
        if folder_id == -2 or folder_id == -1 or folder_id <= TAG_FOLDER:
            self.refresh()
            return
        folder = self._folder(folder_id)
        if folder is None:
            return
        text = self._plume.t["folder_synced"].replace("%1", label)
        self._job(lambda conn: self._sync_folder(conn, folder_id), folder["box"])
        self._job(lambda conn: self._run.emit(lambda: self._plume.toast.emit(text)), folder["box"], quiet=True)

    def _inbox_id(self, key=ORNEOS):
        rows = self._store.query("SELECT id FROM mail_folders WHERE box = ? AND role = 'inbox'", (key,))
        return rows[0]["id"] if rows else 0

    def _box_key(self, folder_id):
        folder = self._folder(folder_id) if folder_id and folder_id > 0 else None
        return folder["box"] if folder else ORNEOS

    def _sync_folders(self, conn, key=ORNEOS):
        remote = conn.folders()
        local = {r["path"]: r for r in self._store.query("SELECT * FROM mail_folders WHERE box = ?", (key,))}
        gone_paths = set(local) - {f["path"] for f in remote}
        for gone in gone_paths:
            self._store.execute("DELETE FROM mail_folders WHERE box = ? AND path = ?", (key, gone))
        changed = bool(gone_paths)
        columns = ("name", "full", "role", "delimiter", "noselect", "uidvalidity", "total", "unseen")
        for f in remote:
            stats = {}
            if not f["noselect"]:
                try:
                    stats = conn.status(f["path"])
                except imap.MailError:
                    stats = {}
            row = local.get(f["path"])
            values = (f["name"], f["full"], f["role"], f["delimiter"], int(f["noselect"]),
                      stats.get("uidvalidity", 0), stats.get("messages", 0), stats.get("unseen", 0))
            if row is not None and tuple(row[c] for c in columns) == values:
                continue
            changed = True
            if row is not None and stats.get("uidvalidity") and row["uidvalidity"] and stats["uidvalidity"] != row["uidvalidity"]:
                self._store.execute("DELETE FROM messages WHERE folder_id = ?", (row["id"],))
            self._store.execute(
                "INSERT INTO mail_folders (box, path, name, full, role, delimiter, noselect, uidvalidity, total, unseen) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(box, path) DO UPDATE SET name = excluded.name, "
                "full = excluded.full, role = excluded.role, delimiter = excluded.delimiter, noselect = excluded.noselect, "
                "uidvalidity = excluded.uidvalidity, total = excluded.total, unseen = excluded.unseen",
                (key, f["path"], *values))

        def apply():
            if key == ORNEOS and (not self._folder_id or (self._folder_id > 0 and not self._folder(self._folder_id))):
                self._folder_id = self._inbox_id(ORNEOS)
                self._reload_list()
            elif not changed:
                return                  # the same folders and counts: nothing for the window to redo
            self._emit_changed()
        self._run.emit(apply)

    def _folder(self, folder_id):
        rows = self._store.query("SELECT * FROM mail_folders WHERE id = ?", (folder_id,))
        return rows[0] if rows else None

    def _role_folder(self, role, key=ORNEOS):
        rows = self._store.query("SELECT * FROM mail_folders WHERE box = ? AND role = ? ORDER BY length(path)", (key, role))
        return rows[0] if rows else None

    def _sync_folder(self, conn, folder_id, notify=False):
        folder = self._folder(folder_id)
        if folder is None or folder["noselect"]:
            return
        conn.select(folder["path"])
        uids = conn.uids()
        keep = uids[-(LATEST + self._depth.get(folder_id, 0)):]
        cached = {r["uid"]: r for r in self._store.query(
            "SELECT id, uid, seen, flagged, answered, tags FROM messages WHERE folder_id = ?", (folder_id,))}
        present = set(uids)
        gone = [r["id"] for u, r in cached.items() if u not in present]
        if gone:
            self._store.many("DELETE FROM messages WHERE id = ?", [(i,) for i in gone])
        path = folder["path"]
        waiting_flags, moved = self._queued(folder["box"])
        if (path, "*") in moved:
            keep = []
        new = [u for u in keep if u not in cached and (path, u) not in moved]
        fresh = conn.headers(new) if new else []
        self._insert_headers(folder_id, fresh)
        if folder["role"] == "inbox":
            self._invitations(conn, folder_id, [h for h in fresh if h.get("calendar") and h["date"] > time.time() - INVITES_DAYS * 86400])
        old = [u for u in keep if u in cached]
        updates = []
        if old:
            states = conn.flag_states(old)
            for uid, flags in states.items():
                row = cached[uid]
                if (path, uid) in waiting_flags or (path, "*") in waiting_flags:
                    continue                    # changed here, the server does not have it yet
                values = (int("\\seen" in flags), int("\\flagged" in flags), int("\\answered" in flags),
                          imap.tags_of(flags))
                if values != (row["seen"], row["flagged"], row["answered"], row["tags"]):
                    updates.append(values + (row["id"],))
            if updates:
                self._store.many("UPDATE messages SET seen = ?, flagged = ?, answered = ?, tags = ? WHERE id = ?", updates)
        # read here, not yet on the server: the count stays what Plume shows
        unseen = 0 if (path, "*") in waiting_flags else len(conn.uids("UNSEEN"))
        if not (gone or fresh or updates) and (len(uids), unseen) == (folder["total"], folder["unseen"]):
            return                      # nothing new (most syncs): the window has nothing to redo
        self._store.execute("UPDATE mail_folders SET total = ?, unseen = ? WHERE id = ?", (len(uids), unseen, folder_id))
        if notify and folder["role"] == "inbox":
            self._notify_new([h for h in fresh if not h["seen"] and h["date"] > time.time() - 900])

        def apply():
            self._emit_changed()
            # a reply arriving in Sent changes the conversations of the folder shown
            if folder_id == self._folder_id or self._folder_id < 0 or (self._conversations() and fresh):
                self._reload_list()
        self._run.emit(apply)

    def _invitations(self, conn, folder_id, headers):
        """New invitations go to the calendar as they arrive (waiting for an answer), like on a phone:
        their message is read now (and kept, it opens at once)."""
        for h in headers[-INVITES_MAX:]:
            raw = conn.message(h["uid"])
            if raw is None:
                continue
            rows = self._store.query("SELECT id FROM messages WHERE folder_id = ? AND uid = ?", (folder_id, h["uid"]))
            if rows:
                self._store.execute("INSERT OR REPLACE INTO bodies (message_id, raw, fetched_at) VALUES (?, ?, ?)",
                                    (rows[0]["id"], raw, int(time.time())))
            ics = mime.calendar_of(mime.parse(raw))
            if ics:
                self._run.emit(lambda ics=ics: self.invitationArrived.emit(ics))

    def _sync_sent(self, conn, key):
        """Sent stays in the cache like the inbox: my replies belong to the conversations they answer."""
        sent = self._role_folder("sent", key)
        if sent is not None and sent["id"] != self._folder_id:
            self._sync_folder(conn, sent["id"])

    def _insert_headers(self, folder_id, headers):
        self._store.many(
            "INSERT OR REPLACE INTO messages (folder_id, uid, message_id, date_ts, from_name, from_email, recipients, "
            "subject, preview, seen, flagged, answered, attachments, size, in_reply_to, refs, tags) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(folder_id, h["uid"], h["message_id"], h["date"], h["from"]["name"], h["from"]["email"],
              json.dumps(h["to"] + h["cc"]), h["subject"], h["preview"], int(h["seen"]), int(h["flagged"]),
              int(h["answered"]), int(h["attachments"]), h["size"], h["in_reply_to"], h["references"],
              h.get("tags", "")) for h in headers])

    def _notify_new(self, fresh):
        """New mail while Plume is in the background: a desktop notification per message (3 at most)."""
        if not self._store.get("mail_notify", True):
            return
        for h in fresh[:3]:
            def show(h=h):
                if QGuiApplication.applicationState() != Qt.ApplicationState.ApplicationActive:
                    cloud.desktop_notify(h["from"]["name"] or h["from"]["email"], h["subject"], icon=QGuiApplication.desktopFileName() or "eu.orneos.plume")
            self._run.emit(show)

    def _forget_folders(self):
        self._folders_made = None

    def _emit_changed(self):
        self._folders_made = None
        self.changed.emit()

    @js_property(notify=changed)
    def folders(self):
        """The folder list. One mailbox: its folders, Favoris after the inbox. With external ones: the unified
        inbox and Favoris first, then each mailbox under its name (Orneos first), which folds. Special
        folders in their usual order, then the others by name; the tags in use come last.
        Made once per change: every line of the list reads it (the folder above it)."""
        if self._folders_made is None:
            self._folders_made = self._folder_list()
        return self._folders_made

    def _folder_list(self):
        several = any(k != ORNEOS for k in self._boxes)
        labels = {ORNEOS: self._box_label(ORNEOS) if several else ""} \
            | {c["key"]: self._box_label(c["key"]) for c in self._configs()}
        folded = set(self._store.get("mail_folded", []) or []) if several else set()
        hosts = {c["key"]: ((c.get("imap") or {}).get("host") or "").lower() for c in self._configs()}

        def entry(**values):
            return {"id": 0, "name": "", "full": "", "role": "", "unseen": 0, "total": 0, "depth": 0, "box": "", "emptiable": False,
                    "boxLabel": "", "folded": False, "tag": 0} | values
        flagged = self._store.query("SELECT COUNT(*) FROM messages WHERE flagged = 1")[0][0]
        star = entry(id=-1, role="flagged", total=flagged, box="" if several else ORNEOS)
        out = []
        for key in labels:
            if key != ORNEOS and key not in self._boxes:
                continue
            rows = self._store.query("SELECT * FROM mail_folders WHERE box = ? AND noselect = 0", (key,))
            if hosts.get(key, "").endswith(EXCHANGE_HOSTS):
                rows = [r for r in rows if (r["full"].split(r["delimiter"])[0] if r["delimiter"] else r["full"]).lower()
                        not in EXCHANGE_HIDDEN or r["role"] in ROLE_ORDER]
            # a role Plume has no place for (Dovecot's virtual "All"): an ordinary folder, under its own name
            entries = [entry(id=r["id"], name=r["name"], full=r["full"], role=r["role"] if r["role"] in ROLE_ORDER else "",
                             unseen=r["unseen"], emptiable=self._emptiable(r),
                             total=r["total"], depth=r["full"].count(r["delimiter"]) if r["delimiter"] else 0,
                             box=key, boxLabel=labels[key], folded=key in folded) for r in rows]
            special = sorted([f for f in entries if f["role"] in ROLE_ORDER], key=lambda f: ROLE_ORDER.index(f["role"]))
            seen_roles, unique = set(), []
            for f in special:
                if f["role"] not in seen_roles:
                    seen_roles.add(f["role"])
                    unique.append(f)
            others = sorted([f for f in entries if f not in unique], key=lambda f: f["full"].lower())
            # indented under the folders shown above it: one kept in the inbox (Outlook: "Inbox/À garder") sits
            # among the others, at the left, not under a parent that is not there
            shown, delimiters = {f["full"] for f in others}, {r["id"]: r["delimiter"] for r in rows}
            for f in others:
                delim = delimiters[f["id"]]
                parts = f["full"].split(delim) if delim else [f["full"]]
                f["depth"] = sum(delim.join(parts[:n]) in shown for n in range(1, len(parts)))
            if not several and unique and unique[0]["role"] == "inbox":
                unique.insert(1, star)
            out += unique + others
        if several:
            unseen = sum(f["unseen"] for f in out if f["role"] == "inbox")
            out = [entry(id=-2, role="allinbox", unseen=unseen), star] + out
        # the outbox shows only while something waits in it (no network, or the seconds of « Annuler »)
        waiting = len(self._queue.items(kind="send", owner=self._owner()))
        if waiting or self._folder_id == OUTBOX:
            at = next((i + 1 for i, f in enumerate(out) if f["role"] in ("inbox", "allinbox")), 0)
            out.insert(at, entry(id=OUTBOX, role="outbox", total=waiting, unseen=waiting, box="" if several else ORNEOS))
        counts = {}
        for r in self._store.query("SELECT tags, seen FROM messages WHERE tags != ''"):
            for tag in r["tags"].split():
                total, unseen = counts.get(tag, (0, 0))
                counts[tag] = (total + 1, unseen + (not r["seen"]))
        for number, tag in enumerate(imap.TAGS, start=1):
            if tag in counts:
                out.append(entry(id=TAG_FOLDER - number, role="tag", tag=number, total=counts[tag][0],
                                 unseen=counts[tag][1]))
        return out

    def _box_label(self, key):
        """A mailbox's name in the folder list: the one given to it, else its address (the sender's name, the
        "name" of a mailbox, is another thing)."""
        if key == ORNEOS:
            return self._store.get("mail_label_orneos") or self._account.get("address") or "Orneos"
        config = next((c for c in self._configs() if c["key"] == key), {})
        return config.get("label") or config.get("address", "")

    @Slot(str, result=str)
    def boxLabel(self, key):
        return self._box_label(key)

    @Slot(str, str)
    def renameBox(self, key, label):
        """Its name in the folder list; empty, or its own address, gives the address back."""
        label = " ".join(label.split())[:80]
        if key == ORNEOS:
            self._store.set("mail_label_orneos", "" if label.lower() == (self._account.get("address") or "").lower() else label)
        else:
            configs = self._configs()
            for config in configs:
                if config["key"] == key:
                    config["label"] = "" if label.lower() == config["address"].lower() else label
            self._save_configs(configs)
        self._emit_changed()
        self._reload_list()

    @Slot(str)
    def toggleBox(self, key):
        """A mailbox of the folder list folds (or unfolds) under its name; kept for the next launch."""
        folded = set(self._store.get("mail_folded", []) or [])
        folded ^= {key}
        self._store.set("mail_folded", sorted(folded))
        self._emit_changed()

    @Property(int, notify=changed)
    def inboxUnseen(self):
        keys = [k for k, b in self._boxes.items() if b.password is not None] or [ORNEOS]
        rows = self._store.query("SELECT SUM(unseen) FROM mail_folders WHERE role = 'inbox' "
                                 f"AND box IN ({','.join('?' * len(keys))})", keys)
        return int(rows[0][0] or 0)

    @Property(int, notify=changed)
    def folderId(self):
        return self._folder_id

    @Property(str, notify=changed)
    def folderRole(self):
        if self._folder_id == OUTBOX:
            return "outbox"
        if self._folder_id == -1:
            return "flagged"
        if self._folder_id == -2:
            return "inbox"
        if self._folder_id <= TAG_FOLDER:
            return "tag"
        folder = self._folder(self._folder_id)
        return folder["role"] if folder else ""

    @Slot(int)
    def selectFolder(self, folder_id):
        if folder_id != self._folder_id:
            self._folder_id = folder_id
            self._store.set("mail_folder", folder_id)
            self._query, self._server_hits = "", set()
            self._current, self._current_raw, self._current_thread = {}, None, None
            self.currentChanged.emit()
            self._emit_changed()
            self._reload_list()
        if folder_id > 0:
            self._queue_sync(folder_id, self._box_key(folder_id))
        elif folder_id == OUTBOX:
            self._flush_all()
        elif folder_id == -2:
            for key in list(self._boxes):
                self._job(lambda conn, k=key: self._sync_folder(conn, self._inbox_id(k)), key)

    @Slot()
    def loadMore(self):
        folder_id = self._folder_id
        if folder_id > 0:
            self._depth[folder_id] = self._depth.get(folder_id, 0) + PAGE
            self._job(lambda conn: self._sync_folder(conn, folder_id), self._box_key(folder_id))

    # ---- settings of the module -------------------------------------------------------------------------
    def _conversations(self):
        return bool(self._store.get("mail_threads", True))

    @Property(bool, notify=changed)
    def conversations(self):
        return self._conversations()

    @conversations.setter
    def conversations(self, value):
        self._store.set("mail_threads", bool(value))
        self._reload_list()

    @Property(bool, notify=changed)
    def notifyNew(self):
        return bool(self._store.get("mail_notify", True))

    @notifyNew.setter
    def notifyNew(self, value):
        self._store.set("mail_notify", bool(value))
        self._emit_changed()

    # ---- conversations --------------------------------------------------------------------------------
    def _threads(self):
        """{message id: conversation key}: messages of a mailbox linked by Message-ID, In-Reply-To and
        References, whatever their folder (a reply in Sent joins the message it answers). Kept until messages
        come or go: the list and each message opened ask for it."""
        mark = tuple(self._store.query("SELECT COUNT(*), MAX(id), SUM(id), SUM(uid), SUM(date_ts) FROM messages")[0])
        if self._threads_made is not None and self._threads_made[0] == mark:
            return self._threads_made[1]
        rows = self._store.query("SELECT m.id, m.message_id, m.in_reply_to, m.refs, f.box FROM messages m "
                                 "JOIN mail_folders f ON f.id = m.folder_id")
        parent = {}

        def find(x):
            root = x
            while parent[root] != root:
                root = parent[root]
            while parent[x] != root:
                parent[x], x = root, parent[x]
            return root
        node_of = {}
        for r in rows:
            own = (r["message_id"] or "").strip().lower() or f"#{r['id']}"
            node = f"{r['box']}:{own}"
            parent.setdefault(node, node)
            for ref in REF.findall(f"{r['refs'] or ''} {r['in_reply_to'] or ''}".lower()):
                other = f"{r['box']}:{ref}"
                parent.setdefault(other, other)
                a, b = find(node), find(other)
                if a != b:
                    parent[a] = b
            node_of[r["id"]] = node
        out = {i: find(n) for i, n in node_of.items()}
        self._threads_made = (mark, out)
        return out

    def _thread_members(self, row):
        """The messages of the conversation of this one (all folders of its mailbox, without what is in the
        bin or the junk folder unless the message is there too), newest first; [] when it is alone."""
        self._thread_of = self._threads()
        key = self._thread_of.get(row["id"])
        ids = [i for i, k in self._thread_of.items() if k == key]
        if len(ids) < 2:
            return []
        hidden = {"trash", "junk", "drafts"} - {row["role"]}
        found = self._store.query(
            "SELECT m.*, f.path, f.role, f.box FROM messages m JOIN mail_folders f ON f.id = m.folder_id "
            f"WHERE m.id IN ({','.join('?' * len(ids))})", ids)
        members, seen_ids = [], set()
        # the same message in two folders (a copy in Archive, a mail to oneself) shows once: the opened one first
        for r in sorted(found, key=lambda r: r["id"] != row["id"]):
            mid = (r["message_id"] or "").lower() or f"#{r['id']}"
            if r["role"] in hidden or mid in seen_ids or r["id"] in self._hidden:
                continue
            seen_ids.add(mid)
            members.append(r)
        members.sort(key=lambda r: (r["date_ts"], r["id"]), reverse=True)
        return members if len(members) > 1 else []

    @Slot(int, result="QVariantList")
    def threadIds(self, message_id):
        """The messages a list line stands for (its conversation in this folder): what actions move."""
        return self._members.get(message_id, [message_id])

    # ---- the list -----------------------------------------------------------------------------------
    @Property(QObject, constant=True)
    def model(self):
        return self._model

    @Property(int, notify=changed)
    def count(self):
        return self._model.rowCount()

    @Property(str, notify=changed)
    def query(self):
        return self._query

    @Property(bool, notify=changed)
    def everywhere(self):
        return self._everywhere

    @Slot(bool)
    def setEverywhere(self, value):
        if value != self._everywhere:
            self._everywhere = bool(value)
            self.search(self._query)

    def _search_folders(self):
        """Where the servers look: the folder shown; « everywhere », the main folders of every mailbox; the unified
        inbox, every inbox."""
        if self._everywhere:
            rows = self._store.query("SELECT id, box FROM mail_folders WHERE noselect = 0 AND role IN "
                                     "('inbox', 'sent', 'archive', 'drafts', '')")
            # Gmail's « All Mail » holds everything already: no need to read its labels one by one
            gmail = {r["box"] for r in self._store.query("SELECT box FROM mail_folders WHERE role = 'archive' AND "
                                                         "(path LIKE '[Gmail]%' OR path LIKE '[Google Mail]%')")}
            ids = [r["id"] for r in rows if r["box"] not in gmail or (self._folder(r["id"]) or {}).get("role") in ("archive", "sent")]
            return ids[:60]
        if self._folder_id > 0:
            return [self._folder_id]
        if self._folder_id == -2:
            return [i for i in (self._inbox_id(k) for k in self._boxes) if i]
        return []

    @Slot(str)
    def search(self, text):
        """Instant filter on what is cached, then the servers' own search (bodies too) joins in. Filters can be
        written in the field (de:, à:, objet:, avec:pj, est:non-lu, avant:, après:)."""
        self._query = text.strip()
        self._server_hits = set()
        self._reload_list()
        q = parse_query(self._query)
        if not self._query or not (any(len(w) >= 3 for w in q["words"]) or q["from"] or q["to"] or q["subject"]):
            return
        criteria, needle = imap_criteria(q), self._query
        for folder_id in self._search_folders():
            def run(conn, folder_id=folder_id):
                folder = self._folder(folder_id)
                if folder is None or self._query != needle:
                    return
                conn.select(folder["path"])
                uids = conn.search_criteria(criteria)[-200:]
                cached = {r["uid"] for r in self._store.query("SELECT uid FROM messages WHERE folder_id = ?", (folder_id,))}
                missing = [u for u in uids if u not in cached]
                if missing:
                    self._insert_headers(folder_id, conn.headers(missing))
                found = {r["id"] for r in self._store.query(
                    f"SELECT id FROM messages WHERE folder_id = ? AND uid IN ({','.join(str(int(u)) for u in uids) or '-1'})",
                    (folder_id,))}

                def apply():
                    if self._query == needle and found:
                        self._server_hits |= found
                        self._reload_list()
                self._run.emit(apply)
            self._job(run, self._box_key(folder_id), quiet=True)

    def _search_sql(self):
        """The WHERE part of a search on the cache, and its arguments: filters always, words in the headers and
        preview, or found by a server in the body."""
        q = parse_query(self._query)
        sql, args = "", []
        for field, columns in (("from", ("m.from_name", "m.from_email")), ("to", ("m.recipients",)), ("subject", ("m.subject",))):
            for value in q[field]:
                sql += " AND (" + " OR ".join(f"lower({c}) LIKE ?" for c in columns) + ")"
                args += ["%" + value.lower() + "%"] * len(columns)
        if q["unread"]:
            sql += " AND m.seen = 0"
        if q["read"]:
            sql += " AND m.seen = 1"
        if q["flagged"]:
            sql += " AND m.flagged = 1"
        if q["attachment"]:
            sql += " AND m.attachments = 1"
        if q["before"] is not None:
            sql += " AND m.date_ts < ?"
            args.append(int(q["before"]))
        if q["after"] is not None:
            sql += " AND m.date_ts >= ?"
            args.append(int(q["after"]))
        hits = ",".join(str(int(i)) for i in self._server_hits) or "-1"
        for word in q["words"]:
            sql += (" AND (lower(m.subject) LIKE ? OR lower(m.from_name) LIKE ? OR lower(m.from_email) LIKE ? "
                    f"OR lower(m.preview) LIKE ? OR lower(m.recipients) LIKE ? OR m.id IN ({hits}))")
            args += ["%" + word.lower() + "%"] * 5
        return sql, args

    def _outbox_rows(self):
        """The lines of the outbox: one per message waiting, newest first."""
        today = time.mktime(time.localtime()[:3] + (0, 0, 0, 0, 0, -1))
        rows, self._outbox_ids = [], {}
        for n, op in enumerate(reversed(self._queue.items(kind="send", owner=self._owner()))):
            fields = op.get("fields") or {}
            to = ", ".join(fields.get("to") or fields.get("cc") or fields.get("bcc") or [])
            planned = (op.get("fields") or {}).get("scheduled")
            stamp = int(planned) if planned else int(op["seq"][:20]) // 1_000_000_000
            row_id = OUTBOX_ROW - n
            self._outbox_ids[row_id] = op["id"]
            if planned:
                to = self._plume.t["scheduled_for"].replace("%1", self._when(planned)) + " · " + to
            rows.append({"messageId": row_id, "uid": 0, "fromName": to, "fromEmail": "", "initials": initials(to or "?"),
                         "subject": fields.get("subject") or "", "preview": " ".join((fields.get("body") or "").split())[:200],
                         "date": stamp, "seen": True, "flagged": False, "answered": False,
                         "attachments": bool(fields.get("attachments")), "tint": 0, "folderId": OUTBOX,
                         "section": "today" if stamp >= today else "older", "count": 1, "boxLabel": "", "tags": [],
                         "box": op["box"], "where": "outbox"})
        return rows

    def _outbox_take(self, row_id):
        """A message of the outbox back in the composer (to change it, or keep it as a draft)."""
        op_id = getattr(self, "_outbox_ids", {}).get(row_id)
        op = self._queue.get(op_id) if op_id else None
        if op is None or op.get("smtp_done") or op_id in self._running:
            return None
        timer = self._send_timers.pop(op_id, None)
        if timer is not None:
            timer.stop()
        self._queue.remove(op_id)
        self._reload_list()
        return dict(op.get("fields") or {}, drop=op.get("drop"))

    def _reload_list(self):
        if self._folder_id == OUTBOX:
            rows = self._outbox_rows()
            self._members = {r["messageId"]: [r["messageId"]] for r in rows}
            self._model.set_rows(rows)
            self._emit_changed()
            return
        base = "SELECT m.*, f.role, f.box FROM messages m JOIN mail_folders f ON f.id = m.folder_id"
        if self._query and self._everywhere:
            sql, args = base + " WHERE 1 = 1", []
        elif self._folder_id == -1:
            sql, args = base + " WHERE m.flagged = 1", []
        elif self._folder_id == -2:
            sql, args = base + " WHERE f.role = 'inbox'", []
        elif self._folder_id <= TAG_FOLDER:
            sql, args = base + " WHERE (' ' || m.tags || ' ') LIKE ?", [f"% {imap.TAGS[TAG_FOLDER - self._folder_id - 1]} %"]
        else:
            sql, args = base + " WHERE m.folder_id = ?", [self._folder_id]
        if self._unread_only:
            sql += " AND m.seen = 0"
        if self._query:
            more, more_args = self._search_sql()
            sql += more
            args += more_args
        sql += " ORDER BY m.date_ts DESC, m.uid DESC"
        rows = self._store.query(sql, args)
        role = self.folderRole
        grouping = self._conversations() and role not in ("drafts", "sent")
        sizes = {}
        if grouping:
            self._thread_of = self._threads()
            hidden = {"trash", "junk", "drafts"} - {role}
            for r in self._store.query("SELECT m.id, m.message_id, f.role FROM messages m "
                                       "JOIN mail_folders f ON f.id = m.folder_id"):
                if r["role"] not in hidden and r["id"] not in self._hidden:
                    key = self._thread_of.get(r["id"])
                    sizes.setdefault(key, set()).add((r["message_id"] or "").lower() or f"#{r['id']}")
        today = time.mktime(time.localtime()[:3] + (0, 0, 0, 0, 0, -1))
        week = today - time.localtime().tm_wday * 86400
        out, by_key, members = [], {}, {}
        # the folders that gather several mailboxes say which one each message came to
        several = self._folder_id < 0 and any(k != ORNEOS for k in self._boxes)
        labels = {c["key"]: self._box_label(c["key"]) for c in self._configs()} if several else {}
        # a search everywhere says the folder of each message (and its mailbox when there are several)
        where_of = {}
        if self._query and self._everywhere:
            boxes = any(k != ORNEOS for k in self._boxes)
            for f in self._store.query("SELECT id, name, role, box FROM mail_folders"):
                name = self._plume.t.get("folder_" + f["role"], f["name"]) if f["role"] else f["name"]
                where_of[f["id"]] = (self._box_label(f["box"]) + " · " + name) if boxes else name
        for r in rows:
            if r["id"] in self._hidden:
                continue
            key = self._thread_of.get(r["id"]) if grouping else None
            lead = by_key.get(key) if key is not None else None
            if lead is not None:
                # an older message of a conversation already listed: it only adds to that line
                members[lead["messageId"]].append(r["id"])
                lead["seen"] = lead["seen"] and bool(r["seen"])
                lead["flagged"] = lead["flagged"] or bool(r["flagged"])
                lead["attachments"] = lead["attachments"] or bool(r["attachments"])
                lead["tags"] = sorted(set(lead["tags"]) | set(self._tag_numbers(r["tags"])))
                continue
            stamp = r["date_ts"]
            section = "today" if stamp >= today else "yesterday" if stamp >= today - 86400 else \
                "week" if stamp >= week else "older"
            name = r["from_name"] or r["from_email"]
            row = {"messageId": r["id"], "uid": r["uid"], "fromName": name, "fromEmail": r["from_email"],
                   "initials": initials(name), "subject": r["subject"], "preview": r["preview"],
                   "date": r["date_ts"], "seen": bool(r["seen"]), "flagged": bool(r["flagged"]),
                   "answered": bool(r["answered"]), "attachments": bool(r["attachments"]),
                   "tint": zlib.crc32((r["from_email"] or name).encode()) % 4, "folderId": r["folder_id"],
                   "section": section, "count": max(1, len(sizes.get(key, ()))),
                   "boxLabel": where_of.get(r["folder_id"]) or (labels.get(r["box"]) or self._store.get("mail_label_orneos") or "Orneos" if labels else ""),
                   "tags": self._tag_numbers(r["tags"]),
                   "box": r["box"], "where": r["role"]}
            out.append(row)
            members[r["id"]] = [r["id"]]
            if key is not None:
                by_key[key] = row
        self._members = members
        self._model.set_rows(out)
        self._emit_changed()

    @Property(bool, notify=changed)
    def unreadOnly(self):
        return self._unread_only

    @Slot(bool)
    def setUnreadOnly(self, value):
        if value != self._unread_only:
            self._unread_only = value
            self._reload_list()

    @Property(bool, notify=changed)
    def hasMore(self):
        if self._folder_id <= 0 or self._query or self._unread_only:
            return False
        folder = self._folder(self._folder_id)
        return bool(folder) and folder["total"] > sum(len(m) for m in self._members.values())

    @Slot(int, result=int)
    def idAt(self, row):
        item = self._model.row(row)
        return item["messageId"] if item else 0

    @Slot(int, result=int)
    def rowOf(self, message_id):
        """The line of this message: its own, or the line of its conversation."""
        found = self._model.index_of(message_id)
        if found >= 0:
            return found
        lead = next((lead for lead, ids in self._members.items() if message_id in ids), None)
        return self._model.index_of(lead) if lead is not None else -1

    # ---- one message, or a conversation -----------------------------------------------------------------
    @js_property(notify=currentChanged)
    def current(self):
        return self._current

    @Slot(str, result=str)
    def pageUrl(self, page):
        """A page too large for a data: URL (Chromium stops at 2 MB: a long thread with its quotes and
        inline pictures, shown blank) goes through a private file. "" when loadHtml can take it."""
        data = page.encode("utf-8")
        if len(data) < 1_500_000:
            return ""
        folder = system.runtime_dir() / "plume"
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        for old in folder.glob("page-*.html"):
            old.unlink(missing_ok=True)
        path = folder / f"page-{uuid.uuid4().hex}.html"      # a new name: the view never reuses the last one
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as out:
            out.write(data)
        return path.as_uri()

    def _message(self, message_id):
        rows = self._store.query("SELECT m.*, f.path, f.role, f.box FROM messages m JOIN mail_folders f ON f.id = m.folder_id "
                                 "WHERE m.id = ?", (message_id,))
        return rows[0] if rows else None

    @Slot()
    def close(self):
        """Nothing opened any more (the line clicked again)."""
        self._current, self._current_raw, self._current_thread = {}, None, None
        self.currentChanged.emit()

    @Slot(int)
    def open(self, message_id):
        if message_id <= OUTBOX_ROW:
            fields = self._outbox_take(message_id)
            self.close()
            if fields is not None:
                self.sendCancelled.emit(fields)
            return
        row = self._message(message_id)
        if row is None:
            self.close()
            return
        members = self._thread_members(row) if self._conversations() and row["role"] != "drafts" else []
        self._current = {"messageId": message_id, "loading": True, "subject": row["subject"],
                         "from": {"name": row["from_name"], "email": row["from_email"]}, "flagged": bool(row["flagged"]),
                         "role": row["role"], "box": row["box"], "wasUnseen": not row["seen"], "count": len(members) or 1}
        self._current_thread = None
        self.currentChanged.emit()
        unread = {m["id"] for m in members if not m["seen"]}
        ids = [m["id"] for m in members] or [message_id]
        self._read_memo = {k: v for k, v in self._read_memo.items() if k[0] in ids}   # one conversation kept read
        thread = [dict(m) | {"unread": m["id"] in unread} for m in members]

        def loaded(raws, partial=False):
            if self._current.get("messageId") != message_id:
                return
            if message_id in raws:
                if members:
                    self._current_thread = (thread, raws)
                try:
                    self._show(message_id, raws[message_id], partial=partial)
                    return
                except Exception:       # a message Python cannot read must not spin forever
                    pass
            # offline, gone from the server, unreadable: said, with « Try again »
            self._current = dict(self._current, loading=False, failed=True)
            self.currentChanged.emit()

        others = [i for i in ids if i != message_id]
        if len(others) < THREAD_AT_ONCE:
            self._load_raws(ids, loaded)
        else:
            # a long conversation: the message opened shows first, the others (read, laid out) join it after
            def first(raws):
                if self._current.get("messageId") != message_id:
                    return
                if message_id not in raws:
                    loaded(raws)
                    return
                loaded(raws, partial=True)
                self._load_raws(others, lambda more: loaded({**raws, **more}))
            self._load_raws([message_id], first)
        # the conversation is read: its unread messages in this folder (and the one opened), at once or after the
        # few seconds of the setting (going down the list with ↓ then leaves what was only glanced at unread)
        to_mark = [m["id"] for m in members if not m["seen"] and m["folder_id"] == row["folder_id"]]
        if not row["seen"] and message_id not in to_mark:
            to_mark.append(message_id)
        self._read_timer.stop()
        delay = int(self._store.get("pref_mail_read_delay", 0) or 0)
        if to_mark and delay > 0:
            self._to_read = [message_id] + to_mark
            self._read_timer.start(delay * 1000)
        elif to_mark:
            self._store_flag(to_mark, "seen", "\\Seen", True)

    def _mark_shown_read(self):
        if self._to_read and self._current.get("messageId") == self._to_read[0]:
            self._store_flag(self._to_read[1:], "seen", "\\Seen", True)
        self._to_read = []

    def _load_raws(self, ids, done):
        """The whole messages (from the cache, else the server), then done({id: raw}) on the main thread."""
        raws = {r["message_id"]: r["raw"] for r in self._store.query(
            f"SELECT message_id, raw FROM bodies WHERE message_id IN ({','.join('?' * len(ids))})", ids)}
        missing = [r for r in (self._message(i) for i in ids if i not in raws) if r is not None]
        if not missing:
            done(raws)
            return
        by_box = {}
        for r in missing:
            by_box.setdefault(r["box"], []).append(r)
        left = [len(by_box)]

        def fetch(conn, rows):
            by_path = {}
            for r in rows:
                by_path.setdefault(r["path"], []).append(r)
            for path, in_folder in by_path.items():      # a conversation: one command per folder
                conn.select(path, refresh=False)
                got = conn.messages([r["uid"] for r in in_folder])
                kept = []
                for r in in_folder:
                    if r["uid"] in got:
                        raws[r["id"]] = got[r["uid"]]
                        kept.append((r["id"], got[r["uid"]], int(time.time())))
                if kept:
                    self._store.many("INSERT OR REPLACE INTO bodies (message_id, raw, fetched_at) VALUES (?, ?, ?)", kept)
            self._store.execute("DELETE FROM bodies WHERE message_id NOT IN "
                                f"(SELECT message_id FROM bodies ORDER BY fetched_at DESC LIMIT {BODIES})")

        # each box answers once, even offline or when its worker gave up: the reader never waits forever
        def finished():
            left[0] -= 1
            if left[0] == 0:
                done(raws)
        for key, rows in by_box.items():
            self._job(lambda conn, rows=rows: fetch(conn, rows), key, after=finished, read=True)

    def _trusted(self, sender):
        return sender.lower() in set(self._store.get("trusted_senders", []))

    def _labels(self):
        t = self._plume.t
        return {"reply": t["reply"], "all": t["reply_all"], "forward": t["forward"], "to": t["to_label"],
                "cc": t["cc_label"], "bcc": t["bcc_label"], "reply_to": t["reply_to_label"], "quote": t["quote_show"], "more_files": t["files_more"]}

    def _show(self, message_id, raw, images=None, partial=False):
        """partial: only the opened message is here yet; the others are their line of the list, folded."""
        if self._current.get("messageId") != message_id:
            return
        row = self._message(message_id)
        sender = row["from_email"] if row else ""
        thread = self._current_thread
        if images is None:
            # pictures load on their own when every other writer of the conversation is trusted (my own
            # messages always are: my signature has pictures too)
            senders = [m["from_email"] for m in thread[0]] if thread else [sender]
            others = [s for s in senders if s and s.lower() not in self._me()]
            allowed = all(self._trusted(s) for s in others)
        else:
            allowed = images
        known = {"messageId": message_id, "loading": False, "flagged": bool(row["flagged"]) if row else False,
                 "wasUnseen": bool(self._current.get("wasUnseen")),
                 "role": row["role"] if row else "", "box": row["box"] if row else ORNEOS,
                 "imagesShown": allowed, "trusted": self._trusted(sender),
                 "count": 1, "tags": self._tags_of(self.threadIds(message_id))}
        unsubscribed = (self._store.get("unsubscribed", {}) or {}).get(sender.lower())
        dark, me, lang, labels, me_label = self._theme.dark, self._me(), self._plume.lang, self._labels(), self._plume.t["me"]
        self._shown_seq += 1
        seq = self._shown_seq
        memo = self._read_memo

        def parsed(mid, data, whole):
            # a message read once is not read again (images shown, the theme changed, the rest of the thread in)
            key = (mid, len(data), allowed, dark, whole)
            if key not in memo:
                memo[key] = mime.read(data, images=allowed, dark=dark, whole=whole)
            return dict(memo[key])

        def stub(m):
            when = datetime.datetime.fromtimestamp(m["date_ts"]).astimezone().isoformat() if m["date_ts"] else ""
            return {"from": {"name": m["from_name"], "email": m["from_email"]}, "date": when, "text": m["preview"] or "",
                    "attachments": [], "fragment": "", "pictures": {}}

        def read():
            info = parsed(message_id, raw, True)
            info.update(known)
            if info.get("calendar"):
                # Ornis reads the invitation's real times too (the mail's text often has none, or another zone)
                info["inviteText"] = ical.invitation_text(ical.invitation(info["calendar"]))
            if info.get("unsubscribe"):
                info["unsubscribe"] = dict(info["unsubscribe"], state="done" if unsubscribed else "")
            if thread:
                members, raws = thread
                items = []
                for index, m in enumerate(members):
                    here = m["id"] == message_id
                    if partial and not here:
                        one = stub(m)
                    elif m["id"] in raws:
                        one = info if here else parsed(m["id"], raws[m["id"]], False)
                    else:
                        continue
                    mine = m["role"] == "sent" or (m["from_email"] or "").lower() in me
                    items.append({"id": m["id"], "info": one, "mine": mine, "unread": m["unread"],
                                  "open": here or (not partial and (index == 0 or m["unread"]))})
                if len(items) > 1:
                    info["html"] = mime.conversation(items, dark=dark, images=allowed, lang=lang, labels=labels)
                    info["remote"] = sum(i["info"].get("remote", 0) for i in items)
                    info["count"] = len(items)
                    info["participants"] = self._participants(items, me_label)
                    if partial:
                        info["partial"] = True
                    else:
                        info["threadText"] = mime.thread_text(list(reversed(items)))
            info.pop("fragment", None)          # the page has them: QML gets the page only
            info.pop("pictures", None)
            return info

        def apply(info):
            if seq != self._shown_seq or self._current.get("messageId") != message_id:
                return                  # another message opened meanwhile
            if info is None:            # a message Python cannot read must not spin forever
                self._current = dict(self._current, loading=False, failed=True)
                self.currentChanged.emit()
                return
            self._current, self._current_raw = info, raw
            self.currentChanged.emit()
            if info.get("calendar") and info.get("role") not in ("sent", "drafts", "trash"):
                self.invitationArrived.emit(info["calendar"])

        # reading a long conversation and laying it out takes a few hundred ms: not on the window's thread
        def run():
            try:
                info = read()
            except Exception:  # noqa: BLE001
                info = None
            self._run.emit(lambda: apply(info))
        threading.Thread(target=run, daemon=True, name="plume-read").start()

    def _participants(self, items, me_label):
        """Who writes in a conversation, oldest first (« moi » for the person themself)."""
        names, seen = [], set()
        for item in reversed(items):
            sender = item["info"].get("from") or {}
            label = me_label if item["mine"] else (sender.get("name") or sender.get("email") or "").split(" ")[0]
            if label and label.lower() not in seen:
                seen.add(label.lower())
                names.append(label)
        return names

    @Slot(bool)
    def showImages(self, always):
        if not self._current_raw:
            return
        if always:
            trusted = set(self._store.get("trusted_senders", []))
            members = self._current_thread[0] if self._current_thread else []
            for sender in [self._current.get("from", {}).get("email", "")] + [m["from_email"] for m in members]:
                if sender and sender.lower() not in self._me():
                    trusted.add(sender.lower())
            self._store.set("trusted_senders", sorted(trusted))
        self._show(self._current["messageId"], self._current_raw, images=True)

    @Property("QVariantList", notify=changed)
    def trustedSenders(self):
        """The senders whose pictures load on their own (« Toujours pour cet expéditeur »)."""
        return sorted(self._store.get("trusted_senders", []) or [])

    @Slot(str)
    def untrust(self, sender):
        trusted = [s for s in self._store.get("trusted_senders", []) or [] if s != sender.lower()]
        self._store.set("trusted_senders", trusted)
        self._emit_changed()
        if self._current_raw and (self._current.get("from") or {}).get("email", "").lower() == sender.lower():
            self._show(self._current["messageId"], self._current_raw)

    # ---- « Me le rappeler »: a conversation put away until a time, back in the inbox (unread) then ----------
    def _snoozed(self):
        try:
            items = json.loads(SNOOZED.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            items = []
        return [i for i in items if isinstance(i, dict) and i.get("mid")]

    def _save_snoozed(self, items):
        system.private_write(SNOOZED, json.dumps(items, ensure_ascii=False))

    @Slot("QVariantList", float)
    def snooze(self, leads, until):
        """The conversations of these lines go to the « Plus tard » folder (Snoozed) until « until »."""
        ids = self._lines([int(i) for i in (leads.toVariant() if hasattr(leads, "toVariant") else leads)])
        rows = [r for r in self._rows(ids) if r["message_id"]]
        if not rows or until <= time.time():
            return
        items = self._snoozed() + [{"box": r["box"], "mid": r["message_id"], "until": float(until), "subject": r["subject"],
                                    "owner": self._owner()} for r in rows]
        self._save_snoozed(items)
        self.moveTo([r["id"] for r in rows], "snoozed")
        self._plume.toast.emit(self._plume.t["snoozed_until"].replace("%1", self._when(until)))

    def _wake_snoozed(self):
        """What was put away and whose time came: back in the inbox, unread, with a notification."""
        if self._state != "ready" or self._passive:
            return
        items, now, owner = self._snoozed(), time.time(), self._owner()
        due = [i for i in items if i["until"] <= now and i.get("owner", owner) == owner and i["box"] in self._boxes]
        if not due:
            return
        self._save_snoozed([i for i in items if i not in due])
        for i in due:
            self._enqueue({"box": i["box"], "kind": "unsnooze", "mid": i["mid"]})
        subjects = list(dict.fromkeys(i["subject"] or self._plume.t["subject_empty"] for i in due))
        if self._store.get("mail_notify", True):
            cloud.desktop_notify(self._plume.t["snooze_back"], " · ".join(subjects[:3]),
                                 icon=QGuiApplication.desktopFileName() or "eu.orneos.plume")

    @Slot(str, result="QVariantList")
    def laterOptions(self, kind):
        """The usual moments for « Envoyer plus tard » (kind "send") or « Me le rappeler » ("snooze"):
        [{label, at}], each in the future."""
        now = time.time()
        today = time.localtime()

        def at(days, hour):
            return time.mktime((today.tm_year, today.tm_mon, today.tm_mday + days, hour, 0, 0, 0, 0, -1))
        t = self._plume.t
        out = []
        if kind == "snooze" and today.tm_hour < 17:
            out.append({"label": t["later_evening"], "at": at(0, 18)})
        out.append({"label": t["later_tomorrow"], "at": at(1, 8)})
        weekday = today.tm_wday                      # 0 = Monday
        if kind == "snooze" and weekday < 4:
            out.append({"label": t["later_weekend"], "at": at(5 - weekday, 9)})
        monday = 7 - weekday
        if monday > 1:
            out.append({"label": t["later_monday"], "at": at(monday, 8)})
        return [o for o in out if o["at"] > now + 60]

    # ---- templates: answers written once, used again ----------------------------------------------------
    @Property("QVariantList", notify=changed)
    def templates(self):
        try:
            items = json.loads(TEMPLATES.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            items = []
        return [i for i in items if isinstance(i, dict) and i.get("name")]

    @Slot(str, "QVariantMap")
    def saveTemplate(self, name, fields):
        fields = self._plain(fields)
        name = name.strip()
        if not name:
            return
        items = [i for i in self.templates if i["name"].lower() != name.lower()]
        items.append({"name": name, "subject": fields.get("subject", ""), "html": fields.get("html", ""), "text": fields.get("body", "")})
        system.private_write(TEMPLATES, json.dumps(sorted(items, key=lambda i: i["name"].lower()), ensure_ascii=False))
        self._emit_changed()
        self._plume.toast.emit(self._plume.t["template_saved"].replace("%1", name))

    @Slot(str)
    def deleteTemplate(self, name):
        items = [i for i in self.templates if i["name"] != name]
        system.private_write(TEMPLATES, json.dumps(items, ensure_ascii=False))
        self._emit_changed()

    # ---- the automatic reply: set on the Orneos account (its page), the server answers even when all is off --
    @Slot()
    def openAutoreply(self):
        lang = self._plume.lang if self._plume.lang in ("fr", "en", "de") else "fr"
        slug = {"fr": "tableau-de-bord/compte", "en": "dashboard/account", "de": "dashboard/konto"}[lang]
        cloud.open_url(f"https://orneos.eu/{lang}/{slug}#mail")

    # ---- folders of a mailbox: made, renamed, deleted here (the special ones never) --------------------
    def _folder_job(self, key, fn, done_text):
        """A change of folders, on the server first (it may refuse: the name is taken, not allowed); said when
        done, the list read again."""
        failed = []

        def run(conn):
            try:
                fn(conn)
            except imap.MailError as error:
                if error.kind != "server":
                    raise
                failed.append(True)
            self._sync_folders(conn, key)

        def after():
            self._plume.toast.emit(self._plume.t["folder_failed"] if failed else done_text)
        self._job(run, key, after=after)

    def _new_path(self, key, parent_id, name):
        name = name.strip().replace("/", "-")
        parent = self._folder(parent_id) if parent_id and parent_id > 0 else None
        rows = self._store.query("SELECT delimiter FROM mail_folders WHERE box = ? AND delimiter != '' LIMIT 1", (key,))
        delim = (parent["delimiter"] if parent and parent["delimiter"] else rows[0]["delimiter"] if rows else "/")
        encoded = imap.imap_utf7_encode(name.replace(delim, "-"))
        return (parent["path"] + delim + encoded) if parent else encoded

    @Slot(str, int, str)
    def createFolder(self, key, parent_id, name):
        """A new folder in a mailbox, at its top or inside another one."""
        if not name.strip() or key not in self._boxes:
            return
        path = self._new_path(key, parent_id, name)
        self._folder_job(key, lambda conn: conn.make_folder(path), self._plume.t["folder_created"].replace("%1", name.strip()))

    @Slot(int, str)
    def renameFolder(self, folder_id, name):
        folder = self._folder(folder_id)
        if folder is None or folder["role"] in ROLE_ORDER or not name.strip():
            return
        delim = folder["delimiter"]
        parent_path = folder["path"].rsplit(delim, 1)[0] if delim and delim in folder["path"] else ""
        encoded = imap.imap_utf7_encode(name.strip().replace("/", "-").replace(delim or "/", "-"))
        new_path = (parent_path + delim + encoded) if parent_path else encoded
        if self._folder_id == folder_id:
            self.selectFolder(self._inbox_id(folder["box"]))
        self._folder_job(folder["box"], lambda conn: conn.rename_folder(folder["path"], new_path),
                         self._plume.t["folder_renamed"].replace("%1", name.strip()))

    @Slot(int)
    def deleteFolder(self, folder_id):
        """A folder and what it holds (asked first, with how many messages)."""
        folder = self._folder(folder_id)
        if folder is None or folder["role"] in ROLE_ORDER:
            return
        if self._folder_id == folder_id:
            self.selectFolder(self._inbox_id(folder["box"]))
        self._store.execute("DELETE FROM messages WHERE folder_id = ?", (folder_id,))
        self._folder_job(folder["box"], lambda conn: conn.delete_folder(folder["path"]),
                         self._plume.t["folder_deleted"].replace("%1", folder["name"]))

    # ---- flags and moves ----------------------------------------------------------------------------
    def _rows(self, ids):
        rows = [self._message(i) for i in ids]
        return [r for r in rows if r is not None]

    @Slot(int, bool)
    def setSeen(self, message_id, seen):
        self._store_flag(self.threadIds(message_id), "seen", "\\Seen", seen)

    @Slot(int, bool)
    def setFlagged(self, message_id, flagged):
        self._store_flag([message_id], "flagged", "\\Flagged", flagged)
        if self._current.get("messageId") == message_id:
            self._current = dict(self._current, flagged=flagged)
            self.currentChanged.emit()

    @staticmethod
    def _tag_numbers(text):
        """"$label1 $label4" → [1, 4]"""
        words = (text or "").split()
        return [n for n, tag in enumerate(imap.TAGS, start=1) if tag in words]

    def _tags_of(self, ids):
        rows = self._store.query(f"SELECT tags FROM messages WHERE id IN ({','.join('?' * len(ids))})", list(ids)) if ids else []
        return sorted({n for r in rows for n in self._tag_numbers(r["tags"])})

    @Slot(int, int, bool)
    def setTag(self, message_id, number, on):
        """Tag 1 … 5 (Important, Work, Personal, To do, Later) on a list line (its whole conversation): the
        IMAP keywords $label1 … $label5, which the cloud's Mail app and Thunderbird show too."""
        self._set_tag(self.threadIds(message_id), number, on)

    # ---- several lines at once (the list's selection) -----------------------------------------------
    def _lines(self, leads):
        """The messages several list lines stand for, each once."""
        out = []
        for lead in leads:
            out += [i for i in self.threadIds(int(lead)) if i not in out]
        return out

    @Slot("QVariantList", result="QVariantList")
    def threadsIds(self, leads):
        return self._lines(leads)

    @Slot("QVariantList", result="QVariantMap")
    def selectionInfo(self, leads):
        """What the menu of a selection offers: read (if all are), Favori (if all are), the tags all of them
        have, and their mailbox and folder role when they share one (moving stays within a mailbox)."""
        rows = [r for r in (self._model.row(self._model.index_of(int(lead))) for lead in leads) if r]
        if not rows:
            return {}
        tags = set(rows[0]["tags"] or [])
        for r in rows[1:]:
            tags &= set(r["tags"] or [])
        boxes, roles = {r["box"] for r in rows}, {r["where"] for r in rows}
        return {"seen": all(r["seen"] for r in rows), "flagged": all(r["flagged"] for r in rows), "tags": sorted(tags),
                "box": boxes.pop() if len(boxes) == 1 else "", "role": roles.pop() if len(roles) == 1 else ""}

    @Slot("QVariantList", bool)
    def setSeenMany(self, leads, seen):
        self._store_flag(self._lines(leads), "seen", "\\Seen", seen)

    @Slot("QVariantList", bool)
    def setFlaggedMany(self, leads, flagged):
        ids = [int(lead) for lead in leads]
        self._store_flag(ids, "flagged", "\\Flagged", flagged)
        if self._current.get("messageId") in ids:
            self._current = dict(self._current, flagged=flagged)
            self.currentChanged.emit()

    @Slot("QVariantList", int, bool)
    def setTagMany(self, leads, number, on):
        self._set_tag(self._lines(leads), number, on)

    def _set_tag(self, ids, number, on):
        if not 1 <= number <= len(imap.TAGS):
            return
        keyword = imap.TAGS[number - 1]
        rows = self._rows(ids)
        for r in rows:
            words = set((r["tags"] or "").split())
            words = words | {keyword} if on else words - {keyword}
            self._store.execute("UPDATE messages SET tags = ? WHERE id = ?",
                                (" ".join(t for t in imap.TAGS if t in words), r["id"]))
        if self._folder_id <= TAG_FOLDER:
            self._reload_list()
        else:
            touched = {r["id"] for r in rows}
            for lead, members in self._members.items():
                if touched & set(members):
                    self._model.update(lead, tags=self._tags_of(members))
        opened = self._current.get("messageId")
        if opened in {r["id"] for r in rows}:
            self._current = dict(self._current, tags=self._tags_of(self.threadIds(opened)))
            self.currentChanged.emit()
        self._emit_changed()
        self._write_flag(rows, keyword, on)
        if keyword == imap.TAGS[3]:
            self._to_do(rows, on)

    def _to_do(self, rows, on):
        """« À faire » on a conversation: a task in Tâches at once (the cloud makes it, linked to the latest
        message; the orneos app keeps both in step afterwards), or the task completed when the tag goes."""
        account = self._plume.account()
        if account is None:
            return
        latest = {}
        for r in rows:
            lead = next((lead for lead, ids in self._members.items() if r["id"] in ids), r["id"])
            if r["message_id"] and (lead not in latest or r["date_ts"] > latest[lead]["date_ts"]):
                latest[lead] = r
        if not latest:
            return
        server, user, password = account

        def run():
            sent = False
            for r in latest.values():
                status, _ = cloud.rest(server, user, password, "/index.php/apps/orneos/api/mail-todos/tag", method="POST",
                                       body={"messageId": r["message_id"], "on": bool(on), "subject": r["subject"] or "",
                                             "from": r["from_name"] or r["from_email"] or "", "preview": r["preview"] or ""})
                sent = sent or status == 200
            if sent and system.has_app("tasks"):
                # Tâches reads the new task now rather than at its next sync
                system.launch("tasks", "--refresh")
        threading.Thread(target=run, daemon=True).start()

    @Slot(str, result=bool)
    def openByMessageId(self, message_id):
        """The message with this Message-ID (from a task of Tâches): its folder, then the message itself."""
        bare = message_id.strip().strip("<>")
        rows = self._store.query("SELECT m.id, m.folder_id, f.role FROM messages m JOIN mail_folders f ON f.id = m.folder_id "
                                 "WHERE m.message_id IN (?, ?, ?) ORDER BY CASE f.role WHEN 'inbox' THEN 0 WHEN 'trash' THEN 2 "
                                 "ELSE 1 END, m.date_ts DESC LIMIT 1", (message_id, bare, f"<{bare}>"))
        if not rows:
            self._plume.toast.emit(self._plume.t["message_not_here"])
            return False
        self.selectFolder(rows[0]["folder_id"])
        self.reveal.emit(rows[0]["id"])
        return True

    @staticmethod
    def _emptiable(folder):
        """The trash, the junk, the archive. Not Gmail's: its archive is « All Mail », every message of the
        mailbox, the inbox's too."""
        if folder["role"] == "archive":
            return not folder["path"].startswith(("[Gmail]", "[Google Mail]"))
        return folder["role"] in ("trash", "junk")

    @Slot(int)
    def emptyFolder(self, folder_id):
        """The trash, the junk or the archive emptied (its menu in the list, after a confirmation): the cache at
        once, then every message of the folder on the server, not only what is cached. Other folders never are."""
        folder = self._folder(folder_id) if folder_id > 0 else None
        if folder is None or not self._emptiable(folder):
            return
        self._store.execute("DELETE FROM messages WHERE folder_id = ?", (folder_id,))
        self._store.execute("UPDATE mail_folders SET total = 0, unseen = 0 WHERE id = ?", (folder_id,))

        self._enqueue({"box": folder["box"], "kind": "empty", "path": folder["path"]})
        self._reload_list()
        self._emit_changed()

    @Slot(int)
    def markAllRead(self, folder_id):
        """Every message of a folder read (its menu in the list): the cache at once, then the whole folder on
        the server (not only what is cached). On Favoris or a tag: the messages it shows."""
        if folder_id > 0 or folder_id == -2:
            ids = [folder_id] if folder_id > 0 else [self._inbox_id(k) for k in self._boxes]
            for folder in [f for f in (self._folder(i) for i in ids) if f]:
                self._store.execute("UPDATE messages SET seen = 1 WHERE folder_id = ?", (folder["id"],))
                self._store.execute("UPDATE mail_folders SET unseen = 0 WHERE id = ?", (folder["id"],))
                self._enqueue({"box": folder["box"], "kind": "flag_all", "path": folder["path"]})
            self._reload_list()
            return
        if folder_id == -1:
            rows = self._store.query("SELECT id FROM messages WHERE flagged = 1 AND seen = 0")
        elif folder_id <= TAG_FOLDER:
            rows = self._store.query("SELECT id FROM messages WHERE seen = 0 AND (' ' || tags || ' ') LIKE ?",
                                     (f"% {imap.TAGS[TAG_FOLDER - folder_id - 1]} %",))
        else:
            rows = []
        if rows:
            self._store_flag([r["id"] for r in rows], "seen", "\\Seen", True)

    def _store_flag(self, ids, column, flag, on):
        rows = self._rows(ids)
        for r in rows:
            self._store.execute(f"UPDATE messages SET {column} = ? WHERE id = ?", (int(on), r["id"]))
            if column == "seen" and r["seen"] != int(on):
                self._store.execute("UPDATE mail_folders SET unseen = MAX(0, unseen + ?) WHERE id = ?",
                                    (-1 if on else 1, r["folder_id"]))
        touched = {r["id"] for r in rows}
        for lead, members in self._members.items():
            if touched & set(members):
                values = [bool(v[0]) for v in self._store.query(
                    f"SELECT {column} FROM messages WHERE id IN ({','.join('?' * len(members))})", members)]
                self._model.update(lead, **{column: all(values) if column == "seen" else any(values)})
        self._emit_changed()
        self._write_flag(rows, flag, on)

    def _write_flag(self, rows, flag, on):
        """The server follows a flag changed in the window (through the queue: offline, it waits)."""
        for key, by_path in self._by_box(rows).items():
            self._enqueue({"box": key, "kind": "flag", "by_path": by_path, "flag": flag, "on": bool(on)})

    @staticmethod
    def _by_box(rows):
        """{box: {folder path: [uids]}}"""
        out = {}
        for r in rows:
            out.setdefault(r["box"], {}).setdefault(r["path"], []).append(r["uid"])
        return out

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

    @Slot("QVariantList", str)
    def moveTo(self, ids, role):
        """archive, trash, junk, inbox (not spam), or a folder id as text. In the trash, delete for good.
        The list changes at once; the server follows a few seconds later, unless cancelMove() undoes it."""
        outbox = [int(i) for i in ids if int(i) <= OUTBOX_ROW]
        if outbox and role == "trash":
            taken = [row_id for row_id in outbox if self._outbox_take(row_id) is not None]
            if taken:
                self._plume.toast.emit(self._plume.t["outbox_deleted"])
            return
        rows = self._rows([int(i) for i in ids if int(i) not in self._hidden])
        if not rows:
            return
        forever = role == "trash" and rows[0]["role"] == "trash"
        lead = next((l for l, members in self._members.items() if rows[0]["id"] in members), rows[0]["id"])
        self._hidden |= {r["id"] for r in rows}
        self._model.remove([r["id"] for r in rows])
        if self._current.get("messageId") in {r["id"] for r in rows}:
            self._current, self._current_raw, self._current_thread = {}, None, None
            self.currentChanged.emit()
        self._reload_list()
        timer = QTimer(self)
        timer.setSingleShot(True)
        entry = {"rows": rows, "role": role, "forever": forever, "lead": lead, "timer": timer}
        timer.timeout.connect(lambda: self._commit_move(entry))
        self._moves.append(entry)
        timer.start(UNDO_MS)
        kind = "forever" if forever else role if role in ("archive", "trash", "junk", "inbox", "snoozed") else "folder"
        self.moveQueued.emit(kind, len(rows))

    @Slot()
    def cancelMove(self):
        """The last move is undone: its messages come back where they were (nothing reached the server)."""
        entry = next((e for e in reversed(self._moves) if e["timer"].isActive()), None)
        if entry is None:
            return
        entry["timer"].stop()
        self._moves.remove(entry)
        self._hidden -= {r["id"] for r in entry["rows"]}
        self._reload_list()
        self.moveCancelled.emit(entry["lead"])

    def _flush_moves(self):
        for entry in list(self._moves):
            entry["timer"].stop()
            self._commit_move(entry)

    def _commit_move(self, entry):
        if entry not in self._moves:
            return
        self._moves.remove(entry)
        rows, role, forever = entry["rows"], entry["role"], entry["forever"]
        name = {"archive": "Archive", "trash": "Trash", "junk": "Junk", "snoozed": SNOOZE_FOLDER}.get(role, "")
        self._store.many("DELETE FROM messages WHERE id = ?", [(r["id"],) for r in rows])
        self._hidden -= {r["id"] for r in rows}
        for key, by_path in self._by_box(rows).items():
            target = self._folder(int(role)) if role.isdigit() else self._role_folder(role, key)
            if target is not None and target["box"] != key:
                continue                    # a folder of another mailbox: never offered
            self._enqueue({"box": key, "kind": "move", "by_path": by_path, "forever": bool(forever),
                           "dest": target["path"] if target else None,
                           "create": name if target is None and name and not forever else ""})

    # ---- attachments and unsubscribing --------------------------------------------------------------
    def _raw_of(self, message_id):
        if not message_id or message_id == self._current.get("messageId"):
            return self._current_raw
        rows = self._store.query("SELECT raw FROM bodies WHERE message_id = ?", (message_id,))
        return rows[0]["raw"] if rows else None

    def _attachment_file(self, index, message_id=0):
        raw = self._raw_of(message_id)
        if not raw:
            return None
        name, data = mime.attachment(raw, index)
        if data is None:
            return None
        DOWNLOADS.mkdir(parents=True, exist_ok=True)
        safe = "".join(ch for ch in (name or "piece-jointe") if ch not in "/\\\0").strip() or "piece-jointe"
        path = DOWNLOADS / safe
        path.write_bytes(data)
        return path

    @Slot(int)
    @Slot(int, int)
    def openAttachment(self, index, message_id=0):
        path = self._attachment_file(index, message_id)
        if path:
            cloud.open_url(path.as_uri())

    @Slot(int, str)
    @Slot(int, str, int)
    def saveAttachment(self, index, target, message_id=0):
        path = self._attachment_file(index, message_id)
        if path:
            dest = Path(mime.local_path(target))
            shutil.copyfile(path, dest)
            self._plume.toast.emit(self._plume.t["saved_to"].replace("%1", dest.name))

    @Slot(int)
    @Slot(int, int)
    def saveToOrneos(self, index, message_id=0):
        path = self._attachment_file(index, message_id)
        if path:
            copied = cloud.copy_to_sync([str(path)])
            if copied:
                self._plume.toast.emit(self._plume.t["saved_orneos"].replace("%1", copied[0].name))

    @Slot(int, str)
    def saveAllAttachments(self, message_id, target):
        """Every attachment of a message into a folder (names kept; one already there gets a number)."""
        raw = self._raw_of(message_id)
        if not raw:
            return
        info = mime.read(raw)
        folder = Path(mime.local_path(target))
        count = 0
        for a in info.get("attachments") or []:
            name, data = mime.attachment(raw, a["index"])
            if data is None:
                continue
            safe = "".join(ch for ch in (name or "piece-jointe") if ch not in "/\\\0:").strip() or "piece-jointe"
            dest, n = folder / safe, 1
            while dest.exists():
                stem, dot, ext = safe.rpartition(".")
                dest = folder / (f"{stem} ({n}).{ext}" if dot else f"{safe} ({n})")
                n += 1
            try:
                dest.write_bytes(data)
                count += 1
            except OSError:
                pass
        if count:
            self._plume.toast.emit(self._plume.t["saved_all"].replace("%1", str(count)).replace("%2", folder.name))

    @Slot(int, result=str)
    def messageFileName(self, message_id):
        """A file name for a message saved as .eml: its subject."""
        row = self._message(message_id)
        subject = (row["subject"] if row else "") or self._plume.t["subject_empty"]
        return "".join(ch for ch in subject if ch not in '/\\:*?"<>|\0').strip()[:80] + ".eml"

    @Slot(int, str)
    def saveMessage(self, message_id, target):
        """The whole message as a .eml file (opens in any mail app)."""
        raw = self._raw_of(message_id)
        if raw:
            dest = Path(mime.local_path(target))
            dest.write_bytes(raw)
            self._plume.toast.emit(self._plume.t["saved_to"].replace("%1", dest.name))

    @Slot(int)
    def showSource(self, message_id):
        """Its source (headers, parts) in the text editor of the computer, from a private temporary file."""
        raw = self._raw_of(message_id)
        if not raw:
            return
        folder = system.runtime_dir() / "plume-source"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"message-{message_id}.txt"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
        cloud.open_url(path.as_uri())

    @Slot(result=str)
    def printFile(self):
        """Where the reader writes the PDF of what it shows, before the computer opens it to print."""
        folder = system.runtime_dir() / "plume-print"
        folder.mkdir(parents=True, exist_ok=True)
        return str(folder / f"message-{int(time.time())}.pdf")

    @Slot(str)
    def openFile(self, path):
        cloud.open_url(Path(path).as_uri())

    @Slot(int, int, result=str)
    def attachmentName(self, message_id, index):
        raw = self._raw_of(message_id)
        return (mime.attachment(raw, index)[0] or "") if raw else ""

    # ---- links to messages (dragged into a note or onto a task, or copied: links.py) ------------------------
    def _links(self, ids):
        out = []
        for i in ids:
            row = self._message(int(i))
            if row is not None and row["message_id"]:
                out.append({"url": links.mail_url(row["message_id"]), "title": row["subject"] or self._plume.t["subject_empty"],
                            "kind": "mail"})
        return out

    @Slot("QVariantList", result="QVariantMap")
    def dragData(self, ids):
        """What a dragged line carries: the links of its messages, and their addresses as text."""
        ids = ids.toVariant() if hasattr(ids, "toVariant") else list(ids)
        items = self._links(ids)
        if not items:
            return {}
        return {links.MIME: links.encode(items), "text/plain": "\n".join(i["url"] for i in items),
                MESSAGES_MIME: json.dumps([int(i) for i in ids])}

    @Slot("QVariantList")
    def copyLinks(self, ids):
        items = self._links(ids.toVariant() if hasattr(ids, "toVariant") else ids)
        if not items:
            return
        data = QMimeData()
        data.setData(links.MIME, QByteArray(links.encode(items).encode()))
        data.setText("\n".join(i["url"] for i in items))
        QGuiApplication.clipboard().setMimeData(data)
        self._plume.toast.emit(self._plume.t["link_copied"])

    def _image(self, url, done):
        """The bytes and type of a picture of the opened message (data: URI, or the remote picture the page
        shows), then done(data, kind) on the window's thread; nothing (a toast) when it cannot be had."""
        url = str(url or "")
        if url.lower().startswith("data:"):
            head, _, payload = url.partition(",")
            try:
                data = (base64.b64decode(payload + "=" * (-len(payload) % 4)) if ";base64" in head.lower()
                        else urllib.parse.unquote_to_bytes(payload))
            except ValueError:
                data = b""
            if data:
                done(data, head[5:].split(";")[0].lower())
            else:
                self._plume.toast.emit(self._plume.t["image_failed"])
            return
        if not url.lower().startswith(("https://", "http://")):
            self._plume.toast.emit(self._plume.t["image_failed"])
            return

        def run():
            try:
                request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Orneos Plume)"})
                with urllib.request.urlopen(request, timeout=20) as answer:
                    data = answer.read(25 * 1024 * 1024 + 1)
                    kind = answer.headers.get_content_type()
                if len(data) > 25 * 1024 * 1024:
                    raise OSError("too big")
            except (OSError, ValueError):
                self._run.emit(lambda: self._plume.toast.emit(self._plume.t["image_failed"]))
                return
            self._run.emit(lambda: done(data, kind))
        threading.Thread(target=run, daemon=True).start()

    @Slot(str)
    def copyImage(self, url):
        """« Copier l'image »: the picture itself in the clipboard (pasted as a picture anywhere), its address
        too when it has one."""
        def done(data, kind):
            image = QImage.fromData(data)
            if image.isNull():
                self._plume.toast.emit(self._plume.t["image_failed"])
                return
            mime_data = QMimeData()
            mime_data.setImageData(image)
            if kind.startswith("image/") and kind != "image/svg+xml":
                mime_data.setData(kind, QByteArray(data))
            if not url.lower().startswith("data:"):
                mime_data.setText(url)
            QGuiApplication.clipboard().setMimeData(mime_data)
            self._plume.toast.emit(self._plume.t["image_copied"])
        self._image(url, done)

    @Slot(str, result=str)
    def imageName(self, url):
        """The file name offered to « Enregistrer l'image sous… »."""
        url = str(url or "")
        if url.lower().startswith("data:"):
            kind = url[5:].split(";")[0].split(",")[0].lower()
            return "image." + {"image/jpeg": "jpg", "image/svg+xml": "svg"}.get(kind, kind.partition("/")[2] or "png")
        name = Path(urllib.parse.unquote(urllib.parse.urlsplit(url).path)).name
        name = re.sub(r'[\\/:*?"<>|]', "_", name)[:120]
        return name if "." in name else (name or "image") + ".png"

    @Slot(str, str)
    def saveImage(self, url, target):
        def done(data, kind):
            try:
                Path(mime.local_path(target)).write_bytes(data)
            except OSError:
                self._plume.toast.emit(self._plume.t["image_failed"])
                return
            self._plume.toast.emit(self._plume.t["image_saved"])
        self._image(url, done)

    @Slot()
    def unsubscribe(self):
        """Leave the list the opened message comes from (List-Unsubscribe): the one-click request when the
        sender offers it, else an email to its unsubscribe address (from the address that received the
        message), else its page in the browser. The button follows: working, then done (remembered for
        this sender)."""
        info = dict(self._current.get("unsubscribe") or {})
        message_id = self._current.get("messageId")
        row = self._message(message_id) if message_id else None
        if row is None or info.get("state") in ("working", "done") or not (info.get("https") or info.get("mailto")):
            return
        sender = (row["from_email"] or "").lower()

        def state(value, toast=""):
            if value == "done":
                done = self._store.get("unsubscribed", {}) or {}
                done[sender] = int(time.time())
                self._store.set("unsubscribed", done)
            if self._current.get("messageId") == message_id:
                self._current = dict(self._current, unsubscribe=dict(info, state=value))
                self.currentChanged.emit()
            if toast:
                self._plume.toast.emit(self._plume.t[toast])

        if info.get("oneClick"):
            state("working")
            url = info["https"]

            def post():
                try:
                    req = urllib.request.Request(url, data=b"List-Unsubscribe=One-Click", method="POST",
                                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
                    urllib.request.urlopen(req, timeout=15).read()
                    self._run.emit(lambda: state("done", "unsubscribed"))
                except Exception:
                    self._run.emit(lambda: (cloud.open_url(url), state("", "unsub_web")))
            threading.Thread(target=post, daemon=True).start()
        elif info.get("mailto"):
            state("working")
            self._unsubscribe_mail(info["mailto"], row,
                                   lambda ok: state("done", "unsubscribed") if ok else state("", "unsub_failed"))
        else:
            cloud.open_url(info["https"])
            state("", "unsub_web")

    def _unsubscribe_mail(self, uri, row, done):
        """The email that asks a list to drop this address (mailto:list@…?subject=…&body=…)."""
        address, _, query = uri[len("mailto:"):].partition("?")
        params = urllib.parse.parse_qs(query)
        box = self._boxes.get(row["box"])
        if box is None or box.password is None:
            done(False)
            return
        received = {a.get("email", "").lower() for a in json.loads(row["recipients"] or "[]") if isinstance(a, dict)}
        own = [i for i in self._identities() if i["box"] == box.key]
        identity = next((i for i in own if i["email"].lower() in received), own[0] if own else {"email": box.address})
        fields = {"to": [urllib.parse.unquote(address)], "subject": (params.get("subject") or ["unsubscribe"])[0],
                  "body": (params.get("body") or ["unsubscribe"])[0]}
        raw, recipients, _ = mime.build(fields, identity.get("name") or "", identity["email"])

        def run():
            try:
                with box.smtp() as smtp:
                    box.sign_in(smtp)
                    smtp.sendmail(identity["email"], recipients, raw)
                ok = True
            except (smtplib.SMTPException, OSError, socket.timeout, ssl.SSLError):
                ok = False
            self._run.emit(lambda: done(ok))
        threading.Thread(target=run, daemon=True).start()

    # ---- writing ------------------------------------------------------------------------------------
    def _identities(self):
        """Every address Plume writes from: Orneos (and its aliases), then the external mailboxes."""
        own = self._account.get("identities") or []
        if not own and self._account.get("address"):
            own = [{"email": self._account["address"], "name": self._account.get("name", ""), "signature": ""}]
        out = [dict(i, box=ORNEOS) for i in own]
        for config in self._configs():
            out.append({"email": config["address"], "name": config.get("name") or self._account.get("name", ""),
                        "signature": config.get("signature", ""), "box": config["key"]})
        return out

    def addresses(self):
        """Every address of mine, external mailboxes included: who "me" is in an invitation."""
        return {i["email"].lower() for i in self._identities() if i.get("email")}

    @Slot("QVariantMap")
    def sendCalendarReply(self, fields):
        """My answer to an invitation, by mail to its organizer, from the address it was sent to."""
        identity = self._identity(fields.get("from", ""))
        box = self._boxes.get(identity["box"])
        if box is None or box.password is None:
            self._plume.toast.emit(self._plume.t["invite_reply_failed"])
            return
        raw, recipients = mime.calendar_reply(fields["ics"], fields.get("text", ""), fields.get("subject", ""),
                                              fields["to"], identity.get("name") or self._account.get("name", ""),
                                              identity["email"])

        def run(conn):
            try:
                with box.smtp() as smtp:
                    box.sign_in(smtp)
                    smtp.sendmail(identity["email"], recipients, raw)
            except (smtplib.SMTPException, OSError, socket.timeout, ssl.SSLError):
                self._run.emit(lambda: self._plume.toast.emit(self._plume.t["invite_reply_failed"]))
        self._job(run, box.key, important=True)

    @js_property(notify=changed)
    def account(self):
        info = dict(self._account)
        info["identities"] = self._identities()
        return info

    @Property(str, notify=changed)
    def state(self):
        return self._state

    @Property(bool, notify=busyChanged)
    def busy(self):
        return self._busy > 0

    def _me(self):
        return {i["email"].lower() for i in self._identities()} | {self._account.get("address", "").lower()}

    @Slot(str, result="QVariantMap")
    @Slot(str, int, result="QVariantMap")
    def compose(self, mode, message_id=0):
        """Fields for the composer: "new", "reply", "all", "forward" (from the opened message, or from
        another message of the opened conversation)."""
        identities = self._identities()
        source = self._current
        if message_id and message_id != self._current.get("messageId"):
            raw = self._raw_of(message_id)
            source = dict(mime.read(raw), messageId=message_id) if raw else {}
        row = self._message(source.get("messageId") or 0) if source.get("messageId") else None
        box = row["box"] if row else self._box_key(self._folder_id)
        sender = next((i for i in identities if i["box"] == box), identities[0])
        fields = {"to": [], "cc": [], "bcc": [], "subject": "", "body": "", "html": "", "quoteText": "",
                  "quoteHtml": "", "inReplyTo": "", "references": "", "replyTo": 0, "attachments": []}
        if mode != "new" and source.get("from"):
            fields.update(mime.reply_fields(source, self._me(), mode, self._plume.lang))
            if mode == "forward":
                fields["attachments"] = self._keep_files(source, self._raw_of(source.get("messageId") or 0))
            fields["replyTo"] = source.get("messageId", 0) if mode != "forward" else 0
            # answer from the address the message was sent to
            sent_to = {a["email"].lower() for a in source.get("to", []) + source.get("cc", [])}
            sender = next((i for i in identities if i["email"].lower() in sent_to), sender)
        fields["from"] = sender["email"]
        # the editor shows the signature under what is written, above the quote; it follows the sender
        fields["signature"] = sender.get("signature") or ""
        return fields

    @Slot(str, str)
    def saveSignature(self, email, signature):
        """The signature of one address: kept by the cloud's Mail app for Orneos addresses (the same in Plume
        and on the web), by Plume for external mailboxes."""
        signature = signature.strip()
        configs = self._configs()
        config = next((c for c in configs if c["address"].lower() == email.lower()), None)
        if config is not None:
            config["signature"] = signature
            self._save_configs(configs)
            self._emit_changed()
            self._plume.toast.emit(self._plume.t["signature_saved"])
            return
        identity = next((i for i in self._account.get("identities", []) if i["email"].lower() == email.lower()), None)
        account = self._plume.account()
        if identity is None or account is None or not identity.get("accountId"):
            return
        identity["signature"] = signature
        if identity.get("aliasId"):
            identity["inherits"] = False
        else:
            for other in self._account["identities"]:
                if other.get("aliasId") and other.get("inherits"):
                    other["signature"] = signature
        self._store.set("mail_account", self._account)
        self._emit_changed()
        path = (f"/apps/mail/api/accounts/{identity['accountId']}/aliases/{identity['aliasId']}/signature"
                if identity.get("aliasId") else f"/apps/mail/api/accounts/{identity['accountId']}/signature")

        def put():
            status, _ = cloud.rest(*account, path, method="PUT", body={"signature": signature or None})
            text = self._plume.t["signature_saved"] if status in (200, 204) else self._plume.t["signature_failed"]
            self._run.emit(lambda: self._plume.toast.emit(text))
        threading.Thread(target=put, daemon=True).start()

    @Slot(str, result="QVariantList")
    def identities(self, _unused=""):
        return self._identities()

    @staticmethod
    def _plain(fields):
        return {k: (v.toVariant() if hasattr(v, "toVariant") else v) for k, v in dict(fields).items()}

    def _where(self, message_id):
        """{path, uid} of a cached message, for an operation that outlives the cache."""
        row = self._message(int(message_id or 0)) if message_id else None
        return ({"path": row["path"], "uid": row["uid"], "box": row["box"]}, row) if row else (None, None)

    def _reply_target(self, fields, box_key):
        """The message a reply answers (marked answered once it left): the one it was written from, else the
        one its In-Reply-To names in the same mailbox (a reply continued from Drafts)."""
        where, row = self._where(fields.get("replyTo"))
        if where is None and fields.get("inReplyTo"):
            mid = str(fields["inReplyTo"]).strip()
            rows = self._store.query("SELECT m.id FROM messages m JOIN mail_folders f ON f.id = m.folder_id "
                                     "WHERE f.box = ? AND m.message_id = ? AND f.role NOT IN ('sent', 'drafts') LIMIT 1",
                                     (box_key, mid))
            if rows:
                where, row = self._where(rows[0]["id"])
        return where if where and where["box"] == box_key else None

    def _draft_target(self, fields, box_key):
        """The draft this message replaces (sent or saved again): taken off the list now, off the server next."""
        kept = fields.get("drop")
        if isinstance(kept, dict) and kept.get("path"):
            return {"path": kept["path"], "uid": int(kept["uid"])}   # a send cancelled: the draft it replaced
        where, row = self._where(fields.get("draftId"))
        if where is None or where["box"] != box_key or row["role"] != "drafts":
            return None
        self._store.execute("DELETE FROM messages WHERE id = ?", (row["id"],))
        if self._current.get("messageId") == row["id"]:
            self._current, self._current_raw, self._current_thread = {}, None, None
            self.currentChanged.emit()
        self._reload_list()
        return {"path": where["path"], "uid": where["uid"]}

    @Slot("QVariantMap")
    def send(self, fields):
        """Written to the outbox at once (nothing is lost if Plume stops), sent once the few seconds that allow
        cancelling it are over (the toast offers it), or when the network is back. Several can wait together."""
        fields = self._plain(fields)
        identity = self._identity(fields.get("from") or self._account.get("address", ""))
        key = identity["box"]
        box = self._boxes.get(key)
        if box is None:
            self._plume.toast.emit(self._plume.t["send_failed"])
            self.sendCancelled.emit(fields)
            return
        raw, recipients, _ = mime.build(fields, identity.get("name") or self._account.get("name", ""), identity["email"], richtext.PASTED)
        # « Envoyer plus tard »: it waits in the outbox until then (Plume sends it; if it is closed at that time,
        # at its next start)
        at = float(fields.get("sendAt") or 0)
        scheduled = at > time.time() + 30
        fields = {k: v for k, v in fields.items() if k not in ("sendAt", "scheduled")}
        if scheduled:
            fields["scheduled"] = at
        op = self._enqueue({"box": key, "kind": "send", "due": at if scheduled else time.time() + UNDO_MS / 1000, "fields": fields,
                            "sender": identity["email"], "recipients": recipients,
                            "reply": self._reply_target(fields, key), "drop": self._draft_target(fields, key)},
                           raw, flush=False)
        self.clearComposing()
        if scheduled:
            self._queue_timer.start()
            self._plume.toast.emit(self._plume.t["send_scheduled"].replace("%1", self._when(at)))
            self._emit_changed()
            return
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: (self._send_timers.pop(op["id"], None), self._flush(key)))
        self._send_timers[op["id"]] = timer
        timer.start(UNDO_MS)
        self.sendQueued.emit()
        self._emit_changed()

    def _when(self, stamp):
        """« demain 08:00 », « lun. 10/11 08:00 »: a moment to come, short."""
        t, now = time.localtime(stamp), time.localtime()
        days = (time.mktime(t[:3] + (0, 0, 0, 0, 0, -1)) - time.mktime(now[:3] + (0, 0, 0, 0, 0, -1))) / 86400
        clock = time.strftime("%H:%M", t)
        if round(days) == 0:
            return self._plume.t["today_at"].replace("%1", clock)
        if round(days) == 1:
            return self._plume.t["tomorrow_at"].replace("%1", clock)
        return time.strftime("%d/%m", t) + " " + clock

    @Slot()
    def cancelSend(self):
        """The last message sent, back to the composer (only while it has not left)."""
        for op in reversed(self._queue.items(kind="send", owner=self._owner())):
            if op.get("smtp_done") or op["id"] in self._running or op.get("due", 0) <= time.time() \
                    or (op.get("fields") or {}).get("scheduled"):
                continue
            timer = self._send_timers.pop(op["id"], None)
            if timer is not None:
                timer.stop()
            self._queue.remove(op["id"])
            self.sendCancelled.emit(dict(op.get("fields") or {}, drop=op.get("drop")))
            self._emit_changed()
            return

    @Slot()
    def flush(self):
        """On quit: moves still undoable are made, messages waiting go now. Without network they stay in the
        outbox and leave at the next start."""
        self._flush_moves()
        for op in self._queue.items(kind="send", owner=self._owner()):
            if op.get("due", 0) > time.time() and not (op.get("fields") or {}).get("scheduled"):
                self._queue.update(op["id"], due=0)
        for timer in self._send_timers.values():
            timer.stop()
        self._send_timers.clear()
        for key in {op["box"] for op in self._queue.items(owner=self._owner())}:
            self._flushing.discard(key)
            self._flush(key, important=True)

    def _identity(self, email):
        identities = self._identities()
        return next((i for i in identities if i["email"].lower() == (email or "").lower()), identities[0])

    @Slot("QVariantMap")
    def saveDraft(self, fields):
        """The composer closed without sending: the draft goes to the Drafts folder (and to other devices),
        through the queue (offline, it waits there)."""
        fields = self._plain(fields)
        if not (fields.get("to") or fields.get("cc") or fields.get("bcc") or fields.get("subject", "").strip()
                or fields.get("body", "").strip() or fields.get("attachments")):
            self.clearComposing()
            return
        identity = self._identity(fields.get("from") or self._account.get("address", ""))
        raw, _, _ = mime.build(fields, identity.get("name") or self._account.get("name", ""), identity["email"], richtext.PASTED)
        raw = mime.keep_bcc(raw, fields.get("bcc"))
        key = identity["box"]
        self._enqueue({"box": key, "kind": "draft", "drop": self._draft_target(fields, key)}, raw)
        self.clearComposing()
        self._plume.toast.emit(self._plume.t["draft_saved"])

    def _keep_files(self, info, raw):
        """The attachments of a message as files (a forward or a draft continued sends them again)."""
        out = []
        if not raw:
            return out
        folder = DOWNLOADS / f"msg-{uuid.uuid4().hex[:10]}"
        for a in info.get("attachments") or []:
            name, data = mime.attachment(raw, a["index"])
            if data is None:
                continue
            safe = "".join(ch for ch in (name or "piece-jointe") if ch not in "/\\\0:").strip() or "piece-jointe"
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / safe
            path.write_bytes(data)
            out.append(str(path))
        return out

    @Slot(result="QVariantMap")
    def draftFields(self):
        """Fields of the opened draft, to continue it in the composer: its attachments and what it answers too."""
        info = self._current
        if not info or info.get("role") != "drafts":
            return {}
        written, signature, quote = mime.draft_parts(info.get("source", ""))
        return {"to": [a["email"] for a in info.get("to", [])], "cc": [a["email"] for a in info.get("cc", [])],
                "bcc": [a["email"] for a in info.get("bcc", [])], "subject": info.get("subject", ""),
                "body": mime.text_from_html(written) if info.get("isHtml") else info.get("text", ""),
                "html": written, "signature": signature, "quoteText": "", "quoteHtml": quote,
                "from": (info.get("from") or {}).get("email", ""), "draftId": info.get("messageId", 0),
                "attachments": self._keep_files(info, self._current_raw), "inReplyTo": info.get("inReplyTo", ""),
                "references": info.get("references", ""), "replyTo": 0}

    # ---- the message being written, kept against a crash ---------------------------------------------
    @Slot("QVariantMap")
    def keepComposing(self, fields):
        """The composer's content, every few seconds while it changes: back at the next start if Plume stopped."""
        try:
            system.private_write(RECOVERY, json.dumps({"at": time.time(), "owner": self._owner(),
                                                       "fields": self._plain(fields)}, ensure_ascii=False))
        except (OSError, TypeError, ValueError):
            pass

    @Slot()
    def clearComposing(self):
        try:
            RECOVERY.unlink()
        except OSError:
            pass

    def _recover(self):
        if getattr(self, "_recovered", False):
            return
        self._recovered = True
        try:
            kept = json.loads(RECOVERY.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        self.clearComposing()
        if not isinstance(kept, dict) or kept.get("owner") != self._owner() or time.time() - kept.get("at", 0) > 14 * 86400:
            return
        fields = kept.get("fields") or {}
        if fields.get("to") or fields.get("subject") or (fields.get("body") or "").strip():
            QTimer.singleShot(800, lambda: (self.composeRecovered.emit(fields), self._plume.toast.emit(self._plume.t["compose_recovered"])))

    @Slot(str, result=int)
    def attachmentSize(self, path):
        try:
            return Path(mime.local_path(path)).stat().st_size
        except OSError:
            return 0

    @Slot(str)
    def requestShareLink(self, path):
        """A cloud link instead of a heavy attachment (the file goes to the cloud first): shareLinkReady."""
        account = self._plume.account()
        local = mime.local_path(path)

        def run():
            try:
                url = cloud.create_share_link(*account, local) or "" if account else ""
            except Exception:
                url = ""
            self._run.emit(lambda: self.shareLinkReady.emit(path, url))
        threading.Thread(target=run, daemon=True).start()

    # ---- new mail, live -----------------------------------------------------------------------------
    def _start_idle(self, box):
        box.idle_stop = threading.Event()
        stop = box.idle_stop

        def loop():
            delay = 5
            while not stop.is_set():
                try:
                    conn = box.connect(timeout=60)
                    conn.select("INBOX", readonly=True)
                    delay = 5
                    while not stop.is_set():
                        if conn.idle(300):
                            inbox = self._inbox_id(box.key)
                            self._job(lambda c, i=inbox: self._sync_folder(c, i, notify=True), box.key, quiet=True)
                    conn.close()
                except imap.MailError as error:
                    if error.kind == "auth":
                        return
                except Exception:
                    pass
                stop.wait(delay)
                delay = min(delay * 2, 300)
        threading.Thread(target=loop, daemon=True, name=f"plume-idle-{box.key}").start()
