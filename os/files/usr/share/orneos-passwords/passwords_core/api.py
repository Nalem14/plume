"""The cloud's Passwords app (API 1.0), with the app password of Orneos Connect.

Server-side encryption only, like the browser extension: an account that protects its passwords with a
master password (client-side encryption) is told so and sent to the cloud.
"""
import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request

import cloud

BASE = "/index.php/apps/passwords/api/1.0"
ROOT_FOLDER = "00000000-0000-0000-0000-000000000000"
DETAILS = "model+tag-ids"


class ApiError(Exception):
    def __init__(self, status, message=""):
        super().__init__(message or f"HTTP {status}")
        self.status = status          # 0: no network


def sha1(text):
    return hashlib.sha1((text or "").encode()).hexdigest()


class Api:
    def __init__(self, account):
        self.server, self.user, self.password = account

    def call(self, method, path, body=None):
        status, data = cloud.rest(self.server, self.user, self.password, BASE + path, method=method, body=body)
        if status == 0:
            raise ApiError(0, "offline")
        if status >= 400:
            message = data.get("message") if isinstance(data, dict) else ""
            raise ApiError(status, str(message or ""))
        return data

    # ---- reading -----------------------------------------------------------------------------------------
    def locked(self):
        """True when the account uses client-side encryption (a master password this app does not handle)."""
        data = self.call("GET", "/session/request")
        return bool(isinstance(data, dict) and (data.get("challenge") or data.get("token")))

    def passwords(self):
        return self.call("POST", "/password/list", {"details": DETAILS}) or []

    def trashed(self):
        return self.call("POST", "/password/find", {"criteria": {"trashed": True}, "details": DETAILS}) or []

    def show(self, entry_id, details="model+tag-ids"):
        return self.call("POST", "/password/show", {"id": entry_id, "details": details})

    def history(self, entry_id):
        data = self.show(entry_id, "model+revisions")
        return (data or {}).get("revisions") or []

    def folders(self):
        return self.call("POST", "/folder/list", {"details": "model"}) or []

    def tags(self):
        return self.call("POST", "/tag/list", {"details": "model"}) or []

    def shares(self):
        return self.call("POST", "/share/list", {"details": "model"}) or []

    # ---- writing -----------------------------------------------------------------------------------------
    @staticmethod
    def payload(entry):
        """Every field: the API resets the ones left out."""
        return {
            "password": entry.get("password") or "",
            "hash": sha1(entry.get("password")),
            "username": entry.get("username") or "",
            "label": entry.get("label") or "",
            "url": entry.get("url") or "",
            "notes": entry.get("notes") or "",
            "customFields": json.dumps(entry.get("customFields") or [], ensure_ascii=False),
            "folder": entry.get("folder") or ROOT_FOLDER,
            "favorite": bool(entry.get("favorite")),
            "hidden": False,
            "cseType": "none",
            "cseKey": "",
            "tags": list(entry.get("tags") or []),
        }

    def create(self, entry):
        return self.call("POST", "/password/create", self.payload(entry))

    def update(self, entry, revision):
        body = self.payload(entry)
        body.update({"id": entry["id"], "revision": revision})
        return self.call("PATCH", "/password/update", body)

    def delete(self, entry_id):
        """To the trash the first time, for good the second."""
        return self.call("DELETE", "/password/delete", {"id": entry_id})

    def restore(self, entry_id):
        return self.call("PATCH", "/password/restore", {"id": entry_id})

    def restore_revision(self, entry_id, revision):
        return self.call("PATCH", "/password/restore", {"id": entry_id, "revision": revision})

    def create_folder(self, label, parent=ROOT_FOLDER):
        return self.call("POST", "/folder/create", {"label": label, "parent": parent})

    def rename_folder(self, folder, label):
        return self.call("PATCH", "/folder/update", {"id": folder["id"], "label": label,
                                                     "parent": folder.get("parent") or ROOT_FOLDER,
                                                     "favorite": bool(folder.get("favorite"))})

    def delete_folder(self, folder_id):
        return self.call("DELETE", "/folder/delete", {"id": folder_id})

    def create_tag(self, label, color):
        return self.call("POST", "/tag/create", {"label": label, "color": color})

    # ---- sharing (with other accounts of the cloud) --------------------------------------------------------
    def recipients(self, search):
        data = self.call("POST", "/share/recipients", {"search": search, "limit": 8, "withGroups": False})
        return [r for r in (data or []) if isinstance(r, dict) and r.get("type", "user") == "user"]

    def share(self, entry_id, recipient, editable):
        return self.call("POST", "/share/create", {"password": entry_id, "recipient": recipient, "type": "user",
                                                   "editable": bool(editable), "shareable": False})

    def update_share(self, share_id, editable):
        return self.call("PATCH", "/share/update", {"id": share_id, "editable": bool(editable), "shareable": False})

    def unshare(self, share_id):
        return self.call("DELETE", "/share/delete", {"id": share_id})

    # ---- services ----------------------------------------------------------------------------------------
    def change_url(self, domain):
        """Where the site lets one change a password (/.well-known/change-password when it has one)."""
        data = self.call("POST", "/service/password-change", {"domain": domain})
        return (data or {}).get("url") or ""

    def favicon(self, domain, size=64):
        """Image bytes of a site's icon, fetched by the cloud (the site never sees this computer). b"" when the
        cloud only has its letter placeholder (its file name ends in _default): the window draws its own tile."""
        url = f"{self.server}{BASE}/service/favicon/{urllib.parse.quote(domain, safe='')}/{size}"
        req = urllib.request.Request(url, headers={"Authorization": cloud.auth_header(self.user, self.password),
                                                   "User-Agent": "Orneos OS", "Accept": "image/*"})
        try:
            with urllib.request.urlopen(req, timeout=20) as res:
                if "_default" in (res.headers.get("Content-Disposition") or ""):
                    return b""
                raw = res.read(512 * 1024)
        except urllib.error.HTTPError:
            return b""
        except (urllib.error.URLError, OSError, TimeoutError):
            raise ApiError(0, "offline")
        image = raw[:4] in (b"\x89PNG", b"GIF8", b"RIFF") or raw[:3] == b"\xff\xd8\xff"
        return raw if image else b""
