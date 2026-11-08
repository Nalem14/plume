"""A Talk message as Meet shows it: the placeholders of Talk ({mention-user1}, {file0}, {actor}…) replaced by
names and attachments, Talk's Markdown made into the small HTML subset a QML Text draws, everything else
escaped (nothing from the cloud ever reaches the view as markup).

render() returns {html, plain, files, poll, location, mentioned, emojiOnly}. Links in the HTML are ours:
  mention:<type>:<id>    a person, a group, a team (QML opens the person)
  file:<id>              an attachment (QML opens or saves it)
  https://…              a link in the text (opened in the browser)
"""
import html
import re

URL = re.compile(r"(?<![\w/\"'=])(https?://[^\s<>\"']+[^\s<>\"'.,;:!?)\]])")
EMOJI = re.compile(r"^(?:[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍\U0001F3FB-\U0001F3FF\s])+$")
TOKEN = re.compile(r"\{([a-z0-9-]+)\}")


def _inline(text, accent):
    """Markdown of one line (already escaped): code, bold, italic, strike, links."""
    codes = []

    def keep_code(m):
        codes.append(m.group(1))
        return f"\x00{len(codes) - 1}\x00"
    text = re.sub(r"`([^`]+)`", keep_code, text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text)
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", text)
    text = re.sub(r"(?<![\w_])_(?!\s)(.+?)(?<!\s)_(?![\w_])", r"<i>\1</i>", text)
    text = re.sub(r"~~(.+?)~~", r"<s>\1</s>", text)
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)\s\"'<>]+)\)",       # no quote: the address stays an address
                  lambda m: f'<a href="{m.group(2)}" style="color:{accent}">{m.group(1)}</a>', text)
    text = URL.sub(lambda m: f'<a href="{m.group(1)}" style="color:{accent}">{m.group(1)}</a>', text)
    return re.sub(r"\x00(\d+)\x00", lambda m: f"<code>{codes[int(m.group(1))]}</code>", text)


def markdown(text, accent="#002FA7", markdown_on=True):
    """Talk's Markdown (escaped first) to HTML: blocks of code, quotes, lists, headings, then inline."""
    text = html.escape(text, quote=False)
    if not markdown_on:
        return URL.sub(lambda m: f'<a href="{m.group(1)}" style="color:{accent}">{m.group(1)}</a>',
                       text).replace("\n", "<br>")
    out, block, in_code, items = [], [], False, []

    def flush_list():
        if items:
            tag = items[0][0]
            out.append(f"<{tag}>" + "".join(f"<li>{_inline(i[1], accent)}</li>" for i in items) + f"</{tag}>")
            items.clear()
    for line in text.split("\n"):
        if line.strip().startswith("```"):
            if in_code:
                out.append("<pre>" + "\n".join(block) + "</pre>")
                block, in_code = [], False
            else:
                flush_list()
                in_code = True
            continue
        if in_code:
            block.append(line)
            continue
        m = re.match(r"^\s*(?:[-*+]|(\d+)[.)])\s+(.*)$", line)
        if m:
            items.append(("ol" if m.group(1) else "ul", m.group(2)))
            continue
        flush_list()
        if line.startswith("&gt; ") or line == "&gt;":
            quote = "#D6DEF5" if accent.upper() == "#FFFFFF" else "#7A8699"      # on our Klein bubble: light
            out.append(f'<span style="color:{quote}">▎ {_inline(line[5:], accent)}</span><br>')
        elif re.match(r"^#{1,3} ", line):
            out.append(f"<b>{_inline(line.lstrip('#').strip(), accent)}</b><br>")
        else:
            out.append(_inline(line, accent) + "<br>")
    if in_code:
        out.append("<pre>" + "\n".join(block) + "</pre>")
    flush_list()
    result = "".join(out)
    # a list or a block already starts on its own line
    result = re.sub(r"<br>(<(?:ul|ol|pre)>)", r"\1", result)
    return result[:-4] if result.endswith("<br>") else result


def _file(p):
    return {
        "id": str(p.get("id", "")), "name": p.get("name", ""), "mime": p.get("mimetype", ""),
        "size": int(p.get("size") or 0), "path": p.get("path", ""), "link": p.get("link", ""),
        "preview": p.get("preview-available") == "yes", "width": int(p.get("width") or 0),
        "height": int(p.get("height") or 0), "blurhash": p.get("blurhash", ""),
    }


def render(message, me="", accent="#002FA7", mention="#002FA7"):
    """The parts of one Talk message for the view."""
    params = message.get("messageParameters") or {}
    if isinstance(params, list):                 # Talk sends [] for none
        params = {}
    text = message.get("message") or ""
    files, poll, location, mentioned = [], None, None, False
    names = {}
    for key, p in params.items():
        if not isinstance(p, dict):
            continue
        kind = p.get("type")
        if kind == "file":
            files.append(_file(p))
        elif kind == "talk-poll":
            poll = {"id": str(p.get("id", "")), "question": p.get("name", "")}
        elif kind == "geo-location":
            location = {"name": p.get("name", ""), "lat": p.get("latitude", ""), "lon": p.get("longitude", "")}
        if kind in ("user", "guest", "email", "user-group", "group", "circle", "call", "federated_user"):
            names[key] = p
            if (kind == "user" and p.get("id") == me) or kind == "call":
                mentioned = mentioned or key.startswith("mention")

    # plain text (for previews, notifications, copy): the names in place of the placeholders
    def plain_token(m):
        p = params.get(m.group(1))
        if not isinstance(p, dict):
            return m.group(0)
        if p.get("type") == "file":
            return p.get("name", "")
        name = p.get("name", "")
        return ("@" + name) if m.group(1).startswith("mention") else name
    plain = TOKEN.sub(plain_token, text)

    # html: placeholders become marks that survive the escaping, then links and chips
    marks = {}

    def mark(m):
        key = m.group(1)
        if key not in params or not isinstance(params[key], dict):
            return m.group(0)
        marks[key] = params[key]
        return f"\x01{key}\x01"
    marked = TOKEN.sub(mark, text)
    body = markdown(marked, accent, message.get("markdown", True) is not False)

    def chip(m):
        p = marks.get(m.group(1), {})
        kind = p.get("type", "")
        name = html.escape(p.get("name", ""))
        if kind == "file":
            return f'<a href="file:{html.escape(str(p.get("id", "")))}" style="color:{accent}">{name}</a>'
        if m.group(1).startswith("mention") or m.group(1) == "actor" or kind in ("user", "guest", "call", "user-group", "circle"):
            target = f'mention:{html.escape(kind)}:{html.escape(str(p.get("id", "")))}'
            weight = "font-weight:600;" if m.group(1).startswith("mention") else ""
            return f'<a href="{target}" style="color:{mention};text-decoration:none;{weight}">' + \
                   (f"@{name}" if m.group(1).startswith("mention") else name) + "</a>"
        return name
    body = re.sub(r"\x01([a-z0-9-]+)\x01", chip, body)
    # a message that is only a file or a poll: its card says it all
    if (files or poll) and TOKEN.fullmatch(text.strip() or "x"):
        body = ""
    stripped = plain.strip()
    emoji_only = bool(stripped) and len(stripped) <= 12 and bool(EMOJI.match(stripped))
    return {"html": body, "plain": plain, "files": files, "poll": poll, "location": location,
            "mentioned": mentioned, "emojiOnly": emoji_only}
