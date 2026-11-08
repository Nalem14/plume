"""Messages for Plume: read one (safe HTML, plain text, attachments) and write one (reply, forward, send).

Reading never runs anything from the message: the HTML gets a Content-Security-Policy that forbids
scripts and every remote load (images, fonts, styles) until the person allows images for it. Remote
pictures are mostly trackers; how many were blocked is shown. Inline pictures (cid:) are put in once each,
by their content, wherever the text shows them.
"""
import base64
import hashlib
import html
import mimetypes
import re
import struct
import urllib.parse
import urllib.request
from datetime import datetime
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import formataddr, format_datetime, getaddresses, make_msgid, parsedate_to_datetime
from pathlib import Path

CSP_BLOCKED = "default-src 'none'; img-src data: cid:; style-src 'unsafe-inline'; font-src data:; media-src data:"
CSP_IMAGES = "default-src 'none'; img-src data: cid: https: http:; style-src 'unsafe-inline' https:; font-src data: https:; media-src data:"
REMOTE = re.compile(r"""(?i)(?:\bsrc\s*=\s*["']?\s*https?:|\bbackground\s*=\s*["']?\s*https?:|url\(\s*["']?\s*https?:)""")
URL = re.compile(r"(https?://[^\s<>\"')\]]+)")


def parse(raw):
    return BytesParser(policy=policy.default).parsebytes(raw)


def _addresses(value):
    return [{"name": n, "email": a} for n, a in getaddresses([str(value or "")]) if a]


def _unsubscribe(msg):
    """(mailto or https link, one-click POST allowed) from List-Unsubscribe."""
    value = str(msg.get("List-Unsubscribe", "") or "")
    links = re.findall(r"<([^>]+)>", value)
    https = next((l for l in links if l.startswith("https://")), "")
    mailto = next((l for l in links if l.startswith("mailto:")), "")
    one_click = "One-Click" in str(msg.get("List-Unsubscribe-Post", "") or "")
    return {"https": https, "mailto": mailto, "oneClick": bool(https and one_click)}


def _text_of(part):
    try:
        return part.get_content()
    except (LookupError, UnicodeDecodeError, AssertionError):
        payload = part.get_payload(decode=True) or b""
        return payload.decode("utf-8", "replace")


def _base64_of(part):
    """A part's content in base64, without decoding it when it already is (pictures of several MB)."""
    if str(part.get("Content-Transfer-Encoding", "")).strip().lower() == "base64":
        payload = part.get_payload(decode=False)
        if isinstance(payload, str):
            return "".join(payload.split())
    return base64.b64encode(part.get_payload(decode=True) or b"").decode()


def _size_of(part):
    if str(part.get("Content-Transfer-Encoding", "")).strip().lower() == "base64":
        payload = part.get_payload(decode=False)
        if isinstance(payload, str):
            return (len(payload) - payload.count("\n") - payload.count("\r")) * 3 // 4
    return len(part.get_payload(decode=True) or b"")


def _dims(head):
    """Width and height of a PNG, GIF, WebP or JPEG from its first bytes; None when unknown (a JPEG that
    says how to turn it is shown turned: its size is not the one written)."""
    if head[:8] == b"\x89PNG\r\n\x1a\n" and len(head) >= 24:
        return struct.unpack(">II", head[16:24])
    if head[:6] in (b"GIF87a", b"GIF89a") and len(head) >= 10:
        return struct.unpack("<HH", head[6:10])
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP" and len(head) >= 30:
        kind = head[12:16]
        if kind == b"VP8 ":
            w, h = struct.unpack("<HH", head[26:30])
            return w & 0x3FFF, h & 0x3FFF
        if kind == b"VP8L":
            b = head[21:25]
            return 1 + (((b[1] & 0x3F) << 8) | b[0]), 1 + (((b[3] & 0x0F) << 10) | (b[2] << 2) | ((b[1] & 0xC0) >> 6))
        if kind == b"VP8X":
            return 1 + int.from_bytes(head[24:27], "little"), 1 + int.from_bytes(head[27:30], "little")
        return None
    if head[:2] != b"\xff\xd8":
        return None
    i = 2
    while i + 9 < len(head):
        if head[i] != 0xFF:
            return None
        marker = head[i + 1]
        if marker == 0xFF:
            i += 1
            continue
        if marker == 0x01 or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        length = struct.unpack(">H", head[i + 2:i + 4])[0]
        if marker == 0xE1 and head[i + 4:i + 8] == b"Exif":
            return None
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            h, w = struct.unpack(">HH", head[i + 5:i + 9])
            return w, h
        i += 2 + length
    return None


def _cids(msg):
    """Content-ID → (key, data: URI, size) for the inline pictures of a message. The key names the picture by
    its content: the same picture sent again (each reply of an Outlook thread carries them all) is one."""
    found = {}
    for part in msg.walk():
        cid = str(part.get("Content-ID", "") or "").strip("<> ")
        if cid and part.get_content_maintype() == "image":
            data = _base64_of(part)
            key = "p" + hashlib.blake2s(data.encode(), digest_size=8).hexdigest()
            try:
                size = _dims(base64.b64decode(data[:131072]))
            except ValueError:
                size = None
            found[cid] = (key, f"data:{part.get_content_type()};base64,{data}", size if size and all(size) else None)
    return found


CID_REF = re.compile(r"""(?i)\bcid:([^"'\s)>]+)""")
CID_IMG = re.compile(r"""(?i)(<img\b[^>]*?(?<![\w-])src\s*=\s*)(["']?)cid:([^"'\s>]+)\2""")
KEYED_IMG = re.compile(r'src="data:image/svg\+xml,[^"]*" data-p="(p[0-9a-f]{16})"')


def _picture_style(pictures, root):
    """Each picture once in the page (a custom property of the root), painted behind the <img> that has its
    key: the <img> itself shows an empty picture of the same size, so its width, height and proportions
    behave as usual. A thread quoting its pictures in every message stays one copy of each."""
    if not pictures:
        return ""
    if root:
        return ":root{" + "".join(f'--{key}:url("{uri}");' for key, uri in pictures.items()) + "}"
    return "".join(f'img[data-p="{key}"]{{background:var(--{key}) 0 0/100% 100% no-repeat}}' for key in pictures)


def _inline(body, pictures):
    """The pictures put back in the HTML (for the editor: a reply or a forward keeps them)."""
    return KEYED_IMG.sub(lambda m: f'src="{pictures[m.group(1)]}"' if m.group(1) in pictures else m.group(0), body)


def _sanitize(body):
    body = re.sub(r"(?is)<(script|iframe|object|embed|applet|base|frameset|frame)\b.*?(</\1>|/?>)", "", body)
    body = re.sub(r"(?is)<meta[^>]+http-equiv\s*=\s*[\"']?(refresh|content-security-policy)[^>]*>", "", body)
    body = re.sub(r"(?is)<link\b[^>]*>", "", body)
    body = re.sub(r"(?i)\son[a-z]+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", "", body)
    body = re.sub(r"(?i)(href|src)\s*=\s*([\"'])\s*(javascript|vbscript):[^\"']*\2", r'\1="#"', body)
    return body


def _plain_to_html(text):
    """Plain text as readable HTML: links clickable, quoted lines set apart, paragraphs kept."""
    lines = []
    for line in html.escape(text).split("\n"):
        depth = len(re.match(r"^(&gt;\s?)*", line).group(0).replace(" ", "")) // 4
        content = re.sub(r"^(&gt;\s?)+", "", line)
        content = URL.sub(r'<a href="\1">\1</a>', content)
        lines.append(f'<div class="q{min(depth, 3)}">{content or "&nbsp;"}</div>')
    return '<div class="plain">' + "".join(lines) + "</div>"


BASE_STYLE = """
html{color-scheme:light}
body{margin:0;padding:20px 28px 40px;font:15px/1.6 'Schibsted Grotesk',system-ui,sans-serif;color:#0F2440;background:#FFFFFF;
     overflow-wrap:anywhere;-webkit-text-size-adjust:100%}
img{max-width:100%;height:auto}
a{color:#002FA7}
a[href]{cursor:pointer}
table{max-width:100%}
blockquote{margin:8px 0;padding-left:14px;border-left:3px solid #DCE3F7;color:#45556E}
pre{white-space:pre-wrap}
.plain{font:15px/1.6 'Schibsted Grotesk',system-ui,sans-serif;white-space:pre-wrap}
.q1,.q2,.q3{color:#45556E;padding-left:14px;border-left:3px solid #DCE3F7}
.q2{border-left-color:#C9D3EC}.q3{border-left-color:#9AA8BF}
"""
DARK_PLAIN = """
html{color-scheme:dark}
body{color:#DDE3EE;background:#101D33}
a{color:#9AABFF}
.q1,.q2,.q3,blockquote{color:#9AA8BF;border-left-color:#2A3D6B}
"""


def read(raw, images=False, dark=False, whole=True):
    """Everything the reader shows. dark: plain-text mails follow the theme; HTML ones stay on paper.
    whole=False: a message of a conversation (its fragment and pictures, no page of its own, nothing to edit).
    The pictures stay cid: references, named by their content ("pictures": key → data: URI)."""
    msg = parse(raw)
    html_part = msg.get_body(preferencelist=("html",))
    text_part = msg.get_body(preferencelist=("plain",))
    text = _text_of(text_part) if text_part is not None else ""
    remote = 0
    pictures, shown_cids = {}, set()
    if html_part is not None:
        # everything read from the HTML before its pictures are in (megabytes of base64 to search otherwise)
        body = _sanitize(_text_of(html_part))
        remote = len(REMOTE.findall(body))
        if not text:
            text = re.sub(r"\s+\n", "\n", html.unescape(re.sub(r"(?s)<[^>]+>", " ", re.sub(r"(?is)<(style|head)\b.*?</\1>", "", body))))
        found_cids = _cids(msg)

        def keyed(match):
            cid = match.group(3)
            if cid not in found_cids or not found_cids[cid][2]:
                return match.group(0)
            key, uri, (w, h) = found_cids[cid]
            pictures[key] = uri
            shown_cids.add(cid)
            empty = f"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='{w}' height='{h}'/%3E"
            return f'{match.group(1)}"{empty}" data-p="{key}"'

        def inlined(match):         # elsewhere (a background, a picture of unknown size): the picture itself
            cid = match.group(1)
            if cid not in found_cids:
                return match.group(0)
            shown_cids.add(cid)
            return found_cids[cid][1]
        body = CID_REF.sub(inlined, CID_IMG.sub(keyed, body))
        style = BASE_STYLE
        is_html = True
    else:
        body = _plain_to_html(text)
        style = BASE_STYLE + (DARK_PLAIN if dark else "")
        is_html = False
    csp = CSP_IMAGES if images else CSP_BLOCKED
    shown = body
    # the quoted history folds under « ··· », as in a conversation (not in a forward: the quote is the message)
    found = QUOTED.search(body)
    if found and not re.match(r"(?i)^\s*(tr|fwd?|wg)\s*:", str(msg.get("Subject", "") or "")):
        at = body.rfind("<", 0, found.start())
        label = '<label class="more" for="q">···</label>'
        shown = ('<input type="checkbox" id="q"><div class="root">'
                 + (body[:at] + label + body[at:] if at >= 0 else body + label) + "</div>")
        style += FOLD_STYLE + (FOLD_DARK if dark and not is_html else "")
    page = ""
    if whole:
        style += _picture_style(pictures, True) + _picture_style(pictures, False)
        page = (f'<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="{csp}">'
                f'<meta name="viewport" content="width=device-width"><style>{style}</style>{shown}')
    attachments = []
    for index, part in enumerate(_files(msg)):
        cid = str(part.get("Content-ID", "") or "").strip("<> ")
        # a picture of the text (a signature, a screenshot pasted in) is not an attachment, even named
        if part.get_content_maintype() == "image" and cid and (cid in shown_cids or not part.get_filename()):
            continue
        attachments.append({"index": index, "name": _file_name(part, index), "type": part.get_content_type(), "size": _size_of(part)})
    try:
        date = parsedate_to_datetime(str(msg.get("Date", ""))).astimezone()
    except (TypeError, ValueError, IndexError):
        date = None
    return {
        "subject": str(msg.get("Subject", "") or ""),
        "from": (_addresses(msg.get("From")) or [{"name": "", "email": ""}])[0],
        "to": _addresses(msg.get("To")),
        "cc": _addresses(msg.get("Cc")),
        "bcc": _addresses(msg.get("Bcc")),          # only in my own copies (Sent, Drafts)
        "replyTo": _addresses(msg.get("Reply-To")),
        "date": date.isoformat() if date else "",
        "mid": str(msg.get("Message-ID", "") or "").strip(),
        "references": " ".join(str(msg.get("References", "") or "").split()),
        "inReplyTo": str(msg.get("In-Reply-To", "") or "").strip(),
        "html": page,
        "fragment": body,
        "pictures": pictures,
        "isHtml": is_html,
        "source": editable(_inline(body, pictures)) if is_html and whole else "",
        "text": text.strip(),
        "remote": remote,
        "attachments": attachments,
        "unsubscribe": _unsubscribe(msg),
        "calendar": calendar_of(msg),
        "warning": suspicious(msg),
    }


def suspicious(msg):
    """Why a sender may not be who they say: "dmarc" (their domain's servers did not send it, a mail server on
    the way said so), "name" (the name shown is another address than the real one, « service@banque.fr
    <x@ailleurs.ru> »). "" otherwise."""
    results = " ".join(str(v) for v in msg.get_all("Authentication-Results", []) or []).lower()
    if re.search(r"\bdmarc=fail\b", results):
        return "dmarc"
    sender = (_addresses(msg.get("From")) or [{"name": "", "email": ""}])[0]
    shown = re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", sender["name"] or "")
    if shown and all(a.lower() != sender["email"].lower() for a in shown):
        return "name"
    return ""


# ---- a conversation: every message of a thread on one page --------------------------------------------
# Without JavaScript: <details> folds a message, a checkbox inside each message unfolds its quotes, and each
# body sits in its own declarative shadow root, so the styles of one message never reach another.
# Links to https://plume.invalid/ (reply, attachment) are caught by the reader and never leave the app.
# An open message keeps only its avatar in <summary> (a click there folds it): its heading (sender, To, Cc,
# Reply-To) sits outside, so the mouse selects it instead of folding the message. People are mailto: links,
# which the reader turns into a menu (write, copy the address).
ACTION = "https://plume.invalid/"      # .invalid never resolves (RFC 2606)
FILES_SHOWN = 4                         # past this, a message's other files wait behind « +N autres »
CONV_STYLE = """
html{color-scheme:light}
body{margin:0;padding:12px 16px 32px;font:15px/1.5 'Schibsted Grotesk',system-ui,sans-serif;color:#0F2440;background:#FFFFFF}
details.msg{position:relative;border:1px solid #E1E5EE;border-radius:12px;margin:0 0 12px;background:#FFFFFF}
details.msg>summary{list-style:none;cursor:pointer;display:flex;gap:12px;align-items:center;padding:12px 16px;border-radius:12px}
details.msg>summary::-webkit-details-marker{display:none}
details.msg>summary:hover{background:#F5F6F9}
details.msg[open]>summary{position:absolute;left:0;top:0;border-radius:12px 0 12px 0}
details.msg[open]>summary:hover{background:none}
details.msg[open]>summary:hover .av{box-shadow:0 0 0 3px #DCE3F7}
details.msg[open]>summary .who{display:none}
.head{padding:12px 16px 4px 64px;min-height:40px;box-sizing:border-box}
.head .line{min-height:20px}
.head .line a.person{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.rcpt{color:#5B6B82;font-size:14px;margin-top:2px}
.rcpt .lab{margin-right:4px}
a.person{color:inherit;text-decoration:none;cursor:pointer;-webkit-user-drag:none}
a.person:hover .pn{text-decoration:underline}
.rcpt .pn{color:#0F2440}
a[href]{cursor:pointer}
.av{flex:none;width:36px;height:36px;border-radius:18px;background:#DCE3F7;color:#002FA7;font-weight:600;font-size:13px;
    display:flex;align-items:center;justify-content:center}
.mine .av{background:#FDF1D6;color:#7A5200}
.who{flex:1;min-width:0}
.line{display:flex;gap:8px;align-items:baseline}
.name{font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.addr{color:#5B6B82;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.when{margin-left:auto;color:#5B6B82;font:12px 'JetBrains Mono',monospace;white-space:nowrap}
.sub{color:#5B6B82;font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.unread .name::before{content:"";display:inline-block;width:8px;height:8px;border-radius:4px;background:#002FA7;margin-right:7px;vertical-align:1px}
.files{display:flex;flex-wrap:wrap;gap:8px;padding:2px 16px 10px 64px}
.file{display:inline-flex;gap:8px;align-items:center;padding:6px 10px;border:1px solid #E1E5EE;border-radius:8px;color:#0F2440;
      text-decoration:none;font-size:13px}
.file:hover{background:#F5F6F9}
.file b{font:700 10px 'Schibsted Grotesk',sans-serif;color:#fff;background:#002FA7;border-radius:4px;padding:3px 5px}
.files .all,.files .all:checked+.more-files,.files .all:not(:checked)~.rest{display:none}
.files .rest{display:contents}
.more-files{cursor:pointer;color:#5B6B82;font-weight:600}
.body{margin:0 16px 0 64px;padding-bottom:6px}
.paper{background:#FFFFFF;border-radius:8px}
.acts{display:flex;gap:6px;padding:4px 16px 14px 64px}
.acts a{color:#0F2440;text-decoration:none;font-size:13px;font-weight:500;padding:5px 10px;border:1px solid #E1E5EE;border-radius:6px}
.acts a:hover{background:#F5F6F9}
"""
CONV_DARK = """
html{color-scheme:dark}
body{color:#E8ECF3;background:#101D33}
details.msg{border-color:#1E2E4A;background:#101D33}
details.msg>summary:hover,.file:hover,.acts a:hover{background:#16233A}
details.msg[open]>summary:hover{background:none}
details.msg[open]>summary:hover .av{box-shadow:0 0 0 3px #2A3D6B}
.rcpt{color:#9AA8BF}
.rcpt .pn{color:#E8ECF3}
.av{background:#1B2C55;color:#C3CEFF}
.mine .av{background:#3A2C0C;color:#F5C04A}
.addr,.when,.sub{color:#9AA8BF}
.unread .name::before{background:#7D93FF}
.file,.acts a{color:#E8ECF3;border-color:#1E2E4A}
.more-files{color:#9AA8BF}
.paper{padding:8px 14px;margin-bottom:8px}
"""
SHADOW_STYLE = """
:host{display:block;font:15px/1.6 'Schibsted Grotesk',system-ui,sans-serif;color:#0F2440;overflow-wrap:anywhere}
.root{padding:4px 0}
img{max-width:100%;height:auto}
a{color:#002FA7}
a[href]{cursor:pointer}
table{max-width:100%}
blockquote{margin:8px 0;padding-left:14px;border-left:3px solid #DCE3F7;color:#45556E}
pre{white-space:pre-wrap}
.plain{white-space:pre-wrap}
.q1,.q2,.q3{color:#45556E;padding-left:14px;border-left:3px solid #DCE3F7}
.q2{border-left-color:#C9D3EC}.q3{border-left-color:#9AA8BF}
#q{display:none}
.more{display:table;margin:10px 0 6px;padding:0 8px;border-radius:9px;background:#E9ECF2;color:#45556E;cursor:pointer;
      font:700 13px/18px sans-serif;letter-spacing:1px}
#q:not(:checked)~.root :is(blockquote[type=cite],.gmail_quote,.moz-cite-prefix,#divRplyFwdMsg,#appendonsend,
  .yahoo_quoted,.q1,.q2,.q3,.orneos-quote),
#q:not(:checked)~.root #divRplyFwdMsg~*{display:none}
"""
SHADOW_DARK_PLAIN = """
:host{color:#DDE3EE}
a{color:#9AABFF}
.q1,.q2,.q3,blockquote{color:#9AA8BF;border-left-color:#2A3D6B}
.more{background:#1A2840;color:#9AA8BF}
"""
FOLD_STYLE = """
#q{display:none}
.more{display:table;margin:10px 0 6px;padding:0 8px;border-radius:9px;background:#E9ECF2;color:#45556E;cursor:pointer;
      font:700 13px/18px sans-serif;letter-spacing:1px}
#q:not(:checked)~.root :is(blockquote[type=cite],.gmail_quote,.moz-cite-prefix,#divRplyFwdMsg,#appendonsend,
  .yahoo_quoted,.q1,.q2,.q3,.orneos-quote),
#q:not(:checked)~.root #divRplyFwdMsg~*{display:none}
"""
FOLD_DARK = ".more{background:#1A2840;color:#9AA8BF}"
QUOTED = re.compile(r"""(?i)(blockquote[^>]*type=["']?cite|class=["'][^"']*(gmail_quote|moz-cite-prefix|yahoo_quoted|orneos-quote)|id=["']?(divRplyFwdMsg|appendonsend)|class=["']?q[123]\b)""")


def _initials(name):
    parts = [p for p in re.split(r"[\s@._-]+", name or "") if p]
    if not parts:
        return "?"
    return (parts[0][0] + (parts[-1][0] if len(parts) > 1 else parts[0][1:2])).upper()


def _when(iso, lang):
    if not iso:
        return ""
    try:
        d = datetime.fromisoformat(iso)
    except ValueError:
        return ""
    months = {"fr": "janv. févr. mars avr. mai juin juil. août sept. oct. nov. déc.",
              "de": "Jan. Feb. März Apr. Mai Juni Juli Aug. Sept. Okt. Nov. Dez.",
              "en": "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec"}[lang if lang in ("fr", "de") else "en"].split()
    return f"{d.day} {months[d.month - 1]} · {d:%H:%M}"


def _person(a, strong=False):
    """Someone of a heading: the name, then the address; a mailto: link the reader catches."""
    esc = html.escape
    email, name = a.get("email") or "", (a.get("name") or "").strip()
    label = f'<b class="name pn">{esc(name or email)}</b>' if strong else f'<span class="pn">{esc(name or email)}</span>'
    address = f' <span class="addr">&lt;{esc(email)}&gt;</span>' if name and name != email else ""
    return f'<a class="person" href="mailto:{esc(email, quote=True)}">{label}{address}</a>'


def _recipients(label, people):
    if not people:
        return ""
    return (f'<div class="rcpt"><span class="lab">{html.escape(label)}</span>'
            + ", ".join(_person(a) for a in people) + "</div>")


def conversation(items, dark=False, images=False, lang="fr", labels=None):
    """One page for a thread. items: [{id, info (from read()), mine, open, unread}], newest first."""
    labels = labels or {}
    esc = html.escape
    blocks = []
    pictures = {}
    for item in items:
        info, mid = item["info"], int(item["id"])
        sender = info.get("from") or {}
        name = sender.get("name") or sender.get("email") or ""
        reply_to = [a for a in info.get("replyTo") or [] if (a.get("email") or "").lower() != (sender.get("email") or "").lower()]
        head = (f'<div class="head"><div class="line">{_person(sender, strong=True)}'
                f'<span class="when">{esc(_when(info.get("date", ""), lang))}</span></div>'
                + _recipients(labels.get("to", ""), info.get("to") or [])
                + _recipients(labels.get("cc", ""), info.get("cc") or [])
                + _recipients(labels.get("bcc", ""), info.get("bcc") or [])
                + _recipients(labels.get("reply_to", ""), reply_to) + "</div>")
        preview = re.sub(r"\s+", " ", _drop_quotes(info.get("text") or ""))[:200]
        fragment = info.get("fragment") or ""
        fragment = _untemplate(fragment)
        found = QUOTED.search(fragment)
        toggle = ""
        if found:
            # the hidden checkbox heads the message (the rule that folds quotes follows it); the « ··· » that
            # ticks it sits where the quote begins, under what was written
            toggle = '<input type="checkbox" id="q">'
            at = fragment.rfind("<", 0, found.start())
            label = f'<label class="more" for="q" title="{esc(labels.get("quote", ""))}">···</label>'
            fragment = fragment[:at] + label + fragment[at:] if at >= 0 else fragment + label
        mine = info.get("pictures") or {}
        pictures.update(mine)
        shadow = SHADOW_STYLE + ("" if info.get("isHtml") or not dark else SHADOW_DARK_PLAIN) + _picture_style(mine, False)
        body = (f'<div class="body{" paper" if info.get("isHtml") and dark else ""}"><template shadowrootmode="open">'
                f'<style>{shadow}</style>{toggle}<div class="root">{fragment}</div></template></div>')
        chips = [f'<a class="file" href="{ACTION}attachment?m={mid}&amp;i={a["index"]}"><b>{esc((a["name"].rsplit(".", 1)[-1] if "." in a["name"] else "")[:4].upper() or "•")}</b>'
                 f'{esc(a["name"])}</a>' for a in info.get("attachments") or []]
        files = "".join(chips)
        if len(chips) > FILES_SHOWN + 1:
            # many files (pictures sent again with each reply): the first ones, the rest one click away
            files = ("".join(chips[:FILES_SHOWN]) + f'<input type="checkbox" class="all" id="f{mid}">'
                     f'<label class="file more-files" for="f{mid}">{esc(labels.get("more_files", "+%1").replace("%1", str(len(chips) - FILES_SHOWN)))}</label>'
                     f'<span class="rest">{"".join(chips[FILES_SHOWN:])}</span>')
        acts = "".join(f'<a href="{ACTION}{kind}?m={mid}">{esc(labels.get(kind, kind))}</a>'
                       for kind in ("reply", "all", "forward"))
        classes = "msg" + (" mine" if item.get("mine") else "") + (" unread" if item.get("unread") else "")
        blocks.append(
            f'<details class="{classes}"{" open" if item.get("open") else ""}><summary>'
            f'<span class="av">{esc(_initials(name))}</span><span class="who">'
            f'<span class="line"><span class="name">{esc(name)}</span>'
            f'<span class="addr">{esc(sender.get("email", "") if sender.get("name") else "")}</span>'
            f'<span class="when">{esc(_when(info.get("date", ""), lang))}</span></span>'
            f'<span class="sub">{esc(preview)}</span></span></summary>{head}'
            f'{f"<div class=files>{files}</div>" if files else ""}{body}<div class="acts">{acts}</div></details>')
    csp = CSP_IMAGES if images else CSP_BLOCKED
    return (f'<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="{csp}">'
            f'<meta name="viewport" content="width=device-width"><style>{CONV_STYLE}{CONV_DARK if dark else ""}'
            f'{_picture_style(pictures, True)}</style>' + "".join(blocks))


def _untemplate(fragment):
    """A message must not close the shadow root it sits in."""
    return re.sub(r"(?i)</?template\b[^>]*>", "", fragment)


def _drop_quotes(text):
    """The words of a message without what it quotes (for previews and for Ornis)."""
    out = []
    for line in (text or "").split("\n"):
        if line.lstrip().startswith(">"):
            continue
        if re.match(r"(?i)^\s*(le .{4,80} a écrit|on .{4,80} wrote|am .{4,80} schrieb)\s*:?\s*$", line) or \
                re.match(r"(?i)^\s*-{2,}\s*(original message|message d'origine|ursprüngliche nachricht)", line) or \
                re.match(r"(?i)^\s*(de|from|von)\s*:.*$", line) and out and not out[-1].strip():
            break
        out.append(line)
    return "\n".join(out).strip()


def thread_text(items):
    """A conversation for Ornis: each message, oldest first, without its quotes."""
    parts = []
    for item in items:
        info = item["info"]
        sender = info.get("from") or {}
        parts.append(f"From: {sender.get('name', '')} <{sender.get('email', '')}>\nDate: {info.get('date', '')}\n\n"
                     + _drop_quotes(info.get("text") or ""))
    return "\n\n-----\n\n".join(parts)


def attachment(raw, index):
    """(file name, bytes) of one attachment."""
    msg = parse(raw)
    for i, part in enumerate(_files(msg)):
        if i == index:
            return _file_name(part, index), part.get_payload(decode=True) or b""
    return None, None


def _is_calendar(part):
    return part.get_content_type() in ("text/calendar", "application/ics") \
        or (part.get_filename() or "").lower().endswith(".ics")


def _files(msg):
    """The attachments, plus an invitation's calendar part: Outlook and Teams send it inside the text
    alternatives (not as an attachment), and it is still the file people look for (Google sends both: one)."""
    files = list(msg.iter_attachments())
    if not any(_is_calendar(f) for f in files):
        files += [p for p in msg.walk() if not p.is_multipart() and _is_calendar(p)][:1]
    return files


def _file_name(part, index):
    if part.get_filename():
        return part.get_filename()
    if _is_calendar(part):
        return "invitation.ics"
    return f"piece-jointe-{index + 1}{mimetypes.guess_extension(part.get_content_type()) or ''}"


def calendar_of(msg):
    """The iCalendar text of an invitation (iMIP): the text/calendar part first (it carries the method),
    else an .ics attachment. "" when there is none."""
    parts = [p for p in msg.walk() if not p.is_multipart() and _is_calendar(p)]
    parts.sort(key=lambda p: p.get_content_type() != "text/calendar")
    for part in parts:
        payload = part.get_payload(decode=True) or b""
        charset = part.get_content_charset() or "utf-8"
        try:
            text = payload.decode(charset, "replace")
        except LookupError:
            text = payload.decode("utf-8", "replace")
        if "BEGIN:VEVENT" in text:
            return text
    return ""


# ---- writing ---------------------------------------------------------------------------------------------
def quote_header(original, lang):
    who = original["from"].get("name") or original["from"].get("email")
    when = original.get("date", "")
    try:
        moment = datetime.fromisoformat(when)
        stamp = moment.strftime("%d/%m/%Y %H:%M") if lang != "en" else moment.strftime("%d %b %Y %H:%M")
    except ValueError:
        stamp = ""
    if not stamp:
        return {"fr": f"{who} a écrit :", "en": f"{who} wrote:", "de": f"{who} schrieb:"}.get(lang, f"{who} wrote:")
    return {"fr": f"Le {stamp}, {who} a écrit :", "en": f"On {stamp}, {who} wrote:",
            "de": f"Am {stamp} schrieb {who}:"}.get(lang, f"On {stamp}, {who} wrote:")


def reply_fields(original, me_addresses, mode, lang):
    """To, Cc, subject and quoted body of a reply ("reply", "all") or a forward ("forward")."""
    subject = original.get("subject", "")
    prefix = {"forward": {"fr": "Tr", "en": "Fwd", "de": "WG"}.get(lang, "Fwd")}.get(mode, "Re")
    if not re.match(rf"(?i)^\s*{prefix}\s*:", subject):
        subject = f"{prefix}: {subject}"
    to, cc = [], []
    if mode in ("reply", "all"):
        to = [a["email"] for a in (original.get("replyTo") or [original["from"]]) if a.get("email")]
        if mode == "all":
            seen = {e.lower() for e in to} | set(me_addresses)
            for a in original.get("to", []) + original.get("cc", []):
                if a["email"].lower() not in seen:
                    cc.append(a["email"])
                    seen.add(a["email"].lower())
    quoted = "\n".join("> " + line for line in original.get("text", "").splitlines())
    source = original.get("source") or _html_from_text(original.get("text", ""))
    if mode == "forward":
        head = {"fr": "Message transféré", "de": "Weitergeleitete Nachricht"}.get(lang, "Forwarded message")
        labels = {"fr": ("De", "Date", "Objet", "À", "Cc"), "de": ("Von", "Datum", "Betreff", "An", "Cc")}.get(
            lang, ("From", "Date", "Subject", "To", "Cc"))
        sep = " : " if lang == "fr" else ": "

        def people(items):
            return ", ".join(formataddr((a.get("name") or "", a["email"])) if a.get("name") else a["email"]
                             for a in items or [] if a.get("email"))
        try:
            stamp = datetime.fromisoformat(original.get("date", "")).strftime("%d/%m/%Y %H:%M")
        except ValueError:
            stamp = ""
        rows = [(labels[0], people([original["from"]])), (labels[1], stamp), (labels[2], original.get("subject", "")),
                (labels[3], people(original.get("to"))), (labels[4], people(original.get("cc")))]
        lines = [f"-------- {head} --------"] + [f"{label}{sep}{value}" for label, value in rows if value]
        quote_text = "\n\n" + "\n".join(lines) + "\n\n" + original.get("text", "")
        quote_html = ('<div class="orneos-forward" style="margin-top:24px;color:#45556E">' + "<br>".join(html.escape(x) for x in lines)
                      + '</div><div style="margin-top:12px">' + source + "</div>")
    else:
        header = quote_header(original, lang)
        quote_text = f"\n\n{header}\n{quoted}"
        quote_html = (f'<div class="orneos-quote" style="margin-top:24px;color:#45556E">{html.escape(header)}</div>'
                      '<blockquote type="cite" style="margin:6px 0 0 2px;padding-left:12px;'
                      f'border-left:3px solid #DCE3F7;color:#45556E">{source}</blockquote>')
    refs = (original.get("references", "") + " " + original.get("mid", "")).strip()
    return {"to": to, "cc": cc, "subject": subject, "body": "", "quoteText": quote_text, "quoteHtml": quote_html,
            "inReplyTo": original.get("mid", "") if mode != "forward" else "", "references": refs if mode != "forward" else ""}


def _html_from_text(text):
    """The HTML twin of plain text: same lines, links clickable, quotes set apart (no page around it)."""
    paragraphs = []
    for line in html.escape(text).split("\n"):
        if line.startswith("&gt;"):
            paragraphs.append('<div style="color:#45556E;border-left:3px solid #DCE3F7;padding-left:12px">'
                              + (line[4:].lstrip() or "&nbsp;") + "</div>")
        else:
            paragraphs.append("<div>" + (URL.sub(r'<a href="\1">\1</a>', line) or "<br>") + "</div>")
    return "".join(paragraphs)


def text_from_html(fragment):
    """Readable plain text of an HTML fragment (signatures, editor content without a plain twin)."""
    fragment = re.sub(r"(?is)<(style|head|script)\b.*?</\1>", "", fragment or "")
    fragment = re.sub(r"(?i)<li\b[^>]*>", "\n• ", fragment)
    fragment = re.sub(r"(?i)<br\s*/?>|</(p|div|li|tr|h[1-6]|blockquote)>", "\n", fragment)
    fragment = re.sub(r'(?is)<a\b[^>]*href="(https?:[^"]+)"[^>]*>(.*?)</a>',
                      lambda m: m.group(2) if m.group(1) in m.group(2) else f"{m.group(2)} <{m.group(1)}>", fragment)
    text = html.unescape(re.sub(r"<[^>]+>", "", fragment)).replace("\xa0", " ")
    return re.sub(r"\n{3,}", "\n\n", "\n".join(line.rstrip() for line in text.split("\n"))).strip()


def signature_html(signature):
    """A signature as HTML: the cloud keeps either HTML (its editor) or older plain text."""
    signature = (signature or "").strip()
    if not signature or re.search(r"(?i)<(br|p|div|span|a|b|strong|i|em|img|table|font)\b", signature):
        return signature
    return html.escape(signature).replace("\n", "<br>")


def editable(source):
    """The body of a message, made fit for the editor: no page, head or styles around it."""
    source = re.sub(r"(?is)<(head|style|title)\b.*?</\1>", "", source or "")
    return re.sub(r"(?is)</?(html|body|!doctype)\b[^>]*>", "", source).strip()


def _div_end(source, start):
    """Where the <div> opened at start closes (after its </div>), or len(source)."""
    depth = 0
    for tag in re.finditer(r"(?i)<(/?)div\b[^>]*>", source[start:]):
        depth += -1 if tag.group(1) else 1
        if depth == 0:
            return start + tag.end()
    return len(source)


def draft_parts(source):
    """A draft as build() made it, back in its parts: (written, signature, quote). The text editor gets
    only what was written; the signature and the quote stay as they are (the editor would flatten them)."""
    sig = re.search(r"""(?i)<div class=["']orneos-signature["'][^>]*>""", source)
    if sig:
        end = _div_end(source, sig.start())
        return source[:sig.start()], source[sig.end():end - len("</div>")], source[end:].strip()
    quote = re.search(r"""(?i)<div class=["']orneos-(quote|forward)["']""", source)
    if quote:
        return source[:quote.start()], "", source[quote.start():]
    return source, "", ""


DESIGNED = re.compile(r"(?i)<(table|img)\b")


def designed_signature(page):
    """HTML copied with a layout (tables, pictures: a signature made on a site or in a mail app), as it is,
    to keep without the text editor (Qt keeps a few colours, loses sizes, spacing, gradients). "" otherwise."""
    if not page or not DESIGNED.search(page):
        return ""
    found = re.search(r"(?s)<!--StartFragment-->(.*)<!--EndFragment-->", page)
    fragment = re.sub(r"(?is)<meta\b[^>]*>", "", found.group(1) if found else page)
    return editable(_sanitize(fragment))


def local_path(value):
    """A path from QML: file:// URLs (encoded, or file:///C:/… on Windows) as a path of this system."""
    value = str(value or "")
    if value.lower().startswith("file:"):
        return urllib.request.url2pathname(urllib.parse.urlsplit(value).path)
    return value


IMG_SRC = re.compile(r"""(?is)(<img\b[^>]*?\bsrc\s*=\s*)(["'])(data:image/[a-z0-9.+-]+;base64,[^"']+|file://[^"']+)\2""")


def inline_images(rich, local_dir=None):
    """The pictures of the HTML as parts of the message (cid:), the way every mail app shows them: data: URIs
    (forwarded or reopened messages, signatures) and the pictures pasted in the composer, local files read
    only from local_dir (a received message could otherwise name any file of the computer in an <img>).
    (html, [(cid, bytes, maintype, subtype)])."""
    parts, seen = [], {}
    root = Path(local_dir).resolve() if local_dir else None

    def swap(match):
        src = html.unescape(match.group(3))
        if src in seen:
            return f"{match.group(1)}{match.group(2)}cid:{seen[src]}{match.group(2)}"
        if src.lower().startswith("data:"):
            head, _, payload = src.partition(",")
            kind = head[5:].split(";")[0].lower()
            try:
                data = base64.b64decode(payload + "=" * (-len(payload) % 4))
            except ValueError:
                return match.group(0)
        else:
            if root is None:
                return match.group(0)
            try:
                path = Path(local_path(src)).resolve()
                if root not in path.parents:
                    return match.group(0)
                data = path.read_bytes()
            except (OSError, ValueError):
                return match.group(0)
            kind = mimetypes.guess_type(path.name)[0] or ""
        main, _, sub = kind.partition("/")
        if main != "image" or not sub or not data:
            return match.group(0)
        cid = make_msgid(domain="plume.orneos.eu")[1:-1]
        seen[src] = cid
        parts.append((cid, data, main, sub))
        return f"{match.group(1)}{match.group(2)}cid:{cid}{match.group(2)}"

    return IMG_SRC.sub(swap, rich), parts


def build(fields, sender_name, sender_email, local_dir=None):
    """(raw bytes, envelope recipients, Message-ID) of an outgoing message. fields: to, cc, bcc (lists of
    addresses), subject, body (plain text of what was written) and html (the same, formatted; optional),
    signature (HTML), quoteText and quoteHtml (the message answered or forwarded), attachments (file paths),
    inReplyTo, references. Written text, then the signature, then the quote. Pictures go inline (cid:),
    pasted ones read from local_dir."""
    msg = EmailMessage()
    msg["From"] = formataddr((sender_name or "", sender_email))
    to = [a for a in fields.get("to", []) if a.strip()]
    cc = [a for a in fields.get("cc", []) if a.strip()]
    bcc = [a for a in fields.get("bcc", []) if a.strip()]
    if to:
        msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = fields.get("subject", "")
    msg["Date"] = format_datetime(datetime.now().astimezone())
    msg["Message-ID"] = make_msgid(domain=sender_email.split("@")[-1] if "@" in sender_email else "orneos.eu")
    if fields.get("inReplyTo"):
        msg["In-Reply-To"] = fields["inReplyTo"]
    if fields.get("references"):
        msg["References"] = fields["references"]
    msg["User-Agent"] = "Orneos Plume"
    text = fields.get("body", "").rstrip()
    rich = fields.get("html") or _html_from_text(text)
    signature = signature_html(fields.get("signature", ""))
    if signature:
        text += "\n\n-- \n" + text_from_html(signature)
        rich += f'<div class="orneos-signature" style="margin-top:20px">{signature}</div>'
    if fields.get("quoteText") or fields.get("quoteHtml"):
        text += fields.get("quoteText") or ("\n\n" + text_from_html(fields["quoteHtml"]))
        rich += fields.get("quoteHtml") or _html_from_text(fields["quoteText"])
    rich, pictures = inline_images(rich, local_dir)
    msg.set_content(text + "\n")
    msg.add_alternative('<!doctype html><html><head><meta charset="utf-8"></head>'
                        '<body style="font:15px/1.5 Arial,sans-serif;color:#0F2440">' + rich + "</body></html>",
                        subtype="html")
    if pictures:
        page = msg.get_body(preferencelist=("html",))
        for n, (cid, data, main, sub) in enumerate(pictures, 1):
            page.add_related(data, maintype=main, subtype=sub, cid=f"<{cid}>", disposition="inline",
                             filename=f"image{n}.{sub.replace('jpeg', 'jpg').split('+')[0]}")
    for path in fields.get("attachments", []):
        p = Path(local_path(path))
        try:
            data = p.read_bytes()
        except OSError:
            continue
        kind, _ = mimetypes.guess_type(p.name)
        main, _, sub = (kind or "application/octet-stream").partition("/")
        msg.add_attachment(data, maintype=main, subtype=sub, filename=p.name)
    recipients = [a for _, a in getaddresses(to + cc + bcc) if a]
    return msg.as_bytes(policy=policy.SMTP), recipients, str(msg["Message-ID"])


def keep_bcc(raw, bcc):
    """The copy kept in Sent or Drafts: with the Bcc that never leaves (build() leaves it out of what is sent),
    as other mail apps do, so that the sender still sees who got it."""
    bcc = [a for a in bcc or [] if a.strip()]
    if not bcc:
        return raw
    head = EmailMessage()
    head["Bcc"] = ", ".join(bcc)
    return head.as_bytes(policy=policy.SMTP).split(b"\r\n\r\n", 1)[0] + b"\r\n" + raw


def calendar_reply(ics, text, subject, to, sender_name, sender_email):
    """An answer to an invitation (iMIP REPLY): a line of text and the calendar part the organizer's
    calendar reads (Outlook, Google, the cloud). (raw bytes, recipients)."""
    msg = EmailMessage()
    msg["From"] = formataddr((sender_name or "", sender_email))
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = format_datetime(datetime.now().astimezone())
    msg["Message-ID"] = make_msgid(domain=sender_email.split("@")[-1] if "@" in sender_email else "orneos.eu")
    msg["User-Agent"] = "Orneos Plume"
    msg.set_content(text + "\n")
    msg.add_alternative(ics, subtype="calendar", params={"method": "REPLY"})
    return msg.as_bytes(policy=policy.SMTP), [a for _, a in getaddresses([to]) if a]
