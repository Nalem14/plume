#!/usr/bin/env python3
"""The files of Plume, laid out as in /usr/share on Orneos OS, for the packages (plume.spec, the .rpm).

    <out>/share/orneos/              the shared code (system, cloud, account, tray, updater…) + apps.json
    <out>/share/orneos-plume/        Plume; orneos-notes/, orneos-tasks/, orneos-passwords/, orneos-ornis/, orneos-meet/, orneos-photos/: its modules
    <out>/share/icons/hicolor/scalable/apps/eu.orneos.*.svg   the icons of the grid of apps (os/tools/apps.py)
    <out>/share/fonts/orneos/        Schibsted Grotesk, the same files and checksums as os/Containerfile
    <out>/icons/plume.{png,ico,icns} the app's icon for Windows, macOS and Linux

Usage: python plume/stage.py <out>   (any system: Python, PySide6 and Pillow from plume/requirements-build.txt)
"""
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SOURCES = REPO / "os" / "files" / "usr" / "share"
APPS = ("orneos", "orneos-plume", "orneos-notes", "orneos-tasks", "orneos-passwords", "orneos-ornis", "orneos-meet", "orneos-photos")
# only on Orneos OS (Firefox policies, KDE accounts, Plasma widgets): not in the packages
LEFT_OUT = {"firefox", "accounts", "widgets-qml", "widgets.py", "osupdate.py", "__pycache__"}


def copy_apps(share):
    for name in APPS:
        shutil.copytree(SOURCES / name, share / name, ignore=lambda _dir, names: [n for n in names if n in LEFT_OUT])


def copy_helpers(share):
    target = share / "orneos" / "helpers"
    target.mkdir(parents=True, exist_ok=True)
    for name in ("consent", "computer"):
        shutil.copy2(REPO / "os/files/usr/libexec" / ("orneos-ornis-" + name), target)


def catalogue(share):
    """apps.json and the icons, written by the same script as the start menu of Orneos OS."""
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run([sys.executable, str(REPO / "os" / "tools" / "apps.py"),
                        str(REPO / "public_html" / "assets" / "img" / "icons.svg"), tmp], check=True)
        root = Path(tmp) / "usr" / "share"
        shutil.copy2(root / "orneos" / "apps.json", share / "orneos" / "apps.json")
        icons = share / "icons" / "hicolor" / "scalable" / "apps"
        icons.mkdir(parents=True, exist_ok=True)
        for svg in (root / "icons" / "hicolor" / "scalable" / "apps").glob("eu.orneos.*.svg"):
            shutil.copy2(svg, icons / svg.name)


def fonts(share):
    """The fonts of os/Containerfile (ADD --checksum lines): one list for the system and for Plume."""
    text = (REPO / "os" / "Containerfile").read_text(encoding="utf-8")
    commit = re.search(r"^ARG FONTS_COMMIT=(\S+)", text, re.M).group(1)
    target = share / "fonts" / "orneos"
    target.mkdir(parents=True, exist_ok=True)
    for checksum, url, dest in re.findall(r"ADD --checksum=sha256:(\w+) \\\n\s+(\S+) (\S+)", text):
        if "${FONTS_COMMIT}" not in url:          # another download of the image (Klassy…)
            continue
        url = url.replace("${FONTS_COMMIT}", commit)
        with urllib.request.urlopen(url, timeout=60) as res:
            data = res.read()
        if hashlib.sha256(data).hexdigest() != checksum:
            sys.exit(f"stage: wrong checksum for {url}")
        (target / Path(dest).name).write_bytes(data)


def app_icons(share, out):
    """The tile of Plume (os/tools/apps.py) as PNG, .ico (Windows) and .icns (macOS)."""
    from PIL import Image  # noqa: PLC0415 - build only
    from PySide6.QtCore import QRectF  # noqa: PLC0415
    from PySide6.QtGui import QGuiApplication, QImage, QPainter  # noqa: PLC0415
    from PySide6.QtSvg import QSvgRenderer  # noqa: PLC0415

    QGuiApplication.instance() or QGuiApplication(["stage", "-platform", "offscreen"])
    renderer = QSvgRenderer(str(share / "icons" / "hicolor" / "scalable" / "apps" / "eu.orneos.plume.svg"))
    out.mkdir(parents=True, exist_ok=True)
    image = QImage(1024, 1024, QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    # macOS draws app icons on a grid: the tile fills 824 of 1024 points, centred
    renderer.render(painter, QRectF(100, 100, 824, 824))
    painter.end()
    image.save(str(out / "plume-1024.png"))
    big = Image.open(out / "plume-1024.png")
    big.save(out / "plume.icns")
    big.crop((100, 100, 924, 924)).resize((512, 512), Image.LANCZOS).save(out / "plume.png")
    big.crop((100, 100, 924, 924)).resize((256, 256), Image.LANCZOS).save(
        out / "plume.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


def main():
    out = Path(sys.argv[1]).resolve()
    share = out / "share"
    if share.exists():
        shutil.rmtree(share)
    share.mkdir(parents=True)
    copy_apps(share)
    copy_helpers(share)
    catalogue(share)
    fonts(share)
    app_icons(share, out / "icons")
    version = re.search(r'VERSION = "([^"]+)"', (share / "orneos-plume" / "plume_core" / "__init__.py").read_text(encoding="utf-8"))
    (out / "version").write_text(version.group(1) + "\n")
    print(json.dumps({"share": str(share), "version": version.group(1)}))


if __name__ == "__main__":
    main()
