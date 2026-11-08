"""Shared helpers for the Orneos desktop: the app password Connect stored, OCS and DAV."""
import json
import mimetypes
import os
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import uuid
from base64 import b64encode
from pathlib import Path
from xml.dom import minidom
from xml.parsers.expat import ExpatError

import system

CLOUD = "https://app.orneos.eu"
SSO = CLOUD + "/apps/user_oidc/login/1?redirectUrl="
CFG = system.CONFIG / "connect.json"
TOKEN = CFG.parent / "notify.token"
STATE = system.STATE
SYNC_DIR = Path.home() / "Orneos"
OCNS = "http://owncloud.org/ns"


_keychain = {}


def secret_entry(server, user):
    """The app password's name in the system's keychain (Plume outside Orneos OS: account.py)."""
    return f"app-password:{user}@{server.rstrip('/')}"


def account():
    """(server, user, app password) of the account Connect (or Plume) signed in, or None."""
    try:
        data = json.loads(CFG.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    user, server = data.get("user"), data.get("server")
    try:
        password = TOKEN.read_text().strip("\n")
    except OSError:
        password = ""
    if not password and data.get("keychain") and user and server:
        key = (secret_entry(server, user), data.get("at"))      # read once per sign-in, not at every call
        if not _keychain.get(key):                                 # a locked keychain: asked again
            _keychain.clear()
            _keychain[key] = system.secret_get(key[0]) or ""
        password = _keychain[key]
    if not user or not server or not password:
        return None
    return server.rstrip("/"), user, password


def auth_header(user, password):
    return "Basic " + b64encode(f"{user}:{password}".encode()).decode()


def _call(url, user, password, method="GET", data=None, headers=None, timeout=20):
    req_headers = {
        "Authorization": auth_header(user, password),
        "User-Agent": "Orneos OS",
        "OCS-APIRequest": "true",
        "Accept": "application/json",
    }
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.status, res.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()
    except (urllib.error.URLError, OSError, TimeoutError):
        return 0, b""


def _parse(raw):
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def ocs(server, user, password, path, method="GET", body=None, content_type="application/json"):
    url = server.rstrip("/") + path
    data = None
    headers = {}
    if body is not None:
        headers["Content-Type"] = content_type
        if isinstance(body, bytes):
            data = body
        elif content_type.startswith("application/x-www-form-urlencoded"):
            data = urllib.parse.urlencode(body).encode()
        else:
            data = json.dumps(body).encode()
    status, raw = _call(url, user, password, method, data, headers)
    return status, _parse(raw)


def rest(server, user, password, path, method="GET", body=None, content_type="application/json"):
    return ocs(server, user, password, path, method, body, content_type)


def dav(server, user, password, url, method, body=None, depth=None, content_type="application/xml; charset=utf-8"):
    if url.startswith("/"):
        url = server.rstrip("/") + url
    headers = {}
    if body is not None:
        headers["Content-Type"] = content_type
    if depth is not None:
        headers["Depth"] = depth
    data = body.encode() if isinstance(body, str) else body
    return _call(url, user, password, method, data, headers, timeout=60)


def copy_to_sync(paths):
    """Copy files into ~/Orneos (the files-client sync root). Used only by « Copier dans Orneos »."""
    SYNC_DIR.mkdir(parents=True, exist_ok=True)
    copied = []
    for raw in paths:
        src = Path(raw)
        if not src.exists() or not src.is_file():
            continue
        dest = SYNC_DIR / src.name
        n = 1
        while dest.exists():
            n += 1
            dest = SYNC_DIR / f"{src.stem}-{n}{src.suffix}"
        shutil.copy2(src, dest)
        copied.append(dest)
    return copied


def cloud_link(path):
    """SSO URL into the cloud. Path may include ?query; never use a #fragment (lost on redirect)."""
    if not path:
        return CLOUD
    if path.startswith("https://") or path.startswith("http://"):
        parsed = urllib.parse.urlsplit(path)
        cloud_host = urllib.parse.urlsplit(CLOUD).netloc
        if parsed.netloc == cloud_host and not parsed.path.startswith(("/apps/user_oidc/", "/s/")):
            rel = parsed.path or "/"
            if parsed.query:
                rel += "?" + parsed.query
            return SSO + urllib.parse.quote(rel, safe="/")
        return path
    if not path.startswith("/"):
        path = "/" + path
    path = path.split("#", 1)[0]
    return SSO + urllib.parse.quote(path, safe="/")


def open_url(url):
    system.open_url(url)


def copy_to_clipboard(text: str) -> bool:
    if not text:
        return False
    for cmd in (
        ["qdbus6", "org.kde.klipper", "/klipper", "org.kde.klipper.klipper.setClipboardContents", text],
        ["qdbus", "org.kde.klipper", "/klipper", "org.kde.klipper.klipper.setClipboardContents", text],
        ["busctl", "--user", "call", "org.kde.klipper", "/klipper", "org.kde.klipper.klipper", "setClipboardContents", "s", text],
    ):
        try:
            r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=4)
            if r.returncode == 0:
                return True
        except (OSError, subprocess.TimeoutExpired):
            continue
    if shutil.which("wl-copy"):
        try:
            subprocess.Popen(["wl-copy", text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except OSError:
            pass
    return False


def desktop_notify(title: str, body: str = "", icon: str = "orneos", url: str = "") -> None:
    if not system.has_notify_send():
        system.notify(title, body, (lambda: open_url(url)) if url else None)
        return
    lang = (os.environ.get("LANG") or "fr").split("_", 1)[0][:2]
    open_label = {"fr": "Ouvrir", "de": "Öffnen", "en": "Open"}.get(lang, "Open")
    cmd = ["notify-send", "-a", "Orneos", "-i", icon, "-h", "string:desktop-entry:eu.orneos.connect"]
    if url:
        cmd.append(f"--action=default={open_label}")
    cmd.append(title)
    if body:
        cmd.append(body)
    if not url:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    import threading
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)

    def _watch():
        out = proc.stdout.read() if proc.stdout else ""
        if "default" in out:
            open_url(url)

    threading.Thread(target=_watch, daemon=True).start()


def userinfo(server, user, password):
    status, body = ocs(server, user, password, "/ocs/v2.php/cloud/user?format=json")
    if status not in (200, 100):
        return {}
    return (body.get("ocs") or {}).get("data") or {}


def format_bytes(num_bytes: int, lang: str = "fr") -> str:
    unit_gb = "Go" if lang == "fr" else "GB"
    unit_mb = "Mo" if lang == "fr" else "MB"
    b = max(0, int(num_bytes or 0))
    if b >= 1024 ** 3 or b == 0:
        val = f"{b / (1024 ** 3):.1f}"
        if lang in ("fr", "de"):
            val = val.replace(".", ",")
        return f"{val} {unit_gb}"
    val = f"{max(1, round(b / (1024 ** 2)))}"
    return f"{val} {unit_mb}"


def quota_info(server, user, password, lang="fr"):
    info = userinfo(server, user, password)
    if not info:
        return None
    q = info.get("quota") if isinstance(info.get("quota"), dict) else {}
    used = int(q.get("used") or 0)
    total = int(q.get("total") or 0)
    rel = float(q.get("relative") or (round(used * 100.0 / total, 1) if total > 0 else 0.0))
    display_name = info.get("displayname") or info.get("display-name") or user
    email = info.get("email") or (f"{user}@orneos.eu" if "@" not in user else user)
    return {
        "user": user,
        "displayName": str(display_name),
        "email": str(email),
        "usedBytes": used,
        "totalBytes": total,
        "usedText": format_bytes(used, lang),
        "totalText": format_bytes(total, lang) if total > 0 else "∞",
        "percent": max(0, min(100, int(round(rel)))),
    }


def create_share_link(server, user, password, local_path):
    """Ensure local_path is in the user's cloud, create a public share link, and return its URL."""
    src = Path(local_path).resolve()
    if not src.exists():
        return None
    sync_root = SYNC_DIR.resolve()
    try:
        rel_posix = src.relative_to(sync_root).as_posix()
        in_sync = True
    except ValueError:
        in_sync = False
        rel_posix = ""

    quoted_user = urllib.parse.quote(user, safe="")
    if not in_sync:
        if not src.is_file():
            return None
        shares_dir = SYNC_DIR / "Partages"
        shares_dir.mkdir(parents=True, exist_ok=True)
        dest = shares_dir / src.name
        if not dest.exists() or dest.stat().st_mtime < src.stat().st_mtime:
            shutil.copy2(src, dest)
        rel_posix = f"Partages/{dest.name}"
        dav(server, user, password, f"/remote.php/dav/files/{quoted_user}/Partages", "MKCOL")
        try:
            dav(
                server, user, password,
                f"/remote.php/dav/files/{quoted_user}/{urllib.parse.quote(rel_posix, safe='/')}",
                "PUT", dest.read_bytes(), content_type="application/octet-stream")
        except OSError:
            return None
    else:
        dav_path = f"/remote.php/dav/files/{quoted_user}/{urllib.parse.quote(rel_posix, safe='/')}"
        st, _ = dav(server, user, password, dav_path, "PROPFIND", depth="0")
        if st not in (200, 207) and src.is_file():
            try:
                dav(server, user, password, dav_path, "PUT", src.read_bytes(), content_type="application/octet-stream")
            except OSError:
                pass

    status, body = ocs(
        server, user, password,
        "/ocs/v2.php/apps/files_sharing/api/v1/shares?format=json",
        method="POST",
        body={"path": "/" + rel_posix.lstrip("/"), "shareType": "3"},
        content_type="application/x-www-form-urlencoded",
    )
    data = (body.get("ocs") or {}).get("data") if isinstance(body, dict) else None
    if status in (200, 100) and isinstance(data, dict) and data.get("url"):
        return str(data["url"])
    return None


def search(server, user, password, provider, term, limit=5):
    q = urllib.parse.urlencode({"term": term, "limit": str(limit)})
    status, body = ocs(
        server, user, password,
        f"/ocs/v2.php/search/providers/{urllib.parse.quote(provider, safe='')}/search?{q}")
    if status not in (200, 100):
        return []
    data = (body.get("ocs") or {}).get("data")
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        rows = data.get("entries") or data.get("data") or []
    else:
        rows = []
    origin = urllib.parse.urlsplit(server)
    base = f"{origin.scheme}://{origin.netloc}"
    found = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = " ".join((row.get("title") or "").split())
        url = row.get("resourceUrl") or row.get("url") or ""
        if url.startswith("/"):
            url = cloud_link(url)
        elif url.startswith("http"):
            url = cloud_link(url)
        elif url:
            url = cloud_link("/" + url.lstrip("/"))
        if title and url:
            row = dict(row)
            row["title"] = title
            row["resourceUrl"] = url
            found.append(row)
    return found


def mail_accounts(server, user, password):
    for path in (
        "/apps/mail/api/accounts",
        "/index.php/apps/mail/api/accounts",
        "/apps/mail/api/v1/accounts",
        "/index.php/apps/mail/api/v1/accounts",
    ):
        status, body = rest(server, user, password, path)
        if isinstance(body, list):
            rows = body
        elif isinstance(body, dict):
            rows = body.get("data") if isinstance(body.get("data"), list) else (
                (body.get("ocs") or {}).get("data"))
        else:
            rows = None
        if status in (200, 100) and isinstance(rows, list):
            return rows
    return []


def _flatten_mailboxes(items):
    flat = []
    for box in items or []:
        if not isinstance(box, dict):
            continue
        flat.append(box)
        children = box.get("mailboxes") or box.get("children")
        if isinstance(children, list) and children:
            flat.extend(_flatten_mailboxes(children))
    return flat


def mail_mailboxes(server, user, password, account_id, sync=False):
    aid = int(account_id)
    queries = (
        [f"accountId={aid}&forceSync=true", f"accountId={aid}", f"id={aid}"]
        if sync else [f"accountId={aid}", f"id={aid}"]
    )
    bases = (
        "/apps/mail/api/mailboxes",
        "/index.php/apps/mail/api/mailboxes",
        "/apps/mail/api/v1/mailboxes",
        "/index.php/apps/mail/api/v1/mailboxes",
    )
    for q in queries:
        for base in bases:
            status, body = rest(server, user, password, f"{base}?{q}")
            if status not in (200, 100):
                continue
            if isinstance(body, list):
                rows = body
            elif isinstance(body, dict):
                if isinstance(body.get("mailboxes"), list):
                    rows = body["mailboxes"]
                elif isinstance(body.get("data"), list):
                    rows = body["data"]
                else:
                    ocs_data = (body.get("ocs") or {}).get("data")
                    rows = ocs_data.get("mailboxes") if isinstance(ocs_data, dict) else ocs_data
            else:
                rows = None
            if isinstance(rows, list):
                return _flatten_mailboxes(rows)
    return []


def _mailbox_roles(box):
    use = (
        box.get("specialUse")
        or box.get("specialRole")
        or box.get("specialUses")
        or box.get("attributes")
        or []
    )
    if isinstance(use, (str, int)):
        use = [use]
    names = {
        str(part).lstrip("\\").strip().lower()
        for part in use
        if part not in (None, "", 0, "0")
    }
    for key in ("name", "displayName", "id"):
        val = str(box.get(key) or "").strip().lower()
        if val in {"inbox", "courrier entrant", "boîte de réception", "posteingang"}:
            names.add("inbox")
        elif val in {"drafts", "brouillons", "entwürfe"}:
            names.add("drafts")
        elif val in {"trash", "corbeille", "papierkorb", "deleted", "deleted messages"}:
            names.add("trash")
        elif val in {"junk", "spam", "indésirables", "courrier indésirable"}:
            names.add("junk")
        elif val in {"sent", "envoyés", "messages envoyés", "gesendet"}:
            names.add("sent")
    return names


def _mailbox_db_id(box):
    """Mail API `id` is base64(name); the numeric id for URLs is `databaseId`."""
    if not isinstance(box, dict):
        return None
    for key in ("databaseId", "database_id"):
        if box.get(key) is not None:
            try:
                return int(box[key])
            except (TypeError, ValueError):
                pass
    raw = box.get("id")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _box_unread(box):
    for key in ("unread", "unreadCounter", "unreadCount", "totalUnread", "unseen"):
        if box.get(key) is not None:
            try:
                return int(box.get(key) or 0)
            except (TypeError, ValueError):
                pass
    return 0


def mail_unread(server, user, password):
    """Unread count for the Courrier badge. Prefer Inbox; otherwise sum non-trash/junk mailboxes."""
    total_inbox = 0
    total_other = 0
    found_inbox = False
    ignored_roles = {"trash", "junk", "spam", "drafts", "sent", "deleted"}
    accounts = mail_accounts(server, user, password)
    if not accounts:
        return 0
    for item in accounts:
        if not isinstance(item, dict):
            continue
        acc_id = item.get("accountId") if item.get("accountId") is not None else item.get("id")
        if acc_id is None:
            continue
        for box in mail_mailboxes(server, user, password, acc_id, sync=True):
            if not isinstance(box, dict):
                continue
            n = max(0, _box_unread(box))
            roles = _mailbox_roles(box)
            if "inbox" in roles:
                found_inbox = True
                total_inbox += n
            elif roles.isdisjoint(ignored_roles):
                total_other += n
    return total_inbox if found_inbox else total_other


def mail_draft_mailbox(server, user, password):
    """(account_id, drafts_mailbox_database_id) for opening a draft in the Mail UI."""
    accounts = mail_accounts(server, user, password)
    if not accounts:
        return None, None
    first_acc = accounts[0] if isinstance(accounts[0], dict) else {}
    account_id = first_acc.get("accountId") if first_acc.get("accountId") is not None else first_acc.get("id")
    if account_id is None:
        return None, None
    boxes = mail_mailboxes(server, user, password, account_id)
    drafts = None
    inbox = None
    first = None
    for box in boxes:
        db_id = _mailbox_db_id(box)
        if db_id is None:
            continue
        if first is None:
            first = db_id
        roles = _mailbox_roles(box)
        if "drafts" in roles:
            drafts = db_id
        if "inbox" in roles:
            inbox = db_id
    mailbox = drafts if drafts is not None else (inbox if inbox is not None else first)
    return int(account_id), mailbox


def _multipart_file(field, path: Path):
    boundary = "----Orneos" + uuid.uuid4().hex
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    data = path.read_bytes()
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field}"; filename="{path.name}"\r\n'
        f"Content-Type: {mime}\r\n\r\n"
    ).encode() + data + f"\r\n--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


def mail_upload_attachment(server, user, password, path: Path, account_id=None):
    """POST /apps/mail/api/attachments — returns local attachment id or None."""
    try:
        body, content_type = _multipart_file("attachment", path)
    except OSError:
        return None
    q = f"?accountId={int(account_id)}" if account_id else ""
    for base in ("/apps/mail/api/attachments", "/index.php/apps/mail/api/attachments"):
        status, created = rest(
            server, user, password, base + q, method="POST",
            body=body, content_type=content_type)
        data = created.get("data") if isinstance(created, dict) and "data" in created else created
        if status in (200, 201) and isinstance(data, dict) and data.get("id") is not None:
            return int(data["id"])
    return None


def mail_attach_draft(server, user, password, subject, files):
    """Create a draft with real local attachments (no copy into ~/Orneos)."""
    account_id, mailbox_id = mail_draft_mailbox(server, user, password)
    if not account_id or not mailbox_id:
        return None, None
    attachments = []
    for path in files:
        att_id = mail_upload_attachment(server, user, password, Path(path), account_id)
        if att_id is not None:
            attachments.append({"type": "local", "id": att_id})
    if not attachments:
        return mailbox_id, None
    body = {
        "accountId": account_id,
        "subject": subject,
        "bodyPlain": "",
        "bodyHtml": "",
        "editorBody": "",
        "isHtml": False,
        "smimeSign": False,
        "smimeEncrypt": False,
        "to": [],
        "cc": [],
        "bcc": [],
        "attachments": attachments,
    }
    for path in ("/apps/mail/api/drafts", "/index.php/apps/mail/api/drafts"):
        status, created = rest(server, user, password, path, method="POST", body=body)
        data = created.get("data") if isinstance(created, dict) else None
        if not isinstance(data, dict) and isinstance(created, dict):
            data = created
        if status in (200, 201) and isinstance(data, dict) and data.get("id") is not None:
            return mailbox_id, int(data["id"])
    return mailbox_id, None


def _djb2(text: str) -> int:
    h = 5381
    for b in text.encode():
        h = ((h << 5) + h + b) & 0xFFFFFFFF
    return h


# The unread badge goes on Courrier's dock pin (the app of Orneos OS). Before, it went on Plume's (one app for
# mail, calendar and contacts), and before Plume on the Courrier web shortcut (the same id as the app now).
BADGE_APP = "eu.orneos.mail"
LEGACY_BADGE_APP = "eu.orneos.plume"


def _forget_legacy_badge() -> bool:
    """Remove the badge overrides of Plume's pin. Its user .desktop copy would otherwise keep a Plume entry
    that no longer starts anything. True when something was removed."""
    removed = False
    home = Path.home() / ".local" / "share"
    desktop = home / "applications" / f"{LEGACY_BADGE_APP}.desktop"
    try:
        if desktop.is_file() and "mail-dock-icon" in desktop.read_text():
            desktop.unlink()
            removed = True
    except OSError:
        pass
    for path in [home / "icons" / "hicolor" / f"{size}x{size}" / "apps" / f"{LEGACY_BADGE_APP}.png" for size in (32, 48, 64, 128)] + [
            home / "icons" / "hicolor" / "scalable" / "apps" / f"{LEGACY_BADGE_APP}.svg", STATE / "mail-icon-base.png",
            STATE / "plume-icon-base.png"]:
        try:
            if path.is_file():
                path.unlink()
                removed = True
        except OSError:
            pass
    return removed


def _mail_desktop_override(icon_path: Path | None) -> bool:
    """Override ~/.local/share/applications/eu.orneos.mail.desktop with an absolute Icon= path.

    Plasma's LauncherTasksModel (org.kde.plasma.icontasks) caches QIcon::fromTheme("eu.orneos.mail")
    in KIconLoader's disk cache, so overwriting hicolor PNGs alone does not update a pinned dock icon.
    Changing Icon= in the user .desktop file to a count-specific PNG path and running kbuildsycoca6
    triggers KSycoca::databaseChanged(), which clears LauncherTasksModel::appDataCache and reloads the
    new QIcon directly from the file path.
    """
    src = Path(f"/usr/share/applications/{BADGE_APP}.desktop")
    dest = Path.home() / ".local" / "share" / "applications" / f"{BADGE_APP}.desktop"
    if icon_path is None:
        try:
            if dest.is_file() or dest.is_symlink():
                dest.unlink()
                return True
        except OSError:
            pass
        return False
    if not src.is_file():
        return False
    try:
        text = src.read_text()
    except OSError:
        return False
    target_line = f"Icon={icon_path}"
    lines = []
    seen_icon = False
    for line in text.splitlines():
        if line.startswith("Icon="):
            lines.append(target_line)
            seen_icon = True
        else:
            lines.append(line)
    if not seen_icon:
        lines.append(target_line)
    new_text = "\n".join(lines) + "\n"
    try:
        if dest.is_file() and dest.read_text() == new_text:
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".desktop.tmp")
        tmp.write_text(new_text)
        tmp.replace(dest)
        return True
    except OSError:
        return False


def _refresh_sycoca(icon_root: Path) -> None:
    if shutil.which("gtk-update-icon-cache"):
        try:
            subprocess.run(
                ["gtk-update-icon-cache", "-f", str(icon_root)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            pass
    try:
        subprocess.run(
            ["kbuildsycoca6", "--noincremental"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        pass


def _mail_icon_badge(count: int, legacy: bool = False) -> bool:
    """Paint the unread badge on Courrier's icon and update the user .desktop + hicolor theme."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return False
    base_svg = Path(f"/usr/share/icons/hicolor/scalable/apps/{BADGE_APP}.svg")
    if not base_svg.is_file():
        return False
    STATE.mkdir(parents=True, exist_ok=True)
    icon_root = Path.home() / ".local" / "share" / "icons" / "hicolor"
    stamp = STATE / "mail.badge.icon"
    key = str(count)
    dock_png = STATE / f"mail-dock-icon-{count}.png"
    user_desktop = Path.home() / ".local" / "share" / "applications" / f"{BADGE_APP}.desktop"

    def clear_override() -> bool:
        changed = False
        for old in STATE.glob("mail-dock-icon*.png"):
            try:
                old.unlink()
                changed = True
            except OSError:
                pass
        for size in (32, 48, 64, 128):
            p = icon_root / f"{size}x{size}" / "apps" / f"{BADGE_APP}.png"
            try:
                if p.is_file():
                    p.unlink()
                    changed = True
            except OSError:
                pass
        scalable = icon_root / "scalable" / "apps" / f"{BADGE_APP}.svg"
        try:
            if scalable.is_file():
                scalable.unlink()
                changed = True
        except OSError:
            pass
        if _mail_desktop_override(None):
            changed = True
        return changed

    if count <= 0:
        prev = ""
        try:
            prev = stamp.read_text().strip()
        except OSError:
            pass
        changed = clear_override()
        try:
            stamp.write_text("0\n")
        except OSError:
            pass
        if changed or legacy or prev not in ("", "0"):
            _refresh_sycoca(icon_root)
        return True

    try:
        if (
            stamp.read_text().strip() == key
            and dock_png.is_file()
            and user_desktop.is_file()
            and f"Icon={dock_png}" in user_desktop.read_text()
        ):
            if legacy:
                _refresh_sycoca(icon_root)
            return True
    except OSError:
        pass

    tmp = STATE / f"{BADGE_APP}-icon-base.png"
    if not tmp.is_file():
        for cmd in (
            ["rsvg-convert", "-w", "128", "-h", "128", str(base_svg), "-o", str(tmp)],
            ["magick", "-background", "none", str(base_svg), "-resize", "128x128", str(tmp)],
            ["convert", "-background", "none", str(base_svg), "-resize", "128x128", str(tmp)],
        ):
            try:
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15, check=True)
                if tmp.is_file():
                    break
            except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
                continue
        else:
            return False
    try:
        base = Image.open(tmp).convert("RGBA")
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass
        return False

    label = "99+" if count > 99 else str(count)
    for size in (32, 48, 64, 128):
        img = base.resize((size, size), Image.Resampling.LANCZOS)
        draw = ImageDraw.Draw(img)
        badge_d = max(14, size // 2)
        bx, by = size - badge_d - 1, 1
        # saffron with Prussian-blue figures, like the badges inside Plume
        draw.ellipse(
            (bx, by, bx + badge_d, by + badge_d),
            fill=(240, 162, 2, 255), outline=(255, 255, 255, 255),
            width=max(1, size // 42))
        font_size = max(9, int(badge_d * (0.42 if len(label) >= 3 else 0.52)))
        try:
            font = ImageFont.truetype("/usr/share/fonts/orneos/SchibstedGrotesk-wght.ttf", font_size)
        except OSError:
            try:
                font = ImageFont.load_default(font_size)
            except TypeError:                      # Pillow < 10.1
                font = ImageFont.load_default()
        bb = draw.textbbox((0, 0), label, font=font)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        draw.text(
            (bx + (badge_d - tw) / 2 - bb[0], by + (badge_d - th) / 2 - bb[1]),
            label, fill=(15, 36, 64, 255), font=font)
        out = icon_root / f"{size}x{size}" / "apps" / f"{BADGE_APP}.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        img.save(out)
        if size == 128:
            img.save(dock_png)

    for old in STATE.glob("mail-dock-icon*.png"):
        if old != dock_png:
            try:
                old.unlink()
            except OSError:
                pass

    # Scalable override: embed the 128px PNG so theme lookup never keeps the clean SVG.
    png128 = icon_root / "128x128" / "apps" / f"{BADGE_APP}.png"
    try:
        import base64
        b64 = base64.b64encode(png128.read_bytes()).decode("ascii")
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
            'width="128" height="128" viewBox="0 0 128 128">\n'
            f'<image width="128" height="128" xlink:href="data:image/png;base64,{b64}"/>\n'
            "</svg>\n"
        )
        scalable = icon_root / "scalable" / "apps" / f"{BADGE_APP}.svg"
        scalable.parent.mkdir(parents=True, exist_ok=True)
        scalable.write_text(svg)
    except OSError:
        pass

    _mail_desktop_override(dock_png)
    try:
        stamp.write_text(key + "\n")
    except OSError:
        pass
    _refresh_sycoca(icon_root)
    return True


_DBUS_BUS = None


def mail_badge_owner(pid):
    """Courrier (or Plume), while it runs, keeps the badge itself (it knows at once what is read): orneos-notify
    leaves it alone. None gives it back (only when this process holds it)."""
    path = STATE / "mail.badge.plume"
    try:
        if pid is None:
            if path.is_file() and path.read_text().strip() == str(os.getpid()):
                path.unlink(missing_ok=True)
        elif not path.is_file() or path.read_text().strip() != str(pid):
            STATE.mkdir(parents=True, exist_ok=True)
            path.write_text(f"{pid}\n")
    except OSError:
        pass


def mail_badge_owned():
    """True while a running Plume keeps the badge."""
    try:
        pid = int((STATE / "mail.badge.plume").read_text().strip())
        return b"plume" in Path(f"/proc/{pid}/cmdline").read_bytes()
    except (OSError, ValueError):
        return False


def talk_owner(pid):
    """Meet (or Plume with its Meet module), while it runs, tells the chats and calls of Talk itself (a click
    opens the conversation in the app): orneos-notify leaves those to it. None gives them back."""
    path = STATE / "talk.notify.meet"
    try:
        if pid is None:
            if path.is_file() and path.read_text().strip() == str(os.getpid()):
                path.unlink(missing_ok=True)
        elif not path.is_file() or path.read_text().strip() != str(pid):
            STATE.mkdir(parents=True, exist_ok=True)
            path.write_text(f"{pid}\n")
    except OSError:
        pass


def talk_owned():
    """True while a running Meet (or Plume) tells Talk's chats and calls."""
    try:
        pid = int((STATE / "talk.notify.meet").read_text().strip())
        cmdline = Path(f"/proc/{pid}/cmdline").read_bytes()
        return b"meet" in cmdline or b"plume" in cmdline
    except (OSError, ValueError):
        return False


def mail_badge(count, heavy=False):
    """Unread count (mail.badge, read by Plume and the panel) + the badge on Courrier's dock pin."""
    global _DBUS_BUS
    count = max(0, min(int(count or 0), 9999))
    try:
        STATE.mkdir(parents=True, exist_ok=True)
        (STATE / "mail.badge").write_text(str(count) + "\n")
        (STATE / "mail.badge.meta").write_text("count=%d\n" % count)
    except OSError:
        pass
    system.badge(count)                      # Plume's tray and the app's icon (Windows, macOS)
    if system.WINDOWS or system.MACOS:
        return                               # no Plasma dock to paint
    painted = False
    legacy = _forget_legacy_badge()
    try:
        painted = bool(_mail_icon_badge(count, legacy))
    except Exception as error:
        try:
            (STATE / "mail.badge.meta").write_text(
                "count=%d\nicon_error=%s\n" % (count, type(error).__name__))
        except OSError:
            pass
    if legacy and not painted:
        _refresh_sycoca(Path.home() / ".local" / "share" / "icons" / "hicolor")
    # Only show the Unity LauncherEntry overlay if painting the icon badge failed;
    # otherwise clear it so Icon Tasks does not draw a second badge on top of ours.
    unity_visible = bool(count > 0 and not painted)
    uri = f"application://{BADGE_APP}.desktop"
    try:
        import dbus
        if _DBUS_BUS is None:
            _DBUS_BUS = dbus.SessionBus()
        props = dbus.Dictionary({
            dbus.String("count"): dbus.Int64(count),
            dbus.String("count-visible"): dbus.Boolean(unity_visible),
            dbus.String("urgent"): dbus.Boolean(False),
        }, signature="sv")
        path = f"/com/canonical/unity/launcherentry/{_djb2(uri)}"
        msg = dbus.lowlevel.SignalMessage(path, "com.canonical.Unity.LauncherEntry", "Update")
        msg.append(dbus.String(uri), signature="s")
        msg.append(props, signature="a{sv}")
        _DBUS_BUS.send_message(msg)
        _DBUS_BUS.flush()
    except Exception:
        _DBUS_BUS = None


