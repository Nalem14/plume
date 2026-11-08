.pragma library
// ornis-tokens:begin (generated from design/tokens.json by tools/design-tokens.py, do not edit)
// Ornis tokens for QML: import "file:///usr/share/orneos/widgets-qml/ornis.js" as Ornis,
// then Ornis.palette(dark).action, Ornis.family("organize", dark), Ornis.t.radius.card.
var t = {
    "brand": {
        "klein": "#002FA7",
        "prusse": "#0F2440",
        "brume": "#F5F6F9",
        "safran": "#F0A202",
        "vert_de_gris": "#2F7D6D",
        "vermillon": "#C8381E",
        "nuit": "#0A1424"
    },
    "families": {
        "communicate": {
            "name": "Klein",
            "light": "#002FA7",
            "dark": "#8A9EFF"
        },
        "docs": {
            "name": "Vert-de-gris",
            "light": "#2F7D6D",
            "dark": "#5CC2AC"
        },
        "organize": {
            "name": "Safran",
            "light": "#8A5A00",
            "dark": "#F2B13A"
        },
        "media": {
            "name": "Teal",
            "light": "#1A5F7A",
            "dark": "#7EB8CC"
        },
        "tools": {
            "name": "Prusse",
            "light": "#0F2440",
            "dark": "#C5D0E6"
        },
        "space": {
            "name": "Prune",
            "light": "#7A3B6E",
            "dark": "#DDA8D3"
        }
    },
    "radius": {
        "control": 6,
        "card": 10
    },
    "motion": {
        "fast_ms": 140,
        "ease": "cubic-bezier(.2,.7,.2,1)"
    },
    "desktop": {
        "veil": 0.6,
        "glass": {
            "panel": 0.5,
            "popup": 0.74,
            "menu": 0.76,
            "toolbar": 0.78,
            "titlebar": 0.78,
            "sidebar": 0.6,
            "terminal": 0.82,
            "blur": 10
        },
        "widget_radius": 10,
        "ring": {
            "open_deg": 80,
            "day_start": 8,
            "day_end": 20
        }
    },
    "light": {
        "chrome": "#EDF0F5",
        "bg": "#F5F6F9",
        "card": "#FFFFFF",
        "line": "#E1E5EE",
        "hairline": "#E9ECF2",
        "text": "#0F2440",
        "body": "#0F2440",
        "muted": "#5B6B82",
        "faint": "#637289",
        "action": "#002FA7",
        "actionHover": "#00238A",
        "actionText": "#FFFFFF",
        "tint": "#DCE3F7",
        "tintText": "#002FA7",
        "accent": "#002FA7",
        "accentLine": "#C9D3EC",
        "hover": "#E4E8F0",
        "field": "#FFFFFF",
        "rail": "#002FA7",
        "railText": "#FFFFFF",
        "railMark": "#FFFFFF",
        "railMarkText": "#002FA7",
        "saffron": "#F0A202",
        "saffronText": "#0F2440",
        "saffronTint": "#FDF1D6",
        "saffronInk": "#7A5200",
        "ok": "#2F7D6D",
        "okTint": "#E2F1EE",
        "okInk": "#1F5A4D",
        "danger": "#C8381E",
        "dangerTint": "#FBE7E3",
        "overlay": "#FFFFFF",
        "overlayLine": "#D5DBE6",
        "shadow": "#290F2440",
        "scrim": "#660A1424",
        "tag1": "#C8381E",
        "tag2": "#002FA7",
        "tag3": "#2F7D6D",
        "tag4": "#E09600",
        "tag5": "#6E5BB8",
        "famCommunicate": "#002FA7",
        "famDocs": "#2F7D6D",
        "famOrganize": "#8A5A00",
        "famMedia": "#1A5F7A",
        "famTools": "#0F2440",
        "famSpace": "#7A3B6E",
        "elev": "#240F2440",
        "elevEdge": "#00FFFFFF"
    },
    "dark": {
        "chrome": "#0A1424",
        "bg": "#0A1424",
        "card": "#101D33",
        "line": "#1E2E4A",
        "hairline": "#1A2840",
        "text": "#E8ECF3",
        "body": "#DDE3EE",
        "muted": "#9AA8BF",
        "faint": "#77859C",
        "action": "#7D93FF",
        "actionHover": "#9AABFF",
        "actionText": "#0A1424",
        "tint": "#1B2C55",
        "tintText": "#C3CEFF",
        "accent": "#9AABFF",
        "accentLine": "#2A3D6B",
        "hover": "#16233A",
        "field": "#0D1A2E",
        "rail": "#0A2A8C",
        "railText": "#FFFFFF",
        "railMark": "#E8ECF3",
        "railMarkText": "#0A2A8C",
        "saffron": "#F0A202",
        "saffronText": "#0A1424",
        "saffronTint": "#3A2C0C",
        "saffronInk": "#F5C04A",
        "ok": "#5FC2AC",
        "okTint": "#123129",
        "okInk": "#8FDCC9",
        "danger": "#FF7A5C",
        "dangerTint": "#3A1A16",
        "overlay": "#132240",
        "overlayLine": "#2A3B5C",
        "shadow": "#80000000",
        "scrim": "#99050A12",
        "tag1": "#FF7A5C",
        "tag2": "#7D93FF",
        "tag3": "#5FC2AC",
        "tag4": "#F0A202",
        "tag5": "#A897F0",
        "famCommunicate": "#8A9EFF",
        "famDocs": "#5CC2AC",
        "famOrganize": "#F2B13A",
        "famMedia": "#7EB8CC",
        "famTools": "#C5D0E6",
        "famSpace": "#DDA8D3",
        "elev": "#A0000000",
        "elevEdge": "#14FFFFFF"
    }
};
function palette(dark) { return dark ? t.dark : t.light; }
function family(key, dark) { const f = t.families[key] || t.families.tools; return dark ? f.dark : f.light; }
// ornis-tokens:end
