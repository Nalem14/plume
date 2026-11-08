"""What a note's Markdown says without drawing it: its title (the first line, like on macOS), the line shown
under it in the list, its #tags, checklist progress, the images it shows and the tasks it lists."""
import re

TITLE_MAX = 100
_MARK = re.compile(r"^\s{0,3}(#{1,6}\s+|>\s*|[-*+]\s+\[[ xX]\]\s+|[-*+]\s+|\d+[.)]\s+)")
_INLINE = [
    (re.compile(r"!\[([^\]]*)\]\([^)]*\)"), r"\1"),          # images: their alt text
    (re.compile(r"\[([^\]]+)\]\([^)]*\)"), r"\1"),           # links: their text
    (re.compile(r"(\*\*|__)(.+?)\1"), r"\2"),
    (re.compile(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])"), r"\1"),
    (re.compile(r"(?<![\w_])_(?!\s)(.+?)(?<!\s)_(?![\w_])"), r"\1"),
    (re.compile(r"~~(.+?)~~"), r"\1"),
    (re.compile(r"`([^`]+)`"), r"\1"),
]
TAG = re.compile(r"(?:(?<=\s)|^)#([^\W\d_][\w\-/]{0,40})", re.UNICODE)
CHECK = re.compile(r"^(\s*)[-*+]\s+\[([ xX])\]\s+(.*)$")
IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
FENCE = re.compile(r"^\s{0,3}(```|~~~)")


def plain(line):
    """A line without its Markdown marks."""
    line = _MARK.sub("", line, count=1)
    for pattern, repl in _INLINE:
        line = pattern.sub(repl, line)
    return line.strip()


def lines_outside_code(content):
    """(index, line) of the lines that are not inside a ``` block."""
    inside = False
    for i, line in enumerate((content or "").split("\n")):
        if FENCE.match(line):
            inside = not inside
            continue
        if not inside:
            yield i, line


def title_of(content):
    """The first line with words in it, without its marks ("# Courses" → "Courses")."""
    for line in (content or "").split("\n"):
        text = plain(line)
        if text:
            return text[:TITLE_MAX].strip()
    return ""


def preview(content, limit=160):
    """The first words after the title, on one line (what the list shows under the title)."""
    seen_title = False
    out = []
    for _i, line in lines_outside_code(content):
        text = plain(line)
        if not text:
            continue
        if not seen_title:
            seen_title = True
            continue
        out.append(text)
        if sum(len(x) for x in out) > limit:
            break
    return " ".join(out)[:limit]


def tags(content):
    """The #tags of a note, without the # and in lower case, each once (headings are not tags: "# Titre")."""
    found = []
    for _i, line in lines_outside_code(content):
        if re.match(r"^\s{0,3}#{1,6}\s", line):
            line = re.sub(r"^\s{0,3}#{1,6}\s", "", line)
        line = re.sub(r"`[^`]*`|\]\([^)]*\)|https?://\S+", " ", line)
        for match in TAG.finditer(line):
            tag = match.group(1).rstrip("-/").lower()
            if tag and tag not in found:
                found.append(tag)
    return found


def checklist(content):
    """(done, total) of the checklist items."""
    done = total = 0
    for _i, line in lines_outside_code(content):
        m = CHECK.match(line)
        if m:
            total += 1
            done += m.group(2) in "xX"
    return done, total


def open_items(content):
    """The unchecked checklist items, in order: what « Envoyer vers Tâches » takes."""
    return [plain(m.group(3)) for _i, line in lines_outside_code(content)
            for m in [CHECK.match(line)] if m and m.group(2) == " " and plain(m.group(3))]


def images(content):
    """The images the note shows: [(alt, path)], attachments (relative paths) and web images alike."""
    return [(m.group(1), m.group(2)) for _i, line in lines_outside_code(content) for m in IMAGE.finditer(line)]


def is_attachment(path):
    return not re.match(r"^[a-z][a-z0-9+.-]*:", path or "", re.I)


LINK = re.compile(r"(!?)\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


def files(content):
    """The files attached to the note that are not images: [(label, path)] (« 📎 rapport.pdf »)."""
    return [(m.group(2).replace("📎", "").strip(), m.group(3)) for _i, line in lines_outside_code(content)
            for m in LINK.finditer(line) if not m.group(1) and is_attachment(m.group(3))
            and not m.group(3).startswith("#")]


def attachments(content):
    """Every attachment the note links (images and files), in order."""
    return [m.group(3) for _i, line in lines_outside_code(content) for m in LINK.finditer(line)
            if is_attachment(m.group(3)) and not m.group(3).startswith("#")]


def _tag_pattern(tag, nested):
    # « #tag » as a word, whatever its case; nested: « #tag/sous » too
    tail = r"(?=$|[^\w\-/]|/)" if nested else r"(?=$|[^\w\-/])"
    return re.compile(r"(?:(?<=\s)|^)#" + re.escape(tag) + tail, re.IGNORECASE | re.UNICODE)


def _outside_inline_code(line, fn):
    parts = re.split(r"(`[^`]*`)", line)
    return "".join(p if p.startswith("`") and p.endswith("`") and len(p) > 1 else fn(p) for p in parts)


def rename_tag(content, old, new):
    """#old (and #old/…) becomes #new, outside code; the rest of the text stays exactly as it was."""
    pattern = _tag_pattern(old, True)
    lines = (content or "").split("\n")
    for i, line in lines_outside_code(content):
        lines[i] = _outside_inline_code(line, lambda part: pattern.sub("#" + new, part))
    return "\n".join(lines)


def remove_tag(content, tag):
    """#tag goes from the text (with the space before it); a line left empty by it goes too."""
    pattern = re.compile(r"[ \t]?" + _tag_pattern(tag, False).pattern, re.IGNORECASE | re.UNICODE)
    lines = (content or "").split("\n")
    drop = set()
    for i, line in lines_outside_code(content):
        changed = _outside_inline_code(line, lambda part: pattern.sub("", part))
        if changed != line and not changed.strip():
            drop.add(i)
        lines[i] = changed
    return "\n".join(line for i, line in enumerate(lines) if i not in drop)
