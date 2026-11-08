"""Address books themselves, over the cloud's CardDAV: made, renamed, deleted, shared with an account or a
group (the sharing of the cloud's Contacts app: POST <oc:share> on the book, <oc:invite> to read it back).
Each function takes a dav.Client; Sync runs them on its worker thread."""
import uuid
import xml.etree.ElementTree as ET

from plume_core.dav import CARD, D, OC, XMLNS, DavError, escape, q

XML = {"Content-Type": "application/xml; charset=utf-8"}


def make(client, home, name):
    """A new address book under home; its href."""
    href = home.rstrip("/") + "/" + uuid.uuid4().hex[:12] + "/"
    body = (f'<?xml version="1.0" encoding="utf-8"?><d:mkcol {XMLNS}><d:set><d:prop>'
            '<d:resourcetype><d:collection/><card:addressbook/></d:resourcetype>'
            f'<d:displayname>{escape(name)}</d:displayname></d:prop></d:set></d:mkcol>')
    status, _, _ = client.request("MKCOL", href, body, XML)
    if status not in (200, 201):
        raise DavError(status, "MKCOL addressbook")
    return href


def rename(client, href, name):
    body = (f'<?xml version="1.0" encoding="utf-8"?><d:propertyupdate {XMLNS}><d:set><d:prop>'
            f'<d:displayname>{escape(name)}</d:displayname></d:prop></d:set></d:propertyupdate>')
    status, _, _ = client.request("PROPPATCH", href, body, XML)
    if status not in (200, 207):
        raise DavError(status, "PROPPATCH")


def shares(client, href):
    """[{principal, name, readOnly}] of the book, from <oc:invite>."""
    body = f'<?xml version="1.0" encoding="utf-8"?><d:propfind {XMLNS}><d:prop><oc:invite/></d:prop></d:propfind>'
    status, _, data = client.request("PROPFIND", href, body, dict(XML, Depth="0"))
    if status not in (200, 207) or not data:
        raise DavError(status, "PROPFIND invite")
    root = ET.fromstring(data)
    found = []
    for user in root.iter(q(OC, "user")):
        principal = (user.findtext(q(D, "href")) or "").strip()
        access = user.find(q(OC, "access"))
        read_only = access is not None and access.find(q(OC, "read-write")) is None
        name = (user.findtext(q(OC, "common-name")) or "").strip()
        if principal:
            found.append({"principal": principal.removeprefix("principal:"), "name": name or principal.rstrip("/").split("/")[-1],
                          "readOnly": read_only, "group": "/groups/" in principal})
    return found


def share(client, href, principal, read_only):
    access = "" if read_only else "<oc:read-write/>"
    body = (f'<?xml version="1.0" encoding="utf-8"?><oc:share {XMLNS}><oc:set>'
            f'<d:href>principal:{escape(principal)}</d:href>{access}</oc:set></oc:share>')
    status, _, _ = client.request("POST", href, body, XML)
    if status not in (200, 204):
        raise DavError(status, "share")


def unshare(client, href, principal):
    body = (f'<?xml version="1.0" encoding="utf-8"?><oc:share {XMLNS}><oc:remove>'
            f'<d:href>principal:{escape(principal)}</d:href></oc:remove></oc:share>')
    status, _, _ = client.request("POST", href, body, XML)
    if status not in (200, 204):
        raise DavError(status, "unshare")


__all__ = ["make", "rename", "shares", "share", "unshare", "CARD"]
