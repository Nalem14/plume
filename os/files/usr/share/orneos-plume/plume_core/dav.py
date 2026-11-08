"""CalDAV and CardDAV for Plume: discovery, incremental sync (RFC 6578), multiget, PUT and DELETE.

One keep-alive HTTPS connection per client (a TLS handshake per request would cost more than the
requests themselves). Calls run on the sync worker thread, never on the UI thread.
"""
import http.client
import ssl
import urllib.parse
import uuid
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
        all_headers = {"Authorization": self._auth, "User-Agent": "Orneos Plume"}
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

    def collections(self, home, kind):
        """Calendars (kind "calendar", events only) or address books ("addressbook") under home."""
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
            if kind == "calendar":
                subscribed = q(CS, "subscribed") in types
                if q(C, "calendar") not in types and not subscribed:
                    continue
                comps = props.get(q(C, "supported-calendar-component-set"))
                names = {comp.get("name") for comp in comps} if comps is not None else {"VEVENT"}
                if "VEVENT" not in names:
                    continue
            else:
                if q(CARD, "addressbook") not in types:
                    continue
                subscribed = False
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
                "subscribed": subscribed,
            })
        return found

    def freebusy(self, organizer, attendees, start, end):
        """When people of the cloud are busy (RFC 6638 scheduling outbox): {address: [(start, end) UTC
        "YYYYMMDDTHHMMSSZ" pairs]}, or None for an address the cloud does not know. Only busy times
        come back, never what the events are."""
        calendars, _ = self.homes()
        stamp = start.strftime("%Y%m%dT%H%M%SZ")
        lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Orneos//Plume//FR", "METHOD:REQUEST", "BEGIN:VFREEBUSY",
                 f"UID:{uuid.uuid4()}", f"DTSTAMP:{stamp}", f"DTSTART:{stamp}", f"DTEND:{end.strftime('%Y%m%dT%H%M%SZ')}",
                 f"ORGANIZER:mailto:{organizer}"] + [f"ATTENDEE:mailto:{a}" for a in attendees] + ["END:VFREEBUSY", "END:VCALENDAR"]
        status, _, raw = self.request("POST", calendars.rstrip("/") + "/outbox/", "\r\n".join(lines) + "\r\n",
                                      {"Content-Type": "text/calendar; charset=utf-8"})
        if status != 200:
            raise DavError(status, "free/busy")
        out = {}
        for resp in ET.fromstring(raw).findall(q(C, "response")):
            who = (resp.findtext(f"{q(C, 'recipient')}/{q(D, 'href')}") or "").strip().removeprefix("mailto:").lower()
            if not (resp.findtext(q(C, "request-status")) or "").startswith("2."):
                out[who] = None
                continue
            busy = []
            for line in (resp.findtext(q(C, "calendar-data")) or "").replace("\r\n ", "").splitlines():
                name, _, value = line.partition(":")
                if name.split(";")[0].upper() == "FREEBUSY" and "FBTYPE=FREE" not in name.upper():
                    busy += [tuple(period.split("/", 1)) for period in value.strip().split(",") if "/" in period]
            out[who] = busy
        return out

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

    def multiget(self, href, hrefs, kind):
        """{href: (etag, data)} for the given objects, in batches."""
        if kind == "calendar":
            report, data_tag, ns = "c:calendar-multiget", "c:calendar-data", C
        else:
            report, data_tag, ns = "card:addressbook-multiget", "card:address-data", CARD
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
        if "etag" not in res_headers:
            # the server changed what it stored (scheduling, ids) and sends no etag: ask for it, or the
            # next change of this object would be refused
            status, res_headers, _ = self.request("HEAD", href)
        return res_headers.get("etag", "")

    def move(self, href, destination):
        """Into another collection of the same account, as one object: the server sends no cancellation or
        refusal to the guests, which a copy then a deletion would. Returns its etag there."""
        target = f"{self.scheme}://{self.host}{self.path(destination)}"
        status, _, _ = self.request("MOVE", href, None, {"Destination": urllib.parse.quote(target, safe=":/@%"), "Overwrite": "F"})
        if status not in (201, 204):
            raise DavError(status, "MOVE")
        status, res_headers, _ = self.request("HEAD", destination)
        return res_headers.get("etag", "")

    # ---- calendars themselves ----------------------------------------------------------------------------
    def make_calendar(self, home, name, color):
        """A new calendar of events under home; its href."""
        href = home.rstrip("/") + "/" + uuid.uuid4().hex[:12] + "/"
        body = (f'<?xml version="1.0" encoding="utf-8"?><c:mkcalendar {XMLNS}><d:set><d:prop>'
                f'<d:displayname>{escape(name)}</d:displayname><a:calendar-color>{escape(color)}</a:calendar-color>'
                '<c:supported-calendar-component-set><c:comp name="VEVENT"/></c:supported-calendar-component-set>'
                '</d:prop></d:set></c:mkcalendar>')
        status, _, _ = self.request("MKCALENDAR", href, body, {"Content-Type": "application/xml; charset=utf-8"})
        if status not in (200, 201):
            raise DavError(status, "MKCALENDAR")
        return href

    def subscribe(self, home, url, name, color):
        """A calendar followed from a link (webcal, .ics): the cloud reads it again on its own; its href."""
        href = home.rstrip("/") + "/" + uuid.uuid4().hex[:12] + "/"
        body = (f'<?xml version="1.0" encoding="utf-8"?><d:mkcol {XMLNS}><d:set><d:prop>'
                '<d:resourcetype><d:collection/><cs:subscribed/></d:resourcetype>'
                f'<d:displayname>{escape(name)}</d:displayname><a:calendar-color>{escape(color)}</a:calendar-color>'
                f'<cs:source><d:href>{escape(url)}</d:href></cs:source></d:prop></d:set></d:mkcol>')
        status, _, _ = self.request("MKCOL", href, body, {"Content-Type": "application/xml; charset=utf-8"})
        if status not in (200, 201):
            raise DavError(status, "MKCOL subscribed")
        return href

    def update_calendar(self, href, name=None, color=None):
        props = ""
        if name is not None:
            props += f"<d:displayname>{escape(name)}</d:displayname>"
        if color is not None:
            props += f"<a:calendar-color>{escape(color)}</a:calendar-color>"
        if not props:
            return
        body = f'<?xml version="1.0" encoding="utf-8"?><d:propertyupdate {XMLNS}><d:set><d:prop>{props}</d:prop></d:set></d:propertyupdate>'
        status, _, _ = self.request("PROPPATCH", href, body, {"Content-Type": "application/xml; charset=utf-8"})
        if status not in (200, 207):
            raise DavError(status, "PROPPATCH")

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
