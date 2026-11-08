"""QR codes: drawn (a Wi-Fi network to join, a verification code to move to a phone) and read (the setup
code a site shows when turning on two-factor authentication).

Reading looks at the screen, like macOS: Spectacle takes a picture of every screen in the background, zbarimg
finds the code, and the picture is deleted at once. An image in the clipboard works too.
"""
import os
import shutil
import subprocess
import tempfile

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtGui import QGuiApplication


def matrix(text):
    """Rows of "0"/"1" (dark modules), with no margin: the window draws them."""
    try:
        import qrcode
    except ImportError:
        return []
    code = qrcode.QRCode(border=0, error_correction=qrcode.constants.ERROR_CORRECT_M)
    code.add_data(text)
    code.make(fit=True)
    return ["".join("1" if cell else "0" for cell in row) for row in code.get_matrix()]


def decode(path):
    """The texts of the QR codes in an image file."""
    if not shutil.which("zbarimg"):
        return []
    try:
        res = subprocess.run(["zbarimg", "--raw", "-q", "-Sdisable", "-Sqrcode.enable", path],
                             capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [line.strip() for line in res.stdout.splitlines() if line.strip()]


class Scanner(QObject):
    found = Signal(str, str)          # how ("screen" | "clipboard"), the otpauth:// text ("" when none)

    @Slot(result=bool)
    def canScreen(self):
        return bool(shutil.which("spectacle") and shutil.which("zbarimg"))

    @Slot()
    def screen(self):
        """Every screen, in the background (no window, no sound, no notification)."""
        import threading

        def run():
            fd, path = tempfile.mkstemp(prefix="orneos-qr-", suffix=".png")
            os.close(fd)
            try:
                subprocess.run(["spectacle", "-b", "-n", "-f", "-o", path], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=20)
                texts = decode(path)
            except (OSError, subprocess.TimeoutExpired):
                texts = []
            finally:
                try:
                    os.unlink(path)
                except OSError:
                    pass
            self.found.emit("screen", next((t for t in texts if t.lower().startswith("otpauth://")), ""))
        threading.Thread(target=run, daemon=True).start()

    @Slot()
    def clipboard(self):
        image = QGuiApplication.clipboard().image()
        text = QGuiApplication.clipboard().text().strip()
        if text.lower().startswith("otpauth://"):
            self.found.emit("clipboard", text)
            return
        if image.isNull():
            self.found.emit("clipboard", "")
            return
        fd, path = tempfile.mkstemp(prefix="orneos-qr-", suffix=".png")
        os.close(fd)
        try:
            image.save(path, "PNG")
            texts = decode(path)
        finally:
            os.unlink(path)
        self.found.emit("clipboard", next((t for t in texts if t.lower().startswith("otpauth://")), ""))

    @Slot(str, result="QVariantList")
    def matrix(self, text):
        return matrix(text)
