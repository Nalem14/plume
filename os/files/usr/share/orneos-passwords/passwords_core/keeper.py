"""What the QML sees of the passwords: the list of the selected category, the details of one entry, the
security review, and every change, written to the vault at once and sent to the cloud behind.

Network calls run on one worker thread (the order of writes is kept); site icons on a small pool of their
own, so a slow site never holds a sync. Sync: at start, every 5 minutes, a moment after each change, when
the window comes back to the front and as soon as the network returns.
"""
import csv
import hashlib
import os
import threading
import time
import traceback
import unicodedata
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import QObject, Property, QTimer, QUrl, Signal, Slot
from PySide6.QtNetwork import QNetworkInformation

import cloud
import system
from passwords_core import generator, importer, secure, sites, strength, totp
from passwords_core.api import Api, ApiError, ROOT_FOLDER
from passwords_core.vault import Vault

EVERY_MS = 5 * 60 * 1000
ICONS = system.CACHE / "passwords-icons"
ICON_RETRY = 7 * 86400
# Tiles of the entries without an icon: the rail families (Klein, vert-de-gris, teal, Prusse, safran ink)
TILES = ("#002FA7", "#2F7D6D", "#1A5F7A", "#0F2440", "#7A5200", "#3D5AA8", "#5B6B82")


def fold(text):
    return unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().lower()


def title_of(entry):
    return entry.get("label") or sites.host(entry.get("url")) or entry.get("username") or "—"


class Keeper(QObject):
    changed = Signal()               # the list, the counts, an entry
    categoryChanged = Signal()
    stateChanged = Signal()
    iconsChanged = Signal()
    historyReady = Signal(str, "QVariantList")
    recipientsReady = Signal("QVariantList")
    importReady = Signal("QVariantMap")
    done = Signal(str, bool, str)    # what, ok, message (folder, share, history restore…)
    _sync_finished = Signal(str)     # "" or an error kind
    _icon_ready = Signal(str)
    _ran = Signal(object)

    def __init__(self, app):
        super().__init__()
        self._app = app
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="passwords-sync")
        self._icons = ThreadPoolExecutor(max_workers=3, thread_name_prefix="passwords-icons")
        self._vault = None
        self._state = "signed_out"
        self._online = True
        self._syncing = False
        self._queued = False
        self._category = app.pref("category") or "all"
        self._query = ""
        self._entries = {}
        self._issues = {}
        self._items = []
        self._icon_files = {}
        self._icon_asked = set()
        self._import = None
        self._last_sync = 0.0
        # Changes that need the cloud (folders, shares) show at once; until it answers they live here. Refused,
        # they go back as they were and the window says why.
        self._local_folders = {}        # id → folder made here, not confirmed yet
        self._folder_labels = {}        # id → new name, not confirmed yet
        self._hidden_folders = set()    # being deleted
        self._local_shares = []         # shares made here, not confirmed yet
        self._share_edits = {}          # share id → editable, not confirmed yet
        self._hidden_shares = set()     # being stopped
        self._sync_finished.connect(self._after_sync)
        self._icon_ready.connect(self._icon_arrived)
        self._ran.connect(lambda fn: fn())
        ICONS.mkdir(parents=True, exist_ok=True)
        for f in ICONS.glob("*.png"):
            self._icon_files[f.stem] = QUrl.fromLocalFile(str(f)).toString()

        self._timer = QTimer(self)
        self._timer.setInterval(EVERY_MS)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self._soon = QTimer(self)
        self._soon.setSingleShot(True)
        self._soon.setInterval(800)
        self._soon.timeout.connect(self.refresh)

        if QNetworkInformation.loadDefaultBackend() and QNetworkInformation.instance():
            QNetworkInformation.instance().reachabilityChanged.connect(self._reachability)
        app.accountChanged.connect(self._account_changed)
        app.prefsChanged.connect(self._rebuild)
        self._account_changed()

    # ---- account and state -------------------------------------------------------------------------------
    def _account_changed(self):
        account = self._app.account()
        user = account[1] if account else None
        if self._vault is not None and self._vault.user == user:
            return
        if self._vault is not None:
            secure.forget()                    # another account (or signed out): nothing of the previous stays
        self._vault = None
        self._entries, self._issues = {}, {}
        if account is None:
            self._set_state("signed_out")
            self._rebuild()
            return
        self._vault = Vault(user)
        self._set_state("ready" if self._vault.load() else "loading")
        if self._vault.cse:
            self._set_state("cse")
        self._reload()
        threading.Thread(target=self._load_profile, args=(account,), daemon=True).start()
        self.refresh()

    def _load_profile(self, account):
        info = cloud.userinfo(*account)
        if info:
            profile = {"name": str(info.get("displayname") or info.get("display-name") or account[1]),
                       "email": str(info.get("email") or "")}
            self._ran.emit(lambda: self._app.set_profile(profile))

    def _set_state(self, state):
        if state != self._state:
            self._state = state
            self.stateChanged.emit()

    @Property(str, notify=stateChanged)
    def state(self):
        return self._state

    @Property(bool, notify=stateChanged)
    def online(self):
        return self._online

    @Property(bool, notify=stateChanged)
    def syncing(self):
        return self._syncing

    @Property(int, notify=stateChanged)
    def pending(self):
        return self._vault.pending_count() if self._vault else 0

    @Property(int, notify=stateChanged)
    def syncedAt(self):
        return self._vault.synced_at if self._vault else 0

    @Property(int, notify=stateChanged)
    def unreadable(self):
        return self._vault.unreadable if self._vault else 0

    def _reachability(self, reachability):
        if reachability == QNetworkInformation.Reachability.Online:
            self.refresh()

    # ---- sync --------------------------------------------------------------------------------------------
    def api(self):
        account = self._app.account()
        return Api(account) if account else None

    @Slot()
    def refresh(self):
        if self._vault is None:
            return
        if self._syncing:
            self._queued = True
            return
        self._syncing = True
        self._last_sync = time.monotonic()
        self.stateChanged.emit()
        vault, api = self._vault, self.api()

        def run():
            error = ""
            try:
                vault.sync(api, report=self._refused)
            except ApiError as e:
                error = "offline" if e.status == 0 else "auth" if e.status == 401 else "server"
            except Exception:
                traceback.print_exc()
                error = "server"
            self._sync_finished.emit(error)
        self._pool.submit(run)

    def stale(self, seconds):
        return time.monotonic() - self._last_sync > seconds

    def _refused(self, kind, entry, error):
        name = title_of(entry) if entry else ""
        self._ran.emit(lambda: self._app.toast.emit(self._app.t["sync_refused"].replace("%1", name)))

    def _after_sync(self, error):
        self._syncing = False
        was_online = self._online
        self._online = error != "offline"
        if self._vault is None:
            return
        if self._vault.cse:
            self._set_state("cse")
        elif error and not self._vault.loaded and not self._vault.synced_at:
            self._set_state("offline_first" if error == "offline" else "error_first")
        else:
            self._vault.loaded = self._vault.loaded or not error
            self._set_state("ready" if self._vault.loaded else self._state)
        if error == "auth":
            self._app.toast.emit(self._app.t["error_auth"])
        elif error == "server":
            self._app.toast.emit(self._app.t["error_server"])
        elif error == "offline" and was_online and self._vault.pending_count():
            self._app.toast.emit(self._app.t["offline_saved"])
        self.stateChanged.emit()
        self._reload()
        if self._queued:
            self._queued = False
            self.refresh()

    def shutdown(self):
        self._pool.shutdown(wait=False, cancel_futures=True)
        self._icons.shutdown(wait=False, cancel_futures=True)

    # ---- the list ------------------------------------------------------------------------------------------
    def _reload(self):
        self._entries = self._vault.entries() if self._vault else {}
        self._issues = self._review(self._entries)
        self._rebuild()

    def _review(self, entries):
        """id → issues: breached, reused, weak, old, twofa (a site that takes a code, and none here)."""
        ignored = set(self._app.pref("ignored") or [])
        live = [e for e in entries.values() if not e.get("trashed")]
        by_password = {}
        for e in live:
            if e.get("password"):
                by_password.setdefault(e["password"], []).append(e["id"])
        out = {}
        for e in live:
            found = []
            if e.get("statusCode") == "BREACHED" or e.get("status") == 2:
                found.append("breached")
            if len(by_password.get(e.get("password"), [])) > 1 or e.get("statusCode") == "DUPLICATE":
                found.append("reused")
            context = (e.get("label"), e.get("username"), sites.site_of(e.get("url")).split(".")[0])
            if strength.weak(e.get("password"), context):
                found.append("weak")
            if e.get("statusCode") == "OUTDATED":
                found.append("old")
            if sites.two_factor(e.get("url")) and totp.find(e.get("customFields")) < 0:
                found.append("twofa")
            if found and e["id"] not in ignored:
                out[e["id"]] = found
        return out

    def _row(self, e):
        host = sites.host(e.get("url"))
        site = sites.site(host)
        name = title_of(e)
        issues = [i for i in self._issues.get(e["id"], []) if i != "twofa"]
        key = site or fold(name)
        if host and site not in self._icon_files and self._state in ("ready",):
            self._fetch_icon(site)
        return {
            "id": e["id"], "label": name, "username": e.get("username") or "", "host": host, "site": site,
            "letter": (fold(name)[:1] or "#").upper() if fold(name)[:1].isalpha() else "#",
            "initial": (name[:1] or "?").upper(), "tile": TILES[int(hashlib.md5(key.encode()).hexdigest(), 16) % len(TILES)],
            "icon": self._icon_files.get(site, ""), "favorite": bool(e.get("favorite")),
            "code": totp.find(e.get("customFields")) >= 0, "issue": issues[0] if issues else "",
            "shared": bool(e.get("shared") or e.get("share")), "sharedIn": bool(e.get("share")),
            "pending": bool(e.get("pending")), "trashed": bool(e.get("trashed")), "updated": int(e.get("updated") or 0),
        }

    def _matches(self, e, words):
        if not words:
            return True
        folder = (self._vault.folders.get(e.get("folder")) or {}).get("label", "") if self._vault else ""
        tags = " ".join((self._vault.tags.get(t) or {}).get("label", "") for t in e.get("tags") or []) if self._vault else ""
        hay = fold(" ".join([e.get("label") or "", e.get("username") or "", e.get("url") or "", folder, tags]))
        return all(w in hay for w in words)

    def _in(self, e, category):
        if category == "trash":
            return bool(e.get("trashed"))
        if category == "wifi":
            return False
        if e.get("trashed"):
            return False
        if category == "favorites":
            return bool(e.get("favorite"))
        if category == "codes":
            return totp.find(e.get("customFields")) >= 0
        if category == "shared":
            return bool(e.get("shared") or e.get("share"))
        if category == "security":
            return any(i in ("breached", "reused", "weak") for i in self._issues.get(e["id"], []))
        if category.startswith("folder:"):
            return e.get("folder") == category[7:]
        return True

    def _rebuild(self):
        words = fold(self._query).split()
        category = "all" if words and self._category not in ("trash",) else self._category
        chosen = [e for e in self._entries.values() if self._in(e, category) and self._matches(e, words)]
        if self._app.pref("sort") == "recent" or category == "trash":
            chosen.sort(key=lambda e: -int(e.get("updated") or 0))
        else:
            chosen.sort(key=lambda e: (fold(title_of(e)), fold(e.get("username"))))
        self._items = [self._row(e) for e in chosen]
        self.changed.emit()

    @Property(str, notify=categoryChanged)
    def category(self):
        return self._category

    @Slot(str)
    def setCategory(self, category):
        if category != self._category:
            self._category = category
            self._app.setPref("category", category if not category.startswith("folder:") else "all")
            self._rebuild()
            self.categoryChanged.emit()

    @Property(str, notify=changed)
    def query(self):
        return self._query

    @Slot(str)
    def setQuery(self, query):
        if query != self._query:
            self._query = query
            self._rebuild()

    @Property("QVariantList", notify=changed)
    def items(self):
        return self._items

    @Property("QVariantMap", notify=changed)
    def counts(self):
        live = [e for e in self._entries.values() if not e.get("trashed")]
        counts = {
            "all": len(live),
            "favorites": sum(1 for e in live if e.get("favorite")),
            "codes": sum(1 for e in live if totp.find(e.get("customFields")) >= 0),
            "shared": sum(1 for e in live if e.get("shared") or e.get("share")),
            "security": sum(1 for e in live if any(i in ("breached", "reused", "weak") for i in self._issues.get(e["id"], []))),
            "breached": sum(1 for e in live if "breached" in self._issues.get(e["id"], [])),
            "trash": sum(1 for e in self._entries.values() if e.get("trashed")),
        }
        for e in live:
            if e.get("folder") and e["folder"] != ROOT_FOLDER:
                counts["folder:" + e["folder"]] = counts.get("folder:" + e["folder"], 0) + 1
        return counts

    @Property("QVariantList", notify=changed)
    def folders(self):
        if not self._vault:
            return []
        rows = [dict(f, label=self._folder_labels.get(f["id"], f["label"]), pending=f["id"] in self._folder_labels)
                for f in self._vault.folders.values()
                if not f.get("trashed") and f["id"] != ROOT_FOLDER and f["id"] not in self._hidden_folders]
        rows += list(self._local_folders.values())
        return sorted(rows, key=lambda f: fold(f["label"]))

    @Property("QVariantMap", notify=changed)
    def security(self):
        """The review, by kind: rows of the entries concerned (the most serious first)."""
        groups = {k: [] for k in ("breached", "reused", "weak", "old", "twofa")}
        ignored = set(self._app.pref("ignored") or [])
        for entry_id, issues in self._issues.items():
            e = self._entries.get(entry_id)
            if not e:
                continue
            for issue in issues:
                groups[issue].append(self._row(e))
        for rows in groups.values():
            rows.sort(key=lambda r: fold(r["label"]))
        live = [e for e in self._entries.values() if not e.get("trashed")]
        serious = sum(1 for e in live if any(i in ("breached", "reused", "weak") for i in self._issues.get(e["id"], [])))
        hidden = sum(1 for e in live if e["id"] in ignored)
        return {**groups, "total": len(live), "serious": serious, "ignored": hidden}

    # ---- one entry ---------------------------------------------------------------------------------------
    @Slot(str, result="QVariantMap")
    def detail(self, entry_id):
        e = self._entries.get(entry_id)
        if not e:
            return {}
        fields = list(e.get("customFields") or [])
        otp_index = totp.find(fields)
        otp = totp.parse(fields[otp_index]["value"]) if otp_index >= 0 else None
        shown = [dict(f, index=i) for i, f in enumerate(fields) if i != otp_index]
        vault = self._vault
        folder = (vault.folders.get(e.get("folder")) or {}) if vault else {}
        all_shares = [dict(x, editable=self._share_edits.get(x.get("id"), x.get("editable")))
                      for x in (vault.shares if vault else []) if x.get("id") not in self._hidden_shares] + self._local_shares
        received = next((s for s in all_shares if e.get("share") and s.get("id") == e.get("share")), None)
        sent = [s for s in all_shares if s.get("password") == entry_id and s.get("id") != e.get("share")]
        issues = self._issues.get(entry_id, [])
        others = []
        if "reused" in issues:
            others = sorted(title_of(x) for x in self._entries.values()
                            if x["id"] != entry_id and not x.get("trashed") and x.get("password") == e.get("password"))
        context = (e.get("label"), e.get("username"), sites.site_of(e.get("url")).split(".")[0])
        row = self._row(e)
        return {
            **row, "password": e.get("password") or "", "url": e.get("url") or "", "link": sites.link(e.get("url")),
            "notes": e.get("notes") or "", "fields": shown, "otp": totp.uri(otp, e.get("username"), e.get("label")) if otp else "",
            "otpIssuer": (otp or {}).get("issuer", ""), "folder": e.get("folder") or "", "folderName": folder.get("label", ""),
            "tags": [vault.tags[t] for t in e.get("tags") or [] if vault and t in vault.tags],
            "issues": issues, "reusedWith": others[:6], "strength": strength.score(e.get("password"), context),
            "ignored": entry_id in set(self._app.pref("ignored") or []),
            "editable": e.get("editable", True) is not False and not e.get("trashed"),
            "sharedBy": ((received or {}).get("owner") or {}).get("name", "") if e.get("share") else "",
            "shares": [{"id": s["id"], "name": (s.get("receiver") or {}).get("name") or (s.get("receiver") or {}).get("id", ""),
                        "editable": s.get("editable"), "pending": bool(s.get("pending"))} for s in sent],
            "created": int(e.get("created") or 0), "edited": int(e.get("edited") or 0),
            "twofaSite": sites.two_factor(e.get("url")),
        }

    @Slot(str, result="QVariantMap")
    def code(self, entry_id):
        """The current verification code: {code, remaining, period}, or {} for an entry without one."""
        e = self._entries.get(entry_id)
        if not e:
            return {}
        fields = e.get("customFields") or []
        index = totp.find(fields)
        config = totp.parse(fields[index]["value"]) if index >= 0 else None
        if not config:
            return {}
        value, remaining = totp.code(config)
        return {"code": value, "remaining": remaining, "period": config["period"]}

    @Slot(str, result="QVariantMap")
    def codeFor(self, uri):
        """The code of a setup key not saved yet (the editor shows it, to check it matches the site)."""
        config = totp.parse(uri)
        if not config:
            return {}
        value, remaining = totp.code(config)
        return {"code": value, "remaining": remaining, "period": config["period"], "uri": totp.uri(config),
                "issuer": config.get("issuer", ""), "account": config.get("account", "")}

    # ---- changes -----------------------------------------------------------------------------------------
    @Slot("QVariantMap", result=str)
    def save(self, data):
        """From the editor: {id?, label, username, password, url, notes, fields, folder, otp}."""
        if self._vault is None:
            return ""
        data = {k: (v.toVariant() if hasattr(v, "toVariant") else v) for k, v in dict(data).items()}
        current = self._entries.get(data.get("id") or "") or {}
        fields = [{"label": str(f.get("label") or "").strip(), "type": f.get("type") or "text", "value": str(f.get("value") or "")}
                  for f in (data.get("fields") or []) if str(f.get("value") or "").strip() or str(f.get("label") or "").strip()]
        otp = totp.parse(data.get("otp") or "")
        if otp:
            fields.append({"label": totp.FIELD_LABEL, "type": "secret",
                           "value": totp.uri(otp, data.get("username") or "", data.get("label") or "")})
        # the fields kept by other apps (files, data) that this editor does not show
        kept = [f for f in (current.get("customFields") or []) if f.get("type") in ("file",)]
        entry = {
            **current, "id": data.get("id") or "", "label": str(data.get("label") or "").strip(),
            "username": str(data.get("username") or "").strip(), "password": str(data.get("password") or ""),
            "url": str(data.get("url") or "").strip(), "notes": str(data.get("notes") or ""),
            "customFields": fields + kept, "folder": data.get("folder") or current.get("folder") or ROOT_FOLDER,
            "favorite": bool(data.get("favorite", current.get("favorite", False))),
            "tags": list(current.get("tags") or []),
        }
        if not entry["label"]:
            entry["label"] = sites.site_of(entry["url"]) or entry["username"] or self._app.t["untitled"]
        changed = [f for f in ("label", "username", "password", "url", "notes", "customFields", "folder", "favorite")
                   if not current or current.get(f) != entry.get(f)]
        if current and not changed:
            return current["id"]
        entry_id = self._vault.save_entry(entry, changed or None)
        self._changed_here()
        return entry_id

    def _changed_here(self):
        self._reload()
        self.stateChanged.emit()
        self._soon.start()

    @Slot(str)
    def toggleFavorite(self, entry_id):
        e = self._entries.get(entry_id)
        if e and self._vault:
            self._vault.save_entry({**e, "favorite": not e.get("favorite")}, ["favorite"])
            self._changed_here()

    @Slot(str, str)
    def moveTo(self, entry_id, folder):
        e = self._entries.get(entry_id)
        if e and self._vault:
            self._vault.save_entry({**e, "folder": folder or ROOT_FOLDER}, ["folder"])
            self._changed_here()

    def _queue(self, kind, ids):
        """trash, restore or purge one entry or a selection of the list."""
        ids = [i for i in ids if i in self._entries]
        if self._vault and ids:
            getattr(self._vault, kind)(*ids)
            self._changed_here()
        return len(ids)

    @Slot(str)
    def trash(self, entry_id):
        self._queue("trash", [entry_id])

    @Slot(str)
    def restore(self, entry_id):
        self._queue("restore", [entry_id])

    @Slot(str)
    def purge(self, entry_id):
        self._queue("purge", [entry_id])

    @Slot("QVariantList")
    def trashMany(self, ids):
        count = self._queue("trash", [i for i in ids if not self._entries.get(i, {}).get("trashed")])
        if count > 1:
            self._app.toast.emit(self._app.plural("trashed_many", count))

    @Slot("QVariantList")
    def restoreMany(self, ids):
        self._queue("restore", ids)

    @Slot("QVariantList")
    def purgeMany(self, ids):
        self._queue("purge", ids)

    @Slot()
    def emptyTrash(self):
        self._queue("purge", [e["id"] for e in self._entries.values() if e.get("trashed")])

    @Slot(str, bool)
    def ignore(self, entry_id, on):
        ignored = [i for i in (self._app.pref("ignored") or []) if i != entry_id]
        if on:
            ignored.append(entry_id)
        self._app.setPref("ignored", ignored)
        self._reload()

    # ---- helpers for the editor --------------------------------------------------------------------------
    @Slot(str, int, bool, result=str)
    def generate(self, style, length, symbols):
        return generator.make(style, length, symbols, count=length)

    @Slot(str, str, str, result=int)
    def strength(self, password, label, username):
        return strength.score(password, (label, username))

    @Slot(str, str, result="QVariantList")
    def reusedBy(self, password, entry_id):
        """Other entries with this password (the editor warns before saving it again)."""
        if not password:
            return []
        return sorted(title_of(e) for e in self._entries.values()
                      if e["id"] != entry_id and not e.get("trashed") and e.get("password") == password)[:4]

    @Slot(str, result="QVariantList")
    def forOtp(self, uri):
        """Entries a scanned code may belong to: the same site or issuer first (otpauth:// links, QR codes)."""
        config = totp.parse(uri) or {}
        issuer, account = fold(config.get("issuer")), fold(config.get("account"))
        scored = []
        for e in self._entries.values():
            if e.get("trashed"):
                continue
            hay = fold(" ".join([e.get("label") or "", e.get("url") or ""]))
            score = (2 if issuer and issuer in hay else 0) + (1 if account and account == fold(e.get("username")) else 0)
            if score:
                scored.append((-score, fold(title_of(e)), self._row(e)))
        return [r for _, _, r in sorted(scored, key=lambda x: x[:2])][:8]

    @Slot(str, str)
    def addCode(self, entry_id, uri):
        e = self._entries.get(entry_id)
        config = totp.parse(uri)
        if not e or not config or not self._vault:
            return
        fields = [f for i, f in enumerate(e.get("customFields") or []) if i != totp.find(e.get("customFields"))]
        fields.append({"label": totp.FIELD_LABEL, "type": "secret", "value": totp.uri(config, e.get("username"), e.get("label"))})
        self._vault.save_entry({**e, "customFields": fields}, ["customFields"])
        self._changed_here()

    # ---- what needs the cloud now (folders, sharing, history, the site's change page) -----------------------
    def _online_job(self, what, fn, then=None, undo=None):
        """A change only the cloud can make. The window shows it done already; refused, undo() puts things
        back and done(what, False, why) brings the reason up in a dialog."""
        api = self.api()
        if api is None:
            return

        def failed(message):
            if undo:
                self._ran.emit(undo)
            self.done.emit(what, False, message)

        def run():
            try:
                result = fn(api)
            except ApiError as error:
                failed(self._app.t["error_offline_action"] if error.status == 0 else self._app.t["error_server"])
                return
            except Exception:
                traceback.print_exc()
                failed(self._app.t["error_server"])
                return
            if then:
                self._ran.emit(lambda: then(result))
            self.done.emit(what, True, "")
        self._pool.submit(run)

    def _overlay_changed(self):
        self._rebuild()

    @Slot(str)
    def createFolder(self, label):
        label = label.strip()
        if not label:
            return
        local_id = "pending-" + uuid.uuid4().hex
        self._local_folders[local_id] = {"id": local_id, "label": label, "parent": ROOT_FOLDER, "trashed": False,
                                         "revision": "", "favorite": False, "pending": True}
        self._overlay_changed()

        def settle(_result=None):
            self._local_folders.pop(local_id, None)
            self.refresh()
        self._online_job("folder", lambda api: api.create_folder(label), settle,
                         undo=lambda: (self._local_folders.pop(local_id, None), self._overlay_changed()))

    @Slot(str, str)
    def renameFolder(self, folder_id, label):
        folder = (self._vault.folders.get(folder_id) if self._vault else None)
        label = label.strip()
        if not folder or not label:
            return
        self._folder_labels[folder_id] = label
        self._overlay_changed()

        def settle(_result=None):
            self._folder_labels.pop(folder_id, None)
            self.refresh()
        self._online_job("folder", lambda api: api.rename_folder(folder, label), settle,
                         undo=lambda: (self._folder_labels.pop(folder_id, None), self._overlay_changed()))

    @Slot(str)
    def deleteFolder(self, folder_id):
        """The folder goes to the cloud's trash; its entries come back to the top level first (at once, offline
        too: they are changes of the entries)."""
        if not self._vault:
            return
        for e in list(self._entries.values()):
            if e.get("folder") == folder_id:
                self._vault.save_entry({**e, "folder": ROOT_FOLDER}, ["folder"])
        vault = self._vault
        self._hidden_folders.add(folder_id)

        def job(api):
            vault.push(api)
            api.delete_folder(folder_id)

        def settle(_result=None):
            self._hidden_folders.discard(folder_id)
            self.refresh()
        if self._category == "folder:" + folder_id:
            self.setCategory("all")
        self._reload()
        self._soon.start()
        self._online_job("folder", job, settle,
                         undo=lambda: (self._hidden_folders.discard(folder_id), self._overlay_changed()))

    @Slot(str)
    def loadHistory(self, entry_id):
        if entry_id.startswith("local-"):
            self.historyReady.emit(entry_id, [])
            return

        def then(revisions):
            rows, seen = [], set()
            for r in sorted(revisions or [], key=lambda r: -int(r.get("edited") or r.get("created") or 0)):
                password = r.get("password") or ""
                if not password or password in seen:
                    continue
                seen.add(password)
                rows.append({"revision": r.get("id"), "password": password, "edited": int(r.get("edited") or r.get("created") or 0)})
            self.historyReady.emit(entry_id, rows)
        self._online_job("history", lambda api: api.history(entry_id), then)

    @Slot(str, str)
    def usePassword(self, entry_id, password):
        """Back to an older password from the history (a new revision: the current one stays in history)."""
        e = self._entries.get(entry_id)
        if e and self._vault and password:
            self._vault.save_entry({**e, "password": password}, ["password"])
            self._changed_here()

    @Slot(str)
    def findRecipients(self, search):
        if len(search.strip()) < 2:
            self.recipientsReady.emit([])
            return
        me = self._app.account()[1] if self._app.account() else ""

        def then(rows):
            self.recipientsReady.emit([{"id": r.get("id"), "name": r.get("name") or r.get("id")}
                                       for r in rows if r.get("id") and r.get("id") != me])
        self._online_job("recipients", lambda api: api.recipients(search.strip()), then)

    @Slot(str, str, str, bool)
    def share(self, entry_id, user_id, name, editable):
        if entry_id.startswith("local-"):
            self.done.emit("share", False, self._app.t["share_wait_sync"])
            return
        local_id = "pending-" + uuid.uuid4().hex
        self._local_shares.append({"id": local_id, "password": entry_id, "owner": {}, "receiver": {"id": user_id, "name": name or user_id},
                                   "editable": bool(editable), "pending": True})
        self.changed.emit()

        def forget():
            self._local_shares = [x for x in self._local_shares if x["id"] != local_id]

        def settle(_result=None):
            forget()
            self.refresh()
        self._online_job("share", lambda api: api.share(entry_id, user_id, editable), settle,
                         undo=lambda: (forget(), self.changed.emit()))

    @Slot(str, bool)
    def setShareEditable(self, share_id, editable):
        if share_id.startswith("pending-"):
            return
        self._share_edits[share_id] = bool(editable)
        self.changed.emit()

        def settle(_result=None):
            self._share_edits.pop(share_id, None)
            self.refresh()
        self._online_job("share", lambda api: api.update_share(share_id, editable), settle,
                         undo=lambda: (self._share_edits.pop(share_id, None), self.changed.emit()))

    @Slot(str)
    def unshare(self, share_id):
        if share_id.startswith("pending-"):
            return
        self._hidden_shares.add(share_id)
        self.changed.emit()

        def settle(_result=None):
            self._hidden_shares.discard(share_id)
            self.refresh()
        self._online_job("share", lambda api: api.unshare(share_id), settle,
                         undo=lambda: (self._hidden_shares.discard(share_id), self.changed.emit()))

    @Slot(str)
    def changePassword(self, entry_id):
        """The site's own page for a new password (/.well-known/change-password), else the site itself."""
        e = self._entries.get(entry_id)
        if not e:
            return
        link = sites.link(e.get("url"))
        host = sites.host(e.get("url"))
        if not host:
            return

        # at once: the window says the page is coming; without an answer from the cloud, the site itself opens
        self._app.toast.emit(self._app.t["change_opening"])
        api = self.api()

        def run():
            try:
                url = api.change_url(host) if api else ""
            except Exception:
                url = ""
            self._ran.emit(lambda: self._app.openUrl(url if url.startswith("https://") else link))
        threading.Thread(target=run, daemon=True).start()

    # ---- site icons ----------------------------------------------------------------------------------------
    def _fetch_icon(self, site):
        if not site or site in self._icon_asked:
            return
        self._icon_asked.add(site)
        miss = ICONS / f"{site}.none"
        try:
            if time.time() - miss.stat().st_mtime < ICON_RETRY:
                return
        except OSError:
            pass
        api = self.api()
        if api is None:
            return

        def run():
            try:
                raw = api.favicon(site, 64)
            except ApiError:
                self._icon_asked.discard(site)      # offline: asked again later
                return
            if not raw:
                miss.touch()
                return
            path = ICONS / f"{site}.png"
            try:
                from PySide6.QtGui import QImage
                image = QImage.fromData(raw)
                if image.isNull() or image.width() < 16:
                    miss.touch()
                    return
                image.save(str(path), "PNG")
            except Exception:
                return
            self._icon_ready.emit(site)
        self._icons.submit(run)

    def _icon_arrived(self, site):
        path = ICONS / f"{site}.png"
        self._icon_files[site] = QUrl.fromLocalFile(str(path)).toString() + f"?{int(time.time())}"
        for row in self._items:
            if row["site"] == site:
                row["icon"] = self._icon_files[site]
        self.iconsChanged.emit()
        self.changed.emit()

    @Slot(str, result=str)
    def iconFor(self, site):
        return self._icon_files.get(site, "")

    # ---- import and export ---------------------------------------------------------------------------------
    @Slot(str)
    def readImport(self, path):
        path = QUrl(path).toLocalFile() if path.startswith("file:") else path

        def run():
            result = importer.read(path)
            if result.get("rows") is not None:
                known = {(sites.site_of(e.get("url")), fold(e.get("username")), e.get("password"))
                         for e in self._entries.values() if not e.get("trashed")}
                fresh = [r for r in result["rows"] if (sites.site_of(r["url"]), fold(r["username"]), r["password"]) not in known]
                result["duplicates"] = len(result["rows"]) - len(fresh)
                result["rows"] = fresh
            self._import = result
            preview = {k: v for k, v in result.items() if k != "rows"}
            preview["count"] = len(result.get("rows") or [])
            preview["codes"] = sum(1 for r in result.get("rows") or [] if r.get("otp"))
            self.importReady.emit(preview)
        threading.Thread(target=run, daemon=True).start()

    @Slot(result=int)
    def confirmImport(self):
        rows = (self._import or {}).get("rows") or []
        if not self._vault:
            return 0
        for r in rows:
            fields = []
            config = totp.parse(r.get("otp") or "")
            if config:
                fields.append({"label": totp.FIELD_LABEL, "type": "secret", "value": totp.uri(config, r["username"], r["label"])})
            self._vault.save_entry({"label": r["label"] or sites.site_of(r["url"]) or r["username"], "username": r["username"],
                                    "password": r["password"], "url": r["url"], "notes": r.get("notes") or "",
                                    "customFields": fields, "folder": ROOT_FOLDER, "favorite": bool(r.get("favorite")),
                                    "tags": []})
        self._import = None
        self._changed_here()
        return len(rows)

    @Slot(str, result=bool)
    def exportCsv(self, path):
        """Every entry, readable by Chrome, Firefox, Bitwarden, Apple Passwords (and this app's import)."""
        path = QUrl(path).toLocalFile() if path.startswith("file:") else path
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", newline="", encoding="utf-8") as handle:
                out = csv.writer(handle)
                out.writerow(["name", "url", "username", "password", "note", "totp"])
                for e in sorted(self._entries.values(), key=lambda e: fold(title_of(e))):
                    if e.get("trashed"):
                        continue
                    fields = e.get("customFields") or []
                    index = totp.find(fields)
                    otp = totp.parse(fields[index]["value"]) if index >= 0 else None
                    out.writerow([e.get("label") or "", e.get("url") or "", e.get("username") or "", e.get("password") or "",
                                  e.get("notes") or "", totp.uri(otp, e.get("username"), e.get("label")) if otp else ""])
            return True
        except OSError:
            return False

    @Slot(result=str)
    def exportName(self):
        return str(Path.home() / f"{self._app.t['export_file']}-{time.strftime('%Y-%m-%d')}.csv")
