#!/usr/bin/env python3
"""Orneos icon theme: folders and places, document mimetypes, system apps and settings categories,
and the shared tile of every Orneos app icon. Inherits Breeze for everything else.

- Folders: Klein light (a lighter front over a deep back, a sheet of paper between them), the place drawn
  as a white line glyph on the front; ~/Orneos carries the arches of the mark with the saffron inner arch.
  At 16, 22 and 24 px, side-panel places use crisp monochrome line icons (with a dedicated folder-orneos
  line icon carrying the saffron inner arch).
- Mimetypes: Ornis document sheets color-coded by family (Klein, Vert-de-gris, Safran, Teal, Vermillon, Prusse)
  so files in Dolphin and the Launcher match the Orneos visual identity.
- System apps & Settings categories: tiles in the Ornis palette with a white line glyph and one saffron detail.
- Window buttons (window-*-symbolic): minimise −, maximise ^, restore ⌄, close ×, plain bars in the text
  colour; Klassy draws every window's title bar with them (/etc/xdg/klassy/klassyrc, StyleSystemIconTheme).

Usage: icons.py <dest root>                  → <dest root>/usr/share/icons/Orneos
       icons.py --small <icons dir>          in the image, once Breeze is there: our places
                                             at 16, 22 and 24 px point to Breeze's line icons
"""
import re
import sys
from pathlib import Path

SAFFRON = "#F0A202"
KLEIN = "#002FA7"
NIGHT = "#0F2440"
DOCS = "#2F7D6D"
MEDIA = "#1A5F7A"
DANGER = "#C8381E"

# ── Tiles ──────────────────────────────────────────────────────────────────────────────────────────────


def mix(hex_color, other, t):
    a = [int(hex_color[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(other[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02X}" for x, y in zip(a, b))


def tile(bg, glyph, uid):
    """An app icon, 48 grid: a rounded square in one colour, a touch lighter at the top, a hairline of
    light inside its edge (it keeps the tile apart from a dark dock), the 24 grid glyph centred on it."""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48"><defs>'
            f'<linearGradient id="t{uid}" x1="0" y1="2" x2="0" y2="46" gradientUnits="userSpaceOnUse">'
            f'<stop offset="0" stop-color="{mix(bg, "#FFFFFF", 0.12)}"/><stop offset="1" stop-color="{bg}"/></linearGradient></defs>'
            f'<rect x="2" y="2" width="44" height="44" rx="10" fill="url(#t{uid})"/>'
            f'<rect x="2.5" y="2.5" width="43" height="43" rx="9.5" fill="none" stroke="#FFFFFF" stroke-opacity=".14"/>'
            f'<g transform="translate(10 10) scale(1.1667)">{glyph}</g></svg>\n')


def lines(d, color="#FFFFFF", width=2, extra=""):
    return (f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linecap="round" '
            f'stroke-linejoin="round"{extra}/>')


# icon names used by the apps' .desktop files → glyph (24 grid): white lines, one saffron detail
SYSTEM_APPS = {
    "org.kde.dolphin": lines("M3 7.5a2 2 0 0 1 2-2h3.8l2 2H19a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z")
                       + lines("M3 11h18", SAFFRON),
    "system-file-manager": None,
    "preferences-system": lines("M4 7h9M19 7h1M4 17h1M11 17h9") + lines("M16 7m-2.5 0a2.5 2.5 0 1 0 5 0a2.5 2.5 0 1 0-5 0", SAFFRON)
                          + lines("M8 17m-2.5 0a2.5 2.5 0 1 0 5 0a2.5 2.5 0 1 0-5 0"),
    "systemsettings": None,
    "plasmadiscover": lines("M5 8h14l-1.2 11.2a2 2 0 0 1-2 1.8H8.2a2 2 0 0 1-2-1.8zM9 8V6.5a3 3 0 0 1 6 0V8")
                      + lines("M12 11.5v5M9.8 14.5l2.2 2.2 2.2-2.2", SAFFRON),
    "org.kde.discover": None,
    "utilities-terminal": lines("M5 7.5l4.5 4.5L5 16.5") + lines("M12.5 17h6.5", SAFFRON),
    "org.kde.konsole": None,
    "kwrite": lines("M6 3.5h8l4 4V20.5H6zM14 3.5v4h4") + lines("M9 12h6M9 15.5h4", SAFFRON),
    "org.kde.kwrite": None,
    "accessories-text-editor": None,
    "spectacle": lines("M4 9V6a2 2 0 0 1 2-2h3M15 4h3a2 2 0 0 1 2 2v3M20 15v3a2 2 0 0 1-2 2h-3M9 20H6a2 2 0 0 1-2-2v-3")
                 + lines("M12 12m-3 0a3 3 0 1 0 6 0a3 3 0 1 0-6 0", SAFFRON),
    "org.kde.spectacle": None,
    "utilities-system-monitor": lines("M3 12.5h4l2.2-5.5 4.2 11 2.4-5.5H21") + lines("M3 20.5h18", SAFFRON, 1.6, ' stroke-opacity=".9"'),
    "org.kde.plasma-systemmonitor": None,
    "ark": lines("M4 7.5l8-4 8 4v9l-8 4-8-4zM4 7.5l8 4 8-4M12 11.5v9") + lines("M8 5.5l8 4", SAFFRON),
    "org.kde.ark": None,
    "hwinfo": lines("M12 12m-8.5 0a8.5 8.5 0 1 0 17 0a8.5 8.5 0 1 0-17 0M12 11v5.5") + lines("M12 7.6v.1", SAFFRON, 2.6),
    "help-browser": lines("M12 12m-8.5 0a8.5 8.5 0 1 0 17 0a8.5 8.5 0 1 0-17 0M9.5 9.5a2.5 2.5 0 1 1 3.4 2.3c-.6.3-.9.8-.9 1.4v.6")
                    + lines("M12 16.6v.1", SAFFRON, 2.6),
    "orneos-appearance": lines("M12 12m-8 0a8 8 0 1 0 16 0a8 8 0 1 0-16 0")
                         + '<path d="M12 5.5a6.5 6.5 0 0 1 0 13z" fill="#F0A202"/>',
    "orneos-account": lines("M12 8.5m-3.5 0a3.5 3.5 0 1 0 7 0a3.5 3.5 0 1 0-7 0") + lines("M5 20c.8-3.6 3.6-5.5 7-5.5s6.2 1.9 7 5.5", SAFFRON),
    "kfind": lines("M10.5 10.5m-6 0a6 6 0 1 0 12 0a6 6 0 1 0-12 0") + lines("M15 15l5 5", SAFFRON),
    "gwenview": lines("M4 6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2zM4 16l4.5-4.5 3.5 3.5 3-3 5 4")
                + lines("M15.5 8.5m-1.5 0a1.5 1.5 0 1 0 3 0a1.5 1.5 0 1 0-3 0", SAFFRON),
    "org.kde.gwenview": None,
    "okular": lines("M6 3.5h8l4 4V20.5H6zM14 3.5v4h4") + lines("M9 14.5c1.5-3 4.5-3 6 0M10 11h4", SAFFRON),
    "org.kde.okular": None,
    "haruna": lines("M3.5 5.5h17a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1h-17a1 1 0 0 1-1-1v-11a1 1 0 0 1 1-1z")
              + lines("M10 9v6l5-3z", SAFFRON),
    "org.kde.haruna": None,
    "elisa": lines("M9 17.5V6l10-2v11.5M9 9.5l10-2") + lines("M6.5 17.5m-2.5 0a2.5 2.5 0 1 0 5 0a2.5 2.5 0 1 0-5 0M16.5 15.5m-2.5 0a2.5 2.5 0 1 0 5 0a2.5 2.5 0 1 0-5 0", SAFFRON),
    "org.kde.elisa": None,
    "kcalc": lines("M5 4h14a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1zM4 9.5h16M12 9.5V20M4 14.8h8")
             + lines("M14.5 13.5h3M14.5 16.5h3", SAFFRON),
    "org.kde.kcalc": None,
    "accessories-calculator": None,
}

ALIASES = {
    "system-file-manager": "org.kde.dolphin",
    "systemsettings": "preferences-system",
    "org.kde.discover": "plasmadiscover",
    "org.kde.konsole": "utilities-terminal",
    "org.kde.kwrite": "kwrite",
    "accessories-text-editor": "kwrite",
    "org.kde.spectacle": "spectacle",
    "org.kde.plasma-systemmonitor": "utilities-system-monitor",
    "org.kde.ark": "ark",
    "org.kde.gwenview": "gwenview",
    "org.kde.okular": "okular",
    "org.kde.haruna": "haruna",
    "org.kde.elisa": "elisa",
    "org.kde.kcalc": "kcalc",
    "accessories-calculator": "kcalc",
}

# System Settings sidebar categories: Ornis tiles instead of stock KDE Breeze rainbow icons
SETTINGS_TILES = {
    "preferences-desktop-theme-global": (KLEIN, lines("M12 12m-8 0a8 8 0 1 0 16 0a8 8 0 1 0-16 0") + '<path d="M12 5.5a6.5 6.5 0 0 1 0 13z" fill="#F0A202"/>'),
    "preferences-desktop-theme": ("preferences-desktop-theme-global",),
    "preferences-desktop-theme-applications": ("preferences-desktop-theme-global",),
    "preferences-desktop-color": ("preferences-desktop-theme-global",),
    "preferences-desktop-wallpaper": (MEDIA, lines("M4 6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2zM4 16.5c3-4.5 6-6.5 8-6.5s5 2 8 6.5") + lines("M8 16.5c1.5-2.2 2.8-3.2 4-3.2s2.5 1 4 3.2", SAFFRON)),
    "preferences-desktop-font": (DOCS, lines("M5 19L10.5 5h3L19 19M7.2 14h9.6") + lines("M4 19h4M16 19h4", SAFFRON)),
    "preferences-desktop-icons": (KLEIN, lines("M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4z") + '<rect x="14" y="14" width="6" height="6" rx="1" fill="#F0A202"/>'),
    "preferences-desktop-cursors": (NIGHT, lines("M6 4l12 7.5-5.2 1.6L16 19l-2.4 1.2-3.2-5.8L6 18z") + lines("M6 4l6.8 9.1", SAFFRON)),
    "preferences-desktop-display-randr": (KLEIN, lines("M3.5 5.5h17a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1h-17a1 1 0 0 1-1-1v-9a1 1 0 0 1 1-1zM8.5 20h7M12 16.5V20") + lines("M6.5 11h11", SAFFRON)),
    "preferences-desktop-display": ("preferences-desktop-display-randr",),
    "video-display": ("preferences-desktop-display-randr",),
    "preferences-desktop-sound": (KLEIN, lines("M5 9.5h3.5L13 5.5v13l-4.5-4H5z") + lines("M16 9a4.5 4.5 0 0 1 0 6M18.5 6.5a8 8 0 0 1 0 11", SAFFRON)),
    "audio-card": ("preferences-desktop-sound",),
    "preferences-system-bluetooth": (KLEIN, lines("M7.5 7.5l9 9-4.5 4V3.5l4.5 4-9 9") + lines("M5 12h.1M19 12h.1", SAFFRON, 2.6)),
    "preferences-system-network": (KLEIN, lines("M12 12m-8 0a8 8 0 1 0 16 0a8 8 0 1 0-16 0M4 12h16") + lines("M12 4c2.4 2.4 3.5 5.1 3.5 8s-1.1 5.6-3.5 8c-2.4-2.4-3.5-5.1-3.5-8S9.6 6.4 12 4", SAFFRON)),
    "network-workgroup": ("preferences-system-network",),
    "input-keyboard": (NIGHT, lines("M3.5 6.5h17a1.5 1.5 0 0 1 1.5 1.5v8a1.5 1.5 0 0 1-1.5 1.5h-17A1.5 1.5 0 0 1 2 16V8a1.5 1.5 0 0 1 1.5-1.5zM6 10h1M10 10h1M14 10h1M18 10h1M6 13h1M18 13h1") + lines("M8.5 14.5h7", SAFFRON)),
    "preferences-desktop-keyboard": ("input-keyboard",),
    "input-mouse": (NIGHT, lines("M12 3.5a5.5 5.5 0 0 1 5.5 5.5v6a5.5 5.5 0 0 1-11 0V9A5.5 5.5 0 0 1 12 3.5z") + lines("M12 7v3.5", SAFFRON, 2.2)),
    "input-touchpad": (NIGHT, lines("M4 5.5h16a1.5 1.5 0 0 1 1.5 1.5v10a1.5 1.5 0 0 1-1.5 1.5H4A1.5 1.5 0 0 1 2.5 17V7A1.5 1.5 0 0 1 4 5.5z") + lines("M2.5 14.5h19M12 14.5v4", SAFFRON)),
    "preferences-desktop-touchscreen": (NIGHT, lines("M7 3.5h10a1.5 1.5 0 0 1 1.5 1.5v14a1.5 1.5 0 0 1-1.5 1.5H7A1.5 1.5 0 0 1 5.5 19V5A1.5 1.5 0 0 1 7 3.5z") + lines("M12 11.5m-2.2 0a2.2 2.2 0 1 0 4.4 0a2.2 2.2 0 1 0-4.4 0", SAFFRON)),
    "preferences-desktop-notification": (DOCS, lines("M12 4a5 5 0 0 1 5 5v4.5l1.8 2H5.2l1.8-2V9a5 5 0 0 1 5-5z") + lines("M10 18.5a2 2 0 0 0 4 0", SAFFRON, 2.2)),
    "preferences-desktop-accessibility": (KLEIN, lines("M5 8.5l7 1.5 7-1.5M12 10v4.5l-3 5M12 14.5l3 5") + lines("M12 5.2m-1.8 0a1.8 1.8 0 1 0 3.6 0a1.8 1.8 0 1 0-3.6 0", SAFFRON)),
    "preferences-system-power-management": (DOCS, lines("M13 3.5L6.5 13h5.5l-1 7.5L17.5 11H12z", SAFFRON)),
    "preferences-system-time": (NIGHT, lines("M12 12m-8.5 0a8.5 8.5 0 1 0 17 0a8.5 8.5 0 1 0-17 0") + lines("M12 7.5V12l3.5 2", SAFFRON, 2.2)),
    "preferences-desktop-locale": (DOCS, lines("M4 6h9M8.5 4v2M6 6c.5 4 2.5 7 6 8.5M11 6c-.8 3.5-2.5 6.2-5.5 8") + lines("M13.5 19.5l3.2-8.5 3.3 8.5M14.6 17h4.3", SAFFRON)),
    "preferences-desktop-default-applications": (KLEIN, lines("M12 3.8l2.5 5 5.5.8-4 3.9.9 5.5-4.9-2.6-4.9 2.6.9-5.5-4-3.9 5.5-.8z", SAFFRON)),
    "preferences-online-accounts": (KLEIN, lines("M7.5 18.5a4 4 0 0 1-.6-8 5.5 5.5 0 0 1 10.6 1.3 3.4 3.4 0 0 1-.5 6.7z") + lines("M9.5 14.5c1-1.6 2-2.2 2.8-2.2s1.8.6 2.8 2.2", SAFFRON)),
    "preferences-desktop-user": ("orneos-account",),
    "preferences-system-users": ("orneos-account",),
    "preferences-system-disks": (NIGHT, lines("M5 4.5h14a1.5 1.5 0 0 1 1.5 1.5v12a1.5 1.5 0 0 1-1.5 1.5H5A1.5 1.5 0 0 1 3.5 18V6A1.5 1.5 0 0 1 5 4.5zM3.5 14.5h17") + lines("M7.5 17h.1M11 17h.1", SAFFRON, 2.5)),
}

# 3C Tri-Blade Prism paths (36x36 coordinate space)
PRISM_P1 = "M21.4 3.2C11.2 2 2.8 9.8 2.8 19.4c0 2.4.6 4.6 1.6 6.6L11 19.4c-.8-5 2.8-9.6 7.8-10l2.6-6.2z"
PRISM_P2 = "M32.8 16.2c.8 9.4-6.6 17-16 17-4 0-7.7-1.5-10.4-4.2l6.6-6.6c3.8 3.4 9.8 2.6 12.6-2.2l7.2-4z"
PRISM_P3 = "M24.4 4.2c4.4 2 7.4 5.8 8.2 9.4l-6.8 3.8c-.8-3.4-3-6-6-7.2l4.6-6z"

# The 3C Tri-Blade Prism scaled to the 24x24 glyph grid for tiles and 64px folder fronts
START_GLYPH = (
    '<g transform="translate(-1.2 -1.2) scale(.7333)">'
    f'<path d="{PRISM_P1}" fill="#FFFFFF"/>'
    f'<path d="{PRISM_P2}" fill="#FFFFFF" fill-opacity=".76"/>'
    f'<path d="{PRISM_P3}" fill="{SAFFRON}"/>'
    '</g>'
)


def standalone_mark(dark=False):
    """Standalone 3C Tri-Blade Prism (no bounding box) for the top-bar menu icon (orneos-start)."""
    c1 = "#FFFFFF" if dark else KLEIN
    c2 = "#C2D1F8" if dark else "#2B5CE6"
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 36 36">'
        f'<path d="{PRISM_P1}" fill="{c1}"/>'
        f'<path d="{PRISM_P2}" fill="{c2}"/>'
        f'<path d="{PRISM_P3}" fill="{SAFFRON}"/>'
        '</svg>\n'
    )


# Ornis: the AI symbol (two stars, design/ornis-ai/ai.svg copied by tools/ornis-mascot.py). The mascot only
# appears inside the apps (hover, answers), never as an app or top-bar icon (docs/ORNIS-MASCOT.md).
# In the repository next to os/files; in the image's --small step, only os/tools is mounted: the copy already installed
AI_SVG = next(p for p in (Path(__file__).resolve().parents[1] / "files/usr/share/orneos/mascot/ai.svg",
                          Path("/usr/share/orneos/mascot/ai.svg")) if p.is_file())
AI_D = re.findall(r'\sd="([^"]+)"', AI_SVG.read_text())  # big, small


def ai_glyph(fg="#FFFFFF"):
    return (f'<path fill="{fg}" stroke="{fg}" stroke-width=".9" stroke-linejoin="round" d="{AI_D[0]}"/>'
            f'<path fill="{SAFFRON}" stroke="{SAFFRON}" stroke-width=".7" stroke-linejoin="round" d="{AI_D[1]}"/>')


def standalone_ornis(dark=False):
    """Standalone AI symbol for the top bar (orneos-ornis-bar / orneos-ornis-bar-dark)."""
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">{ai_glyph("#FFFFFF" if dark else KLEIN)}</svg>\n'


# The dock launcher: a 3×3 grid of app tiles, one saffron.
APPS_GLYPH = "".join(
    f'<rect x="{4.6 + c * 5.3:.1f}" y="{4.6 + r * 5.3:.1f}" width="4.2" height="4.2" rx="1" '
    f'fill="{SAFFRON if r == 0 and c == 0 else "#FFFFFF"}"/>'
    for r in range(3) for c in range(3)
)

# ── Folders ────────────────────────────────────────────────────────────────────────────────────────────

BACK, FRONT_TOP, FRONT_BOTTOM, PAPER = "#1A3FB8", "#5682F7", "#2A55DA", "#EAF0FD"

# place → glyph (24 grid, drawn white on the folder front)
PLACES = {
    "folder": "",
    "folder-documents": lines("M7 3.5h7l4 4v13H7zM14 3.5v4h4M10 12h5M10 15.5h5"),
    "folder-download": lines("M12 4v11M7.5 10.5 12 15l4.5-4.5M5 19.5h14"),
    "folder-downloads": None,
    "folder-music": lines("M9 17.5V6l10-2v11.5") + lines("M6.5 17.5m-2.5 0a2.5 2.5 0 1 0 5 0a2.5 2.5 0 1 0-5 0M16.5 15.5m-2.5 0a2.5 2.5 0 1 0 5 0a2.5 2.5 0 1 0-5 0"),
    "folder-pictures": lines("M4 18l5-6 4 4.5 2.5-2.5 4.5 4M15.5 8m-1.8 0a1.8 1.8 0 1 0 3.6 0a1.8 1.8 0 1 0-3.6 0"),
    "folder-images": None,
    "folder-videos": lines("M8.5 6.5l9.5 5.5-9.5 5.5z"),
    "folder-video": None,
    "user-desktop": lines("M4 6a1.5 1.5 0 0 1 1.5-1.5h13A1.5 1.5 0 0 1 20 6v9a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 15zM9 20h6M12 16.5V20"),
    "folder-desktop": None,
    "user-home": lines("M4 11l8-7 8 7M6.5 9v11h11V9M10 20v-5.5h4V20"),
    "folder-home": None,
    "folder-templates": lines("M5 4.5h14v15H5zM5 9h14M10 9v10.5"),
    "folder-publicshare": lines("M8 9m-2.5 0a2.5 2.5 0 1 0 5 0a2.5 2.5 0 1 0-5 0M16.5 10m-2 0a2 2 0 1 0 4 0a2 2 0 1 0-4 0M3.5 19c.6-3.2 2.3-5 4.5-5s3.9 1.8 4.5 5M13.5 18.5c.5-2.4 1.6-3.8 3-3.8s2.6 1.4 3 3.8"),
    "folder-public": None,
    "folder-appimage": lines("M5 5h5.5v5.5H5zM13.5 5H19v5.5h-5.5zM5 13.5h5.5V19H5zM13.5 13.5H19V19h-5.5z"),  # Applications (AppImage)
    "folder-cloud": lines("M7.5 18.5a4 4 0 0 1-.6-8 5.5 5.5 0 0 1 10.6 1.3 3.4 3.4 0 0 1-.5 6.7z"),
    # the files client's folder (~/Orneos): the 3C Tri-Blade Prism emblem
    "folder-orneos": START_GLYPH,
    "folder-network": lines("M12 12m-8 0a8 8 0 1 0 16 0a8 8 0 1 0-16 0M4 12h16M12 4c2.2 2.3 3.2 5 3.2 8s-1 5.7-3.2 8c-2.2-2.3-3.2-5-3.2-8s1-5.7 3.2-8"),
    "folder-remote": None,
}
PLACE_ALIASES = {"folder-downloads": "folder-download", "folder-images": "folder-pictures", "folder-video": "folder-videos",
                 "folder-desktop": "user-desktop", "folder-home": "user-home", "folder-public": "folder-publicshare",
                 "folder-remote": "folder-network"}


def folder(glyph):
    """64 grid: deep back with its tab, a sheet of paper, the lighter front (light from the top edge)."""
    emblem = f'<g transform="translate(21.2 26.5) scale(.9)" opacity=".92">{glyph}</g>' if glyph else ""
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><defs>'
            f'<linearGradient id="f" x1="0" y1="22" x2="0" y2="54" gradientUnits="userSpaceOnUse">'
            f'<stop offset="0" stop-color="{FRONT_TOP}"/><stop offset="1" stop-color="{FRONT_BOTTOM}"/></linearGradient>'
            '<linearGradient id="s" x1="0" y1="50" x2="0" y2="56" gradientUnits="userSpaceOnUse">'
            '<stop offset="0" stop-color="#000C33" stop-opacity=".22"/><stop offset="1" stop-color="#000C33" stop-opacity="0"/></linearGradient></defs>'
            '<rect x="7" y="50" width="50" height="6" rx="3" fill="url(#s)"/>'
            f'<path d="M5 15a5 5 0 0 1 5-5h12.6a4 4 0 0 1 2.9 1.2L29 14.5h25a5 5 0 0 1 5 5V47a5 5 0 0 1-5 5H10a5 5 0 0 1-5-5z" fill="{BACK}"/>'
            f'<rect x="9" y="17" width="46" height="22" rx="2.5" fill="{PAPER}"/>'
            '<path d="M5 26.5a5 5 0 0 1 5-5h44a5 5 0 0 1 5 5V47a5 5 0 0 1-5 5H10a5 5 0 0 1-5-5z" fill="url(#f)"/>'
            '<path d="M10 22h44a4.5 4.5 0 0 1 4.5 4.5" fill="none" stroke="#FFFFFF" stroke-opacity=".45" stroke-width="1"/>'
            f'{emblem}</svg>\n')


def small_orneos_place(size):
    """Monochrome 16/22/24 px sidebar icon for ~/Orneos: uses ColorScheme-Text + saffron blade."""
    vb = 16 if size == 16 else 22
    scale = 0.42 if vb == 16 else 0.56
    offset = 0.44 if vb == 16 else 0.92
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {vb} {vb}">'
            '<defs><style id="current-color-scheme" type="text/css">.ColorScheme-Text { color:#0F2440; }</style></defs>'
            f'<g transform="translate({offset:.2f} {offset:.2f}) scale({scale:.4f})">'
            f'<path d="{PRISM_P1}" class="ColorScheme-Text" fill="currentColor"/>'
            f'<path d="{PRISM_P2}" class="ColorScheme-Text" fill="currentColor" fill-opacity=".75"/>'
            f'<path d="{PRISM_P3}" fill="{SAFFRON}"/>'
            '</g></svg>\n')


def trash(full):
    """64 grid: a Brume bin with Klein ribs and lid; full, sheets of paper rise from it."""
    papers = ('<g transform="rotate(-12 26 16)"><rect x="17" y="6" width="16" height="20" rx="2" fill="#FFFFFF" stroke="#C3CEE6"/>'
              '<path d="M21 12h8M21 16h6" stroke="#8A9EFF" stroke-width="1.6" stroke-linecap="round"/></g>'
              '<g transform="rotate(10 38 16)"><rect x="31" y="5" width="15" height="20" rx="2" fill="#FFFFFF" stroke="#C3CEE6"/>'
              '<path d="M35 11h7M35 15h5" stroke="#F0A202" stroke-width="1.6" stroke-linecap="round"/></g>') if full else ""
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><defs>'
            '<linearGradient id="b" x1="0" y1="20" x2="0" y2="58" gradientUnits="userSpaceOnUse">'
            '<stop offset="0" stop-color="#FFFFFF"/><stop offset="1" stop-color="#E3E9F5"/></linearGradient></defs>'
            '<rect x="16" y="54" width="32" height="5" rx="2.5" fill="#000C33" fill-opacity=".12"/>'
            f'{papers}'
            '<path d="M14.5 24h35l-3 28.2a4 4 0 0 1-4 3.6H21.5a4 4 0 0 1-4-3.6z" fill="url(#b)" stroke="#C3CEE6"/>'
            '<path d="M25 31l1 18M32 31v18M39 31l-1 18" stroke="#2A55DA" stroke-width="2.2" stroke-linecap="round"/>'
            '<rect x="11" y="19" width="42" height="6.5" rx="3.25" fill="#1A3FB8"/>'
            '<path d="M27 19v-2.5a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2V19" fill="none" stroke="#1A3FB8" stroke-width="2.2"/>'
            '</svg>\n')


# ── Mimetype Document Icons (64 grid) ──────────────────────────────────────────────────────────────────


def doc_sheet(accent, content_svg, uid, bar_color=SAFFRON):
    """64 grid Ornis document sheet: crisp rounded page, folded top-right corner, colored header/footer cue,
    and vector emblem in the center."""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><defs>'
        f'<linearGradient id="p{uid}" x1="0" y1="6" x2="0" y2="58" gradientUnits="userSpaceOnUse">'
        f'<stop offset="0" stop-color="#FFFFFF"/><stop offset="1" stop-color="#EDF1FA"/></linearGradient>'
        f'</defs>'
        f'<rect x="13" y="54" width="38" height="5" rx="2.5" fill="#000C33" fill-opacity=".14"/>'
        f'<path d="M12 11a5 5 0 0 1 5-5h22l13 13v34a5 5 0 0 1-5 5H17a5 5 0 0 1-5-5z" '
        f'fill="url(#p{uid})" stroke="#C5D0E6" stroke-width="1.2"/>'
        f'<path d="M39 6l13 13h-8a5 5 0 0 1-5-5z" fill="{mix(accent, "#FFFFFF", 0.78)}" stroke="#C5D0E6" stroke-width="1" stroke-linejoin="round"/>'
        f'<rect x="18" y="49" width="28" height="3.2" rx="1.6" fill="{bar_color}"/>'
        f'{content_svg}'
        f'</svg>\n'
    )


MIME_CONTENT = {
    "text": (
        KLEIN,
        f'<rect x="19" y="18" width="13" height="2.6" rx="1.3" fill="{KLEIN}"/>'
        '<rect x="19" y="25" width="26" height="2.2" rx="1.1" fill="#6B7D99"/>'
        '<rect x="19" y="31" width="26" height="2.2" rx="1.1" fill="#6B7D99"/>'
        '<rect x="19" y="37" width="19" height="2.2" rx="1.1" fill="#6B7D99"/>',
        SAFFRON,
    ),
    "markdown": (
        KLEIN,
        f'<rect x="18" y="22" width="28" height="19" rx="3.5" fill="{KLEIN}"/>'
        '<path d="M22.5 36v-9l3.2 4 3.2-4v9M36.5 27v9m-2.8-2.8l2.8 2.8 2.8-2.8" '
        'fill="none" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
        SAFFRON,
    ),
    "doc": (
        DOCS,
        f'<rect x="19" y="17" width="15" height="3" rx="1.5" fill="{DOCS}"/>'
        f'<rect x="19" y="24" width="26" height="2.4" rx="1.2" fill="{DOCS}" fill-opacity=".8"/>'
        '<rect x="19" y="30" width="26" height="2.2" rx="1.1" fill="#5A726C"/>'
        '<rect x="19" y="36" width="26" height="2.2" rx="1.1" fill="#5A726C"/>'
        '<rect x="19" y="42" width="18" height="2.2" rx="1.1" fill="#5A726C"/>',
        DOCS,
    ),
    "sheet": (
        DOCS,
        f'<rect x="18" y="22" width="28" height="21" rx="3" fill="none" stroke="{DOCS}" stroke-width="2"/>'
        f'<path d="M18 29h28M18 36h28M28 22v21" stroke="{DOCS}" stroke-width="1.8"/>'
        f'<rect x="18" y="22" width="28" height="7" rx="2" fill="{DOCS}"/>',
        SAFFRON,
    ),
    "slides": (
        SAFFRON,
        f'<rect x="18" y="22" width="28" height="20" rx="3.5" fill="{SAFFRON}" fill-opacity=".18" stroke="{SAFFRON}" stroke-width="2"/>'
        f'<path d="M24 36v-5M30 36v-8M36 36v-3" stroke="{NIGHT}" stroke-width="2.6" stroke-linecap="round"/>',
        SAFFRON,
    ),
    "pdf": (
        DANGER,
        f'<rect x="18" y="23" width="28" height="17" rx="3.5" fill="{DANGER}"/>'
        '<path d="M22.5 35.5v-8h2.6a2.4 2.4 0 0 1 0 4.8h-2.6M30.2 35.5v-8h2.2a4 4 0 0 1 0 8zM38 35.5v-8h4.2M38 31.5h3.2" '
        'fill="none" stroke="#FFFFFF" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/>',
        DANGER,
    ),
    "image": (
        MEDIA,
        f'<rect x="18" y="21" width="28" height="22" rx="3.5" fill="{MEDIA}"/>'
        f'<circle cx="38" cy="27.5" r="2.8" fill="{SAFFRON}"/>'
        '<path d="M19.5 41l7.5-8.5 5.5 5.5 4-4 6 7z" fill="#FFFFFF" fill-opacity=".9"/>',
        MEDIA,
    ),
    "video": (
        MEDIA,
        f'<rect x="18" y="21" width="28" height="22" rx="3.5" fill="{MEDIA}"/>'
        '<path d="M29 27.5l9 4.5-9 4.5z" fill="#FFFFFF"/>',
        SAFFRON,
    ),
    "audio": (
        KLEIN,
        f'<path d="M21 34v-4M25.5 38V26M30 41V23M34.5 36v-8M39 39V25M43 34v-4" stroke="{KLEIN}" stroke-width="2.6" stroke-linecap="round"/>',
        SAFFRON,
    ),
    "archive": (
        NIGHT,
        f'<rect x="28" y="14" width="8" height="28" rx="2" fill="{NIGHT}" fill-opacity=".12"/>'
        f'<path d="M30 17h4M30 21h4M30 25h4M30 29h4" stroke="{NIGHT}" stroke-width="2" stroke-linecap="round"/>'
        f'<rect x="27.5" y="33" width="9" height="10" rx="2.5" fill="{NIGHT}"/>'
        f'<circle cx="32" cy="38" r="1.8" fill="{SAFFRON}"/>',
        SAFFRON,
    ),
    "calendar": (
        SAFFRON,
        f'<rect x="18" y="21" width="28" height="22" rx="3.5" fill="none" stroke="{NIGHT}" stroke-width="2"/>'
        f'<rect x="18" y="21" width="28" height="6.5" rx="2" fill="{SAFFRON}"/>'
        f'<circle cx="26" cy="33" r="1.8" fill="{KLEIN}"/><circle cx="32" cy="33" r="1.8" fill="{NIGHT}"/><circle cx="38" cy="33" r="1.8" fill="{NIGHT}"/>'
        f'<circle cx="26" cy="38" r="1.8" fill="{NIGHT}"/><circle cx="32" cy="38" r="1.8" fill="{SAFFRON}"/>',
        SAFFRON,
    ),
    "code": (
        NIGHT,
        f'<path d="M26 26l-5.5 5.5L26 37M38 26l5.5 5.5L38 37" fill="none" stroke="{NIGHT}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>'
        f'<path d="M34 24.5l-4 14" fill="none" stroke="{SAFFRON}" stroke-width="2.4" stroke-linecap="round"/>',
        KLEIN,
    ),
}

MIME_MAP = {
    "text": ("text-plain", "text-x-generic", "application-x-zerosize", "text-x-log", "text-x-readme"),
    "markdown": ("text-markdown", "text-x-markdown"),
    "doc": (
        "x-office-document",
        "application-msword",
        "application-vnd.oasis.opendocument.text",
        "application-vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application-rtf",
        "text-richtext",
    ),
    "sheet": (
        "x-office-spreadsheet",
        "application-vnd.ms-excel",
        "application-vnd.oasis.opendocument.spreadsheet",
        "application-vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "text-csv",
        "text-x-csv",
    ),
    "slides": (
        "x-office-presentation",
        "application-vnd.ms-powerpoint",
        "application-vnd.oasis.opendocument.presentation",
        "application-vnd.openxmlformats-officedocument.presentationml.presentation",
    ),
    "pdf": ("application-pdf", "application-x-pdf"),
    "image": ("image-x-generic", "image-png", "image-jpeg", "image-jpg", "image-gif", "image-webp", "image-svg+xml", "image-bmp"),
    "video": ("video-x-generic", "video-mp4", "video-x-matroska", "video-webm", "video-quicktime", "video-x-msvideo"),
    "audio": ("audio-x-generic", "audio-mp3", "audio-mpeg", "audio-flac", "audio-ogg", "audio-x-wav", "audio-mp4", "audio-aac"),
    "archive": (
        "package-x-generic",
        "application-zip",
        "application-x-tar",
        "application-x-compressed-tar",
        "application-x-bzip-compressed-tar",
        "application-x-xz-compressed-tar",
        "application-x-7z-compressed",
        "application-x-rar",
        "application-gzip",
    ),
    "calendar": ("text-calendar", "application-ics"),
    "code": (
        "text-html",
        "application-xhtml+xml",
        "application-json",
        "text-xml",
        "application-xml",
        "text-x-python",
        "text-x-script",
        "application-x-shellscript",
        "text-x-csrc",
        "text-x-c++src",
        "application-javascript",
        "text-css",
    ),
}


INDEX = """[Icon Theme]
Name=Orneos
Comment=Orneos folders, documents and apps, Breeze for the rest
Inherits=breeze,hicolor
DisplayDepth=32
Example=folder
FollowsColorScheme=true
Directories=apps/scalable,places/scalable,mimetypes/scalable,actions/symbolic

[apps/scalable]
Size=48
MinSize=16
MaxSize=512
Context=Applications
Type=Scalable

[places/scalable]
Size=64
MinSize=32
MaxSize=512
Context=Places
Type=Scalable

[mimetypes/scalable]
Size=64
MinSize=16
MaxSize=512
Context=MimeTypes
Type=Scalable

[actions/symbolic]
Size=16
MinSize=8
MaxSize=512
Context=Actions
Type=Scalable
"""

# The title bar buttons, 16 grid, in the colour scheme's text colour (Klassy colours them again). Filled bars, not
# strokes: KDE recolours either, but GTK (Firefox's own title bar) only recolours fills, and a stroke kept the navy
# below, invisible on a dark title bar. One bar: (centre x, centre y, length, angle).
WINDOW_BUTTONS = {
    "window-minimize": [(8, 8, 9.5, 0)],
    "window-maximize": [(6, 8, 7.2, -45), (10, 8, 7.2, 45)],
    "window-restore": [(6, 8, 7.2, 45), (10, 8, 7.2, -45)],
    "window-close": [(8, 8, 11.4, 45), (8, 8, 11.4, -45)],
}


def window_button(bars):
    shapes = "".join(
        f'<rect class="ColorScheme-Text" style="fill:currentColor" x="{x - length / 2:g}" y="{y - 0.75:g}" '
        f'width="{length:g}" height="1.5" rx="0.75" transform="rotate({angle} {x} {y})"/>'
        for x, y, length, angle in bars)
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><style id="current-color-scheme">'
            '.ColorScheme-Text{color:#0F2440;}</style>' + shapes + '</svg>\n')


def symbolic_mark():
    """The prism in the text colour, for the places that show Plasma's own mark (plasma-symbolic): the "Begin setup"
    button of the first-run assistant, Plasma's About pages."""
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 36 36"><style id="current-color-scheme">'
            '.ColorScheme-Text{color:#0F2440;}</style>'
            f'<path class="ColorScheme-Text" fill="currentColor" d="{PRISM_P1}"/>'
            f'<path class="ColorScheme-Text" fill="currentColor" fill-opacity=".7" d="{PRISM_P2}"/>'
            f'<path class="ColorScheme-Text" fill="currentColor" d="{PRISM_P3}"/></svg>\n')


def dark_index(text):
    return text.replace("Name=Orneos", "Name=Orneos Dark").replace("Inherits=breeze,", "Inherits=breeze-dark,")


SMALL = re.compile(r"^places/(16|22|24)(@\dx)?$")


def link_small(icons):
    """Small places stay Breeze's line icons: KIconLoader takes the nearest size in the first theme that
    has the name, so our 3D folders would otherwise be shrunk into the side panels.
    Also writes a dedicated monochrome + saffron folder-orneos.svg at 16, 22 and 24 px."""
    ours, breeze = icons / "Orneos", icons / "breeze"
    names = {p.stem for p in (ours / "places/scalable").glob("*.svg")} | {"inode-directory"}
    index = (breeze / "index.theme").read_text()
    sections = dict(re.findall(r"^\[([^\]]+)\]\n(.*?)(?=^\[|\Z)", index, re.S | re.M))
    dirs = []
    for d, body in sections.items():
        if not SMALL.match(d):
            continue
        linked = 0
        for name in names:
            src = breeze / d / f"{name}.svg"
            if src.exists():
                (ours / d).mkdir(parents=True, exist_ok=True)
                dest = ours / d / f"{name}.svg"
                if dest.exists() or dest.is_symlink():
                    dest.unlink()
                dest.symlink_to(src.resolve())
                linked += 1
        # Dedicated small line icon for ~/Orneos in Dolphin's Places sidebar
        if "@" not in d:
            sz = 16 if "/16" in d else 22
            (ours / d).mkdir(parents=True, exist_ok=True)
            (ours / d / "folder-orneos.svg").write_text(small_orneos_place(sz))
            linked += 1
        if linked:
            dirs.append((d, body.strip()))
    text = (ours / "index.theme").read_text()
    text = re.sub(r"^Directories=(.*)$", lambda m: "Directories=" + m.group(1) + "".join("," + d for d, _ in dirs), text, flags=re.M)
    text += "".join(f"\n[{d}]\n{body}\n" for d, body in dirs)
    (ours / "index.theme").write_text(text)
    (icons / "Orneos-dark/index.theme").write_text(dark_index(text))


def main():
    if sys.argv[1] == "--small":
        return link_small(Path(sys.argv[2]))
    theme = Path(sys.argv[1]) / "usr/share/icons/Orneos"
    for sub in ("apps/scalable", "places/scalable", "mimetypes/scalable", "actions/symbolic"):
        (theme / sub).mkdir(parents=True, exist_ok=True)
    (theme / "index.theme").write_text(INDEX)

    for i, (name, glyph) in enumerate(SYSTEM_APPS.items()):
        glyph = glyph if glyph is not None else SYSTEM_APPS[ALIASES[name]]
        (theme / "apps/scalable" / f"{name}.svg").write_text(tile(NIGHT, glyph, f"s{i}"))

    for i, (name, spec) in enumerate(SETTINGS_TILES.items()):
        if len(spec) == 1:
            ref = spec[0]
            if ref in SYSTEM_APPS:
                bg, glyph = NIGHT, SYSTEM_APPS[ref]
            else:
                bg, glyph = SETTINGS_TILES[ref]
        else:
            bg, glyph = spec
        (theme / "apps/scalable" / f"{name}.svg").write_text(tile(bg, glyph, f"c{i}"))

    # Kickoff's "Démarrer" icon on Fedora is start-here-kde. The top-bar menu uses the standalone
    # 3C Tri-Blade Prism (orneos-start / orneos-start-dark); app tiles use the Klein tile (orneos / start-here-kde).
    mark_tile = tile(KLEIN, START_GLYPH, "start")
    mark_light = standalone_mark(False)
    mark_dark = standalone_mark(True)
    ornis_tile = tile(KLEIN, ai_glyph(), "ornis")
    ornis_light = standalone_ornis(False)
    ornis_dark = standalone_ornis(True)
    apps = tile(KLEIN, APPS_GLYPH, "apps")
    hicolor = Path(sys.argv[1]) / "usr/share/icons/hicolor/scalable/apps"
    hicolor.mkdir(parents=True, exist_ok=True)
    for name in ("orneos", "start-here-kde", "start-here"):
        (theme / "apps/scalable" / f"{name}.svg").write_text(mark_tile)
        (hicolor / f"{name}.svg").write_text(mark_tile)
    for name in ("eu.orneos.ornis", "orneos-ornis"):
        (theme / "apps/scalable" / f"{name}.svg").write_text(ornis_tile)
        (hicolor / f"{name}.svg").write_text(ornis_tile)
    (theme / "apps/scalable/orneos-start.svg").write_text(mark_light)
    (hicolor / "orneos-start.svg").write_text(mark_light)
    (theme / "apps/scalable/orneos-start-dark.svg").write_text(mark_dark)
    (hicolor / "orneos-start-dark.svg").write_text(mark_dark)
    (theme / "apps/scalable/orneos-ornis-bar.svg").write_text(ornis_light)
    (hicolor / "orneos-ornis-bar.svg").write_text(ornis_light)
    (theme / "apps/scalable/orneos-ornis-bar-dark.svg").write_text(ornis_dark)
    (hicolor / "orneos-ornis-bar-dark.svg").write_text(ornis_dark)
    (theme / "apps/scalable/orneos-apps.svg").write_text(apps)
    (hicolor / "orneos-apps.svg").write_text(apps)

    for name, glyph in PLACES.items():
        glyph = glyph if glyph is not None else PLACES[PLACE_ALIASES[name]]
        (theme / "places/scalable" / f"{name}.svg").write_text(folder(glyph))
    (theme / "mimetypes/scalable/inode-directory.svg").write_text(folder(""))
    (theme / "places/scalable/folder-open.svg").write_text(folder(""))
    (theme / "places/scalable/user-trash.svg").write_text(trash(False))
    (theme / "places/scalable/user-trash-full.svg").write_text(trash(True))

    for name, d in WINDOW_BUTTONS.items():
        (theme / "actions/symbolic" / f"{name}-symbolic.svg").write_text(window_button(d))
    (theme / "actions/symbolic/plasma-symbolic.svg").write_text(symbolic_mark())

    for kind, names in MIME_MAP.items():
        accent, content_svg, bar_color = MIME_CONTENT[kind]
        svg = doc_sheet(accent, content_svg, kind, bar_color)
        for name in names:
            (theme / "mimetypes/scalable" / f"{name}.svg").write_text(svg)

    # Orneos-dark: the same files over Breeze Dark, with dark-surface standalone mark for orneos-start
    dark = theme.parent / "Orneos-dark"
    (dark / "apps/scalable").mkdir(parents=True, exist_ok=True)
    for svg_file in (theme / "apps/scalable").glob("*.svg"):
        dest = dark / "apps/scalable" / svg_file.name
        if dest.exists() or dest.is_symlink():
            dest.unlink()
        if svg_file.name == "orneos-start.svg":
            dest.write_text(mark_dark)
        elif svg_file.name == "orneos-ornis-bar.svg":
            dest.write_text(ornis_dark)
        else:
            dest.symlink_to(f"../../../Orneos/apps/scalable/{svg_file.name}")
    for sub in ("places", "mimetypes", "actions"):
        link = dark / sub
        if link.exists() or link.is_symlink():
            link.unlink()
        link.symlink_to(f"../Orneos/{sub}")
    (dark / "index.theme").write_text(dark_index(INDEX))


if __name__ == "__main__":
    main()
