"""The cloud's Notes app (API v1), with the app password of Orneos Connect, plus the two things it does not
offer: the notes deleted recently (the Files trash: a note is a Markdown file in the Notes folder), and a
note shared by a public link or with people of the cloud (the sharing API, on the note's file).

Notes are files: a note's id is its file id, its title its file name, its category the folder it is in, and
its ETag changes with its content. A change sent with If-Match is refused (412) when the cloud's copy moved.
"""
import http.client
import json
import ssl
import urllib.parse
import uuid
import xml.etree.ElementTree as ET
from base64 import b64encode

BASE = "/index.php/apps/notes/api/v1"
D, NC, OC = "DAV:", "http://nextcloud.com/ns", "http://owncloud.org/ns"


class ApiError(Exception):
    def __init__(self, status, message="", body=None):
        super().__init__(message or f"HTTP {status}")
        self.status = status          # 0: no network
        self.body = body


class Api:
    """One keep-alive connection (the worker thread makes several calls in a row)."""

    def __init__(self, account, timeout=30):
        self.server, self.user, self.password = account
        parts = urllib.parse.urlsplit(self.server)
        self._scheme, self._host, self._prefix = parts.scheme, parts.netloc, parts.path.rstrip("/")
        self._auth = "Basic " + b64encode(f"{self.user}:{self.password}".encode()).decode()
        self._timeout = timeout
        self._conn = None

    def close(self):
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def request(self, method, path, body=None, headers=None):
        """(status, headers, raw body). Retries once on a dropped keep-alive connection."""
        all_headers = {"Authorization": self._auth, "User-Agent": "Orneos Notes", "OCS-APIRequest": "true",
                       "Accept": "application/json"}
        all_headers.update(headers or {})
        data = body.encode() if isinstance(body, str) else body
        for attempt in (1, 2):
            try:
                if self._conn is None:
                    if self._scheme == "https":
                        self._conn = http.client.HTTPSConnection(self._host, timeout=self._timeout,
                                                                 context=ssl.create_default_context())
                    else:
                        self._conn = http.client.HTTPConnection(self._host, timeout=self._timeout)
                self._conn.request(method, self._prefix + path, body=data, headers=all_headers)
                res = self._conn.getresponse()
                raw = res.read()
                return res.status, {k.lower(): v for k, v in res.getheaders()}, raw
            except (http.client.HTTPException, ConnectionError, TimeoutError, OSError):
                self.close()
                if attempt == 2:
                    raise ApiError(0, "offline")
        raise ApiError(0, "offline")

    def call(self, method, path, body=None, headers=None):
        extra = dict(headers or {})
        payload = None
        if body is not None:
            extra.setdefault("Content-Type", "application/json")
            payload = json.dumps(body)
        status, res_headers, raw = self.request(method, BASE + path, payload, extra)
        try:
            data = json.loads(raw) if raw else None
        except (json.JSONDecodeError, UnicodeDecodeError):
            data = None
        if status >= 400:
            message = data.get("message") if isinstance(data, dict) else ""
            raise ApiError(status, str(message or ""), data)
        return data, res_headers

    # ---- notes ---------------------------------------------------------------------------------------------
    def settings(self):
        data, _ = self.call("GET", "/settings")
        return data if isinstance(data, dict) else {}

    def notes_meta(self):
        """Every note without its content: ids, ETags, titles, folders (to see what changed)."""
        data, _ = self.call("GET", "/notes?exclude=content")
        return [n for n in (data or []) if isinstance(n, dict) and n.get("id") is not None]

    def notes_full(self):
        data, _ = self.call("GET", "/notes")
        return [n for n in (data or []) if isinstance(n, dict) and n.get("id") is not None]

    def note(self, note_id):
        data, _ = self.call("GET", f"/notes/{int(note_id)}")
        return data

    def create(self, note):
        data, _ = self.call("POST", "/notes", {"title": note["title"], "content": note["content"],
                                               "category": note["category"], "favorite": bool(note["favorite"]),
                                               "modified": int(note["modified"] or 0)})
        return data

    def update(self, note_id, note, etag):
        """Refused with 412 (ApiError, the cloud's note in .body) when the note changed in the cloud since etag."""
        headers = {"If-Match": f'"{etag}"'} if etag else {}
        data, _ = self.call("PUT", f"/notes/{int(note_id)}",
                            {"title": note["title"], "content": note["content"], "category": note["category"],
                             "favorite": bool(note["favorite"]), "modified": int(note["modified"] or 0)}, headers)
        return data

    def delete(self, note_id):
        """To the cloud's Files trash (30 days)."""
        try:
            self.call("DELETE", f"/notes/{int(note_id)}")
        except ApiError as error:
            if error.status != 404:
                raise

    # ---- attachments (images shown in a note, kept in the folder .attachments.<id> beside it) ----------------
    def upload(self, note_id, name, data, content_type="application/octet-stream"):
        """The attachment's path relative to the note (".attachments.123/photo.png"), as the note links it."""
        boundary = "orneos" + uuid.uuid4().hex
        safe = name.replace('"', "").replace("\r", "").replace("\n", "") or "image.png"
        body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{safe}\"\r\n"
                f"Content-Type: {content_type}\r\n\r\n").encode() + data + f"\r\n--{boundary}--\r\n".encode()
        status, _, raw = self.request("POST", f"{BASE}/attachment/{int(note_id)}", body,
                                      {"Content-Type": f"multipart/form-data; boundary={boundary}"})
        if status >= 400:
            raise ApiError(status, "upload")
        try:
            return (json.loads(raw) or {}).get("filename") or ""
        except (json.JSONDecodeError, UnicodeDecodeError):
            return ""

    def attachment(self, note_id, path):
        status, _, raw = self.request("GET", f"{BASE}/attachment/{int(note_id)}?path={urllib.parse.quote(path)}",
                                      None, {"Accept": "*/*"})
        if status >= 400:
            raise ApiError(status, "attachment")
        return raw

    # ---- recently deleted (the Files trash, filtered on the Notes folder) -----------------------------------
    def _dav(self, method, path, body=None, headers=None):
        all_headers = {"Content-Type": "application/xml; charset=utf-8"} if body else {}
        all_headers.update(headers or {})
        return self.request(method, path, body, all_headers)

    def trash(self, notes_path):
        """[{name, title, category, deleted, href}] of the notes deleted from the Notes folder."""
        folder = "/" + (notes_path or "Notes").strip("/") + "/"
        body = (f'<d:propfind xmlns:d="{D}" xmlns:nc="{NC}" xmlns:oc="{OC}"><d:prop><nc:trashbin-filename/>'
                '<nc:trashbin-original-location/><nc:trashbin-deletion-time/><d:getcontentlength/>'
                '<d:resourcetype/></d:prop></d:propfind>')
        status, _, raw = self._dav("PROPFIND", f"/remote.php/dav/trashbin/{urllib.parse.quote(self.user)}/trash/",
                                   body, {"Depth": "1"})
        if status != 207:
            raise ApiError(status, "trash")
        out = []
        for resp in ET.fromstring(raw).findall(f"{{{D}}}response"):
            href = resp.findtext(f"{{{D}}}href") or ""
            props = resp.find(f".//{{{D}}}prop")
            if props is None or props.find(f"{{{D}}}resourcetype/{{{D}}}collection") is not None:
                continue
            original = "/" + (props.findtext(f"{{{NC}}}trashbin-original-location") or "").lstrip("/")
            name = props.findtext(f"{{{NC}}}trashbin-filename") or ""
            if not original.startswith(folder) or not name.lower().endswith((".md", ".txt", ".markdown")):
                continue
            inside = original[len(folder):]
            if "/.attachments." in "/" + inside:
                continue
            category = inside.rsplit("/", 1)[0] if "/" in inside else ""
            out.append({"href": href, "name": name, "title": name.rsplit(".", 1)[0], "category": category,
                        "original": original.strip("/"),
                        "deleted": int(props.findtext(f"{{{NC}}}trashbin-deletion-time") or 0)})
        return sorted(out, key=lambda x: -x["deleted"])

    # ---- versions (the Files versions of the note's file: the cloud keeps them 90 days) ------------------------
    def versions(self, file_id):
        """[{href, modified, size}] of the earlier versions of a note (its id is its file's), newest first. Nextcloud
        (26 and later) lists the current version too, with the file's mtime: it is no file of the versions folder (a GET
        of it is a 404, the cloud's error popup), and it is the note itself: left out, as « Current version » of Files."""
        body = (f'<d:propfind xmlns:d="{D}"><d:prop><d:getlastmodified/><d:getcontentlength/></d:prop></d:propfind>')
        status, _, raw = self._dav("PROPFIND", f"/remote.php/dav/versions/{urllib.parse.quote(self.user)}/versions/{int(file_id)}",
                                   body, {"Depth": "1"})
        if status == 404:
            return []
        if status != 207:
            raise ApiError(status, "versions")
        out = []
        for resp in ET.fromstring(raw).findall(f"{{{D}}}response"):
            href = resp.findtext(f"{{{D}}}href") or ""
            name = href.rstrip("/").rsplit("/", 1)[-1]
            if not name.isdigit() or href.rstrip("/").endswith(f"/versions/{int(file_id)}"):
                continue                       # the collection itself
            props = resp.find(f".//{{{D}}}prop")
            size = props.findtext(f"{{{D}}}getcontentlength") if props is not None else ""
            out.append({"href": href, "modified": int(name), "size": int(size or 0)})
        current = self._mtime(file_id)
        out = [v for v in out if v["modified"] != current] if current else out
        return sorted(out, key=lambda v: -v["modified"])

    def _mtime(self, file_id):
        """The modification time of the note's file (the current version's timestamp), 0 if unknown."""
        try:
            data, _ = self.call("GET", f"/notes/{int(file_id)}?exclude=content")
        except ApiError:
            return 0
        return int(data.get("modified") or 0) if isinstance(data, dict) else 0

    def version_content(self, href):
        status, _, raw = self._dav("GET", urllib.parse.urlsplit(href).path)
        if status >= 400:
            raise ApiError(status, "version")
        return raw.decode("utf-8", "replace")

    def trash_content(self, href):
        status, _, raw = self._dav("GET", urllib.parse.urlsplit(href).path)
        if status >= 400:
            raise ApiError(status, "trash item")
        return raw.decode("utf-8", "replace")

    def restore(self, href):
        path = urllib.parse.urlsplit(href).path
        name = path.rstrip("/").rsplit("/", 1)[-1]
        target = f"{self.server}/remote.php/dav/trashbin/{urllib.parse.quote(self.user)}/restore/{name}"
        status, _, _ = self._dav("MOVE", path, None, {"Destination": target})
        if status not in (200, 201, 204):
            raise ApiError(status, "restore")

    def purge(self, href):
        status, _, _ = self._dav("DELETE", urllib.parse.urlsplit(href).path)
        if status not in (200, 204, 404):
            raise ApiError(status, "purge")

    # ---- a public link (read only) to one note --------------------------------------------------------------
    def share_link(self, internal_path):
        """The URL of a read-only public link to the note's file (an existing one is reused)."""
        query = urllib.parse.urlencode({"path": internal_path, "reshares": "false"})
        status, _, raw = self.request("GET", f"/ocs/v2.php/apps/files_sharing/api/v1/shares?{query}&format=json")
        if status == 200:
            for share in ((json.loads(raw or b"{}").get("ocs") or {}).get("data") or []):
                if int(share.get("share_type", -1)) == 3 and share.get("url"):
                    return share["url"]
        form = urllib.parse.urlencode({"path": internal_path, "shareType": 3, "permissions": 1})
        status, _, raw = self.request("POST", "/ocs/v2.php/apps/files_sharing/api/v1/shares?format=json", form,
                                      {"Content-Type": "application/x-www-form-urlencoded"})
        if status >= 400:
            raise ApiError(status, "share")
        return ((json.loads(raw or b"{}").get("ocs") or {}).get("data") or {}).get("url") or ""

    # ---- sharing with people of the cloud (the sharing API, on the note's file, as in the cloud) ---------------
    SHARES = "/ocs/v2.php/apps/files_sharing/api/v1/shares"
    PEOPLE = (0, 1, 4, 7)            # an account, a group, an e-mail address, a team

    def _ocs(self, method, path, form=None):
        body = urllib.parse.urlencode(form) if form is not None else None
        status, _, raw = self.request(method, path + ("&" if "?" in path else "?") + "format=json", body,
                                      {"Content-Type": "application/x-www-form-urlencoded"} if body else None)
        if status >= 400:
            raise ApiError(status, "share")
        try:
            return (json.loads(raw or b"{}").get("ocs") or {}).get("data")
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None

    def sharees(self, search):
        """[{type, with, name, sub}]: the accounts, groups, teams and e-mail addresses that match (exact first)."""
        query = urllib.parse.urlencode({"search": search, "itemType": "file", "perPage": 8, "lookup": "false"})
        data = self._ocs("GET", f"/ocs/v2.php/apps/files_sharing/api/v1/sharees?{query}") or {}
        out, seen = [], set()
        for group in (data.get("exact") or {}, data):
            for kind in ("users", "groups", "circles", "emails"):
                for item in group.get(kind) or []:
                    value = item.get("value") or {}
                    entry = (int(value.get("shareType", -1)), str(value.get("shareWith") or ""))
                    if entry[0] in self.PEOPLE and entry[1] and entry not in seen:
                        seen.add(entry)
                        out.append({"type": entry[0], "with": entry[1], "name": str(item.get("label") or entry[1]),
                                    "sub": str(item.get("shareWithDisplayNameUnique") or item.get("subline") or "")})
        return out

    def shares(self, internal_path):
        """[{id, type, with, name, editable}]: the people the note is shared with (not its public link)."""
        query = urllib.parse.urlencode({"path": internal_path, "reshares": "false"})
        return [{"id": str(s.get("id")), "type": int(s.get("share_type")), "with": str(s.get("share_with") or ""),
                 "name": str(s.get("share_with_displayname") or s.get("share_with") or ""),
                 "editable": bool(int(s.get("permissions") or 0) & 2)}
                for s in self._ocs("GET", f"{self.SHARES}?{query}") or []
                if isinstance(s, dict) and int(s.get("share_type", -1)) in self.PEOPLE]

    def share(self, internal_path, share_type, share_with, editable):
        return self._ocs("POST", self.SHARES, {"path": internal_path, "shareType": int(share_type),
                                               "shareWith": share_with, "permissions": 3 if editable else 1})

    def update_share(self, share_id, editable):
        return self._ocs("PUT", f"{self.SHARES}/{urllib.parse.quote(str(share_id))}", {"permissions": 3 if editable else 1})

    def unshare(self, share_id):
        return self._ocs("DELETE", f"{self.SHARES}/{urllib.parse.quote(str(share_id))}")

    def sharing(self):
        """Every share of the account in one go: ({file id: [{id, type, with, name, editable}]} of what it shares
        (a public link is type 3), {file id: {id, owner, editable}} of what is shared with it)."""
        out, received = {}, {}
        for s in self._ocs("GET", f"{self.SHARES}?reshares=false") or []:
            if isinstance(s, dict) and int(s.get("share_type", -1)) in self.PEOPLE + (3,) and s.get("file_source"):
                out.setdefault(int(s["file_source"]), []).append(
                    {"id": str(s.get("id")), "type": int(s["share_type"]), "with": str(s.get("share_with") or ""),
                     "name": str(s.get("share_with_displayname") or s.get("share_with") or ""),
                     "editable": bool(int(s.get("permissions") or 0) & 2)})
        for s in self._ocs("GET", f"{self.SHARES}?shared_with_me=true") or []:
            if isinstance(s, dict) and s.get("file_source"):
                received[int(s["file_source"])] = {"id": str(s.get("id")), "editable": bool(int(s.get("permissions") or 0) & 2),
                                                   "owner": str(s.get("displayname_owner") or s.get("uid_owner") or "")}
        return out, received
