"""Ornis palette for Mots de passe, light and dark (the same tokens as Plume and orneosui.py), following the session.

The window chrome (header, side panels) takes the palette's window colour, so it meets the Klassy title
bar, which matches the application colour, without a seam. Everything else comes from the tokens below.
PASSWORDS_THEME=light|dark forces one (tests, screenshots).
"""
import os

from PySide6.QtCore import QObject, Property, Signal
from PySide6.QtGui import QGuiApplication

from qmlvalue import js_property

# ornis-tokens:begin (generated from design/tokens.json by tools/design-tokens.py, do not edit)
LIGHT = {
    "chrome": "#EDF0F5", "bg": "#F5F6F9", "card": "#FFFFFF", "line": "#E1E5EE", "hairline": "#E9ECF2",
    "text": "#0F2440", "body": "#0F2440", "muted": "#5B6B82", "faint": "#637289", "action": "#002FA7",
    "actionHover": "#00238A", "actionText": "#FFFFFF", "tint": "#DCE3F7", "tintText": "#002FA7",
    "accent": "#002FA7", "accentLine": "#C9D3EC", "hover": "#E4E8F0", "field": "#FFFFFF", "rail": "#002FA7",
    "railText": "#FFFFFF", "railMark": "#FFFFFF", "railMarkText": "#002FA7", "saffron": "#F0A202",
    "saffronText": "#0F2440", "saffronTint": "#FDF1D6", "saffronInk": "#7A5200", "ok": "#2F7D6D",
    "okTint": "#E2F1EE", "okInk": "#1F5A4D", "danger": "#C8381E", "dangerTint": "#FBE7E3",
    "overlay": "#FFFFFF", "overlayLine": "#D5DBE6", "shadow": "#290F2440", "scrim": "#660A1424",
    "tag1": "#C8381E", "tag2": "#002FA7", "tag3": "#2F7D6D", "tag4": "#E09600", "tag5": "#6E5BB8",
    "famCommunicate": "#002FA7", "famDocs": "#2F7D6D", "famOrganize": "#8A5A00", "famMedia": "#1A5F7A",
    "famTools": "#0F2440", "famSpace": "#7A3B6E", "elev": "#240F2440", "elevEdge": "#00FFFFFF",
}
DARK = {
    "chrome": "#0A1424", "bg": "#0A1424", "card": "#101D33", "line": "#1E2E4A", "hairline": "#1A2840",
    "text": "#E8ECF3", "body": "#DDE3EE", "muted": "#9AA8BF", "faint": "#77859C", "action": "#7D93FF",
    "actionHover": "#9AABFF", "actionText": "#0A1424", "tint": "#1B2C55", "tintText": "#C3CEFF",
    "accent": "#9AABFF", "accentLine": "#2A3D6B", "hover": "#16233A", "field": "#0D1A2E", "rail": "#0A2A8C",
    "railText": "#FFFFFF", "railMark": "#E8ECF3", "railMarkText": "#0A2A8C", "saffron": "#F0A202",
    "saffronText": "#0A1424", "saffronTint": "#3A2C0C", "saffronInk": "#F5C04A", "ok": "#5FC2AC",
    "okTint": "#123129", "okInk": "#8FDCC9", "danger": "#FF7A5C", "dangerTint": "#3A1A16",
    "overlay": "#132240", "overlayLine": "#2A3B5C", "shadow": "#80000000", "scrim": "#99050A12",
    "tag1": "#FF7A5C", "tag2": "#7D93FF", "tag3": "#5FC2AC", "tag4": "#F0A202", "tag5": "#A897F0",
    "famCommunicate": "#8A9EFF", "famDocs": "#5CC2AC", "famOrganize": "#F2B13A", "famMedia": "#7EB8CC",
    "famTools": "#C5D0E6", "famSpace": "#DDA8D3", "elev": "#A0000000", "elevEdge": "#14FFFFFF",
}
# ornis-tokens:end


class Theme(QObject):
    changed = Signal()

    def __init__(self, app):
        super().__init__()
        self._forced = os.environ.get("PASSWORDS_THEME", "")
        self._dark = False
        self._c = dict(LIGHT)
        # Follow the Plasma colour scheme through signals. An application-wide eventFilter in Python sees every
        # event of every object: PySide 6.11 crashed on the first focus change with one.
        app.styleHints().colorSchemeChanged.connect(lambda _scheme: self._refresh())
        if hasattr(app, "paletteChanged"):
            app.paletteChanged.connect(lambda _palette: self._refresh())
        self._refresh()

    def _refresh(self):
        window = QGuiApplication.palette().window().color()
        dark = self._forced == "dark" if self._forced in ("light", "dark") else window.lightness() < 128
        c = dict(DARK if dark else LIGHT)
        if not self._forced:
            c["chrome"] = window.name()
        if dark != self._dark or c != self._c:
            self._dark, self._c = dark, c
            self.changed.emit()

    @Property(bool, notify=changed)
    def dark(self):
        return self._dark

    @js_property(notify=changed)
    def c(self):
        return self._c
