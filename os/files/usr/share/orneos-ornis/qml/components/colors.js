// Colours that arrive as "#RRGGBB" strings (calendar colours from the cloud): the same hue, lighter.
.pragma library

function tint(hex, alpha) {
    const h = String(hex || "#002FA7").replace("#", "")
    const v = parseInt(h.length === 3 ? h.split("").map(x => x + x).join("") : h.slice(0, 6), 16)
    return Qt.rgba(((v >> 16) & 255) / 255, ((v >> 8) & 255) / 255, (v & 255) / 255, alpha)
}

// A calendar colour as shown: as is on light surfaces, lifted towards white on Nuit de Prusse so a
// Klein calendar stays readable.
function display(hex, dark) {
    if (!dark)
        return String(hex || "#002FA7")
    const base = tint(hex, 1)
    return Qt.rgba(base.r + (1 - base.r) * 0.38, base.g + (1 - base.g) * 0.38, base.b + (1 - base.b) * 0.38, 1)
}
