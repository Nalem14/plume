"""The note's text as one reads it, while it stays plain Markdown underneath (what the cloud and every other
Notes app keep): the first line as a title, headings in size, bold, italics, struck and code in their style,
the marks themselves faded, links and #tags in Klein. Checklist and bullet marks are hidden: the window
draws a round box or a dot over them (marks), like macOS. A link to a mail, a note or a task (links.py) is a
chip: its title on a tint, the window's icon of the thing in the room its « [ » keeps.

A QSyntaxHighlighter on the TextArea's document: it only changes how characters look, never the text, so
undo, copy and what is saved are exactly what was typed.
"""
import re
import unicodedata

import links
from PySide6.QtCore import Property, QObject, Signal, Slot
from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat, QTextFormat
from PySide6.QtQuick import QQuickTextDocument

HEADING = re.compile(r"^(\s{0,3})(#{1,6})(\s+)(.*)$")
CHECK = re.compile(r"^(\s*)([-*+]\s+\[([ xX])\]\s)")
BULLET = re.compile(r"^(\s*)([-*+]\s)(?!\[[ xX]\])")
NUMBER = re.compile(r"^(\s*)(\d+[.)]\s)")
QUOTE = re.compile(r"^(\s{0,3}>\s?)")
RULE = re.compile(r"^\s{0,3}([-*_])(\s*\1){2,}\s*$")
FENCE = re.compile(r"^\s{0,3}(```|~~~)")
TABLE = re.compile(r"^\s*\|")
INLINE = [
    ("code", re.compile(r"(`+)(?!`)(.+?)(?<!`)\1(?!`)")),
    ("bold", re.compile(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1")),
    ("italic", re.compile(r"(?<![\w*])(\*)(?=[^\s*])(.+?)(?<=[^\s*])\*(?![\w*])|(?<![\w_])(_)(?=[^\s_])(.+?)(?<=[^\s_])_(?![\w_])")),
    ("strike", re.compile(r"(~~)(?=\S)(.+?)(?<=\S)~~")),
]
LINK = re.compile(r"(!?)\[([^\]]*)\]\(([^)\s]*)(?:\s+\"[^\"]*\")?\)")
URL = re.compile(r"(?<![(\[])\bhttps?://[^\s<>()]+[^\s<>().,;:!?'\"]")
TAG = re.compile(r"(?:(?<=\s)|^)#[^\W\d_][\w\-/]{0,40}", re.UNICODE)
IN_CODE, SEEN = 1, 2


def fold_chars(text):
    """Lower case and without accents, one character for one (positions stay those of the text)."""
    return "".join((unicodedata.normalize("NFD", ch)[:1].lower() or ch)[:1] for ch in text)


class Highlighter(QSyntaxHighlighter):
    def __init__(self, document, colors, size):
        super().__init__(document)
        self.colors = colors
        self.size = size
        self.active = -1          # the block with the cursor: its marks show, faded
        self.find = ""            # what « Rechercher dans la note » looks for (folded): every match in saffron
        self.current = -1         # the match the cursor is on (its position in the document)

    def hide(self, start, length, base=None):
        """Marks out of the way (« # », « ** », a link's address): on the cursor's line they show, faded;
        elsewhere they take almost no room and no colour. The text stays exactly what was typed."""
        if length <= 0:
            return
        if self.currentBlock().blockNumber() == self.active:
            f = QTextCharFormat(base) if base is not None else QTextCharFormat()
            f.setForeground(QColor(self.colors["faint"]))
            self.setFormat(start, length, f)
            return
        f = QTextCharFormat()
        f.setForeground(QColor(0, 0, 0, 0))
        f.setProperty(QTextFormat.Property.FontPixelSize, 1)
        f.setFontLetterSpacingType(QFont.SpacingType.PercentageSpacing)
        f.setFontLetterSpacing(1)              # 1 % of a 1 px glyph: a long address takes no visible room
        self.setFormat(start, length, f)

    def fmt(self, color=None, weight=None, italic=None, size=None, family=None, strike=False, background=None,
            transparent=False, underline=False):
        f = QTextCharFormat()
        if transparent:
            f.setForeground(QColor(0, 0, 0, 0))
        elif color:
            f.setForeground(QColor(self.colors[color]))
        if weight:
            f.setFontWeight(weight)
        if italic:
            f.setFontItalic(True)
        if size:
            f.setProperty(QTextFormat.Property.FontPixelSize, int(size))
        if family:
            f.setFontFamilies([family])
        if strike:
            f.setFontStrikeOut(True)
        if underline:
            f.setFontUnderline(True)
        if background:
            f.setBackground(QColor(self.colors[background]))
        return f

    def highlightBlock(self, text):
        self._highlight(text)
        if self.find:
            hay, at, start = fold_chars(text), 0, self.currentBlock().position()
            while True:
                at = hay.find(self.find, at)
                if at < 0:
                    break
                current = start + at == self.current
                for i in range(at, at + len(self.find)):
                    f = QTextCharFormat(self.format(i))
                    f.setBackground(QColor(self.colors["saffron" if current else "saffronTint"]))
                    if current:
                        f.setForeground(QColor(self.colors.get("saffronText", "#1C1400")))
                    self.setFormat(i, 1, f)
                at += len(self.find)

    def _highlight(self, text):
        # block state: IN_CODE inside a ``` block, SEEN once a line with words came (the next ones are not the title)
        previous = max(0, self.previousBlockState())
        inside = bool(previous & IN_CODE)
        seen = bool(previous & SEEN)
        first = not seen and bool(text.strip())
        mono = "JetBrains Mono"
        if FENCE.match(text):
            self.setFormat(0, len(text), self.fmt("faint", family=mono, size=self.size - 2))
            self.setCurrentBlockState((0 if inside else IN_CODE) | SEEN)
            return
        if inside:
            self.setFormat(0, len(text), self.fmt("body", family=mono, size=self.size - 1, background="codeBg"))
            self.setCurrentBlockState(IN_CODE | SEEN)
            return
        self.setCurrentBlockState(SEEN if seen or first else 0)
        start = 0
        m = HEADING.match(text)
        if m:
            level = len(m.group(2))
            size = {1: self.size + 10, 2: self.size + 5, 3: self.size + 2}.get(level, self.size)
            if first:
                size = max(size, self.size + 12)
            self.setFormat(0, len(text), self.fmt("text", weight=QFont.Weight.Bold, size=size))
            self.hide(0, m.end(3), self.fmt("faint", weight=QFont.Weight.Normal, size=size))
            start = m.end(3)
        elif first and text.strip():
            self.setFormat(0, len(text), self.fmt("text", weight=QFont.Weight.Bold, size=self.size + 12))
        elif RULE.match(text):
            self.setFormat(0, len(text), self.fmt("faint"))
            return
        elif TABLE.match(text):
            self.setFormat(0, len(text), self.fmt("body", family=mono, size=self.size - 2))
            for i, ch in enumerate(text):
                if ch in "|-:" and (ch == "|" or set(text.strip()) <= set("|-: ")):
                    self.setFormat(i, 1, self.fmt("faint", family=mono, size=self.size - 2))
            return
        else:
            m = CHECK.match(text)
            if m:
                self.setFormat(0, m.end(2), self.fmt(transparent=True))
                start = m.end(2)
                if m.group(3) in "xX":
                    self.setFormat(start, len(text) - start, self.fmt("muted", strike=True))
            else:
                m = BULLET.match(text) or NUMBER.match(text) or QUOTE.match(text)
                if m and BULLET.match(text):
                    # room for the dot the window draws: the mark itself is invisible and a little wider
                    f = self.fmt(transparent=True)
                    f.setFontLetterSpacingType(QFont.SpacingType.AbsoluteSpacing)
                    f.setFontLetterSpacing(max(4, self.size // 3))
                    self.setFormat(m.end(1), m.end(2) - m.end(1), f)
                    start = m.end(2)
                elif m and NUMBER.match(text):
                    self.setFormat(0, m.end(2), self.fmt("muted"))
                    start = m.end(2)
                elif m:
                    self.setFormat(0, m.end(1), self.fmt("accentLine"))
                    self.setFormat(m.end(1), len(text) - m.end(1), self.fmt("muted", italic=True))
                    start = m.end(1)
        self._inline(text, start)

    def _inline(self, text, start):
        taken = [False] * len(text)
        for kind, pattern in INLINE:
            for m in pattern.finditer(text, start):
                if any(taken[m.start():m.end()]):
                    continue
                mark = len(m.group(1) or m.group(3) or "") if kind == "italic" else len(m.group(1))
                inner_start, inner_end = m.start() + mark, m.end() - mark
                current = self.format(inner_start)
                if kind == "code":
                    f = self.fmt("body", family="JetBrains Mono", background="codeBg")
                    f.setProperty(QTextFormat.Property.FontPixelSize, max(10, self.size - 1))
                    self.setFormat(inner_start, inner_end - inner_start, f)
                else:
                    f = QTextCharFormat(current)
                    if kind == "bold":
                        f.setFontWeight(QFont.Weight.Bold)
                    elif kind == "italic":
                        f.setFontItalic(True)
                    else:
                        f.setFontStrikeOut(True)
                    self.setFormat(inner_start, inner_end - inner_start, f)
                self.hide(m.start(), mark, current)
                self.hide(inner_end, mark, current)
                for i in range(m.start(), m.end()):
                    taken[i] = True
        for m in LINK.finditer(text, start):
            image, label = m.group(1), m.group(2)
            if image:
                # an image is a chip where it sits (its picture shows under the note): « ! » keeps room for the
                # icon the window draws, the alt text on a tint, the address hidden
                base = self.format(m.start())
                room = QTextCharFormat(base)
                room.setForeground(QColor(0, 0, 0, 0))
                room.setBackground(QColor(self.colors["tint"]))
                room.setFontLetterSpacingType(QFont.SpacingType.AbsoluteSpacing)
                room.setFontLetterSpacing(round(self.size * 0.95))
                self.setFormat(m.start(), 1, room)
                self.hide(m.start() + 1, 1, base)
                if label:
                    f = QTextCharFormat(base)
                    f.setForeground(QColor(self.colors["tintText"]))
                    f.setBackground(QColor(self.colors["tint"]))
                    self.setFormat(m.start(2), len(label), f)
                self.hide(m.end(2), m.end() - m.end(2), base)
                for i in range(m.start(), m.end()):
                    taken[i] = True
                continue
            if not label:
                continue
            base = self.format(m.start(2))
            if links.is_link(m.group(3)):
                # a chip: « [ » keeps room for the icon (drawn by the window), the title on a tint
                room = QTextCharFormat(base)
                room.setForeground(QColor(0, 0, 0, 0))
                room.setBackground(QColor(self.colors["tint"]))
                room.setFontLetterSpacingType(QFont.SpacingType.AbsoluteSpacing)
                room.setFontLetterSpacing(round(self.size * 0.95))
                self.setFormat(m.start(), 1, room)
                f = QTextCharFormat(base)
                f.setForeground(QColor(self.colors["tintText"]))
                f.setBackground(QColor(self.colors["tint"]))
                self.setFormat(m.start(2), len(label), f)
                self.hide(m.end(2), m.end() - m.end(2), base)
                for i in range(m.start(), m.end()):
                    taken[i] = True
                continue
            self.hide(m.start(), 1, base)                           # [
            self.hide(m.end(2), m.end() - m.end(2), base)           # ](address)
            f = QTextCharFormat(base)
            f.setForeground(QColor(self.colors["accent"]))
            f.setFontUnderline(True)
            self.setFormat(m.start(2), len(label), f)
            for i in range(m.start(), m.end()):
                taken[i] = True
        for m in URL.finditer(text, start):
            if any(taken[m.start():m.end()]):
                continue
            f = QTextCharFormat(self.format(m.start()))
            f.setForeground(QColor(self.colors["accent"]))
            f.setFontUnderline(True)
            self.setFormat(m.start(), m.end() - m.start(), f)
        for m in TAG.finditer(text, start):
            if any(taken[m.start():m.end()]):
                continue
            f = QTextCharFormat(self.format(m.start()))
            f.setForeground(QColor(self.colors["accent"]))
            f.setFontWeight(QFont.Weight.DemiBold)
            self.setFormat(m.start(), m.end() - m.start(), f)


class EditorHelper(QObject):
    """One per editor: attach() it to the TextArea's textDocument. marks: where the window draws the boxes
    and dots ({pos, kind: "check" | "done" | "bullet", indent})."""
    marksChanged = Signal()

    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self._theme = theme
        self._highlighter = None
        self._doc = None
        self._marks = []
        self._size = 16
        theme.changed.connect(self._restyle)

    def _colors(self):
        c = dict(self._theme.c)
        c.setdefault("codeBg", c.get("hover", "#E4E8F0"))
        c["codeBg"] = c.get("hover")
        return c

    @Slot(QObject, int)
    def attach(self, text_document, size):
        doc = text_document.textDocument() if isinstance(text_document, QQuickTextDocument) else None
        if doc is None:
            return
        self._size = size
        self._quick_doc = text_document         # kept: the document's wrapper lives as long as this one
        self._doc = doc
        self._highlighter = Highlighter(doc, self._colors(), size)
        doc.contentsChanged.connect(self._scan)
        self._scan()

    @Slot(int)
    def setCursor(self, position):
        """The cursor moved: the marks of its line show, those of the line it left hide again."""
        if self._highlighter is None or self._doc is None:
            return
        block = self._doc.findBlock(position) if position >= 0 else None
        number = block.blockNumber() if block is not None and block.isValid() else -1
        old = self._highlighter.active
        if number == old:
            return
        self._highlighter.active = number
        for n in (old, number):
            b = self._doc.findBlockByNumber(n)
            if b.isValid():
                self._highlighter.rehighlightBlock(b)

    @Slot(str, int)
    def setFind(self, text, current):
        """Every match of text in saffron, the one at current (a position, or -1) deeper; "" takes them off."""
        if self._highlighter is None:
            return
        text = fold_chars(text or "")
        if text == self._highlighter.find and current == self._highlighter.current:
            return
        self._highlighter.find = text
        self._highlighter.current = current
        self._highlighter.rehighlight()

    @Slot(str, result="QVariantList")
    def matches(self, text):
        """Where text is in the note (accents and case aside): the positions of its matches."""
        if self._doc is None or not text:
            return []
        needle, hay = fold_chars(text), fold_chars(self._doc.toPlainText())
        out, at = [], hay.find(needle)
        while at >= 0 and len(out) < 2000:
            out.append(at)
            at = hay.find(needle, at + len(needle))
        return out

    @Slot(int)
    def setSize(self, size):
        if self._highlighter and size != self._size:
            self._size = size
            self._highlighter.size = size
            self._highlighter.rehighlight()

    def _restyle(self):
        if self._highlighter:
            self._highlighter.colors = self._colors()
            self._highlighter.rehighlight()

    def _scan(self):
        if self._doc is None:
            return
        try:
            self._doc = self._quick_doc.textDocument()
        except RuntimeError:
            return
        marks, pos, inside = [], 0, False
        for line in self._doc.toPlainText().split("\n"):
            if FENCE.match(line):
                inside = not inside
            elif not inside:
                for link in LINK.finditer(line):
                    if link.group(1) and not re.match(r"^[a-z][a-z0-9+.-]*:", link.group(3), re.I):
                        marks.append({"pos": pos + link.start(), "kind": "image", "indent": 0, "icon": "image",
                                      "url": link.group(3), "label": link.group(2)})
                    elif not link.group(1) and link.group(2) and links.is_link(link.group(3)):
                        marks.append({"pos": pos + link.start(), "kind": "link", "indent": 0,
                                      "icon": links.ICONS[links.parse(link.group(3))[0]], "url": link.group(3)})
                m = CHECK.match(line)
                if m:
                    marks.append({"pos": pos + len(m.group(1)), "kind": "done" if m.group(3) in "xX" else "check",
                                  "indent": len(m.group(1))})
                else:
                    m = BULLET.match(line)
                    if m:
                        marks.append({"pos": pos + len(m.group(1)), "kind": "bullet", "indent": len(m.group(1))})
            pos += len(line) + 1
        if marks != self._marks:
            self._marks = marks
            self.marksChanged.emit()

    @Property("QVariantList", notify=marksChanged)
    def marks(self):
        return self._marks
