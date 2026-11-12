"""AppImages, as on macOS: the « Applications » folder of the home folder (« Programme » in German), and every
AppImage dropped there is an app of the launcher, with its own name and icon.

Nothing here runs an AppImage to read it: its squashfs starts right after its ELF part (the offset the AppImage
runtime itself computes), and unsquashfs takes from it only the .desktop entry and the icon.
"""
from __future__ import annotations

import configparser
import hashlib
import json
import os
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path

HOME = Path.home()
DATA = Path(os.environ.get("XDG_DATA_HOME") or HOME / ".local/share")
# the icons the launcher shows: kept with the data, a cleared cache would leave the apps without their icon
CACHE = DATA / "orneos/appimages"
CONFIG = Path(os.environ.get("XDG_CONFIG_HOME") or HOME / ".config") / "orneos/appimages.json"
ENTRIES = DATA / "applications"
PREFIX = "orneos-appimage-"
NAMES = {"de": "Programme"}           # the folder's name; « Applications » otherwise (macOS's own names)
ALL_NAMES = ("Applications", "Programme")


def folder(lang: str | None = None) -> Path:
    """The Applications folder of this account: an existing one first, else the one of its language."""
    for name in ALL_NAMES:
        if (HOME / name).is_dir():
            return HOME / name
    lang = (lang or os.environ.get("LANG") or "fr")[:2]
    return HOME / NAMES.get(lang, "Applications")


def is_appimage(path: Path) -> bool:
    if not path.is_file() or not path.name.lower().endswith(".appimage"):
        return False
    try:
        with path.open("rb") as f:
            head = f.read(11)
    except OSError:
        return False
    return head[:4] == b"\x7fELF"           # type 1 and 2 alike (AI\x01, AI\x02 at 8: not always written)


def squashfs_offset(path: Path) -> int | None:
    """Where the squashfs of a type 2 AppImage starts: the end of its ELF section headers."""
    try:
        with path.open("rb") as f:
            head = f.read(64)
    except OSError:
        return None
    if len(head) < 52 or head[:4] != b"\x7fELF":
        return None
    endian = "<" if head[5] == 1 else ">"
    if head[4] == 2:                                   # 64-bit
        shoff, = struct.unpack_from(endian + "Q", head, 0x28)
        shentsize, shnum = struct.unpack_from(endian + "HH", head, 0x3A)
    else:                                              # 32-bit
        shoff, = struct.unpack_from(endian + "I", head, 0x20)
        shentsize, shnum = struct.unpack_from(endian + "HH", head, 0x2E)
    offset = shoff + shentsize * shnum
    try:
        with path.open("rb") as f:
            f.seek(offset)
            magic = f.read(4)
    except OSError:
        return None
    return offset if magic == b"hsqs" else None


def _inside(root: Path, path: Path) -> Path | None:
    """The file a (possibly symlinked) path of the extracted tree points to, if it stays in the tree."""
    try:
        real = path.resolve()
    except OSError:
        return None
    return real if real.is_file() and real.is_relative_to(root.resolve()) else None


def read(path: Path) -> dict:
    """{name, comment, categories, icon (a file in the cache, or "")} of an AppImage, read without running it."""
    info = {"name": path.name[: -len(".appimage")].replace("_", " ").replace("-x86_64", ""), "comment": "",
            "categories": "", "icon": "", "wm_class": ""}
    offset = squashfs_offset(path)
    if offset is None or not shutil.which("unsquashfs"):
        return info
    with tempfile.TemporaryDirectory() as tmp:
        tree = Path(tmp) / "x"
        # the entry and the icons only; -no-xattrs: nothing of the file's but its content
        base = ["unsquashfs", "-q", "-n", "-no-xattrs", "-o", str(offset), "-d", str(tree), str(path)]
        if subprocess.run(base + ["*.desktop", ".DirIcon"], capture_output=True, timeout=30).returncode not in (0, 2):
            return info
        desktop = next(iter(sorted(tree.glob("*.desktop"))), None)
        icon_name = ""
        if desktop and _inside(tree, desktop):
            cp = configparser.RawConfigParser(strict=False, interpolation=None)
            cp.optionxform = str
            try:
                cp.read(desktop, encoding="utf-8")
                entry = cp["Desktop Entry"]
            except (configparser.Error, KeyError, UnicodeDecodeError):
                entry = {}
            lang = (os.environ.get("LANG") or "fr")[:2]
            info["name"] = entry.get(f"Name[{lang}]") or entry.get("Name") or info["name"]
            info["comment"] = entry.get(f"Comment[{lang}]") or entry.get("Comment") or ""
            info["categories"] = entry.get("Categories", "")
            info["wm_class"] = entry.get("StartupWMClass", "")
            icon_name = entry.get("Icon", "")
        # the icon named by the entry at the root (where the AppImage tools put it), else .DirIcon
        candidates = []
        if icon_name and "/" not in icon_name:
            subprocess.run(base + [f"{icon_name}.png", f"{icon_name}.svg",
                                   f"usr/share/icons/hicolor/256x256/apps/{icon_name}.png",
                                   f"usr/share/icons/hicolor/scalable/apps/{icon_name}.svg"],
                           capture_output=True, timeout=30)
            candidates += [tree / f"{icon_name}.svg", tree / f"usr/share/icons/hicolor/scalable/apps/{icon_name}.svg",
                           tree / f"usr/share/icons/hicolor/256x256/apps/{icon_name}.png", tree / f"{icon_name}.png"]
        candidates.append(tree / ".DirIcon")
        for candidate in candidates:
            real = _inside(tree, candidate) if candidate.exists() or candidate.is_symlink() else None
            if real is None:
                continue
            with real.open("rb") as f:
                head = f.read(256)
            ext = ".png" if head[:8] == b"\x89PNG\r\n\x1a\n" else ".svg" if b"<svg" in head or b"<?xml" in head else ""
            if not ext:
                continue
            CACHE.mkdir(parents=True, exist_ok=True)
            dest = CACHE / (key(path) + ext)
            shutil.copyfile(real, dest)
            info["icon"] = str(dest)
            break
    return info


def key(path: Path) -> str:
    return hashlib.sha1(str(path.resolve()).encode()).hexdigest()[:16]


def _quote(path: Path) -> str:
    # Desktop entry Exec quoting: inside double quotes, \ " ` $ are escaped
    text = str(path)
    for ch in ("\\", '"', "`", "$"):
        text = text.replace(ch, "\\" + ch)
    return f'"{text}"'


def entry_for(path: Path, info: dict) -> str:
    lines = ["[Desktop Entry]", "Type=Application", f"Name={info['name']}", f"Exec={_quote(path)} %U",
             f"TryExec={path}", f"Icon={info['icon'] or 'application-x-executable'}",
             f"X-Orneos-AppImage={path}", "Terminal=false"]
    if info["comment"]:
        lines.append(f"Comment={info['comment']}")
    if info["categories"]:
        lines.append(f"Categories={info['categories']}")
    if info["wm_class"]:
        lines.append(f"StartupWMClass={info['wm_class']}")
    return "\n".join(lines) + "\n"


PLACES = DATA / "user-places.xbel"


def pin_place(home_apps: Path) -> None:
    """The Applications folder in Dolphin's side panel, after Téléchargements, once (taken out, it stays out).
    Text inserted in the file rather than rewritten: KDE reads its own namespace prefixes (bookmark:icon)."""
    if prefs().get("place_pinned") or not PLACES.is_file():
        return                              # Dolphin writes the file at its first start: the next sync pins it
    text = PLACES.read_text(encoding="utf-8")
    href = home_apps.as_uri()
    if f'href="{href}"' not in text:
        place = (f' <bookmark href="{href}">\n  <title>{home_apps.name}</title>\n  <info>\n'
                 '   <metadata owner="http://freedesktop.org">\n    <bookmark:icon name="folder-appimage"/>\n   </metadata>\n'
                 '   <metadata owner="http://www.kde.org">\n    <ID>orneos-applications</ID>\n   </metadata>\n'
                 '  </info>\n </bookmark>\n')
        downloads = subprocess.run(["xdg-user-dir", "DOWNLOAD"], capture_output=True, text=True).stdout.strip()
        at = text.find(f'href="{Path(downloads).as_uri()}"') if downloads else -1
        end = text.find("</bookmark>", at) if at >= 0 else -1
        if end >= 0:
            end += len("</bookmark>\n")
        else:
            end = text.rfind("</xbel>")
        if end < 0:
            return
        PLACES.write_text(text[:end] + place + text[end:], encoding="utf-8")
    set_pref("place_pinned", True)


def sync() -> list[str]:
    """The launcher entries of the Applications folder: one per AppImage, the others removed. Returns the names."""
    home_apps = folder()
    home_apps.mkdir(exist_ok=True)
    directory = home_apps / ".directory"         # its own icon in Dolphin
    if not directory.exists():
        directory.write_text("[Desktop Entry]\nIcon=folder-appimage\n")
    pin_place(home_apps)
    ENTRIES.mkdir(parents=True, exist_ok=True)
    wanted, names = {}, []
    for path in sorted(home_apps.iterdir()):
        if not is_appimage(path):
            continue
        if not os.access(path, os.X_OK):
            try:
                path.chmod(path.stat().st_mode | 0o111)
            except OSError:
                continue
        file = ENTRIES / f"{PREFIX}{key(path)}.desktop"
        stamp = f"{path.stat().st_size}:{int(path.stat().st_mtime)}"
        old = file.read_text(errors="replace") if file.exists() else ""
        if f"X-Orneos-Stamp={stamp}\n" in old:
            wanted[file.name] = old
        else:
            wanted[file.name] = entry_for(path, read(path)) + f"X-Orneos-Stamp={stamp}\n"
        names.append(path.name)
    for file in ENTRIES.glob(PREFIX + "*.desktop"):
        if file.name not in wanted:
            file.unlink(missing_ok=True)
            for icon in CACHE.glob(file.stem[len(PREFIX):] + ".*"):
                icon.unlink(missing_ok=True)
    for name, text in wanted.items():
        file = ENTRIES / name
        if not file.exists() or file.read_text(errors="replace") != text:
            file.write_text(text)
    return names


def prefs() -> dict:
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def set_pref(name: str, value) -> None:
    data = prefs()
    data[name] = value
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(data))


def install(path: Path) -> Path:
    """Moves an AppImage into the Applications folder (a free name), executable, listed in the launcher."""
    home_apps = folder()
    home_apps.mkdir(exist_ok=True)
    dest = home_apps / path.name
    for icon in CACHE.glob(key(path) + ".*"):        # read where it was, for the window: no longer needed
        icon.unlink(missing_ok=True)
    if dest.resolve() != path.resolve():
        n = 2
        while dest.exists():
            dest = home_apps / f"{path.name[: -len('.AppImage')]} ({n}).AppImage"
            n += 1
        shutil.move(str(path), dest)
    dest.chmod(dest.stat().st_mode | 0o111)
    sync()
    return dest


def launch(path: Path, args: list[str] | None = None) -> None:
    """Starts it detached, executable first (a downloaded file is not)."""
    try:
        path.chmod(path.stat().st_mode | 0o111)
    except OSError:
        pass
    subprocess.Popen([str(path)] + (args or []), start_new_session=True, stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=str(HOME))
