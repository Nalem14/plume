"""The cloud's photos, through Memories (the timeline the cloud's own Photos page shows), with the app password
of Orneos Connect.

Memories answers in JSON: the days of the timeline (a day id is the number of days since 1970, in the photo's
own local time), the photos of some days, the people (Recognize), places, tags and albums as « clusters », the
details of a photo, many thumbnails in one answer, and the edits (applied on the server, the previous file kept
in the versions of Files). What Memories does not do, the cloud's DAV does: favourites (Files), the albums
themselves (the Photos app's DAV), naming and merging people (Recognize's DAV), the trash and uploads.
Recognize's DAV refuses (403) any request without X-Recognize-Api-Key, a key Memories hands out (24 h).
"""
import http.client
import json
import ssl
import time
import urllib.parse
import xml.etree.ElementTree as ET
from base64 import b64encode

MEM = "/index.php/apps/memories/api"
D, NC, OC = "DAV:", "http://nextcloud.org/ns", "http://owncloud.org/ns"
NS = {"d": D, "nc": NC, "oc": OC}


class ApiError(Exception):
    def __init__(self, status, message="", body=None):
        super().__init__(message or f"HTTP {status}")
        self.status = status          # 0: no network
        self.body = body


def q(text):
    return urllib.parse.quote(str(text), safe="")


def qpath(path):
    return urllib.parse.quote(str(path).lstrip("/"), safe="/")


def parse_multipreview(raw):
    """Memories' batched thumbnails: for each, one byte (the length of a JSON header), the header {reqid, len,
    type}, then the image. {reqid: bytes}; a truncated answer keeps what came whole."""
    out, i = {}, 0
    while i < len(raw):
        size = raw[i]
        i += 1
        try:
            head = json.loads(raw[i:i + size].decode())
        except (UnicodeDecodeError, json.JSONDecodeError):
            break
        i += size
        length = int(head.get("len") or 0)
        if length <= 0 or i + length > len(raw):
            break
        out[str(head.get("reqid"))] = raw[i:i + length]
        i += length
    return out


class Api:
    """One keep-alive connection (a worker thread makes several calls in a row)."""

    def __init__(self, account, timeout=40):
        self.server, self.user, self.password = account
        parts = urllib.parse.urlsplit(self.server)
        self._scheme, self._host, self._prefix = parts.scheme, parts.netloc, parts.path.rstrip("/")
        self._auth = "Basic " + b64encode(f"{self.user}:{self.password}".encode()).decode()
        self._timeout = timeout
        self._conn = None
        self.files_root = f"/remote.php/dav/files/{q(self.user)}"

    def clone(self):
        """The same account on a connection of its own (one per thread)."""
        return Api((self.server, self.user, self.password), self._timeout)

    def close(self):
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _connect(self):
        if self._conn is None:
            if self._scheme == "https":
                self._conn = http.client.HTTPSConnection(self._host, timeout=self._timeout,
                                                         context=ssl.create_default_context())
            else:
                self._conn = http.client.HTTPConnection(self._host, timeout=self._timeout)

    def request(self, method, path, body=None, headers=None):
        """(status, headers, raw body). Retries once on a dropped keep-alive connection."""
        all_headers = {"Authorization": self._auth, "User-Agent": "Orneos Photos", "OCS-APIRequest": "true",
                       "Accept": "application/json"}
        all_headers.update(headers or {})
        data = body.encode() if isinstance(body, str) else body
        for attempt in (1, 2):
            if hasattr(data, "seek"):
                data.seek(0)                            # a file sent again from its start
            try:
                self._connect()
                self._conn.request(method, self._prefix + path, body=data, headers=all_headers)
                res = self._conn.getresponse()
                raw = res.read()
                return res.status, {k.lower(): v for k, v in res.getheaders()}, raw
            except (http.client.HTTPException, ConnectionError, TimeoutError, OSError):
                self.close()
                if attempt == 2:
                    raise ApiError(0, "offline")
        raise ApiError(0, "offline")

    def _json(self, method, path, body=None, ok=(200,)):
        headers = {}
        payload = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            payload = json.dumps(body)
        status, _, raw = self.request(method, path, payload, headers)
        try:
            data = json.loads(raw) if raw else None
        except (json.JSONDecodeError, UnicodeDecodeError):
            data = None
        if status not in ok:
            message = data.get("message") if isinstance(data, dict) else ""
            raise ApiError(status, str(message or ""), data)
        return data

    def _dav(self, method, path, body=None, headers=None, ok=(200, 201, 204, 207)):
        extra = dict(headers or {})
        if body is not None:
            extra.setdefault("Content-Type", "application/xml; charset=utf-8")
        status, res_headers, raw = self.request(method, path, body, extra)
        if status not in ok:
            raise ApiError(status, f"{method} {status}")
        return status, res_headers, raw

    @staticmethod
    def _query(params):
        return ("?" + urllib.parse.urlencode(params)) if params else ""

    # ---- the timeline ------------------------------------------------------------------------------------
    def config(self):
        """The person's settings in Memories: timeline_path (the folders of the library, « ; » between them)."""
        return self._json("GET", MEM + "/config") or {}

    def set_config(self, key, value):
        self._json("PUT", MEM + "/config/" + q(key), {"value": str(value)})

    def exists(self, path):
        status, _, _ = self.request("PROPFIND", f"{self.files_root}/{qpath(path)}", headers={"Depth": "0"})
        if status == 0:
            raise ApiError(0, "offline")
        return status == 207

    def days(self, filters=None):
        """[{dayid, count}] newest first, for the whole library or one cluster ({"albums": "alex/Été"} …)."""
        params = {"nopreload": 1}
        params.update(filters or {})
        return self._json("GET", MEM + "/days" + self._query(params)) or []

    def day(self, dayids, filters=None):
        """The photos of these days: [{fileid, etag, dayid, w, h, basename, isvideo, video_duration, liveid,
        isfavorite, size, …}]."""
        ids = ",".join(str(int(d)) for d in dayids)
        return self._json("GET", MEM + "/days/" + ids + self._query(filters or {})) or []

    def clusters(self, backend):
        """people (recognize), places, tags or albums: [{cluster_id, name, count, cover, cover_etag, …}]."""
        try:
            return self._json("GET", MEM + "/clusters/" + q(backend)) or []
        except ApiError as error:
            if error.status in (400, 404, 412, 500):      # that app is not enabled on the cloud
                return []
            raise

    def map_clusters(self, bounds, zoom):
        """The photos of that part of the map, grouped on a grid of 180 / 2^zoom degrees:
        [{id, center: [lat, lon], count, preview: {fileid, etag, …}}]. bounds: « minLat,maxLat,minLon,maxLon »."""
        return self._json("GET", MEM + "/map/clusters" + self._query({"bounds": bounds, "zoom": int(zoom)})) or []

    def map_start(self):
        """Where the newest photo with a position was taken: {lat, lon}, or None."""
        return (self._json("GET", MEM + "/map/init") or {}).get("pos")

    def info(self, fileid):
        return self._json("GET", MEM + f"/image/info/{int(fileid)}"
                          + self._query({"tags": 1, "clusters": "recognize,albums"})) or {}  # places: refused by Memories, the place is in « address »

    def trash(self):
        try:
            return self._json("GET", MEM + "/trash/list") or []
        except ApiError as error:
            if error.status in (400, 404, 412):
                return []
            raise

    # ---- images ------------------------------------------------------------------------------------------
    def multipreview(self, wanted):
        """wanted: [(reqid, fileid, size)] → {reqid: image bytes}, the photo's whole frame (not cropped)."""
        files = [{"reqid": str(r), "fileid": int(f), "x": int(s), "y": int(s), "a": "1"} for r, f, s in wanted]
        status, _, raw = self.request("POST", MEM + "/image/multipreview", json.dumps({"files": files}),
                                      {"Content-Type": "application/json", "Accept": "*/*"})
        if status != 200:
            raise ApiError(status)
        return parse_multipreview(raw)

    def preview(self, fileid, size):
        status, _, raw = self.request("GET", MEM + f"/image/preview/{int(fileid)}"
                                      + self._query({"x": size, "y": size, "a": 1}), headers={"Accept": "*/*"})
        if status != 200:
            raise ApiError(status)
        return raw

    def cluster_preview(self, backend, name, cover=0):
        params = {"name": name}
        if cover:
            params["cover"] = cover
        status, _, raw = self.request("GET", MEM + f"/clusters/{q(backend)}/preview" + self._query(params),
                                      headers={"Accept": "*/*"})
        if status != 200:
            raise ApiError(status)
        return raw

    def download(self, fileid, dest):
        """The file itself (videos, downloads) written to dest as it comes, never whole in memory; a broken
        transfer leaves nothing behind."""
        part = dest.with_name(dest.name + ".part")
        for attempt in (1, 2):
            try:
                self._connect()
                self._conn.request("GET", self._prefix + MEM + f"/stream/{int(fileid)}",
                                   headers={"Authorization": self._auth, "User-Agent": "Orneos Photos", "Accept": "*/*"})
                res = self._conn.getresponse()
                if res.status != 200:
                    res.read()
                    raise ApiError(res.status)
                with open(part, "wb") as out:
                    while chunk := res.read(1 << 20):
                        out.write(chunk)
                part.replace(dest)
                return dest
            except (http.client.HTTPException, ConnectionError, TimeoutError, OSError):
                self.close()
                part.unlink(missing_ok=True)
                if attempt == 2:
                    raise ApiError(0, "offline")
        raise ApiError(0, "offline")

    # ---- changes -----------------------------------------------------------------------------------------
    def edit(self, fileid, name, extension, state):
        """The edit applied by the server (crop, rotation, light, colour). width/height 0: no resize. Saved
        over the file (Files keeps the previous one in its versions) or, under another name, as a copy."""
        body = {"name": name, "width": 0, "height": 0, "quality": 0.92, "extension": extension, "state": state}
        return self._json("PUT", MEM + f"/image/edit/{int(fileid)}", body) or {}

    def delete(self, fileid):
        """To the cloud's trash (Memories deletes through Files). A file already gone counts as deleted."""
        status, _, _ = self.request("DELETE", MEM + f"/image/delete/{int(fileid)}")
        if status not in (200, 404):
            raise ApiError(status)

    def set_exif(self, fileid, raw):
        """Some of the photo's metadata written into the file by Memories (AllDates « YYYY:MM:DD HH:MM:SS »,
        Description, Title, Orientation 1-8); it reads the photo again after."""
        return self._json("PATCH", MEM + f"/image/set-exif/{int(fileid)}", {"raw": raw}) or {}

    def archive(self, fileid, on):
        """Into the « .archive » folder of the library (out of the timeline, kept), or back where it was."""
        self._json("PATCH", MEM + f"/archive/{int(fileid)}", {"archive": bool(on)})

    def set_cover(self, backend, name, fileid):
        """This photo as the picture of an album (« owner/name ») or a person (« user/id »)."""
        self._json("POST", MEM + f"/clusters/{q(backend)}/set-cover", {"name": name, "fileid": int(fileid)})

    def favorite(self, path, on):
        body = (f'<?xml version="1.0"?><d:propertyupdate xmlns:d="{D}" xmlns:oc="{OC}"><d:set><d:prop>'
                f"<oc:favorite>{1 if on else 0}</oc:favorite></d:prop></d:set></d:propertyupdate>")
        self._dav("PROPPATCH", f"{self.files_root}/{qpath(path)}", body)

    def restore(self, trash_path):
        name = trash_path.rstrip("/").rsplit("/", 1)[-1]
        dest = f"{self.server}{self._dav_root()}/trashbin/{q(self.user)}/restore/{q(name)}"
        self._dav("MOVE", self._dav_root() + qpath_abs(trash_path), headers={"Destination": dest})

    def purge(self, trash_path):
        self._dav("DELETE", self._dav_root() + qpath_abs(trash_path), ok=(200, 204, 404))

    def _dav_root(self):
        return "/remote.php/dav"

    def mkdirs(self, folder):
        path = ""
        for part in [p for p in str(folder).split("/") if p]:
            path += "/" + part
            status, _, _ = self.request("MKCOL", f"{self.files_root}/{qpath(path)}")
            if status not in (201, 405):        # 405: already there
                raise ApiError(status)

    def upload(self, folder, name, source, mtime=0):
        """A file of the computer (its path) into one of the library's folders, read as it goes up; a name
        already taken gets « (2) »."""
        self.mkdirs(folder)
        stem, dot, ext = name.rpartition(".")
        if not dot:
            stem, ext = name, ""
        candidate, n = name, 1
        while True:
            status, _, _ = self.request("PROPFIND", f"{self.files_root}/{qpath(folder + '/' + candidate)}",
                                        headers={"Depth": "0"})
            if status == 404:
                break
            n += 1
            candidate = f"{stem} ({n}).{ext}" if ext else f"{stem} ({n})"
        headers = {"Content-Type": "application/octet-stream", "Content-Length": str(source.stat().st_size)}
        if mtime:
            headers["X-OC-Mtime"] = str(int(mtime))
        with open(source, "rb") as data:
            self._dav("PUT", f"{self.files_root}/{qpath(folder + '/' + candidate)}", data, headers)
        return f"{folder.rstrip('/')}/{candidate}"

    # ---- albums (the Photos app's DAV) -----------------------------------------------------------------------
    def _album(self, name, owner=None):
        if owner and owner != self.user:
            return f"/remote.php/dav/photos/{q(self.user)}/sharedalbums/{q(name + ' (' + owner + ')')}"
        return f"/remote.php/dav/photos/{q(self.user)}/albums/{q(name)}"

    def album_create(self, name):
        status, _, _ = self.request("MKCOL", self._album(name))
        if status not in (201, 405):
            raise ApiError(status)

    def album_rename(self, name, new):
        self._dav("MOVE", self._album(name), headers={"Destination": self.server + self._album(new)})

    def album_delete(self, name):
        self._dav("DELETE", self._album(name), ok=(200, 204, 404))

    def album_leave(self, name, owner):
        """An album someone shares with me, left: I am no longer among its collaborators."""
        self._dav("DELETE", self._album(name, owner), ok=(200, 204, 404))

    def album_add(self, name, path, owner=None):
        """A photo of the library (its path in Files) into the album; already in it counts as done."""
        basename = path.rstrip("/").rsplit("/", 1)[-1]
        dest = self.server + self._album(name, owner) + "/" + q(basename)
        status, _, _ = self.request("COPY", f"{self.files_root}/{qpath(path)}", headers={"Destination": dest})
        if status not in (200, 201, 204, 409):
            raise ApiError(status)

    def album_remove(self, name, fileid, basename, owner=None):
        self._dav("DELETE", self._album(name, owner) + "/" + q(f"{int(fileid)}-{basename}"), ok=(200, 204, 404))

    def album_collaborators(self, name):
        body = (f'<?xml version="1.0"?><d:propfind xmlns:d="{D}" xmlns:nc="{NC}"><d:prop>'
                "<nc:collaborators/></d:prop></d:propfind>")
        _, _, raw = self._dav("PROPFIND", self._album(name), body, {"Depth": "0"})
        try:
            node = ET.fromstring(raw).find(".//nc:collaborators", NS)
        except ET.ParseError:
            return []
        people = []
        for c in (node if node is not None else []):
            entry = {child.tag.split("}")[-1]: (child.text or "") for child in c}
            if entry:
                people.append({"id": entry.get("id", ""), "label": entry.get("label", entry.get("id", "")),
                               "type": int(entry.get("type") or 0)})
        return people

    def album_set_collaborators(self, name, people):
        value = json.dumps([{"id": p["id"], "label": p.get("label", p["id"]), "type": int(p["type"])} for p in people])
        body = (f'<?xml version="1.0"?><d:propertyupdate xmlns:d="{D}" xmlns:nc="{NC}"><d:set><d:prop>'
                f"<nc:collaborators>{_xml(value)}</nc:collaborators></d:prop></d:set></d:propertyupdate>")
        self._dav("PROPPATCH", self._album(name), body)

    # ---- people (Recognize's DAV) ------------------------------------------------------------------------
    _recognize_keys = {}            # server → (time, key), shared by the workers' connections

    def _recognize_key(self, fresh=False):
        when, key = Api._recognize_keys.get(self.server, (0.0, ""))
        if fresh or not key or time.time() - when > 6 * 3600:
            key = str((self._json("GET", MEM + "/recognize/api-key") or {}).get("apiKey") or "")
            Api._recognize_keys[self.server] = (time.time(), key)
        return key

    def _faces_dav(self, method, path, body=None, headers=None, ok=(200, 201, 204, 207)):
        """A request to Recognize's DAV with its key; once more with a new key when refused (expired)."""
        for fresh in (False, True):
            extra = dict(headers or {}, **{"X-Recognize-Api-Key": self._recognize_key(fresh)})
            try:
                return self._dav(method, path, body, extra, ok)
            except ApiError as e:
                if e.status != 403 or fresh:
                    raise

    def _faces(self):
        return f"/remote.php/dav/recognize/{q(self.user)}/faces"

    def face_rename(self, name, new):
        self._faces_dav("MOVE", f"{self._faces()}/{q(name)}",
                        headers={"Destination": f"{self.server}{self._faces()}/{q(new)}"})

    def face_photos(self, name):
        """[(detection name, fileid)] of a person."""
        body = (f'<?xml version="1.0"?><d:propfind xmlns:d="{D}" xmlns:oc="{OC}"><d:prop><oc:fileid/></d:prop>'
                "</d:propfind>")
        _, _, raw = self._faces_dav("PROPFIND", f"{self._faces()}/{q(name)}", body, {"Depth": "1"})
        out = []
        try:
            root = ET.fromstring(raw)
        except ET.ParseError:
            return out
        for resp in root.findall("d:response", NS):
            href = urllib.parse.unquote(resp.findtext("d:href", "", NS)).rstrip("/")
            fileid = resp.findtext(".//oc:fileid", "", NS)
            leaf = href.rsplit("/", 1)[-1]
            if fileid and leaf != name:
                out.append((leaf, int(fileid)))
        return out

    def face_move(self, name, detection, into):
        self._faces_dav("MOVE", f"{self._faces()}/{q(name)}/{q(detection)}",
                        headers={"Destination": f"{self.server}{self._faces()}/{q(into)}/{q(detection)}"})

    def face_unassign(self, name, detection):
        self._faces_dav("DELETE", f"{self._faces()}/{q(name)}/{q(detection)}", ok=(200, 204, 404))

    # ---- sharing -----------------------------------------------------------------------------------------
    def share_link(self, path):
        status, _, raw = self.request(
            "POST", "/ocs/v2.php/apps/files_sharing/api/v1/shares?format=json",
            urllib.parse.urlencode({"path": "/" + path.lstrip("/"), "shareType": "3"}),
            {"Content-Type": "application/x-www-form-urlencoded"})
        try:
            data = (json.loads(raw).get("ocs") or {}).get("data") or {}
        except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
            data = {}
        if status not in (200, 100) or not data.get("url"):
            raise ApiError(status)
        return str(data["url"])

    def people_search(self, term):
        """Accounts and groups of the cloud, to share an album with."""
        params = {"search": term, "itemType": " ", "itemId": " ", "shareTypes[]": "0", "limit": 12, "format": "json"}
        status, _, raw = self.request("GET", "/ocs/v2.php/core/autocomplete/get?" + urllib.parse.urlencode(params)
                                      + "&shareTypes[]=1")
        try:
            rows = (json.loads(raw).get("ocs") or {}).get("data") or []
        except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
            rows = []
        if status not in (200, 100):
            raise ApiError(status)
        out = []
        for r in rows:
            source = str(r.get("source") or "")
            kind = 1 if source == "groups" else 0
            out.append({"id": str(r.get("id") or ""), "label": str(r.get("label") or r.get("id") or ""), "type": kind})
        return [p for p in out if p["id"] and not (p["type"] == 0 and p["id"] == self.user)]

    def versions(self, fileid):
        """The file's earlier versions in Files, oldest first: [href]."""
        body = (f'<?xml version="1.0"?><d:propfind xmlns:d="{D}"><d:prop><d:getlastmodified/></d:prop></d:propfind>')
        _, _, raw = self._dav("PROPFIND", f"/remote.php/dav/versions/{q(self.user)}/versions/{int(fileid)}",
                              body, {"Depth": "1"})
        try:
            root = ET.fromstring(raw)
        except ET.ParseError:
            return []
        hrefs = [resp.findtext("d:href", "", NS) for resp in root.findall("d:response", NS)]
        mine = f"/versions/{int(fileid)}"
        versions = [h for h in hrefs if h.rstrip("/").rsplit("/", 1)[-1].isdigit() and not h.rstrip("/").endswith(mine)]
        return sorted(versions, key=lambda h: int(h.rstrip("/").rsplit("/", 1)[-1]))

    def restore_version(self, href):
        dest = f"{self.server}/remote.php/dav/versions/{q(self.user)}/restore/target"
        path = urllib.parse.urlsplit(href).path
        if self._prefix and path.startswith(self._prefix):
            path = path[len(self._prefix):]
        self._dav("MOVE", path, headers={"Destination": dest})


def qpath_abs(path):
    return "/" + qpath(path)


def _xml(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
