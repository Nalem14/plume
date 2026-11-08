"""The Code panel on the right of a session (as Cursor's): the folder's files, what changed (this turn, not committed,
the commits), the plan, the terminals. Read off the window's thread, handed back by signals; nothing here writes in the
project except what the user asks (a commit goes through CodeChat.commit, an undo through its checkpoints)."""
import re
import subprocess
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Property, Signal, Slot
from PySide6.QtGui import QDesktopServices

import ornis_code

MAX_DIFF_LINES = 4000
MAX_PREVIEW = 400 * 1024
MAX_PREVIEW_LINES = 6000
IMAGES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".ico"}
HUNK = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def _git(folder, *args, timeout=20) -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(folder), *args], capture_output=True, timeout=timeout,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.decode("utf-8", "replace") if out.returncode == 0 else None


def parse_unified(text: str) -> list[dict]:
    """A unified diff as rows {t: '+'|'-'|' '|'@', s, o, n}: o and n are the line numbers before and after."""
    rows, old, new = [], 0, 0
    for line in text.splitlines():
        if line.startswith(("diff --git", "index ", "--- ", "+++ ", "new file mode", "deleted file mode", "similarity", "rename ",
                            "old mode", "new mode", "Binary files")):
            if line.startswith("Binary files"):
                rows.append({"t": "@", "s": "binary", "o": 0, "n": 0})
            continue
        m = HUNK.match(line)
        if m:
            old, new = int(m.group(1)), int(m.group(2))
            rows.append({"t": "@", "s": line, "o": 0, "n": 0})
        elif line.startswith("+"):
            rows.append({"t": "+", "s": line[1:], "o": 0, "n": new})
            new += 1
        elif line.startswith("-"):
            rows.append({"t": "-", "s": line[1:], "o": old, "n": 0})
            old += 1
        elif line.startswith(" ") or line == "":
            rows.append({"t": " ", "s": line[1:], "o": old, "n": new})
            old, new = old + 1, new + 1
        if len(rows) >= MAX_DIFF_LINES:
            rows.append({"t": "@", "s": "…", "o": 0, "n": 0})
            break
    return rows


def text_diff(old: str, new: str) -> list[dict]:
    import difflib  # noqa: PLC0415
    lines = difflib.unified_diff((old or "").splitlines(), (new or "").splitlines(), lineterm="", n=3)
    return parse_unified("\n".join(lines))


def plan_doc(folder) -> dict:
    """The last plan of the project (.ornis/plans/*.md, written in Plan mode): its title, text and steps."""
    plans = Path(folder) / ornis_code.ORNIS_DIR / "plans" if folder else None
    if not plans or not plans.is_dir():
        return {}
    files = sorted((p for p in plans.glob("*.md") if p.is_file()), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return {}
    path = files[0]
    try:
        text = path.read_text(errors="replace")[:200000]
    except OSError:
        return {}
    title, steps = "", []
    for line in text.splitlines():
        s = line.strip()
        if not title and s.startswith("#"):
            title = s.lstrip("#").strip()
        m = re.match(r"^(?:[-*]\s+\[( |x|X)\]\s+|(\d+)[.)]\s+)(.+)$", s)
        if m:
            steps.append({"text": re.sub(r"[*_`]", "", m.group(3)).strip(), "done": (m.group(1) or "").lower() == "x"})
    return {"path": str(path), "name": path.name, "title": title or path.stem, "text": text, "steps": steps[:80],
            "updated": path.stat().st_mtime, "count": len(files)}


class Bench(QObject):
    changed = Signal()               # files, status, commits
    diffChanged = Signal()
    commitChanged = Signal()
    turnChanged = Signal()
    _loaded = Signal(str, object)
    _diffed = Signal(str, object)
    _shown = Signal(str, object)

    def __init__(self, code):
        super().__init__(code)
        self._code = code
        self._folder = ""
        self._files: list[str] = []
        self._tree: dict = {}            # dir -> ([subdirs], [files])
        self._status: dict = {}          # path -> {status, added, removed}
        self._dirty_dirs: set = set()
        self._commits: list = []
        self._is_git = False
        self._branch = ""
        self._plan: dict = {}
        self._diff: dict = {}
        self._commit: dict = {}
        self._loading = False
        self._stamp = 0.0
        self._loaded.connect(self._on_loaded)
        self._diffed.connect(self._on_diffed)
        self._shown.connect(self._on_shown)
        code.changed.connect(self._follow)

    # ---- the folder followed -------------------------------------------------------------------------------------
    def _follow(self):
        folder = self._code._folder
        if folder != self._folder:
            self._folder = folder
            self._files, self._tree, self._status, self._dirty_dirs, self._commits = [], {}, {}, set(), []
            self._is_git, self._plan, self._diff, self._commit = False, {}, {}, {}
            self.changed.emit()
            self.diffChanged.emit()
            self.commitChanged.emit()
            if folder:
                self.refresh()
        self.turnChanged.emit()

    @Slot()
    def refresh(self):
        """Read the folder again (after a turn, a commit, a click on « Actualiser »)."""
        folder = self._folder
        if not folder:
            return
        self._loading = True
        self.changed.emit()
        threading.Thread(target=lambda: self._loaded.emit(folder, self._collect(folder)), daemon=True,
                         name="ornis-bench").start()

    def _collect(self, folder) -> dict:
        self._code._file_list_for = ""                       # the list again: files made since
        files = self._code._list_files(folder)
        status, commits, git, branch = {}, [], False, ""
        if (Path(folder) / ".git").exists() and ornis_code.git_usable():
            git = True
            branch = (_git(folder, "rev-parse", "--abbrev-ref", "HEAD") or "").strip()
            porcelain = _git(folder, "status", "--porcelain=v1", "-z", "--untracked-files=all") or ""
            parts = porcelain.split("\0")
            i = 0
            while i < len(parts):
                entry = parts[i]
                i += 1
                if len(entry) < 4:
                    continue
                xy, path = entry[:2], entry[3:]
                if xy[0] in "RC":                          # a rename: its old name follows
                    i += 1
                letter = "A" if xy in ("??", "A ", "AM") else "D" if "D" in xy else "R" if "R" in xy else "M"
                status[path] = {"path": path, "status": letter, "added": 0, "removed": 0, "untracked": xy == "??"}
            numstat = _git(folder, "diff", "HEAD", "--numstat") or _git(folder, "diff", "--numstat") or ""
            for line in numstat.splitlines():
                bits = line.split("\t")
                if len(bits) == 3 and bits[2] in status:
                    status[bits[2]]["added"] = int(bits[0]) if bits[0].isdigit() else 0
                    status[bits[2]]["removed"] = int(bits[1]) if bits[1].isdigit() else 0
            for s in status.values():
                if s["untracked"]:
                    s["added"] = ornis_code.Checkpoints._lines(Path(folder) / s["path"])
            log = _git(folder, "log", "-n", "60", "--pretty=format:%H%x1f%h%x1f%s%x1f%an%x1f%at%x1f%D%x1e") or ""
            for row in log.split("\x1e"):
                bits = row.strip("\n").split("\x1f")
                if len(bits) >= 5:
                    commits.append({"sha": bits[0], "short": bits[1], "subject": bits[2], "author": bits[3],
                                    "time": int(bits[4] or 0), "refs": bits[5] if len(bits) > 5 else ""})
        return {"files": files, "status": status, "commits": commits, "git": git, "branch": branch, "plan": plan_doc(folder)}

    def _on_loaded(self, folder, data):
        if folder != self._folder:
            return
        self._loading = False
        self._files = list(data["files"])
        for path in data["status"]:                         # a new file not listed yet (made this very second)
            if path not in self._files and not path.endswith("/"):
                self._files.append(path)
        tree: dict = {"": ([], [])}
        for rel in sorted(self._files, key=str.lower):
            parts = rel.split("/")
            for depth in range(len(parts) - 1):
                parent, here = "/".join(parts[:depth]), "/".join(parts[:depth + 1])
                if here not in tree:
                    tree[here] = ([], [])
                    tree[parent][0].append(here)
            tree["/".join(parts[:-1])][1].append(rel)
        self._tree = tree
        self._status = data["status"]
        self._dirty_dirs = {"/".join(p.split("/")[:i]) for p in self._status for i in range(1, len(p.split("/")))}
        self._commits, self._is_git, self._branch, self._plan = data["commits"], data["git"], data["branch"], data["plan"]
        self._stamp = time.time()
        self.changed.emit()

    # ---- what QML reads ------------------------------------------------------------------------------------------
    @Property(bool, notify=changed)
    def loading(self):
        return self._loading

    @Property(bool, notify=changed)
    def isGit(self):
        return self._is_git

    @Property(str, notify=changed)
    def branch(self):
        return self._branch

    @Property(int, notify=changed)
    def fileCount(self):
        return len(self._files)

    @Property("QVariantList", notify=changed)
    def status(self):
        return sorted(self._status.values(), key=lambda s: s["path"].lower())

    @Property("QVariantList", notify=changed)
    def commits(self):
        now = time.time()
        return [dict(c, ago=self._ago(now - c["time"])) for c in self._commits]

    @Property("QVariantMap", notify=changed)
    def planDoc(self):
        return self._plan

    @Property("QVariantMap", notify=diffChanged)
    def diff(self):
        return self._diff

    @Property("QVariantMap", notify=commitChanged)
    def commit(self):
        return self._commit

    @Property("QVariantMap", notify=turnChanged)
    def turn(self):
        """The last turn that changed files and is not undone: {rev, files, added, removed}, {} when none."""
        for row in reversed(self._code._items.rows):
            if row.get("kind") == "changes" and not row.get("undone"):
                return {"rev": row["rev"], "files": row.get("files") or [], "added": row.get("added", 0),
                        "removed": row.get("removed", 0), "reverted": row.get("reverted") or []}
        return {}

    def _ago(self, seconds: float) -> str:
        t = self._code._app._t
        if seconds < 3600:
            return t.get("ago_minutes", "%1 min").replace("%1", str(max(1, int(seconds // 60))))
        if seconds < 86400:
            return t.get("ago_hours", "%1 h").replace("%1", str(int(seconds // 3600)))
        days = int(seconds // 86400)
        return t.get("ago_days", "%1 d").replace("%1", str(days))

    @Slot("QVariantList", str, result="QVariantList")
    def rows(self, expanded, query):
        """The tree as it shows: the folders opened (expanded), or the files matching a filter, flat."""
        q = (query or "").strip().lower()
        if q:
            found = [p for p in self._files if q in p.rsplit("/", 1)[-1].lower()]
            found += [p for p in self._files if q in p.lower() and p not in found][:200]
            return [self._row(p, 0, False) for p in found[:300]]
        opened, out = set(expanded or []), []

        def walk(directory, depth):
            dirs, files = self._tree.get(directory, ([], []))
            for d in sorted(dirs, key=lambda x: x.rsplit("/", 1)[-1].lower()):
                out.append(self._row(d, depth, True, d in opened))
                if d in opened:
                    walk(d, depth + 1)
                if len(out) > 5000:
                    return
            for f in files:
                out.append(self._row(f, depth, False))
        walk("", 0)
        return out

    def _row(self, path, depth, is_dir, is_open=False):
        name = path.rsplit("/", 1)[-1]
        st = self._status.get(path)
        return {"path": path, "name": name, "dir": is_dir, "depth": depth, "open": is_open,
                "status": st["status"] if st else "", "dirty": is_dir and path in self._dirty_dirs,
                "ext": "" if is_dir or "." not in name else name.rsplit(".", 1)[-1].lower()}

    # ---- a file ---------------------------------------------------------------------------------------------------
    def _inside(self, rel) -> Path | None:
        if not self._folder or not rel:
            return None
        root = Path(self._folder).resolve()
        target = (root / rel).resolve()
        return target if target == root or root in target.parents else None

    @Slot(str, result="QVariantMap")
    def read(self, rel):
        """A file to look at: {lines, binary, image, truncated, size}."""
        path = self._inside(rel)
        if not path or not path.is_file():
            return {"missing": True}
        size = path.stat().st_size
        if path.suffix.lower() in IMAGES:
            return {"image": QUrl.fromLocalFile(str(path)).toString(), "size": size}
        try:
            with path.open("rb") as handle:
                data = handle.read(MAX_PREVIEW)
        except OSError:
            return {"missing": True}
        if b"\0" in data[:8000]:
            return {"binary": True, "size": size}
        lines = data.decode("utf-8", "replace").splitlines()
        return {"lines": lines[:MAX_PREVIEW_LINES], "size": size,
                "truncated": size > MAX_PREVIEW or len(lines) > MAX_PREVIEW_LINES, "count": len(lines)}

    @Slot(str)
    def openFile(self, rel):
        path = self._inside(rel)
        if path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    @Slot(str)
    def reveal(self, rel):
        path = self._inside(rel) if rel else Path(self._folder) if self._folder else None
        if path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path if path.is_dir() else path.parent)))

    @Slot(str, result=str)
    def absolute(self, rel):
        path = self._inside(rel)
        return str(path) if path else ""

    # ---- diffs ------------------------------------------------------------------------------------------------------
    @Slot(str, str, str)
    def loadDiff(self, scope, ref, rel):
        """The diff of one file: scope « work » (not committed), « commit » (ref = sha), « turn » (ref = checkpoint)."""
        folder, key = self._folder, f"{scope}:{ref}:{rel}"
        self._diff = {"key": key, "path": rel, "scope": scope, "loading": True, "lines": []}
        self.diffChanged.emit()

        def work():
            lines: list = []
            try:
                if scope == "commit":
                    lines = parse_unified(_git(folder, "show", "--format=", ref, "--", rel) or "")
                elif scope == "turn":
                    store = ornis_code.Checkpoints(folder)
                    before = store._manifest(ref).get(rel)
                    old = (store.store / "objects" / before[:2] / before).read_text(errors="replace") if before else ""
                    target = Path(folder) / rel
                    new = target.read_text(errors="replace") if target.is_file() else ""
                    lines = text_diff(old, new)
                else:
                    st = self._status.get(rel) or {}
                    if st.get("untracked"):
                        target = Path(folder) / rel
                        new = target.read_text(errors="replace") if target.is_file() else ""
                        lines = text_diff("", new)
                    else:
                        lines = parse_unified(_git(folder, "diff", "HEAD", "--", rel) or _git(folder, "diff", "--", rel) or "")
            except Exception:  # noqa: BLE001
                lines = []
            self._diffed.emit(key, lines)
        threading.Thread(target=work, daemon=True, name="ornis-bench-diff").start()

    def _on_diffed(self, key, lines):
        if self._diff.get("key") != key:
            return
        added = sum(1 for r in lines if r["t"] == "+")
        removed = sum(1 for r in lines if r["t"] == "-")
        self._diff = dict(self._diff, loading=False, lines=lines, added=added, removed=removed,
                          binary=any(r["s"] == "binary" for r in lines if r["t"] == "@"))
        self.diffChanged.emit()

    @Slot()
    def closeDiff(self):
        self._diff = {}
        self.diffChanged.emit()

    @Slot(str)
    def loadCommit(self, sha):
        """The files of a commit, with what each gained and lost."""
        folder = self._folder
        if self._commit.get("sha") == sha:
            self._commit = {}
            self.commitChanged.emit()
            return
        self._commit = {"sha": sha, "loading": True, "files": []}
        self.commitChanged.emit()

        def work():
            files = {}
            for line in (_git(folder, "show", "--format=", "--name-status", sha) or "").splitlines():
                bits = line.split("\t")
                if len(bits) >= 2:
                    files[bits[-1]] = {"path": bits[-1], "status": bits[0][:1], "added": 0, "removed": 0}
            for line in (_git(folder, "show", "--format=", "--numstat", sha) or "").splitlines():
                bits = line.split("\t")
                if len(bits) == 3 and bits[2] in files:
                    files[bits[2]]["added"] = int(bits[0]) if bits[0].isdigit() else 0
                    files[bits[2]]["removed"] = int(bits[1]) if bits[1].isdigit() else 0
            self._shown.emit(sha, list(files.values())[:500])
        threading.Thread(target=work, daemon=True, name="ornis-bench-commit").start()

    def _on_shown(self, sha, files):
        if self._commit.get("sha") == sha:
            self._commit = {"sha": sha, "loading": False, "files": files}
            self.commitChanged.emit()

    # ---- the plan --------------------------------------------------------------------------------------------------
    @Slot()
    def openPlan(self):
        if self._plan.get("path"):
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._plan["path"]))


def home_folder() -> str:
    return str(Path.home())


def is_home(folder: str) -> bool:
    try:
        return bool(folder) and Path(folder).resolve() == Path.home().resolve()
    except OSError:
        return False

