# PyInstaller: Plume for Windows, macOS and Linux (AppImage, .deb), one folder (plus Plume.app on macOS).
# Run after stage.py: PLUME_STAGE=<stage dir> pyinstaller plume/plume.spec   (see .github/workflows/plume.yml)
#
# The apps are data (the tree of /usr/share, see launch.py), not frozen modules: PyInstaller only reads them
# to find what they import (Qt, the libraries, the standard library), then they are left out of its archive.
import os
import platform
import re
import sys
from pathlib import Path

STAGE = Path(os.environ.get("PLUME_STAGE") or "build/stage").resolve()
SHARE = STAGE / "share"
HERE = Path(SPECPATH)
VERSION = (STAGE / "version").read_text().strip()
TREES = ["orneos", "orneos-plume", "orneos-notes", "orneos-tasks", "orneos-passwords", "orneos-ornis", "orneos-meet", "orneos-photos"]


def ours():
    """Every module of the apps (top-level files and the *_core packages), to be followed but not frozen."""
    names = set()
    for tree in TREES:
        root = SHARE / tree
        for path in root.rglob("*.py"):
            parts = path.relative_to(root).with_suffix("").parts
            if parts[-1] == "__init__":
                parts = parts[:-1]
            if parts and all(re.fullmatch(r"\w+", p) for p in parts):
                names.add(".".join(parts))
    return names


OURS = ours()
TOPS = {name.split(".")[0] for name in OURS}

a = Analysis(
    [str(HERE / "launch.py")],
    pathex=[str(SHARE / tree) for tree in TREES],
    hiddenimports=sorted(OURS) + ["keyring.backends", "tzdata"],
    datas=[(str(SHARE), ".")],
    # PIL: only for the dock badge of KDE (cloud.py, skipped without it)
    excludes=["tkinter", "PIL", "PySide6.Qt3DCore", "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtGraphs",
              "PySide6.QtBluetooth", "PySide6.QtSensors", "PySide6.QtSerialPort",
              "PySide6.QtDesigner", "PySide6.QtHelp",
              "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtPdf", "PySide6.QtRemoteObjects", "PySide6.QtScxml"],
    noarchive=False,
)
# the apps run from their files (datas), as on Orneos OS
a.pure = [entry for entry in a.pure if entry[0].split(".")[0] not in TOPS]

# PySide6's hooks bring every QML module of Qt (3D, multimedia, charts…): only what the apps import stays.
# TextToSpeech stays (Ornis reads its answers aloud with the system's voices: SAPI/WinRT, macOS).
# Positioning and WebChannel stay: QtWebEngine needs them. Location stays (the Photothèque's map, OpenStreetMap
# tiles: the geoservices plugin). Same names on Linux (libQt6X.so), Windows (Qt6X.dll)
# and macOS (QtX.framework).
UNUSED = ("3D|Quick3D|Graphs|Charts|DataVisualization|MultimediaQuick|SpatialAudio|VirtualKeyboard"
          "|Sensors|Scxml|StateMachine|RemoteObjects|Test|QuickTest|WaylandCompositor|WebView|Bluetooth"
          "|Nfc|SerialPort|SerialBus|Designer|UiTools|Help|Sql|ShaderTools|Pdf|PdfQuick|LabsStyleKit|HttpServer|QmlLocalStorage"
          "|QuickControls2(?:Material|Universal|Imagine|FluentWinUI3)\\w*")
DROP = re.compile(
    rf"(?:^|[/\\])(?:lib)?Qt6?(?:{UNUSED})\w*(?:\.|[/\\]|$)"
    rf"|[/\\]qml[/\\](?:Qt3D|QtQuick3D|QtGraphs|QtCharts|QtDataVisualization|QtTest|QtMultimedia"
    rf"|QtTextToSpeech|QtWebSockets|QtSensors|QtScxml|QtWebView|QtRemoteObjects|QtWayland|Qt5Compat)(?:[/\\]|$)"
    rf"|[/\\]qml[/\\]QtQuick[/\\](?:VirtualKeyboard|Scene2D|Scene3D|Pdf|Controls[/\\](?:Material|Universal|Imagine"
    rf"|FluentWinUI3|designer))(?:[/\\]|$)"
    rf"|[/\\]plugins[/\\](?:qmltooling|designer|sqldrivers|sensors|canbus"
    rf"|renderers|sceneparsers|assetimporters|virtualkeyboard)(?:[/\\]|$)"
    # the PDF image plugin (QtPdf is left out), GTK's theme (needs GTK, Qt does without)
    rf"|[/\\](?:imageformats[/\\](?:lib)?qpdf|platformthemes[/\\](?:lib)?qgtk3)\w*\."
    , re.I)
# a file inside a framework that stays (macOS): never removed, the framework's signature seals all its files
TRIM = re.compile(r"qtwebengine_devtools_resources", re.I)
KEEP_LANGS = re.compile(r"(?:_|[/\\])(?:en|en-US|en-GB|fr|de)(?:\.qm|\.pak)$", re.I)


def wanted(dest):
    if DROP.search(dest):
        return False
    if ".framework" in dest:
        return True
    if TRIM.search(dest):
        return False
    # translations: French, English and German only (Qt's own, Chromium's)
    if re.search(r"[/\\]translations[/\\]", dest) and re.search(r"\.(?:qm|pak)$", dest):
        return bool(KEEP_LANGS.search(dest))
    return True


a.binaries = [entry for entry in a.binaries if wanted(entry[0])]
a.datas = [entry for entry in a.datas if wanted(entry[0])]
pyz = PYZ(a.pure)

icon = {"win32": "plume.ico", "darwin": "plume.icns"}.get(sys.platform, "plume.png")
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Plume",
    console=False,
    icon=str(STAGE / "icons" / icon),
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Plume", upx=False)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Plume.app",
        icon=str(STAGE / "icons" / "plume.icns"),
        bundle_identifier="eu.orneos.plume",
        version=VERSION,
        info_plist={
            "CFBundleName": "Plume",
            "CFBundleDisplayName": "Plume",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "LSMinimumSystemVersion": "12.0" if platform.machine() == "x86_64" else "13.0",  # Intel: Qt 6.9
            "NSHighResolutionCapable": True,
            "LSApplicationCategoryType": "public.app-category.productivity",
            "NSHumanReadableCopyright": "Orneos",
            # Meet: the camera and the microphone of a call (macOS asks once, with these words)
            "NSCameraUsageDescription": "Meet utilise la caméra pendant vos appels vidéo.",
            "NSMicrophoneUsageDescription": "Meet utilise le micro pendant vos appels.",
            # mailto: and webcal: (Plume can be the default mail app), orneos:// (links between mails, notes, tasks),
            # otpauth:// (a site's two-factor code, set up in Mots de passe)
            "CFBundleURLTypes": [
                {"CFBundleURLName": "eu.orneos.plume.mailto", "CFBundleURLSchemes": ["mailto"]},
                {"CFBundleURLName": "eu.orneos.plume.webcal", "CFBundleURLSchemes": ["webcal", "webcals"]},
                {"CFBundleURLName": "eu.orneos.link", "CFBundleURLSchemes": ["orneos"]},
                {"CFBundleURLName": "eu.orneos.passwords.otpauth", "CFBundleURLSchemes": ["otpauth"]},
            ],
            "CFBundleDocumentTypes": [
                {"CFBundleTypeName": "iCalendar", "CFBundleTypeRole": "Viewer", "LSHandlerRank": "Alternate",
                 "LSItemContentTypes": ["com.apple.ical.ics"], "CFBundleTypeExtensions": ["ics"]},
            ],
        },
    )
