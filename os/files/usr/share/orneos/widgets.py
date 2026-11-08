"""JSON bridge for optional Plasma widgets: agenda, tasks, mail, notes, news, photos, Meet, files,
Deck, the day's brief, account and weather.

Agenda uses Plume's recurrence engine and Connect's account, with a private, account-scoped
cache. Tasks reads the app's database; completing uses its Store (including repeating tasks)
and wakes its existing sync agent. Mail and Notes read their local caches without changing
read markers, content or pinned status. News, account (Drive, Ornis) and weather read the cloud's
own apps as the connected user. Nothing runs until a widget requests data.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import fcntl
import hashlib
import importlib.util
from importlib.machinery import SourceFileLoader
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
from urllib.parse import quote, urljoin, urlsplit
import xml.etree.ElementTree as ET

SHARE = Path(__file__).resolve().parent.parent
CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "orneos"
DATA = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "orneos"
CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "orneos/widgets"


def local_db(path):
    db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=3)
    db.row_factory = sqlite3.Row
    db.execute("BEGIN")
    return db


def read_notes(acc):
    empty = {"ready": False, "state": "setupNotes", "items": [], "groups": []}
    if not (DATA / "notes.db").exists():
        return empty
    db = local_db(DATA / "notes.db")
    try:
        owner = db.execute("SELECT v FROM meta WHERE k='user'").fetchone()
        if not owner or owner[0] != acc[1]:
            return empty
        items = [{"id": r["key"], "title": r["title"], "group": r["category"],
                  "subtitle": r["category"], "favorite": bool(r["favorite"]), "stamp": r["modified"]}
                 for r in db.execute("SELECT key,title,category,favorite,modified FROM notes WHERE deleted=0 ORDER BY modified DESC, key")]
        groups = [{"id": name, "name": name} for name in sorted({n["group"] for n in items if n["group"]})]
        return {"ready": True, "state": "ready", "items": items, "groups": groups}
    finally:
        db.close()


def read_mail(acc):
    empty = {"ready": False, "state": "setupMail", "items": [], "groups": []}
    path = CACHE.parent / "plume.db"
    if not path.exists():
        return empty
    db = local_db(path)
    try:
        def setting(key, default):
            row = db.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
            return json.loads(row[0]) if row else default
        # Plume scopes its disposable cache before loading the account's mailboxes.
        if setting("widget_mail_owner", []) != list(acc[:2]):
            return empty
        primary = setting("mail_account", {})
        boxes = [{"key": "orneos", "address": primary.get("address", ""), "name": "Orneos"}]
        boxes += setting("mail_boxes", [])
        groups = [{"id": b["key"], "name": b.get("name") or b.get("address") or b["key"]} for b in boxes]
        names = {g["id"]: g["name"] for g in groups}
        items = []
        for row in db.execute("SELECT m.message_id,m.subject,m.from_name,m.from_email,m.date_ts,m.seen,f.box "
                              "FROM messages m JOIN mail_folders f ON f.id=m.folder_id "
                              "WHERE f.role='inbox' ORDER BY m.date_ts DESC,m.id DESC"):
            if row["box"] not in names:
                continue
            items.append({"id": row["message_id"], "title": row["subject"], "group": row["box"],
                          "subtitle": row["from_name"] or row["from_email"], "stamp": row["date_ts"],
                          "unread": not bool(row["seen"]), "boxName": names[row["box"]]})
        return {"ready": True, "state": "ready", "items": items, "groups": groups,
                "unread": sum(i["unread"] for i in items)}
    finally:
        db.close()


def load_file(name, path):
    spec = importlib.util.spec_from_loader(name, SourceFileLoader(name, str(path)))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def account():
    try:
        cfg = json.loads((CONFIG / "connect.json").read_text())
        token = (CONFIG / "notify.token").read_text().strip("\n")
        if cfg.get("user") and cfg.get("server") and token:
            return cfg["server"].rstrip("/"), cfg["user"], token
    except (OSError, ValueError):
        pass
    return None


def identity(acc):
    return hashlib.sha256(json.dumps(acc).encode()).hexdigest()


def task_revision(row):
    # Native rev tracks local edits; a clean cloud update may retain it.
    return hashlib.sha256(json.dumps([row["rev"], row["ics"], row["list"]]).encode()).hexdigest()


def read_tasks(acc):
    path = DATA / "tasks.db"
    if not path.exists():
        return {"ready": False, "state": "setup", "tasks": [], "lists": []}
    db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=3)
    db.row_factory = sqlite3.Row
    try:
        db.execute("BEGIN")
        owner = db.execute("SELECT v FROM meta WHERE k='user'").fetchone()
        if not owner or owner[0] != acc[1]:
            return {"ready": False, "state": "setup", "tasks": [], "lists": []}
        lists = [dict(r) for r in db.execute("SELECT href, name, color, readonly FROM lists WHERE state <> 'deleted' ORDER BY ord, name")]
        allowed = {r["href"]: r for r in lists}
        tasks, done = [], []
        # Done since midnight: the ring of the day counts them (a repeating task leaves a done copy).
        midnight = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        for row in db.execute("SELECT key, list, uid, data, rev, ics FROM tasks WHERE deleted=0"):
            item = json.loads(row["data"])
            if row["list"] not in allowed or item.get("cancelled"):
                continue
            if item.get("done"):
                if item.get("done_ts", 0) >= midnight:
                    done.append({"key": row["key"], "title": item.get("title", ""), "list": row["list"],
                                 "doneTs": item["done_ts"]})
                continue
            info = allowed[row["list"]]
            tasks.append({"key": row["key"], "uid": row["uid"], "revision": task_revision(row),
                          "title": item.get("title", ""), "due": item.get("due", ""),
                          "dueTs": item.get("due_ts", 0), "list": row["list"],
                          "listName": info["name"], "color": info["color"] or "#002FA7",
                          "readonly": bool(info["readonly"])})
        tasks.sort(key=lambda t: (t["dueTs"] or float("inf"), t["title"].casefold()))
        return {"ready": True, "state": "ready", "tasks": tasks, "done": done, "lists": lists, "identity": identity(acc)}
    finally:
        db.close()


def complete_task(acc, key, revision, expected_identity):
    # Stale widgets must never complete a different occurrence or another account's task.
    if expected_identity != identity(acc):
        raise ValueError("account changed")
    snapshot = read_tasks(acc)
    task = next((t for t in snapshot.get("tasks", []) if t["key"] == key), None)
    if task is None or task["readonly"] or task["revision"] != revision:
        raise ValueError("task changed")
    sys.path.insert(0, str(SHARE / "orneos-tasks"))
    from tasks_core.store import Store
    store = Store(acc[1], DATA / "tasks.db", existing_only=True)
    try:
        store.db.execute("BEGIN IMMEDIATE")
        row = store.db.execute("SELECT t.rev, t.ics, t.list, l.readonly, l.state FROM tasks t JOIN lists l ON l.href=t.list "
                               "WHERE t.key=? AND t.deleted=0", (key,)).fetchone()
        if (not row or task_revision(row) != revision or row["readonly"] or row["state"] == "deleted"
                or store.meta("user") != acc[1] or account() != acc):
            raise ValueError("task changed")
        store.complete(key, True)
        store.db.execute("COMMIT")
    except Exception:
        store.db.execute("ROLLBACK")
        raise
    finally:
        store.close()
    try:
        subprocess.Popen(["orneos-tasks", "--refresh"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    except OSError:
        # The local edit is already saved; the next normal agent sync will send it.
        pass


def calendar_data(acc, start, end):
    # Reuse the clock's authenticated DAV transport, and Plume's exact recurrence/zone semantics.
    transport = load_file("widget_transport", SHARE.parent / "libexec/orneos-agenda")
    ical = load_file("widget_ical", SHARE / "orneos-plume/plume_core/ical.py")
    server, user, password = acc
    home = f"{server}/remote.php/dav/calendars/{quote(user, safe='')}/"
    body = ('<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
            '<d:prop><d:resourcetype/><d:displayname/><c:supported-calendar-component-set/>'
            '</d:prop></d:propfind>')
    status, raw = transport.call(home, user, password, "PROPFIND", body, depth="1")
    if status != 207:
        raise OSError("calendar unavailable")
    calendars = []
    for response in ET.fromstring(raw).findall("{DAV:}response"):
        if response.find(".//{urn:ietf:params:xml:ns:caldav}calendar") is None:
            continue
        components = response.findall(".//{urn:ietf:params:xml:ns:caldav}comp")
        if components and not any(c.get("name") == "VEVENT" for c in components):
            continue
        href = urljoin(server + "/", response.findtext("{DAV:}href", ""))
        # Never send the app password to a URL on another server.
        if urlsplit(href)[:2] != urlsplit(server)[:2] or not urlsplit(href).path.startswith(urlsplit(home).path):
            continue
        calendars.append((href, response.findtext(".//{DAV:}displayname", "")))

    def fetch(cal):
        href, name = cal
        body = ('<c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
                '<d:prop><c:calendar-data/></d:prop><c:filter><c:comp-filter name="VCALENDAR">'
                '<c:comp-filter name="VEVENT">'
                f'<c:time-range start="{transport.stamp(start)}" end="{transport.stamp(end)}"/>'
                '</c:comp-filter></c:comp-filter></c:filter></c:calendar-query>')
        status, raw = transport.call(href, user, password, "REPORT", body, depth="1")
        if status != 207:
            raise OSError("calendar unavailable")
        events = []
        for data in ET.fromstring(raw).iter("{urn:ietf:params:xml:ns:caldav}calendar-data"):
            for item in ical.occurrences(data.text or "", start, end):
                if not item.get("cancelled"):
                    events.append({k: item[k] for k in ("title", "start", "end", "startTs", "endTs", "allDay", "meet")})
                    events[-1]["calendar"] = name
        return events

    with ThreadPoolExecutor(max_workers=4) as pool:
        events = [event for batch in pool.map(fetch, calendars) for event in batch]
    events.sort(key=lambda e: (e["startTs"], not e["allDay"], e["title"]))
    return {"ready": True, "state": "ready", "events": events}


def read_agenda(acc, start_iso, days):
    ical = load_file("widget_zone", SHARE / "orneos-plume/plume_core/ical.py")
    start = datetime.strptime(start_iso, "%Y-%m-%d").replace(tzinfo=ical.local_zone())
    if not 1 <= days <= 42:
        raise ValueError("range too large")
    directory = CACHE / identity(acc)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    key = f"{start_iso}-{days}-{hashlib.sha256(str(start.tzinfo).encode()).hexdigest()[:12]}"
    path = directory / (key + ".json")
    # Concurrent instances share one fetch, never a partial file. Bound retention of personal data.
    for old in directory.glob("*.json"):
        try:
            if time.time() - old.stat().st_mtime > 30 * 86400:
                old.unlink()
        except FileNotFoundError:
            pass
    with (directory / "fetch.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        cached = None
        try:
            cached = json.loads(path.read_text())
            if time.time() - cached["at"] < 60:
                return cached
        except (OSError, ValueError, KeyError):
            pass
        try:
            result = calendar_data(acc, start, start + timedelta(days=days))
            result["at"] = time.time()
            path.write_text(json.dumps(result))
            return result
        except (OSError, ET.ParseError, ValueError):
            if cached:
                return dict(cached, state="offline")
            return {"ready": False, "state": "offline", "events": []}


def read_feed(acc, kind, folder=""):
    """Read remote data as the connected user, without retaining shared data offline."""
    import cloud
    from xml.sax.saxutils import escape
    items = []
    if kind == "assistant":
        from ornis_chat import Chat
        items = [{"id": r["id"], "title": r["title"], "subtitle": ""}
                 for r in Chat(*acc).sessions()[:20]]
    elif kind == "favorites":
        status, body = cloud.rest(*acc, "/index.php/apps/bookmarks/public/rest/v2/folder/-1/children?layers=-1")
        if status != 200 or body.get("status") == "error":
            raise ValueError("bookmarks unavailable")
        def walk(rows, parent=""):
            for row in rows:
                if row.get("type") == "folder":
                    walk(row.get("children", []), parent + "/" + row.get("title", ""))
                elif row.get("type") == "bookmark":
                    url = row.get("url") or row.get("target", "")
                    if urlsplit(url).scheme in ("https", "http") and urlsplit(url).hostname:
                        items.append({"id": str(row["id"]), "title": row.get("title") or url,
                                      "subtitle": parent.strip("/"), "url": url})
        walk(body.get("data", []))
    else:
        folder = folder.strip("/")
        if not folder:
            return {"ready": False, "state": "chooseTeamFolder", "items": []}
        if any(part in (".", "..", "") for part in folder.split("/")):
            raise ValueError("invalid folder")
        scope = "/files/" + quote(acc[1], safe="") + "/" + quote(folder, safe="/")
        body = ('<d:searchrequest xmlns:d="DAV:" xmlns:oc="http://owncloud.org/ns"><d:basicsearch>'
                '<d:select><d:prop><d:displayname/><oc:fileid/><d:getlastmodified/></d:prop></d:select>'
                '<d:from><d:scope><d:href>' + escape(scope) + '</d:href><d:depth>infinity</d:depth></d:scope></d:from>'
                '<d:where><d:not><d:is-collection/></d:not></d:where>'
                '<d:orderby><d:order><d:prop><d:getlastmodified/></d:prop><d:descending/></d:order></d:orderby>'
                '<d:limit><d:nresults>20</d:nresults></d:limit></d:basicsearch></d:searchrequest>')
        status, raw = cloud.dav(*acc, "/remote.php/dav/", "SEARCH", body, "0")
        if status != 207:
            raise ValueError("folder unavailable")
        for response in ET.fromstring(raw).findall("{DAV:}response"):
            for propstat in response.findall("{DAV:}propstat"):
                if " 200 " not in propstat.findtext("{DAV:}status", ""):
                    continue
                prop = propstat.find("{DAV:}prop")
                fid = prop.findtext("{http://owncloud.org/ns}fileid", "")
                if not fid.isdigit():
                    continue
                items.append({"id": fid, "title": prop.findtext("{DAV:}displayname", ""),
                              "subtitle": prop.findtext("{DAV:}getlastmodified", ""),
                              "url": acc[0] + "/apps/user_oidc/login/1?redirectUrl=" + quote("/f/" + fid, safe="")})
    return {"ready": True, "state": "ready", "items": items}

NEWS_API = "/index.php/apps/news/api/v1-3"
NEWS_IMAGES = 12
NEWS_IMAGE_BYTES = 3 * 1024 * 1024


def news_call(acc, path, method="GET", body=None):
    import cloud
    status, data = cloud.rest(*acc, NEWS_API + path, method, body)
    if status != 200 or not isinstance(data, dict):
        raise ValueError("news unavailable")
    return data


def web_url(url):
    url = (url or "").strip()
    parts = urlsplit(url)
    return url if parts.scheme in ("https", "http") and parts.hostname else ""


def public_host(url):
    """Images come from the feeds: never let one make this computer call its own network."""
    import ipaddress
    import socket
    host = urlsplit(url).hostname
    try:
        infos = socket.getaddrinfo(host, None)
    except (OSError, UnicodeError):
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if not ip.is_global:
            return False
    return bool(infos)


def news_image(item):
    """The picture of an article: its thumbnail, an image enclosure, else the first image of its body."""
    import re
    candidates = [item.get("mediaThumbnail")]
    if str(item.get("enclosureMime") or "").startswith("image/"):
        candidates.append(item.get("enclosureLink"))
    found = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', item.get("body") or "", re.I)
    if found:
        import html
        candidates.append(html.unescape(found.group(1)))
    return next((web_url(c) for c in candidates if web_url(c)), "")


def fetch_image(directory, url):
    """Download once into the widget cache (no credentials, public hosts only); returns the local path."""
    import urllib.request
    path = directory / (hashlib.sha256(url.encode()).hexdigest()[:32] + ".img")
    if path.exists():
        os.utime(path)
        return str(path)
    if not public_host(url):
        return ""
    request = urllib.request.Request(url, headers={"User-Agent": "Orneos OS"})
    try:
        with urllib.request.urlopen(request, timeout=6) as res:
            if not res.headers.get("Content-Type", "").startswith("image/") or not public_host(res.geturl()):
                return ""
            data = res.read(NEWS_IMAGE_BYTES + 1)
    except (OSError, ValueError):
        return ""
    if len(data) > NEWS_IMAGE_BYTES:
        return ""
    temp = path.with_suffix(".part")
    temp.write_bytes(data)
    temp.replace(path)
    return str(path)


def news_catalog(acc, lang):
    """Orneos's Explore catalogue of the cloud's News (news-explore/, else the app's own)."""
    import cloud
    lang = lang if lang in ("fr", "en", "de") else "en"
    for path in (f"/news-explore/feeds.{lang}.json", f"/index.php/apps/news/explore/feeds.{lang}.json",
                 "/index.php/apps/news/explore/feeds.en.json"):
        status, data = cloud.rest(*acc, path)
        if status == 200 and isinstance(data, dict) and data:
            break
    else:
        raise ValueError("catalogue unavailable")
    categories = []
    for name, rows in data.items():
        sources = [{"title": str(r.get("title") or ""), "feed": web_url(r.get("feed")), "site": web_url(r.get("url")),
                    "description": str(r.get("description") or ""), "votes": int(r.get("votes") or 0)}
                   for r in rows if isinstance(r, dict)]
        sources = [s for s in sources if s["feed"] and s["title"]]
        if sources:
            categories.append({"name": str(name), "sources": sources})
    return categories


def same_feed(a, b):
    def norm(url):
        parts = urlsplit(url.strip())
        return (parts.hostname or "").removeprefix("www."), parts.path.rstrip("/"), parts.query
    return norm(a) == norm(b)


def mark_followed(categories, feeds):
    urls = [f.get("url", "") for f in feeds]
    for category in categories:
        for source in category["sources"]:
            source["followed"] = any(same_feed(source["feed"], u) for u in urls)
    return categories


def suggestions(categories, count=6):
    """A few of the best-voted sources not followed yet, one category after another."""
    queues = [[dict(src, category=c["name"]) for src in sorted(c["sources"], key=lambda x: -x["votes"])
               if not src.get("followed")] for c in categories]
    picks = []
    while len(picks) < count and any(queues):
        for queue in queues:
            if queue and len(picks) < count:
                picks.append(queue.pop(0))
    return picks


def news_source(source, feeds, folders):
    """all, starred, folder:<id>, feed:<id> → (type, id) of the News API, or None when it is gone."""
    kind, _, ident = (source or "all").partition(":")
    if kind == "starred":
        return 2, 0
    if kind in ("folder", "feed") and ident.isdigit():
        known = folders if kind == "folder" else feeds
        if any(int(x["id"]) == int(ident) for x in known):
            return (1 if kind == "folder" else 0), int(ident)
        return None
    return 3, 0


def news_data(acc, source, unread_only, lang):
    import html
    feeds = news_call(acc, "/feeds").get("feeds") or []
    folders = news_call(acc, "/folders").get("folders") or []
    names = {int(f["id"]): str(f.get("title") or "") for f in feeds}
    result = {"ready": True, "state": "ready", "items": [],
              "feeds": [{"id": int(f["id"]), "name": names[int(f["id"])], "folder": int(f.get("folderId") or 0),
                         "unread": int(f.get("unreadCount") or 0)} for f in feeds],
              "folders": [{"id": int(f["id"]), "name": str(f.get("name") or "")} for f in folders],
              "suggestions": []}
    if not feeds:
        result["state"] = "noSources"
        try:
            result["suggestions"] = suggestions(mark_followed(news_catalog(acc, lang), feeds))
        except ValueError:
            pass
        return result
    target = news_source(source, result["feeds"], result["folders"])
    if target is None:
        result["state"] = "missingSource"
        return result
    query = f"/items?type={target[0]}&id={target[1]}&getRead={'false' if unread_only else 'true'}&batchSize=60"
    rows = news_call(acc, query).get("items") or []
    # The API orders by id (import order): the widget wants the newest publications first.
    rows.sort(key=lambda r: -int(r.get("pubDate") or 0))
    directory = CACHE / identity(acc) / "news"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    for old in directory.glob("*"):
        try:
            if time.time() - old.stat().st_mtime > 7 * 86400:
                old.unlink()
        except FileNotFoundError:
            pass
    items = []
    for row in rows[:20]:
        link = web_url(row.get("url"))
        items.append({"id": int(row["id"]), "title": html.unescape(str(row.get("title") or "")).strip(),
                      "url": link, "source": names.get(int(row.get("feedId") or 0), ""),
                      "author": str(row.get("author") or ""), "stamp": int(row.get("pubDate") or 0),
                      "unread": bool(row.get("unread")), "starred": bool(row.get("starred")),
                      "picture": news_image(row), "image": ""})
    with ThreadPoolExecutor(max_workers=4) as pool:
        wanted = [i for i in items[:NEWS_IMAGES] if i["picture"]]
        for item, path in zip(wanted, pool.map(lambda i: fetch_image(directory, i["picture"]), wanted)):
            item["image"] = path
    for item in items:
        del item["picture"]
    result["items"] = items
    return result


def read_news(acc, source, unread_only, lang):
    """Shared between instances for 2 min; the last copy stays readable offline."""
    directory = CACHE / identity(acc)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    key = hashlib.sha256(json.dumps([source, unread_only, lang]).encode()).hexdigest()[:16]
    path = directory / f"news-{key}.json"
    with (directory / "news.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        cached = None
        try:
            cached = json.loads(path.read_text())
            if time.time() - cached["at"] < 120:
                return cached
        except (OSError, ValueError, KeyError):
            pass
        try:
            result = news_data(acc, source, unread_only, lang)
        except (OSError, ValueError, KeyError, TypeError):
            if cached:
                return dict(cached, state="offline")
            return {"ready": False, "state": "offline", "items": []}
        result["at"] = time.time()
        path.write_text(json.dumps(result, ensure_ascii=False))
        return result


def forget_news(acc):
    for old in (CACHE / identity(acc)).glob("news-*.json"):
        old.unlink(missing_ok=True)


def follow_news(acc, url):
    url = web_url(url)
    if not url:
        raise ValueError("invalid feed")
    import cloud
    status, _ = cloud.rest(*acc, NEWS_API + "/feeds", "POST", {"url": url, "folderId": 0})
    # 409: already followed, which is what the person wanted.
    if status not in (200, 409):
        raise ValueError("feed refused")
    forget_news(acc)


def read_article(acc, item_id):
    if not str(item_id).isdigit():
        raise ValueError("invalid item")
    import cloud
    status, _ = cloud.rest(*acc, f"{NEWS_API}/items/{int(item_id)}/read", "PUT")
    if status != 200:
        raise ValueError("item unavailable")
    forget_news(acc)


def read_catalog(acc, lang):
    feeds = news_call(acc, "/feeds").get("feeds") or []
    return {"ready": True, "state": "ready", "categories": mark_followed(news_catalog(acc, lang), feeds)}


def read_account(acc):
    """Drive storage and Ornis's 24 h usage, as the cloud counts them."""
    import cloud
    quota = cloud.quota_info(*acc)
    if not quota:
        raise ValueError("account unavailable")
    result = {"ready": True, "state": "ready", "drive": quota, "ornis": None}
    status, data = cloud.rest(*acc, "/index.php/apps/integration_openai/quota-info")
    usage = (data or {}).get("quota_usage") if status == 200 and isinstance(data, dict) else None
    text = (usage.get("0") if isinstance(usage, dict) else usage[0] if isinstance(usage, list) and usage else None)
    if isinstance(text, dict) and int(text.get("limit") or 0) > 0:
        used, limit = int(text.get("used") or 0), int(text["limit"])
        result["ornis"] = {"used": used, "limit": limit, "percent": max(0, min(100, round(used * 100 / limit)))}
    return result


WEATHER_API = "/ocs/v2.php/apps/weather_status/api/v1"


def read_weather(acc):
    """The cloud's weather (weather_status: met.no, the place chosen in the cloud's dashboard)."""
    import cloud
    status, data = cloud.ocs(*acc, WEATHER_API + "/location?format=json")
    place = ((data or {}).get("ocs") or {}).get("data") if status == 200 else None
    if not isinstance(place, dict):
        raise ValueError("weather unavailable")
    if not place.get("lat") or not place.get("lon"):
        return {"ready": True, "state": "noPlace", "place": "", "hours": []}
    status, data = cloud.ocs(*acc, WEATHER_API + "/forecast?format=json")
    series = ((data or {}).get("ocs") or {}).get("data") if status == 200 else None
    if not isinstance(series, list):
        raise ValueError("weather unavailable")
    hours = []
    for step in series:
        details = ((step.get("data") or {}).get("instant") or {}).get("details") or {}
        nxt = (step.get("data") or {}).get("next_1_hours") or {}
        try:
            stamp = datetime.fromisoformat(str(step["time"]).replace("Z", "+00:00")).timestamp()
        except (KeyError, ValueError):
            continue
        hours.append({"stamp": stamp, "temp": details.get("air_temperature"),
                      "wind": details.get("wind_speed"), "humidity": details.get("relative_humidity"),
                      "symbol": str((nxt.get("summary") or {}).get("symbol_code") or ""),
                      "rain": (nxt.get("details") or {}).get("precipitation_amount")})
    return {"ready": True, "state": "ready" if hours else "error", "place": str(place.get("address") or ""), "hours": hours}


def set_weather_place(acc, address):
    import cloud
    address = (address or "").strip()
    if not 2 <= len(address) <= 200:
        raise ValueError("invalid place")
    status, data = cloud.ocs(*acc, WEATHER_API + "/location?format=json", "PUT", {"address": address})
    found = ((data or {}).get("ocs") or {}).get("data") if status == 200 else None
    if not isinstance(found, dict) or not found.get("success"):
        raise ValueError("place not found")


PHOTOS_SHOWN = 24
PHOTOS_SIZE = 768


def photos_api(acc):
    sys.path.insert(0, str(SHARE / "orneos-photos"))
    from photos_core.api import Api
    return Api(acc, timeout=25)


def photo_days(api, source, today):
    """(Memories filters, the day ids to show) for recent, favorites, onthisday or album:<owner/name>."""
    kind, _, album = source.partition(":")
    filters = {"fav": 1} if kind == "favorites" else {"albums": album} if kind == "album" and album else {}
    days = [int(d["dayid"]) for d in api.days(filters) if int(d.get("count") or 0) > 0]
    if kind == "onthisday":
        # A day id counts days since 1970 in the photo's own time: the same day of other years, ±3 days.
        def near(dayid):
            date = datetime(1970, 1, 1) + timedelta(days=dayid)
            if date.year >= today.year:
                return False
            same = date.replace(year=today.year) if not (date.month == 2 and date.day == 29) else date.replace(year=today.year, day=28)
            return abs((same.date() - today.date()).days) <= 3
        days = [d for d in days if near(d)]
    return filters, days


def photos_data(acc, source):
    api = photos_api(acc)
    try:
        albums = [{"id": str(a.get("cluster_id") or ""), "name": str(a.get("name") or ""), "count": int(a.get("count") or 0)}
                  for a in api.clusters("albums") if a.get("cluster_id")]
        kind = source.partition(":")[0]
        if kind == "album" and not any("album:" + a["id"] == source for a in albums):
            return {"ready": True, "state": "missingAlbum", "items": [], "albums": albums, "shown": source}
        filters, days = photo_days(api, source, datetime.now())
        shown = source
        if not days and kind == "onthisday":
            # No memory today: the latest photos rather than an empty widget (the view says so).
            filters, days = photo_days(api, "recent", datetime.now())
            shown = "recent"
        rows = []
        for start in range(0, len(days), 6):
            rows += [r for r in api.day(days[start:start + 6], filters) if not r.get("isvideo")]
            if len(rows) >= PHOTOS_SHOWN * 2:
                break
        if kind != "recent" or shown != source:
            # Favourites, memories and albums: a different selection every day, the same all day long.
            import random
            random.Random(datetime.now().strftime("%Y-%m-%d") + source).shuffle(rows)
        rows = rows[:PHOTOS_SHOWN]
        directory = CACHE / identity(acc) / "photos"
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        for old in directory.glob("*"):
            try:
                if time.time() - old.stat().st_mtime > 14 * 86400:
                    old.unlink()
            except FileNotFoundError:
                pass
        def path_of(row):
            return directory / (hashlib.sha256(f"{row['fileid']}:{row.get('etag', '')}".encode()).hexdigest()[:32] + ".img")
        missing = [r for r in rows if not path_of(r).exists()]
        for start in range(0, len(missing), 8):
            batch = missing[start:start + 8]
            try:
                images = api.multipreview([(str(r["fileid"]), r["fileid"], PHOTOS_SIZE) for r in batch])
            except Exception:
                images = {}
            for row in batch:
                data = images.get(str(row["fileid"]))
                if data:
                    temp = path_of(row).with_suffix(".part")
                    temp.write_bytes(data)
                    temp.replace(path_of(row))
        items = []
        for row in rows:
            path = path_of(row)
            if not path.exists():
                continue
            os.utime(path)
            dayid = int(row.get("dayid") or 0)
            items.append({"id": int(row["fileid"]), "image": str(path), "w": int(row.get("w") or 0),
                          "h": int(row.get("h") or 0), "day": (datetime(1970, 1, 1) + timedelta(days=dayid)).strftime("%Y-%m-%d"),
                          "favorite": bool(row.get("isfavorite"))})
        state = "ready" if items else "emptyPhotos"
        return {"ready": True, "state": state, "items": items, "albums": albums, "shown": shown}
    finally:
        api.close()


def read_photos(acc, source):
    """Shared between instances for 10 min; the last selection stays on the desktop offline."""
    directory = CACHE / identity(acc)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    key = hashlib.sha256(json.dumps([source, datetime.now().strftime("%Y-%m-%d")]).encode()).hexdigest()[:16]
    path = directory / f"photos-{key}.json"
    for old in directory.glob("photos-*.json"):
        if old != path:
            old.unlink(missing_ok=True)
    with (directory / "photos.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        cached = None
        try:
            cached = json.loads(path.read_text())
            if time.time() - cached["at"] < 600 and all(Path(i["image"]).exists() for i in cached["items"]):
                return cached
        except (OSError, ValueError, KeyError):
            pass
        try:
            result = photos_data(acc, source)
        except Exception:
            if cached:
                return dict(cached, state="offline")
            return {"ready": False, "state": "offline", "items": []}
        result["at"] = time.time()
        path.write_text(json.dumps(result, ensure_ascii=False))
        return result


TALK_ONE_TO_ONE, TALK_CHANGELOG = 1, 4


def talk_text(message):
    """A Talk message as plain text: {actor}, {file}… replaced by their names."""
    text = str(message.get("message") or "")
    for key, value in (message.get("messageParameters") or {}).items():
        if isinstance(value, dict):
            text = text.replace("{" + key + "}", str(value.get("name") or ""))
    return " ".join(text.split())


def read_meet(acc):
    """Meet's copy on this computer (the app keeps it fresh while it runs), and today's meetings."""
    empty = {"ready": False, "state": "setupMeet", "rooms": [], "meetings": []}
    path = DATA / "meet.db"
    if not path.exists():
        return empty
    db = local_db(path)
    try:
        owner = db.execute("SELECT v FROM meta WHERE k='user'").fetchone()
        if not owner or owner[0] != acc[1]:
            return empty
        rooms = []
        for (raw,) in db.execute("SELECT data FROM rooms ORDER BY activity DESC"):
            r = json.loads(raw)
            if int(r.get("type") or 0) == TALK_CHANGELOG or r.get("isArchived"):
                continue
            last = r.get("lastMessage") if isinstance(r.get("lastMessage"), dict) else {}
            one = int(r.get("type") or 0) == TALK_ONE_TO_ONE
            mention = bool(r.get("unreadMention") or r.get("unreadMentionDirect"))
            unread = int(r.get("unreadMessages") or 0)
            rooms.append({"token": str(r.get("token") or ""), "name": str(r.get("displayName") or r.get("name") or ""),
                          "one": one, "unread": unread, "mention": mention, "call": bool(r.get("hasCall")),
                          "waiting": bool(unread and (one or mention)),
                          "last": talk_text(last), "actor": "" if one else str(last.get("actorDisplayName") or ""),
                          "stamp": int(r.get("lastActivity") or 0)})
    finally:
        db.close()
    rooms.sort(key=lambda r: (not r["call"], not r["waiting"], -r["stamp"]))
    meetings = []
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        agenda = read_agenda(acc, today, 1)
        meetings = [e for e in agenda.get("events", []) if e.get("meet") and e["endTs"] > time.time()]
    except Exception:
        pass
    return {"ready": True, "state": "ready", "rooms": rooms, "meetings": meetings,
            "waiting": sum(r["waiting"] for r in rooms)}


def read_files(acc):
    """The latest documents changed in the Drive; opened from ~/Orneos when the file is already there."""
    import cloud
    from urllib.parse import unquote
    from xml.sax.saxutils import escape
    root = "/files/" + quote(acc[1], safe="")
    body = ('<d:searchrequest xmlns:d="DAV:" xmlns:oc="http://owncloud.org/ns"><d:basicsearch>'
            '<d:select><d:prop><d:displayname/><oc:fileid/><d:getlastmodified/><d:getcontenttype/><oc:size/></d:prop></d:select>'
            '<d:from><d:scope><d:href>' + escape(root) + '</d:href><d:depth>infinity</d:depth></d:scope></d:from>'
            '<d:where><d:not><d:is-collection/></d:not></d:where>'
            '<d:orderby><d:order><d:prop><d:getlastmodified/></d:prop><d:descending/></d:order></d:orderby>'
            '<d:limit><d:nresults>20</d:nresults></d:limit></d:basicsearch></d:searchrequest>')
    status, raw = cloud.dav(*acc, "/remote.php/dav/", "SEARCH", body, "0")
    if status != 207:
        raise ValueError("files unavailable")
    prefix = "/remote.php/dav" + root + "/"
    sync = cloud.SYNC_DIR.resolve()
    items = []
    for response in ET.fromstring(raw).findall("{DAV:}response"):
        href = unquote(urlsplit(response.findtext("{DAV:}href", "")).path)
        if prefix not in href:
            continue
        relative = href.split(prefix, 1)[1]
        for propstat in response.findall("{DAV:}propstat"):
            if " 200 " not in propstat.findtext("{DAV:}status", ""):
                continue
            prop = propstat.find("{DAV:}prop")
            fid = prop.findtext("{http://owncloud.org/ns}fileid", "")
            if not fid.isdigit():
                continue
            try:
                from email.utils import parsedate_to_datetime
                stamp = parsedate_to_datetime(prop.findtext("{DAV:}getlastmodified", "")).timestamp()
            except (TypeError, ValueError):
                stamp = 0
            local = (sync / relative).resolve()
            inside = local.is_relative_to(sync) and local.is_file()
            folder = relative.rsplit("/", 1)[0] if "/" in relative else ""
            items.append({"id": fid, "title": prop.findtext("{DAV:}displayname", "") or relative.rsplit("/", 1)[-1],
                          "folder": folder, "mime": prop.findtext("{DAV:}getcontenttype", ""), "stamp": stamp,
                          "local": str(local) if inside else "",
                          "url": acc[0] + "/apps/user_oidc/login/1?redirectUrl=" + quote("/f/" + fid, safe="")})
    return {"ready": True, "state": "ready", "items": items}


DECK_BUCKETS = ("overdue", "today", "tomorrow", "nextSevenDays", "later")


def read_deck(acc):
    """Deck cards with a due date, assigned to me or to nobody, as the cloud's Upcoming page lists them."""
    import cloud
    status, data = cloud.ocs(*acc, "/ocs/v2.php/apps/deck/api/v1.0/overview/upcoming?format=json")
    overview = ((data or {}).get("ocs") or {}).get("data") if status == 200 else None
    if status in (404, 412):
        return {"ready": False, "state": "noDeck", "items": []}
    if not isinstance(overview, dict):
        raise ValueError("deck unavailable")
    items = []
    for bucket in DECK_BUCKETS:
        for card in overview.get(bucket) or []:
            if not isinstance(card, dict) or card.get("done") or card.get("archived") or card.get("deletedAt"):
                continue
            try:
                due = datetime.fromisoformat(str(card.get("duedate"))).timestamp()
            except ValueError:
                continue
            board = card.get("board") if isinstance(card.get("board"), dict) else {}
            color = str(board.get("color") or "")
            items.append({"id": int(card["id"]), "title": str(card.get("title") or ""), "due": due, "bucket": bucket,
                          "board": str(board.get("title") or ""),
                          "color": "#" + color if len(color) == 6 and all(c in "0123456789abcdefABCDEF" for c in color) else "",
                          "url": acc[0] + "/apps/user_oidc/login/1?redirectUrl=" + quote(f"/apps/deck/card/{int(card['id'])}", safe="")})
    items.sort(key=lambda c: c["due"])
    return {"ready": True, "state": "ready", "items": items}


def read_brief(acc):
    """Ornis du jour, computed on this computer: what is left today in the calendar, the tasks, the mail
    and Meet. Nothing goes to Ornis until the person asks it to prepare the day."""
    brief = {"ready": True, "state": "ready", "events": [], "tasks": None, "mail": None, "waiting": None}
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        brief["events"] = [e for e in read_agenda(acc, today, 1).get("events", []) if e["endTs"] > time.time()]
    except Exception:
        pass
    try:
        tasks = read_tasks(acc)
        if tasks.get("ready"):
            end = datetime.now().replace(hour=23, minute=59, second=59).timestamp()
            due = [t for t in tasks["tasks"] if t["dueTs"] and t["dueTs"] <= end]
            midnight = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
            brief["tasks"] = {"today": len(due), "late": sum(t["dueTs"] < midnight for t in due),
                              "done": len(tasks.get("done", [])), "first": [t["title"] for t in due[:3]]}
    except Exception:
        pass
    try:
        mail = read_mail(acc)
        if mail.get("ready"):
            unread = [i for i in mail["items"] if i["unread"]]
            brief["mail"] = {"unread": len(unread), "from": list(dict.fromkeys(i["subtitle"] for i in unread if i["subtitle"]))[:3]}
    except Exception:
        pass
    try:
        meet = read_meet(acc)
        if meet.get("ready"):
            brief["waiting"] = meet["waiting"]
    except Exception:
        pass
    return brief


def add_note(acc, text, folder=""):
    """A note written in the Notes widget: straight to the cloud (Notes API), so it is on every device at once;
    the Notes app takes it at its next sync. First line = title."""
    import cloud
    text = (text or "").strip()
    if not text or len(text) > 20000 or any(part in (".", "..") for part in folder.split("/")):
        raise ValueError("invalid note")
    title = text.splitlines()[0].strip().lstrip("#").strip()[:80]
    rest = "\n".join(text.splitlines()[1:]).strip()
    content = f"# {title}\n\n{rest}\n" if rest else f"# {title}\n"
    status, _ = cloud.rest(*acc, "/index.php/apps/notes/api/v1/notes", "POST",
                           {"title": title, "content": content, "category": folder.strip("/")})
    if status != 200:
        raise ValueError("note refused")



def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=("agenda", "tasks", "complete", "mail", "notes", "assistant", "favorites", "team",
                                         "news", "news-catalog", "news-follow", "news-read", "account", "weather", "weather-place",
                                         "photos", "meet", "files", "deck", "brief", "notes-add"))
    parser.add_argument("--start")
    parser.add_argument("--folder", default="")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--key")
    parser.add_argument("--revision")
    parser.add_argument("--identity")
    parser.add_argument("--source", default="all")
    parser.add_argument("--unread", action="store_true")
    parser.add_argument("--lang", default="en")
    parser.add_argument("--url", default="")
    parser.add_argument("--address", default="")
    parser.add_argument("--text", default="")
    args = parser.parse_args()
    lang = args.lang[:2].lower()
    acc = account()
    result = {"ready": False, "state": "signed_out", "events": [], "tasks": [], "lists": []}
    try:
        if acc:
            if args.kind in ("news-follow", "news-read", "weather-place", "notes-add"):
                # Actions: the widget reads the exit code, then refreshes its view.
                try:
                    if args.kind == "news-follow":
                        follow_news(acc, args.url)
                    elif args.kind == "news-read":
                        read_article(acc, args.key)
                    elif args.kind == "notes-add":
                        add_note(acc, args.text, args.folder)
                    else:
                        set_weather_place(acc, args.address)
                except Exception:
                    print(json.dumps({"ready": False, "state": "actionError"}))
                    sys.exit(1)
                result = {"ready": True, "state": "ready"}
            elif args.kind == "news":
                result = read_news(acc, args.source, args.unread, lang)
            elif args.kind == "news-catalog":
                result = read_catalog(acc, lang)
            elif args.kind == "meet":
                result = read_meet(acc)
            elif args.kind == "files":
                result = read_files(acc)
            elif args.kind == "deck":
                result = read_deck(acc)
            elif args.kind == "brief":
                result = read_brief(acc)
            elif args.kind == "photos":
                result = read_photos(acc, args.source if args.source != "all" else "recent")
            elif args.kind == "account":
                result = read_account(acc)
            elif args.kind == "weather":
                result = read_weather(acc)
            elif args.kind in ("assistant", "favorites", "team"):
                result = read_feed(acc, args.kind, args.folder)
            elif args.kind == "agenda":
                result = read_agenda(acc, args.start, args.days)
            elif args.kind == "mail":
                result = read_mail(acc)
            elif args.kind == "notes":
                result = read_notes(acc)
            else:
                if args.kind == "complete":
                    complete_task(acc, args.key, args.revision, args.identity)
                result = read_tasks(acc)
            # A request started on a previous account must not display its result after switching.
            if account() != acc:
                result = {"ready": False, "state": "signed_out", "events": [], "tasks": [], "lists": []}
    except Exception:
        result = {"ready": False, "state": "error", "events": [], "tasks": [], "lists": []}
    print(json.dumps(result, ensure_ascii=False))
