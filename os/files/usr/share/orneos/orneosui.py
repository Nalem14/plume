"""Ornis look for the Orneos OS system windows (updates, package installer): one palette, one set of parts.

Light: Brume background, white cards, Klein actions. Dark: Nuit de Prusse. The header is the Klein flat
area, the signature of the brand; the rest of the window stays calm. Saffron marks what is active or
needs attention, never decoration.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QFrame, QHBoxLayout, QLabel, QLayout, QProgressBar, QPushButton, QScrollArea,
    QSizePolicy, QToolButton, QVBoxLayout, QWidget,
)

FONT = "Schibsted Grotesk"
MARK = "/usr/share/orneos-connect/mark-inv.svg"
WIDTH = 540

# ornis-tokens:begin (generated from design/tokens.json by tools/design-tokens.py, do not edit)
LIGHT = {
    "bg": "#F5F6F9", "card": "#FFFFFF", "line": "#E1E5EE", "text": "#0F2440", "muted": "#5B6B82",
    "action": "#002FA7", "action_hover": "#00238A", "action_text": "#FFFFFF", "tint": "#DCE3F7",
    "saffron": "#F0A202", "ok": "#2F7D6D", "ok_tint": "#E2F1EE", "danger": "#C8381E",
    "danger_tint": "#FBE7E3", "warn_tint": "#FDF1D6", "header": "#002FA7", "field": "#FFFFFF",
}
DARK = {
    "bg": "#0A1424", "card": "#101D33", "line": "#1E2E4A", "text": "#E8ECF3", "muted": "#9AA8BF",
    "action": "#7D93FF", "action_hover": "#9AABFF", "action_text": "#0A1424", "tint": "#1B2C55",
    "saffron": "#F0A202", "ok": "#5FC2AC", "ok_tint": "#123129", "danger": "#FF7A5C",
    "danger_tint": "#3A1A16", "warn_tint": "#3A2C0C", "header": "#0A2A8C", "field": "#0D1A2E",
}
# ornis-tokens:end


def is_dark(app: QApplication) -> bool:
    return app.palette().window().color().lightness() < 128


def tokens(app: QApplication | None = None) -> dict[str, str]:
    app = app or QApplication.instance()
    return DARK if app and is_dark(app) else LIGHT


def setup(app: QApplication) -> dict[str, str]:
    """Font and style sheet for the whole application; returns the palette in use."""
    if FONT in QFontDatabase.families():
        font = QFont(FONT)
        font.setPointSizeF(10.5)
        app.setFont(font)
    c = tokens(app)
    app.setStyleSheet(f"""
        QDialog, QWidget#page {{ background: {c['bg']}; color: {c['text']}; }}
        QLabel {{ color: {c['text']}; background: transparent; }}
        QLabel[role="muted"] {{ color: {c['muted']}; }}
        QLabel[role="title"] {{ font-size: 15px; font-weight: 600; }}
        QLabel[role="section"] {{ color: {c['muted']}; font-size: 11px; font-weight: 600; letter-spacing: 0.6px; }}
        QFrame#card {{ background: {c['card']}; border: 1px solid {c['line']}; border-radius: 12px; }}
        QFrame#hairline {{ background: {c['line']}; max-height: 1px; min-height: 1px; border: none; }}
        QPushButton {{
            background: transparent; color: {c['action']}; border: 1px solid {c['line']};
            border-radius: 8px; padding: 7px 14px; font-weight: 600;
        }}
        QPushButton:hover {{ background: {c['tint']}; border-color: {c['tint']}; }}
        QPushButton:focus {{ outline: none; border: 2px solid {c['saffron']}; }}
        QPushButton:disabled {{ color: {c['muted']}; border-color: {c['line']}; background: transparent; }}
        QPushButton[kind="primary"] {{ background: {c['action']}; color: {c['action_text']}; border: none; }}
        QPushButton[kind="primary"]:hover {{ background: {c['action_hover']}; }}
        QPushButton[kind="primary"]:disabled {{ background: {c['line']}; color: {c['muted']}; }}
        QPushButton[kind="danger"] {{ color: {c['danger']}; }}
        QPushButton[kind="danger"]:hover {{ background: {c['danger_tint']}; border-color: {c['danger_tint']}; }}
        QPushButton[kind="quiet"] {{ border: none; padding: 6px 8px; }}
        QPushButton[kind="segment"] {{
            border: none; border-radius: 7px; padding: 7px 12px; color: {c['muted']}; background: transparent;
        }}
        QPushButton[kind="segment"]:checked {{ background: {c['card']}; color: {c['text']}; }}
        QPushButton[kind="segment"]:hover:!checked {{ color: {c['text']}; }}
        QFrame#segments {{ background: {c['bg']}; border: 1px solid {c['line']}; border-radius: 9px; }}
        QToolButton#disclosure {{
            border: none; color: {c['muted']}; font-weight: 600; padding: 4px 2px; background: transparent;
        }}
        QToolButton#disclosure:hover {{ color: {c['text']}; }}
        QComboBox {{
            background: {c['field']}; color: {c['text']}; border: 1px solid {c['line']}; border-radius: 8px;
            padding: 7px 10px;
        }}
        QComboBox:focus {{ border: 2px solid {c['saffron']}; }}
        QComboBox::drop-down {{ border: none; width: 26px; }}
        QComboBox::down-arrow {{ image: url(/usr/share/orneos/ui/chevron-down.svg); width: 12px; height: 12px; }}
        QComboBox QAbstractItemView {{
            background: {c['card']}; color: {c['text']}; selection-background-color: {c['tint']};
            selection-color: {c['text']}; border: 1px solid {c['line']}; outline: none;
        }}
        QProgressBar {{ background: {c['line']}; border: none; border-radius: 2px; max-height: 4px; }}
        QProgressBar::chunk {{ background: {c['saffron']}; border-radius: 2px; }}
        QFrame#banner {{ border-radius: 10px; border: none; }}
        QFrame#banner[tone="ok"] {{ background: {c['ok_tint']}; }}
        QFrame#banner[tone="danger"] {{ background: {c['danger_tint']}; }}
        QFrame#banner[tone="warn"] {{ background: {c['warn_tint']}; }}
        QFrame#banner[tone="info"] {{ background: {c['tint']}; }}
        QScrollArea#pagescroll, QScrollArea#pagescroll > QWidget > QWidget#page {{ background: {c['bg']}; border: none; }}
        QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px 2px; }}
        QScrollBar::handle:vertical {{ background: {c['line']}; border-radius: 3px; min-height: 32px; }}
        QScrollBar::handle:vertical:hover {{ background: {c['muted']}; }}
        QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ background: none; height: 0; }}
        QPlainTextEdit {{
            background: {c['field']}; color: {c['muted']}; border: 1px solid {c['line']}; border-radius: 8px;
            font-family: "JetBrains Mono"; font-size: 11px;
        }}
    """)
    return c


def repolish(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def label(text: str = "", role: str | None = None, wrap: bool = True) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(wrap)
    lbl.setTextFormat(Qt.PlainText)
    if role:
        lbl.setProperty("role", role)
    return lbl


def button(text: str, kind: str | None = None) -> QPushButton:
    btn = QPushButton(text)
    btn.setCursor(Qt.PointingHandCursor)
    if kind:
        btn.setProperty("kind", kind)
    return btn


def hairline() -> QFrame:
    line = QFrame()
    line.setObjectName("hairline")
    return line


class Card(QFrame):
    """White (or Prussian night) surface with an optional small uppercase heading."""

    def __init__(self, heading: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(18, 16, 18, 16)
        self.body.setSpacing(10)
        if heading:
            self.body.addWidget(label(heading.upper(), "section"))


class Header(QWidget):
    """Klein flat area with a faint graticule: the mark, a title and a line of facts."""

    def __init__(self, title: str, subtitle: str = "", icon: str = "orneos", parent: QWidget | None = None):
        super().__init__(parent)
        self._color = QColor(tokens()["header"])
        self.setFixedHeight(96)
        row = QHBoxLayout(self)
        row.setContentsMargins(24, 18, 24, 18)
        row.setSpacing(16)
        self.icon = QLabel()
        self.icon.setFixedSize(48, 48)
        self.set_icon(icon)
        row.addWidget(self.icon)
        col = QVBoxLayout()
        col.setSpacing(2)
        self.title = QLabel(title)
        self.title.setStyleSheet("color: white; font-size: 20px; font-weight: 600;")
        self.subtitle = QLabel(subtitle)
        self.subtitle.setStyleSheet("color: rgba(255,255,255,0.78);")
        self.subtitle.setWordWrap(True)
        col.addStretch(1)
        col.addWidget(self.title)
        col.addWidget(self.subtitle)
        col.addStretch(1)
        row.addLayout(col, 1)

    def set_icon(self, name: str) -> None:
        # The white mark reads on Klein; a themed icon (a Klein tile) would melt into the header
        icon = QIcon(MARK) if name == "orneos" and Path(MARK).is_file() else QIcon.fromTheme(name)
        if not icon.isNull():
            self.icon.setPixmap(icon.pixmap(QSize(44, 44), self.devicePixelRatioF()))

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), self._color)
        # Graticule: meridians and parallels, white at 8 %, only on the Klein area
        p.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor(255, 255, 255, 20))
        pen.setWidthF(1.0)
        p.setPen(pen)
        w, h = self.width(), self.height()
        cx = w * 0.82
        for i in range(1, 9):
            r = 28 * i
            p.drawEllipse(int(cx - r), int(h * 0.5 - r), int(2 * r), int(2 * r))
        for x in range(0, w, 56):
            p.drawLine(x, 0, x, h)
        # Saffron marker under the area, 3 px, as under the active item everywhere else
        p.fillRect(0, h - 3, 72, 3, QColor(tokens()["saffron"]))


class Segments(QFrame):
    """Segmented control (two to four exclusive choices)."""

    def __init__(self, choices: list[tuple[str, str]], parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("segments")
        row = QHBoxLayout(self)
        row.setContentsMargins(3, 3, 3, 3)
        row.setSpacing(2)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self._keys: dict[QPushButton, str] = {}
        for key, text in choices:
            btn = button(text, "segment")
            btn.setCheckable(True)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self.group.addButton(btn)
            self._keys[btn] = key
            row.addWidget(btn)

    def value(self) -> str:
        btn = self.group.checkedButton()
        return self._keys.get(btn, "") if btn else ""

    def set_value(self, key: str) -> None:
        for btn, k in self._keys.items():
            btn.blockSignals(True)
            btn.setChecked(k == key)
            btn.blockSignals(False)


class Banner(QFrame):
    """Inline state: ok, info, warn, danger. Replaces message boxes."""

    GLYPHS = {"ok": "✓", "info": "ℹ", "warn": "!", "danger": "✕"}

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("banner")
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 10, 14, 10)
        row.setSpacing(10)
        self.glyph = QLabel()
        self.glyph.setFixedWidth(16)
        self.glyph.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        row.addWidget(self.glyph)
        self.text = label()
        row.addWidget(self.text, 1)
        self.hide()

    def show_message(self, tone: str, text: str) -> None:
        c = tokens()
        color = {"ok": c["ok"], "danger": c["danger"], "warn": c["text"], "info": c["action"]}[tone]
        self.setProperty("tone", tone)
        self.glyph.setText(self.GLYPHS[tone])
        self.glyph.setStyleSheet(f"color: {color}; font-weight: 700;")
        self.text.setText(text)
        repolish(self)
        self.show()


class Busy(QWidget):
    """A thin saffron progress line and a short status under it."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 2, 0, 0)
        col.setSpacing(6)
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        self.bar.setTextVisible(False)
        col.addWidget(self.bar)
        self.text = label("", "muted")
        col.addWidget(self.text)
        self.hide()

    def start(self, text: str) -> None:
        self.text.setText(text)
        self.show()

    def stop(self) -> None:
        self.hide()


class Disclosure(QWidget):
    """« Advanced ▸ » that unfolds its content in place, quietly."""

    def __init__(self, text: str, parent: QWidget | None = None):
        super().__init__(parent)
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(8)
        self.toggle = QToolButton()
        self.toggle.setObjectName("disclosure")
        self.toggle.setText(text)
        self.toggle.setCheckable(True)
        self.toggle.setCursor(Qt.PointingHandCursor)
        self.toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toggle.setArrowType(Qt.RightArrow)
        col.addWidget(self.toggle, 0, Qt.AlignLeft)
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(10)
        self.content.setVisible(False)
        col.addWidget(self.content)
        self.toggle.toggled.connect(self._on_toggle)

    def _on_toggle(self, on: bool) -> None:
        self.toggle.setArrowType(Qt.DownArrow if on else Qt.RightArrow)
        self.content.setVisible(on)
        win = self.window()
        if win:
            fit(win)


def fit(window: QWidget) -> None:
    """Fixed width; height from the content, but never taller than the screen: past that, the page scrolls.

    Word-wrapped labels need a known width to measure, hence the fixed width.
    """
    window.setFixedWidth(WIDTH)
    lay = window.layout()
    if lay is None:
        return
    lay.activate()
    body = window.findChild(QWidget, "page")
    area = window.findChild(QScrollArea, "pagescroll")
    if body is None or area is None:
        window.adjustSize()
        return
    blay = body.layout()
    blay.activate()
    natural_body = blay.totalHeightForWidth(WIDTH) if blay.hasHeightForWidth() else blay.totalSizeHint().height()
    others = sum(lay.itemAt(i).widget().sizeHint().height() for i in range(lay.count())
                 if lay.itemAt(i).widget() is not None and lay.itemAt(i).widget() is not area)
    screen = window.screen() or QApplication.primaryScreen()
    cap = screen.availableGeometry().height() - 60 if screen else 900
    height = min(others + natural_body, cap)
    area.setMinimumHeight(0)
    window.setFixedHeight(max(height, 200))


def page() -> tuple[QScrollArea, QVBoxLayout]:
    """The body under the header, with the window margins, in a scroll area that only scrolls when needed."""
    body = QWidget()
    body.setObjectName("page")
    col = QVBoxLayout(body)
    col.setContentsMargins(20, 18, 20, 18)
    col.setSpacing(14)
    area = QScrollArea()
    area.setObjectName("pagescroll")
    area.setWidget(body)
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    return area, col
