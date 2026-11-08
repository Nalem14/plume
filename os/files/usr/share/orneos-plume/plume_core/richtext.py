"""Formatted writing for the composer and the signature editor.

The QML TextArea (RichText) holds a QTextDocument; bold, italic and underline go through its
cursorSelection. What needs the document itself is here: lists, links, clearing the formatting, and
the HTML and plain text that leave with the message.
"""
import base64
import re
import time
import uuid

from PySide6.QtCore import QBuffer, QIODevice, QObject, QUrl, Slot
from PySide6.QtGui import (QColor, QGuiApplication, QImage, QTextCharFormat, QTextCursor, QTextDocument, QTextFormat,
                           QTextImageFormat, QTextListFormat)
from PySide6.QtQuick import QQuickTextDocument

import system
from plume_core import mime

# Pictures pasted in the composer (and those of a reopened draft) wait here as files: the editor shows them,
# and mime.build reads them from here only, as parts of the message. A week is kept, for drafts left open.
PASTED = system.CACHE / "plume-pasted"
SHOWN_WIDTH = 560          # a big screenshot is shown (and sent) at most this wide; the file keeps its pixels
DATA_IMG = re.compile(r"""(?is)(<img\b[^>]*?\bsrc\s*=\s*["'])(data:image/([a-z0-9.+-]+);base64,([^"']+))""")


def _document(handle):
    """The QTextDocument behind a TextArea's textDocument (QQuickTextDocument)."""
    return handle.textDocument()


def _cursor(doc, start, end):
    cursor = QTextCursor(doc)
    cursor.setPosition(max(0, min(start, end)))
    cursor.setPosition(max(start, end), QTextCursor.MoveMode.KeepAnchor)
    return cursor


def html_of(doc):
    """The body of the document as compact mail HTML (Qt's page, head and editor-only styles removed)."""
    page = doc.toHtml()
    if not doc.toPlainText().strip() and "<img" not in page:
        return ""
    match = re.search(r"(?is)<body[^>]*>(.*)</body>", page)
    body = match.group(1) if match else page
    body = re.sub(r"\s*-qt-[a-z-]+:[^;\"]*;?", "", body)
    body = re.sub(r"\s*(margin-(top|bottom|left|right)|text-indent):\s*0px;", "", body)
    body = re.sub(r'\s*style="\s*"', "", body)
    return body.strip()


def text_of(doc):
    """Plain text twin: list items keep a bullet or their number, quotes their "> ", links their address."""
    lines = []
    block = doc.begin()
    while block.isValid():
        parts = []
        iterator = block.begin()
        while not iterator.atEnd():
            fragment = iterator.fragment()
            if fragment.isValid():
                text = fragment.text()
                href = fragment.charFormat().anchorHref()
                parts.append(f"{text} <{href}>" if href and href not in text and not href.startswith("mailto:") else text)
            iterator += 1
        line = "".join(parts).replace(" ", "\n").replace("￼", "")
        listed = block.textList()
        if listed is not None:
            numbered = listed.format().style() in (QTextListFormat.Style.ListDecimal, QTextListFormat.Style.ListLowerAlpha)
            line = (f"{listed.itemNumber(block) + 1}. " if numbered else "• ") + line
        level = block.blockFormat().intProperty(QTextFormat.Property.BlockQuoteLevel)
        if level:
            line = "\n".join("> " * level + x for x in line.split("\n"))
        lines.append(line)
        block = block.next()
    return "\n".join(lines).strip("\n")


class RichText(QObject):
    @Slot(QQuickTextDocument, int, int, str)
    def toggleList(self, handle, start, end, style):
        """Bullets ("bullet") or numbers ("number") on the paragraphs of the selection; again to remove."""
        doc = _document(handle)
        cursor = _cursor(doc, start, end)
        wanted = QTextListFormat.Style.ListDecimal if style == "number" else QTextListFormat.Style.ListDisc
        current = cursor.currentList()
        cursor.beginEditBlock()
        if current is not None and current.format().style() == wanted:
            block = doc.findBlock(min(start, end))
            last = doc.findBlock(max(start, end))
            while block.isValid():
                if block.textList() is not None:
                    block.textList().remove(block)
                    fmt = block.blockFormat()
                    fmt.setIndent(0)
                    QTextCursor(block).setBlockFormat(fmt)
                if block == last:
                    break
                block = block.next()
        elif current is not None:
            fmt = current.format()
            fmt.setStyle(wanted)
            current.setFormat(fmt)
        else:
            fmt = QTextListFormat()
            fmt.setStyle(wanted)
            cursor.createList(fmt)
        cursor.endEditBlock()

    @Slot(QQuickTextDocument, int, result=str)
    def listAt(self, handle, position):
        """"bullet", "number" or "" for the paragraph at this position (toolbar state)."""
        doc = _document(handle)
        listed = doc.findBlock(position).textList()
        if listed is None:
            return ""
        return "number" if listed.format().style() == QTextListFormat.Style.ListDecimal else "bullet"

    @Slot(QQuickTextDocument, int, result=str)
    def linkAt(self, handle, position):
        doc = _document(handle)
        cursor = QTextCursor(doc)
        cursor.setPosition(position)
        return cursor.charFormat().anchorHref()

    @Slot(QQuickTextDocument, int, int, str, str)
    def setLink(self, handle, start, end, url, label):
        """Turn the selection into a link (or insert label as one); an empty url removes the link."""
        doc = _document(handle)
        url = url.strip()
        if url and not re.match(r"(?i)^(https?|mailto):", url):
            url = ("mailto:" if "@" in url and "/" not in url else "https://") + url
        cursor = _cursor(doc, start, end)
        fmt = QTextCharFormat()
        fmt.setAnchor(bool(url))
        fmt.setAnchorHref(url)
        if url:
            fmt.setForeground(QColor("#002FA7"))
            fmt.setFontUnderline(True)
        else:
            fmt.clearForeground()
            fmt.setFontUnderline(False)
        cursor.beginEditBlock()
        if start == end and url:
            cursor.insertText(label.strip() or url.removeprefix("mailto:"), fmt)
            cursor.setCharFormat(QTextCharFormat())
        else:
            cursor.mergeCharFormat(fmt)
        cursor.endEditBlock()

    @Slot(QQuickTextDocument, int, int)
    def clearFormat(self, handle, start, end):
        doc = _document(handle)
        cursor = _cursor(doc, start, end)
        cursor.setCharFormat(QTextCharFormat())

    @Slot(str, result=str)
    def markdownHtml(self, text):
        """What Ornis wrote (light Markdown: bold, lists, links) as HTML for the editor."""
        doc = QTextDocument()
        doc.setMarkdown(text, QTextDocument.MarkdownFeature.MarkdownDialectGitHub)
        return html_of(doc)

    @staticmethod
    def _keep(data, ext):
        """A picture's bytes as a file of PASTED (older ones cleared): its file:// URL."""
        PASTED.mkdir(parents=True, exist_ok=True)
        try:
            PASTED.chmod(0o700)
        except OSError:
            pass
        limit = time.time() - 7 * 86400
        for old in PASTED.iterdir():
            try:
                if old.stat().st_mtime < limit:
                    old.unlink()
            except OSError:
                pass
        path = PASTED / f"{uuid.uuid4().hex}.{ext}"
        path.write_bytes(data)
        return QUrl.fromLocalFile(str(path)).toString()

    @Slot(str, result=str)
    def prepare(self, page):
        """HTML for the editor: its data: pictures (a reopened draft, Ornis) as files, which it can show."""
        def swap(match):
            ext = {"jpeg": "jpg", "svg+xml": "svg"}.get(match.group(3).lower(), match.group(3).lower())
            try:
                data = base64.b64decode(match.group(4) + "=" * (-len(match.group(4)) % 4))
                return match.group(1) + self._keep(data, ext)
            except (ValueError, OSError):
                return match.group(0)
        return DATA_IMG.sub(swap, page or "") if "data:image/" in (page or "") else (page or "")

    @Slot(QQuickTextDocument, int, int, result=bool)
    def pasteImage(self, handle, start, end):
        """A picture of the clipboard (a screenshot, « Copier l'image » of a browser) into the text, in place
        of the selection. False when the clipboard holds no picture (the editor then pastes as usual)."""
        data = QGuiApplication.clipboard().mimeData()
        if data is None or not data.hasImage():
            return False
        image = QGuiApplication.clipboard().image()
        if image.isNull():
            return False
        raw, ext = None, "png"
        for kind, name in (("image/jpeg", "jpg"), ("image/png", "png"), ("image/gif", "gif"), ("image/webp", "webp")):
            if data.hasFormat(kind) and data.data(kind).size() > 0:
                raw, ext = bytes(data.data(kind).data()), name
                break
        if raw is None:
            buffer = QBuffer()
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            image.save(buffer, "PNG")
            raw = bytes(buffer.data().data())
            if len(raw) > 1_500_000 and not image.hasAlphaChannel():   # a photo: JPEG, ten times lighter
                buffer = QBuffer()
                buffer.open(QIODevice.OpenModeFlag.WriteOnly)
                image.save(buffer, "JPEG", 88)
                raw, ext = bytes(buffer.data().data()), "jpg"
        try:
            url = self._keep(raw, ext)
        except OSError:
            return False
        doc = _document(handle)
        doc.addResource(QTextDocument.ResourceType.ImageResource, QUrl(url), image)
        picture = QTextImageFormat()
        picture.setName(url)
        width = image.width() / max(1.0, image.devicePixelRatio())
        if width > SHOWN_WIDTH:
            picture.setWidth(SHOWN_WIDTH)
            picture.setHeight(round(image.height() * SHOWN_WIDTH / image.width()))
        cursor = _cursor(doc, start, end)
        cursor.insertImage(picture)
        return True

    @Slot(result=str)
    def designedClipboard(self):
        """A signature with a layout in the clipboard (the signature editor keeps it as it is), or ""."""
        data = QGuiApplication.clipboard().mimeData()
        if data is None or not data.hasHtml():
            return ""
        return mime.designed_signature(data.html())

    @Slot(result="QStringList")
    def clipboardFiles(self):
        """Files copied in the file manager (or anywhere): their file:// URLs, to attach them."""
        data = QGuiApplication.clipboard().mimeData()
        if data is None or not data.hasUrls():
            return []
        return [u.toString() for u in data.urls() if u.isLocalFile()]

    @Slot(QQuickTextDocument, result="QVariantMap")
    def export(self, handle):
        doc = _document(handle)
        return {"html": html_of(doc), "text": text_of(doc)}
