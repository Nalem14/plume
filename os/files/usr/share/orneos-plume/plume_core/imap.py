"""IMAP for Plume (imaplib underneath): folders with their roles, headers and previews of the latest
messages, one message in full, flags, moves, append, search, and IDLE for new mail.

The Orneos mailbox is mail.orneos.eu (993, TLS) with the address and the Orneos password; an external one
gives its own server: (host, port, "ssl" | "starttls" | "plain"). PLUME_IMAP=host:port and PLUME_MAIL_PLAIN=1
point the tests at a local server.
"""
import email
import imaplib
import os
import re
import socket
import ssl
import sys
from email import policy
from email.utils import getaddresses, parsedate_to_datetime

HOST, PORT = "mail.orneos.eu", 993
HEADERS = "FROM TO CC REPLY-TO SUBJECT DATE MESSAGE-ID IN-REPLY-TO REFERENCES LIST-UNSUBSCRIBE CONTENT-TYPE"
ROLES = {"\\inbox": "inbox", "\\sent": "sent", "\\drafts": "drafts", "\\trash": "trash", "\\junk": "junk",
         "\\archive": "archive", "\\flagged": "flagged", "\\all": "all"}
NAME_ROLES = {"inbox": "inbox", "sent": "sent", "sent mail": "sent", "sent messages": "sent", "drafts": "drafts",
              "trash": "trash", "deleted messages": "trash", "junk": "junk", "spam": "junk", "archive": "archive",
              "snoozed": "snoozed"}


class MailError(Exception):
    def __init__(self, kind, detail=""):
        super().__init__(f"{kind} {detail}".strip())
        self.kind = kind            # "auth", "offline", "server"


def endpoint():
    """The Orneos IMAP server: (host, port, security)."""
    value = os.environ.get("PLUME_IMAP", "")
    security = "plain" if os.environ.get("PLUME_MAIL_PLAIN") == "1" else "ssl"
    if value:
        host, _, port = value.partition(":")
        return host, int(port or 993), security
    return HOST, PORT, security


# ---- the IMAP grammar Plume needs: atoms, strings, NIL, lists, literals -------------------------------
def tokens(parts):
    """Flatten imaplib's FETCH data (bytes and (bytes, literal) tuples) into one token stream."""
    out = []
    for part in parts:
        if isinstance(part, tuple):
            head, literal = part
            text = head.decode("utf-8", "replace")
            text = re.sub(r"\{\d+\}$", "", text)
            out.extend(_lex(text))
            out.append(literal)
        elif isinstance(part, bytes):
            out.extend(_lex(part.decode("utf-8", "replace")))
    return out


def _lex(text):
    found, i = [], 0
    while i < len(text):
        ch = text[i]
        if ch in " \r\n":
            i += 1
        elif ch in "()":
            found.append(ch)
            i += 1
        elif ch == '"':
            j, buf = i + 1, []
            while j < len(text) and text[j] != '"':
                if text[j] == "\\" and j + 1 < len(text):
                    j += 1
                buf.append(text[j])
                j += 1
            found.append("".join(buf).encode())
            i = j + 1
        else:
            j = i
            while j < len(text) and text[j] not in ' ()"\r\n':
                if text[j] == "[":       # BODY[HEADER.FIELDS (…)] is one atom
                    depth = 0
                    while j < len(text):
                        depth += text[j] == "["
                        depth -= text[j] == "]"
                        j += 1
                        if depth == 0:
                            break
                    continue
                j += 1
            atom = text[i:j]
            found.append(None if atom.upper() == "NIL" else atom)
            i = j
    return found


def parse_lists(stream):
    """Tokens → nested Python lists (one per top-level parenthesised group)."""
    stack, top = [[]], None
    for tok in stream:
        if tok == "(":
            stack.append([])
        elif tok == ")":
            done = stack.pop()
            stack[-1].append(done)
        else:
            stack[-1].append(tok)
    top = stack[0]
    return top


def fetch_items(data):
    """imaplib FETCH data → [{UID: …, FLAGS: […], BODY[…]: bytes, …}] (one dict per message)."""
    items = []
    for group in parse_lists(tokens(data)):
        if not isinstance(group, list):
            continue
        it = iter(group)
        record = {}
        for key in it:
            if isinstance(key, str):
                record[re.sub(r"<\d+>$", "", key.upper())] = next(it, None)
        items.append(record)
    return items


def _children(node):
    """The parts of a multipart node: its leading lists (then come the subtype and its parameters)."""
    out = []
    for item in node:
        if not isinstance(item, list):
            break
        out.append(item)
    return out


def _text(value):
    return value.decode("utf-8", "replace").lower() if isinstance(value, bytes) else str(value or "").lower()


def _disposition(node):
    """"attachment", "inline" or "" for a leaf (its place differs between text and other parts)."""
    for item in node[7:]:
        if isinstance(item, list) and item and isinstance(item[0], bytes) and item[0].lower() in (b"attachment", b"inline"):
            return item[0].decode().lower()
    return ""


def text_part(structure, prefix=""):
    """(part number, encoding, charset, subtype) of the first text/plain (else text/html) body part."""
    best = None

    def walk(node, number):
        nonlocal best
        if not isinstance(node, list) or not node:
            return
        if isinstance(node[0], list):
            for index, child in enumerate(_children(node), 1):
                walk(child, f"{number}.{index}" if number else str(index))
            return
        kind, sub = _text(node[0]), _text(node[1])
        params = node[2] if len(node) > 2 and isinstance(node[2], list) else []
        charset = "utf-8"
        for i in range(0, len(params) - 1, 2):
            if _text(params[i]) == "charset" and isinstance(params[i + 1], bytes):
                charset = params[i + 1].decode()
        encoding = _text(node[5]) if len(node) > 5 and node[5] else "7bit"
        if kind == "text" and sub in ("plain", "html") and _disposition(node) != "attachment":
            if best is None or (best[3] == "html" and sub == "plain"):
                best = (number or "1", encoding, charset, sub)

    walk(structure, prefix)
    return best


def has_attachments(structure):
    found = False

    def walk(node):
        nonlocal found
        if not isinstance(node, list) or not node:
            return
        if isinstance(node[0], list):
            for child in _children(node):
                walk(child)
            return
        kind = _text(node[0])
        if _disposition(node) == "attachment" or kind in ("application", "audio", "video") \
                or (kind == "image" and len(node) > 3 and node[3] is None):
            found = True

    walk(structure)
    return found


def has_calendar(structure):
    """True when a part is an invitation (text/calendar or application/ics): it goes to the calendar."""
    found = False

    def walk(node):
        nonlocal found
        if not isinstance(node, list) or not node:
            return
        if isinstance(node[0], list):
            for child in _children(node):
                walk(child)
            return
        if (_text(node[0]), _text(node[1])) in (("text", "calendar"), ("application", "ics")):
            found = True

    walk(structure)
    return found


def decode_preview(raw, encoding, charset, subtype):
    if raw is None:
        return ""
    data = raw if isinstance(raw, bytes) else str(raw).encode()
    try:
        if encoding == "base64":
            import base64
            data = base64.b64decode(data[: len(data) - len(data) % 4] or b"", validate=False)
        elif encoding == "quoted-printable":
            import quopri
            data = quopri.decodestring(data)
    except Exception:
        pass
    text = data.decode(charset if charset else "utf-8", "replace")
    if subtype == "html":
        text = re.sub(r"(?is)<(style|script|head)[^>]*>.*?</\1>", " ", text)
        text = re.sub(r"<[^>]+>", " ", text)
        import html as html_lib
        text = html_lib.unescape(text)
    lines = [l for l in text.splitlines() if l.strip() and not l.lstrip().startswith(">")]
    return re.sub(r"\s+", " ", " ".join(lines)).strip()[:220]


TAGS = ["$label1", "$label2", "$label3", "$label4", "$label5"]


def tags_of(flags):
    """The tags among lowercase flags, as stored: "$label1 $label4"."""
    return " ".join(t for t in TAGS if t in flags)


def addresses(value):
    return [{"name": n, "email": a.lower()} for n, a in getaddresses([value or ""]) if a]


class Connection:
    """One logged-in IMAP session. Not thread-safe: each worker owns its own."""

    def __init__(self, user, password, timeout=30, server=None, xoauth2=False):
        """xoauth2: password is an OAuth access token (Google, Microsoft)."""
        host, port, security = server or endpoint()
        try:
            if security == "ssl":
                self.imap = imaplib.IMAP4_SSL(host, port, ssl_context=ssl.create_default_context(), timeout=timeout)
            else:
                self.imap = imaplib.IMAP4(host, port, timeout=timeout)
                if security == "starttls":
                    self.imap.starttls(ssl_context=ssl.create_default_context())
        except (OSError, socket.timeout, ssl.SSLError) as error:
            raise MailError("offline", type(error).__name__) from error
        except imaplib.IMAP4.error as error:
            raise MailError("server", "STARTTLS") from error
        try:
            if xoauth2:
                said = []

                def respond(challenge):
                    if said:                    # the server explained a refusal: end the exchange
                        said.append(challenge)
                        return b""
                    said.append(1)
                    return f"user={user}\x01auth=Bearer {password}\x01\x01".encode()
                try:
                    self.imap.authenticate("XOAUTH2", respond)
                except imaplib.IMAP4.error as error:
                    # why, in plume.log (Google says it in JSON: status, scope); never the token
                    why = said[1].decode(errors="replace") if len(said) > 1 and isinstance(said[1], bytes) else ""
                    print("plume: XOAUTH2 refused by", host, "-", error, why, file=sys.stderr)
                    raise
            else:
                self.imap.login(user, password)
        except imaplib.IMAP4.error as error:
            raise MailError("auth") from error
        self.caps = {c.upper() for c in self.imap.capabilities}
        self.selected = None

    def close(self):
        try:
            self.imap.logout()
        except Exception:
            pass

    def _ok(self, result, what):
        typ, data = result
        if typ != "OK":
            raise MailError("server", f"{what}: {data!r}"[:200])
        return data

    # ---- folders ----------------------------------------------------------------------------------
    def folders(self):
        """[{path, name, role, delimiter, noselect}] with roles from SPECIAL-USE, else from the name."""
        data = self._ok(self.imap.list(), "LIST")
        out = []
        for line in data:
            if not line:
                continue
            text = line.decode("utf-8", "replace") if isinstance(line, bytes) else line[0].decode()
            m = re.match(r'\((?P<flags>[^)]*)\) (?P<delim>"[^"]*"|NIL) (?P<name>.+)$', text)
            if not m:
                continue
            flags = {f.lower() for f in m.group("flags").split()}
            delim = m.group("delim").strip('"') if m.group("delim") != "NIL" else ""
            path = m.group("name").strip()
            if path.startswith('"'):
                path = path[1:-1].replace('\\"', '"').replace("\\\\", "\\")
            name = imap_utf7_decode(path)
            leaf = name.split(delim)[-1] if delim else name
            role = next((ROLES[f] for f in flags if f in ROLES), None) or NAME_ROLES.get(name.lower()) \
                or ("inbox" if name.upper() == "INBOX" else "")
            out.append({"path": path, "name": leaf, "full": name, "role": role, "delimiter": delim,
                        "noselect": "\\noselect" in flags or "\\nonexistent" in flags})
        # Gmail has no Archive: archiving takes the inbox label off, the message stays in "All Mail"
        if not any(f["role"] == "archive" for f in out):
            for f in out:
                if f["role"] == "all":
                    f["role"] = "archive"
                    break
        return out

    def status(self, path):
        data = self._ok(self.imap.status(quote(path), "(MESSAGES UNSEEN UIDNEXT UIDVALIDITY)"), "STATUS")
        text = data[0].decode() if isinstance(data[0], bytes) else str(data[0])
        values = dict(re.findall(r"(MESSAGES|UNSEEN|UIDNEXT|UIDVALIDITY) (\d+)", text))
        return {k.lower(): int(v) for k, v in values.items()}

    def select(self, path, readonly=False, refresh=True):
        """refresh: an open folder asks the server what changed (not needed to read messages by UID)."""
        if self.selected != (path, readonly):
            self._ok(self.imap.select(quote(path), readonly=readonly), "SELECT")
            self.selected = (path, readonly)
        elif refresh:
            # Already open: NOOP lets the server bring its view up to date (new mail, expunges)
            self._ok(self.imap.noop(), "NOOP")

    # ---- messages ---------------------------------------------------------------------------------
    def uids(self, criteria="ALL"):
        data = self._ok(self.imap.uid("SEARCH", None, criteria), "SEARCH")
        return [int(x) for x in (data[0] or b"").split()]

    def headers(self, uids):
        """Header records for these UIDs: addresses, subject, date, flags, preview, attachment."""
        if not uids:
            return []
        preview = "PREVIEW" in self.caps
        items = f"(UID FLAGS RFC822.SIZE BODYSTRUCTURE BODY.PEEK[HEADER.FIELDS ({HEADERS})]{' PREVIEW' if preview else ''})"
        out = []
        for chunk in range(0, len(uids), 200):
            ids = ",".join(str(u) for u in uids[chunk:chunk + 200])
            data = self._ok(self.imap.uid("FETCH", ids, items), "FETCH headers")
            records = fetch_items(data)
            wanted = {}
            for rec in records:
                head = next((v for k, v in rec.items() if k.startswith("BODY[HEADER")), b"") or b""
                msg = email.message_from_bytes(head if isinstance(head, bytes) else head.encode(), policy=policy.default)
                structure = rec.get("BODYSTRUCTURE")
                flags = [f.lower() for f in (rec.get("FLAGS") or []) if isinstance(f, str)]
                try:
                    stamp = int(parsedate_to_datetime(str(msg.get("Date", ""))).timestamp())
                except (TypeError, ValueError, IndexError):
                    stamp = 0
                sender = addresses(str(msg.get("From", "")))
                item = {
                    "uid": int(rec.get("UID") or 0),
                    "from": sender[0] if sender else {"name": "", "email": ""},
                    "to": addresses(str(msg.get("To", ""))),
                    "cc": addresses(str(msg.get("Cc", ""))),
                    "subject": str(msg.get("Subject", "") or "").strip(),
                    "date": stamp,
                    "message_id": str(msg.get("Message-ID", "") or "").strip(),
                    "in_reply_to": str(msg.get("In-Reply-To", "") or "").strip(),
                    "references": " ".join(str(msg.get("References", "") or "").split()),
                    "unsubscribe": str(msg.get("List-Unsubscribe", "") or "").strip(),
                    "seen": "\\seen" in flags, "flagged": "\\flagged" in flags, "answered": "\\answered" in flags,
                    "tags": tags_of(flags),
                    "size": int(rec.get("RFC822.SIZE") or 0),
                    "attachments": has_attachments(structure) if structure else False,
                    "calendar": has_calendar(structure) if structure else False,
                    "preview": "",
                }
                if preview and rec.get("PREVIEW"):
                    value = rec["PREVIEW"]
                    item["preview"] = (value.decode("utf-8", "replace") if isinstance(value, bytes) else str(value))[:220]
                elif structure:
                    part = text_part(structure)
                    if part:
                        wanted[item["uid"]] = part
                out.append(item)
            if wanted:
                self._previews(out, wanted)
        return out

    def _previews(self, items, wanted):
        """Without PREVIEW: the first bytes of each message's text part, decoded."""
        by_part = {}
        for uid, part in wanted.items():
            by_part.setdefault(part, []).append(uid)
        index = {i["uid"]: i for i in items}
        for (number, encoding, charset, sub), uids in by_part.items():
            ids = ",".join(str(u) for u in uids)
            try:
                data = self._ok(self.imap.uid("FETCH", ids, f"(UID BODY.PEEK[{number}]<0.1200>)"), "FETCH preview")
            except MailError:
                continue
            for rec in fetch_items(data):
                raw = next((v for k, v in rec.items() if k.startswith("BODY[")), None)
                uid = int(rec.get("UID") or 0)
                if uid in index:
                    index[uid]["preview"] = decode_preview(raw, encoding, charset, sub)

    def message(self, uid):
        """The whole message (bytes), without marking it read."""
        data = self._ok(self.imap.uid("FETCH", str(uid), "(UID BODY.PEEK[])"), "FETCH body")
        for rec in fetch_items(data):
            raw = rec.get("BODY[]")
            if raw is not None:
                return raw if isinstance(raw, bytes) else str(raw).encode()
        return None

    def messages(self, uids):
        """{uid: whole message (bytes)} for these UIDs of the selected folder, in one command (a long conversation
        was a command per message), without marking them read."""
        out = {}
        for attempt in range(2):
            wanted = [u for u in uids if u not in out]
            if not wanted:
                break
            if attempt:
                # arrived since this session opened the folder: the server shows it only once told of it
                self._ok(self.imap.noop(), "NOOP")
            data = self._ok(self.imap.uid("FETCH", ",".join(map(str, wanted)), "(UID BODY.PEEK[])"), "FETCH bodies")
            for rec in fetch_items(data):
                raw = rec.get("BODY[]")
                if raw is not None and rec.get("UID"):
                    out[int(rec["UID"])] = raw if isinstance(raw, bytes) else str(raw).encode()
        return out

    def flag_states(self, uids):
        """{uid: {lowercase flags}} for messages already cached (to follow reads made elsewhere)."""
        out = {}
        for chunk in range(0, len(uids), 500):
            ids = ",".join(map(str, uids[chunk:chunk + 500]))
            data = self._ok(self.imap.uid("FETCH", ids, "(UID FLAGS)"), "FETCH flags")
            for rec in fetch_items(data):
                out[int(rec.get("UID") or 0)] = {f.lower() for f in (rec.get("FLAGS") or []) if isinstance(f, str)}
        return out

    def flags(self, uids, flag, on):
        if uids:
            self._ok(self.imap.uid("STORE", ",".join(map(str, uids)), "+FLAGS.SILENT" if on else "-FLAGS.SILENT",
                                   f"({flag})"), "STORE")

    def move(self, uids, target):
        if not uids:
            return
        ids = ",".join(map(str, uids))
        if "MOVE" in self.caps:
            self._ok(self.imap.uid("MOVE", ids, quote(target)), "MOVE")
        else:
            self._ok(self.imap.uid("COPY", ids, quote(target)), "COPY")
            self.flags(uids, "\\Deleted", True)
            self.imap.expunge()

    def delete(self, uids):
        if uids:
            self.flags(uids, "\\Deleted", True)
            if "UIDPLUS" in self.caps:
                self.imap.uid("EXPUNGE", ",".join(map(str, uids)))
            else:
                self.imap.expunge()

    def append(self, path, raw, flags="(\\Seen)"):
        """Store a message (sent copy, draft). Returns its UID when the server says (UIDPLUS)."""
        typ, data = self.imap.append(quote(path), flags, imaplib.Time2Internaldate(__import__("time").time()), raw)
        if typ != "OK":
            raise MailError("server", "APPEND")
        m = re.search(rb"APPENDUID \d+ (\d+)", data[0] or b"") if data and isinstance(data[0], bytes) else None
        return int(m.group(1)) if m else 0

    def create(self, path):
        self.imap.create(quote(path))
        try:
            self.imap.subscribe(quote(path))
        except imaplib.IMAP4.error:
            pass

    def make_folder(self, path):
        """A new folder (a refusal says why: it exists, the name is not allowed)."""
        self._ok(self.imap.create(quote(path)), "CREATE")
        try:
            self.imap.subscribe(quote(path))
        except imaplib.IMAP4.error:
            pass

    def rename_folder(self, path, new_path):
        self._ok(self.imap.rename(quote(path), quote(new_path)), "RENAME")
        try:
            self.imap.unsubscribe(quote(path))
            self.imap.subscribe(quote(new_path))
        except imaplib.IMAP4.error:
            pass

    def delete_folder(self, path):
        try:
            self.imap.unsubscribe(quote(path))
        except imaplib.IMAP4.error:
            pass
        self._ok(self.imap.delete(quote(path)), "DELETE")

    def search(self, text):
        """UIDs of the selected folder whose headers or body contain text (server-side)."""
        return self.search_criteria([("TEXT", text)])

    def search_criteria(self, criteria):
        """UIDs of the selected folder matching every criterion: [("TEXT", "devis"), ("FROM", "iris"),
        ("UNSEEN", None), ("SINCE", "01-Nov-2026")…]. Text in ASCII is quoted; the first one that is not goes as
        the one literal imaplib can send (more would need several, which it cannot: they are left out)."""
        args, literal, literal_key = [], None, ""
        for key, value in criteria:
            if value is None:
                args.append(key)
            elif all(32 <= ord(ch) < 127 for ch in value):
                args += [key, quote(value)]
            elif literal is None:
                literal, literal_key = value.encode("utf-8"), key
        if literal is not None:
            # imaplib sends its literal after the last argument: its criterion comes last
            self.imap.literal = literal
            data = self._ok(self.imap.uid("SEARCH", "CHARSET", "UTF-8", *args, literal_key), "SEARCH")
        else:
            data = self._ok(self.imap.uid("SEARCH", *(args or ["ALL"])), "SEARCH")
        return [int(x) for x in (data[0] or b"").split()]

    def idle(self, seconds=600):
        """Wait for the server to report a change in the selected folder (True), or the timeout (False)."""
        try:
            with self.imap.idle(duration=seconds) as events:
                for kind, _ in events:
                    if kind in ("EXISTS", "EXPUNGE", "FETCH", "RECENT"):
                        return True
        except (imaplib.IMAP4.error, OSError) as error:
            raise MailError("offline", type(error).__name__) from error
        return False


def quote(path):
    return '"' + path.replace("\\", "\\\\").replace('"', '\\"') + '"'


def imap_utf7_decode(value):
    """Folder names come in IMAP's modified UTF-7 ("&AOk-" is "é")."""
    import base64

    def repl(m):
        chunk = m.group(1)
        if chunk == "":
            return "&"
        data = chunk.replace(",", "/")
        data += "=" * (-len(data) % 4)
        return base64.b64decode(data).decode("utf-16-be", "replace")
    return re.sub(r"&([^-]*)-", repl, value)


def imap_utf7_encode(value):
    import base64
    out, buf = [], []

    def flush():
        if buf:
            data = base64.b64encode("".join(buf).encode("utf-16-be")).decode().rstrip("=").replace("/", ",")
            out.append("&" + data + "-")
            buf.clear()
    for ch in value:
        if 0x20 <= ord(ch) <= 0x7E:
            flush()
            out.append("&-" if ch == "&" else ch)
        else:
            buf.append(ch)
    flush()
    return "".join(out)
