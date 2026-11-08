"""Plume in the tray (Windows, macOS, Linux without Orneos OS): it keeps running with its window closed, so the
reminders of Tâches and new mail still come; it shows them as notifications, and the unread count in its tooltip
and on the app's icon (Dock, taskbar). Closing the window hides it; « Quitter Plume » quits.
"""
from PySide6.QtCore import QByteArray, QObject, QRectF, Qt, Signal, Slot
from PySide6.QtGui import QAction, QGuiApplication, QIcon, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

import system

# The plume of the app's tile alone, black on transparent: macOS draws a menu bar icon as a template (in white on a
# dark bar, in black on a light one). Plume.app has no window icon (system.icon): the tray needs its own.
GLYPH = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><g fill="none" stroke="#000" stroke-width="1.9" '
         'stroke-linecap="square"><path d="M20 4C11 4 6 9 6 17M6 17c7 0 12-5 14-13M6 17l-2 3M9.5 13.5h5"/></g></svg>')


def tray_icon(fallback):
    """The menu bar's template icon on macOS; the app's icon elsewhere (or the plume if it has none)."""
    if not system.MACOS and not fallback.isNull():
        return fallback
    from PySide6.QtSvg import QSvgRenderer  # noqa: PLC0415
    renderer = QSvgRenderer(QByteArray(GLYPH.encode()))
    icon = QIcon()
    for size in (16, 18, 32, 36, 44):
        image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(painter, QRectF(0, 0, size, size))
        painter.end()
        icon.addPixmap(QPixmap.fromImage(image))
    if system.MACOS:
        icon.setIsMask(True)
    return icon


class Tray(QObject):
    # the mail's badge is written from a worker thread: everything reaches the tray through these
    _countArrived = Signal(int)
    _noteArrived = Signal(str, str, object)

    def __init__(self, texts, icon, show, actions, autostart=None):
        """show(): bring the window up; actions: [(text, callback)] between « Ouvrir » and the settings."""
        super().__init__()
        self._t = texts
        self._show = show
        self._on_click = None
        self._count = 0
        self._icon = QSystemTrayIcon(tray_icon(icon))
        self._menu = QMenu()
        self._menu.addAction(texts["tray_open"]).triggered.connect(show)
        self._menu.addSeparator()
        for text, callback in actions:
            self._menu.addAction(text).triggered.connect(callback)
        self._menu.addSeparator()
        # autostart: (read, write, changed) of the app, so the Settings' switch and this entry show the same thing
        read, write, changed = autostart or (system.autostart_enabled, system.set_autostart, None)
        self._autostart = QAction(texts["tray_autostart"], self._menu, checkable=True)
        self._autostart.setChecked(read())
        self._autostart.triggered.connect(write)

        def refresh():
            self._autostart.setChecked(read())
        if changed is not None:
            changed.connect(refresh)
        self._menu.aboutToShow.connect(refresh)
        self._menu.addAction(self._autostart)
        self._menu.addAction(texts["tray_quit"]).triggered.connect(QGuiApplication.quit)
        self._icon.setContextMenu(self._menu)
        self._icon.activated.connect(self._activated)
        self._icon.messageClicked.connect(self._clicked)
        self._icon.setToolTip("Plume")
        self._icon.show()
        self._countArrived.connect(self.set_count)
        self._noteArrived.connect(self._show_message)
        system.set_notifier(lambda title, body, on_click=None: self._noteArrived.emit(title, body, on_click))
        system.set_badge_hook(self._countArrived.emit)

    def _activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self._show()

    def _show_message(self, title, body, on_click=None):
        self._on_click = on_click
        self._icon.showMessage(title, body, self._icon.icon(), 8000)

    def _clicked(self):
        callback, self._on_click = self._on_click, None
        if callback:
            callback()
        else:
            self._show()

    def set_hint(self, hint):
        """A line under the name (the global shortcut of Ornis)."""
        self._hint = hint
        self._tip()

    def _tip(self):
        count = self._count
        tip = "Plume · " + self._t["unread"].replace("%1", str(count)) if count else "Plume"
        hint = getattr(self, "_hint", "")
        self._icon.setToolTip(tip + ("\n" + hint if hint else ""))

    @Slot(int)
    def set_count(self, count):
        if count == self._count:
            return
        self._count = count
        self._tip()
        app = QGuiApplication.instance()
        if hasattr(app, "setBadgeNumber"):              # Qt 6.5: the Dock (macOS), the taskbar (Windows)
            app.setBadgeNumber(count)
