"""The projects of the Work mode, as Claude and ChatGPT have them: a name, instructions that apply to each of its
conversations, a folder for its files (in the Drive, seen from everywhere, or on this computer) and its conversations
grouped under it. Kept by the cloud (orneos app, OrnisProjects: the same in every Plume, Orneos OS and the cloud), with
a copy here for offline use. A question asked in a project ends with « (Projet: <id>) »: the agent reads the project
at each question (its instructions, its folder, what its other conversations were about). Nothing waits for the cloud:
a change shows at once, a refusal comes back as a toast.
"""
import json
import platform
import shutil
import threading
import time
import uuid
from pathlib import Path

from PySide6.QtCore import QObject, Property, QSysInfo, QTimer, QUrl, Signal, Slot

import system
from ornis_chat import Chat as Client, Error
from ornis_core.chat import _when

CACHE = system.DATA / "ornis-projects.json"
MAX_FILES = 200


def _host() -> str:
    """This computer, so that a project's folder on it is not looked for on another one."""
    raw = bytes(QSysInfo.machineUniqueId()).decode(errors="ignore").strip()
    return (raw or platform.node() or "here")[:64]


def _local(raw: str) -> str:
    raw = str(raw or "").strip()
    return QUrl(raw).toLocalFile() if raw.startswith("file://") else raw


class Projects(QObject):
    changed = Signal()
    filesChanged = Signal()
    toast = Signal(str)
    _loaded = Signal(object, str)         # data from the cloud (or None), the account it belongs to
    _listed = Signal(str, object, str)    # project id, files, problem
    _refresh = Signal()

    def __init__(self, app, chat):
        super().__init__()
        self._app = app
        self._chat = chat
        self._t = app.t
        self._host = _host()
        self._data = {"projects": [], "sessions": {}}
        self._account = ""
        self._dirty = False
        self._opened = ""
        self._files, self._files_state = [], ""
        self._save = QTimer(self, singleShot=True, interval=400, timeout=self._push)
        self._loaded.connect(self._on_loaded)
        self._listed.connect(self._on_listed)
        self._refresh.connect(self.refreshFiles)
        app.accountChanged.connect(self.reload)
        chat.changed.connect(self.changed)      # counts and last activity follow the conversations
        self.reload()

    # ---- the cloud, and the copy here ------------------------------------------------------------------------
    def _client(self):
        account = self._app.account()
        return Client(*account) if account else None

    def _key(self):
        account = self._app.account()
        return f"{account[1]}@{account[0]}" if account else ""

    @Slot()
    def reload(self):
        key = self._key()
        if key != self._account:                # another account: its own projects, never the previous one's
            self._account, self._opened = key, ""
            self._data = self._read_cache(key)
            self.changed.emit()
        client = self._client()
        if not client:
            return

        def work():
            try:
                self._loaded.emit(client.projects(), key)
            except Error:
                self._loaded.emit(None, key)
        threading.Thread(target=work, daemon=True).start()

    def _read_cache(self, key):
        try:
            data = json.loads(CACHE.read_text()).get(key) or {}
        except (OSError, ValueError, AttributeError):
            data = {}
        return {"projects": [p for p in data.get("projects") or [] if isinstance(p, dict)],
                "sessions": {str(k): str(v) for k, v in (data.get("sessions") or {}).items()}}

    def _write_cache(self):
        try:
            all_ = json.loads(CACHE.read_text()) if CACHE.exists() else {}
        except (OSError, ValueError):
            all_ = {}
        all_[self._account] = self._data
        try:
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            tmp = CACHE.with_suffix(".tmp")
            tmp.write_text(json.dumps(all_, ensure_ascii=False))
            tmp.replace(CACHE)
        except OSError:
            pass

    def _on_loaded(self, data, key):
        if key != self._account:
            return
        if data is not None and not self._dirty:
            self._data = data
            self._write_cache()
        self._migrate()
        self.changed.emit()

    def _migrate(self):
        """Once: the folders the conversations of this computer were tied to (before projects) become projects."""
        if self._app.pref("projects_migrated"):
            return
        self._app.setPref("projects_migrated", True)
        mapping = dict(self._app.pref("session_workspaces") or {})
        by_folder = {}
        for sid, path in mapping.items():
            if path and sid not in self._data["sessions"]:
                by_folder.setdefault(str(path), []).append(str(sid))
        known = {p["folder"].get("path") for p in self._data["projects"] if p.get("folder", {}).get("kind") == "local"}
        for path, sids in by_folder.items():
            if path in known:
                continue
            pid = self._new(Path(path).name or path, "local", path, "")
            for sid in sids:
                self._data["sessions"][sid] = pid
        if by_folder:
            self._changed_here()

    def _changed_here(self):
        self._dirty = True
        self._write_cache()
        self.changed.emit()
        self._save.start()

    def _push(self):
        client = self._client()
        if not client:
            return
        data, key = json.loads(json.dumps(self._data)), self._account

        def work():
            try:
                saved = client.set_projects(data["projects"], data["sessions"])
                self._loaded.emit(saved, key) if data == self._data else None
            except Error as error:
                if error.code:                       # offline: sent again at the next change or start
                    self.toast.emit(self._t["project_save_failed"])
            finally:
                if data == self._data:
                    self._dirty = False
        threading.Thread(target=work, daemon=True).start()

    # ---- the list --------------------------------------------------------------------------------------------
    def _find(self, pid):
        return next((p for p in self._data["projects"] if p.get("id") == pid), None)

    def _row(self, p, rows):
        folder = p.get("folder") or {}
        kind, path = folder.get("kind") or "", folder.get("path") or ""
        here = kind == "local" and folder.get("host") == self._host and Path(path).is_dir()
        mine = [s for s in rows if s.get("project") == p["id"]]
        last = max([int(s.get("timestamp") or 0) for s in mine] + [int(p.get("created") or 0)])
        if kind == "drive":
            sub = self._t["project_in_drive"].replace("%1", path)
        elif kind == "local":
            try:
                shown = "~/" + str(Path(path).relative_to(Path.home()))
            except ValueError:
                shown = path
            sub = shown if folder.get("host") == self._host else self._t["project_other_computer"].replace("%1", folder.get("hostName") or "?")
        else:
            sub = ""
        return dict(p, initial=(p["name"][:1] or "?").upper(), count=len(mine), last=last,
                    when=_when(last, self._app.lang) if last else "", folderSub=sub, folderHere=here,
                    folderName=Path(path).name if path else "", folderMissing=kind == "local" and folder.get("host") == self._host and not here)

    @Property("QVariantList", notify=changed)
    def items(self):
        rows = self._chat.allSessions
        out = [self._row(p, rows) for p in self._data["projects"]]
        out.sort(key=lambda r: -r["last"])
        return out

    @Property("QVariantMap", notify=changed)
    def current(self):
        """The open project's page (empty when none is open)."""
        p = self._find(self._opened)
        return self._row(p, self._chat.allSessions) if p else {}

    @Property(str, notify=changed)
    def opened(self):
        return self._opened

    def projectOf(self, session_id) -> str:
        return self._data["sessions"].get(str(session_id or ""), "")

    def name(self, pid) -> str:
        p = self._find(pid)
        return p["name"] if p else ""

    def local_folder(self, session_id="", pid="") -> str:
        """The folder of the project on this computer (the workspace of its conversations), else ""."""
        p = self._find(pid or self.projectOf(session_id))
        folder = (p or {}).get("folder") or {}
        if folder.get("kind") == "local" and folder.get("host") == self._host and Path(folder.get("path") or "").is_dir():
            return folder["path"]
        return ""

    # ---- making and changing them ----------------------------------------------------------------------------
    def _new(self, name, kind, path, instructions):
        pid = uuid.uuid4().hex[:12]
        folder = {"kind": kind if kind in ("drive", "local") and path else "", "path": path if kind in ("drive", "local") else "",
                  "host": self._host if kind == "local" else "", "hostName": platform.node()[:80] if kind == "local" else ""}
        self._data["projects"].insert(0, {"id": pid, "name": str(name).strip()[:60], "tone": sum(map(ord, pid)) % 6,
                                          "instructions": str(instructions or "").strip()[:4000], "folder": folder,
                                          "memory": True, "created": int(time.time())})
        return pid

    @Slot(str, str, str, str, result=str)
    def create(self, name, kind, path, instructions):
        """A new project: in the Drive, its folder is made if it does not exist (/Projets/<name> by default)."""
        name = str(name or "").strip() or self._t["project_untitled"]
        path = _local(path) if kind == "local" else str(path or "").strip()
        if kind == "drive" and not path:
            path = "/" + self._t["project_drive_root"] + "/" + name.replace("/", "-")
        pid = self._new(name, kind, path, instructions)
        self._changed_here()
        if kind == "drive":
            self._make_drive_folder(path)
        self.open(pid)
        return pid

    def _make_drive_folder(self, path):
        client = self._client()
        if not client:
            return

        def work():
            try:
                client.make_folder(path)
            except Error as error:
                if error.code:
                    self.toast.emit(self._t["project_folder_failed"])
        threading.Thread(target=work, daemon=True).start()

    @Slot(str, str, "QVariant")
    def update(self, pid, key, value):
        """name, instructions, memory or tone."""
        p = self._find(pid)
        if not p or key not in ("name", "instructions", "memory", "tone"):
            return
        value = value.toVariant() if hasattr(value, "toVariant") else value
        if key == "name":
            value = str(value or "").strip()[:60] or p["name"]
        elif key == "instructions":
            value = str(value or "").strip()[:4000]
        elif key == "memory":
            value = bool(value)
        else:
            value = max(0, min(5, int(value or 0)))
        if p.get(key) != value:
            p[key] = value
            self._changed_here()

    @Slot(str, str, str)
    def setFolder(self, pid, kind, path):
        """Where its files are: a Drive folder, a folder of this computer, or none."""
        p = self._find(pid)
        if not p:
            return
        path = _local(path) if kind == "local" else str(path or "").strip()
        p["folder"] = {"kind": kind if kind in ("drive", "local") and path else "", "path": path,
                       "host": self._host if kind == "local" else "", "hostName": platform.node()[:80] if kind == "local" else ""}
        self._changed_here()
        if kind == "drive" and path:
            self._make_drive_folder(path)
        if self._chat.project == pid:
            self._chat.projectFolderChanged()
        if pid == self._opened:
            self.refreshFiles()

    @Slot(str)
    def remove(self, pid):
        """The project goes; its conversations stay, out of any project (as in the other assistants)."""
        if not self._find(pid):
            return
        self._data["projects"] = [p for p in self._data["projects"] if p.get("id") != pid]
        self._data["sessions"] = {s: v for s, v in self._data["sessions"].items() if v != pid}
        if self._opened == pid:
            self._opened = ""
        self._changed_here()
        self._chat.changed.emit()

    @Slot(str, str)
    def assign(self, session_id, pid):
        """A conversation into a project ("" : out of any)."""
        sid = str(session_id or "")
        if not sid:
            return
        if pid and self._find(pid):
            if self._data["sessions"].get(sid) == pid:
                return
            self._data["sessions"][sid] = pid
        elif sid in self._data["sessions"]:
            del self._data["sessions"][sid]
        else:
            return
        self._changed_here()
        self._chat.changed.emit()
        if sid == self._chat.current:
            self._chat.projectFolderChanged()

    # ---- the project's page ----------------------------------------------------------------------------------
    @Slot(str)
    def open(self, pid):
        self._opened = pid if self._find(pid) else ""
        self._files, self._files_state = [], ""
        self.changed.emit()
        self.filesChanged.emit()
        if self._opened:
            self.refreshFiles()

    @Slot()
    def close(self):
        self.open("")

    @Slot(str)
    def newChat(self, pid):
        """A new conversation in the project: its instructions and folder go with each question."""
        self._chat.newChatInProject(pid if self._find(pid) else "")

    @Property("QVariantList", notify=filesChanged)
    def files(self):
        return self._files

    @Property(str, notify=filesChanged)
    def filesState(self):
        return self._files_state

    @Slot()
    def refreshFiles(self):
        p = self._find(self._opened)
        folder = (p or {}).get("folder") or {}
        kind, path, pid = folder.get("kind"), folder.get("path") or "", self._opened
        if not p or not kind:
            self._files, self._files_state = [], ""
            self.filesChanged.emit()
            return
        self._files_state = "loading"
        self.filesChanged.emit()
        if kind == "local":
            if folder.get("host") != self._host:
                self._listed.emit(pid, [], "elsewhere")
                return
            try:
                rows = [{"name": e.name, "path": str(e), "folder": e.is_dir(), "size": e.stat().st_size if e.is_file() else 0}
                        for e in Path(path).iterdir() if not e.name.startswith(".")]
            except OSError:
                self._listed.emit(pid, [], "missing")
                return
            rows.sort(key=lambda r: (not r["folder"], r["name"].lower()))
            self._listed.emit(pid, rows[:MAX_FILES], "")
            return
        client = self._client()
        if not client:
            return

        def work():
            try:
                rows = client.folder(path)
                self._listed.emit(pid, [{"name": r["name"], "path": r["path"], "folder": r["folder"], "size": r["size"],
                                         "file_id": r["file_id"]} for r in rows][:MAX_FILES], "")
            except Error as error:
                if error.code == 404:              # the folder went away: made again, empty
                    self._make_drive_folder(path)
                    self._listed.emit(pid, [], "")
                else:
                    self._listed.emit(pid, [], "offline" if error.code == 0 else "failed")
        threading.Thread(target=work, daemon=True).start()

    def _on_listed(self, pid, rows, problem):
        if pid != self._opened:
            return
        self._files, self._files_state = list(rows), problem
        self.filesChanged.emit()

    @Slot("QVariantList")
    def addFiles(self, urls):
        """Files dropped on the project's page (or chosen): copied into its folder, in the Drive or here."""
        p = self._find(self._opened)
        folder = (p or {}).get("folder") or {}
        paths = [Path(_local(u.toString() if hasattr(u, "toString") else u)) for u in urls]
        paths = [x for x in paths if x.is_file()]
        if not p or not paths:
            return
        if not folder.get("kind"):
            self.toast.emit(self._t["project_no_folder"])
            return
        if folder["kind"] == "local":
            if folder.get("host") != self._host:
                self.toast.emit(self._t["project_other_computer"].replace("%1", folder.get("hostName") or "?"))
                return
            for src in paths:
                try:
                    shutil.copy2(src, Path(folder["path"]) / src.name)
                except OSError:
                    self.toast.emit(self._t["project_add_failed"].replace("%1", src.name))
            self.refreshFiles()
            return
        client, base = self._client(), folder["path"].rstrip("/")
        if not client:
            return
        # shown at once; the Drive follows
        self._files = self._files + [{"name": x.name, "path": base + "/" + x.name, "folder": False, "size": x.stat().st_size,
                                      "file_id": ""} for x in paths if not any(f["name"] == x.name for f in self._files)]
        self.filesChanged.emit()

        def work():
            for src in paths:
                try:
                    client.put_file(base + "/" + src.name, src.read_bytes())
                except (Error, OSError):
                    self.toast.emit(self._t["project_add_failed"].replace("%1", src.name))
            self._refresh.emit()
        threading.Thread(target=work, daemon=True).start()

    @Slot(str)
    def openFolder(self, pid):
        """The folder in the Files app of the cloud (Drive) or of the computer."""
        p = self._find(pid or self._opened)
        folder = (p or {}).get("folder") or {}
        if folder.get("kind") == "drive":
            self._app.openCloud("/apps/files/?dir=" + QUrl.toPercentEncoding(folder["path"], b"/").data().decode())
        elif folder.get("kind") == "local" and folder.get("host") == self._host:
            self._app.openFolder(folder["path"])

    @Slot("QVariantMap")
    def openFile(self, row):
        p = self._find(self._opened)
        folder = (p or {}).get("folder") or {}
        if folder.get("kind") == "local":
            system.open_url(QUrl.fromLocalFile(row.get("path") or "").toString())
        elif row.get("file_id"):
            self._app.openCloud(f"/f/{row['file_id']}")
