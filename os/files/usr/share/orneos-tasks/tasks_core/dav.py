"""CalDAV for Tâches (Plume's client, for the lists that hold tasks): discovery, incremental sync (RFC 6578),
multiget, PUT and DELETE, and the lists themselves (MKCALENDAR, PROPPATCH).

One keep-alive HTTPS connection per client (a TLS handshake per request would cost more than the
requests themselves). Calls run on the sync worker thread, never on the UI thread.
"""
import http.client
import ssl
import urllib.parse
import xml.etree.ElementTree as ET
from base64 import b64encode

D, C, CARD, CS, APPLE, OC, NC = (
    "DAV:", "urn:ietf:params:xml:ns:caldav", "urn:ietf:params:xml:ns:carddav", "http://calendarserver.org/ns/",
    "http://apple.com/ns/ical/", "http://owncloud.org/ns", "http://nextcloud.com/ns")
XMLNS = (f'xmlns:d="{D}" xmlns:c="{C}" xmlns:card="{CARD}" xmlns:cs="{CS}" xmlns:a="{APPLE}" '
         f'xmlns:oc="{OC}" xmlns:nc="{NC}"')
BATCH = 50


class DavError(Exception):
    def __init__(self, status, message=""):
        super().__init__(f"{status} {message}".strip())
        self.status = status


def q(ns, tag):
    return f"{{{ns}}}{tag}"


class Client:
    def __init__(self, root, user, password, timeout=30):
        """root: the DAV root, https://app.orneos.eu/remote.php/dav/ on the cloud."""
        self.root = root if root.endswith("/") else root + "/"
        parts = urllib.parse.urlsplit(self.root)
        self.scheme, self.host = parts.scheme, parts.netloc
        self.user = user
        self._auth = "Basic " + b64encode(f"{user}:{password}".encode()).decode()
        self._timeout = timeout
        self._conn = None

    # ---- transport ----------------------------------------------------------------------------------
    def _connection(self):
        if self._conn is None:
            if self.scheme == "https":
                self._conn = http.client.HTTPSConnection(self.host, timeout=self._timeout,
                                                         context=ssl.create_default_context())
            else:
                self._conn = http.client.HTTPConnection(self.host, timeout=self._timeout)
        return self._conn

    def close(self):
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def request(self, method, href, body=None, headers=None):
        """(status, headers, body bytes). Retries once on a dropped keep-alive connection."""
        path = self.path(href)
        all_headers = {"Authorization": self._auth, "User-Agent": "Orneos Taches"}
        if headers:
            all_headers.update(headers)
        data = body.encode() if isinstance(body, str) else body
        for attempt in (1, 2):
            try:
                conn = self._connection()
                conn.request(method, path, body=data, headers=all_headers)
                res = conn.getresponse()
                raw = res.read()
                return res.status, {k.lower(): v for k, v in res.getheaders()}, raw
            except (http.client.HTTPException, ConnectionError, TimeoutError, OSError) as error:
                self.close()
                if attempt == 2:
                    raise DavError(0, type(error).__name__) from error
        raise DavError(0)

    def path(self, href):
        if href.startswith(("http://", "https://")):
            parts = urllib.parse.urlsplit(href)
            return parts.path + ("?" + parts.query if parts.query else "")
        if href.startswith("/"):
            return href
        return urllib.parse.urlsplit(self.root).path + href

    def _xml(self, method, href, body, depth=None):
        headers = {"Content-Type": "application/xml; charset=utf-8"}
        if depth is not None:
            headers["Depth"] = depth
        status, _, raw = self.request(method, href, body, headers)
        if status == 207:
            try:
                return status, ET.fromstring(raw)
            except ET.ParseError as error:
                raise DavError(status, "bad XML") from error
        return status, None

    # ---- discovery ----------------------------------------------------------------------------------
    def _href_prop(self, href, ns, tag):
        status, doc = self._xml("PROPFIND", href, f'<d:propfind {XMLNS}><d:prop><{prefix(ns)}:{tag}/></d:prop></d:propfind>', "0")
        if doc is None:
            raise DavError(status, f"PROPFIND {tag}")
        node = doc.find(f".//{q(ns, tag)}/{q(D, 'href')}")
        if node is None or not (node.text or "").strip():
            raise DavError(status, f"no {tag}")
        return node.text.strip()

    def homes(self):
        """(calendar home, address book home) hrefs, from the current user's principal."""
        principal = self._href_prop(self.root, D, "current-user-principal")
        self.principal = principal
        calendars = self._href_prop(principal, C, "calendar-home-set")
        try:
            books = self._href_prop(principal, CARD, "addressbook-home-set")
        except DavError:
            books = None
        return calendars, books

    def collections(self, home, kind="tasks"):
        """The calendars that hold tasks (VTODO) under home."""
        body = (f'<d:propfind {XMLNS}><d:prop><d:resourcetype/><d:displayname/><a:calendar-color/><a:calendar-order/>'
                '<c:supported-calendar-component-set/><d:sync-token/><cs:getctag/><d:current-user-privilege-set/>'
                '<oc:owner-principal/><nc:owner-displayname/><cs:source/></d:prop></d:propfind>')
        status, doc = self._xml("PROPFIND", home, body, "1")
        if doc is None:
            raise DavError(status, "PROPFIND collections")
        found = []
        home_path = self.path(home).rstrip("/")
        for resp in doc.findall(q(D, "response")):
            href = (resp.findtext(q(D, "href")) or "").strip()
            if not href or self.path(href).rstrip("/") == home_path:
                continue
            props = {}
            for propstat in resp.findall(q(D, "propstat")):
                if "200" in (propstat.findtext(q(D, "status")) or ""):
                    for prop in propstat.find(q(D, "prop")) or []:
                        props[prop.tag] = prop
            rtype = props.get(q(D, "resourcetype"))
            types = {child.tag for child in rtype} if rtype is not None else set()
            subscribed = q(CS, "subscribed") in types
            if q(C, "calendar") not in types or subscribed:
                continue
            comps = props.get(q(C, "supported-calendar-component-set"))
            names = {comp.get("name") for comp in comps} if comps is not None else {"VEVENT"}
            if "VTODO" not in names:
                continue
            privileges = props.get(q(D, "current-user-privilege-set"))
            granted = {p.tag for p in privileges.iter()} if privileges is not None else {q(D, "write")}
            writable = bool(granted & {q(D, "write"), q(D, "all"), q(D, "write-content")}) and not subscribed
            owner = props.get(q(OC, "owner-principal"))
            owner_text = (owner.text or "").strip() if owner is not None else ""
            shared = bool(owner_text) and owner_text.rstrip("/").split("/")[-1] != self.user
            found.append({
                "href": href if href.endswith("/") else href + "/",
                "name": text(props.get(q(D, "displayname"))) or href.rstrip("/").split("/")[-1],
                "color": (text(props.get(q(APPLE, "calendar-color"))) or "")[:7],
                "order": int(text(props.get(q(APPLE, "calendar-order"))) or 0) if (text(props.get(q(APPLE, "calendar-order"))) or "0").lstrip("-").isdigit() else 0,
                "sync_token": text(props.get(q(D, "sync-token"))),
                "ctag": text(props.get(q(CS, "getctag"))),
                "readonly": not writable,
                "shared": shared,
                "owner_name": text(props.get(q(NC, "owner-displayname"))) if shared else "",
                "events": "VEVENT" in names,
            })
        return found

    # ---- reading ------------------------------------------------------------------------------------
    def sync(self, href, token):
        """RFC 6578 sync-collection. (new token, {href: etag} changed, [deleted hrefs]).
        Raises DavError(409/403) when the token is no longer valid: start again with token ""."""
        changed, deleted = {}, []
        while True:
            body = (f'<d:sync-collection {XMLNS}><d:sync-token>{escape(token or "")}</d:sync-token>'
                    '<d:sync-level>1</d:sync-level><d:prop><d:getetag/></d:prop></d:sync-collection>')
            status, doc = self._xml("REPORT", href, body)
            if doc is None:
                raise DavError(status, "sync-collection")
            truncated = False
            for resp in doc.findall(q(D, "response")):
                ref = (resp.findtext(q(D, "href")) or "").strip()
                code = resp.findtext(q(D, "status")) or ""
                if self.path(ref).rstrip("/") == self.path(href).rstrip("/"):
                    if "507" in code:
                        truncated = True
                    continue
                if "404" in code:
                    deleted.append(ref)
                    changed.pop(ref, None)
                    continue
                etag = resp.findtext(f".//{q(D, 'getetag')}")
                if etag:
                    changed[ref] = etag.strip()
            token = (doc.findtext(q(D, "sync-token")) or token or "").strip()
            if not truncated:
                return token, changed, deleted

    def etags(self, href):
        """{href: etag} of every object: for servers without sync-collection."""
        status, doc = self._xml("PROPFIND", href, f'<d:propfind {XMLNS}><d:prop><d:getetag/></d:prop></d:propfind>', "1")
        if doc is None:
            raise DavError(status, "PROPFIND etags")
        found = {}
        for resp in doc.findall(q(D, "response")):
            ref = (resp.findtext(q(D, "href")) or "").strip()
            etag = resp.findtext(f".//{q(D, 'getetag')}")
            if ref and etag and self.path(ref).rstrip("/") != self.path(href).rstrip("/"):
                found[ref] = etag.strip()
        return found

    def multiget(self, href, hrefs):
        """{href: (etag, data)} for the given objects, in batches."""
        report, data_tag, ns = "c:calendar-multiget", "c:calendar-data", C
        result = {}
        hrefs = list(hrefs)
        for start in range(0, len(hrefs), BATCH):
            chunk = hrefs[start:start + BATCH]
            refs = "".join(f"<d:href>{escape(self.path(h))}</d:href>" for h in chunk)
            body = f'<{report} {XMLNS}><d:prop><d:getetag/><{data_tag}/></d:prop>{refs}</{report}>'
            status, doc = self._xml("REPORT", href, body, "1")
            if doc is None:
                raise DavError(status, "multiget")
            for resp in doc.findall(q(D, "response")):
                ref = (resp.findtext(q(D, "href")) or "").strip()
                etag = resp.findtext(f".//{q(D, 'getetag')}")
                data = resp.findtext(f".//{q(ns, data_tag.split(':')[1])}")
                if ref and data:
                    result[ref] = ((etag or "").strip(), data)
        return result

    # ---- writing ------------------------------------------------------------------------------------
    def put(self, href, data, content_type, etag=None):
        """Create (etag None) or update an object. Returns its new etag ("" when the server sent none)."""
        headers = {"Content-Type": content_type}
        if etag:
            headers["If-Match"] = etag
        else:
            headers["If-None-Match"] = "*"
        status, res_headers, _ = self.request("PUT", href, data, headers)
        if status not in (200, 201, 204):
            raise DavError(status, "PUT")
        return res_headers.get("etag", "")

    def get(self, href):
        """(etag, data) of one object; None when it is gone."""
        status, headers, raw = self.request("GET", href, None, {"Accept": "text/calendar"})
        if status == 404:
            return None
        if status != 200:
            raise DavError(status, "GET")
        return headers.get("etag", ""), raw.decode("utf-8", "replace")

    def make_list(self, home, slug, name, color):
        """A new list (a calendar for tasks only). Returns its href; an existing one of that name is reused."""
        href = self.path(home).rstrip("/") + "/" + slug + "/"
        body = (f'<c:mkcalendar {XMLNS}><d:set><d:prop><d:displayname>{escape(name)}</d:displayname>'
                f'<a:calendar-color>{escape(color)}</a:calendar-color><c:supported-calendar-component-set>'
                '<c:comp name="VTODO"/></c:supported-calendar-component-set></d:prop></d:set></c:mkcalendar>')
        status, _, _ = self.request("MKCALENDAR", href, body, {"Content-Type": "application/xml; charset=utf-8"})
        if status not in (201, 405):        # 405: it exists already
            raise DavError(status, "MKCALENDAR")
        return href

    def set_list(self, href, name=None, color=None, order=None):
        props = ""
        if name is not None:
            props += f"<d:displayname>{escape(name)}</d:displayname>"
        if color is not None:
            props += f"<a:calendar-color>{escape(color)}</a:calendar-color>"
        if order is not None:
            props += f"<a:calendar-order>{int(order)}</a:calendar-order>"
        if not props:
            return
        status, _, _ = self.request("PROPPATCH", href, f'<d:propertyupdate {XMLNS}><d:set><d:prop>{props}</d:prop></d:set></d:propertyupdate>',
                                    {"Content-Type": "application/xml; charset=utf-8"})
        if status not in (200, 207):
            raise DavError(status, "PROPPATCH")

    # ---- sharing a list with an account or a group (the cloud's own: <oc:share>, read back by <oc:invite>) --------
    def shares(self, href):
        """[{principal, name, readOnly, group}] of the list."""
        status, doc = self._xml("PROPFIND", href, f'<d:propfind {XMLNS}><d:prop><oc:invite/></d:prop></d:propfind>', "0")
        if doc is None:
            raise DavError(status, "PROPFIND invite")
        found = []
        for user in doc.iter(q(OC, "user")):
            principal = (user.findtext(q(D, "href")) or "").strip()
            access = user.find(q(OC, "access"))
            name = (user.findtext(q(OC, "common-name")) or "").strip()
            if principal:
                found.append({"principal": principal.removeprefix("principal:"), "name": name or principal.rstrip("/").split("/")[-1],
                              "readOnly": access is not None and access.find(q(OC, "read-write")) is None,
                              "group": "/groups/" in principal})
        return found

    def share(self, href, principal, read_only):
        access = "" if read_only else "<oc:read-write/>"
        body = (f'<?xml version="1.0" encoding="utf-8"?><oc:share {XMLNS}><oc:set>'
                f'<d:href>principal:{escape(principal)}</d:href>{access}</oc:set></oc:share>')
        status, _, _ = self.request("POST", href, body, {"Content-Type": "application/xml; charset=utf-8"})
        if status not in (200, 204):
            raise DavError(status, "share")

    def unshare(self, href, principal):
        body = (f'<?xml version="1.0" encoding="utf-8"?><oc:share {XMLNS}><oc:remove>'
                f'<d:href>principal:{escape(principal)}</d:href></oc:remove></oc:share>')
        status, _, _ = self.request("POST", href, body, {"Content-Type": "application/xml; charset=utf-8"})
        if status not in (200, 204):
            raise DavError(status, "unshare")

    def delete(self, href, etag=None):
        headers = {"If-Match": etag} if etag else {}
        status, _, _ = self.request("DELETE", href, None, headers)
        if status not in (200, 204, 404):
            raise DavError(status, "DELETE")


def prefix(ns):
    return {D: "d", C: "c", CARD: "card", CS: "cs", APPLE: "a", OC: "oc", NC: "nc"}[ns]


def text(node):
    return (node.text or "").strip() if node is not None and node.text else ""


def escape(value):
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
