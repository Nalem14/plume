"""Pictures of Meet for QML (image://meet/…), fetched with the account and kept on disk:

  image://meet/user/<user id>             a person's photo (the cloud's avatar, 1 day)
  image://meet/room/<token>/<version>     a conversation's picture (kept until its version changes)
  image://meet/preview/<file id>          a shared file's preview (kept)
  image://meet/ref/<address, quoted>      the picture of a link's preview (the cloud's references, kept)
  …/dark                                  a picture for a dark background (the cloud draws both)

Fetched on a small pool of threads; the cache is CACHE/meet (trimmed past 150 MB, oldest first). Photos and
pictures come round, drawn here (no shader effect in the view); an SVG is drawn at the size asked.
"""
import hashlib
import html
import re
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QSize, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QImage, QImageReader, QPainter, QPainterPath
from PySide6.QtQuick import QQuickAsyncImageProvider, QQuickImageResponse, QQuickTextureFactory

import system

CACHE = system.CACHE / "meet"
LIMIT = 150 * 1024 * 1024
AVATAR_TTL = 24 * 3600


def trim(limit=LIMIT):
    try:
        files = sorted((p for p in CACHE.iterdir() if p.is_file()), key=lambda p: p.stat().st_mtime)
        total = sum(p.stat().st_size for p in files)
        for p in files:
            if total <= limit:
                break
            total -= p.stat().st_size
            p.unlink(missing_ok=True)
    except OSError:
        pass


def emoji_avatar(data, side):
    """Talk's picture of a conversation named by an emoji (the note to self: 📝) is an SVG with a <text>
    centred by text-anchor, which Qt's SVG ignores (the emoji lands on the left, cut): drawn here instead."""
    if b"<text" not in data[:2000]:
        return None
    text = data.decode("utf-8", "ignore")
    letter = re.search(r"<text[^>]*>([^<]+)</text>", text)
    fill = re.search(r'<rect[^>]*fill="(#[0-9a-fA-F]{3,8})"', text)
    if not letter:
        return None
    side = side or 256
    out = QImage(side, side, QImage.Format.Format_ARGB32_Premultiplied)
    out.fill(QColor(fill.group(1)) if fill else Qt.GlobalColor.transparent)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    font = QFont()
    font.setPixelSize(int(side * 0.5))
    painter.setFont(font)
    painter.drawText(out.rect(), Qt.AlignmentFlag.AlignCenter, html.unescape(letter.group(1).strip()))
    painter.end()
    return out


def decode(data, size, round_=False):
    """Bytes to a QImage at about `size` (SVG drawn at that size), cut in a circle for a photo."""
    side = max(size.width(), size.height()) if size.isValid() and size.width() > 0 else 0
    drawn = emoji_avatar(data, side) if data[:200].lstrip().startswith((b"<?xml", b"<svg")) else None
    if drawn is not None:
        data = None
    buffer = QBuffer()
    if drawn is not None:
        image = drawn
    else:
        buffer.setData(QByteArray(data))
        buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        reader = QImageReader(buffer)
        if reader.format() == b"svg" or not side:
            side = side or 256
            reader.setScaledSize(QSize(side, side))
        image = reader.read()
    if image.isNull() or not round_:
        return image
    side = min(image.width(), image.height())
    if size.isValid() and size.width() > 0:
        side = min(side, max(size.width(), size.height()))
    square = image.scaled(side, side, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                          Qt.TransformationMode.SmoothTransformation)
    out = QImage(side, side, QImage.Format.Format_ARGB32_Premultiplied)
    out.fill(Qt.GlobalColor.transparent)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addEllipse(0, 0, side, side)
    painter.setClipPath(path)
    painter.drawImage((side - square.width()) // 2, (side - square.height()) // 2, square)
    painter.end()
    return out


class _Response(QQuickImageResponse):
    def __init__(self, requested):
        super().__init__()
        self._image = QImage()
        self._requested = requested
        self.size = QSize(requested)

    def deliver(self, image):
        if image is not None and not image.isNull():
            req = self._requested
            if req.isValid() and req.width() > 0 and req.height() > 0 and \
                    (image.width() > req.width() * 1.5 or image.height() > req.height() * 1.5):
                image = image.scaled(req, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self._image = image
        self.finished.emit()

    def textureFactory(self):
        factory = QQuickTextureFactory.textureFactoryForImage(self._image)
        self._image = QImage()
        return factory


class Provider(QQuickAsyncImageProvider):
    def __init__(self, talk_fn):
        super().__init__()
        self._talk = talk_fn               # () -> api.Talk or None (the account can change)
        self._pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="meet-images")
        self._alive = set()
        CACHE.mkdir(parents=True, exist_ok=True)

    def requestImageResponse(self, address, requested):
        response = _Response(QSize(requested))
        self._alive.add(response)
        response.finished.connect(lambda: self._alive.discard(response))
        self._pool.submit(self._load, address, response)
        return response

    def _load(self, address, response):
        path = CACHE / hashlib.sha1(address.encode()).hexdigest()
        fresh = path.exists() and (not address.startswith("user/") or time.time() - path.stat().st_mtime < AVATAR_TTL)
        data = None
        if fresh:
            try:
                data = path.read_bytes()
            except OSError:
                data = None
        if data is None:
            data = self._fetch(address)
            if data:
                try:
                    path.write_bytes(data)
                except OSError:
                    pass
            elif path.exists():                # offline: the old copy is better than nothing
                data = path.read_bytes()
        image = decode(data, response.size, round_=not address.startswith(("preview/", "ref/"))) if data else QImage()
        response.deliver(image)

    def _fetch(self, address):
        talk = self._talk()
        if talk is None:
            return None
        parts = address.split("/")
        kind = parts[0]
        dark = parts[-1] == "dark"
        if kind == "user" and len(parts) >= 2:
            status, raw = talk.user_avatar(urllib.parse.unquote(parts[1]), 256, dark)
        elif kind == "room" and len(parts) >= 2:
            status, raw = talk.avatar(parts[1], dark)
        elif kind == "ref" and len(parts) >= 2:
            url = urllib.parse.unquote(parts[1])
            if not url.startswith(talk.server + "/"):       # the account's password goes to our cloud only
                return None
            status, raw = talk._call(url, headers={"Accept": "image/*"})
        elif kind == "preview" and len(parts) >= 2:
            query = urllib.parse.urlencode({"fileId": parts[1], "x": 1024, "y": 1024, "a": 1, "forceIcon": 0})
            status, raw = talk._call(f"{talk.server}/index.php/core/preview?{query}", headers={"Accept": "image/*"})
        else:
            return None
        return raw if status == 200 and raw else None
