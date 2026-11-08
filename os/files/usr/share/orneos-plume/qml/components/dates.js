// Date helpers for the calendar: local days, ISO strings for Python, Monday-first weeks.
.pragma library

function startOfDay(d) { return new Date(d.getFullYear(), d.getMonth(), d.getDate()) }
function addDays(d, n) { return new Date(d.getFullYear(), d.getMonth(), d.getDate() + n, d.getHours(), d.getMinutes()) }
function addMonths(d, n) { return new Date(d.getFullYear(), d.getMonth() + n, 1) }
function startOfWeek(d) { const s = startOfDay(d); return addDays(s, -((s.getDay() + 6) % 7)) }
function startOfMonth(d) { return new Date(d.getFullYear(), d.getMonth(), 1) }
function sameDay(a, b) { return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate() }
function pad(n) { return (n < 10 ? "0" : "") + n }
function iso(d) { return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()) }
function isoLocal(d) { return iso(d) + "T" + pad(d.getHours()) + ":" + pad(d.getMinutes()) }
function hm(d) { return pad(d.getHours()) + ":" + pad(d.getMinutes()) }
function minutes(d) { return d.getHours() * 60 + d.getMinutes() }
function withTime(day, text) {
    const parts = String(text).split(":")
    return new Date(day.getFullYear(), day.getMonth(), day.getDate(), parseInt(parts[0]) || 0, parseInt(parts[1]) || 0)
}
function weekNumber(d) {
    const t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()))
    const day = t.getUTCDay() || 7
    t.setUTCDate(t.getUTCDate() + 4 - day)
    const yearStart = new Date(Date.UTC(t.getUTCFullYear(), 0, 1))
    return Math.ceil(((t - yearStart) / 86400000 + 1) / 7)
}
function capitalize(s) { return s ? s.charAt(0).toUpperCase() + s.slice(1) : s }

// Side-by-side columns for overlapping events of one day: each item gets col and cols.
function layoutDay(items) {
    const sorted = items.slice().sort((a, b) => a.top - b.top || b.height - a.height)
    let cluster = [], clusterEnd = -1, columns = []
    const out = []
    function flush() {
        for (const it of cluster) it.cols = columns.length
        cluster = []; columns = []
    }
    for (const it of sorted) {
        if (it.top >= clusterEnd && cluster.length) flush()
        let placed = false
        for (let i = 0; i < columns.length; ++i) {
            if (columns[i] <= it.top) { it.col = i; columns[i] = it.top + it.height; placed = true; break }
        }
        if (!placed) { it.col = columns.length; columns.push(it.top + it.height) }
        cluster.push(it); out.push(it)
        clusterEnd = Math.max(clusterEnd, it.top + it.height)
    }
    flush()
    return out
}
