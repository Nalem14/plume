"""The local copy of the photo library: the days of the timeline and their photos, the albums, people, places
and tags, the photos of the ones opened, and the changes not sent yet.

Every change is written here at once (the window shows it), as an operation in a queue that goes up in order
when the network allows. A change the cloud refuses is undone here and reported. After each pull from the
cloud, the operations still waiting are applied again, so what was done offline stays visible.

Plain Python (no Qt): the sync thread and the window both use it, under one lock.
"""
import json
import shutil
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import system
from photos_core.api import ApiError

DB = system.DATA / "photos.db"
STAGING = system.DATA / "photos-uploads"
UNSET = ("", "_empty_")                 # Memories' « not chosen yet »
FIRST_FOLDER, PHONE_FOLDER = "/Photos", "/InstantUpload"
BATCH = 1500          # photos per request when the days are loaded
RECHECK = 60          # days read again at each pull, in turn
BACKENDS = ("albums", "recognize", "places", "tags")
PARALLEL = 4          # requests at once for a run of the same change (175 photos into an album: seconds, not minutes)
PARALLEL_KINDS = ("fav", "album_add", "album_remove")

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS days (dayid INTEGER PRIMARY KEY, count INTEGER, loaded INTEGER DEFAULT -1);
CREATE TABLE IF NOT EXISTS photos (fileid INTEGER PRIMARY KEY, dayid INTEGER, pos INTEGER, etag TEXT, w INTEGER,
    h INTEGER, name TEXT, video INTEGER DEFAULT 0, duration INTEGER DEFAULT 0, live TEXT DEFAULT '',
    fav INTEGER DEFAULT 0, size INTEGER DEFAULT 0, added INTEGER DEFAULT 0, deleted INTEGER DEFAULT 0,
    outside INTEGER DEFAULT 0);
CREATE INDEX IF NOT EXISTS photos_day ON photos (dayid);
CREATE TABLE IF NOT EXISTS clusters (backend TEXT, id TEXT, name TEXT, count INTEGER, cover INTEGER,
    cover_etag TEXT, data TEXT, PRIMARY KEY (backend, id));
CREATE TABLE IF NOT EXISTS members (backend TEXT, id TEXT, fileid INTEGER, PRIMARY KEY (backend, id, fileid));
CREATE TABLE IF NOT EXISTS paths (fileid INTEGER PRIMARY KEY, path TEXT);
CREATE TABLE IF NOT EXISTS ops (n INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, data TEXT, tries INTEGER DEFAULT 0);
"""

PHOTO = ("fileid", "dayid", "pos", "etag", "w", "h", "name", "video", "duration", "live", "fav", "size", "added")


def _photo(row, pos):
    return (int(row["fileid"]), int(row.get("dayid_real") or row.get("dayid") or 0), pos, str(row.get("etag") or ""),
            int(row.get("w") or 0), int(row.get("h") or 0), str(row.get("basename") or ""),
            1 if row.get("isvideo") else 0, int(row.get("video_duration") or 0), str(row.get("liveid") or ""),
            1 if row.get("isfavorite") else 0, int(row.get("size") or 0), int(row.get("indexed_at") or 0))


# EXIF orientations as quarter turns to the right: upright (1, 6, 3, 8) and mirrored (2, 7, 4, 5)
_UPRIGHT, _MIRRORED = (1, 6, 3, 8), (2, 7, 4, 5)


def turned(orientation, turn):
    """The orientation after turning the photo by turn degrees (90 = a quarter to the right)."""
    ring = _MIRRORED if orientation in _MIRRORED else _UPRIGHT
    at = ring.index(orientation) if orientation in ring else 0
    return ring[(at + int(turn) // 90) % 4]


def cluster_filter(backend, cid, user):
    """The parameter that narrows Memories' days to one album (« owner/name »), person (« user/id »), place
    (its OpenStreetMap id), tag (its name) or a square of the map (« minLat,maxLat,minLon,maxLon »)."""
    if backend == "map":
        return {"mapbounds": cid}
    if backend == "archive":
        return {"archive": 1}
    return {backend: f"{user}/{cid}" if backend == "recognize" else cid}


class Store:
    def __init__(self, user):
        self.user = user
        self.lock = threading.RLock()
        self.hold = ()                       # deletions that can still be undone: not sent yet
        DB.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(DB), check_same_thread=False, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)
        if self.meta("user") not in (None, user):
            self._wipe()
        self.set_meta("user", user)
        self.db.commit()

    # ---- meta --------------------------------------------------------------------------------------------
    def meta(self, key, default=None):
        with self.lock:
            row = self.db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_meta(self, key, value):
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, str(value)))
            self.db.commit()

    @property
    def loaded(self):
        return self.meta("synced_at") is not None

    @property
    def synced_at(self):
        return int(float(self.meta("synced_at") or 0))

    @property
    def folders(self):
        return [p for p in (self.meta("timeline_path") or "").split(";") if p.strip()]

    def _wipe(self):
        with self.lock:
            for table in ("meta", "days", "photos", "clusters", "members", "paths", "ops"):
                self.db.execute(f"DELETE FROM {table}")
            self.db.commit()
        shutil.rmtree(STAGING, ignore_errors=True)

    def forget(self):
        """Signed out or another account: nothing of this one stays."""
        self._wipe()
        self.db.close()

    # ---- reading -----------------------------------------------------------------------------------------
    def photos(self):
        with self.lock:
            rows = self.db.execute("SELECT * FROM photos WHERE deleted = 0 AND outside = 0 "
                                   "ORDER BY dayid DESC, pos ASC").fetchall()
        return [dict(r) for r in rows]

    def photo_rows(self, fileids):
        """These photos, the library's and those of albums shared by others, newest first."""
        ids = [int(f) for f in fileids]
        out = []
        with self.lock:
            for i in range(0, len(ids), 500):
                chunk = ids[i:i + 500]
                out += [dict(r) for r in self.db.execute(
                    f"SELECT * FROM photos WHERE deleted = 0 AND fileid IN ({','.join('?' * len(chunk))})", chunk)]
        archived = self.archived()
        for p in out:
            self._mark(p, archived)
        out.sort(key=lambda p: (-p["dayid"], p["pos"]))
        return out

    def archived(self):
        """The photos of my archive: out of the timeline (outside), but mine."""
        return self.members("archive", "all")

    @staticmethod
    def _mark(p, archived):
        p["archived"] = 1 if p["fileid"] in archived else 0
        if p["archived"]:
            p["outside"] = 0

    def photo(self, fileid):
        with self.lock:
            row = self.db.execute("SELECT * FROM photos WHERE fileid = ?", (int(fileid),)).fetchone()
        if not row:
            return None
        p = dict(row)
        self._mark(p, self.archived())
        return p

    def clusters(self, backend):
        with self.lock:
            rows = self.db.execute("SELECT * FROM clusters WHERE backend = ? ORDER BY count DESC, name",
                                   (backend,)).fetchall()
        out = []
        for r in rows:
            item = dict(r)
            item["data"] = json.loads(item["data"] or "{}")
            out.append(item)
        return out

    def cluster(self, backend, cid):
        with self.lock:
            row = self.db.execute("SELECT * FROM clusters WHERE backend = ? AND id = ?", (backend, cid)).fetchone()
        if not row:
            return None
        item = dict(row)
        item["data"] = json.loads(item["data"] or "{}")
        return item

    def members(self, backend, cid):
        with self.lock:
            return {r[0] for r in self.db.execute("SELECT fileid FROM members WHERE backend = ? AND id = ?",
                                                    (backend, cid))}

    def has_members(self, backend, cid):
        with self.lock:
            return self.db.execute("SELECT 1 FROM meta WHERE key = ?", (f"members:{backend}:{cid}",)).fetchone() is not None

    def path(self, fileid):
        with self.lock:
            row = self.db.execute("SELECT path FROM paths WHERE fileid = ?", (int(fileid),)).fetchone()
        return row["path"] if row else ""

    def set_path(self, fileid, path):
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO paths (fileid, path) VALUES (?, ?)", (int(fileid), path))
            self.db.commit()

    def pending(self):
        """The photos and albums with a change still on its way: {"photos": {fileid}, "albums": {id}, "uploads": n}."""
        photos, albums, uploads, turns = set(), set(), 0, {}
        for op in self.ops():
            d = op["data"]
            if "fileid" in d:
                photos.add(int(d["fileid"]))
            if op["kind"].startswith("album_"):
                albums.add(d.get("album") or d.get("id") or "")
            if op["kind"] == "upload":
                uploads += 1
            if op["kind"] == "rotate":
                turns[int(d["fileid"])] = (turns.get(int(d["fileid"]), 0) + int(d["turn"])) % 360
        return {"photos": photos, "albums": albums, "uploads": uploads, "turns": turns}

    def pending_count(self):
        with self.lock:
            return self.db.execute("SELECT COUNT(*) FROM ops").fetchone()[0]

    def ops(self):
        with self.lock:
            rows = self.db.execute("SELECT n, kind, data, tries FROM ops ORDER BY n").fetchall()
        return [{"n": r["n"], "kind": r["kind"], "data": json.loads(r["data"]), "tries": r["tries"]} for r in rows]

    # ---- changes made here -------------------------------------------------------------------------------
    def queue(self, kind, **data):
        """Applied here at once, sent later. Returns the operation's number (to undo it)."""
        with self.lock:
            self._apply(kind, data)
            cur = self.db.execute("INSERT INTO ops (kind, data) VALUES (?, ?)", (kind, json.dumps(data)))
            self.db.commit()
            return cur.lastrowid

    def queue_many(self, kind, items):
        """The same change for many photos, in one write. Returns the operations' numbers."""
        out = []
        with self.lock:
            for data in items:
                self._apply(kind, data)
                out.append(self.db.execute("INSERT INTO ops (kind, data) VALUES (?, ?)",
                                           (kind, json.dumps(data))).lastrowid)
            self.db.commit()
        return out

    def unqueue(self, n):
        """« Annuler »: the operation goes away and its effect is undone here."""
        with self.lock:
            row = self.db.execute("SELECT kind, data FROM ops WHERE n = ?", (int(n),)).fetchone()
            if not row:
                return
            self._revert(row["kind"], json.loads(row["data"]))
            self.db.execute("DELETE FROM ops WHERE n = ?", (int(n),))
            self.db.commit()

    def _count(self, backend, cid, delta):
        self.db.execute("UPDATE clusters SET count = MAX(0, count + ?) WHERE backend = ? AND id = ?",
                        (delta, backend, cid))

    def _apply(self, kind, d):
        db = self.db
        if kind == "fav":
            db.execute("UPDATE photos SET fav = ? WHERE fileid = ?", (1 if d["on"] else 0, int(d["fileid"])))
        elif kind == "delete":
            db.execute("UPDATE photos SET deleted = 1 WHERE fileid = ?", (int(d["fileid"]),))
        elif kind == "album_create":
            db.execute("INSERT OR IGNORE INTO clusters (backend, id, name, count, cover, cover_etag, data) "
                       "VALUES ('albums', ?, ?, 0, 0, '', ?)",
                       (d["album"], d["name"], json.dumps({"user": self.user, "created": int(time.time())})))
            self.set_meta_quiet(f"members:albums:{d['album']}", 1)
        elif kind == "album_rename":
            db.execute("UPDATE clusters SET id = ?, name = ? WHERE backend = 'albums' AND id = ?",
                       (d["new_id"], d["new"], d["album"]))
            db.execute("UPDATE members SET id = ? WHERE backend = 'albums' AND id = ?", (d["new_id"], d["album"]))
        elif kind == "album_delete":
            db.execute("DELETE FROM clusters WHERE backend = 'albums' AND id = ?", (d["album"],))
            db.execute("DELETE FROM members WHERE backend = 'albums' AND id = ?", (d["album"],))
        elif kind == "album_add":
            cur = db.execute("INSERT OR IGNORE INTO members (backend, id, fileid) VALUES ('albums', ?, ?)",
                             (d["album"], int(d["fileid"])))
            if cur.rowcount:
                self._count("albums", d["album"], 1)
                db.execute("UPDATE clusters SET cover = ?, cover_etag = ? WHERE backend = 'albums' AND id = ? "
                           "AND (cover IS NULL OR cover = 0)", (int(d["fileid"]), d.get("etag", ""), d["album"]))
        elif kind == "album_remove":
            cur = db.execute("DELETE FROM members WHERE backend = 'albums' AND id = ? AND fileid = ?",
                             (d["album"], int(d["fileid"])))
            if cur.rowcount:
                self._count("albums", d["album"], -1)
        elif kind == "face_rename":
            db.execute("UPDATE clusters SET name = ? WHERE backend = 'recognize' AND id = ?", (d["new"], d["id"]))
        elif kind == "face_merge":
            for (fileid,) in db.execute("SELECT fileid FROM members WHERE backend = 'recognize' AND id = ?",
                                        (d["id"],)).fetchall():
                db.execute("INSERT OR IGNORE INTO members (backend, id, fileid) VALUES ('recognize', ?, ?)",
                           (d["into"], fileid))
            row = db.execute("SELECT count FROM clusters WHERE backend = 'recognize' AND id = ?", (d["id"],)).fetchone()
            if row:
                self._count("recognize", d["into"], row["count"])
            db.execute("DELETE FROM clusters WHERE backend = 'recognize' AND id = ?", (d["id"],))
            db.execute("DELETE FROM members WHERE backend = 'recognize' AND id = ?", (d["id"],))
        elif kind == "face_remove":
            cur = db.execute("DELETE FROM members WHERE backend = 'recognize' AND id = ? AND fileid = ?",
                             (d["id"], int(d["fileid"])))
            if cur.rowcount:
                self._count("recognize", d["id"], -1)
        elif kind == "cover" and d["backend"] != "recognize":       # a face's cover is a detection: after the pull
            db.execute("UPDATE clusters SET cover = ?, cover_etag = ? WHERE backend = ? AND id = ?",
                       (int(d["fileid"]), d.get("etag", ""), d["backend"], d["id"]))
        elif kind == "date":
            db.execute("UPDATE photos SET dayid = ? WHERE fileid = ?", (int(d["dayid"]), int(d["fileid"])))
        elif kind == "archive":
            db.execute("UPDATE photos SET outside = ? WHERE fileid = ?", (1 if d["on"] else 0, int(d["fileid"])))
            db.execute("DELETE FROM paths WHERE fileid = ?", (int(d["fileid"]),))     # it moves in Files
            if d["on"]:
                db.execute("INSERT OR IGNORE INTO members (backend, id, fileid) VALUES ('archive', 'all', ?)",
                           (int(d["fileid"]),))
            else:
                db.execute("DELETE FROM members WHERE backend = 'archive' AND fileid = ?", (int(d["fileid"]),))
        elif kind == "album_leave":
            db.execute("DELETE FROM clusters WHERE backend = 'albums' AND id = ?", (d["album"],))
            db.execute("DELETE FROM members WHERE backend = 'albums' AND id = ?", (d["album"],))

    def _revert(self, kind, d):
        db = self.db
        if kind == "fav":
            db.execute("UPDATE photos SET fav = ? WHERE fileid = ?", (0 if d["on"] else 1, int(d["fileid"])))
        elif kind == "delete":
            db.execute("UPDATE photos SET deleted = 0 WHERE fileid = ?", (int(d["fileid"]),))
        elif kind == "album_create":
            db.execute("DELETE FROM clusters WHERE backend = 'albums' AND id = ?", (d["album"],))
        elif kind == "album_rename":
            db.execute("UPDATE clusters SET id = ?, name = ? WHERE backend = 'albums' AND id = ?",
                       (d["album"], d["name"], d["new_id"]))
            db.execute("UPDATE members SET id = ? WHERE backend = 'albums' AND id = ?", (d["album"], d["new_id"]))
        elif kind == "album_add":
            cur = db.execute("DELETE FROM members WHERE backend = 'albums' AND id = ? AND fileid = ?",
                             (d["album"], int(d["fileid"])))
            if cur.rowcount:
                self._count("albums", d["album"], -1)
        elif kind == "album_remove":
            cur = db.execute("INSERT OR IGNORE INTO members (backend, id, fileid) VALUES ('albums', ?, ?)",
                             (d["album"], int(d["fileid"])))
            if cur.rowcount:
                self._count("albums", d["album"], 1)
        elif kind == "face_rename":
            db.execute("UPDATE clusters SET name = ? WHERE backend = 'recognize' AND id = ?", (d["name"], d["id"]))
        elif kind == "face_remove":
            cur = db.execute("INSERT OR IGNORE INTO members (backend, id, fileid) VALUES ('recognize', ?, ?)",
                             (d["id"], int(d["fileid"])))
            if cur.rowcount:
                self._count("recognize", d["id"], 1)
        elif kind == "date":
            db.execute("UPDATE photos SET dayid = ? WHERE fileid = ?", (int(d["old_dayid"]), int(d["fileid"])))
        elif kind == "archive":
            self._apply("archive", dict(d, on=not d["on"]))
        # album_delete, album_leave, face_merge, cover, rotate, description, upload: the next pull from the cloud
        # shows what is really there

    def set_meta_quiet(self, key, value):
        self.db.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, str(value)))

    def stage(self, source):
        """A copy of a file to upload, so it goes up even if the original moves meanwhile."""
        STAGING.mkdir(parents=True, exist_ok=True)
        dest = STAGING / f"{time.time_ns()}-{source.name}"
        shutil.copy2(source, dest)
        return dest

    # ---- sync --------------------------------------------------------------------------------------------
    def sync(self, api, report=None, members=(), progress=None):
        """Send the waiting changes, then bring the library up to date. members: the clusters whose photos
        are on screen ([(backend, id)]), read again too."""
        self.push(api, report, progress)
        self.pull(api, members)

    def push(self, api, report=None, progress=None):
        """progress(kind, data): an operation is done with (sent, or refused and undone)."""
        ops = [op for op in self.ops()
               if not (op["kind"] == "delete" and int(op["data"]["fileid"]) in self.hold)]
        i = 0
        while i < len(ops):
            j = i + 1
            if ops[i]["kind"] in PARALLEL_KINDS:
                while j < len(ops) and ops[j]["kind"] == ops[i]["kind"]:
                    j += 1
            if j - i > 1:
                self._push_parallel(api, ops[i:j], report, progress)
            elif self._push_one(api, ops[i], report) and progress:
                progress(ops[i]["kind"], ops[i]["data"])
            i = j

    def _push_parallel(self, api, ops, report, progress):
        """A run of the same change, a few at once, each worker with its own connection. Their order does not
        matter (a photo added to an album, a favourite); what comes before and after the run still waits."""
        local, clones = threading.local(), []

        def one(op):
            if not hasattr(local, "api"):
                local.api = api.clone()
                clones.append(local.api)
            return self._push_one(local.api, op, report)
        pool = ThreadPoolExecutor(max_workers=PARALLEL, thread_name_prefix="photos-push")
        try:
            futures = {pool.submit(one, op): op for op in ops}
            for future in as_completed(futures):
                if future.result() and progress:      # offline or signed out: raised, the rest waits
                    op = futures[future]
                    progress(op["kind"], op["data"])
        finally:
            pool.shutdown(wait=True, cancel_futures=True)
            for c in clones:
                c.close()

    def _push_one(self, api, op, report):
        """True when the operation is done with, False when it waits for the next sync."""
        d = op["data"]
        try:
            self._send(api, op["kind"], d)
        except ApiError as error:
            if error.status in (0, 401):
                raise
            if error.status >= 500 and op["tries"] < 3:
                with self.lock:
                    self.db.execute("UPDATE ops SET tries = tries + 1 WHERE n = ?", (op["n"],))
                    self.db.commit()
                return False
            with self.lock:
                self._revert(op["kind"], d)
                self.db.execute("DELETE FROM ops WHERE n = ?", (op["n"],))
                self.db.commit()
            if report:
                report(op["kind"], d, error.status)
            return True
        with self.lock:
            self.db.execute("DELETE FROM ops WHERE n = ?", (op["n"],))
            self.db.commit()
        if op["kind"] == "upload":
            try:
                (STAGING / d["staged"]).unlink()
            except OSError:
                pass
        return True

    def path_of(self, api, fileid):
        """Where a photo is in Files (favourites, albums and links need it), asked once."""
        path = self.path(fileid)
        if not path:
            info = api.info(fileid)
            path = str(info.get("filename") or "")
            if path:
                self.set_path(fileid, path)
        if not path:
            raise ApiError(404, "not in your files")
        return path

    def _send(self, api, kind, d):
        if kind == "fav":
            api.favorite(self.path_of(api, d["fileid"]), d["on"])
        elif kind == "delete":
            api.delete(d["fileid"])
        elif kind == "album_create":
            api.album_create(d["name"])
        elif kind == "album_rename":
            api.album_rename(d["name"], d["new"])
        elif kind == "album_delete":
            api.album_delete(d["name"])
        elif kind == "album_add":
            api.album_add(d["name"], self.path_of(api, d["fileid"]), d.get("owner"))
        elif kind == "album_remove":
            api.album_remove(d["name"], d["fileid"], d["basename"], d.get("owner"))
        elif kind == "face_rename":
            api.face_rename(d["dav"], d["new"])
        elif kind == "face_merge":
            for detection, _fileid in api.face_photos(d["dav"]):
                api.face_move(d["dav"], detection, d["into_dav"])
        elif kind == "face_remove":
            for detection, fileid in api.face_photos(d["dav"]):
                if fileid == int(d["fileid"]):
                    api.face_unassign(d["dav"], detection)
        elif kind == "cover":
            api.set_cover(d["backend"], cluster_filter(d["backend"], d["id"], self.user)[d["backend"]], d["fileid"])
        elif kind == "date":
            when = d.get("time")
            if not when:                            # several photos moved to a day: each keeps its own time
                taken = int(api.info(d["fileid"]).get("datetaken") or 0)
                when = time.strftime("%H:%M:%S", time.gmtime(taken)) if taken else "12:00:00"
            api.set_exif(d["fileid"], {"AllDates": d["day"].replace("-", ":") + " " + when})
        elif kind == "rotate":
            exif = api.info(d["fileid"]).get("exif") or {}
            api.set_exif(d["fileid"], {"Orientation": turned(int(exif.get("Orientation") or 1), int(d["turn"]))})
        elif kind == "description":
            api.set_exif(d["fileid"], {"Description": d["text"]})
        elif kind == "archive":
            api.archive(d["fileid"], d["on"])
        elif kind == "album_leave":
            api.album_leave(d["name"], d["owner"])
        elif kind == "upload":
            source = STAGING / d["staged"]
            if not source.is_file():
                return                              # nothing left to send
            api.upload(d["folder"], d["name"], source, d.get("mtime", 0))

    def pull(self, api, members=(), recheck=()):
        """The library brought up to date. A day is read again when its count changed, when asked (recheck:
        the day of an edit made here), and in turn, a slice at each pull: an edit made elsewhere keeps the
        count, so the whole library is looked at again within the hour."""
        config = api.config()
        path = config.get("timeline_path") if isinstance(config, dict) else None
        if path is not None and str(path).strip() in UNSET:
            path = self._first_folders(api)
        if path is not None:
            self.set_meta("timeline_path", path or "")
        days = api.days()
        counts = {int(d["dayid"]): int(d.get("count") or 0) for d in days if "dayid" in d}
        with self.lock:
            local = {r["dayid"]: (r["count"], r["loaded"]) for r in self.db.execute("SELECT * FROM days")}
            gone = [d for d in local if d not in counts]
            for dayid in gone:
                self.db.execute("DELETE FROM days WHERE dayid = ?", (dayid,))
                self.db.execute("DELETE FROM photos WHERE dayid = ? AND outside = 0", (dayid,))
            for dayid, count in counts.items():
                self.db.execute("INSERT INTO days (dayid, count) VALUES (?, ?) ON CONFLICT(dayid) DO UPDATE SET "
                                "count = excluded.count", (dayid, count))
            self.db.commit()
            stale = {d for d, c in counts.items() if local.get(d, (None, -1))[1] != c}
            stale.update(int(d) for d in recheck if int(d) in counts)
            stale.update(self._turn(sorted(counts, reverse=True)))
            stale = list(stale)
        # newest first: the top of the timeline fills before the old years
        stale.sort(reverse=True)
        batch, size = [], 0
        for dayid in stale:
            batch.append(dayid)
            size += counts[dayid]
            if size >= BATCH or len(batch) >= 60:
                self._load_days(api, batch, counts)
                batch, size = [], 0
        if batch:
            self._load_days(api, batch, counts)
        for backend in BACKENDS:
            self._load_clusters(api, backend)
        for backend, cid in members:
            if backend in ("map", "archive") or self.cluster(backend, cid) is not None:
                self.load_members(api, backend, cid)
        with self.lock:
            for op in self.ops():
                self._apply(op["kind"], op["data"])
            for fileid in self.hold:
                self.db.execute("UPDATE photos SET deleted = 1 WHERE fileid = ?", (int(fileid),))
            self.db.commit()
        self.set_meta("synced_at", time.time())

    def _turn(self, dayids):
        """The next days to look at again (newest first, around and around), RECHECK at most."""
        if not dayids:
            return []
        cursor = int(self.meta("recheck_from") or 0)
        start = next((i for i, d in enumerate(dayids) if d < cursor), 0) if cursor else 0
        picked = dayids[start:start + RECHECK]
        self.set_meta_quiet("recheck_from", picked[-1] if start + RECHECK < len(dayids) else 0)
        return picked

    @staticmethod
    def _first_folders(api):
        """An account that never chose its library's folders (Memories says « _empty_ », and refuses the
        timeline until one is set): /Photos, where the phone and the imports put them (made if missing), and
        the phone's former folder when it holds something. Set in the cloud, so the web shows the same."""
        api.mkdirs(FIRST_FOLDER)
        folders = [FIRST_FOLDER] + ([PHONE_FOLDER] if api.exists(PHONE_FOLDER) else [])
        value = ";".join(folders)
        api.set_config("timelinePath", value)
        return value

    def _load_days(self, api, dayids, counts):
        rows = api.day(dayids)
        with self.lock:
            self.db.execute(f"DELETE FROM photos WHERE outside = 0 AND dayid IN ({','.join('?' * len(dayids))})", dayids)
            pos = {}
            for row in rows:
                if not isinstance(row, dict) or "fileid" not in row:
                    continue
                values = _photo(row, 0)
                day = values[1]
                pos[day] = pos.get(day, -1) + 1
                values = values[:2] + (pos[day],) + values[3:]
                self.db.execute(f"INSERT OR REPLACE INTO photos ({','.join(PHOTO)}) VALUES ({','.join('?' * len(PHOTO))})",
                                values)
            for dayid in dayids:
                self.db.execute("UPDATE days SET loaded = ? WHERE dayid = ?", (counts[dayid], dayid))
            self.db.commit()

    def _load_clusters(self, api, backend):
        rows = api.clusters(backend)
        with self.lock:
            self.db.execute("DELETE FROM clusters WHERE backend = ?", (backend,))
            for r in rows:
                if not isinstance(r, dict):
                    continue
                cid = str(r.get("cluster_id") if r.get("cluster_id") is not None else r.get("id"))
                name = str(r.get("name") or r.get("title") or "")
                data = {k: r.get(k) for k in ("user", "user_display", "created", "location", "update_id", "shared",
                                              "album_id", "id") if r.get(k) is not None}
                self.db.execute("INSERT OR REPLACE INTO clusters (backend, id, name, count, cover, cover_etag, data) "
                                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                                (backend, cid, name, int(r.get("count") or 0), int(r.get("cover") or 0),
                                 str(r.get("cover_etag") or ""), json.dumps(data)))
            known = {r[0] for r in self.db.execute("SELECT id FROM clusters WHERE backend = ?", (backend,))}
            self.db.execute(f"DELETE FROM members WHERE backend = ? AND id NOT IN ({','.join('?' * len(known)) or 'NULL'})",
                            (backend, *known))
            self.db.commit()                             # albums made offline come back with the waiting operations

    def load_members(self, api, backend, cid):
        """The photos of one album, person, place or tag (asked when it is opened)."""
        filters = cluster_filter(backend, cid, self.user)
        days = [int(d["dayid"]) for d in api.days(filters) if "dayid" in d]
        rows = []
        for i in range(0, len(days), 60):
            rows += [r for r in api.day(days[i:i + 60], filters) if isinstance(r, dict) and "fileid" in r]
        fileids = [int(r["fileid"]) for r in rows]
        with self.lock:
            # photos not in this library (an album someone shares): kept beside it, not in the timeline
            for pos, r in enumerate(rows):
                self.db.execute(f"INSERT OR IGNORE INTO photos ({','.join(PHOTO)}, outside) "
                                f"VALUES ({','.join('?' * len(PHOTO))}, 1)", _photo(r, pos))
            self.db.execute("DELETE FROM members WHERE backend = ? AND id = ?", (backend, cid))
            self.db.executemany("INSERT OR IGNORE INTO members (backend, id, fileid) VALUES (?, ?, ?)",
                                [(backend, cid, f) for f in fileids])
            if backend == "archive":                 # out of the timeline, even if it was in it a moment ago
                self.db.executemany("UPDATE photos SET outside = 1 WHERE fileid = ?", [(f,) for f in fileids])
            self.set_meta_quiet(f"members:{backend}:{cid}", 1)
            for op in self.ops():
                if op["kind"].startswith(("album_", "face_", "archive")):
                    self._apply(op["kind"], op["data"])
            self.db.commit()
        return fileids

    def search(self, api, filters):
        """The photos matching Memories' filters ({"recognize": …, "places": …, "tags": …, "fav": 1}), from
        the cloud."""
        days = [int(d["dayid"]) for d in api.days(filters) if "dayid" in d]
        out = []
        for i in range(0, len(days), 60):
            out += [int(r["fileid"]) for r in api.day(days[i:i + 60], filters) if isinstance(r, dict) and "fileid" in r]
        return out
